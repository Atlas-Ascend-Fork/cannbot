---
name: ops-perf-analysis
description: 用于冻结性能任务的基线 profiling、逐 case 瓶颈诊断和方案规划。产出分析报告、精确实施契约与待冻结 scope。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 诊断分析

每轮选定一个就绪实施方案。启用 `search_policy` 时先读取 [搜索决策](../ops-perf-acceptance-criteria/references/architecture-search.md) 与 `inspect.search`，消费历史实测和重试条件，按需重新评估架构，再在本轮契约中记录父实现、依赖与机制验收条件。

启用 experience_policy 时，把上轮 selection 中的适用条件、失败成本与重试前提落实到本轮 analysis：写清采纳了什么、排除了什么、哪个新证据允许重试。后处理交来的经验只能在平台/工具链/输入/路径范围匹配且出处有效时作为设计依据；否则作为待验证假设。方案描述保留具体改动、减少工作和新增代价，便于后续按 [经验提炼与验收](../ops-perf-postprocess/references/experience-reflux.md) 复盘；不新增每轮知识文件。

从派发信封读取 `WORKFLOW_ROOT`、`WORKFLOW_SCRIPTS`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；manifest/state 必须已初始化并通过身份核验。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与未决项，不以对话替代产物。输入缺失、证据身份不一致、阶段前置未满足或缺少写入范围时返回主 Agent，不猜测环境或权限。

信封中的路径均为解析后的绝对路径；调用工作流脚本（`scripts/` 目录下）必须直接使用这些绝对路径，不要把 `$WORKFLOW_ROOT`/`$WORKFLOW_SCRIPTS` 当作环境变量。工作目录内对普通文件的常规相对路径操作不受此限制。

## 语言路由

从已确认的 request（freeze 前）或 manifest.configuration 读取 `backend`，缺省为 `ascendc`。先加载本阶段 Skill 和 `ops-perf-acceptance-criteria` 的共享验证契约，其余技能按本阶段任务调用，使用前完整读取。

- `ascendc`：执行下文的 AscendC 步骤，保留原有 TTK、工程工具及排障要求。
- `cannbot_dsl`：执行下文的 DSL 步骤；共享验证与领域边界见 `ops-perf-acceptance-criteria` 的 [cannbot-dsl.md](../ops-perf-acceptance-criteria/references/cannbot-dsl.md)，功能验证使用原 pytest/checker/golden。原工程包含 Native/AOT、C++ 扩展或注册入口时保留相应工程检查；生成 AscendC 中间代码本身不要求改造为 C++ 注册工程。

两条路径均执行冻结输入、源码隔离、精度、性能与阶段交接门禁；DSL 按其共享验证契约补齐编译及实际加载证据。

## Agent 的参考输入

以下资料没有固定先后顺序，按当前瓶颈和证据选择。检索、引用和证据处理见[分析执行参考](references/analysis-execution.md)，本节只给入口和用途。

- **内置板卡事实库（`references/kb/`）**：按 `TARGET_SOCS` 查 910/950 册的 `INDEX.md` 和条目，用于核对板卡资源、存储层级、搬运、同步、计算、Tiling 与性能陷阱；引用规则见 [GOVERNANCE.md](references/kb/GOVERNANCE.md#1-引用)。
- **精炼区知识卡（`KB_ROOT` 下的 `distill/book`）**：cann-refinery 的 `book/` 只读软链。用 `demand/` 和 `guides/` 找问题与路线，`claims/` 作为知识索引读主张卡，`obs/` 查原始证据；只读，不写卡、不建索引。
- **扩展知识库（`knowledge-query`）**：补充 API 约束、存储层级、SIMD/SIMT、同步、Roofline、反模式和排障。先读其 SKILL 与 `references/cli.md`，确认任务目标平台后检索并阅读全文；不可用时记录 `kb_unavailable`。
- **最佳实践（`ascendc-performance-best-practices`）**：按目标代际和算子族找参考实现，对照布局、Tiling 和流水。
- **优化方法（`ascendc-perf-optimize`）**：Tiling 建模或卡间/核间/单核流水分析，把模型与 profiling 对照。
- **理论建模（`ops-theoretical-performance-estimation` / `ops-opmodel-toolkit`）**：在搜索、比较方案时评估适用性和决策价值；粗粒度 roofline 不足以解释实测差距，或需要比较融合、驻留、tiling、分核等候选收益时，优先尝试或复用能回答当前问题的模型。按整体计算结构选择入口：MM/Cube、融合算子、多阶段 DAG、流水空泡和映射/参数寻优优先使用 `ops-opmodel-toolkit`；单一纯 Vector/RegBase 计算链使用 `ops-theoretical-performance-estimation` 的标定引擎。跨阶段数据流即使全由 Vector 组成，也按整体 DAG 评估建模路线，内部 Vector 子图可按需细化。输入含 Skill 入口、适用平台与工作流索引；实际版本、硬件绑定、成本可信度和模型范围以核验结果为准。模型是搜索辅助证据，运行模型或达到某个预测精度不是方案进入实施的必要条件。

**以下三项仅适用于 AscendC 路径：**

- **MC² 最佳实践（`ascendc-mc2-best-practice`）**：确认多卡通信/多 rank 路径后使用，分析通信隐藏和通算重叠。
- **静态性能检视（`ascendc-performance-review`）**：按检查点索引只读排查，把 finding 作为待实测假设。
- **API 文档检索（`ascendc-docs-search`）**：方案依赖具体 AscendC API 时使用，并结合目标 SDK 核验。

概览和索引不能代替正文、代码或实测证据；来源缺失时说明原因，不把未检索写成无覆盖。

## AscendC 执行与交付

1. **准备性能基线。** 按 `ops-perf-acceptance-criteria` 复用或采集当前基线；诊断按证据缺口使用 `ops-profiling-report`。

2. **分析瓶颈并选择方案。** 按 [分析执行参考](references/analysis-execution.md) 给出逐 case 的瓶颈、目标差距与优化方向，结合上述[参考输入](#agent-的参考输入)选择本轮方案；精炼区卡用于核对机制和失效边界。实际采用的实现须核对目标芯片、内嵌 MM、VF/SIMT 和 API 约束。generalization 按共享 ratio 口径计算全集结果，再按 [泛化选例](references/generalization-selection.md) 确定性选例。

3. **确定修改范围和调度约束。** 读取 `$WORKFLOW_ROOT/workflows/references/source-isolation.md`，形成源码隔离 scope。启用 `schedule_policy` 时按 [调度契约](../ops-perf-acceptance-criteria/references/async-schedule-contract.md) 核验适用性；涉及跨 tile、多 engine、异步复用时补齐独立程序、约束及候选模型，未知同步事实先取证。

4. **交付本轮方案。** 按分析执行参考输出一份 `analysis/roundN/analysis.md`，以及就绪方案的 exact/forbidden 实施契约和 source-isolation scope。报告覆盖每个调优 case 的瓶颈、目标差距与证据；`analysis.md` 和实施契约同时作为回流时的策略来源，不额外维护知识文件。主 Agent 冻结 scope 后交实施。

## DSL 执行与交付

1. **准备性能基线。** 按 `ops-perf-acceptance-criteria` 复用或采集当前基线；同一 sample 的全部相关 target launches 聚合后取中位数，JIT 编译/加载在正式样本前完成。诊断按证据缺口使用 `ops-profiling-report`。

2. **分析瓶颈并选择方案。** 结合源码、profiling 和历史结果，自主选用上述[参考输入](#agent-的参考输入)中的知识库、最佳实践、优化方法和理论建模工具，逐 case 给出 bound、瓶颈和优化方向；上节末尾三项仅用于 AscendC。选用最佳实践时，按目标平台和问题查询公共能力、cannbot-dsl 公共库或族级 `cannbot-dsl/` 实现；API 事实按 [DSL 共享验证与领域边界](../ops-perf-acceptance-criteria/references/cannbot-dsl.md) 的「文档与样例检索」核验。

3. **评估方案净收益。** 候选生成前按 [DSL 诊断分析](references/dsl-analysis.md) 的净收益要求，评估关键路径可节省的耗时和新增成本；不调用仅适用于 AscendC 的静态性能检视参考输入。

4. **确定修改范围和调度约束。** 读取 `$WORKFLOW_ROOT/workflows/references/source-isolation.md`，形成源码隔离 scope。启用 `schedule_policy` 时按 [调度契约](../ops-perf-acceptance-criteria/references/async-schedule-contract.md) 完成 A1 独立程序恢复、A2 约束检查、A3 候选，交付 `schedule-contract-<scheme_id>.json` 与 model 检查报告；未知同步事实先取证。

5. **交付本轮方案。** 按 [DSL 诊断分析](references/dsl-analysis.md) 输出一份 `analysis/roundN/analysis.md`，包含逐 case 的 MBU/MFU/bound/headroom、双 roofline、瓶颈和目标差距证据；另交就绪方案的 exact/forbidden 实施契约与 source-isolation scope。主 Agent 冻结 scope 后交实施。

两条路径的阶段产物均写入 `$OUTPUT_DIR/analysis/`。

需要调用工具时使用 `$WORKFLOW_SCRIPTS/`；写进度或提交保存点时按需读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
