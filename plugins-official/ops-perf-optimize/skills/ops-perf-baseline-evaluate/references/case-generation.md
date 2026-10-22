# AscendC 用例设计专家

本参考只处理 standard 的 `FUNCTIONAL_MODE=generate`，或 generalization 的泛化用例生成。standard 的 `existing`/`reuse_performance` 是本地确定性冻结任务，不得另派用例 Agent；generalization 虽固定为 `reuse_performance`，但缺少性能用例时仍由基线评估 Agent生成性能/功能合一全集。

## 模式差异

| 项目 | `standard` | `generalization` |
|---|---|---|
| 何时派发 | 仅 `FUNCTIONAL_MODE=generate` | 缺少泛化性能用例时 |
| 生成目标 | 完整 L0/L1/L2 功能库存 | 默认 1000 条 L0 性能/功能合一用例 |
| 性能用途 | 不作为性能用例生成任务 | 同一全集同时用于性能采集和功能回归 |
| 接入命令 | `attach-functional` | `attach-generalization` |
| 验收子集 | 接入时确定性选择最多 40 条 L0 | 接入时从泛化全集确定性选择最多 40 条 L0 |

新版接入流程完整覆盖两种模式：基线评估 Agent 只生成可信库存，`prepare_case_sets.py` 负责确定性冻结、选择与 manifest 更新；不得把 generalization 当作 standard 的普通功能库存，也不得在 Agent 内重写选择算法。

## 输入

- `CODE_DIR`、`RUN_MANIFEST`；standard 的 `PERFORMANCE_FULL_CASES`，或 generalization 中待生成的空集合状态；
- `OUTPUT_DIR`；
- `TUNING_MODE=standard|generalization`；
- generalization 的 `TARGET_CASE_COUNT`（默认 1000）；
- 算子接口、语义和目标 dtype/attrs 范围。

## 执行

1. 完整读取 `ascendc-st-design`；standard 生成完整 L0/L1/L2 库，generalization 基于接口、约束和测试因子生成 `TARGET_CASE_COUNT` 条 L0 性能/功能合一用例。
2. 加载 `ops-precision-standard`，逐 dtype 明确 `atol`/`rtol`。golden 只能来自数学定义或可信 CPU 参考实现，不得来自被测 kernel。
3. dtype、format、attrs、输入输出个数和约束只能来自冻结的原始接口；不得因为优化实现新增了分支就扩大测试合同或反向把新增 dtype 当作原接口能力。把接口来源文件与 SHA 写进 `functional-generation.json`。
4. standard 库存不受性能 50 条或快速验收 40 条上限影响；generalization 覆盖执行路径、dtype/attrs、shape 规模、对齐/尾块和边界，不得用随机填充凑数。
5. 每个 case 有稳定 ID、level、shape、dtype、attrs、seed、golden 来源、比较器和阈值。
6. standard 原子写入 `functional-full/` 与 `functional-generation.json`；generalization 原子写入 `generalization-full-cases.csv` 与 `functional-generation.json`，并由接入步骤在 manifest 中把同一集合登记为 `functional_full`，其中每条用例同时具备性能采集字段和可信功能判定字段。
7. 返回后由基线评估 Agent 调用 `prepare_case_sets.py attach-functional`（standard）或 `attach-generalization`（generalization）生成冻结集合及最多 40 条 L0 验收子集；基线评估 Agent不重复实现选择算法。

## 输出

- `functional-full/`：完整 L0/L1/L2 库；
- `generalization-full-cases.csv`：generalization 模式的性能/功能合一全集；
- `functional-generation.json`：接口、数量、SHA、覆盖、golden/阈值来源、起止时间和状态；
- `functional-design.md`：人可审阅的设计与覆盖缺口。

不编译、不运行 NPU、不修改算子、不执行精度诊断。返回“生成完成”只表示静态库存有效，实际验收由主工作流执行。
