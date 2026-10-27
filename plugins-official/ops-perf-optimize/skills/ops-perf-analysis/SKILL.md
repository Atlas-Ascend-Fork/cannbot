---
name: ops-perf-analysis
description: 用于冻结性能任务的基线 profiling、逐 case 瓶颈诊断和方案规划。产出分析报告、精确实施契约与待冻结 scope。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 诊断分析

从派发信封读取 `WORKFLOW_ROOT`、`WORKFLOW_SCRIPTS`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；manifest/state 必须已初始化并通过身份核验。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与缺口。缺少输入或写入范围时返回主 Agent。

信封中的路径均为解析后的绝对路径；调用工作流脚本（`scripts/` 目录下）必须直接使用这些绝对路径，不要把 `$WORKFLOW_ROOT`/`$WORKFLOW_SCRIPTS` 当作环境变量。工作目录内对普通文件的常规相对路径操作不受此限制。

## 执行与交付

1. 先按 `ops-perf-acceptance-criteria` 的性能采集路由复用或采集当前基线；聚合指标等简单 profile 信息不足以支撑分析时，在采集阶段按需加载 `ops-perf-profile-feature-extractor` 提取诊断级性能特征（流水图、逐指令时序）。再读取 [analysis-execution.md](references/analysis-execution.md) 完成只读分析。采集阶段可使用隔离探针，分析推导不得重采、重选 case 或修改基线。
2. 读取 `$WORKFLOW_ROOT/workflows/references/source-isolation.md` 的共享源码隔离契约；generalization 先按共享 ratio 口径计算全集结果，再读 [generalization-selection.md](references/generalization-selection.md) 确定性选例。
3. 仅在静态代码检视确有用途时加载 `ascendc-performance-review`，按其检查点索引只读排查；检查结论作为假设级证据并入本轮分析。
4. 算子族与模板按 `ascendc-performance-best-practices`，策略推导按 `ascendc-perf-optimize`，MC²/多 rank 的指标口径与流水判定按 `ascendc-mc2-best-practice`，具体 API 由 `ascendc-docs-search` 和本机 SDK 核验。方案设计前按信封 `KB_ROOT` 经 `knowledge-query` 检索优化方法、机制与反模式知识卡，方案须引用实际读过的卡片；`KB_ROOT` 缺失时标注 `kb_unavailable`，按无知识增强继续。调用前先读其 SKILL 与 `references/cli.md`，确认任务目标平台后按当前接口组命令；复杂性能任务按其性能优化模式与证据工作流记录审计，参数和输出字段以该 Skill 为准。
5. 交付一份 `roundN/analysis.md`、最多三份 exact/forbidden 实施契约和 source-isolation scope；每个调优 case 有瓶颈与目标差距证据，主 Agent 冻结 scope 后交实施。

需要调用工具时使用 `$WORKFLOW_SCRIPTS/`；写进度或提交保存点时按需读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
