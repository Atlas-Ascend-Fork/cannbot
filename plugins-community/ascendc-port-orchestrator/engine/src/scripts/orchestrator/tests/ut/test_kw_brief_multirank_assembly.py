# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Multirank kw-brief assembly — brief-level wiring of the structural blocks.

The plugin-level block tests (test_multirank_plugin.py) assert what each
block CONTAINS; these tests assert what an assembled worker brief actually
CARRIES, for both spawn routes:

- cold start (no directive): the multirank phase block (scaffold command,
  multirank_runner verify) and the NEST layout block are present;
- respawn with a directive: the directive stays a tactical overlay and the
  multirank structural recipe rides along;
- npubench-bound multirank workspace: the single-card npubench builder does
  NOT take over the brief (the binding selects the truth tier, not the
  worker contract);
- single-card npubench workspace: the npubench builder still owns the brief
  (regression).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))
from briefs import kw_brief  # noqa: E402
from briefs._common import AscendCEnv  # noqa: E402
from npubench.npubench_inputs import stage_npubench_inputs  # noqa: E402
from reference_source import explicit_a3_live_binding  # noqa: E402

_MR_PHASE_TITLE = "Multirank compute-communication fusion kernel-worker"
_MR_LAYOUT_TITLE = "FIXED OUTPUT LAYOUT (Multirank: nest"
_GENERIC_LAYOUT_TITLE = "FIXED OUTPUT LAYOUT CONTRACT (PB-33"
_NPUBENCH_PHASE_TITLE = "# PHASES (NPUKernelBench port)"
_SCAFFORD_SCRIPT = "multirank_msopgen_scaffold.py"


def make_env(opgen_mode: str = "port_a3_to_a5") -> AscendCEnv:
    """Minimal AscendCEnv for tests."""
    return AscendCEnv(
        target="a5",
        host="198.51.100.35",
        user="root",
        password="",
        container="npu_dev3",
        cann_path="/data/cann_b103/cann-9.0.0",
        soc_version="Ascend950PR_9579",
        benchmark_root="/root/AscendOpGenAgent",
        local_benchmark="/tmp/bench",
        local_project="/tmp/proj",
        archive_project="test_archive",
        build_archive_enabled=False,
        opgen_mode=opgen_mode,
        port_a3_source="",
        a3_host="",
        a3_user="root",
        a3_container="",
        a3_cann_path="",
        a3_soc_version="",
        a3_workspace="",
    )


def _write_state(ws: Path, reference: dict, multirank: bool) -> None:
    (ws / ".opgen_state.json").write_text(
        json.dumps(
            {
                "opgen_mode": "port_a3_to_a5",
                "multirank": multirank,
                "reference": reference,
            }
        )
    )


def make_a3_live_multirank_workspace(
    tmp_path: Path, op: str = "fused_deep_moe"
) -> Path:
    """A multirank workspace with an a3_live truth binding."""
    ws = tmp_path / "workspace" / op
    ws.mkdir(parents=True)
    _write_state(ws, dict(explicit_a3_live_binding()), True)
    return ws


def make_npubench_workspace(
    tmp_path: Path, op: str = "add", multirank: bool = False
) -> Path:
    """An old-format NPUKernelBench-bound workspace (optionally multirank)."""
    ws = tmp_path / "workspace" / op
    ws.mkdir(parents=True)
    task_root = tmp_path / "npu_benchmark" / "level1"
    task_root.mkdir(parents=True)
    task = task_root / "3_Add.py"
    task.write_text(
        "from pathlib import Path\n"
        "def get_input_groups():\n"
        "    return [Path(__file__).with_suffix('.json').read_bytes()]\n"
    )
    task.with_suffix(".json").write_bytes(b'{"shape": [8]}\n{"shape": [16]}\n')
    reference = stage_npubench_inputs(
        ws, npubench_task=task, npubench_root=task_root
    ).state_block()
    _write_state(ws, reference, multirank)
    return ws


def _build_brief(ws: Path, op: str, **kwargs) -> str:
    return kw_brief.build_worker_brief(
        op=op,
        workspace=ws,
        lane=0,
        spawn_index=1,
        iter_cap_remaining=3,
        env=make_env(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Cold start — structural blocks present
# ---------------------------------------------------------------------------
def test_multirank_cold_start_brief_carries_phase_and_nest_layout(tmp_path):
    """A multirank workspace (a3_live) gets the multirank phase + NEST layout."""
    ws = make_a3_live_multirank_workspace(tmp_path)
    brief = _build_brief(ws, "fused_deep_moe")
    assert _MR_PHASE_TITLE in brief
    assert _MR_LAYOUT_TITLE in brief
    assert _GENERIC_LAYOUT_TITLE not in brief
    # The scaffold entry must be self-sufficient in the brief (not a
    # CLAUDE.md cross-reference that only exists AFTER scaffolding).
    assert _SCAFFORD_SCRIPT in brief
    assert "multirank_runner" in brief


# ---------------------------------------------------------------------------
# Respawn with a directive — structural recipe stays
# ---------------------------------------------------------------------------
def test_multirank_directive_respawn_keeps_structural_recipe(tmp_path):
    """A directive stays a tactical overlay; the multirank recipe rides along."""
    ws = make_a3_live_multirank_workspace(tmp_path)
    directive = "fix the tiling split for ws=4 in the candidate"
    brief = _build_brief(ws, "fused_deep_moe", directive_text=directive)
    assert "# DIRECTIVE FROM PRIOR AGENT" in brief
    assert directive in brief
    assert _MR_PHASE_TITLE in brief
    assert _SCAFFORD_SCRIPT in brief
    assert _MR_LAYOUT_TITLE in brief


# ---------------------------------------------------------------------------
# npubench-bound multirank — the single-card builder must not take over
# ---------------------------------------------------------------------------
def test_multirank_npubench_binding_keeps_multirank_brief(tmp_path):
    """An npubench-bound multirank workspace keeps the multirank brief shape."""
    ws = make_npubench_workspace(tmp_path, multirank=True)
    brief = _build_brief(ws, "add")
    assert _MR_PHASE_TITLE in brief
    assert _SCAFFORD_SCRIPT in brief
    assert _MR_LAYOUT_TITLE in brief
    assert _NPUBENCH_PHASE_TITLE not in brief


# ---------------------------------------------------------------------------
# Regression — single-card npubench still isolated
# ---------------------------------------------------------------------------
def test_single_card_npubench_still_routes_to_npubench_builder(tmp_path):
    """A single-card npubench workspace keeps the npubench worker contract."""
    ws = make_npubench_workspace(tmp_path, multirank=False)
    brief = _build_brief(ws, "add")
    assert _NPUBENCH_PHASE_TITLE in brief
    assert _MR_PHASE_TITLE not in brief
    assert _MR_LAYOUT_TITLE not in brief
