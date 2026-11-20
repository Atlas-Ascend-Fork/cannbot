# 合并交付协议

在独立后处理专家收到 `ROLE=integration` 时读取（两个后端同构适用）。交付 = 工作分支（final 标签）合并回原工程目标分支；未接纳最终优化时交付有证据的 no-op。DSL 的编译/加载复验细节按 [dsl-integration.md](dsl-integration.md) 执行。本协议的步骤不授予其他阶段修改原工程的权限。

## 输入与前置条件

1. `FINAL_COMMIT`：最终保留 commit（final 标签 `perf-opt/<run-id>/final` 所指），及其功能/性能全集验收报告（`final-functional-regression.md`、`final-performance-comparison.md`）。
2. `WORKSPACE_MANIFEST`：`workspace-manifest.json`（仓库、基线 commit、worktree、构建入口与 harness 身份）。
3. `SOURCE_COMPATIBILITY`：`source-compatibility.md`（支持 SoC/共享文件/模板分支盘点）。
4. `RUN_MANIFEST`：锁定 `TARGET_SOCS` 与集合身份。
5. `VALIDATE_INTEGRATION_SAFETY` / `GIT_WORKSPACE`：`$WORKFLOW_SCRIPTS/validate_integration_safety.py` 与 `$WORKFLOW_SCRIPTS/git_workspace.py` 的绝对路径。
6. 最终候选的冻结 source-isolation scope（fast-forward 等价时直接复用）。

缺任一前置证据或 SHA 不匹配时停止并报告，不重新生成用例、不替代最终验收。

## 职责边界

本阶段只做：解析最终保留 commit → 判定合并条件 → 执行合并（或 no-op 登记）→ 代码安全门禁 → 条件性复验 → 报告。

不做：

- 把 demo 性能当作原工程交付性能；身份完全相同的已有证据按复用规则处理；
- 生成/修改功能用例，或在规定范围外重新抽样；
- 重新选择性能算法方案；性能退化时按工作流生成可验证的原始代码回路由；
- 人工"移植/重写"已验收代码——忠实性由 blob 一致性机器校验保证。

机械接线经验（模板轴、TilingKey、host 路由、命名四位一致、内置同名早检、vendor 打包）见 [`integration-mechanics.md`](integration-mechanics.md)；该参考描述的是"在注册工程里挂新模板"的坑，与合并方式无关，仍然适用。

## 条件分路判定

判定与验证时序（merge-check 是**合并后**验证工具，其 fast-forward 等价判定为“目标分支当前 HEAD == 最终保留 commit”）：

1. 可先用 `git merge-base --is-ancestor <target HEAD> <final commit>` 预判目标分支是否未被推进；
2. 执行 `git merge --ff-only <final commit>`：成功 → 条件①（合并后目标 HEAD == final commit）；失败（分叉）→ 条件②，按下方全量复验路径处理冲突；
3. 合并后用 `$WORKFLOW_SCRIPTS/git_workspace.py merge-check --repo <repo> --candidate-rev <final commit> --target-branch <branch> --baseline-rev <workspace 基线 commit> ...` 产出证据。

- **条件①（fast-forward 等价）**：合并后树 == 验收树（树哈希机器可证），原工程身份 == 验收身份，两套全集性能**免重测**，执行下方快速路径。
- **条件②（并发变更）**：目标分支被用户/他人推进过，合并树 ≠ 验收树。**必须**对合并后的新身份完整重跑两套全集与三门禁，执行下方“全量复验路径”。有冲突时报用户决策，不覆盖用户改动。

## 快速路径（条件①：fast-forward 等价）

1. **树哈希与 blob 等价证明**：`merge-check --baseline-rev <workspace 基线 commit>` 输出 `tree_identity.equal == true` 且 `blob_identity.mismatches == []`（基线 commit 与最终 commit 之间的全部变更文件，在合并结果与最终 commit 中逐文件 blob 一致——这是对旧"人工逐行移植"纪律的机器化替代）。注意：fast-forward 合并后必须显式传 `--baseline-rev`，缺省的 merge-base 会退化为候选自身、得到空证明（工具会拒绝）。
2. **原工程重建比对**：在原工程环境（原仓库工作目录、原构建入口）重构建一次，比对安装产物 SHA 与最终验收时的产物 SHA 一致（构建确定性证明）；经 `--rebuild-artifact/--accepted-artifact` 传入 merge-check。
3. **回归验证**：通过原入口重跑冻结的回归验收子集（规模与等级由基线评估冻结的功能验收子集契约决定，不在此写死）全部 PASS；回归报告为 JSON 对象且 `result`（或 `status`）字段为 `PASS`（如 `{"result": "PASS"}`），经 `--smoke-report` 传入 merge-check，未 PASS 时 `evidence_reuse_eligible` 为 false。
4. 生成 `merge-equivalence.json`（`git_workspace.py merge-check --repo <repo> --candidate-rev <final> --target-branch <branch> --baseline-rev <基线 commit> --smoke-report <回归报告> --reuse-json <复用清单> --out <json>`），登记证据复用清单：两套全集证据按最终验收身份（final 标签 commit）复用，显式注明 SoC、来源保存点与身份。
5. 任一步不成立（含 smoke FAIL、产物 SHA 不一致）→ 视为条件②，走全量复验路径。

## 全量复验路径（条件②）

1. **重新冻结集成 scope**：并发变更构成新身份，按 `$WORKFLOW_ROOT/workflows/references/source-isolation.md` 对合并前目标分支 HEAD 到最终 commit 的完整 diff 重新生成并冻结 `source-isolation-integration.json`（记录旧 scope 与变更原因）；fast-forward 场景不生成此文件（交付 diff 即候选 diff，复用分析期 scope）。
2. **合并执行**：merge 冲突逐项报告用户决策；不自动解决语义冲突。
3. **三门禁**：`validate_integration_safety.py --git-repo <repo> --baseline-rev <merge 前目标 HEAD> --candidate-rev <merge 后 HEAD> --scope <integration-safety-scope.json> --isolation-scope <source-isolation-integration.json>`，`decision != pass` 时禁止部署与进入复验；`integration-safety-scope.json`（schema v2）的编写规则与 `supported_socs` 精确一致要求不变（见 postprocessing.md 与 integration-mechanics.md）。
4. **两套全集全量复测**：每个目标 SoC 用 `$WORKFLOW_SCRIPTS/validate_postprocess_performance.py` 检查功能全集与性能全集的完整覆盖与逐 case 回退；预期报错行按参考文档检查前后错误语义。退化回路由规则照旧（`route_required` → 谓词分区 → `regression-routing.md` → 新身份完整复验）。
5. **执行身份重验的等价归档**：集成改写原工程目录后，重验执行身份时旧 `preparation/original_snapshot` 字节归档已不存在（v13 准备阶段不再产出）；用 `git archive <基线 commit> | tar -x -C <归档目录>` 导出作为等价字节归档，与冻结的 source-tree-v1 哈希逐字节一致，供 `validate_execution_identity.py` 的 fallback 路径使用。
6. 硬件参数写死检查、泛化涉及/不涉及路由核验照旧（见 postprocessing.md）。

## 验证范围不是支持范围

按 `NpuArch` 族确定源码隔离范围；`TARGET_SOCS` 记录现有设备上的实际验证型号，`SUPPORTED_SOCS` 从目标工程 build config、`SocVersion` 路由、架构目录和入口分派取证。不得用当前设备推断工程只支持该型号。

共享代码被多个 NpuArch 族或模板分支使用时，必须先在最终 commit 中复制副本再单独路由；实施 scope 之外的代码保持不变。审阅代码对同族资源差异的适配，不得新增具体型号专属门禁；非目标族按目标工程已有风格隔离：

- kernel 优先放入工程既有 target 架构目录/编译宏分支，新入口只在 target 编译或分派；legacy kernel 保持不变且对非目标 SoC 可达；
- host tiling 先按工程既有 `SocVersion`、TilingKey 或 build config 选 target 路由；专用 UB/核数/VF 模型不得覆盖共享 legacy 计算；
- 共享入口文件只允许增加 target guard + legacy fallback 接线。

不能从源码证明 target guard 和 non-target fallback 时停止；没有非目标硬件不是放弃隔离的理由。

## no-op 与交付

未接纳优化时交付 no-op 说明：基线 commit 身份的两套全集证据（或同身份复用收据）+ 目标分支未变的证明。

交付 `VERIFY_REPORT.md`：合并条件与判定证据（merge-equivalence 或全量复验 gate）、两侧代码/二进制/入口身份、SoC 兼容矩阵、公开契约 diff 与安全 gate 结论、构建/部署命令、逐 case 结果（条件①为 smoke + 复用清单，条件②为两套全集 gate）、回路由前后证据（如有）、非目标族未变证据、目标达成状态。最终原工程性能仍按 state-reporting 用 `mark --stage integration.performance.<soc> --performance-scope full` 登记（条件① 引用复用证据，条件② 引用复测结果），不把 demo `final.performance` 留作最终集成性能。
