#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Workflow 文档一致性自检（离线、零依赖）。

校验项：
1. templates/*.json 可被解析；
2. workflow 内相对链接可解析；
3. Markdown 无裸单波浪线 `~`（GFM 删除线风险）；
4. 主工作流条目 0-14 齐全；
5. 引用的原子 skill 目录存在（找不到 skill 源时降级为告警）；
6. 无已删除文件（gate-rules/loop-rules/precision-gate-template）的残留引用。

用法：python3 workflows/scripts/check_docs.py
退出码：0 通过，1 有错误。
"""
import json
import logging
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WF = ROOT / "workflows" / "model-recommend-infer-workflow.md"
errors, warnings = [], []

LOG = logging.getLogger("check_docs")


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    return text


def find_skills_root():
    cands = []
    env = os.environ.get("CANNBOT_SKILL_SRC_ROOT")
    if env:
        cands.append(Path(env))
        cands.append(Path(env) / "community" / "model")
    cands += [
        ROOT / "vendor" / "cannbot-skills" / "community" / "model",
        ROOT.parent / "vendor" / "cannbot-skills" / "community" / "model",
        ROOT.parents[2] / "cannbot-skills" / "community" / "model",
    ]
    for c in cands:
        if c.is_dir():
            return c
    return None


def check_json():
    for p in sorted((ROOT / "workflows" / "templates").glob("*.json")):
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[json] {p.relative_to(ROOT)}: {exc}")


def check_links_and_tilde():
    link_re = re.compile(r"\]\(([^)]+)\)")
    for p in sorted((ROOT / "workflows").rglob("*.md")):
        raw = p.read_text(encoding="utf-8")
        clean = strip_code(raw)
        for m in link_re.finditer(clean):
            t = m.group(1).strip()
            if t.startswith(("http://", "https://", "#", "mailto:")):
                continue
            t = t.split("#")[0]
            if not t:
                continue
            if not (p.parent / t).exists():
                errors.append(f"[link] {p.relative_to(ROOT)} -> {t} (missing)")
        for i, line in enumerate(raw.splitlines(), 1):
            if "~" in strip_code(line):
                errors.append(f"[tilde] {p.relative_to(ROOT)}:{i}: {line.strip()}")


def check_entries():
    if not WF.exists():
        errors.append("[entry] 主工作流文件缺失")
        return
    text = WF.read_text(encoding="utf-8")
    for n in range(15):
        if not re.search(rf"^###\s+{n}\.", text, re.M):
            errors.append(f"[entry] 缺少条目 {n}")
    skills = set(re.findall(r"model-recommend-[a-z0-9-]+", text))
    skills = {s for s in skills if not s.startswith("model-recommend-infer-")}
    root = find_skills_root()
    if root is None:
        warnings.append("[skill] 未找到 skill 源目录，跳过目录存在性校验（可设 CANNBOT_SKILL_SRC_ROOT）")
        return
    for s in sorted(skills):
        if not (root / s / "SKILL.md").exists():
            errors.append(f"[skill] 引用不存在：{s}（查于 {root}）")


def check_stale():
    stale = ["gate-rules.md", "loop-rules.md", "precision-gate-template"]
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in {".md", ".json", ".py"}:
            continue
        if p.name == "check_docs.py":
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for s in stale:
            if s in text:
                errors.append(f"[stale] {p.relative_to(ROOT)} 仍引用已删除的 {s}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True)
    check_json()
    check_links_and_tilde()
    check_entries()
    check_stale()
    for w in warnings:
        LOG.warning("WARN %s", w)
    for e in errors:
        LOG.error("FAIL %s", e)
    if errors:
        LOG.error("%d error(s), %d warning(s)", len(errors), len(warnings))
        return 1
    LOG.info("OK: workflow docs consistent (%d warning(s))", len(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
