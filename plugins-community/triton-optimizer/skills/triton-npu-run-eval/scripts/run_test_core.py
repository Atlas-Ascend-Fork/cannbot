# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Recording wrapper for run-test: workflow gates, timing events, and evidence."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path

from execution_lifecycle import (
    RoundContext,
    active_optimize_round_context,
    append_managed_evidence,
    append_optimize_timing_event,
    baseline_phase_timing_context,
    cleanup_run_test_pt_files,
    managed_round_context,
    optimize_round_gate_required,
    require_optimize_round,
    timing_exception_return_code,
    validate_managed_input,
)
from execution_records import append_baseline_evidence
from run_test_executor import (
    EarlyExit,
    RunSpec,
    RunTestOutcome,
    execute_run,
    prepare_execution,
)
from run_test_executor import RunTestRequest


@dataclass(frozen=True)
class RunTestContext:
    """Managed-workflow context the recording wrapper resolved for a request.

    ``timing`` is the round stream the run is accounted to in timing and
    evidence records (the active round, or "baseline" during the baseline
    phase); it is None when the run records no timing (run-test-convert, or
    no active round or phase).
    """

    state_path: Path | None
    managed_integrity: dict[str, object] | None
    timing: RoundContext | None


def run_test(request: RunTestRequest) -> int:
    """Run one structured run-test request with workflow recording."""
    context = _resolve_context(request)
    if context is None:
        return 1
    spec = prepare_execution(
        request,
        managed_integrity=context.managed_integrity,
        state_path=context.state_path,
    )
    if isinstance(spec, EarlyExit):
        if spec.record_baseline_evidence:
            return _record_baseline_evidence(request, spec.return_code)
        return spec.return_code
    return _execute_with_recording(request, context, spec)


def _resolve_context(request: RunTestRequest) -> RunTestContext | None:
    """Resolve managed-workflow gates and the timing context for the request."""
    managed = managed_round_context(request.test_file, request.operator_file)
    if managed is not None and request.command in {"run-test-baseline", "run-test-convert"}:
        print(
            f"{request.command} is not accepted during an active optimize round; use run-test-optimize",
            file=sys.stderr,
        )
        return None
    active_round = active_optimize_round_context(request.test_file, request.operator_file)
    if request.command == "run-test-optimize" and optimize_round_gate_required(
        request.test_file, request.operator_file
    ):
        try:
            active_round = require_optimize_round(
                request.command,
                request.operator_file,
                request.test_file,
            )
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return None
    if managed is not None:
        try:
            _validate_managed_request(request, active_round)
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return None
    if request.command == "run-test-optimize":
        timing = active_round
    elif request.command == "run-test-baseline":
        timing = baseline_phase_timing_context(request.test_file, request.operator_file)
    else:
        timing = None
    return RunTestContext(
        state_path=managed[0] if managed is not None else None,
        managed_integrity=managed[1] if managed is not None else None,
        timing=timing,
    )


def _validate_managed_request(request: RunTestRequest, active_round: object) -> None:
    """Raise ValueError when the request violates managed-workflow input pinning."""
    validate_managed_input(request.test_file, role="test_file")
    if active_round is not None:
        try:
            request.operator_file.resolve().relative_to(active_round.round_dir.resolve())
        except ValueError as exc:
            raise ValueError(
                f"managed optimize operator must be inside active round: {request.operator_file}"
            ) from exc


def _record_round_correctness_evidence(
    request: RunTestRequest,
    context: RunTestContext,
    spec: RunSpec,
    outcome: RunTestOutcome,
    final_code: int,
) -> None:
    evidence_ready = (
        context.state_path is not None
        and final_code == 0
        and outcome.managed_evidence_eligible
    )
    if not evidence_ready:
        return
    append_managed_evidence(
        context.state_path,
        round_name=context.timing.round_name if context.timing is not None else "",
        command=request.command,
        mode=spec.resolved_test_mode,
        artifact_kind="correctness",
        artifact_path=None,
        operator_path=request.operator_file,
        remote=request.remote is not None,
    )


def _execute_with_recording(request: RunTestRequest, context: RunTestContext, spec: RunSpec) -> int:
    """Run the prepared execution inside the recording envelope.

    Emits the timing start/end events around the candidate run and owns
    cleanup plus managed evidence for it; the finally block always records
    baseline evidence and the end event, on success, handled failure, and
    exception paths alike.
    """
    append_optimize_timing_event(
        context.timing,
        event="run_test_start",
        command=request.command,
        case_id=request.case_id,
        test_file=request.test_file,
        operator_file=request.operator_file,
    )
    final_code = 1
    try:
        outcome = execute_run(spec)
        final_code = outcome.return_code
        if request.command == "run-test-optimize" and outcome.archived_result is not None:
            cleanup_run_test_pt_files((outcome.archived_result,))
        _record_round_correctness_evidence(request, context, spec, outcome, final_code)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        final_code = 1
    except BaseException as exc:
        final_code = timing_exception_return_code(exc)
        raise
    finally:
        # _record_baseline_evidence never raises (it renders its own
        # failures as return code 1), so it cannot mask an in-flight
        # exception; the return happens after the finally block instead.
        final_code = _record_baseline_evidence(request, final_code)
        append_optimize_timing_event(
            context.timing,
            event="run_test_end",
            command=request.command,
            return_code=final_code,
            case_id=request.case_id,
            test_file=request.test_file,
            operator_file=request.operator_file,
        )
    return final_code


def _record_baseline_evidence(request: RunTestRequest, return_code: int) -> int:
    """Append baseline evidence for run-test-baseline.

    Returns the final return code: other commands pass the code through, and
    a failed evidence write turns the result into 1.
    """
    if request.command != "run-test-baseline":
        return return_code
    try:
        append_baseline_evidence(
            command=request.command,
            artifact_kind="correctness",
            status="passed" if return_code == 0 else "failed",
            return_code=return_code,
            operator_path=request.operator_file,
            test_file=request.test_file,
            remote=request.remote is not None,
            full_execution=request.case_id is None,
        )
    except (OSError, ValueError) as exc:
        print(f"baseline evidence recording failed: {exc}", file=sys.stderr)
        return 1
    return return_code
