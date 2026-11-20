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

"""Inactive historical npu-compute report reader.

Collection and metric interpretation belong to tool-npu-compute. This module
does not infer a kernel from a directory name or turn a replay median into an
application launch duration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from report_common import positive as positive, roofline as roofline


def receipt(path):
    path = Path(path).resolve(strict=True)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "sha256": digest.hexdigest()}


def load_summary(path):
    records = [
        json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()
    ]
    if not all(isinstance(row, dict) for row in records):
        raise ValueError("summary records must be JSON objects")
    categories = [row.get("category") for row in records]
    if (
        not records
        or categories[-1] != "OpInfoSummary"
        or len(set(categories)) != len(categories)
    ):
        raise ValueError("summary requires unique categories and a final OpInfoSummary")
    return records


def select_summary(root, op_name, summary=None):
    root = Path(root).resolve(strict=True)
    if summary is not None:
        chosen = Path(summary).resolve(strict=True)
        if not chosen.is_relative_to(root):
            raise ValueError("selected summary must belong to this collection")
        candidates = [chosen]
    else:
        candidates = sorted(root.rglob("summary.jsonl"))
    matches = []
    for path in candidates:
        records = load_summary(path)
        if records[-1].get("Op Name") == op_name:
            matches.append((path, records))
    if len(matches) != 1:
        raise ValueError(
            f"expected one exact Op Name match, found {len(matches)}; select --summary explicitly"
        )
    return matches[0]


def timing(info):
    duration = info.get("Task Duration(us)")
    current, rated = info.get("Current Freq"), info.get("Rated Freq")
    return {
        "duration_us": duration if positive(duration) else None,
        "metric": "Task Duration(us)",
        "statistic": "npu-compute task-log replay median",
        "current_frequency_mhz": current,
        "rated_frequency_mhz": rated,
        "rated_frequency_valid": positive(current)
        and positive(rated)
        and current == rated,
        "use": "comparison follows the caller's measurement policy",
    }


def inspect(skill, script, target, out):
    command = [
        sys.executable,
        "-B",
        str(Path(skill) / "scripts" / script),
        str(target),
        "--format",
        "json",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    out.write_text(result.stdout)
    out.with_suffix(".stderr").write_text(result.stderr)
    if result.returncode:
        raise ValueError(
            f"{script} failed ({result.returncode}): {result.stderr[-1000:]}"
        )
    json.loads(result.stdout)
    return {"command": command, "returncode": result.returncode, "result": receipt(out)}


def build_report(
    root,
    case_id,
    op_name,
    skill,
    out,
    summary=None,
    identity=None,
    specialist_report=None,
):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out == root or out.is_relative_to(root):
        raise ValueError("write reports outside immutable unpacked collection files")
    out.mkdir(parents=True)
    inspections = [
        inspect(
            skill, "inspect_collection.py", root, out / "collection-inspection.json"
        )
    ]
    path, records = select_summary(root, op_name, summary)
    compatibility = None
    try:
        checked_summary = inspect(
            skill, "inspect_summary.py", path, out / "summary-inspection.json"
        )
    except ValueError as original_error:
        from summary_compat import known_view

        view, compatibility = known_view(records, skill)
        derived = out / "summary-known-view.jsonl"
        derived.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
                for row in view
            )
        )
        checked_summary = inspect(
            skill, "inspect_summary.py", derived, out / "summary-known-inspection.json"
        )
        compatibility.update(
            original_summary=receipt(path),
            derived_view=receipt(derived),
            original_inspector=receipt(Path(skill) / "scripts/inspect_summary.py"),
            original_error=str(original_error),
            original_stdout=receipt(out / "summary-inspection.json"),
            original_stderr=receipt(out / "summary-inspection.stderr"),
        )
    inspections.append(checked_summary)
    # Root HardwareInfo can describe child result collections; preserve both identities.
    hardware = path.parent / "HardwareInfo.jsonl"
    if not hardware.exists():
        hardware = root / "HardwareInfo.jsonl"
    if hardware.exists():
        inspections.append(
            inspect(
                skill,
                "inspect_hardware_info.py",
                hardware,
                out / "hardware-inspection.json",
            )
        )
    pipeline = path.parent / "PipeTrace.json"
    if pipeline.exists():
        inspections.append(
            inspect(
                skill,
                "inspect_pipe_trace.py",
                pipeline,
                out / "pipeline-inspection.json",
            )
        )
    info = records[-1]
    duration = timing(info)
    limitations = []
    if pipeline.exists():
        limitations.append("Pipeline coverage is limited to recorded sources.")
    if not duration["rated_frequency_valid"]:
        limitations.append("Rated/current frequency is missing or mismatched.")
    result = {
        "schema_version": 1,
        "provider": "npu-compute",
        "case_id": case_id,
        "status": "diagnostic_valid"
        if duration["duration_us"] is not None
        else "incomplete",
        "performance_eligible": False,
        "identity": identity or {},
        "op_info": info,
        "timing": duration,
        "sections": {r["category"]: r for r in records[:-1]},
        "summary": receipt(path),
        "collection_root": str(root),
        "hardware": receipt(hardware) if hardware.exists() else None,
        "pipeline": receipt(pipeline) if pipeline.exists() else None,
        "specialist_report": receipt(specialist_report) if specialist_report else None,
        "inspections": inspections,
        "limitations": limitations,
        "summary_compatibility": compatibility,
    }
    target = out / "profile-report.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    temp.replace(target)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--op-name", required=True)
    parser.add_argument("--tool-skill", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--identity", type=Path)
    parser.add_argument("--specialist-report", type=Path)
    args = parser.parse_args()
    try:
        identity = json.loads(args.identity.read_text()) if args.identity else None
        result = build_report(
            args.collection_root,
            args.case_id,
            args.op_name,
            args.tool_skill,
            args.out,
            args.summary,
            identity,
            args.specialist_report,
        )
    except (OSError, ValueError, KeyError) as error:
        print(
            json.dumps({"status": "failed", "reason": str(error)}, ensure_ascii=False)
        )
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": str(args.out.resolve() / "profile-report.json"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
