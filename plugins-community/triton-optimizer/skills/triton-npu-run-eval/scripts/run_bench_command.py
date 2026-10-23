# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Command adapter for the two public run-bench subcommands.

Builds a structured RunBenchRequest from parsed CLI arguments and delegates
to the core run-bench API (recording wrapper plus execution). Invalid input
combinations surface as argparse errors exactly like before.
"""

from __future__ import annotations

import argparse
from typing import Optional, cast

from command_paths import resolve_existing_path
from perf_artifacts import MetricSource
from run_bench_core import run_bench
from run_bench_executor import RunBenchInputError
from run_bench_executor import RunBenchRequest


def handle_run_bench_command(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    remote: str | None,
    remote_workdir: str | None,
) -> int:
    request = RunBenchRequest(
        command=args.command,
        bench_file=resolve_existing_path(parser, args.bench_file, "Bench file"),
        operator_file=resolve_existing_path(parser, args.operator_file, "Operator file"),
        bench_mode=cast(Optional[str], getattr(args, "bench_mode", None)),
        baseline_operator_file=cast(Optional[str], getattr(args, "baseline_operator_file", None)),
        fast_probe=bool(getattr(args, "fast_probe", False)),
        output=cast(Optional[str], getattr(args, "output", None)),
        skip_latency_errors=bool(getattr(args, "skip_latency_errors", False)),
        metric_source=cast(MetricSource, getattr(args, "metric_source", "auto")),
        remote=remote,
        remote_workdir=remote_workdir,
        keep_remote_workdir=bool(args.keep_remote_workdir),
        verbose=bool(args.verbose),
    )
    try:
        return run_bench(request)
    except RunBenchInputError as exc:
        # parser.error is NoReturn (it exits the CLI); returning it keeps every
        # branch of this function an explicit return.
        return parser.error(str(exc))
