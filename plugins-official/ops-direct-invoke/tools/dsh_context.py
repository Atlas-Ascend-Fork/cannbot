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

"""Prepare frozen direct-invoke inputs for the unchanged DSH native scheduler."""

import argparse
import json
from pathlib import Path
import sys

from workspace import RESULT_LOGGER, load_context, phase_identity, prepare_phase, validate_graph_context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--yaml", type=Path)
    args = parser.parse_args()
    work = args.work_dir.resolve(strict=True)
    context = load_context(work)
    if context["provider"] != "dsh":
        raise ValueError("provider differs from the frozen DSH run")
    frozen = work / ".context"
    if args.yaml:
        validate_graph_context(args.yaml, work, context)
        harness = Path(context["skills"]["workflow-orchestrator"]).resolve(strict=True)
        if not harness.is_relative_to(frozen):
            raise ValueError("Harness must belong to the frozen workflow")
        runner = harness / "scripts/orchestrator.py"
        if not runner.is_file():
            raise ValueError("frozen workflow runner is missing")
        RESULT_LOGGER.info("%s", json.dumps({"runner": str(runner)}))
        return
    request = json.load(sys.stdin)
    if Path(request["workDir"]).resolve() != work:
        raise ValueError("node belongs to another workflow")
    prepared = prepare_phase({"task_id": request["taskId"], "agent": request["role"],
                              "_phase": request["phase"], "prompt": request["prompt"]}, work, context)
    cwd = Path(prepared["cwd"]).resolve(strict=True)
    if not cwd.is_relative_to(work / "agents") or cwd == work / "agents":
        raise ValueError("Phase cwd must stay inside this workflow")
    identity = Path(prepared["identity"]).resolve(strict=True)
    expected = phase_identity(context, prepared["role"], prepared["skills"])
    if (identity != expected or not identity.is_relative_to(frozen)
            or (cwd / "AGENTS.md").resolve(strict=True) != identity):
        raise ValueError("Invalid phase identity location")
    for path in prepared["skills"].values():
        if not Path(path).resolve(strict=True).is_relative_to(frozen):
            raise ValueError("Invalid phase Skill location")
    prompt = ("Execute one Python-scheduled workflow node using the DSH agent loop.\n"
              f"Phase identity: {identity}\nSelected Skills: {json.dumps(prepared['skills'])}\n"
              f"Role instructions (frontmatter is metadata):\n{identity.read_text(encoding='utf-8')}\n\n"
              "Follow the task's verdict callback instructions. "
              "Python owns dependencies, retries, approvals and status updates.\n"
              + prepared["prompt"])
    RESULT_LOGGER.info("%s", json.dumps({"cwd": str(cwd), "prompt": prompt}, ensure_ascii=False))


if __name__ == "__main__":
    main()
