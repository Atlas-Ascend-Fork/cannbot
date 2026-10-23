# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Command adapter for the three public run-test subcommands.

Builds a structured RunTestRequest from parsed CLI arguments and delegates to
the core run-test API (recording wrapper plus execution). Invalid input
combinations surface as argparse errors exactly like before.
"""

from __future__ import annotations

import argparse
from typing import Optional, cast

from command_paths import resolve_existing_path
from run_test_core import run_test
from run_test_executor import ReferenceRunFailure, RunTestInputError
from run_test_executor import RunTestRequest


def handle_run_test_command(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    remote: str | None,
    remote_workdir: str | None,
) -> int:
    request = RunTestRequest(
        command=args.command,
        test_file=resolve_existing_path(parser, args.test_file, "Test file"),
        operator_file=resolve_existing_path(parser, args.operator_file, "Operator file"),
        test_mode=cast(Optional[str], getattr(args, "test_mode", None)),
        ref_result=cast(Optional[str], getattr(args, "ref_result", None)),
        ref_operator_file=cast(Optional[str], getattr(args, "ref_operator_file", None)),
        case_id=cast(Optional[str], getattr(args, "case_id", None)),
        accuracy_mode=cast(Optional[str], getattr(args, "accuracy_mode", None)),
        remote=remote,
        remote_workdir=remote_workdir,
        keep_remote_workdir=bool(args.keep_remote_workdir),
        verbose=bool(args.verbose),
    )
    try:
        return run_test(request)
    except RunTestInputError as exc:
        # parser.error is NoReturn (it exits the CLI); returning it keeps every
        # branch of this function an explicit return.
        return parser.error(str(exc))
    except ReferenceRunFailure as exc:
        return exc.exit_code
