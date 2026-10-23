# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""CLI orchestration for the profile-bench command."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Protocol, cast

from result_payload import render_result
from command_paths import resolve_existing_path, temporary_sys_path_entry
from execution_lifecycle import (
    append_optimize_timing_event,
    active_optimize_round_context,
    deep_analysis_context,
    deep_analysis_state_path,
    managed_round_context,
    validate_managed_input,
)
from run_bench_local_api import run_local_profile_bench
from run_bench_remote_api import run_remote_profile_bench

SCRIPT_DIR = Path(__file__).resolve().parent


class _ProfileSummaryModule(Protocol):
    def build_report(
        self,
        profile_path: str | Path,
        target_op: str | None = None,
        top_count: int = 5,
        output_format: str = "markdown",
    ) -> str:
        ...


def build_profile_report(
    profile_dir: Path,
    target_op: str | None = None,
    top_count: int = 5,
    output_format: str = "markdown",
) -> str:
    script = SCRIPT_DIR.parents[1] / "triton-npu-profile-operator" / "scripts" / "reporter.py"
    with temporary_sys_path_entry(str(script.parent)):
        spec = importlib.util.spec_from_file_location("profile_reporter_runtime", script)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load profile reporter script: {script}")
        loaded_module = importlib.util.module_from_spec(spec)
        # Register before exec: dataclass/typing decorators resolve the module via sys.modules.
        sys.modules[spec.name] = loaded_module
        try:
            spec.loader.exec_module(loaded_module)
        finally:
            sys.modules.pop(spec.name, None)
    module = cast(_ProfileSummaryModule, loaded_module)
    return module.build_report(
        profile_dir,
        target_op=target_op,
        top_count=top_count,
        output_format=output_format,
    )


def _end_profile_timing(
    timing: object, return_code: int, operator_file: Path, bench_file: Path
) -> None:
    append_optimize_timing_event(
        timing,
        event="profile_bench_end",
        command="profile-bench",
        return_code=return_code,
        operator_file=operator_file,
        bench_file=bench_file,
    )


def _resolve_deep_profile_context(
    bench_file: Path, operator_file: Path, output_dir: Path | None
) -> "tuple[dict[str, object] | None, Path | None] | None":
    """Validate the deep-analysis context; None means a printed failure."""
    deep_context = deep_analysis_context(bench_file, operator_file)
    deep_state_path = deep_analysis_state_path(bench_file, operator_file)
    if deep_state_path is not None and deep_context is None:
        print(
            "deep analysis workflow state is invalid for profile-bench; restart the pending round "
            "from its validated parent before retrying.",
            file=sys.stderr,
        )
        return None
    if deep_context is None:
        return None, output_dir
    if operator_file != Path(str(deep_context["operator_file"])).resolve():
        print(
            "deep analysis profile-bench operator_file does not match the round candidate",
            file=sys.stderr,
        )
        return None
    if bench_file != Path(str(deep_context["bench_file"])).resolve():
        print(
            "deep analysis profile-bench bench_file does not match the canonical benchmark",
            file=sys.stderr,
        )
        return None
    expected_output_dir = Path(str(deep_context["round_dir"])) / "profile"
    if output_dir is None:
        output_dir = expected_output_dir
    if output_dir != expected_output_dir.resolve():
        print(f"deep analysis profile output must be under {expected_output_dir}", file=sys.stderr)
        return None
    return deep_context, output_dir


def _execute_profile_bench(
    args: argparse.Namespace,
    bench_file: Path,
    operator_file: Path,
    remote: str | None,
    remote_workdir: str | None,
    *,
    output_dir: Path | None,
    timing: object,
) -> "tuple[ResultPayload, Path | None, str | None] | None":
    try:
        if remote is not None:
            return run_remote_profile_bench(
                bench_file,
                operator_file,
                remote,
                remote_workdir,
                case_id=args.case_id,
                output_dir=output_dir,
                kernel_name=args.kernel_name,
                keep_remote_workdir=args.keep_remote_workdir,
                verbose=args.verbose,
                stderr=sys.stderr,
            )
        result, profile_dir = run_local_profile_bench(
            bench_file,
            operator_file,
            case_id=args.case_id,
            output_dir=output_dir,
            kernel_name=args.kernel_name,
        )
        return result, profile_dir, None
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        _end_profile_timing(timing, 1, operator_file, bench_file)
        return None
    except BaseException:
        _end_profile_timing(timing, 1, operator_file, bench_file)
        raise


def _render_profile_outcome(
    args: argparse.Namespace,
    result: ResultPayload,
    profile_dir: Path | None,
    *,
    workspace: str | None,
    deep_context: "dict[str, object] | None",
    remote: str | None,
    timing: object,
    operator_file: Path,
    bench_file: Path,
) -> int:
    render_result(result, remote is not None and args.verbose)
    final_code = int(result["return_code"])
    print(f"Return code: {final_code}")
    if profile_dir is not None:
        print(f"Profile directory: {profile_dir}")
        if deep_context is not None:
            try:
                _write_deep_profile_manifest(
                    profile_dir,
                    case_id=args.case_id,
                    context=deep_context,
                    remote=remote is not None,
                )
            except OSError as exc:
                print(f"unable to write deep analysis profile manifest: {exc}", file=sys.stderr)
                _end_profile_timing(timing, 1, operator_file, bench_file)
                return 1
        print(build_profile_report(profile_dir, args.target_op))
        print(_profile_bench_hint(profile_dir))
    if remote is not None and args.keep_remote_workdir:
        print(f"Remote workspace: {workspace}")
    _end_profile_timing(timing, final_code, operator_file, bench_file)
    return final_code


def handle_run_profile_command(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    remote: str | None,
    remote_workdir: str | None,
) -> int:
    bench_file = resolve_existing_path(parser, args.bench_file, "Bench file")
    operator_file = resolve_existing_path(parser, args.operator_file, "Operator file")
    managed = managed_round_context(bench_file, operator_file)
    timing = active_optimize_round_context(bench_file, operator_file)
    output_dir = None if args.output_dir is None else Path(args.output_dir).expanduser().resolve()
    deep_resolved = _resolve_deep_profile_context(bench_file, operator_file, output_dir)
    if deep_resolved is None:
        return 1
    deep_context, output_dir = deep_resolved
    if managed is not None:
        try:
            validate_managed_input(bench_file, role="bench_file")
            round_context = active_optimize_round_context(bench_file, operator_file)
            if round_context is not None:
                operator_file.resolve().relative_to(round_context.round_dir.resolve())
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    append_optimize_timing_event(
        timing,
        event="profile_bench_start",
        command="profile-bench",
        operator_file=operator_file,
        bench_file=bench_file,
    )
    executed = _execute_profile_bench(
        args, bench_file, operator_file, remote, remote_workdir, output_dir=output_dir, timing=timing
    )
    if executed is None:
        return 1
    result, profile_dir, workspace = executed
    return _render_profile_outcome(
        args, result, profile_dir,
        workspace=workspace, deep_context=deep_context, remote=remote,
        timing=timing, operator_file=operator_file, bench_file=bench_file,
    )


def _write_deep_profile_manifest(
    profile_dir: Path,
    *,
    case_id: str | None,
    context: dict[str, object],
    remote: bool,
) -> Path:
    manifest_path = profile_dir / "helix-profile-manifest.json"
    operator_file = Path(str(context["operator_file"])).resolve()
    bench_file = Path(str(context["bench_file"])).resolve()
    manifest = {
        "case_id": str(case_id),
        "operator_file": str(operator_file),
        "operator_sha256": str(context["operator_sha256"]),
        "bench_file": str(bench_file),
        "bench_sha256": str(context["bench_sha256"]),
        "artifact_dir": str(profile_dir.resolve()),
        "remote": remote,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def _profile_bench_hint(profile_dir: Path) -> str:
    return (
        "Hint: rerun the bundled `profile-report` helper for this "
        f"`--profile-dir {profile_dir}` if you need the summary again; "
        "if that is not enough, inspect the raw files in this profile directory directly."
    )
