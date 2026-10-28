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
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from performance_effect_evidence import policy, receipt, verify_proof

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
    parser.add_argument("--policy", choices=("legacy_jitter_v1", "confidence_effect_v1"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--same-implementation", type=Path, help="identity evidence for a byte-identical no-op")
    args = parser.parse_args()
    if not args.policy and not args.manifest:
        parser.error("explicit --policy or --manifest is required; old API defaults to legacy")
    return args


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
                raise ValueError(f"{path}:{line_number}: invalid total_us for {case_id}") from error
            if not math.isfinite(total_us) or total_us <= 0:
                raise ValueError(f"{path}:{line_number}: total_us must be finite and > 0")
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
    if abs(delta_us) <= threshold_us:
        classification = "jitter_no_effect"
    elif delta_us < 0:
        classification = "effective_improvement"
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
    return math.exp(sum(math.log(case["speedup"]) for case in effective) / len(effective))


def _case_counts(cases: list[dict], effective: list[dict]) -> dict:
    return {
        "total_case_count": len(cases),
        "jitter_case_count": sum(case["classification"] == "jitter_no_effect" for case in cases),
        "effective_case_count": len(effective),
        "effective_improvement_count": sum(case["classification"] == "effective_improvement" for case in cases),
        "effective_regression_count": sum(case["classification"] == "effective_regression" for case in cases),
    }


def _verify_summary_inputs(baseline_path, candidate_path):
    baseline_order, baseline = load_performance(baseline_path)
    candidate_order, candidate = load_performance(candidate_path)
    if set(baseline) != set(candidate):
        missing = sorted(set(baseline) - set(candidate))
        extra = sorted(set(candidate) - set(baseline))
        raise ValueError(f"case set mismatch: missing={missing}, extra={extra}")
    if candidate_order != baseline_order:
        raise ValueError("candidate case order differs from baseline case order")
    return baseline_order, baseline, candidate


def _collect_proofs(evidence_paths, baseline_path, candidate_path, baseline):
    proofs = {}
    for evidence_path in evidence_paths:
        proof = verify_proof(evidence_path, baseline_path, candidate_path)
        identifier = proof["case_id"]
        if identifier in proofs or identifier not in baseline:
            raise ValueError("duplicate or wrong-case paired proof")
        proofs[identifier] = proof
    return proofs


def _apply_noop(same_implementation, baseline_path, candidate_path, proofs, dependencies):
    if not same_implementation:
        return None
    from performance_effect_evidence import verify_noop

    noop = verify_noop(same_implementation, baseline_path, candidate_path)
    if set(proofs) & set(noop["case_ids"]):
        raise ValueError("paired proof and same-implementation cases overlap")
    for item in noop["dependencies"] + [receipt(same_implementation)]:
        dependencies[item["path"]] = item
    return noop


def _apply_case_proof(case, proofs, evidence_paths, screening):
    statistics = proofs[case["case_id"]]["statistics"]
    low, high = statistics.get("paired_ci_us", statistics.get("ci_us"))
    case["classification"] = (
        "effective_improvement" if high < 0 else "effective_regression" if low > 0 else "inconclusive"
    )
    proof_kind = proofs[case["case_id"]].get("kind")
    independent = proof_kind in ("canonical10_independent", "msprof_op10_independent_v1")
    if independent and screening == "jitter_no_effect":
        case["classification"] = "inconclusive"
        case["classification_basis"] = "small_change_requires_paired_confirmation"
    else:
        prefix = proof_kind if independent else "paired"
        case["classification_basis"] = prefix + (
            "_confidence" if case["classification"] != "inconclusive" else "_interval_crosses_zero"
        )
    case["target_soc"] = proofs[case["case_id"]]["target_soc"]
    case["source_identities"] = proofs[case["case_id"]]["source_identities"]
    case["statistical_evidence"] = statistics
    case["proof_path"] = str(Path(evidence_paths[list(proofs).index(case["case_id"])]).resolve())


def _classify_confidence_cases(cases, proofs, evidence_paths, noop):
    for case in cases:
        screening = case["classification"]
        case["screening_signal"] = screening
        case["classification"] = "inconclusive"
        case["classification_basis"] = (
            "needs_confirmation" if screening == "jitter_no_effect" else "screening_only_needs_confirmation"
        )
        if case["case_id"] in proofs:
            _apply_case_proof(case, proofs, evidence_paths, screening)
        elif noop and case["case_id"] in noop["case_ids"]:
            case["target_socs"] = noop["target_socs"]
            case["classification"] = "same_implementation"
            case["classification_basis"] = "byte_identical_source_build_runtime"
        case["effective"] = case["classification"] in ("effective_improvement", "effective_regression")


def _confidence_extension(selected_policy, cases, evidence_paths, same_implementation, dependencies):
    return {
        "schema_version": 3,
        "policy_id": selected_policy["id"],
        "policy_version": selected_policy["version"],
        "classification_basis": "verified_paired_confidence_or_same_implementation",
        "inconclusive_case_count": sum(c["classification"] == "inconclusive" for c in cases),
        "same_implementation_case_count": sum(c["classification"] == "same_implementation" for c in cases),
        "evidence_paths": [str(Path(p).resolve()) for p in evidence_paths],
        "same_implementation_path": str(Path(same_implementation).resolve()) if same_implementation else None,
        "dependencies": sorted(dependencies.values(), key=lambda d: d["path"]),
    }


def summarize(
    baseline_path: Path,
    candidate_path: Path,
    *,
    policy_id="legacy_jitter_v1",
    evidence_paths=None,
    same_implementation=None,
) -> dict:
    selected_policy = policy(policy_id)
    evidence_paths = evidence_paths or []
    if selected_policy["id"] == "legacy_jitter_v1" and (evidence_paths or same_implementation):
        raise ValueError("legacy policy cannot consume confidence proofs")
    baseline_order, baseline, candidate = _verify_summary_inputs(baseline_path, candidate_path)
    cases = [classify_case(case_id, baseline[case_id], candidate[case_id]) for case_id in baseline_order]
    proofs, dependencies = {}, {}
    noop = None
    if selected_policy["id"] == "confidence_effect_v1":
        proofs = _collect_proofs(evidence_paths, baseline_path, candidate_path, baseline)
        for evidence_path in evidence_paths:
            item = receipt(evidence_path)
            dependencies[item["path"]] = item
            for item in proofs[_proof_by_path(evidence_path, proofs, evidence_paths)]["dependencies"]:
                dependencies[item["path"]] = item
        noop = _apply_noop(same_implementation, baseline_path, candidate_path, proofs, dependencies)
        _classify_confidence_cases(cases, proofs, evidence_paths, noop)
    effective = [case for case in cases if case["effective"]]
    result = {
        "schema_version": 2,
        "policy": _jitter_policy(),
        "baseline_path": str(baseline_path.resolve()),
        "candidate_path": str(candidate_path.resolve()),
        **_case_counts(cases, effective),
        "effective_geomean_speedup": _effective_geomean(effective),
        "cases": cases,
    }
    if selected_policy["id"] == "confidence_effect_v1":
        result.update(_confidence_extension(selected_policy, cases, evidence_paths, same_implementation, dependencies))
    return result


def _proof_by_path(evidence_path, proofs, evidence_paths):
    index = evidence_paths.index(evidence_path)
    return list(proofs)[index]


def recompute_summary(summary):
    if summary.get("schema_version") == 2:
        return summarize(Path(summary["baseline_path"]), Path(summary["candidate_path"]))
    if summary.get("schema_version") != 3:
        raise ValueError("unknown performance effect summary schema")
    selected = policy({"id": summary.get("policy_id"), "version": summary.get("policy_version")})
    if selected["id"] != "confidence_effect_v1":
        raise ValueError("summary schema/policy mismatch")
    return summarize(
        Path(summary["baseline_path"]),
        Path(summary["candidate_path"]),
        policy_id=selected,
        evidence_paths=summary.get("evidence_paths", []),
        same_implementation=summary.get("same_implementation_path"),
    )


def summary_dependency_paths(summary):
    return [item["path"] for item in summary.get("dependencies", [])]


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
    if any("classification_basis" in case for case in cases):
        columns += [
            "classification_basis",
            "screening_signal",
            "paired_estimate_us",
            "paired_ci_us",
            "independent_estimate_us",
            "independent_ci_us",
            "method_id",
        ]
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for case in cases:
        row = {column: case.get(column, "") for column in columns}
        if "classification_basis" in case:
            stats = case.get("statistical_evidence", {})
            row.update(
                {
                    "paired_estimate_us": stats.get("paired_estimate_us", ""),
                    "paired_ci_us": json.dumps(stats["paired_ci_us"]) if "paired_ci_us" in stats else "",
                    "independent_estimate_us": stats.get("estimate_us", ""),
                    "independent_ci_us": json.dumps(stats["ci_us"]) if "ci_us" in stats else "",
                    "method_id": stats.get("method", {}).get("id", ""),
                }
            )
        writer.writerow(row)
    return output.getvalue()


def main() -> int:
    args = parse_args()
    frozen = None
    if args.manifest:
        manifest = json.loads(args.manifest.read_text())
        frozen = policy(manifest["configuration"].get("performance_effect_policy"))
    selected = policy(args.policy) if args.policy else frozen
    if frozen and selected != frozen:
        raise ValueError("CLI policy differs from frozen manifest")
    summary = summarize(
        args.baseline,
        args.candidate,
        policy_id=selected,
        evidence_paths=args.evidence,
        same_implementation=args.same_implementation,
    )
    atomic_write_text(args.out_csv, render_csv(summary["cases"]))
    atomic_write_text(
        args.out_json,
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
