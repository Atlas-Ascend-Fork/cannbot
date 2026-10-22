---
name: ops-perf-postprocess
description: 用于将验收后的性能优化 demo 回集成原工程，保护非目标芯片族并对两个全集检查退化及原代码回路由。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 后处理

从派发信封读取 `PLUGIN_ROOT`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；manifest/state 必须已初始化并通过身份核验。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与缺口。缺少输入或写入范围时返回主 Agent。

## 执行与交付

1. 读取 [postprocessing.md](references/postprocessing.md)，核对最终 demo 全集证据、剥离映射、原快照、兼容矩阵和冻结集合。
2. 按 [writeback.md](references/writeback.md) 执行回写；计划提交主 Agent 冻结后实施，注册/直调均保持原入口。发现原工程并发改动先返回冲突证据。
3. 加载 共享源码隔离路由（`$PLUGIN_ROOT/workflows/references/source-isolation.md`）与 `ops-perf-acceptance-criteria` 的精度、性能采集与抖动路由；芯片族归类统一查询 `npu-arch` skill（按其 NpuArch 代际划分归族），任何族归类结论不扩大精确 TARGET_SOCS；回写 diff 中不得写死核数/UB/L2 等硬件参数（同 NpuArch 内取值范围以 npu-arch 硬件参数表核对）。
4. 执行原工程前后功能全集、性能全集精度与逐 case 性能检查；冻结的预期报错行按参考文档检查前后错误语义，不编造 kernel 耗时。有效退化范围按真实输入谓词回原代码，新身份完整复验。无优化时仍交付有覆盖证据的 no-op。
5. generalization 继续涉及/不涉及路由核验并按共享 ratio 复核最终达标；仅用户要求 CANN-Bench 时读取 `$PLUGIN_ROOT/workflows/cannbench-a5-baseline-collection.md`。
6. 交付安全/精度 gates、每 SoC `postprocess-performance-<soc>.json`、回路由证据和 `VERIFY_REPORT.md`；两个全集无有效回退方可完成，最终报告引用集成后的真实身份。

需要调用工具时使用 `$PLUGIN_ROOT/scripts/`；写进度或提交保存点时按需读取 `$PLUGIN_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
