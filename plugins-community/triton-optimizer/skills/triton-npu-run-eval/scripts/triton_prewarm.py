# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Opt-in Triton kernel pre-warming for differential run-test and run-bench.

When HELIX_PREWARM_TRITON=1, differential run-test runs and run-bench runs
with more than one case dry-run every case fn once before the real
execution, intercepting Triton's launch entrypoint (``JITFunction.run``) to
record each call's kernel, args, kwargs, and grid without compiling or
launching.  Each case's recorded calls are replayed through
``kernel.warmup(...)`` under ``triton.AsyncCompileMode`` on a bounded
thread pool right after that case's dry run, so first-sight compiles run
in parallel and land in TRITON_CACHE_DIR before the measured run starts.

The pass is a per-case pipeline: clone inputs -> dry-run under the recorder
patch -> restore random state and inputs -> (first case: cache-warm probe,
taken outside the async mode so it measures a real synchronous compile)
-> submit the case's warmups -> drop its records.  Peak memory is one case's
tensors plus the in-flight compile tasks, never the whole run's captures.

Side-effect contract: capture executes each case fn's non-Triton code one
extra time.  The random state of every generator a case fn may draw from
(Python ``random``, torch CPU, torch NPU) is saved before each case's dry
run and restored after, so the measured run draws the same inputs as a
no-prewarm run; case inputs are cloned before the dry run and restored in
place after, so in-place operators see clean tensors in the real run —
inputs whose mutable leaves cannot be cloned (anything beyond tensors,
numpy arrays, containers, and immutable scalars) skip prewarm for that
case, and inputs the dry run restructured beyond recovery fail the run
explicitly; case-fn output is suppressed; a case that raises loses all of
its records.  Any other side effect persists and happens twice — see the
design contract in
docs/notes/implemented/2026-09-03-run-eval-differential-prewarm-and-inprocess-deferred-parse.md

Run-bench callers pair each case fn with ``None`` inputs (the bench
contract closes over inputs without exposing them), so clone/restore is a
no-op there and dry-run input mutations persist — sound only because bench
never compares values.  See
docs/notes/implemented/2026-09-08-run-bench-triton-prewarm.md
"""

from __future__ import annotations

import importlib
import os
import random
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from contextvars import ContextVar
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, NamedTuple, Optional, Protocol, cast

from env_registry import (
    HELIX_EVAL_TIMEOUT_SECONDS,
    HELIX_PREWARM_TRITON,
    HELIX_PREWARM_WORKERS,
    TRITON_AUTOTUNE_PARALLEL_COMPILE,
    prewarm_enabled,
)
from run_runtime import eval_timeout_seconds

_BUDGET_CAP_SECONDS = 600.0
_PROBE_WARM_THRESHOLD_SECONDS = 3.0
_WORKERS_FLOOR = 8
_WORKERS_CAP = 32

# Process-level prewarm deadline: anchored on first entry and reused by
# later ones (e.g. baseline and candidate passes share one process), so a
# second pass whose budget is already spent skips prewarm instead of
# eating the next evaluation's wall-clock again.
_process_deadline: Optional[float] = None

# Test seam: lets tests drive the deadline without patching the shared
# stdlib time module.
_monotonic = time.monotonic

# Immutable leaves cannot be mutated by a dry run, so they never need a
# restore clone.
_IMMUTABLE_INPUT_TYPES = (bool, int, float, complex, str, bytes, type(None))


class _CapturedCall(NamedTuple):
    kernel: Any
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    grid: Any


class _RandomStateSnapshot(NamedTuple):
    """Saved state of every random source a case fn may draw from.

    Capture executes the case fns' real code (e.g. ``torch.randn`` for
    input generation), which advances the random streams.  Without a
    restore, the measured run afterwards would draw *different* inputs
    than a run without prewarm — silently changing what a differential
    test compares.  Snapshotting before capture and restoring after makes
    the random stream identical to a no-prewarm run.
    """

    python_state: Any
    torch_cpu: Any
    npu_all: Optional[Any]


class _InputRestoreError(RuntimeError):
    """Raised when capture-mutated case inputs cannot be restored."""


def _max_workers() -> int:
    raw = os.environ.get(HELIX_PREWARM_WORKERS)
    if raw is not None:
        try:
            override = int(raw)
        except ValueError as exc:
            raise ValueError(
                f"{HELIX_PREWARM_WORKERS} must be a positive integer, got {raw!r}"
            ) from exc
        if override <= 0:
            raise ValueError(
                f"{HELIX_PREWARM_WORKERS} must be a positive integer, got {raw!r}"
            )
        return min(override, _WORKERS_CAP)
    cpu_count = os.cpu_count() or 2
    # Up to 64 cores this reproduces the historical min(8, cpu_count // 2)
    # exactly; larger hosts scale linearly up to the cap.
    return min(_WORKERS_CAP, max(min(_WORKERS_FLOOR, cpu_count // 2), cpu_count // 8))


def reset_prewarm_budget() -> None:
    """Re-anchor the process-level prewarm deadline.

    Logically separate evaluations sharing one process (the single-worker
    differential flow's reference and candidate phases) each get a full
    submission budget; entries within one evaluation keep sharing the
    anchored deadline.
    """
    global _process_deadline
    _process_deadline = None


def _budget_seconds() -> float:
    timeout = eval_timeout_seconds()
    if timeout == 0:
        return _BUDGET_CAP_SECONDS
    return min(_BUDGET_CAP_SECONDS, timeout / 2)


class _ProgressEmitter(Protocol):
    """What maybe_prewarm_case_fns needs from a worker runtime: the locked
    protocol-progress entry point. Structural, so the runtime itself and test
    recorders both satisfy it without importing the protocol stack here.
    """

    def emit_progress(self, event: str, **detail: object) -> None:
        ...


# Reporting seam for one prewarm pass: when maybe_prewarm_case_fns is given
# an emitter, _warn routes each message through it as a protocol progress
# event instead of the stderr print, so supervised runs surface prewarm
# output. All reporting happens on the calling thread; the warmup pool
# never reports. _prewarm_label carries the caller's command name into the
# message prefix ("run-test" for differential runs, "run-bench" for bench).
# Each event carries a level: "warning" for degradations (surfaced live by
# supervised parents in every mode), "info" for happy-path lines (visible
# only when the raw worker stream is forwarded, e.g. --verbose).
_prewarm_emitter: "Optional[_ProgressEmitter]" = None
_prewarm_label: str = "run-test"


def _report(message: str, *, level: str) -> None:
    text = f"[{_prewarm_label}] triton prewarm: {message}"
    emitter = _prewarm_emitter
    if emitter is not None:
        emitter.emit_progress("prewarm", message=text, level=level)
        return
    print(text, file=sys.stderr, flush=True)


def _warn(message: str) -> None:
    """Report a prewarm degradation (supervised parents surface it live)."""
    _report(message, level="warning")


def _info(message: str) -> None:
    """Report a happy-path line (visible only when the raw stream is forwarded)."""
    _report(message, level="info")


def _load_triton_module() -> Any:
    """Import triton dynamically (absent in type-check environments)."""
    return importlib.import_module("triton")


def _load_jit_function() -> Any:
    jit = getattr(importlib.import_module("triton.runtime"), "jit")
    return jit.JITFunction


def _load_autotuner_class() -> Optional[Any]:
    """Return Triton's autotuner class when this installation exposes it."""
    try:
        return importlib.import_module("triton.runtime.autotuner").Autotuner
    except (ImportError, AttributeError):
        return None


def prewarm_available() -> bool:
    """Probe the installed Triton for the API surface this feature needs."""
    try:
        triton = _load_triton_module()
        jit_function = _load_jit_function()
        if getattr(triton, "AsyncCompileMode", None) is None:
            return False
        import inspect

        params = list(inspect.signature(jit_function.run).parameters)
        return "grid" in params and "warmup" in params and hasattr(jit_function, "warmup")
    except (ImportError, AttributeError):
        return False


def _numpy_module() -> Any:
    """Return the numpy module, or None where it is not importable."""
    try:
        return importlib.import_module("numpy")
    except ImportError:
        return None


@contextmanager
def _suppressed_output() -> Iterator[None]:
    sink = StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        yield


@contextmanager
def _autotune_parallel_compile() -> Iterator[None]:
    """Enable Triton's own parallel autotune compilation during prewarm.

    Scoped to the warmup phase and restored afterwards, so a value the
    user set for the real run is never clobbered.
    """
    previous = os.environ.get(TRITON_AUTOTUNE_PARALLEL_COMPILE)
    os.environ[TRITON_AUTOTUNE_PARALLEL_COMPILE] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(TRITON_AUTOTUNE_PARALLEL_COMPILE, None)
        else:
            os.environ[TRITON_AUTOTUNE_PARALLEL_COMPILE] = previous


def _snapshot_random_state() -> _RandomStateSnapshot:
    """Save Python/torch random state; raise when NPU state is unsaveable.

    A torch without ``torch.npu`` has no NPU random generator to protect.
    A torch whose NPU interface cannot snapshot/restore its generator
    makes the capture's random stream unrecoverable, which the caller
    treats as a skip-with-warning.
    """
    import torch

    npu_all = None
    npu = getattr(torch, "npu", None)
    if npu is not None:
        get_all = getattr(npu, "get_rng_state_all", None)
        set_all = getattr(npu, "set_rng_state_all", None)
        if not callable(get_all) or not callable(set_all):
            raise RuntimeError("torch.npu lacks get/set_rng_state_all")
        npu_all = get_all()
    return _RandomStateSnapshot(random.getstate(), torch.get_rng_state(), npu_all)


def _restore_random_state(state: _RandomStateSnapshot) -> None:
    import torch

    random.setstate(state.python_state)
    torch.set_rng_state(state.torch_cpu)
    npu = getattr(torch, "npu", None)
    if state.npu_all is not None and npu is not None:
        npu.set_rng_state_all(state.npu_all)


def _clone_case_inputs(value: object) -> object:
    """Deep-clone one case's inputs for in-place restore after the dry run.

    Unlike the archive snapshot (which passes unknown types through by
    reference), the restore clone must be able to undo every mutable leaf:
    tensors are detached/cloned, numpy arrays are copied, containers are
    rebuilt recursively, and any other mutable type raises so the caller
    skips prewarm for that case instead of silently failing to restore.
    """
    import torch

    if isinstance(value, torch.Tensor):
        return value.detach().clone()
    numpy = _numpy_module()
    if numpy is not None and isinstance(value, numpy.ndarray):
        return numpy.array(value, copy=True)
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        return tuple(_clone_case_inputs(item) for item in items)
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [_clone_case_inputs(item) for item in items]
    if isinstance(value, Mapping):
        entries = cast(Mapping[object, object], value)
        return {key: _clone_case_inputs(item) for key, item in entries.items()}
    if isinstance(value, _IMMUTABLE_INPUT_TYPES):
        return value
    raise RuntimeError(
        f"case input of type {type(value).__name__} cannot be cloned for restore"
    )


def _restore_tensor_tree(original: object, clone: object) -> None:
    """Copy cloned values back into the original case inputs in place.

    In-place restore keeps every holder of the original tensor objects
    (case closures, the real run's own archive snapshot) reading clean
    values.  Structural divergence (shape, mapping keys, sequence length,
    leaf type) means the case fn rebuilt or replaced its inputs, which
    cannot be restored.  Immutable scalar inputs cannot be mutated by the
    dry run and are skipped; any other unrecognized pair raises instead of
    being silently left polluted.
    """
    import torch

    if isinstance(original, torch.Tensor) and isinstance(clone, torch.Tensor):
        if original.shape != clone.shape:
            raise RuntimeError(
                f"input tensor shape changed during capture "
                f"({tuple(clone.shape)} -> {tuple(original.shape)})"
            )
        with torch.no_grad():
            original.copy_(clone)
        return
    numpy = _numpy_module()
    if (
        numpy is not None
        and isinstance(original, numpy.ndarray)
        and isinstance(clone, numpy.ndarray)
    ):
        original_array = cast(Any, original)
        clone_array = cast(Any, clone)
        if original_array.shape != clone_array.shape:
            raise RuntimeError(
                f"input array shape changed during capture "
                f"({clone_array.shape} -> {original_array.shape})"
            )
        numpy.copyto(original_array, clone_array)
        return
    if isinstance(original, Mapping) and isinstance(clone, Mapping):
        original_mapping = cast(Mapping[object, object], original)
        clone_mapping = cast(Mapping[object, object], clone)
        if set(original_mapping.keys()) != set(clone_mapping.keys()):
            raise RuntimeError("input mapping keys changed during capture")
        for key in original_mapping:
            _restore_tensor_tree(original_mapping[key], clone_mapping[key])
        return
    if isinstance(original, (list, tuple)) and isinstance(clone, (list, tuple)):
        original_seq = cast(Sequence[object], original)
        clone_seq = cast(Sequence[object], clone)
        if len(original_seq) != len(clone_seq):
            raise RuntimeError("input sequence length changed during capture")
        for original_item, clone_item in zip(original_seq, clone_seq):
            _restore_tensor_tree(original_item, clone_item)
        return
    if isinstance(original, _IMMUTABLE_INPUT_TYPES) and isinstance(clone, _IMMUTABLE_INPUT_TYPES):
        return
    raise RuntimeError(
        f"input leaf changed during capture "
        f"({type(cast(Any, clone)).__name__} -> {type(cast(Any, original)).__name__})"
    )


def _restore_case_inputs(inputs: object, clone: object) -> None:
    """Restore one case's inputs mutated by the capture dry run.

    Raises _InputRestoreError when the inputs cannot be restored: the real
    run would otherwise start from polluted tensors and produce silently
    wrong results, so an explicit failure beats any fallback.
    """
    try:
        _restore_tensor_tree(inputs, clone)
    except Exception as exc:
        raise _InputRestoreError(
            f"triton prewarm capture mutated case inputs beyond recovery "
            f"({type(exc).__name__}: {exc}); "
            f"disable {HELIX_PREWARM_TRITON} and rerun"
        ) from exc


def _capture_case_fn(case_fn: Callable[[], object]) -> Optional[list[_CapturedCall]]:
    """Dry-run one case fn under the recorder patch; None when it raises.

    The recorder returns without compiling or launching, so no real kernel
    launch happens during capture.  The patch is active only for the dry
    run: warmup submissions later in the pass must find the real
    ``JITFunction.run`` (their ``warmup=True`` calls would otherwise be
    swallowed by the recorder).  A fn that raises loses all of its records;
    earlier cases keep theirs.
    """
    jit_function = _load_jit_function()
    original_run = getattr(jit_function, "run")
    autotuner_class = _load_autotuner_class()
    original_autotuner_run = (
        getattr(autotuner_class, "run", None) if autotuner_class is not None else None
    )
    records: list[_CapturedCall] = []

    def _recording_run(self: Any, *args: Any, grid: Any, warmup: bool = False, **kwargs: Any) -> None:
        if not warmup:
            records.append(_CapturedCall(self, args, dict(kwargs), grid))
        return None

    def _capture_autotuner_run(self: Any, *args: Any, **kwargs: Any) -> Any:
        """Capture each config once without retaining synthetic timing state."""
        if original_autotuner_run is None:
            raise RuntimeError("internal error: autotuner capture installed without the original run")
        attributes = cast("dict[str, Any]", vars(self))
        state = dict(attributes)
        benchmark_records = 0

        def _capture_once(kernel_call: Callable[[], Any], quantiles: object) -> list[float]:
            nonlocal benchmark_records
            del quantiles
            before = len(records)
            kernel_call()
            benchmark_records += len(records) - before
            return [0.0, 0.0, 0.0]

        self.cache = dict(self.cache)
        self.do_bench = _capture_once
        try:
            before = len(records)
            result = original_autotuner_run(self, *args, **kwargs)
            if len(records) - before == benchmark_records + 1:
                records.pop()  # Drop the synthetic winner launch.
            return result
        finally:
            attributes.clear()
            attributes.update(state)

    setattr(jit_function, "run", _recording_run)
    if autotuner_class is not None and original_autotuner_run is not None:
        setattr(autotuner_class, "run", _capture_autotuner_run)
    try:
        with _suppressed_output():
            case_fn()
    except Exception:
        return None
    finally:
        if autotuner_class is not None and original_autotuner_run is not None:
            setattr(autotuner_class, "run", original_autotuner_run)
        setattr(jit_function, "run", original_run)
    return records


def _cache_warm_probe(record: _CapturedCall) -> bool:
    """Heuristic: warm one captured record synchronously.

    Must be called outside any AsyncCompileMode: inside it, warmup only
    enqueues onto the pool and returns in milliseconds, so every probe
    would report "cache warm".  Outside it, a disk-cache hit returns in
    milliseconds while a real compile takes seconds to tens of seconds,
    so a fast probe means the shared TRITON_CACHE_DIR already holds this
    run's kernels and the parallel pass can be skipped.  Both
    misjudgments are cheap: a false "warm" defers compiles to the real
    run (the un-warmed behavior), a false "cold" runs a pass that mostly
    hits the disk cache.
    """
    try:
        t0 = time.monotonic()
        record.kernel.warmup(*record.args, grid=record.grid, **record.kwargs)
        return time.monotonic() - t0 < _PROBE_WARM_THRESHOLD_SECONDS
    except Exception:
        return False


@contextmanager
def _safe_async_compile_mode(async_mode_cls: Any, pool: Any) -> Iterator[Any]:
    """Enter AsyncCompileMode and recover from an exit-time compile failure.

    triton-ascend clears the active mode only after its exit-time finalize
    loop; a compile failure at exit would otherwise leave the mode bound
    to the now-shut-down executor, and every later cache-miss kernel
    launch would raise "cannot schedule new futures after shutdown" —
    failing runs that should merely degrade to the un-warmed flow.  The
    caller drains every captured future after an ordinary exit failure;
    process-control exceptions still propagate.
    """
    mode = async_mode_cls(pool)
    mode.__enter__()
    try:
        yield mode
    finally:
        try:
            mode.__exit__(*sys.exc_info())
        except Exception as exc:
            _clear_stale_async_mode(mode)
            _warn(
                f"async compile exit reported {type(exc).__name__}; "
                "draining captured compiles individually"
            )
        except BaseException:
            _clear_stale_async_mode(mode)
            raise


def _clear_mode_in_module(module: object, mode: Any) -> tuple[bool, list[str]]:
    """Clear the mode binding in one module; return (cleared, failed entries)."""
    cleared = False
    failures: list[str] = []
    for name, value in list(vars(module).items()):
        if value is mode:
            try:
                setattr(module, name, None)
                cleared = True
            except Exception:
                failures.append(name)
        elif isinstance(value, ContextVar):
            context_var = cast("ContextVar[Any]", value)
            if _clear_context_var(context_var, mode, name, failures):
                cleared = True
    return cleared, failures


def _clear_context_var(
    context_var: "ContextVar[Any]", mode: Any, name: str, failures: list[str]
) -> bool:
    try:
        if context_var.get() is mode:
            context_var.set(None)
            return True
    except (LookupError, TypeError) as exc:
        failures.append(f"{name} ({exc})")
    return False


def _clear_stale_async_mode(mode: Any) -> None:
    """Remove a stale AsyncCompileMode binding, found by identity.

    Triton versions store the private active mode either directly in a
    module-level global or inside a ContextVar. Scan the plausible runtime
    modules for the exact mode instance instead of depending on one name.
    """
    cleared = False
    failures: list[str] = []
    for module_name in ("triton.runtime._async_compile", "triton.runtime", "triton.runtime.jit"):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        module_cleared, module_failures = _clear_mode_in_module(module, mode)
        cleared = cleared or module_cleared
        failures.extend(module_failures)
    if not cleared:
        detail = f" (failed entries: {', '.join(failures)})" if failures else ""
        _warn(
            "could not clear a stale AsyncCompileMode; "
            "later compiles may fail in this process" + detail
        )


def _is_future_like(value: object) -> bool:
    return value is not None and callable(getattr(value, "result", None))


def _drain_pending(pending: list[Any]) -> tuple[int, int]:
    """Collect final compile outcomes from future-like warmup results.

    Under AsyncCompileMode a successful submission only enqueues the
    compile; its real outcome surfaces when the future's result is read
    after the mode has exited and the pool has drained.
    """
    warmed = failed = 0
    for future in pending:
        try:
            future.result()
            warmed += 1
        except Exception as exc:
            failed += 1
            _warn(f"one captured compile failed ({type(exc).__name__}: {exc})")
    return warmed, failed


def _submit_case_records(records: list[_CapturedCall], deadline: float) -> tuple[int, int, int, list[Any]]:
    """Warm one case's captured records with their original args and grid.

    No Helix-side dedup: duplicate warmups are absorbed by Triton's own
    cache.  Records are submitted until the deadline.  A submission whose
    warmup returns a future (the AsyncCompileMode behavior) is not yet a
    successful compile — its outcome is collected by _drain_pending after
    the mode exits.  Returns (warmed, failed, skipped, pending_futures).
    """
    warmed = failed = skipped = 0
    pending: list[Any] = []
    for record in records:
        if _monotonic() >= deadline:
            skipped += 1
            continue
        try:
            result = record.kernel.warmup(*record.args, grid=record.grid, **record.kwargs)
        except Exception as exc:
            failed += 1
            _warn(
                f"one captured call failed to submit "
                f"({type(exc).__name__}: {exc}); skipped"
            )
            continue
        if _is_future_like(result):
            pending.append(result)
        else:
            warmed += 1
    return warmed, failed, skipped, pending


def maybe_prewarm_case_fns(
    cases: "Iterable[tuple[Callable[[], object], object]]",
    *,
    emit: "Optional[_ProgressEmitter]" = None,
    label: str = "run-test",
) -> None:
    """Stream the case fns through capture + parallel-compile.

    ``cases`` pairs each case fn with its inputs (the same objects the fn
    closes over).  No-op unless HELIX_PREWARM_TRITON=1 and more than one
    case is given.  ``emit``, when given, routes every prewarm message
    through ``emit.emit_progress("prewarm", message=...)``; without it the
    messages go to stderr.  ``label`` is the command name used in the
    message prefix (``run-test`` for differential runs, ``run-bench`` for
    bench runs).  Failures degrade to a warning and the normal (un-warmed)
    flow, with one exception: if capture mutated case inputs and they
    cannot be restored, _InputRestoreError is raised — the real run would
    otherwise start from polluted inputs and silently produce wrong
    results.

    Callers whose case contract does not expose the fn's inputs (run-bench
    case closures) pass ``None`` as the inputs: clone/restore then no-op,
    so dry-run mutations of closure-captured tensors persist into the
    measured run.  That is only sound where the run never compares values
    (bench times executions); the per-case RNG snapshot/restore still
    applies either way.
    """
    pairs = list(cases)
    if not prewarm_enabled() or len(pairs) <= 1:
        return
    global _prewarm_emitter, _prewarm_label
    previous_emitter = _prewarm_emitter
    previous_label = _prewarm_label
    _prewarm_emitter = emit
    _prewarm_label = label
    try:
        _run_prewarm_pass(pairs)
    finally:
        _prewarm_emitter = previous_emitter
        _prewarm_label = previous_label


@dataclass
class _CasePrewarmOutcome:
    """One case's contribution to the prewarm pass totals."""

    captured: int = 0
    warmed: int = 0
    failed: int = 0
    skipped: int = 0
    pending: list[Any] = field(default_factory=list)
    case_failed: bool = False
    probed: bool = False
    warm_cache_abort: bool = False


@dataclass
class _PassTotals:
    """Aggregated prewarm pass counters."""

    captured: int = 0
    warmed: int = 0
    failed: int = 0
    skipped: int = 0
    failed_cases: int = 0
    uncaptured: int = 0
    pending: list[Any] = field(default_factory=list)
    warm_cache_abort: bool = False

    def absorb(self, outcome: _CasePrewarmOutcome) -> None:
        self.captured += outcome.captured
        self.warmed += outcome.warmed
        self.failed += outcome.failed
        self.skipped += outcome.skipped
        self.pending.extend(outcome.pending)
        if outcome.case_failed:
            self.failed_cases += 1


def _prewarm_one_case(
    fn: Callable[[], object],
    inputs: object,
    *,
    probed: bool,
    async_compile_mode: Any,
    pool: ThreadPoolExecutor,
    modes: ExitStack,
    deadline: float,
) -> _CasePrewarmOutcome:
    outcome = _CasePrewarmOutcome(probed=probed)
    try:
        random_state = _snapshot_random_state()
        clone = _clone_case_inputs(inputs)
    except Exception as exc:
        _warn(
            f"cannot snapshot execution state for one case "
            f"({type(exc).__name__}: {exc}); case skipped"
        )
        return outcome
    try:
        records = _capture_case_fn(fn)
    finally:
        try:
            _restore_random_state(random_state)
        except Exception as exc:
            _warn(f"random state restore failed ({type(exc).__name__}: {exc})")
        _restore_case_inputs(inputs, clone)
    if records is None:
        outcome.case_failed = True
        _warn(
            "one case dry run raised; its kernels are not prewarmed "
            "(the case still runs normally)"
        )
        return outcome
    outcome.captured = len(records)
    if records and not probed:
        outcome.probed = True
        # The probe measures a synchronous compile, so it must run before the
        # async mode is entered.
        if _cache_warm_probe(records[0]):
            outcome.warm_cache_abort = True
            return outcome
        modes.enter_context(_safe_async_compile_mode(async_compile_mode, pool))
        modes.enter_context(_autotune_parallel_compile())
    case_warmed, case_failed, case_skipped, case_pending = _submit_case_records(records, deadline)
    outcome.warmed = case_warmed
    outcome.failed = case_failed
    outcome.skipped = case_skipped
    outcome.pending = case_pending
    # Drop this case's records now: the next case's dry run must not keep the
    # previous case's argument tensors (captured intermediates included) alive.
    return outcome


def _capture_and_submit_cases(
    pairs: "list[tuple[Callable[[], object], object]]",
    *,
    deadline: float,
    async_compile_mode: Any,
    pool: ThreadPoolExecutor,
) -> _PassTotals:
    totals = _PassTotals()
    probed = False
    with ExitStack() as modes:
        for index, (fn, inputs) in enumerate(pairs):
            if _monotonic() >= deadline:
                totals.uncaptured = len(pairs) - index
                break
            outcome = _prewarm_one_case(
                fn,
                inputs,
                probed=probed,
                async_compile_mode=async_compile_mode,
                pool=pool,
                modes=modes,
                deadline=deadline,
            )
            totals.absorb(outcome)
            probed = outcome.probed
            if outcome.warm_cache_abort:
                totals.warm_cache_abort = True
                break
    return totals


def _warn_budget_exhausted(totals: _PassTotals) -> None:
    _warn(
        f"prewarm budget exhausted mid-pass: {totals.uncaptured} case(s) not dry-run, "
        f"{totals.skipped} captured compile(s) left unsubmitted; those kernels "
        f"compile serially in the real run "
        f"(budget derives from {HELIX_EVAL_TIMEOUT_SECONDS})"
    )


def _run_prewarm_pass(pairs: "list[tuple[Callable[[], object], object]]") -> None:
    if not prewarm_available():
        _warn("disabled: installed Triton does not expose the expected warmup API")
        return
    global _process_deadline
    try:
        if _process_deadline is None:
            _process_deadline = _monotonic() + _budget_seconds()
    except Exception as exc:
        _warn(
            f"cannot derive the prewarm budget from {HELIX_EVAL_TIMEOUT_SECONDS} "
            f"({type(exc).__name__}: {exc}); skipping prewarm"
        )
        return
    deadline = _process_deadline
    if _monotonic() >= deadline:
        _warn(
            "prewarm budget already exhausted in this process; "
            "skipping (the real run compiles as usual)"
        )
        return
    triton = _load_triton_module()
    async_compile_mode = getattr(triton, "AsyncCompileMode")
    exit_error = False
    with ThreadPoolExecutor(max_workers=_max_workers()) as pool:
        try:
            totals = _capture_and_submit_cases(
                pairs,
                deadline=deadline,
                async_compile_mode=async_compile_mode,
                pool=pool,
            )
            if totals.warm_cache_abort:
                _info(f"captured={totals.captured}; cache warm, parallel pass skipped")
                return
            # The async mode has exited and in-flight compiles drained, so the
            # futures now carry final compile outcomes.
            drained_warmed, drained_failed = _drain_pending(totals.pending)
            totals.warmed += drained_warmed
            totals.failed += drained_failed
            if totals.uncaptured or totals.skipped:
                _warn_budget_exhausted(totals)
        except _InputRestoreError:
            raise
        except Exception as exc:
            exit_error = True
            _warn(f"compile pass reported errors ({type(exc).__name__}: {exc})")
    _info(
        f"captured={totals.captured} warmed={totals.warmed} failed={totals.failed} skipped={totals.skipped}"
        + (f" case-capture-failures={totals.failed_cases}" if totals.failed_cases else "")
        + (" pass-exit-error" if exit_error else "")
    )
