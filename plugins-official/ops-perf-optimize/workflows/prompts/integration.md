# 后处理任务模板

仅在 `ROLE=integration` 时读取，派发给独立的通用 subagent（加载 `ops-perf-postprocess`），不能复用前处理实例。注册与直调输入均适用。

```text
ROLE: integration
TASK_KIND: integrate-and-prevent-regressions
PLUGIN_ROOT: <resolved absolute plugin root>
REQUEST: <optimization-request.json absolute path>
RUN_MANIFEST: <run-manifest.json absolute path>
WORKFLOW_STATE: <workflow-state.json absolute path>
TUNING_MODE: <standard|generalization>
TARGET_SOCS: <exact list from RUN_MANIFEST>
ROUND: absent
CODE_DIR: <original project absolute path, restricted to frozen integration scope>
KB_ROOT: <cannbot-knowledge knowledge root for analysis/implementation, or absent>
INPUT_ARTIFACTS:
  <final_optimized, ARCHIVE_MANIFEST.md and full demo validation reports>
  <functional-full inventory, performance-full inventory and performance-targets.json>
  <extraction-manifest.json, original snapshot and source-compatibility.md>
  <final candidate frozen source-isolation scope/gate>
  <optimized-involved-cases.csv and ratio evidence when applicable>
OUTPUT_ARTIFACTS:
  <INTEGRATION_PLAN.md and SOC_COMPATIBILITY_MATRIX.md>
  <integration-safety-scope.json and source-isolation-integration.json, frozen before edits>
  <integration-safety-gate.json and source/build/loaded-binary evidence>
  <before/after functional and performance full-inventory precision and profiling evidence; expected-error rows have before/after semantic results rather than kernel time>
  <postprocess-performance-SoC.json for every target SoC>
  <regression-routing.md and guard/legacy boundary verification>
  <VERIFY_REPORT.md and final integrated source archive>
  <uninvolved-cases-verification.md for generalization>
ACCEPTANCE:
  <original invocation preserved; public API/constraints/dtypes have zero diff; safety gates pass; no edits to non-target chip-family implementations/dependencies; both full inventories pass strict/conditional precision and have no effective performance regressions on every target SoC; regressed predicates execute original code and the final routed binary has been fully revalidated; no-op requires original-identity full coverage evidence>
CONDITIONAL_SKILLS:
  <ascendc-mc2-best-practice for confirmed MC²/multi-rank input; CANN-Bench only when requested>
```

按 `ops-perf-postprocess` 的执行参考与工程技能 `references/writeback.md` 执行。generalization 涉及/不涉及路由核验与原有抽检扩样仍保留，不能替代两类全集精度和性能检查。

泛化附加路由抽检为稳定 ID 的 5%，至少 10 条、不足则全选；失败扩大到 20%，仍失败则全量。
