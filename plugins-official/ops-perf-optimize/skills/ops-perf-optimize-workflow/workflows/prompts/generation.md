# 用例设计与生成任务模板

仅由 `ROLE=baseline` 在需要生成库存时读取，由 baseline 的通用 subagent 执行，不是独立派发角色。用例设计专家只设计并生成库存；冻结、attach 和验收子集选择仍由基线评估代理调用确定性脚本完成。

## Standard 功能库存

```text
ROLE: baseline
TASK_KIND: standard-functional-inventory
WORKFLOW_ROOT: <resolved absolute ops-perf-optimize-workflow skill directory>
WORKFLOW_SCRIPTS: <resolved absolute ops-perf-optimize-workflow/scripts directory>
REQUEST: <optimization-request.json absolute path>
RUN_MANIFEST: <run-manifest.json absolute path>
WORKFLOW_STATE: <workflow-state.json absolute path>
TUNING_MODE: standard
TARGET_SOCS: <exact list from RUN_MANIFEST>
ROUND: absent
CODE_DIR: <source code absolute path>
KB_ROOT: <absolute cannbot-knowledge repository root containing governance/ and knowledge/, or absent>
INPUT_ARTIFACTS:
  <operator interface absolute path>
  <performance-full-cases.csv absolute path>
OUTPUT_ARTIFACTS:
  <functional-full inventory absolute path>
  <functional-generation.json absolute path>
ACCEPTANCE:
  <stable case IDs; complete coverage metadata; trusted golden, comparator and tolerances; atomic outputs>
CONDITIONAL_SKILLS:
  absent
```

仅在 `FUNCTIONAL_MODE=generate` 时使用。生成完成后调用 `attach-functional`，不得重选或缩减验收子集。

## Generalization 性能/功能合一库存

```text
ROLE: baseline
TASK_KIND: generalization-combined-inventory
WORKFLOW_ROOT: <resolved absolute ops-perf-optimize-workflow skill directory>
WORKFLOW_SCRIPTS: <resolved absolute ops-perf-optimize-workflow/scripts directory>
REQUEST: <optimization-request.json absolute path>
RUN_MANIFEST: <run-manifest.json absolute path>
WORKFLOW_STATE: <workflow-state.json absolute path>
TUNING_MODE: generalization
TARGET_SOCS: <exact list from RUN_MANIFEST>
ROUND: absent
CODE_DIR: <source code absolute path>
KB_ROOT: <absolute cannbot-knowledge repository root containing governance/ and knowledge/, or absent>
INPUT_ARTIFACTS:
  <operator interface and generation constraints absolute paths>
OUTPUT_ARTIFACTS:
  <generalization-full-cases.csv absolute path>
  <functional-generation.json absolute path>
ACCEPTANCE:
  <each stable case ID contains performance inputs and trusted functional oracle metadata; contract coverage and target count are met; atomic outputs>
CONDITIONAL_SKILLS:
  absent
```

生成完成后调用 `attach-generalization`，也不得另造语义不同的功能全集。
