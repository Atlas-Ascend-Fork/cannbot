# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import argparse
from collections import deque
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
import importlib
import importlib.util
import json
import os
import queue
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, cast

from bench_contract import KernelResolution, resolve_bench_kernel_resolution
import analyse_service  # noqa: F401  # pyright: ignore[reportUnusedImport] (staged for remote runs by importing it)
from ascendc_runtime import build_ascendc_operator, is_ascendc_operator
from env_registry import (
    HELIX_BENCH_OUTPUT_DIR,
    bench_defer_parse_enabled,
    bench_output_dir,
)
from run_runtime import eval_timeout_seconds
from perf_artifacts import (
    PerfCaseRecord,
    PerfMetrics,
    perf_output_path,
    perf_record_to_mapping,
    render_perf_case_records_jsonl,
    write_perf_lines,
)
from profile_csv_parser import (
    find_latest_op_statistic_csv,
    find_optional_profile_csv,
    parse_kernel_details_csv,
    parse_op_statistic_csv,
    resolve_perf_metrics,
)
from result_payload import ResultPayload, make_result
from torch_npu_warnings import bootstrap_torch_npu, temporary_sys_path_entries
from worker_runtime import NullWorkerRuntime, WorkerRuntime


# ---------------------------------------------------------------------------
# Constants & data model
# ---------------------------------------------------------------------------

LoadedBenchCases = tuple[list["BenchCase"], KernelResolution]
RuntimeBenchResult = tuple[ResultPayload, Path]
ProfileCaseOutcome = tuple[Optional[PerfMetrics], Optional[str]]
ResolvedProfileOutputRoot = tuple[Optional[str], str]
PreservedRunDir = tuple[Path, Optional[tempfile.TemporaryDirectory[str]]]

WARMUP_DEFAULT = 5
REPEATS_DEFAULT = 50
_MISSING_KERNEL_MATCH_ERROR = "no resolved kernels matched profiler kernel view"


@dataclass(frozen=True)
class BenchCase:
    case_id: str
    fn: Callable[[], object]
    warmup: int
    repeats: int
    case_data: Mapping[str, object]


# ---------------------------------------------------------------------------
# Module loading & case construction
# ---------------------------------------------------------------------------

def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(f"{module_name}_{time.time_ns()}", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclass/typing decorators resolve the module via sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _require_callable(module: object, name: str, bench_file: Path) -> Callable[..., Any]:
    candidate = getattr(module, name, None)
    if not callable(candidate):
        raise ValueError(f"Benchmark module missing required hook '{name}': {bench_file}")
    return candidate


def _normalize_cases(
    raw_cases: object,
    operator_api: object,
    build_case_fn: Callable[[object, Mapping[str, object]], object],
) -> list[BenchCase]:
    if isinstance(raw_cases, (str, bytes)) or isinstance(raw_cases, Mapping) or not isinstance(raw_cases, Iterable):
        raise ValueError("Benchmark hook 'build_bench_cases' must return an iterable of cases")
    cases: list[BenchCase] = []
    seen_case_ids: set[str] = set()
    for raw_case in cast(Iterable[object], raw_cases):
        if not isinstance(raw_case, Mapping):
            raise ValueError("Benchmark cases must be mappings")
        case_map = cast(Mapping[str, object], raw_case)
        case_id = case_map.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Benchmark case is missing required string field 'id'")
        if case_id in seen_case_ids:
            raise ValueError(f"Duplicate benchmark case id: {case_id}")
        warmup = _normalize_non_negative_int(case_map.get("warmup", WARMUP_DEFAULT), "warmup", case_id)
        repeats = _normalize_positive_int(case_map.get("repeats", REPEATS_DEFAULT), "repeats", case_id)
        seen_case_ids.add(case_id)
        cases.append(
            BenchCase(
                case_id=case_id,
                fn=_resolve_case_fn(operator_api, build_case_fn, case_map, case_id),
                warmup=warmup,
                repeats=repeats,
                case_data=case_map,
            )
        )
    if not cases:
        raise ValueError("Benchmark hook 'build_bench_cases' returned no cases")
    return cases


def _resolve_case_fn(
    operator_api: object,
    build_case_fn: Callable[[object, Mapping[str, object]], object],
    case_map: Mapping[str, object],
    case_id: str,
) -> Callable[[], object]:
    candidate = build_case_fn(operator_api, case_map)
    if not callable(candidate):
        raise ValueError(f"Benchmark hook 'build_bench_case_fn' for case '{case_id}' must return a callable")
    return cast(Callable[[], object], candidate)


def _normalize_non_negative_int(value: object, field_name: str, case_id: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"Benchmark case '{case_id}' field '{field_name}' must be an integer")
    if value < 0:
        raise ValueError(f"Benchmark case '{case_id}' field '{field_name}' must be >= 0")
    return value


def _normalize_positive_int(value: object, field_name: str, case_id: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"Benchmark case '{case_id}' field '{field_name}' must be an integer")
    if value <= 0:
        raise ValueError(f"Benchmark case '{case_id}' field '{field_name}' must be > 0")
    return value


def load_bench_cases(
    bench_file: Path,
    operator_file: Path,
) -> LoadedBenchCases:
    """Load benchmark cases without building the operator."""
    bench_path = bench_file.resolve()
    operator_path = operator_file.resolve()
    bootstrap_torch_npu()
    with temporary_sys_path_entries(bench_path.parent, operator_path.parent):
        bench_module = _load_module(bench_path, f"run_bench_execution_bench_{bench_path.stem}")
        operator_module = _load_module(operator_path, f"run_bench_execution_operator_{operator_path.stem}")
        build_operator_api = _require_callable(bench_module, "build_operator_api", bench_path)
        build_cases = _require_callable(bench_module, "build_bench_cases", bench_path)
        build_case_fn = _require_callable(bench_module, "build_bench_case_fn", bench_path)
        operator_api = build_operator_api(operator_module)
        raw_cases = build_cases()
    return _normalize_cases(raw_cases, operator_api, build_case_fn), resolve_bench_kernel_resolution(
        bench_path,
        operator_path,
    )


def select_bench_case(cases: list[BenchCase], case_id: str | None) -> BenchCase:
    if case_id is None:
        if len(cases) == 1:
            return cases[0]
        available = ", ".join(case.case_id for case in cases)
        raise ValueError(
            "Benchmark profiling requires --case-id when multiple cases exist. "
            f"Available case ids: {available}"
        )
    for case in cases:
        if case.case_id == case_id:
            return case
    available = ", ".join(case.case_id for case in cases)
    raise ValueError(f"Unknown benchmark case id '{case_id}'. Available case ids: {available}")


# ---------------------------------------------------------------------------
# Bench execution (public API)
# ---------------------------------------------------------------------------

def execute_bench_case(
    bench_file: Path,
    operator_file: Path,
    case_id: str | None = None,
) -> ResultPayload:
    """Execute one bench case without profiling (the ``exec-one`` entrypoint).

    Only runs the case function so an external profiler wrapping this process
    (simulator) has something to measure; metrics are never collected here.
    """
    import torch
    cases, _resolution = load_bench_cases(bench_file, operator_file)
    case = select_bench_case(cases, case_id)
    case.fn()
    _synchronize(torch)
    return make_result(return_code=0, stdout="", stderr="")


def profile_bench_case(
    bench_file: Path,
    operator_file: Path,
    case_id: str | None,
    *,
    preserved_run_dir: Path | None = None,
    verbose: bool = False,
    preloaded: LoadedBenchCases | None = None,
) -> PerfCaseRecord:
    cases, resolution = preloaded or load_bench_cases(bench_file, operator_file)
    case = select_bench_case(cases, case_id)
    return _run_bench_case(
        case,
        resolution,
        preserved_run_dir,
        bench_file.parent,
        verbose=verbose,
    )


def deferred_parse_warranted(cases: list[BenchCase]) -> bool:
    """One shared gate for the deferred CANN parse pipeline.

    Deferred parsing pays off only across multiple cases and requires
    HELIX_BENCH_DEFER_PARSE=1; single-case runs keep the simple
    synchronous path everywhere (router, in-process profiler, batched
    worker, profile-all).
    """
    return len(cases) > 1 and bench_defer_parse_enabled()


def profile_bench_cases(
    cases: list[BenchCase],
    resolution: KernelResolution,
    *,
    preserved_run_dir: Path | None,
    cleanup_workdir: Path,
    verbose: bool = False,
    emit: "Optional[WorkerRuntime]" = None,
) -> list[PerfCaseRecord]:
    """Profile all supplied cases directly in the current process.

    When deferred parse is warranted, delegates to the shared
    deferred-parse pipeline (online CANN parse disabled, rolling
    background parse) so the fixed per-trace parse cost stops stacking
    serially. Single-case and flag-off runs keep the synchronous path,
    which emits the plan line and one record per completed case.
    """
    emit = emit or NullWorkerRuntime()
    if deferred_parse_warranted(cases):
        return profile_bench_cases_deferred(
            cases,
            resolution,
            preserved_root=preserved_run_dir,
            verbose=verbose,
            cleanup_workdir=cleanup_workdir,
            emit=emit,
        )
    emit.emit_progress("plan", case_ids=[case.case_id for case in cases])
    records: list[PerfCaseRecord] = []
    for case in cases:
        record = _run_bench_case(
            case,
            resolution,
            preserved_run_dir,
            cleanup_workdir,
            verbose=verbose,
        )
        records.append(record)
        emit.emit_case(perf_record_to_mapping(record))
    return records


def profile_bench_case_artifacts(
    bench_file: Path,
    operator_file: Path,
    case_id: str | None,
) -> ResultPayload:
    """Run one case under the profiler only to produce its PROF_* directory.

    Unlike ``profile_bench_case`` this discards the collected metrics and
    returns a plain success/failure payload; it backs ``run-profile`` artifact
    generation rather than perf-file benchmarking.
    """
    cases, resolution = load_bench_cases(bench_file, operator_file)
    case = select_bench_case(cases, case_id)
    profile_root = _profile_output_root(bench_file.parent, case.case_id)
    _metrics, error_message = _profile_case_with_profiler(case, resolution, profile_root)
    if error_message is not None:
        return make_result(return_code=1, stdout="", stderr=error_message)
    return make_result(return_code=0, stdout="", stderr="")


def _failed_case_lines(case_records: list[PerfCaseRecord]) -> list[str]:
    lines = []
    for record in case_records:
        if record.error_message is not None:
            lines.append(f"{record.case_label}: {record.error_message}")
    return lines


def _perf_artifacts_result(
    operator_file: Path,
    output: str | None,
    case_records: list[PerfCaseRecord],
) -> RuntimeBenchResult:
    error_lines = _failed_case_lines(case_records)
    perf_path = _resolve_output_path(operator_file, output=output)
    write_perf_lines(
        perf_path,
        render_perf_case_records_jsonl(
            case_records,
            missing_kernel_match_error=_MISSING_KERNEL_MATCH_ERROR,
        ),
    )
    return (
        make_result(
            return_code=1 if error_lines else 0,
            stdout="",
            stderr="\n".join(error_lines),
        ),
        perf_path,
    )


def _profile_all_serial(
    bench_file: Path,
    operator_file: Path,
    cases: list[BenchCase],
    resolution: KernelResolution,
    *,
    verbose: bool,
    emit: "WorkerRuntime",
) -> list[PerfCaseRecord]:
    case_records: list[PerfCaseRecord] = []
    preserved_run_dir = create_local_preserved_profile_run_dir(prefix="helix-bench-")
    emit.emit_progress("plan", case_ids=[case.case_id for case in cases])

    for case in cases:
        record = profile_bench_case(
            bench_file,
            operator_file,
            case.case_id,
            preserved_run_dir=preserved_run_dir,
            verbose=verbose,
            preloaded=(cases, resolution),
        )
        case_records.append(record)
        emit.emit_case(perf_record_to_mapping(record))
    return case_records


def profile_all_bench_cases(
    bench_file: Path,
    operator_file: Path,
    *,
    verbose: bool = False,
    output: str | None = None,
    preloaded: LoadedBenchCases | None = None,
    emit: "Optional[WorkerRuntime]" = None,
) -> RuntimeBenchResult:
    emit = emit or NullWorkerRuntime()
    cases, resolution = preloaded or load_bench_cases(bench_file, operator_file)
    if deferred_parse_warranted(cases):
        # Deferred parsing covers the profile-all entry as well (remote bench
        # always runs profile-all); same behaviour as the profile-case gate.
        case_records = profile_bench_cases_deferred(
            cases, resolution, verbose=verbose, cleanup_workdir=bench_file.parent, emit=emit
        )
        return _perf_artifacts_result(operator_file, output, case_records)
    case_records = _profile_all_serial(bench_file, operator_file, cases, resolution, verbose=verbose, emit=emit)
    return _perf_artifacts_result(operator_file, output, case_records)


# ---------------------------------------------------------------------------
# Perf-counter timing (no profiler)
# ---------------------------------------------------------------------------


def _time_case_iterations(
    *,
    fn: Callable[[], object],
    warmup: int,
    repeats: int,
) -> PerfMetrics:
    import torch
    for _ in range(warmup):
        fn()
        _synchronize(torch)
    iteration_times: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        _synchronize(torch)
        iteration_times.append(time.perf_counter() - t0)
    avg_us = statistics.mean(iteration_times) * 1_000_000
    return {"kernel_avg_time_us": avg_us, "ops": []}


def time_bench_case(
    case: BenchCase,
    resolution: KernelResolution,
    *,
    bench_mode: str,
) -> PerfCaseRecord:
    t0 = time.monotonic()
    try:
        metrics = _time_case_iterations(
            fn=case.fn,
            warmup=case.warmup,
            repeats=case.repeats,
        )
        elapsed = time.monotonic() - t0
        return PerfCaseRecord(
            case_label=case.case_id,
            kernel_names=resolution.kernel_names,
            kernel_source=resolution.kernel_source,
            metrics=metrics,
            case_wall_clock_seconds=elapsed,
            bench_mode=bench_mode,
        )
    except Exception as exc:
        elapsed = time.monotonic() - t0
        return PerfCaseRecord(
            case_label=case.case_id,
            kernel_names=resolution.kernel_names,
            kernel_source=resolution.kernel_source,
            error_message=f"{type(exc).__name__}: {exc}",
            case_wall_clock_seconds=elapsed,
            bench_mode=bench_mode,
        )


def time_all_bench_cases(
    bench_file: Path,
    operator_file: Path,
    *,
    bench_mode: str = "perf-counter",
    output: str | None = None,
    preloaded: LoadedBenchCases | None = None,
    emit: "Optional[WorkerRuntime]" = None,
) -> RuntimeBenchResult:
    emit = emit or NullWorkerRuntime()
    cases, resolution = preloaded or load_bench_cases(bench_file, operator_file)
    emit.emit_progress("plan", case_ids=[case.case_id for case in cases])
    case_records: list[PerfCaseRecord] = []
    had_failures = False
    stderr_chunks: list[str] = []

    for case in cases:
        record = time_bench_case(
            case,
            resolution,
            bench_mode=bench_mode,
        )
        if record.error_message is not None:
            had_failures = True
            stderr_chunks.append(f"{case.case_id}: {record.error_message}")
        case_records.append(record)
        emit.emit_case(perf_record_to_mapping(record))

    perf_path = _resolve_output_path(operator_file, output=output)
    write_perf_lines(
        perf_path,
        render_perf_case_records_jsonl(
            case_records,
        ),
    )
    return (
        make_result(
            return_code=1 if had_failures else 0,
            stdout="",
            stderr="\n".join(stderr_chunks),
        ),
        perf_path,
    )


# ---------------------------------------------------------------------------
# Profiling internals
# ---------------------------------------------------------------------------


def _prepare_profile_root(profile_root: Path, fresh_dir: bool) -> None:
    if not fresh_dir:
        # Shared parent dir (deferred batch mode): traces of previously
        # profiled cases live alongside, never wipe them.
        profile_root.mkdir(parents=True, exist_ok=True)
        return
    try:
        profile_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        shutil.rmtree(profile_root, ignore_errors=True)
        profile_root.mkdir(parents=True, exist_ok=False)


def _experimental_profiler_config(profiler_api: Any) -> Any:
    # torch_npu exposes the experimental profiler config only under the
    # underscore name; look it up dynamically so a future public spelling
    # cannot silently break profiling.
    config_cls = getattr(profiler_api, "_ExperimentalConfig", None)
    if config_cls is None:
        raise RuntimeError("torch_npu profiler does not expose the experimental config API")
    return config_cls(
        profiler_level=profiler_api.ProfilerLevel.Level1,
        l2_cache=False,
        data_simplification=False,
    )


def _run_profiled_steps(
    profiler_api: Any,
    case: BenchCase,
    profile_root: Path,
    *,
    parse_online: bool,
    experimental_config: Any,
    torch: Any,
) -> None:

    def _run_once() -> None:
        case.fn()
        _synchronize(torch)

    skip_first = 1
    total_steps = skip_first + case.warmup + case.repeats
    with profiler_api.profile(
        activities=[
            profiler_api.ProfilerActivity.NPU,
            profiler_api.ProfilerActivity.CPU,
        ],
        schedule=profiler_api.schedule(
            wait=0,
            warmup=case.warmup,
            active=case.repeats,
            repeat=1,
            skip_first=skip_first,
        ),
        # parse_online=False keeps the raw trace and skips the
        # synchronous CANN parse; the caller parses it later via
        # torch_npu.profiler.analyse (same parser, same CSVs).
        on_trace_ready=profiler_api.tensorboard_trace_handler(
            str(profile_root), analyse_flag=parse_online
        ),
        record_shapes=False,
        profile_memory=False,
        with_stack=False,
        with_flops=False,
        with_modules=False,
        experimental_config=experimental_config,
    ) as profiler:
        for _step_index in range(total_steps):
            _run_once()
            profiler.step()


def _profile_case_with_profiler(
    case: BenchCase,
    resolution: KernelResolution,
    profile_root: Path,
    *,
    verbose: bool = False,
    parse_online: bool = True,
    fresh_dir: bool = True,
) -> ProfileCaseOutcome:
    try:
        import torch
        torch_npu = cast(Any, importlib.import_module("torch_npu"))
    except ImportError as exc:
        return None, f"Missing profiler dependency: {exc}"

    _prepare_profile_root(profile_root, fresh_dir)

    try:
        profiler_api = torch_npu.profiler
        experimental_config = _experimental_profiler_config(profiler_api)

        _suppress_ctx = _suppress_output_streams() if not verbose else nullcontext()
        with _suppress_ctx:
            case.fn()
            _synchronize(torch)
            _run_profiled_steps(
                profiler_api, case, profile_root,
                parse_online=parse_online, experimental_config=experimental_config, torch=torch,
            )

        if not parse_online:
            return None, None  # metrics pending deferred parse
        return _read_profiler_metrics(profile_root, case.repeats, resolution.kernel_names, verbose=verbose), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def profile_bench_cases_deferred(
    cases: list[BenchCase],
    resolution: KernelResolution,
    *,
    preserved_root: Path | None = None,
    verbose: bool = False,
    cleanup_workdir: Path | None = None,
    emit: "Optional[WorkerRuntime]" = None,
) -> list[PerfCaseRecord]:
    """Profile all cases with online CANN parsing disabled (analyse_flag=False);
    a single background thread parses rolling batches of completed case
    directories while profiling continues. Each case profiles into its own
    directory (attribution by name); every _deferred_parse_max_workers()
    completed directories are renamed into a fresh plain batch directory and
    parsed by one isolated analyse() call, whose internal pool runs at the
    batch size. Design rationale: docs/notes/implemented/
    2026-08-28-run-bench-deferred-parse-design.md

    When cleanup_workdir is given, the workspace extra-info directory is
    removed even when the pipeline raises mid-run, so a failed deferred
    run strands no artifacts the synchronous path would have cleaned per
    case.
    """
    emit = emit or NullWorkerRuntime()
    # Same entry contract as the synchronous path: the plan line precedes the
    # first case so the supervisor knows the planned case ids up front.
    emit.emit_progress("plan", case_ids=[case.case_id for case in cases])
    import torch  # noqa: F401  # pyright: ignore[reportUnusedImport] (ensures runtime initialized before profiling)

    # One analyse process for the whole run: its torch_npu import starts before
    # the profile loop and finishes while profiling proceeds, instead of being
    # paid per batch (see
    # docs/notes/implemented/2026-09-14-analyse-service-process.md).
    analyse_service_client = _AnalyseService(emit=emit)
    analyse_service_client.start()

    # Deferred traces of op-heavy targets can reach tens of GB; tmpfs (/tmp)
    # is RAM-backed, so prefer an explicit output dir on real disk when given.
    run_root = _deferred_run_root(preserved_root)

    pipeline = _DeferredParsePipeline(
        cases, resolution, verbose=verbose, emit=emit,
        run_root=run_root, analyse_service_client=analyse_service_client,
    )
    thread = threading.Thread(
        target=pipeline.rolling_parse_worker,
        name="helix-deferred-rolling-parse",
        daemon=True,
    )
    thread.start()
    try:
        return pipeline.run()
    finally:
        # Failure safety: let the rolling parser drain what it still holds,
        # then remove the extra-info dir even when the run raised — the
        # synchronous path cleans per case inside _run_bench_case's finally,
        # and the deferred pipeline must not strand extra-info behind.
        pipeline.parse_queue.put(None)
        thread.join()
        analyse_service_client.close()
        if preserved_root is None:
            shutil.rmtree(run_root, ignore_errors=True)
        if cleanup_workdir is not None:
            cleanup_local_bench_extra_info(cleanup_workdir)


def _deferred_run_root(preserved_root: Path | None) -> Path:
    defer_parent = preserved_root
    if defer_parent is None:
        configured = bench_output_dir()
        if configured is not None:
            defer_parent = Path(configured).expanduser().resolve()
            defer_parent.mkdir(parents=True, exist_ok=True)
    return Path(
        tempfile.mkdtemp(
            prefix="helix-bench-defer-",
            dir=str(defer_parent) if defer_parent is not None else None,
        )
    )


class _DeferredParsePipeline:
    """Rolling-parse pipeline state for profile_bench_cases_deferred.

    Backpressure gate: cap the on-disk bytes of raw traces that may sit
    unparsed. The parse queue is unbounded, so without a gate a stalled
    parser (CPU contention on shared hosts) lets profiling pile traces up
    to the full run size — tolerable on real disk, fatal on tmpfs (RAM).
    Gated, unparsed bytes stay under budget + one batch, which is what
    makes tmpfs placement safe. The budget derives from the live free
    space of the output filesystem, so it needs no tuning knob.
    """

    def __init__(
        self,
        cases: list[BenchCase],
        resolution: KernelResolution,
        *,
        verbose: bool,
        emit: "WorkerRuntime",
        run_root: Path,
        analyse_service_client: "_AnalyseService",
    ) -> None:
        self.cases = cases
        self.resolution = resolution
        self.verbose = verbose
        self.emit = emit
        self.run_root = run_root
        self.analyse_service_client = analyse_service_client
        self.budget_bytes = shutil.disk_usage(run_root).free // _DEFERRED_UNPARSED_BUDGET_DIVISOR
        self.space_cond = threading.Condition()
        self.unparsed_bytes = 0  # unparsed raw-trace bytes still on disk
        self.pending_release_bytes = 0  # subset the parser can still free (queued or parsing)
        self.case_bytes: dict[str, int] = {}
        self.parse_queue: queue.Queue[tuple[Path, list[tuple[BenchCase, Path, float]]] | None] = (
            queue.Queue()
        )
        # Records the parse thread finalised, keyed by case id; written only by
        # that thread and read by the main thread after joining it.
        self.thread_records: dict[str, PerfCaseRecord] = {}
        self.case_dirs: dict[str, Path] = {}
        self.batch: list[tuple[BenchCase, Path, float]] = []
        self.batch_number = 0
        self.pending: list[tuple[BenchCase, float, Optional[str]]] = []

    def run(self) -> list[PerfCaseRecord]:
        self._profile_cases()
        self.parse_queue.put(None)
        # The caller joins the rolling-parse thread after run() returns.
        self._final_retries()
        return self._collect_records()

    def record_for(
        self, case: BenchCase, case_dir: Path, elapsed: float, error_message: Optional[str]
    ) -> PerfCaseRecord:
        metrics: Optional[PerfMetrics] = None
        if error_message is None:
            try:
                metrics = _read_profiler_metrics(
                    case_dir, case.repeats, self.resolution.kernel_names, verbose=self.verbose
                )
            except Exception as exc:
                metrics, error_message = None, f"{type(exc).__name__}: {exc}"
        return PerfCaseRecord(
            case_label=case.case_id,
            kernel_names=self.resolution.kernel_names,
            kernel_source=self.resolution.kernel_source,
            metrics=metrics,
            error_message=error_message,
            case_wall_clock_seconds=elapsed,
            bench_mode="torch-npu-profiler",
        )

    def rolling_parse_worker(self) -> None:
        while True:
            item = self.parse_queue.get()
            try:
                if item is None:
                    return
                batch_dir, batch = item
                self._parse_batch(batch_dir, batch)
            finally:
                self.parse_queue.task_done()

    def _parse_batch(self, batch_dir: Path, batch: list[tuple[BenchCase, Path, float]]) -> None:
        workers = len(batch)
        self.emit.emit_progress(
            "batch-start", case_ids=[case.case_id for case, _root, _elapsed in batch]
        )
        print(
            f"[run-bench] [deferred] batch parse start: "
            f"{len(batch)} trace(s), max_workers={workers}",
            flush=True,
        )
        t_batch = time.monotonic()
        _analyse_traces_isolated(
            batch_dir, workers, timeout=_analyse_timeout_seconds(), emit=self.emit,
            service=self.analyse_service_client,
        )
        print(
            f"[run-bench] [deferred] batch analyse returned in "
            f"{time.monotonic() - t_batch:.1f}s",
            flush=True,
        )
        purged_bytes = 0
        for case, case_dir, elapsed in batch:
            if not _case_parsed(case_dir):
                # Batch call missed this one: retry pointed directly
                # at the case's own directory.
                _analyse_traces_isolated(
                    case_dir, workers, timeout=_analyse_timeout_seconds(), emit=self.emit,
                    service=self.analyse_service_client,
                )
            if _case_parsed(case_dir):
                _purge_raw_trace_files(case_dir)
                purged_bytes += self.case_bytes.get(case.case_id, 0)
                record = self.record_for(case, case_dir, elapsed, None)
                self.thread_records[case.case_id] = record
                self.emit.emit_case(perf_record_to_mapping(record))
            else:
                print(
                    f"[run-bench] [deferred] {case.case_id} not parsed; "
                    f"retrying after the profile loop",
                    flush=True,
                )
        # Failed (zombie) cases stay in unparsed_bytes but leave
        # pending_release_bytes, so the gate can never deadlock: it only
        # blocks while the parser still holds work that frees space.
        with self.space_cond:
            self.unparsed_bytes -= purged_bytes
            self.pending_release_bytes -= sum(
                self.case_bytes.get(case.case_id, 0) for case, _root, _elapsed in batch
            )
            self.space_cond.notify_all()
        self.emit.emit_progress(
            "batch-returned", case_ids=[case.case_id for case, _root, _elapsed in batch]
        )

    def _pack_batch(self) -> None:
        batch_dir = self.run_root / f"batch-{self.batch_number:02d}"
        batch_dir.mkdir(parents=True)
        moved: list[tuple[BenchCase, Path, float]] = []
        for case, holder, elapsed in self.batch:
            # analyse() scans only the batch dir's direct children, and the
            # profiler writes the trace into a session subdirectory of the
            # per-case dir (tensorboard_trace_handler), so renaming the case
            # dir would leave every trace one level too deep and parse
            # nothing. Hoist that subdirectory instead, keeping the per-case
            # name as a prefix so attribution stays in the directory name.
            # Same filesystem (the batch dir lives under run_root): a plain
            # rename, never a symlink.
            trace_dirs = [child for child in holder.iterdir() if child.is_dir()]
            if len(trace_dirs) == 1:
                target = batch_dir / f"{holder.name}__{trace_dirs[0].name}"
                os.rename(trace_dirs[0], target)
                try:
                    holder.rmdir()
                except OSError:
                    pass  # non-empty scratch dir: removed with run_root
            else:
                # No subdirectory: the profiler wrote the trace in place, so
                # the per-case dir is itself the one-level shape analyse()
                # scans. Several subdirectories is a layout this pipeline does
                # not model: the batch call then matches nothing and the
                # per-case retry parses them, as before.
                target = batch_dir / holder.name
                os.rename(holder, target)
            self.case_dirs[case.case_id] = target
            moved.append((case, target, elapsed))
        packed = sum(self.case_bytes.get(case.case_id, 0) for case, _root, _elapsed in moved)
        with self.space_cond:
            self.unparsed_bytes += packed
            self.pending_release_bytes += packed
        self.emit.emit_progress(
            "batch-submitted", case_ids=[case.case_id for case, _root, _elapsed in moved]
        )
        self.parse_queue.put((batch_dir, moved))
        self.batch = []
        self.batch_number += 1

    def _profile_cases(self) -> None:
        for index, case in enumerate(self.cases, start=1):
            # Backpressure gate. Only blocks while the parser still holds
            # work that frees space (pending_release_bytes > 0); a zombie-only backlog
            # opens the gate so the loop always reaches the final retry.
            # The throttle notice is plain output that resets the parent's
            # no-output timer.
            with self.space_cond:
                while self.unparsed_bytes > self.budget_bytes and self.pending_release_bytes > 0:
                    self.space_cond.wait(timeout=15)
                    print(
                        f"[run-bench] [deferred] parse backlog "
                        f"{self.unparsed_bytes / 2**30:.1f} GiB over budget "
                        f"{self.budget_bytes / 2**30:.1f} GiB; throttling profile",
                        flush=True,
                    )
            # Each case profiles into its own directory: attribution is the
            # directory name, and it survives the rename into a batch dir.
            holder = self.run_root / f"case-{index:03d}-{_sanitize_case_id(case.case_id)}"
            t0 = time.monotonic()
            _metrics, error_message = _profile_case_with_profiler(
                case,
                self.resolution,
                holder,
                verbose=self.verbose,
                parse_online=False,
                fresh_dir=True,
            )
            elapsed = time.monotonic() - t0
            self.pending.append((case, elapsed, error_message))
            self.case_dirs[case.case_id] = holder
            if error_message is None:
                self.case_bytes[case.case_id] = _dir_bytes(holder)
                # Per-case progress the moment raw profiling completes:
                # records wait for parsing, so without this line the
                # parent's stall detection would kill this worker mid-run.
                self.emit.emit_progress("raw-profiled", case_id=case.case_id)
                self.batch.append((case, holder, elapsed))
                if len(self.batch) >= _deferred_parse_max_workers():
                    # Seal the batch for the parser and start a fresh one.
                    self._pack_batch()
        if self.batch:
            self._pack_batch()

    def _final_retries(self) -> None:
        unparsed = []
        for case, _elapsed, err in self.pending:
            case_dir = self.case_dirs[case.case_id]
            if err is None and not _case_parsed(case_dir):
                unparsed.append((case.case_id, case_dir))
        for case_id, root in unparsed:
            print(f"[run-bench] [deferred] final retry for {case_id}", flush=True)
            if _analyse_traces_isolated(
                root,
                _deferred_parse_max_workers(),
                timeout=_analyse_timeout_seconds(),
                emit=self.emit,
                service=self.analyse_service_client,
            ):
                _purge_raw_trace_files(root)
        if not unparsed:
            print(
                f"[run-bench] [deferred] all {len(self.cases)} case(s) profiled and parsed",
                flush=True,
            )

    def _collect_records(self) -> list[PerfCaseRecord]:
        records: list[PerfCaseRecord] = []
        for case, elapsed, error_message in self.pending:
            record = self.thread_records.get(case.case_id)
            if record is None:
                record = self.record_for(case, self.case_dirs[case.case_id], elapsed, error_message)
                self.emit.emit_case(perf_record_to_mapping(record))
            records.append(record)
        return records


# Backpressure budget divisor: unparsed raw traces may use at most 1/N of the
# output filesystem's live free space. Leaves headroom for parser RSS and
# co-tenant benches sharing the same filesystem (tmpfs shares RAM with all).
_DEFERRED_UNPARSED_BUDGET_DIVISOR = 4


def _dir_bytes(root: Path) -> int:
    """Total size of files under root (0 when missing or unreadable)."""
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            pass
    return total


def _mem_available_gb() -> float | None:
    try:
        with open("/proc/meminfo") as fh:
            return _scan_mem_available_gb(fh)
    except (OSError, ValueError, IndexError):
        return None


def _scan_mem_available_gb(fh: object) -> float | None:
    for line in fh:
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1_048_576
    return None


def _deferred_parse_max_workers() -> int:
    # Each msprof parse worker peaks at several GB RSS (30GB+ for op-heavy
    # traces), so cpu_count//2 parallel parsers can exhaust even TB-scale
    # hosts and hang the machine. Hard-cap the pool, and shrink it further
    # when the box is already memory-tight (shared-host neighbourliness).
    cap = max(1, min(8, (os.cpu_count() or 2) // 2))
    available_gb = _mem_available_gb()
    if available_gb is None:
        return cap
    if available_gb < 64:
        return min(cap, 2)
    if available_gb < 128:
        return min(cap, 4)
    return cap


def _case_parsed(root: Path) -> bool:
    return (
        find_optional_profile_csv(root, "kernel_details.csv") is not None
        or find_latest_op_statistic_csv(root) is not None
    )


def _analyse_timeout_seconds() -> float | None:
    value = eval_timeout_seconds()
    return float(value) if value > 0 else None


# analyse() job for _analyse_traces_isolated, run as `python -c <snippet>`.
# argv: [target, max_workers, timeout_seconds]. The SIGALRM self-deadline is
# armed before the torch_npu import (a slow import must not dodge it) and
# disarmed on success; timeout_seconds="0" arms no deadline at all.
_ANALYSE_SNIPPET = (
    "import os, signal, sys\n"
    "def _deadline(signum, frame):\n"
    "    try:\n"
    "        os.killpg(0, signal.SIGKILL)\n"
    "    except OSError:\n"
    "        os._exit(1)\n"
    "signal.signal(signal.SIGALRM, _deadline)\n"
    "signal.alarm(int(sys.argv[3]))\n"
    "from torch_npu.profiler.profiler import analyse\n"
    "analyse(sys.argv[1], max_process_number=int(sys.argv[2]), export_type='text')\n"
    "signal.alarm(0)\n"
)


def _analyse_traces_isolated(
    target: Path,
    max_workers: int,
    timeout: float | None,
    emit: "Optional[WorkerRuntime]" = None,
    service: "Optional[_AnalyseService]" = None,
) -> bool:
    """Parse one target and decide whether it produced parse output.

    ``service`` routes the job to the run's long-lived analyse process; when it
    is absent or unusable the job runs in a throwaway interpreter exactly as
    before, so correctness never depends on the service.

    True only when analyse exited 0 *and* the target now carries parse output:
    analyse() also exits 0 when it matched no profiler input at all, and
    reporting that as success silently degrades the pipeline to per-case
    retries that each pay a fresh interpreter plus import torch_npu.
    """
    outcome = service.analyse(target, max_workers, timeout) if service is not None else None
    rc, log_path = outcome if outcome is not None else _run_analyse_job(
        target, max_workers, timeout, emit
    )
    if rc == 0 and _case_parsed(target):
        log_path.unlink(missing_ok=True)
        return True
    tail = _analyse_log_tail(log_path)
    if rc == 0:
        # analyse() exits 0 when it matched no profiler input; keep the raw
        # traces, since an unparsed case is recoverable and a purged one is
        # not. The job log stays for diagnosis and dies with the run root.
        print(
            f"[run-bench] [deferred] isolated analyse of {target.name} exited 0 "
            f"without parse output; keeping its raw traces"
            f"{': ' + tail if tail else ''}",
            flush=True,
        )
        return False
    reason = "timeout" if rc is None else f"rc={rc}"
    print(
        f"[run-bench] [deferred] isolated analyse of {target.name} failed "
        f"({reason}){': ' + tail if tail else ''}",
        flush=True,
    )
    return False


def _run_analyse_job(
    target: Path,
    max_workers: int,
    timeout: float | None,
    emit: "Optional[WorkerRuntime]" = None,
) -> tuple[Optional[int], Path]:
    """Run CANN analyse() for one target in a throwaway subprocess.

    analyse() forks a process pool, and forking THIS worker process is racy:
    the profile loop, heartbeat and device threads hold internal locks at
    arbitrary moments, and a pool inheriting a locked queue deadlocks in
    shutdown() — observed live: the rolling-parse thread stuck in
    close_pool -> ProcessPoolExecutor.join forever, the main thread stuck
    joining it, the whole run frozen with every process at 0% CPU. A fresh
    single-threaded interpreter has no inherited lock state, and the
    subprocess gives a hard timeout: a hung parser gets its whole process
    group killed and the caller falls back, instead of deadlocking the run.

    The job also carries its own deadline: the snippet arms a SIGALRM whose
    handler kills the job's whole session. The wait(timeout) + killpg below
    is the normal enforcement, but it dies with this worker — the alarm
    bounds the job even when its parent enforcer is gone (fork clears
    interval timers in the parse pool's children, so they cannot fire it
    early). ``emit`` registers the Popen so the worker's SIGTERM cleanup
    also kills in-flight jobs.
    """
    with tempfile.NamedTemporaryFile(
        mode="w+b",
        prefix="helix-analyse-",
        suffix=".log",
        dir=str(target.parent),
        delete=False,
    ) as logf:
        log_path = Path(logf.name)
        deadline_arg = str(int(timeout)) if timeout is not None else "0"
        rc: Optional[int]
        proc = subprocess.Popen(
            [sys.executable, "-c", _ANALYSE_SNIPPET, str(target), str(max_workers), deadline_arg],
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # own process group: timeout kills the pool too
        )
        if emit is not None:
            emit.register_child(proc)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait()
            rc = None
        finally:
            if emit is not None:
                emit.unregister_child(proc)
    return rc, log_path


class _AnalyseService:
    """One long-lived analyse process per deferred run, with a safe fallback.

    A throwaway interpreter per batch pays torch_npu's import and teardown every
    time (5.5s of an 8.7s batch on the measured host). This client keeps one
    ``analyse_service.py`` process alive for the run, hands it one batch per
    request, and gives up on it — falling back to ``_run_analyse_job`` — when it
    cannot be spawned, cannot be started, is lost, or has spent its restart
    budget. A job timeout is reported as a timeout verdict instead of being
    retried through the fallback, so a hung parser costs one timeout window.

    The service is single-threaded and started in its own session, so a hung job
    is killed with its whole forked pool by ``os.killpg``, and it is registered
    with the worker runtime so SIGTERM cleanup reaches it too.

    Rationale and measurements: docs/notes/implemented/
    2026-09-14-analyse-service-process.md.
    """

    _READY_TIMEOUT_SECONDS = 180.0
    _STOP_TIMEOUT_SECONDS = 5.0
    _MAX_RESTARTS = 2
    # The service's SIGALRM is a backstop for an orphaned job, not the primary
    # timeout: it must fire after the parent stops waiting for the result.
    _JOB_DEADLINE_MARGIN_SECONDS = 60.0
    # Bound the CANN state one process accumulates; measured RSS was flat over
    # two batches, so this is headroom rather than a known leak.
    _MAX_JOBS_PER_PROCESS = 8

    def __init__(
        self,
        *,
        emit: "Optional[WorkerRuntime]" = None,
    ) -> None:
        self._emit = emit
        self._process: Optional[subprocess.Popen[str]] = None
        self._results: "queue.Queue[Optional[dict[str, object]]]" = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self._stderr_reader: Optional[threading.Thread] = None
        self._stderr_tail: "deque[str]" = deque(maxlen=20)
        self._restarts = 0
        self._jobs_served = 0
        self._ready = False
        self._disabled = False

    @property
    def usable(self) -> bool:
        """False once the service is not worth attempting again this run."""
        return not self._disabled

    @staticmethod
    def _note(message: str) -> None:
        print(f"[run-bench] [deferred] {message}", flush=True)

    def start(self) -> bool:
        """Spawn the service without waiting for its ready handshake.

        Called before the profile loop, so the torch_npu import this service
        exists to amortize runs while profiling proceeds; the handshake is
        awaited on first use in ``analyse()``. False means the service will not
        take jobs, which is what the throwaway path is for.
        """
        return self._spawn()

    def analyse(
        self, target: Path, max_workers: int, timeout: float | None
    ) -> "Optional[tuple[Optional[int], Path]]":
        """Parse one target.

        Returns a verdict tuple ``(rc, log_path)`` — ``rc is None`` meaning the
        job timed out — or ``None`` when the service cannot take the job and the
        caller must use the throwaway-subprocess path instead.
        """
        log_fd, log_name = tempfile.mkstemp(
            prefix="helix-analyse-", suffix=".log", dir=str(target.parent)
        )
        os.close(log_fd)
        log_path = Path(log_name)
        if self._jobs_served >= self._MAX_JOBS_PER_PROCESS:
            self._note(f"recycling after {self._jobs_served} batches")
            self._stop_process()  # planned, so it does not spend restart budget
        if not self._ensure_ready():
            log_path.unlink(missing_ok=True)
            return None
        process = self._process
        if process is None or process.stdin is None:
            log_path.unlink(missing_ok=True)
            raise RuntimeError("internal error: analyse service ready without a live process")
        # The parent's wait below is the enforcer; the service's own alarm is
        # only a backstop for an orphaned job, so it must fire after it.
        deadline_s = float(timeout) + self._JOB_DEADLINE_MARGIN_SECONDS if timeout is not None else 0.0
        request = {
            "target": str(target),
            "workers": max_workers,
            "deadline_s": deadline_s,
            "log": str(log_path),
        }
        try:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
        except OSError:
            self._note(f"analyse service lost on {target.name}; recycling")
            self._stop_process(lost=True)
            log_path.unlink(missing_ok=True)
            return None
        self._jobs_served += 1
        try:
            result = self._results.get(timeout=timeout)
        except queue.Empty:
            # A hung parser is a job verdict, not an availability problem: the
            # caller must not pay a second timeout window on the fallback path.
            self._note(f"analyse service timed out on {target.name}; recycling")
            self._stop_process(lost=True)
            return None, log_path
        if result is None:
            self._note(f"analyse service exited during {target.name}; falling back")
            self._stop_process(lost=True)
            return None
        return_code = result.get("rc")
        return (return_code if isinstance(return_code, int) else 1), log_path

    def close(self) -> None:
        """Stop the service; safe to call twice and after a failure."""
        process = self._process
        if process is None:
            return
        if process.poll() is None and process.stdin is not None:
            try:
                process.stdin.write(json.dumps({"stop": True}) + "\n")
                process.stdin.flush()
                process.wait(timeout=self._STOP_TIMEOUT_SECONDS)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self._stop_process()

    def _ensure_ready(self) -> bool:
        """True when a service is up and has completed its handshake."""
        if self._ready and self._process is not None and self._process.poll() is None:
            return True
        self._ready = False  # the flag is only good for a live process
        if not self._spawn():
            return False
        if self._process is None:
            raise RuntimeError("internal error: analyse service spawn reported success without a process")
        try:
            ready = self._results.get(timeout=self._READY_TIMEOUT_SECONDS)
        except queue.Empty:
            ready = None
        if isinstance(ready, dict) and ready.get("ready"):
            self._ready = True
            return True
        # A service that cannot come up is not retried every batch: each
        # attempt costs a full import before it fails. Its stderr carries the
        # reason (a missing torch_npu, a broken CANN environment).
        self._stop_process()
        detail = "; ".join(self._stderr_tail)
        self._note(
            "analyse service did not become ready"
            f"{': ' + detail if detail else ''}; using per-batch subprocesses"
        )
        self._disabled = True
        return False

    def _spawn(self) -> bool:
        if self._disabled:
            return False
        if self._process is not None:
            if self._process.poll() is None:
                return True
            # Died unnoticed since the last job: that spends restart budget.
            self._stop_process(lost=True)
            if self._disabled:
                return False
            self._note(f"starting analyse service (restart {self._restarts})")
        else:
            self._note("starting analyse service")
        self._reap_reader()
        self._results = queue.Queue()
        try:
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).with_name("analyse_service.py"))],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,  # own process group: a hung job dies with its pool
            )
        except OSError as exc:
            # The run must survive a host that cannot give us a process (fork
            # hitting RLIMIT_NPROC or EAGAIN on a loaded shared machine).
            self._note(f"cannot start analyse service ({exc}); using per-batch subprocesses")
            self._disabled = True
            return False
        self._process = process
        # CANN state accumulates per process, so the counter restarts with it.
        self._jobs_served = 0
        self._ready = False
        if self._emit is not None:
            self._emit.register_child(process)
        self._reader = threading.Thread(
            target=self._read_results, args=(process,), daemon=True, name="helix-analyse-results"
        )
        self._reader.start()
        self._stderr_reader = threading.Thread(
            target=self._read_stderr, args=(process,), daemon=True, name="helix-analyse-stderr"
        )
        self._stderr_reader.start()
        return True

    def _record_loss(self) -> None:
        """Spend restart budget for a service this run could not use."""
        self._restarts += 1
        if self._restarts > self._MAX_RESTARTS:
            self._note(
                "analyse service restart budget exhausted; using per-batch subprocesses"
            )
            self._disabled = True

    def _read_results(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            raise RuntimeError("internal error: analyse service stdout pipe is missing")
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._results.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        self._results.put(None)  # EOF: the service is gone

    def _read_stderr(self, process: subprocess.Popen[str]) -> None:
        """Keep the service's last stderr lines: it is the only place a failed
        startup explains itself (per-job output goes to the job logs)."""
        if process.stderr is None:
            raise RuntimeError("internal error: analyse service stderr pipe is missing")
        for line in process.stderr:
            self._stderr_tail.append(line.rstrip())

    def _stop_process(self, *, lost: bool = False) -> None:
        process, self._process = self._process, None
        if process is None:
            if lost:
                self._record_loss()
            return
        if process.stdin is not None:
            # Close the request pipe before the child goes away: a buffered
            # write into a dead child raises out of Popen.__del__ at GC time.
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()
            process.wait()
        if self._emit is not None:
            self._emit.unregister_child(process)
        self._reap_reader()
        if lost:
            self._record_loss()

    def _reap_reader(self) -> None:
        reader, self._reader = self._reader, None
        stderr_reader, self._stderr_reader = self._stderr_reader, None
        for thread in (reader, stderr_reader):
            if thread is not None:
                thread.join(timeout=2)


def _analyse_log_tail(log_path: Path) -> str:
    """Last non-empty lines of one analyse job's log, as a one-line detail."""
    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "; ".join(line.strip() for line in lines[-3:] if line.strip())


def _purge_raw_trace_files(case_root: Path) -> None:
    """Delete everything under a parsed case trace dir except the CSVs.

    Raw traces of op-heavy targets reach tens of GB per case; the parsed
    CSVs (kernel_details.csv, op_statistic) are all helix reads afterwards,
    so once parsing succeeded the raw data is dead weight on disk.
    """
    for path in case_root.rglob("*"):
        if path.is_file() and path.suffix.lower() != ".csv":
            try:
                path.unlink()
            except OSError:
                pass
    # Remove now-empty directories, deepest first.
    for path in sorted(
        (p for p in case_root.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        try:
            path.rmdir()
        except OSError:
            pass


def _run_bench_case(
    case: BenchCase,
    resolution: KernelResolution,
    preserved_run_dir: Path | None,
    cleanup_workdir: Path,
    *,
    verbose: bool = False,
    bench_mode: str = "torch-npu-profiler",
) -> PerfCaseRecord:
    profile_root, temp_dir = _create_local_bench_profile_dir(case.case_id, preserved_run_dir)
    try:
        t0 = time.monotonic()
        metrics, error_message = _profile_case_with_profiler(
            case,
            resolution,
            profile_root,
            verbose=verbose,
        )
        elapsed = time.monotonic() - t0
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
        cleanup_local_bench_extra_info(cleanup_workdir)
    if error_message is not None:
        return PerfCaseRecord(
            case_label=case.case_id,
            kernel_names=resolution.kernel_names,
            kernel_source=resolution.kernel_source,
            error_message=error_message,
            case_wall_clock_seconds=elapsed,
            bench_mode=bench_mode,
        )
    return PerfCaseRecord(
        case_label=case.case_id,
        kernel_names=resolution.kernel_names,
        kernel_source=resolution.kernel_source,
        metrics=metrics,
        case_wall_clock_seconds=elapsed,
        bench_mode=bench_mode,
    )


def _read_profiler_metrics(
    profile_root: Path,
    active_count: int,
    kernel_names: list[str],
    *,
    verbose: bool = False,
) -> PerfMetrics:
    kernel_details_path = find_optional_profile_csv(profile_root, "kernel_details.csv")
    kernel_details_rows = None
    if kernel_details_path is not None:
        if verbose:
            print(f"[metrics] found kernel_details.csv at {kernel_details_path}", file=sys.stderr)
        kernel_details_rows = parse_kernel_details_csv(
            kernel_details_path,
            active_count=active_count,
            verbose=verbose,
        )
        if kernel_details_rows.total_time_us > 0:
            return resolve_perf_metrics(
                kernel_details_rows.ops,
                kernel_names,
                total_op_avg_time_us=kernel_details_rows.total_op_avg_time_us,
                verbose=verbose,
            )
        if verbose:
            print(
                f"[metrics] kernel_details.csv total_time_us={kernel_details_rows.total_time_us}, "
                f"falling back to op_statistic.csv",
                file=sys.stderr,
            )

    op_statistic_path = find_latest_op_statistic_csv(profile_root)
    if op_statistic_path is not None:
        if verbose:
            print(f"[metrics] found op_statistic.csv at {op_statistic_path}", file=sys.stderr)
        op_statistic_rows = parse_op_statistic_csv(
            op_statistic_path,
            active_count=active_count,
            verbose=verbose,
        )
        return resolve_perf_metrics(
            op_statistic_rows.ops,
            kernel_names,
            total_op_avg_time_us=op_statistic_rows.total_op_avg_time_us,
            verbose=verbose,
        )

    if kernel_details_rows is not None:
        if verbose:
            print("[metrics] kernel_details.csv total_time_us=0, no other CSV found", file=sys.stderr)
        return resolve_perf_metrics(
            kernel_details_rows.ops,
            kernel_names,
            total_op_avg_time_us=kernel_details_rows.total_op_avg_time_us,
            verbose=verbose,
        )

    raise FileNotFoundError(
        f"No kernel_details.csv or op_statistic.csv found under {profile_root}"
    )


@contextmanager
def _suppress_output_streams() -> Iterator[None]:
    with open(os.devnull, "w", encoding="utf-8") as quiet_output:
        stdout_fd = os.dup(1)
        stderr_fd = os.dup(2)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            with redirect_stdout(quiet_output), redirect_stderr(quiet_output):
                os.dup2(quiet_output.fileno(), 1)
                os.dup2(quiet_output.fileno(), 2)
                yield
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(stdout_fd, 1)
            os.dup2(stderr_fd, 2)
            os.close(stdout_fd)
            os.close(stderr_fd)


def _synchronize(torch_module: Any) -> None:
    if hasattr(torch_module, "npu"):
        torch_module.npu.synchronize()


# ---------------------------------------------------------------------------
# Directory & path management
# ---------------------------------------------------------------------------

def _resolve_output_path(operator_file: Path, *, output: str | None = None) -> Path:
    if output is not None:
        return Path(output).expanduser().resolve()
    return perf_output_path(operator_file)


def _profile_output_root(parent: Path, case_id: str) -> Path:
    return parent / f"PROF_{_sanitize_case_id(case_id)}_{int(time.time() * 1000)}"


def resolve_local_bench_profile_output_root() -> ResolvedProfileOutputRoot:
    configured_root = bench_output_dir()
    if configured_root is not None:
        return str(Path(configured_root).expanduser().resolve()), HELIX_BENCH_OUTPUT_DIR
    return None, HELIX_BENCH_OUTPUT_DIR


def create_local_preserved_profile_run_dir(prefix: str) -> Path | None:
    configured_root, configured_env = resolve_local_bench_profile_output_root()
    if not configured_root:
        return None
    root = Path(configured_root).expanduser()
    if root.exists() and not root.is_dir():
        raise ValueError(f"{configured_env} must point to a directory: {root}")
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        set_directory_owner_only(root)
    run_dir = Path(tempfile.mkdtemp(prefix=prefix, dir=str(root)))
    set_directory_owner_only(run_dir)
    return run_dir


def _create_local_bench_profile_dir(
    case_id: str,
    preserved_run_dir: Path | None,
) -> PreservedRunDir:
    if preserved_run_dir is None:
        temp_dir = tempfile.TemporaryDirectory(prefix=f"helix-bench-{_sanitize_case_id(case_id)}-")
        return Path(temp_dir.name), temp_dir
    profile_root = preserved_run_dir.resolve() / f"case-{_sanitize_case_id(case_id)}"
    profile_root.mkdir(parents=True, exist_ok=False)
    set_directory_owner_only(profile_root)
    return profile_root, None


def set_directory_owner_only(path: Path) -> None:
    path.chmod(0o700)


def _sanitize_case_id(case_id: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in case_id)
    return sanitized or "case"


def cleanup_local_bench_extra_info(workdir: Path) -> None:
    extra_info_dir = workdir / "extra-info"
    if not extra_info_dir.is_dir():
        return
    shutil.rmtree(extra_info_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Shared benchmark runtime helper.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_cases = subparsers.add_parser("list-cases")
    _add_common_case_arguments(list_cases)

    # exec-one is the pure case executor for external profilers: the simulator
    # wraps this process and collects traces itself, so it must run the case
    # without any in-python profiling. In contrast, run-all uses the
    # in-process torch.profiler (profile_all_bench_cases) and writes perf files.
    exec_one = subparsers.add_parser("exec-one")
    _add_common_case_arguments(exec_one)

    profile_one = subparsers.add_parser("profile-one")
    _add_common_case_arguments(profile_one)
    profile_one.add_argument(
        "--emit-record",
        action="store_true",
        help="Print the selected case record as compact JSON.",
    )
    profile_one.add_argument(
        "--verbose",
        action="store_true",
        help="Keep profiler helper diagnostics visible.",
    )

    run_all = subparsers.add_parser("run-all")
    _add_common_case_arguments(run_all, include_case_id=False)
    run_all.add_argument("--output")
    run_all.add_argument("--verbose", action="store_true")
    return parser


def _add_common_case_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_case_id: bool = True,
) -> None:
    parser.add_argument("--bench-file", required=True)
    parser.add_argument("--operator-file", required=True)
    if include_case_id:
        parser.add_argument("--case-id")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bench_file = _resolve_existing_path(args.bench_file, "Bench file")
    operator_file = _resolve_existing_path(args.operator_file, "Operator file")

    try:
        if is_ascendc_operator(operator_file):
            build_ascendc_operator(operator_file)
        if args.command == "list-cases":
            cases, _resolution = load_bench_cases(bench_file, operator_file)
            for case in cases:
                print(case.case_id)
            return 0

        if args.command == "exec-one":
            result = execute_bench_case(
                bench_file,
                operator_file,
                args.case_id,
            )
            return _emit_result(result)

        if args.command == "profile-one":
            if bool(args.emit_record):
                record = profile_bench_case(
                    bench_file,
                    operator_file,
                    args.case_id,
                    verbose=bool(args.verbose),
                )
                print(_render_case_record_json(record))
                return 1 if record.error_message is not None else 0
            result = profile_bench_case_artifacts(
                bench_file,
                operator_file,
                args.case_id,
            )
            return _emit_result(result)

        if args.command == "run-all":
            result, perf_path = profile_all_bench_cases(
                bench_file,
                operator_file,
                verbose=bool(args.verbose),
                output=args.output,
            )
            print(f"Perf file: {perf_path}")
            return _emit_result(result)
    except (FileNotFoundError, RuntimeError, ValueError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    raise AssertionError(f"Unhandled bench runtime command: {args.command}")


def _resolve_existing_path(raw_path: str, label: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"{label} path does not exist: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"{label} path is not a file: {path}")
    return path


def _emit_result(result: ResultPayload) -> int:
    stdout_text = str(result["stdout"]).strip()
    stderr_text = str(result["stderr"]).strip()
    if stdout_text:
        print(stdout_text)
    if stderr_text:
        print(stderr_text, file=sys.stderr)
    return int(result["return_code"])


def _render_case_record_json(record: PerfCaseRecord) -> str:
    payload = {
        "case_label": record.case_label,
        "kernel_names": record.kernel_names,
        "kernel_source": record.kernel_source,
        "metrics": record.metrics,
        "error_message": record.error_message,
        "case_wall_clock_seconds": record.case_wall_clock_seconds,
    }
    return json.dumps(payload, separators=(",", ":"))


if __name__ == "__main__":
    raise SystemExit(main())
