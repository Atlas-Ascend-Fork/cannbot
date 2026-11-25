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
"""skills/tilelang2ascendc-knowledge/scripts/knowledge_store.py 的 UT。

覆盖：frontmatter 解析、卡片发现与覆盖、query 过滤/排序、initialize、
record 写入与索引重建、promote 清单与 diff、CLI 退出码。

运行：python3 tests/knowledge/test_knowledge_store.py
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from runtime import PYTHON  # noqa: E402


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    PLUGIN_ROOT
    / "skills"
    / "tilelang2ascendc-knowledge"
    / "scripts"
    / "knowledge_store.py"
)

_spec = importlib.util.spec_from_file_location("knowledge_store_ut", str(SCRIPT))
ks = importlib.util.module_from_spec(_spec)
sys.modules["knowledge_store_ut"] = ks  # dataclasses 解析类型注解时需要模块已注册
_spec.loader.exec_module(ks)


def card_text(
    title,
    description="",
    tags=(),
    type_="Runbook",
    status="stable",
    platforms=(),
    body="",
):
    def quoted_list(values):
        return "[" + ", ".join(json.dumps(value) for value in values) + "]"

    return (
        "---\n"
        f"title: {json.dumps(title)}\n"
        f"description: {json.dumps(description)}\n"
        f"type: {json.dumps(type_)}\n"
        f"status: {json.dumps(status)}\n"
        f"tags: {quoted_list(tags)}\n"
        f"platforms: {quoted_list(platforms)}\n"
        "---\n"
        "\n"
        f"{body}\n"
    )


class KnowledgeTestBase(unittest.TestCase):
    # ── properties ──────────────────────────────────────────
    @property
    def project_bundle(self):
        return self.project / ".tilelang2ascendc" / "knowledge"

    # ── static fixtures ─────────────────────────────────────
    @staticmethod
    def write_card(base, category, name, **kwargs):
        directory = base / category
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.md"
        path.write_text(card_text(name, **kwargs), encoding="utf-8")
        return path

    @staticmethod
    def run_cli(*args):
        return subprocess.run(
            [PYTHON, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )

    # ── lifecycle ───────────────────────────────────────────
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="t2a-knowledge-")
        self.root = Path(self._tmp.name)
        self.project = self.root / "project"
        self.builtin = self.root / "builtin"
        self.project.mkdir()
        self.builtin.mkdir()

    def tearDown(self):
        self._tmp.cleanup()


class FrontmatterTest(KnowledgeTestBase):
    def test_inline_list_and_quotes(self):
        data, body = ks.parse_frontmatter(
            card_text("Title", "desc", tags=("A", "B"), platforms=("a2",))
        )
        self.assertEqual(data["title"], "Title")
        self.assertEqual(data["tags"], ["A", "B"])
        self.assertEqual(data["platforms"], ["a2"])
        self.assertNotIn("title:", body)

    def test_block_list(self):
        text = '---\ntitle: T\ntags:\n  - one\n  - "two"\n---\nbody\n'
        data, _ = ks.parse_frontmatter(text)
        self.assertEqual(data["tags"], ["one", "two"])

    def test_comments_and_blank_lines_are_skipped(self):
        text = "---\n# comment\ntitle: T\n\nstatus: draft\n---\n"
        data, _ = ks.parse_frontmatter(text)
        self.assertEqual(data["title"], "T")
        self.assertEqual(data["status"], "draft")

    def test_missing_frontmatter(self):
        data, body = ks.parse_frontmatter("plain text")
        self.assertEqual(data, {})
        self.assertEqual(body, "plain text")


class HelperTest(KnowledgeTestBase):
    def test_split_csv(self):
        self.assertEqual(ks.split_csv(["a,b", " c ", ""]), ["a", "b", "c"])

    def test_unquote(self):
        self.assertEqual(ks.unquote('"x"'), "x")
        self.assertEqual(ks.unquote("'y'"), "y")
        self.assertEqual(ks.unquote("z"), "z")

    def test_as_list(self):
        self.assertEqual(ks.as_list(["a", 1]), ["a", "1"])
        self.assertEqual(ks.as_list(""), [])
        self.assertEqual(ks.as_list("x"), ["x"])

    def test_slugify(self):
        self.assertEqual(ks.slugify("Hello World!"), "hello_world")
        self.assertEqual(ks.slugify("  a__b  "), "a_b")
        self.assertEqual(ks.slugify("中文标题"), "")

    def test_resolve_slug_uses_title_and_stable_fallback(self):
        request = ks.RecordRequest(
            project=self.project, title="Add Mask", description="d"
        )
        self.assertEqual(ks.resolve_slug(request), "add_mask")

        chinese = ks.RecordRequest(
            project=self.project, title="中文标题", description="d"
        )
        first = ks.resolve_slug(chinese)
        self.assertTrue(first.startswith("entry_"))
        self.assertEqual(first, ks.resolve_slug(chinese))


class DiscoveryTest(KnowledgeTestBase):
    def test_read_cards_skips_index_and_symlink(self):
        self.write_card(self.builtin, "learned", "a", description="first")
        (self.builtin / "learned" / "index.md").write_text(
            "# index\n", encoding="utf-8"
        )
        (self.builtin / "learned" / "link.md").symlink_to(
            self.builtin / "learned" / "a.md"
        )
        cards = ks.read_cards(self.builtin)
        self.assertEqual([card["title"] for card in cards], ["a"])

    def test_read_card_metadata(self):
        self.write_card(
            self.builtin,
            "debug",
            "a",
            description="desc",
            tags=("X",),
            type_="Runbook",
            status="draft",
            body="body text",
        )
        card = ks.read_cards(self.builtin)[0]
        self.assertEqual(card["category"], "debug")
        self.assertEqual(card["tags"], ["x"])
        self.assertIn("body text", card["body"])

    def test_project_overrides_builtin_same_relative_path(self):
        self.write_card(self.builtin, "learned", "same", description="builtin")
        self.write_card(self.project_bundle, "learned", "same", description="project")
        cards = ks.collect_cards(
            [("builtin", self.builtin), ("project", self.project_bundle)]
        )
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["scope"], "project")
        self.assertEqual(cards[0]["description"], "project")

    def test_resolve_query_roots(self):
        self.assertEqual(
            ks.resolve_query_roots(self.project_bundle, self.builtin, "builtin"),
            [("builtin", self.builtin)],
        )
        self.assertEqual(
            ks.resolve_query_roots(self.project_bundle, None, "builtin"), []
        )
        self.assertEqual(
            ks.resolve_query_roots(self.project_bundle, self.builtin, "project"),
            [("project", self.project_bundle)],
        )
        self.assertEqual(
            ks.resolve_query_roots(self.project_bundle, self.builtin, "all"),
            [("builtin", self.builtin), ("project", self.project_bundle)],
        )

    def test_auto_scope_prefers_existing_project_bundle(self):
        (self.project_bundle / "learned").mkdir(parents=True)
        self.assertEqual(
            ks.resolve_query_roots(self.project_bundle, self.builtin, "auto"),
            [("project", self.project_bundle)],
        )
        self.assertEqual(
            ks.resolve_query_roots(
                self.project_bundle / "missing", self.builtin, "auto"
            ),
            [("builtin", self.builtin)],
        )


class QueryTest(KnowledgeTestBase):
    def setUp(self):
        super().setUp()
        self.write_card(
            self.builtin,
            "learned",
            "tbuf_overflow",
            description="UB 缓冲区越界",
            tags=("ub", "overflow"),
            type_="Runbook",
            status="stable",
            body="TQue 深度过大",
        )
        self.write_card(
            self.builtin,
            "optimization",
            "pipe_balance",
            description="流水线并行度",
            tags=("pipeline",),
            type_="Strategy",
            status="draft",
            body="double buffer",
        )

    def request(self, **kwargs):
        base = dict(project=self.project, builtin=self.builtin, scope="builtin")
        base.update(kwargs)
        return ks.QueryRequest(**base)

    def test_returns_matching_card(self):
        result = ks.query(self.request(text="overflow"))
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["cards"][0]["title"], "tbuf_overflow")

    def test_terms_are_combined_with_and(self):
        self.assertEqual(ks.query(self.request(text="overflow pipeline"))["total"], 0)

    def test_filters_by_category_type_status(self):
        self.assertEqual(ks.query(self.request(category="optimization"))["total"], 1)
        self.assertEqual(ks.query(self.request(type_="runbook"))["total"], 1)
        self.assertEqual(ks.query(self.request(status="draft"))["total"], 1)
        self.assertEqual(ks.query(self.request(status="stable"))["total"], 1)

    def test_filters_by_tags(self):
        self.assertEqual(
            ks.query(
                ks.QueryRequest(
                    project=self.project,
                    builtin=self.builtin,
                    scope="builtin",
                    tags=("ub", "overflow"),
                )
            )["total"],
            1,
        )
        self.assertEqual(
            ks.query(
                ks.QueryRequest(
                    project=self.project,
                    builtin=self.builtin,
                    scope="builtin",
                    tags=("ub", "pipeline"),
                )
            )["total"],
            0,
        )

    def test_title_hit_ranks_first(self):
        self.write_card(
            self.builtin,
            "learned",
            "other",
            description="overflow in body",
            body="overflow",
        )
        result = ks.query(self.request(text="overflow"))
        self.assertEqual(result["cards"][0]["title"], "tbuf_overflow")

    def test_limit_is_applied(self):
        result = ks.query(self.request(limit=1))
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["cards"]), 1)

    def test_body_is_not_returned(self):
        result = ks.query(self.request())
        self.assertNotIn("body", result["cards"][0])


class InitializeTest(KnowledgeTestBase):
    def test_copies_builtin_and_creates_index(self):
        self.write_card(self.builtin, "learned", "a", description="d")
        result = ks.initialize(self.project, self.builtin)
        self.assertEqual(result["status"], "ready")
        bundle = self.project_bundle
        self.assertTrue((bundle / "learned" / "a.md").is_file())
        for category in ks.CATEGORIES:
            self.assertTrue((bundle / category).is_dir())
        self.assertIn("index.md", result["copied"])
        self.assertTrue((bundle / "index.md").is_file())

    def test_does_not_overwrite_existing_card(self):
        self.write_card(self.builtin, "learned", "a", description="builtin")
        bundle = self.project_bundle
        (bundle / "learned").mkdir(parents=True)
        (bundle / "learned" / "a.md").write_text("keep me", encoding="utf-8")
        ks.initialize(self.project, self.builtin)
        self.assertEqual(
            (bundle / "learned" / "a.md").read_text(encoding="utf-8"), "keep me"
        )


class RecordTest(KnowledgeTestBase):
    def request(self, **kwargs):
        base = dict(project=self.project, title="T", description="D")
        base.update(kwargs)
        return ks.RecordRequest(**base)

    def test_writes_draft_card_and_index(self):
        result = ks.record(self.request(title="Add Mask", description="shape 对齐"))
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn('status: "draft"', text)
        self.assertIn("shape 对齐", text)
        index = (self.project_bundle / "learned" / "index.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Add Mask", index)

    def test_tags_and_platforms_are_written(self):
        # 逗号拆分发生在 CLI 层（split_csv）；这里直接传入已拆分的值
        result = ks.record(self.request(tags=("a", "b", "c"), platforms=("a2",)))
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn('tags: ["a", "b", "c"]', text)
        self.assertIn('platforms: ["a2"]', text)

    def test_duplicate_is_refused_without_force(self):
        ks.record(self.request(title="Same", slug="same"))
        with self.assertRaises(ks.KnowledgeStoreError):
            ks.record(self.request(title="Same", slug="same"))

    def test_force_overwrites(self):
        ks.record(self.request(title="Same", slug="same", body="first"))
        ks.record(self.request(title="Same", slug="same", body="second", force=True))
        text = (self.project_bundle / "learned" / "same.md").read_text(encoding="utf-8")
        self.assertIn("second", text)

    def test_body_defaults_to_description(self):
        result = ks.record(self.request(title="X", description="desc only"))
        self.assertIn("desc only", Path(result["path"]).read_text(encoding="utf-8"))

    def test_empty_title_or_description_is_rejected(self):
        with self.assertRaises(ks.KnowledgeStoreError):
            ks.record(self.request(title="   "))
        with self.assertRaises(ks.KnowledgeStoreError):
            ks.record(self.request(description=""))


class PromoteTest(KnowledgeTestBase):
    def setUp(self):
        super().setUp()
        self.card = self.write_card(
            self.project_bundle, "learned", "candidate", description="d"
        )

    def test_json_manifest(self):
        result = ks.promote(self.project, "learned/candidate.md", None, "json")
        self.assertEqual(result["status"], "review-required")
        self.assertEqual(result["suggested_target"], "knowledge/learned/candidate.md")
        self.assertFalse(result["target_exists"])
        self.assertTrue(result["checklist"])

    def test_patch_diff_against_missing_target(self):
        result = ks.promote(
            self.project, "learned/candidate.md", str(self.root / "target"), "patch"
        )
        self.assertIn("--- /dev/null", result["diff"])
        self.assertIn("+++", result["diff"])

    def test_patch_diff_against_existing_target(self):
        target = self.root / "target" / "knowledge" / "learned"
        target.mkdir(parents=True)
        (target / "candidate.md").write_text("old\n", encoding="utf-8")
        result = ks.promote(
            self.project, "learned/candidate.md", str(self.root / "target"), "patch"
        )
        self.assertTrue(result["target_exists"])
        self.assertIn("-old", result["diff"])

    def test_path_escape_is_rejected(self):
        with self.assertRaises(ks.KnowledgeStoreError):
            ks.promote(self.project, "../../etc/passwd", None, "json")

    def test_unsupported_category_is_rejected(self):
        (self.project_bundle / "misc.md").write_text("x", encoding="utf-8")
        with self.assertRaises(ks.KnowledgeStoreError):
            ks.promote(self.project, "misc.md", None, "json")

    def test_missing_card_is_rejected(self):
        with self.assertRaises(ks.KnowledgeStoreError):
            ks.promote(self.project, "learned/none.md", None, "json")


class CliTest(KnowledgeTestBase):
    def test_initialize_and_query_json(self):
        self.write_card(self.builtin, "learned", "a", description="d")
        init = self.run_cli(
            "initialize",
            "--project-root",
            str(self.project),
            "--builtin-root",
            str(self.builtin),
        )
        self.assertEqual(init.returncode, 0, init.stderr)

        query = self.run_cli(
            "query",
            "--project-root",
            str(self.project),
            "--builtin-root",
            str(self.builtin),
            "--json",
        )
        self.assertEqual(query.returncode, 0, query.stderr)
        payload = json.loads(query.stdout)
        self.assertEqual(payload["matched"], 1)

    def test_record_and_duplicate_exit_code(self):
        args = (
            "record",
            "--project-root",
            str(self.project),
            "--title",
            "Card",
            "--description",
            "desc",
        )
        first = self.run_cli(*args, "--tag", "x,y", "--tag", "z")
        self.assertEqual(first.returncode, 0, first.stderr)
        card = self.project / ".tilelang2ascendc" / "knowledge" / "learned" / "card.md"
        self.assertIn('tags: ["x", "y", "z"]', card.read_text(encoding="utf-8"))
        second = self.run_cli(*args)
        self.assertEqual(second.returncode, 2)
        self.assertIn("error:", second.stderr)

    def test_invalid_project_root_exits_two(self):
        proc = self.run_cli("query", "--project-root", str(self.root / "missing"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not a directory", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
