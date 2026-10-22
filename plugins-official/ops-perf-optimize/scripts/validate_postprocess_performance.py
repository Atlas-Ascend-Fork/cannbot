#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Version 2.0 (the "License").
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


def functional_case_kinds(collection: dict) -> tuple[set[str], dict[str, str]]:
    """Separate launched cases from frozen cases that must raise before timing."""
    _, rows = read_csv(inventory_csv(Path(collection["path"])))
    timed: set[str] = set()
    expected_errors: dict[str, str] = {}
    for index, row in enumerate(rows):
        identifier = case_id(row, index)
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


def _collection(name: str, manifest: dict) -> dict:
    collection = manifest["collections"].get(f"{name}_full")
    if name == "performance" and not collection:
        collection = manifest["collections"].get("generalization_full")
    if not collection:
        raise ValueError(f"{name} full collection is not ready")
    if identity(Path(collection["path"]))["sha256"] != collection["sha256"]:
        raise ValueError(f"{name} collection identity changed")
    return collection


def _validate_one(name: str, manifest: dict, paths: dict, functional_errors) -> dict:
    collection = _collection(name, manifest)
    expected = case_ids_from_collection(collection)
    expected_errors: dict[str, str] = {}
    if name == "functional":
        expected, expected_errors = functional_case_kinds(collection)
    baseline, candidate = paths[name]
    summary = summarize(baseline, candidate)
    actual = {row["case_id"] for row in summary["cases"]}
    if actual != expected:
        raise ValueError(
            f"{name} full coverage mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    result = {
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
    if name != "functional" or not expected_errors:
        return result
    if functional_errors is None:
        raise ValueError("expected-error rows require before/after functional error evidence")
    result["expected_errors"] = {
        "baseline": validate_expected_errors(functional_errors[0], expected_errors),
        "candidate": validate_expected_errors(functional_errors[1], expected_errors),
    }
    return result


def validate(
    manifest_path: Path,
    target_soc: str,
    paths: dict[str, tuple[Path, Path]],
    functional_errors: tuple[Path, Path] | None = None,
) -> dict:
    manifest = load_manifest(manifest_path)
    if target_soc not in manifest["configuration"]["target_socs"]:
        raise ValueError("target_soc is not in frozen TARGET_SOCS")
    results = {
        name: _validate_one(name, manifest, paths, functional_errors)
        for name in ("functional", "performance")
    }
    regressions = any(item["regressed_case_ids"] for item in results.values())
    return {
        "schema_version": 1,
        "manifest": identity(manifest_path),
        "target_soc": target_soc,
        "decision": "route_required" if regressions else "pass",
        "collections": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target-soc", required=True)
    for kind in ("functional", "performance"):
        parser.add_argument(f"--baseline-{kind}", type=Path, required=True)
        parser.add_argument(f"--candidate-{kind}", type=Path, required=True)
    parser.add_argument("--baseline-functional-errors", type=Path)
    parser.add_argument("--candidate-functional-errors", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.baseline_functional_errors) != bool(args.candidate_functional_errors):
        raise ValueError("both before/after functional error evidence paths are required together")
    functional_errors = (
        (args.baseline_functional_errors.resolve(), args.candidate_functional_errors.resolve())
        if args.baseline_functional_errors else None
    )
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
    )
    atomic_json(args.out.resolve(), result)
    emit(json.dumps({"decision": result["decision"], "gate": str(args.out.resolve())}))
    return 0 if result["decision"] == "pass" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(str(error)) from error
