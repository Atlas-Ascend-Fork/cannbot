# 方案实施任务模板

仅在 `ROLE=implementation` 时读取。一个实施验证阶段代理管理最多三份实施契约，每个方案使用独立候选目录；按 `ops-perf-implementation` 调度独立构建/静态检查、排他设备验证和唯一终选。

```text
ROLE: implementation
TASK_KIND: implement-validate-select
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
CODE_DIR: <isolated round workspace absolute path>
KB_ROOT: <absolute cannbot-knowledge repository root containing governance/ and knowledge/, or absent>
INPUT_ARTIFACTS:
  <analysis/roundN/analysis.md absolute path>
  <up to three implementation-contract-<scheme_id>.json absolute paths>
  <frozen schedule contracts and model checks referenced by implementation contracts when policy enabled>
  <functional-acceptance-cases.csv absolute path>
  <working baseline gate and source identity absolute paths>
  <source-compatibility.md and pristine working baseline absolute paths>
  <extraction-manifest.json and frozen source-isolation-<scheme_id>.json absolute paths>
OUTPUT_ARTIFACTS:
  <candidate source and real-build evidence absolute paths>
  <schedule lowering/runtime evidence and checks for current candidate when policy enabled>
  <scheme-conformance.json absolute path>
  <scheme-conformance-gate.json absolute path>
  <candidate safety section inside scheme-conformance-gate.json>
  <dead-code-audit.md absolute path>
  <functional acceptance and sequence-stress evidence absolute paths>
  <eligible candidate profiling, effect summaries and selection.json absolute paths>
  <final-functional-regression.md, final-performance-comparison.md and final_optimized when exiting loop>
  <implementation/阶段总结.md absolute path>
ACCEPTANCE:
  <exact contract conformance; source_isolation gate passes against unchanged frozen scope; shared implementations copied before optimization and independently routed; public API/constraints/dtypes unchanged; non-target SoCs and uninvolved templates unchanged; real target builds; dead-code audit has no UNKNOWN; complete strict_pass or credible conditional_pass; eligible_for_performance is evidence-backed>
CONDITIONAL_SKILLS:
  <skills required by the implementation contract, or absent>
```

不得换成未授权路线、减少 case 或跳过功能门禁。通过序列门禁后按统一协议采集性能，主 Agent 只负责设备排他调度和选择/状态登记。终选后按阶段 Skill 完成 demo 全集验收。

`BACKEND=cannbot_dsl` 时采用本阶段 Skill 的 references/dsl-implementation.md，共享验证与领域边界见 ops-perf-acceptance-criteria 的 references/cannbot-dsl.md；在 INPUT_ARTIFACTS 追加领域知识原始路径、dsl-environment.json 和当前编译/加载证据。本模板中的 TTK、C++ 模板和注册机械要求仅在真实相关路径启用，保持冻结集合、目标和证据门禁。

启用 SCHEDULE_POLICY 时，ACCEPTANCE 追加 [调度契约](../../skills/ops-perf-acceptance-criteria/references/async-schedule-contract.md)：先消费冻结模型，再将 task/edge/buffer/event 映到实际生成代码；核对独立提交顺序、事件 pipe/generation、alias 最后读者、分支计数与启停。runtime 报告绑定候选源码、生成/编译/运行证据和相关边界覆盖；eligible 后才正式测速，合法不代表更快。源码/参数/SDK/输入分支变化须重核相应证据。旧任务缺策略时保持原门禁。
