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

from pathlib import Path

from baseline.contract import (
    BASELINE_BENCHMARK_STATUS_VALUES,
    BASELINE_CORRECTNESS_STATUS_VALUES,
    BASELINE_STATE_REQUIRED_FIELDS,
)
from shared.ascendc_operator_files import ascendc_source_path, is_ascendc_api
from shared.json_io import load_json_object, optional_str
from shared.models import BaselineArtifactsInspection, BaselineState
from shared.paths import (
    baseline_dir,
    declared_state_file,
    existing_file,
    missing_path_issue,
)


_BASELINE_METADATA_FILENAMES = {
    "state.json",
    "perf.txt",
}
_ALLOWED_CORRECTNESS_STATUS_VALUES = frozenset(BASELINE_CORRECTNESS_STATUS_VALUES)
_ALLOWED_BENCHMARK_STATUS_VALUES = frozenset(BASELINE_BENCHMARK_STATUS_VALUES)
# Retired bench-mode spellings recorded by historical workspaces. Loading
# normalizes them so resume and verify paths see only live modes.
_RETIRED_BENCH_MODE_ALIASES = {
    "standalone": "torch-npu-profiler",
    "msprof": "torch-npu-profiler",
}


def load_baseline_state(workspace: Path) -> BaselineState:
    state_path = baseline_dir(workspace) / "state.json"
    data = load_json_object(state_path, display_name="baseline/state.json")
    missing_fields = [
        field_name
        for field_name in BASELINE_STATE_REQUIRED_FIELDS
        if field_name not in data
    ]
    if missing_fields:
        raise ValueError("missing required baseline-state fields: " + ", ".join(missing_fields))
    correctness_status = _validated_status_value(
        "correctness_status",
        data["correctness_status"],
        allowed_values=_ALLOWED_CORRECTNESS_STATUS_VALUES,
    )
    benchmark_status = _validated_status_value(
        "benchmark_status",
        data["benchmark_status"],
        allowed_values=_ALLOWED_BENCHMARK_STATUS_VALUES,
    )
    return BaselineState(
        source_operator=str(data["source_operator"]),
        baseline_operator=str(data["baseline_operator"]),
        test_file=str(data["test_file"]),
        test_mode=str(data["test_mode"]),
        bench_file=str(data["bench_file"]),
        bench_mode=_RETIRED_BENCH_MODE_ALIASES.get(str(data["bench_mode"]), str(data["bench_mode"])),
        perf_artifact=str(data["perf_artifact"]),
        correctness_status=correctness_status,
        benchmark_status=benchmark_status,
        preparation_notes=optional_str(data.get("preparation_notes")),
        baseline_repairs_summary=optional_str(data.get("baseline_repairs_summary")),
    )


def inspect_baseline_artifacts(workspace: Path) -> BaselineArtifactsInspection:
    root = baseline_dir(workspace)
    state_path = existing_file(root / "state.json")
    state: BaselineState | None = None
    if state_path is not None:
        try:
            state = load_baseline_state(workspace)
        except ValueError:
            state = None

    declared_perf = state.perf_artifact if state is not None else None
    declared_operator = state.baseline_operator if state is not None else None

    if state is None:
        perf_path = None
        operator_path = None
    else:
        perf_path = declared_state_file(root, workspace, declared_perf)
        operator_path = declared_state_file(root, workspace, declared_operator)

    if state is None and perf_path is None:
        perf_path = _find_fallback_perf_artifact(root)
    if state is None and operator_path is None:
        operator_path = _find_baseline_operator_snapshot(root)

    issues: list[str] = []
    if state_path is None:
        issues.append("missing baseline/state.json")
    if perf_path is None:
        issues.append(missing_path_issue("perf_artifact", declared_perf))
    if operator_path is None:
        if declared_operator is None:
            issues.append("missing baseline operator snapshot")
        else:
            issues.append(
                missing_path_issue(
                    "baseline_operator",
                    declared_operator,
                )
            )
    elif is_ascendc_api(operator_path) and not ascendc_source_path(operator_path).is_file():
        issues.append(f"missing AscendC source: {ascendc_source_path(operator_path).name}")

    return BaselineArtifactsInspection(
        baseline_dir=root,
        state_path=state_path,
        perf_path=perf_path,
        operator_path=operator_path,
        issues=tuple(issues),
    )


def _find_baseline_operator_snapshot(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    candidates = [
        path
        for path in sorted(root.iterdir())
        if path.is_file() and path.name not in _BASELINE_METADATA_FILENAMES
    ]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        preferred_python = [path for path in candidates if path.suffix == ".py"]
        if len(preferred_python) == 1:
            return preferred_python[0]
        return candidates[0]
    return None


def _find_fallback_perf_artifact(root: Path) -> Path | None:
    legacy_perf = existing_file(root / "perf.txt")
    if legacy_perf is not None:
        return legacy_perf
    candidates = sorted(path for path in root.glob("*_perf.txt") if path.is_file())
    if len(candidates) == 1:
        return candidates[0]
    return None


def _validated_status_value(
    field_name: str,
    raw_value: object,
    *,
    allowed_values: frozenset[str],
) -> str:
    value = str(raw_value)
    if value not in allowed_values:
        allowed_text = ", ".join(sorted(allowed_values))
        raise ValueError(f"baseline/state.json {field_name} must be one of: {allowed_text}")
    return value
