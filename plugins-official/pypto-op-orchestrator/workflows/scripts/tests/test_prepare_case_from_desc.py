# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""prepare_case.py --from-desc (无 golden 纯提示词触发) 黑盒 CLI 测试。

fixture：临时 work_dir；覆盖落盘结构封装/逐字落盘、算子名经 --op-name
显式传入（脚本不解析需求文本）、幂等 (--verify 与重复执行)、冲突保护与
prepared_case.json 契约字段。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from require_fixture import PREPARE_SCRIPT, REQUIRE_CONTENT

RAW_DESC = "实现一个 relu 算子, out[i] = max(x[i], 0), 输入 float32"

STRUCTURED_DESC = REQUIRE_CONTENT


class FromDescTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="from-desc-test-")
        self.addCleanup(temporary.cleanup)
        self.work_dir = Path(temporary.name)

    def test_unstructured_desc_is_wrapped_with_template(self):
        r = self._run_from_desc(RAW_DESC, "--op-name", "relu")
        self.assertEqual(r.returncode, 0, r.stderr)
        content = self._require_path().read_text(encoding="utf-8")
        # 按 require_template.md 包一层: front matter + 必备三节 + 原文保留
        self.assertIn("op_name: relu", content)
        self.assertIn("## 算子语义", content)
        self.assertIn("## 输入输出规格", content)
        self.assertIn("## 精度要求", content)
        self.assertIn("## 原始需求描述", content)
        self.assertIn(RAW_DESC, content)
        # 模板头部填写说明注释不落进产物
        self.assertNotIn("<!--", content)

    def test_structured_desc_written_verbatim(self):
        r = self._run_from_desc(STRUCTURED_DESC, "--op-name", "relu")
        self.assertEqual(r.returncode, 0, r.stderr)
        content = self._require_path().read_text(encoding="utf-8")
        self.assertEqual(content, STRUCTURED_DESC.strip() + "\n")

    def test_prepared_case_json_interactive_contract(self):
        r = self._run_from_desc(RAW_DESC, "--op-name", "relu", "--device-id", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        prepared = self._prepared()
        self.assertEqual(prepared["mode"], "interactive")
        self.assertIsNone(prepared["task_desc"])
        self.assertEqual(prepared["op"], "relu")
        self.assertEqual(prepared["device_id"], 2)
        self.assertEqual(prepared["tune_rounds"], 3)
        self.assertEqual(prepared["require"], str(self._require_path()))
        # stdout 契约输出与 prepared_case.json 一致
        self.assertEqual(json.loads(r.stdout), prepared)

    def test_front_matter_op_name_not_parsed(self):
        # 脚本不解析需求文本: 文本 front matter 的 op_name 字段被忽略,
        # 算子名只认 --op-name
        r = self._run_from_desc(
            "---\nop_name: sigmoid\n---\n逐元素 sigmoid", "--op-name", "relu"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self._require_path("relu").is_file())
        self.assertFalse(self._require_path("sigmoid").exists())

    def test_missing_op_name_fails(self):
        # 即使文本 front matter 含 op_name 字段也不解析, 缺 --op-name 即报错
        r = self._run_from_desc(RAW_DESC)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--op-name", r.stderr)
        self.assertFalse(self._require_path().exists())
        r2 = self._run_from_desc("---\nop_name: sigmoid\n---\n逐元素 sigmoid")
        self.assertEqual(r2.returncode, 2)
        self.assertIn("--op-name", r2.stderr)

    def test_invalid_op_name_fails(self):
        r = self._run_from_desc(RAW_DESC, "--op-name", "19relu!")
        self.assertEqual(r.returncode, 2)

    def test_desc_from_file_path(self):
        desc_file = self.work_dir / "desc.md"
        desc_file.write_text(RAW_DESC, encoding="utf-8")
        r = self._run_from_desc(str(desc_file), "--op-name", "relu")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(RAW_DESC, self._require_path().read_text(encoding="utf-8"))

    def test_idempotent_rerun_and_verify(self):
        r1 = self._run_from_desc(RAW_DESC, "--op-name", "relu")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        first = self._require_path().read_text(encoding="utf-8")
        r2 = self._run_from_desc(RAW_DESC, "--op-name", "relu")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertEqual(self._require_path().read_text(encoding="utf-8"), first)
        for _ in range(2):
            v = self._run("--verify", "--work-dir", str(self.work_dir))
            self.assertEqual(v.returncode, 0, v.stderr)
            self.assertEqual(json.loads(v.stdout)["status"], "ok")

    def test_conflicting_existing_require_fails(self):
        r1 = self._run_from_desc(RAW_DESC, "--op-name", "relu")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        r2 = self._run_from_desc("完全不同的另一份需求", "--op-name", "relu")
        self.assertEqual(r2.returncode, 2)
        # 已有 REQUIRE.md 不被覆盖
        self.assertIn(RAW_DESC, self._require_path().read_text(encoding="utf-8"))

    def _run(self, *argv):
        return subprocess.run(
            [sys.executable, str(PREPARE_SCRIPT), *argv],
            capture_output=True,
            text=True,
        )

    def _run_from_desc(self, desc, *extra):
        return self._run("--from-desc", desc, "--work-dir", str(self.work_dir), *extra)

    def _require_path(self, op="relu"):
        return self.work_dir / "custom" / op / "REQUIRE.md"

    def _prepared(self):
        return json.loads(
            (self.work_dir / "prepared_case.json").read_text(encoding="utf-8")
        )


if __name__ == "__main__":
    unittest.main()
