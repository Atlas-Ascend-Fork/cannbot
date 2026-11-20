---
name: ops-perf-postprocess
description: 用于将验收后的性能优化 demo 回集成原工程，保护非目标芯片族并对两个全集检查退化及原代码回路由。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 后处理

从派发信封读取 `WORKFLOW_ROOT`、`WORKFLOW_SCRIPTS`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；manifest/state 必须已初始化并通过身份核验。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与未决项，不以对话替代产物。输入缺失、证据身份不一致、阶段前置未满足或缺少写入范围时返回主 Agent，不猜测环境或权限。

信封中的路径均为解析后的绝对路径；调用工作流脚本（`scripts/` 目录下）必须直接使用这些绝对路径，不要把 `$WORKFLOW_ROOT`/`$WORKFLOW_SCRIPTS` 当作环境变量。工作目录内对普通文件的常规相对路径操作不受此限制。

## 语言路由

从已确认的 request（freeze 前）或 manifest.configuration 读取 `backend`，缺省为 `ascendc`。先加载本阶段 Skill 和 `ops-perf-acceptance-criteria` 的共享验证契约，其余技能按本阶段任务调用，使用前完整读取。

- `ascendc`：执行下文的 AscendC 步骤，保留原有 TTK、工程工具及排障要求。
- `cannbot_dsl`：执行下文的 DSL 步骤；共享验证与领域边界见 `ops-perf-acceptance-criteria` 的 [cannbot-dsl.md](../ops-perf-acceptance-criteria/references/cannbot-dsl.md)，功能验证使用原 pytest/checker/golden。原工程包含 Native/AOT、C++ 扩展或注册入口时保留相应工程检查；生成 AscendC 中间代码本身不要求改造为 C++ 注册工程。

启用 schedule_policy 时，两条路径都先读取 [调度契约的回集成要求](../ops-perf-acceptance-criteria/references/async-schedule-contract.md#回集成身份与全集门禁)，准备实际集成 root、全集 scope 和 source/build/load 链，再执行原验收；最终提交带 integration 链的 schedule runtime conformance gate。

两条路径均执行冻结输入、源码隔离、精度、性能与阶段交接门禁；DSL 按其共享验证契约补齐编译及实际加载证据。语言选择只决定具体工具和执行步骤，不授予跳过验收的权限。客户端若自动预加载声明技能，仍按上述适用范围执行。

## 知识回流（两条路径均执行）

后处理把本轮既有产物（`analysis.md`、实施契约、`selection.json`、effect 摘要、构建/加载身份、原始测试/性能证据）整理成回流材料。两条路径均不 commit、不 push，不写 claims/obs/journal：

先读取 [经验提炼与验收](references/experience-reflux.md)：覆盖所有已完成轮次，逐条写适用条件、具体改法及新增成本、观察与归因、采用/避免/重试条件、复核与证伪步骤。结果表和来源清单不足以完成回流。新请求启用 `experience_policy` 时交付 `experience-lessons.json`、由其生成的 `experience-material.md` 和独立阅读的 `experience-review.json`，主端机械重算后才能完成 integration；不改变算子精度或性能终选标准。历史冻结产物不回写。

同时交付 `knowledge-reflux.json`，绑定实际原料卡、已评正文和评审的 SHA；实际回流卡保留完整经验内容。v2 按 [可移植回流交付](references/portable-reflux.md) 补齐脱敏公开副本及 `portable_delivery`，出口通过来源覆盖、脱敏与哈希检查；本地路径不能直接成为公开引用，原料投稿不夹带接收仓的工具/约定修改。

- **本地沉淀**：未安装 CANNBOT_REFINERY 时，写入 `$OUTPUT_DIR/integration/knowledge-reflux/` 供观测。
- **CANNBOT_REFINERY 回流**：已安装时（`REFINERY_ROOT` 可用），按该仓 README 的「整理原料」写入原料架位（四区 `yard/rough/`，旧布局 `rough/`）。

`REFINERY_ROOT` 从 `CANNBOT_REFINERY_ROOT`、工程或祖先 `.cannbot/ops-perf-references.env`，或同级 `cann-refinery` 检出解析。

## AscendC 执行与交付

1. 读取 [postprocessing.md](references/postprocessing.md)，核对最终保留 commit（final 标签）的全集证据、workspace-manifest、兼容矩阵和冻结集合。
2. 按 [merge-protocol.md](references/merge-protocol.md) 执行合并交付：先用 `git_workspace.py merge-check` 判定条件①（fast-forward 等价）/条件②（并发变更）；条件①免两套全集重测（树哈希等价 + 原工程重建产物 SHA 比对 + 按冻结回归验收子集的回归验证 + 证据复用清单），条件②全量复验。发现原工程并发改动先返回冲突证据。计划提交主 Agent 冻结后实施，注册/直调均保持原入口。
3. 加载 共享源码隔离路由（`$WORKFLOW_ROOT/workflows/references/source-isolation.md`）与 `ops-perf-acceptance-criteria` 的精度、性能采集与抖动路由；芯片族归类统一查询 `npu-arch` skill，在现有目标设备上验证并记录实际型号与 NpuArch；审阅同族泛化，不得新增具体型号专属门禁，回写 diff 中不得写死核数/UB/L2 等硬件参数（同族资源差异以实际平台查询处理）。
4. 执行原工程前后功能全集、性能全集精度与逐 case 性能检查；冻结的预期报错行按参考文档检查前后错误语义，不编造 kernel 耗时。冻结策略要求回路由时按真实输入谓词回原代码，新身份完整复验。无优化时仍交付有覆盖证据的 no-op。
5. 仅用户要求 CANN-Bench 时读取 `$WORKFLOW_ROOT/workflows/cannbench-a5-baseline-collection.md`。
6. 交付安全/精度 gates、合并条件分路证据（条件①：`merge-equivalence.json`；条件②：每 SoC `postprocess-performance-<soc>.json`）、回路由证据和 `VERIFY_REPORT.md`；两个全集按冻结效果策略通过方可完成（条件①以身份等价与复用清单替代重测），最终报告引用集成后的真实身份。阶段产物写入 `$OUTPUT_DIR/integration/`。

## DSL 执行与交付

1. 合并前核对与合并交付：核对最终全集证据与 workspace-manifest；按 merge-protocol 把工作分支（final 标签）合并回原工程目标分支，fast-forward 等价/并发变更分路与 AscendC 同构（树哈希 + blob 一致性机器证明替代逐文件移植）；发现原工程并发改动先返回冲突证据，用户工作树脏改动归用户。计划提交主 Agent 冻结后实施，保持原 Python 入口与公开契约。
2. 回到原 Python 调用链一次验收：功能用例就是性能用例，同一冻结集合先按原 pytest/checker/golden 判精度，再按统一采集协议做 before/after 性能对比，不另造额外验证集，整体越快越好。
3. 交付合并条件分路证据（fast-forward 等价：`merge-equivalence.json`；并发变更：每 SoC `postprocess-performance-<soc>.json`）、回路由证据、stage=integration 的 `dsl-compile-evidence.json` 与 `VERIFY_REPORT.md`；冻结集合的功能与性能检查按冻结策略通过方可完成，最终报告引用集成后的真实身份。启用 schedule_policy 时按调度契约提交带 integration 链的 runtime conformance gate。细则见 [DSL 回集成](references/dsl-integration.md)。阶段产物写入 `$OUTPUT_DIR/integration/`。

需要调用工具时使用 `$WORKFLOW_SCRIPTS/`；写进度或提交保存点时按需读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
