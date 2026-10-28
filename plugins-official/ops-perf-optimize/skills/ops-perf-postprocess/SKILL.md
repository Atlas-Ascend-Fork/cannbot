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

## AscendC 执行与交付

1. 读取 [postprocessing.md](references/postprocessing.md)，核对最终 demo 全集证据、剥离映射、原快照、兼容矩阵和冻结集合。
2. 按 [writeback.md](references/writeback.md) 执行回写；计划提交主 Agent 冻结后实施，注册/直调均保持原入口。发现原工程并发改动先返回冲突证据。
3. 加载 共享源码隔离路由（`$WORKFLOW_ROOT/workflows/references/source-isolation.md`）与 `ops-perf-acceptance-criteria` 的精度、性能采集与抖动路由；芯片族归类统一查询 `npu-arch` skill（按其 NpuArch 代际划分归族），A2/A3 共用同一套实现与验证结论，可复用代表 SoC 的证据；其他族归类结论不扩大精确 TARGET_SOCS；回写 diff 中不得写死核数/UB/L2 等硬件参数（同 NpuArch 内取值范围以 npu-arch 硬件参数表核对）。
4. 执行原工程前后功能全集、性能全集精度与逐 case 性能检查；冻结的预期报错行按参考文档检查前后错误语义，不编造 kernel 耗时。有效退化范围按真实输入谓词回原代码，新身份完整复验。无优化时仍交付有覆盖证据的 no-op。
5. generalization 继续涉及/不涉及路由核验并按共享 ratio 复核最终达标；仅用户要求 CANN-Bench 时读取 `$WORKFLOW_ROOT/workflows/cannbench-a5-baseline-collection.md`。
6. 交付安全/精度 gates、每 SoC `postprocess-performance-<soc>.json`、回路由证据和 `VERIFY_REPORT.md`；两个全集无有效回退方可完成，最终报告引用集成后的真实身份。阶段产物写入 `$OUTPUT_DIR/integration/`，交付时更新该文件夹的 `阶段总结.md`（做了什么、成果、关键产物清单、未决项）。

## DSL 执行与交付

1. 回写前核对与回写：核对最终 demo 全集证据、逐文件回写映射与原源码快照；回写映射按文件名逐字节核对，无关同名文件不入候选 diff；发现原工程并发改动先返回冲突证据。计划提交主 Agent 冻结后实施，保持原 Python 入口与公开契约。
2. 回到原 Python 调用链一次验收：功能用例就是性能用例，同一冻结集合先按原 pytest/checker/golden 判精度，再按统一采集协议做 before/after 性能对比，不另造额外验证集，整体越快越好。before/after 用 canonical10_independent proof（先 `--register` 后采集，baseline 绑定既有冻结收据）；回写字节等价且源/编译/加载身份链闭合时，集成层效果结论绑定 demo 正式确认，不重复 20-slot 全量确认。长采集按上方双后端纪律脱离会话执行。
3. 交付每 SoC `postprocess-performance-<soc>.json`、回路由证据、stage=integration 的 `dsl-compile-evidence.json` 与 `VERIFY_REPORT.md`；冻结集合的功能与性能检查无有效回退方可完成，最终报告引用集成后的真实身份。启用 schedule_policy 时按调度契约提交带 integration 链的 runtime conformance gate。细则见 [DSL 回集成](references/dsl-integration.md)。阶段产物写入 `$OUTPUT_DIR/integration/`，交付时更新该文件夹的 `阶段总结.md`（做了什么、成果、关键产物清单、未决项）。

两个后端的长采集（多 case 全集、20 slot 确认、A/B 配对轮）一律按 `ops-perf-acceptance-criteria` 的长采集执行纪律（`performance-collection.md` 与 `msprof-op-effect-evidence.md`）：驱动脚本 `setsid`/`nohup` 脱离会话、逐 case/slot 进度日志与独立证据目录、跳过已完成部分断点续跑、失败 attempt 合规记录；禁止把整段采集放在代理前台单命令内执行。

需要调用工具时使用 `$WORKFLOW_SCRIPTS/`；写进度或提交保存点时按需读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
