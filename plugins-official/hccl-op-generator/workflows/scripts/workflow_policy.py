#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms of the
# CANN Open Software License Agreement Version 2.0 (the "License").
"""Validate HCCLBot engine routing and role/state transition decisions."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)


ENGINES = ("AICPU", "CCU")
ACTORS = (
    "hcclbot",
    "hccl-architect",
    "hccl-developer",
    "hccl-reviewer",
    "hccl-verifier",
)
RESULTS = (
    "PASS",
    "PASS_WITH_NOTES",
    "FAIL",
    "DESIGN_ISSUE",
    "REVIEW_FAIL",
    "TEST_FAIL",
    "BLOCKED",
)
FAILURE_CLASSES = ("SOURCE", "ENVIRONMENT")
MAX_REPAIR_ROUNDS = 3
ASCII_IDENTIFIER_CHAR = r"a-z0-9_"


@dataclass(frozen=True)
class Stage:
    actor: str
    pass_state: str
    pass_results: frozenset[str] = frozenset({"PASS"})


STAGES = {
    "AICPU": {
        "ENV_READY": Stage("hccl-architect", "DESIGN_READY"),
        "DESIGN_READY": Stage("hccl-verifier", "BASELINE_READY"),
        "BASELINE_READY": Stage("hccl-developer", "IMPLEMENTED"),
        "IMPLEMENTED": Stage("hccl-reviewer", "REVIEW_PASS"),
        "REVIEW_PASS": Stage("hccl-verifier", "TEST_PASS"),
        "TEST_PASS": Stage("hcclbot", "COMPLETE"),
    },
    "CCU": {
        "ENV_READY": Stage("hccl-architect", "DESIGN_READY"),
        "DESIGN_READY": Stage("hccl-developer", "IMPLEMENTED"),
        "IMPLEMENTED": Stage("hccl-verifier", "VERIFIED"),
        "VERIFIED": Stage(
            "hccl-reviewer",
            "REVIEW_PASS",
            frozenset({"PASS", "PASS_WITH_NOTES"}),
        ),
        "REVIEW_PASS": Stage("hcclbot", "COMPLETE"),
    },
}

RECOVERY_CHAINS = {
    "AICPU": {
        "REDESIGN": {("hccl-architect",)},
        "REPAIR": {
            ("hccl-developer", "hccl-reviewer"),
            ("hccl-reviewer",),
            ("hccl-developer", "hccl-reviewer", "hccl-verifier"),
            ("hccl-reviewer", "hccl-verifier"),
            ("hccl-verifier",),
        },
    },
    "CCU": {
        "REDESIGN": {("hccl-architect",)},
        "REPAIR": {
            ("hccl-developer", "hccl-verifier"),
            ("hccl-verifier",),
            ("hccl-developer", "hccl-verifier", "hccl-reviewer"),
            ("hccl-verifier", "hccl-reviewer"),
            ("hccl-reviewer",),
        },
    },
}

RECOVERY_ACTOR_STATES = {
    "AICPU": {
        "hccl-architect": "ENV_READY",
        "hccl-developer": "IMPLEMENTED",
        "hccl-reviewer": "IMPLEMENTED",
        "hccl-verifier": "REVIEW_PASS",
    },
    "CCU": {
        "hccl-architect": "ENV_READY",
        "hccl-developer": "IMPLEMENTED",
        "hccl-verifier": "IMPLEMENTED",
        "hccl-reviewer": "VERIFIED",
    },
}


@dataclass(frozen=True)
class Decision:
    ok: bool
    engine: str | None
    action: str
    reason: str
    current_state: str | None = None
    next_state: str | None = None
    next_roles: tuple[str, ...] = ()
    repair_round: int = 0
    pending_action: str = "NONE"
    workflow: str | None = None


@dataclass(frozen=True)
class PolicyContext:
    engine: str
    state: str
    repair_round: int = 0
    failure_class: str | None = None


def _detect_engine_markers(normalized: str) -> tuple[bool, bool, bool, bool]:
    has_aicpu = "aicpu" in normalized or "ai_cpu" in normalized
    has_ccu = bool(
        re.search(
            rf"(?<![{ASCII_IDENTIFIER_CHAR}])ccu(?![{ASCII_IDENTIFIER_CHAR}])",
            normalized,
        )
        or any(marker in normalized for marker in ("ccusched", "ccums", "ccu_sched", "ccu_ms", "ccu_kernel", "ccu::"))
    )
    has_aiv = bool(
        re.search(
            rf"(?<![{ASCII_IDENTIFIER_CHAR}])aiv(?![{ASCII_IDENTIFIER_CHAR}])",
            normalized,
        )
        or "aivector" in normalized
    )
    has_hostdpu = bool(
        re.search(r"(?<![a-z0-9_])host[ _-]?dpu(?![a-z0-9_])", normalized)
        or re.search(r"(?<![a-z0-9_])dpu(?![a-z0-9_])", normalized)
    )
    return has_aicpu, has_ccu, has_aiv, has_hostdpu


def route_requirement(requirement: str) -> Decision:
    """Route only from explicit engine markers defined by the Plugin contract."""
    has_aicpu, has_ccu, has_aiv, has_hostdpu = _detect_engine_markers(requirement.casefold())

    if sum((has_aicpu, has_ccu, has_aiv, has_hostdpu)) > 1:
        return Decision(
            False,
            None,
            "ASK_ENGINE",
            "CONFLICTING_ENGINE_MARKERS",
            pending_action="BLOCKED",
        )
    if has_aiv or has_hostdpu:
        return Decision(
            False,
            None,
            "BLOCK",
            "AIV_OUT_OF_SCOPE" if has_aiv else "HOSTDPU_OUT_OF_SCOPE",
            pending_action="BLOCKED",
        )
    if has_ccu:
        return Decision(
            False,
            None,
            "BLOCK",
            "CCU_OUT_OF_SCOPE",
            pending_action="BLOCKED",
        )
    reason = "EXPLICIT_AICPU_MARKER" if has_aicpu else "DEFAULT_STANDARD_OP_TO_AICPU"
    return Decision(
        True,
        "AICPU",
        "ROUTE",
        reason,
        workflow="aicpu-multi-agent-workflow.md",
    )


def transition(ctx: PolicyContext, actor: str, result: str) -> Decision:
    """Validate one completed stage and return the only allowed next action."""
    if ctx.engine not in STAGES:
        return _invalid(ctx, "UNKNOWN_ENGINE")
    if ctx.state == "COMPLETE":
        return _invalid(ctx, "TERMINAL_STATE")
    stage = STAGES[ctx.engine].get(ctx.state)
    if stage is None:
        return _invalid(ctx, "UNKNOWN_STATE")
    if actor != stage.actor:
        return _invalid(ctx, "STAGE_OWNER_VIOLATION")
    if not 0 <= ctx.repair_round <= MAX_REPAIR_ROUNDS:
        return _invalid(ctx, "INVALID_REPAIR_ROUND")

    if result in stage.pass_results:
        next_stage = STAGES[ctx.engine].get(stage.pass_state)
        return Decision(
            True,
            ctx.engine,
            "ADVANCE",
            "STAGE_PASS",
            current_state=ctx.state,
            next_state=stage.pass_state,
            next_roles=(next_stage.actor,) if next_stage else (),
            repair_round=ctx.repair_round,
        )
    if result == "BLOCKED":
        return _blocked(ctx, "AGENT_BLOCKED")

    if ctx.engine == "AICPU":
        return _aicpu_failure(ctx, result)
    return _ccu_failure(ctx, result)


def _recovery_failure(
    ctx: PolicyContext, pending_roles: list[str], actor: str, result: str
) -> Decision:
    if actor == "hccl-architect" and result == "DESIGN_ISSUE":
        return _retry_design(ctx)
    if actor == "hccl-developer" and result == "DESIGN_ISSUE":
        return Decision(
            True,
            ctx.engine,
            "REDESIGN",
            "DEVELOPER_FOUND_DESIGN_ISSUE",
            current_state=ctx.state,
            next_state="ENV_READY",
            next_roles=("hccl-architect",),
            repair_round=ctx.repair_round,
            pending_action="REDESIGN",
        )
    if actor == "hccl-reviewer" and result in {"REVIEW_FAIL", "FAIL"}:
        if ctx.engine == "AICPU":
            roles = ("hccl-developer", "hccl-reviewer")
            if "hccl-verifier" in pending_roles[1:]:
                roles += ("hccl-verifier",)
        else:
            roles = ("hccl-developer", "hccl-verifier", "hccl-reviewer")
        return _repair(ctx, "REVIEW_FAILED_DURING_RECOVERY", roles, next_state="IMPLEMENTED")
    if actor == "hccl-verifier" and result in {"TEST_FAIL", "FAIL"}:
        if ctx.failure_class is None:
            return _invalid(ctx, "FAILURE_CLASS_REQUIRED")
        if ctx.failure_class == "ENVIRONMENT":
            return _blocked(ctx, "TEST_ENVIRONMENT_BLOCKED")
        if ctx.engine == "AICPU":
            roles = ("hccl-developer", "hccl-reviewer", "hccl-verifier")
        else:
            roles = ("hccl-developer", "hccl-verifier")
            if "hccl-reviewer" in pending_roles[1:]:
                roles += ("hccl-reviewer",)
        return _repair(ctx, "TEST_SOURCE_FAILED_DURING_RECOVERY", roles, next_state="IMPLEMENTED")
    return _invalid(ctx, "RESULT_NOT_ALLOWED_FOR_RECOVERY_ROLE")


def recovery(
    ctx: PolicyContext,
    pending_action: str,
    pending_roles: list[str],
    actor: str,
    result: str,
) -> Decision:
    """Validate and consume one role from a previously authorized recovery chain."""
    if ctx.engine not in STAGES:
        return _invalid(ctx, "UNKNOWN_ENGINE")
    if pending_action not in {"REPAIR", "REDESIGN"} or not pending_roles:
        return _invalid(ctx, "NO_PENDING_RECOVERY")
    if tuple(pending_roles) not in RECOVERY_CHAINS[ctx.engine][pending_action]:
        return _invalid(ctx, "INVALID_RECOVERY_CHAIN")
    if not 0 <= ctx.repair_round <= MAX_REPAIR_ROUNDS:
        return _invalid(ctx, "INVALID_REPAIR_ROUND")
    if actor != pending_roles[0]:
        return _invalid(ctx, "RECOVERY_OWNER_VIOLATION")
    if ctx.state != RECOVERY_ACTOR_STATES[ctx.engine].get(actor):
        return _invalid(ctx, "RECOVERY_STATE_MISMATCH")
    if result == "BLOCKED":
        return _blocked(ctx, "AGENT_BLOCKED")

    pass_results = {"PASS"}
    if ctx.engine == "CCU" and actor == "hccl-reviewer":
        pass_results.add("PASS_WITH_NOTES")
    if result in pass_results:
        remaining = tuple(pending_roles[1:])
        next_state = _recovery_output_state(ctx.engine, actor)
        return Decision(
            True,
            ctx.engine,
            "CONTINUE_RECOVERY" if remaining else "RECOVERY_COMPLETE",
            "RECOVERY_STEP_PASS" if remaining else "RECOVERY_CHAIN_PASS",
            current_state=ctx.state,
            next_state=next_state,
            next_roles=remaining,
            repair_round=ctx.repair_round,
            pending_action=pending_action if remaining else "NONE",
        )

    return _recovery_failure(ctx, pending_roles, actor, result)


def _recovery_output_state(engine: str, actor: str) -> str:
    states = {
        "hccl-architect": "DESIGN_READY",
        "hccl-developer": "IMPLEMENTED",
        "hccl-reviewer": "REVIEW_PASS",
        "hccl-verifier": "TEST_PASS" if engine == "AICPU" else "VERIFIED",
    }
    return states.get(actor, "")


def _aicpu_failure(ctx: PolicyContext, result: str) -> Decision:
    if ctx.state == "ENV_READY" and result == "DESIGN_ISSUE":
        return _retry_design(ctx)
    if ctx.state == "DESIGN_READY" and result == "FAIL":
        return _blocked(ctx, "BASELINE_FAILED")
    if ctx.state == "BASELINE_READY" and result == "DESIGN_ISSUE":
        return Decision(
            True,
            "AICPU",
            "REDESIGN",
            "DEVELOPER_FOUND_DESIGN_ISSUE",
            current_state=ctx.state,
            next_state="ENV_READY",
            next_roles=("hccl-architect",),
            repair_round=ctx.repair_round,
            pending_action="REDESIGN",
        )
    if ctx.state == "IMPLEMENTED" and result == "REVIEW_FAIL":
        return _repair(
            ctx,
            "REVIEW_FAILED",
            ("hccl-developer", "hccl-reviewer"),
        )
    if ctx.state == "REVIEW_PASS" and result == "TEST_FAIL":
        if ctx.failure_class is None:
            return _invalid(ctx, "FAILURE_CLASS_REQUIRED")
        if ctx.failure_class == "ENVIRONMENT":
            return _blocked(ctx, "TEST_ENVIRONMENT_BLOCKED")
        if ctx.failure_class == "SOURCE":
            return _repair(
                ctx,
                "TEST_SOURCE_FAILED",
                ("hccl-developer", "hccl-reviewer", "hccl-verifier"),
                next_state="IMPLEMENTED",
            )
    return _invalid(ctx, "RESULT_NOT_ALLOWED_FOR_STAGE")


def _ccu_failure(ctx: PolicyContext, result: str) -> Decision:
    if ctx.state == "ENV_READY" and result == "DESIGN_ISSUE":
        return _retry_design(ctx)
    if ctx.state == "DESIGN_READY" and result == "DESIGN_ISSUE":
        return Decision(
            True,
            "CCU",
            "REDESIGN",
            "DEVELOPER_FOUND_DESIGN_ISSUE",
            current_state=ctx.state,
            next_state="ENV_READY",
            next_roles=("hccl-architect",),
            repair_round=ctx.repair_round,
            pending_action="REDESIGN",
        )
    if ctx.state == "IMPLEMENTED" and result in {"FAIL", "TEST_FAIL"}:
        if ctx.failure_class is None:
            return _invalid(ctx, "FAILURE_CLASS_REQUIRED")
        if ctx.failure_class == "ENVIRONMENT":
            return _blocked(ctx, "TEST_ENVIRONMENT_BLOCKED")
        if ctx.failure_class == "SOURCE":
            return _repair(
                ctx,
                "TEST_SOURCE_FAILED",
                ("hccl-developer", "hccl-verifier"),
            )
    if ctx.state == "VERIFIED" and result in {"FAIL", "REVIEW_FAIL"}:
        return _repair(
            ctx,
            "REVIEW_FAILED",
            ("hccl-developer", "hccl-verifier", "hccl-reviewer"),
            next_state="IMPLEMENTED",
        )
    return _invalid(ctx, "RESULT_NOT_ALLOWED_FOR_STAGE")


def _retry_design(ctx: PolicyContext) -> Decision:
    return Decision(
        True,
        ctx.engine,
        "RETRY_DESIGN",
        "DESIGN_INPUT_INCOMPLETE",
        current_state=ctx.state,
        next_state="ENV_READY",
        next_roles=("hccl-architect",),
        repair_round=ctx.repair_round,
        pending_action="REDESIGN",
    )


def _repair(
    ctx: PolicyContext,
    reason: str,
    roles: tuple[str, ...],
    next_state: str | None = None,
) -> Decision:
    if ctx.repair_round >= MAX_REPAIR_ROUNDS:
        return _blocked(ctx, "REPAIR_LIMIT_REACHED")
    return Decision(
        True,
        ctx.engine,
        "REPAIR",
        reason,
        current_state=ctx.state,
        next_state=next_state or ctx.state,
        next_roles=roles,
        repair_round=ctx.repair_round + 1,
        pending_action="REPAIR",
    )


def _blocked(ctx: PolicyContext, reason: str) -> Decision:
    return Decision(
        True,
        ctx.engine,
        "BLOCK",
        reason,
        current_state=ctx.state,
        next_state=ctx.state,
        repair_round=ctx.repair_round,
        pending_action="BLOCKED",
    )


def _invalid(ctx: PolicyContext, reason: str) -> Decision:
    return Decision(
        False,
        ctx.engine if ctx.engine in ENGINES else None,
        "REJECT",
        reason,
        current_state=ctx.state,
        next_state=ctx.state,
        repair_round=ctx.repair_round,
        pending_action="BLOCKED",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate HCCLBot routing and transition policy.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    route = subparsers.add_parser("route", help="route an HCCL requirement to AICPU or block unsupported engines")
    route.add_argument("--requirement", required=True)
    route.add_argument("--json", action="store_true")

    step = subparsers.add_parser("transition", help="validate a completed workflow stage")
    step.add_argument("--engine", required=True, choices=ENGINES)
    step.add_argument("--state", required=True)
    step.add_argument("--actor", required=True, choices=ACTORS)
    step.add_argument("--result", required=True, choices=RESULTS)
    step.add_argument("--repair-round", type=int, default=0)
    step.add_argument("--failure-class", choices=FAILURE_CLASSES)
    step.add_argument("--json", action="store_true")

    resume = subparsers.add_parser("recovery", help="validate one role in a recovery chain")
    resume.add_argument("--engine", required=True, choices=ENGINES)
    resume.add_argument("--state", required=True)
    resume.add_argument("--pending-action", required=True, choices=("REPAIR", "REDESIGN"))
    resume.add_argument("--pending-roles", required=True, nargs="+", choices=ACTORS)
    resume.add_argument("--actor", required=True, choices=ACTORS)
    resume.add_argument("--result", required=True, choices=RESULTS)
    resume.add_argument("--repair-round", required=True, type=int)
    resume.add_argument("--failure-class", choices=FAILURE_CLASSES)
    resume.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.command == "route":
        decision = route_requirement(args.requirement)
    elif args.command == "transition":
        ctx = PolicyContext(args.engine, args.state, args.repair_round, args.failure_class)
        decision = transition(ctx, args.actor, args.result)
    else:
        ctx = PolicyContext(args.engine, args.state, args.repair_round, args.failure_class)
        decision = recovery(ctx, args.pending_action, args.pending_roles, args.actor, args.result)
    payload = asdict(decision)
    if args.json:
        logging.info(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        logging.info(
            f"{decision.action}: {decision.reason}; "
            f"engine={decision.engine}, next_state={decision.next_state}, "
            f"next_roles={','.join(decision.next_roles) or '-'}, "
            f"repair_round={decision.repair_round}"
        )
    return 0 if decision.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
