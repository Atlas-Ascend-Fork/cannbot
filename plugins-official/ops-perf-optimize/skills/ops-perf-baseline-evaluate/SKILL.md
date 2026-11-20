---
name: ops-perf-baseline-evaluate
description: 用于已接收的算子性能任务：检查环境/NPU、定稿基线 commit、在 run worktree 上构建原实现并建立功能基线、冻结或生成用例并产出逐 case 对标目标。仅执行基线评估阶段。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 基线评估

从派发信封读取 `WORKFLOW_ROOT`、`WORKFLOW_SCRIPTS`、`REQUEST`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`CODE_DIR`、`TARGET_SOCS` 和输入/输出路径；基线 freeze 前 manifest/state 可为 pending。只执行当前阶段，返回状态、产物绝对路径、源码/二进制 SHA、门禁与未决项，不以对话替代产物。输入缺失、证据身份不一致、阶段前置未满足或缺少写入范围时返回主 Agent，不猜测环境或权限。

信封中的路径均为解析后的绝对路径；调用工作流脚本（`scripts/` 目录下）必须直接使用这些绝对路径，不要把 `$WORKFLOW_ROOT`/`$WORKFLOW_SCRIPTS` 当作环境变量。工作目录内对普通文件的常规相对路径操作不受此限制。

## 语言路由

从已确认的 request（freeze 前）或 manifest.configuration 读取 `backend`，缺省为 `ascendc`。先加载本阶段 Skill 和 `ops-perf-acceptance-criteria` 的共享验证契约，其余技能按本阶段任务调用，使用前完整读取。

- `ascendc`：执行下文的 AscendC 步骤，保留原有 TTK、工程工具及排障要求。
- `cannbot_dsl`：执行下文的 DSL 步骤；共享验证与领域边界见 `ops-perf-acceptance-criteria` 的 [cannbot-dsl.md](../ops-perf-acceptance-criteria/references/cannbot-dsl.md)，功能验证使用原 pytest/checker/golden。原工程包含 Native/AOT、C++ 扩展或注册入口时保留相应工程检查；生成 AscendC 中间代码本身不要求改造为 C++ 注册工程。

两条路径均执行冻结输入、源码隔离、精度、性能与阶段交接门禁；DSL 按其共享验证契约补齐编译及实际加载证据。语言选择只决定具体工具和执行步骤，不授予跳过验收的权限。客户端若自动预加载声明技能，仍按上述适用范围执行。

## AscendC 执行与交付（两次派发结构）

**派发 1（定稿）**：确认 REQUEST 已存在且已获用户确认；读取 [input-freezing.md](references/input-freezing.md) 执行依赖预检、freeze 和集合接入。确认意图由主 Agent 完成，本阶段不重复询问已有信息。随后按 harness-git 协议（`$WORKFLOW_ROOT/workflows/references/harness-git.md`）定稿基线 commit：**基线 = 原工程已提交状态（HEAD，或用户显式选择的 upstream 状态），未提交/暂存区改动不进基线**；非 git 目录按 request 冻结的 `GIT_INIT` 处置（同意 → `git_workspace.py init` 原地初始化并以首 commit 作基线；拒绝 → 终止）；脏改动按 `DIRTY_POLICY` 处置（默认 (b) 留在用户工作树；可选 (d) 存 patch 丢弃 / (c) 终止）。定稿产物返回主 Agent 后，主 Agent 机械调用 `git_workspace.py worktree-add` 建立 run worktree（登记进事件流与 `workspace-manifest.json`），再派发派发 2。

**派发 2（工作区构建、功能基线与采集）**：
1. 读取 [baseline-evaluation.md](references/baseline-evaluation.md) 完成环境报告与逐 case 目标；按 [harness.md](references/harness.md) 在 worktree 基线 commit 上就绪构建入口与 runner，构建原实现。
2. 原实现实测时，正式功能或性能采集之前先建立并验证 `execution-identity.json`，证明冻结源码、构建产物和实际加载产物属于同一实现。
3. 加载 TTK 标准 skill（`ttk-how-run-test`，排障用 `ttk-how-diagnose`）在 worktree 基线 commit 上执行完整功能验收子集，按 `ops-perf-acceptance-criteria` 精度规则分类 strict/conditional；已知原始失败依工作流规则分类，不直接终止。盘点产出 `source-compatibility.md`（工程支持 SoC、公开契约面、共享文件/模板分支与使用者，只陈述源码事实）。
4. 仅需要生成库存时读取 [case-generation.md](references/case-generation.md)，使用 `ascendc-st-design` 和 `ops-precision-standard`；generalization 另外读取 [generalization-inputs.md](references/generalization-inputs.md)。
5. 竞品/其他算力卡性能由用户提供文件接入（见 [baseline-evaluation.md](references/baseline-evaluation.md)）；理论上限使用 `ops-theoretical-performance-estimation`（当前仅 Ascend950 纯 Vector）；原实现/小算子实测先加载 `ops-perf-acceptance-criteria` 的性能采集路由。
6. 交付 `preflight-report.json`、`环境检查报告.md`、冻结集合、`performance-targets.json`、`性能目标.md`、`workspace-manifest.json`、`functional-acceptance.md`、`source-compatibility.md`；原实现实测另交 `execution-identity.json`。无 fail 且所有目标/库存就绪、strict_pass 或可信 conditional_pass 才能交接；缺来源或模型不支持则返回证据缺口。阶段产物写入 `$OUTPUT_DIR/baseline/`。

## DSL 执行与交付（两次派发结构，与 AscendC 同构）

**派发 1（定稿）**：`preflight_dependencies.py` 按 backend 检查 DSL 包、Python/pytest、CANN/毕昇 与设备（不能用 `--skip-device` 的静态报告宣称上板条件就绪），保存 `dsl-environment.json` 并登记身份；随后按 harness-git 协议（`$WORKFLOW_ROOT/workflows/references/harness-git.md`）定稿基线 commit（HEAD/upstream 已提交状态；GIT_INIT/DIRTY_POLICY 同 AscendC），返回基线 commit 后主 Agent 机械调用 worktree-add 建立 run worktree，再派发派发 2。

**派发 2（工作区构建、功能基线与采集）**：
1. 在 worktree 上建立编译/加载证据（`dsl-compile-evidence.json`，collection=functional_acceptance），并用原 pytest/checker/golden 执行完整功能验收子集（原实现身份），strict/conditional 分类，产出 `functional-acceptance.md` 与 `workspace-manifest.json`。
2. 原实现实测时先建立并验证 execution identity（source→build→loaded 同源链），再用同一套用例按共享采集协议采基线；`build_performance_targets.py` 生成精确 case×SoC 目标，用户给定目标/竞品不被自基线替换，理论模型缺失时标缺口，不将 Cube/Mix 塞进纯 Vector 模型。DSL 功能用例就是性能用例：一套冻结集合同时服务功能判定与性能采集，不另造独立功能验证集；原测试优先使用 existing 库存，确有缺口才补必要边界。
3. 交付 `preflight-report.json`、`环境检查报告.md`、冻结集合、`performance-targets.json`、`性能目标.md`、`dsl-environment.json`、`workspace-manifest.json`、`functional-acceptance.md`；无 fail 且目标/库存就绪、strict_pass 或可信 conditional_pass 才能交接。细则见 [DSL 基线评估](references/dsl-baseline.md)。阶段产物写入 `$OUTPUT_DIR/baseline/`。

需要调用工具时使用 `$WORKFLOW_SCRIPTS/`；写进度或提交保存点时按需读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。保持现有 phase/round/gen 键，代码与证据身份不变时复用已有结果。阶段内不加载主编排 Skill `ops-perf-optimize-workflow` 或其他阶段 Skill；工程机械能力与共享验证能力按上述路由调用。
