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
"""Check explicitly selected Checker evidence without changing it or assigning workflow PASS."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import contextlib
from dataclasses import dataclass, field
import importlib.util
import io
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
CLI = importlib.import_module("validate_aicpu_artifacts")


@dataclass
class Collection:
    result: dict
    totals: Counter = field(
        default_factory=lambda: Counter(runs=0, cases=0, case_seconds=0)
    )
    recorded_totals: Counter = field(
        default_factory=lambda: Counter(runs=0, cases=0, case_seconds=0)
    )
    by_role: dict = field(default_factory=lambda: defaultdict(Counter))
    identities: dict = field(
        default_factory=lambda: {"baseline": set(), "candidate": set()}
    )
    snapshots: dict = field(default_factory=dict)
    phase_keys: dict = field(default_factory=dict)


def load_tool(root):
    path = Path(root).resolve() / "evidence.py"
    spec = importlib.util.spec_from_file_location("ccu_checker_evidence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def validate_expected_cases(expected):
    if not isinstance(expected, list) or not expected:
        raise ValueError(
            "explicit unique expected_cases must come from the frozen plan"
        )
    if any(not isinstance(case, str) or not case for case in expected):
        raise ValueError(
            "explicit unique expected_cases must come from the frozen plan"
        )
    if len(set(expected)) != len(expected):
        raise ValueError(
            "explicit unique expected_cases must come from the frozen plan"
        )


def validate_run_selection(item, chosen):
    rid, role = item.get("id"), item.get("role")
    if not isinstance(rid, str) or not rid.strip() or rid in chosen:
        raise ValueError("run ids must be nonempty and unique")
    if role not in {"baseline", "directed", "regression"}:
        raise ValueError("explicit baseline/directed/regression role is required")
    if not isinstance(item.get("source_id"), str) or not item["source_id"].strip():
        raise ValueError("explicit expected source_id is required")
    validate_expected_cases(item.get("expected_cases"))
    if role == "directed" and not item.get("expect_algo"):
        raise ValueError("directed selection requires expect_algo from the frozen plan")
    if not isinstance(item.get("allow_case_overlap", False), bool):
        raise ValueError("allow_case_overlap must be boolean")
    if item.get("allow_case_overlap"):
        basis = item.get("overlap_basis")
        if not isinstance(basis, str) or not basis.strip():
            raise ValueError(
                "intentional case overlap requires a frozen-plan overlap_basis"
            )
    return rid


def select_runs(config, selection):
    if (
        config.get("schema_version") != 1
        or not isinstance(config.get("runs"), list)
        or not config["runs"]
    ):
        raise ValueError(
            "selection requires schema_version=1 and a nonempty explicit runs list"
        )
    chosen, paths = {}, set()
    for item in config["runs"]:
        rid = validate_run_selection(item, chosen)
        root = (selection.parent / item["path"]).resolve()
        if root in paths:
            raise ValueError("the same resolved run directory was selected twice")
        paths.add(root)
        chosen[rid] = (item, root)
    return chosen


def validate_comparisons(comparisons, chosen):
    if not isinstance(comparisons, list):
        raise ValueError("comparisons must be a list")
    seen = set()
    for pair in comparisons:
        ids = (pair["baseline"], pair["regression"])
        if ids in seen:
            raise ValueError("duplicate comparison pair")
        seen.add(ids)
        if any(rid not in chosen for rid in ids):
            raise ValueError(
                "comparison must reference selected baseline and regression ids"
            )
        roles = (chosen[ids[0]][0]["role"], chosen[ids[1]][0]["role"])
        if roles != ("baseline", "regression"):
            raise ValueError(
                "comparison must reference selected baseline and regression ids"
            )


def initial_result(selection, tool_path, tool):
    return dict(
        schema_version=1,
        evidence_checks_ok=True,
        scope="mechanical evidence checks only; role reports and state gates remain required",
        totals_basis="validated runs only; all failed selected runs remain listed and block evidence_checks_ok",
        selection_sha256=tool.digest(selection),
        evidence_tool_sha256=tool.digest(tool_path),
        runs=[],
        comparisons=[],
        issues=[],
        totals={},
        recorded_totals={},
        by_role={},
    )


def duration_seconds(value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("invalid duration_seconds")
    return value


def recorded_seconds(path):
    records = [
        json.loads(line) for line in path.read_text().splitlines() if line.strip()
    ]
    seconds = 0
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("invalid duration_seconds in recorded results")
        try:
            seconds += duration_seconds(record.get("duration_seconds"))
        except ValueError as exc:
            raise ValueError("invalid duration_seconds in recorded results") from exc
    return len(records), seconds


def record_identity(manifest):
    libraries = sorted(
        (entry["kind"], entry["sha256"]) for entry in manifest["installed_libraries"]
    )
    return json.dumps(
        dict(
            source_id=manifest["source_id"],
            artifact=manifest["declared_artifact"],
            libraries=libraries,
        ),
        sort_keys=True,
    )


def validate_record(cid, record, item, tool):
    raw = Path(record["raw_log"])
    expected = item.get("expect_algo", "")
    text = raw.read_text(errors="replace")
    # A success summary must never waive a concrete error-level log entry.
    normalized = re.sub(r"\x1b\[[0-9;]*m", "", text)
    if re.search(r"\[(?:error|fatal)\]", normalized, re.I):
        raise ValueError(
            cid
            + ": original log contains ERROR/FATAL severity; a success summary cannot waive it"
        )
    parsed = tool.parse_log(text, expected, record["timed_out"])
    if parsed["verdict"] != "PASS":
        raise ValueError(cid + ": original log fails Checker/algorithm assertion")
    for key, value in parsed.items():
        if record.get(key) != value:
            raise ValueError(
                cid + ": recorded result disagrees with original log: " + key
            )
    if tool.digest(raw) != record["raw_log_sha256"]:
        raise ValueError(cid + ": log changed during collection")
    if expected:
        if record.get("expected_algorithm") != expected or record[
            "observed_algorithms"
        ] != [expected]:
            raise ValueError(
                cid + ": directed algorithm does not match frozen expectation"
            )
    try:
        return duration_seconds(record["duration_seconds"])
    except ValueError as exc:
        raise ValueError(cid + ": invalid duration_seconds") from exc


def validate_records(records, item, tool, phase_keys):
    algorithms, seconds = Counter(), 0
    for cid, record in records.items():
        phase_key = (item["role"], cid)
        allowed_overlap = item.get("allow_case_overlap") or phase_keys.get(
            phase_key, False
        )
        if phase_key in phase_keys and not allowed_overlap:
            raise ValueError(
                "duplicate case within one role; distinguish an intentional smoke/repeat with a separate selection"
            )
        phase_keys[phase_key] = phase_keys.get(phase_key, False) or item.get(
            "allow_case_overlap", False
        )
        seconds += validate_record(cid, record, item, tool)
        algorithms.update(record["algorithm_counts"])
    return seconds, algorithms


def collect_run(row, item, root, tool, state):
    manifest_path, results_path = root / "manifest.json", root / "results.jsonl"
    initial = (tool.digest(manifest_path), tool.digest(results_path))
    state.snapshots[root] = initial
    row.update(manifest_sha256=initial[0], results_sha256=initial[1])
    raw_count, raw_seconds = recorded_seconds(results_path)
    row.update(recorded_cases=raw_count, recorded_case_seconds=raw_seconds)
    state.recorded_totals.update(runs=1, cases=raw_count, case_seconds=raw_seconds)
    manifest, records = tool.validate(
        root, require_pass=True, require_role=item["role"]
    )
    if manifest["source_id"] != item["source_id"]:
        raise ValueError("manifest source_id differs from the selected source identity")
    if set(records) != set(item["expected_cases"]):
        raise ValueError("run cases differ from the frozen selection")
    identity_role = "baseline" if item["role"] == "baseline" else "candidate"
    state.identities[identity_role].add(record_identity(manifest))
    seconds, algorithms = validate_records(records, item, tool, state.phase_keys)
    if initial != (tool.digest(manifest_path), tool.digest(results_path)):
        raise ValueError("manifest/results changed during collection")
    row.update(
        validation_ok=True,
        source_id=manifest["source_id"],
        package_sha256=manifest["declared_artifact"]["package_sha256"],
        expected_libraries=manifest["declared_artifact"]["expected_libraries"],
        manifest_sha256=initial[0],
        results_sha256=initial[1],
        cases=len(records),
        case_seconds=seconds,
        algorithm_counts=dict(algorithms),
        case_ids=sorted(records),
    )
    values = dict(runs=1, cases=len(records), case_seconds=seconds)
    state.totals.update(values)
    state.by_role[item["role"]].update(values)


def compare_runs(pair, chosen, tool, result):
    row = dict(pair, comparison_ok=False)
    result["comparisons"].append(row)
    try:
        runs_by_id = {run["id"]: run for run in result["runs"]}
        for role in ("baseline", "regression"):
            selected = runs_by_id.get(pair.get(role))
            if not selected or not selected.get("validation_ok"):
                raise ValueError("a selected run failed integrity checks")
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            tool.compare(chosen[pair["baseline"]][1], chosen[pair["regression"]][1])
        row.update(comparison_ok=True, detail=capture.getvalue().strip())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        row["error"] = str(exc)
        result["issues"].append("comparison: " + str(exc))


def check_identities(state):
    if len(state.identities["candidate"]) > 1:
        state.result["issues"].append(
            "directed and regression runs do not share one candidate artifact/library identity"
        )
    if len(state.identities["baseline"]) > 1:
        state.result["issues"].append(
            "baseline runs do not share one baseline artifact/library identity"
        )


def check_final_inputs(selection, original, tool_path, tool, state):
    for root, snapshot in state.snapshots.items():
        if snapshot != (
            tool.digest(root / "manifest.json"),
            tool.digest(root / "results.jsonl"),
        ):
            state.result["issues"].append(
                str(root) + ": inputs changed during final comparison"
            )
    if (
        selection.read_bytes() != original
        or tool.digest(tool_path) != state.result["evidence_tool_sha256"]
    ):
        state.result["issues"].append(
            "selection or evidence tool changed during collection"
        )


def summarize(selection, hvm_skill_dir):
    selection = Path(selection).resolve()
    original = selection.read_bytes()
    config = json.loads(original)
    tool, tool_path = load_tool(hvm_skill_dir)
    chosen = select_runs(config, selection)
    comparisons = config.get("comparisons", [])
    validate_comparisons(comparisons, chosen)
    result = initial_result(selection, tool_path, tool)
    state = Collection(result)
    regression_ids = {
        rid for rid, (item, _) in chosen.items() if item["role"] == "regression"
    }
    compared_ids = {pair["regression"] for pair in comparisons}
    if regression_ids != compared_ids:
        result["issues"].append(
            "every selected regression run needs an explicit baseline comparison"
        )
    for rid, (item, root) in chosen.items():
        row = dict(id=rid, path=str(root), role=item["role"], validation_ok=False)
        result["runs"].append(row)
        try:
            collect_run(row, item, root, tool, state)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            row["error"] = str(exc)
            result["issues"].append(rid + ": " + str(exc))
    check_identities(state)
    for pair in comparisons:
        compare_runs(pair, chosen, tool, result)
    check_final_inputs(selection, original, tool_path, tool, state)
    result.update(
        totals=dict(state.totals),
        recorded_totals=dict(state.recorded_totals),
        by_role={role: dict(values) for role, values in state.by_role.items()},
        evidence_checks_ok=not result["issues"],
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--hvm-skill-dir", required=True)
    args = parser.parse_args()
    try:
        result = summarize(args.selection, args.hvm_skill_dir)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        result = dict(evidence_checks_ok=False, error=str(exc))
    CLI.emit_json(result, indent=2)
    return 0 if result["evidence_checks_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
