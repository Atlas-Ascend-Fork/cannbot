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

"""Rank existing effect summaries without collecting or reclassifying evidence."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from . import policy as search
from . import evidence


def _pareto(items):
    def dominates(left, right):
        keys = ("score", "cost", "risk")
        return all(left[k] <= right[k] for k in keys) and any(
            left[k] < right[k] for k in keys
        )

    for rank, front in enumerate(search.pareto_fronts(items, dominates), 1):
        for item in front:
            item["pareto_rank"] = rank


def build(measurements_path, frontier_path, holdout_path=None, neutral_control=None):
    frontier = search.load(frontier_path)
    measurements = evidence.read(measurements_path, frontier)
    nodes = {node["scheme_id"]: node for node in frontier["nodes"]}
    controls = next(
        (c for c in measurements["candidates"] if c["scheme_id"] == neutral_control),
        None,
    )
    control_ratios = (
        {c["case_id"]: c["ratio"] for c in controls["cases"]} if controls else {}
    )
    items = []
    for candidate in measurements["candidates"]:
        scheme = candidate["scheme_id"]
        if scheme == neutral_control:
            continue
        ratios = [case["ratio"] for case in candidate["cases"]]
        items.append(
            {
                **candidate,
                "score": statistics.geometric_mean(ratios),
                "cost": float(nodes[scheme].get("cost", 0)),
                "risk": float(nodes[scheme].get("risk", 0)),
            }
        )
    _pareto(items)
    observations = []
    for item in items:
        cases = item["cases"]
        observations.append(
            {
                "scheme_id": item["scheme_id"],
                "outcome": "measured",
                "effect_summary": item["effect_summary"],
                "score_distribution": {
                    "metric": "candidate_over_reference",
                    "unit": "case_median_ratio",
                    "effect_summary": item["effect_summary"],
                    "case_ids": [c["case_id"] for c in cases],
                    "samples": [c["ratio"] for c in cases],
                },
                "statistical_evidence": [
                    {"case_id": c["case_id"], "statistics": c["statistical_evidence"]}
                    for c in cases
                    if "statistical_evidence" in c
                ],
                "pareto_rank": item["pareto_rank"],
                "mechanism": {"status": "unknown"},
                "retry_condition": "complete evidence under the frozen performance policy",
                "factors": nodes[item["scheme_id"]].get("factors", {}),
                # Diagnostic only: a control never changes scores or policy verdicts.
                "differential": [
                    {
                        "case_id": c["case_id"],
                        "control_ratio": control_ratios[c["case_id"]],
                        "adjusted_ratio": c["ratio"] / control_ratios[c["case_id"]],
                    }
                    for c in cases
                    if c["case_id"] in control_ratios
                ]
                or None,
            }
        )
    best = min(items, key=lambda item: item["score"]) if items else None
    holdout = None
    if holdout_path:
        payload = evidence.read(holdout_path, frontier)
        search.require(
            payload["manifest"] == measurements["manifest"], "holdout manifest differs"
        )
        search.require(
            not set(payload["cases"]) & set(measurements["cases"]),
            "holdout cases overlap tuning cases",
        )
        if best:
            holdout = next(
                (
                    c
                    for c in payload["candidates"]
                    if c["scheme_id"] == best["scheme_id"]
                ),
                None,
            )
    eligible = bool(best and best["score"] < 1 and not best["requires_routing"])
    blocker = None
    if not best:
        blocker = "no_measured_candidate"
    elif not eligible:
        blocker = "tuning_set_not_eligible"
    elif holdout is None:
        blocker = "holdout_measurements_required"
    elif holdout["requires_routing"]:
        blocker = "holdout_regression"
    elif best["inconclusive_case_count"] or holdout["inconclusive_case_count"]:
        blocker = "evidence_pending"
    return {
        "schema_version": 1,
        "evidence_role": "screening",
        "neutral_control": neutral_control,
        "source_measurements": search.ref(measurements_path),
        "frontier": search.ref(frontier_path),
        "policy_id": measurements["policy_id"],
        "confirmation_required": True,
        "eligible_for_confirmation": eligible,
        "recommended": best["scheme_id"] if best else None,
        "holdout": holdout,
        "exploration_eligible": eligible,
        "exploration_blocker": None if eligible else blocker,
        "ready_for_confirmation": blocker is None,
        "confirmation_blocker": blocker,
        "no_go": [],
        "observations": observations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", type=Path, required=True)
    parser.add_argument("--frontier", type=Path, required=True)
    parser.add_argument("--holdout-measurements", type=Path)
    parser.add_argument("--neutral-control")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = build(
            args.measurements,
            args.frontier,
            args.holdout_measurements,
            args.neutral_control,
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(
            json.dumps({"status": "invalid", "reason": str(error)}, ensure_ascii=False)
        )
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
