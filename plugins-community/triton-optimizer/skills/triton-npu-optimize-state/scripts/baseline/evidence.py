# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from baseline.artifacts import inspect_baseline_artifacts, load_baseline_state
from shared.managed_integrity import operator_sha256, sha256_file
from shared.paths import declared_state_file


def baseline_evidence_issues(workspace: Path) -> tuple[str, ...]:
    """Return baseline evidence failures for the current baseline contract."""
    inspection = inspect_baseline_artifacts(workspace)
    if inspection.issues:
        return inspection.issues
    try:
        state = load_baseline_state(workspace)
        records = _load_records(workspace)
    except ValueError as exc:
        return (str(exc),)

    test_path = _declared_path(workspace, state.test_file)
    bench_path = _declared_path(workspace, state.bench_file)
    operator_path = _declared_path(workspace, state.baseline_operator)
    perf_path = _declared_path(workspace, state.perf_artifact)
    if any(path is None for path in (test_path, bench_path, operator_path, perf_path)):
        return ("baseline evidence requires all canonical baseline artifacts",)
    test_path = _require_declared(test_path)
    bench_path = _require_declared(bench_path)
    operator_path = _require_declared(operator_path)
    perf_path = _require_declared(perf_path)

    test_record = _last_matching_record(
        records,
        command="run-test-baseline",
        harness_key="test_file",
        harness_path=test_path,
        operator_path=operator_path,
    )
    bench_record = _last_matching_record(
        records,
        command="run-bench-baseline",
        harness_key="bench_file",
        harness_path=bench_path,
        operator_path=operator_path,
    )
    issues: list[str] = []
    if test_record is None:
        issues.append("missing baseline correctness evidence")
    elif test_record.get("status") != "passed":
        issues.append("last baseline correctness evidence failed")
    elif test_record.get("full_execution") is not True:
        issues.append("last baseline correctness evidence is not a full test run")

    if bench_record is None:
        issues.append("missing baseline benchmark evidence")
    elif bench_record.get("status") != "passed":
        issues.append("last baseline benchmark evidence failed")
    elif not _perf_matches(bench_record, perf_path):
        issues.append("baseline perf artifact does not match last benchmark evidence")
    return tuple(issues)


def _load_records(workspace: Path) -> list[dict[str, Any]]:
    path = workspace / ".helix" / "evidence" / "baseline.jsonl"
    if not path.is_file():
        raise ValueError("missing baseline evidence: .helix/evidence/baseline.jsonl")
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"unable to read baseline evidence: {exc}") from exc
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid baseline evidence JSON at line {index}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"invalid baseline evidence record at line {index}")
        records.append(cast(dict[str, Any], payload))
    return records


def _declared_path(workspace: Path, value: str) -> Path | None:
    return declared_state_file(workspace / "baseline", workspace, value)


def _require_declared(path: Path | None) -> Path:
    # Callers guard against None before narrowing; keep a defensive check for the type checker.
    if path is None:
        raise RuntimeError("baseline evidence requires all canonical baseline artifacts")
    return path


def _last_matching_record(
    records: list[dict[str, Any]],
    *,
    command: str,
    harness_key: str,
    harness_path: Path,
    operator_path: Path,
) -> dict[str, Any] | None:
    harness_hash_key = harness_key.replace("_file", "_sha256")
    harness_hash = sha256_file(harness_path)
    operator_hash = operator_sha256(operator_path)
    matches = []
    for record in records:
        if record.get("command") != command:
            continue
        if record.get(harness_key) != str(harness_path.resolve()):
            continue
        if record.get(harness_hash_key) != harness_hash:
            continue
        if record.get("operator_file") != str(operator_path.resolve()):
            continue
        if record.get("operator_sha256") != operator_hash:
            continue
        matches.append(record)
    return matches[-1] if matches else None


def _perf_matches(record: dict[str, Any], perf_path: Path) -> bool:
    recorded_path = record.get("artifact_path")
    recorded_hash = record.get("artifact_sha256")
    return (
        isinstance(recorded_path, str)
        and Path(recorded_path).resolve() == perf_path.resolve()
        and isinstance(recorded_hash, str)
        and perf_path.is_file()
        and sha256_file(perf_path) == recorded_hash
    )
