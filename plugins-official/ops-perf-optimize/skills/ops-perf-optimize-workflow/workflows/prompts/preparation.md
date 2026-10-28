# 准备任务模板

仅在 `ROLE=preparation` 时读取，派发给通用 subagent（加载 `ops-perf-preparation`）。本阶段工程步骤、harness 协议和功能门禁以 `ops-perf-preparation` 和共享验证规则为准。

```text
ROLE: preparation
TASK_KIND: extract-single-operator
WORKFLOW_ROOT: <resolved absolute ops-perf-optimize-workflow skill directory>
WORKFLOW_SCRIPTS: <resolved absolute ops-perf-optimize-workflow/scripts directory>
REQUEST: <optimization-request.json absolute path>
RUN_MANIFEST: <run-manifest.json absolute path>
WORKFLOW_STATE: <workflow-state.json absolute path>
BACKEND: <ascendc|cannbot_dsl; frozen request/manifest value>
DSL_REPO_ROOT: <frozen dsl.repo_root for DSL, otherwise absent>
DSL_ENTRYPOINT: <frozen dsl.entrypoint for DSL, otherwise absent>
DSL_EXECUTION_MODE: <jit|aot for DSL, otherwise absent>
TUNING_MODE: <standard|generalization>
TARGET_SOCS: <exact list from RUN_MANIFEST>
ROUND: absent
CODE_DIR: <isolated preparation workspace absolute path>
KB_ROOT: <absolute cannbot-knowledge repository root containing governance/ and knowledge/, or absent>
INPUT_ARTIFACTS:
  <original project and target operator absolute paths>
  <mode-specific frozen case inventory and performance-targets.json>
OUTPUT_ARTIFACTS:
  <single-operator working baseline absolute path>
  <extraction-manifest.json absolute path>
  <real-build, dependency-closure and loaded-binary evidence absolute paths>
  <harness identity evidence absolute path>
  <TTK functional-acceptance.md and acceptance-run-manifest.json absolute paths>
  <source-compatibility.md and original source snapshot absolute paths>
  <preparation/阶段总结.md absolute path>
ACCEPTANCE:
  <registry input becomes a standalone custom registry project; direct input becomes a standalone direct project; invocation and kernel/tiling/public semantics preserved; original source SHA unchanged; no source/build dependency on the original repository; target and supported SoCs evidence-mapped; shared source and template users inventoried; real target builds and loaded artifact identity proven>
CONDITIONAL_SKILLS:
  <ascendc-mc2-best-practice for confirmed MC²/multi-rank input, otherwise absent>
```

已有独立工程也要复制到工作区并验证闭包；已有合规构建/harness 可复用。只完成工程剥离，不优化、不采集性能、不把注册调用替换成直调。前处理代理必须加载 TTK 标准 skill（`ttk-how-run-test`）执行工作基线完整功能验收子集，按 strict/conditional 分类；全部证据通过才返回阶段完成。
`BACKEND=cannbot_dsl` 时本阶段不派发（DSL 前处理默认跳过）；冻结功能库存由基线评估维护，编译/加载证据按 ops-perf-acceptance-criteria 的 references/cannbot-dsl.md 在实施与回集成交接时取证。本模板中的 TTK、C++ 模板和注册机械要求仅在真实相关路径启用，保持冻结集合、目标和证据门禁。
