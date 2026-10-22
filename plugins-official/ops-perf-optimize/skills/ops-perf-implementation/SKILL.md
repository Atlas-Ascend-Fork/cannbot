---
name: ops-perf-implementation
description: 用于性能任务的隔离方案实施、功能与性能门禁、候选终选及最终 demo 全集验收。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 实施验证

从派发信封读取 `PLUGIN_ROOT`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；manifest/state 必须已初始化并通过身份核验。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与缺口。缺少输入或写入范围时返回主 Agent。

## 执行与交付

1. 读取 [implementation-execution.md](references/implementation-execution.md) 与 [engineering-constraints.md](references/engineering-constraints.md)；消费已冻结方案和 scope，不改原工程或放宽 required features。信封 `KB_ROOT` 存在时，先读取所选方案 `kb_cards` 列出的支撑知识卡并按需经 `knowledge-query` 补充检索实施约束（API 语义、队列同步、精度反模式）；`KB_ROOT` 缺失时标注 `kb_unavailable` 继续，不阻塞实施。
2. 按需读取 `$PLUGIN_ROOT/workflows/references/source-isolation.md` 与 `ops-perf-acceptance-criteria` 的精度、采集和抖动路由；数值与功能故障诊断统一使用 `ascendc-precision-debug`，由本代理执行，不嵌套派发。
3. 读取 [selection-and-final.md](references/selection-and-final.md) 执行序列压测、eligible 候选一次性能采集、含 baseline 的唯一终选和 demo 全集验收；generalization 还读取共享 ratio 参考。
4. 每方案独立副本和证据；独立构建/静态检查可并行，设备采集排他。新组合代码是新候选，必须重过完整门禁。
5. 交付候选 gates、`selection.json`、本轮/累计 effect 摘要；退出循环时交付 `final-functional-regression.md`、`final-performance-comparison.md`、`final_optimized/` 与归档身份。主 Agent 复核、登记状态并决定进入下一轮或后处理。

需要调用工具时使用 `$PLUGIN_ROOT/scripts/`；写进度或提交保存点时按需读取 `$PLUGIN_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
