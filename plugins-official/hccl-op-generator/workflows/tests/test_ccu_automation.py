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
"""Real Git draft initialization and raw-log evidence collection in isolated fixtures."""

import argparse
import copy
import json
import importlib
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from skill_sources import COMMUNICATION

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
init = importlib.import_module("init_ccu_task")
summary = importlib.import_module("summarize_ccu_evidence")
Validator = importlib.import_module("validate_ccu_artifacts").Validator

HVM = COMMUNICATION / "hccl-test-tool-hvm"
SKILL = COMMUNICATION / "hccl-ccu-best-practice"


def git(root, *args):
    return subprocess.check_output(
        [shutil.which("git"), "-C", str(root), *args], text=True
    ).strip()


class InitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.hccl, self.hcomm = [self.root / n for n in ["hccl", "hcomm"]]
        for p in [self.hccl, self.hcomm]:
            p.mkdir()
            git(p, "init", "-q", "-b", "main")
            (p / "src/ops/all_gather").mkdir(parents=True)
            (p / "src/ops/all_gather/source.cc").write_text("original source\n")
            git(p, "add", ".")
            git(
                p,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "fixture",
            )
        requirement = self.root / "request.txt"
        requirement.write_text(
            "Use CCU_SCHED for AllGather Ring with allgather:sole{ring}"
        )
        self.a = argparse.Namespace(
            source_repo=str(self.hccl),
            hcomm_repo=str(self.hcomm),
            source_identity=None,
            hcomm_source_identity=None,
            op_type="all_gather",
            task_id="ccu-fixture",
            requirement_file=str(requirement),
            evidence_root=str(self.root / "ccu-fixture/evidence"),
        )

    def create(self):
        result = init.initialize(self.a)
        self.task = Path(result["task_dir"])
        return result

    def reviewed_environment(self):
        p = self.task / "environment.md"
        p.write_text(
            p.read_text()
            .replace('status: "BLOCKED"', 'status: "PASS"')
            .replace("checks_pass: false", "checks_pass: true")
        )

    def test_draft_fails_gate_and_binding_requires_existing_owner_pass(self):
        result = self.create()
        self.assertFalse(result["environment_ready"])
        gate = Validator(self.task, SKILL)
        gate.validate_state("ENV_READY")
        self.assertTrue(gate.problems)
        with self.assertRaisesRegex(ValueError, "already be reviewed PASS"):
            init.bind_environment(self.task)
        self.reviewed_environment()
        before = (self.task / "environment.md").read_bytes()
        init.bind_environment(self.task)
        gate = Validator(self.task, SKILL)
        gate.validate_state("ENV_READY")
        self.assertEqual([], gate.problems)
        self.assertEqual(before, (self.task / "environment.md").read_bytes())

    def test_existing_destination_and_downstream_task_never_overwritten(self):
        self.create()
        before = {p.name: p.read_bytes() for p in self.task.iterdir()}
        with self.assertRaisesRegex(ValueError, "never overwrites"):
            init.initialize(self.a)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.task.iterdir()})
        self.reviewed_environment()
        p = self.task / "task-index.json"
        data = json.loads(p.read_text())
        data["calls"] = [dict(call_id="actual-owner-call")]
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "before role calls"):
            init.bind_environment(self.task)

    def test_invalid_paths_fail_before_creating_destinations(self):
        for task_id, evidence in [
            ("../escape", self.a.evidence_root),
            ("ccu-fixture", str(self.hccl / "ccu-fixture/evidence")),
            ("ccu-fixture", str(self.hcomm / "ccu-fixture/evidence")),
            ("ccu-fixture", str(self.root / "unscoped")),
        ]:
            args = copy.copy(self.a)
            args.task_id, args.evidence_root = task_id, evidence
            with self.assertRaises(ValueError):
                init.initialize(args)
        self.assertFalse((self.hccl / "src/ops/all_gather/docs").exists())

    def test_dirty_repository_requires_confirmed_identity_and_tracks_content_changes(
        self,
    ):
        p = self.hcomm / "new-source.cc"
        p.write_text("first")
        with self.assertRaisesRegex(ValueError, "dirty worktree"):
            self.create()
        self.a.hcomm_source_identity = (
            str(self.hcomm)
            + "@main:"
            + git(self.hcomm, "rev-parse", "HEAD")
            + ":DIRTY:snapshot-fixture"
        )
        self.create()
        self.reviewed_environment()
        p.write_text("second")
        with self.assertRaisesRegex(ValueError, "contents changed"):
            init.bind_environment(self.task)

    def test_production_source_change_invalidates_initial_binding(self):
        self.create()
        self.reviewed_environment()
        (self.hccl / "src/ops/all_gather/source.cc").write_text("changed")
        with self.assertRaises(ValueError):
            init.bind_environment(self.task)

    def test_detached_head_and_cli_errors_do_not_create_task(self):
        git(self.hccl, "checkout", "--detach", "-q")
        with self.assertRaises(subprocess.CalledProcessError):
            self.create()
        run = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPTS / "init_ccu_task.py"),
                "bind-environment",
                "--task-dir",
                str(self.root / "missing"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, run.returncode)
        self.assertFalse(json.loads(run.stdout)["ok"])


class SummaryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.tool, _ = summary.load_tool(HVM)
        self.config = self.root / "selection.json"
        self.case = "CCU_SCHED|allgather|int32|64|118"
        self.selection = dict(schema_version=1, runs=[], comparisons=[])

    def add_run(self, name, role, algo="CcuSchedAllGatherSoleMesh", source="candidate"):
        root = self.root / name
        root.mkdir()
        text = (
            "the selected algo type is " + algo + "\n[CMD DONE] mpirun (exit=0)\n"
            "[CHECKER_RUN_SUMMARY] All Success (Total Op: 2, Big Graph: 1)\n"
        )
        log = root / "case.log"
        log.write_text(text)
        record = self.tool.parse_log(text, algo if role == "directed" else "")
        record.update(
            case_id=self.case,
            raw_log=str(log),
            raw_log_sha256=self.tool.digest(log),
            expected_algorithm=algo if role == "directed" else "",
            test_binary_sha256="binary",
            duration_seconds=13,
            case_environment={
                "HCCL_OP_EXPANSION_MODE": "CCU_SCHED",
                "HCCL_ENABLE_OPEN_CCU": "1",
            },
        )
        manifest = self.manifest(role, source)
        self.tool.write_json(root / "manifest.json", manifest)
        (root / "results.jsonl").write_text(json.dumps(record) + "\n")
        item = dict(
            id=name, path=name, role=role, source_id=source, expected_cases=[self.case]
        )
        if role == "directed":
            item["expect_algo"] = algo
        self.selection["runs"].append(item)
        return root

    def manifest(self, role, source):
        artifact = dict(
            schema_version=1,
            source_id=source,
            package_sha256=source,
            environment_id="same-environment",
            build_log_sha256="build-log",
            build_command="build",
            package="pkg.run",
            build_exit_code=0,
            expected_libraries={"host": source, "device": "device"},
        )
        manifest = dict(
            role=role,
            dry_run=False,
            source_id=source,
            declared_artifact=artifact,
            installed_libraries=[
                dict(kind=k, sha256=v)
                for k, v in artifact["expected_libraries"].items()
            ],
            expected_cases=[self.case],
            environment={
                "HCCL_ALGO": "allgather:sole{ring}" if role == "directed" else ""
            },
            cluster="same-cluster",
            iterations=1,
            warmup=0,
            runner=0,
        )
        return manifest

    def run_summary(self):
        self.config.write_text(json.dumps(self.selection))
        return summary.summarize(self.config, HVM)

    def complete(self):
        b = self.add_run("base", "baseline", source="baseline")
        a = self.add_run("target", "directed", algo="CcuSchedAllGatherSoleRing")
        c = self.add_run("default", "regression")
        self.selection["comparisons"] = [dict(baseline="base", regression="default")]
        return b, a, c

    def test_all_three_phases_compare_and_sum_real_records(self):
        self.complete()
        out = self.run_summary()
        self.assertTrue(out["evidence_checks_ok"], out["issues"])
        self.assertEqual(dict(runs=3, cases=3, case_seconds=39), out["totals"])
        self.assertEqual(1, out["by_role"]["directed"]["cases"])
        self.assertTrue(out["comparisons"][0]["comparison_ok"])

    def test_tampered_log_or_forged_result_never_passes(self):
        b, _, _ = self.complete()
        (b / "case.log").write_text("overwritten")
        out = self.run_summary()
        self.assertFalse(out["evidence_checks_ok"])
        self.assertEqual(3, out["recorded_totals"]["runs"])
        self.assertEqual(39, out["recorded_totals"]["case_seconds"])
        self.assertEqual(2, out["totals"]["runs"])
        self.assertIn("manifest_sha256", out["runs"][0])
        self.assertIn("results_sha256", out["runs"][0])

    def test_raw_failure_cannot_be_hidden_by_pass_result_and_matching_hash(self):
        root = self.add_run("target", "directed", algo="CcuSchedAllGatherSoleRing")
        p = root / "case.log"
        p.write_text(p.read_text().replace("exit=0", "exit=1"))
        r = root / "results.jsonl"
        row = json.loads(r.read_text())
        row["raw_log_sha256"] = self.tool.digest(p)
        r.write_text(json.dumps(row) + "\n")
        self.assertFalse(self.run_summary()["evidence_checks_ok"])

    def test_explicit_error_severity_is_not_waived_by_a_success_summary(self):
        root = self.add_run("target", "directed", algo="CcuSchedAllGatherSoleRing")
        p = root / "case.log"
        original = p.read_text()
        r = root / "results.jsonl"
        record = json.loads(r.read_text())
        for line in [
            "[ERROR] rank 3: Checker compare failed; expected=17 actual=19",
            "\x1b[31m[error]\x1b[0m transfer failed",
            "[FATAL] failure",
        ]:
            p.write_text(line + "\n" + original)
            record["raw_log_sha256"] = self.tool.digest(p)
            r.write_text(json.dumps(record) + "\n")
            out = self.run_summary()
            self.assertFalse(out["evidence_checks_ok"])
            self.assertIn("ERROR/FATAL", str(out["issues"]))
        p.write_text("info: error_count=0, no error detected\n" + original)
        record["raw_log_sha256"] = self.tool.digest(p)
        r.write_text(json.dumps(record) + "\n")
        self.assertTrue(self.run_summary()["evidence_checks_ok"])

    def test_source_library_and_expected_algorithm_mismatch(self):
        _, a, c = self.complete()
        self.selection["runs"][1]["source_id"] = "wrong-source"
        self.assertFalse(self.run_summary()["evidence_checks_ok"])
        self.selection["runs"][1]["source_id"] = "candidate"
        self.selection["runs"][1]["expect_algo"] = "Wrong"
        self.assertFalse(self.run_summary()["evidence_checks_ok"])
        self.selection["runs"][1]["expect_algo"] = "CcuSchedAllGatherSoleRing"
        manifest = self.tool.load(c / "manifest.json")
        manifest["installed_libraries"][0]["sha256"] = "wrong-library"
        self.tool.write_json(c / "manifest.json", manifest)
        self.assertFalse(self.run_summary()["evidence_checks_ok"])

    def test_missing_case_compare_or_dryrun_is_rejected(self):
        _, a, _ = self.complete()
        self.selection["runs"][1]["expected_cases"] = ["missing-case"]
        self.assertFalse(self.run_summary()["evidence_checks_ok"])
        self.selection["runs"][1]["expected_cases"] = [self.case]
        self.selection["comparisons"] = []
        self.assertFalse(self.run_summary()["evidence_checks_ok"])
        m = self.tool.load(a / "manifest.json")
        m["dry_run"] = True
        self.tool.write_json(a / "manifest.json", m)
        self.assertFalse(self.run_summary()["evidence_checks_ok"])

    def test_duplicate_paths_rejected_and_intentional_smoke_overlap_explicit(self):
        self.add_run("target", "directed", algo="CcuSchedAllGatherSoleRing")
        self.add_run("smoke", "directed", algo="CcuSchedAllGatherSoleRing")
        self.assertFalse(self.run_summary()["evidence_checks_ok"])
        self.selection["runs"][1].update(
            allow_case_overlap=True, overlap_basis="frozen smoke then matrix"
        )
        self.assertTrue(self.run_summary()["evidence_checks_ok"])
        self.selection["runs"][1]["path"] = "target"
        with self.assertRaisesRegex(ValueError, "selected twice"):
            self.run_summary()

    def test_overlap_permission_requires_a_json_boolean(self):
        self.add_run("target", "directed", algo="CcuSchedAllGatherSoleRing")
        for invalid in (0, 1, "false", None):
            with self.subTest(value=invalid):
                self.selection["runs"][0]["allow_case_overlap"] = invalid
                with self.assertRaisesRegex(ValueError, "must be boolean"):
                    self.run_summary()

    def test_invalid_recorded_duration_cannot_enter_validated_totals(self):
        baseline, _, _ = self.complete()
        results = baseline / "results.jsonl"
        record = json.loads(results.read_text())
        for invalid in (True, False, -1, 1.5, "13", None):
            with self.subTest(value=invalid):
                record["duration_seconds"] = invalid
                results.write_text(json.dumps(record) + "\n")
                result = self.run_summary()
                self.assertFalse(result["evidence_checks_ok"])
                self.assertFalse(result["runs"][0]["validation_ok"])
                self.assertEqual(2, result["totals"]["runs"])
                self.assertEqual(26, result["totals"]["case_seconds"])
                self.assertIn("manifest_sha256", result["runs"][0])
                self.assertIn("results_sha256", result["runs"][0])

    def test_same_failure_or_default_routing_change_fails_comparison(self):
        self.complete()
        p = self.root / "default/case.log"
        p.write_text(p.read_text().replace("SoleMesh", "SoleRing"))
        r = self.root / "default/results.jsonl"
        old = json.loads(r.read_text())
        old.update(self.tool.parse_log(p.read_text()))
        old["raw_log_sha256"] = self.tool.digest(p)
        r.write_text(json.dumps(old) + "\n")
        self.assertFalse(self.run_summary()["comparisons"][0]["comparison_ok"])

    def test_cli_and_input_tree_remain_read_only(self):
        self.complete()
        self.config.write_text(json.dumps(self.selection))
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        cli = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPTS / "summarize_ccu_evidence.py"),
                "--selection",
                str(self.config),
                "--hvm-skill-dir",
                str(HVM),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, cli.returncode, cli.stdout + cli.stderr)
        self.assertTrue(json.loads(cli.stdout)["evidence_checks_ok"])
        self.assertEqual(
            before,
            {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()},
        )


if __name__ == "__main__":
    unittest.main()
