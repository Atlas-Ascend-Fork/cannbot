# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""prepare_case.py --verify staged 模式入口 (预置用例核对) 黑盒 CLI 测试。

fixture：临时 work_dir + 调用方预写的 custom/<op>/ 三产物；覆盖
合成 prepared_case.json (mode=staged)、缺失产物逐项报错、--op-dir 显式
指定、算子名 --op-name 优先与目录名兜底 (不解析 REQUIRE.md front matter)、
custom/ 自动探测对 .bak/隐藏目录的过滤、幂等复核 (prepared_case.json
已存在时纯校验)。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from require_fixture import PREPARE_SCRIPT, REQUIRE_CONTENT

TASK_DESC_CONTENT = "def get_inputs():\n    return []\n"
GEN_PROMPT_CONTENT = "# 用例事实与桥接契约: relu\n"


class StagedVerifyTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="staged-verify-test-")
        self.addCleanup(temporary.cleanup)
        self.work_dir = Path(temporary.name)
        self.op_dir = self.work_dir / "custom" / "relu"
        self.op_dir.mkdir(parents=True)

    def test_staged_synthesizes_prepared_case(self):
        self._prewrite()
        r = self._verify("--device-id", "3", "--perf-target-us", "12.5")
        self.assertEqual(r.returncode, 0, r.stderr)
        prepared = self._prepared()
        self.assertEqual(prepared["mode"], "staged")
        self.assertEqual(prepared["op"], "relu")
        self.assertEqual(prepared["op_dir"], str(self.op_dir))
        self.assertEqual(prepared["require"], str(self.op_dir / "REQUIRE.md"))
        self.assertEqual(prepared["task_desc"], str(self.op_dir / "task_desc.py"))
        self.assertEqual(prepared["gen_prompt"], str(self.op_dir / "gen_prompt.md"))
        self.assertEqual(prepared["device_id"], 3)
        self.assertEqual(prepared["perf_target_us"], 12.5)
        self.assertEqual(prepared["tune_rounds"], 3)
        # stdout 契约输出与 prepared_case.json 一致
        self.assertEqual(json.loads(r.stdout), prepared)

    def test_staged_explicit_op_dir(self):
        self._prewrite()
        r = self._verify("--op-dir", str(self.op_dir))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._prepared()["mode"], "staged")

    def test_staged_op_name_cli_overrides_dir_name(self):
        self._prewrite()
        r = self._verify("--op-name", "relu_v2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._prepared()["op"], "relu_v2")

    def test_staged_op_name_dir_fallback_ignores_front_matter(self):
        # 脚本不解析 REQUIRE.md: front matter 声明别的 op_name 也不生效,
        # 缺省取目录名
        self._prewrite()
        (self.op_dir / "REQUIRE.md").write_text(
            REQUIRE_CONTENT.replace("op_name: relu", "op_name: sigmoid"),
            encoding="utf-8",
        )
        r = self._verify()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._prepared()["op"], "relu")

    def test_staged_invalid_dir_name_fails(self):
        bad_dir = self.work_dir / "custom" / "19relu!"
        bad_dir.mkdir(parents=True)
        for name, content in (
            ("REQUIRE.md", REQUIRE_CONTENT),
            ("task_desc.py", TASK_DESC_CONTENT),
            ("gen_prompt.md", GEN_PROMPT_CONTENT),
        ):
            (bad_dir / name).write_text(content, encoding="utf-8")
        r = self._verify()
        self.assertEqual(r.returncode, 2)
        self.assertIn("--op-name", r.stderr)

    def test_staged_invalid_dir_name_rescued_by_cli_op_name(self):
        bad_dir = self.work_dir / "custom" / "19relu!"
        bad_dir.mkdir(parents=True)
        for name, content in (
            ("REQUIRE.md", REQUIRE_CONTENT),
            ("task_desc.py", TASK_DESC_CONTENT),
            ("gen_prompt.md", GEN_PROMPT_CONTENT),
        ):
            (bad_dir / name).write_text(content, encoding="utf-8")
        r = self._verify("--op-dir", str(bad_dir), "--op-name", "relu")
        self.assertEqual(r.returncode, 0, r.stderr)
        prepared = self._prepared()
        self.assertEqual(prepared["op"], "relu")
        self.assertEqual(prepared["op_dir"], str(bad_dir.resolve()))

    def test_staged_probe_ignores_bak_and_hidden_dirs(self):
        self._prewrite()
        # .bak 归档目录与隐藏目录即便含 REQUIRE.md 也不得干扰自动探测
        for name in ("relu.bak", ".archive"):
            shadow = self.work_dir / "custom" / name
            shadow.mkdir()
            (shadow / "REQUIRE.md").write_text(REQUIRE_CONTENT, encoding="utf-8")
        r = self._verify()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._prepared()["op"], "relu")

    def test_staged_missing_gen_prompt_fails(self):
        self._prewrite(gen_prompt=False)
        r = self._verify()
        self.assertEqual(r.returncode, 1)
        self.assertIn("gen_prompt.md", r.stderr)
        self.assertFalse((self.work_dir / "prepared_case.json").exists())

    def test_staged_missing_task_desc_fails(self):
        self._prewrite(task_desc=False)
        r = self._verify()
        self.assertEqual(r.returncode, 1)
        self.assertIn("task_desc.py", r.stderr)

    def test_staged_empty_artifact_fails(self):
        self._prewrite()
        (self.op_dir / "task_desc.py").write_text("", encoding="utf-8")
        r = self._verify()
        self.assertEqual(r.returncode, 1)
        self.assertIn("task_desc.py", r.stderr)

    def test_staged_no_prewrite_fails(self):
        r = self._verify()
        self.assertEqual(r.returncode, 2)
        self.assertFalse((self.work_dir / "prepared_case.json").exists())

    def test_staged_idempotent_reverify(self):
        self._prewrite()
        r1 = self._verify()
        self.assertEqual(r1.returncode, 0, r1.stderr)
        # prepared_case.json 已存在: --verify 退化为纯复核, 不重复合成
        for _ in range(2):
            r = self._verify()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["status"], "ok")

    def test_staged_reverify_detects_deleted_artifact(self):
        self._prewrite()
        r1 = self._verify()
        self.assertEqual(r1.returncode, 0, r1.stderr)
        (self.op_dir / "gen_prompt.md").unlink()
        r = self._verify()
        self.assertEqual(r.returncode, 1)
        self.assertIn("gen_prompt", r.stderr)

    def _run(self, *argv):
        return subprocess.run(
            [sys.executable, str(PREPARE_SCRIPT), *argv],
            capture_output=True,
            text=True,
        )

    def _verify(self, *extra):
        return self._run("--verify", "--work-dir", str(self.work_dir), *extra)

    def _prewrite(self, require=True, task_desc=True, gen_prompt=True):
        if require:
            (self.op_dir / "REQUIRE.md").write_text(REQUIRE_CONTENT, encoding="utf-8")
        if task_desc:
            (self.op_dir / "task_desc.py").write_text(
                TASK_DESC_CONTENT, encoding="utf-8"
            )
        if gen_prompt:
            (self.op_dir / "gen_prompt.md").write_text(
                GEN_PROMPT_CONTENT, encoding="utf-8"
            )

    def _prepared(self):
        return json.loads(
            (self.work_dir / "prepared_case.json").read_text(encoding="utf-8")
        )


class FromRequireTest(unittest.TestCase):
    """--from-require (interactive): 算子名 --op-name 优先, 目录名兜底, 不解析 REQUIRE.md."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="from-require-test-")
        self.addCleanup(temporary.cleanup)
        self.work_dir = Path(temporary.name)
        self.op_dir = self.work_dir / "custom" / "relu"
        self.op_dir.mkdir(parents=True)
        (self.op_dir / "REQUIRE.md").write_text(REQUIRE_CONTENT, encoding="utf-8")

    def test_from_require_dir_name_fallback(self):
        r = self._run(
            "--from-require",
            str(self.op_dir / "REQUIRE.md"),
            "--work-dir",
            str(self.work_dir),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        prepared = self._prepared()
        self.assertEqual(prepared["op"], "relu")
        self.assertEqual(prepared["mode"], "interactive")

    def test_from_require_op_name_cli_overrides_dir_name(self):
        r = self._run(
            "--from-require",
            str(self.op_dir / "REQUIRE.md"),
            "--work-dir",
            str(self.work_dir),
            "--op-name",
            "relu_v2",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._prepared()["op"], "relu_v2")

    def _run(self, *argv):
        return subprocess.run(
            [sys.executable, str(PREPARE_SCRIPT), *argv],
            capture_output=True,
            text=True,
        )

    def _prepared(self):
        return json.loads(
            (self.work_dir / "prepared_case.json").read_text(encoding="utf-8")
        )


if __name__ == "__main__":
    unittest.main()
