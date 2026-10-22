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

from ops_perf_test_paths import ANALYSIS, CONTRACT, IMPL, ROOT, WRAPPER



def read(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    references = {
        "ops-perf-analysis": "references/analysis-execution.md",
        "ops-perf-implementation": "references/implementation-execution.md",
    }
    if path.parent.name in references:
        text += (path.parent / references[path.parent.name]).read_text()
    return text


def test_strategy_flow_skill_is_a_required_analysis_dependency() -> None:
    # 阶段走通用 subagent + 阶段 Skill：共享策略 Skill 在阶段正文路由，不再做 frontmatter 声明。
    analysis = read(ANALYSIS)
    body = analysis.split("---", 2)[2]
    assert "ascendc-perf-optimize" in body
    assert "ascendc-performance-best-practices" in body
    # The strategy skill stays analysis-only: no other role or entry point loads it.
    for path in (IMPL, WRAPPER):
        assert "ascendc-perf-optimize" not in read(path)


def test_analysis_standards_execute_the_four_step_strategy_flow() -> None:
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
    analysis = read(ANALYSIS)
    contract = read(CONTRACT)
    # The strategy flow supplements domain method; the contract stays the single
    # source of truth for stages, routing and acceptance.
    assert "角色文件只补充领域执行方法" in contract or "唯一工作流真源" in contract
    assert "不得重选 case、重采性能" in analysis
    assert "分析推导不得重采、重选 case 或修改基线" in read(
        ROOT / "skills/ops-perf-analysis/SKILL.md"
    )
