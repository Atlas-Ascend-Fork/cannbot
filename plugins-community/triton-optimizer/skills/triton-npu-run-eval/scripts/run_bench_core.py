# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Recording wrapper for run-bench: workflow gates, timing events, and evidence."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path

from execution_lifecycle import (
    RoundContext,
    active_optimize_round_context,
    is_optimize_round_candidate,
    managed_round_context,
    optimize_round_gate_required,
    require_optimize_round,
    validate_managed_input,
)
from execution_lifecycle import (
    append_managed_evidence,
    append_optimize_timing_event,
    baseline_phase_timing_context,
    timing_exception_return_code,
)
from execution_records import append_baseline_evidence
from run_bench_executor import (
    BenchExecution,
    RunBenchSpec,
    compare_results,
    execute_benchmarks,
    prepare_execution,
)
from run_bench_executor import RunBenchRequest


@dataclass(frozen=True)
class RunBenchContext:
    """Managed-workflow context the recording wrapper resolved for a request.

    ``timing`` is the stream the run is accounted to (the active round, or
    "baseline" during the baseline phase); it is None when the run records
    no timing. ``active_round`` is the actual optimize-round gate result
    (None outside a round, where ``timing`` may still be the baseline-phase
    stream). The canonical baseline paths are the managed baseline inputs
    pinned in workflow state — the only integrity keys this flow reads — and
    are None outside a managed round; the perf path is also None when an
    older or damaged state lacks the key.
    """

    state_path: Path | None
    timing: RoundContext | None
    active_round: RoundContext | None
    canonical_baseline_operator_file: Path | None
    canonical_baseline_perf_file: Path | None


def run_bench(request: RunBenchRequest) -> int:
    """Run one structured run-bench request with workflow recording."""
    context = _resolve_context(request)
    if context is None:
        return 1
    spec = prepare_execution(
        request,
        canonical_baseline_operator_file=context.canonical_baseline_operator_file,
        canonical_baseline_perf_file=context.canonical_baseline_perf_file,
        optimize_round_active=context.active_round is not None,
        managed_state_path=context.state_path,
    )
    return _execute_with_recording(request, context, spec)


def _resolve_context(request: RunBenchRequest) -> RunBenchContext | None:
    """Resolve managed-workflow gates and the timing context for the request."""
    managed = managed_round_context(request.bench_file, request.operator_file)
    if is_optimize_round_candidate(request.operator_file) and optimize_round_gate_required(
        request.bench_file, request.operator_file
    ):
        try:
            round_context = require_optimize_round(request.command, request.operator_file, request.bench_file)
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return None
    else:
        round_context = active_optimize_round_context(request.bench_file, request.operator_file)
    state_path = managed[0] if managed is not None else None
    if managed is not None:
        try:
            validate_managed_input(request.bench_file, role="bench_file")
            if round_context is not None:
                request.operator_file.resolve().relative_to(round_context.round_dir.resolve())
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return None
    timing = round_context
    if timing is None:
        # The baseline phase is outside the round gate; baseline repair/prepare
        # benchmarks still belong to a per-phase timing stream.
        timing = baseline_phase_timing_context(request.bench_file, request.operator_file)
    canonical_operator = None
    canonical_perf = None
    if managed is not None:
        integrity = managed[1]
        canonical_operator = Path(str(integrity["baseline_operator_file"]))
        # Read the perf key tolerantly: the pre-split flow only touched it on
        # the canonical-baseline branch, so a custom-baseline run must not
        # depend on it, and an older or damaged state may lack it (the
        # canonical branch then degrades to a comparison-less run).
        raw_perf = integrity.get("baseline_perf_file")
        canonical_perf = Path(raw_perf) if isinstance(raw_perf, str) else None
    return RunBenchContext(
        state_path=state_path,
        timing=timing,
        active_round=round_context,
        canonical_baseline_operator_file=canonical_operator,
        canonical_baseline_perf_file=canonical_perf,
    )


def _execute_with_recording(request: RunBenchRequest, context: RunBenchContext, spec: RunBenchSpec) -> int:
    """Run the prepared execution inside the recording envelope.

    Emits the timing start/end events around the benchmark runs, records
    managed perf evidence strictly between the runs and the comparison (the
    artifact fact must land even if the comparison later crashes), and
    records baseline evidence plus the end event in the finally block, on
    success, handled failure, and exception paths alike.
    """
    append_optimize_timing_event(
        context.timing,
        event="run_bench_start",
        command=request.command,
        fast_probe=request.fast_probe,
        bench_file=request.bench_file,
        operator_file=request.operator_file,
    )
    final_code = 1
    execution: BenchExecution | None = None
    try:
        execution = execute_benchmarks(spec)
        final_code = execution.benchmark_return_code
        if request.command != "run-bench-baseline":
            evidence_ready = (
                context.state_path is not None
                and execution.benchmark_return_code == 0
                and execution.candidate_perf_path is not None
                and execution.baseline_perf_path is not None
            )
            if evidence_ready:
                _record_managed_perf_evidence(request, context, spec, execution)
            final_code = compare_results(spec, execution)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        final_code = 1
    except BaseException as exc:
        final_code = timing_exception_return_code(exc)
        raise
    finally:
        if execution is None or execution.record_baseline_evidence:
            # _record_baseline_evidence never raises (it renders its own
            # failures as return code 1), so it cannot mask an in-flight
            # exception; the return happens after the finally block instead.
            final_code = _record_baseline_evidence(request, execution, final_code)
        append_optimize_timing_event(
            context.timing,
            event="run_bench_end",
            command=request.command,
            fast_probe=request.fast_probe,
            return_code=final_code,
            bench_file=request.bench_file,
            operator_file=request.operator_file,
        )
    return final_code


def _record_managed_perf_evidence(
    request: RunBenchRequest,
    context: RunBenchContext,
    spec: RunBenchSpec,
    execution: BenchExecution,
) -> None:
    """Append the round's perf evidence for a successful canonical or custom run."""
    if context.state_path is None:
        raise RuntimeError("internal error: managed perf evidence requires workflow state")  # gated by the caller
    round_name = context.active_round.round_name if context.active_round is not None else ""
    if execution.using_canonical_baseline:
        append_managed_evidence(
            context.state_path,
            round_name=round_name,
            command=request.command,
            mode=spec.bench_mode,
            artifact_kind="perf",
            artifact_path=execution.candidate_perf_path,
            operator_path=request.operator_file,
            remote=request.remote is not None,
            full_execution=not request.fast_probe,
            comparison_target_path=execution.baseline_perf_path,
            comparison_operator_path=spec.baseline_operator_file,
        )
        return
    # A custom comparison is exploratory: record only the execution fact,
    # with no artifacts or provenance the round gate could read.
    append_managed_evidence(
        context.state_path,
        round_name=round_name,
        command=request.command,
        mode=spec.bench_mode,
        artifact_kind="perf",
        artifact_path=None,
        operator_path=request.operator_file,
        remote=request.remote is not None,
        full_execution=not request.fast_probe,
        custom_baseline=True,
    )


def _record_baseline_evidence(
    request: RunBenchRequest,
    execution: BenchExecution | None,
    return_code: int,
) -> int:
    """Append baseline evidence for run-bench-baseline.

    Returns the final return code: other commands pass the code through, and
    a failed evidence write turns the result into 1.
    """
    if request.command != "run-bench-baseline":
        return return_code
    perf_path = execution.candidate_perf_path if execution is not None else None
    passed = return_code == 0 and perf_path is not None
    try:
        append_baseline_evidence(
            command=request.command,
            artifact_kind="perf",
            status="passed" if passed else "failed",
            return_code=return_code,
            operator_path=request.operator_file,
            bench_file=request.bench_file,
            artifact_path=perf_path if passed else None,
            remote=request.remote is not None,
        )
    except (OSError, ValueError) as exc:
        print(f"baseline evidence recording failed: {exc}", file=sys.stderr)
        return 1
    return 0 if passed else return_code or 1
