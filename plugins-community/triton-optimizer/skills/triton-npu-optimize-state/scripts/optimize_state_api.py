# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Stable Helix-facing API for optimize-state contracts and workflow state."""

from __future__ import annotations

__all__ = (
    "baseline_gate_issues",
    "best_completed_round_geomean_speedup",
    "bootstrap_state",
    "check_baseline",
    "check_round",
    "cleanup_dir_pt_files",
    "cleanup_pt_file",
    "cleanup_workspace_profile_artifacts",
    "count_completed_round_directories",
    "count_terminal_round_directories",
    "initialize_baseline_integrity",
    "inspect_round_artifacts",
    "iter_terminal_round_directories",
    "load_baseline_state",
    "load_round_state",
    "load_state",
    "ordinary_optimize_pt_cleanup_mode",
    "update_execution_context",
    "resolve_round_operator_file",
    "resolve_round_perf_file",
)

from baseline.check import (
    baseline_gate_issues,
    check_baseline,
    load_baseline_state,
)
from round.check import (
    best_completed_round_geomean_speedup,
    check_round,
    cleanup_dir_pt_files,
    cleanup_pt_file,
    cleanup_workspace_profile_artifacts,
    count_completed_round_directories,
    count_terminal_round_directories,
    inspect_round_artifacts,
    iter_terminal_round_directories,
    load_round_state,
    ordinary_optimize_pt_cleanup_mode,
    resolve_round_operator_file,
    resolve_round_perf_file,
)
from state_manage.state_machine import (
    bootstrap_state,
    load_state,
    update_execution_context,
)
from shared.managed_integrity import initialize_baseline_integrity
