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

"""Adapt the frozen DSL casebook without changing its recipes or test semantics."""

import argparse
import csv
import hashlib
import io
import json
import logging
import re
import sys
from pathlib import Path

import yaml

SHEETS = {"blackbox", "whitebox", "tdd"}
IGNORED = {"__pycache__", ".pytest_cache", "testcase_output", ".git"}


def write_frozen_inputs(work, payload, mapping):
    output = work / "perf-optimize/inputs"
    # Compare the entire snapshot before writing; a retry must never replace frozen input.
    if output.exists():
        existing = {
            path.relative_to(output).as_posix(): path.read_bytes()
            for path in output.rglob("*")
            if path.is_file()
        }
        if existing != payload:
            raise ValueError(
                "stale performance inputs; preserve the run and resolve changed inputs"
            )
        return mapping
    for name, data in payload.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return mapping


def execution_mapping(tests, op, normalized, payload):
    mapping = {
        "schema_version": 1,
        "casebook": {
            "path": str(tests / "testcase.csv"),
            "sha256": sha((tests / "testcase.csv").read_bytes()),
        },
        "operator": op,
        "runner_relative": f"operators/{op}/test/test_{op}.py",
        "module": f"operators.{op}.{op}",
        "cases": [
            {
                "case_id": row["case_id"],
                "sheet": row["sheet"],
                "execution_kind": row["execution_kind"],
                "arguments": [
                    "--sheet",
                    row["sheet"],
                    "--case-id",
                    row["case_id"],
                    "--device",
                    "npu",
                    "--require-accelerator",
                ],
            }
            for row in normalized
        ],
        "assets": {key: sha(value) for key, value in payload.items()},
    }
    return mapping


def read_casebook(tests):
    with (tests / "testcase.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if not {"sheet", "case_id", "status", "expected", "seed", "inputs_json"} <= set(
        fields
    ):
        raise ValueError("casebook missing required DSL columns")
    active = [row for row in rows if row["status"] == "active"]
    if {row["sheet"] for row in active} != SHEETS:
        raise ValueError("active blackbox, whitebox and tdd groups are required")
    ids = [row["case_id"] for row in active]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("case IDs must be nonempty and globally unique")
    extra = [
        key
        for key in ("execution_kind", "expected_error", "host_assertion")
        if key not in fields
    ]
    normalized = []
    for row in active:
        json.loads(row["inputs_json"])
        if row.get("assertions_json"):
            json.loads(row["assertions_json"])
        kind = classify(row)
        item = {**row, "execution_kind": kind}
        item.setdefault("expected_error", "")
        item.setdefault("host_assertion", "")
        if row["expected"].startswith("raises_error:"):
            item["expected_error"] = ""
            item["host_assertion"] = "original_runner:" + row["expected"]
        normalized.append(item)
    device = [row for row in normalized if row["execution_kind"] == "device"]
    if not device:
        raise ValueError("no device cases available for performance optimization")
    return fields, extra, normalized, device


def sha(data):
    return hashlib.sha256(data).hexdigest()


def csv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def classify(row):
    expected = row.get("expected", "")
    kind = row.get("execution_kind", "")
    if expected.startswith("raises_error:"):
        if kind not in ("", "expected_error"):
            raise ValueError("error case cannot be a device performance case")
        # The generation runner matches symbolic codes through its error matcher.
        # The performance protocol's expected_error means a literal substring.
        # Use its non-timed assertion route instead of inventing an error message.
        return "host_only"
    if kind == "host_only":
        if not row.get("host_assertion"):
            raise ValueError("host_only requires an explicit host_assertion")
        return kind
    if kind not in ("", "device"):
        raise ValueError(f"unsupported execution_kind: {kind}")
    if expected not in ("match_golden", "match_golden_nan", "assertions"):
        raise ValueError(f"unsupported expected outcome: {expected}")
    return "device"


def prepare(work, code_dir=None):
    work = work.resolve()
    spec = yaml.safe_load((work / "design/doc/spec.yaml").read_text(encoding="utf-8"))
    op = spec["op"]["name"]
    if not isinstance(op, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", op):
        raise ValueError("spec.op.name must be a Python identifier")
    source = code_dir.resolve() if code_dir is not None else work
    tests = source / "operators" / op / "test"
    for name in (f"test_{op}.py", f"{op}_golden.py", "testcase.csv"):
        if not (tests / name).is_file():
            raise ValueError(f"missing test asset: {name}")
    fields, extra, normalized, device = read_casebook(tests)
    payload = {}
    for path in sorted(tests.rglob("*")):
        relative = path.relative_to(tests)
        if any(part in IGNORED for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"test asset symlink is not frozen: {path}")
        if path.is_file():
            payload["functional/" + relative.as_posix()] = path.read_bytes()
    payload["functional/cases.csv"] = csv_bytes(fields + extra, normalized)
    payload["performance.csv"] = csv_bytes(fields + extra, device)
    mapping = execution_mapping(tests, op, normalized, payload)
    payload["execution-map.json"] = (
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    return write_frozen_inputs(work, payload, mapping)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument(
        "--code-dir", type=Path, help="source root returned by code_versions status"
    )
    args = parser.parse_args()
    try:
        result = prepare(args.work_dir, args.code_dir)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"{error}\n")
    output = logging.Logger("dsl_performance.inventory", level=logging.INFO)
    output.addHandler(logging.StreamHandler(sys.stdout))
    output.info(
        "%s",
        json.dumps({"operator": result["operator"], "cases": len(result["cases"])}),
    )


if __name__ == "__main__":
    main()
