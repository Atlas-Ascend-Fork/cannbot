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

"""Validate and freeze per-case/SoC reference evidence and latency targets."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from prepare_case_sets import (
    atomic_json,
    case_ids_from_collection,
    identity,
    load_manifest,
    validate_reference,
)
from summarize_performance_effects import atomic_write_text


def _source_identities(raw_sources: list) -> list[dict]:
    sources = []
    for raw in raw_sources:
        path = Path(raw)
        if not path.is_absolute():
            raise ValueError("source_artifacts must contain absolute paths")
        sources.append(identity(path))
    return sources


def _evidence_record(row: dict, reference: dict) -> tuple[tuple[str, str], dict]:
    key = (row["case_id"], row["target_soc"])
    if row.get("kind") != reference["kind"]:
        raise ValueError(f"reference kind mismatch: {key}")
    value = row.get("reference_us")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"invalid reference_us: {key}")
    if value <= 0:
        raise ValueError(f"invalid reference_us: {key}")
    if not row.get("method") or not row.get("source_artifacts"):
        raise ValueError(f"missing method or source evidence: {key}")
    target = value / reference["target_ratio"]
    if not math.isfinite(target) or target <= 0:
        raise ValueError(f"invalid calculated target_us: {key}")
    return key, {
        **row,
        "target_ratio": reference["target_ratio"],
        "target_us": target,
        "source_artifacts": _source_identities(row["source_artifacts"]),
    }


def build(manifest_path: Path, evidence_path: Path) -> dict:
    manifest = load_manifest(manifest_path)
    config = manifest["configuration"]
    reference = validate_reference(config["performance_reference"])
    collection = manifest["collections"].get("performance_full") or manifest[
        "collections"
    ].get("generalization_full")
    if not collection:
        raise ValueError("performance full collection is not ready")
    if identity(Path(collection["path"]))["sha256"] != collection["sha256"]:
        raise ValueError("performance collection identity changed")
    expected = {
        (case, soc)
        for case in case_ids_from_collection(collection)
        for soc in config["target_socs"]
    }
    evidence = json.loads(evidence_path.read_text())
    if not isinstance(evidence.get("cases"), list):
        raise ValueError("evidence requires cases list")
    records, seen = [], set()
    for row in evidence["cases"]:
        key, record = _evidence_record(row, reference)
        if key in seen or key not in expected:
            raise ValueError(f"duplicate or unexpected case/SoC: {key}")
        seen.add(key)
        records.append(record)
    if seen != expected:
        raise ValueError(f"missing target evidence: {sorted(expected - seen)}")
    if not expected:
        raise ValueError("empty performance collection")
    return {
        "schema_version": 1,
        "reference": reference,
        "request": manifest["request"],
        "performance_collection": collection,
        "evidence": identity(evidence_path),
        "target_socs": config["target_socs"],
        "cases": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.manifest.resolve(), args.evidence.resolve())
    atomic_json(args.out.resolve(), result)
    lines = [
        "# 性能目标",
        "",
        f"对标来源：{result['reference']['kind']}；target_us = reference_us / target_ratio。",
        "",
        "| case_id | 目标 SoC | 对标耗时 us | 目标比例 | 目标耗时 us | 方法 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in result["cases"]:
        cells = [
            row["case_id"],
            row["target_soc"],
            row["reference_us"],
            row["target_ratio"],
            row["target_us"],
            row["method"],
        ]
        lines.append(
            "| "
            + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in cells)
            + " |"
        )
    lines += ["", f"完整来源与 SHA：{args.out.resolve()}", ""]
    atomic_write_text(args.out_md.resolve(), "\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(str(error)) from error
