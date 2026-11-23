# 版本迁移

输入身份变化返回 `stale_inputs`，必须新建 run；仅工作流版本变化先做影响审计，只失效受影响保存点。

两种模式恢复旧版本时：旧 `registry-to-direct`/`gen.baseline.convert` 保存点不满足本版准备契约；登记迁移审计，使其及依赖该工程/二进制的下游证据失效，重新剥离并建立基线，不改写历史记录。旧候选缺冻结 source-isolation scope 时不得事后补写免责清单，需重新分析并验证；冻结用例和独立竞品证据可复用。

升级到 execution identity 版（v12）时，原实现实测只有在既有证据已经同时包含冻结源码、本次构建产物和实际加载产物的可核对同源链时才能复用，并用统一脚本生成 `execution-identity.json`；不能从彼此独立的 SHA、文件名、时间戳或历史安装状态补推血缘。缺少该链时只失效原实现的功能与性能证据，冻结请求、集合以及独立的 xpu/theoretical/unfused 证据继续有效。

升级到五阶段版（v11）时，登记迁移审计：旧工程角色的 preparation/integration 分别路由到新前处理/后处理角色，生成归入基线评估。身份不变的剥离、profiling、精度与方案证据可复用；缺少逐 case 目标、功能全集性能检查或后处理路由证据的阶段不得直接认定完成，补齐新增门禁。旧注册抽检与 demo 性能不能冒充原工程两类全集性能；不覆盖历史事件、不重置泛化内外层计数。

升级到 v10 逐轮性能报告版时，迁移审计记录新增报告字段；已有采集和门禁不因报告格式变化失效。按原轮次顺序用已有性能 CSV 生成或复用 effect 摘要，重新登记轮次完成保存点；旧保存点缺摘要时报告明确显示待补齐，不推测性能数值，也不为刷新报告重新 profiling。

v11 的入口调整不改变 request、manifest 和阶段键：原来因入口要求而完整读取主流程的 subagent 改为加载对应阶段 Skill；身份未变的证据不因文件迁移重新采集。旧引用通过阶段 Skill 的当前入口恢复，禁止恢复旧版整份工作流上下文。

升级到 git 原生版（v13，`unified-workflow-v13-git-native`）时，登记迁移审计并按以下规则处理旧 run：

- 旧 `phase.preparation` 保存点（剥离 demo、`extraction-manifest.json`、原源码快照）**失效**：不满足 worktree/基线 commit 准备契约；重新定稿基线 commit（按 request 已确认的脏改动处置）并重建 worktree 后续接。`source-compatibility.md` 内容可参考但身份需随新基线重建。
- 旧 scope v1（`baseline_files` 全量快照）在 git 模式校验器下不再被接受：重新按 scope v2（`baseline_commit` + `baseline_tree_sha`）生成，行级范围可保留；DSL 目录模式继续使用 v1。
- 冻结集合、竞品数据、精度诊断记录、执行身份链完整的两套全集性能证据**可复用**（与源码管理机制无关）。
- 旧 integration 保存点（桶A/B 移植产物）**失效**：非 commit 身份无法做 fast-forward 等价；未开始的 integration 从当前代码状态按 merge-protocol 重走。
- `optimization_objective.rounds` 缺省解释从 3 改 5（与上游搜索决策合入后的新默认一致；显式值不变）；泛化 `inner_max_rounds` 维持上游合同值 3。v13 开发期间曾短暂采用 9 轮默认，合入上游单方案搜索（三次停滞触发重规划）后由 5 轮默认替代；旧 manifest 显式记录的轮数按冻结值保留。
- 每轮候选数合同改为恰一份：旧多候选历史记录保留原样，不重写；恢复后按单候选继续。
- **执行身份层过渡设计（显式标注）**：v13 的 git 原生化覆盖 preparation/implementation/integration 的源码事实，但执行身份链（`validate_execution_identity.py`）的源码主键仍是 source-tree-v1 目录树哈希，manifest 中 git 身份（head_commit/dirty_files）仅为附加事实——为 DSL/非 git 输入与历史证据复用保留，属已知双重口径。旧 `preparation/original_snapshot` 字节归档不再产出；集成后重验执行身份用 `git archive <基线 commit>` 导出作等价归档（与冻结哈希逐字节一致）。执行身份链的 git 主键化列为后续可优化项。
- 迁移不重置泛化内外层计数、不覆盖历史事件、不改写旧报告；缺 worktree 身份的旧 run 不得直接标 complete。

升级到四阶段 git 统一版（v14，`four-stage-v1`）时，登记迁移审计并按以下规则处理旧 run：

- **前处理阶段移除**：git 版本管理是 harness 贯穿机制（协议 `workflows/references/harness-git.md`），基线定稿移入基线评估派发 1（两次派发：定稿 → 采集，派发间主 Agent 机械调用 worktree-add），worktree 构建/TTK/原测试功能基线与 source-compatibility 归入基线评估派发 2。旧 `phase.preparation` 保存点**失效**：已完成的 workspace-manifest/functional-acceptance/source-compatibility 归档可参考，身份与产物需按新阶段契约重新登记（同一 worktree 身份未变时可复用证据）。
- **基线定义变更**：基线 = 原工程已提交状态（HEAD/upstream）；旧 (a) 快照分支基线的 run 保留历史证据，交付 diff 仍按其冻结基线 commit 计算，不重写历史。
- **脏改动默认处置**：(a) 快照分支选项删除；新默认 (b) 留在用户工作树。旧 request 冻结的 (a) 处置按冻结值保留（已定稿的快照基线有效）。
- **DSL git 统一**：DSL 候选从逐方案物理副本改为 worktree attempt commit、scope v1→v2；旧 DSL 副本身份的保存点失效，按 git 身份重走对应阶段。
- 旧 manifest `five-stage-v1`：in-flight 恢复沿用旧布局的阶段键读取（`phase.preparation` 记录被忽略，不再派发），新 run 一律 `four-stage-v1`；泛化内外层计数不重置、历史事件不覆盖。
- **调度契约按需开启**：新请求默认不再冻结 `schedule_policy`（显式 `--schedule-policy` 才启用）；旧 request 已冻结的按冻结值继续生效。
- **身份快照 git-tree-v1**：git 仓输入的源码身份改为临时索引树哈希（O(改动集)，尊重 .gitignore）；旧 `source-tree-v1` 身份按其原方法复验，不重写。

仅旧 state writer 漏存 request/manifest 已冻结的 schedule_policy 且尚未开始 analysis 等受约束活动时，可显式 `migrate-workflow --adopt-schedule-policy`；必须非空审计、原 manifest SHA 不变和冻结 request 匹配。具体命令、前置条件与拒绝范围见 [调度策略补登记](../../ops-perf-acceptance-criteria/references/async-schedule-contract.md#显式补登记已冻结策略)。普通新任务无需此迁移，历史本无策略或已进入后续阶段不能借此升级或补验。

升级到逐 case 收敛账本版（schema 4）时，`case_convergence` 为附加字段，不改 `WORKFLOW_VERSION`、不失效任何保存点：

- 账本由脚本在每个性能保存点完成时自动重算，旧 state 缺字段时在 `case-ledger`/`finish` 惰性重建；推不出结论的 case 一律记 `pending`/`headroom_open`，宁可不收敛，不可误收敛。
- 收紧的门禁只作用于新写入的终态：收敛类 reason code 与 `scope=per_case` 的 `completed` 要求账本完全了结（`optimized`/`converged`/`waived`）；旧 run 的既有终态不回溯重判，重开后改用 `budget_exhausted` 驻留，或以 `case-converge`/`remaining-work` 推进未了结 case。
- **验收口径（issue #205 纠偏）**：新 request 的 `target` 目标携带 `scope: per_case | aggregate`，create-request 默认 `per_case`；旧 request 无 scope 按 `aggregate` 解释以保持兼容。
- 逐 case verdict 与搜索失败记忆（`case_bucket`）为可选字段，旧 frontier/selection 不带时按原全集语义解释；`freeze` 对 `fixed_rounds` 轮数与调优集规模失配仅输出 `advisories`，不阻塞。
