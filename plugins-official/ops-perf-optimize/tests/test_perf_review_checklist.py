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

"""静态代码检视检查点索引的完整性门禁。

索引是检视 Agent 的唯一真源：一条断链或一个 status 漂移都会让该检查点被静默跳过，
而检视报告仍然显示"全部 ready 检查点已排查"。这些不变量必须机器校验。
"""
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
REFS = ROOT / "skills" / "ascendc-performance-review" / "references"
INDEX = REFS / "perf-review-checklist.md"
KNOWLEDGE = REFS / "perf-review-knowledge"

ROW = re.compile(
    r"\|\s*(PRC-[A-Z]+-\d{3})\s*\|[^|]*\|[^|]*\|([^|]+)\|\s*(\w+)\s*\|"
)
TARGET = re.compile(r"\[[^\]]+\]\(([^)]+)\)(?:\s*`([^`]+)`)?$")


def parse_target(cell):
    """Return (base_dir, relative_path) for an index row's knowledge-file cell."""
    match = TARGET.match(cell.strip())
    if not match:
        raise AssertionError(f"知识点文件单元格格式非法：{cell.strip()}")
    url, path = match.groups()
    if url.startswith("skill:"):
        skill_root = resolve_skill(url[len("skill:"):])
        if skill_root is None:
            raise AssertionError(f"skill 引用无法定位：{url}")
        if not path:
            raise AssertionError(f"skill 引用缺相对路径：{cell.strip()}")
        return skill_root, path
    if path:
        raise AssertionError(f"普通链接不允许附加路径：{cell.strip()}")
    return REFS, url


def resolve_skill(name):
    candidates = [REPO / "vendor" / "cannbot-skills" / "ops" / name]
    candidates += sorted(REPO.glob(f"plugins-*/**/skills/{name}"))
    for candidate in candidates:
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


def rows():
    return [
        (cid, *parse_target(cell), status)
        for cid, cell, status in ROW.findall(INDEX.read_text(encoding="utf-8"))
    ]


class ChecklistIndex(unittest.TestCase):
    def test_index_declares_a_valid_status(self):
        head = INDEX.read_text(encoding="utf-8")
        declared = re.search(r"^status:\s*(\S+)\s*$", head, re.M)
        self.assertIsNotNone(declared, "索引缺 status 头，检视 Agent 无法判断是否跳过本步骤")
        self.assertIn(declared.group(1), ("ready", "pending"), "索引 status 取值非法")

    def test_every_row_resolves_to_a_knowledge_file(self):
        for cid, base, rel, _ in rows():
            path, _, anchor = rel.partition("#")
            self.assertTrue((base / path).is_file(), f"{cid} 链接断裂：{rel}")
            if anchor:
                text = (base / path).read_text(encoding="utf-8")
                self.assertIn(f'<a id="{anchor}"></a>', text)
                self.assertIn(cid, text.split(f'<a id="{anchor}"></a>', 1)[1].split('<a id=', 1)[0])

    def test_no_orphan_knowledge_files(self):
        linked = {
            (base / rel.split("#", 1)[0]).resolve()
            for _, base, rel, _ in rows()
            if base == REFS
        }
        on_disk = {p.resolve() for p in KNOWLEDGE.rglob("PRC-*.md")}
        self.assertEqual(on_disk - linked, set(), "知识点文件未登记进索引，会被静默跳过")

    def test_id_and_status_agree_with_file_front_matter(self):
        for cid, base, rel, status in rows():
            if "#" in rel:
                self.assertEqual(status, "ready")
                continue  # Family chapters expose anchored criteria, not private card frontmatter.
            text = (base / rel).read_text(encoding="utf-8")
            fid = re.search(r"^id:\s*(\S+)", text, re.M)
            fstatus = re.search(r"^status:\s*(\S+)", text, re.M)
            self.assertIsNotNone(fid, f"{rel} 缺 id")
            self.assertIsNotNone(fstatus, f"{rel} 缺 status")
            self.assertEqual(fid.group(1), cid, f"{rel} 的 id 与索引不一致")
            self.assertEqual(fstatus.group(1), status, f"{rel} 的 status 与索引不一致")
            self.assertIn(status, ("ready", "draft"), f"{cid} status 取值非法")

    def test_ids_are_unique(self):
        ids = [cid for cid, _, _, _ in rows()]
        dupes = [cid for cid, n in Counter(ids).items() if n > 1]
        self.assertEqual(dupes, [], "检查点 ID 重复（ID 一经分配不复用）")

    def test_summary_line_matches_actual_counts(self):
        parsed = rows()
        ready = sum(1 for *_, s in parsed if s == "ready")
        draft = sum(1 for *_, s in parsed if s == "draft")
        expected = f"统计：{len(parsed)} 条（ready {ready} / draft {draft}）。"
        self.assertIn(expected, INDEX.read_text(encoding="utf-8"), "索引统计行与实际条目数不符")

    def test_knowledge_files_carry_all_six_sections(self):
        required = ("## 知识点", "## 错误写法", "## 正确写法", "## 识别方法", "## 证据要求", "## 参考")
        for cid, base, rel, _ in rows():
            if "#" in rel:
                continue  # Anchor existence and checkpoint identity are validated above.
            text = (base / rel).read_text(encoding="utf-8")
            for section in required:
                self.assertIn(section, text, f"{cid} 缺章节 {section}")


if __name__ == "__main__":
    unittest.main(verbosity=1) if "-v" in sys.argv else unittest.main()
