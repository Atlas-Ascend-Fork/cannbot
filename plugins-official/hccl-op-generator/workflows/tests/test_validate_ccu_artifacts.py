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
"""CCU CLI integration tests. Synthetic evidence is not an algorithm test."""

import json
import importlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from skill_sources import COMMUNICATION
from test_validate_aicpu_artifacts import GATE, TaskFixture, sha256

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
Validator = importlib.import_module("validate_ccu_artifacts").Validator

SKILL = COMMUNICATION / "hccl-ccu-best-practice"


class CcuFixture(TaskFixture):
    task_id = "all-reduce-ccu-001"

    def __init__(self, root, ccu_mode="CCU_SCHED", **kwargs):
        self.ccu_mode = ccu_mode
        self.hcomm_repo = root / "hcomm"
        self.hcomm_repo.mkdir()
        super().__init__(root, **kwargs)

    def build_calls(self):
        return self._build_calls()

    def write_handoff(self, *args, **kwargs):
        super().write_handoff(*args, **kwargs)
        self.rewrite_doc("HANDOFF_LOG", engine="CCU")

    def write_design_inputs(self, dataflow_required):
        super().write_design_inputs(dataflow_required)
        source_report = {
            "schema_version": 1,
            "repositories": {
                "hccl": {"root": str(self.source_repo), "head": "a" * 40},
                "hcomm": {"root": str(self.hcomm_repo), "head": "b" * 40},
            },
            "sources": [
                {
                    "repo": name,
                    "path": "include/example.h",
                    "required": True,
                    "status": "unchanged",
                    "sha256": "c" * 64,
                }
                for name in ("hccl", "hcomm")
            ],
        }
        (self.task_dir / "source-report.json").write_text(json.dumps(source_report))
        (self.task_dir / "launch-contract.json").write_bytes(
            (SKILL / "assets/launch-contract.example.json").read_bytes()
        )
        self.rewrite_doc(
            "DESIGN",
            ccu_mode=self.ccu_mode,
            hcomm_source_identity="main@hcomm+clean",
            source_report_sha256=sha256(self.task_dir / "source-report.json"),
            launch_contract_sha256=sha256(self.task_dir / "launch-contract.json"),
        )
        self.rewrite_doc("TEST_PLAN", ccu_mode=self.ccu_mode)

    def write_estimate(self):
        path = super().write_estimate()
        data = json.loads(path.read_text())
        data.update(
            engine="CCU",
            ccu_mode=self.docs["DESIGN"]["ccu_mode"],
            hcomm_source_identity=self.docs["DESIGN"]["hcomm_source_identity"],
            expected_algorithm="CcuAllReduceExample",
            observed_algorithm="CcuAllReduceExample",
        )
        path.write_text(json.dumps(data))
        return path

    def write_index(self, *args, **kwargs):
        super().write_index(*args, **kwargs)
        path = self.task_dir / "task-index.json"
        data = json.loads(path.read_text())
        data.update(
            engine="CCU",
            requirement="Implement a CCU AllReduce algorithm",
            hcomm_repo=str(self.hcomm_repo),
            hcomm_source_identity="main@hcomm+clean",
        )
        path.write_text(json.dumps(data))

    def _common(self, artifact, owner):
        return dict(super()._common(artifact, owner), engine="CCU")

    def _build_calls(self):
        calls = super()._build_calls()
        calls[0]["outputs"] += self.task_outputs(
            "source-report.json", "launch-contract.json"
        )
        calls[2]["outputs"][-1] = "src/ops/all_reduce/algorithm/template/ccu/new.cc"
        return calls


class CcuArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = CcuFixture(Path(self.temp.name), dataflow_required=True)

    def codes(self, state="COMPLETE"):
        gate = Validator(self.fixture.task_dir, SKILL)
        gate.validate_state(state)
        return {problem.code for problem in gate.problems}

    def test_complete_contract_passes_and_aicpu_gate_rejects_it(self):
        self.assertEqual(set(), self.codes())
        gate = GATE.Validator(self.fixture.task_dir)
        gate.validate_state("COMPLETE")
        self.assertIn("INDEX_ENGINE", {problem.code for problem in gate.problems})

    def change_estimate(self, **updates):
        path = Path(self.fixture.docs["TEST_REPORT"]["estimate_evidence_path"])
        data = json.loads(path.read_text())
        data.update(updates)
        path.write_text(json.dumps(data))
        self.fixture.rewrite_doc("TEST_REPORT", estimate_evidence_sha256=sha256(path))
        self.fixture.write_index()

    def test_old_ccu_report_without_estimate_blocks_test_pass_and_complete(self):
        fields = {
            key: value
            for key, value in self.fixture.docs["TEST_REPORT"].items()
            if not key.startswith("estimate_")
        }
        self.fixture.write_doc("TEST_REPORT", fields)
        for state in ("TEST_PASS", "COMPLETE"):
            with self.subTest(state=state):
                self.fixture.set_state(state)
                codes = self.codes(state)
                self.assertIn("ARTIFACT_FIELD", codes)
                self.assertIn("ESTIMATE_STATUS", codes)

    def test_failed_or_unexecuted_estimate_blocks_completion(self):
        for state in ("TEST_PASS", "COMPLETE"):
            for status in ("FAILED", "NOT_RUN"):
                with self.subTest(state=state, status=status):
                    self.fixture.rewrite_doc("TEST_REPORT", estimate_status=status)
                    self.fixture.set_state(state)
                    self.assertIn("ESTIMATE_STATUS", self.codes(state))

    def test_estimate_metadata_is_bound_to_current_ccu_candidate(self):
        path = Path(self.fixture.docs["TEST_REPORT"]["estimate_evidence_path"])
        original = json.loads(path.read_text())
        cases = (
            ("source_identity", self.fixture.design_identity, "ESTIMATE_IDENTITY"),
            ("engine", "AICPU", "ESTIMATE_ENGINE"),
            ("engine", None, "ESTIMATE_ENGINE"),
            ("ccu_mode", "CCU_MS", "ESTIMATE_CCU_MODE"),
            ("ccu_mode", None, "ESTIMATE_CCU_MODE"),
            ("hcomm_source_identity", "main@other-hcomm", "ESTIMATE_HCOMM_IDENTITY"),
            ("hcomm_source_identity", None, "ESTIMATE_HCOMM_IDENTITY"),
            ("observed_algorithm", "OtherAlgorithm", "ESTIMATE_ALGORITHM"),
            ("comm_domain", "118", "ESTIMATE_COMM"),
            ("makespan_us", 0, "ESTIMATE_TIME"),
            ("makespan_us", float("nan"), "ESTIMATE_TIME"),
        )
        for field, value, code in cases:
            with self.subTest(field=field, value=value):
                self.change_estimate(**{**original, field: value})
                self.assertIn(code, self.codes())

    def test_estimate_report_identity_must_match_candidate(self):
        self.fixture.rewrite_doc(
            "TEST_REPORT", estimate_source_identity=self.fixture.design_identity
        )
        self.fixture.write_index()
        self.assertIn("ESTIMATE_IDENTITY", self.codes())

    def test_ccu_ms_and_explicit_domain_use_same_estimate_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = CcuFixture(Path(temp), ccu_mode="CCU_MS")
            path = Path(fixture.docs["TEST_REPORT"]["estimate_evidence_path"])
            data = json.loads(path.read_text())
            data["comm_domain"] = "118"
            path.write_text(json.dumps(data))
            fixture.rewrite_doc(
                "TEST_REPORT",
                estimate_comm_domain="118",
                estimate_evidence_sha256=sha256(path),
            )
            fixture.write_index()
            gate = Validator(fixture.task_dir, SKILL)
            gate.validate_state("COMPLETE")
            self.assertEqual([], gate.problems)

    def test_estimate_parameters_and_real_exit_codes_are_required(self):
        path = Path(self.fixture.docs["TEST_REPORT"]["estimate_evidence_path"])
        original = json.loads(path.read_text())
        for key, value in dict(
            np=8, begin="1M", end="2G", warmup=1, iterations=2, check=1
        ).items():
            with self.subTest(parameter=key):
                self.change_estimate(parameters={**original["parameters"], key: value})
                self.assertIn("ESTIMATE_PARAMETERS", self.codes())
        self.change_estimate(parameters=original["parameters"])
        for key in original["exit_codes"]:
            with self.subTest(exit_code=key):
                self.change_estimate(exit_codes={**original["exit_codes"], key: 1})
                self.assertIn("ESTIMATE_EXIT", self.codes())

    def test_missing_estimate_manifest_blocks_completion(self):
        Path(self.fixture.docs["TEST_REPORT"]["estimate_evidence_path"]).unlink()
        self.assertIn("ESTIMATE_MISSING", self.codes())

    def test_missing_or_tampered_estimate_files_block_completion(self):
        directory = self.fixture.external_evidence_root / "estimate"
        (directory / "plugin_log").write_text("tampered")
        (directory / "trace").unlink()
        codes = self.codes()
        self.assertIn("ESTIMATE_HASH", codes)
        self.assertIn("ESTIMATE_MISSING", codes)

    def test_estimate_files_cannot_escape_registered_evidence_roots(self):
        outside = Path(self.temp.name) / "outside.log"
        outside.write_text("synthetic evidence")
        path = Path(self.fixture.docs["TEST_REPORT"]["estimate_evidence_path"])
        data = json.loads(path.read_text())
        data["files"]["test_log"] = {"path": str(outside), "sha256": sha256(outside)}
        self.change_estimate(files=data["files"])
        self.assertIn("ESTIMATE_PATH", self.codes())

    def test_mixed_engine_report_is_rejected(self):
        self.fixture.rewrite_doc("REVIEW", engine="AICPU")
        self.fixture.write_index()
        self.assertIn("ARTIFACT_ENGINE", self.codes())

    def test_launch_mutation_invalidates_frozen_design(self):
        path = self.fixture.task_dir / "launch-contract.json"
        path.write_text(path.read_text() + "\n")
        self.assertIn("CCU_DEPENDENCY_HASH", self.codes())

    def test_invalid_launch_mapping_runs_skill_checker_and_blocks(self):
        path = self.fixture.task_dir / "launch-contract.json"
        contract = json.loads(path.read_text())
        contract["kernels"][0]["launch_count"] += 1
        path.write_text(json.dumps(contract))
        self.fixture.rewrite_doc("DESIGN", launch_contract_sha256=sha256(path))
        self.fixture.write_index()
        self.assertIn("CCU_CONTRACT_CHECK", self.codes())
        self.assertIn("DEPENDENCY_HASH", self.codes())

    def test_reduce_cache_header_reaches_real_skill_gate(self):
        path = self.fixture.task_dir / "launch-contract.json"
        path.write_bytes(
            (SKILL / "assets/launch-contract.reduce.example.json").read_bytes()
        )
        gate = Validator(self.fixture.task_dir, SKILL)
        gate.validate_launch_contract(path)
        self.assertEqual([], gate.problems)
        contract = json.loads(path.read_text())
        contract["kernels"][0]["fast_launch"]["cache_launch_offset"] = 0
        path.write_text(json.dumps(contract))
        gate = Validator(self.fixture.task_dir, SKILL)
        gate.validate_launch_contract(path)
        self.assertIn("CCU_CONTRACT_CHECK", {p.code for p in gate.problems})

    def test_attachment_path_escape_is_rejected(self):
        path = self.fixture.task_dir / "launch-contract.json"
        outside = Path(self.temp.name) / "outside.json"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        self.assertIn("CCU_PATH", self.codes())

    def test_missing_attachment_or_checker_blocks(self):
        (self.fixture.task_dir / "source-report.json").unlink()
        self.assertIn("CCU_ARTIFACT_MISSING", self.codes())
        gate = Validator(self.fixture.task_dir, Path(self.temp.name) / "missing-skill")
        gate.validate_state("COMPLETE")
        self.assertIn("CCU_SKILL_MISSING", {problem.code for problem in gate.problems})

    def test_wrong_hcomm_repo_is_rejected(self):
        path = self.fixture.task_dir / "source-report.json"
        report = json.loads(path.read_text())
        report["repositories"]["hcomm"]["root"] = str(Path(self.temp.name) / "another")
        path.write_text(json.dumps(report))
        self.assertIn("CCU_SOURCE_ROOT", self.codes())

    def test_mode_disagreement_blocks(self):
        self.fixture.rewrite_doc("TEST_PLAN", ccu_mode="CCU_MS")
        self.fixture.write_index()
        self.assertIn("CCU_MODE", self.codes())

    def test_stale_source_identity_cannot_complete(self):
        self.fixture.current_identity = "new-hccl+hcomm-dependency"
        self.fixture.write_index()
        self.assertIn("CURRENT_IDENTITY", self.codes())

    def test_hcomm_only_change_invalidates_design(self):
        path = self.fixture.task_dir / "task-index.json"
        data = json.loads(path.read_text())
        data["hcomm_source_identity"] = "main@new-hcomm"
        path.write_text(json.dumps(data))
        self.assertIn("HCOMM_IDENTITY", self.codes())

    def test_designer_call_must_include_ccu_attachments(self):
        self.fixture.calls[0]["outputs"].pop()
        self.fixture.write_index()
        self.assertIn("CALL_OUTPUT", self.codes())

    def test_redesign_selects_a_new_immutable_source_report(self):
        original = self.fixture.task_dir / "source-report.json"
        saved = original.read_bytes()
        revised = self.fixture.task_dir / "source-report-r2.json"
        revised.write_bytes(saved + b"\n")
        self.fixture.rewrite_doc(
            "DESIGN",
            source_report_file=revised.name,
            source_report_sha256=sha256(revised),
        )
        self.fixture.calls[0]["outputs"] = [
            str(revised) if Path(p).name == original.name else p
            for p in self.fixture.calls[0]["outputs"]
        ]
        self.fixture.write_baseline()
        self.fixture.write_development_log()
        self.fixture.write_review()
        self.fixture.write_test_report()
        self.fixture.write_index()
        self.assertEqual(set(), self.codes())
        gate = Validator(self.fixture.task_dir, SKILL)
        gate.load_index()
        self.assertEqual([], GATE.verify_rebind(gate))
        revised.write_bytes(revised.read_bytes() + b"\n")
        self.assertIn("CCU_DEPENDENCY_HASH", self.codes())
        self.assertIn(
            "source_report_sha256", {row["field"] for row in GATE.verify_rebind(gate)}
        )
        self.assertEqual(saved, original.read_bytes())
        revised.unlink()
        self.assertIn("CCU_ARTIFACT_MISSING", self.codes())

    def test_invalid_revision_path_and_role_cannot_change_source_evidence(self):
        for filename in (
            "../source-report-r2.json",
            "source-report-r0.json",
            "/tmp/source-report.json",
            None,
        ):
            with self.subTest(filename=filename):
                self.fixture.rewrite_doc("DESIGN", source_report_file=filename)
                self.assertIn("CCU_SOURCE_REPORT_PATH", self.codes())
        self.fixture.rewrite_doc("DESIGN", source_report_file="source-report.json")
        for actor in ("hccl-architect", "hccl-developer", "hccl-verifier", "hcclbot"):
            gate = Validator(self.fixture.task_dir, SKILL)
            gate.validate_actor(
                actor, [str(self.fixture.task_dir / "source-report-r2.json")]
            )
            self.assertEqual(actor != "hccl-architect", bool(gate.problems))

    def test_only_architect_can_change_contract(self):
        path = str(self.fixture.task_dir / "launch-contract.json")
        for actor in (
            "hcclbot",
            "hccl-architect",
            "hccl-developer",
            "hccl-reviewer",
            "hccl-verifier",
        ):
            with self.subTest(actor=actor):
                gate = Validator(self.fixture.task_dir, SKILL)
                gate.validate_actor(actor, [path])
                self.assertEqual(actor != "hccl-architect", bool(gate.problems))

    def test_both_ccu_modes_have_valid_completion(self):
        self.fixture.rewrite_doc("DESIGN", ccu_mode="CCU_MS")
        self.fixture.rewrite_doc("TEST_PLAN", ccu_mode="CCU_MS")
        self.fixture.write_baseline()
        self.fixture.write_development_log()
        self.fixture.write_review()
        self.fixture.write_test_report()
        self.fixture.write_index()
        self.assertEqual(set(), self.codes())


class CcuSyncGateTests(unittest.TestCase):
    """Version 2 runs the actual Skill checker against an isolated reviewed fixture."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.fixture = CcuFixture(root, dataflow_required=True)
        self.skill = root / "skill"
        shutil.copytree(
            SKILL, self.skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
        header = (
            self.fixture.hcomm_repo
            / "src/base_comm/resources/ccu/ccu_transport/ccu_transport_.h"
        )
        header.parent.mkdir(parents=True)
        header.write_text(
            "static constexpr uint32_t INIT_CKE_NUM = 4;\nstatic constexpr uint32_t INIT_XN_NUM = 4;\n"
        )
        CcuSyncGateTests.write_sync_baseline(self, header)
        self.sync = self.fixture.task_dir / "sync-contract.json"
        self.sync.write_bytes(
            (self.skill / "assets/sync-contract.example.json").read_bytes()
        )
        self.fixture.rewrite_doc("DESIGN", sync_contract_sha256=sha256(self.sync))
        self.fixture.write_baseline()
        self.fixture.write_development_log()
        self.fixture.write_review()
        self.fixture.write_test_report()
        self.fixture.calls[0]["outputs"] += self.fixture.task_outputs(
            "sync-contract.json"
        )
        self.fixture.write_index()
        path = self.fixture.task_dir / "task-index.json"
        index = json.loads(path.read_text())
        index["ccu_contract_version"] = 2
        path.write_text(json.dumps(index))

    def write_sync_baseline(self, header):
        baseline = {
            "schema_version": 1,
            "cards": {
                "sync-limits": {
                    "scope": "isolated test implementation",
                    "reference": "test.md",
                    "files": [
                        {
                            "repo": "hcomm",
                            "path": str(header.relative_to(self.fixture.hcomm_repo)),
                            "sha256": sha256(header),
                        }
                    ],
                }
            },
        }
        (self.skill / "references/knowledge-baseline.json").write_text(
            json.dumps(baseline)
        )

    def codes(self):
        gate = Validator(self.fixture.task_dir, self.skill)
        gate.validate_state("COMPLETE")
        return {p.code for p in gate.problems}

    def test_v2_complete_with_source_backed_sync_check(self):
        self.assertEqual(set(), self.codes())

    def test_original_slot_five_is_rejected_by_gate(self):
        data = json.loads(self.sync.read_text())
        data["pools"][0]["epochs"][0]["signals"][-1]["slot"] = 5
        self.sync.write_text(json.dumps(data))
        self.assertIn("CCU_SYNC_CHECK", self.codes())
        self.assertIn("CCU_DEPENDENCY_HASH", self.codes())

    def test_missing_sync_artifact_blocks_v2(self):
        self.sync.unlink()
        self.assertIn("CCU_ARTIFACT_MISSING", self.codes())

    def test_sync_changes_invalidate_frozen_design(self):
        self.sync.write_text(self.sync.read_text() + "\n")
        self.assertIn("CCU_DEPENDENCY_HASH", self.codes())

    def test_sync_attachment_is_in_rebind_audit_and_work_order(self):
        self.sync.write_text(self.sync.read_text() + "\n")
        gate = Validator(self.fixture.task_dir, self.skill)
        gate.load_index()
        self.assertIn(
            "sync_contract_sha256", {row["field"] for row in GATE.verify_rebind(gate)}
        )
        work = GATE.rebind_report(gate, ["sync-contract.json"])["work"]
        self.assertEqual("DESIGN", work[0]["artifact"])

    def test_source_drift_is_not_silently_accepted(self):
        header = (
            self.fixture.hcomm_repo
            / "src/base_comm/resources/ccu/ccu_transport/ccu_transport_.h"
        )
        header.write_text(header.read_text().replace("CKE_NUM = 4", "CKE_NUM = 8"))
        self.assertIn("CCU_SYNC_CHECK", self.codes())

    def test_design_call_must_report_sync_artifact(self):
        path = self.fixture.task_dir / "task-index.json"
        index = json.loads(path.read_text())
        index["calls"][0]["outputs"].pop()
        path.write_text(json.dumps(index))
        self.assertIn("CALL_OUTPUT", self.codes())

    def test_new_checker_must_be_installed(self):
        (self.skill / "scripts/check_sync_contract.py").unlink()
        self.assertIn("CCU_SKILL_MISSING", self.codes())

    def test_invalid_contract_version_is_rejected(self):
        path = self.fixture.task_dir / "task-index.json"
        index = json.loads(path.read_text())
        index["ccu_contract_version"] = True
        path.write_text(json.dumps(index))
        self.assertIn("CCU_CONTRACT_VERSION", self.codes())


class CcuArithmeticGateTests(unittest.TestCase):
    def setUp(self):
        CcuSyncGateTests.setUp(self)
        baseline_path = self.skill / "references/knowledge-baseline.json"
        baseline = json.loads(baseline_path.read_text())
        entries = []
        for version, extra in (
            ("v1", ""),
            ("v2", ",{CcuRepType::MUL,1},{CcuRepType::SUB,1}"),
        ):
            path = (
                self.fixture.hcomm_repo
                / "src/base_comm/resources/ccu/ccu_representation/reps/translator"
                / f"ccu_ins_generator_{version}.h"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "repTypeInstrCount = {{CcuRepType::ASSIGN,1},{CcuRepType::ADD,1}"
                + extra
                + "};"
            )
            entries.append(
                {
                    "repo": "hcomm",
                    "path": str(path.relative_to(self.fixture.hcomm_repo)),
                    "sha256": sha256(path),
                }
            )
        baseline["cards"]["generator-arith"] = {
            "scope": "isolated generator fixture",
            "reference": "test.md",
            "files": entries,
        }
        baseline_path.write_text(json.dumps(baseline))
        path = self.fixture.task_dir / "task-index.json"
        data = json.loads(path.read_text())
        data["ccu_contract_version"] = 3
        path.write_text(json.dumps(data))

    def codes(self):
        return CcuSyncGateTests.codes(self)

    def test_v3_complete_with_safe_arithmetic(self):
        self.assertEqual(set(), self.codes())

    def test_v3_rejects_mul_before_execution(self):
        data = json.loads(self.sync.read_text())
        data["compute_ops"]["operations"][0]["rep"] = "MUL"
        self.sync.write_text(json.dumps(data))
        self.assertIn("CCU_ARITH_CHECK", self.codes())

    def test_v3_requires_compute_mapping(self):
        data = json.loads(self.sync.read_text())
        data.pop("compute_ops")
        self.sync.write_text(json.dumps(data))
        self.assertIn("CCU_ARITH_CHECK", self.codes())

    def test_v3_requires_installed_arithmetic_checker(self):
        (self.skill / "scripts/check_arith_ops.py").unlink()
        self.assertIn("CCU_SKILL_MISSING", self.codes())

    def test_v3_rejects_generator_source_drift(self):
        path = (
            self.fixture.hcomm_repo
            / "src/base_comm/resources/ccu/ccu_representation/reps/translator/ccu_ins_generator_v1.h"
        )
        path.write_text(path.read_text() + "// unreviewed capability change")
        self.assertIn("CCU_ARITH_CHECK", self.codes())

    def adopt_reviewed_baseline(self):
        baseline = json.loads(
            (self.skill / "references/knowledge-baseline.json").read_text()
        )
        for card in baseline["cards"].values():
            for entry in card["files"]:
                path = self.fixture.hcomm_repo / entry["path"]
                path.write_text(path.read_text() + "\n// reviewed revision\n")
                entry["sha256"] = sha256(path)
        selected = self.fixture.task_dir / "knowledge-baseline.json"
        selected.write_text(json.dumps(baseline))
        source = self.fixture.task_dir / "source-report.json"
        data = json.loads(source.read_text())
        data["knowledge"] = {"baseline_sha256": sha256(selected)}
        source.write_text(json.dumps(data))
        self.fixture.rewrite_doc(
            "DESIGN",
            knowledge_baseline_sha256=sha256(selected),
            source_report_sha256=sha256(source),
        )
        self.fixture.calls[0]["outputs"] += self.fixture.task_outputs(
            "knowledge-baseline.json"
        )
        self.refresh_bindings()
        return selected

    def refresh_bindings(self):
        self.fixture.write_baseline()
        self.fixture.write_development_log()
        self.fixture.write_review()
        self.fixture.write_test_report()
        self.fixture.write_index()
        path = self.fixture.task_dir / "task-index.json"
        data = json.loads(path.read_text())
        data["ccu_contract_version"] = 3
        path.write_text(json.dumps(data))

    def test_reviewed_task_baseline_reaches_both_real_checkers(self):
        selected = self.adopt_reviewed_baseline()
        self.assertEqual(set(), self.codes())
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "validate_ccu_artifacts.py"),
                "--task-dir",
                str(self.fixture.task_dir),
                "--ccu-skill-dir",
                str(self.skill),
                "--target-state",
                "COMPLETE",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        gate = Validator(self.fixture.task_dir, self.skill)
        gate.load_index()
        self.assertEqual([], GATE.verify_rebind(gate))
        selected.write_text(selected.read_text() + "\n")
        self.assertIn("CCU_BASELINE_HASH", self.codes())
        self.assertIn(
            "knowledge_baseline_sha256",
            {row["field"] for row in GATE.verify_rebind(gate)},
        )
        work = {
            row["artifact"]: row
            for row in GATE.rebind_report(gate, ["knowledge-baseline.json"])["work"]
        }
        self.assertLess(work["SOURCE_REPORT"]["order"], work["DESIGN"]["order"])

    def test_reviewed_baseline_does_not_bypass_new_source_drift(self):
        self.adopt_reviewed_baseline()
        header = (
            self.fixture.hcomm_repo
            / "src/base_comm/resources/ccu/ccu_transport/ccu_transport_.h"
        )
        header.write_text(header.read_text() + "// new unreviewed change\n")
        generator = (
            self.fixture.hcomm_repo
            / "src/base_comm/resources/ccu/ccu_representation/reps/translator/ccu_ins_generator_v1.h"
        )
        generator.write_text(generator.read_text() + "// new unreviewed change\n")
        self.assertTrue({"CCU_SYNC_CHECK", "CCU_ARITH_CHECK"} <= self.codes())

    def test_optional_baseline_is_required_hashed_confined_and_architect_owned(self):
        selected = self.adopt_reviewed_baseline()
        outside = Path(self.temp.name) / "outside-baseline.json"
        outside.write_bytes(selected.read_bytes())
        selected.unlink()
        self.assertIn("CCU_BASELINE_MISSING", self.codes())
        selected.symlink_to(outside)
        self.assertIn("CCU_PATH", self.codes())
        selected.unlink()
        selected.write_bytes(outside.read_bytes())
        self.fixture.docs["DESIGN"].pop("knowledge_baseline_sha256")
        self.fixture.write_doc("DESIGN", self.fixture.docs["DESIGN"])
        self.assertIn("CCU_BASELINE_HASH", self.codes())
        for actor in (
            "hccl-architect",
            "hccl-developer",
            "hccl-reviewer",
            "hccl-verifier",
        ):
            gate = Validator(self.fixture.task_dir, self.skill)
            gate.validate_actor(actor, [str(selected)])
            self.assertEqual(actor != "hccl-architect", bool(gate.problems))

    def test_source_inventory_must_bind_the_selected_knowledge_baseline(self):
        self.adopt_reviewed_baseline()
        source = self.fixture.task_dir / "source-report.json"
        data = json.loads(source.read_text())
        data["knowledge"]["baseline_sha256"] = "0" * 64
        source.write_text(json.dumps(data))
        self.fixture.rewrite_doc("DESIGN", source_report_sha256=sha256(source))
        self.refresh_bindings()
        self.assertIn("CCU_BASELINE_SOURCE", self.codes())
        gate = Validator(self.fixture.task_dir, self.skill)
        gate.load_index()
        self.assertIn(
            ("SOURCE_REPORT", "baseline_sha256"),
            {(row["artifact"], row["field"]) for row in GATE.verify_rebind(gate)},
        )

    def test_optional_checker_plan_binding_survives_full_dependency_chain(self):
        plan = self.fixture.task_dir / "checker-plan.json"
        plan.write_text(
            json.dumps({"schema_version": 1, "batches": [{"id": "frozen-batch"}]})
        )
        self.fixture.rewrite_doc("TEST_PLAN", checker_plan_sha256=sha256(plan))
        self.fixture.write_baseline()
        self.fixture.write_development_log()
        self.fixture.write_review()
        self.fixture.write_test_report()
        self.fixture.write_index()
        path = self.fixture.task_dir / "task-index.json"
        index = json.loads(path.read_text())
        index["ccu_contract_version"] = 3
        index["calls"][0]["outputs"] += self.fixture.task_outputs(
            "sync-contract.json", "checker-plan.json"
        )
        path.write_text(json.dumps(index))
        self.assertEqual(set(), self.codes())
        plan.write_text(plan.read_text() + "\n")
        self.assertIn("CCU_CHECKER_PLAN_HASH", self.codes())
        gate = Validator(self.fixture.task_dir, self.skill)
        gate.load_index()
        self.assertIn(
            "checker_plan_sha256", {row["field"] for row in GATE.verify_rebind(gate)}
        )
        self.assertEqual(
            "TEST_PLAN",
            GATE.rebind_report(gate, ["CHECKER_PLAN"])["work"][0]["artifact"],
        )

    def test_optional_plan_without_binding_or_with_escaping_path_blocks(self):
        plan = self.fixture.task_dir / "checker-plan.json"
        plan.write_text('{"schema_version":1,"batches":[{"id":"batch"}]}')
        self.assertIn("CCU_CHECKER_PLAN_HASH", self.codes())
        outside = Path(self.temp.name) / "outside-plan.json"
        outside.write_bytes(plan.read_bytes())
        plan.unlink()
        plan.symlink_to(outside)
        self.assertIn("CCU_PATH", self.codes())

    def test_checker_plan_owner_is_architect(self):
        gate = Validator(self.fixture.task_dir, self.skill)
        gate.validate_actor(
            "hccl-architect", self.fixture.task_outputs("checker-plan.json")
        )
        self.assertEqual([], gate.problems)
        other = Validator(self.fixture.task_dir, self.skill)
        other.validate_actor(
            "hccl-verifier", self.fixture.task_outputs("checker-plan.json")
        )
        self.assertTrue(other.problems)


class CcuWorkflowCliTests(unittest.TestCase):
    def run_gate(self, fixture, state):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "validate_ccu_artifacts.py"),
                "--task-dir",
                str(fixture.task_dir),
                "--ccu-skill-dir",
                str(SKILL),
                "--target-state",
                state,
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def check_transition(self, fixture, role, target):
        policy = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "workflow_policy.py"),
                "transition",
                "--engine",
                "CCU",
                "--state",
                fixture.current_state,
                "--actor",
                role,
                "--result",
                "PASS",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, policy.returncode, policy.stdout + policy.stderr)
        self.assertEqual(target, json.loads(policy.stdout)["next_state"])

    def test_incremental_cli_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = CcuFixture(
                Path(temp),
                build_complete=False,
                current_identity=TaskFixture.design_identity,
            )
            self.run_gate(fixture, "ENV_READY")
            stages = [
                (
                    "hccl-architect",
                    "DESIGN_READY",
                    lambda: fixture.write_design_inputs(True),
                ),
                ("hccl-verifier", "BASELINE_READY", fixture.write_baseline),
                ("hccl-developer", "IMPLEMENTED", fixture.write_development_log),
                ("hccl-reviewer", "REVIEW_PASS", fixture.write_review),
                ("hccl-verifier", "TEST_PASS", fixture.write_test_report),
            ]
            for number, (role, target, write) in enumerate(stages):
                if target == "IMPLEMENTED":
                    fixture.current_identity = "main@ccu-candidate+hcomm@unchanged"
                write()
                fixture.write_handoff(role)
                fixture.calls.append(fixture.build_calls()[number])
                fixture.write_index()
                self.check_transition(fixture, role, target)
                self.run_gate(fixture, target)
                fixture.current_state = target
                fixture.write_index()
                self.run_gate(fixture, target)
            self.run_gate(fixture, "COMPLETE")


if __name__ == "__main__":
    unittest.main()
