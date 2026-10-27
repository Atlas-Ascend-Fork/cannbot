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
TUNING_MODE: <standard|generalization>
TARGET_SOCS: <exact list from RUN_MANIFEST>
ROUND: <N>
CODE_DIR: <isolated round workspace absolute path>
KB_ROOT: <absolute cannbot-knowledge repository root containing governance/ and knowledge/, or absent>
INPUT_ARTIFACTS:
  <roundN/analysis.md absolute path>
  <up to three implementation-contract-<scheme_id>.json absolute paths>
  <functional-acceptance-cases.csv absolute path>
  <working baseline gate and source identity absolute paths>
  <source-compatibility.md and pristine working baseline absolute paths>
  <extraction-manifest.json and frozen source-isolation-<scheme_id>.json absolute paths>
OUTPUT_ARTIFACTS:
  <candidate source and real-build evidence absolute paths>
  <scheme-conformance.json absolute path>
  <scheme-conformance-gate.json absolute path>
  <candidate safety section inside scheme-conformance-gate.json>
  <dead-code-audit.md absolute path>
  <functional acceptance and sequence-stress evidence absolute paths>
  <eligible candidate profiling, effect summaries and selection.json absolute paths>
  <final-functional-regression.md, final-performance-comparison.md and final_optimized when exiting loop>
ACCEPTANCE:
  <exact contract conformance; source_isolation gate passes against unchanged frozen scope; shared implementations copied before optimization and independently routed; public API/constraints/dtypes unchanged; non-target SoCs and uninvolved templates unchanged; real target builds; dead-code audit has no UNKNOWN; complete strict_pass or credible conditional_pass; eligible_for_performance is evidence-backed>
CONDITIONAL_SKILLS:
  <skills required by the implementation contract, or absent>
```

不得换成未授权路线、减少 case 或跳过功能门禁。通过序列门禁后按统一协议采集性能，主 Agent 只负责设备排他调度和选择/状态登记。终选后按阶段 Skill 完成 demo 全集验收。
