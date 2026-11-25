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
"""init.sh 参数解析的 UT（只覆盖解析阶段的成功/失败路径，不触发实际安装）。

运行：python3 tests/install/test_init_args.py
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from runtime import BASH  # noqa: E402


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
INIT = PLUGIN_ROOT / "init.sh"


class InitArgsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="t2a-init-")
        self.home = Path(self._tmp.name) / "home"
        self.home.mkdir()
        self.addCleanup(self._tmp.cleanup)

    def run_init(self, *args):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        return subprocess.run(
            [BASH, str(INIT), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            shell=False,
        )

    def test_help(self):
        proc = self.run_init("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage: init.sh", proc.stdout)
        self.assertIn("--knowledge-root", proc.stdout)

    def test_unknown_option(self):
        proc = self.run_init("--bogus")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Unknown option", proc.stdout)

    def test_target_requires_value(self):
        proc = self.run_init("--target")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--target requires a directory", proc.stdout)

    def test_duplicate_target_is_rejected(self):
        proc = self.run_init("project", "claude", "/tmp/a", "/tmp/b")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unexpected extra argument", proc.stdout)

    def test_no_knowledge_conflicts_with_knowledge_root(self):
        proc = self.run_init(
            "--no-knowledge", "--knowledge-root", str(self.home / "knowledge")
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("cannot be combined", proc.stdout)

    def test_knowledge_platform_requires_value(self):
        proc = self.run_init("--knowledge-platform")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--knowledge-platform requires a value", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
