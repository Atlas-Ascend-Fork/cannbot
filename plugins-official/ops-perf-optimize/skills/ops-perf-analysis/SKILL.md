---
name: ops-perf-analysis
description: 用于冻结性能任务的基线 profiling、逐 case 瓶颈诊断和方案规划。产出分析报告、精确实施契约与待冻结 scope。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 诊断分析

每轮选定一个就绪实施方案。启用 `search_policy` 时先读取 [搜索决策](../ops-perf-acceptance-criteria/references/architecture-search.md) 与 `inspect.search`，消费历史实测和重试条件，按需重新评估架构，再在本轮契约中记录父实现、依赖与机制验收条件。

从派发信封读取 `WORKFLOW_ROOT`、`WORKFLOW_SCRIPTS`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；manifest/state 必须已初始化并通过身份核验。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与未决项，不以对话替代产物。输入缺失、证据身份不一致、阶段前置未满足或缺少写入范围时返回主 Agent，不猜测环境或权限。

信封中的路径均为解析后的绝对路径；调用工作流脚本（`scripts/` 目录下）必须直接使用这些绝对路径，不要把 `$WORKFLOW_ROOT`/`$WORKFLOW_SCRIPTS` 当作环境变量。工作目录内对普通文件的常规相对路径操作不受此限制。

## 语言路由

从已确认的 request（freeze 前）或 manifest.configuration 读取 `backend`，缺省为 `ascendc`。先加载本阶段 Skill 和 `ops-perf-acceptance-criteria` 的共享验证契约，其余技能按本阶段任务调用，使用前完整读取。

- `ascendc`：执行下文的 AscendC 步骤，保留原有 TTK、工程工具及排障要求。
- `cannbot_dsl`：执行下文的 DSL 步骤；共享验证与领域边界见 `ops-perf-acceptance-criteria` 的 [cannbot-dsl.md](../ops-perf-acceptance-criteria/references/cannbot-dsl.md)，功能验证使用原 pytest/checker/golden。原工程包含 Native/AOT、C++ 扩展或注册入口时保留相应工程检查；生成 AscendC 中间代码本身不要求改造为 C++ 注册工程。

两条路径均执行冻结输入、源码隔离、精度、性能与阶段交接门禁；DSL 按其共享验证契约补齐编译及实际加载证据。语言选择只决定具体工具和执行步骤，不授予跳过验收的权限。客户端若自动预加载声明技能，仍按上述适用范围执行。

## Agent 的参考输入

主 Agent 派发时，将以下资料的**概览、索引入口和适用范围**一并提供给分析 Agent：

- **知识库（`knowledge-query`）**：代表性关键词为 API 约束、存储层级、SIMD/SIMT、同步、Roofline、优化反模式、编译/精度/性能排障。用于解释 profiling 现象、核对约束和借鉴失败经验：围绕当前瓶颈检索，读相关卡片正文，将机制和约束用于提出或排除候选方向。输入含 Query/CLI 入口、`KB_ROOT`、已有覆盖信息或卡片索引及目标适用范围。
- **最佳实践（`ascendc-performance-best-practices`）**：代表性关键词为 MatMul、FlashAttention、MC²、Reduction/Softmax、Scan、Gather/Scatter、Transpose、数据搬运、UB 复用、Reg/VF。用于寻找可复用的成熟实现：按目标代际与算子族找参考代码，对照当前实现的布局、Tiling 和流水，提取可迁移的做法并核对集成条件。输入含 Skill 入口、族级与公共能力索引及平台/语言适用范围。
- **优化方法（`ascendc-perf-optimize`）**：用于定位瓶颈、估算优化空间和推导策略。按当前问题选用 Tiling 建模或卡间/核间/单核流水分析，将模型与 profiling 对照，形成有预期收益依据的修改方向。输入含 Skill 入口、方法索引和适用条件。
- **理论建模（`ops-theoretical-performance-estimation` / `ops-opmodel-toolkit`）**：粗粒度 roofline 不足以解释实测差距，或需要在设计期定量比较融合、驻留、tiling、分核等候选收益时使用。按计算结构选择入口：纯 Vector/RegBase 计算流使用 `ops-theoretical-performance-estimation` 的标定引擎；MM/Cube、融合算子、多阶段 DAG、流水空泡和映射/参数寻优优先使用 `ops-opmodel-toolkit`。混合算子由 OpModel 建立整体融合图，内部纯 Vector 子图可在需要时再用标定模型细化，不能把含 MM 或跨阶段数据流的融合算子当成单一纯 Vector 算子。输入含 Skill 入口、适用平台与工作流索引；实际版本、硬件绑定和模型范围以运行时核验结果为准。

**以下三项仅适用于 AscendC 路径，不作为 CANNBot-DSL 的参考输入：**

- **MC² 最佳实践（`ascendc-mc2-best-practice`）**：覆盖 AllGather/AllReduce/AllToAll + MatMul、MoE Dispatch/Combine、SHMEM/APACE、URMA/MTE/HCCL 路线及通算流水。确认多卡通信/多 rank 路径后使用，核对芯片、调用形态与通信底座的能力登记，再分析通信隐藏和通算重叠；未命中时不执行通信专用步骤。输入含 Skill 入口、能力登记与对应路线索引。
- **静态性能检视（`ascendc-performance-review`）**：覆盖架构宏门控、平台参数写死、双缓冲与搬运合并、UB 切分、核间均衡、Reg/VF/SIMT、Scalar 与头开销。需要源码佐证时按检查点索引只读排查，将 finding 作为待实测的假设并入同一分析报告。输入含 Skill 入口、检查点索引及平台适用范围。
- **API 文档检索（`ascendc-docs-search`）**：覆盖 API 签名与变体、参数约束、平台/版本兼容、官方示例和 Tiling 实现。方案依赖具体 AscendC API 时，本地资料优先、缺失时在线补查，并结合目标 SDK 核验。输入含 Skill 入口、API/示例索引及目标 SDK 路径。

分析 Agent 先浏览各项概览，了解可用知识和候选方法，再结合源码、冻结用例、性能目标、profiling 和历史尝试择优形成方案。详细资料按问题与适用范围深读，可组合使用或复用已有证据；不规定深读顺序，也不要求每轮完整读取所有资料。来源缺失时保留该项概览并说明不可用原因，不把未检索误写成无覆盖。

各项资料得出的方向合并比较，按目标适配、预期收益、实施成本和证据可信度选择本轮方案；在同一分析报告中说明采用了什么、如何支撑决策，以及未采用相关候选的原因。例如搬运等待占主导时，可用知识库核对搬运/同步约束，从最佳实践寻找流水骨架，再用优化方法评估重叠能节省的时间与新增成本；按现有证据选择需要深读的部分。

概览和索引用于发现候选，不能代替正文、代码或实测证据。选用 `knowledge-query` 时，先读其 SKILL 与 `references/cli.md`，确认任务目标平台后检索并阅读全文；只引用实际读过的卡片及 doc-id，复杂任务按其证据工作流记录审计。未采用知识卡时 `kb_cards` 留空；知识库缺失或查询失败时停止该次知识检索，记录 `kb_unavailable` 及原因，使用其他有效输入继续分析；不自动重建索引。

平台、API、同步、资源容量及特殊路线的适用性检查，按实际源码和候选机制触发，与 Agent 选用哪类参考资料无关；资料选择不能免除这些约束。

## AscendC 执行与交付

1. **准备性能基线。** 按 `ops-perf-acceptance-criteria` 复用或采集当前基线。**聚合指标、Duration 等简单 profile 不足以支撑瓶颈分析时，必须在采集阶段使用 `ops-perf-profile-feature-extractor` 补齐流水图**，定位 pipe 依赖、重叠、气泡和同步等待，必要时补逐指令时序；已有同身份有效流水图可复用。按目标平台选择板上或仿真来源，聚合利用率不能当作流水图，流水图也不替代稳态耗时验收。采集可用隔离探针，分析推导不得重采、重选 case 或修改基线。

2. **分析瓶颈并选择方案。** 按 [分析执行参考](references/analysis-execution.md) 给出逐 case 的瓶颈、目标差距与优化方向，结合上述[参考输入](#agent-的参考输入)选择本轮方案。实际采用的实现须核对目标芯片、内嵌 MM、VF/SIMT 和 API 约束。generalization 按共享 ratio 口径计算全集结果，再按 [泛化选例](references/generalization-selection.md) 确定性选例。

3. **确定修改范围和调度约束。** 读取 `$WORKFLOW_ROOT/workflows/references/source-isolation.md`，形成源码隔离 scope。启用 `schedule_policy` 时按 [调度契约](../ops-perf-acceptance-criteria/references/async-schedule-contract.md) 核验适用性；涉及跨 tile、多 engine、异步复用时补齐独立程序、约束及候选模型，未知同步事实先取证。

4. **交付本轮方案。** 按分析执行参考输出一份 `analysis/roundN/analysis.md`，以及就绪方案的 exact/forbidden 实施契约和 source-isolation scope。报告覆盖每个调优 case 的瓶颈、目标差距与证据；主 Agent 冻结 scope 后交实施。

## DSL 执行与交付

1. **准备性能基线。** 按 `ops-perf-acceptance-criteria` 复用或采集当前基线；同一 sample 的全部相关 target launches 聚合后取中位数，JIT 编译/加载在正式样本前完成。**聚合指标、Duration 等简单 profile 不足以支撑瓶颈分析时，必须在采集阶段使用 `ops-perf-profile-feature-extractor` 补齐流水图**，定位 pipe 依赖、重叠、气泡和同步等待，必要时补逐指令时序；已有同身份有效流水图可复用。按目标平台选择板上或仿真来源，聚合利用率不能当作流水图，流水图也不替代稳态耗时验收。采集可用隔离探针，分析推导不得重采、重选 case 或修改基线。

2. **分析瓶颈并选择方案。** 结合源码、profiling 和历史结果，自主选用上述[参考输入](#agent-的参考输入)中的知识库、最佳实践、优化方法和理论建模工具，逐 case 给出 bound、瓶颈和优化方向；上节末尾三项仅用于 AscendC。选用最佳实践时，按目标平台和问题查询公共能力、cannbot-dsl 公共库或族级 `cannbot-dsl/` 实现；API 事实按 [DSL 共享验证与领域边界](../ops-perf-acceptance-criteria/references/cannbot-dsl.md) 的「文档与样例检索」核验。

3. **评估方案净收益。** 候选生成前按 [DSL 诊断分析](references/dsl-analysis.md) 的净收益要求，评估关键路径可节省的耗时和新增成本；不调用仅适用于 AscendC 的静态性能检视参考输入。

4. **确定修改范围和调度约束。** 读取 `$WORKFLOW_ROOT/workflows/references/source-isolation.md`，形成源码隔离 scope。启用 `schedule_policy` 时按 [调度契约](../ops-perf-acceptance-criteria/references/async-schedule-contract.md) 完成 A1 独立程序恢复、A2 约束检查、A3 候选，交付 `schedule-contract-<scheme_id>.json` 与 model 检查报告；未知同步事实先取证。

5. **交付本轮方案。** 按 [DSL 诊断分析](references/dsl-analysis.md) 输出一份 `analysis/roundN/analysis.md`，包含逐 case 的 MBU/MFU/bound/headroom、双 roofline、瓶颈和目标差距证据；另交就绪方案的 exact/forbidden 实施契约与 source-isolation scope。主 Agent 冻结 scope 后交实施。

两条路径的阶段产物均写入 `$OUTPUT_DIR/analysis/`，交付时更新该目录的 `阶段总结.md`，记录本阶段做了什么、成果、关键产物清单与未决项。

需要调用工具时使用 `$WORKFLOW_SCRIPTS/`；写进度或提交保存点时按需读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
