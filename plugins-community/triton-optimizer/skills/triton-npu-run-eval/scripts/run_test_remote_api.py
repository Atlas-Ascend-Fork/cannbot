# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Remote SSH API for run-test execution."""

from __future__ import annotations
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO, cast

from debug_device import maybe_print_visible_devices
from ascendc_runtime import ascendc_source_path, is_ascendc_operator
from remote_python_bundle import resolve_remote_python_bundle
from result_payload import ResultPayload, archive_long_failure_output, load_result, replace_result
from run_runtime import (
    RemoteSpec,
    StagingInput,
    cleanup_remote_workspace,
    copy_file_from_remote,
    copy_staging_files_to_remote,
    collect_staging_input_files,
    create_remote_workspace,
    delete_remote_files,
    result_succeeded,
)
from result_payload import differential_archive_path, filter_result_payload
from test_contract import deserialize_payload_object, run_test_accuracy_env
from worker_supervisor import SupervisedRun, run_remote_worker

SCRIPT_DIR = Path(__file__).resolve().parent


def run_remote_test(
    test_file: Path,
    operator_file: Path,
    test_mode: str,
    remote: str,
    remote_workdir: str | None,
    *,
    case_id: str | None = None,
    accuracy_mode: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    extra_staging_files: Sequence[tuple[Path, str]] | None = None,
    keep_remote_workdir: bool = False,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> tuple[ResultPayload, Path | None, str]:
    maybe_print_visible_devices()
    spec, remote_workspace = create_remote_workspace(
        remote, remote_workdir, verbose=verbose, stderr=stderr
    )
    try:
        _copy_run_test_runtime(
            spec, test_file, operator_file, remote_workspace,
            verbose=verbose, stderr=stderr, extra_staging_files=extra_staging_files,
        )
        run = run_remote_worker(
            spec,
            remote_workspace,
            _build_remote_worker_command(
                test_file.name, operator_file.name, test_mode, case_id=case_id
            ),
            extra_env=_test_extra_env(accuracy_mode, extra_env),
            verbose=verbose,
            stderr=stderr,
        )
        worker_result, archived_raw, _ = _worker_outcome(run)
        archived_result = None
        if result_succeeded(worker_result) and test_mode == "differential":
            archived_result = _fetch_differential_archive(
                spec,
                remote_workspace,
                operator_file,
                archived_raw,
                extra_staging_files,
                keep_remote_workdir=keep_remote_workdir,
                verbose=verbose,
                stderr=stderr,
            )
        return _remote_test_outcome(worker_result, verbose, archived_result, remote_workspace)
    finally:
        if not keep_remote_workdir:
            cleanup_remote_workspace(spec, remote_workspace, verbose=verbose, stderr=stderr)


def run_remote_differential_case(
    test_file: Path,
    operator_file: Path,
    remote: str,
    remote_workdir: str | None,
    *,
    case_id: str,
    accuracy_mode: str | None = None,
    keep_remote_workdir: bool = False,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> tuple[ResultPayload, object | None, str]:
    maybe_print_visible_devices()
    spec, remote_workspace = create_remote_workspace(
        remote, remote_workdir, verbose=verbose, stderr=stderr
    )
    try:
        _copy_run_test_runtime(spec, test_file, operator_file, remote_workspace, verbose=verbose, stderr=stderr)
        run = run_remote_worker(
            spec,
            remote_workspace,
            _build_remote_worker_command(
                test_file.name,
                operator_file.name,
                "differential",
                case_id=case_id,
                emit_serialized_payload=True,
            ),
            extra_env=run_test_accuracy_env(accuracy_mode),
            verbose=verbose,
            stderr=stderr,
        )
        worker_result, _archived, serialized_payload = _worker_outcome(run)
        case_payload = None
        if serialized_payload is not None:
            case_payload = deserialize_payload_object(serialized_payload)
        return _differential_case_outcome(worker_result, case_payload, remote_workspace, verbose)
    finally:
        if not keep_remote_workdir:
            cleanup_remote_workspace(spec, remote_workspace, verbose=verbose, stderr=stderr)


def run_remote_differential_comparison(
    test_file: Path,
    ref_operator_file: Path,
    operator_file: Path,
    remote: str,
    remote_workdir: str | None,
    *,
    case_id: str | None = None,
    accuracy_mode: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    keep_remote_workdir: bool = False,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> tuple[ResultPayload, str]:
    """Run and compare differential archives without moving PT payloads locally."""
    maybe_print_visible_devices()
    spec, remote_workspace = create_remote_workspace(
        remote, remote_workdir, verbose=verbose, stderr=stderr
    )
    remote_ref_operator = f"{remote_workspace}/reference_{ref_operator_file.name}"
    remote_operator = f"{remote_workspace}/candidate_{operator_file.name}"
    execution_env = _test_extra_env(accuracy_mode, extra_env)
    try:
        _stage_remote_differential_inputs(
            spec, test_file, ref_operator_file, operator_file, remote_workspace,
            verbose=verbose, stderr=stderr,
        )
        run = run_remote_worker(
            spec, remote_workspace,
            _build_remote_differential_worker_command(
                test_file.name, Path(remote_ref_operator).name, Path(remote_operator).name,
                case_id=case_id, accuracy_mode=accuracy_mode,
            ),
            extra_env=execution_env, verbose=verbose, stderr=stderr,
        )
        worker_result, _archived_raw, _serialized = _worker_outcome(run)
        # The worker compares both payloads in process and writes no archive,
        # so nothing GB-scale remains in the remote workspace on any path.
        worker_result = _annotate_failed_phase(run, worker_result)
        return (
            filter_result_payload(
                archive_long_failure_output(worker_result, workflow="run-test"),
                verbose=verbose,
            ),
            remote_workspace,
        )
    finally:
        if not keep_remote_workdir:
            cleanup_remote_workspace(spec, remote_workspace, verbose=verbose, stderr=stderr)


def _annotate_failed_phase(run: object, worker_result: ResultPayload) -> ResultPayload:
    failed_phase = run.final.get("failed_phase") if run.final is not None else None
    if not isinstance(failed_phase, str):
        return worker_result
    return replace_result(
        worker_result,
        stderr=(
            f"[run-test] differential {failed_phase} phase failed\n"
            f"{worker_result['stderr']}"
        ),
    )


def _remote_test_outcome(
    worker_result: ResultPayload,
    verbose: bool,
    archived_result: Path | None,
    remote_workspace: str,
) -> tuple[ResultPayload, Path | None, str]:
    return (
        filter_result_payload(
            archive_long_failure_output(worker_result, workflow="run-test"),
            verbose=verbose,
        ),
        archived_result,
        remote_workspace,
    )


def _fetch_differential_archive(
    spec: RemoteSpec,
    remote_workspace: str,
    operator_file: Path,
    archived_raw: object,
    extra_staging_files: Sequence[tuple[Path, str]] | None,
    *,
    keep_remote_workdir: bool,
    verbose: bool,
    stderr: TextIO | None,
) -> Path | None:
    archive_path = differential_archive_path(operator_file)
    remote_archive_name = (
        Path(str(archived_raw)).name if archived_raw is not None else archive_path.name
    )
    archived_result = _copy_remote_differential_archive(
        spec,
        remote_workspace,
        remote_archive_name,
        local_archive_path=archive_path,
        verbose=verbose,
        stderr=stderr,
    )
    # Consume-then-delete: the archive is safely copied back locally
    # and the staged uploads have been read by the worker. If the
    # session dir leaks (SIGKILL before teardown), the residue stays
    # MB-scale code/logs instead of GB-scale archives.
    if not keep_remote_workdir:
        delete_remote_files(
            spec,
            remote_workspace,
            [remote_archive_name]
            + [target for _source, target in (extra_staging_files or ())],
            verbose=verbose,
            stderr=stderr,
        )
    return archived_result


def _differential_case_outcome(
    worker_result: ResultPayload,
    case_payload: object | None,
    remote_workspace: str,
    verbose: bool,
) -> tuple[ResultPayload, object | None, str]:
    if not result_succeeded(worker_result):
        return _remote_test_outcome(worker_result, verbose, None, remote_workspace)
    if case_payload is None:
        return (
            archive_long_failure_output(
                replace_result(
                    worker_result,
                    return_code=1,
                    stderr=str(worker_result["stderr"])
                    + "Remote test payload worker did not return case payload.",
                ),
                workflow="run-test",
            ),
            None,
            remote_workspace,
        )
    return (
        filter_result_payload(
            archive_long_failure_output(worker_result, workflow="run-test"),
            verbose=verbose,
        ),
        case_payload,
        remote_workspace,
    )


def _stage_remote_differential_inputs(
    spec: RemoteSpec,
    test_file: Path,
    ref_operator_file: Path,
    operator_file: Path,
    remote_workspace: str,
    *,
    verbose: bool,
    stderr: TextIO | None,
) -> None:
    remote_ref_operator = f"{remote_workspace}/reference_{ref_operator_file.name}"
    remote_operator = f"{remote_workspace}/candidate_{operator_file.name}"
    runtime_bundle = resolve_remote_python_bundle(
        [SCRIPT_DIR / "run_bench_worker.py"]
    )
    records = collect_staging_input_files(
        (test_file.parent, ref_operator_file.parent, operator_file.parent),
        (
            (test_file, test_file.name),
            (ref_operator_file, Path(remote_ref_operator).name),
            (operator_file, Path(remote_operator).name),
        ),
        extra_files=_ascendc_remote_files(
            ref_operator_file,
            remote_name=Path(remote_ref_operator).name,
        )
        + _ascendc_remote_files(
            operator_file,
            remote_name=Path(remote_operator).name,
        ),
        excluded_names=tuple(path.name for path in runtime_bundle),
    )
    bundle_records: list[StagingInput] = [
        {"source": path, "target": path.name}
        for path in runtime_bundle
    ]
    copy_staging_files_to_remote(
        spec,
        [*bundle_records, *records],
        remote_workspace,
        verbose=verbose,
        stderr=stderr,
    )


def _copy_remote_differential_archive(
    spec: RemoteSpec,
    remote_workspace: str,
    remote_archive_name: str,
    *,
    local_archive_path: Path,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> Path:
    copy_file_from_remote(
        spec,
        f"{remote_workspace}/{remote_archive_name}",
        local_archive_path,
        verbose=verbose,
        stderr=stderr,
    )
    return local_archive_path


def _test_extra_env(
    accuracy_mode: str | None,
    extra_env: Mapping[str, str] | None,
) -> dict[str, str]:
    return {
        **run_test_accuracy_env(accuracy_mode),
        **(extra_env or {}),
    }


def _copy_run_test_runtime(
    spec: RemoteSpec,
    test_file: Path,
    operator_file: Path,
    remote_workspace: str,
    *,
    verbose: bool = False,
    stderr: TextIO | None = None,
    extra_staging_files: Sequence[tuple[Path, str]] | None = None,
) -> None:
    runtime_bundle = resolve_remote_python_bundle(
        [SCRIPT_DIR / "run_bench_worker.py", SCRIPT_DIR / "npu_compare.py"]
    )
    extra_files = _ascendc_remote_files(operator_file, remote_name=operator_file.name)
    records = collect_staging_input_files(
        (test_file.parent, operator_file.parent),
        ((test_file, test_file.name), (operator_file, operator_file.name)),
        extra_files=extra_files,
        excluded_names=tuple(path.name for path in runtime_bundle),
    )
    bundle_records: list[StagingInput] = [
        {"source": path, "target": path.name}
        for path in runtime_bundle
    ]
    extra_records: list[StagingInput] = [
        {"source": source, "target": target}
        for source, target in (extra_staging_files or ())
    ]
    copy_staging_files_to_remote(
        spec,
        [
            *bundle_records,
            *records,
            *extra_records,
        ],
        remote_workspace,
        verbose=verbose,
        stderr=stderr,
    )


def _ascendc_remote_files(operator_file: Path, *, remote_name: str) -> tuple[tuple[Path, str], ...]:
    if not is_ascendc_operator(operator_file):
        return ()
    ascendc_source = ascendc_source_path(operator_file)
    return ((ascendc_source, Path(remote_name).with_suffix(".asc").name),)


def _worker_outcome(
    run: SupervisedRun,
) -> tuple[ResultPayload, str | None, str | None]:
    """Decode a supervised run into the worker result and optional artifacts.

    A run whose worker died or was killed carries no ``final`` line; its
    supervisor result (nonzero, with the failure note on stderr) flows through
    the same filtering as a decoded failure.
    """
    if run.final is None:
        return run.result, None, None
    worker_result = load_result(cast(Mapping[str, object], run.final["result"]))
    archived = run.final.get("archived_result")
    serialized = run.final.get("serialized_payload")
    return (
        worker_result,
        None if archived is None else str(archived),
        None if serialized is None else str(serialized),
    )


def _build_remote_differential_worker_command(
    test_name: str,
    ref_operator_name: str,
    operator_name: str,
    *,
    case_id: str | None = None,
    accuracy_mode: str | None = None,
) -> list[str]:
    command = [
        "python3",
        "run_bench_worker.py",
        "run-test-differential",
        "--test-file",
        test_name,
        "--ref-operator-file",
        ref_operator_name,
        "--operator-file",
        operator_name,
    ]
    if case_id is not None:
        command.extend(["--case-id", case_id])
    if accuracy_mode is not None:
        command.extend(["--accuracy-mode", accuracy_mode])
    return command


def _build_remote_worker_command(
    test_name: str,
    operator_name: str,
    test_mode: str,
    *,
    case_id: str | None = None,
    emit_serialized_payload: bool = False,
) -> list[str]:
    command = [
        "python3",
        "run_bench_worker.py",
        "run-test",
        "--test-file",
        test_name,
        "--operator-file",
        operator_name,
        "--test-mode",
        test_mode,
    ]
    if case_id is not None:
        command.extend(["--case-id", case_id])
    if emit_serialized_payload:
        command.append("--emit-serialized-payload")
    return command
