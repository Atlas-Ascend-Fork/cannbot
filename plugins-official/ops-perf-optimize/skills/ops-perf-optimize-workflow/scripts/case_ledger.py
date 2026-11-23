#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: CANN-2.0
# This program is free software: you can redistribute it and/or modify it under the terms and conditions of
# the CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You should not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Per-case convergence ledger: machine-computed status partition and finish gates.

The ledger turns "还能不能优化" from an LLM judgement into a script-decidable
bookkeeping problem (invariant I1): a run may only claim convergence-type
terminal reasons when every frozen tuning case is in a machine-checkable
terminal state. Verdicts and waivers are bound to identities (invariant I3):
a converged claim survives only while the reference implementation it was
derived on stays current and its evidence files stay intact. Pure functions
only; all file I/O lives in workflow_state.py, which passes plain data in via
``inputs`` dicts.
"""

from __future__ import annotations

import json
import math
from typing import Any

SCHEMA_VERSION = 1
CASE_STATUSES = ("pending", "headroom_open", "optimized", "converged", "waived")
UNRESOLVED_CASE_STATUSES = ("pending", "headroom_open")
CONVERGENCE_REASON_CODES = ("no_material_improvement", "ceiling_bound")
CEILING_VERDICTS = (
    "NEAR-BANDWIDTH-CEILING",
    "NEAR-COMPUTE-CEILING",
    "MEMORY-CEILING",
)
UNSPECIFIED_DEVICE = "(device unspecified)"
STATUS_LABELS = {
    "pending": "未测",
    "headroom_open": "未达标",
    "optimized": "已达标",
    "converged": "收敛(逐case证据)",
    "waived": "用户豁免",
}


def soc_from_stage(stage: str) -> str | None:
    """integration.performance.<soc> checkpoints carry a per-SoC measurement."""
    prefix = "integration.performance."
    return stage[len(prefix):] if stage.startswith(prefix) else None


def _is_positive_finite(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value > 0


def targets_map(
    targets_payload: dict[str, Any],
    expected_keys: set[tuple[str, str]] | None = None,
) -> dict[str, dict[str, float]]:
    """performance-targets.json payload → validated {case_id: {soc: target_us}}."""
    rows = targets_payload.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ValueError("performance-targets.json requires a non-empty cases list")
    cases: dict[str, dict[str, float]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("performance target rows must be objects")
        case_id = row.get("case_id")
        soc = row.get("target_soc")
        target_us = row.get("target_us")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("performance target requires non-empty case_id/target_soc")
        if not isinstance(soc, str) or not soc.strip():
            raise ValueError("performance target requires non-empty case_id/target_soc")
        if not _is_positive_finite(target_us):
            raise ValueError(
                f"performance target must be finite and positive: {(case_id, soc)}"
            )
        key = (case_id, soc)
        if key in seen:
            raise ValueError(f"duplicate performance target: {key}")
        seen.add(key)
        cases.setdefault(case_id, {})[soc] = float(target_us)
    if expected_keys is not None and seen != expected_keys:
        raise ValueError(
            "performance target coverage differs from the frozen collection: "
            f"missing={sorted(expected_keys - seen)}, extra={sorted(seen - expected_keys)}"
        )
    return cases


def _positive_finite(value: Any, label: str) -> float:
    if not _is_positive_finite(value):
        raise ValueError(f"{label} must be finite and positive")
    return float(value)


def _case_status(
    targets: dict[str, float],
    measurements: dict[str, float],
    single_soc: bool,
) -> tuple[str, float | None]:
    """Derive machine status from per-SoC targets and measurements.

    A measurement satisfies a target SoC only when taken on that SoC
    (stage-suffixed checkpoint) or when the run targets exactly one SoC and
    the measurement device is unspecified. Honest by default: anything not
    proven met stays unresolved.
    """
    if not measurements:
        return "pending", None
    best = min(measurements.values())
    if not targets:
        # Measured but no frozen target row: nothing can be proven met.
        return "headroom_open", best
    for soc, target_us in targets.items():
        measured = measurements.get(soc)
        if measured is None and single_soc:
            measured = measurements.get(UNSPECIFIED_DEVICE)
        if measured is None or measured > target_us:
            return "headroom_open", best
    return "optimized", best


def _replay_checkpoints(
    checkpoints: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, float]], dict[str, str], str | None]:
    measured: dict[str, dict[str, float]] = {}
    evidence: dict[str, str] = {}
    reference: str | None = None
    for checkpoint in checkpoints:
        selected = checkpoint.get("selected_candidate")
        if selected and reference is not None and selected != reference:
            # A terminal claim belongs to one current implementation. Never
            # stitch disjoint case results from an older reference into a newly
            # promoted one; unchanged cases must be measured again.
            measured = {}
            evidence = {}
        reference = selected or reference
        device = checkpoint.get("soc") or UNSPECIFIED_DEVICE
        for case_id, value in (checkpoint.get("cumulative") or {}).items():
            measured.setdefault(case_id, {})[device] = _positive_finite(
                value, f"measured candidate_total_us for {case_id}"
            )
            evidence[case_id] = checkpoint["name"]
    return measured, evidence, reference


def _restore_previous_status(
    entry: dict[str, Any],
    prev: dict[str, Any],
    derived: str,
    case_id: str,
    context: dict[str, Any],
) -> None:
    prev_status = prev.get("status")
    # Sticky: a waiver survives until the case is provably optimized.
    if prev_status == "waived" and derived != "optimized":
        entry["status"] = "waived"
        entry["waiver"] = prev.get("waiver")
    if prev_status != "converged":
        return
    # Sticky: converged survives only while bound to the current reference
    # implementation and its evidence files stay intact; a promotion or a
    # tampered evidence chain demotes the claim (invariant I3).
    verdict = prev.get("verdict") or {}
    reference = context["reference"]
    bound = reference is not None and verdict.get("reference_identity") == reference
    invalid_verdicts = context["invalid_verdicts"]
    if derived == "optimized":
        return
    if bound and case_id not in invalid_verdicts:
        entry["status"] = "converged"
        entry["verdict"] = verdict
        return
    entry["status"] = "headroom_open" if entry["measured_us"] else "pending"
    if not verdict:
        return
    if case_id in invalid_verdicts:
        reason = "verdict_evidence_changed"
    elif not bound:
        reason = "reference_implementation_changed"
    else:
        reason = "measurement_no_longer_supports_claim"
    entry["stale_verdict"] = {**verdict, "demoted_because": reason}


def _recompute_case(
    case_id: str, prev: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    targets = context["targets"].get(case_id, {})
    measurements = context["measured"].get(case_id, {})
    derived, best = _case_status(targets, measurements, context["single_soc"])
    entry: dict[str, Any] = {
        "status": derived,
        "target_us": targets,
        "measured_us": measurements,
        "updated_at": context["now"],
    }
    if not targets:
        entry["no_target"] = True
    if best is not None:
        entry["best_us"] = best
        entry["evidence_checkpoint"] = context["evidence"][case_id]
        if targets:
            # Remaining distance to the strictest frozen target.
            entry["gap_us"] = round(best - min(targets.values()), 6)
    _restore_previous_status(entry, prev, derived, case_id, context)
    return entry


def _recompute_cases(
    previous_cases: dict[str, Any],
    by_case: dict[str, dict[str, float]],
    inputs: dict[str, Any],
    now: str,
) -> tuple[str | None, dict[str, Any]]:
    checkpoints = inputs.get("checkpoints") or []
    single_soc = bool(inputs.get("single_soc"))
    invalid_verdicts = set(inputs.get("invalid_verdicts") or ())
    measured, evidence, reference = _replay_checkpoints(checkpoints)
    context = {
        "targets": by_case,
        "measured": measured,
        "evidence": evidence,
        "reference": reference,
        "single_soc": single_soc,
        "invalid_verdicts": invalid_verdicts,
        "now": now,
    }
    cases = {}
    for case_id in sorted(set(by_case) | set(measured)):
        prev = previous_cases.get(case_id) or {}
        cases[case_id] = _recompute_case(case_id, prev, context)
    return reference, cases


def recompute(
    previous: dict[str, Any] | None,
    inputs: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    """Rebuild the ledger from plain data (no file I/O).

    inputs keys:
      targets: performance-targets.json payload or None
      targets_identity: {"path","sha256"} artifact identity or None
      targets_error: str | None when targets could not be located/validated
      single_soc: bool — manifest targets exactly one SoC
      expected_target_keys: frozen {(case_id, soc)} keys, or None for legacy runs
      checkpoints: ordered list (oldest first) of
        {"name": stage, "soc": soc|None, "selected_candidate": str,
         "cumulative": {case_id: candidate_total_us}}
      invalid_verdicts: case_ids whose registered verdict/evidence files changed
    """
    ledger: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "targets": inputs.get("targets_identity"),
        "targets_error": inputs.get("targets_error"),
        "reference_candidate": None,
        "computed_at": now,
        "cases": {},
    }
    previous_cases = (previous or {}).get("cases", {})
    targets_payload = inputs.get("targets")
    by_case = (
        targets_map(targets_payload, inputs.get("expected_target_keys"))
        if targets_payload is not None
        else {}
    )
    reference, cases = _recompute_cases(previous_cases, by_case, inputs, now)
    ledger["reference_candidate"] = reference
    ledger["cases"] = cases
    return ledger


def counts(ledger: dict[str, Any] | None) -> dict[str, int]:
    result = {status: 0 for status in CASE_STATUSES}
    total = 0
    for entry in (ledger or {}).get("cases", {}).values():
        result[entry["status"]] = result.get(entry["status"], 0) + 1
        total += 1
    result["total"] = total
    return result


def unresolved_cases(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case_id,
            "status": entry["status"],
            **{key: entry[key] for key in ("best_us", "gap_us") if key in entry},
        }
        for case_id, entry in sorted((ledger or {}).get("cases", {}).items())
        if entry["status"] in UNRESOLVED_CASE_STATUSES
    ]


def _unresolved_listing(unresolved: list[dict[str, Any]]) -> str:
    listing = ", ".join(
        f"{item['case_id']}[{item['status']}]" for item in unresolved[:20]
    )
    if len(unresolved) > 20:
        listing += f", ... (+{len(unresolved) - 20} more)"
    return listing


def _require_verifiable(ledger: dict[str, Any] | None, claim: str) -> None:
    """Shared precondition: a terminal claim needs usable targets and evidence."""
    if (ledger or {}).get("targets_error"):
        raise ValueError(
            f"cannot {claim}: per-case targets are unavailable or invalid "
            f"({ledger.get('targets_error')}). Fix the target evidence or finish "
            "with an honest reason (budget_exhausted / awaiting_operator)."
        )
    if (ledger or {}).get("evidence_errors"):
        raise ValueError(
            f"cannot {claim} with invalid performance evidence: "
            + json.dumps(ledger["evidence_errors"], ensure_ascii=False)
        )
    if counts(ledger)["total"] == 0:
        raise ValueError(f"cannot {claim}: the per-case target ledger is empty")


def gate_convergence_finish(ledger: dict[str, Any] | None) -> None:
    """Invariant I1 as a hard gate for convergence-type terminal reasons."""
    _require_verifiable(ledger, "claim convergence")
    unresolved = unresolved_cases(ledger)
    if not unresolved:
        return
    raise ValueError(
        "cannot claim no_material_improvement/ceiling_bound with unresolved cases: "
        f"{_unresolved_listing(unresolved)}. Every frozen tuning case must be "
        "optimized, converged (with a per-case verdict bound to the current "
        "reference implementation) or waived by an operator decision. For an honest "
        "stop use reason-code budget_exhausted, or continue the loop."
    )


def gate_per_case_objective(ledger: dict[str, Any] | None) -> None:
    """Issue #205: success under a per_case objective requires every case met.

    An aggregate metric (e.g. geomean speedup) can pass while most cases still
    miss their per-case bottom line; with the per_case acceptance scope such a
    run must not be reported ACHIEVED. Aggregate scope is an explicit,
    user-confirmed request field and is not gated here.
    """
    _require_verifiable(ledger, "verify a per_case objective")
    unresolved = unresolved_cases(ledger)
    if not unresolved:
        return
    total = counts(ledger)["total"]
    raise ValueError(
        "per_case objective not met: "
        f"{len(unresolved)} of {total} frozen cases still unresolved "
        f"({_unresolved_listing(unresolved)}). An aggregate metric passing must not "
        "be reported as ACHIEVED under the per-case acceptance scope. Continue the "
        "loop, waive cases with an operator decision, or finish with "
        "budget_exhausted/awaiting_operator; switching to an aggregate objective "
        "requires an explicit user-confirmed request."
    )


def terminal_summary(ledger: dict[str, Any] | None) -> dict[str, Any]:
    """Machine-generated honesty block attached to the terminal record."""
    summary = counts(ledger)
    summary["unresolved"] = unresolved_cases(ledger)
    summary["unresolved_count"] = len(summary["unresolved"])
    if (ledger or {}).get("targets_error"):
        summary["targets_error"] = ledger["targets_error"]
    return summary


def inspect_view(ledger: dict[str, Any] | None) -> dict[str, Any]:
    """Bounded ledger view for `inspect`: counts, unresolved, reference, errors."""
    view: dict[str, Any] = {
        "counts": counts(ledger),
        "unresolved": unresolved_cases(ledger),
        "reference_candidate": (ledger or {}).get("reference_candidate"),
    }
    for key in ("targets_error", "evidence_errors"):
        if (ledger or {}).get(key):
            view[key] = ledger[key]
    return view


def _verdict_evidence_issues(evidence: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(evidence, list) or not evidence:
        issues.append("verdict requires non-empty evidence: [{path, sha256}]")
        return issues
    for item in evidence:
        if not isinstance(item, dict):
            issues.append("verdict evidence entries must be objects")
            continue
        path = item.get("path")
        sha = item.get("sha256")
        if not isinstance(path, str) or not path.startswith("/"):
            issues.append("verdict evidence path must be absolute")
        if not isinstance(sha, str) or not sha:
            issues.append("verdict evidence sha256 is required")
    return issues


def verdict_issues(
    payload: dict[str, Any], case_id: str, reference: str | None
) -> list[str]:
    """Validate a per-case ceiling verdict artifact (pure checks, no file I/O)."""
    issues: list[str] = []
    if payload.get("schema_version") != 1:
        issues.append("verdict schema_version must be 1")
    if payload.get("case_id") != case_id:
        issues.append(f"verdict case_id {payload.get('case_id')!r} != {case_id!r}")
    if payload.get("verdict") not in CEILING_VERDICTS:
        issues.append(
            f"verdict must be one of {CEILING_VERDICTS}, got {payload.get('verdict')!r}"
        )
    for key in ("measured_us", "ceiling_us"):
        if not _is_positive_finite(payload.get(key)):
            issues.append(f"verdict requires finite positive numeric {key}")
    issues.extend(_verdict_evidence_issues(payload.get("evidence")))
    identity = payload.get("reference_identity")
    if not isinstance(identity, str) or not identity:
        issues.append("verdict requires reference_identity")
    elif reference is not None and identity != reference:
        issues.append(
            f"verdict reference_identity {identity!r} is stale; the current reference "
            f"implementation is {reference!r} — re-derive the verdict on the current "
            "implementation before claiming convergence"
        )
    return issues


def _target_text(entry: dict[str, Any]) -> str:
    targets = entry.get("target_us") or {}
    if not targets:
        return "-"
    return "; ".join(f"{soc}={value:g}" for soc, value in sorted(targets.items()))


def _report_basis(entry: dict[str, Any]) -> str:
    verdict = entry.get("verdict") or {}
    if entry["status"] == "converged":
        return (
            f"{verdict.get('verdict', '-')} @ "
            f"{verdict.get('reference_identity', '-')}"
        )
    if entry["status"] == "waived":
        return f"豁免：{entry.get('waiver', {}).get('reason', '-')}"
    if entry.get("stale_verdict"):
        return f"verdict 已过期（{entry['stale_verdict'].get('demoted_because')}）"
    return entry.get("evidence_checkpoint") or "-"


def _report_case_lines(ledger: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "| case_id | 状态 | 目标(us) | 最优实测(us) | 剩余差距(us) | 依据 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for case_id, entry in sorted(ledger["cases"].items()):
        gap = entry.get("gap_us")
        lines.append(
            f"| {case_id} | {STATUS_LABELS[entry['status']]} | "
            f"{_target_text(entry)} | "
            f"{entry.get('best_us', '-')} | "
            f"{gap if gap is not None else '-'} | {_report_basis(entry)} |"
        )
    return lines


def report_lines(ledger: dict[str, Any] | None) -> list[str]:
    """Report section; script-rendered so the wording cannot drift into "优化不动"."""
    if not ledger:
        return []
    summary = counts(ledger)
    lines = [
        "",
        "## 逐 case 收敛账本",
        "",
        f"- 目标全集 {summary['total']} 个 case；已达标 {summary['optimized']} · "
        f"收敛(逐case证据) {summary['converged']} · 用户豁免 {summary['waived']} · "
        f"未达标 {summary['headroom_open']} · 未测 {summary['pending']}。",
        f"- 当前参考实现：`{ledger.get('reference_candidate') or '-'}`",
    ]
    if ledger.get("targets_error"):
        lines.append(
            f"- ⚠ 账本不可用：{ledger['targets_error']}；收敛类终态被拒绝，"
            "预算停止须如实申报（budget_exhausted）。"
        )
        return lines
    if summary["total"]:
        lines.extend(_report_case_lines(ledger))
    unresolved = unresolved_cases(ledger)
    if unresolved:
        listing = ", ".join(item["case_id"] for item in unresolved)
        lines.append("")
        lines.append(
            "- ⚠ 未了结 case（阻止 no_material_improvement/ceiling_bound 终态）："
            f"{listing}"
        )
    return lines


def _achieved_cases(ledger: dict[str, Any] | None) -> list[str]:
    return sorted(
        case_id
        for case_id, entry in (ledger or {}).get("cases", {}).items()
        if entry["status"] == "optimized"
    )


def _verified_mechanisms(state: dict[str, Any]) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in state.get("events", []):
        result = event.get("result") or {}
        mechanism = result.get("mechanism") or {}
        if (
            event.get("kind") != "search_result"
            or event.get("invalidated")
            or mechanism.get("status") != "verified"
        ):
            continue
        scheme_id = result.get("scheme_id")
        if not isinstance(scheme_id, str) or not scheme_id:
            raise ValueError("verified search_result is missing result.scheme_id")
        if scheme_id in seen:
            continue
        seen.add(scheme_id)
        verified.append(
            {
                "scheme_id": scheme_id,
                "mechanism": mechanism,
                "evidence": mechanism.get("evidence"),
            }
        )
    return verified


def _remaining_work_inherit(
    state: dict[str, Any], ledger: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    return {
        "note": "继承白名单：冻结输入与基线、已验证机制、已达标 case 的结论",
        "frozen_inputs": manifest.get("inputs") or {},
        "reference_candidate": ledger.get("reference_candidate"),
        "achieved_cases": _achieved_cases(ledger),
        "verified_mechanisms": _verified_mechanisms(state),
    }


def remaining_work_envelope(
    state: dict[str, Any],
    ledger: dict[str, Any] | None,
    now: str,
    *,
    state_identity: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Focused follow-up run proposal from the ledger (the "fresh window" made official).

    Inherits frozen inputs, baseline evidence and verified mechanisms
    (whitelist); deliberately drops failure priors, stagnation counters and
    retry blocks. Auditable and state-backed instead of an ad-hoc new session.
    """
    _require_verifiable(ledger, "generate a remaining-work envelope")
    summary = counts(ledger)
    if not summary["total"]:
        raise ValueError("cannot generate remaining-work from an empty target ledger")
    return {
        "schema_version": 2,
        "generated_at": now,
        "source_state": state_identity,
        "source_manifest": state.get("manifest"),
        "remaining_cases": unresolved_cases(ledger),
        "summary": summary,
        "inherit": _remaining_work_inherit(state, ledger, manifest),
        "do_not_inherit": {
            "note": (
                "甩掉黑名单：失败先验、停滞计数、retry 封锁不跨 run 继承；"
                "机制可在新证据下重新尝试"
            ),
            "stagnation_counters": "reset",
            "failure_observations": "excluded",
            "retry_blocks": "excluded",
        },
        "usage": (
            "用 remaining_cases 构造聚焦新 run 的调优集合（prepare_case_sets "
            "create-request --performance-cases <csv>），基线证据按身份复用；"
            "不得把本信封当作原 run 的收敛结论"
        ),
    }
