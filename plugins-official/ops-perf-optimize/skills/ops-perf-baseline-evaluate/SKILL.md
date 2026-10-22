---
name: ops-perf-baseline-evaluate
description: 用于已接收的算子性能任务：检查环境/NPU、冻结或生成用例并产出逐 case 对标目标。仅执行基线评估阶段。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 基线评估

从派发信封读取 `PLUGIN_ROOT`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；基线 freeze 前 manifest/state 可为 pending。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与缺口。缺少输入或写入范围时返回主 Agent。

## 执行与交付

1. 确认 REQUEST 已存在且已获用户确认；读取 [input-freezing.md](references/input-freezing.md) 执行依赖预检、freeze 和集合接入。确认意图由主 Agent 完成，本阶段不重复询问已有信息。
2. 读取 [baseline-evaluation.md](references/baseline-evaluation.md) 完成环境报告与逐 case 目标。原实现实测时，正式功能或性能采集之前先建立并验证 `execution-identity.json`，证明冻结源码、构建产物和实际加载产物属于同一实现。
3. 仅需要生成库存时读取 [case-generation.md](references/case-generation.md)，使用 `ascendc-st-design` 和 `ops-precision-standard`；generalization 另外读取 [generalization-inputs.md](references/generalization-inputs.md)。
4. 竞品/其他算力卡性能由用户提供文件接入（见 [baseline-evaluation.md](references/baseline-evaluation.md)）；理论上限使用 `ops-theoretical-performance-estimation`（当前仅 Ascend950 纯 Vector）；原实现/小算子实测先加载 `ops-perf-acceptance-criteria` 的性能采集路由。
5. 交付 `preflight-report.json`、`环境检查报告.md`、冻结集合、`performance-targets.json` 和 `性能目标.md`；原实现实测另交 `execution-identity.json`。无 fail 且所有目标/库存就绪才能交接；缺来源或模型不支持则返回证据缺口。

需要调用工具时使用 `$PLUGIN_ROOT/scripts/`；写进度或提交保存点时按需读取 `$PLUGIN_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
