# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    references = {
        "ops-perf-analysis": "references/analysis-execution.md",
        "ops-perf-implementation": "references/implementation-execution.md",
    }
    if path.parent.name in references:
        text += (path.parent / references[path.parent.name]).read_text()
    return text


def test_workflow_has_one_contract_and_small_dispatch_envelope() -> None:
    skill = read("skills/ops-perf-optimize-workflow/SKILL.md")
    contract = read("skills/ops-perf-optimize-workflow/references/workflow-contract.md")
    prompts = read("workflows/task-prompts.md")
    assert "唯一工作流真源" in contract
    assert "阶段、派发、恢复和报告的唯一工作流真源" in skill
    for field in (
        "PLUGIN_ROOT:",
        "ROLE:",
        "TASK_KIND:",
        "RUN_MANIFEST:",
        "WORKFLOW_STATE:",
        "TARGET_SOCS:",
        "ROUND:",
        "CODE_DIR:",
        "INPUT_ARTIFACTS:",
        "OUTPUT_ARTIFACTS:",
        "ACCEPTANCE:",
        "CONDITIONAL_SKILLS:",
    ):
        assert "通用信封的字段定义以该稳定派发入口为准" in contract
        assert field in prompts
    assert "必须保留的稳定派发入口" in prompts
    assert "不复制或改写业务规则" in prompts
    assert "只读取一份角色模板" in prompts
    assert len(prompts.splitlines()) < 80
    assert not (ROOT / "workflows" / "resume-and-lessons.md").exists()


def test_dispatch_templates_cover_every_role_and_mode_specific_interface() -> None:
    prompts = read("workflows/task-prompts.md")
    role_templates = {
        "preparation": "preparation.md",
        "baseline": "baseline.md",
        "analysis": "analysis.md",
        "implementation": "implementation.md",
        "integration": "integration.md",
    }
    loaded = {}
    for role, filename in role_templates.items():
        relative = f"workflows/prompts/{filename}"
        assert f"prompts/{filename}" in prompts
        loaded[role] = read(relative)
        assert f"ROLE: {role}" in loaded.get(role, "")

    assert "TASK_KIND: extract-single-operator" in loaded.get("preparation", "")
    assert "通用 subagent + `ops-perf-preparation`" in prompts
    assert "performance-full-cases.csv" in read("workflows/prompts/generation.md")
    assert "generalization-full-cases.csv" in read("workflows/prompts/generation.md")
    assert "performance-tuning-cases.csv" in loaded.get("analysis", "")
    assert "generalization-tuning-cases.csv" in loaded.get("analysis", "")
    assert "MC²/多 rank" in loaded.get("analysis", "")
    assert "implementation-contract-<scheme_id>.json" in loaded.get("implementation", "")
    assert "scheme-conformance-gate.json" in loaded.get("implementation", "")
    assert "public API/constraints/dtypes unchanged" in loaded.get("implementation", "")
    assert "integration-safety-gate.json" in loaded.get("integration", "")
    for token in (
        "optimized-involved-cases.csv",
        "uninvolved-cases-verification.md",
        "5%",
        "至少 10",
        "20%",
    ):
        assert token in loaded.get("integration", "")


def test_vf_discovery_readiness_and_real_build_gate_are_preserved() -> None:
    analysis = read("skills/ops-perf-analysis/SKILL.md")
    impl = read("skills/ops-perf-implementation/SKILL.md")
    contract = read("skills/ops-perf-optimize-workflow/references/workflow-contract.md")
    combined = "\n".join((analysis, impl, contract))
    for token in (
        "reference/common/arch35/regbase/catalog.json",
        "vf_preflight.py --strict",
        "readiness",
        "example_build_contract",
        "annotated_excerpt",
        "reference_only",
    ):
        assert token in combined
    for token in (
        "reference/common/arch35/regbase/catalog.json",
        "vf_preflight.py --strict",
        "readiness",
        "example_build_contract",
    ):
        assert token in analysis or token in contract
        assert token in impl or token in contract
    assert "真实候选翻译单元才是门禁" in impl
    assert "真实候选构建才是门禁" in read(
        "skills/ops-perf-implementation/references/engineering-constraints.md"
    )
    assert "--expect-vf" in impl
    assert "--expect-cast" in impl
    assert "static constexpr" in impl


def test_deterministic_rope_quant_and_family_routing_remain_explicit() -> None:
    analysis = read("skills/ops-perf-analysis/SKILL.md")
    impl = read("skills/ops-perf-implementation/SKILL.md")
    contract = read("skills/ops-perf-optimize-workflow/references/workflow-contract.md")
    combined = "\n".join((analysis, impl, contract))
    for token in (
        "paired-segment-rotate",
        "quant_vf_route",
        "shared-exponent-pack",
        "two-pass-amax-cast",
        "no_matching_vf_example",
        "Gather",
        "Scatter",
        "SIMT",
    ):
        assert token in combined
    assert "算子名不能锁定单一族" in analysis
    assert "只有族级终选仍使用 SIMT" in analysis


def test_exact_implementation_contract_and_conformance_gate_are_mechanical() -> None:
    analysis = read("skills/ops-perf-analysis/SKILL.md")
    impl = read("skills/ops-perf-implementation/SKILL.md")
    contract = read("skills/ops-perf-optimize-workflow/references/workflow-contract.md")
    for token in (
        '"implementation_mode": "exact"',
        '"substitution_policy": "forbidden"',
        '"target_socs"',
        '"public_contract": "unchanged"',
        '"non_target_socs": "unchanged"',
        '"required_features"',
    ):
        assert token in analysis
    assert "validate_implementation_conformance.py" in impl
    assert "scheme-conformance.json" in impl
    assert "scheme-conformance-gate.json" in impl
    assert "dead-code-audit.md" in impl
    assert "不得带 `UNKNOWN` 交付" in impl
    assert "任何组合代码都是新候选" in read(
        "skills/ops-perf-implementation/references/selection-and-final.md"
    )


def test_soc_isolation_and_public_contract_span_workflow_agents_skills() -> None:
    skill = read("skills/ops-perf-optimize-workflow/SKILL.md")
    contract = read("skills/ops-perf-optimize-workflow/references/workflow-contract.md")
    analysis = read("skills/ops-perf-analysis/SKILL.md")
    impl = read("skills/ops-perf-implementation/SKILL.md")
    integrate = read("skills/ops-perf-postprocess/references/writeback.md")
    mechanics = read(
        "skills/ops-perf-postprocess/references/integration-mechanics.md"
    )
    integration_prompt = read("workflows/prompts/integration.md")
    combined = "\n".join(
        (skill, contract, analysis, impl, integrate, mechanics, integration_prompt)
    )
    for token in (
        "TARGET_SOCS",
        "SUPPORTED_SOCS",
        "SOC_COMPATIBILITY_MATRIX.md",
        "target guard",
        "non-target fallback",
        "validate_integration_safety.py",
        "integration-safety-gate.json",
        "op_api",
        "支持 dtype",
    ):
        assert token in combined
    assert "验证范围不是支持范围" in integrate
    assert "共享实现先复制后单独路由" in skill
    assert "public API/constraints/dtypes have zero diff" in integration_prompt


def test_api_existence_is_not_confused_with_build_visibility() -> None:
    impl = read("skills/ops-perf-implementation/SKILL.md")
    contract = read("skills/ops-perf-optimize-workflow/references/workflow-contract.md")
    for text in (
        impl,
        read("skills/ops-perf-implementation/references/engineering-constraints.md"),
    ):
        assert "api_missing" in text
        assert "host" in text
        assert "device" in text
        assert "辅助 probe" in text
    assert "build_contract_mismatch" in impl
    assert "host_pass_leakage" in impl
    assert "xasc_combined" in impl
    assert "__local_mem__" in impl


def test_case_freezing_is_deterministic_and_not_agent_work() -> None:
    skill = read("skills/ops-perf-optimize-workflow/SKILL.md")
    contract = read("skills/ops-perf-optimize-workflow/references/workflow-contract.md")
    case_designer = read(
        "skills/ops-perf-baseline-evaluate/references/case-generation.md"
    )
    assert "prepare_case_sets.py" in skill
    assert "optimization-request.json" in skill
    assert "validate-request" in skill
    freezing = read("skills/ops-perf-baseline-evaluate/references/input-freezing.md")
    assert "coverage-v1" in freezing
    assert "禁止默认取前 N" in freezing
    assert "existing" in case_designer and "reuse_performance" in case_designer
    assert "不得另派用例 Agent" in case_designer
    assert (
        "只处理 standard 的 `FUNCTIONAL_MODE=generate`，或 generalization 的泛化用例生成"
        in case_designer
    )


def test_reviewed_mode_analysis_and_acceptance_guards_remain_explicit() -> None:
    skill = read("skills/ops-perf-optimize-workflow/SKILL.md")
    contract = read("skills/ops-perf-optimize-workflow/references/workflow-contract.md")
    analysis = read("skills/ops-perf-analysis/SKILL.md")
    impl = read("skills/ops-perf-implementation/SKILL.md")
    case_designer = read(
        "skills/ops-perf-baseline-evaluate/references/case-generation.md"
    )
    sources = read("plugin-sources.json")

    for text in (skill, case_designer):
        assert "| 项目 | `standard`" in text
        assert "| `generalization` |" in text
    assert "不得被删除或退化为 `standard`" in skill
    assert "完整覆盖两种模式" in case_designer

    for text in (
        read("skills/ops-perf-analysis/references/analysis-execution.md"),
        analysis,
    ):
        assert "《性能分析报告》" in text
        assert "MC²/多 rank" in text
        assert "Broadcast" in text and "Gather" in text and "Scatter" in text
    assert "固定按以下顺序执行" in analysis
    assert "ascendc-mc2-best-practice" in analysis
    assert "ascendc-mc2-best-practice" in sources
    assert "ops/ascendc-mc2-best-practice" in sources

    assert "功能验收不是可删除的“提速步骤”" in impl
    assert "## 核心约束" in impl
    assert "不得通过减少 case、跳过门禁或缩短精度诊断换取速度" in impl
