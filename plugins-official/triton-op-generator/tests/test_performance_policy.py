# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

import importlib.util
from itertools import product
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / "workflows/evaluate_performance.py"
spec = importlib.util.spec_from_file_location("evaluate_performance", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def report(values):
    return {
        "total_cases": len(values),
        "passed_cases": len(values),
        "failed_cases": 0,
        "per_shape_results": [
            {
                "case_idx": i + 1,
                "status": "pass",
                "speedup_vs_torch": v,
                "framework": {"avg_latency_ms": v},
                "implementation": {"avg_latency_ms": 1.0},
            }
            for i, v in enumerate(values)
        ],
    }


class PolicyTests(unittest.TestCase):
    def test_each_case_cannot_hide_regression(self):
        data = report([0.5, 2.0])
        self.assertTrue(module.evaluate(data, 1.0, "geometric_mean")["target_reached"])
        result = module.evaluate(data, 1.0, "each_required_case")
        self.assertFalse(result["target_reached"])
        self.assertEqual(result["decision_metric"], 0.5)

    def test_both_cases_reach(self):
        self.assertTrue(
            module.evaluate(report([1.0, 1.1]), 1.0, "each_required_case")["target_reached"]
        )

    def test_rounded_display_cannot_pass_parity(self):
        data = report([1.0])
        data["per_shape_results"][0]["framework"]["avg_latency_ms"] = 0.999999
        self.assertFalse(module.evaluate(data, 1.0, "each_required_case")["target_reached"])

    def test_invalid_required_case_cannot_be_dropped(self):
        for value in [None, float("nan"), float("inf"), 0, -1, True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.evaluate(report([1.0, value]), 1.0, "each_required_case")

    def test_missing_or_failed_case(self):
        data = report([2.0, 2.0])
        data["total_cases"] = 3
        with self.assertRaises(ValueError):
            module.evaluate(data, 1.0)
        data = report([2.0, 2.0])
        data["per_shape_results"][1]["status"] = "fail"
        with self.assertRaises(ValueError):
            module.evaluate(data, 1.0)

    def test_unique_case_ids(self):
        data = report([2.0, 2.0])
        data["per_shape_results"][1]["case_idx"] = 1
        with self.assertRaises(ValueError):
            module.evaluate(data, 1.0)

    def test_target_validation(self):
        for target in [0, -1, math.inf, math.nan]:
            with self.assertRaises(ValueError):
                module.evaluate(report([2.0]), target)

    def test_invalid_measured_latency(self):
        kinds = ("framework", "implementation")
        invalid_values = [None, True, "1", 0, -1, math.inf, math.nan]
        for kind, value in product(kinds, invalid_values):
            with self.subTest(kind=kind, value=value):
                data = report([2.0])
                data["per_shape_results"][0][kind]["avg_latency_ms"] = value
                with self.assertRaisesRegex(ValueError, "invalid measured latency"):
                    module.evaluate(data, 1.0)

    def test_failed_summary_and_empty_report(self):
        data = report([2.0])
        data["failed_cases"] = 1
        with self.assertRaisesRegex(ValueError, "failed required cases"):
            module.evaluate(data, 1.0)
        with self.assertRaisesRegex(ValueError, "all required cases"):
            module.evaluate(report([]), 1.0)

    def test_unknown_policy_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown target_policy"):
            module.evaluate(report([2.0]), 1.0, "unknown")

    def test_cli_json_output_and_validation_error(self):
        with tempfile.TemporaryDirectory() as task_dir:
            perf_path = Path(task_dir) / "perf_result.json"
            perf_path.write_text(json.dumps(report([0.5, 2.0])), encoding="utf-8")
            command = [
                sys.executable, str(path), "--perf-result", str(perf_path),
                "--target-speedup", "1", "--target-policy", "each_required_case",
            ]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertTrue(result.stdout.endswith("\n"))
            self.assertFalse(json.loads(result.stdout)["target_reached"])
            perf_path.write_text("{}", encoding="utf-8")
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("all required cases", result.stderr)


if __name__ == "__main__":
    unittest.main()
