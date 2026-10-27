# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Perf aggregation for the multirank runner (pure function).

Two-level aggregation: within a case the per-rank values are comparable
(symmetric work — same shape, even shards) so they are averaged (with a
cross-rank std measuring load balance); across cases the ratios are
dimensionless but not comparable, so each case votes once via the median.
The absolute-time medians are evidence fields only — they never feed the
ratio.

Scope note: `aggregate_perf` is the only public surface here — no per-op
perf_report.md writer and no trusted perf receipt (runtime_perf_receipt /
runtime_execution_identity provenance plumbing) is assembled or fabricated;
the aggregate flows into verification.json.performance schema-aligned by
multirank_emit, and the multirank plugin's finalize_perf_capture consumes/merges
it directly.
"""

from __future__ import annotations

import os
import statistics
from typing import Optional


def _mean_std(values) -> tuple:
    """(mean, std) of the numeric entries, rounded; (None, None) when empty."""
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None, None
    return (
        round(statistics.mean(vals), 3),
        round(statistics.stdev(vals), 3) if len(vals) > 1 else 0.0,
    )


def _aggregate_case_stats(by_case: dict) -> dict:
    """Level 1: per-case mean/std across the case's ranks."""
    case_stats: dict = {}
    for name, entries in by_case.items():
        cm, cs = _mean_std([e.get("candidate_us") for e in entries])
        bm, bs = _mean_std([e.get("baseline_us") for e in entries])
        rm, _ = _mean_std([e.get("ratio") for e in entries])
        case_stats[name] = {
            "candidate_us_mean": cm,
            "candidate_us_std": cs,
            "baseline_us_mean": bm,
            "baseline_us_std": bs,
            "ratio": rm,
        }
    return case_stats


def _overall_perf(perfs: list, case_stats: dict, rank_summaries: list) -> dict:
    """Level 2 + evidence fields: median per-case ratio, per-side time medians
    (evidence only), the raw rank rows, and the method stamp."""
    valid_ratios = [
        s["ratio"] for s in case_stats.values() if isinstance(s["ratio"], (int, float))
    ]
    ratio = round(statistics.median(valid_ratios), 3) if valid_ratios else None
    cand = [
        p.get("candidate_us")
        for p in perfs
        if isinstance(p.get("candidate_us"), (int, float))
    ]
    base = [
        p.get("baseline_us")
        for p in perfs
        if isinstance(p.get("baseline_us"), (int, float))
    ]
    cand_med = statistics.median(cand) if cand else None
    base_med = statistics.median(base) if base else None
    return {
        "ran": True,
        "ratio": ratio,
        "median_ratio": ratio,
        "case_stats": case_stats,
        "candidate_us": round(cand_med, 3) if cand_med is not None else None,
        "baseline_us": round(base_med, 3) if base_med is not None else None,
        "rows": [
            {"rank": rs.get("rank"), **(rs.get("perf") or {})}
            for rs in rank_summaries
            if rs.get("perf")
        ],
        "method": (
            "torch_npu.profiler operator_details.csv Device Self Duration "
            "SUM/active (sync="
            + (
                "end-of-window"
                if os.environ.get("MULTIRANK_PERF_SYNC_MODE") == "end"
                else "per-iteration"
            )
            + "; campaign aggregate: median of per-case mean ratios)",
        ),
    }


def aggregate_perf(rank_summaries: list) -> Optional[dict]:
    """Aggregate per-rank perf blocks into an overall perf dict, or None.

    Two-level aggregation:
    1. within a case (across its ranks): MEAN of the per-rank values —
    the ranks do symmetric work (same shape, even shards), so their
    numbers are comparable and the mean is the efficient estimator.
    The per-case STD across ranks is recorded too: it measures the
    load balance (0 = perfectly balanced; large = wait/compute
    skewed onto a subset of ranks).
    2. across cases: MEDIAN of the per-case ratios — ratios are
    dimensionless but cases are not comparable, so each case votes
    once and outlier cases (e.g. a wait-flipped tiny case) are trimmed.
    The per-side time medians are kept as evidence fields only — absolute
    times across cases/ranks are not comparable, so they never feed the
    ratio.
    """
    perfs = [
        rs.get("perf") for rs in rank_summaries if isinstance(rs.get("perf"), dict)
    ]
    if not perfs:
        return None
    by_case: dict = {}
    for p in perfs:
        for c in p.get("cases") or []:
            by_case.setdefault(c.get("case_id"), []).append(c)
    if not by_case:
        return None
    case_stats = _aggregate_case_stats(by_case)
    return _overall_perf(perfs, case_stats, rank_summaries)
