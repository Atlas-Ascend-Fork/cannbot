# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Multirank brief KB wiring tests.

Two audit findings this file pins:
1. ko_brief_phase_block was dead code — `_optimizer_phase_block` accepted
   the plugin and never called it, so multirank optimizers got the generic
   single-card brief (kernel/ + deploy_to_npu_lane.sh — wrong entries for
   the nest layout). Mirrors the pp-side FIX-5 regression guard.
2. Three brief-referenced KB paths did not resolve (bare prefixes missing
   `target/ascendc/`, and an official CANN doc that lived only in the
   sibling a5_ops checkout). Every backticked path in the multirank kw/pp/
   ko overrides must now exist under its declared root (kb/ for plugin KB,
   the plugin root for docs/references official docs).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ORCH_DIR = _HERE.parent.parent  # src/scripts/orchestrator/
if str(_ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(_ORCH_DIR))

import ko_brief  # noqa: E402
from plugins.multirank import get_plugin_instance  # noqa: E402

_PLUGIN_ROOT = Path(__file__).resolve().parents[6]  # ascendc-port-orchestrator/
_ENGINE_ROOT = _PLUGIN_ROOT / "engine"
assert (_ENGINE_ROOT / "src").is_dir(), _ENGINE_ROOT
_KB_ROOT = _PLUGIN_ROOT / "kb"


# ---------------------------------------------------------------------------
# 1. ko override wiring (was dead code)
# ---------------------------------------------------------------------------
class _OverridePlugin:
    @staticmethod
    def ko_brief_phase_block(*, handoff_str: str = "", directive_str: str = ""):
        return "# multirank ko override"


class _DefaultPlugin:
    @staticmethod
    def ko_brief_phase_block(*, handoff_str: str = "", directive_str: str = ""):
        return None  # BasePlugin default


def test_ko_phase_block_plugin_override_wins():
    out = getattr(ko_brief, "_optimizer_phase_block")(
        None, None, 5, plugin=_OverridePlugin()
    )
    assert out == "# multirank ko override"


def test_ko_phase_block_default_plugin_is_generic(tmp_path):
    """None-default plugin (and plugin=None) keep the generic single-card

    brief — byte-identical between the two.
    """
    via_default = getattr(ko_brief, "_optimizer_phase_block")(
        None, None, 5, plugin=_DefaultPlugin(), workspace=tmp_path
    )
    via_none = getattr(ko_brief, "_optimizer_phase_block")(
        None, None, 5, plugin=None, workspace=tmp_path
    )
    assert via_default == via_none
    assert "aog-kernel-optimizer" in via_default


def test_multirank_ko_override_reaches_optimizer_brief():
    """The production multirank plugin's ko override flows through the

    wired hook (nest-layout entries, not the single-card kernel/ path).
    """
    out = getattr(ko_brief, "_optimizer_phase_block")(
        None, None, 5, plugin=get_plugin_instance()
    )
    assert "aog-kernel-optimizer — multirank backend" in out
    assert "run.py verify" in out
    assert "deploy_to_npu_lane.sh" not in out  # single-card entry must be gone


# ---------------------------------------------------------------------------
# 2. brief-referenced paths must exist under their declared root
# ---------------------------------------------------------------------------
def _referenced_paths(text: str) -> tuple[list, list]:
    """(kb_root_paths, plugin_root_paths) backticked in a brief text."""
    kb_paths = []
    for m in re.finditer(r"`(target/ascendc/[\w./-]+?\.md)`", text):
        kb_paths.append(m.group(1))
    doc_paths = []
    for m in re.finditer(
        r"`(src/scripts/orchestrator/plugins/multirank/docs/[\w./-]+?\.md)`", text
    ):
        doc_paths.append(m.group(1))
    return kb_paths, doc_paths


def test_multirank_brief_referenced_paths_resolve():
    plug = get_plugin_instance()
    texts = [
        plug.kw_brief_phase_block(op="some_op"),
        plug.pp_brief_phase_block(),
        plug.ko_brief_phase_block(),
        plug.kernel_author_constraints_block() or "",
    ]
    all_kb, all_docs = [], []
    for t in texts:
        kb, docs = _referenced_paths(t)
        all_kb += kb
        all_docs += docs
    assert all_docs  # plugin docs are referenced; kb/ refs are OKF-era and now optional
    assert not all_kb or all((_KB_ROOT / rel).is_file() for rel in all_kb)
    for rel in all_kb:
        assert (_KB_ROOT / rel).is_file(), f"kb/ path not found: {rel}"
    for rel in all_docs:
        assert (_ENGINE_ROOT / rel).is_file(), f"plugin docs path not found: {rel}"


# ---------------------------------------------------------------------------
# 3. migration knowledge reuse (route A: shared into the multirank kw brief)
# ---------------------------------------------------------------------------
def test_kw_brief_carries_migration_knowledge(tmp_path):
    """The single-card migration knowledge reaches the multirank worker:

    the migration-level guide routing (level decision + MUST-READ guides),
    the L-tier OL/EC/PB anchor lists, and the cube-class routing.
    """
    import json

    ws = tmp_path / "some_op"
    ws.mkdir()
    (ws / "op_classification.json").write_text(
        json.dumps({"op_class_tags": ["multirank_fusion"]})
    )
    brief = get_plugin_instance().kw_brief_phase_block(op="some_op", workspace=ws)
    # migration-level routing: the level decision + at least one guide
    assert (
        "MIGRATION LEVEL" in brief
    )  # level routing present (guides resolve via knowledge-query)
    # L-tier anchors (same IDs the single-card Phase A.1.5 cites)
    assert "L1: OL-142, EC-47" in brief
    assert "OL-150, OL-151" in brief  # L3 set present too
    # cube-class routing directive (knowledge lives in OKF cards; the
    # directive itself is inline text)
    assert "AIC(cube)/AIV(vector)" in brief
