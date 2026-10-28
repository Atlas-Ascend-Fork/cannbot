---
name: ops-perf-analysis
description: 用于冻结性能任务的基线 profiling、逐 case 瓶颈诊断和方案规划。产出分析报告、精确实施契约与待冻结 scope。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 诊断分析

从派发信封读取 `WORKFLOW_ROOT`、`WORKFLOW_SCRIPTS`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；manifest/state 必须已初始化并通过身份核验。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与未决项，不以对话替代产物。输入缺失、证据身份不一致、阶段前置未满足或缺少写入范围时返回主 Agent，不猜测环境或权限。

信封中的路径均为解析后的绝对路径；调用工作流脚本（`scripts/` 目录下）必须直接使用这些绝对路径，不要把 `$WORKFLOW_ROOT`/`$WORKFLOW_SCRIPTS` 当作环境变量。工作目录内对普通文件的常规相对路径操作不受此限制。

## 语言路由

从已确认的 request（freeze 前）或 manifest.configuration 读取 `backend`，缺省为 `ascendc`。先加载本阶段 Skill 和 `ops-perf-acceptance-criteria` 的共享验证契约，其余技能按本阶段任务调用，使用前完整读取。

- `ascendc`：执行下文的 AscendC 步骤，保留原有 TTK、工程工具及排障要求。
- `cannbot_dsl`：执行下文的 DSL 步骤；共享验证与领域边界见 `ops-perf-acceptance-criteria` 的 [cannbot-dsl.md](../ops-perf-acceptance-criteria/references/cannbot-dsl.md)，功能验证使用原 pytest/checker/golden。原工程包含 Native/AOT、C++ 扩展或注册入口时保留相应工程检查；生成 AscendC 中间代码本身不要求改造为 C++ 注册工程。

两条路径均执行冻结输入、源码隔离、精度、性能与阶段交接门禁；DSL 按其共享验证契约补齐编译及实际加载证据。语言选择只决定具体工具和执行步骤，不授予跳过验收的权限。客户端若自动预加载声明技能，仍按上述适用范围执行。

## AscendC 执行与交付

1. 先按 `ops-perf-acceptance-criteria` 的性能采集路由复用或采集当前基线；聚合指标等简单 profile 信息不足以支撑分析时，在采集阶段按需加载 `ops-perf-profile-feature-extractor` 提取诊断级性能特征（流水图、逐指令时序）。再读取 [analysis-execution.md](references/analysis-execution.md) 完成只读分析。采集阶段可使用隔离探针，分析推导不得重采、重选 case 或修改基线。
2. 读取 `$WORKFLOW_ROOT/workflows/references/source-isolation.md` 的共享源码隔离契约；generalization 先按共享 ratio 口径计算全集结果，再读 [generalization-selection.md](references/generalization-selection.md) 确定性选例。
3. 仅在静态代码检视确有用途时加载 `ascendc-performance-review`（共享 skill），按其检查点索引只读排查；检查结论作为假设级证据并入本轮分析。
4. 算子族与模板按 `ascendc-performance-best-practices`，策略推导按 `ascendc-perf-optimize`，具体 API 由 `ascendc-docs-search` 和本机 SDK 核验；保留算子族、内嵌 MM 路线、VF/SIMT、API 取证及静态检查点能力。MC²/多 rank 路径确认后使用 `ascendc-mc2-best-practice`，未命中时不执行通信专用步骤。方案设计前按信封 `KB_ROOT` 经 `knowledge-query` 检索优化方法、机制与反模式知识卡，方案须引用实际读过的卡片；`KB_ROOT` 缺失时标注 `kb_unavailable`，按无知识增强继续。调用前先读其 SKILL 与 `references/cli.md`，确认任务目标平台后按当前接口组命令；复杂性能任务按其性能优化模式与证据工作流记录审计，参数和输出字段以该 Skill 为准。
5. 启用 schedule_policy 时，按 [调度契约](../ops-perf-acceptance-criteria/references/async-schedule-contract.md) 核验适用性；涉及跨 tile、多 engine、异步复用的方案补独立程序、约束及候选模型，未知同步事实先取证。交付一份 `analysis/roundN/analysis.md`、最多三份 exact/forbidden 实施契约和 source-isolation scope；每个调优 case 有瓶颈与目标差距证据，主 Agent 冻结 scope 后交实施。阶段产物写入 `$OUTPUT_DIR/analysis/`，交付时更新该文件夹的 `阶段总结.md`（做了什么、成果、关键产物清单、未决项）。

## DSL 执行与交付

1. 采集/复用性能基线：按 `ops-perf-acceptance-criteria` 的性能采集路由复用或采集当前基线；DSL 按同一 sample 全部相关 target launches 聚合取中位数，JIT 编译/加载在正式样本前完成。聚合指标不足以支撑分析时，按需加载 `ops-perf-profile-feature-extractor` 提取流水图与逐指令时序。采集阶段可使用隔离探针，分析推导不得重采、重选 case 或修改基线。
2. 分析性能瓶颈与优化用例：按 `ascendc-perf-optimize`（语言无关 4 步流程：Step 1 Tiling 理论建模必选，Step 2 卡间流水仅通信类算子，Step 3 核间流水仅多核同步算子，Step 4 单核流水必选）逐 case 完成 bound 诊断与瓶颈定位；按 `ascendc-performance-best-practices` 查优化用例：先查公共优化能力与 cannbot-dsl 公共库等跨算子族公共知识，再进族级 `cannbot-dsl/` 语言子目录查族级 DSL 实践。需要静态佐证或净收益评估时加载 `ascendc-performance-review`：检查点索引只读排查，实施契约生成前执行其 `references/dsl-benefit-assessment.md`，融合多阶段、量化 MM 或讨论 MBU/小收益时读取其 `references/dsl-flow-and-headroom.md`。方案设计前按信封 `KB_ROOT` 经 `knowledge-query` 检索优化方法与反模式知识卡，方案须引用支撑卡片 doc-id；缺失标注 `kb_unavailable` 继续。具体 API 事实按 cannbot-dsl.md 的「文档与样例检索」核验。
3. 输出性能调优方案：按 [DSL 诊断分析](references/dsl-analysis.md) 交付一份 `analysis/roundN/analysis.md`（逐 case 的 MBU/MFU/bound/headroom 与双 roofline、瓶颈与目标差距证据）、最多三份 exact/forbidden 实施契约和 source-isolation scope；启用 schedule_policy 时完成 A1 独立程序恢复、A2 约束检查、A3 形成候选，另交 `schedule-contract-<scheme_id>.json` 与 model 检查报告。主 Agent 冻结 scope 后交实施。阶段产物写入 `$OUTPUT_DIR/analysis/`，交付时更新该文件夹的 `阶段总结.md`（做了什么、成果、关键产物清单、未决项）。

需要调用工具时使用 `$WORKFLOW_SCRIPTS/`；写进度或提交保存点时按需读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
