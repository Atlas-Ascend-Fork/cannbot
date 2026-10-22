# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
from __future__ import annotations

import csv
import importlib.util
import math
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "summarize_performance_effects.py"
SPEC = importlib.util.spec_from_file_location("performance_effects", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_performance(path: Path, rows: list[tuple[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case_id", "total_us"])
        writer.writerows(rows)


class PerformanceJitterSummaryTest(unittest.TestCase):
    def assert_classifications(self, cases, expected):
        for case_id, classification in expected.items():
            self.assertEqual(cases[case_id]["classification"], classification)

    def assert_thresholds(self, cases, expected):
        for case_id, value in expected.items():
            self.assertEqual(cases[case_id]["threshold_value"], value)

    def write_piecewise_pair(self, root):
        baseline = root / "baseline.csv"
        candidate = root / "candidate.csv"
        write_performance(baseline, [
            ("micro_boundary", 5.0), ("micro_effective", 4.0),
            ("short_boundary", 20.0), ("short_effective", 10.0),
            ("medium_boundary", 100.0), ("medium_effective", 40.0),
            ("long_floor_boundary", 200.0), ("long_relative_boundary", 1000.0),
            ("long_effective", 1000.0),
        ])
        write_performance(candidate, [
            ("micro_boundary", 5.25), ("micro_effective", 3.0),
            ("short_boundary", 20.5), ("short_effective", 8.0),
            ("medium_boundary", 103.0), ("medium_effective", 30.0),
            ("long_floor_boundary", 203.0), ("long_relative_boundary", 1010.0),
            ("long_effective", 1100.0),
        ])
        return baseline, candidate

    def test_piecewise_boundaries_and_effective_geomean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, candidate = self.write_piecewise_pair(root)
            result = MODULE.summarize(baseline, candidate)
            cases = {case["case_id"]: case for case in result["cases"]}
            self.assert_classifications(cases, {
                "micro_boundary": "jitter_no_effect",
                "micro_effective": "effective_improvement",
                "short_boundary": "jitter_no_effect",
                "short_effective": "effective_improvement",
                "medium_boundary": "jitter_no_effect",
                "medium_effective": "effective_improvement",
                "long_floor_boundary": "jitter_no_effect",
                "long_relative_boundary": "jitter_no_effect",
                "long_effective": "effective_regression",
            })
            self.assert_thresholds(cases, {
                "micro_boundary": 0.25,
                "short_boundary": 0.5,
                "medium_boundary": 3.0,
                "long_floor_boundary": 3.0,
                "long_relative_boundary": 10.0,
            })
            self.assertEqual(result["jitter_case_count"], 5)
            self.assertEqual(result["effective_case_count"], 4)
            self.assertEqual(result["effective_improvement_count"], 3)
            self.assertEqual(result["effective_regression_count"], 1)
            expected = math.exp(
                (
                    math.log(4.0 / 3.0)
                    + math.log(1.25)
                    + math.log(4.0 / 3.0)
                    + math.log(1.0 / 1.1)
                )
                / 4
            )
            self.assertAlmostEqual(result["effective_geomean_speedup"], expected)
            self.assertNotIn("full_geomean_speedup", result)

    def write_standard_pair(self, root, candidate_rows):
        baseline = root / "baseline.csv"
        candidate = root / "candidate.csv"
        write_performance(
            baseline,
            [("a", 5.0), ("b", 20.0), ("c", 100.0), ("d", 200.0)],
        )
        write_performance(candidate, candidate_rows)
        return baseline, candidate

    def test_regressions_within_jitter_report_null_geomean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, candidate = self.write_standard_pair(
                root, [("a", 5.25), ("b", 20.5), ("c", 103.0), ("d", 203.0)]
            )
            result = MODULE.summarize(baseline, candidate)
            self.assertEqual(result["effective_case_count"], 0)
            self.assertIsNone(result["effective_geomean_speedup"])

    def test_improvements_bypass_jitter_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, candidate = self.write_standard_pair(
                root, [("a", 4.9), ("b", 19.5), ("c", 97.0), ("d", 197.0)]
            )
            result = MODULE.summarize(baseline, candidate)
            self.assertEqual(result["effective_case_count"], 4)
            self.assertEqual(result["effective_improvement_count"], 4)
            self.assertEqual(result["effective_regression_count"], 0)
            self.assertEqual(result["jitter_case_count"], 0)
            self.assertGreater(result["effective_geomean_speedup"], 1.0)
            self.assertTrue(
                all(
                    case["classification"] == "effective_improvement"
                    for case in result["cases"]
                )
            )

    def test_prediction_and_target_are_not_candidate_rejection_thresholds(self) -> None:
        analysis = (
            ROOT
            / "skills/ops-perf-analysis/references/analysis-execution.md"
        ).read_text(encoding="utf-8")
        selection = (
            ROOT
            / "skills/ops-perf-implementation/references/selection-and-final.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("则弃", analysis)
        self.assertNotIn('"abandon_if"', analysis)
        self.assertIn("不得新增 `abandon_if`", analysis)
        self.assertIn("不参与候选选择", analysis)
        self.assertIn("整体目标未达不等于候选落选", selection)
        self.assertIn("提升不按抖动过滤", selection)

    def test_case_set_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.csv"
            candidate = root / "candidate.csv"
            write_performance(baseline, [("a", 10.0)])
            write_performance(candidate, [("b", 10.0)])
            with self.assertRaisesRegex(ValueError, "case set mismatch"):
                MODULE.summarize(baseline, candidate)


if __name__ == "__main__":
    unittest.main()
