# 后处理任务模板

仅在 `ROLE=integration` 时读取，派发给独立的通用 subagent（加载 `ops-perf-postprocess`）。注册与直调输入均适用。

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
EXPERIENCE_POLICY: <frozen manifest.configuration.experience_policy, or absent for legacy>
TUNING_MODE: <standard|generalization>
TARGET_SOCS: <exact list from RUN_MANIFEST>
ROUND: absent
CODE_DIR: <original project absolute path, restricted to frozen integration scope>
KB_ROOT: <absolute cannbot-knowledge repository root containing governance/ and knowledge/, or absent>
REFINERY_ROOT: <optional absolute cann-refinery checkout for knowledge reflux (four-zone or legacy layout); or absent>
INPUT_ARTIFACTS:
  <final tag commit identity and full final validation reports (both backends)>
  <functional-full inventory, performance-full inventory and performance-targets.json>
  <workspace-manifest.json (ascendc) or extraction mapping (dsl) and source-compatibility.md>
  <final candidate frozen source-isolation scope/gate>
  <final model/runtime schedule contracts, checks and conformance evidence when policy enabled>
  <optimized-involved-cases.csv and ratio evidence when applicable>
  <every analysis/round*/analysis.md and implementation/round*/selection.json absolute path>
OUTPUT_ARTIFACTS:
  <merge plan and SOC_COMPATIBILITY_MATRIX.md>
  <merge-equivalence.json with tree/blob identity, rebuild SHA comparison, L0 smoke result and evidence-reuse list (fast-forward path)>
  <integration-safety-scope.json and source-isolation-integration.json, frozen before merge on the concurrent-change path>
  <integration-safety-gate.json and source/build/loaded-binary evidence>
  <before/after functional and performance full-inventory precision and profiling evidence on the concurrent-change path; expected-error rows have before/after semantic results rather than kernel time>
  <postprocess-performance-SoC.json for every target SoC on the concurrent-change path>
  <actual integrated-root schedule runtime conformance gate with integration identity/full-scope postprocess chain when policy enabled>
  <regression-routing.md and guard/legacy boundary verification>
  <local knowledge-reflux folder under $OUTPUT_DIR/integration/knowledge-reflux/ when REFINERY_ROOT is absent, or raw-material cards under the detected cann-refinery layout (yard/rough/ or rough/) when present>
  <analysis reads KB_ROOT/distill/book but never writes it>
  <experience-lessons.json and generated experience-material.md covering all completed rounds; independent experience-review.json supplied by a separate reviewer when EXPERIENCE_POLICY enabled>
  <knowledge-reflux.json binding the actual raw card, complete reviewed material and review by path/SHA; final card must preserve the full reviewed body>
  <VERIFY_REPORT.md and final integrated source identity>
ACCEPTANCE:
  <original invocation preserved; public API/constraints/dtypes have zero diff; safety gates pass; no edits to non-target chip-family implementations/dependencies; fast-forward path proves tree/blob identity, rebuild artifact SHA equality and full L0 smoke pass with an evidence-reuse list; concurrent-change path proves both full inventories pass strict/conditional precision and pass the frozen performance effect policy on every target SoC; regressed predicates execute original code and the final routed binary has been fully revalidated; no-op requires original-identity full coverage evidence; reflux used the existing analysis and implementation artifacts: when REFINERY_ROOT is available it followed cann-refinery README 整理原料 and wrote only the detected raw-material intake; otherwise it wrote the local knowledge-reflux folder under $OUTPUT_DIR/integration/knowledge-reflux/; no commit or push was made in either path>
CONDITIONAL_SKILLS:
  <ascendc-mc2-best-practice for confirmed MC²/multi-rank input; CANN-Bench only when requested>
```

AscendC 按 `ops-perf-postprocess` 的执行参考与合并交付协议 `references/merge-protocol.md` 执行（先 `git_workspace.py merge-check` 判定 fast-forward 等价/并发变更条件分路）。

经验回流按 [经验提炼与验收](../../../ops-perf-postprocess/references/experience-reflux.md) 执行。作者先交 bundle 和正文，主端再派未参与编写的通用 subagent 独立阅读：输入只含实际正文、该参考的量表与必要原件，不给期望答案；先只读正文作 apply/reject/retry/uncertainty 决策题，再核对原件，输出绑定当前SHA的 experience-review.json。ACCEPTANCE 增加经验门禁通过且原料正文保留全部经验。作者不能自行填独立评审；低分先修具体缺口，换正文必须重新评审。语义评分不声称独立NPU作证。新请求在未提交三件经验产物及绑定实际回流卡的 knowledge-reflux.json 时不能完成integration；主端重查实际卡保留完整正文。

`BACKEND=cannbot_dsl` 时采用本阶段 Skill 的 references/dsl-integration.md，共享验证与领域边界见 ops-perf-acceptance-criteria 的 references/cannbot-dsl.md；在 INPUT_ARTIFACTS 追加领域知识原始路径、dsl-environment.json 和当前编译/加载证据。本模板中的 TTK、C++ 模板和注册机械要求仅在真实相关路径启用，保持冻结集合、目标和证据门禁。

启用 SCHEDULE_POLICY 时，派发前即读取 [回集成调度要求](../../../ops-perf-acceptance-criteria/references/async-schedule-contract.md#回集成身份与全集门禁)。ACCEPTANCE 增加实际集成 root 的 source/build/load、冻结全集与所有目标 SoC 原 postprocess gates 交叉核验，以及逐 case/SoC/branch 的运行证据；提交带 integration 链的 runtime conformance gate。换 root 创建当前身份的 model/runtime/conformance；同 root 同身份才可复核复用。实施目录旧 gate 不能替代回集成验收。
