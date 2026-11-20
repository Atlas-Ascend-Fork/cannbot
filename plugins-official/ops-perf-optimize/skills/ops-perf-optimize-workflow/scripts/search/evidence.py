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

"""Associate frontier candidates with existing, reproducible effect summaries.

This adapter never collects samples or introduces a measurement policy. Input
receipts bind the frozen manifest, case set and existing effect summaries.
"""

from pathlib import Path

from performance_effect_evidence import check_receipt, policy, receipt
from summarize_performance_effects import recompute_summary, requires_routing
from . import policy as search


def _read(ref):
    return search.load(check_receipt(ref)["path"])


def build(index_path, frontier):
    index = search.load(index_path)
    search.require(index.get("schema_version") == 1, "invalid evidence index schema")
    manifest = _read(index["manifest"])
    frozen = policy(manifest["configuration"].get("performance_effect_policy"))
    cases_ref = check_receipt(index["cases"])
    cases = search.case_ids(cases_ref["path"])
    nodes = {node["scheme_id"] for node in frontier["nodes"]}
    records, seen = [], set()
    for item in index["candidates"]:
        scheme = item["scheme_id"]
        search.require(
            scheme in nodes and scheme not in seen, "unknown/duplicate scheme_id"
        )
        seen.add(scheme)
        summary = _read(item["effect_summary"])
        actual = policy(summary.get("policy_id"))
        search.require(actual == frozen, "effect policy differs from frozen manifest")
        search.require(
            recompute_summary(summary) == summary, "effect summary is stale or altered"
        )
        search.require(
            [row["case_id"] for row in summary["cases"]] == cases,
            "effect case coverage/order differs",
        )
        # Preserve per-case proof statistics with their original units/method;
        # case medians are not independent repeats or paired ratio samples.
        rows = [
            {
                **row,
                "candidate_us": row["candidate_total_us"],
                "reference_us": row["baseline_total_us"],
                "ratio": row["candidate_total_us"] / row["baseline_total_us"],
            }
            for row in summary["cases"]
        ]
        records.append(
            {
                "scheme_id": scheme,
                "status": "measured",
                "effect_summary": item["effect_summary"],
                "performance_sources": [
                    receipt(summary[key]) for key in ("baseline_path", "candidate_path")
                ],
                "policy_id": frozen["id"],
                "cases": rows,
                "requires_routing": requires_routing(summary),
                "inconclusive_case_count": summary.get("inconclusive_case_count", 0),
                "effective_geomean_speedup": summary["effective_geomean_speedup"],
            }
        )
    search.require(records, "evidence index has no completed candidates")
    return {
        "schema_version": 1,
        "evidence_role": "screening",
        "evidence_index": receipt(index_path),
        "manifest": index["manifest"],
        "case_source": cases_ref,
        "cases": cases,
        "policy_id": frozen["id"],
        "candidates": records,
    }


def read(path, frontier):
    """Revalidate transitive sources before using a saved search observation."""
    payload = search.load(path)
    ref = check_receipt(payload["evidence_index"])
    search.require(
        build(Path(ref["path"]), frontier) == payload,
        "search evidence is stale or altered",
    )
    return payload
