#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------

"""Use the public harness callback to launch each phase in its own context."""

import logging
import os
from pathlib import Path
import subprocess
import sys

from workspace import load_context, prepare_phase, validate_graph_context

sys.dont_write_bytecode = True
LOGGER = logging.getLogger(__name__)


def main():
    # All arguments after this one belong to the unchanged public harness parser.
    harness = Path(sys.argv.pop(1)).resolve(strict=True)
    sys.path.insert(0, str(harness / "scripts"))
    import orchestrator

    args = orchestrator.parse_args()
    context = load_context(args.work_dir)
    if context["provider"] != args.provider:
        raise ValueError("provider differs from the frozen run")
    validate_graph_context(args.yaml, args.work_dir, context)
    provider = orchestrator.PROVIDERS.get(args.provider)
    if provider is None:
        raise ValueError(f"unsupported CLI provider: {args.provider}")

    def execute(entry, work_dir, session_path):
        prepared = prepare_phase(entry, work_dir, context)
        with open(session_path, "wb") as output:
            result = subprocess.run(
                provider.build_command(prepared["role"], prepared["prompt"]),
                cwd=prepared["cwd"], env={**os.environ, **prepared["env"]},
                stdout=output, stderr=subprocess.PIPE,
            )
        if result.returncode:
            with open(session_path, "ab") as output:
                output.write(f"\nexit={result.returncode}\n".encode() + result.stderr)
        return ("executed" if entry["_phase"] == "execute" else ""), result.returncode != 0

    return orchestrator.main(task_executor=execute, args=args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        LOGGER.error("[ops-direct-invoke] %s", error)
        sys.exit(2)
