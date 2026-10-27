# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Rank-verdict record shaping for the multirank runner's verification.json multirank
block.

Per-case isolation means the runner measures ONE CASE per launch; these
helpers fold the per-case rank summaries back into the group-shaped
rank_verdicts contract the finalize gate validates (exactly world_size
entries per group, each self-describing its covered cases), and shape the
UNVERIFIED card-shortage records (full-group placeholder vs per-case
entries).

Zero external dependencies (pure dict shaping) — imported by multirank_runner and
by the finalize rank-verdicts gate (ported in a follow-up task).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GroupUnverifiedRecord:
    """One group's card-short outcome feeding record_group_unverified.

    Construct with one keyword per line; the two output dicts stay separate
    parameters (they are cumulative containers owned by the caller).
    """

    ws: int
    group_cases: list
    ran: list
    missing: list
    probe_label: str


def failed_cases_of(rs: dict) -> list[dict]:
    """Per-case failure detail of one rank summary (case name + precision

    numbers) so a failure stays diagnosable after the rank logs rotate.
    verdict == FAIL / EVAL_ERR = genuinely failed cases. tier1_pass is NOT
    the discriminator — a PASS_T2 case has tier1_pass=False yet is a pass
    (rescued by the competitor-parity arm), and must not be listed as a
    failure.
    """
    return [
        {
            "case_id": c.get("case_id"),
            "verdict": c.get("verdict"),
            "ours_mere": c.get("ours_mere"),
            "ours_mare": c.get("ours_mare"),
            "comp_mere": c.get("comp_mere"),
            "comp_mare": c.get("comp_mare"),
        }
        for c in (rs.get("results") or [])
        if c.get("verdict") in ("FAIL", "EVAL_ERR")
    ]


def rank_verdict_entry(rs: dict, cases: list | None = None) -> dict:
    """One rank_verdicts entry. `cases` names the cases this entry folds

    (coverage-partition evidence for the finalize gate); FAIL additionally
    carries `failed_cases`.
    """
    covered = (
        cases
        if cases is not None
        else [c.get("case_id") for c in (rs.get("results") or [])]
    )
    entry = {"rank": rs.get("rank"), "status": rs.get("status"), "cases": covered}
    failed = failed_cases_of(rs)
    if failed:
        entry["failed_cases"] = failed
    return entry


def _fold_one_rank(r: int, ran: list) -> dict:
    """Entry r: every case rank-r ran; PASS only if all folded summaries PASS."""
    covered: list = []
    summaries: list = []
    for cname, rank_summaries, _rank_ok in ran:
        for rs in rank_summaries:
            if rs.get("rank") == r:
                covered.append(cname)
                summaries.append(rs)
    status = (
        "PASS"
        if summaries and all(rs.get("status") == "PASS" for rs in summaries)
        else "FAIL"
    )
    entry = {"rank": r, "status": status, "cases": covered}
    failed: list = []
    for rs in summaries:
        failed.extend(failed_cases_of(rs))
    if failed:
        entry["failed_cases"] = failed
    return entry


def fold_rank_verdicts(ws: int, ran: list) -> list[dict]:
    """Fold per-case rank summaries into the rank_verdicts group shape —

    exactly ws entries (the finalize gate's structural contract).
    `ran` is [(case_name, rank_summaries, rank_ok)] for the cases that
    launched at this ws. Entry r folds every case rank-r ran: status PASS
    only if every folded summary PASSed; `cases` records the covered case
    names; FAIL entries carry the failed-case detail of every folded case.
    """
    return [_fold_one_rank(r, ran) for r in range(ws)]


def case_verdicts_of(ran: list, leaks: "dict[str, str] | None" = None) -> dict:
    """Compact per-case verdict map of one group's launched cases.

    `ran` is [(case_name, rank_summaries, rank_ok)] exactly as _run_group_cases
    produces it (one launch per case, --filter-case, so each rank summary's
    results cover that single case). The O5 coverage-aware reconcile compares
    these per-cell identities against the claim and folds them into a claim
    upgrade — finer than the aggregate pass_a counts, which cannot say WHICH
    case×rank cell passed.
    `leaks` maps a case name to a post-run probe-leak note (confirm_idle saw
    residual processes after the case finished); it lands on that case's
    entry as `probe_leak` — a hygiene note ORTHOGONAL to the verdicts (any
    status may carry it), never a status change.
    """
    out: dict = {}
    for cname, rank_summaries, _rank_ok in ran:
        ranks: dict = {}
        failed: list = []
        tier1 = 0
        tier2 = 0
        total = 0
        for rs in rank_summaries:
            results = rs.get("results") or [{}]
            ranks[str(rs.get("rank"))] = results[0].get("verdict") or rs.get("status")
            tier1 += int(rs.get("tier1_pass", 0) or 0)
            tier2 += int(rs.get("tier2_pass", 0) or 0)
            total += int(rs.get("total", 0) or 0)
            failed.extend(failed_cases_of(rs))
        entry = {
            "world_size": len(rank_summaries),
            "ranks": ranks,
            "failed_cases": failed,
            "tier1_pass": tier1,
            "tier2_pass": tier2,
            "total": total,
        }
        if leaks and cname in leaks:
            entry["probe_leak"] = leaks[cname]
        out[cname] = entry
    return out


def record_group_unverified(
    record: GroupUnverifiedRecord, unverified: dict, unverified_cases: dict
) -> None:
    """Record a group's card-short cases: ALL missing → the full-group

    placeholder (the finalize gate's shape); some ran → per-case
    unverified_cases entries.
    """
    ws, group_cases = record.ws, record.group_cases
    ran, missing, probe_label = record.ran, record.missing, record.probe_label
    if missing and not ran:
        c0, e0 = missing[0]
        unverified[str(ws)] = {
            "status": "UNVERIFIED",
            "reason": "card_shortage",
            "detail": (
                f"all {len(group_cases)} case(s) at world_size={ws} "
                f"card-short (e.g. {c0['name']}: {e0})"
            ),
            "probe": probe_label,
        }
    elif missing:
        for c, e in missing:
            unverified_cases[c["name"]] = {
                "status": "UNVERIFIED",
                "reason": "card_shortage",
                "detail": f"needed {ws} idle NPU(s): {e}",
                "probe": probe_label,
                "world_size": ws,
            }
