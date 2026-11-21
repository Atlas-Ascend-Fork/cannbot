# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

import json
from pathlib import Path

from ops_perf_test_paths import ANALYSIS, CONTRACT, IMPL, ROOT, WRAPPER


def read(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    references = {
        "ops-perf-analysis": "references/analysis-execution.md",
        "ops-perf-implementation": "references/selection-and-final.md",
    }
    if path.parent.name in references:
        text += (path.parent / references[path.parent.name]).read_text()
    return text


def test_reference_skills_are_available_to_analysis() -> None:
    # 阶段走通用 subagent + 阶段 Skill：共享策略 Skill 在阶段正文路由，不再做 frontmatter 声明。
    analysis = read(ANALYSIS)
    # Stage skills declare no `skills:` frontmatter; reference resources are
    # available in the body and selected for the current analysis task.
    assert "ascendc-perf-optimize" in analysis
    assert "ascendc-performance-best-practices" in analysis
    assert "ops-theoretical-performance-estimation" in analysis
    assert "ops-opmodel-toolkit" in analysis
    # 策略推导保留在 analysis；implementation 仅在 DSL 路由用其做候选诊断与流水/tiling 复核；
    # 主编排入口不加载该策略 Skill。
    assert "ascendc-perf-optimize" in read(IMPL)
    assert "ascendc-perf-optimize" not in read(WRAPPER)


def test_dsl_implementation_skill_is_installed_and_dispatched() -> None:
    sources = json.loads(
        (ROOT / "plugin-sources.json").read_text(encoding="utf-8")
    )["skills"]
    assert "ops/cannbot-dsl-best-practice" in sources

    prompt = read(
        ROOT
        / "skills"
        / "ops-perf-optimize-workflow"
        / "workflows"
        / "prompts"
        / "implementation.md"
    )
    assert "BACKEND=cannbot_dsl" in prompt
    assert "CONDITIONAL_SKILLS" in prompt
    assert "cannbot-dsl-best-practice" in prompt


def test_selected_strategy_flow_preserves_its_four_steps() -> None:
    analysis = read(ANALYSIS)
    assert "`ascendc-perf-optimize` 的 4 步流程" in analysis
    assert "Step 1 Tiling 理论建模必选" in analysis
    assert "理想 tiling data" in analysis
    assert "Step 4 单核流水 bound 诊断结论并入逐 case bound 证据" in analysis
    assert (
        "tiling 修正建议和优化策略直接映射为方案与实施契约 required features"
        in analysis
    )


def test_mc2_step2_evidence_is_collected_upstream_and_consumed_read_only() -> None:
    contract = read(
        ROOT / "skills/ops-perf-acceptance-criteria/references/performance-collection.md"
    )
    analysis = read(ANALYSIS)
    # Collection stage owns the source-touching MC2 evidence.
    assert "TilingData 打印证据（baseM/baseN/baseK/usedCoreNum）" in contract
    assert "tileCnt=1 隔离测试证据（T_comm/T_compute/R 值）" in contract
    assert "登记进采集 manifest" in contract
    assert "缺失时退回采集阶段补采" in contract
    # The read-only analysis role only consumes registered evidence.
    assert "只消费基线采集阶段已登记的 TilingData 与隔离测试证据" in analysis
    assert "不得修改源码自行补采" in analysis


def test_strategy_flow_does_not_widen_analysis_boundaries() -> None:
    skill = ANALYSIS.read_text(encoding="utf-8")
    analysis = read(ANALYSIS.parent / "references/analysis-execution.md")
    contract = read(CONTRACT)
    # The strategy flow supplements domain method; the contract stays the single
    # source of truth for stages, routing and acceptance.
    assert "角色文件只补充领域执行方法" in contract or "唯一工作流真源" in contract
    assert "](references/analysis-execution.md)" in skill
    assert "准备性能基线" in skill and "复用或采集当前基线" in skill
    assert "只读边界约束采集完成后的分析推导" in analysis
    assert "不得重选 case、重采性能、编译 demo 或修改源码" in analysis
    assert "冻结基线不变" in analysis
