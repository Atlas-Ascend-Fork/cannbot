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
import os
import re
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

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
    cell = cell.strip()
    if "](" not in cell:
        # 裸相对路径（历史格式）：直接视为 REFS 相对路径。
        path = cell.strip('`')
        if not path:
            raise AssertionError("知识点文件单元格为空")
        return REFS, path
    match = TARGET.match(cell)
    if not match:
        raise AssertionError(f"知识点文件单元格格式非法：{cell}")
    url, path = match.groups()
    if url.startswith("skill:"):
        skill_root = resolve_skill(url[len("skill:"):])
        if skill_root is None:
            raise AssertionError(f"skill 引用无法定位：{url}")
        if not path:
            raise AssertionError(f"skill 引用缺相对路径：{cell.strip()}")
        # cannbot-skills 布局：该 skill 的参考目录名为 references/（上游为 reference/）。
        if skill_root.name == "ascendc-performance-best-practices":
            path = re.sub(r"(?:^|/)reference/", "references/", path)
        return skill_root, path
    if path:
        raise AssertionError(f"普通链接不允许附加路径：{cell.strip()}")
    return REFS, url


def resolve_skill(name):
    candidates = [REPO / "vendor" / "cannbot-skills" / "ops" / name, REPO / "ops" / name, REPO / "infra" / name]
    candidates += sorted(REPO.glob(f"plugins-*/**/skills/{name}"))
    for candidate in candidates:
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


def rows():
    entries = []
    for cid, cell, status in ROW.findall(INDEX.read_text(encoding="utf-8")):
        base_dir, rel_path = parse_target(cell)
        rel = os.path.relpath(base_dir / rel_path, REFS)
        entries.append((cid, rel, status))
    return entries


REQUIRED_SECTIONS = ("知识点", "错误写法", "正确写法", "识别方法", "证据要求", "参考")
ANCHOR = re.compile(r'^<a\s+id=["\']([^"\']+)["\']\s*></a>\s*$', re.M)
HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.M)


def read_entry(cid, rel, refs=REFS):
    """Resolve a real file and isolate the exact anchored topic subsection.

    Legacy cards own YAML id/status and six chapters. Topic chapters instead own
    explicit anchors and fourth-level PRC headings; their status is declared only
    by the index, not by fabricated per-topic front matter.
    """
    file_rel, marker, fragment = rel.partition("#")
    path = refs / unquote(file_rel)
    if not path.is_file():
        raise AssertionError(f"{cid} 链接断裂：{rel}")
    text = path.read_text(encoding="utf-8")
    if not marker:
        return dict(path=path.resolve(), text=text, fragment=None, section=text)
    anchor = unquote(fragment)
    if not anchor or "#" in anchor or anchor != cid.lower():
        raise AssertionError(f"{cid} 锚点与精确 ID 不一致：{fragment}")
    # Do not accept an example HTML anchor inside a fenced code block.
    visible = re.sub(r"^(`{3,}|~{3,}).*?^\1[ \t]*$", "", text, flags=re.M | re.S)
    anchors = [match for match in ANCHOR.finditer(visible) if match.group(1) == anchor]
    if len(anchors) != 1:
        raise AssertionError(f"{cid} 锚点不存在或不唯一：{anchor}")
    tail = visible[anchors[0].end():]
    heading = re.match(r"\s*####[ \t]+([^\n]+)\n", tail)
    if heading is None or re.findall(r"PRC-[A-Z]+-\d{3}", heading.group(1)) != [cid]:
        raise AssertionError(f"{cid} 锚点后章节标题不是对应精确 ID")
    body = tail[heading.end():]
    # Evidence and boundaries must belong to this subsection, never its neighbor.
    end = len(body)
    for next_heading in HEADING.finditer(body):
        if len(next_heading.group(1)) <= 4:
            end = min(end, next_heading.start())
            break
    next_anchor = ANCHOR.search(body)
    if next_anchor:
        end = min(end, next_anchor.start())
    section = body[:end].strip()
    if not section:
        raise AssertionError(f"{cid} 锚点章节内容为空")
    return dict(path=path.resolve(), text=text, fragment=anchor, section=section)


def check_metadata(cid, status, entry):
    if status not in ("ready", "draft"):
        raise AssertionError(f"{cid} status 取值非法")
    if entry["fragment"] is not None:
        # Exact section ID already verified; index is the topic status authority.
        return
    front = re.match(r"\A---\s*\n(.*?)\n---[ \t]*(?:\n|$)", entry["text"], re.S)
    if front is None:
        raise AssertionError(f"{cid} 缺 front matter")
    for field, expected in (("id", cid), ("status", status)):
        values = re.findall(rf"^{field}:[ \t]*(\S+)[ \t]*$", front.group(1), re.M)
        if values != [expected]:
            raise AssertionError(f"{cid} 的 {field} 与索引不一致：{values}")


def check_content(cid, entry):
    text = entry["section"]
    if entry["fragment"] is None:
        for section in REQUIRED_SECTIONS:
            if not re.search(rf"^##[ \t]+{section}[ \t]*$", text, re.M):
                raise AssertionError(f"{cid} 缺章节 {section}")
        return
    # Current topic format uses prose: detection/conditions, false-positive
    # boundaries, and concrete finding evidence, rather than six copied chapters.
    paragraphs = [part.strip() for part in re.split(r"\n[ \t]*\n", text) if part.strip()]
    if len(paragraphs) < 2:
        raise AssertionError(f"{cid} 缺独立识别/边界与证据段落")
    requirements = {
        "识别/检查方法": r"检视时|检查|计算|追值|核对|先证明",
        "误报边界": r"不报|不建议|不足以报错|不机械替换",
        "finding 证据要求": r"finding\s*(?:必须|应)(?:给出|列出)[^。\n]+",
    }
    for label, pattern in requirements.items():
        if not re.search(pattern, text):
            raise AssertionError(f"{cid} 缺 {label}")


class ChecklistIndex(unittest.TestCase):
    def test_index_declares_a_valid_status(self):
        head = INDEX.read_text(encoding="utf-8")
        declared = re.search(r"^status:\s*(\S+)\s*$", head, re.M)
        self.assertIsNotNone(declared, "索引缺 status 头，检视 Agent 无法判断是否跳过本步骤")
        self.assertIn(declared.group(1), ("ready", "pending"), "索引 status 取值非法")

    def test_every_row_resolves_to_a_knowledge_file(self):
        for cid, rel, _ in rows():
            read_entry(cid, rel)

    def test_no_orphan_knowledge_files(self):
        linked = {(REFS / rel.partition("#")[0]).resolve() for _, rel, _ in rows()}
        on_disk = {p.resolve() for p in KNOWLEDGE.rglob("PRC-*.md")}
        self.assertEqual(on_disk - linked, set(), "知识点文件未登记进索引，会被静默跳过")

    def test_id_and_status_follow_their_maintained_format(self):
        for cid, rel, status in rows():
            check_metadata(cid, status, read_entry(cid, rel))

    def test_ids_are_unique(self):
        ids = [cid for cid, _, _ in rows()]
        dupes = [cid for cid, n in Counter(ids).items() if n > 1]
        self.assertEqual(dupes, [], "检查点 ID 重复（ID 一经分配不复用）")

    def test_summary_line_matches_actual_counts(self):
        parsed = rows()
        ready = sum(1 for _, _, s in parsed if s == "ready")
        draft = sum(1 for _, _, s in parsed if s == "draft")
        expected = f"统计：{len(parsed)} 条（ready {ready} / draft {draft}）。"
        self.assertIn(expected, INDEX.read_text(encoding="utf-8"), "索引统计行与实际条目数不符")

    def test_legacy_six_sections_and_topic_section_content(self):
        for cid, rel, _ in rows():
            check_content(cid, read_entry(cid, rel))

    def test_topic_sections_have_no_unindexed_prc_anchors(self):
        linked = {(read_entry(cid, rel)["path"], cid.lower())
                  for cid, rel, _ in rows() if "#" in rel}
        for path in {path for path, _ in linked}:
            for anchor in ANCHOR.findall(path.read_text(encoding="utf-8")):
                if re.fullmatch(r"prc-[a-z]+-\d{3}", anchor):
                    self.assertIn((path, anchor), linked, f"{path} 未登记章节 {anchor}")


class TopicLinkValidation(unittest.TestCase):
    CID = "PRC-MM-001"
    TOPIC = ('<a id="prc-mm-001"></a>\n'
             '#### 多级流水（PRC-MM-001）\n\n'
             '检视时检查地址区间并计算容量，证明生产者与消费者。\n\n'
             'K 只有一轮时不报。finding 必须给出地址、容量与事件配对表。\n')

    def resolve_fixture(self, text, rel="topic.md#prc-mm-001"):
        with tempfile.TemporaryDirectory() as tmp:
            refs = Path(tmp)
            (refs / "topic.md").write_text(text, encoding="utf-8")
            return read_entry(self.CID, rel, refs)

    def test_valid_topic_has_real_anchor_exact_id_and_local_content(self):
        entry = self.resolve_fixture(self.TOPIC)
        check_metadata(self.CID, "ready", entry)
        check_content(self.CID, entry)

    def test_missing_anchor_rejected_even_when_file_and_id_exist(self):
        with self.assertRaisesRegex(AssertionError, "锚点不存在"):
            self.resolve_fixture(self.TOPIC.replace('<a id="prc-mm-001"></a>\n', ""))

    def test_wrong_heading_id_rejected_even_when_anchor_exists(self):
        with self.assertRaisesRegex(AssertionError, "对应精确 ID"):
            self.resolve_fixture(self.TOPIC.replace('（PRC-MM-001）', '（PRC-MM-002）'))
        with self.assertRaisesRegex(AssertionError, "锚点与精确 ID"):
            self.resolve_fixture(self.TOPIC, "topic.md#prc-mm-002")

    def test_neighbor_evidence_cannot_satisfy_empty_or_incomplete_section(self):
        prefix = '<a id="prc-mm-001"></a>\n#### 当前（PRC-MM-001）\n\n'
        neighbor = ('<a id="prc-mm-002"></a>\n#### 邻项（PRC-MM-002）\n\n'
                    '检视时检查容量。\n\n不报误判。finding 必须给出配对表。\n')
        with self.assertRaisesRegex(AssertionError, "内容为空"):
            self.resolve_fixture(prefix + neighbor)
        entry = self.resolve_fixture(prefix + '检查地址和容量。\n\n不报误判。\n\n' + neighbor)
        with self.assertRaisesRegex(AssertionError, "finding 证据要求"):
            check_content(self.CID, entry)

    def test_legacy_still_requires_original_id_status_and_six_chapters(self):
        text = ('---\nid: PRC-MM-001\nstatus: draft\n---\n\n' +
                '\n\n'.join('## ' + title for title in REQUIRED_SECTIONS))
        entry = self.resolve_fixture(text, "topic.md")
        check_metadata(self.CID, "draft", entry)
        check_content(self.CID, entry)
        with self.assertRaisesRegex(AssertionError, "status 与索引不一致"):
            check_metadata(self.CID, "ready", entry)
        entry["section"] = entry["section"].replace('## 证据要求', '')
        with self.assertRaisesRegex(AssertionError, "缺章节 证据要求"):
            check_content(self.CID, entry)


if __name__ == "__main__":
    unittest.main(verbosity=1) if "-v" in sys.argv else unittest.main()
