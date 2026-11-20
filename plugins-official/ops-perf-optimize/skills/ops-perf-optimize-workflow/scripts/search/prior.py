# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Measured priors derived from existing workflow events and effect summaries.

Keep the original search's hierarchical prior; workflow artifacts remain the
source of truth, including across runs. This module owns no persistent store.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path

from . import policy

SHRINK_N = 3.0


def read_history(paths):
    """Read completed, applicable measurements, once per original decision."""
    records, seen = [], set()
    for path in dict.fromkeys(Path(p).resolve() for p in paths):
        policy.accepted_from_state(path)  # Verify stages and their dependencies.
        state = policy.load(path)
        manifest = policy.load(state["manifest"]["path"])
        current = policy.replay(state)
        for scheme, event in current["results"].items():
            if scheme in current["retired"] or event["result"]["outcome"] != "measured":
                continue
            plan, contract = current["decisions"][scheme]
            reference = event["result"]["effect_summary"]
            key = (plan["contract"]["sha256"], reference["sha256"])
            if key in seen:
                continue
            seen.add(key)
            summary, _ = policy.checked_summary(reference, manifest)
            search = contract["search"]
            frontier = current["frontiers"].get(event["round"], {})
            node = next(
                (n for n in frontier.get("nodes", []) if n["scheme_id"] == scheme), {}
            )
            records.append(
                {
                    "scheme_id": scheme,
                    "mechanism": search["mechanism"],
                    "mechanism_status": event["result"]
                    .get("mechanism", {})
                    .get("status", "unknown"),
                    "factors": search.get("candidate_factors", node.get("factors", {})),
                    "expected_gain_range": node.get("expected_gain_range"),
                    "parent": search["parent"],
                    "workload": search["workload"],
                    "target_socs": contract["target_socs"],
                    "effect_summary": reference,
                    "contract": plan["contract"],
                    "cases": [
                        {
                            **case,
                            "candidate_us": case["candidate_total_us"],
                            "reference_us": case["baseline_total_us"],
                            "ratio": case["candidate_total_us"]
                            / case["baseline_total_us"],
                        }
                        for case in summary["cases"]
                    ],
                }
            )
    return records


def iter_rows(history, *, soc=None):
    rows = []
    for item in history:
        targets = item["target_socs"]
        for case in item["cases"]:
            target = case.get("target_soc") or (
                targets[0] if len(targets) == 1 else None
            )
            if soc is not None and target != soc:
                continue
            rows.append(
                {
                    "mechanism": item["mechanism"],
                    "soc": target,
                    "ratio": case["ratio"],
                    "axes": item["factors"],
                }
            )
    return rows


def _aggregate(rows):
    if not rows:
        return None
    logs = [math.log(row["ratio"]) for row in rows]
    return {
        "n": len(logs),
        "mean_log_ratio": statistics.fmean(logs),
        "success_rate": sum(value < 0 for value in logs) / len(logs),
    }


def query(history, *, mechanism=None, soc=None):
    rows = iter_rows(history)
    exact = _aggregate(
        [row for row in rows if row["mechanism"] == mechanism and row["soc"] == soc]
    )
    mech = _aggregate([row for row in rows if row["mechanism"] == mechanism])
    glob = _aggregate(rows)
    chosen = exact or mech or glob
    if chosen is None:
        return {"n": 0, "geomean_speedup": None, "source": "none"}
    wider = mech or glob
    weight = chosen["n"] / (chosen["n"] + SHRINK_N)
    mean = chosen["mean_log_ratio"]
    if wider is not None and wider is not chosen:
        mean = weight * mean + (1 - weight) * wider["mean_log_ratio"]
    return {
        "n": chosen["n"],
        "geomean_speedup": math.exp(-mean),
        "success_rate": chosen["success_rate"],
        "source": "exact" if exact else "mechanism" if mech else "global",
        "shrink_weight": round(weight, 6),
    }


def rank_nodes(history, nodes, *, soc, weights=None):
    weights = weights or {"prior": 1.0, "novelty": 0.5, "cost": 0.3, "risk": 0.3}
    ranked = []
    for node in nodes:
        q = query(history, mechanism=node.get("mechanism", node["scheme_id"]), soc=soc)
        utility = (
            weights["prior"] * (q.get("geomean_speedup") or 1.0)
            + weights["novelty"] / (q["n"] + 1.0)
            - weights["cost"] * float(node.get("cost", 0))
            - weights["risk"] * float(node.get("risk", 0))
        )
        ranked.append({"scheme_id": node["scheme_id"], "utility": utility, "prior": q})
    return sorted(ranked, key=lambda item: -item["utility"])
