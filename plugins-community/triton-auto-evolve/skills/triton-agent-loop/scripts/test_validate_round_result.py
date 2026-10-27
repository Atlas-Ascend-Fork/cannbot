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
"""validate_round_result.py 迭代自洽检查回归测试（python3 -m unittest test_validate_round_result -v）。

通过 CLI 公共入口驱动（不触碰模块私有成员），断言 verdict JSON 中
iterations_consistent 项的状态：best_speedup 虚高（iterations 全部低于
自报值）标 suspicious、低于最小值标 suspicious、范围内 pass、
浮点容差边界、缺数据兜底。纯标准库，可在无 NPU 环境运行。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "validate_round_result.py"


def make_result(speeds, best):
    """构造仅含 iterations/best_speedup 的最小 round_result。"""
    return {
        "iterations": [{"round": i + 1, "speedup": s} for i, s in enumerate(speeds)],
        "best_speedup": best,
    }


def run_validate(round_result):
    """调用 CLI 并解析 verdict JSON（其他检查项拒收不影响本项断言）。"""
    with tempfile.TemporaryDirectory() as tmp:
        rr_path = Path(tmp) / "round_result.json"
        rr_path.write_text(json.dumps(round_result, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--round-result", str(rr_path)],
            capture_output=True, text=True, check=False,
        )
    return json.loads(proc.stdout)


def iterations_check(verdict):
    """取 verdict 中 iterations_consistent 检查项。"""
    return next(c for c in verdict["checks"] if c["name"] == "iterations_consistent")


class TestIterationsConsistent(unittest.TestCase):
    def test_inflated_best_flagged(self):
        """评审回归用例：iterations 全为 1.0/1.1，自报 best=2.9 必须标 suspicious。"""
        verdict = run_validate(make_result([1.0, 1.1], 2.9))
        check = iterations_check(verdict)
        self.assertEqual(check["status"], "suspicious")
        self.assertIn("大于 iterations 最大值", check["detail"])
        self.assertIn("iterations_consistent", verdict["suspicious"])

    def test_deflated_best_flagged(self):
        verdict = run_validate(make_result([1.0, 1.1], 0.5))
        check = iterations_check(verdict)
        self.assertEqual(check["status"], "suspicious")
        self.assertIn("小于 iterations 最小值", check["detail"])

    def test_best_at_max_passes(self):
        verdict = run_validate(make_result([1.0, 1.1, 1.05], 1.1))
        check = iterations_check(verdict)
        self.assertEqual(check["status"], "pass")
        self.assertIn("自洽", check["detail"])

    def test_float_epsilon_tolerance(self):
        """best 与最大值差在 1e-9 容差内不误报。"""
        verdict = run_validate(make_result([1.0, 1.1], 1.1 + 5e-10))
        self.assertEqual(iterations_check(verdict)["status"], "pass")

    def test_missing_speeds_suspicious(self):
        verdict = run_validate({"iterations": [], "best_speedup": 1.2})
        self.assertEqual(iterations_check(verdict)["status"], "suspicious")

    def test_non_numeric_best_suspicious(self):
        verdict = run_validate(make_result([1.0], "2.9"))
        self.assertEqual(iterations_check(verdict)["status"], "suspicious")


if __name__ == "__main__":
    unittest.main()
