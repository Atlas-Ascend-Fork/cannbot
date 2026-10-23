# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Bench-mode normalization and copy-file collection for run-bench workflows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from env_registry import HELIX_BENCH_COPY_FILES
from perf_artifacts import normalize_bench_mode as _normalize_retired_bench_mode


def _collect_pattern_matches(
    search_dir: Path, pattern: str, seen: set[Path], paths: list[Path]
) -> None:
    for matched in sorted(search_dir.glob(pattern)):
        if not matched.is_file():
            continue
        resolved = matched.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        paths.append(matched)


def _collect_env_copy_files(search_dir: Path) -> list[Path]:
    patterns_str = os.environ.get(HELIX_BENCH_COPY_FILES, "")
    if not patterns_str.strip():
        return []
    patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]
    paths: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        _collect_pattern_matches(search_dir, pattern, seen, paths)
    return paths


def collect_bench_copy_files(search_dir: Path) -> list[Path]:
    return _collect_env_copy_files(search_dir)


_msprof_deprecation_emitted = False


def normalize_bench_mode(bench_mode: str) -> str:
    """Map retired bench-mode spellings to the mode that replaced them.

    ``msprof`` used to be a dedicated bench mode backed by the external
    msprof binary; it now falls back to the torch-npu-profiler path, with a
    one-time deprecation notice so callers can observe the behavior change.
    """
    if bench_mode == "msprof":
        _emit_msprof_deprecation_notice()
    return _normalize_retired_bench_mode(bench_mode)


def _emit_msprof_deprecation_notice() -> None:
    global _msprof_deprecation_emitted
    if _msprof_deprecation_emitted:
        return
    _msprof_deprecation_emitted = True
    print(
        'bench-mode "msprof" is deprecated; using "torch-npu-profiler" instead.',
        file=sys.stderr,
    )
