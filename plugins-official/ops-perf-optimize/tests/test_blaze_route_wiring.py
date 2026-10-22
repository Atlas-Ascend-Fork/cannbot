# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Blaze route wiring: knowledge-base routing entry plus plugin installation.

The matmul family in ascendc-performance-best-practices routes to the Blaze
skills; the plugin installs both skills so the dispatch envelope's
CONDITIONAL_SKILLS mechanism can load them on demand. Roles never preload the
Blaze skills as base dependencies.
"""

import json
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
OPS_ROOT = PLUGIN_ROOT.parents[1] / "vendor" / "cannbot-skills" / "ops"
PERF_BP = OPS_ROOT / "ascendc-performance-best-practices"
BLAZE_SKILL = OPS_ROOT / "ascendc-blaze-best-practice" / "SKILL.md"
MIGRATION_SKILL = OPS_ROOT / "ascendc-blaze-migration" / "SKILL.md"
MATMUL_GUIDE = PERF_BP / "reference" / "matmul" / "arch35" / "guide.md"
BLAZE_DESIGN = PERF_BP / "reference" / "matmul" / "arch35" / "blaze_design.md"
SKILL_MD = PERF_BP / "SKILL.md"
CONV_GUIDE = PERF_BP / "reference" / "conv" / "guide.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_blaze_skills_exist_in_shared_ops_tree() -> None:
    assert BLAZE_SKILL.is_file()
    assert MIGRATION_SKILL.is_file()


def test_matmul_family_routes_to_blaze() -> None:
    guide = read(MATMUL_GUIDE)
    design = read(BLAZE_DESIGN)
    skill = read(SKILL_MD)

    assert "blaze_design.md" in guide
    assert "先完成 Blaze 路线判定" in guide
    for route in ("blaze_native", "blaze_custom", "blaze_migration", "unsupported"):
        assert route in design
        assert route in skill or route in guide
    # Deterministic routing rule lives in the skill entry point.
    assert "MatMul Blaze 确定性路由" in skill
    assert "ascendc-blaze-best-practice" in skill
    assert "ascendc-blaze-migration" in skill
    assert "`unsupported_points` 证据" in skill


def test_blaze_design_defers_execution_to_the_blaze_skill() -> None:
    design = read(BLAZE_DESIGN)
    # Routing entry only; the Blaze workflow is not duplicated here.
    assert "不在本文复述" in design
    assert "../../../ascendc-blaze-best-practice/SKILL.md" in design
    assert "../../../ascendc-blaze-migration/SKILL.md" in design
    # Evidence discipline: read-only ops-tensor with commit identity.
    assert "只读" in design
    assert "commit SHA" in design
    assert "environment_blocked" in design
    assert "abi_crosswalk" in design


def test_conv_family_stays_out_of_blaze_routing() -> None:
    assert "blaze" not in read(CONV_GUIDE).lower()


def test_plugin_installs_blaze_skills_for_conditional_dispatch() -> None:
    sources = json.loads(read(PLUGIN_ROOT / "plugin-sources.json"))
    manifest = json.loads(read(PLUGIN_ROOT / ".claude-plugin" / "plugin.json"))
    for name in ("ascendc-blaze-best-practice", "ascendc-blaze-migration"):
        assert f"ops/{name}" in sources["skills"]
    # Marketplace 安装由 ops-perf-optimize-skills 依赖包提供两个 Blaze skill。
    assert "ops-perf-optimize-skills" in manifest["dependencies"]


def test_roles_do_not_preload_blaze_skills() -> None:
    for agent in sorted((PLUGIN_ROOT / "agents").glob("*.md")):
        frontmatter = read(agent).split("---", 2)[1]
        assert "ascendc-blaze" not in frontmatter, agent
    wrapper_frontmatter = read(PLUGIN_ROOT / "AGENTS.md").split("---", 2)[1]
    assert "ascendc-blaze" not in wrapper_frontmatter
