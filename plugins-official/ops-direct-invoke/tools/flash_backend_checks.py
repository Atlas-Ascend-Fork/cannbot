#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------
"""Fast, read-only checks for retained Flash cases and search budget."""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

import yaml

LOG = logging.getLogger(__name__)

SHEETS = {"blackbox", "whitebox", "performance"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_cell(row, field, expected):
    value = json.loads(row.get(field) or ("[]" if expected is list else "{}"))
    require(isinstance(value, expected), f"{row['case_id']}: {field} must be a {expected.__name__}")
    return value


def check_output_fields(case_id, assertion):
    for current in _iter_assertions(assertion):
        kind = current.get("kind")
        if kind == "output_shape":
            shape = current.get("shape")
            require(isinstance(shape, list) and all(type(dim) is int and dim >= 0 for dim in shape),
                    f"{case_id}: output_shape requires a nonnegative integer shape list")
        elif kind == "output_dtype":
            dtype = current.get("dtype")
            require(isinstance(dtype, str) and bool(dtype.strip()),
                    f"{case_id}: output_dtype requires dtype")


def _iter_assertions(assertion):
    if not isinstance(assertion, dict):
        return
    yield assertion
    if assertion.get("kind") != "execution":
        return
    for call in assertion.get("calls", []):
        if isinstance(call, dict):
            for nested in call.get("assertions", []):
                yield from _iter_assertions(nested)


def check_cases(path, selected):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require({"sheet", "case_id", "status"} <= set(reader.fieldnames or ()),
                "casebook is missing basic columns")
        rows = list(reader)
    checked = 0
    for row in rows:
        if row.get("status") != "active" or row.get("sheet") not in selected:
            continue
        case_id = row.get("case_id") or "unnamed case"
        for assertion in json_cell(row, "assertions_json", list):
            check_output_fields(case_id, assertion)
        checked += 1
    require(checked > 0, f"no active cases in {sorted(selected)}")
    return {"status": "pass", "checked_cases": checked, "sheets": sorted(selected)}


def load_yaml(path):
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path} must contain a mapping")
    return value


def check_budget(contract_path, next_candidates, next_rounds):
    budget = load_yaml(contract_path).get("budget")
    require(isinstance(budget, dict), "contract.budget is required")
    limits = {}
    for key in ("max_candidates", "max_rounds"):
        value = budget.get(key)
        require(type(value) is int and value > 0, f"budget.{key} must be positive")
        limits[key] = value
    opt_dir = contract_path.resolve().parent.parent / "opt"
    candidates_path = opt_dir / "candidates.yaml"
    iteration_path = opt_dir / "iteration.yaml"
    require(candidates_path.is_file() and iteration_path.is_file(), "both opt budget ledgers are required")
    candidate_data = load_yaml(candidates_path)
    iteration_data = load_yaml(iteration_path)
    require("candidates" in candidate_data and "rounds" in iteration_data,
            "existing budget ledgers need candidates and rounds lists")
    candidates = candidate_data["candidates"]
    rounds = iteration_data["rounds"]
    require(isinstance(candidates, list) and isinstance(rounds, list), "candidate and round entries must be lists")
    candidate_ids = [c.get("id") for c in candidates if isinstance(c, dict)]
    require(len(candidate_ids) == len(candidates) and all(candidate_ids)
            and len(set(candidate_ids)) == len(candidate_ids), "candidate IDs must be unique and nonempty")
    require(all(isinstance(r, dict) for r in rounds), "round entries must be mappings")
    started = [r.get("id") for r in rounds
               if r.get("status") not in ("planned", "not_started", "closed_without_candidate")]
    require(len(set(started)) == len(started) and all(started), "started round IDs must be unique and nonempty")
    require(next_candidates >= 0 and next_rounds >= 0, "requested budget must be nonnegative")
    max_candidates = limits.get("max_candidates")
    max_rounds = limits.get("max_rounds")
    require(len(candidates) + next_candidates <= max_candidates, "candidate budget exhausted")
    require(len(started) + next_rounds <= max_rounds, "round budget exhausted")
    return {
        "status": "pass", "registered_candidates": len(candidates),
        "started_rounds": len(started),
        "remaining_candidates": max_candidates - len(candidates) - next_candidates,
        "remaining_rounds": max_rounds - len(started) - next_rounds,
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    cases = sub.add_parser("cases")
    cases.add_argument("--casebook", required=True, type=Path)
    cases.add_argument("--sheet", choices=sorted(SHEETS), action="append")
    budget = sub.add_parser("budget")
    budget.add_argument("--contract", required=True, type=Path)
    budget.add_argument("--next-candidates", type=int, default=0)
    budget.add_argument("--next-rounds", type=int, default=0)
    args = parser.parse_args()
    try:
        if args.action == "cases":
            output = check_cases(args.casebook, set(args.sheet or SHEETS))
        else:
            output = check_budget(args.contract, args.next_candidates, args.next_rounds)
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        LOG.error(json.dumps({"status": "fail", "error": str(error)}))
        return 1
    LOG.info(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
