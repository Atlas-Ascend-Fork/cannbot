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

from baseline.artifacts import (
    BaselineState as BaselineState,
    inspect_baseline_artifacts,
    load_baseline_state,
)
from baseline.evidence import baseline_evidence_issues
from shared.models import OptimizeCheckResult
from shared.results import build_check_result


def baseline_gate_issues(workspace: Path) -> tuple[str, ...]:
    inspection = inspect_baseline_artifacts(workspace)
    if inspection.issues:
        return inspection.issues

    try:
        state = load_baseline_state(workspace)
    except ValueError as exc:
        return (str(exc),)

    issues: list[str] = []
    if state.correctness_status != "passed":
        issues.append(f"baseline correctness_status={state.correctness_status}")
    if state.benchmark_status != "passed":
        issues.append(f"baseline benchmark_status={state.benchmark_status}")
    return tuple(issues)


def check_baseline(baseline_dir_path: Path) -> OptimizeCheckResult:
    issues = baseline_gate_issues(baseline_dir_path.parent)
    if not issues:
        issues = baseline_evidence_issues(baseline_dir_path.parent)
    if issues:
        return build_check_result(
            kind="baseline",
            status="fail",
            issues=issues,
        )
    return build_check_result(
        kind="baseline",
        status="pass",
        issues=(),
    )
