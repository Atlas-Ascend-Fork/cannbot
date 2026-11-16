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
"""Summarize existing Flash artifacts without running tests or issuing a verdict."""

import argparse
import collections
import csv
import hashlib
import logging
import json
from pathlib import Path
import subprocess
import sys

import yaml

LOG = logging.getLogger(__name__)


def version_status(work, node):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("code_versions.py")),
         "--work-dir", str(work), "status", "--node", node],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ValueError("code_versions status: " + result.stderr.strip())
    return json.loads(result.stdout)


class Summary:
    def __init__(self, work):
        self.work = work.resolve()
        self.files = {}
        self.issues = []

    @staticmethod
    def _current_attempts(state, node):
        return [(key, value) for key, value in state.get("attempts", {}).items()
                if key.startswith(node + "/") and value.get("sha") == state["head"]]

    @staticmethod
    def _validate_identity(identity):
        if not identity or Path(identity).name != identity:
            raise ValueError("invalid evidence ID")

    @staticmethod
    def _read_result_rows(path):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            return list(reader) if {"case_id", "status"} <= set(reader.fieldnames or []) else []

    @staticmethod
    def _record_result(row, active, device, seen, failed, duplicates, wrong_device, wrong_group, devices):
        case_id = row["case_id"]
        if case_id in seen:
            duplicates.add(case_id)
        seen.add(case_id)
        if row["status"].lower() != "passed":
            failed.add(case_id)
        actual_device = row.get("device", "")
        devices[actual_device] += 1
        if device and actual_device != device:
            wrong_device.add(case_id)
        if row.get("sheet") and case_id in active and row["sheet"] != active[case_id]:
            wrong_group.add(case_id)

    def file(self, name, expected=None, required=True):
        path = Path(name)
        path = (path if path.is_absolute() else self.work / path).resolve()
        if not path.is_relative_to(self.work):
            raise ValueError(f"artifact outside work directory: {name}")
        key = path.relative_to(self.work).as_posix()
        if key not in self.files:
            if path.is_file():
                data = path.read_bytes()
                self.files[key] = {"path": key, "bytes": len(data),
                                   "sha256": hashlib.sha256(data).hexdigest()}
            else:
                self.files[key] = {"path": key, "missing": True}
        item = self.files[key]
        if required and item.get("missing"):
            self.issues.append(f"missing: {key}")
        if expected is not None and item.get("sha256") != expected:
            self.issues.append(f"hash mismatch: {key}")
        return path

    def cases(self, path):
        if not path.is_file():
            return {}, {}
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not {"case_id", "sheet", "status"} <= set(reader.fieldnames or []):
                raise ValueError("casebook requires case_id, sheet and status")
            rows = list(reader)
        groups = collections.Counter()
        active = {}
        seen = set()
        for row in rows:
            case_id = row["case_id"]
            if not case_id or case_id in seen:
                self.issues.append(f"empty or duplicate case ID: {case_id!r}")
            seen.add(case_id)
            groups[(row["sheet"], row["status"])] += 1
            if row["status"] == "active":
                active[case_id] = row["sheet"]
        return active, {"rows": len(rows), "active": len(active), "groups": [
            {"sheet": sheet, "status": status, "count": count}
            for (sheet, status), count in sorted(groups.items())]}

    def evidence(self, state, node, active, device):
        attempts = self._current_attempts(state, node)
        if not attempts:
            self.issues.append("no attempt for current HEAD")
            return None
        key, attempt = attempts[-1]
        items = attempt.get("evidence", [])
        if not items:
            self.issues.append("current attempt has no recorded run")
            return {"attempt": key}
        evidence = items[-1]
        identity = evidence.get("id", "")
        self._validate_identity(identity)
        self._check_evidence_status(attempt, evidence, state)
        inputs = attempt.get("inputs", {})
        self._check_frozen_inputs(inputs, evidence)
        self._record_input_files(inputs)
        self._record_evidence_log(identity, evidence)
        results = self._record_evidence_artifacts(evidence)
        result_summary = self.results(results, active, device) if results else None
        if not results:
            self.issues.append("no archived result CSV; review the recorded runner output")
        return {"attempt": key, "id": identity, "sha": evidence.get("sha"),
                "exit_code": evidence.get("exit_code"), "valid": evidence.get("valid"),
                "command": evidence.get("command"), "log": f"versioning/{identity}.log",
                "results": result_summary}

    def _record_input_files(self, inputs):
        for name, digest in inputs.items():
            self.file(name, expected=digest)

    def _record_evidence_log(self, identity, evidence):
        log_hash = evidence.get("log_sha256")
        if not log_hash:
            self.issues.append("missing evidence log hash")
        self.file(Path("versioning") / (identity + ".log"), expected=log_hash)

    def _record_evidence_artifacts(self, evidence):
        results = []
        for name, digest in evidence.get("artifacts", {}).items():
            path = self.file(Path("versioning") / name, expected=digest)
            if path.name.startswith("verify_result") and path.suffix == ".csv" and path.is_file():
                results.append(path)
        return results

    def results(self, paths, active, device):
        rows = [row for path in paths for row in self._read_result_rows(path)]
        seen = set()
        failed, duplicates, wrong_device, wrong_group = set(), set(), set(), set()
        devices = collections.Counter()
        for row in rows:
            self._record_result(row, active, device, seen, failed, duplicates, wrong_device, wrong_group, devices)
        differences = {"missing": sorted(set(active) - seen), "unexpected": sorted(seen - set(active)),
                       "failed_or_skipped": sorted(failed), "duplicates": sorted(duplicates),
                       "wrong_device": sorted(wrong_device), "wrong_group": sorted(wrong_group)}
        if not active:
            self.issues.append("no active cases to match against results")
        for label, ids in differences.items():
            if ids:
                self.issues.append(f"results {label}: {len(ids)} case(s)")
        return {"rows": sum(devices.values()), "devices": dict(devices), **differences}

    def _check_evidence_status(self, attempt, evidence, state):
        valid = attempt.get("state") == "verified"
        valid = valid and evidence.get("sha") == state["head"]
        valid = valid and evidence.get("valid") is True
        valid = valid and evidence.get("exit_code") == 0
        if not valid:
            self.issues.append("latest evidence is not a valid successful run for current HEAD")

    def _check_frozen_inputs(self, inputs, evidence):
        if not inputs or evidence.get("inputs") != inputs:
            self.issues.append("missing or inconsistent frozen inputs")


def _validate_op_name(op):
    if not isinstance(op, str) or not op:
        raise ValueError("spec.op.name must be one directory name")
    if op in (".", "..") or "/" in op or "\\" in op:
        raise ValueError("spec.op.name must be one directory name")


def summarize(work, node, device=None):
    summary = Summary(work)
    op = _load_op_name(summary)
    _register_design_files(summary)
    state = _load_version_state(summary, work, node)
    tests = work / "operators" / op / "test"
    casebook = summary.file(tests / "testcase.csv")
    active, cases = summary.cases(casebook)
    delivered = _register_delivered(summary, work, node, op, tests, casebook)
    version = _register_version(summary, state, delivered, node)
    evidence = summary.evidence(state, node, active, device) if state else None
    return _summary_result(summary, node, cases, version, evidence)


def _load_op_name(summary):
    spec = yaml.safe_load(summary.file("design/doc/spec.yaml").read_text(encoding="utf-8"))
    op = spec["op"]["name"]
    _validate_op_name(op)
    return op


def _register_design_files(summary):
    for name in ("design/doc/REQUIREMENTS.md", "design/doc/DESIGN.md", "design/selection.yaml"):
        summary.file(name)
    for name in ("environment/environment.yaml", "environment/soc-info.yaml"):
        summary.file(name, required=False)


def _load_version_state(summary, work, node):
    if node == "solution-design":
        return None
    if (work / "versioning/state.json").is_file():
        return version_status(work, node)
    if node == "implementation":
        summary.issues.append("implementation has no registered code version")
    return None


def _register_delivered(summary, work, node, op, tests, casebook):
    delivered = [casebook]
    if node != "solution-design":
        delivered += [summary.file(tests / f"{op}_golden.py"), summary.file(tests / f"test_{op}.py")]
        summary.file(f"{node}/report.md", required=False)
    if node == "implementation":
        delivered.append(summary.file(work / "operators" / op / f"{op}.py"))
    return delivered


def _register_version(summary, state, delivered, node):
    if not state:
        return None
    version = {"CODE_DIR": state["CODE_DIR"], "head": state["head"],
               "changes": state.get("changes", []), "accepted": state.get("accepted", {}).get(node),
               "stale_accepted": state.get("stale_accepted", [])}
    for path in delivered:
        registered = summary.file(Path(state["CODE_DIR"]) / path.relative_to(summary.work))
        digest = summary.files[registered.relative_to(summary.work).as_posix()].get("sha256")
        if digest:
            summary.file(path, expected=digest)
    if state.get("changes"):
        summary.issues.append("code checkout has uncommitted changes")
    return version


def _summary_result(summary, node, cases, version, evidence):
    return {"status": "attention" if summary.issues else "ok", "node": node,
            "scope": "artifact identities and recorded results only; no semantic verdict",
            "files": list(summary.files.values()), "cases": cases, "version": version,
            "evidence": evidence, "issues": list(dict.fromkeys(summary.issues))}


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--node", required=True,
                        choices=("solution-design", "test-integration", "implementation"))
    parser.add_argument("--device", help="expected device value in archived result rows")
    args = parser.parse_args()
    try:
        result = summarize(args.work_dir.resolve(), args.node, args.device)
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        result = {"status": "attention", "error": str(error)}
    LOG.info(json.dumps(result, ensure_ascii=False, indent=2))
    # This command reports findings. Existing verdict/accept protocols remain authoritative.
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
