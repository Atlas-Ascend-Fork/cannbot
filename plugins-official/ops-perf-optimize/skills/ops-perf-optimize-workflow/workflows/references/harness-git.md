# harness git 版本管理协议（贯穿全流程）

本参考定义 git 版本管理的单点协议，由 **harness 机械操作**（`$WORKFLOW_SCRIPTS/git_workspace.py`）与主 Agent 的机械调用承载，**贯穿基线评估、分析、实施与后处理全部阶段及 AscendC/DSL 两个后端**。它不属于任何单一阶段：阶段 Skill 与派发信封引用本协议，语义判断（scope、门禁、路由）留在 validator 和派发方。所有 git 调用钉死 `core.autocrlf=false`，行号与字节口径与仓库记录一致。

## 0. 两条不变量

1. **优化任务的一切构建、采集与验证只在 run worktree 内进行，绝不使用用户工作树**——这同时保证目录不被污染与基线采集的身份正确。
2. **用户工作树上的脏改动归用户**：合并回写时若用户脏改动与合并文件冲突，git 拒绝合并是正确行为，提示用户先处理（提交/stash/丢弃），不代为处置、不覆盖。

## 1. 基线 commit 定稿（基线评估阶段，git 管理的起点）

**基线 = 原工程的已提交状态（HEAD，或用户显式选择的 upstream 状态）。未提交/暂存区改动不得进入基线。**

启动时（基线评估定稿步骤）检测 `git status`：

| 情形 | 处置 | 命令 |
|---|---|---|
| 非 git 目录 | 按 request 冻结的 `GIT_INIT` 询问结果：同意 → 原地 `git init` + 首 commit 作基线（只新增 `.git`，不动任何文件，可逆；配置仓内局部 git 身份，不碰全局配置）；拒绝 → 终止并列出待办 | `git_workspace.py init --code-dir <dir> --out <json>` |
| 有未提交/暂存区改动 | 按 request 冻结的 `DIRTY_POLICY` 执行：**(b) 留在用户工作树（默认）**——脏改动原地不动、不进优化范围，报告"脏文件 ∩ 算子闭包"交集警告；**(d) 存 patch 丢弃**——审计 patch 存 run 目录后清理用户工作树至 HEAD（仅用户显式选择时执行）；**(c) 终止**——用户先自行整理 | `git_workspace.py prepare-baseline --repo <repo> --run-dir <run-dir> --option b --closure-files <json> --out <json>`（或 `--option d`） |
| 工作树干净 | 基线即 HEAD | `git_workspace.py prepare-baseline --repo <repo> --run-dir <run-dir> --out <json>`（默认即 `--option b`） |

处置结果、patch 路径与清单记入事件日志，不静默消失。基线 commit 是本次优化的起点树身份，也是最终交付 diff 的基准（`git diff <baseline_commit>..<final_tag>`）。

## 2. run worktree（主 Agent 机械调用）

- 全 run **仅一个 worktree**（`<run-dir>/worktree/`），跨轮复用，后处理合并交付后清理：`git_workspace.py worktree-add --repo <repo> --branch perf-opt/<run-id>/work --from <baseline_commit> --path <run-dir>/worktree --out <json>`。
- **调用时机**：基线评估定稿步骤返回基线 commit 后、原实现构建/采集派发前，由**主 Agent 机械调用**（与调用 `workflow_state.py` 同类，不算替代阶段执行），调用结果登记进状态事件流与 `workspace-manifest.json`。
- 创建后必须核验 `verified_tree_sha` == 基线树哈希。
- **恢复**：从中断保存点恢复时先核对 worktree HEAD 树哈希与保存点登记一致；不一致时按第 4 节丢弃协议处理预期外改动，或把该保存点转 `invalid`。
- 移除：`git_workspace.py worktree-remove --path <worktree> --out <json>`；有未提交改动时拒绝，须先丢弃（存 patch）或显式 `--force`。
- 工作分支保留作审计；`workspace-manifest.json`（基线 commit/worktree/构建/harness 身份）作为基线评估阶段交付物由构建步骤补全。

## 3. commit 语义与线性历史（两个后端同构）

- 工作分支 `perf-opt/<run-id>/work` 保持**严格线性**：一次 commit = 一次完整优化尝试（attempt）。commit message 约定 `perf-opt(rN): <scheme_id> <一句话摘要>`。**AscendC 与 DSL 均使用本模型**（DSL 不再使用逐方案物理副本）。
- **回退到历史节点**：在新 commit 中包含"超前提交的 revert + 新尝试"，不使用 git 分叉。revert 冲突按保留实现语义解决，解决内容视为新改动，重过该轮全部门禁。被淘汰尝试的 commit 留在历史中（审计链）。
- attempt 元数据（attempt_id、branch、revert_of、gate 引用）落盘到 `selection.json` 的 attempt 记录，不依赖会话记忆。

## 4. 开发期丢弃协议（预期外改动）

每个 attempt commit 前必须执行：

1. `git status` / `git diff --stat` 与冻结 scope 的允许文件清单比对；
2. 预期外改动先存 patch（`git_workspace.py discard-unexpected --worktree <worktree> --allow-list <scope 解析的路径集> --patch-out <patch.json> --out <json>`，tracked 存 patch、untracked 备份后移除；worktree 建立时已注入构建产物 exclude，编译/打包产物不会进入此清单）；
3. 丢弃清单入事件日志。不执行本步不得 commit；commit 后发现预期外改动属流程违规，须 revert 重做。

## 5. 最终标签与交付身份

- 退出循环后打 final 标签：`perf-opt/<run-id>/final` 指向最终保留 commit。
- 交付 diff = `git diff <baseline_commit>..<final_tag>`；回集成映射不再是逐文件对照表。
- 合并交付按 [merge-protocol](../../ops-perf-postprocess/references/merge-protocol.md) 执行（fast-forward 等价快速路径 / 并发变更全量复验）。

## 6. 隔离模式（唯一主路径 + 对拍 oracle）

- **git 模式是两个后端的唯一主路径**：scope schema v2（`baseline_commit` + `baseline_tree_sha`），门禁（`validate_source_isolation.py` / `validate_implementation_conformance.py` / `validate_integration_safety.py`）git 模式传 `--git-repo/--baseline-rev/--candidate-rev`，evidence 从 commit 读取。
- **目录模式仅为 validator 对拍 oracle 与测试基线**（非交付路径）：22 个对拍测试用目录模式交叉验证 git 模式的判定一致性；不作为任何后端的交付流程。
