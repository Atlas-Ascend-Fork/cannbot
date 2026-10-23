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
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from models import HostApiCall, KernelInvocation, OperatorStats, PipelineStage

# Columns in op_statistic CSV (identical in both msprof and torch-npu-profiler modes)
_STATISTIC_REQUIRED_COLUMNS = (
    "OP Type",
    "Core Type",
    "Count",
    "Total Time(us)",
    "Min Time(us)",
    "Avg Time(us)",
    "Max Time(us)",
    "Ratio(%)",
)

# Columns in api_statistic CSV (identical in both modes)
_API_NAME_COLUMNS = ("API Name", "Name")
_API_TIME_COLUMNS = ("Time(us)", "Duration(us)")


def parse_float_value(value: str) -> float:
    return float(value.strip())


def safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def build_pipeline_stage(
    fieldnames: Sequence[str],
    row: Mapping[str, str],
) -> PipelineStage | None:
    """Preserve dynamic pipe columns and their paired stage/engine times."""
    ratios: dict[str, float] = {}
    ratio_headers: dict[str, str] = {}
    stage_times: dict[str, float] = {}
    engine_times: dict[str, float] = {}
    cube_header: str | None = None
    cube_value: float | None = None
    for header in fieldnames:
        value = safe_float(row.get(header))
        normalized = header.strip().lower()
        if value is None:
            continue
        if normalized.startswith(("aic_", "aiv_")) and "_ratio" in normalized:
            canonical = normalized.split("(", 1)[0].strip()
            ratios[canonical] = value
            ratio_headers[canonical] = header
        elif normalized in ("aicore_time(us)", "aiv_time(us)"):
            engine_times["aic" if normalized.startswith("aicore") else "aiv"] = value
        elif normalized.startswith(("aic_", "aiv_")) and "_time(us)" in normalized:
            canonical = normalized.split("(", 1)[0].strip().removesuffix("_time")
            stage_times[canonical] = value
        elif normalized.startswith("cube_utilization"):
            cube_header = header
            cube_value = value
    if not ratios and cube_value is None:
        return None
    return PipelineStage(
        ratios=ratios,
        ratio_headers=ratio_headers,
        stage_times_us=stage_times,
        engine_times_us=engine_times,
        cube_utilization=cube_value,
        cube_utilization_header=cube_header,
    )


def parse_kernel_invocations(
    reader: csv.DictReader,
    fieldnames: Sequence[str],
    *,
    name_col: str | None,
    duration_col: str | None,
    wait_col: str | None,
    block_dim_col: str | None,
    block_num_col: str | None,
) -> list[KernelInvocation]:
    """Shared row loop for op_summary (msprof) and kernel_details (torch-npu-profiler)."""
    invocations: list[KernelInvocation] = []
    for row in reader:
        op_name = (row.get(name_col, "") if name_col else "").strip()
        if not op_name:
            continue
        duration = safe_float(row[duration_col]) if duration_col else None
        wait_time = safe_float(row[wait_col]) if wait_col else None
        block_dim = int(safe_float(row[block_dim_col]) or 0) if block_dim_col else 0
        block_num = int(safe_float(row[block_num_col]) or 0) if block_num_col else 0

        pipeline = build_pipeline_stage(fieldnames, row)
        invocations.append(
            KernelInvocation(
                op_name=op_name,
                duration_us=duration or 0.0,
                wait_time_us=wait_time or 0.0,
                block_dim=block_dim,
                block_num=block_num,
                block_num_header=block_num_col,
                block_dim_header=block_dim_col,
                pipeline=pipeline,
            )
        )

    return invocations


def detect_profile_mode(profile_path: Path) -> tuple[Literal["msprof", "torch-npu-profiler"], Path]:
    """Auto-detect profile mode from directory structure.

    Returns (mode, artifacts_dir).
    """
    candidate = profile_path.expanduser().resolve()

    # torch-npu-profiler: check ASCEND_PROFILER_OUTPUT first
    # (torch_npu.profiler also emits a PROF_*/mindstudio_profiler_output as a side effect,
    #  but ASCEND_PROFILER_OUTPUT has kernel_details.csv with richer pipeline data)
    torch_npu_profiler_dir = _find_artifacts_dir(candidate, "ASCEND_PROFILER_OUTPUT")
    msprof_dir = _find_artifacts_dir(candidate, "mindstudio_profiler_output")

    # Fallback: rglob within candidate
    if torch_npu_profiler_dir is None:
        for match in candidate.rglob("ASCEND_PROFILER_OUTPUT"):
            if match.is_dir():
                torch_npu_profiler_dir = match
                break
    if msprof_dir is None:
        for match in candidate.rglob("mindstudio_profiler_output"):
            if match.is_dir():
                msprof_dir = match
                break

    # Prefer torch-npu-profiler when both exist (richer data)
    if torch_npu_profiler_dir is not None:
        return "torch-npu-profiler", torch_npu_profiler_dir
    if msprof_dir is not None:
        return "msprof", msprof_dir

    raise FileNotFoundError(
        f"No profile artifacts directory found under {candidate}"
    )


def _find_artifacts_dir(base: Path, name: str) -> Path | None:
    if not base.is_dir():
        return None
    if base.name == name and base.is_dir():
        return base
    candidate = base / name
    if candidate.is_dir():
        return candidate
    return None


def find_newest_csv(output_dir: Path, prefix: str) -> Path | None:
    matches = sorted(output_dir.glob(f"{prefix}_*.csv"))
    if not matches:
        # Try without timestamp suffix
        plain = output_dir / f"{prefix}.csv"
        if plain.is_file():
            return plain
        return None
    return max(matches, key=lambda item: item.stat().st_mtime_ns)


def parse_op_statistic(csv_path: Path) -> list[OperatorStats]:
    """Parse op_statistic CSV (identical schema in both modes)."""
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [
            col
            for col in _STATISTIC_REQUIRED_COLUMNS
            if col not in fieldnames
        ]
        if missing:
            raise ValueError(
                f"Missing required columns in {csv_path}: {', '.join(missing)}"
            )

        rows: list[OperatorStats] = []
        for row in reader:
            rows.append(
                OperatorStats(
                    op_type=row["OP Type"].strip(),
                    core_type=row["Core Type"].strip(),
                    count=int(parse_float_value(row["Count"])),
                    total_time_us=parse_float_value(row["Total Time(us)"]),
                    min_time_us=parse_float_value(row["Min Time(us)"]),
                    avg_time_us=parse_float_value(row["Avg Time(us)"]),
                    max_time_us=parse_float_value(row["Max Time(us)"]),
                    ratio_percent=parse_float_value(row["Ratio(%)"]),
                )
            )

    if not rows:
        raise ValueError(f"No rows found in {csv_path}")
    return rows


def parse_api_statistic(csv_path: Path) -> list[HostApiCall]:
    """Parse api_statistic CSV (identical schema in both modes)."""
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        name_column = next(
            (name for name in _API_NAME_COLUMNS if name in fieldnames), None
        )
        time_column = next(
            (name for name in _API_TIME_COLUMNS if name in fieldnames), None
        )
        if name_column is None:
            raise ValueError(
                f"No API-identifying column recognized in {csv_path}"
            )

        rows: list[HostApiCall] = []
        for row in reader:
            count_raw = row.get("Count", "1")
            count = int(parse_float_value(count_raw)) if count_raw.strip() else 1
            rows.append(
                HostApiCall(
                    api_name=row.get(name_column, "").strip(),
                    level=row.get("Level", "").strip(),
                    time_us=parse_float_value(row[time_column]) if time_column else 0.0,
                    count=count,
                    avg_us=parse_float_value(row.get("Avg(us)", row.get("Avg", "0"))),
                )
            )

    return rows
