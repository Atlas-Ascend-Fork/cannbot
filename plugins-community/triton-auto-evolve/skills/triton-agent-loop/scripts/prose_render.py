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
"""prose_render.py — H2 分层模型：叙述类产物由独立 headless 小模型会话渲染。

大模型 route/父会话只产结构化 JSON；模板能渲染的走 python（render_report.py，
零 token）；必须行文的（如 knowledge_evolution.md 知识演化叙述）由本脚本
另起 ``claude --print --model <prose_model>`` 小模型会话完成——Claude 会话
内不能换模型，但每次 CLI 启动可选模型。

调用方（gene-fusion/round.md 轮末知识管理步骤）失败即跳过，不得阻塞主流程：
    python3 prose_render.py --kind knowledge_evolution \
        --json route-1/knowledge_pool_update.json route-2/... \
        --out knowledge_evolution.md

超时或非零退出码 → exit 1；调用方据此回退（产物缺章节优于阻塞）。
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 默认 prose 模型：haiku 级小模型（渲染叙述够用，成本/耗时远低于 route 主模型）
DEFAULT_PROSE_MODEL = "claude-haiku-4-5-20251001"

# 各 kind 的输出骨架与纪律。叙述只允许使用 JSON 中出现过的数字与结论，禁止编造。
PROMPT_TEMPLATES = {
    "knowledge_evolution": {
        "title": "# 知识演化",
        "sections": [
            "## 知识单元价值评估",
            "## 删除单元及原因",
            "## 新增洞见",
            "## 下一轮建议",
        ],
        "instruction": (
            "根据以下 gene-fusion route 产物 JSON，撰写本轮知识演化叙述。"
            "数字与结论必须来自 JSON 原文，禁止编造；各 route 间用子标题区分；"
            "无对应内容的章节写「（无）」。"
        ),
    },
    "round_journal": {
        "title": "# Round {round_index} Journal",
        "sections": [
            "## Design / Evolution Rationale",
            "## Route Iteration Summary",
            "## Final Outcome",
        ],
        "instruction": (
            "根据以下 gene-fusion 本轮产物 JSON（round_result / route 迭代 / 基因池更新），"
            "撰写 Round Journal 行文。数字与结论必须来自 JSON 原文，禁止编造；"
            "每条 route 一行摘要（方向、迭代数、关键修复、最终取舍与 speedup）；"
            "无对应内容的章节写「（无）」。"
        ),
    },
}


def build_prompt(kind: str, json_texts: list[tuple[str, str]], round_index: int = 0) -> str:
    spec = PROMPT_TEMPLATES[kind]
    title = spec["title"].format(round_index=round_index)
    parts = [spec["instruction"], "输出骨架（严格保持标题层级）：", title]
    parts.extend(spec["sections"])
    parts.append("---")
    for name, text in json_texts:
        parts.append(f"[来源 JSON: {name}]\n{text}")
    parts.append("---")
    parts.append("只输出 markdown 正文，不要代码围栏，不要额外解释。")
    return "\n".join(parts)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="H2 分层模型：headless 小模型渲染叙述类产物")
    parser.add_argument("--kind", choices=sorted(PROMPT_TEMPLATES), default="knowledge_evolution",
                        help="产物类型（决定输出骨架），默认 knowledge_evolution")
    parser.add_argument("--round-index", type=int, default=0,
                        help="轮号（round_journal 骨架标题用）")
    parser.add_argument("--json", nargs="+", required=True, help="输入 JSON 文件路径（可多个）")
    parser.add_argument("--out", required=True, help="输出 markdown 文件路径")
    parser.add_argument("--prose-model", default=None,
                        help="渲染用小模型；默认取 TRITON_PROSE_MODEL 环境变量，再退回内置默认")
    parser.add_argument("--timeout", type=int, default=180,
                        help="小模型会话超时（秒），默认 180")
    return parser.parse_args()


def _load_json_inputs(paths: list[str]) -> list[tuple[str, str]]:
    """读取输入 JSON 文件（缺失/不可读的条目告警跳过）。"""
    json_texts: list[tuple[str, str]] = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            logger.warning("[prose_render] WARN: %s 不存在，跳过", p)
            continue
        try:
            json_texts.append((path.name, path.read_text(encoding="utf-8")))
        except OSError as exc:
            logger.warning("[prose_render] WARN: %s 读取失败（%s），跳过", p, exc)
    return json_texts


def _run_prose_session(claude_bin: str, prose_model: str, prompt: str, timeout: int) -> str:
    """调用 claude CLI 完成 prose 会话；失败记录日志并返回空串。"""
    start = time.time()
    try:
        proc = subprocess.run(
            [claude_bin, "--print", "--model", prose_model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.error("[prose_render] FAIL: prose 会话超时（%ss），调用方应回退跳过", timeout)
        return ""
    except OSError as exc:
        logger.error("[prose_render] FAIL: 无法启动 claude CLI（%s）", exc)
        return ""

    elapsed = time.time() - start
    if proc.returncode != 0 or not proc.stdout.strip():
        logger.error(
            "[prose_render] FAIL: prose 会话 rc=%s，stderr: %s",
            proc.returncode, (proc.stderr or "")[:500],
        )
        return ""
    logger.info("[prose_render] prose 会话完成 elapsed=%.1fs", elapsed)
    return proc.stdout.strip()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()

    prose_model = (
        args.prose_model
        or os.environ.get("TRITON_PROSE_MODEL")
        or DEFAULT_PROSE_MODEL
    )

    json_texts = _load_json_inputs(args.json)
    if not json_texts:
        logger.error("[prose_render] FAIL: 无可用输入 JSON")
        return 1

    claude_bin = shutil.which("claude")
    if claude_bin is None:
        logger.error("[prose_render] FAIL: PATH 中找不到 claude CLI，调用方应回退跳过")
        return 1

    prompt = build_prompt(args.kind, json_texts, round_index=args.round_index)
    body = _run_prose_session(claude_bin, prose_model, prompt, args.timeout)
    if not body:
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body + "\n", encoding="utf-8")
    logger.info("[prose_render] OK: %s model=%s", out_path, prose_model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
