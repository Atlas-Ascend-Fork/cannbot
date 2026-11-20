---
name: ops-perf-implementation
description: 实施已选定的 AscendC / CANNBot-DSL 优化方案，完成试测、候选选择和最终回归。仅由 ops-perf-optimize 工作流派发时使用。
---

# 实施验证

在派发的 `CODE_DIR` 中实施本轮方案。输入是 `analysis.md`、`implementation-contract-<scheme_id>.json`、冻结 scope、当前基线与用例；从通用信封和 `workflow_state.py inspect` 取得路径、backend、目标 SoC 与恢复点。

修改范围、公开接口和非目标路径按契约及 `$WORKFLOW_ROOT/workflows/references/source-isolation.md` 执行。使用 run worktree，按 harness-git 协议保存 attempt commit。

## 实施循环

1. 复用基线的构建和测试入口，完成方案修改。工程实际情况与方案有差异时，在契约范围内调整实现并记录原因；需要改变方案或 scope 时交回主 Agent。
2. 用原 golden 对改动相关的代表 case 冒烟，短测性能，根据结果继续修正或保留该次探索。
3. 对准备保留的版本完成冻结功能子集、变更相关的序列测试、实际构建/加载身份和符合性检查。
4. 按冻结性能策略与当前基线比较，保存选择结果。身份、集合和协议一致的构建或采集结果直接复用。

候选选择、工具接口和最终全集验收见 [selection-and-final.md](references/selection-and-final.md)。实施产物写入 `implementation/roundN/`，并直接作为知识回流素材；不额外维护知识文件。主 Agent 根据交接结果登记状态并决定下一步。

## 按问题使用工具

| 当前问题 | 入口 |
|---|---|
| 功能、性能采集与效果判定 | `ops-perf-acceptance-criteria`；[精度规则](../ops-perf-acceptance-criteria/references/precision-policy.md) |
| AscendC 构建与测试 | 基线已有 harness、TTK 标准技能；数值故障使用 `ascendc-precision-debug` |
| DSL 编译、加载与测试 | [DSL 共享契约](../ops-perf-acceptance-criteria/references/cannbot-dsl.md)，原 pytest/checker/golden；保留 `dsl-compile-evidence.json` |
| 实现或 API 证据缺口 | 方案已有 `kb_cards`、`knowledge-query`、目标 SDK 与 `ascendc-docs-search` |
| 同步、资源复用问题 | `ascendc-sync-audit`，结合变更路径的实际测试 |
| 流水、tiling 或优化写法 | `ascendc-perf-optimize`、`ascendc-performance-best-practices`；DSL 使用 `cannbot-dsl-best-practice` |

交接说明实际修改、自检命令与结果、方案偏差和未决问题，并引用源码 commit、构建/加载身份及原始测试与性能结果。
