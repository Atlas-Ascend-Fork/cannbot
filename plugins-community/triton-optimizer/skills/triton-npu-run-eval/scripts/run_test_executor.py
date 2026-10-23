# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Concrete run-test execution: validation, reference resolution, and test runs.

Timing events and evidence appends live in run_test_core; this module runs the
test flow itself, though it still registers a derived reference result into
managed workflow state when one is resolved. Invalid input combinations raise
RunTestInputError so the command adapter can surface them through argparse;
test-metadata resolution raises ValueError and reference-run failures raise
ReferenceRunFailure. Every raise happens before the caller's timed region starts.
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path
from typing import Any, Literal, TextIO

from compare_result import (
    compare_result_files,
    compare_result_payload_objects,
    find_case_result_payload,
    load_case_result_payload,
)
from cann_bench_native_replay import create_native_ref_operator
from command_paths import require_existing_path
from test_contract import archive_load_size_allowed
from execution_lifecycle import ensure_managed_reference_result
from result_payload import ResultPayload, archive_long_failure_output, render_result
from run_test_local_api import run_local_test, run_local_differential_case
from run_test_remote_api import (
    run_remote_differential_comparison,
    run_remote_test,
    run_remote_differential_case,
)
from api_contract import parse_metadata
from triton_api_check import check_triton_api


@dataclass(frozen=True)
class RunTestRequest:
    """One run-test invocation expressed independently of argparse.

    The reference paths stay raw (as typed on the CLI) so the executor
    validates them only after the recording wrapper's workflow gates pass,
    preserving the original error ordering.
    """

    command: str
    test_file: Path
    operator_file: Path
    test_mode: str | None = None
    ref_result: str | None = None
    ref_operator_file: str | None = None
    case_id: str | None = None
    accuracy_mode: str | None = None
    remote: str | None = None
    remote_workdir: str | None = None
    keep_remote_workdir: bool = False
    verbose: bool = False


class RunTestInputError(Exception):
    """Invalid run-test input combination; the adapter renders it as a CLI error."""


class ReferenceRunFailure(Exception):
    """Reference-run failure carrying the intended CLI exit code (replaces SystemExit)."""

    def __init__(self, exit_code: int = 1) -> None:
        super().__init__(f"reference run failed (exit code {exit_code})")
        self.exit_code = exit_code


RunTestBranch = Literal["remote_differential", "case", "full"]


@dataclass(frozen=True)
class EarlyExit:
    """Execution resolved to an exit before the timed region (no timing events)."""

    return_code: int
    record_baseline_evidence: bool


@dataclass(frozen=True)
class RunSpec:
    """Complete specification of one execution, produced by prepare_execution.

    Everything execute_run needs is here: the branch to run, the resolved
    test mode, the resolved references, and the execution inputs carried
    over from the request.
    """

    branch: RunTestBranch
    test_file: Path
    operator_file: Path
    resolved_test_mode: str
    ref_result: Path | None
    ref_operator_file: Path | None
    ref_case_payload: object | None
    case_id: str | None
    accuracy_mode: str | None
    remote: str | None
    remote_workdir: str | None
    keep_remote_workdir: bool
    verbose: bool


@dataclass(frozen=True)
class RunTestOutcome:
    """Result of one timed execution for the recording wrapper."""

    return_code: int
    archived_result: Path | None = None
    managed_evidence_eligible: bool = True


def prepare_execution(
    request: RunTestRequest,
    *,
    managed_integrity: dict[str, object] | None,
    state_path: Path | None,
) -> RunSpec | EarlyExit:
    """Validate the request and resolve references before the timed region."""
    ref_result = _resolve_optional_input_path(request.ref_result, "Reference result")
    ref_operator_file = _resolve_optional_input_path(request.ref_operator_file, "Reference operator file")
    resolved_test_mode = request.test_mode or _resolve_test_mode_from_metadata(request.test_file)
    missing_ref_inputs = ref_result is None and ref_operator_file is None
    if managed_integrity is not None and resolved_test_mode == "differential" and missing_ref_inputs:
        ref_operator_file = Path(str(managed_integrity["baseline_operator_file"]))
    require_reference_input = request.command in {"run-test-convert", "run-test-optimize"}

    _validate_comparison_request(
        request, resolved_test_mode, ref_result, ref_operator_file,
        require_reference_input=require_reference_input,
    )

    api_early_exit = _check_triton_api_or_exit(request)
    if api_early_exit is not None:
        return api_early_exit

    branch, ref_result, ref_case_payload, early_exit = _resolve_branch(
        request, ref_result, ref_operator_file,
        resolved_test_mode=resolved_test_mode,
        state_path=state_path,
        require_reference_input=require_reference_input,
    )
    if early_exit is not None:
        return early_exit

    return RunSpec(
        branch=branch,
        test_file=request.test_file,
        operator_file=request.operator_file,
        resolved_test_mode=resolved_test_mode,
        ref_result=ref_result,
        ref_operator_file=ref_operator_file,
        ref_case_payload=ref_case_payload,
        case_id=request.case_id,
        accuracy_mode=request.accuracy_mode,
        remote=request.remote,
        remote_workdir=request.remote_workdir,
        keep_remote_workdir=request.keep_remote_workdir,
        verbose=request.verbose,
    )


@dataclass(frozen=True)
class _ComparisonResolution:
    """Inputs for resolving the comparison reference in a full test run."""

    command_name: str
    resolved_test_mode: str
    ref_result: Path | None
    ref_operator_file: Path | None
    test_file: Path
    remote: str | None
    remote_workdir: str | None
    case_id: str | None
    accuracy_mode: str | None
    keep_remote_workdir: bool
    verbose: bool
    require_reference_input: bool


def _resolve_branch(
    request: RunTestRequest,
    ref_result: Path | None,
    ref_operator_file: Path | None,
    *,
    resolved_test_mode: str,
    state_path: Path | None,
    require_reference_input: bool,
) -> tuple[RunTestBranch, Path | None, object | None, EarlyExit | None]:
    """Resolve the execution branch and its reference inputs before the timed region."""
    if request.remote is not None and resolved_test_mode == "differential":
        _validate_remote_differential_inputs(ref_result, ref_operator_file)
        if ref_operator_file is None:
            raise RuntimeError("internal error: remote differential branch requires a reference operator file")
        return "remote_differential", ref_result, None, None
    if request.case_id is not None:
        ref_case_payload = _resolve_case_reference_payload(
            request.test_file,
            ref_result,
            ref_operator_file,
            request.remote,
            request.remote_workdir,
            case_id=request.case_id,
            accuracy_mode=request.accuracy_mode,
            keep_remote_workdir=request.keep_remote_workdir,
            verbose=request.verbose,
            stderr=sys.stderr,
        )
        return "case", ref_result, ref_case_payload, None
    ref_result = _resolve_comparison_inputs(
        _ComparisonResolution(
            command_name=request.command,
            resolved_test_mode=resolved_test_mode,
            ref_result=ref_result,
            ref_operator_file=ref_operator_file,
            test_file=request.test_file,
            remote=request.remote,
            remote_workdir=request.remote_workdir,
            case_id=request.case_id,
            accuracy_mode=request.accuracy_mode,
            keep_remote_workdir=request.keep_remote_workdir,
            verbose=request.verbose,
            require_reference_input=require_reference_input,
        )
    )
    if state_path is not None and ref_result is not None:
        try:
            ensure_managed_reference_result(state_path, ref_result)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return "full", ref_result, None, EarlyExit(return_code=1, record_baseline_evidence=False)
    return "full", ref_result, None, None


def execute_run(spec: RunSpec) -> RunTestOutcome:
    """Execute the candidate test run and any automatic comparison."""
    if spec.branch == "remote_differential":
        return _execute_remote_differential(spec)
    if spec.branch == "case":
        return _execute_case(spec)
    return _execute_full(spec)


def _execute_remote_differential(spec: RunSpec) -> RunTestOutcome:
    if spec.remote is None or spec.ref_operator_file is None:
        raise RuntimeError("internal error: remote differential run requires remote and ref_operator_file")
    result, remote_workspace = run_remote_differential_comparison(
        spec.test_file,
        spec.ref_operator_file,
        spec.operator_file,
        spec.remote,
        spec.remote_workdir,
        case_id=spec.case_id,
        accuracy_mode=spec.accuracy_mode,
        keep_remote_workdir=spec.keep_remote_workdir,
        verbose=spec.verbose,
        stderr=sys.stderr,
    )
    _render_result(result, skip_stdout=True)
    print(f"Return code: {result['return_code']}")
    if spec.keep_remote_workdir:
        print(f"Remote workspace: {remote_workspace}")
    return RunTestOutcome(return_code=int(result["return_code"]))


def _execute_case(spec: RunSpec) -> RunTestOutcome:
    if spec.case_id is None:
        raise RuntimeError("internal error: case run requires case_id")
    result, candidate_payload, remote_workspace = _run_case_payload_once(
        spec.test_file,
        spec.operator_file,
        spec.remote,
        spec.remote_workdir,
        case_id=spec.case_id,
        accuracy_mode=spec.accuracy_mode,
        keep_remote_workdir=spec.keep_remote_workdir,
        verbose=spec.verbose,
        stderr=sys.stderr,
    )
    _render_ref_run_result(
        result,
        archived_result=None,
        remote_workspace=remote_workspace if spec.keep_remote_workdir else None,
        skip_stdout=spec.remote is not None,
    )
    final_code = int(result["return_code"])
    if final_code == 0 and spec.ref_case_payload is not None:
        if candidate_payload is None:
            print(
                "Differential run-test single-case execution did not produce "
                "a result payload required for automatic comparison.",
                file=sys.stderr,
            )
            final_code = 1
        else:
            final_code = compare_result_payload_objects(
                spec.ref_case_payload,
                candidate_payload,
                accuracy_mode=spec.accuracy_mode,
                native_ref_operator=_native_ref_operator(
                    spec.accuracy_mode, spec.test_file, spec.ref_operator_file
                ),
            )
    return RunTestOutcome(return_code=final_code, managed_evidence_eligible=False)


def _execute_full(spec: RunSpec) -> RunTestOutcome:
    if spec.remote is not None:
        result, archived_result, remote_workspace = run_remote_test(
            spec.test_file,
            spec.operator_file,
            spec.resolved_test_mode,
            spec.remote,
            spec.remote_workdir,
            case_id=spec.case_id,
            accuracy_mode=spec.accuracy_mode,
            extra_staging_files=_remote_input_archive_staging(
                spec.operator_file, spec.ref_result, spec.resolved_test_mode
            ),
            keep_remote_workdir=spec.keep_remote_workdir,
            verbose=spec.verbose,
            stderr=sys.stderr,
        )
    else:
        result, archived_result = run_local_test(
            spec.test_file,
            spec.operator_file,
            spec.resolved_test_mode,
            case_id=spec.case_id,
            accuracy_mode=spec.accuracy_mode,
            verbose=spec.verbose,
        )
        remote_workspace = None
    _render_result(result, skip_stdout=spec.remote is not None)
    print(f"Return code: {result['return_code']}")
    final_code = int(result["return_code"])
    if archived_result is not None:
        print(f"Archived result: {archived_result}")
        if spec.ref_result is not None:
            final_code = _compare_result(
                spec.ref_result,
                archived_result,
                accuracy_mode=spec.accuracy_mode,
                native_ref_operator=_native_ref_operator(
                    spec.accuracy_mode, spec.test_file, spec.ref_operator_file
                ),
            )
    elif spec.ref_result is not None:
        print(
            "Differential run-test did not produce an archived result required for automatic comparison.",
            file=sys.stderr,
        )
        final_code = 1
    if spec.remote is not None and spec.keep_remote_workdir:
        print(f"Remote workspace: {remote_workspace}")
    return RunTestOutcome(return_code=final_code, archived_result=archived_result)


def _validate_comparison_request(
    request: RunTestRequest,
    resolved_test_mode: str,
    ref_result: Path | None,
    ref_operator_file: Path | None,
    *,
    require_reference_input: bool,
) -> None:
    cann_bench_ref_conflict = (
        _is_cann_bench(request.accuracy_mode)
        and ref_result is not None
        and ref_operator_file is None
    )
    if resolved_test_mode == "differential" and cann_bench_ref_conflict:
        raise RunTestInputError(
            "cann-bench differential comparison requires --ref-operator-file, not --ref-result"
        )
    _validate_run_test_comparison_inputs(
        request.command,
        resolved_test_mode,
        ref_result,
        ref_operator_file,
        case_id=request.case_id,
        require_reference_input=require_reference_input,
    )


def _check_triton_api_or_exit(request: RunTestRequest) -> EarlyExit | None:
    api_check = check_triton_api(request.operator_file, request.test_file)
    if api_check.ok:
        return None
    for issue in api_check.issues:
        print("Triton API check failed: {0}".format(issue), file=sys.stderr)
    return EarlyExit(return_code=1, record_baseline_evidence=True)


def _resolve_optional_input_path(raw_path: str | None, label: str) -> Path | None:
    """Resolve an optional CLI reference path for prepare_execution.

    The ValueError catch is scoped to the path check alone so unrelated
    ValueErrors (e.g. test-mode metadata resolution) keep bubbling.
    """
    if raw_path is None:
        return None
    try:
        return require_existing_path(raw_path, label)
    except ValueError as exc:
        raise RunTestInputError(str(exc)) from exc


def _resolve_test_mode_from_metadata(test_file: Path) -> str:
    mode = parse_metadata(test_file).get("test-mode")
    if mode not in {"standalone", "differential"}:
        raise ValueError(f"Test metadata is missing required 'test-mode' entry: {test_file}")
    return mode


def _validate_run_test_comparison_inputs(
    command_name: str,
    resolved_test_mode: str,
    ref_result: Path | None,
    ref_operator_file: Path | None,
    *,
    case_id: str | None,
    require_reference_input: bool,
) -> None:
    if case_id is not None and resolved_test_mode != "differential":
        raise RunTestInputError(f"{command_name} standalone mode does not accept --case-id")
    if ref_result is not None and resolved_test_mode != "differential":
        raise RunTestInputError(f"{command_name} standalone mode does not accept --ref-result")
    if ref_operator_file is not None and resolved_test_mode != "differential":
        raise RunTestInputError(f"{command_name} standalone mode does not accept --ref-operator-file")
    if ref_result is not None and ref_operator_file is not None:
        qualifier = "requires exactly one of" if require_reference_input else "accepts at most one of"
        raise RunTestInputError(
            f"{command_name} differential mode {qualifier} --ref-result or --ref-operator-file"
        )
    missing_reference = ref_result is None and ref_operator_file is None
    if require_reference_input and resolved_test_mode == "differential" and missing_reference:
        raise RunTestInputError(
            f"{command_name} differential mode requires exactly one of --ref-result or --ref-operator-file"
        )


def _validate_remote_differential_inputs(
    ref_result: Path | None,
    ref_operator_file: Path | None,
) -> None:
    if ref_result is not None:
        raise RunTestInputError("Remote differential run-test does not accept --ref-result; use --ref-operator-file.")
    if ref_operator_file is None:
        raise RunTestInputError("Remote differential run-test requires --ref-operator-file.")


def _resolve_comparison_inputs(ctx: _ComparisonResolution) -> Path | None:
    _validate_run_test_comparison_inputs(
        ctx.command_name,
        ctx.resolved_test_mode,
        ctx.ref_result,
        ctx.ref_operator_file,
        case_id=ctx.case_id,
        require_reference_input=ctx.require_reference_input,
    )
    if ctx.ref_operator_file is None:
        return ctx.ref_result
    return _resolve_ref_operator_result(
        ctx.test_file,
        ctx.ref_operator_file,
        ctx.resolved_test_mode,
        ctx.remote,
        ctx.remote_workdir,
        case_id=ctx.case_id,
        accuracy_mode=ctx.accuracy_mode,
        keep_remote_workdir=ctx.keep_remote_workdir,
        verbose=ctx.verbose,
    )


def _resolve_ref_operator_result(
    test_file: Path,
    ref_operator_file: Path,
    test_mode: str,
    remote: str | None,
    remote_workdir: str | None,
    *,
    case_id: str | None,
    accuracy_mode: str | None,
    keep_remote_workdir: bool,
    verbose: bool,
) -> Path:
    derived_ref_result = _derived_result_path(ref_operator_file)
    if derived_ref_result.exists():
        return derived_ref_result
    if remote is not None:
        try:
            result, archived_result, remote_workspace = run_remote_test(
                test_file,
                ref_operator_file,
                test_mode,
                remote,
                remote_workdir,
                case_id=case_id,
                accuracy_mode=accuracy_mode,
                keep_remote_workdir=keep_remote_workdir,
                verbose=verbose,
                stderr=sys.stderr,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            raise ReferenceRunFailure(1) from exc
        _render_ref_run_result(
            result,
            archived_result,
            remote_workspace=remote_workspace if keep_remote_workdir else None,
            skip_stdout=True,
        )
    else:
        try:
            result, archived_result = run_local_test(
                test_file,
                ref_operator_file,
                test_mode,
                case_id=case_id,
                accuracy_mode=accuracy_mode,
                verbose=verbose,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            raise ReferenceRunFailure(1) from exc
        _render_ref_run_result(result, archived_result, remote_workspace=None)
    if int(result["return_code"]) != 0 or archived_result is None:
        raise ReferenceRunFailure(1)
    return derived_ref_result


def _resolve_case_reference_payload(
    test_file: Path,
    ref_result: Path | None,
    ref_operator_file: Path | None,
    remote: str | None,
    remote_workdir: str | None,
    *,
    case_id: str,
    accuracy_mode: str | None,
    keep_remote_workdir: bool,
    verbose: bool,
    stderr: TextIO | None,
) -> object | None:
    if ref_result is not None:
        return load_case_result_payload(ref_result, case_id)
    if ref_operator_file is None:
        return None
    derived_ref_result = _derived_result_path(ref_operator_file)
    if derived_ref_result.exists():
        payload = find_case_result_payload(derived_ref_result, case_id)
        if payload is not None:
            return payload
    try:
        result, payload, remote_workspace = _run_case_payload_once(
            test_file,
            ref_operator_file,
            remote,
            remote_workdir,
            case_id=case_id,
            accuracy_mode=accuracy_mode,
            keep_remote_workdir=keep_remote_workdir,
            verbose=verbose,
            stderr=stderr,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(str(exc), file=stderr or sys.stderr)
        raise ReferenceRunFailure(1) from exc
    _render_ref_run_result(
        result,
        archived_result=None,
        remote_workspace=remote_workspace if keep_remote_workdir else None,
        skip_stdout=remote is not None,
    )
    if int(result["return_code"]) != 0 or payload is None:
        raise ReferenceRunFailure(int(result["return_code"]) or 1)
    return payload


def _run_case_payload_once(
    test_file: Path,
    operator_file: Path,
    remote: str | None,
    remote_workdir: str | None,
    *,
    case_id: str,
    accuracy_mode: str | None,
    keep_remote_workdir: bool,
    verbose: bool,
    stderr: TextIO | None,
) -> tuple[ResultPayload, object | None, str | None]:
    if remote is not None:
        result, payload, workspace = run_remote_differential_case(
            test_file,
            operator_file,
            remote,
            remote_workdir,
            case_id=case_id,
            accuracy_mode=accuracy_mode,
            keep_remote_workdir=keep_remote_workdir,
            verbose=verbose,
            stderr=stderr,
        )
        return result, payload, workspace
    result, payload = run_local_differential_case(
        test_file,
        operator_file,
        case_id=case_id,
        accuracy_mode=accuracy_mode,
        verbose=verbose,
    )
    return result, payload, None


def _compare_result(
    ref_result: Path,
    archived_result: Path,
    *,
    accuracy_mode: str | None,
    native_ref_operator: Any = None,
) -> int:
    return compare_result_files(
        ref_result,
        archived_result,
        accuracy_mode=accuracy_mode,
        native_ref_operator=native_ref_operator,
    )


def _is_cann_bench(accuracy_mode: str | None) -> bool:
    return accuracy_mode == "cann-bench"


def _native_ref_operator(
    accuracy_mode: str | None,
    test_file: Path,
    ref_operator_file: Path | None,
) -> Any:
    if not _is_cann_bench(accuracy_mode) or ref_operator_file is None:
        return None
    return create_native_ref_operator(test_file, ref_operator_file)


def _remote_input_archive_staging(
    operator_file: Path,
    ref_result: Path | None,
    test_mode: str,
) -> list[tuple[Path, str]] | None:
    """Stage the local reference archive beside the remote candidate so the
    remote worker's contract-based derivation can load inputs from it.
    Skipped when off-contract or when the archive exceeds the load size guard
    (the remote worker would refuse to load it anyway)."""
    if test_mode != "differential" or ref_result is None:
        return None
    stem = operator_file.stem
    if stem.startswith("opt_"):
        remote_name = f"{stem[len('opt_'):]}_result.pt"
    elif stem.startswith("triton_"):
        remote_name = f"{stem[len('triton_'):]}_result.pt"
    else:
        return None
    archive = Path(ref_result)
    if not archive.is_file() or not archive_load_size_allowed(archive):
        return None
    return [(archive, remote_name)]


def _derived_result_path(operator_file: Path) -> Path:
    return operator_file.parent / f"{operator_file.stem}_result.pt"


def _render_ref_run_result(
    result: ResultPayload,
    archived_result: Path | None,
    *,
    remote_workspace: str | None,
    skip_stdout: bool = False,
) -> None:
    _render_result(result, skip_stdout=skip_stdout)
    print(f"Return code: {result['return_code']}")
    if archived_result is not None:
        print(f"Archived result: {archived_result}")
    if remote_workspace is not None:
        print(f"Remote workspace: {remote_workspace}")


def _render_result(result: ResultPayload, skip_stdout: bool) -> None:
    render_result(archive_long_failure_output(result, workflow="run-test"), skip_stdout)
