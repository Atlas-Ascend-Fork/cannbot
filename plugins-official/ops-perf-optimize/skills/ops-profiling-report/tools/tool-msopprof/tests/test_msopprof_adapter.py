# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Offline regressions from empty msopprof output after application startup failure."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from msopprof_fixture import backend as adapter
from device_fixture import bare_plan, process_receipt


class EmptyCaptureTests(unittest.TestCase):
    def test_empty_wrapper_directory_is_retryable_but_files_are_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "output"
            wrapper = root / "OPPROF_empty"
            wrapper.mkdir(parents=True)
            attempt = {"command": ["msopprof", f"--output={root}"]}
            adapter.validate_failure(attempt, "initialization failed")
            (wrapper / "partial.csv").write_text("retained partial data")
            with self.assertRaises(ValueError):
                adapter.validate_failure(attempt, "initialization failed")
            (wrapper / "partial.csv").unlink()
            with self.assertRaises(ValueError):
                adapter.validate_failure({**attempt, "archive": {"path": "receipt"}}, "")

    def test_recovery_classifies_empty_output_without_restarting_application(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            (output / "OPPROF_empty").mkdir(parents=True)
            log = root / "run.log"
            log.write_text("Child process exited with return value 1; results empty")
            plan = bare_plan(adapter.PROTOCOL)
            identity = {"runner": ["/fake/app"], "cwd": str(root)}
            attempt = {"command": adapter.command(plan, identity, output),
                       "run_log": adapter.receipt(log), "returncode": 0,
                       "status": "needs_review", "error": "no captured artifacts",
                       **{k: plan[k] for k in ("device_binding", "environment", "physical_device", "logical_device")}}
            with patch.object(adapter.subprocess, "run", side_effect=AssertionError("must not launch")):
                recovered = adapter.recover_attempt(plan, identity, attempt, root)
            self.assertEqual(recovered["status"], "failed")
            self.assertEqual(attempt["status"], "needs_review")
            adapter.validate_failure(recovered, log.read_text())
            self.assertTrue(log.is_file())


class MeasurementBoundaryTests(unittest.TestCase):
    def plan(self, **extra):
        return {
            **bare_plan(adapter.PROTOCOL),
            "protocol": {**adapter.PROTOCOL, "warmup": 5},
            "identities": {"candidate": {"kernel_name": "kernel", "runner": ["/fake/app"]}},
            "logical_device": 0,
            **extra,
        }

    def test_rated_frequency_preflight_and_direct_raw_error(self):
        for value in (None, 0, -1, True, "1650", float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "rated_frequency_mhz"):
                adapter.validate_measurement(self.plan(rated_frequency_mhz=value))
        with self.assertRaisesRegex(ValueError, "rated_frequency_mhz"):
            adapter.raw_sample("not-read", {}, self.plan())
        adapter.validate_measurement(self.plan(rated_frequency_mhz=1650))
        with self.assertRaisesRegex(ValueError, "frequency_policy"):
            adapter.validate_measurement(self.plan(frequency_policy="typo"))

    def test_missing_rated_frequency_rejected_before_launch_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(adapter.subprocess, "run", side_effect=AssertionError("must not launch")):
                with self.assertRaisesRegex(ValueError, "rated_frequency_mhz"):
                    adapter.collect_attempt(self.plan(), {}, {}, root)
            self.assertFalse((root / "output").exists())

    def test_record_only_without_rated_frequency_preserves_frozen_warmup(self):
        plan = self.plan(frequency_policy="record_only")
        identity = plan["identities"]["candidate"]
        adapter.validate_measurement(plan)
        self.assertIn("--warm-up=5", adapter.command(plan, identity, Path.cwd()))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            output.mkdir()
            source = output / "OpBasicInfo.csv"
            source.write_text("Op Name,Task Duration(us),Device Id,Pid\nkernel,12.966,0,1234\n")
            extracted = adapter.tools.inspect_collection(output, [identity["kernel_name"]])
            extraction = root / "extraction.json"
            extraction.write_text(json.dumps(extracted))
            selected = root / "selected.json"
            selected.write_text(
                json.dumps(
                    {
                        "extraction": adapter.receipt(extraction),
                        "record": extracted["records"][0],
                        "target_process": process_receipt(root, plan, identity["runner"]),
                        "capture_output": str(root / "output"),
                        "effect_case_id": plan["effect_case_id"],
                    }
                )
            )
            self.assertEqual(adapter.raw_sample(selected, identity, plan), (12.966, 1234))

    def test_trace_prepare_returns_binding_without_statistics_fields(self):
        found = {
            "tool": {"path": "/fake/msopprof"},
            "command_prefix": ["/fake/msopprof"],
            "options": ["--output", "--warm-up", "--replay-mode", "--launch-count", "--aic-metrics"],
        }
        with patch.object(adapter.tools, "find_tool", return_value="/fake/msopprof"), \
                patch.object(adapter.tools, "capabilities", return_value=found), \
                patch.object(adapter.subprocess, "run", side_effect=AssertionError("must not launch")):
            binding = adapter.prepare({"aic_metrics": "InstrTimeline"})
        self.assertEqual(binding["protocol"]["aic_metrics"], "InstrTimeline")
        self.assertNotIn("identities", binding)
        self.assertNotIn("rated_frequency_mhz", binding)
        self.assertNotIn("samples_per_variant", binding)


class FrequencyReportTests(unittest.TestCase):
    def test_low_frequency_is_visible_with_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "capture"
            root.mkdir()
            (root / "OpBasicInfo.csv").write_text(
                "Op Name,Task Duration(us),Device Id,Pid,Current Freq,Rated Freq\n"
                "compressor_kernel,12.966,0,1234,875,1650\n"
            )
            output = Path(tmp) / "report"
            report = adapter.tools.build_report(root, "c5", ["compressor_kernel"], output)
            self.assertEqual(report["timing"]["current_frequency_mhz"], 875)
            self.assertIn("875.0/1650.0", (output / "性能分析报告.md").read_text())
            adapter.validate_report(report)
