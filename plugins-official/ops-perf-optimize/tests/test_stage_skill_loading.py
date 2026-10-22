# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from pathlib import Path
import re

from stage_skill_contract import STAGE_SKILLS, check_skill_layout

ROOT = Path(__file__).resolve().parents[1]


def test_stage_references_are_reachable_without_orchestrator() -> None:
    check_skill_layout(ROOT / "skills", ROOT / "skills" / "ops-perf-optimize-workflow" / "workflows")


def test_stages_dispatch_to_generic_subagent_and_primary_only_orchestrates() -> None:
    """五个阶段统一派发通用 subagent + 阶段 Skill，不注册命名专家 agent。"""
    assert not (ROOT / "agents").exists(), "agents/ 目录应已移除（阶段走通用 subagent）"
    routes = (ROOT / "skills" / "ops-perf-optimize-workflow" / "workflows/task-prompts.md").read_text()
    contract = (
        ROOT / "skills/ops-perf-optimize-workflow/references/workflow-contract.md"
    ).read_text()
    assert "通用 subagent" in contract
    for role, skill in STAGE_SKILLS.items():
        row = next(
            line for line in routes.splitlines() if line.startswith(f"| `{role}` |")
        )
        assert row.split("|")[-2].strip() == f"通用 subagent + `{skill}`", row
    primary = (ROOT / "AGENTS.md").read_text().split("---", 2)[1]
    assert set(re.findall(r"^  - ([\w-]+)$", primary, re.M)) == {
        "ops-perf-optimize-workflow"
    }


def test_shared_collection_protocol_has_one_owner() -> None:
    skills = ROOT / "skills"
    owned = []
    for name in (
        *STAGE_SKILLS.values(),
        "ops-perf-acceptance-criteria",
        "ops-perf-optimize-workflow",
    ):
        owned.append(skills / name)
    definitions = []
    for root in owned:
        for path in root.rglob("*.md"):
            if "10 组 `warmup → target`" in path.read_text():
                definitions.append(path)
    assert definitions == [
        skills / "ops-perf-acceptance-criteria/references/performance-collection.md"
    ]
    for filename in (
        "analysis",
        "baseline",
        "generation",
        "implementation",
        "integration",
        "preparation",
    ):
        template = (ROOT / "skills" / "ops-perf-optimize-workflow" / "workflows/prompts" / f"{filename}.md").read_text()
        assert "WORKFLOW_ROOT:" in template
