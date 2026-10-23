# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Dispatch hygiene contract: role template first, absolute envelope paths.

Pinned against two dispatch failures observed in a production run: the
dispatcher skipped the per-role template (role-specific deliverables were
dropped) and subagents built workflow-script paths relative to their working
directory. The rules are deliberately scoped — they must not forbid ordinary
same-directory relative operations or pin knowledge-query CLI specifics.
"""

from pathlib import Path

from stage_skill_contract import STAGE_SKILLS

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "skills" / "ops-perf-optimize-workflow"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dispatcher_reads_role_template_before_dispatch() -> None:
    routes = read(WORKFLOW / "workflows/task-prompts.md")
    assert "## 派发前检查" in routes
    assert "workflows/prompts/<role>.md" in routes
    assert "派发准备未完成" in routes

    orchestration = read(WORKFLOW / "SKILL.md")
    assert "派发前检查" in orchestration
    assert "workflows/prompts/<role>.md" in orchestration

    contract = read(WORKFLOW / "references/workflow-contract.md")
    assert "workflows/prompts/<role>.md" in contract
    assert "逐字段填写信封" in contract


def test_envelope_paths_are_absolute_and_placeholders_are_not_env_vars() -> None:
    routes = read(WORKFLOW / "workflows/task-prompts.md")
    assert "不是环境变量" in routes
    assert "工作流脚本" in routes

    contract = read(WORKFLOW / "references/workflow-contract.md")
    assert "占位符而非环境变量" in contract
    assert "常规相对路径操作不受影响" in contract

    for skill in STAGE_SKILLS.values():
        entry = read(ROOT / "skills" / skill / "SKILL.md")
        assert "信封中的路径均为解析后的绝对路径" in entry, skill
        assert "当作环境变量" in entry, skill
        # The rule must stay scoped: ordinary relative operations stay allowed.
        assert "不受此限制" in entry, skill


def test_path_rule_is_scoped_not_a_general_relative_path_ban() -> None:
    """绝对路径条款只覆盖信封与工作流脚本，不得升级成全面相对路径禁令。"""
    routes = read(WORKFLOW / "workflows/task-prompts.md")
    assert "常规相对路径操作不受此限制" in routes
    for name in ("ops-perf-analysis", "ops-perf-implementation"):
        entry = read(ROOT / "skills" / name / "SKILL.md")
        assert "不得按当前工作目录拼接相对路径" not in entry, name


def test_knowledge_query_note_defers_to_its_own_skill() -> None:
    """不把 knowledge-query 的 CLI 细节钉死在本插件文案里。"""
    for skill in ("ops-perf-analysis", "ops-perf-implementation"):
        entry = read(ROOT / "skills" / skill / "SKILL.md")
        assert "先读其 SKILL 的参数表" in entry, skill
        assert "`--json`" in entry, skill
        assert "--limit" not in entry, skill
        assert "--platform" not in entry, skill
