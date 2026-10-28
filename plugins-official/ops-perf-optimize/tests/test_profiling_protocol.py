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


SKILL = ROOT / "skills" / "ops-perf-optimize-workflow" / "SKILL.md"
HOOK = ROOT / "hooks" / "session-start-ops-perf-optimize"
QUICKSTART = ROOT / "quickstart.md"


def read(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    references = {
        "ops-perf-analysis": "references/analysis-execution.md",
        "ops-perf-implementation": "references/implementation-execution.md",
    }
    if path.parent.name in references:
        text += (path.parent / references[path.parent.name]).read_text()
    return text


def test_application_profiling_protocol_is_single_source_and_identity_bound() -> None:
    contract = read(
        ROOT / "skills/ops-perf-acceptance-criteria/references/performance-collection.md"
    )
    analysis = read(ANALYSIS)
    for token in (
        "profiler=msprof",
        "aic_metrics=PipeUtilization",
        "10 组 `warmup → target`",
        "schema v3",
        "expected/parsed/mapped relevant launches",
        "全部 kernel",
        "源码、加载二进制、case、Device、CANN、频率和 warmup 身份",
        "ArgMax",
        "Max",
    ):
        assert token in contract
    assert "只使用 `mapped_launches[]`" in analysis
    assert "MC²" in contract and "msprof op" in contract
    assert "不套用 application 协议" in analysis
    assert "身份与覆盖完全相同时复用已有证据" in contract


def test_runtime_artifact_model_has_three_truth_layers_and_no_duplicate_summaries() -> (
    None
):
    skill = read(SKILL)
    contract = read(CONTRACT)
    for token in (
        "optimization-request.json",
        "run-manifest.json",
        "workflow-state.json",
        "性能调优报告.md",
    ):
        assert token in skill
        assert token in contract
    assert (
        "每次状态提交" not in skill
    )  # wording stays operational, not implementation chatter
    assert "持续更新" in skill
    assert "一份 `analysis/roundN/analysis.md`" in skill
    assert "同一事实只写一次" in contract

    prompts = read(ROOT / "skills" / "ops-perf-optimize-workflow" / "workflows" / "task-prompts.md")
    assert "必须保留的稳定派发入口" in prompts
    assert "唯一工作流真源" in prompts
    assert not (ROOT / "skills" / "ops-perf-optimize-workflow" / "workflows" / "resume-and-lessons.md").exists()
    assert "不另建进度 JSON、双份多轮汇总或逐轮同名报告" in contract
    assert "不拆成三段保存点或重复的方案报告" in read(
        ROOT / "skills/ops-perf-analysis/references/analysis-execution.md"
    )


def test_precision_redlines_are_explicit_in_entry_contract_and_implementation_role() -> (
    None
):
    documents = [read(SKILL), read(CONTRACT), read(IMPL)]
    for text in documents:
        assert "known_baseline_failure" in text
        assert "conditional_pass" in text
        assert "不" in text and "终止" in text
        assert "固定持续执行" in text
        assert "persistent" not in text
        assert "interactive" not in text
        assert "token" in text
    contract = documents[1]
    assert "新失败或恶化只淘汰/修复该候选" in read(SKILL)
    assert "其他候选和当前基线继续" in contract
    assert "未证实的失败" in read(SKILL)
    assert "精度诊断没有自动停止预算" in contract
    assert "命令级防挂死 watchdog" in contract


def test_analysis_is_one_atomic_reviewable_result() -> None:
    contract = read(CONTRACT)
    analysis = read(ANALYSIS)
    assert "analysis/roundN/analysis.md" in contract
    assert "analysis/roundN/analysis.md" in analysis
    assert "每个冻结 case 必须恰好出现" in analysis
    assert "implementation-contract-<scheme_id>.json" in analysis
    assert '"implementation_mode": "exact"' in analysis
    assert '"substitution_policy": "forbidden"' in analysis
    assert "不再生成独立代码检视阶段" in analysis


def test_workflow_trigger_requires_explicit_optimization_and_concrete_operator() -> (
    None
):
    skill = read(SKILL)
    wrapper = read(WRAPPER)
    hook = read(HOOK)
    assert "仅当用户明确要求对某个具体 AscendC 算子或代码目录" in skill
    assert "只有同时满足以下两项" in wrapper
    assert "明确的执行意图" in wrapper
    assert "具体 AscendC 算子" in wrapper
    for token in ("安装或使用咨询", "分析已有报告或日志", "精度排障", "普通代码检视"):
        assert token in wrapper
    for token in ("cases.csv", "msprof", "profiling", "加速比"):
        assert token in skill
        assert token in wrapper
    assert "only when the user explicitly asks" in hook
    assert (
        "without both explicit optimization intent and a concrete operator target"
        in hook
    )


def test_quickstart_remains_a_complete_human_guide() -> None:
    quickstart = read(QUICKSTART)
    for section in (
        "## 触发边界",
        "## 1. 安装",
        "## 2. 发起任务",
        "## 3. 工作流会做什么",
        "## 4. 人工如何介入",
        "## 5. 如何理解精度结果",
        "## 6. 输出目录",
        "## 8. 耗时预期",
        "## 9. 恢复与版本兼容",
        "## 10. 完成判定",
    ):
        assert section in quickstart
    assert "## 1. 开始前准备" not in quickstart
    assert quickstart.index("## 1. 安装") < quickstart.index("## 2. 发起任务")
    assert quickstart.index("#### 启动时确认") > quickstart.index("## 2. 发起任务")
    prompt_examples = (
        "##### 性能用例 + 现有功能用例：按指标调优",
        "##### 性能用例 + 自动生成功能用例：按轮次调优",
    )
    assert quickstart.count("#### 提示词范例") == 1
    prompt_examples_start = quickstart.index("#### 提示词范例")
    assert all(
        quickstart.index(example) > prompt_examples_start for example in prompt_examples
    )
    for client in ("claude", "codex", "opencode"):
        assert client in quickstart
    assert "直调 demo" in quickstart
    assert "注册算子工程" in quickstart
    assert "自动生成功能用例" in quickstart
    assert "性能调优报告.md" in quickstart
    assert "optimization-request.json" in quickstart
    assert "默认 3 轮" in quickstart
    assert "Python 环境" in quickstart
    assert "CANN 环境" in quickstart
    assert "目标 SoC" in quickstart
    assert "复用性能用例" in quickstart
    assert "使用已有功能用例" in quickstart
    for target_source in ("其他算力卡", "理论上限", "小算子"):
        assert target_source in quickstart
    assert "精度诊断策略" not in quickstart
    assert "persistent" not in quickstart
    assert "interactive" not in quickstart
