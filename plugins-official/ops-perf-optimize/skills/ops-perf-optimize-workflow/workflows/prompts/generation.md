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
BACKEND: <ascendc|cannbot_dsl; frozen request/manifest value>
DSL_REPO_ROOT: <frozen dsl.repo_root for DSL, otherwise absent>
DSL_ENTRYPOINT: <frozen dsl.entrypoint for DSL, otherwise absent>
DSL_EXECUTION_MODE: <jit|aot for DSL, otherwise absent>
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

`BACKEND=cannbot_dsl` 时采用本阶段 Skill 的 references/dsl-generation.md，共享验证与领域边界见 ops-perf-acceptance-criteria 的 references/cannbot-dsl.md；在 INPUT_ARTIFACTS 追加领域知识原始路径、dsl-environment.json 和当前编译/加载证据。本模板中的 TTK、C++ 模板和注册机械要求仅在真实相关路径启用，保持冻结集合、目标和证据门禁。
