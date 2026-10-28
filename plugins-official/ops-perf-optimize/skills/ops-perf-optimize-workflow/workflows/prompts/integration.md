# 后处理任务模板

仅在 `ROLE=integration` 时读取，派发给独立的通用 subagent（加载 `ops-perf-postprocess`），不能复用前处理实例。注册与直调输入均适用。

```text
ROLE: integration
TASK_KIND: integrate-and-prevent-regressions
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
ROUND: absent
CODE_DIR: <original project absolute path, restricted to frozen integration scope>
KB_ROOT: <absolute cannbot-knowledge repository root containing governance/ and knowledge/, or absent>
INPUT_ARTIFACTS:
  <final_optimized, ARCHIVE_MANIFEST.md and full demo validation reports>
  <functional-full inventory, performance-full inventory and performance-targets.json>
  <extraction-manifest.json, original snapshot and source-compatibility.md>
  <final candidate frozen source-isolation scope/gate>
  <final model/runtime schedule contracts, checks and conformance evidence when policy enabled>
  <optimized-involved-cases.csv and ratio evidence when applicable>
OUTPUT_ARTIFACTS:
  <INTEGRATION_PLAN.md and SOC_COMPATIBILITY_MATRIX.md>
  <integration-safety-scope.json and source-isolation-integration.json, frozen before edits>
  <integration-safety-gate.json and source/build/loaded-binary evidence>
  <before/after functional and performance full-inventory precision and profiling evidence; expected-error rows have before/after semantic results rather than kernel time>
  <postprocess-performance-SoC.json for every target SoC>
  <actual integrated-root schedule runtime conformance gate with integration identity/full-scope postprocess chain when policy enabled>
  <regression-routing.md and guard/legacy boundary verification>
  <VERIFY_REPORT.md and final integrated source archive>
  <uninvolved-cases-verification.md for generalization>
  <integration/阶段总结.md absolute path>
ACCEPTANCE:
  <original invocation preserved; public API/constraints/dtypes have zero diff; safety gates pass; no edits to non-target chip-family implementations/dependencies; both full inventories pass strict/conditional precision and have no effective performance regressions on every target SoC; regressed predicates execute original code and the final routed binary has been fully revalidated; no-op requires original-identity full coverage evidence>
CONDITIONAL_SKILLS:
  <ascendc-mc2-best-practice for confirmed MC²/multi-rank input; CANN-Bench only when requested>
```

按 `ops-perf-postprocess` 的执行参考与工程技能 `references/writeback.md` 执行。generalization 涉及/不涉及路由核验与原有抽检扩样仍保留，不能替代两类全集精度和性能检查。

泛化附加路由抽检为稳定 ID 的 5%，至少 10 条、不足则全选；失败扩大到 20%，仍失败则全量。

`BACKEND=cannbot_dsl` 时采用本阶段 Skill 的 references/dsl-integration.md，共享验证与领域边界见 ops-perf-acceptance-criteria 的 references/cannbot-dsl.md；在 INPUT_ARTIFACTS 追加领域知识原始路径、dsl-environment.json 和当前编译/加载证据。本模板中的 TTK、C++ 模板和注册机械要求仅在真实相关路径启用，保持冻结集合、目标和证据门禁。

启用 SCHEDULE_POLICY 时，派发前即读取 [回集成调度要求](../../skills/ops-perf-acceptance-criteria/references/async-schedule-contract.md#回集成身份与全集门禁)。ACCEPTANCE 增加实际集成 root 的 source/build/load、冻结全集与所有目标 SoC 原 postprocess gates 交叉核验，以及逐 case/SoC/branch 的运行证据；提交带 integration 链的 runtime conformance gate。换 root 创建当前身份的 model/runtime/conformance；同 root 同身份才可复核复用。实施目录旧 gate 不能替代回集成验收。
