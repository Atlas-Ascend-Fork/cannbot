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
"""Classify performance changes with asymmetric regression-only jitter filtering."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import tempfile


MICRO_CASE_MAX_US = 5.0
MICRO_CASE_ABS_JITTER_US = 0.25
SHORT_CASE_MAX_US = 20.0
SHORT_CASE_ABS_JITTER_US = 0.5
MEDIUM_CASE_MAX_US = 100.0
MEDIUM_CASE_REL_JITTER = 0.03
LONG_CASE_ABS_JITTER_FLOOR_US = 3.0
LONG_CASE_REL_JITTER = 0.01


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    return parser.parse_args()


def load_performance(path: Path) -> tuple[list[str], dict[str, float]]:
    order: list[str] = []
    values: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"case_id", "total_us"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path}: expected columns {sorted(required)}")
        for line_number, row in enumerate(reader, start=2):
            case_id = row["case_id"].strip()
            if not case_id:
                raise ValueError(f"{path}:{line_number}: empty case_id")
            if case_id in values:
                raise ValueError(f"{path}:{line_number}: duplicate case_id {case_id}")
            try:
                total_us = float(row["total_us"])
            except ValueError as error:
                raise ValueError(
                    f"{path}:{line_number}: invalid total_us for {case_id}"
                ) from error
            if not math.isfinite(total_us) or total_us <= 0:
                raise ValueError(
                    f"{path}:{line_number}: total_us must be finite and > 0"
                )
            order.append(case_id)
            values[case_id] = total_us
    if not order:
        raise ValueError(f"{path}: no performance cases")
    return order, values


def classify_case(case_id: str, baseline_us: float, candidate_us: float) -> dict:
    delta_us = candidate_us - baseline_us
    delta_ratio = delta_us / baseline_us
    speedup = baseline_us / candidate_us
    if baseline_us <= MICRO_CASE_MAX_US:
        threshold_mode = "micro_absolute_us"
        threshold_us = MICRO_CASE_ABS_JITTER_US
    elif baseline_us <= SHORT_CASE_MAX_US:
        threshold_mode = "short_absolute_us"
        threshold_us = SHORT_CASE_ABS_JITTER_US
    elif baseline_us <= MEDIUM_CASE_MAX_US:
        threshold_mode = "medium_relative_percent"
        threshold_us = baseline_us * MEDIUM_CASE_REL_JITTER
    else:
        threshold_mode = "long_max_absolute_or_relative"
        threshold_us = max(
            LONG_CASE_ABS_JITTER_FLOOR_US,
            baseline_us * LONG_CASE_REL_JITTER,
        )
    if delta_us < 0:
        classification = "effective_improvement"
    elif delta_us <= threshold_us:
        classification = "jitter_no_effect"
    else:
        classification = "effective_regression"

    return {
        "case_id": case_id,
        "baseline_total_us": baseline_us,
        "candidate_total_us": candidate_us,
        "delta_us": delta_us,
        "delta_percent": delta_ratio * 100.0,
        "speedup": speedup,
        "threshold_mode": threshold_mode,
        "threshold_value": threshold_us,
        "threshold_unit": "us",
        "threshold_percent": threshold_us / baseline_us * 100.0,
        "classification": classification,
        "effective": classification != "jitter_no_effect",
    }


def _jitter_policy() -> dict:
    return {
        "micro_case": {
            "condition": "baseline_total_us <= 5",
            "absolute_jitter_us_inclusive": MICRO_CASE_ABS_JITTER_US,
        },
        "short_case": {
            "condition": "5 < baseline_total_us <= 20",
            "absolute_jitter_us_inclusive": SHORT_CASE_ABS_JITTER_US,
        },
        "medium_case": {
            "condition": "20 < baseline_total_us <= 100",
            "relative_jitter_percent_inclusive": MEDIUM_CASE_REL_JITTER * 100.0,
        },
        "long_case": {
            "condition": "baseline_total_us > 100",
            "absolute_jitter_floor_us": LONG_CASE_ABS_JITTER_FLOOR_US,
            "relative_jitter_percent_inclusive": LONG_CASE_REL_JITTER * 100.0,
            "combination": "max(absolute_jitter_floor_us, relative_jitter)",
        },
    }


def _effective_geomean(effective: list[dict]) -> float | None:
    if not effective:
        return None
    return math.exp(
        sum(math.log(case["speedup"]) for case in effective) / len(effective)
    )


def _case_counts(cases: list[dict], effective: list[dict]) -> dict:
    return {
        "total_case_count": len(cases),
        "jitter_case_count": sum(
            case["classification"] == "jitter_no_effect" for case in cases
        ),
        "effective_case_count": len(effective),
        "effective_improvement_count": sum(
            case["classification"] == "effective_improvement" for case in cases
        ),
        "effective_regression_count": sum(
            case["classification"] == "effective_regression" for case in cases
        ),
    }


def summarize(baseline_path: Path, candidate_path: Path) -> dict:
    baseline_order, baseline = load_performance(baseline_path)
    candidate_order, candidate = load_performance(candidate_path)
    if set(baseline) != set(candidate):
        missing = sorted(set(baseline) - set(candidate))
        extra = sorted(set(candidate) - set(baseline))
        raise ValueError(f"case set mismatch: missing={missing}, extra={extra}")
    if candidate_order != baseline_order:
        raise ValueError("candidate case order differs from baseline case order")
    cases = [
        classify_case(case_id, baseline[case_id], candidate[case_id])
        for case_id in baseline_order
    ]
    effective = [case for case in cases if case["effective"]]
    return {
        "schema_version": 2,
        "policy": _jitter_policy(),
        "baseline_path": str(baseline_path.resolve()),
        "candidate_path": str(candidate_path.resolve()),
        **_case_counts(cases, effective),
        "effective_geomean_speedup": _effective_geomean(effective),
        "cases": cases,
    }


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def render_csv(cases: list[dict]) -> str:
    from io import StringIO

    columns = [
        "case_id",
        "baseline_total_us",
        "candidate_total_us",
        "delta_us",
        "delta_percent",
        "speedup",
        "threshold_mode",
        "threshold_value",
        "threshold_unit",
        "threshold_percent",
        "classification",
        "effective",
    ]
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows({column: case[column] for column in columns} for case in cases)
    return output.getvalue()


def main() -> int:
    args = parse_args()
    summary = summarize(args.baseline, args.candidate)
    atomic_write_text(args.out_csv, render_csv(summary["cases"]))
    atomic_write_text(
        args.out_json,
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
