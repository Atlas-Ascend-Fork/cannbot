# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Shared optimize-round lifecycle helpers for test and benchmark commands."""

from __future__ import annotations
# ruff: noqa: E402

import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
from typing import Iterator, Literal, cast

from execution_records import (
    active_state_path,
    append_evidence,
    ensure_reference_result,
    load_state,
    record_generated_file,
    sha256_file,
    validate_managed_path,
)

from env_registry import (
    ASCEND_RT_VISIBLE_DEVICES,
    HELIX_OPTIMIZE_DELETE_PT_FILES,
    TRITON_ALL_BLOCKS_PARALLEL,
)


def parse_npu_devices(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    raw_parts = tuple(part.strip() for part in raw.split(","))
    if not raw_parts or any(not part for part in raw_parts):
        raise ValueError("device list must be a comma-separated non-empty list.")
    devices: list[str] = []
    for part in raw_parts:
        devices.extend(_expand_device_token(part))
    expanded = tuple(devices)
    if len(set(expanded)) != len(expanded):
        raise ValueError(f"device list must not contain duplicate devices: {raw!r}")
    return expanded


def _expand_device_token(token: str) -> list[str]:
    if "-" not in token:
        return [token]
    if token.count("-") != 1:
        raise ValueError(f"device range token is invalid: {token!r}")
    start_text, end_text = token.split("-", 1)
    if not start_text.isdigit() or not end_text.isdigit():
        raise ValueError(f"device range token is invalid: {token!r}")
    start = int(start_text)
    end = int(end_text)
    if start > end:
        raise ValueError(f"device range token must be ascending: {token!r}")
    return [str(value) for value in range(start, end + 1)]


_BLOCKS_PARALLEL_UNSAFE_VALUE = "1"
_BLOCKS_PARALLEL_SAFE_VALUE = "0"
_PT_CLEANUP_MODES = frozenset({"never", "round", "run-test"})
_LEGACY_ROUND_CLEANUP_VALUES = frozenset({"1", "true", "yes", "on"})
_LEGACY_NEVER_CLEANUP_VALUES = frozenset({"0", "false", "no", "off"})
PtCleanupMode = Literal["never", "round", "run-test"]
_TIMED_COMMANDS = frozenset(
    {"run-test-baseline", "run-test-optimize", "run-bench", "run-bench-baseline"}
)
_OPTIMIZE_ROUND_DIR = re.compile(r"opt-round-\d+$")
_OPTIMIZE_ROUND_GATE_PHASES = frozenset(
    {"awaiting_round_start", "round_active", "deep_analysis"}
)


class TerminationSignalReceived(BaseException):
    """SIGTERM during a timed command, unwinding into the timing finalizer.

    A signal handler can only interrupt the main flow by raising. This custom
    BaseException carries the conventional 128+N exit code through
    timing_exception_return_code without raising SystemExit outside a process
    entry point.
    """

    def __init__(self, signum: int) -> None:
        super().__init__(f"received termination signal {signum}")
        self.signum = signum
        self.exit_code = 128 + signum


@contextlib.contextmanager
def guard_termination_signal(command: str) -> Iterator[None]:
    if command not in _TIMED_COMMANDS:
        yield
        return
    previous_handler = signal.getsignal(signal.SIGTERM)

    def _handle_sigterm(signum: int, _frame: object) -> None:
        # Unwind into the command timing finalizer, then preserve SIGTERM's exit code.
        # Raising here is deliberate: a signal handler can only interrupt the
        # main flow by raising, and TerminationSignalReceived carries the
        # conventional 128+N exit code through timing_exception_return_code.
        raise TerminationSignalReceived(signum)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


def pt_cleanup_mode() -> PtCleanupMode:
    raw_value = os.environ.get(HELIX_OPTIMIZE_DELETE_PT_FILES)
    if raw_value is None:
        return "round"
    value = raw_value.strip().lower()
    if value in _PT_CLEANUP_MODES:
        return cast(PtCleanupMode, value)
    if value in _LEGACY_ROUND_CLEANUP_VALUES:
        return "round"
    if value in _LEGACY_NEVER_CLEANUP_VALUES:
        return "never"
    return "round"


def cleanup_run_test_pt_files(paths: tuple[Path | None, ...]) -> list[str]:
    if pt_cleanup_mode() != "run-test":
        return []
    cleaned: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        if path is None:
            continue
        resolved_path = path.resolve()
        if resolved_path in seen:
            continue
        seen.add(resolved_path)
        if _is_ordinary_pt_result_file(resolved_path) and resolved_path.is_file():
            try:
                resolved_path.unlink()
            except OSError:
                continue
            cleaned.append(str(resolved_path))
    return cleaned


@dataclass(frozen=True)
class RoundContext:
    """An optimize round (or the baseline-phase stream) located on disk.

    ``round_name`` is the round directory name exactly as stored in the
    workflow state; start-round only ever writes single opt-round-N names,
    and the baseline phase uses the literal ``"baseline"``. ``round_dir``
    joins the two and is only meaningful for actual rounds.
    """

    workspace_root: Path
    round_name: str

    @property
    def round_dir(self) -> Path:
        return self.workspace_root / self.round_name


def active_optimize_round_context(*paths: Path) -> RoundContext | None:
    """Return the active round context, or None when no round is active."""
    state_path = active_state_path(*paths)
    if state_path is None:
        return None
    try:
        raw_payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw_payload, dict):
        return None
    payload = cast(dict[str, object], raw_payload)
    if payload.get("phase") != "round_active":
        return None
    current_round = payload.get("current_round")
    rounds = payload.get("rounds")
    if not isinstance(current_round, int) or not isinstance(rounds, dict):
        return None
    round_entry = cast(dict[str, object], rounds).get(str(current_round))
    if not isinstance(round_entry, dict):
        return None
    round_entry_dict = cast(dict[str, object], round_entry)
    round_dir = round_entry_dict.get("round_dir")
    if round_entry_dict.get("status") != "active" or not isinstance(round_dir, str) or not round_dir:
        return None
    return RoundContext(workspace_root=state_path.parent.parent, round_name=round_dir)


def baseline_phase_timing_context(*paths: Path) -> RoundContext | None:
    """Return the baseline-phase timing context, or None.

    The baseline phase is not a numbered round; baseline repair/prepare
    evaluations share one timing file named after the workflow phase so the
    repair launch keeps the same per-phase accounting as active rounds.
    """
    state_path = active_state_path(*paths)
    if state_path is None:
        return None
    payload = load_state(state_path)
    if payload is None or payload.get("phase") != "baseline":
        return None
    return RoundContext(workspace_root=state_path.parent.parent, round_name="baseline")


def require_optimize_round(
    command: str,
    operator_path: Path,
    *related_paths: Path,
) -> RoundContext:
    """Require an active workflow round before running optimize evaluation."""
    paths = (operator_path, *related_paths)
    state_path = active_state_path(*paths)
    if state_path is None:
        raise ValueError(
            f"{command} requires an active optimize round; run `start-round` first"
        )
    round_context = active_optimize_round_context(*paths)
    if round_context is None:
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"unable to read optimize workflow state: {exc}") from exc
        payload_object = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
        phase = payload_object.get("phase")
        raise ValueError(
            f"{command} requires an active optimize round; current workflow phase is "
            f"{phase!s}. Run `start-round` first"
        )
    resolved_operator_path = operator_path.resolve()
    try:
        resolved_operator_path.relative_to(round_context.round_dir.resolve())
    except ValueError as exc:
        raise ValueError(
            f"{command} operator must belong to active round {round_context.round_name}: "
            f"{resolved_operator_path}"
        ) from exc
    return round_context


def optimize_round_gate_required(*paths: Path) -> bool:
    """Return whether an existing workflow state requires the round gate.

    Baseline setup is intentionally outside the round gate because generated
    tests and benchmarks may run before the baseline has been submitted.
    Malformed state remains gated so it cannot silently bypass workflow checks.
    """
    state_path = active_state_path(*paths)
    if state_path is None:
        return False
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True
    if not isinstance(payload, dict):
        return True
    phase = cast(dict[str, object], payload).get("phase")
    return phase in _OPTIMIZE_ROUND_GATE_PHASES


def is_optimize_round_candidate(path: Path) -> bool:
    """Return whether a candidate is directly inside an ``opt-round-N`` directory."""
    return _OPTIMIZE_ROUND_DIR.fullmatch(path.resolve().parent.name) is not None


def deep_analysis_context(*paths: Path) -> dict[str, object] | None:
    state_path = active_state_path(*paths)
    if state_path is None:
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    state = cast(dict[str, object], payload)
    if state.get("phase") != "deep_analysis":
        return None
    return _deep_analysis_context_from_state(state_path, state)


def _deep_analysis_context_from_state(
    state_path: Path,
    state: dict[str, object],
) -> dict[str, object] | None:
    """Build the deep-analysis context from a phase-checked workflow state."""
    current_round = state.get("current_round")
    rounds = state.get("rounds")
    baseline = state.get("baseline")
    if not isinstance(current_round, int) or not isinstance(rounds, dict) or not isinstance(baseline, dict):
        return None
    round_entry = cast(dict[str, object], rounds).get(str(current_round))
    if not isinstance(round_entry, dict):
        return None
    round_entry = cast(dict[str, object], round_entry)
    deep_analysis = round_entry.get("deep_analysis")
    integrity = cast(dict[str, object], baseline).get("integrity")
    if not isinstance(deep_analysis, dict) or not isinstance(integrity, dict):
        return None
    deep_analysis = cast(dict[str, object], deep_analysis)
    integrity = cast(dict[str, object], integrity)
    operator_relative = deep_analysis.get("operator_file")
    operator_sha256 = deep_analysis.get("operator_sha256")
    bench_file = integrity.get("bench_file")
    bench_sha256 = integrity.get("bench_sha256")
    round_dir = round_entry.get("round_dir")
    for value in (operator_relative, operator_sha256, bench_file, bench_sha256, round_dir):
        if not isinstance(value, str) or not value:
            return None
    workspace_root = state_path.parent.parent.resolve()
    operator_file = workspace_root / str(operator_relative)
    if not operator_file.is_file() or sha256_file(operator_file) != operator_sha256:
        return None
    canonical_bench_file = Path(str(bench_file)).resolve()
    if (
        not canonical_bench_file.is_file()
        or sha256_file(canonical_bench_file) != bench_sha256
    ):
        return None
    return {
        "workspace_root": str(workspace_root),
        "round_dir": str(workspace_root / str(round_dir)),
        "operator_file": str(operator_file.resolve()),
        "operator_sha256": operator_sha256,
        "bench_file": str(canonical_bench_file),
        "bench_sha256": bench_sha256,
    }


def deep_analysis_state_path(*paths: Path) -> Path | None:
    """Return an active deep-analysis state path even when its evidence is invalid."""
    state_path = active_state_path(*paths)
    if state_path is None:
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(payload, dict) and cast(dict[str, object], payload).get("phase") == "deep_analysis":
        return state_path
    return None


def validate_managed_input(
    path: Path,
    *,
    role: str,
) -> tuple[Path | None, dict[str, object] | None]:
    state_path = active_state_path(path)
    if state_path is None:
        return None, None
    state = load_state(state_path)
    if state is None:
        return state_path, None
    if state.get("phase") != "round_active":
        return state_path, None
    baseline = state.get("baseline")
    if not isinstance(baseline, dict):
        return state_path, None
    integrity = cast(dict[str, object], baseline).get("integrity")
    if not isinstance(integrity, dict):
        return state_path, None
    return state_path, validate_managed_path(state_path, role=role, supplied=path)


def managed_round_context(*paths: Path) -> tuple[Path, dict[str, object]] | None:
    state_path = active_state_path(*paths)
    if state_path is None:
        return None
    state = load_state(state_path)
    if state is None:
        return None
    if state.get("phase") != "round_active":
        return None
    baseline = state.get("baseline")
    if not isinstance(baseline, dict):
        return None
    integrity = cast(dict[str, object], baseline).get("integrity")
    if not isinstance(integrity, dict):
        # Older/resumed sessions may predate private integrity state.
        return None
    return state_path, cast(dict[str, object], integrity)


def record_managed_generated_file(state_path: Path, *, role: str, path: Path) -> dict[str, object]:
    return record_generated_file(state_path, role=role, path=path)


def ensure_managed_reference_result(state_path: Path, path: Path) -> None:
    ensure_reference_result(state_path, path)


def append_managed_evidence(state_path: Path, **evidence: object) -> dict[str, object]:
    """Append one managed evidence record.

    Thin keyword-forwarding wrapper over ``execution_records.append_evidence``;
    that function owns the authoritative keyword contract, so it is not
    mirrored here.
    """
    return append_evidence(state_path, **evidence)


def append_optimize_timing_event(
    context: RoundContext | None,
    *,
    event: str,
    command: str,
    fast_probe: bool = False,
    return_code: int | None = None,
    case_id: str | None = None,
    test_file: Path | None = None,
    bench_file: Path | None = None,
    operator_file: Path | None = None,
) -> None:
    """Append one event to the context's ``.helix/round-timings/<round>.jsonl``.

    A None context disables timing recording entirely.
    """
    if context is None:
        return
    try:
        log_path = (
            context.workspace_root / ".helix" / "round-timings" / f"{context.round_name}.jsonl"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {
            "event": event,
            "timestamp": _utc_now(),
            "round": context.round_name,
            "command": command,
        }
        if fast_probe:
            payload["fast_probe"] = True
        if return_code is not None:
            payload["return_code"] = return_code
        assigned_devices = _timing_assigned_devices()
        if assigned_devices is not None:
            payload["assigned_devices"] = list(assigned_devices)
        if case_id is not None:
            payload["case_id"] = case_id
        for key, path in (
            ("test_file", test_file),
            ("bench_file", bench_file),
            ("operator_file", operator_file),
        ):
            if path is not None:
                payload[key] = str(path.resolve())
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except OSError:
        return


def _timing_assigned_devices() -> tuple[str, ...] | None:
    raw_devices = os.environ.get(ASCEND_RT_VISIBLE_DEVICES)
    if raw_devices is None:
        return None
    try:
        return parse_npu_devices(raw_devices)
    except ValueError:
        return None


@contextlib.contextmanager
def guard_operator_execution_env(command: str) -> Iterator[None]:
    if command not in {
        "run-test-baseline",
        "run-test-convert",
        "run-test-optimize",
        "run-bench",
        "run-bench-baseline",
        "profile-bench",
    }:
        yield
        return
    previous = os.environ.get(TRITON_ALL_BLOCKS_PARALLEL)
    if previous != _BLOCKS_PARALLEL_UNSAFE_VALUE:
        yield
        return
    os.environ[TRITON_ALL_BLOCKS_PARALLEL] = _BLOCKS_PARALLEL_SAFE_VALUE
    try:
        yield
    finally:
        os.environ[TRITON_ALL_BLOCKS_PARALLEL] = previous


def _is_ordinary_pt_result_file(path: Path) -> bool:
    name_lower = path.name.lower()
    return name_lower == "test_result.pt" or name_lower.endswith("_result.pt")


def timing_exception_return_code(exc: BaseException) -> int:
    if isinstance(exc, KeyboardInterrupt):
        return 130
    if isinstance(exc, TerminationSignalReceived):
        return exc.exit_code
    # CLI 入口路径（如 argparse 的 parser.error）以 SystemExit 携带退出码；
    # 这里通过 code 属性识别而不显式引用 SystemExit 类型。
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    return 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
