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

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, NamedTuple, cast

from models import (
    KernelInvocation,
    OperatorStats,
    StepTrace,
    TorchNpuProfilerParseResult,
    TorchOpTiming,
)
from parser_base import (
    find_newest_csv,
    parse_api_statistic,
    parse_kernel_invocations,
    parse_op_statistic,
    safe_float as _safe_float,
)


def parse_kernel_details(csv_path: Path) -> list[KernelInvocation]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []

        # torch-npu-profiler uses: Name, Type, Accelerator Core, Duration(us), Wait Time(us), Block Dim
        invocations = parse_kernel_invocations(
            reader,
            fieldnames,
            name_col="Name" if "Name" in fieldnames else None,
            duration_col="Duration(us)" if "Duration(us)" in fieldnames else None,
            wait_col="Wait Time(us)" if "Wait Time(us)" in fieldnames else None,
            block_dim_col="Block Dim" if "Block Dim" in fieldnames else None,
            block_num_col="Block Num" if "Block Num" in fieldnames else None,
        )

    return invocations


def aggregate_kernel_details(invocations: list[KernelInvocation]) -> list[OperatorStats]:
    """Build minimal operator aggregates when op_statistic is unavailable."""
    grouped: dict[str, list[float]] = defaultdict(list)
    for invocation in invocations:
        grouped[invocation.op_name].append(invocation.duration_us)
    total_time = sum(sum(values) for values in grouped.values())
    operators: list[OperatorStats] = []
    for op_name, values in grouped.items():
        op_total = sum(values)
        operators.append(
            OperatorStats(
                op_type=op_name,
                core_type="unknown",
                count=len(values),
                total_time_us=op_total,
                min_time_us=min(values),
                avg_time_us=op_total / len(values),
                max_time_us=max(values),
                ratio_percent=(op_total / total_time * 100.0) if total_time else 0.0,
            )
        )
    return operators


def _operator_timing_from_row(
    row: dict[str, str], has_device: bool, has_aicore: bool
) -> TorchOpTiming | None:
    name = row.get("Name", "").strip()
    if not name:
        return None
    host_self = _safe_float(row.get("Host Self Duration(us)")) or 0.0
    host_total = _safe_float(row.get("Host Total Duration(us)")) or 0.0
    device_self = _safe_float(row.get("Device Self Duration(us)")) if has_device else 0.0
    device_total = _safe_float(row.get("Device Total Duration(us)")) if has_device else 0.0
    if has_aicore:
        aicore_self = _safe_float(row.get("Device Self Duration With AICore(us)")) or 0.0
        aicore_total = _safe_float(row.get("Device Total Duration With AICore(us)")) or 0.0
        if aicore_self > 0:
            device_self = aicore_self
            device_total = aicore_total
    return TorchOpTiming(
        name=name,
        host_self_us=host_self,
        host_total_us=host_total,
        device_self_us=device_self or 0.0,
        device_total_us=device_total or 0.0,
    )


def parse_operator_details(csv_path: Path) -> list[TorchOpTiming]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []

        has_device = "Device Self Duration(us)" in fieldnames
        has_aicore = "Device Self Duration With AICore(us)" in fieldnames

        ops: list[TorchOpTiming] = []
        for row in reader:
            timing = _operator_timing_from_row(row, has_device, has_aicore)
            if timing is not None:
                ops.append(timing)

    return ops


def parse_step_trace(csv_path: Path) -> list[StepTrace]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        traces: list[StepTrace] = []
        for row in reader:
            traces.append(
                StepTrace(
                    step=int(row.get("Step", "0")),
                    computing_us=_safe_float(row.get("Computing")) or 0.0,
                    communication_not_overlapped_us=_safe_float(
                        row.get("Communication(Not Overlapped)")
                    ) or 0.0,
                    overlapped_us=_safe_float(row.get("Overlapped")) or 0.0,
                    communication_us=_safe_float(row.get("Communication")) or 0.0,
                    free_us=_safe_float(row.get("Free")) or 0.0,
                    stage_us=_safe_float(row.get("Stage")) or 0.0,
                    bubble_us=_safe_float(row.get("Bubble")) or 0.0,
                    communication_not_overlapped_exclude_receive_us=_safe_float(
                        row.get("Communication(Not Overlapped and Exclude Receive)")
                    ) or 0.0,
                    preparing_us=_safe_float(row.get("Preparing")) or 0.0,
                )
            )
    return traces


def parse_trace_view(json_path: Path) -> list[dict[str, Any]]:
    data: Any = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    if isinstance(data, dict) and "traceEvents" in data:
        return cast(list[dict[str, Any]], data["traceEvents"])
    return []


class TorchNpuProfilerParser:
    """Parser for torch_npu.profiler ASCEND_PROFILER_OUTPUT/ artifacts."""

    @staticmethod
    def parse(
        artifacts_dir: Path,
    ) -> TorchNpuProfilerParseResult:
        paths = _locate_profile_artifacts(artifacts_dir)
        invocations = parse_kernel_details(paths.kernel_details) if paths.kernel_details else []
        operators = _resolve_operators(paths, invocations, artifacts_dir)
        timeline = parse_trace_view(paths.trace_view_files[-1]) if paths.trace_view_files else []
        return TorchNpuProfilerParseResult(
            operators=operators,
            invocations=invocations,
            torch_ops=parse_operator_details(paths.operator_details) if paths.operator_details else [],
            step_traces=parse_step_trace(paths.step_trace) if paths.step_trace else [],
            host_api=parse_api_statistic(paths.api_statistic) if paths.api_statistic else [],
            timeline=timeline,
            source_files=_source_files(paths),
        )


class _ProfileArtifactPaths(NamedTuple):
    op_statistic: Path | None
    kernel_details: Path | None
    operator_details: Path | None
    step_trace: Path | None
    api_statistic: Path | None
    trace_view_files: list[Path]


def _locate_profile_artifacts(artifacts_dir: Path) -> _ProfileArtifactPaths:
    return _ProfileArtifactPaths(
        op_statistic=find_newest_csv(artifacts_dir, "op_statistic"),
        kernel_details=find_newest_csv(artifacts_dir, "kernel_details"),
        operator_details=find_newest_csv(artifacts_dir, "operator_details"),
        step_trace=find_newest_csv(artifacts_dir, "step_trace_time"),
        api_statistic=find_newest_csv(artifacts_dir, "api_statistic"),
        trace_view_files=sorted(artifacts_dir.glob("trace_view.json")),
    )


def _resolve_operators(
    paths: _ProfileArtifactPaths, invocations: list[KernelInvocation], artifacts_dir: Path
) -> list[OperatorStats]:
    operators = parse_op_statistic(paths.op_statistic) if paths.op_statistic else []
    if not operators:
        operators = aggregate_kernel_details(invocations)
    if not operators:
        raise FileNotFoundError(f"No usable profile CSV found in {artifacts_dir}")
    return operators


def _source_files(paths: _ProfileArtifactPaths) -> dict[str, str | None]:
    return {
        "op_statistic": paths.op_statistic.name if paths.op_statistic else None,
        "kernel_details": paths.kernel_details.name if paths.kernel_details else None,
        "operator_stats_source": "op_statistic" if paths.op_statistic else "kernel_details",
        "operator_details": paths.operator_details.name if paths.operator_details else None,
        "step_trace_time": paths.step_trace.name if paths.step_trace else None,
        "api_statistic": paths.api_statistic.name if paths.api_statistic else None,
        "trace_view": paths.trace_view_files[-1].name if paths.trace_view_files else None,
    }
