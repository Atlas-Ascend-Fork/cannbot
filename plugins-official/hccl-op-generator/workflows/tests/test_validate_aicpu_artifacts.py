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
"""Unit tests for the AICPU task artifact gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_aicpu_artifacts.py"
MODULE_SPEC = importlib.util.spec_from_file_location("validate_aicpu_artifacts", SCRIPT)
assert MODULE_SPEC and MODULE_SPEC.loader
GATE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = GATE
MODULE_SPEC.loader.exec_module(GATE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frontmatter(fields: dict[str, object], body: str = "evidence recorded") -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, bool):
            rendered = str(value).lower()
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.extend(("---", "", body, ""))
    return "\n".join(lines)


@dataclass(frozen=True)
class CallEvidence:
    identity: str
    outputs: list[str]
    status: str = "PASS"


class TaskFixture:
    task_id = "all-reduce-aicpu-001"
    design_identity = "main@base+clean"
    current_identity = "main@candidate+diff:1234"

    def __init__(
        self,
        root: Path,
        dataflow_required: bool = False,
        build_complete: bool = True,
        source_repo: Path | None = None,
        design_identity: str | None = None,
        current_identity: str | None = None,
    ):
        self.source_repo = source_repo or root / "hccl"
        self.design_identity = design_identity or type(self).design_identity
        self.current_identity = current_identity or type(self).current_identity
        self.task_dir = (
            self.source_repo / "src" / "ops" / "all_reduce" / "docs" / self.task_id
        )
        self.task_dir.mkdir(parents=True)
        self.external_evidence_root = root / "evidence" / self.task_id
        self.external_evidence_root.mkdir(parents=True)
        self.docs: dict[str, dict[str, object]] = {}
        self.dataflow_specs: list[dict[str, object]] = []
        self.invalidated: list[dict[str, object]] = []
        self.current_state = "ENV_READY"
        self.calls: list[dict[str, object]] = []
        self.source_branch = "main"
        self.source_head = "abcdef1"
        self.source_worktree = "DIRTY"
        self.repair_round = 0
        self.pending_action = "NONE"
        self.pending_roles: list[str] = []
        self.write_environment()
        if not build_complete:
            self.write_index()
            return

        self.write_design_inputs(dataflow_required)
        self.write_baseline()
        self.write_development_log()
        self.write_review()
        self.write_test_report()
        self.write_handoff("hccl-verifier")
        self.current_state = "COMPLETE"
        self.calls = self._build_calls()
        self.write_index()

    @staticmethod
    def call(
        call_id: str,
        role: str,
        target_state: str,
        evidence: CallEvidence,
    ) -> dict[str, object]:
        return {
            "call_id": call_id,
            "role": role,
            "target_state": target_state,
            "status": evidence.status,
            "source_identity": evidence.identity,
            "started_at": "2026-09-15T09:00:00+08:00",
            "ended_at": "2026-09-15T09:05:00+08:00",
            "outputs": evidence.outputs,
        }

    def rewrite_doc(self, name: str, **updates: object) -> None:
        fields = dict(self.docs[name])
        fields.update(updates)
        self.write_doc(name, fields)

    def set_state(self, state: str) -> None:
        owners = GATE.EXPECTED_HANDOFF_OWNER
        if state in owners:
            self.write_handoff(owners[state])
        self.current_state = state
        self.write_index()

    def task_outputs(self, *names: str) -> list[str]:
        task_rel = self.task_dir.relative_to(self.source_repo)
        return [str(task_rel / name) for name in names]

    def write_baseline(self) -> None:
        fields = self._common("BASELINE_REPORT", "hccl-verifier")
        fields.update(
            status="PASS",
            source_identity="installed-old-package@sha256:abcd",
            task_spec_sha256=sha256(self.task_dir / "TASK_SPEC.md"),
            design_sha256=sha256(self.task_dir / "DESIGN.md"),
            test_plan_sha256=sha256(self.task_dir / "TEST_PLAN.md"),
            round=1,
            evidence_complete=True,
            unresolved_failure_count=0,
            install_test_ready=True,
            created_at="2026-09-15T10:00:00+08:00",
        )
        self.write_doc("BASELINE_REPORT", fields)

    def write_design_inputs(self, dataflow_required: bool) -> None:
        for name in ("TASK_SPEC", "DESIGN", "PLAN", "TEST_PLAN"):
            fields = self._common(name, "hccl-architect")
            fields.update(
                status="FROZEN",
                source_identity=self.design_identity,
                artifact_revision=1,
                semantic_tbd_count=0,
                created_at="2026-09-15T09:10:00+08:00",
            )
            self.write_doc(name, fields)

        dataflow = self._common("DATAFLOW_SPEC_INDEX", "hccl-architect")
        dataflow.update(
            status="PASS" if dataflow_required else "NOT_REQUIRED",
            source_identity=self.design_identity,
            artifact_revision=1,
            applicability="REQUIRED" if dataflow_required else "NOT_REQUIRED",
            spec_count=1 if dataflow_required else 0,
            passed_spec_count=1 if dataflow_required else 0,
            semantic_tbd_count=0,
            created_at="2026-09-15T09:10:00+08:00",
        )
        if dataflow_required:
            path = self.task_dir / "dataflow" / "mesh.md"
            path.parent.mkdir()
            path.write_text("# Verified dataflow\n", encoding="utf-8")
            self.dataflow_specs.append(
                {
                    "path": "dataflow/mesh.md",
                    "status": "PASS",
                    "source_identity": self.design_identity,
                    "sha256": sha256(path),
                    "valid": True,
                }
            )
            body = f"dataflow/mesh.md {sha256(path)}"
        else:
            body = "NOT_REQUIRED: no dataflow change"
        self.write_doc("DATAFLOW_SPEC_INDEX", dataflow, body)

    def write_development_log(self) -> None:
        fields = self._common("DEVELOPMENT_LOG", "hccl-developer")
        fields.update(
            status="PASS",
            input_source_identity=self.design_identity,
            output_source_identity=self.current_identity,
            task_spec_sha256=sha256(self.task_dir / "TASK_SPEC.md"),
            dataflow_index_sha256=sha256(self.task_dir / "DATAFLOW_SPEC.md"),
            design_sha256=sha256(self.task_dir / "DESIGN.md"),
            plan_sha256=sha256(self.task_dir / "PLAN.md"),
            baseline_sha256=sha256(self.task_dir / "BASELINE_REPORT.md"),
            round=1,
            static_failure_count=0,
            updated_at="2026-09-15T11:00:00+08:00",
        )
        self.write_doc("DEVELOPMENT_LOG", fields)

    def write_doc(
        self, name: str, fields: dict[str, object], body: str = "evidence recorded"
    ) -> None:
        self.docs[name] = fields
        path = self.task_dir / GATE.ARTIFACTS[name].path
        path.write_text(frontmatter(fields, body), encoding="utf-8")

    def write_environment(self, status: str = "PASS") -> None:
        environment = self._common("ENVIRONMENT", "hcclbot")
        environment.update(
            status=status,
            source_identity=self.design_identity,
            checks_pass=status == "PASS",
            created_at="2026-09-15T09:00:00+08:00",
        )
        self.write_doc("ENVIRONMENT", environment)

    def write_handoff(
        self,
        owner: str,
        status: str = "PASS",
        sequence: int = 5,
        source_identity: str | None = None,
    ) -> None:
        fields = {
            "schema_version": 1,
            "artifact": "HANDOFF_LOG",
            "engine": "AICPU",
            "task_id": self.task_id,
            "owner_policy": "current_stage_agent",
            "latest_sequence": sequence,
            "latest_owner": owner,
            "latest_status": status,
            "latest_source_identity": source_identity or self.current_identity,
            "entry_count": sequence,
            "updated_at": "2026-09-15T13:10:00+08:00",
        }
        self.write_doc("HANDOFF_LOG", fields)

    def write_index(self, valid_overrides: dict[str, bool] | None = None) -> None:
        valid_overrides = valid_overrides or {}
        artifacts = {}
        for name, fields in self.docs.items():
            path = self.task_dir / GATE.ARTIFACTS[name].path
            identity = GATE.Validator.artifact_identity(name, fields)
            owner = (
                fields.get("latest_owner")
                if name == "HANDOFF_LOG"
                else fields.get("owner")
            )
            status = (
                fields.get("latest_status")
                if name == "HANDOFF_LOG"
                else fields.get("status")
            )
            artifacts[name] = {
                "path": GATE.ARTIFACTS[name].path,
                "owner": owner,
                "status": status,
                "source_identity": identity,
                "sha256": sha256(path),
                "valid": valid_overrides.get(name, True),
            }
        index = {
            "schema_version": 1,
            "task_id": self.task_id,
            "engine": "AICPU",
            "requirement": "implement an AICPU AllReduce algorithm",
            "source_repo": str(self.source_repo),
            "source_branch": self.source_branch,
            "source_head": self.source_head,
            "source_worktree": self.source_worktree,
            "source_identity": self.current_identity,
            "external_evidence_roots": [str(self.external_evidence_root)],
            "current_state": self.current_state,
            "repair_round": self.repair_round,
            "pending_action": self.pending_action,
            "pending_roles": self.pending_roles,
            "created_at": "2026-09-15T09:00:00+08:00",
            "updated_at": "2026-09-15T13:10:00+08:00",
            "artifacts": artifacts,
            "dataflow_specs": self.dataflow_specs,
            "calls": self.calls,
            "invalidated_artifacts": self.invalidated,
        }
        (self.task_dir / "task-index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def write_review(self) -> None:
        fields = self._common("REVIEW", "hccl-reviewer")
        fields.update(
            status="PASS",
            source_identity=self.current_identity,
            task_spec_sha256=sha256(self.task_dir / "TASK_SPEC.md"),
            dataflow_index_sha256=sha256(self.task_dir / "DATAFLOW_SPEC.md"),
            design_sha256=sha256(self.task_dir / "DESIGN.md"),
            plan_sha256=sha256(self.task_dir / "PLAN.md"),
            test_plan_sha256=sha256(self.task_dir / "TEST_PLAN.md"),
            baseline_sha256=sha256(self.task_dir / "BASELINE_REPORT.md"),
            round=1,
            blocking_issue_count=0,
            created_at="2026-09-15T12:00:00+08:00",
        )
        self.write_doc("REVIEW", fields)

    def write_estimate(self) -> Path:
        directory = self.external_evidence_root / "estimate"
        directory.mkdir(exist_ok=True)
        files = {}
        for key in (
            "candidate_package",
            "cluster",
            "test_log",
            "plugin_log",
            "profiling",
            "trace",
        ):
            path = directory / key
            path.write_text(f"synthetic {key} evidence\n", encoding="utf-8")
            files[key] = {"path": str(path), "sha256": sha256(path)}
        data = {
            "schema_version": 1,
            "status": "SUCCESS",
            "source_identity": self.current_identity,
            "operator": "allreduce",
            "dtype": "int32",
            "comm_domain": "112",
            "expected_algorithm": "InsAllReduceExample",
            "observed_algorithm": "InsAllReduceExample",
            "makespan_us": 2500.5,
            "parameters": {
                "np": 1,
                "begin": "1G",
                "end": "1G",
                "warmup": 0,
                "iterations": 1,
                "check": 0,
            },
            "exit_codes": {"start": 0, "mock_comm": 0, "mpirun": 0, "estimate": 0},
            "files": files,
        }
        path = directory / "estimate.json"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return path

    def write_test_report(self) -> None:
        estimate = self.write_estimate()
        fields = self._common("TEST_REPORT", "hccl-verifier")
        fields.update(
            status="PASS",
            source_identity=self.current_identity,
            review_source_identity=self.current_identity,
            baseline_sha256=sha256(self.task_dir / "BASELINE_REPORT.md"),
            review_sha256=sha256(self.task_dir / "REVIEW.md"),
            test_plan_sha256=sha256(self.task_dir / "TEST_PLAN.md"),
            round=1,
            build_pass=True,
            track_a_pass=True,
            track_b_pass=True,
            identity_match=True,
            environment_clean=True,
            test_failure_count=0,
            estimate_status="SUCCESS",
            estimate_source_identity=self.current_identity,
            estimate_comm_domain="112",
            estimate_evidence_path=str(estimate),
            estimate_evidence_sha256=sha256(estimate),
            created_at="2026-09-15T13:00:00+08:00",
        )
        self.write_doc("TEST_REPORT", fields)

    def _build_calls(self) -> list[dict[str, object]]:
        stages = (
            (
                "architect-1",
                "hccl-architect",
                "DESIGN_READY",
                self.design_identity,
                self.task_outputs(
                    "TASK_SPEC.md",
                    "DATAFLOW_SPEC.md",
                    "DESIGN.md",
                    "PLAN.md",
                    "TEST_PLAN.md",
                    "HANDOFF.md",
                ),
            ),
            (
                "verifier-baseline-1",
                "hccl-verifier",
                "BASELINE_READY",
                self.design_identity,
                self.task_outputs("BASELINE_REPORT.md", "HANDOFF.md"),
            ),
            (
                "developer-1",
                "hccl-developer",
                "IMPLEMENTED",
                self.current_identity,
                self.task_outputs("LOG.md", "HANDOFF.md")
                + ["src/ops/all_reduce/template/aicpu/new.cc"],
            ),
            (
                "reviewer-1",
                "hccl-reviewer",
                "REVIEW_PASS",
                self.current_identity,
                self.task_outputs("REVIEW.md", "HANDOFF.md"),
            ),
            (
                "verifier-test-1",
                "hccl-verifier",
                "TEST_PASS",
                self.current_identity,
                self.task_outputs("TEST_REPORT.md", "HANDOFF.md"),
            ),
        )
        return [
            self.call(call_id, role, state, CallEvidence(identity, outputs))
            for call_id, role, state, identity, outputs in stages
        ]

    def _common(self, artifact: str, owner: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "artifact": artifact,
            "engine": "AICPU",
            "owner": owner,
            "task_id": self.task_id,
        }


class ArtifactGateTests(unittest.TestCase):
    @staticmethod
    def codes(validator: GATE.Validator) -> set[str]:
        return {problem.code for problem in validator.problems}

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_actor_write_boundaries(self) -> None:
        fixture = TaskFixture(self.root)
        task_rel = fixture.task_dir.relative_to(fixture.source_repo)
        external_log = fixture.external_evidence_root / "candidate" / "build.log"
        cases = (
            ("hccl-architect", [str(task_rel / "DESIGN.md")], False),
            ("hccl-developer", ["src/ops/all_reduce/template/aicpu/new.cc"], False),
            ("hccl-developer", [str(task_rel / "REVIEW.md")], True),
            ("hccl-reviewer", ["src/ops/all_reduce/template/aicpu/new.cc"], True),
            ("hccl-verifier", [str(task_rel / "TEST_REPORT.md")], False),
            ("hccl-verifier", [str(external_log)], False),
            ("hccl-reviewer", [str(external_log)], True),
            ("hccl-verifier", [str(self.root / "unlisted" / "build.log")], True),
        )
        for actor, changed, should_fail in cases:
            with self.subTest(actor=actor, changed=changed):
                validator = GATE.Validator(fixture.task_dir)
                validator.validate_actor(actor, changed)
                self.assertEqual(should_fail, "OWNER_BOUNDARY" in self.codes(validator))

    def test_cli_json_result_and_exit_code(self) -> None:
        fixture = TaskFixture(self.root)
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--task-dir",
                str(fixture.task_dir),
                "--target-state",
                "COMPLETE",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_complete_task_passes(self) -> None:
        fixture = TaskFixture(self.root)
        validator = self.validate(fixture, "COMPLETE")
        self.assertEqual([], validator.problems)

    def test_dataflow_change_requires_current_index_evidence(self) -> None:
        fixture = TaskFixture(self.root, dataflow_required=True)
        path = fixture.task_dir / "dataflow" / "mesh.md"
        path.write_text("# Changed dataflow\n", encoding="utf-8")
        fixture.dataflow_specs[0]["sha256"] = sha256(path)
        fixture.write_index()
        validator = self.validate(fixture, "DESIGN_READY")
        self.assertIn("DATAFLOW_EVIDENCE", self.codes(validator))

    def test_dataflow_path_escape_is_rejected(self) -> None:
        fixture = TaskFixture(self.root, dataflow_required=True)
        fixture.dataflow_specs[0]["path"] = "../outside.md"
        fixture.write_index()
        validator = self.validate(fixture, "DESIGN_READY")
        self.assertIn("DATAFLOW_PATH", self.codes(validator))

    def test_dependency_change_rejects_old_reports(self) -> None:
        fixture = TaskFixture(self.root)
        fixture.write_doc("PLAN", fixture.docs["PLAN"], "semantically changed plan")
        fixture.write_index()
        validator = self.validate(fixture, "COMPLETE")
        self.assertIn("DEPENDENCY_HASH", self.codes(validator))
        self.assertIn("INVALIDATION_REQUIRED", self.codes(validator))

    def test_duplicate_call_id_is_rejected(self) -> None:
        fixture = TaskFixture(self.root)
        fixture.calls[-1]["call_id"] = fixture.calls[-2]["call_id"]
        fixture.write_index()
        validator = self.validate(fixture, "COMPLETE")
        self.assertIn("CALL_ID", self.codes(validator))

    def test_each_intermediate_state_passes(self) -> None:
        fixture = TaskFixture(self.root)
        for state in GATE.STATES[:-1]:
            with self.subTest(state=state):
                fixture.set_state(state)
                validator = self.validate(fixture, state)
                self.assertEqual([], validator.problems)

    def test_external_evidence_root_must_be_narrow_and_external(self) -> None:
        fixture = TaskFixture(self.root)
        index_path = fixture.task_dir / "task-index.json"
        broad_root = self.root / "broad-evidence"
        broad_root.mkdir()
        for invalid_root in (
            "relative/evidence",
            str(self.root),
            str(broad_root),
            str(fixture.source_repo),
        ):
            with self.subTest(invalid_root=invalid_root):
                index = json.loads(index_path.read_text(encoding="utf-8"))
                index["external_evidence_roots"] = [invalid_root]
                index_path.write_text(
                    json.dumps(index, indent=2) + "\n", encoding="utf-8"
                )
                validator = GATE.Validator(fixture.task_dir)
                validator.load_index()
                self.assertIn("INDEX_EXTERNAL_ROOT", self.codes(validator))

    def test_fake_test_pass_is_rejected(self) -> None:
        fixture = TaskFixture(self.root)
        fixture.rewrite_doc("TEST_REPORT", track_b_pass=False, test_failure_count=1)
        fixture.write_index()
        validator = self.validate(fixture, "COMPLETE")
        self.assertIn("PASS_INVARIANT", self.codes(validator))

    def test_index_hash_mismatch_is_rejected(self) -> None:
        fixture = TaskFixture(self.root)
        path = fixture.task_dir / "environment.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "changed\n", encoding="utf-8"
        )
        validator = self.validate(fixture, "COMPLETE")
        self.assertIn("INDEX_HASH", self.codes(validator))

    def test_invalid_state_transition_is_rejected(self) -> None:
        fixture = TaskFixture(self.root)
        validator = self.validate(fixture, "DESIGN_READY")
        self.assertIn("STATE_TRANSITION", self.codes(validator))

    def test_missing_agent_call_is_rejected(self) -> None:
        fixture = TaskFixture(self.root)
        fixture.calls = [
            call for call in fixture.calls if call["target_state"] != "REVIEW_PASS"
        ]
        fixture.write_index()
        validator = self.validate(fixture, "COMPLETE")
        self.assertIn("CALL_REQUIRED", self.codes(validator))

    def test_not_required_dataflow_cannot_index_specs(self) -> None:
        fixture = TaskFixture(self.root)
        fixture.dataflow_specs.append(
            {
                "path": "dataflow/unexpected.md",
                "status": "PASS",
                "source_identity": fixture.design_identity,
                "sha256": "0" * 64,
                "valid": True,
            }
        )
        fixture.write_index()
        validator = self.validate(fixture, "DESIGN_READY")
        self.assertIn("DATAFLOW_NOT_REQUIRED", self.codes(validator))

    def test_pending_repair_cannot_pass_state_gate(self) -> None:
        fixture = TaskFixture(self.root)
        index_path = fixture.task_dir / "task-index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["repair_round"] = 1
        index["pending_action"] = "REPAIR"
        index["pending_roles"] = ["hccl-developer", "hccl-reviewer"]
        index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        validator = self.validate(fixture, "COMPLETE")
        self.assertIn("PENDING_ACTION", self.codes(validator))

    def test_required_dataflow_spec_passes(self) -> None:
        fixture = TaskFixture(self.root, dataflow_required=True)
        validator = self.validate(fixture, "COMPLETE")
        self.assertEqual([], validator.problems)

    def test_stale_reports_must_be_explicitly_invalidated(self) -> None:
        fixture = TaskFixture(self.root)
        fixture.current_identity = "main@candidate-2+diff:5678"
        fixture.rewrite_doc(
            "DEVELOPMENT_LOG", output_source_identity=fixture.current_identity
        )
        fixture.calls.append(
            fixture.call(
                "developer-2",
                "hccl-developer",
                "IMPLEMENTED",
                CallEvidence(
                    fixture.current_identity,
                    fixture.task_outputs("LOG.md", "HANDOFF.md")
                    + ["src/ops/all_reduce/template/aicpu/new.cc"],
                ),
            )
        )
        fixture.set_state("IMPLEMENTED")
        validator = self.validate(fixture, "IMPLEMENTED")
        self.assertIn("INVALIDATION_REQUIRED", self.codes(validator))

        fixture.invalidated = [
            {"artifact": "REVIEW", "path": "REVIEW.md", "reason": "source changed"},
            {
                "artifact": "TEST_REPORT",
                "path": "TEST_REPORT.md",
                "reason": "source changed",
            },
        ]
        fixture.write_index({"REVIEW": False, "TEST_REPORT": False})
        validator = self.validate(fixture, "IMPLEMENTED")
        self.assertEqual([], validator.problems)

    def change_estimate(self, fixture: TaskFixture, **updates: object) -> None:
        path = Path(fixture.docs["TEST_REPORT"]["estimate_evidence_path"])
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(updates)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        fixture.rewrite_doc("TEST_REPORT", estimate_evidence_sha256=sha256(path))
        fixture.write_index()

    def test_estimate_is_required_for_test_pass_and_complete(self) -> None:
        for state in ("TEST_PASS", "COMPLETE"):
            for status in ("FAILED", "NOT_RUN"):
                with self.subTest(state=state, status=status):
                    fixture = TaskFixture(self.root / f"{state}-{status}")
                    fixture.set_state(state)
                    fixture.rewrite_doc("TEST_REPORT", estimate_status=status)
                    fixture.write_index()
                    self.assertIn(
                        "ESTIMATE_STATUS", self.codes(self.validate(fixture, state))
                    )

    def test_old_report_without_estimate_cannot_complete(self) -> None:
        fixture = TaskFixture(self.root)
        fields = {
            key: value
            for key, value in fixture.docs["TEST_REPORT"].items()
            if not key.startswith("estimate_")
        }
        fixture.write_doc("TEST_REPORT", fields)
        fixture.write_index()
        codes = self.codes(self.validate(fixture, "COMPLETE"))
        self.assertIn("ARTIFACT_FIELD", codes)
        self.assertIn("ESTIMATE_STATUS", codes)

    def test_stale_estimate_is_rejected_even_with_current_test_identity(self) -> None:
        fixture = TaskFixture(self.root)
        self.change_estimate(fixture, source_identity=fixture.design_identity)
        self.assertIn(
            "ESTIMATE_IDENTITY", self.codes(self.validate(fixture, "COMPLETE"))
        )

    def test_estimate_report_identity_must_be_current(self) -> None:
        fixture = TaskFixture(self.root)
        fixture.rewrite_doc(
            "TEST_REPORT", estimate_source_identity=fixture.design_identity
        )
        fixture.write_index()
        self.assertIn(
            "ESTIMATE_IDENTITY", self.codes(self.validate(fixture, "COMPLETE"))
        )

    def test_estimate_algorithm_mismatch_is_rejected(self) -> None:
        fixture = TaskFixture(self.root)
        self.change_estimate(fixture, observed_algorithm="OtherAlgorithm")
        self.assertIn(
            "ESTIMATE_ALGORITHM", self.codes(self.validate(fixture, "COMPLETE"))
        )

    def test_user_selected_estimate_domain_is_allowed_with_np_one(self) -> None:
        fixture = TaskFixture(self.root)
        fixture.rewrite_doc("TEST_REPORT", estimate_comm_domain="122")
        self.change_estimate(fixture, comm_domain="122")
        self.assertEqual([], self.validate(fixture, "COMPLETE").problems)

    def test_estimate_domain_must_match_report(self) -> None:
        fixture = TaskFixture(self.root)
        self.change_estimate(fixture, comm_domain="122")
        self.assertIn("ESTIMATE_COMM", self.codes(self.validate(fixture, "COMPLETE")))

    def test_estimate_fixed_parameters_and_exit_codes_are_enforced(self) -> None:
        fixture = TaskFixture(self.root)
        path = Path(fixture.docs["TEST_REPORT"]["estimate_evidence_path"])
        original = json.loads(path.read_text(encoding="utf-8"))
        for key, value in {
            "np": 2,
            "begin": "1M",
            "end": "2G",
            "warmup": 1,
            "iterations": 2,
            "check": 1,
        }.items():
            with self.subTest(parameter=key):
                self.change_estimate(
                    fixture, parameters={**original["parameters"], key: value}
                )
                self.assertIn(
                    "ESTIMATE_PARAMETERS",
                    self.codes(self.validate(fixture, "COMPLETE")),
                )
        self.change_estimate(fixture, parameters=original["parameters"])
        for key in original["exit_codes"]:
            with self.subTest(exit_code=key):
                self.change_estimate(
                    fixture, exit_codes={**original["exit_codes"], key: 1}
                )
                self.assertIn(
                    "ESTIMATE_EXIT", self.codes(self.validate(fixture, "COMPLETE"))
                )

    def test_invalid_estimate_times_are_rejected(self) -> None:
        fixture = TaskFixture(self.root)
        invalid_values = (
            None,
            True,
            False,
            "2500",
            [],
            {},
            0,
            -1,
            float("nan"),
            float("inf"),
            float("-inf"),
        )
        for value in invalid_values:
            with self.subTest(makespan=value):
                self.change_estimate(fixture, makespan_us=value)
                self.assertIn(
                    "ESTIMATE_TIME", self.codes(self.validate(fixture, "COMPLETE"))
                )

    def test_positive_finite_estimate_times_are_allowed(self) -> None:
        fixture = TaskFixture(self.root)
        for value in (1, 0.25, 10**400):
            with self.subTest(makespan=value):
                self.change_estimate(fixture, makespan_us=value)
                self.assertEqual([], self.validate(fixture, "COMPLETE").problems)

    def test_missing_estimate_manifest_is_rejected(self) -> None:
        fixture = TaskFixture(self.root)
        Path(fixture.docs["TEST_REPORT"]["estimate_evidence_path"]).unlink()
        self.assertIn(
            "ESTIMATE_MISSING", self.codes(self.validate(fixture, "COMPLETE"))
        )

    def test_missing_or_tampered_estimate_raw_evidence_is_rejected(self) -> None:
        fixture = TaskFixture(self.root)
        directory = fixture.external_evidence_root / "estimate"
        (directory / "plugin_log").write_text("altered\n", encoding="utf-8")
        (directory / "profiling").unlink()
        codes = self.codes(self.validate(fixture, "COMPLETE"))
        self.assertIn("ESTIMATE_HASH", codes)
        self.assertIn("ESTIMATE_MISSING", codes)

    def test_estimate_evidence_cannot_escape_external_roots(self) -> None:
        fixture = TaskFixture(self.root)
        path = Path(fixture.docs["TEST_REPORT"]["estimate_evidence_path"])
        data = json.loads(path.read_text(encoding="utf-8"))
        outside = self.root / "outside.log"
        outside.write_text("evidence\n", encoding="utf-8")
        data["files"]["test_log"] = {"path": str(outside), "sha256": sha256(outside)}
        self.change_estimate(fixture, files=data["files"])
        self.assertIn("ESTIMATE_PATH", self.codes(self.validate(fixture, "COMPLETE")))

    def test_unresolved_template_placeholder_is_rejected(self) -> None:
        fixture = TaskFixture(self.root)
        fields = fixture.docs["TASK_SPEC"]
        fixture.write_doc("TASK_SPEC", fields, "unresolved: {task_id}")
        fixture.write_index()
        validator = self.validate(fixture, "COMPLETE")
        self.assertIn("PLACEHOLDER", self.codes(validator))

    def test_verifier_call_can_record_allowlisted_external_evidence(self) -> None:
        fixture = TaskFixture(self.root)
        external_log = fixture.external_evidence_root / "candidate" / "build.log"
        fixture.calls[-1]["outputs"].append(str(external_log))
        fixture.write_index()

        validator = self.validate(fixture, "COMPLETE")
        self.assertEqual([], validator.problems)

    def validate(self, fixture: TaskFixture, state: str) -> GATE.Validator:
        validator = GATE.Validator(fixture.task_dir)
        validator.validate_state(state)
        return validator


if __name__ == "__main__":
    unittest.main()
