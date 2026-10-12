#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms of the
# CANN Open Software License Agreement Version 2.0 (the "License").
"""End-to-end dry-runs for the AICPU multi-Agent workflow.

The scenarios use a temporary Git repository and synthetic build/test evidence.
They execute the public policy and artifact-gate CLIs, but never invoke a real
HCCL or CANN build.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from test_validate_aicpu_artifacts import CallEvidence, TaskFixture


WORKFLOW_DIR = Path(__file__).resolve().parents[1]
POLICY = WORKFLOW_DIR / "scripts" / "workflow_policy.py"
ARTIFACT_GATE = WORKFLOW_DIR / "scripts" / "validate_aicpu_artifacts.py"
SOURCE_REL = Path("src/ops/all_reduce/template/aicpu/ins_temp_all_reduce_e2e.cc")


class AicpuDryRun:
    """Drive one synthetic task through the same CLI gates as HCCLBot."""

    def __init__(self, root: Path, environment_ok: bool = True):
        self.root = root
        self.source_repo = root / "hccl"
        self.source_file = self.source_repo / SOURCE_REL
        self._init_git_repo()

        self.branch = self._git("branch", "--show-current")
        self.head = self._git("rev-parse", "HEAD")
        self.base_identity = f"{self.branch}@{self.head}+clean"
        self.fixture = TaskFixture(
            root,
            build_complete=False,
            source_repo=self.source_repo,
            design_identity=self.base_identity,
            current_identity=self.base_identity,
        )
        self.fixture.source_branch = self.branch
        self.fixture.source_head = self.head
        # Task artifacts intentionally live inside the source repository.
        self.fixture.source_worktree = "DIRTY"
        self.sequence = 0
        self.call_number = 0

        route = self._policy(
            "route",
            "--requirement",
            "Implement an AICPU AllReduce algorithm",
        )
        self._expect(route, action="ROUTE", engine="AICPU")

        if not environment_ok:
            self.fixture.write_environment("FAIL")
        self._sync_index(
            self.task_outputs("task-index.json", "environment.md"),
        )
        if environment_ok:
            self._gate_state("ENV_READY")
        else:
            failed = self._gate_state("ENV_READY", expect_ok=False)
            codes = {item["code"] for item in failed["errors"]}
            if not codes.intersection({"ARTIFACT_NOT_READY", "ARTIFACT_STATUS", "PASS_INVARIANT"}):
                raise AssertionError(f"environment failure was not rejected: {failed}")
            self.fixture.pending_action = "BLOCKED"
            self._sync_index(self.task_outputs("task-index.json"))

    @staticmethod
    def _expect(payload: dict[str, Any], **expected: object) -> None:
        for key, value in expected.items():
            if payload.get(key) != value:
                raise AssertionError(f"expected {key}={value!r}, got {payload.get(key)!r}: {payload}")

    @staticmethod
    def _run_json(
        script: Path,
        *args: str,
        expect_ok: bool = True,
    ) -> dict[str, Any]:
        result = subprocess.run(
            [sys.executable, str(script), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"{script.name} did not emit JSON\nstdout={result.stdout}\nstderr={result.stderr}"
            ) from exc
        if expect_ok and (result.returncode != 0 or payload.get("ok") is False):
            raise AssertionError(
                f"{script.name} failed ({result.returncode})\n{json.dumps(payload, indent=2)}\n{result.stderr}"
            )
        if not expect_ok and (result.returncode == 0 or payload.get("ok") is not False):
            raise AssertionError(f"{script.name} unexpectedly passed: {payload}")
        return payload

    def baseline(self) -> None:
        self.fixture.write_baseline()
        outputs = self.task_outputs("BASELINE_REPORT.md", "HANDOFF.md")
        self._normal_pass("hccl-verifier", "BASELINE_READY", outputs, self.base_identity)

    def complete(self) -> None:
        decision = self._transition("hcclbot", "PASS")
        self._expect(decision, action="ADVANCE", next_state="COMPLETE")
        self._gate_state("COMPLETE")
        self._apply_decision(decision)
        self._sync_index(self.task_outputs("task-index.json"))
        self._gate_state("COMPLETE")

    def design(self) -> None:
        self.fixture.write_design_inputs(dataflow_required=False)
        outputs = self.task_outputs(
            "TASK_SPEC.md",
            "DATAFLOW_SPEC.md",
            "DESIGN.md",
            "PLAN.md",
            "TEST_PLAN.md",
            "HANDOFF.md",
        )
        self._normal_pass("hccl-architect", "DESIGN_READY", outputs, self.base_identity)

    def develop(self, label: str = "initial implementation") -> None:
        self._change_source(label)
        self.fixture.write_development_log()
        outputs = self.task_outputs("LOG.md", "HANDOFF.md") + [SOURCE_REL.as_posix()]
        self._normal_pass(
            "hccl-developer",
            "IMPLEMENTED",
            outputs,
            self.fixture.current_identity,
        )

    def fail_review(self) -> None:
        self.fixture.write_review()
        self.fixture.rewrite_doc(
            "REVIEW",
            status="REVIEW_FAIL",
            blocking_issue_count=1,
        )
        outputs = self.task_outputs("REVIEW.md", "HANDOFF.md")
        self.write_handoff("hccl-reviewer", "REVIEW_FAIL")
        self._recordcall(
            "hccl-reviewer",
            "REVIEW_PASS",
            self.fixture.current_identity,
            outputs,
            "REVIEW_FAIL",
        )
        self._sync_index(self.task_outputs("task-index.json"))
        self._gate_actor("hccl-reviewer", outputs)

        decision = self._transition("hccl-reviewer", "REVIEW_FAIL")
        self._expect(
            decision,
            action="REPAIR",
            next_state="IMPLEMENTED",
            next_roles=["hccl-developer", "hccl-reviewer"],
            repair_round=1,
        )
        self._apply_decision(decision)
        self._sync_index(self.task_outputs("task-index.json"))
        rejected = self._gate_state("REVIEW_PASS", expect_ok=False)
        if "PENDING_ACTION" not in {item["code"] for item in rejected["errors"]}:
            raise AssertionError(f"active review recovery passed the state gate: {rejected}")

    def fail_source_test(self) -> None:
        self.fixture.write_test_report()
        self.fixture.rewrite_doc(
            "TEST_REPORT",
            status="TEST_FAIL",
            build_pass=False,
            track_a_pass=False,
            track_b_pass=False,
            test_failure_count=1,
        )
        outputs = self.task_outputs("TEST_REPORT.md", "HANDOFF.md")
        self.write_handoff("hccl-verifier", "TEST_FAIL")
        self._recordcall(
            "hccl-verifier",
            "TEST_PASS",
            self.fixture.current_identity,
            outputs,
            "TEST_FAIL",
        )
        self._sync_index(self.task_outputs("task-index.json"))
        self._gate_actor("hccl-verifier", outputs)

        decision = self._transition("hccl-verifier", "TEST_FAIL", "SOURCE")
        self._expect(
            decision,
            action="REPAIR",
            next_state="IMPLEMENTED",
            next_roles=["hccl-developer", "hccl-reviewer", "hccl-verifier"],
            repair_round=1,
        )
        self._apply_decision(decision)
        self._sync_index(self.task_outputs("task-index.json"))
        rejected = self._gate_state("TEST_PASS", expect_ok=False)
        if "PENDING_ACTION" not in {item["code"] for item in rejected["errors"]}:
            raise AssertionError(f"active test recovery passed the state gate: {rejected}")

    def repair_after_review_failure(self) -> None:
        self._change_source("repair review finding")
        self.fixture.invalidated.append(
            {"artifact": "REVIEW", "path": "REVIEW.md", "reason": "source changed during review repair"}
        )
        self.fixture.write_development_log()
        self.fixture.rewrite_doc("DEVELOPMENT_LOG", round=self.fixture.repair_round + 1)
        developer_outputs = self.task_outputs("LOG.md", "HANDOFF.md") + [SOURCE_REL.as_posix()]
        self._recovery_pass(
            "hccl-developer",
            "IMPLEMENTED",
            developer_outputs,
            valid_overrides={"REVIEW": False},
        )

        self.fixture.write_review()
        self.fixture.rewrite_doc("REVIEW", round=self.fixture.repair_round + 1)
        reviewer_outputs = self.task_outputs("REVIEW.md", "HANDOFF.md")
        decision = self._recovery_pass(
            "hccl-reviewer",
            "REVIEW_PASS",
            reviewer_outputs,
        )
        self._expect(decision, action="RECOVERY_COMPLETE", next_state="REVIEW_PASS")
        self._gate_state("REVIEW_PASS")

    def repair_after_source_test_failure(self) -> None:
        self._change_source("repair source test failure")
        self.fixture.invalidated.extend(
            (
                {"artifact": "REVIEW", "path": "REVIEW.md", "reason": "source changed after test"},
                {"artifact": "TEST_REPORT", "path": "TEST_REPORT.md", "reason": "source changed after test"},
            )
        )
        self.fixture.write_development_log()
        self.fixture.rewrite_doc("DEVELOPMENT_LOG", round=self.fixture.repair_round + 1)
        developer_outputs = self.task_outputs("LOG.md", "HANDOFF.md") + [SOURCE_REL.as_posix()]
        self._recovery_pass(
            "hccl-developer",
            "IMPLEMENTED",
            developer_outputs,
            valid_overrides={"REVIEW": False, "TEST_REPORT": False},
        )

        self.fixture.write_review()
        self.fixture.rewrite_doc("REVIEW", round=self.fixture.repair_round + 1)
        reviewer_outputs = self.task_outputs("REVIEW.md", "HANDOFF.md")
        self._recovery_pass(
            "hccl-reviewer",
            "REVIEW_PASS",
            reviewer_outputs,
            valid_overrides={"TEST_REPORT": False},
        )

        self.fixture.write_test_report()
        self.fixture.rewrite_doc("TEST_REPORT", round=self.fixture.repair_round + 1)
        verifier_outputs = self.task_outputs("TEST_REPORT.md", "HANDOFF.md")
        decision = self._recovery_pass(
            "hccl-verifier",
            "TEST_PASS",
            verifier_outputs,
        )
        self._expect(decision, action="RECOVERY_COMPLETE", next_state="TEST_PASS")
        self._gate_state("TEST_PASS")

    def review(self) -> None:
        self.fixture.write_review()
        outputs = self.task_outputs("REVIEW.md", "HANDOFF.md")
        self._normal_pass(
            "hccl-reviewer",
            "REVIEW_PASS",
            outputs,
            self.fixture.current_identity,
        )

    def task_outputs(self, *names: str) -> list[str]:
        return self.fixture.task_outputs(*names)

    def verify(self) -> None:
        self.fixture.write_test_report()
        outputs = self.task_outputs("TEST_REPORT.md", "HANDOFF.md")
        self._normal_pass(
            "hccl-verifier",
            "TEST_PASS",
            outputs,
            self.fixture.current_identity,
        )

    def write_handoff(self, actor: str, status: str, identity: str | None = None) -> None:
        self.sequence += 1
        self.fixture.write_handoff(
            actor,
            status=status,
            sequence=self.sequence,
            source_identity=identity or self.fixture.current_identity,
        )

    def _apply_decision(self, decision: dict[str, Any]) -> None:
        self.fixture.current_state = decision["next_state"]
        self.fixture.repair_round = decision["repair_round"]
        self.fixture.pending_action = decision["pending_action"]
        if decision["pending_action"] in {"REPAIR", "REDESIGN"}:
            self.fixture.pending_roles = list(decision["next_roles"])
        else:
            self.fixture.pending_roles = []

    def _change_source(self, label: str) -> None:
        with self.source_file.open("a", encoding="utf-8") as stream:
            stream.write(f"// {label}\n")
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--", SOURCE_REL.as_posix()],
            cwd=self.source_repo,
            check=True,
            capture_output=True,
        ).stdout
        if not diff:
            raise AssertionError("source mutation did not produce a Git diff")
        digest = hashlib.sha256(diff).hexdigest()[:16]
        self.fixture.current_identity = f"{self.branch}@{self.head}+diff:{digest}"
        self.fixture.source_worktree = "DIRTY"

    def _gate_actor(self, actor: str, changed: list[str]) -> None:
        self._run_json(
            ARTIFACT_GATE,
            "--task-dir",
            str(self.fixture.task_dir),
            "--actor",
            actor,
            "--changed",
            *changed,
            "--json",
        )

    def _gate_state(self, state: str, expect_ok: bool = True) -> dict[str, Any]:
        return self._run_json(
            ARTIFACT_GATE,
            "--task-dir",
            str(self.fixture.task_dir),
            "--target-state",
            state,
            "--json",
            expect_ok=expect_ok,
        )

    def _git(self, *args: str) -> str:
        return self._git_run(*args).stdout.strip()

    def _git_run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.source_repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def _init_git_repo(self) -> None:
        self.source_file.parent.mkdir(parents=True)
        self.source_file.write_text("// tracked AICPU source fixture\n", encoding="utf-8")
        self._git_run("init")
        self._git_run("config", "user.name", "HCCL Workflow Dry Run")
        self._git_run("config", "user.email", "hccl-workflow@example.invalid")
        self._git_run("add", SOURCE_REL.as_posix())
        self._git_run("commit", "-m", "seed dry-run source")

    def _normal_pass(
        self,
        actor: str,
        target_state: str,
        outputs: list[str],
        identity: str,
    ) -> None:
        self.write_handoff(actor, "PASS", identity)
        self._recordcall(actor, target_state, identity, outputs, "PASS")
        self._sync_index(self.task_outputs("task-index.json"))
        self._gate_actor(actor, outputs)

        decision = self._transition(actor, "PASS")
        self._expect(decision, action="ADVANCE", next_state=target_state)
        self._gate_state(target_state)
        self._apply_decision(decision)
        self._sync_index(self.task_outputs("task-index.json"))

    def _policy(self, *args: str) -> dict[str, Any]:
        return self._run_json(POLICY, *args, "--json")

    def _recordcall(
        self,
        actor: str,
        target_state: str,
        identity: str,
        outputs: list[str],
        status: str,
    ) -> None:
        self.call_number += 1
        self.fixture.calls.append(
            self.fixture.call(
                f"dry-run-{self.call_number}",
                actor,
                target_state,
                CallEvidence(identity, outputs, status),
            )
        )

    def _recovery_pass(
        self,
        actor: str,
        target_state: str,
        outputs: list[str],
        valid_overrides: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        pending_roles = list(self.fixture.pending_roles)
        pending_action = self.fixture.pending_action
        identity = self.fixture.current_identity
        self.write_handoff(actor, "PASS", identity)
        self._recordcall(actor, target_state, identity, outputs, "PASS")
        self._sync_index(self.task_outputs("task-index.json"), valid_overrides)
        self._gate_actor(actor, outputs)

        decision = self._policy(
            "recovery",
            "--engine",
            "AICPU",
            "--state",
            self.fixture.current_state,
            "--pending-action",
            pending_action,
            "--pending-roles",
            *pending_roles,
            "--actor",
            actor,
            "--result",
            "PASS",
            "--repair-round",
            str(self.fixture.repair_round),
        )
        self._apply_decision(decision)
        self._sync_index(self.task_outputs("task-index.json"), valid_overrides)
        return decision

    def _sync_index(
        self,
        hcclbot_changed: list[str],
        valid_overrides: dict[str, bool] | None = None,
    ) -> None:
        self.fixture.write_index(valid_overrides)
        self._gate_actor("hcclbot", hcclbot_changed)

    def _transition(
        self,
        actor: str,
        result: str,
        failure_class: str | None = None,
    ) -> dict[str, Any]:
        args = [
            "transition",
            "--engine",
            "AICPU",
            "--state",
            self.fixture.current_state,
            "--actor",
            actor,
            "--result",
            result,
            "--repair-round",
            str(self.fixture.repair_round),
        ]
        if failure_class:
            args.extend(("--failure-class", failure_class))
        return self._policy(*args)


@unittest.skipUnless(shutil.which("git"), "requires git")
class AicpuWorkflowEndToEndDryRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_environment_failure_blocks_before_any_agentcall(self) -> None:
        run = AicpuDryRun(self.root, environment_ok=False)

        self.assertEqual("BLOCKED", run.fixture.pending_action)
        self.assertEqual([], run.fixture.calls)
        self.assertEqual({"ENVIRONMENT"}, set(run.fixture.docs))


    def test_happy_path_reaches_complete_through_public_clis(self) -> None:
        run = AicpuDryRun(self.root)
        run.design()
        run.baseline()
        run.develop()
        run.review()
        run.verify()
        run.complete()

        self.assertEqual("COMPLETE", run.fixture.current_state)
        self.assertEqual("NONE", run.fixture.pending_action)
        index = json.loads((run.fixture.task_dir / "task-index.json").read_text(encoding="utf-8"))
        self.assertEqual(run.branch, index["source_branch"])
        self.assertEqual(run.head, index["source_head"])
        self.assertTrue(index["source_identity"].startswith(f"{run.branch}@{run.head}+diff:"))
        self.assertEqual(
            [
                "hccl-architect",
                "hccl-verifier",
                "hccl-developer",
                "hccl-reviewer",
                "hccl-verifier",
            ],
            [call["role"] for call in run.fixture.calls],
        )

    def test_review_failure_consumes_developer_reviewer_recovery(self) -> None:
        run = AicpuDryRun(self.root)
        run.design()
        run.baseline()
        run.develop()
        run.fail_review()
        run.repair_after_review_failure()
        run.verify()
        run.complete()

        self.assertEqual("COMPLETE", run.fixture.current_state)
        self.assertEqual(1, run.fixture.repair_round)
        self.assertIn("REVIEW", {item["artifact"] for item in run.fixture.invalidated})

    def test_source_test_failure_replays_full_quality_chain(self) -> None:
        run = AicpuDryRun(self.root)
        run.design()
        run.baseline()
        run.develop()
        run.review()
        run.fail_source_test()
        run.repair_after_source_test_failure()
        run.complete()

        self.assertEqual("COMPLETE", run.fixture.current_state)
        self.assertEqual(1, run.fixture.repair_round)
        self.assertEqual(
            {"REVIEW", "TEST_REPORT"},
            {item["artifact"] for item in run.fixture.invalidated},
        )

if __name__ == "__main__":
    unittest.main()
