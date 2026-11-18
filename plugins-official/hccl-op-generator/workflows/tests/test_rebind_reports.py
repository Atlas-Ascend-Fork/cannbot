#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Check transitive owner work orders and read-only dependency auditing."""

import hashlib
import contextlib
import io
import logging
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_validate_aicpu_artifacts import GATE, TaskFixture
from test_validate_ccu_artifacts import CcuFixture, Validator as CcuValidator, SKILL

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class RebindTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = TaskFixture(Path(self.temp.name))
        self.validator = GATE.Validator(self.fixture.task_dir)

    def test_json_cli_output_survives_configured_root_logging(self):
        output, root_output = io.StringIO(), io.StringIO()
        root = logging.getLogger()
        handler = logging.StreamHandler(root_output)
        muted_manager = logging.Manager(root)
        muted_manager.disable = logging.CRITICAL
        with (
            mock.patch.object(root, "handlers", [handler]),
            mock.patch.object(root, "level", logging.CRITICAL),
            mock.patch.object(logging.Logger, "manager", muted_manager),
            contextlib.redirect_stdout(output),
        ):
            GATE.emit_json({"ok": True, "message": "检查通过"})
            GATE.emit_json({"ok": False})
        self.assertEqual(
            [{"ok": True, "message": "检查通过"}, {"ok": False}],
            [json.loads(line) for line in output.getvalue().splitlines()],
        )
        self.assertEqual("", root_output.getvalue())

    def test_test_plan_change_includes_second_order_baseline_bindings(self):
        report = GATE.rebind_report(self.validator, ["TEST_PLAN"])
        work = {item["artifact"]: item for item in report["work"]}
        self.assertEqual(
            {"BASELINE_REPORT", "DEVELOPMENT_LOG", "REVIEW", "TEST_REPORT"}, work.keys()
        )
        for name in ("DEVELOPMENT_LOG", "REVIEW"):
            self.assertEqual("BASELINE_REPORT", work[name]["fields"]["baseline_sha256"])
        for item in work.values():
            for dep in item["fields"].values():
                if dep in work:
                    self.assertLess(work[dep]["order"], item["order"])
        self.assertEqual("hccl-verifier", work["BASELINE_REPORT"]["owner_role"])
        self.assertEqual("hccl-developer", work["DEVELOPMENT_LOG"]["owner_role"])
        self.assertEqual("hccl-reviewer", work["REVIEW"]["owner_role"])

    def test_changed_ancestor_and_descendant_do_not_skip_its_bindings(self):
        report = GATE.rebind_report(self.validator, ["TEST_PLAN", "BASELINE_REPORT"])
        work = {item["artifact"]: item for item in report["work"]}
        self.assertIn("test_plan_sha256", work["BASELINE_REPORT"]["fields"])
        self.assertLess(work["BASELINE_REPORT"]["order"], work["REVIEW"]["order"])

    def test_filename_alias_and_unrelated_root(self):
        self.assertEqual(
            GATE.rebind_report(self.validator, ["TEST_PLAN"]),
            GATE.rebind_report(self.validator, ["TEST_PLAN.md"]),
        )
        self.assertEqual(
            [], GATE.rebind_report(self.validator, ["ENVIRONMENT"])["work"]
        )

    def test_missing_or_unknown_root_fails(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            GATE.rebind_report(self.validator, ["NOT_AN_ARTIFACT"])
        (self.fixture.task_dir / "TEST_PLAN.md").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            GATE.rebind_report(self.validator, ["TEST_PLAN"])

    def test_verify_finds_newly_stale_second_order_fields(self):
        self.assertEqual([], GATE.verify_rebind(self.validator))
        path = self.fixture.task_dir / "TEST_PLAN.md"
        path.write_text(path.read_text() + "\nPlan erratum in fixture\n")
        stale = GATE.verify_rebind(self.validator)
        self.assertIn(
            ("BASELINE_REPORT", "test_plan_sha256"),
            {(s["artifact"], s["field"]) for s in stale},
        )
        # Simulate owner revalidation of the first layer, which changes baseline's own hash.
        self.fixture.write_baseline()
        stale = {
            (s["artifact"], s["field"]) for s in GATE.verify_rebind(self.validator)
        }
        self.assertIn(("DEVELOPMENT_LOG", "baseline_sha256"), stale)
        self.assertIn(("REVIEW", "baseline_sha256"), stale)
        self.fixture.write_development_log()
        self.fixture.write_review()
        self.fixture.write_test_report()
        self.assertEqual([], GATE.verify_rebind(self.validator))
        # Dependency consistency cannot restore index validity or confer a workflow PASS.
        gate = GATE.Validator(self.fixture.task_dir)
        gate.validate_state("COMPLETE")
        self.assertIn("INDEX_HASH", {p.code for p in gate.problems})

    def test_cli_for_both_engines_is_read_only(self):
        for engine in ("aicpu", "ccu"):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as temp:
                fixture = (
                    CcuFixture(Path(temp))
                    if engine == "ccu"
                    else TaskFixture(Path(temp))
                )
                before = {
                    str(p.relative_to(fixture.task_dir)): hashlib.sha256(
                        p.read_bytes()
                    ).hexdigest()
                    for p in fixture.task_dir.rglob("*")
                    if p.is_file()
                }
                self.check_rebind_cli(engine, fixture)
                after = {
                    str(p.relative_to(fixture.task_dir)): hashlib.sha256(
                        p.read_bytes()
                    ).hexdigest()
                    for p in fixture.task_dir.rglob("*")
                    if p.is_file()
                }
                self.assertEqual(before, after)

    def check_rebind_cli(self, engine, fixture):
        script = SCRIPTS / f"validate_{engine}_artifacts.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--task-dir",
                str(fixture.task_dir),
                "--rebind-report",
                "TEST_PLAN",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["read_only"])
        self.assertEqual(engine.upper(), payload["engine"])
        self.assertEqual(4, len(payload["work"]))
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--task-dir",
                str(fixture.task_dir),
                "--verify-rebind",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], json.loads(result.stdout)["stale_bindings"])

    def test_cli_returns_failure_for_stale_bindings(self):
        path = self.fixture.task_dir / "TEST_PLAN.md"
        path.write_text(path.read_text() + "\nChanged\n")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "validate_aicpu_artifacts.py"),
                "--task-dir",
                str(self.fixture.task_dir),
                "--verify-rebind",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertFalse(json.loads(result.stdout)["ok"])
        self.assertTrue(json.loads(result.stdout)["stale_bindings"])

    def test_ccu_attachment_changes_are_audited_and_expand_to_design_descendants(self):
        root = Path(self.temp.name) / "ccu"
        root.mkdir()
        fixture = CcuFixture(root)
        for filename, field, artifact in (
            ("source-report.json", "source_report_sha256", "SOURCE_REPORT"),
            ("launch-contract.json", "launch_contract_sha256", "LAUNCH_CONTRACT"),
        ):
            with self.subTest(filename=filename):
                path = fixture.task_dir / filename
                saved = path.read_bytes()
                path.write_bytes(saved + b"\n")
                gate = CcuValidator(fixture.task_dir, SKILL)
                gate.load_index()
                stale = GATE.verify_rebind(gate)
                self.assertIn(
                    ("DESIGN", field),
                    {(row["artifact"], row["field"]) for row in stale},
                )
                report = GATE.rebind_report(gate, [artifact])
                self.assertEqual(report, GATE.rebind_report(gate, [filename]))
                work = {row["artifact"]: row for row in report["work"]}
                self.assertEqual("hccl-architect", work["DESIGN"]["owner_role"])
                self.assertEqual(artifact, work["DESIGN"]["fields"][field])
                self.assertLess(
                    work["DESIGN"]["order"], work["BASELINE_REPORT"]["order"]
                )
                self.assertIn("TEST_REPORT", work)
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "validate_ccu_artifacts.py"),
                        "--task-dir",
                        str(fixture.task_dir),
                        "--verify-rebind",
                        "--json",
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertFalse(json.loads(result.stdout)["ok"])
                self.assertEqual(saved + b"\n", path.read_bytes())
                path.write_bytes(saved)

    def test_ccu_missing_or_escaping_attachment_cannot_pass_audit(self):
        root = Path(self.temp.name) / "ccu"
        root.mkdir()
        fixture = CcuFixture(root)
        path = fixture.task_dir / "launch-contract.json"
        outside = Path(self.temp.name) / "outside.json"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        for escaped in (False, True):
            with self.subTest(escaped=escaped):
                if escaped:
                    path.symlink_to(outside)
                gate = CcuValidator(fixture.task_dir, SKILL)
                gate.load_index()
                GATE.verify_rebind(gate)
                self.assertTrue(
                    {p.code for p in gate.problems}
                    & {"REBIND_PATH", "REBIND_DEPENDENCY_MISSING"}
                )


if __name__ == "__main__":
    unittest.main()
