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

"""Evaluate the requested speedup policy without dropping required cases."""
import argparse
import json
import logging
import math
import sys


def _is_positive_finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value > 0


def _case_speedup(row):
    value = row.get("speedup_vs_torch")
    if row.get("status") != "pass" or not _is_positive_finite(value):
        raise ValueError("required case has invalid speedup")
    latencies = [
        row.get(kind, {}).get("avg_latency_ms")
        for kind in ("framework", "implementation")
    ]
    if any(not _is_positive_finite(value) for value in latencies):
        raise ValueError("required case has invalid measured latency")
    # The report's displayed speedup is rounded; it cannot decide exact parity.
    return latencies[0] / latencies[1]


def _required_case_speedups(data):
    rows = data.get("per_shape_results", [])
    total = data.get("total_cases")
    if not isinstance(total, int) or total <= 0 or len(rows) != total:
        raise ValueError("all required cases must have performance rows")
    if data.get("passed_cases") != total or data.get("failed_cases", 0) != 0:
        raise ValueError("performance contains failed required cases")
    values = []
    seen = set()
    for row in rows:
        case_idx = row.get("case_idx")
        if case_idx in seen or case_idx is None:
            raise ValueError("required case identifiers must be unique")
        seen.add(case_idx)
        values.append(_case_speedup(row))
    return total, values


def evaluate(data, target_speedup, target_policy="geometric_mean"):
    if target_policy not in {"geometric_mean", "each_required_case"}:
        raise ValueError("unknown target_policy")
    if not math.isfinite(target_speedup) or target_speedup <= 0:
        raise ValueError("target_speedup must be finite and positive")
    total, values = _required_case_speedups(data)
    geometric = math.exp(sum(math.log(v) for v in values) / len(values))
    minimum = min(values)
    decision = minimum if target_policy == "each_required_case" else geometric
    return {
        "target_policy": target_policy,
        "target_speedup": target_speedup,
        "required_cases": total,
        "geometric_mean_speedup": geometric,
        "minimum_case_speedup": minimum,
        "decision_metric": decision,
        "target_reached": decision >= target_speedup,
        "per_case_target_reached": [v >= target_speedup for v in values],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--perf-result", required=True)
    parser.add_argument("--target-speedup", type=float, required=True)
    parser.add_argument(
        "--target-policy",
        choices=("geometric_mean", "each_required_case"),
        default="geometric_mean",
    )
    args = parser.parse_args()
    try:
        with open(args.perf_result, encoding="utf-8") as stream:
            result = evaluate(json.load(stream), args.target_speedup, args.target_policy)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    # Keep the CLI result as pure JSON on stdout for downstream consumers.
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    logging.info("%s", json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
