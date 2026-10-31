# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""SessionStart hook: 注入工作流入口纪律（简短，不重复正文）"""

import logging
import sys

LOG = logging.getLogger("session_start")

REMINDER = """[model-recommend-infer-optimize] 推荐模型整网推理优化已就位。

入口纪律（细节以 AGENTS.md 与 workflows/model-recommend-infer-workflow.md 为准）：
1. 先分流：无基线走条目 0-14；有 loop_state 且未终止则从 iteration+1 续跑；单点诉求直接调对应 recommend-* skill。
2. 一处硬约束：onnx 输入禁止改动原始 onnx 文件，改写只能落在 GE 内存图。
3. 一处门禁：任何改动落地前必须过精度门禁（串行单并发 verify）+ 性能门禁（同口径、双口径、噪声带）。
4. 循环纪律：一轮一动作；台账与每轮报告当轮落盘，禁止事后补写。
5. 状态文件（loop_state.json / workflow_status.md / next_actions.json）只由 primary 写。
6. 派发：采集→runner，分析→analyzer，实施→implementer，验收→reviewer。primary 只编排。
"""


def configure_logging():
    """SessionStart 的 stdout 会被注入到上下文，因此日志只走 stdout 且不加前缀。"""
    if LOG.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


def main():
    configure_logging()
    # 载荷内容不影响注入文本，读取一次后丢弃即可
    sys.stdin.read()
    LOG.info(REMINDER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
