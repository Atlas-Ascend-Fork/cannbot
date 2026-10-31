#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""pre_tool_use.py 的行为回归测试。

重点覆盖三条纪律的放行/阻断边界，以及已知可绕过路径：
  - onnx 原图（含 tmp/../ 与 Windows 反斜杠写法）必须阻断；tmp/ 下副本放行
  - 状态文件只由 primary 写
  - 只读角色不得改模型/脚本类文件，但可写自己的产物
  - 载荷畸形时放行（fail-open，客户端不应因 hook 故障失去编辑能力）

用法：python3 tests/test_pre_tool_use.py
"""

import json
import logging
import os
import subprocess
import sys

LOG = logging.getLogger("test_pre_tool_use")


def configure_logging():
    """测试结果按纯文本输出，便于 CI 直接阅读。"""
    if LOG.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "hooks", "pre_tool_use.py")

CASES = [
    ("primary 改原图", "", "/p/models/M100/model/model.onnx", 2),
    ("tmp 副本放行", "", "/p/tmp/M100/probe.onnx", 0),
    ("tmp/../ 绕过应拦", "", "/p/tmp/../models/M100/model/model.onnx", 2),
    ("相对 tmp 放行", "", "tmp/M100/x.onnx", 0),
    ("相对 tmp/../ 应拦", "", "tmp/../model.onnx", 2),
    ("windows 反斜杠 tmp", "", "D:\\p\\tmp\\M100\\x.onnx", 0),
    ("windows 反斜杠绕过", "", "D:\\p\\tmp\\..\\model.onnx", 2),
    (
        "analyzer 改 .py",
        "model-recommend-infer-analyzer",
        "/p/models/M100/infer_run.py",
        2,
    ),
    ("analyzer 改 .pt", "model-recommend-infer-analyzer", "/p/models/M100/w.pt", 2),
    ("analyzer 改 .sh", "model-recommend-infer-analyzer", "/p/run.sh", 2),
    (
        "analyzer 写 findings",
        "model-recommend-infer-analyzer",
        "/p/data/M100/profiling-deep-analysis/iter1/findings.json",
        0,
    ),
    (
        "analyzer 写 loop_state",
        "model-recommend-infer-analyzer",
        "/p/data/M100/optimization_log/loop_state.json",
        2,
    ),
    (
        "analyzer 写 next_actions",
        "model-recommend-infer-analyzer",
        "/p/data/M100/regression-baseline-mgmt/next_actions.json",
        2,
    ),
    (
        "primary 写 next_actions",
        "",
        "/p/data/M100/regression-baseline-mgmt/next_actions.json",
        0,
    ),
    (
        "implementer 改 .cc",
        "model-recommend-infer-implementer",
        "/p/GE_SESSION_DEMO/src/graph_fusion_pass.cc",
        0,
    ),
    (
        "reviewer 改 yaml",
        "model-recommend-infer-reviewer",
        "/p/models/M100/shape_config.yaml",
        2,
    ),
    (
        "reviewer 写台账",
        "model-recommend-infer-reviewer",
        "/p/data/M100/optimization_log/perf_ledger.json",
        0,
    ),
    ("无 file_path", "", None, 0),
]


def invoke(payload):
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=payload,
        capture_output=True,
        text=True,
    )
    return proc.returncode


def main():
    configure_logging()
    failures = 0
    for name, agent, path, expect in CASES:
        tool_input = {} if path is None else {"file_path": path}
        payload = json.dumps({"agent_type": agent, "tool_input": tool_input})
        code = invoke(payload)
        ok = code == expect
        failures += 0 if ok else 1
        LOG.info(
            "%-4s %-22s exit=%d expect=%d"
            % ("OK" if ok else "FAIL", name, code, expect)
        )

    # 畸形载荷：fail-open
    code = invoke("{not-json")
    ok = code == 0
    failures += 0 if ok else 1
    LOG.info(
        "%-4s %-22s exit=%d expect=0" % ("OK" if ok else "FAIL", "畸形载荷放行", code)
    )

    LOG.info("failures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
