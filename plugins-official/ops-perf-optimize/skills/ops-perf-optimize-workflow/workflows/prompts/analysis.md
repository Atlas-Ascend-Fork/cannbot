# 性能分析任务模板

仅在 `ROLE=analysis` 时读取。每轮只派发一次分析任务，依据 `ops-perf-analysis` 的证据与交付要求，浏览其参考输入概览后结合当前任务自主分析，生成一份可审阅报告及本轮就绪方案的实施契约。

```text
ROLE: analysis
TASK_KIND: round-analysis
WORKFLOW_ROOT: <resolved absolute ops-perf-optimize-workflow skill directory>
WORKFLOW_SCRIPTS: <resolved absolute ops-perf-optimize-workflow/scripts directory>
REQUEST: <optimization-request.json absolute path>
RUN_MANIFEST: <run-manifest.json absolute path>
WORKFLOW_STATE: <workflow-state.json absolute path>
BACKEND: <ascendc|cannbot_dsl; frozen request/manifest value>
DSL_REPO_ROOT: <frozen dsl.repo_root for DSL, otherwise absent>
DSL_ENTRYPOINT: <frozen dsl.entrypoint for DSL, otherwise absent>
DSL_EXECUTION_MODE: <jit|aot for DSL, otherwise absent>
SCHEDULE_POLICY: <frozen manifest.configuration.schedule_policy, or absent for legacy>
TUNING_MODE: <standard|generalization>
TARGET_SOCS: <exact list from RUN_MANIFEST>
ROUND: <N>
CODE_DIR: <current baseline absolute path>
KB_ROOT: <absolute cannbot-knowledge repository root containing governance/ and knowledge/, or absent>
INPUT_ARTIFACTS:
  <standard: performance-tuning-cases.csv absolute path>
  <generalization: analysis/roundN/generalization-tuning-cases.csv, competitor-performance.csv and current ratio-analysis.json absolute paths>
  <current baseline profiling and validation evidence absolute paths, or collection pending>
  <performance-targets.json and 性能目标.md absolute paths>
  <previous selection absolute path, or absent>
  <source-compatibility.md absolute path>
  <extraction-manifest.json absolute path>
  <schedule policy applicability evidence; baseline/reference schedule and compiler evidence when applicable>
  <knowledge brief: purpose and coverage keywords; absolute Query/CLI entries, KB_ROOT and existing coverage/card index; target applicability or unavailable reason>
  <best-practices brief: purpose and coverage keywords; absolute Skill, target-family/architecture and common capability indexes; target applicability or unavailable reason>
  <optimization-method brief: purpose and coverage keywords; absolute Skill and Tiling/inter-card/inter-core/single-core indexes; applicability or unavailable reason>
  <AscendC only — MC2 brief: purpose and coverage keywords; absolute Skill, capability declaration and route indexes; target/communication applicability or unavailable reason>
  <AscendC only — static-review brief: purpose and coverage keywords; absolute Skill and checkpoint index; target applicability or unavailable reason>
  <AscendC only — API-docs brief: purpose and coverage keywords; absolute Skill, API/example indexes and target SDK paths; target applicability or unavailable reason>
OUTPUT_ARTIFACTS:
  <analysis/roundN/analysis.md absolute path>
  <analysis/roundN/implementation-contract-<scheme_id>.json absolute paths>
  <analysis/roundN/source-isolation-<scheme_id>.json absolute paths>
  <schedule-contract-<scheme_id>.json and model schedule-check-<scheme_id>.json when policy enabled>
  <analysis/阶段总结.md absolute path>
ACCEPTANCE:
  <profiling and artifact identities valid; every frozen tuning case appears exactly once; each case reports MBU/MFU/cost_bound/ceiling_us/headroom/verdict via ops-profiling compute_efficiency (cost model registered or --flops/--bytes; peaks per TARGET_SOCS, not defaults); required per-case analysis evidence complete; proposed schemes respect the verdict (no non-quant reshuffle candidates padded under NEAR-BANDWIDTH-CEILING / NEAR-COMPUTE-CEILING); each case ALSO reports the operator's intrinsic-minimum-cost roofline (weights crossed HBM once + necessary IO + minimal FLOP, excluding current-impl intermediate round-trips and precision-compensation FLOP) alongside the current-impl roofline; when measured > ceiling_intrinsic*1.5 or behind REFERENCE_PERF, the report MUST include >=1 structural/architecture-level direction (fuse-away intermediates / data layout / precision scheme / internal format conversion; public contract & invocation unchanged) as a candidate or an evidence-based infeasibility argument (hard gate under OPTIMIZATION_INTENT=pursue_optimal, else record direction + estimated gain for user decision); zero schemes require explicit convergence_eligible yes/no, evidence for each infeasible direction and bounded next evidence when no; every strategy maps bidirectionally to non-empty required features; target SoCs, public contract, non-target SoCs and uninvolved templates preserved; copy/route plan and complete baseline-bound source isolation scope ready for main-agent review and SHA freeze>
CONDITIONAL_SKILLS:
  <skills required by confirmed operator routes, or absent>
```

知识库、最佳实践和优化方法的概览适用于两条 backend；MC²、静态性能检视和 API 文档检索三项仅在 `BACKEND=ascendc` 时随输入提供，`BACKEND=cannbot_dsl` 删除这三行。适用项可直接附摘要，也可引用已有概览文件的绝对路径；分析 Agent 在选择方案前浏览全部适用概览。主 Agent 使用已安装 Skill 的说明与索引准备概览，列出代表性覆盖关键词，注明目标平台、语言及已知覆盖；关键词帮助定位资料，不证明任意组合已有覆盖。来源缺失也保留对应适用项并说明原因，不要求为准备概览遍历全文或额外采集。Agent 根据概览和当前证据择优选方案，按需深读或复用已有结论；平台/API/同步与特殊路线检查按实际代码触发，不由资料选择决定。

输入中的 standard/generalization 两行是互斥分支，只保留与 manifest 一致的一行。先复用或采集一次当前基线；简单 profile 不足以支撑瓶颈分析时，在采集阶段按 `ops-perf-profile-feature-extractor` 补齐流水图，已有同身份有效图可复用，不能以聚合利用率代替。再只读分析；分析不得重采性能、重选 case 或修改源码。

启用 `manifest.configuration.search_policy` 时，在 INPUT_ARTIFACTS 传入当前参考身份、上轮 selection 和相关失败/机制证据；ACCEPTANCE 增加 [搜索决策](../../../ops-perf-acceptance-criteria/references/architecture-search.md) 的单方案、父实现、已接受依赖、触发证据与重试条件校验。`inspect.search.next_action=replan` 时，本次先完成架构复盘并交主 Agent 登记，不能直接重试已停滞方向。

MC²/多 rank 和各特殊算子族的路由按阶段 Skill 与共享验证规则执行，不得降级为通用 application 分析。

`BACKEND=cannbot_dsl` 时采用本阶段 Skill 的 references/dsl-analysis.md，共享验证与领域边界见 ops-perf-acceptance-criteria 的 references/cannbot-dsl.md；在 INPUT_ARTIFACTS 追加领域知识原始路径、dsl-environment.json 和当前编译/加载证据，已有诊断流水图同时提供 case/tiling/核数/编译身份及覆盖范围。本模板中的 TTK、C++ 模板和注册机械要求仅在真实相关路径启用，保持冻结集合、目标和证据门禁。

DSL 的 ACCEPTANCE 必须追加 [方案净收益评估](../../skills/ops-perf-analysis/references/dsl-benefit-assessment.md) 的要求：候选方向先完成可行性与净收益评估，覆盖每个方案的全部冻结调优 case × SoC；同一 analysis.md 包含关键路径、新增成本、候选耗时/收益区间或 unknown、目标贡献、可信度、处置及否定条件。ready_for_implementation 才生成实施契约，needs_probe 先完成已登记的隔离诊断，deferred 保留理由与重新评估条件。未知量不充当收敛证据；估计不参与正式候选选择。主 Agent 审阅评估与完整调用计时范围后冻结 scope。

启用 SCHEDULE_POLICY 时，ACCEPTANCE 追加 [调度契约](../../skills/ops-perf-acceptance-criteria/references/async-schedule-contract.md)：同一 analysis.md 引用 A1 独立程序有序微任务、A2 data/resource/reuse/容量/事件/unknown 与 A3 候选；模型报告和方案引用身份吻合。主 Agent 核验 applicability，候选不能自报不适用绕过。关键同步未知须 probe；纯性能 unknown 可 ready，MODEL_FEASIBLE 不自动等于 ready。使用 [三层模板](../../skills/ops-perf-analysis/references/async-schedule-templates.md)，不固定 lag/depth，不虚构 DSL API。
