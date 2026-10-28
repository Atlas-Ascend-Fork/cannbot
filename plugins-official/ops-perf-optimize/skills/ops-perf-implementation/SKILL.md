---
name: ops-perf-implementation
description: 用于性能任务的隔离方案实施、功能与性能门禁、候选终选及最终 demo 全集验收。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 实施验证

从派发信封读取 `WORKFLOW_ROOT`、`WORKFLOW_SCRIPTS`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；manifest/state 必须已初始化并通过身份核验。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与未决项，不以对话替代产物。输入缺失、证据身份不一致、阶段前置未满足或缺少写入范围时返回主 Agent，不猜测环境或权限。

信封中的路径均为解析后的绝对路径；调用工作流脚本（`scripts/` 目录下）必须直接使用这些绝对路径，不要把 `$WORKFLOW_ROOT`/`$WORKFLOW_SCRIPTS` 当作环境变量。工作目录内对普通文件的常规相对路径操作不受此限制。

## 语言路由

从已确认的 request（freeze 前）或 manifest.configuration 读取 `backend`，缺省为 `ascendc`。先加载本阶段 Skill 和 `ops-perf-acceptance-criteria` 的共享验证契约，其余技能按本阶段任务调用，使用前完整读取。

- `ascendc`：执行下文的 AscendC 步骤，保留原有 TTK、工程工具及排障要求。
- `cannbot_dsl`：执行下文的 DSL 步骤；共享验证与领域边界见 `ops-perf-acceptance-criteria` 的 [cannbot-dsl.md](../ops-perf-acceptance-criteria/references/cannbot-dsl.md)，功能验证使用原 pytest/checker/golden。

两条路径均执行冻结输入、源码隔离、精度、性能与阶段交接门禁；DSL 按其共享验证契约补齐编译及实际加载证据。语言选择只决定具体工具和执行步骤，不授予跳过验收的权限。客户端若自动预加载声明技能，仍按上述适用范围执行。

## AscendC 执行与交付

1. 读取 [implementation-execution.md](references/implementation-execution.md) 与 [engineering-constraints.md](references/engineering-constraints.md)；消费已冻结方案和 scope，不改原工程或放宽 required features。信封 `KB_ROOT` 存在时，先读取所选方案 `kb_cards` 列出的支撑知识卡并按需经 `knowledge-query` 补充检索实施约束（API 语义、队列同步、精度反模式）；`KB_ROOT` 缺失时标注 `kb_unavailable` 继续，不阻塞实施。调用前先读其 SKILL 与 `references/cli.md`，确认任务目标平台后按当前接口组命令；复用分析阶段的适用卡片与审计，只对新证据缺口重入检索，按该 Skill 记录真实工程验证结果。
2. 按需读取 `$WORKFLOW_ROOT/workflows/references/source-isolation.md` 与 `ops-perf-acceptance-criteria` 的精度、采集和抖动路由；数值与功能故障诊断统一使用 `ascendc-precision-debug`，由本代理执行，不嵌套派发。精度问题按 strict/conditional 规则固定持续执行，失败只影响对应候选。
3. 读取 [selection-and-final.md](references/selection-and-final.md) 执行序列压测、eligible 候选一次性能采集、含 baseline 的唯一终选和 demo 全集验收；generalization 还读取共享 ratio 参考。
4. 每方案独立副本和证据；独立构建/静态检查可并行，设备采集排他。新组合代码是新候选，必须重过完整门禁。
5. 交付候选 gates、`selection.json`、本轮/累计 effect 摘要；退出循环时交付 `final-functional-regression.md`、`final-performance-comparison.md`、`final_optimized/` 与归档身份。主 Agent 复核、登记状态并决定进入下一轮或后处理。阶段产物（候选工程、采集与 effect 均在 `implementation/roundN/`）写入 `$OUTPUT_DIR/implementation/`，交付时更新该文件夹的 `阶段总结.md`（做了什么、成果、关键产物清单、未决项）。

## DSL 执行与交付

1. 按设计方案实现：消费已冻结的实施契约和 scope，逐方案在独立物理副本上修改 Python/tiling/流水，不改原工程、不放宽 required features。实现依据按 `ascendc-performance-best-practices`（公共优化能力 + 族级 `cannbot-dsl/` 语言子目录的 DSL 实践与 KB 分册）与 `cannbot-dsl-best-practice`（局部写法与生产代码正反例）；候选诊断与流水/tiling 复核按 `ascendc-perf-optimize`（语言无关）。按需读取 `$WORKFLOW_ROOT/workflows/references/source-isolation.md`；新组合代码是新候选，必须重过完整门禁。
2. 编译与精度验证：按 cannbot-dsl.md 共享验证契约完成编译与实际加载取证（`dsl-compile-evidence.json`）；用原 pytest/checker/golden 执行冻结 functional_acceptance，按 strict/conditional 记录，新增失败先对照可信原基线再修复或淘汰候选。执行变更相关序列压测（重复/交替 shape、槽位 wraparound、不同进程与缓存命中、metadata 更新/复用）。数值与功能故障诊断优先 DSL 参数/布局/tail/Channel/VF 与编译结果依据，AscendC 排障仅在确认后端生成代码问题时使用；精度问题固定持续执行，失败只影响对应候选。
3. 终选与全集验收：按 [DSL 实施细则](references/dsl-implementation.md) 执行 eligible 候选一次性能采集、含 baseline 的唯一终选与 demo 全集验收，generalization 另按共享 ratio 复核。交付候选 gates、`selection.json`、本轮/累计 effect 摘要；退出循环时交付 `final-functional-regression.md`、`final-performance-comparison.md`、`final_optimized/` 与归档身份。主 Agent 复核、登记状态并决定进入下一轮或后处理。阶段产物（候选工程、采集与 effect 均在 `implementation/roundN/`）写入 `$OUTPUT_DIR/implementation/`，交付时更新该文件夹的 `阶段总结.md`（做了什么、成果、关键产物清单、未决项）。

需要调用工具时使用 `$WORKFLOW_SCRIPTS/`；写进度或提交保存点时按需读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
