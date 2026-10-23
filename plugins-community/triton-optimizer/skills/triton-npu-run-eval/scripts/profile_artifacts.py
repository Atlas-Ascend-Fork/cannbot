# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Shared profile artifact file contract for transport and validation."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path


RETAINED_PROFILE_FILE_PATTERNS = (
    "kernel_details.csv",
    "operator_details.csv",
    "step_trace_time.csv",
    "api_statistic.csv",
    "op_statistic.csv",
    "op_statistic_*.csv",
    "op_summary.csv",
    "op_summary_*.csv",
    "task_time.csv",
    "task_time_*.csv",
)


def is_retained_profile_file(path: Path) -> bool:
    return any(fnmatch(path.name, pattern) for pattern in RETAINED_PROFILE_FILE_PATTERNS)


def has_retained_profile_file(profile_dir: Path) -> bool:
    return any(path.is_file() and is_retained_profile_file(path) for path in profile_dir.rglob("*"))


def validate_profile_dir(profile_dir: Path) -> None:
    if not has_retained_profile_file(profile_dir):
        raise FileNotFoundError(f"Profiler output is incomplete: no optimization CSV under {profile_dir}")
