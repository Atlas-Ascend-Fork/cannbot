# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Command-line arguments and payload validation for workflow state operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import search_policy
from summarize_performance_effects import recompute_summary, summary_dependency_paths


STAGE_STATUSES = ("in_progress", "complete", "invalid", "skipped")
TERMINAL_STATUSES = ("success", "failed", "blocked", "awaiting_operator")
TERMINAL_REASON_CODES = (
    "completed",
    "external_blocker",
    "input_invalid",
    "workflow_error",
    "known_baseline_failure",
    "candidate_precision_regression",
    "no_material_improvement",
    "ceiling_bound",
    "structural_headroom_unrealized",
)
# Structural-direction ledger (pursue_optimal). A structural direction proposed by analysis is a
# cross-round obligation that must be discharged before a clean success finish under pursue_optimal.
STRUCTURAL_DIRECTION_STATUSES = (
    "not_attempted",  # proposed, not yet implemented — UNRESOLVED
    "blocked_by_scope",  # frozen scope too narrow — UNRESOLVED (re-freeze + re-attempt)
    "blocked_by_precision",  # attempted, evidenced it breaks the precision contract — resolved
    "infeasible_evidenced",  # attempted, source/model evidence proves infeasibility — resolved
    "realized",  # implemented and selected — resolved
)
PRECISION_CLASSIFICATIONS = (
    "known_baseline_failure",
    "improved_baseline_failure",
    "new_or_worsened_failure",
    "under_diagnosis",
)


def validate_mark_args(args):
    if args.reason and args.status not in ("skipped", "invalid"):
        raise ValueError("--reason is valid only with --status skipped or invalid")
    has_performance = any(
        (
            args.performance_summary,
            args.cumulative_performance_summary,
            args.selected_candidate,
        )
    )
    if has_performance and args.status != "complete":
        raise ValueError("performance summaries are valid only with --status complete")
    return has_performance


def progress_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": args.message}
    if args.next_action:
        payload["next_action"] = args.next_action
    for key in ("stage", "evidence", "case_id", "candidate", "classification"):
        value = getattr(args, key, None)
        if value:
            payload[key] = value
    if not args.detail:
        return payload
    details: dict[str, str] = {}
    for item in args.detail:
        if "=" not in item:
            raise ValueError("--detail must use key=value")
        key, value = item.split("=", 1)
        if not key:
            raise ValueError("--detail key cannot be empty")
        details[key] = value
    payload["details"] = details
    return payload


def _command(
    subparsers: argparse._SubParsersAction, name: str, help_text: str, func
) -> argparse.ArgumentParser:
    command = subparsers.add_parser(name, help=help_text)
    command.add_argument("--state", type=Path, required=True)
    command.set_defaults(func=func)
    return command


def _add_mark_args(mark: argparse.ArgumentParser) -> None:
    mark.add_argument("--stage", required=True)
    mark.add_argument("--status", choices=STAGE_STATUSES, required=True)
    mark.add_argument("--reason")
    mark.add_argument("--message")
    mark.add_argument("--next-action", help="next action at this lifecycle checkpoint")
    mark.add_argument("--artifact", action="append")
    mark.add_argument("--context", action="append")
    mark.add_argument(
        "--performance-summary",
        type=Path,
        help="selected implementation vs round baseline effect-summary.json",
    )
    mark.add_argument(
        "--cumulative-performance-summary",
        type=Path,
        help="same selected performance vs original baseline effect-summary.json",
    )
    mark.add_argument(
        "--selected-candidate",
        help="retained implementation identity, including baseline when retained",
    )
    mark.add_argument(
        "--performance-scope",
        choices=("tuning_subset", "full"),
        default="tuning_subset",
    )


def _add_progress_args(progress: argparse.ArgumentParser) -> None:
    progress.add_argument(
        "--kind", choices=("progress", "diagnosis"), default="progress"
    )
    progress.add_argument("--message", required=True)
    progress.add_argument("--stage")
    progress.add_argument("--evidence")
    progress.add_argument("--hypothesis")
    progress.add_argument("--excluded-hypothesis", action="append")
    progress.add_argument("--next-action")
    progress.add_argument("--case-id")
    progress.add_argument("--candidate")
    progress.add_argument("--classification", choices=PRECISION_CLASSIFICATIONS)
    progress.add_argument(
        "--detail", action="append", help="structured report field as key=value"
    )


def _add_structural_args(sdir: argparse.ArgumentParser) -> None:
    sdir.add_argument(
        "--id", required=True, help="stable direction id (e.g. whole-op-fusion)"
    )
    sdir.add_argument("--status", choices=STRUCTURAL_DIRECTION_STATUSES, required=True)
    sdir.add_argument("--description")
    sdir.add_argument("--round", type=int)
    sdir.add_argument("--evidence")
    sdir.add_argument("--estimated-gain")


def _add_run_commands(sub, handlers):
    start = _command(sub, "start", "start or resume a run", handlers["start"])
    start.add_argument("--manifest", type=Path, required=True)
    start.add_argument("--workflow-version")
    sync = _command(
        sub,
        "sync-manifest",
        "accept an intentional manifest update",
        handlers["sync_manifest"],
    )
    sync.add_argument("--message")
    _add_mark_args(
        _command(sub, "mark", "change a stage lifecycle state", handlers["mark"])
    )
    _add_progress_args(
        _command(
            sub,
            "progress",
            "record meaningful work or a diagnosis checkpoint",
            handlers["progress"],
        )
    )


def _add_control_commands(sub, handlers):
    decision = _command(
        sub, "decision", "record an operator wait or decision", handlers["decision"]
    )
    group = decision.add_mutually_exclusive_group(required=True)
    group.add_argument("--awaiting", action="store_true")
    group.add_argument("--decision")
    decision.add_argument("--question")
    decision.add_argument("--safe-restore-point")
    _add_structural_args(
        _command(
            sub,
            "structural-direction",
            "upsert a structural-direction ledger entry (pursue_optimal cross-round obligation)",
            handlers["structural_direction"],
        )
    )
    migrate = _command(
        sub, "migrate-workflow", "record workflow impact audit", handlers["migrate"]
    )
    migrate.add_argument("--audit", type=Path, required=True)
    migrate.add_argument("--workflow-version", required=True)
    migrate.add_argument("--invalidate-stage", action="append")
    migrate.add_argument(
        "--adopt-schedule-policy",
        action="store_true",
        help="explicitly adopt an already frozen policy into a pre-analysis legacy state",
    )


def _add_search_commands(sub, handlers):
    replan = _command(
        sub,
        "search-replan",
        "record an evidence-backed architecture review",
        handlers["search_replan"],
    )
    replan.add_argument("--reason", choices=search_policy.REPLAN_REASONS, required=True)
    replan.add_argument(
        "--reopen",
        action="append",
        help="earliest affected decision ID; repeat for independent roots",
    )
    replan.add_argument("--evidence", type=Path, action="append", required=True)
    replan.add_argument("--message", required=True)


def _add_report_commands(sub, handlers):
    _command(
        sub, "verify", "verify manifest and completed artifacts", handlers["verify"]
    )
    inspect = _command(
        sub,
        "inspect",
        "read manifest identity and selected stage context without full history",
        handlers["inspect"],
    )
    inspect.add_argument(
        "--stage",
        action="append",
        help="exact stage key; repeat for prerequisite stages",
    )
    inspect.add_argument("--recent", type=int, default=3)
    render = _command(
        sub, "render", "render the live report from current state", handlers["render"]
    )
    render.add_argument("--output", type=Path)
    finish = _command(
        sub,
        "finish",
        "record terminal status and finalize the live report",
        handlers["finish"],
    )
    finish.add_argument("--status", choices=TERMINAL_STATUSES, required=True)
    finish.add_argument("--reason-code", choices=TERMINAL_REASON_CODES, required=True)
    finish.add_argument("--message", required=True)


def build_parser(handlers, description) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=description)
    sub = result.add_subparsers(dest="command", required=True)
    _add_run_commands(sub, handlers)
    _add_control_commands(sub, handlers)
    _add_search_commands(sub, handlers)
    _add_report_commands(sub, handlers)
    return result


def _checked_performance_summary(path):
    summary = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or any(
        not isinstance(summary.get(field), str)
        for field in ("baseline_path", "candidate_path")
    ):
        raise ValueError(
            f"{path}: expected an effect summary with performance source paths"
        )
    baseline = Path(summary["baseline_path"])
    candidate = Path(summary["candidate_path"])
    if not baseline.is_absolute() or not candidate.is_absolute():
        raise ValueError(f"{path}: performance source paths must be absolute")
    expected = recompute_summary(summary)
    if any(
        field not in summary or summary[field] != value
        for field, value in expected.items()
    ):
        raise ValueError(
            f"{path}: effect summary differs from source performance or jitter policy"
        )
    artifacts = [str(path), str(baseline), str(candidate)] + summary_dependency_paths(
        summary
    )
    return summary, artifacts


def prepare_performance(args: argparse.Namespace) -> tuple[dict[str, str], list[str]]:
    """Validate existing effect artifacts without collecting performance again."""
    required = (
        args.performance_summary,
        args.cumulative_performance_summary,
        args.selected_candidate,
    )
    if not all(required):
        raise ValueError(
            "performance checkpoint requires --performance-summary, "
            "--cumulative-performance-summary and --selected-candidate"
        )
    references = {
        "round_summary": str(args.performance_summary.resolve()),
        "cumulative_summary": str(args.cumulative_performance_summary.resolve()),
        "selected_candidate": args.selected_candidate,
        "scope": args.performance_scope,
    }
    artifacts: list[str] = []
    summaries = []
    for key in ("round_summary", "cumulative_summary"):
        reference = references.get(key)
        if reference is None:
            raise ValueError(f"missing performance reference: {key}")
        path = Path(reference)
        summary, paths = _checked_performance_summary(path)
        artifacts.extend(paths)
        summaries.append(summary)
    current, cumulative = summaries
    if current["candidate_path"] != cumulative["candidate_path"]:
        raise ValueError(
            "round and cumulative summaries must reference the same selected performance"
        )
    if [case["case_id"] for case in current["cases"]] != [
        case["case_id"] for case in cumulative["cases"]
    ]:
        raise ValueError(
            "round and cumulative summaries must cover the same ordered cases"
        )
    return references, artifacts
