#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""Host tests for actual profiling CSV discovery and duration parsing."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dashboard_parsers import extract_profiling_time


class TestProfilingCsv(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)

    def write_csv(self, name, rows, quoting=csv.QUOTE_MINIMAL):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle, quoting=quoting).writerows(rows)
        return path

    def test_quoted_shapes_before_duration(self):
        self.write_csv(
            "op_summary_shapes.csv",
            [["Input Shapes", "Task Duration(us)"], ["2,3", "12.5"], ["4,5", "7.5"]],
        )
        self.assertEqual(extract_profiling_time(self.root), 20.0)

    def test_quoted_headers_and_durations(self):
        self.write_csv(
            "op_summary_quoted.csv",
            [["Op Name", "Task Duration(us)"], ["Add", "25"], ["Mul", "7.5"]],
            quoting=csv.QUOTE_ALL,
        )
        self.assertEqual(extract_profiling_time(self.root), 32.5)

    def test_escaped_quotes_and_commas_in_op_name(self):
        self.write_csv(
            "op_summary_names.csv",
            [["Op Name", "Duration(us)"], ['custom,"phase"', "11"], ["other,op", "12"]],
        )
        self.assertEqual(extract_profiling_time(self.root), 23.0)

    def test_existing_comments_blanks_and_invalid_rows(self):
        (self.root / "op_summary_legacy.csv").write_text(
            "# profiler metadata\n\nOp Name, Task Duration(us) \n"
            "Add, 2.5 \n# comment,999\nMul,4\nBad,invalid\nShort\n\n",
            encoding="utf-8",
        )
        self.assertEqual(extract_profiling_time(self.root), 6.5)

    def test_missing_duration_and_empty_files(self):
        self.write_csv("op_summary_a.csv", [["Op Name", "Stream ID"], ["Add", "7"]])
        (self.root / "op_summary_b.csv").write_text("# metadata\n\n", encoding="utf-8")
        self.assertEqual(extract_profiling_time(self.root), 0.0)

    def test_discovery_skips_unusable_file_and_uses_nested_csv(self):
        self.write_csv("op_summary_a.csv", [["Op Name", "Stream ID"], ["Add", "7"]])
        self.write_csv("nested/op_summary_b.csv", [["Duration(us)"], ["2"], ["3"]])
        self.assertEqual(extract_profiling_time(self.root), 5.0)

    def test_dashboard_cli_keeps_paired_performance(self):
        self.write_csv(
            "profiling/Model_device0/op_summary_ref.csv",
            [["Input Shapes", "Task Duration(us)"], ["2,3", "20"]],
        )
        self.write_csv(
            "profiling/ModelNew_device0/op_summary_custom.csv",
            [["Input Shapes", "Task Duration(us)"], ["2,3", "10"]],
        )
        (self.root / "evaluation_results.json").write_text(
            json.dumps({"passed": True, "shape": [2, 3]}), encoding="utf-8"
        )
        script = Path(__file__).resolve().parents[1] / "scripts/gen_dashboard.py"
        result = subprocess.run(
            [sys.executable, str(script), "--op-dir", str(self.root), "--extract-only"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(
            (self.root / "panels/perf/data.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["cases"][0]["performance"]["ref_time_us"], 20.0)
        self.assertEqual(data["cases"][0]["performance"]["custom_time_us"], 10.0)
        self.assertEqual(data["cases"][0]["performance"]["speedup"], 2.0)


if __name__ == "__main__":
    unittest.main()
