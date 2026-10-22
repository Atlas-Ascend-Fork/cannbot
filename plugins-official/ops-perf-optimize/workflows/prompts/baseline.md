# 基线评估任务模板

仅在 `ROLE=baseline` 时读取，派发给通用 subagent（加载 `ops-perf-baseline-evaluate`）。执行 `ops-perf-baseline-evaluate` Skill；需要生成时按需读取 generation 库存变体。

```text
ROLE: baseline
TASK_KIND: environment-cases-targets
PLUGIN_ROOT: <resolved absolute plugin root>
REQUEST: <confirmed optimization-request.json absolute path>
RUN_MANIFEST: <absolute path, or pending before freeze>
WORKFLOW_STATE: <absolute path, or pending before freeze>
TUNING_MODE: <standard|generalization, from REQUEST before freeze>
TARGET_SOCS: <exact list from REQUEST, then RUN_MANIFEST>
ROUND: absent
CODE_DIR: <isolated evaluation workspace absolute path>
KB_ROOT: <cannbot-knowledge knowledge root for analysis/implementation, or absent>
INPUT_ARTIFACTS:
  <original source and existing inventories absolute paths>
  <confirmed reference configuration and any existing reference measurements>
OUTPUT_ARTIFACTS:
  <preflight-report.json and 环境检查报告.md absolute paths>
  <run-manifest.json and frozen case inventory absolute paths>
  <execution-identity.json absolute path when measuring the original implementation>
  <target-evidence.json, performance-targets.json and 性能目标.md absolute paths>
  <unfused_reference.py and unfused chain measurement evidence when requested>
ACCEPTANCE:
  <dependency/NPU checks have no failures; required inventories ready; original-implementation measurement proves frozen-source → build-artifact → loaded-artifact identity before formal functional or performance collection; every full performance case and target SoC has finite positive evidenced reference and target latency; source remains unchanged>
CONDITIONAL_SKILLS:
  <ops-theoretical-performance-estimation for theory; ops-profiling for unfused/baseline; ascendc-st-design and ops-precision-standard when generating>
```
