---
name: ops-perf-preparation
description: 用于性能任务的独立 demo 前处理：保持调用方式剥离工程，建立构建/加载证据并用 TTK 验证基线精度。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 前处理

从派发信封读取 `WORKFLOW_ROOT`、`WORKFLOW_SCRIPTS`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；manifest/state 必须已初始化并通过身份核验。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与未决项，不以对话替代产物。输入缺失、证据身份不一致、阶段前置未满足或缺少写入范围时返回主 Agent，不猜测环境或权限。

信封中的路径均为解析后的绝对路径；调用工作流脚本（`scripts/` 目录下）必须直接使用这些绝对路径，不要把 `$WORKFLOW_ROOT`/`$WORKFLOW_SCRIPTS` 当作环境变量。工作目录内对普通文件的常规相对路径操作不受此限制。

## 语言路由

从已确认的 request（freeze 前）或 manifest.configuration 读取 `backend`，缺省为 `ascendc`。先加载本阶段 Skill 和 `ops-perf-acceptance-criteria` 的共享验证契约，其余技能按本阶段任务调用，使用前完整读取。

- `ascendc`：执行下文的 AscendC 步骤，保留原有 TTK、工程工具及排障要求。
- `cannbot_dsl`：**DSL 调优不执行前处理：backend=cannbot_dsl 时主 Agent 不派发本阶段，状态登记 skipped**。原因与去向：DSL 程序为纯 Python，无需工程剥离/demo 工程构建；源码隔离由实施阶段逐方案独立物理副本落地；冻结功能库存由基线评估维护（功能用例即性能用例）；编译/加载证据按 `ops-perf-acceptance-criteria` 的 `references/cannbot-dsl.md` 在实施与回集成交接时取证。

两条路径均执行冻结输入、源码隔离、精度、性能与阶段交接门禁；DSL 按其共享验证契约补齐编译及实际加载证据。语言选择只决定具体工具和执行步骤，不授予跳过验收的权限。客户端若自动预加载声明技能，仍按上述适用范围执行。

## AscendC 执行与交付

1. 读取 [preparation.md](references/preparation.md)，确认基线评估产物和冻结功能库存已完成。
2. 按 [extraction.md](references/extraction.md) 建立独立工作工程；原工程与共享 SDK 只读，保持原调用方式和算法。
3. 读取 `$WORKFLOW_ROOT/workflows/references/source-isolation.md` 与 `ops-perf-acceptance-criteria` 的精度路由，再用 TTK 标准 skill（`ttk-how-run-test`）执行完整功能验收子集。harness 使用共享采集协议；MC² 按 `ascendc-mc2-best-practice`。已知原始失败依工作流规则分类，不直接终止。
4. 交付 demo、`extraction-manifest.json`、`source-compatibility.md`、原源码快照、构建/加载证据及 `functional-acceptance.md`。strict_pass 或可信 conditional_pass 才可交接。阶段产物写入 `$OUTPUT_DIR/preparation/`，交付时更新该文件夹的 `阶段总结.md`（做了什么、成果、关键产物清单、未决项）。

需要调用工具时使用 `$WORKFLOW_SCRIPTS/`；写进度或提交保存点时按需读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
