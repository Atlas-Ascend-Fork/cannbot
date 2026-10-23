# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Concrete standalone and differential run-test execution."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib
import sys
import time
import traceback
from io import StringIO
from pathlib import Path
from typing import Any, NamedTuple, Optional, TextIO

from result_payload import ResultPayload, make_result
from ascendc_runtime import build_ascendc_operator, is_ascendc_operator
from cann_bench_native_replay import snapshot_differential_inputs
from api_contract import parse_metadata, resolve_operator_api
from test_contract import (
    SCRIPT_DIR,
    bootstrap_torch_npu,
    compute_flag_from_metadata,
    load_differential_test_cases,
    load_module,
    require_callable,
    temporary_sys_path_entries,
)
from triton_prewarm import maybe_prewarm_case_fns
from worker_runtime import NullWorkerRuntime, WorkerRuntime


def run_standalone_test(
    test_file: Path,
    operator_file: Path,
    *,
    verbose: bool = False,
    emit: "Optional[WorkerRuntime]" = None,
) -> ResultPayload:
    real_stderr = sys.stderr
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    try:
        test_path = test_file.resolve()
        operator_path = operator_file.resolve()
        if is_ascendc_operator(operator_path):
            build_ascendc_operator(operator_path)
        metadata = parse_metadata(test_path)
        if verbose:
            print("[run-test] mode: standalone", file=real_stderr)
            print(f"[run-test] test file: {test_path}", file=real_stderr)
            print(f"[run-test] operator file: {operator_path}", file=real_stderr)
            print(
                f"[run-test] operator api: {metadata.get('api-name', '?')} "
                f"({metadata.get('api-kind', '?')})",
                file=real_stderr,
            )
            print("[run-test] running...", file=real_stderr)
        bootstrap_torch_npu(test_path.parent, operator_path.parent)
        with temporary_sys_path_entries(test_path.parent, operator_path.parent, SCRIPT_DIR):
            test_module = load_module(test_path, f"run_test_standalone_{test_path.stem}")
            main_fn = require_callable(test_module, "main", test_path, kind="Standalone test module")
            operator_module = load_module(operator_path, f"run_test_operator_{operator_path.stem}")
            operator_api = resolve_operator_api(operator_module, metadata, operator_path)
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                main_fn(operator_api)
                _maybe_synchronize_torch()
        if verbose:
            print("[run-test] PASSED", file=real_stderr)
        return make_result(return_code=0, stdout=stdout_buffer.getvalue(), stderr=stderr_buffer.getvalue())
    except Exception:
        if verbose:
            print("[run-test] FAILED", file=real_stderr)
        return make_result(
            return_code=1,
            stdout=stdout_buffer.getvalue(),
            stderr=stderr_buffer.getvalue() + traceback.format_exc(),
        )


class _DiffCaseContext(NamedTuple):
    """Per-run constants shared by every differential case execution."""

    torch: object
    runtime: "WorkerRuntime"
    verbose: bool
    real_stderr: TextIO
    total: int


def _run_one_differential_case(
    case: object, index: int, ctx: _DiffCaseContext
) -> dict[str, object]:
    if ctx.verbose:
        print(
            f"[run-test] [{index + 1}/{ctx.total}] {case.case_id} ...",
            file=ctx.real_stderr,
            end="",
            flush=True,
        )
    case_started = time.monotonic()
    try:
        # Preserve the exact pre-execution arguments for later CPU native replay.
        inputs = snapshot_differential_inputs(case.inputs)
        record = {"id": case.case_id, "inputs": inputs, "result": case.fn()}
        _synchronize(ctx.torch)
    except Exception as exc:
        ctx.runtime.emit_case({
            "case_id": case.case_id,
            "ok": False,
            "error_summary": str(exc),
            "case_wall_clock_seconds": time.monotonic() - case_started,
        })
        raise
    ctx.runtime.emit_case({
        "case_id": case.case_id,
        "ok": True,
        "error_summary": None,
        "case_wall_clock_seconds": time.monotonic() - case_started,
    })
    if ctx.verbose:
        print(" ok", file=ctx.real_stderr)
    return record


def _run_differential_cases(
    test_file: Path,
    operator_file: Path,
    *,
    case_id: str | None = None,
    seed_payload: object | None = None,
    verbose: bool = False,
    emit: "Optional[WorkerRuntime]" = None,
) -> tuple[ResultPayload, object | None]:
    runtime = emit if emit is not None else NullWorkerRuntime()
    real_stderr = sys.stderr
    try:
        torch = _bootstrap_differential_runtime(test_file, operator_file)
    except ImportError as exc:
        return make_result(return_code=1, stdout="", stderr=f"Missing differential test dependency: {exc}"), None
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    try:
        metadata = parse_metadata(test_file)
        if verbose:
            print("[run-test] mode: differential", file=real_stderr)
            print(f"[run-test] test file: {test_file}", file=real_stderr)
            print(f"[run-test] operator file: {operator_file}", file=real_stderr)
            if case_id is not None:
                print(f"[run-test] case-id: {case_id}", file=real_stderr)
        compute = compute_flag_from_metadata(metadata)
        cases = load_differential_test_cases(
            test_file, operator_file, case_id=case_id, seed_payload=seed_payload
        )
        runtime.emit_progress("plan", case_ids=[case.case_id for case in cases])
        if verbose:
            print(f"[run-test] total cases: {len(cases)}", file=real_stderr)
        # The original Optional emit goes to prewarm: a real runtime turns
        # the prewarm messages into progress events, a null/direct caller
        # keeps the stderr print.
        maybe_prewarm_case_fns([(case.fn, case.inputs) for case in cases], emit=emit)
        ctx = _DiffCaseContext(
            torch=torch,
            runtime=runtime,
            verbose=verbose,
            real_stderr=real_stderr,
            total=len(cases),
        )
        records: list[dict[str, object]] = []
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            for index, case in enumerate(cases):
                records.append(_run_one_differential_case(case, index, ctx))
        return make_result(return_code=0, stdout=stdout_buffer.getvalue(), stderr=stderr_buffer.getvalue()), {
            "compute": compute,
            "cases": records,
        }
    except Exception:
        return _differential_failure_result(stdout_buffer, stderr_buffer, verbose, real_stderr), None


def _bootstrap_differential_runtime(test_file: Path, operator_file: Path) -> object:
    """Import torch with the autoload guard installed; returns the torch module."""
    if is_ascendc_operator(operator_file):
        build_ascendc_operator(operator_file)
    bootstrap_torch_npu(test_file.resolve().parent, operator_file.resolve().parent)
    return importlib.import_module("torch")


def _differential_failure_result(
    stdout_buffer: StringIO,
    stderr_buffer: StringIO,
    verbose: bool,
    real_stderr: TextIO,
) -> ResultPayload:
    if verbose:
        print("[run-test] FAILED", file=real_stderr)
    return make_result(
        return_code=1,
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue() + traceback.format_exc(),
    )


def run_differential_test(
    test_file: Path,
    operator_file: Path,
    *,
    archive_path: Path | None = None,
    case_id: str | None = None,
    seed_payload: object | None = None,
    verbose: bool = False,
    emit: "Optional[WorkerRuntime]" = None,
) -> tuple[ResultPayload, object | None]:
    result, payload = _run_differential_cases(
        test_file,
        operator_file,
        case_id=case_id,
        seed_payload=seed_payload,
        verbose=verbose,
        emit=emit,
    )
    archive_allowed = (
        archive_path is not None
        and int(result["return_code"]) == 0
        and not bool(result["stalled"])
        and payload is not None
    )
    if archive_allowed:
        torch = importlib.import_module("torch")
        torch.save(payload, archive_path)
        if verbose:
            print(f"[run-test] archive saved: {archive_path}", file=sys.stderr)
    return result, payload


def _maybe_synchronize_torch() -> None:
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return
    _synchronize(torch)


def _synchronize(torch_module: Any) -> None:
    npu = getattr(torch_module, "npu", None)
    synchronize = getattr(npu, "synchronize", None)
    if callable(synchronize):
        synchronize()
