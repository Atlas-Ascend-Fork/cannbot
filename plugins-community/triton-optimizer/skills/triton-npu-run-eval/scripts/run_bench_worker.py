# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Unified worker for the evaluation actions.

One CLI, four actions: ``run-test``, ``run-test-differential``, ``run-bench``
and ``profile-artifact``. The worker's interface to its parent is its CLI plus
the stdout line protocol: progress and case lines stream during execution,
exactly one ``final`` line ends a normal run, and a run that dies or fails
unexpectedly emits no ``final`` at all.
"""

from __future__ import annotations

import argparse
import io
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import Optional, Tuple

from ascendc_runtime import build_ascendc_operator, is_ascendc_operator
from env_registry import bench_defer_parse_enabled
from perf_artifacts import perf_output_path, write_perf_records_file
from profile_artifacts import has_retained_profile_file, is_retained_profile_file
from result_payload import ResultPayload, dump_result_fields, make_result, replace_result
from run_runtime import result_succeeded
from run_test_execution import run_differential_test, run_standalone_test
from result_payload import differential_archive_path
from test_contract import move_payload_tensors_to_cpu, serialize_payload_object
from torch_npu_warnings import suppress_torch_npu_owner_mismatch_warning
from triton_prewarm import maybe_prewarm_case_fns, reset_prewarm_budget
from worker_protocol import PHASE_BENCH, PHASE_PROFILE, PHASE_TEST
from worker_runtime import WorkerRuntime
import run_bench_execution


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=Path(__file__).name)
    parser.add_argument(
        "action",
        choices=("run-test", "run-test-differential", "run-bench", "profile-artifact"),
    )
    parser.add_argument("--test-file")
    parser.add_argument("--bench-file")
    parser.add_argument("--operator-file")
    parser.add_argument("--test-mode", choices=("standalone", "differential"))
    parser.add_argument("--bench-mode", default="torch-npu-profiler")
    parser.add_argument("--output")
    parser.add_argument("--case-id")
    parser.add_argument("--preserved-run-dir")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--warmup-cap", type=int)
    parser.add_argument("--repeats-cap", type=int)
    parser.add_argument("--ref-operator-file")
    parser.add_argument("--ref-result")
    parser.add_argument(
        "--accuracy-mode",
        choices=("npu-contract", "dtype-close", "cann-bench"),
    )
    parser.add_argument("--baseline-operator-file")
    parser.add_argument("--emit-serialized-payload", action="store_true")
    parser.add_argument("--no-archive", action="store_true")
    return parser


# ---------------------------------------------------------------------------
# run-test
# ---------------------------------------------------------------------------


def _run_test_action(args: argparse.Namespace) -> int:
    if args.test_file is None or args.operator_file is None or args.test_mode is None:
        raise ValueError("run-test requires --test-file, --operator-file and --test-mode")
    test_file = Path(args.test_file).expanduser().resolve()
    operator_file = Path(args.operator_file).expanduser().resolve()
    runtime = WorkerRuntime(PHASE_TEST)
    runtime.arm_sigterm_exit()
    if str(args.test_mode) == "standalone":
        result, archived_result, serialized_payload = _run_standalone_case(
            args, test_file, operator_file, runtime
        )
    else:
        result, archived_result, serialized_payload = _run_differential_payload_case(
            args, test_file, operator_file, runtime
        )
    runtime.emit_final(
        {
            "result": dump_result_fields(result),
            "archived_result": archived_result,
            "serialized_payload": serialized_payload,
        }
    )
    return int(result["return_code"])


def _run_standalone_case(
    args: argparse.Namespace, test_file: Path, operator_file: Path, runtime: WorkerRuntime
) -> Tuple[ResultPayload, Optional[str], Optional[str]]:
    if args.case_id is not None:
        raise ValueError("--case-id is supported only with differential tests.")
    if args.no_archive or args.emit_serialized_payload:
        raise ValueError("Standalone tests do not support differential payload options.")
    result = run_standalone_test(
        test_file, operator_file, verbose=bool(args.verbose), emit=runtime
    )
    return result, None, None


def _run_differential_payload_case(
    args: argparse.Namespace, test_file: Path, operator_file: Path, runtime: WorkerRuntime
) -> Tuple[ResultPayload, Optional[str], Optional[str]]:
    archive_path = (
        None
        if args.emit_serialized_payload or args.no_archive
        else differential_archive_path(operator_file)
    )
    result, payload = run_differential_test(
        test_file,
        operator_file,
        archive_path=archive_path,
        case_id=args.case_id,
        verbose=bool(args.verbose),
        emit=runtime,
    )
    archived_result = (
        str(archive_path.resolve())
        if archive_path is not None
        and int(result["return_code"]) == 0
        and not bool(result["stalled"])
        and payload is not None
        else None
    )
    serialized_payload = (
        serialize_payload_object(payload)
        if args.emit_serialized_payload and payload is not None
        else None
    )
    return result, archived_result, serialized_payload


# ---------------------------------------------------------------------------
# run-test-differential: reference run + candidate run + compare in one process
# ---------------------------------------------------------------------------


def _run_test_differential_action(args: argparse.Namespace) -> int:
    if args.test_file is None or args.ref_operator_file is None or args.operator_file is None:
        raise ValueError(
            "run-test-differential requires --test-file, --ref-operator-file and --operator-file"
        )
    unsupported_options = (
        args.ref_result is not None,
        args.no_archive,
        args.emit_serialized_payload,
        args.test_mode is not None,
        args.bench_file is not None,
        args.baseline_operator_file is not None,
    )
    if any(unsupported_options):
        raise ValueError(
            "run-test-differential does not support --ref-result, --no-archive, "
            "--emit-serialized-payload, --test-mode, --bench-file or "
            "--baseline-operator-file."
        )
    test_file = Path(args.test_file).expanduser().resolve()
    ref_operator_file = Path(args.ref_operator_file).expanduser().resolve()
    operator_file = Path(args.operator_file).expanduser().resolve()
    runtime = WorkerRuntime(PHASE_TEST)
    runtime.arm_sigterm_exit()

    ref_result, ref_payload = _run_differential_phase(
        test_file, ref_operator_file, args, runtime, role="reference"
    )
    if ref_payload is None:
        return int(ref_result["return_code"]) or 1
    # The reference payload stays alive through the candidate phase; move its
    # NPU result tensors to CPU so the candidate phase starts with a free
    # device (the three-process flow released them at reference-worker exit).
    move_payload_tensors_to_cpu(ref_payload)
    # Each phase is logically its own evaluation and gets a full prewarm
    # submission budget.
    reset_prewarm_budget()

    candidate_result, candidate_payload = _run_differential_phase(
        test_file, operator_file, args, runtime, role="candidate", seed_payload=ref_payload
    )
    if candidate_payload is None:
        return int(candidate_result["return_code"]) or 1

    return _compare_differential_phase(
        args, test_file, ref_operator_file,
        ref_payload=ref_payload, candidate_payload=candidate_payload, runtime=runtime,
    )


def _run_differential_phase(
    test_file: Path,
    operator_file: Path,
    args: argparse.Namespace,
    runtime: WorkerRuntime,
    *,
    role: str,
    seed_payload: object | None = None,
) -> Tuple[ResultPayload, object | None]:
    """Run one differential phase; emit the failure final and drop the payload on failure."""
    runtime.emit_progress(
        "phase", message=f"[run-test] differential {role} phase", role=role
    )
    result, payload = run_differential_test(
        test_file,
        operator_file,
        archive_path=None,
        case_id=args.case_id,
        seed_payload=seed_payload,
        verbose=bool(args.verbose),
        emit=runtime,
    )
    if int(result["return_code"]) != 0 or bool(result["stalled"]) or payload is None:
        runtime.emit_final(
            {
                "result": dump_result_fields(result),
                "archived_result": None,
                "serialized_payload": None,
                "failed_phase": role,
            }
        )
        return result, None
    return result, payload


def _compare_differential_phase(
    args: argparse.Namespace,
    test_file: Path,
    ref_operator_file: Path,
    *,
    ref_payload: object,
    candidate_payload: object,
    runtime: WorkerRuntime,
) -> int:
    # compare_result's import chain pulls torch in at module level; the
    # imports stay inside the differential call path so the other actions
    # still import torch only after bootstrap_torch_npu has installed the
    # autoload guard.
    from cann_bench_native_replay import create_native_ref_operator
    from compare_result import compare_result_payload_objects
    from npu_compare_common import resolve_accuracy_mode

    runtime.emit_progress("phase", message="[run-test] differential compare phase", role="compare")
    resolved_accuracy_mode = resolve_accuracy_mode(args.accuracy_mode)
    native_ref_operator = None
    if resolved_accuracy_mode == "cann-bench":
        native_ref_operator = create_native_ref_operator(test_file, ref_operator_file)
    compare_out_buffer = io.StringIO()
    compare_err_buffer = io.StringIO()
    with redirect_stdout(compare_out_buffer), redirect_stderr(compare_err_buffer):
        compare_code = compare_result_payload_objects(
            ref_payload,
            candidate_payload,
            accuracy_mode=resolved_accuracy_mode,
            native_ref_operator=native_ref_operator,
        )
    compare_text = compare_out_buffer.getvalue()
    compare_stderr = compare_err_buffer.getvalue()
    # Passthrough output is protocol-defused inside emit_passthrough: nothing
    # the compared code printed can impersonate a protocol envelope.  The
    # final payload carries the same text as the result stdout.
    runtime.emit_passthrough(compare_text)
    runtime.emit_final(
        {
            "result": dump_result_fields(
                make_result(return_code=compare_code, stdout=compare_text, stderr=compare_stderr)
            ),
            "archived_result": None,
            "serialized_payload": None,
        }
    )
    return compare_code


# ---------------------------------------------------------------------------
# Benchmark phase
# ---------------------------------------------------------------------------


def _preserved_root(args: argparse.Namespace) -> Optional[Path]:
    return None if args.preserved_run_dir in {None, "__NONE__"} else Path(args.preserved_run_dir)


def _perf_output_path(operator_file: Path, *, output: Optional[str]) -> Path:
    if output is not None:
        return Path(output).expanduser().resolve()
    return perf_output_path(operator_file)


def _run_bench_phase(
    bench_file: Path,
    operator_file: Path,
    *,
    bench_mode: str,
    output: Optional[str],
    verbose: bool,
    warmup_cap: Optional[int],
    repeats_cap: Optional[int],
    preserved_root: Optional[Path],
    emit: WorkerRuntime,
) -> Tuple[ResultPayload, Path]:
    """Run one full benchmark in-process and write its perf file exactly once."""
    if is_ascendc_operator(operator_file):
        build_ascendc_operator(operator_file)
    if (warmup_cap is None) != (repeats_cap is None):
        raise ValueError("Both execution limits are required together")
    cases, resolution = run_bench_execution.load_bench_cases(bench_file, operator_file)
    # Bench cases close over their inputs without exposing them, so pairs
    # carry None: clone/restore no-ops and dry-run input mutations persist,
    # which is sound here because bench times executions without comparing
    # values.  One hook covers every bench path below: perf-counter and both
    # profile paths (deferred and synchronous).
    maybe_prewarm_case_fns([(case.fn, None) for case in cases], emit=emit, label="run-bench")
    if bench_mode == "perf-counter":
        # Caps apply to the profiler path's per-case iteration counts only.
        return run_bench_execution.time_all_bench_cases(
            bench_file,
            operator_file,
            bench_mode="perf-counter",
            output=output,
            preloaded=(cases, resolution),
            emit=emit,
        )
    cases = _capped_cases(cases, warmup_cap, repeats_cap)
    if bench_defer_parse_enabled() and run_bench_execution.deferred_parse_warranted(cases):
        return _run_deferred_bench(
            bench_file, operator_file, cases, resolution,
            preserved_root=preserved_root, verbose=verbose, output=output, emit=emit,
        )
    return run_bench_execution.profile_all_bench_cases(
        bench_file,
        operator_file,
        preloaded=(cases, resolution),
        verbose=verbose,
        output=output,
        emit=emit,
    )


def _capped_cases(
    cases: list, warmup_cap: Optional[int], repeats_cap: Optional[int]
) -> list:
    if warmup_cap is None or repeats_cap is None:
        return cases
    return [
        replace(
            case,
            warmup=min(case.warmup, warmup_cap),
            repeats=min(case.repeats, repeats_cap),
        )
        for case in cases
    ]


def _run_deferred_bench(
    bench_file: Path,
    operator_file: Path,
    cases: list,
    resolution: object,
    *,
    preserved_root: Optional[Path],
    verbose: bool,
    output: Optional[str],
    emit: WorkerRuntime,
) -> Tuple[ResultPayload, Path]:
    """Deferred parse pipeline: profile with online CANN parsing disabled
    while a background thread parses sealed batches; the worker writes the
    perf file once from the returned records."""
    records = run_bench_execution.profile_bench_cases_deferred(
        cases,
        resolution,
        preserved_root=preserved_root,
        verbose=verbose,
        cleanup_workdir=bench_file.parent,
        emit=emit,
    )
    perf_path = _perf_output_path(operator_file, output=output)
    write_perf_records_file(perf_path, records)
    errors = []
    for record in records:
        if record.error_message is not None:
            errors.append(f"{record.case_label}: {record.error_message}")
    return (
        make_result(return_code=1 if errors else 0, stdout="", stderr="\n".join(errors)),
        perf_path,
    )


# ---------------------------------------------------------------------------
# run-bench
# ---------------------------------------------------------------------------


def _run_bench_action(args: argparse.Namespace) -> int:
    if args.bench_file is None or args.operator_file is None:
        raise ValueError("run-bench requires --bench-file and --operator-file")
    bench_file = Path(args.bench_file).expanduser().resolve()
    operator_file = Path(args.operator_file).expanduser().resolve()
    runtime = WorkerRuntime(PHASE_BENCH)
    runtime.arm_sigterm_exit()
    result, perf_path = _run_bench_phase(
        bench_file,
        operator_file,
        bench_mode=str(args.bench_mode),
        output=args.output,
        verbose=bool(args.verbose),
        warmup_cap=args.warmup_cap,
        repeats_cap=args.repeats_cap,
        preserved_root=_preserved_root(args),
        emit=runtime,
    )
    runtime.emit_final({"result": dump_result_fields(result), "perf_path": str(perf_path)})
    return int(result["return_code"])


# ---------------------------------------------------------------------------
# profile-artifact
# ---------------------------------------------------------------------------


def run_profile_artifact_case_entry(
    bench_file: Path,
    operator_file: Path,
    case_id: str,
) -> tuple[ResultPayload, str | None]:
    """Profile one case and return the result plus the retained PROF_* directory.

    Resolves the profile directory against the current working directory, so
    callers must run this with the benchmark workspace as cwd (the worker
    subprocess is always launched with the benchmark workspace as cwd).
    """
    if is_ascendc_operator(operator_file):
        build_ascendc_operator(operator_file)
    result = run_bench_execution.profile_bench_case_artifacts(bench_file, operator_file, case_id)
    profile_name = None
    if result_succeeded(result):
        profile_name = _latest_profile_name()
        if profile_name is not None:
            _prune_profile_files(Path(profile_name))
    if result_succeeded(result) and profile_name is None:
        result = replace_result(
            result,
            return_code=1,
            stderr=str(result["stderr"]) + "\nProfile worker succeeded but no valid PROF_* directory was produced.",
        )
    return result, profile_name


def _latest_profile_name(search_root: Path = Path(".")) -> str | None:
    candidates = [
        path
        for path in search_root.rglob("PROF_*")
        if path.is_dir() and has_retained_profile_file(path)
    ]
    if not candidates:
        return None
    outer_candidates = [
        path
        for path in candidates
        if (path / "ASCEND_PROFILER_OUTPUT").is_dir()
    ]
    if outer_candidates:
        candidates = outer_candidates
    return max(candidates, key=lambda path: path.stat().st_mtime).as_posix()


def _prune_profile_files(profile_dir: Path) -> None:
    for path in sorted(profile_dir.rglob("*"), reverse=True):
        if path.is_file() and not is_retained_profile_file(path):
            path.unlink()
        elif path.is_dir() and path != profile_dir:
            try:
                path.rmdir()
            except OSError:
                pass


def _run_profile_artifact_action(args: argparse.Namespace) -> int:
    if args.bench_file is None or args.operator_file is None:
        raise ValueError("profile-artifact requires --bench-file and --operator-file")
    if args.case_id is None:
        raise ValueError("profile-artifact requires --case-id")
    runtime = WorkerRuntime(PHASE_PROFILE)
    runtime.arm_sigterm_exit()
    result, profile_name = run_profile_artifact_case_entry(
        Path(args.bench_file), Path(args.operator_file), str(args.case_id)
    )
    profile_dir = None if profile_name is None else str(Path(profile_name).resolve())
    runtime.emit_final(
        {
            "result": dump_result_fields(result),
            "profile_dir": profile_dir,
            "profile_name": profile_name,
        }
    )
    return int(result["return_code"])


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cwd = str(Path.cwd().resolve())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    suppress_torch_npu_owner_mismatch_warning()
    try:
        if args.action == "run-test":
            return _run_test_action(args)
        if args.action == "run-test-differential":
            return _run_test_differential_action(args)
        if args.action == "run-bench":
            return _run_bench_action(args)
        if args.action == "profile-artifact":
            return _run_profile_artifact_action(args)
        raise ValueError(f"Unsupported worker action: {args.action}")
    except Exception:
        # An unexpected failure must never look like a completed run: report
        # to stderr, exit nonzero, emit no final protocol line.
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
