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
import contextlib
import os
import sys
from pathlib import Path
from typing import Generator, Protocol, cast

from execution_lifecycle import (
    TerminationSignalReceived,
    guard_termination_signal as _guard_termination_signal,
    guard_operator_execution_env as _guard_operator_execution_env,
)
from command_paths import (
    resolve_existing_path as _resolve_existing_path,
    temporary_sys_path_entry as _temporary_sys_path_entry,
)
from env_registry import TRITON_CACHE_DIR

SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_TRITON_CACHE_DIR = Path.home() / ".triton" / "cache"


class ResolveRemoteExecutionFn(Protocol):
    def __call__(
        self,
        explicit_remote: str | None,
        explicit_remote_workdir: str | None,
    ) -> tuple[str | None, str | None]:
        ...


class ComparePerfFn(Protocol):
    def __call__(
        self,
        baseline_perf: Path,
        compare_perf: Path,
        *,
        skip_latency_errors: bool = False,
        metric_source: str = "auto",
    ) -> int:
        ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=Path(__file__).name)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_test_baseline = subparsers.add_parser("run-test-baseline")
    _add_run_test_arguments(run_test_baseline)

    run_test_convert = subparsers.add_parser("run-test-convert")
    _add_run_test_arguments(run_test_convert)

    run_test_optimize = subparsers.add_parser("run-test-optimize")
    _add_run_test_arguments(run_test_optimize)

    check_triton_api = subparsers.add_parser("check-triton-api")
    check_triton_api.add_argument("--operator-file", required=True)
    check_triton_api.add_argument("--test-file", required=True)

    run_bench = subparsers.add_parser("run-bench")
    _add_run_bench_arguments(run_bench, include_baseline_operator=True)

    run_bench_baseline = subparsers.add_parser("run-bench-baseline")
    _add_run_bench_arguments(run_bench_baseline, include_baseline_operator=False)

    profile_bench = subparsers.add_parser("profile-bench")
    profile_bench.add_argument("--bench-file", required=True)
    profile_bench.add_argument("--operator-file", required=True)
    profile_bench.add_argument("--case-id", required=True)
    profile_bench.add_argument("--kernel-name", help=argparse.SUPPRESS)
    profile_bench.add_argument("--target-op")
    profile_bench.add_argument("--output-dir")
    profile_bench.add_argument("--remote")
    profile_bench.add_argument("--remote-workdir")
    profile_bench.add_argument("--keep-remote-workdir", action="store_true")
    profile_bench.add_argument("--verbose", action="store_true")

    profile_report = subparsers.add_parser("profile-report")
    profile_report.add_argument("--profile-dir", required=True)
    profile_report.add_argument("--target-op")
    profile_report.add_argument("--format", choices=["markdown", "json"], default="markdown")
    profile_report.add_argument("--top", type=int, default=5)

    compare_perf = subparsers.add_parser("compare-perf")
    compare_perf.add_argument("--baseline", required=True)
    compare_perf.add_argument("--compare", required=True)
    compare_perf.add_argument("--skip-latency-errors", "--skip-error", dest="skip_latency_errors", action="store_true")
    compare_perf.add_argument(
        "-m",
        "--metric-source",
        default="auto",
        choices=["auto", "kernel", "total-op", "all"],
    )

    return parser


def _add_run_test_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--test-file", required=True)
    parser.add_argument("--operator-file", required=True)
    parser.add_argument("--ref-result", "--baseline-result", dest="ref_result")
    parser.add_argument("--ref-operator-file", "--baseline-operator-file", dest="ref_operator_file")
    parser.add_argument("--case-id")
    parser.add_argument("--remote")
    parser.add_argument("--remote-workdir")
    parser.add_argument("--keep-remote-workdir", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--test-mode", choices=["standalone", "differential"])
    parser.add_argument(
        "--accuracy-mode",
        choices=["npu-contract", "dtype-close", "cann-bench"],
        # Leave the policy unset so managed MCP invocations can inherit the
        # HELIX_RUN_TEST_* controls supplied by their parent process.
        default=None,
    )


def _add_run_bench_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_baseline_operator: bool,
) -> None:
    parser.add_argument("--bench-file", required=True)
    parser.add_argument("--operator-file", required=True)
    if include_baseline_operator:
        parser.add_argument("--baseline-operator-file")
        parser.add_argument(
            "--fast-probe",
            action="store_true",
            help="Screening-only run inside an active optimize round: caps warmup/repeats at 1/3, "
            "writes <operator>_probe.txt, and marks the evidence as non-authoritative.",
        )
    parser.add_argument("--skip-latency-errors", "--skip-error", dest="skip_latency_errors", action="store_true")
    parser.add_argument(
        "-m",
        "--metric-source",
        default="auto",
        choices=["auto", "kernel", "total-op", "all"],
    )
    parser.add_argument("--output")
    parser.add_argument("--remote")
    parser.add_argument("--remote-workdir")
    parser.add_argument("--keep-remote-workdir", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--bench-mode",
        choices=["torch-npu-profiler", "msprof", "perf-counter"],
        help='benchmark mode; "msprof" is a deprecated alias for "torch-npu-profiler"',
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_triton_runtime_env()
    with _guard_operator_execution_env(args.command), _guard_termination_signal(args.command):
        try:
            exit_code = _dispatch_command(parser, args)
        except TerminationSignalReceived as exc:
            # The timing finalizers already ran during the unwind; preserve the
            # signal's conventional exit code instead of a traceback exit.
            exit_code = exc.exit_code
    from worker_supervisor import pending_termination_signal

    pending = pending_termination_signal()
    if pending is not None:
        # A parent-side SIGTERM already killed its worker and synthesis ran;
        # preserve the signal's exit code instead of the synthesized 1.
        raise SystemExit(128 + pending)
    return exit_code


def _configure_triton_runtime_env() -> None:
    configured_cache = os.environ.get(TRITON_CACHE_DIR)
    if configured_cache and _resolved_cache_dir(configured_cache) != _DEFAULT_TRITON_CACHE_DIR:
        return

    cache_dir = Path.cwd().resolve() / ".helix" / "triton-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ[TRITON_CACHE_DIR] = str(cache_dir)


def _resolved_cache_dir(raw_path: str) -> Path:
    return Path(raw_path).expanduser().resolve()


def _dispatch_command(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.command == "check-triton-api":
        from triton_api_check import check_triton_api

        operator_file = _resolve_existing_path(parser, args.operator_file, "Operator file")
        test_file = _resolve_existing_path(parser, args.test_file, "Test file")
        result = check_triton_api(operator_file, test_file)
        print(result.as_json())
        return 0 if result.ok else 1

    remote, remote_workdir = _resolve_remote_execution(args)

    if args.command == "compare-perf":
        compare_perf_files = _load_compare_perf_function()
        baseline_perf = _resolve_existing_path(parser, args.baseline, "Baseline perf")
        compare_perf = _resolve_existing_path(parser, args.compare, "Compare perf")
        return compare_perf_files(
            baseline_perf,
            compare_perf,
            skip_latency_errors=args.skip_latency_errors,
            metric_source=args.metric_source,
        )

    if args.command in {"run-test-baseline", "run-test-convert", "run-test-optimize"}:
        from run_test_command import handle_run_test_command

        return handle_run_test_command(parser, args, remote, remote_workdir)

    if args.command == "profile-bench":
        from run_profile_command import handle_run_profile_command

        return handle_run_profile_command(parser, args, remote, remote_workdir)

    if args.command == "profile-report":
        from run_profile_command import build_profile_report

        report = build_profile_report(
            _resolve_existing_path(parser, args.profile_dir, "Profile directory"),
            args.target_op,
            top_count=args.top,
            output_format=args.format,
        )
        print(report)
        return 0

    from run_bench_command import handle_run_bench_command

    return handle_run_bench_command(parser, args, remote, remote_workdir)


def _resolve_remote_execution(args: argparse.Namespace) -> tuple[str | None, str | None]:
    resolve_remote_execution = _load_remote_execution_function()
    return resolve_remote_execution(
        getattr(args, "remote", None),
        getattr(args, "remote_workdir", None),
    )


def _load_compare_perf_function() -> ComparePerfFn:
    with _script_dir_on_path():
        from perf_artifacts import compare_perf_files

    return cast(ComparePerfFn, compare_perf_files)


def _load_remote_execution_function() -> ResolveRemoteExecutionFn:
    with _script_dir_on_path():
        from remote_execution_env import resolve_remote_execution

    return cast(ResolveRemoteExecutionFn, resolve_remote_execution)


@contextlib.contextmanager
def _script_dir_on_path() -> Generator[None, None, None]:
    with _temporary_sys_path_entry(str(SCRIPT_DIR)):
        yield


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
