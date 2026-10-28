# 基线评估任务模板

仅在 `ROLE=baseline` 时读取，派发给通用 subagent（加载 `ops-perf-baseline-evaluate`）。执行 `ops-perf-baseline-evaluate` Skill；需要生成时按需读取 generation 库存变体。

```text
ROLE: baseline
TASK_KIND: environment-cases-targets
WORKFLOW_ROOT: <resolved absolute ops-perf-optimize-workflow skill directory>
WORKFLOW_SCRIPTS: <resolved absolute ops-perf-optimize-workflow/scripts directory>
REQUEST: <confirmed optimization-request.json absolute path>
RUN_MANIFEST: <absolute path, or pending before freeze>
WORKFLOW_STATE: <absolute path, or pending before freeze>
BACKEND: <ascendc|cannbot_dsl; frozen request/manifest value>
DSL_REPO_ROOT: <frozen dsl.repo_root for DSL, otherwise absent>
DSL_ENTRYPOINT: <frozen dsl.entrypoint for DSL, otherwise absent>
DSL_EXECUTION_MODE: <jit|aot for DSL, otherwise absent>
TUNING_MODE: <standard|generalization, from REQUEST before freeze>
TARGET_SOCS: <exact list from REQUEST, then RUN_MANIFEST>
ROUND: absent
CODE_DIR: <isolated evaluation workspace absolute path>
KB_ROOT: <absolute cannbot-knowledge repository root containing governance/ and knowledge/, or absent>
INPUT_ARTIFACTS:
  <original source and existing inventories absolute paths>
  <confirmed reference configuration and any existing reference measurements>
OUTPUT_ARTIFACTS:
  <preflight-report.json and 环境检查报告.md absolute paths>
  <run-manifest.json and frozen case inventory absolute paths>
  <execution-identity.json absolute path when measuring the original implementation>
  <target-evidence.json, performance-targets.json and 性能目标.md absolute paths>
  <unfused_reference.py and unfused chain measurement evidence when requested>
  <baseline/阶段总结.md absolute path>
ACCEPTANCE:
  <dependency/NPU checks have no failures; required inventories ready; original-implementation measurement proves frozen-source → build-artifact → loaded-artifact identity before formal functional or performance collection; every full performance case and target SoC has finite positive evidenced reference and target latency; source remains unchanged>
CONDITIONAL_SKILLS:
  <ops-theoretical-performance-estimation for theory; ops-profiling for unfused/baseline; ascendc-st-design and ops-precision-standard when generating>
```

`BACKEND=cannbot_dsl` 时采用本阶段 Skill 的 references/dsl-baseline-evaluate.md，共享验证与领域边界见 ops-perf-acceptance-criteria 的 references/cannbot-dsl.md；在 INPUT_ARTIFACTS 追加领域知识原始路径、dsl-environment.json 和当前编译/加载证据。本模板中的 TTK、C++ 模板和注册机械要求仅在真实相关路径启用，保持冻结集合、目标和证据门禁。
