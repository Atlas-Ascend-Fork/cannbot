# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""cannbot-knowledge wiring: install-time dependency and graceful stage references.

Install clones the knowledge base and the knowledge-query Skill; the dispatch
envelope carries KB_ROOT; analysis cites kb_cards per scheme and implementation
consumes them, both degrading to kb_unavailable without blocking the workflow.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
CONTRACT = (
    ROOT
    / "skills"
    / "ops-perf-optimize-workflow"
    / "references"
    / "workflow-contract.md"
)
ENTRY_SKILL = ROOT / "skills" / "ops-perf-optimize-workflow" / "SKILL.md"
ANALYSIS = ROOT / "skills" / "ops-perf-analysis" / "SKILL.md"
ANALYSIS_EXEC = (
    ROOT / "skills" / "ops-perf-analysis" / "references" / "analysis-execution.md"
)
IMPL = ROOT / "skills" / "ops-perf-implementation" / "SKILL.md"
IMPL_EXEC = (
    ROOT
    / "skills"
    / "ops-perf-implementation"
    / "references"
    / "implementation-execution.md"
)
WRAPPER = ROOT / "AGENTS.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_install_declares_cannbot_knowledge_and_the_query_skill() -> None:
    dependencies = json.loads(read(ROOT / "plugin-install.json"))["dependencies"]
    knowledge = [dep for dep in dependencies if dep["name"] == "cannbot-knowledge"]
    assert knowledge and knowledge[0]["repository"].endswith("cannbot-knowledge.git")
    # The knowledge base needs no project-root exposure: stages read it under
    # .cannbot/dependencies, unlike the asc-devkit/cann-samples reference repos.
    assert "expose" not in knowledge[0]
    sources = json.loads(read(ROOT / "plugin-sources.json"))["skills"]
    assert "plugins-community/cannbot-knowledge/skills/knowledge-query" in sources
    manifest = json.loads(read(ROOT / ".claude-plugin" / "plugin.json"))
    assert manifest["dependencies"] == [
        "ops-perf-optimize-skills",
        "ops-perf-optimize-kb-skills",
    ]


def test_marketplace_bundle_covers_exactly_the_declared_skills() -> None:
    marketplace = json.loads(read(REPO / ".claude-plugin" / "marketplace.json"))
    entries = {entry["name"]: entry for entry in marketplace["plugins"]}
    manifest = json.loads(read(ROOT / ".claude-plugin" / "plugin.json"))
    bundle = entries["ops-perf-optimize-kb-skills"]
    assert bundle["category"] == "skills"
    assert bundle["source"]["path"] == "plugins-community/cannbot-knowledge/skills"
    assert bundle["skills"] == ["./knowledge-query"]
    assert entries["ops-perf-optimize"]["dependencies"] == manifest["dependencies"]


def test_dispatch_envelope_carries_kb_root() -> None:
    prompts = read(ROOT / "skills" / "ops-perf-optimize-workflow" / "workflows" / "task-prompts.md")
    assert (
        "KB_ROOT: <cannbot-knowledge knowledge root for analysis/implementation, or absent>"
        in prompts
    )
    assert "按编排契约解析一次后全程复用" in prompts
    # Every role template mirrors the generic envelope field set, so the main
    # agent cannot drop KB_ROOT when assembling a stage dispatch.
    for filename in (
        "analysis",
        "baseline",
        "generation",
        "implementation",
        "integration",
        "preparation",
    ):
        assert "KB_ROOT:" in read(
            ROOT / "skills" / "ops-perf-optimize-workflow" / "workflows" / "prompts" / f"{filename}.md"
        ), (
            filename
        )


def test_contract_defines_bootstrap_order_and_non_blocking_degradation() -> None:
    contract = read(CONTRACT)
    assert "环境变量 `CANNBOT_KNOWLEDGE_ROOT`" in contract
    assert ".cannbot/dependencies/*/cannbot-knowledge/knowledge" in contract
    assert "`knowledge-query` Skill 的 `discover`" in contract
    assert "KB_ROOT（或省略）" in contract
    assert "信封省略 `KB_ROOT`" in contract
    assert "kb_unavailable" in contract
    assert "不降低精度与性能验收要求" in contract
    entry = read(ENTRY_SKILL)
    assert "解析一次 `KB_ROOT`" in entry
    assert "kb_unavailable: true" in entry


def test_analysis_designs_schemes_on_cited_kb_cards() -> None:
    analysis = read(ANALYSIS)
    assert "`knowledge-query`" in analysis
    assert "`KB_ROOT`" in analysis
    assert "kb_unavailable" in analysis
    execution = read(ANALYSIS_EXEC)
    assert "信封 `KB_ROOT`" in execution
    assert (
        '`preflight --task "<算子名> <族> <bound 结论与关键指标> 优化方案>"`'
        in execution
    )
    assert '`--knowledge-root "$KB_ROOT"`' in execution
    assert "read_first" in execution
    # Retrieved cards are hypothesis-level evidence, not a replacement for the
    # analysis standards or the shared Skill routes.
    assert "不替代本文件的分析标准和共享 Skill 路由" in execution
    assert "`kb_cards` 列出方案引用的 doc-id" in execution
    assert "不虚构卡片" in execution
    assert "知识卡引用" in execution


def test_implementation_consumes_scheme_cards_before_coding() -> None:
    implementation = read(IMPL)
    assert "`kb_cards`" in implementation
    assert "`knowledge-query`" in implementation
    assert "kb_unavailable" in implementation
    execution = read(IMPL_EXEC)
    assert "信封 `KB_ROOT` 存在时" in execution
    assert "编码前先消费所选方案" in execution
    assert "$KB_ROOT/<doc-id>" in execution
    # The KB complements but never replaces API verification.
    assert "知识库 → `ascendc-docs-search` → 本机 SDK" in execution
    assert "不替代 docs-search 与 SDK 核验" in execution
    assert "顶层 `kb_cards`" in execution
    assert "kb_unavailable" in execution


def test_wrapper_stays_thin_and_carries_no_kb_bootstrap() -> None:
    wrapper = read(WRAPPER)
    assert "CANNBOT_KNOWLEDGE_ROOT" not in wrapper
    assert "kb_cards" not in wrapper
