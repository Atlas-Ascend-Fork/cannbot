# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""PreToolUse hook: 三条纪律的前置防护（尽力拦截，不等同于沙箱）

1. onnx 原图零改动：编辑/写入 .onnx 文件时阻断（规范化路径后位于 tmp/ 下的临时副本除外）
   改写只能发生在 GE 内存图（aclgrphParseONNX 之后、AddGraph 之前）。
2. 状态文件独占写：loop_state.json / workflow_status.md / next_actions.json 只由 primary 写，
   subagent（agent_type 以 model-recommend-infer- 开头）写入一律阻断。
3. 只读角色越界保护：runner / analyzer / reviewer 不得改模型与执行代码，只能写自己的产物目录。

覆盖边界（已知且有意为之）：
- 只挂 PreToolUse 的 Edit / Write / MultiEdit。Bash 重定向、脚本内部写文件、以及客户端未上报
  文件路径的工具调用都无法拦截——这类写入靠流程纪律约束，不靠本 hook。
- 载荷无法解析或缺 file_path 时放行（fail-open），并在 stderr 留下提示：hook 自身故障不应
  让所有编辑失效；需要强隔离时请使用文件系统级沙箱。

退出码 2 = 阻断并把 stderr 反馈给模型；退出码 0 = 放行。
"""

import fnmatch
import json
import logging
import os
import sys

LOG = logging.getLogger("pre_tool_use")

READONLY_AGENTS = {
    "model-recommend-infer-runner",
    "model-recommend-infer-analyzer",
    "model-recommend-infer-reviewer",
}

# 模型与执行相关代码：只读角色一律禁改
MODEL_CODE_PATTERNS = [
    "*.onnx",
    "modeling_*.py",
    "runner_*.py",
    "infer*.py",
    "*.yaml",
    "*.yml",
    "*.cc",
    "*.cpp",
    "*.h",
    "*.hpp",
    "*.pt",
    "*.pth",
    "*.safetensors",
    "*.om",
    "*.py",
    "*.sh",
]

# 仅 primary 可写的状态文件
PRIMARY_ONLY_FILES = [
    "loop_state.json",
    "workflow_status.md",
    "next_actions.json",
    "final_optimization_report.md",
]


def configure_logging():
    """hook 的诊断信息只能走 stderr（stdout 留给协议数据）。"""
    if LOG.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


def block(message):
    """阻断本次调用：原因写 stderr，返回退出码 2 由入口统一退出。"""
    LOG.error(message)
    return 2


def matches(filename, patterns):
    return any(fnmatch.fnmatch(filename, p) for p in patterns)


def is_scratch_copy(file_path):
    """tmp/ 下的临时副本放行：精度定位需要暴露中间输出时按约定只允许落 tmp/。

    先规范化路径再判断，避免 tmp/../model.onnx 这类绕过；realpath 仅在路径存在时使用，
    这样符号链接指向原图也会被识别为原图而不是 scratch。
    """
    raw = file_path.replace("\\", "/")
    if os.path.exists(raw):
        try:
            raw = os.path.realpath(raw).replace("\\", "/")
        except OSError:
            pass
    norm = os.path.normpath(raw).replace("\\", "/")
    parts = [seg for seg in norm.split("/") if seg not in ("", ".")]
    if ".." in parts:
        return False
    return "tmp" in parts[:-1]


def read_payload():
    """读取并解析 hook 载荷；解析失败返回 None（调用方按 fail-open 放行）。"""
    try:
        return json.load(sys.stdin)
    except Exception:
        LOG.warning(
            "[model-recommend-infer-optimize] hook 载荷解析失败，已放行本次调用（fail-open）"
        )
        return None


def main():
    configure_logging()
    data = read_payload()
    if data is None:
        return 0

    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not file_path:
        return 0

    agent_type = data.get("agent_type", "") or ""
    basename = os.path.basename(file_path)

    # 守卫 1：onnx 原图零改动（全角色；tmp/ 下的临时副本除外）
    if basename.lower().endswith(".onnx") and not is_scratch_copy(file_path):
        return block(
            "[model-recommend-infer-optimize] 阻断：禁止修改原始 onnx 文件（%s）。\n"
            "onnx 输入路径的一切改写只能发生在 GE 内存图（aclgrphParseONNX 之后、AddGraph 之前），"
            "或使用 tmp/ 下的运行期临时副本；落盘改写 onnx 违反全局约束。" % basename
        )

    is_subagent = agent_type.startswith("model-recommend-infer-")

    # 守卫 2：状态文件独占写
    if is_subagent and basename in PRIMARY_ONLY_FILES:
        return block(
            "[model-recommend-infer-optimize] 阻断：%s 只由 primary 写入。\n"
            "请把结论摘要回传 primary，由其归并落库（见 workflows/references/artifact-conventions.md §7）。"
            % basename
        )

    # 守卫 3：只读角色越界
    if agent_type in READONLY_AGENTS and matches(basename, MODEL_CODE_PATTERNS):
        return block(
            "[model-recommend-infer-optimize] 阻断：角色 %s 只读，不得修改 %s。\n"
            "需要改动请回报 primary，由 model-recommend-infer-implementer 承接实施。"
            % (agent_type, basename)
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
