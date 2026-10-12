#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms of the
# CANN Open Software License Agreement Version 2.0 (the "License").
"""Behavior tests for HCCLBot engine routing and workflow recovery policy."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workflow_policy.py"
WORKFLOW_DIR = SCRIPT.parent.parent
PLUGIN_ROOT = WORKFLOW_DIR.parent
MODULE_SPEC = importlib.util.spec_from_file_location("workflow_policy", SCRIPT)
assert MODULE_SPEC and MODULE_SPEC.loader
POLICY = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = POLICY
MODULE_SPEC.loader.exec_module(POLICY)

Ctx = POLICY.PolicyContext


class RoutingBehaviorTests(unittest.TestCase):
    def test_aiv_is_not_silently_routed_to_aicpu(self) -> None:
        for requirement in ("新增 AIV AllReduce template", "请用AIV实现AllGather"):
            with self.subTest(requirement=requirement):
                decision = POLICY.route_requirement(requirement)
                self.assertFalse(decision.ok)
                self.assertEqual("AIV_OUT_OF_SCOPE", decision.reason)

    def test_all_ccu_markers_are_blocked_until_supported(self) -> None:
        requirements = (
            "新增 CCU Broadcast",
            "请用CCU开发AllReduce算子",
            "实现 CcuSched 调度",
            "实现 CcuMS 算法",
            "修改 ccu_kernel 文件",
            "使用 ccu::LoadArg",
            "使用 CCU_SCHED 模式",
        )
        for requirement in requirements:
            with self.subTest(requirement=requirement):
                decision = POLICY.route_requirement(requirement)
                self.assertFalse(decision.ok)
                self.assertIsNone(decision.engine)
                self.assertEqual("BLOCK", decision.action)
                self.assertEqual("CCU_OUT_OF_SCOPE", decision.reason)

    def test_conflicting_engine_markers_require_clarification(self) -> None:
        decision = POLICY.route_requirement("同时实现 AICPU 和 CCU 算法")
        self.assertFalse(decision.ok)
        self.assertEqual("ASK_ENGINE", decision.action)
        self.assertEqual("CONFLICTING_ENGINE_MARKERS", decision.reason)

    def test_explicit_aicpu_routes_to_new_workflow(self) -> None:
        decision = POLICY.route_requirement("新增 AICPU AllReduce Mesh 算法")
        self.assertTrue(decision.ok)
        self.assertEqual("AICPU", decision.engine)
        self.assertEqual("aicpu-multi-agent-workflow.md", decision.workflow)
        self.assertEqual("EXPLICIT_AICPU_MARKER", decision.reason)

    def test_hostdpu_is_not_silently_routed_to_aicpu(self) -> None:
        for requirement in ("新增 HostDPU AllReduce", "请用HOST DPU实现AllGather", "修改 DPU 模板"):
            with self.subTest(requirement=requirement):
                decision = POLICY.route_requirement(requirement)
                self.assertFalse(decision.ok)
                self.assertEqual("HOSTDPU_OUT_OF_SCOPE", decision.reason)


    def test_standard_op_without_engine_defaults_to_aicpu(self) -> None:
        decision = POLICY.route_requirement("为 AllGather 新增 Ring 标准通信算法")
        self.assertTrue(decision.ok)
        self.assertEqual("AICPU", decision.engine)
        self.assertEqual("DEFAULT_STANDARD_OP_TO_AICPU", decision.reason)


class AicpuTransitionBehaviorTests(unittest.TestCase):
    def test_baseline_failure_blocks_candidate_build(self) -> None:
        decision = POLICY.transition(Ctx("AICPU", "DESIGN_READY"), "hccl-verifier", "FAIL")
        self.assertTrue(decision.ok)
        self.assertEqual("BLOCK", decision.action)
        self.assertEqual("BASELINE_FAILED", decision.reason)
        self.assertEqual((), decision.next_roles)

    def test_design_issue_retries_architect_without_consuming_repair_round(self) -> None:
        decision = POLICY.transition(
            Ctx("AICPU", "ENV_READY", 2), "hccl-architect", "DESIGN_ISSUE"
        )
        self.assertTrue(decision.ok)
        self.assertEqual("RETRY_DESIGN", decision.action)
        self.assertEqual(("hccl-architect",), decision.next_roles)
        self.assertEqual(2, decision.repair_round)

    def test_developer_design_issue_resets_to_design(self) -> None:
        decision = POLICY.transition(
            Ctx("AICPU", "BASELINE_READY"), "hccl-developer", "DESIGN_ISSUE"
        )
        self.assertTrue(decision.ok)
        self.assertEqual("REDESIGN", decision.action)
        self.assertEqual("ENV_READY", decision.next_state)
        self.assertEqual(("hccl-architect",), decision.next_roles)

    def test_environment_test_failure_does_not_call_developer(self) -> None:
        decision = POLICY.transition(
            Ctx("AICPU", "REVIEW_PASS", failure_class="ENVIRONMENT"),
            "hccl-verifier",
            "TEST_FAIL",
        )
        self.assertTrue(decision.ok)
        self.assertEqual("BLOCK", decision.action)
        self.assertEqual("TEST_ENVIRONMENT_BLOCKED", decision.reason)
        self.assertEqual((), decision.next_roles)

    def test_happy_path_uses_four_roles_and_hcclbot_in_order(self) -> None:
        cases = (
            ("ENV_READY", "hccl-architect", "DESIGN_READY", "hccl-verifier"),
            ("DESIGN_READY", "hccl-verifier", "BASELINE_READY", "hccl-developer"),
            ("BASELINE_READY", "hccl-developer", "IMPLEMENTED", "hccl-reviewer"),
            ("IMPLEMENTED", "hccl-reviewer", "REVIEW_PASS", "hccl-verifier"),
            ("REVIEW_PASS", "hccl-verifier", "TEST_PASS", "hcclbot"),
            ("TEST_PASS", "hcclbot", "COMPLETE", None),
        )
        for state, actor, next_state, next_role in cases:
            with self.subTest(state=state):
                decision = POLICY.transition(Ctx("AICPU", state), actor, "PASS")
                self.assertTrue(decision.ok)
                self.assertEqual("ADVANCE", decision.action)
                self.assertEqual(next_state, decision.next_state)
                self.assertEqual((next_role,) if next_role else (), decision.next_roles)

    def test_result_from_wrong_stage_is_rejected(self) -> None:
        decision = POLICY.transition(Ctx("AICPU", "ENV_READY"), "hccl-architect", "REVIEW_FAIL")
        self.assertFalse(decision.ok)
        self.assertEqual("RESULT_NOT_ALLOWED_FOR_STAGE", decision.reason)

    def test_review_failure_routes_only_to_developer_then_reviewer(self) -> None:
        decision = POLICY.transition(
            Ctx("AICPU", "IMPLEMENTED", 0), "hccl-reviewer", "REVIEW_FAIL"
        )
        self.assertTrue(decision.ok)
        self.assertEqual("REPAIR", decision.action)
        self.assertEqual(("hccl-developer", "hccl-reviewer"), decision.next_roles)
        self.assertEqual(1, decision.repair_round)

    def test_shared_third_repair_is_allowed_but_fourth_is_blocked(self) -> None:
        third = POLICY.transition(
            Ctx("AICPU", "IMPLEMENTED", 2), "hccl-reviewer", "REVIEW_FAIL"
        )
        self.assertEqual("REPAIR", third.action)
        self.assertEqual(3, third.repair_round)

        fourth = POLICY.transition(
            Ctx("AICPU", "REVIEW_PASS", third.repair_round, "SOURCE"),
            "hccl-verifier",
            "TEST_FAIL",
        )
        self.assertTrue(fourth.ok)
        self.assertEqual("BLOCK", fourth.action)
        self.assertEqual("REPAIR_LIMIT_REACHED", fourth.reason)
        self.assertEqual(3, fourth.repair_round)

    def test_source_test_failure_repeats_develop_review_verify_chain(self) -> None:
        decision = POLICY.transition(
            Ctx("AICPU", "REVIEW_PASS", 1, "SOURCE"),
            "hccl-verifier",
            "TEST_FAIL",
        )
        self.assertTrue(decision.ok)
        self.assertEqual("REPAIR", decision.action)
        self.assertEqual("IMPLEMENTED", decision.next_state)
        self.assertEqual(
            ("hccl-developer", "hccl-reviewer", "hccl-verifier"),
            decision.next_roles,
        )
        self.assertEqual(2, decision.repair_round)

    def test_stage_owner_overreach_is_rejected(self) -> None:
        cases = (
            ("ENV_READY", "hccl-developer"),
            ("DESIGN_READY", "hccl-architect"),
            ("IMPLEMENTED", "hccl-verifier"),
            ("REVIEW_PASS", "hccl-developer"),
            ("TEST_PASS", "hccl-verifier"),
        )
        for state, actor in cases:
            with self.subTest(state=state, actor=actor):
                decision = POLICY.transition(Ctx("AICPU", state), actor, "PASS")
                self.assertFalse(decision.ok)
                self.assertEqual("STAGE_OWNER_VIOLATION", decision.reason)

    def test_terminal_state_cannot_dispatch_another_role(self) -> None:
        decision = POLICY.transition(Ctx("AICPU", "COMPLETE"), "hcclbot", "PASS")
        self.assertFalse(decision.ok)
        self.assertEqual("TERMINAL_STATE", decision.reason)


    def test_test_failure_without_classification_is_rejected(self) -> None:
        decision = POLICY.transition(
            Ctx("AICPU", "REVIEW_PASS"), "hccl-verifier", "TEST_FAIL"
        )
        self.assertFalse(decision.ok)
        self.assertEqual("FAILURE_CLASS_REQUIRED", decision.reason)


class CcuCompatibilityBehaviorTests(unittest.TestCase):
    def test_archived_ccu_prompts_use_canonical_machine_statuses(self) -> None:
        prompt = (WORKFLOW_DIR / "task-prompts.md").read_text(encoding="utf-8")
        self.assertIn("CCU 专属 Skill 已移除", prompt)
        self.assertNotIn("返回 design_issue", prompt)
        self.assertNotIn("PASS WITH NOTES", prompt)
        self.assertIn("TEST_FAIL", prompt)
        self.assertIn("failure_class=SOURCE", prompt)
        self.assertIn("PASS_WITH_NOTES", prompt)

    def test_ccu_environment_failure_blocks_source_repair(self) -> None:
        decision = POLICY.transition(
            Ctx("CCU", "IMPLEMENTED", failure_class="ENVIRONMENT"),
            "hccl-verifier",
            "FAIL",
        )
        self.assertEqual("BLOCK", decision.action)
        self.assertEqual((), decision.next_roles)


    def test_ccu_happy_path_keeps_legacy_order(self) -> None:
        cases = (
            ("ENV_READY", "hccl-architect", "PASS", "DESIGN_READY"),
            ("DESIGN_READY", "hccl-developer", "PASS", "IMPLEMENTED"),
            ("IMPLEMENTED", "hccl-verifier", "PASS", "VERIFIED"),
            ("VERIFIED", "hccl-reviewer", "PASS_WITH_NOTES", "REVIEW_PASS"),
            ("REVIEW_PASS", "hcclbot", "PASS", "COMPLETE"),
        )
        for state, actor, result, next_state in cases:
            with self.subTest(state=state):
                decision = POLICY.transition(Ctx("CCU", state), actor, result)
                self.assertTrue(decision.ok)
                self.assertEqual("ADVANCE", decision.action)
                self.assertEqual(next_state, decision.next_state)

    def test_ccu_review_failure_repeats_full_quality_chain(self) -> None:
        decision = POLICY.transition(
            Ctx("CCU", "VERIFIED", 1), "hccl-reviewer", "FAIL"
        )
        self.assertEqual("REPAIR", decision.action)
        self.assertEqual(
            ("hccl-developer", "hccl-verifier", "hccl-reviewer"),
            decision.next_roles,
        )
        self.assertEqual("IMPLEMENTED", decision.next_state)

    def test_ccu_source_test_failure_rechecks_verifier(self) -> None:
        decision = POLICY.transition(
            Ctx("CCU", "IMPLEMENTED", failure_class="SOURCE"),
            "hccl-verifier",
            "TEST_FAIL",
        )
        self.assertEqual("REPAIR", decision.action)
        self.assertEqual(("hccl-developer", "hccl-verifier"), decision.next_roles)

    def test_ccu_verifier_design_issue_is_not_a_valid_legacy_result(self) -> None:
        decision = POLICY.transition(
            Ctx("CCU", "IMPLEMENTED"), "hccl-verifier", "DESIGN_ISSUE"
        )
        self.assertFalse(decision.ok)
        self.assertEqual("RESULT_NOT_ALLOWED_FOR_STAGE", decision.reason)


class RecoveryChainBehaviorTests(unittest.TestCase):
    def test_failure_during_recovery_consumes_shared_round_budget(self) -> None:
        decision = POLICY.recovery(
            Ctx("AICPU", "IMPLEMENTED", 2),
            "REPAIR",
            ["hccl-reviewer", "hccl-verifier"],
            "hccl-reviewer",
            "REVIEW_FAIL",
        )
        self.assertEqual("REPAIR", decision.action)
        self.assertEqual(3, decision.repair_round)
        self.assertEqual(
            ("hccl-developer", "hccl-reviewer", "hccl-verifier"),
            decision.next_roles,
        )

        blocked = POLICY.recovery(
            Ctx("AICPU", "REVIEW_PASS", 3, "SOURCE"),
            "REPAIR",
            ["hccl-verifier"],
            "hccl-verifier",
            "TEST_FAIL",
        )
        self.assertEqual("BLOCK", blocked.action)
        self.assertEqual("REPAIR_LIMIT_REACHED", blocked.reason)


    def test_recovery_role_cannot_skip_the_pending_head(self) -> None:
        decision = POLICY.recovery(
            Ctx("AICPU", "IMPLEMENTED", 1),
            "REPAIR",
            ["hccl-developer", "hccl-reviewer"],
            "hccl-reviewer",
            "PASS",
        )
        self.assertFalse(decision.ok)
        self.assertEqual("RECOVERY_OWNER_VIOLATION", decision.reason)

    def test_recovery_role_requires_its_expected_state(self) -> None:
        decision = POLICY.recovery(
            Ctx("AICPU", "REVIEW_PASS", 1),
            "REPAIR",
            ["hccl-developer", "hccl-reviewer"],
            "hccl-developer",
            "PASS",
        )
        self.assertFalse(decision.ok)
        self.assertEqual("RECOVERY_STATE_MISMATCH", decision.reason)

    def test_review_repair_chain_is_consumed_in_order(self) -> None:
        repair = POLICY.transition(
            Ctx("AICPU", "IMPLEMENTED"), "hccl-reviewer", "REVIEW_FAIL"
        )
        developer = POLICY.recovery(
            Ctx("AICPU", repair.next_state, repair.repair_round),
            repair.pending_action,
            list(repair.next_roles),
            "hccl-developer",
            "PASS",
        )
        self.assertEqual("CONTINUE_RECOVERY", developer.action)
        self.assertEqual("IMPLEMENTED", developer.next_state)
        self.assertEqual(("hccl-reviewer",), developer.next_roles)

        reviewer = POLICY.recovery(
            Ctx("AICPU", developer.next_state, developer.repair_round),
            developer.pending_action,
            list(developer.next_roles),
            "hccl-reviewer",
            "PASS",
        )
        self.assertEqual("RECOVERY_COMPLETE", reviewer.action)
        self.assertEqual("REVIEW_PASS", reviewer.next_state)
        self.assertEqual("NONE", reviewer.pending_action)
        self.assertEqual((), reviewer.next_roles)

    def test_test_repair_chain_reaches_test_pass(self) -> None:
        decision = POLICY.transition(
            Ctx("AICPU", "REVIEW_PASS", failure_class="SOURCE"),
            "hccl-verifier",
            "TEST_FAIL",
        )
        state = decision.next_state
        pending_action = decision.pending_action
        pending_roles = list(decision.next_roles)
        for actor, expected_state in (
            ("hccl-developer", "IMPLEMENTED"),
            ("hccl-reviewer", "REVIEW_PASS"),
            ("hccl-verifier", "TEST_PASS"),
        ):
            with self.subTest(actor=actor):
                step = POLICY.recovery(
                    Ctx("AICPU", state, decision.repair_round),
                    pending_action,
                    pending_roles,
                    actor,
                    "PASS",
                )
                self.assertTrue(step.ok)
                self.assertEqual(expected_state, step.next_state)
                state = step.next_state
                pending_action = step.pending_action
                pending_roles = list(step.next_roles)
        self.assertEqual("RECOVERY_COMPLETE", step.action)
        self.assertEqual("NONE", pending_action)

    def test_unapproved_recovery_chain_is_rejected(self) -> None:
        decision = POLICY.recovery(
            Ctx("AICPU", "IMPLEMENTED", 1),
            "REPAIR",
            ["hccl-developer", "hccl-verifier"],
            "hccl-developer",
            "PASS",
        )
        self.assertFalse(decision.ok)
        self.assertEqual("INVALID_RECOVERY_CHAIN", decision.reason)


class WorkflowPolicyCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--json"],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_ambiguous_route_has_nonzero_exit_and_json_reason(self) -> None:
        result = self.run_cli("route", "--requirement", "AICPU 与 CCU 混合")
        self.assertEqual(1, result.returncode)
        self.assertEqual("CONFLICTING_ENGINE_MARKERS", json.loads(result.stdout)["reason"])

    def test_business_block_is_valid_policy_decision(self) -> None:
        result = self.run_cli(
            "transition",
            "--engine",
            "AICPU",
            "--state",
            "DESIGN_READY",
            "--actor",
            "hccl-verifier",
            "--result",
            "FAIL",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("BLOCK", json.loads(result.stdout)["action"])

    def test_recovery_cli_consumes_only_first_pending_role(self) -> None:
        result = self.run_cli(
            "recovery",
            "--engine",
            "AICPU",
            "--state",
            "IMPLEMENTED",
            "--pending-action",
            "REPAIR",
            "--pending-roles",
            "hccl-developer",
            "hccl-reviewer",
            "--actor",
            "hccl-developer",
            "--result",
            "PASS",
            "--repair-round",
            "1",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("CONTINUE_RECOVERY", payload["action"])
        self.assertEqual(["hccl-reviewer"], payload["next_roles"])


class WorkflowDocumentationContractTests(unittest.TestCase):
    def test_aicpu_workflow_wires_transition_and_recovery(self) -> None:
        text = (WORKFLOW_DIR / "aicpu-multi-agent-workflow.md").read_text(encoding="utf-8")
        self.assertIn("workflow_policy.py\" transition", text)
        self.assertIn("workflow_policy.py\" recovery", text)
        for field in ("repair_round", "pending_action", "pending_roles"):
            self.assertIn(field, text)

    def test_archived_ccu_workflow_is_not_routable(self) -> None:
        text = (WORKFLOW_DIR / "task-prompts.md").read_text(encoding="utf-8")
        self.assertIn("目前不对外支持", text)
        self.assertEqual("CCU_OUT_OF_SCOPE", POLICY.route_requirement("新增 CCU 算法").reason)
        state_block = text.split("```text", 1)[1].split("```", 1)[0]
        expected = ("Architect", "Developer", "Verifier", "Reviewer", "HCCLBot")
        positions = [state_block.index(role) for role in expected]
        self.assertEqual(sorted(positions), positions)
        self.assertIn("workflow_policy.py transition --engine CCU", text)
        self.assertIn("workflow_policy.py recovery --engine CCU", text)


    def test_hcclbot_routes_through_executable_policy(self) -> None:
        text = (PLUGIN_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("workflows/scripts/workflow_policy.py", text)
        self.assertIn("`route`", text)
        self.assertIn("AIV_OUT_OF_SCOPE", POLICY.route_requirement("AIV op").reason)

if __name__ == "__main__":
    unittest.main()
