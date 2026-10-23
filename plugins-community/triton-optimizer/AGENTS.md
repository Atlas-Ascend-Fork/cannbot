---
name: triton-optimizer
description: Triton Optimizer Workflows — 优化 Triton Ascend NPU 算子或转换 PyTorch 算子为 Triton NPU 实现
mode: primary
skills:
  - triton-npu-optimize
  - triton-npu-convert
---

# Triton Optimizer Workflows

本插件是 Triton Optimizer 在 CANNBot 中的 workflow 入口，覆盖两类场景：

- 优化：优化已有 Triton Ascend NPU 算子，按 baseline/round 方式迭代，入口 skill 为 `triton-npu-optimize`。
- 转换：把 PyTorch 算子转换为 PyTorch-facing、Triton Ascend NPU-backed 的实现，并完成验证，入口 skill 为 `triton-npu-convert`。

## 入口职责

- 优化任务使用 `triton-npu-optimize` skill，按 baseline/round 方式迭代。
- 转换任务使用 `triton-npu-convert` skill，把 PyTorch 算子转换为 Triton Ascend NPU 实现并验证。
- 若当前工具不支持 Skill，则按本文件规则在当前会话中直接执行 workflow。
- 所有 Skills 随插件 `skills/` 目录一起提供，由安装脚本（init.sh / install-helper）或插件依赖注入到目标工具。
- `.helix/` 是优化 workflow 运行态目录（如 `.helix/state.json`），由 hooks 与 `triton-npu-optimize-state` skill 管理；不要手动编辑或删除。

## 可用 Skills

入口 Skills：

| Skill | 用途 |
| --- | --- |
| `triton-npu-optimize` | 主优化 workflow，按 canonical baseline 与多轮 round 迭代，通过正确性与性能门禁推进 |
| `triton-npu-convert` | PyTorch 算子到 Triton Ascend NPU 实现的 spec-first 转换 workflow |

支撑 Skills（由入口 skill 按需调用）：

| Skill | 用途 |
| --- | --- |
| `triton-npu-optimize-state` | 优化 workflow 状态管理（submit-baseline / start-round / submit-round 等），维护 `.helix/state.json` |
| `triton-npu-prepare-optimize-baseline` | 建立或修复 canonical `baseline/` |
| `triton-npu-gen-test` | 生成 standalone / differential 正确性测试 |
| `triton-npu-gen-bench` | 生成 benchmark harness |
| `triton-npu-run-eval` | 执行验证与性能评测（`run-test-*`、`run-bench`、`compare-perf`、`profile-bench` 等） |
| `triton-npu-profile-operator` | profiler 诊断 |
| `triton-npu-analyze-round-performance` | round 性能结果分析 |
| `triton-npu-analyze-ir` | IR 归因分析 |
| `triton-npu-analyze-compiler-source` | 编译器源码层面的升级分析 |
| `triton-npu-optimize-knowledge` | 优化路由层（`references/symptom-contract.json` symptom 契约 + `references/pattern_index.md` stage 索引；pattern 卡片内容在 cannbot-knowledge 仓） |
| `triton-npu-retrieve-patterns` | pattern 路由检索 |
| `triton-npu-repair-guide` | Triton 编译、JIT、launch、kernel 结构问题修复 |
| `triton-npu-op-coding-guide` | Triton Ascend NPU 算子编码指导 |
| `triton-npu-cann-ext-api-patterns` | CANN 扩展 API pattern 参考 |

## 状态文件字段

### `baseline/state.json` (baseline state)

Workflow 运行态由 `triton-npu-optimize-state` 脚本自动管理。以下字段出现在 `baseline/state.json` 中，理解其含义有助于诊断状态异常。

| 字段 | 说明 |
|---|---|
| `source_operator` | 相对于 `baseline/` 目录的原始算子路径，通常为 `../<operator>.py` |
| `baseline_operator` | 相对于 `baseline/` 目录的 baseline 算子快照路径，通常为 `<operator>.py` |
| `test_file` | 相对于 `baseline/` 目录的正确性 harness 路径，通常为 `../test_<operator>.py` 或 `../differential_test_<operator>.py` |
| `test_mode` | 解析后的正确性模式 (`standalone` / `differential`) |
| `bench_file` | 相对于 `baseline/` 目录的 benchmark harness 路径，通常为 `../bench_<operator>.py` |
| `bench_mode` | 解析后的 benchmark 模式 (`torch-npu-profiler` / `perf-counter`；历史值 `msprof` 会归一化为 `torch-npu-profiler`) |
| `perf_artifact` | 相对于 `baseline/` 目录的 canonical baseline 性能结果路径，通常为 `<operator>_perf.txt` 或 `perf.txt` |
| `correctness_status` | baseline 正确性结果：`passed` / `failed` / `not_run` |
| `benchmark_status` | baseline benchmark 结果：`passed` / `failed` / `not_run` |

可选字段：`preparation_notes`、`baseline_repairs_summary`。

### `opt-round-N/round-state.json` (round state)

| 字段 | 说明 |
|---|---|
| `round` | round 目录名，如 `opt-round-1` |
| `parent_round` | 直接上游：`baseline` 或前一个 round 名，如 `opt-round-2` |
| `hypothesis` | 本轮测试的优化假设 |
| `correctness_status` | round 正确性结果：`passed` / `failed` / `not_run` |
| `benchmark_status` | round benchmark 结果：`passed` / `failed` / `not_run` |
| `perf_artifact` | 相对于 round 目录的 round perf artifact 路径，通常为 `opt_<operator>_perf.txt`；`benchmark_status=passed` 时必需 |
| `comparison_target_path` | 相对于 round 目录的 baseline perf artifact 路径，用于 compare-perf，通常为 `../baseline/<operator>_perf.txt`；`benchmark_status=passed` 时必需（旧字段名 `comparison_target` 仅作 legacy 兼容） |
| `effective_metric_source` | canonical `run-bench` 比较判定 round 结论的指标：`kernel`、`total-op` 或 `mixed`；`benchmark_status=passed` 时必需 |
| `summary_path` | 相对于 round 目录的 round 总结 markdown 路径，通常为 `summary.md` |
| `opt_note_updated` | 顶层 `opt-note.md` 的本轮条目已更新后置为 `true` |

可选字段：`analysis_skipped_reason`、`profile_dir`、`ir_dir`、`perf_analysis_path`。

## 优化 Workflow

详细流程以 `triton-npu-optimize` skill 为准，核心循环为：

```
Stage 0: Baseline Setup — 建立或复用 canonical baseline（必要时用 triton-npu-prepare-optimize-baseline）
Stage 1: Round Entry — start-round 开启 opt-round-N，记录 strategy / analysis-policy / hypothesis，开始 attempts.md
Stage 2: Layered Analysis — 按 pattern triage -> profiling diagnosis -> IR attribution -> compiler-source escalation 升级证据
Stage 3: Validate And Record — 依次 correctness、canonical run-bench、比较，submit-round 并按 guideline 决定停止或继续
```

每轮只实施一个连贯的代码修改点；首轮 canonical `run-bench` 比较结论出来后即停止编辑该 round，新想法开新 round。首次编辑前必须通过 `triton-npu-optimize-state start-round` 记录本轮 strategy 与 analysis policy，并在 `attempts.md` 中写清 hypothesis、主要分析层级、支撑证据、选中的 pattern 方向（如使用）及理由。

方向选择遵循 `triton-npu-optimize-knowledge/references/pattern_index.md` 的 stage 树顺序（索引条目的 Source 指向 cannbot-knowledge 仓的卡片）：先做结构性改变（Structural），再做 kernel 局部的算法/数据流/存储改变，然后是 refinement，autotune 最后；stage 内的 High/Normal 优先级不得越过 stage 顺序，也不允许用后置 stage 的 High pattern 跳过适用的前置 stage 候选。pattern 卡片由 cannbot-knowledge 仓提供（安装期克隆到 `.cannbot/dependencies/triton-optimizer/cannbot-knowledge/`），symptom 路由契约在本插件 `triton-npu-optimize-knowledge/references/symptom-contract.json`。pattern 指引不是强制门禁，但若某个命名 pattern 指导了本轮，必须在 `attempts.md` 与 `summary.md` 中显式记录。profile、IR、compiler-source 只作为证据升级与问题归因手段，不作为随意试错入口；禁止以盲目的 tiling 或 launch 参数搜索开局。重试已被证伪的方向必须指出因果相关的条件变化和预期判别依据；若无法指出，则 pivot——同一方向最多约 3 次无收益尝试后应转向。

## 转换 Workflow

1. 明确原始 PyTorch 算子文件、转换输出路径、验证模式和运行环境。
2. 使用 `triton-npu-convert` 读取原始算子，但不修改原文件；原文件同时作为差分验证的 correctness oracle。
3. 在算子工作区写入 `spec.json` 作为转换契约（保留的公开 API、kernel 分解计划、语义、测试计划），并在后续流程中保持稳定。
4. 将转换后的 PyTorch-facing Triton Ascend NPU 实现写入用户指定输出路径（默认命名 `triton_<origin-name>.py`），保留原算子的公开 API 与输入构造函数（如 `get_inputs()` / `get_init_inputs()`）。
5. 按 `spec.json` 中的测试计划执行验证：优先复用已有合适测试，否则用 `triton-npu-gen-test` 生成 standalone / differential 测试，再用 `triton-npu-run-eval` 的 `run-test-convert` 执行；differential 模式以原始算子作为 `--ref-operator-file`。
6. 正确性只认 `run-test-convert` 的标准通过输出（differential 为 `PASS:`，standalone 为 `All tests passed!`）；禁止用 `torch.allclose` / `torch.testing.assert_close` 或直接运行测试文件自行宣判通过。
7. 遇到 Triton 编译、JIT、launch 或 kernel 结构问题时，使用 `triton-npu-repair-guide` 修复后重跑同一 `run-test-convert` 命令验证。

## 约束

- 优化流程一次只保持一个 active round。
- 不跳过正确性验证直接比较性能。
- 不把测试、benchmark、profile 结果写成口头假设，必须保留可追溯 artifact。
- 转换流程不得覆盖原始 PyTorch 算子文件。
- 转换结果必须真实走 Triton Ascend NPU kernel 路径，不能用 PyTorch 计算路径伪装替代，也不添加 CUDA/CPU 等后端 fallback 分支。
