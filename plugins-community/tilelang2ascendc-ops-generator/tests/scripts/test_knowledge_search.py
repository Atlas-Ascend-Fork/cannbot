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
"""scripts/knowledge_search.sh 的 UT。

用假的 knowledge-query 覆盖：参数校验、知识不可用降级、检索结果格式化、
去重与限流、allow-unlocated 二次检索。

运行：python3 tests/scripts/test_knowledge_search.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from runtime import BASH  # noqa: E402


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PLUGIN_ROOT / "scripts" / "knowledge_search.sh"

FAKE_QUERY = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(args) + "\\n")

if args and args[-1] == "discover":
    sys.exit(0)

hits_file = os.environ.get("FAKE_HITS")
hits = json.loads(Path(hits_file).read_text()) if hits_file else []

counter_file = os.environ.get("FAKE_COUNTER")
index = 0
if counter_file:
    index = int(Path(counter_file).read_text()) if Path(counter_file).exists() else 0
    Path(counter_file).write_text(str(index + 1))
if hits and isinstance(hits[0], list):
    hits = hits[min(index, len(hits) - 1)]

sys.stdout.write(json.dumps({"hits": hits}) + "\\n")
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""


class SearchTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="t2a-search-")
        self.root = Path(self._tmp.name)
        self.knowledge = self.root / "knowledge"
        self.project = self.root / "project"
        self.project.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.log = self.root / "argv.log"

    def tearDown(self):
        self._tmp.cleanup()

    def install_fake_query(self):
        scripts = self.knowledge / ".agents" / "skills" / "knowledge-query" / "scripts"
        scripts.mkdir(parents=True)
        path = scripts / "knowledge_query.py"
        path.write_text(FAKE_QUERY, encoding="utf-8")
        return path

    def write_registry(self, platforms=("ascend910b",)):
        path = self.knowledge / "governance" / "schemas" / "registries.yaml"
        path.parent.mkdir(parents=True)
        lines = ["platforms:"]
        for platform in platforms:
            lines.append(f"  {platform}:")
            lines.append("    vendor: ascend")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def env(self, **extra):
        env = os.environ.copy()
        for key in (
            "CANNBOT_KNOWLEDGE_ROOT",
            "CANNBOT_KNOWLEDGE_PLATFORM",
            "KNOWLEDGE_ROOT",
        ):
            env.pop(key, None)
        env["HOME"] = str(self.home)
        env["FAKE_LOG"] = str(self.log)
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_search(self, *args, env=None):
        return subprocess.run(
            [BASH, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env=env or self.env(),
            timeout=60,
            shell=False,
        )

    def search_args(self, *extra):
        return [
            "--query",
            "gm_to_ub",
            "--profile",
            "runbooks",
            "--knowledge-root",
            str(self.knowledge),
            "--platform",
            "ascend910b",
            "--project-root",
            str(self.project),
            *extra,
        ]

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]


class ArgumentTest(SearchTestBase):
    def test_help(self):
        proc = self.run_search("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage:", proc.stdout)

    def test_missing_required_arguments(self):
        proc = self.run_search("--query", "x")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Usage:", proc.stderr)

    def test_unknown_argument(self):
        proc = self.run_search("--bogus")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown argument", proc.stderr)

    def test_invalid_match(self):
        proc = self.run_search(*self.search_args("--match", "fuzzy"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--match must be text or literal", proc.stderr)

    def test_invalid_limit(self):
        proc = self.run_search(*self.search_args("-k", "abc"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--limit must be a positive integer", proc.stderr)

    def test_limit_above_five_is_clamped(self):
        self.install_fake_query()
        self.write_registry()
        proc = self.run_search(*self.search_args("-k", "9"), env=self.env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        search_calls = [call for call in self.calls() if "search" in call]
        self.assertEqual(search_calls[-1][search_calls[-1].index("-k") + 1], "5")


class UnavailableTest(SearchTestBase):
    def test_no_knowledge_root(self):
        proc = self.run_search(
            "--query",
            "x",
            "--profile",
            "runbooks",
            "--project-root",
            str(self.project),
            env=self.env(),
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("unavailable (no knowledge root)", proc.stdout)

    def test_missing_knowledge_query(self):
        self.knowledge.mkdir()
        proc = self.run_search(*self.search_args(), env=self.env())
        self.assertEqual(proc.returncode, 0)
        self.assertIn("unavailable (knowledge-query missing)", proc.stdout)

    def test_unknown_platform(self):
        self.install_fake_query()
        self.write_registry(platforms=("ascend950",))
        proc = self.run_search(*self.search_args(), env=self.env())
        self.assertEqual(proc.returncode, 0)
        self.assertIn("unavailable (unknown platform: ascend910b)", proc.stdout)

    def test_search_failure_degrades(self):
        self.install_fake_query()
        self.write_registry()
        hits = self.root / "hits.json"
        hits.write_text("[]", encoding="utf-8")
        proc = self.run_search(
            *self.search_args(),
            env=self.env(FAKE_HITS=hits, FAKE_RC=1),
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("unavailable (search failed)", proc.stdout)


class ResultFormatTest(SearchTestBase):
    def setUp(self):
        super().setUp()
        self.install_fake_query()
        self.write_registry()
        self.hits = self.root / "hits.json"

    def write_hits(self, hits):
        self.hits.write_text(json.dumps(hits), encoding="utf-8")

    def test_formats_hits_and_summary(self):
        self.write_hits(
            [
                {"path": "a.md", "title": "A", "description": "desc a"},
                {"path": "b.md", "title": "B", "description": ""},
            ]
        )
        proc = self.run_search(*self.search_args(), env=self.env(FAKE_HITS=self.hits))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("- a.md — A", proc.stdout)
        self.assertIn("  desc a", proc.stdout)
        self.assertIn("- b.md — B", proc.stdout)
        self.assertIn("knowledge: hits=2 profile=runbooks", proc.stdout)

    def test_duplicate_paths_are_shown_once(self):
        self.write_hits(
            [
                {"path": "a.md", "title": "A", "description": ""},
                {"path": "a.md", "title": "A again", "description": ""},
            ]
        )
        proc = self.run_search(*self.search_args(), env=self.env(FAKE_HITS=self.hits))
        self.assertEqual(proc.stdout.count("- a.md"), 1)
        self.assertIn("hits=2", proc.stdout)

    def test_limit_is_applied_to_output(self):
        self.write_hits(
            [{"path": f"{i}.md", "title": str(i), "description": ""} for i in range(3)]
        )
        proc = self.run_search(
            *self.search_args("-k", "2"), env=self.env(FAKE_HITS=self.hits)
        )
        self.assertEqual(proc.stdout.count(".md — "), 2)

    def test_no_hits_message(self):
        self.write_hits([])
        proc = self.run_search(*self.search_args(), env=self.env(FAKE_HITS=self.hits))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("knowledge: no-hit profile=runbooks", proc.stdout)

    def test_allow_unlocated_second_pass(self):
        # 第一次 search 无命中，第二次（include-unlocated）命中一张无 platforms 的卡
        self.write_hits(
            [
                [],
                [{"path": "c.md", "title": "C", "description": "unlocated"}],
            ]
        )
        counter = self.root / "counter.txt"
        proc = self.run_search(
            *self.search_args("--allow-unlocated"),
            env=self.env(FAKE_HITS=self.hits, FAKE_COUNTER=counter),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("platform-unverified", proc.stdout)
        self.assertIn("- c.md — C", proc.stdout)

        search_calls = [call for call in self.calls() if "search" in call]
        self.assertEqual(len(search_calls), 2)
        self.assertIn("--include-unlocated", search_calls[1])
        self.assertIn("all", search_calls[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
