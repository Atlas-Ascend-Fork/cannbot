# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Parent-process API for isolated local run-test execution."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from debug_device import maybe_print_visible_devices
from result_payload import ResultPayload, archive_long_failure_output, load_result, replace_result
from run_runtime import result_succeeded
from result_payload import filter_result_payload
from test_contract import deserialize_payload_object, run_test_accuracy_env
from worker_supervisor import (
    SupervisedRun,
    local_worker_command,
    print_prewarm_warning,
    run_supervised_worker,
)


SCRIPT_DIR = Path(__file__).resolve().parent


def run_local_test(
    test_file: Path,
    operator_file: Path,
    test_mode: str,
    *,
    case_id: str | None = None,
    accuracy_mode: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    verbose: bool = False,
) -> tuple[ResultPayload, Path | None]:
    maybe_print_visible_devices()
    run = _run_local_test_worker(
        test_file,
        operator_file,
        test_mode,
        case_id=case_id,
        emit_payload=False,
        accuracy_mode=accuracy_mode,
        extra_env=extra_env,
        verbose=verbose,
    )
    if run.final is None:
        return _test_from_entry_result(run.result, None, verbose=verbose)
    return _test_from_entry_result(
        load_result(cast(Mapping[str, object], run.final["result"])),
        _archived_result_raw(run.final),
        verbose=verbose,
    )


def _test_from_entry_result(
    result: ResultPayload,
    archived_raw: str | None,
    *,
    verbose: bool,
) -> tuple[ResultPayload, Path | None]:
    archived_result = None if archived_raw is None else Path(archived_raw).expanduser().resolve()
    return (
        filter_result_payload(
            archive_long_failure_output(result, workflow="run-test"),
            verbose=verbose,
        ),
        archived_result,
    )


def run_local_differential_case(
    test_file: Path,
    operator_file: Path,
    *,
    case_id: str,
    accuracy_mode: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    verbose: bool = False,
) -> tuple[ResultPayload, object | None]:
    maybe_print_visible_devices()
    run = _run_local_test_worker(
        test_file,
        operator_file,
        "differential",
        case_id=case_id,
        emit_payload=True,
        accuracy_mode=accuracy_mode,
        extra_env=extra_env,
        verbose=verbose,
    )
    if run.final is None:
        return _differential_case_from_entry_result(run.result, None, verbose=verbose)
    serialized_payload = run.final.get("serialized_payload")
    return _differential_case_from_entry_result(
        load_result(cast(Mapping[str, object], run.final["result"])),
        None if serialized_payload is None else str(serialized_payload),
        verbose=verbose,
    )


def _differential_case_from_entry_result(
    result: ResultPayload,
    serialized_payload: str | None,
    *,
    verbose: bool,
) -> tuple[ResultPayload, object | None]:
    if not result_succeeded(result):
        return (
            filter_result_payload(
                archive_long_failure_output(result, workflow="run-test"),
                verbose=verbose,
            ),
            None,
        )
    if serialized_payload is None:
        return (
            archive_long_failure_output(
                replace_result(
                    result,
                    return_code=1,
                    stderr=str(result["stderr"])
                    + "Local test payload worker did not return case payload.",
                ),
                workflow="run-test",
            ),
            None,
        )
    case_payload = deserialize_payload_object(serialized_payload)
    return (
        filter_result_payload(
            archive_long_failure_output(result, workflow="run-test"),
            verbose=verbose,
        ),
        case_payload,
    )


def _archived_result_raw(final: Mapping[str, object]) -> str | None:
    raw = final.get("archived_result")
    return None if raw is None else str(raw)


def _run_local_test_worker(
    test_file: Path,
    operator_file: Path,
    test_mode: str,
    *,
    case_id: str | None,
    emit_payload: bool,
    accuracy_mode: str | None,
    extra_env: Mapping[str, str] | None,
    verbose: bool,
) -> SupervisedRun:
    args = [
        "--test-file",
        str(test_file.resolve()),
        "--operator-file",
        str(operator_file.resolve()),
        "--test-mode",
        test_mode,
    ]
    if case_id is not None:
        args.extend(["--case-id", case_id])
    if emit_payload:
        args.append("--emit-serialized-payload")
    if verbose:
        args.append("--verbose")
    return run_supervised_worker(
        local_worker_command(SCRIPT_DIR / "run_bench_worker.py", "run-test", args),
        str(test_file.resolve().parent),
        extra_env={**run_test_accuracy_env(accuracy_mode), **(extra_env or {})},
        forward_stdout=sys.stdout if verbose else None,
        on_progress=None if verbose else print_prewarm_warning,
    )
