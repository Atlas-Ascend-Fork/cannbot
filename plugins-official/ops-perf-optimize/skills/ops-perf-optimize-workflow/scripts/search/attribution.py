# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Advisory failure attribution using the existing frozen effect classification.

Retain the original search's distinction between incomplete implementation,
noise and negative interactions. Timing alone cannot refute a mechanism.
"""

from __future__ import annotations

import statistics


def _components(item, candidates, base):
    factors = item["factors"]
    changed = {name for name, value in factors.items() if base.get(name) != value}
    found = []
    for other in candidates:
        values = other["factors"]
        if values.keys() != factors.keys() or other["reference"] != item["reference"]:
            continue
        if other["inconclusive"] or not other["ratio"] < 1:
            continue
        axes = {name for name, value in values.items() if base.get(name) != value}
        if axes < changed and len(axes) == len(changed) - 1:
            if all(values[name] == factors[name] for name in axes):
                found.append(other)
    return found


def build(measurements, frontier, base_factors, history=()):
    nodes = {node["scheme_id"]: node for node in frontier["nodes"]}
    current = {item["scheme_id"] for item in measurements["candidates"]}
    measured = []
    for item in [*history, *measurements["candidates"]]:
        node = nodes.get(item["scheme_id"], {})
        cases = item["cases"]
        measured.append(
            {
                **item,
                "factors": item.get("factors", node.get("factors", {})),
                "expected_gain_range": item.get(
                    "expected_gain_range", node.get("expected_gain_range")
                ),
                "ratio": statistics.geometric_mean(case["ratio"] for case in cases),
                "reference": [(c["case_id"], c["reference_us"]) for c in cases],
                "inconclusive": any(
                    c["classification"] == "inconclusive" for c in cases
                ),
            }
        )
    rows, counts = [], {}
    for item in measured:
        if item["scheme_id"] not in current:
            continue
        changed = sorted(
            name
            for name, value in item["factors"].items()
            if base_factors.get(name) != value
        )
        supported = (
            _components(item, measured, base_factors) if len(changed) >= 2 else []
        )
        expected = item["expected_gain_range"]
        if item.get("mechanism_status") == "refuted":
            reason, action = (
                "mechanism_wrong",
                "review the mechanism evidence and retry conditions",
            )
        elif item["inconclusive"] or all(
            c["classification"] in ("unchanged", "jitter_no_effect")
            for c in item["cases"]
        ):
            reason, action = (
                "noise",
                "resolve uncertainty under the frozen effect policy",
            )
        elif supported and item["ratio"] > 1:
            reason, action = (
                "negative_interaction",
                "split the combination and retest supported components",
            )
        elif item["ratio"] < 1 and (not expected or 1 - item["ratio"] >= expected[0]):
            reason, action = (
                "improved",
                "use the existing selection and promotion gates",
            )
        else:
            reason, action = (
                "implementation_imperfect",
                "inspect implementation cost and mechanism evidence before refining or rejecting",
            )
        counts[reason] = counts.get(reason, 0) + 1
        rows.append(
            {
                "scheme_id": item["scheme_id"],
                "changed_axes": changed,
                "reason": reason,
                "action": action,
                "ratio": item["ratio"],
                "expected_gain_range": expected,
                "effect_summary": item["effect_summary"],
                "supported_components": [
                    {"scheme_id": c["scheme_id"], "effect_summary": c["effect_summary"]}
                    for c in supported
                ],
            }
        )
    return {
        "schema_version": 1,
        "advisory_only": True,
        "base_factors": base_factors,
        "counts": counts,
        "candidates": rows,
    }
