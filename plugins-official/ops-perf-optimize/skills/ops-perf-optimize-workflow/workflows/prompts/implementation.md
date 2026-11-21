# 方案实施任务

使用 [通用信封](../task-prompts.md)，填入本阶段目标、输入和验收结果。

```text
ROLE: implementation
TASK_KIND: implement-validate-select
INPUT_ARTIFACTS:
  <analysis.md, implementation-contract-<scheme_id>.json and frozen source-isolation scope>
  <previous rounds' analysis.md and selection.json absolute paths, or absent>
  <adopted distill cards and operator-case references cited by the analysis, or unavailable reason>
  <current/original baseline identities, workspace-manifest and frozen cases>
  <schedule model/checks when schedule_policy is enabled>
OUTPUT_ARTIFACTS:
  <attempt commit, real build/load identity and actual test/performance results>
  <scheme-conformance.json, scheme-conformance-gate.json for the retained candidate>
  <selection.json and round/cumulative effect summaries>
  <selection.json, effect summaries, build/load identity and raw test/performance evidence, which are also the knowledge-reflux material; no separate knowledge field or file>
  <final-functional-regression.md, final-performance-comparison.md and final tag when exiting>
ACCEPTANCE:
  <implementation matches the frozen contract and scope; public API/constraints/dtypes unchanged>
  <selection follows ops-perf-implementation; measured or screened results cite actual artifacts>
  <existing implementation artifacts record actual measurements, prediction misses, retained/rejected attempts and failure classification; no separate knowledge field/file is created and no data is written into KB_ROOT/distill/book or REFINERY_ROOT>
CONDITIONAL_SKILLS:
  <tools needed for the current implementation or diagnosis>
```

DSL 使用原测试与编译入口；启用 schedule_policy 时交付当前候选的 runtime conformance。

`BACKEND=cannbot_dsl` 时，`CONDITIONAL_SKILLS` 必须包含 `cannbot-dsl-best-practice`。实施代理在开始修改前完整读取该 Skill，并将实际采用的 DSL 写法、适用边界和版本事实记录到现有交接产物中。
