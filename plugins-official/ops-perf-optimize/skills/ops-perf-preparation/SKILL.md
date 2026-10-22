---
name: ops-perf-preparation
description: 用于性能任务的独立 demo 前处理：保持调用方式剥离工程，建立构建/加载证据并用 TTK 验证基线精度。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 前处理

从派发信封读取 `PLUGIN_ROOT`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；manifest/state 必须已初始化并通过身份核验。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与缺口。缺少输入或写入范围时返回主 Agent。

## 执行与交付

1. 读取 [preparation.md](references/preparation.md)，确认基线评估产物和冻结功能库存已完成。
2. 按 [extraction.md](references/extraction.md) 建立独立工作工程；原工程与共享 SDK 只读，保持原调用方式和算法。
3. 读取 `$PLUGIN_ROOT/workflows/references/source-isolation.md` 与 `ops-perf-acceptance-criteria` 的精度路由，再用 TTK 标准 skill（`ttk-how-run-test`）执行完整功能验收子集。harness 使用共享采集协议；MC² 按 `ascendc-mc2-best-practice`。
4. 交付 demo、`extraction-manifest.json`、`source-compatibility.md`、原源码快照、构建/加载证据及 `functional-acceptance.md`。strict_pass 或可信 conditional_pass 才可交接。

需要调用工具时使用 `$PLUGIN_ROOT/scripts/`；写进度或提交保存点时按需读取 `$PLUGIN_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
