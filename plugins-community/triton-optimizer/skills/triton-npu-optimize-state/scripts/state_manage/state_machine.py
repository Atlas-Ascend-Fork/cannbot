# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from typing import NamedTuple, cast

from shared.managed_integrity import operator_sha256
from round.check import resolve_round_operator_file
from shared.round_naming import expected_round_operator_name
from state_manage.claim_contract import (
    CLAIM_RESPONSE_REQUIRED,
    EDIT_CLAIM_ERROR_CODE_LEDGER_UNAVAILABLE,
    EDIT_CLAIM_ERROR_CODE_PATTERN_REQUIRED,
    EDIT_CLAIM_ERROR_CODE_REASON_REQUIRED,
    EDIT_CLAIM_ERROR_CODE_ROUND_NOT_ACTIVE,
    EDIT_CLAIM_ERROR_CODE_SKILL_DEPENDENCY_INVALID,
    EDIT_CLAIM_ERROR_CODE_STATE_INCONSISTENT,
    EDIT_CLAIM_ERROR_CODE_UNKNOWN_SOURCE,
    EDIT_CLAIM_ERROR_CODE_WRONG_TARGET,
    OPTIMIZE_KNOWLEDGE_PATTERN_INFIXES,
    claim_includes_optimize_knowledge_pattern,
    optimize_knowledge_pattern_paths,
)

WORKFLOW_SCHEMA_VERSION = 2

PHASE_BASELINE = "baseline"
PHASE_AWAITING_ROUND_START = "awaiting_round_start"
PHASE_ROUND_ACTIVE = "round_active"
PHASE_DEEP_ANALYSIS = "deep_analysis"
_PHASES = {
    PHASE_BASELINE,
    PHASE_AWAITING_ROUND_START,
    PHASE_ROUND_ACTIVE,
    PHASE_DEEP_ANALYSIS,
}

DEEP_OPTIMIZATION_POLICIES = ("never", "auto", "always")

ROUND_DIR_PATTERN = re.compile(r"opt-round-(\d+)$")

ROUND_STRATEGIES = (
    "exploration",
    "structural_change",
    "focused_tuning",
    "stabilization",
    "plateau_review",
)
# Order encodes increasing required evidence depth, shallowest first.
ANALYSIS_POLICIES = (
    "pattern_entry",
    "profile_required",
    "ir_required",
    "compiler_source_required",
)
EDIT_CLAIM_SOURCE_KINDS = ("pattern", "self-directed")
# Backends whose skills/ directories can be staged into an optimize workspace.
# Kept in sync with src/helix/skills/staging.py _SKILL_BACKEND_CONFIGS.
_STAGED_SKILL_BACKENDS = (
    ".claude",
    ".codex",
    ".opencode",
    ".pi",
    ".openhands",
    ".trae",
    ".agents",
)
_STAGED_SKILL_PATH_PREFIXES = tuple(f"{backend}/skills/" for backend in _STAGED_SKILL_BACKENDS)
UPDATED_BY_VALUES = ("start-round", "set-current-round-state")
_ANALYSIS_POLICY_ORDER = {name: index for index, name in enumerate(ANALYSIS_POLICIES)}
_WARNING_WORTHY_STRATEGY_TRANSITIONS = {
    ("structural_change", "exploration"): (
        "Returning from structural_change to exploration is unusual; "
        "confirm the previous rewrite direction is no longer justified."
    ),
    ("focused_tuning", "exploration"): (
        "Returning from focused_tuning to exploration is unusual; "
        "confirm the round really needs a broader search again."
    ),
}
_UNUSUAL_STRATEGY_POLICY_COMBINATIONS = {
    ("exploration", "compiler_source_required"): (
        "The combination exploration + compiler_source_required is unusual; "
        "compiler-source depth is often too deep for an exploratory round."
    ),
    ("structural_change", "pattern_entry"): (
        "The combination structural_change + pattern_entry is unusual; "
        "structural rewrites often need deeper evidence than pattern_entry alone."
    ),
    ("plateau_review", "pattern_entry"): (
        "The combination plateau_review + pattern_entry is unusual; plateau review usually follows deeper evidence."
    ),
}


class WorkflowError(ValueError):
    """Structured workflow validation error carrying a machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_state(state_path: Path) -> dict[str, object]:
    try:
        raw_payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed workflow state JSON: {exc}") from exc
    if not isinstance(raw_payload, dict):
        raise ValueError("workflow state must be a JSON object")
    payload = cast(dict[str, object], raw_payload)
    _validate_state(payload)
    return payload


def bootstrap_state(
    state_path: Path,
    *,
    baseline_reused: bool,
    deep_optimization_policy: str = "auto",
    pattern_usage_enabled: bool = False,
    remote: str | None = None,
    remote_workdir: str | None = None,
    language: str = "triton",
) -> None:
    normalized_deep_policy = _validate_deep_optimization_policy(deep_optimization_policy)
    if remote is None:
        remote_workdir = None
    payload: dict[str, object] = {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "execution": {
            "remote": remote,
            "remote_workdir": remote_workdir,
        },
        "language": language,
        "phase": PHASE_AWAITING_ROUND_START if baseline_reused else PHASE_BASELINE,
        "current_round": None,
        "baseline": {
            "status": "passed" if baseline_reused else "pending",
            "submitted_at": None,
        },
        "rounds": {},
        "deep_optimization": _new_deep_optimization_state(normalized_deep_policy),
        "pattern_usage": {
            "enabled": bool(pattern_usage_enabled),
        },
        "pattern_recommendations": {},
    }
    write_state(state_path, payload)


def update_execution_context(
    state_path: Path,
    *,
    remote: str | None,
    remote_workdir: str | None,
    language: str | None = None,
) -> None:
    payload = load_state(state_path)
    if remote is None:
        remote_workdir = None
    payload["execution"] = {
        "remote": remote,
        "remote_workdir": remote_workdir,
    }
    if language is not None:
        if not language.strip():
            raise ValueError("workflow state language must be a non-empty string")
        payload["language"] = language.strip().lower()
    write_state(state_path, payload)


def mark_baseline_passed(state_path: Path) -> None:
    payload = load_state(state_path)
    baseline = _require_baseline_dict(payload)
    baseline["status"] = "passed"
    baseline["submitted_at"] = _utc_now()
    payload["phase"] = PHASE_AWAITING_ROUND_START
    payload["current_round"] = None
    write_state(state_path, payload)


class _RoundStartInput(NamedTuple):
    round_dir: str
    round_number: int
    round_key: str
    round_strategy: str
    analysis_policy: str
    reason: str
    warnings: list[str]


def start_round(
    state_path: Path,
    round_dir: str,
    *,
    round_strategy: str,
    analysis_policy: str,
    reason: str,
) -> dict[str, object]:
    normalized_round_strategy = _validate_round_strategy(round_strategy)
    normalized_analysis_policy = _validate_analysis_policy(analysis_policy)
    normalized_reason = _validate_reason(reason)
    warnings = _build_strategy_state_warnings(
        round_strategy=normalized_round_strategy,
        analysis_policy=normalized_analysis_policy,
    )
    round_number = parse_round_number(round_dir)
    spec = _RoundStartInput(
        round_dir=round_dir,
        round_number=round_number,
        round_key=str(round_number),
        round_strategy=normalized_round_strategy,
        analysis_policy=normalized_analysis_policy,
        reason=normalized_reason,
        warnings=warnings,
    )

    payload = load_state(state_path)
    baseline = _require_baseline_dict(payload)
    if baseline.get("status") == "passed" and isinstance(baseline.get("integrity"), dict):
        from shared.managed_integrity import validate_integrity

        validate_integrity(state_path)
    rounds = require_rounds_dict(payload)
    if baseline.get("status") != "passed":
        raise ValueError("cannot start a round before baseline.status=passed")

    reentry_result = _active_round_reentry_result(payload, rounds, spec)
    if reentry_result is not None:
        return reentry_result

    deep_analysis_required = _validate_new_round_start(payload, rounds, spec)
    return _activate_new_round(state_path, payload, rounds, spec, deep_analysis_required)


def _activate_new_round(
    state_path: Path,
    payload: dict[str, object],
    rounds: dict[str, object],
    spec: _RoundStartInput,
    deep_analysis_required: bool,
) -> dict[str, object]:
    payload["phase"] = PHASE_DEEP_ANALYSIS if deep_analysis_required else PHASE_ROUND_ACTIVE
    payload["current_round"] = spec.round_number
    rounds[spec.round_key] = _build_new_round_entry(
        state_path,
        spec,
        deep_analysis_required=deep_analysis_required,
        pattern_usage_enabled=_pattern_usage_enabled(payload),
    )
    write_state(state_path, payload)
    result_warnings = _record_round_start_side_effects(state_path, spec)
    result = _start_round_result(
        round_dir=spec.round_dir,
        round_strategy=spec.round_strategy,
        analysis_policy=spec.analysis_policy,
        reason=spec.reason,
        warnings=result_warnings,
    )
    if deep_analysis_required:
        result["status"] = "deep_analysis_required"
    return result


def _active_round_reentry_result(
    payload: dict[str, object],
    rounds: dict[str, object],
    spec: _RoundStartInput,
) -> dict[str, object] | None:
    """Return the idempotent result when start-round re-enters the active round."""
    reenters_active_round = (
        payload["phase"] in {PHASE_ROUND_ACTIVE, PHASE_DEEP_ANALYSIS}
        and payload["current_round"] == spec.round_number
        and spec.round_key in rounds
    )
    if not reenters_active_round:
        return None
    active_round = rounds[spec.round_key]
    if not isinstance(active_round, dict) or cast(dict[str, object], active_round).get("status") not in {
        "active",
        "deep_analysis_required",
    }:
        return None
    active_round_dict = cast(dict[str, object], active_round)
    existing_state = _get_optional_strategy_state(active_round_dict)
    if existing_state is None:
        raise ValueError(
            f"active round {spec.round_dir} is missing strategy_state; use set-current-round-state to initialize it"
        )
    if (
        existing_state["round_strategy"] != spec.round_strategy
        or existing_state["analysis_policy"] != spec.analysis_policy
        or existing_state["reason"] != spec.reason
    ):
        raise ValueError(
            f"cannot reinitialize active round {spec.round_dir} with different strategy state"
        )
    result = _start_round_result(
        round_dir=spec.round_dir,
        round_strategy=spec.round_strategy,
        analysis_policy=spec.analysis_policy,
        reason=spec.reason,
        warnings=spec.warnings,
    )
    if payload["phase"] == PHASE_DEEP_ANALYSIS:
        result["status"] = "deep_analysis_required"
    return result


def _validate_new_round_start(
    payload: dict[str, object],
    rounds: dict[str, object],
    spec: _RoundStartInput,
) -> bool:
    """Validate that a fresh round may open; return whether deep analysis is required."""
    if payload["phase"] != PHASE_AWAITING_ROUND_START:
        raise ValueError(
            f"cannot start {spec.round_dir} while workflow phase is {payload['phase']}"
        )

    existing = rounds.get(spec.round_key)
    if isinstance(existing, dict):
        existing_round = cast(dict[str, object], existing)
        if existing_round.get("status") == "passed":
            raise ValueError(f"cannot reopen completed round {spec.round_dir}")

    deep_analysis_required = _deep_analysis_is_required(payload)
    if (
        _first_auto_plateau_review_round(payload, spec.round_number)
        and spec.round_strategy != "plateau_review"
    ):
        raise ValueError(
            "the first deep round after an automatic speedup plateau must use "
            "round_strategy plateau_review"
        )
    if deep_analysis_required and spec.analysis_policy not in {
        "ir_required",
        "compiler_source_required",
    }:
        raise ValueError(
            "deep optimization requires analysis_policy ir_required or compiler_source_required"
        )
    return deep_analysis_required


def _build_new_round_entry(
    state_path: Path,
    spec: _RoundStartInput,
    *,
    deep_analysis_required: bool,
    pattern_usage_enabled: bool,
) -> dict[str, object]:
    round_entry: dict[str, object] = {
        "status": "deep_analysis_required" if deep_analysis_required else "active",
        "round_dir": spec.round_dir,
        "strategy_state": _build_strategy_state(
            round_strategy=spec.round_strategy,
            analysis_policy=spec.analysis_policy,
            reason=spec.reason,
            updated_by="start-round",
        ),
    }
    round_path = state_path.parent.parent / spec.round_dir
    candidate = resolve_round_operator_file(round_path) if round_path.is_dir() else None
    if candidate is not None:
        round_entry["operator_path"] = _workspace_relative_path(state_path, candidate)
    if deep_analysis_required:
        candidate = _resolve_round_candidate_path(state_path, spec.round_dir)
        round_entry["deep_analysis"] = {
            "operator_file": _workspace_relative_path(state_path, candidate),
            "operator_sha256": operator_sha256(candidate),
            "profile_evidence": None,
            "ir_evidence": None,
            "selected_case_id": None,
        }
    round_entry["edit_claim"] = _new_edit_claim_state(
        enabled=pattern_usage_enabled,
    )
    return round_entry


def _record_round_start_side_effects(
    state_path: Path,
    spec: _RoundStartInput,
) -> list[str]:
    """Best-effort timing log and attempts.md mirror; workflow state stays authoritative."""
    result_warnings = list(spec.warnings)
    try:
        _append_round_timing_event(
            state_path,
            round_dir=spec.round_dir,
            event="round_start",
        )
    except OSError as exc:
        result_warnings.append(
            f"round timing log could not be updated: {exc}. Workflow state remains authoritative."
        )
    try:
        _append_state_update_block(
            _attempts_path_for_round(state_path, spec.round_dir),
            source="start-round",
            round_strategy=spec.round_strategy,
            analysis_policy=spec.analysis_policy,
            reason=spec.reason,
            warnings=result_warnings,
        )
    except OSError as exc:
        result_warnings.append(
            f"attempts.md history mirror could not be updated: {exc}. Workflow state remains authoritative."
        )
    return result_warnings


def claim_edit(
    state_path: Path,
    target_path: Path,
    *,
    source_kind: str,
    reason: str,
    pattern_paths: list[str] | None = None,
) -> dict[str, object]:
    normalized_source_kind = _validate_edit_claim_source(source_kind)
    normalized_reason = _validate_reason(reason)
    normalized_pattern_paths = _validate_edit_claim_pattern_paths(
        state_path,
        source_kind=normalized_source_kind,
        pattern_paths=pattern_paths,
    )

    payload = load_state(state_path)
    current_round, round_entry = _require_active_claim_round(payload)
    round_dir = _require_claim_round_dir(round_entry, current_round)
    _require_optimize_knowledge_pattern_claim(
        source_kind=normalized_source_kind,
        pattern_paths=normalized_pattern_paths,
    )
    resolved_target = target_path.expanduser().resolve()
    _validate_claim_target(state_path, round_entry, round_dir, resolved_target)

    target_relative = _workspace_relative_path(state_path, resolved_target)
    claimed_at = _utc_now()
    claim_details: dict[str, object] = {
        "source_kind": normalized_source_kind,
        "reason": normalized_reason,
        "pattern_paths": normalized_pattern_paths,
        "target_path": target_relative,
        "pre_edit_sha256": (
            operator_sha256(resolved_target) if resolved_target.is_file() else None
        ),
        "timestamp": claimed_at,
    }
    # Persist the ledger event before unlocking the edit via state.json. When
    # pattern-usage is enabled the write is fail-closed: an unrecordable claim
    # leaves workflow state unchanged so hooks keep blocking operator edits.
    _persist_edit_claim(state_path, payload, round_entry, current_round, claim_details)

    warnings = _mirror_edit_claim_block(state_path, round_dir, claim_details)

    result: dict[str, object] = {
        "round": round_dir,
        **claim_details,
    }
    if warnings:
        result["warnings"] = warnings
    return result


def _persist_edit_claim(
    state_path: Path,
    payload: dict[str, object],
    round_entry: dict[str, object],
    current_round: int,
    claim_details: dict[str, object],
) -> None:
    _append_pattern_usage_event(
        state_path,
        payload,
        {
            "timestamp": claim_details["timestamp"],
            "round": current_round,
            "pattern_paths": optimize_knowledge_pattern_paths(
                pattern_paths=cast(list[str] | None, claim_details["pattern_paths"])
            ),
            "reason": claim_details["reason"],
            "target_path": claim_details["target_path"],
        },
    )
    round_entry["operator_path"] = claim_details["target_path"]
    round_entry["edit_claim"] = {
        "enabled": _pattern_usage_enabled(payload),
        "active": True,
        "claimed_at": claim_details["timestamp"],
    }
    write_state(state_path, payload)


def _require_active_claim_round(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    """Return the active round number and entry, or raise a structured claim error."""
    if payload.get("phase") != PHASE_ROUND_ACTIVE or not isinstance(
        payload.get("current_round"), int
    ):
        raise WorkflowError(
            EDIT_CLAIM_ERROR_CODE_ROUND_NOT_ACTIVE,
            "cannot claim an edit without an active optimize round",
        )

    current_round = cast(int, payload["current_round"])
    round_entry_obj = require_rounds_dict(payload).get(str(current_round))
    if not isinstance(round_entry_obj, dict):
        raise WorkflowError(
            EDIT_CLAIM_ERROR_CODE_STATE_INCONSISTENT,
            f"missing workflow state entry for opt-round-{current_round}",
        )
    round_entry = cast(dict[str, object], round_entry_obj)
    if round_entry.get("status") != "active":
        raise WorkflowError(
            EDIT_CLAIM_ERROR_CODE_ROUND_NOT_ACTIVE,
            f"cannot claim an edit for non-active round opt-round-{current_round}",
        )
    return current_round, round_entry


def _require_claim_round_dir(round_entry: dict[str, object], current_round: int) -> str:
    round_dir = round_entry.get("round_dir")
    if not isinstance(round_dir, str) or not round_dir:
        raise WorkflowError(
            EDIT_CLAIM_ERROR_CODE_STATE_INCONSISTENT,
            f"workflow state round {current_round} is missing round_dir",
        )
    return round_dir


def _validate_claim_target(
    state_path: Path,
    round_entry: dict[str, object],
    round_dir: str,
    resolved_target: Path,
) -> None:
    """Enforce that the claim target is the active round operator snapshot."""
    operator_path = round_entry.get("operator_path")
    workspace = state_path.parent.parent
    try:
        expected_name = expected_round_operator_name(workspace)
    except ValueError:
        expected_name = None
    # When the workspace source operator is resolvable, the claim target must
    # be the expected round operator snapshot name. This is checked before any
    # round-dir fallback so a claim on an unrelated .py file cannot repurpose
    # the operator edit gate.
    if expected_name is not None and resolved_target.name != expected_name:
        raise WorkflowError(
            EDIT_CLAIM_ERROR_CODE_WRONG_TARGET,
            f"claim target must be the expected operator snapshot {expected_name} "
            f"inside {round_dir}",
        )
    expected_operator = (
        workspace / operator_path
        if isinstance(operator_path, str) and operator_path
        else resolve_round_operator_file(workspace / round_dir)
    )
    if expected_operator is None:
        round_path = (workspace / round_dir).resolve()
        if (
            resolved_target.parent != round_path
            or resolved_target.suffix.lower() != ".py"
        ):
            raise WorkflowError(
                EDIT_CLAIM_ERROR_CODE_WRONG_TARGET,
                f"initial claim target must be one Python operator file directly inside {round_path}",
            )
    elif resolved_target != expected_operator.resolve():
        raise WorkflowError(
            EDIT_CLAIM_ERROR_CODE_WRONG_TARGET,
            f"claim target must be the active round operator snapshot: {expected_operator}",
        )


def _mirror_edit_claim_block(
    state_path: Path,
    round_dir: str,
    claim_details: dict[str, object],
) -> list[str]:
    """Best-effort attempts.md edit-claim mirror; workflow state stays authoritative."""
    warnings: list[str] = []
    try:
        _append_edit_claim_block(
            _attempts_path_for_round(state_path, round_dir),
            edit_claim=claim_details,
        )
    except OSError as exc:
        warnings.append(
            f"attempts.md edit-claim mirror could not be updated: {exc}. Workflow state remains authoritative."
        )
    return warnings


@dataclass(frozen=True)
class _RoundStateTransition:
    existing_state: dict[str, str] | None
    previous_round_strategy: str
    previous_analysis_policy: str
    next_round_strategy: str
    next_analysis_policy: str


def set_current_round_state(
    state_path: Path,
    *,
    round_strategy: str | None = None,
    analysis_policy: str | None = None,
    reason: str,
) -> dict[str, object]:
    normalized_reason = _validate_reason(reason)
    if round_strategy is None and analysis_policy is None:
        raise ValueError(
            "set-current-round-state requires --round-strategy and/or --analysis-policy"
        )

    payload = load_state(state_path)
    round_key, round_entry = _require_update_target_round(payload)
    transition = _resolve_round_state_transition(
        round_entry,
        round_strategy=round_strategy,
        analysis_policy=analysis_policy,
    )
    _validate_round_state_transition(transition)

    warnings = _build_transition_warnings(
        previous_round_strategy=transition.previous_round_strategy,
        next_round_strategy=transition.next_round_strategy,
        next_analysis_policy=transition.next_analysis_policy,
    )
    round_entry["strategy_state"] = _build_strategy_state(
        round_strategy=transition.next_round_strategy,
        analysis_policy=transition.next_analysis_policy,
        reason=normalized_reason,
        updated_by="set-current-round-state",
    )
    write_state(state_path, payload)

    round_dir, result_warnings = _mirror_round_state_update(
        state_path,
        round_entry,
        round_key=round_key,
        transition=transition,
        reason=normalized_reason,
        warnings=warnings,
    )
    return _round_state_update_result(round_dir, transition, normalized_reason, result_warnings)


def _round_state_update_result(
    round_dir: str,
    transition: _RoundStateTransition,
    reason: str,
    result_warnings: list[str],
) -> dict[str, object]:
    return _set_current_round_state_result(
        round_dir=round_dir,
        previous_round_strategy=(
            transition.previous_round_strategy if transition.existing_state is not None else None
        ),
        next_round_strategy=transition.next_round_strategy,
        previous_analysis_policy=(
            transition.previous_analysis_policy if transition.existing_state is not None else None
        ),
        next_analysis_policy=transition.next_analysis_policy,
        reason=reason,
        warnings=result_warnings,
    )


def _require_update_target_round(payload: dict[str, object]) -> tuple[str, dict[str, object]]:
    """Return the active round key and entry targeted by a strategy-state update."""
    if payload.get("phase") == PHASE_DEEP_ANALYSIS:
        raise ValueError("cannot update round strategy state during deep_analysis")
    if payload.get("phase") != PHASE_ROUND_ACTIVE or not isinstance(payload.get("current_round"), int):
        raise ValueError("no optimize round is currently active")

    current_round = cast(int, payload["current_round"])
    round_key = str(current_round)
    rounds = require_rounds_dict(payload)
    round_entry_obj = rounds.get(round_key)
    if not isinstance(round_entry_obj, dict):
        raise ValueError(f"missing workflow state entry for opt-round-{current_round}")
    round_entry = cast(dict[str, object], round_entry_obj)
    if round_entry.get("status") != "active":
        raise ValueError(f"cannot update non-active round opt-round-{current_round}")
    return round_key, round_entry


def _resolve_round_state_transition(
    round_entry: dict[str, object],
    *,
    round_strategy: str | None,
    analysis_policy: str | None,
) -> _RoundStateTransition:
    existing_state = _get_optional_strategy_state(round_entry)
    if existing_state is None and (round_strategy is None or analysis_policy is None):
        raise ValueError(
            "legacy active round is missing strategy_state; provide both --round-strategy and --analysis-policy"
        )

    previous_round_strategy = (
        existing_state["round_strategy"]
        if existing_state is not None
        else _validate_round_strategy(cast(str, round_strategy))
    )
    previous_analysis_policy = (
        existing_state["analysis_policy"]
        if existing_state is not None
        else _validate_analysis_policy(cast(str, analysis_policy))
    )
    next_round_strategy = (
        _validate_round_strategy(round_strategy)
        if round_strategy is not None
        else previous_round_strategy
    )
    next_analysis_policy = (
        _validate_analysis_policy(analysis_policy)
        if analysis_policy is not None
        else previous_analysis_policy
    )
    return _RoundStateTransition(
        existing_state=existing_state,
        previous_round_strategy=previous_round_strategy,
        previous_analysis_policy=previous_analysis_policy,
        next_round_strategy=next_round_strategy,
        next_analysis_policy=next_analysis_policy,
    )


def _validate_round_state_transition(transition: _RoundStateTransition) -> None:
    if (
        transition.previous_round_strategy == "plateau_review"
        and transition.next_round_strategy != "plateau_review"
        and transition.next_round_strategy not in {"structural_change", "focused_tuning"}
    ):
        raise ValueError(
            "leaving plateau_review requires round_strategy structural_change or focused_tuning"
        )

    if transition.existing_state is not None:
        if (
            transition.previous_round_strategy == transition.next_round_strategy
            and transition.previous_analysis_policy == transition.next_analysis_policy
        ):
            raise ValueError("state update would be a no-op")
        if (
            _ANALYSIS_POLICY_ORDER[transition.next_analysis_policy]
            < _ANALYSIS_POLICY_ORDER[transition.previous_analysis_policy]
        ):
            raise ValueError(
                "analysis_policy cannot become shallower within the same round"
            )


def _mirror_round_state_update(
    state_path: Path,
    round_entry: dict[str, object],
    *,
    round_key: str,
    transition: _RoundStateTransition,
    reason: str,
    warnings: list[str],
) -> tuple[str, list[str]]:
    """Best-effort attempts.md history mirror; workflow state stays authoritative."""
    round_dir = round_entry.get("round_dir")
    if not isinstance(round_dir, str) or not round_dir:
        raise ValueError(f"workflow state round {round_key} is missing round_dir")
    result_warnings = list(warnings)
    try:
        _append_state_update_block(
            _attempts_path_for_round(state_path, round_dir),
            source="set-current-round-state",
            round_strategy=transition.next_round_strategy,
            analysis_policy=transition.next_analysis_policy,
            reason=reason,
            previous_round_strategy=(
                transition.previous_round_strategy if transition.existing_state is not None else "<unset>"
            ),
            previous_analysis_policy=(
                transition.previous_analysis_policy if transition.existing_state is not None else "<unset>"
            ),
            warnings=result_warnings,
        )
    except OSError as exc:
        result_warnings.append(
            f"attempts.md history mirror could not be updated: {exc}. Workflow state remains authoritative."
        )
    return round_dir, result_warnings


def complete_round(
    state_path: Path,
    round_dir: str,
    *,
    current_round_arg: int | None = None,
    final_status: str = "passed",
) -> None:
    payload = load_state(state_path)
    round_number = parse_round_number(round_dir)
    round_key = str(round_number)
    rounds = require_rounds_dict(payload)

    if payload["phase"] != PHASE_ROUND_ACTIVE:
        raise ValueError(
            f"cannot complete {round_dir} while workflow phase is {payload['phase']}"
        )
    if payload.get("current_round") != round_number:
        raise ValueError(
            f"workflow state current_round={payload.get('current_round')} does not match {round_dir}"
        )
    if current_round_arg is not None and current_round_arg != round_number:
        raise ValueError(
            f"--current-round={current_round_arg} does not match workflow state round {round_number}"
        )

    round_entry_obj = rounds.get(round_key)
    if not isinstance(round_entry_obj, dict):
        raise ValueError(f"missing workflow state entry for {round_dir}")
    round_entry = cast(dict[str, object], round_entry_obj)
    if round_entry.get("status") != "active":
        raise ValueError(f"cannot complete non-active round {round_dir}")
    if final_status not in {"passed", "failed"}:
        raise ValueError(f"unsupported final_status for {round_dir}: {final_status!r}")

    round_entry["status"] = final_status
    round_entry.pop("started_at", None)
    round_entry.pop("ended_at", None)
    if isinstance(round_entry.get("edit_claim"), dict):
        cast(dict[str, object], round_entry["edit_claim"])["active"] = False
    payload["phase"] = PHASE_AWAITING_ROUND_START
    payload["current_round"] = None
    _activate_auto_deep_optimization_if_plateau(payload, state_path, round_dir)
    write_state(state_path, payload)
    try:
        _append_round_timing_event(
            state_path,
            round_dir=round_dir,
            event="round_end",
        )
    except OSError:
        # Round completion must not fail just because the best-effort timing log
        # could not be updated after workflow state has already been advanced.
        pass


def render_phase_summary(state_path: Path) -> str:
    payload = load_state(state_path)
    baseline = _require_baseline_dict(payload)
    reused = baseline.get("status") == "passed" and baseline.get("submitted_at") is None
    baseline_source = "pending"
    if baseline.get("status") == "passed":
        baseline_source = "reused" if reused else "freshly passed in this run"
    lines = [f"Current phase: {payload['phase']}"]
    current_round = payload.get("current_round")
    lines.append(
        f"Current round: {current_round}" if current_round is not None else "Current round: none"
    )
    if payload["phase"] == PHASE_ROUND_ACTIVE and isinstance(current_round, int):
        round_entry_obj = require_rounds_dict(payload).get(str(current_round))
        if isinstance(round_entry_obj, dict):
            strategy_state = _get_optional_strategy_state(cast(dict[str, object], round_entry_obj))
            if strategy_state is None:
                lines.append("Current round strategy state: missing")
            else:
                lines.append(
                    f"Current round strategy: {strategy_state['round_strategy']}"
                )
                lines.append(
                    f"Required analysis depth: {strategy_state['analysis_policy']}"
                )
                lines.append(
                    f"Current round reason: {strategy_state['reason']}"
                )
    lines.append(f"Baseline source: {baseline_source}")
    return "\n".join(lines)


def _validate_state(payload: dict[str, object]) -> None:
    schema_version = payload.get("schema_version")
    if schema_version not in {1, WORKFLOW_SCHEMA_VERSION}:
        raise ValueError(
            f"unsupported workflow state schema_version: {schema_version!r}"
        )

    deep_optimization = payload.get("deep_optimization")
    if deep_optimization is not None:
        _validate_deep_optimization_state(deep_optimization)

    _validate_pattern_usage_state(payload)
    _validate_pattern_recommendations_state(payload)
    _validate_language_state(payload)
    _validate_execution_state(payload.get("execution"))

    phase = payload.get("phase")
    if phase not in _PHASES:
        raise ValueError(f"unknown workflow state phase: {phase!r}")

    _validate_baseline_state(payload)

    rounds = require_rounds_dict(payload)
    _validate_current_round_consistency(payload, rounds, phase=phase)
    _validate_round_entries(rounds)


def _validate_pattern_usage_state(payload: dict[str, object]) -> None:
    pattern_usage = payload.get("pattern_usage")
    if pattern_usage is None:
        return
    if not isinstance(pattern_usage, dict):
        raise ValueError("workflow state pattern_usage must be an object")
    enabled = cast(dict[str, object], pattern_usage).get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("workflow state pattern_usage.enabled must be a boolean")


def _validate_pattern_recommendations_state(payload: dict[str, object]) -> None:
    pattern_recommendations = payload.get("pattern_recommendations")
    if pattern_recommendations is None:
        return
    if not isinstance(pattern_recommendations, dict):
        raise ValueError("workflow state pattern_recommendations must be an object")
    typed_recommendations = cast(dict[str, object], pattern_recommendations)
    for pattern_id, record in typed_recommendations.items():
        if not pattern_id:
            raise ValueError("workflow state pattern_recommendations has an invalid key")
        if not isinstance(record, dict):
            raise ValueError(
                f"workflow state pattern_recommendations[{pattern_id}] must be an object"
            )
        typed_record = cast(dict[str, object], record)
        if typed_record.get("id") != pattern_id:
            raise ValueError(
                f"workflow state pattern_recommendations[{pattern_id}] has mismatched id"
            )


def _validate_language_state(payload: dict[str, object]) -> None:
    language = payload.get("language", "triton")
    if not isinstance(language, str) or not language.strip():
        raise ValueError("workflow state language must be a non-empty string")


def _validate_execution_state(execution: object) -> None:
    if execution is not None and not isinstance(execution, dict):
        raise ValueError("workflow state execution must be an object")
    if not isinstance(execution, dict):
        return
    execution = cast(dict[str, object], execution)
    remote = execution.get("remote")
    remote_workdir = execution.get("remote_workdir")
    if remote is not None and (not isinstance(remote, str) or not remote.strip()):
        raise ValueError("workflow state execution.remote must be a non-empty string or null")
    if isinstance(remote, str) and remote.lstrip().startswith("-"):
        raise ValueError("workflow state execution.remote must not start with '-'")
    if remote_workdir is not None and (not isinstance(remote_workdir, str) or not remote_workdir.strip()):
        raise ValueError("workflow state execution.remote_workdir must be a non-empty string or null")
    if isinstance(remote_workdir, str) and remote_workdir.lstrip().startswith("-"):
        raise ValueError("workflow state execution.remote_workdir must not start with '-'")
    if remote is None and remote_workdir is not None:
        raise ValueError("workflow state execution.remote_workdir requires execution.remote")


def _validate_baseline_state(payload: dict[str, object]) -> None:
    baseline = _require_baseline_dict(payload)
    baseline_status = baseline.get("status")
    if baseline_status not in {"pending", "passed"}:
        raise ValueError(f"unknown baseline status: {baseline_status!r}")
    submitted_at = baseline.get("submitted_at")
    if submitted_at is not None and not isinstance(submitted_at, str):
        raise ValueError("baseline.submitted_at must be a string or null")


def _validate_current_round_consistency(
    payload: dict[str, object],
    rounds: dict[str, object],
    *,
    phase: object,
) -> None:
    current_round = payload.get("current_round")
    if phase in {PHASE_ROUND_ACTIVE, PHASE_DEEP_ANALYSIS}:
        if not isinstance(current_round, int):
            raise ValueError(f"phase={phase} requires a non-null integer current_round")
        current_entry_obj = rounds.get(str(current_round))
        if not isinstance(current_entry_obj, dict):
            raise ValueError(f"phase=round_active requires rounds[{current_round}]")
        current_entry = cast(dict[str, object], current_entry_obj)
        expected_status = "active" if phase == PHASE_ROUND_ACTIVE else "deep_analysis_required"
        if current_entry.get("status") != expected_status:
            raise ValueError(f"phase={phase} requires {expected_status} state for round {current_round}")
        if phase == PHASE_DEEP_ANALYSIS:
            _validate_deep_analysis_entry(current_entry, round_key=str(current_round))
    elif current_round is not None:
        raise ValueError(f"phase={phase} requires current_round=null")


def _validate_round_entries(rounds: dict[str, object]) -> None:
    for round_key, round_state in rounds.items():
        if not isinstance(round_state, dict):
            raise ValueError(f"workflow state round {round_key} must be an object")
        round_state_dict = cast(dict[str, object], round_state)
        _validate_round_entry_identity(round_state_dict, round_key=round_key)
        _validate_round_entry_timestamps(round_state_dict, round_key=round_key)
        strategy_state = round_state_dict.get("strategy_state")
        if strategy_state is not None:
            _validate_strategy_state(strategy_state, round_key=round_key)
        operator_path = round_state_dict.get("operator_path")
        if operator_path is not None and (
            not isinstance(operator_path, str) or not operator_path
        ):
            raise ValueError(
                f"workflow state round {round_key} operator_path must be a non-empty string"
            )
        edit_claim = round_state_dict.get("edit_claim")
        if edit_claim is not None:
            _validate_edit_claim(edit_claim, round_key=round_key)


def _validate_round_entry_identity(round_state_dict: dict[str, object], *, round_key: str) -> None:
    status = round_state_dict.get("status")
    if status not in {"active", "deep_analysis_required", "passed", "failed"}:
        raise ValueError(f"unknown round status for {round_key}: {status!r}")
    round_dir = round_state_dict.get("round_dir")
    if not isinstance(round_dir, str) or not round_dir:
        raise ValueError(f"workflow state round {round_key} is missing round_dir")
    if parse_round_number(round_dir) != int(round_key):
        raise ValueError(
            f"workflow state round key {round_key} does not match round_dir {round_dir}"
        )


def _validate_round_entry_timestamps(round_state_dict: dict[str, object], *, round_key: str) -> None:
    started_at = round_state_dict.get("started_at")
    if started_at is not None and (not isinstance(started_at, str) or not started_at):
        raise ValueError(f"workflow state round {round_key} started_at must be a non-empty string or null")
    ended_at = round_state_dict.get("ended_at")
    if ended_at is not None and (not isinstance(ended_at, str) or not ended_at):
        raise ValueError(f"workflow state round {round_key} ended_at must be a non-empty string or null")


def _deep_analysis_is_required(payload: dict[str, object]) -> bool:
    deep_optimization = payload.get("deep_optimization")
    if not isinstance(deep_optimization, dict):
        return False
    return cast(dict[str, object], deep_optimization).get("active") is True


def _first_auto_plateau_review_round(
    payload: dict[str, object],
    round_number: int,
) -> bool:
    deep_optimization = payload.get("deep_optimization")
    if not isinstance(deep_optimization, dict):
        return False
    deep_state = cast(dict[str, object], deep_optimization)
    activated_after_round = deep_state.get("activated_after_round")
    return (
        deep_state.get("policy") == "auto"
        and deep_state.get("active") is True
        and deep_state.get("activation_reason") == "speedup_plateau"
        and isinstance(activated_after_round, int)
        and round_number == activated_after_round + 1
    )


def _pattern_usage_enabled(payload: dict[str, object]) -> bool:
    pattern_usage = payload.get("pattern_usage")
    if not isinstance(pattern_usage, dict):
        return False
    return cast(dict[str, object], pattern_usage).get("enabled") is True


def _new_edit_claim_state(*, enabled: bool) -> dict[str, object]:
    return {
        "enabled": enabled,
        "active": False,
        "claimed_at": None,
    }


def _activate_auto_deep_optimization_if_plateau(
    payload: dict[str, object],
    state_path: Path,
    round_dir: str,
) -> None:
    deep_optimization = payload.get("deep_optimization")
    if not isinstance(deep_optimization, dict):
        return
    deep_optimization = cast(dict[str, object], deep_optimization)
    if deep_optimization.get("policy") != "auto" or deep_optimization.get("active") is True:
        return
    baseline = _require_baseline_dict(payload)
    integrity = baseline.get("integrity")
    if not isinstance(integrity, dict):
        return
    integrity = cast(dict[str, object], integrity)
    bench_perf = integrity.get("baseline_perf_file")
    if not isinstance(bench_perf, str):
        return
    from round.local_optimum import local_optimum_result

    result = local_optimum_result(
        state_path.parent.parent / round_dir,
        baseline_perf_path=Path(bench_perf),
    )
    if result is None:
        return
    deep_optimization["active"] = True
    deep_optimization["activated_after_round"] = parse_round_number(round_dir)
    deep_optimization["activation_reason"] = "speedup_plateau"


def _resolve_round_candidate_path(state_path: Path, round_dir: str) -> Path:
    candidate_dir = state_path.parent.parent / round_dir
    candidate = resolve_round_operator_file(candidate_dir)
    if candidate is None:
        raise ValueError(f"deep optimization requires a candidate Python file in {round_dir}")
    return candidate.resolve()


def _validate_deep_analysis_entry(round_entry: dict[str, object], *, round_key: str) -> None:
    value = round_entry.get("deep_analysis")
    if not isinstance(value, dict):
        raise ValueError(f"workflow state round {round_key} deep_analysis must be an object")
    deep_analysis = cast(dict[str, object], value)
    _validate_deep_analysis_identity(deep_analysis, round_key=round_key)
    _validate_deep_analysis_symptoms(deep_analysis, round_key=round_key)
    _validate_deep_analysis_evidence(deep_analysis, round_key=round_key)


def _validate_deep_analysis_identity(deep_analysis: dict[str, object], *, round_key: str) -> None:
    operator_file = deep_analysis.get("operator_file")
    operator_hash = deep_analysis.get("operator_sha256")
    if not isinstance(operator_file, str) or not operator_file:
        raise ValueError(f"workflow state round {round_key} deep_analysis.operator_file is invalid")
    if not isinstance(operator_hash, str) or not operator_hash.startswith("sha256:"):
        raise ValueError(f"workflow state round {round_key} deep_analysis.operator_sha256 is invalid")


def _validate_deep_analysis_symptoms(deep_analysis: dict[str, object], *, round_key: str) -> None:
    symptoms = deep_analysis.get("symptoms")
    if symptoms is None:
        return
    symptoms_invalid = (
        not isinstance(symptoms, list)
        or not symptoms
        or any(not isinstance(item, str) or not item for item in cast(list[object], symptoms))
    )
    if symptoms_invalid:
        raise ValueError(f"workflow state round {round_key} deep_analysis.symptoms is invalid")


def _validate_deep_analysis_evidence(deep_analysis: dict[str, object], *, round_key: str) -> None:
    profile_evidence = deep_analysis.get("profile_evidence")
    ir_evidence = deep_analysis.get("ir_evidence")
    selected_case_id = deep_analysis.get("selected_case_id")
    if profile_evidence is None and ir_evidence is None and selected_case_id is None:
        return
    evidence_complete = (
        isinstance(profile_evidence, list)
        and isinstance(ir_evidence, list)
        and isinstance(selected_case_id, str)
        and bool(selected_case_id)
    )
    if not evidence_complete:
        raise ValueError(f"workflow state round {round_key} deep_analysis evidence is invalid")
    evidence_lists = (
        cast(list[object], profile_evidence),
        cast(list[object], ir_evidence),
    )
    for evidence in evidence_lists:
        _validate_deep_analysis_evidence_selector(evidence, round_key=round_key)


def _validate_deep_analysis_evidence_selector(evidence: list[object], *, round_key: str) -> None:
    if len(evidence) != 1 or not isinstance(evidence[0], dict):
        raise ValueError(f"workflow state round {round_key} deep_analysis evidence is invalid")
    selector = cast(dict[str, object], evidence[0])
    if not isinstance(selector.get("record_id"), str) or not isinstance(
        selector.get("artifact_dir"), str
    ):
        raise ValueError(f"workflow state round {round_key} deep_analysis evidence is invalid")


def _new_deep_optimization_state(policy: str) -> dict[str, object]:
    if policy == "always":
        return {
            "policy": policy,
            "active": True,
            "activated_after_round": 0,
            "activation_reason": "policy_always",
        }
    return {
        "policy": policy,
        "active": False,
        "activated_after_round": None,
        "activation_reason": None,
    }


def _validate_deep_optimization_policy(policy: str) -> str:
    normalized = policy.strip()
    if normalized not in DEEP_OPTIMIZATION_POLICIES:
        raise ValueError(f"unknown deep optimization policy: {policy!r}")
    return normalized


def _validate_deep_optimization_state(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("workflow state deep_optimization must be an object")
    deep_optimization = cast(dict[str, object], value)
    policy = deep_optimization.get("policy")
    if not isinstance(policy, str) or policy not in DEEP_OPTIMIZATION_POLICIES:
        raise ValueError("workflow state deep_optimization.policy is invalid")
    active = deep_optimization.get("active")
    if not isinstance(active, bool):
        raise ValueError("workflow state deep_optimization.active must be a boolean")
    activated_after_round = deep_optimization.get("activated_after_round")
    activation_reason = deep_optimization.get("activation_reason")
    if active:
        if not isinstance(activated_after_round, int) or activated_after_round < 0:
            raise ValueError(
                "active deep optimization requires a non-negative activated_after_round"
            )
        if activation_reason not in {"policy_always", "speedup_plateau"}:
            raise ValueError("active deep optimization requires an activation_reason")
    elif activated_after_round is not None or activation_reason is not None:
        raise ValueError("inactive deep optimization cannot have activation metadata")
    if policy == "never" and active:
        raise ValueError("never deep optimization must remain inactive")
    always_state_invalid = (
        not active
        or activated_after_round != 0
        or activation_reason != "policy_always"
    )
    if policy == "always" and always_state_invalid:
        raise ValueError("always deep optimization must be active from round 0")
    if policy == "auto" and active and activation_reason != "speedup_plateau":
        raise ValueError("auto deep optimization requires speedup_plateau activation")


def _validate_strategy_state(strategy_state: object, *, round_key: str) -> None:
    if not isinstance(strategy_state, dict):
        raise ValueError(f"workflow state round {round_key} strategy_state must be an object")
    strategy_state_dict = cast(dict[str, object], strategy_state)
    round_strategy = strategy_state_dict.get("round_strategy")
    if round_strategy not in ROUND_STRATEGIES:
        raise ValueError(
            f"workflow state round {round_key} has unknown round_strategy: {round_strategy!r}"
        )
    analysis_policy = strategy_state_dict.get("analysis_policy")
    if analysis_policy not in ANALYSIS_POLICIES:
        raise ValueError(
            f"workflow state round {round_key} has unknown analysis_policy: {analysis_policy!r}"
        )
    reason = strategy_state_dict.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"workflow state round {round_key} strategy_state.reason must be a non-empty string")
    updated_at = strategy_state_dict.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at:
        raise ValueError(f"workflow state round {round_key} strategy_state.updated_at must be a non-empty string")
    updated_by = strategy_state_dict.get("updated_by")
    if updated_by not in UPDATED_BY_VALUES:
        raise ValueError(
            f"workflow state round {round_key} strategy_state.updated_by must be one of {UPDATED_BY_VALUES}"
        )


def _require_baseline_dict(payload: dict[str, object]) -> dict[str, object]:
    baseline = payload.get("baseline")
    if not isinstance(baseline, dict):
        raise ValueError("workflow state baseline must be an object")
    return cast(dict[str, object], baseline)


def require_rounds_dict(payload: dict[str, object]) -> dict[str, object]:
    rounds = payload.get("rounds")
    if not isinstance(rounds, dict):
        raise ValueError("workflow state rounds must be an object")
    return cast(dict[str, object], rounds)


def _get_optional_strategy_state(round_entry: dict[str, object]) -> dict[str, str] | None:
    strategy_state = round_entry.get("strategy_state")
    if strategy_state is None:
        return None
    if not isinstance(strategy_state, dict):
        raise ValueError("workflow round strategy_state must be an object")
    strategy_state_dict = cast(dict[str, object], strategy_state)
    round_strategy = strategy_state_dict.get("round_strategy")
    analysis_policy = strategy_state_dict.get("analysis_policy")
    reason = strategy_state_dict.get("reason")
    if not isinstance(round_strategy, str) or round_strategy not in ROUND_STRATEGIES:
        raise ValueError(f"workflow round strategy_state.round_strategy is invalid: {round_strategy!r}")
    if not isinstance(analysis_policy, str) or analysis_policy not in ANALYSIS_POLICIES:
        raise ValueError(f"workflow round strategy_state.analysis_policy is invalid: {analysis_policy!r}")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("workflow round strategy_state.reason must be a non-empty string")
    return {
        "round_strategy": round_strategy,
        "analysis_policy": analysis_policy,
        "reason": reason.strip(),
    }


def _validate_round_strategy(round_strategy: str) -> str:
    normalized = round_strategy.strip()
    if normalized not in ROUND_STRATEGIES:
        raise ValueError(f"unknown round_strategy: {round_strategy!r}")
    return normalized


def _validate_analysis_policy(analysis_policy: str) -> str:
    normalized = analysis_policy.strip()
    if normalized not in ANALYSIS_POLICIES:
        raise ValueError(f"unknown analysis_policy: {analysis_policy!r}")
    return normalized


def _validate_reason(reason: str) -> str:
    normalized = reason.strip()
    if not normalized:
        raise WorkflowError(EDIT_CLAIM_ERROR_CODE_REASON_REQUIRED, "reason is required")
    return normalized


def _validate_edit_claim_source(source_kind: str) -> str:
    normalized = source_kind.strip()
    if normalized not in EDIT_CLAIM_SOURCE_KINDS:
        raise WorkflowError(
            EDIT_CLAIM_ERROR_CODE_UNKNOWN_SOURCE,
            f"unknown edit claim source: {source_kind!r}",
        )
    return normalized


def _require_optimize_knowledge_pattern_claim(
    *,
    source_kind: str,
    pattern_paths: list[str],
) -> None:
    """Require a concrete optimize-knowledge pattern path for pattern claims."""
    if source_kind != "pattern":
        return
    if claim_includes_optimize_knowledge_pattern(pattern_paths=pattern_paths):
        return
    examples = " or ".join(
        f"*{infix}<name>.md" for infix in OPTIMIZE_KNOWLEDGE_PATTERN_INFIXES
    )
    kb_example = "*/cannbot-knowledge/knowledge/ops/<language>/optimizations/patterns/<name>.md"
    raise WorkflowError(
        EDIT_CLAIM_ERROR_CODE_PATTERN_REQUIRED,
        "pattern edit claim requires at least one optimize pattern file from the "
        f"cannbot-knowledge library ({kb_example}) "
        f"or a legacy staged knowledge-skill card ({examples}). "
        "Index, symptom, diagnosis, or cann-ext paths may be listed as extras "
        f"but do not satisfy this requirement. {CLAIM_RESPONSE_REQUIRED}",
    )


def _validate_edit_claim_pattern_paths(
    state_path: Path,
    *,
    source_kind: str,
    pattern_paths: list[str] | None,
) -> list[str]:
    normalized = _validate_claim_text_list(pattern_paths, "pattern_paths") or []
    if source_kind == "self-directed":
        if normalized:
            raise WorkflowError(
                EDIT_CLAIM_ERROR_CODE_SKILL_DEPENDENCY_INVALID,
                "self-directed edit claim must not include pattern paths",
            )
        return []
    if not normalized:
        raise WorkflowError(
            EDIT_CLAIM_ERROR_CODE_SKILL_DEPENDENCY_INVALID,
            "pattern edit claim requires at least one --pattern-path "
            "(the exact optimize-knowledge pattern markdown file)",
        )
    workspace = state_path.parent.parent
    for raw_path in normalized:
        candidate = Path(raw_path).expanduser()
        resolved = (
            candidate if candidate.is_absolute() else (workspace / candidate).resolve()
        )
        if not resolved.is_file() or not _is_staged_skill_path(resolved, workspace):
            raise WorkflowError(
                EDIT_CLAIM_ERROR_CODE_SKILL_DEPENDENCY_INVALID,
                f"edit claim pattern path is not a staged skill file: {raw_path}",
            )
    return normalized


def _is_staged_skill_path(resolved: Path, workspace: Path) -> bool:
    try:
        relative = resolved.relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return False
    if relative.startswith(_STAGED_SKILL_PATH_PREFIXES):
        return True
    # cannbot-knowledge 依赖仓的克隆目录（pattern 卡片的实际所在）
    return relative.startswith(".cannbot/dependencies/")


def _validate_claim_text_list(value: object, field_name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"edit claim {field_name} must be a list of non-empty strings")
    normalized: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"edit claim {field_name} must be a list of non-empty strings")
        normalized.append(item.strip())
    return normalized


def _validate_edit_claim(edit_claim: object, *, round_key: str) -> None:
    if not isinstance(edit_claim, dict):
        raise ValueError(f"workflow state round {round_key} edit_claim must be an object")
    claim = cast(dict[str, object], edit_claim)
    enabled = claim.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError(
            f"workflow state round {round_key} edit_claim.enabled must be a boolean"
        )
    active = claim.get("active")
    if not isinstance(active, bool):
        raise ValueError(
            f"workflow state round {round_key} edit_claim.active must be a boolean"
        )
    claimed_at = claim.get("claimed_at")
    if claimed_at is not None and (not isinstance(claimed_at, str) or not claimed_at):
        raise ValueError(
            f"workflow state round {round_key} edit_claim.claimed_at must be a string or null"
        )


def _build_strategy_state(
    *,
    round_strategy: str,
    analysis_policy: str,
    reason: str,
    updated_by: str,
) -> dict[str, object]:
    return {
        "round_strategy": round_strategy,
        "analysis_policy": analysis_policy,
        "reason": reason,
        "updated_at": _utc_now(),
        "updated_by": updated_by,
    }


def _build_strategy_state_warnings(
    *,
    round_strategy: str,
    analysis_policy: str,
) -> list[str]:
    warning = _UNUSUAL_STRATEGY_POLICY_COMBINATIONS.get(
        (round_strategy, analysis_policy)
    )
    return [warning] if warning is not None else []


def _build_transition_warnings(
    *,
    previous_round_strategy: str,
    next_round_strategy: str,
    next_analysis_policy: str,
) -> list[str]:
    warnings: list[str] = []
    transition_warning = _WARNING_WORTHY_STRATEGY_TRANSITIONS.get(
        (previous_round_strategy, next_round_strategy)
    )
    if transition_warning is not None:
        warnings.append(transition_warning)
    warnings.extend(
        _build_strategy_state_warnings(
            round_strategy=next_round_strategy,
            analysis_policy=next_analysis_policy,
        )
    )
    return warnings


def _append_state_update_block(
    attempts_path: Path,
    *,
    source: str,
    round_strategy: str,
    analysis_policy: str,
    reason: str,
    warnings: list[str],
    previous_round_strategy: str | None = None,
    previous_analysis_policy: str | None = None,
) -> None:
    lines = [f"## State Update {_utc_now()}", f"- Source: {source}"]
    if previous_round_strategy is None and previous_analysis_policy is None:
        lines.extend(
            [
                f"- Round strategy: {round_strategy}",
                f"- Analysis policy: {analysis_policy}",
            ]
        )
    else:
        lines.extend(
            [
                f"- Round strategy: {previous_round_strategy} -> {round_strategy}",
                f"- Analysis policy: {previous_analysis_policy} -> {analysis_policy}",
            ]
        )
    lines.append(f"- Reason: {reason}")
    for warning in warnings:
        lines.append(f"- Warning: {warning}")
    block = "\n".join(lines) + "\n"
    attempts_path.parent.mkdir(parents=True, exist_ok=True)
    existing = attempts_path.read_text(encoding="utf-8") if attempts_path.exists() else ""
    separator = ""
    if existing:
        separator = "\n" if existing.endswith("\n") else "\n\n"
    attempts_path.write_text(existing + separator + block, encoding="utf-8")


def _append_edit_claim_block(
    attempts_path: Path,
    *,
    edit_claim: dict[str, object],
) -> None:
    source_kind = cast(str, edit_claim["source_kind"])
    if source_kind == "pattern":
        raw_paths = edit_claim.get("pattern_paths")
        pattern_paths = (
            [str(path) for path in cast(list[object], raw_paths)]
            if isinstance(raw_paths, list)
            else []
        )
        source = "pattern " + ", ".join(pattern_paths or ["staged pattern"])
    else:
        source = "self-directed"
    lines = [
        f"## Edit Claim {edit_claim['timestamp']}",
        f"- Target: {edit_claim['target_path']}",
        f"- Source: {source}",
        f"- Pattern paths: {_claim_field_text(edit_claim.get('pattern_paths'))}",
        f"- Reason: {edit_claim['reason']}",
        f"- Pre-edit SHA-256: {edit_claim['pre_edit_sha256']}",
    ]
    block = "\n".join(lines) + "\n"
    attempts_path.parent.mkdir(parents=True, exist_ok=True)
    existing = attempts_path.read_text(encoding="utf-8") if attempts_path.exists() else ""
    separator = ""
    if existing:
        separator = "\n" if existing.endswith("\n") else "\n\n"
    attempts_path.write_text(existing + separator + block, encoding="utf-8")


def _claim_field_text(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, list):
        items = cast(list[object], value)
        return ", ".join(str(item) for item in items) if items else "none"
    return str(value)


def _attempts_path_for_round(state_path: Path, round_dir: str) -> Path:
    return state_path.parent.parent / round_dir / "attempts.md"


def _append_pattern_usage_event(
    state_path: Path,
    payload: dict[str, object],
    event: dict[str, object],
) -> None:
    """Append one JSONL event to the pattern-usage ledger.

    The ledger lives under ``.helix/pattern-usage.jsonl``. When
    pattern-usage is enabled the write is fail-closed: any write failure raises
    so the claim fails and the edit guard keeps blocking. When disabled the
    event is dropped and the claim proceeds without a ledger entry.
    """
    if not _pattern_usage_enabled(payload):
        return
    ledger_path = _pattern_usage_ledger_path(state_path)
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
    except OSError as exc:
        raise WorkflowError(
            EDIT_CLAIM_ERROR_CODE_LEDGER_UNAVAILABLE,
            f"pattern-usage ledger could not be updated: {exc}",
        ) from exc


def _pattern_usage_ledger_path(state_path: Path) -> Path:
    return state_path.parent / "pattern-usage.jsonl"


def _workspace_relative_path(state_path: Path, path: Path) -> str:
    workspace = state_path.parent.parent.resolve()
    try:
        return path.resolve().relative_to(workspace).as_posix()
    except ValueError as exc:
        raise ValueError(f"path must stay inside the optimize workspace: {path}") from exc


def _start_round_result(
    *,
    round_dir: str,
    round_strategy: str,
    analysis_policy: str,
    reason: str,
    warnings: list[str],
) -> dict[str, object]:
    result: dict[str, object] = {
        "round": round_dir,
        "round_strategy": round_strategy,
        "analysis_policy": analysis_policy,
        "reason": reason,
    }
    if warnings:
        result["warnings"] = warnings
    return result


def _set_current_round_state_result(
    *,
    round_dir: str,
    previous_round_strategy: str | None,
    next_round_strategy: str,
    previous_analysis_policy: str | None,
    next_analysis_policy: str,
    reason: str,
    warnings: list[str],
) -> dict[str, object]:
    result: dict[str, object] = {
        "round": round_dir,
        "round_strategy": next_round_strategy,
        "analysis_policy": next_analysis_policy,
        "reason": reason,
    }
    if previous_round_strategy is not None:
        result["previous_round_strategy"] = previous_round_strategy
    if previous_analysis_policy is not None:
        result["previous_analysis_policy"] = previous_analysis_policy
    if warnings:
        result["warnings"] = warnings
    return result


def parse_round_number(round_dir: str) -> int:
    match = ROUND_DIR_PATTERN.fullmatch(round_dir)
    if match is None:
        raise ValueError(f"invalid round directory name: {round_dir!r}")
    round_number = int(match.group(1), 10)
    if round_number < 1:
        raise ValueError(f"round number must be >= 1: {round_dir!r}")
    return round_number


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _round_timing_log_path(state_path: Path, round_dir: str) -> Path:
    return state_path.parent / "round-timings" / f"{round_dir}.jsonl"


def _append_round_timing_event(
    state_path: Path,
    *,
    round_dir: str,
    event: str,
) -> None:
    log_path = _round_timing_log_path(state_path, round_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event": event,
        "timestamp": _utc_now(),
        "round": round_dir,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def write_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as temp_handle:
            temp_path = Path(temp_handle.name)
            json.dump(payload, temp_handle, ensure_ascii=True, indent=2)
            temp_handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
