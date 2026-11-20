# 基线评估任务模板

仅在 `ROLE=baseline` 时读取，派发给通用 subagent（加载 `ops-perf-baseline-evaluate`）。执行 `ops-perf-baseline-evaluate` Skill；需要生成时按需读取 generation 库存变体。

**两次派发结构**（`DISPATCH` 字段区分）：
- `DISPATCH: 1`（定稿）：preflight → freeze/集合接入 → 基线 commit 定稿（基线 = HEAD/upstream 已提交状态；非 git 按 `GIT_INIT` 处置、脏改动按 `DIRTY_POLICY` 处置），交付基线 commit 身份后返回；主 Agent 随后机械调用 `git_workspace.py worktree-add` 建立 run worktree。
- `DISPATCH: 2`（工作区构建、功能基线与采集）：在 run worktree 上构建原实现（构建入口/harness 身份）、建立功能基线（AscendC: TTK 功能验收子集 / DSL: 原 pytest/checker/golden + 编译证据）、执行身份、原实现性能采集与逐 case 目标。

```text
ROLE: baseline
TASK_KIND: finalize-baseline | worktree-build-functional-baseline-and-collect
DISPATCH: 1 | 2
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
  <DISPATCH 1: $OUTPUT_DIR/baseline/baseline.json absolute path (canonical name; commit/tree identity, dirty-state or git-init outcome)>
  <DISPATCH 2: preflight-report.json and 环境检查报告.md absolute paths>
  <DISPATCH 2: run-manifest.json and frozen case inventory absolute paths>
  <DISPATCH 2: workspace-manifest.json, functional-acceptance.md and source-compatibility.md absolute paths>
  <DISPATCH 2: execution-identity.json absolute path when measuring the original implementation>
  <DISPATCH 2: target-evidence.json, performance-targets.json and 性能目标.md absolute paths>
  <DISPATCH 2: unfused_reference.py and unfused chain measurement evidence when requested>
ACCEPTANCE:
  <DISPATCH 1: baseline is the committed state (HEAD or chosen upstream); uncommitted/staged changes never enter the baseline; non-git input follows the frozen GIT_INIT answer (init with first commit, or abort on refusal); dirty changes follow the frozen DIRTY_POLICY (stay in the user worktree by default, audit-patch discard, or abort); user worktree and target branch untouched>
  <DISPATCH 2: dependency/NPU checks have no failures; required inventories ready; all builds, collection and verification happen inside the run worktree, never in the user worktree; original-implementation measurement proves frozen-source → build-artifact → loaded-artifact identity before formal functional or performance collection; functional baseline on the worktree baseline commit classifies strict/conditional per shared precision rules; every full performance case and target SoC has finite positive evidenced reference and target latency; source remains unchanged>
CONDITIONAL_SKILLS:
  <ops-theoretical-performance-estimation for theory; ops-profiling-report for unfused/baseline; ascendc-st-design and ops-precision-standard when generating>
```

`BACKEND=cannbot_dsl` 时采用本阶段 Skill 的 references/dsl-baseline-evaluate.md，共享验证与领域边界见 ops-perf-acceptance-criteria 的 references/cannbot-dsl.md；在 INPUT_ARTIFACTS 追加领域知识原始路径、dsl-environment.json 和当前编译/加载证据。本模板中的 TTK、C++ 模板和注册机械要求仅在真实相关路径启用，保持冻结集合、目标和证据门禁。
