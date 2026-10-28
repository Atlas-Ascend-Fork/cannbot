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

"""Check both frozen full inventories for per-case regression after integration.

This numerical gate complements source isolation and runtime route verification;
it does not prove chip dispatch semantics or measurement provenance by itself.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from cli_output import emit

from prepare_case_sets import (
    atomic_json,
    case_id,
    case_ids_from_collection,
    identity,
    inventory_csv,
    load_manifest,
    read_csv,
)
from summarize_performance_effects import summarize
from performance_effect_evidence import policy


def functional_case_kinds(collection: dict) -> tuple[set[str], dict[str, str]]:
    """Separate launched cases from frozen cases that must raise before timing."""
    _, rows = read_csv(inventory_csv(Path(collection["path"])))
    timed: set[str] = set()
    expected_errors: dict[str, str] = {}
    for index, row in enumerate(rows):
        identifier = case_id(row, index)
        if row.get("execution_kind") == "host_only":
            continue
        enabled = row.get("is_enabled", "").lower()
        expected = row.get("expected_error", "")
        if expected and enabled in ("", "false", "0", "no"):
            expected_errors[identifier] = expected
        elif not expected and enabled in ("", "true", "1", "yes"):
            timed.add(identifier)
        elif expected and enabled in ("true", "1", "yes"):
            raise ValueError(f"enabled functional case has expected_error: {identifier}")
        else:
            raise ValueError(f"disabled functional case lacks expected_error: {identifier}")
    return timed, expected_errors


def host_case_assertions(collection: dict) -> dict[str, str]:
    _, rows = read_csv(inventory_csv(Path(collection["path"])))
    results = {}
    for index, row in enumerate(rows):
        if row.get("execution_kind") != "host_only":
            continue
        assertion = row.get("host_assertion") or row.get("pytest_nodeid")
        if not assertion:
            raise ValueError("host_only functional case requires its frozen assertion/nodeid")
        results[case_id(row, index)] = assertion
    return results


def _host_check_failed(row: dict, identifier: object, expected: dict[str, str], seen: set) -> bool:
    if identifier not in expected or identifier in seen:
        return True
    return row.get("status") != "PASS" or row.get("assertion") != expected[identifier]


def validate_host_checks(path: Path, expected: dict[str, str]) -> dict:
    from validate_execution_identity import file_identity
    evidence = json.loads(path.read_text())
    rows = evidence.get("results")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError("host-only functional coverage mismatch")
    seen, dependencies = set(), []
    for row in rows:
        identifier = row.get("case_id")
        if _host_check_failed(row, identifier, expected, seen):
            raise ValueError("host-only assertion/coverage did not pass")
        seen.add(identifier)
        raw = row.get("raw_evidence", {})
        if not raw.get("path") or file_identity(Path(raw["path"])) != raw:
            raise ValueError("host-only raw evidence changed")
        dependencies.append(raw)
    return {"evidence": identity(path), "case_ids": sorted(seen), "raw_evidence": dependencies}


def validate_expected_errors(path: Path, expected: dict[str, str]) -> dict:
    evidence = json.loads(path.read_text(encoding="utf-8"))
    rows = evidence.get("results")
    if not isinstance(rows, list):
        raise ValueError(f"expected-error evidence requires results list: {path}")
    observed: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str):
            raise ValueError(f"malformed expected-error result: {path}")
        identifier = row["case_id"]
        if identifier in observed:
            raise ValueError(f"duplicate expected-error result: {identifier}")
        observed[identifier] = row
    if set(observed) != set(expected):
        raise ValueError(
            f"expected-error coverage mismatch: missing={sorted(set(expected) - set(observed))}, "
            f"extra={sorted(set(observed) - set(expected))}"
        )
    for identifier, frozen_substring in expected.items():
        row = observed[identifier]
        if row.get("status") != "PASS":
            raise ValueError(f"expected-error case did not pass: {identifier}")
        if row.get("expected_substring") != frozen_substring:
            raise ValueError(f"expected-error substring changed: {identifier}")
        if frozen_substring not in str(row.get("error_excerpt", "")):
            raise ValueError(f"expected-error message mismatch: {identifier}")
    return {"evidence": identity(path), "case_ids": sorted(expected)}


def validate_baseline_failure_side(path: Path, side: str, frozen_cases: set) -> dict:
    """One side of semantic evidence for functional cases the ORIGINAL implementation cannot execute.

    Frozen-inventory device cases with a proven deterministic baseline failure (e.g. an
    aicore trap reproduced on the original identity) have no honest before timing; the
    timing comparison cannot express them. This channel requires before/after semantic
    results instead: the before side must be classified non-PASS failures with raw
    evidence, the after side must PASS. It never waives precision gates and never
    fabricates timings.
    """
    from validate_execution_identity import file_identity
    evidence = json.loads(path.read_text(encoding="utf-8"))
    rows = evidence.get("results")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"baseline-failure evidence requires non-empty results: {path}")
    observed: dict[str, dict] = {}
    raw_dependencies: list[dict] = []
    for row in rows:
        identifier = row.get("case_id")
        if not isinstance(identifier, str) or identifier in observed:
            raise ValueError(f"malformed or duplicate baseline-failure case: {path}")
        raw = row.get("raw_evidence", [])
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"baseline-failure case {identifier} ({side}) needs raw_evidence")
        for item in raw:
            if file_identity(Path(item["path"])) != item:
                raise ValueError(f"baseline-failure raw evidence changed: {identifier} ({side})")
        raw_dependencies.extend(raw)
        observed[identifier] = row
    unknown = set(observed) - frozen_cases
    if unknown:
        raise ValueError(f"baseline-failure cases absent from frozen functional inventory: {sorted(unknown)}")
    if side == "baseline":
        for identifier, row in observed.items():
            if row.get("status") == "PASS" or not row.get("failure_kind"):
                raise ValueError(f"baseline-failure before row must be a classified failure: {identifier}")
    else:
        for identifier, row in observed.items():
            if row.get("status") != "PASS":
                raise ValueError(f"baseline-failure after row must PASS: {identifier}")
    return {"evidence": identity(path), "case_ids": sorted(observed), "raw_evidence": raw_dependencies}


def _frozen_collection(manifest: dict, name: str) -> dict:
    collection = manifest["collections"].get(f"{name}_full")
    if name == "performance" and not collection:
        collection = manifest["collections"].get("generalization_full")
    if not collection:
        raise ValueError(f"{name} full collection is not ready")
    if identity(Path(collection["path"]))["sha256"] != collection["sha256"]:
        raise ValueError(f"{name} collection identity changed")
    return collection


def _untimed_functional_summary(baseline: Path, candidate: Path) -> dict:
    for path in (baseline, candidate):
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not {"case_id", "total_us"}.issubset(reader.fieldnames) or list(reader):
                raise ValueError("untimed functional inventory requires header-only performance files")
    return {"cases": [], "total_case_count": 0, "effective_case_count": 0,
            "effective_geomean_speedup": None, "timing_not_applicable": True}


def _mismatched_target_soc(row: dict, target_soc: str) -> bool:
    if row.get("target_soc", target_soc) != target_soc:
        return True
    return "target_socs" in row and target_soc not in row["target_socs"]


def _paired_summary(
    name: str,
    baseline: Path,
    candidate: Path,
    target_soc: str,
    selected_policy: dict,
    effect_evidence: dict[str, list[Path]],
    same_implementation: dict[str, Path],
    expected: set[str],
) -> dict:
    if name == "functional" and not expected:
        return _untimed_functional_summary(baseline, candidate)
    summary = summarize(
        baseline,
        candidate,
        policy_id=selected_policy,
        evidence_paths=effect_evidence.get(name, []),
        same_implementation=same_implementation.get(name),
    )
    if any(_mismatched_target_soc(row, target_soc) for row in summary["cases"]):
        raise ValueError("paired proof target SoC differs from postprocess gate")
    return summary


def _validate_functional_evidence(
    collection: dict,
    expected_errors: dict[str, str],
    results_entry: dict,
    functional_errors: tuple[Path, Path] | None,
    functional_host_checks: tuple[Path, Path] | None,
) -> None:
    if expected_errors:
        if functional_errors is None:
            raise ValueError("expected-error rows require before/after functional error evidence")
        results_entry["expected_errors"] = {
            "baseline": validate_expected_errors(functional_errors[0], expected_errors),
            "candidate": validate_expected_errors(functional_errors[1], expected_errors),
        }
    host_cases = host_case_assertions(collection)
    if host_cases:
        if functional_host_checks is None:
            raise ValueError("host-only rows require before/after functional assertion evidence")
        results_entry["host_checks"] = {
            "baseline": validate_host_checks(functional_host_checks[0], host_cases),
            "candidate": validate_host_checks(functional_host_checks[1], host_cases),
        }


def _validate_collection(
    name: str,
    manifest: dict,
    target_soc: str,
    paths: dict[str, tuple[Path, Path]],
    selected_policy: dict,
    effect_evidence: dict[str, list[Path]],
    same_implementation: dict[str, Path],
    functional_errors: tuple[Path, Path] | None,
    functional_host_checks: tuple[Path, Path] | None,
    functional_baseline_failures: tuple[Path, Path] | None = None,
) -> dict:
    collection = _frozen_collection(manifest, name)
    expected = case_ids_from_collection(collection)
    expected_errors: dict[str, str] = {}
    baseline_failures: dict = {}
    if name == "functional":
        frozen_cases = set(expected)
        expected, expected_errors = functional_case_kinds(collection)
        if functional_baseline_failures is not None:
            failed = validate_baseline_failure_side(
                functional_baseline_failures[0], "baseline", frozen_cases
            )
            fixed = validate_baseline_failure_side(
                functional_baseline_failures[1], "candidate", frozen_cases
            )
            if set(failed["case_ids"]) != set(fixed["case_ids"]):
                raise ValueError("baseline-failure before/after case sets differ")
            overlap = set(failed["case_ids"]) & set(expected_errors)
            if overlap:
                raise ValueError(f"baseline-failure cases overlap expected-error rows: {sorted(overlap)}")
            expected = expected - set(failed["case_ids"])
            baseline_failures = {"baseline": failed, "candidate": fixed}
    baseline, candidate = paths[name]
    summary = _paired_summary(
        name, baseline, candidate, target_soc, selected_policy,
        effect_evidence, same_implementation, expected,
    )
    actual = {row["case_id"] for row in summary["cases"]}
    if actual != expected:
        raise ValueError(
            f"{name} full coverage mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    results_entry = {
        "baseline": identity(baseline),
        "candidate": identity(candidate),
        "collection": collection,
        "summary": summary,
        "regressed_case_ids": [
            row["case_id"]
            for row in summary["cases"]
            if row["classification"] == "effective_regression"
        ],
    }
    if name == "functional":
        _validate_functional_evidence(
            collection, expected_errors, results_entry, functional_errors, functional_host_checks
        )
        if baseline_failures:
            results_entry["baseline_failures"] = baseline_failures
    return results_entry


def _apply_confidence_policy(
    result: dict,
    selected_policy: dict,
    regressions: bool,
    effect_evidence: dict[str, list[Path]],
    same_implementation: dict[str, Path],
) -> None:
    pending = any(
        item["summary"].get("inconclusive_case_count", 0) for item in result["collections"].values()
    )
    result.update({
        "schema_version": 2,
        "policy_id": selected_policy["id"],
        "policy_version": selected_policy["version"],
        "effect_evidence": {k: [str(Path(p).resolve()) for p in v] for k, v in effect_evidence.items()},
        "same_implementation": {k: str(Path(p).resolve()) for k, p in same_implementation.items()},
        "decision": "route_required" if regressions else "confirmation_required" if pending else "pass",
    })


def validate(
    manifest_path: Path,
    target_soc: str,
    paths: dict[str, tuple[Path, Path]],
    functional_errors: tuple[Path, Path] | None = None,
    functional_host_checks: tuple[Path, Path] | None = None,
    functional_baseline_failures: tuple[Path, Path] | None = None,
    effect_evidence: dict[str, list[Path]] | None = None,
    same_implementation: dict[str, Path] | None = None,
) -> dict:
    manifest = load_manifest(manifest_path)
    if target_soc not in manifest["configuration"]["target_socs"]:
        raise ValueError("target_soc is not in frozen TARGET_SOCS")
    selected_policy = policy(manifest["configuration"].get("performance_effect_policy"))
    effect_evidence = effect_evidence or {}
    same_implementation = same_implementation or {}
    results = {
        name: _validate_collection(
            name, manifest, target_soc, paths, selected_policy,
            effect_evidence, same_implementation, functional_errors, functional_host_checks,
            functional_baseline_failures,
        )
        for name in ("functional", "performance")
    }
    regressions = any(item["regressed_case_ids"] for item in results.values())
    result = {
        "schema_version": 1,
        "manifest": identity(manifest_path),
        "target_soc": target_soc,
        "decision": "route_required" if regressions else "pass",
        "collections": results,
    }
    if selected_policy["id"] == "confidence_effect_v1":
        _apply_confidence_policy(result, selected_policy, regressions, effect_evidence, same_implementation)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target-soc", required=True)
    for kind in ("functional", "performance"):
        parser.add_argument(f"--baseline-{kind}", type=Path, required=True)
        parser.add_argument(f"--candidate-{kind}", type=Path, required=True)
        parser.add_argument(f"--{kind}-effect-evidence", type=Path, action="append", default=[])
        parser.add_argument(f"--{kind}-same-implementation", type=Path)
    for prefix in ("errors", "host-checks", "baseline-failures"):
        parser.add_argument(f"--baseline-functional-{prefix}", type=Path)
        parser.add_argument(f"--candidate-functional-{prefix}", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _paired_evidence(args: argparse.Namespace, prefix: str, description: str) -> tuple[Path, Path] | None:
    baseline = getattr(args, f"baseline_functional_{prefix}")
    candidate = getattr(args, f"candidate_functional_{prefix}")
    if bool(baseline) != bool(candidate):
        raise ValueError(f"both before/after {description} evidence paths are required together")
    return (baseline.resolve(), candidate.resolve()) if baseline else None


def main() -> int:
    args = _parse_args()
    functional_errors = _paired_evidence(args, "errors", "functional error")
    functional_host_checks = _paired_evidence(args, "host_checks", "host-only assertion")
    functional_baseline_failures = _paired_evidence(args, "baseline_failures", "baseline-failure")
    effect_evidence = {kind: getattr(args, f"{kind}_effect_evidence") for kind in ("functional", "performance")}
    same_implementation = {
        kind: getattr(args, f"{kind}_same_implementation")
        for kind in ("functional", "performance")
        if getattr(args, f"{kind}_same_implementation")
    }
    result = validate(
        args.manifest.resolve(),
        args.target_soc,
        {
            kind: (
                getattr(args, f"baseline_{kind}").resolve(),
                getattr(args, f"candidate_{kind}").resolve(),
            )
            for kind in ("functional", "performance")
        },
        functional_errors=functional_errors,
        functional_host_checks=functional_host_checks,
        functional_baseline_failures=functional_baseline_failures,
        effect_evidence=effect_evidence,
        same_implementation=same_implementation,
    )
    atomic_json(args.out.resolve(), result)
    emit(json.dumps({"decision": result["decision"], "gate": str(args.out.resolve())}))
    return 0 if result["decision"] == "pass" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(str(error)) from error
