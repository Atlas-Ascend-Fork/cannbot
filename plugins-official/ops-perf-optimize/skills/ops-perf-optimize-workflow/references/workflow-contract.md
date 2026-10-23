# 性能优化编排契约

本文是阶段顺序、派发、输入输出、失败路由、循环和完成条件的唯一工作流真源。各阶段 Skill 定义执行方法，`ops-perf-acceptance-criteria` 定义跨阶段验证口径；主 Agent 不加载全部阶段细则。

## 1. 事实与职责

`optimization-request.json` 保存已确认意图；`run-manifest.json` 冻结本次请求、源码、环境、集合与 SHA；`workflow-state.json` 保存阶段、证据身份、诊断与决策；`性能调优报告.md` 是持续生成的现场和终稿视图。同一事实只写一次，不另建进度 JSON、双份多轮汇总或逐轮同名报告。

各阶段统一派发**当前环境的通用 subagent**，信封声明 `ROLE` 并要求加载对应阶段 Skill；阶段职责、流程与验收以各 Skill 为唯一真源：

| 阶段 / ROLE | 派发方式 | 执行 Skill |
|---|---|---|
| 基线评估 / `baseline` | 通用 subagent + 加载 `ops-perf-baseline-evaluate` | `ops-perf-baseline-evaluate` |
| 前处理 / `preparation` | 通用 subagent + 加载 `ops-perf-preparation` | `ops-perf-preparation` |
| 诊断分析 / `analysis` | 通用 subagent + 加载 `ops-perf-analysis` | `ops-perf-analysis` |
| 实施验证 / `implementation` | 通用 subagent + 加载 `ops-perf-implementation` | `ops-perf-implementation` |
| 后处理 / `integration` | 通用 subagent + 加载 `ops-perf-postprocess` | `ops-perf-postprocess` |

前处理和后处理分别定义、使用独立实例，通过文件映射和证据交接。用例生成归 baseline；同一实施代理管理最多三份隔离方案，独立构建/静态检查可并行。主 Agent 负责请求接入、设备排他调度、scope 冻结、门禁复核、选择登记、恢复和报告，不制定优化算法或修改候选。

## 2. 请求接入

已有 request：`$WORKFLOW_SCRIPTS/prepare_case_sets.py validate-request` 校验后复用。缺少或失效时按 [request-intake.md](request-intake.md) 收集代码、精确 TARGET_SOCS、模式、用例、对标来源、停止目标、优化意图、可选性能锚点、Python/CANN 环境，生成用户已确认的 request。无交互环境必须提供已确认 request，不猜测环境或目标。

`OPTIMIZATION_INTENT`（`safe_incremental` 默认 / `pursue_optimal`）与 `REFERENCE_PERF` 是可选输入身份，写入 request/manifest：前者决定是否把**结构性重写**（融合/数据布局/精度方案/内部格式转换，公开契约仍不变）纳入方案空间并放宽"最小 scope"偏好；后者是同算子/同族更优实现或竞品的 `case_id,ref_total_us`（或参考实现工程路径，由 prepare 采同协议基线），提供后分析以"实测 vs 参考"的差距为绝对参照，缺省则以算子内在最小成本 roofline 为唯一普适锚点。

交给 baseline 执行依赖/NPU 检查与集合冻结。环境有 fail 时禁止 freeze；warn 有理由可继续。`existing/reuse_performance` 使用确定性脚本，生成是可选动作。性能调优子集超过上限的确认提案由 baseline 返回主 Agent，确认后继续，不静默重选。仅性能对标卡不同不自动切换为 generalization。

baseline 允许在 freeze 前以 REQUEST 派发，此时 RUN_MANIFEST/WORKFLOW_STATE 为 pending；freeze 后初始化状态。后续合法 attach/confirm 必须 sync-manifest；未声明的身份变化为 stale_inputs。主 Agent 串行接入集合更新，不让多个代理并发修改 manifest。

## 3. 阶段交接

| 阶段 | 必要输入 | 输出与放行条件 |
|---|---|---|
| baseline | 已确认 request、原代码/库存、对标配置 | `preflight-report.json`、`环境检查报告.md`、冻结集合、`performance-targets.json`、`性能目标.md`；原实现实测另有 `execution-identity.json`；环境无 fail，目标精确覆盖性能全集 × TARGET_SOCS，功能库存就绪 |
| preparation | 基线评估产物与原工程 | 独立 demo、`extraction-manifest.json`、`source-compatibility.md`、原快照、构建/加载证据、`functional-acceptance.md`；原调用方式/算法不变，依赖闭包与 TTK 基线 strict/conditional 门禁通过 |
| analysis | 当前可信基线、冻结目标/调优集合、已有性能证据 | 一份 `roundN/analysis.md`、最多三份 `implementation-contract-<scheme_id>.json` 和 source-isolation scope；每个 case 覆盖，方案收益与目标差额有证据对应，方案 exact/forbidden，主 Agent 冻结 scope |
| implementation | 冻结方案/scope、当前与原始基线、用例/目标 | 每候选符合性/安全/构建/精度/序列门禁、eligible 性能、`selection.json`、本轮/累计 effect；退出循环时另交最终功能/性能全集报告和 `final_optimized/` |
| integration | 最终 demo 与验收证据、原快照/映射、两个全集 | 集成计划/scope、安全与加载证据、两个全集精度/性能、每 SoC `postprocess-performance-<soc>.json`、回路由复验、`VERIFY_REPORT.md`；原入口保持、非目标族不变、无有效性能退化 |

阶段返回 `status`、产物绝对路径、代码/二进制 SHA、门禁结论、未决证据与下一动作。主 Agent 检查实际文件和 gate，不能把文字“完成”当作验收。脚本 gate 证明数值/文件范围，不能替代真实构建、调用链和运行身份审阅。证据身份与覆盖完全相同时复用已有证据，不为确认重复采集。

原实现性能对标在正式功能或性能采集前先通过 execution identity 门禁：冻结源码、本次构建产物与实际加载产物必须形成可复核的同源链。为取得实际加载路径而执行的专用身份探针不产生功能、精度或性能结论。身份不成立时只修正构建或加载路由；不得把该运行的现象归因于冻结源码。身份成立后的基线失败只在本阶段完成故障归类所需的最小复现与对照，根因搜索留给诊断或实施阶段。

派发中的事实必须引用对应身份的证据；待验证的源码路由、完成度或精度解释写成待办，不能写进 ACCEPTANCE 充当已成立前提。父子结论冲突时以冻结输入和实际证据核对差异；不得以派发文字覆盖失败 gate、改变比较器或放宽 scope。能在原授权内补齐的证据由原阶段继续，涉及契约变更才返回主 Agent 决策。

方案 scope 在实施前冻结；原工程 scope 在回写前冻结。原工程有并发变更时先处理冲突与证据差异，不能覆盖用户改动。后处理新增回路由是新候选身份，需重新冻结其范围并完整复验。

## 4. 循环与退出

standard：preparation → 每轮 analysis → implementation → 主 Agent 复核终选及报告 → 下一轮或 integration。最终 demo 全集验收由 implementation 完成。baseline 也参与候选选择，无有效收益时保留 baseline；未实测的拼接代码不参与选择。`expected_effect`、历史 `abandon_if` 和整体优化目标不是候选淘汰条件，有有效净收益的候选即使未达目标也可保留并进入下一轮。每轮按同协议逐 case 核对实测净收益与剩余目标差额。

`fixed_rounds` 执行已确认轮数，默认 3 轮；`target` 使用冻结的 metric/comparison/value/unit，可选 max_rounds，无显式上限则不另设上限。`target` 的性能循环只在目标达成、显式轮数/用户停止条件到达，或证据证明所有仍可能填补目标差额的合法方向均不可实施后结束。某轮零实施契约、候选退化、连续数轮无改善、缺少物理 roofline，均不单独证明“没有可信方向”；一次候选退化须先区分机制、实现、正确性和证据问题。循环停止不截断未完成的精度诊断。

当目标未达且关键收益/安全性仍为 `unknown`，主 Agent 应派下一轮有界诊断或方案分析，并在状态中记录待核验假设与下一动作，不得把 `unknown` 写成 `infeasible_evidenced`、`ceiling_bound` 或用 `no_material_improvement` 结束。足以改变退出结论的未知量须先有界验证；缩小问题规模或改变关键负载特征的探针，只有证明关键路径与目标 case 可比时才可外推，否则只支持定性定位，不能据此否定完整目标场景。诊断工具无法归因时保留未知并继续寻找同身份证据；实际外部资源阻断按第 5 节记录 blocker，不冒充性能收敛。

分析后、候选实施前检查理论上限，门**分两级**且机器可检：(1)「当前结构天花板」——全部冻结调优 case 的 `verdict` 为 `NEAR-BANDWIDTH-CEILING`、`NEAR-COMPUTE-CEILING` 或 `MEMORY-CEILING`，且现 kernel 结构内没有合法可实施减量方案（方案数为 0）；(2)「算子内在天花板」——实测已逼近**算子内在最小成本 roofline**（`实测 ≤ ceiling_intrinsic_us * 1.5`；该 roofline 由 shape/dtype/权重字节恒可计算，无需任何外部实现）且不落后 `REFERENCE_PERF`。**仅两级同时满足**才以 `reason_code=ceiling_bound` 结束性能探索，保留当前基线。若只触及当前结构天花板、但离内在最小成本仍显著（或落后参考锚点），则当前结构天花板 ≠ 物理天花板：门不触发，本轮须先评估结构性重写方向（`pursue_optimal` 下为强制门禁，`safe_incremental` 下记录方向与预估收益交用户决策）；仅当结构性方向也经源码/建模证据判不可行后方可收敛。`safe_incremental` 下需要用户决定更宽实施范围时，先交付可审阅的范围、风险与有依据的收益估计，不能把尚未定界的技术未知当作用户决策。报告须引用逐 case 的 `MBU/MFU/mte2_util/ceiling_us/headroom/verdict`、目标 SoC 峰值口径和合法手段不可用的证据；PIPELINE-TRAP 还须排除已证明不重读权重的重叠方案。有合法候选（增量或结构性）时继续实施，不因 bound/verdict 标签单独停止；用户显式要求继续时，将覆盖理由登记到 workflow-state。

`pursue_optimal` 的结构性方向是跨轮义务，登记进 `workflow-state` 的结构方向台账（`$WORKFLOW_SCRIPTS/workflow_state.py structural-direction --id <稳定id> --status <status>`）：`not_attempted`/`blocked_by_scope` 为**未了结**（`blocked_by_scope` 须重冻结更宽 scope 后重试，不得当作完成），`realized`/`infeasible_evidenced`/`blocked_by_precision` 为了结。**硬门禁**：台账存在未了结方向时，`$WORKFLOW_SCRIPTS/workflow_state.py finish --status success --reason-code completed` 被拒绝；须先把每个方向推进到了结态，或以 `finish --status awaiting_operator --reason-code structural_headroom_unrealized` 显式驻留交人工决策。运行时风险（死锁/同步）不能作为 `infeasible_evidenced` 的理由，须先经 `ascendc-sync-audit` 产出缓解方案或"风险不可避免"的证据。

`ceiling_bound` 只停止性能探索：implementation 仍完成保留基线的交接和最终 demo 全集验收，随后进入 integration；完成剩余验收后再登记任务终态，是否达到用户目标据实报告。

generalization 保留既有规则：

- baseline 准备默认 1000 条性能/功能合一全集和精确覆盖的竞品证据；preparation 建立 demo 功能基线。
- analysis 取得当前 NPU 全集性能及 ratio，每轮从 `ratio < 1.0` 中确定性选择最多 30 条；选例方法属于 analysis，计算口径属于共享验证。
- implementation 先按 geomean ratio ≥ 1.0 且 min ratio ≥ 0.6 判断候选达标，再按原有 ratio/有效性能/复杂度顺序终选；内层最多 3 轮。
- 达到内层门限、没有不达标 case 或内层到上限时，implementation 执行外层全集验证。全集未达标且未到上限时回 analysis；外层最多 2 次，恢复不清零计数。
- 无需修改时 analysis 仍交逐 case 达标/无方案证据，implementation 验证保留基线；不能跳过阶段交接。
- 最后进入 integration；涉及/不涉及路由核验继续保留，不能替代两个全集检查。最终标明 ACHIEVED 或 NOT_FULLY_ACHIEVED；未达标不能伪装完全成功。

## 5. 失败路由与全局约束

| 情况 | 路由 |
|---|---|
| 请求/环境/对标缺失或集合未就绪 | 返回 baseline；需用户决定的缺口由主 Agent 汇总询问 |
| 原始对标的源码、构建产物或实际加载产物身份不一致 | 返回 baseline 修正构建/加载路由；该身份上的运行结论全部失效 |
| 剥离、依赖闭包或基线加载错误 | 返回 preparation，冻结原工程不变 |
| 采集证据缺失/失效、方案与契约不一致 | 返回 analysis；旧方案冻结范围不得被实施代理放宽 |
| 单候选新增/恶化精度失败、符合性失败或压测崩溃 | implementation 修复或淘汰该候选，其他候选和当前基线继续 |
| 回集成接线、隔离或两类全集退化 | integration 修复接线或将真实输入条件回原代码，并复验新身份 |
| 实际外部资源 blocker | 保存证据、未决项和恢复点，由主 Agent 记录状态 |

若冻结用例语义与工作流校验脚本的输入契约冲突，主 Agent 应定位口径差异，修复脚本或证据映射后重跑原门禁；可复现且可修复的校验缺陷不得用 `workflow_error` 结束任务，也不得将未通过的门禁伪装为通过。`workflow_error` 仅用于已记录具体故障、恢复尝试与恢复点后仍无法推进的工作流故障，不代替目标未达或技术方向未知的结论。

公开 API、原约束、dtype/format 和用例/golden/阈值不变。TARGET_SOCS 是精确验证范围，芯片族归类不扩大权限；共享实现先复制后单独路由，未涉及代际/模板保持原路径。前四阶段原工程只读。

精度分类使用共享验证规则：已证实 `known_baseline_failure` 且候选不恶化可 `conditional_pass`；未证实的失败不得冒充原始问题。精度诊断固定持续执行，精度诊断没有自动停止预算，不设总时长、轮次、Agent turn 或 token 上限；命令级防挂死 watchdog 只作用于单命令。候选失败或原始已知失败不得直接终止整个任务。

## 6. 派发、状态与报告

诊断分析与实施验证的方案设计、方案实施引用 cannbot-knowledge 知识卡。主 Agent 在首次派发需要它的阶段前解析一次 `KB_ROOT` 并全程复用，按以下顺序：环境变量 `CANNBOT_KNOWLEDGE_ROOT`（已设置且目录存在）→ 从项目根 glob `.cannbot/dependencies/*/cannbot-knowledge/knowledge`（取第一个含 `ops/ascendc` 子目录的匹配）→ 运行已安装 `knowledge-query` Skill 的 `discover`。解析成功且检索索引缺失时按需构建（`knowledge_query.py --knowledge-root "$KB_ROOT" build`，失败仅告警，不影响卡片直读）。知识库不可用（依赖仓克隆被跳过、离线或解析失败）不是阻塞项：信封省略 `KB_ROOT`，阶段标注 `kb_unavailable`，按无知识增强继续，不降低精度与性能验收要求；主 Agent 在报告中登记该状态。

读取 `$WORKFLOW_ROOT/workflows/task-prompts.md`，按 ROLE 只取对应模板；通用信封的字段定义以该稳定派发入口为准。传入 WORKFLOW_ROOT、WORKFLOW_SCRIPTS、REQUEST、RUN_MANIFEST、WORKFLOW_STATE、TUNING_MODE、TARGET_SOCS、ROUND、CODE_DIR、KB_ROOT（或省略）、输入/输出、ACCEPTANCE 和条件技能；不把整个编排契约复制给 subagent。

派发前主 Agent 必须读取本次 `ROLE` 对应的 `workflows/prompts/<role>.md` 并按模板逐字段填写信封；只凭通用信封手写视为派发准备未完成。信封内路径与工作流脚本调用必须是解析后的绝对路径，`$WORKFLOW_ROOT`/`$WORKFLOW_SCRIPTS` 是主 Agent 侧占位符而非环境变量；子 agent 在自己工作目录内的常规相对路径操作不受影响。同一 `ROLE` 已有 `in_progress` 或取消中的会话时，先核对保存点与产物再决定是否补派；预计超过 2 分钟的命令建议后台执行并轮询日志。

使用 `$WORKFLOW_SCRIPTS/workflow_state.py` 管理状态，具体命令和字段按需读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。主 Agent 派发前 mark in_progress，验收后 complete；诊断假设/候选变化时记录 progress。阶段没有真实开始时间就保留未知，不伪造耗时。

保留 `phase.baseline/preparation/analysis/implementation/integration` 和原 round/gen 保存点。phase.analysis 记录初次交接，轮内重复诊断用细粒度键；phase.implementation 在最终 demo 全集验收后完成。每轮 complete 前登记所保留实现的本轮与累计摘要，二者引用同一候选 CSV；原始基线不能换成上一轮基线或连乘加速比。

主 Agent 复核阶段返回的摘要并登记状态，持续报告由脚本重绘；每轮刷新完整实测范围，最终引用回集成后的性能与身份。恢复前 verify 检查 manifest 和 artifact SHA；失效保存点不能被当作完成。版本变化按 [migration.md](migration.md) 审计，只失效受影响证据。

中止或空返回后，先核对现有保存点和实际产物，只派发尚缺的工作。`verify` 只验证已登记文件是否改变，不证明其属于当前候选；实施 gate 还须按实施 Skill 核验 contract、scope、候选源码及构建/运行身份。未登记或归属不明的产物保留为未核验，不从文件存在、复制目录或工具 completed 推断完成。只有当前基线副本且无方案实现证据时，按未实施恢复。

空返回时优先续接同角色实例补交摘要与缺失文档；实例不可恢复再新派。已验收构建/采集不因缺摘要重做。用户调整轮数、阶段安排或停止目标时先登记决策；被明确暂停或移交给后续阶段的工作，在用户修改决定前不得由主 Agent自动重派。只停止性能探索而仍要求交付的，按最后可信实现安排剩余验收；明确取消整个任务的，立即停止派发、构建和设备操作，仅记录可信实现与恢复点，不追加验收或回集成。恢复信息复用现有 stage/context/progress，不另建并行状态文件。

## 7. 完成定义

- 五个阶段交接产物齐全，request/manifest/state 的模式、目标、环境（含 `optimization_intent`、`reference_perf`）与集合身份一致。
- 每个候选有符合性、隔离、构建与功能结论，合格候选有一次可比较性能证据，淘汰原因可追溯。
- pursue_optimal 的结构空间判定以算子内在最小成本 roofline 为普适锚点，`REFERENCE_PERF` 仅在恰有可比实现时作机会性增强、缺参考不阻塞不降级；结构方向台账无 `not_attempted`/`blocked_by_scope` 残留（否则终态为 `awaiting_operator` + `structural_headroom_unrealized`，不得伪装 `success/completed`）。
- 最终 demo 完成功能/性能全集验收，原工程沿原入口回集成，非目标芯片族与未涉及模板保持原实现。
- 原工程两个全集在每个目标 SoC 都无新增/恶化精度失败和有效性能退化；必要回路由已对最终身份完整复验。no-op 也须有原始身份的全集证据。
- `性能调优报告.md` 与机器状态一致，逐轮/最终性能、精度异常、是否达标、未决问题和安全恢复点完整。泛化内外层计数和最终 ratio 完整。
- 正常成功、失败、等待用户或 blocker 返回前更新状态与报告；finish success 需五阶段完成且证据 SHA 未变，不能用对话替代落盘结果。
