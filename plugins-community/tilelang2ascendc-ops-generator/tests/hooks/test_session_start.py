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
"""hooks/session-start-tilelang2ascendc-ops-generator 的 UT。

覆盖：启动提示、D 类门禁横幅的恢复展示、无状态文件时的静默行为。
运行：python3 tests/hooks/test_session_start.py
"""

import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from hook_sandbox import HookSandbox  # noqa: E402


class SessionStartTest(unittest.TestCase):
    def setUp(self):
        self.sandbox = HookSandbox()
        self.addCleanup(self.sandbox.cleanup)
        self.gate_file = (
            self.sandbox.root / ".claude" / "hooks" / "state" / "precision_gate.json"
        )

    def write_gate(self, state):
        self.gate_file.parent.mkdir(parents=True, exist_ok=True)
        self.gate_file.write_text(json.dumps(state), encoding="utf-8")

    def run_hook(self):
        proc = self.sandbox.run_session_start()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_prints_session_header(self):
        self.assertIn(
            "[tilelang2ascendc-ops-generator] Session started.", self.run_hook()
        )

    def test_no_banner_without_state_file(self):
        output = self.run_hook()
        self.assertNotIn("Precision Gate", output)

    def test_no_banner_when_gate_inactive(self):
        self.write_gate({"d_class_active": False})
        self.assertNotIn("Precision Gate", self.run_hook())

    def test_banner_reports_pending_d_class(self):
        self.write_gate(
            {
                "d_class_active": True,
                "output_dir": "/proj/out/42_Matmul",
                "stage": "D2",
                "debug_call_count": 7,
                "tune_call_count": 2,
            }
        )
        output = self.run_hook()
        self.assertIn("Precision Gate", output)
        self.assertIn("/proj/out/42_Matmul", output)
        self.assertIn("D2", output)
        self.assertIn("debug=7", output)
        self.assertIn("tune=2", output)
        self.assertIn("total=9/12", output)

    def test_invalid_state_file_does_not_break_start(self):
        self.gate_file.parent.mkdir(parents=True, exist_ok=True)
        self.gate_file.write_text("not json", encoding="utf-8")
        self.assertIn(
            "[tilelang2ascendc-ops-generator] Session started.", self.run_hook()
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
