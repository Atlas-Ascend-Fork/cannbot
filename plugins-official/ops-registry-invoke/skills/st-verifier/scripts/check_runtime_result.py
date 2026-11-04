#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""Check native TTK OOB/repetition evidence without changing precision results."""

import argparse
import csv
import json
import logging
import re
import sys
from pathlib import Path


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "testcase_name" not in reader.fieldnames:
            raise ValueError(f"{path}: missing testcase_name column")
        rows = {}
        for row in reader:
            name = row.get("testcase_name", "")
            if not name or name in rows:
                raise ValueError(f"{path}: empty or duplicate testcase_name: {name!r}")
            rows[name] = row
        if not rows:
            raise ValueError(f"{path}: no case rows")
        return rows


def token(value):
    return (value or "").strip().upper()


def oom_checks(row):
    checks = {}
    for mode in ("cst", "dyn"):
        raw = row.get(f"{mode}_oob_result")
        values = [token(value) for value in (raw or "").split(",")]
        precision = token(row.get(f"{mode}_precision"))
        if "FAIL" in values:
            status = "FAIL"
        elif all(value in {"OK", "PASS"} for value in values) and precision in {
            "PASS",
            "FAIL",
        }:
            status = "PASS"
        else:
            status = "GAP"
        checks[mode] = {
            "status": status,
            "oob": raw,
            "precision": row.get(f"{mode}_precision"),
        }
    # memory_oob_status can report PASS even when the mode fields are UNKNOWN.
    # Conversely, preserve an explicit aggregate failure for investigation.
    if token(row.get("memory_oob_status")) == "FAIL":
        checks["aggregate"] = {"status": "FAIL", "oob": row["memory_oob_status"]}
    return checks


def determinism_checks(row, name, log):
    pattern = rf"\[{re.escape(name)}\] MD5 (consistent|mismatch) across (\d+) runs:"
    observations = re.findall(pattern, log)
    raw = token(row.get("deterministic_status"))
    if raw == "FAIL" or any(outcome == "mismatch" for outcome, _ in observations):
        status = "FAIL"
    elif (
        raw == "PASS"
        and observations
        and all(
            outcome == "consistent" and int(count) == 10
            for outcome, count in observations
        )
    ):
        status = "PASS"
    else:
        status = "GAP"
    return {
        "determinism": {
            "status": status,
            "deterministic_status": row.get("deterministic_status"),
            "observed_runs": [int(count) for _, count in observations],
        }
    }


def verdict(checks):
    statuses = [check["status"] for check in checks.values()]
    return "FAIL" if "FAIL" in statuses else "GAP" if "GAP" in statuses else "PASS"


def read_attempts(attempts, source):
    current = {}
    for result_path, log_path in attempts:
        rows = read_rows(result_path)
        unknown = rows.keys() - source.keys()
        if unknown:
            raise ValueError(f"{result_path}: unknown result cases: {sorted(unknown)}")
        log = Path(log_path).read_text(encoding="utf-8", errors="replace")
        if not log.strip():
            raise ValueError(f"{log_path}: empty TTK log")
        # Attempts are explicitly ordered oldest to newest. A later failure must
        # replace an earlier PASS; the original CSVs and logs stay untouched.
        for name, row in rows.items():
            current[name] = (row, log, result_path, log_path)
    return current


def check(args):
    source = read_rows(args.cases)
    expected = args.case_names if args.case_names is not None else list(source)
    if (
        not expected
        or len(expected) != len(set(expected))
        or set(expected) - source.keys()
    ):
        raise ValueError(
            "case selection must contain unique, existing source case names"
        )
    current = read_attempts(args.attempt, source)
    cases = []
    for name in expected:
        if name not in current:
            cases.append(
                {"testcase_name": name, "status": "GAP", "reason": "no result row"}
            )
            continue
        row, log, result_path, log_path = current[name]
        checks = (
            oom_checks(row)
            if args.kind == "oom"
            else determinism_checks(row, name, log)
        )
        cases.append(
            {
                "testcase_name": name,
                "status": verdict(checks),
                "checks": checks,
                "result_csv": result_path,
                "log": log_path,
            }
        )
    counts = {
        status: sum(case["status"] == status for case in cases)
        for status in ("PASS", "FAIL", "GAP")
    }
    return {
        "kind": args.kind,
        "status": verdict({str(i): case for i, case in enumerate(cases)}),
        "expected": len(expected),
        "counts": counts,
        "cases": cases,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["oom", "determinism"])
    parser.add_argument("--cases", required=True, help="Unchanged source case CSV")
    parser.add_argument(
        "--case-names", nargs="+", help="Exact positive-case selection for this batch"
    )
    parser.add_argument(
        "--attempt",
        nargs=2,
        action="append",
        required=True,
        metavar=("RESULT_CSV", "TTK_LOG"),
        help="Repeat oldest to newest for repaired/split batches",
    )
    args = parser.parse_args(argv)
    try:
        report = check(args)
    except (OSError, ValueError, csv.Error) as error:
        report = {"kind": args.kind, "status": "GAP", "diagnostics": [str(error)]}
    logger = logging.Logger(__name__, level=logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.info("%s", json.dumps(report, ensure_ascii=False, indent=2))
    handler.close()
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
