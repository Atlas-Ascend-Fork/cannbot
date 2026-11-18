# CCU 四 Agent 协作工作流

## 1. 适用范围与真源

本文件是 `hccl-op-generator` 的 CCU 开发流程真源。技术能力只加载 `hccl-ccu-best-practice`，测试操作加载 `hccl-test-tool-hvm`；角色边界见 `agents/hccl-*.md`。CCU_SCHED 和 CCU_MS 都路由到本流程，具体模式由 Architect 根据需求与目标版本冻结，不从 Skill 样本推定支持范围。

采用与 AICPU 相同的产物身份协议。共享规则复用 [AICPU 工作流](aicpu-multi-agent-workflow.md) 的 §2 任务目录与 owner、§2.1 调用记录/外部证据、§3 状态机、§4 失效表、§5 权限、§6 共享环境、§7 失败回退和 §8 交接字段。下述 CCU 的模板、命令、技术依据和完成判据替换其中 AICPU 专用部分；不执行 AICPU Skill、Spec 检查器、源码快照工具或构建入口。

## 2. 任务初始化与产物

任务目录：`${HCCL_ROOT}/src/ops/{op_type}/docs/{task_id}/`。先加载已确认环境，完成共享环境检查；`task-index.json` 额外记录 `hcomm_repo`、`hcomm_source_identity`。环境脚本若使用 `HCOMM_CODE_HOME`，从这个已确认值传入 Skill 的 `--hcomm-root`，不猜其他目录。环境 PASS 不代表 CCU 模式或 Checker 可用，Verifier 还须核对实际执行能力。

| 产物 | 模板/来源 | owner |
|---|---|---|
| `task-index.json` | [ccu-task-index-template.json](templates/ccu-task-index-template.json) | HCCLBot |
| `environment.md` | [environment-template.md](templates/environment-template.md)，engine=CCU | HCCLBot |
| `TASK_SPEC.md` | [ccu-task-spec-template.md](templates/ccu-task-spec-template.md) | Architect |
| `DATAFLOW_SPEC.md` | [ccu-dataflow-spec-index-template.md](templates/ccu-dataflow-spec-index-template.md) | Architect |
| `dataflow/*.md` | CCU Skill 的 `assets/dataflow-spec-template.md`，按 template 拆分数据流/资源/同步证明 | Architect |
| `DESIGN.md` | [ccu-design-template.md](templates/ccu-design-template.md) | Architect |
| `PLAN.md` | [plan-template.md](templates/plan-template.md)，engine=CCU | Architect |
| `TEST_PLAN.md` | [ccu-test-plan-template.md](templates/ccu-test-plan-template.md) | Architect |
| `source-report.json` | CCU Skill 的 `inspect_sources.py` 原始输出 | Architect |
| `launch-contract.json` | CCU Skill 的 `assets/launch-contract.example.json` 按实际设计填写 | Architect |
| `sync-contract.json` | CCU Skill 的 `assets/sync-contract.example.json`，按每张接收表/边界场景声明 | Architect |
| `BASELINE_REPORT.md` | [ccu-baseline-report-template.md](templates/ccu-baseline-report-template.md) | Verifier |
| `LOG.md` | [log-template.md](templates/log-template.md)，engine=CCU | Developer |
| `REVIEW.md` | [ccu-review-template.md](templates/ccu-review-template.md) | Reviewer |
| `TEST_REPORT.md` | [ccu-test-report-template.md](templates/ccu-test-report-template.md) | Verifier |
| `HANDOFF.md` | [ccu-handoff-template.md](templates/ccu-handoff-template.md) | 当前阶段 Agent |

HCCLBot 预先创建任务专属外部证据目录，登记 `external_evidence_roots`，逐次记录实际调用 ID、输入输出身份和 outputs。没有真实角色调用能力时进入 BLOCKED；HCCLBot 不能代写角色产物。

新任务优先用 [初始化工具](ccu-automation.md#任务初始化) 创建索引与环境草稿，环境核对后再绑定已有结论并跑原门禁。它不覆盖已有任务、不自动给环境PASS。Architect可选冻结`checker-plan.json`并以TEST_PLAN头的`checker_plan_sha256`绑定；该附件归Architect，不增加必需产物。

Architect 将与 task-index 相同的 `hcomm_source_identity` 写入 DESIGN 头，并冻结 `DESIGN.ccu_mode` 与 `TEST_PLAN.ccu_mode`，取 `CCU_SCHED` 或 `CCU_MS`，一次任务对应一个模式。新任务使用模板的 `ccu_contract_version=3`，三个 JSON 附件的 SHA-256 写入 DESIGN 头的 `source_report_sha256`、`launch_contract_sha256`、`sync_contract_sha256`，随后通过已有 DESIGN 依赖哈希传播到基线、开发、评审和测试。设计调用 outputs 必须包含三个 JSON；Developer 无权修改附件，需要改变 ABI 时返回 DESIGN_ISSUE。

历史未声明版本的任务按版本1执行原有两附件门禁；版本2保留同步检查；新任务版本3在同一个sync-contract.json内增加compute_ops并检查目标生成器算术。不得降级绕过新门禁；历史任务升级需Architect补齐、重新冻结并按影响使下游失效，不改写历史PASS。

`DATAFLOW_SPEC.md` 始终创建。新算法或数据流/资源/同步变化必须为 REQUIRED，每个参与 template 都有带源码依据的推演；纯日志或不改变契约的修复可写 NOT_REQUIRED 及理由。不使用 AICPU 的 A/B/C 模式或 check_spec/check_layout 工具。

## 3. 调用与状态

每次调用读取 [ccu-task-prompts.md](ccu-task-prompts.md) 中的完整对应模板。

| 当前状态 | 调用 | 目标状态 |
|---|---|---|
| ENV_READY | Architect：设计与冻结 CCU 附件 | DESIGN_READY |
| DESIGN_READY | Verifier：旧包保全与同矩阵基线 | BASELINE_READY |
| BASELINE_READY | Developer：实现、静态检查、记录候选身份 | IMPLEMENTED |
| IMPLEMENTED | Reviewer：独立核对真实代码和契约 | REVIEW_PASS |
| REVIEW_PASS | Verifier：候选全量构建、安装、A/B 功能验证与 estimate 性能估算 | TEST_PASS |
| TEST_PASS | HCCLBot：同身份门禁复核 | COMPLETE |

正常返回执行 `workflow_policy.py transition --engine CCU`，参数与共享流程相同。修复中逐角色执行 `workflow_policy.py recovery --engine CCU`，禁止跳过 pending_roles 首项。

- DESIGN_ISSUE 回 Architect，重新冻结设计后重新核对基线适用性。
- 基线 FAIL 阻塞，不能在已有失败上继续宣称候选有效。
- REVIEW_FAIL：Developer → Reviewer，随后正常进入 Verifier。
- TEST_FAIL 且 failure_class=SOURCE：Developer → Reviewer → Verifier。
- TEST_FAIL 且 failure_class=ENVIRONMENT：保留证据并阻塞，禁止猜修源码。
- A/B 通过但 estimate 失败、未执行、未命中或缺证据：保留功能结果并返回 BLOCKED；只有独立证据证明源码问题时才进入 SOURCE 修复，不因估算值较高自动修复。
- Review/Test 共用最多三轮修复；PASS_WITH_NOTES 和旧 VERIFIED 状态不再是有效门禁结果。

## 4. 自动产物门禁

`CCU_SKILL_DIR` 必须指向已安装的 `hccl-ccu-best-practice` 目录；不猜源码仓为 Skill 仓。下面两个门禁必须分别通过，不能仅检查文件存在：

```bash
python3 "$HCCL_WORKFLOW_DIR/scripts/validate_ccu_artifacts.py" \
  --task-dir "$TASK_DIR" --ccu-skill-dir "$CCU_SKILL_DIR" \
  --actor hccl-architect --changed <相对 source_repo 的实际变更路径...> --json

python3 "$HCCL_WORKFLOW_DIR/scripts/validate_ccu_artifacts.py" \
  --task-dir "$TASK_DIR" --ccu-skill-dir "$CCU_SKILL_DIR" \
  --target-state DESIGN_READY --json
```

角色返回后，HCCLBot 根据调用前后真实文件快照生成 changed paths（包括已登记外部证据），更新调用记录、哈希和失效记录，再执行权限门禁、流程策略和目标状态门禁；全部通过才更新 current_state，更新后再校验一次目标状态。ENV_READY 同样校验环境和 HCCLBot 写权限；COMPLETE 只复核门禁，不伪造 Agent 调用。

CCU 门禁复用角色所有权、身份、依赖哈希与失效规则，另检查两仓来源绑定、模式一致、附件哈希，并实际调用 Skill 的 `check_launch_contract.py`；版本2/3调用 `check_sync_contract.py --hcomm-root ...` 对照实现配额，版本3再调用 `check_arith_ops.py --hcomm-root ...` 检查同一附件的compute_ops、目标版本证据和生成器算术表。工具缺失、无效映射、错引 AICPU 报告或旧哈希都会阻止推进。检查器只检查声明内部一致性；源码对应关系与同步活性仍由 Reviewer 证明，构建和功能由 Verifier 执行。

`TEST_PASS` 和 `COMPLETE` 同时要求 `TEST_REPORT.estimate_status=SUCCESS`，估算源码身份与当前候选一致；复用共享 estimate 门禁检查算法命中、通信域、固定参数、有限正数耗时、真实退出码与文件哈希。CCU 的 `estimate.json` 还必须记录 `engine=CCU`、与冻结 DESIGN/TEST_PLAN 一致的 `ccu_mode`，以及与 task-index 一致的 `hcomm_source_identity`。旧报告缺少估算时必须补齐真实证据，不降级契约版本或回填历史 PASS。

## 5. 两仓身份与验证

两仓分别记录身份：`task-index.source_identity`及产物frontmatter的`source_identity`、`input_source_identity`、`output_source_identity`、`review_source_identity`、`latest_source_identity`只填对应时点的HCCL单仓身份；输出/待审/被测身份与登记后的task-index.source_identity逐字符一致。HCOMM依赖使用`task-index.hcomm_source_identity`和DESIGN同名字段。两仓路径、分支、HEAD、未提交文件/权限及可恢复差异或快照仍须可追溯，正文可并列描述，不把两串拼接替代HCCL头字段。

来源报告是设计输入快照，不是候选源码快照。候选改动后不让Developer覆盖来源报告；在LOG、REVIEW、TEST_REPORT中分别记录当前HCCL与HCOMM身份和可恢复快照。重新设计时由 Architect 按 [来源报告修订](ccu-automation.md#重新设计与历史来源证据) 生成全新修订文件，DESIGN 以 `source_report_file`/`source_report_sha256` 选择当前输入，旧报告保留归档。采用已核验新知识基线时，以 DESIGN 的 `knowledge_baseline_sha256` 绑定任务内副本，并向来源/契约检查传入同一基线。

HCOMM 或其他环境依赖发生变化也必须使旧 Review/Test 失效；需要重新核对技术依据时退回 Architect 更新来源报告和设计。HCOMM 在本流程中只读，生产修改范围为冻结计划中的 HCCL 文件；确实需要 HCOMM 源码变更时返回 DESIGN_ISSUE，先明确跨仓任务范围。

Verifier 按 CCU Skill 的 `references/validation.md` 核对目标版本构建命令、template/kernel CMake 和依赖，按 `hccl-test-tool-hvm` 执行已支持的 CCU 模式。候选第一次构建前保全旧包；每个稳定身份保留一次可追溯全量构建及包、命令、原始退出码和日志，不能重新编译来补造证据。

基线与轨道 B 使用同矩阵/默认选路；轨道 A 强制经源码核验的 CCU 算法并证明命中，同时 Checker 失败数为零。默认选路变更仅按用户授权和冻结矩阵验收。用例覆盖实际支持的零数据、切片/尾块、repeat、地址变化、FastLaunch、资源与同步边界，不能套固定 rank/dtype 排除表。

A/B 功能验证全部通过后，Verifier 按已安装 `hccl-test-tool-hvm/references/estimate.md` 在独立会话执行 estimate；基线阶段不追加候选估算。复用同一候选包、HCCL/HCOMM 身份、冻结 CCU 模式和经源码核验的选路配置，并从本次日志重新确认目标算法命中。默认 `mock-comm 112`，用户指定组网时继承需求；默认组网不支持目标算法时返回具体限制，不用其他算法代替。固定 `-np 1`、`-b 1G -e 1G -w 0 -n 1 -c 0` 与 CCU 环境准备以共享参考为准，不改变功能矩阵，也不把 estimate 混入 checker-plan 或功能结果汇总。`estimate.json`、完整日志、profiling/trace 和候选包在本轮登记外部证据目录归档，条件、耗时、观察及限制写入既有 TEST_REPORT。

## 6. 完成判定

冻结设计、基线、实现日志、独立 REVIEW PASS 与 TEST PASS 全部有效，且 Review/Test/候选包绑定同一联合身份；launch 声明与源码经独立核对、目标 CCU 算法确实命中、A/B Checker 通过、同身份/模式目标算法 estimate 成功且证据完整、环境恢复完成后才能 COMPLETE。静态脚本或流程 dry-run 不代表算法功能通过；estimate 成功只证明获得该条件下的仿真估算，不设性能收益阈值，真机性能收益仍需同环境对照实测。

默认不运行 HCCL ST/UT；用户明确要求时单列结果，不替代功能验收。缺工具、硬件、来源或权限时记录 BLOCKED 与未验证范围。最终汇报引擎/模式、task-id、两仓身份、代码路径、阶段状态、报告/原始证据及未完成范围，并必须呈现“算法性能估算”：目标算法、实际组网、数据类型/数据量、算法耗时、观察、适用范围和证据路径；未执行或失败时保留原因与阻塞状态，不省略或复用示例耗时。


## 7. 减少重复调研与已知返工

Architect 按 Skill 的 `development-entry.md` 校验知识卡；在 DESIGN 中记录适用 executor/分支、卡版本与哈希、复用结论及实际补查。Developer/Reviewer/Verifier 消费这一份记录；来源未变不重复扫描 HCOMM、读全部 Mesh/NHR 或生成另一套接入报告。Reviewer 仍独立推导关键算法，复审只重验 delta 与受影响证明。

按Skill的operator-index.md加载本算子接入卡；AllGather Sole另用框架方法卡，其他算子不套其字段/缓存。漂移时按`check_knowledge.py --summary --explain`定位差异，可选样本仅在借鉴时加载。静态检查可用Skill的`check_contracts.py --launch ... --sync ... --hcomm-root ...`一次执行原launch/sync/arith检查，门禁继续独立执行对应原检查器，不改变版本1/2/3语义。数据流证明集中在spec，参数/同步/算术值集中在JSON；其他产物引用路径、字段和哈希，记录自身判断、实现落点及差异，保留必要独立推导。

TEST_PLAN 首版冻结前完成工具可表达域/实际对齐、API/executor 分支可达性和现场内存预算，列明实际库身份及最小模式冒烟计划。环境阶段只作已授权只读身份核对，运行测试继续由 Verifier 独占。已有可信基线的矩阵和环境未变时引用原始证据，只补受影响项；涉及语义/选路/工具变化继续按原失效规则处理。

六算子使用Skill的preview_cases.py --op <算子目录名>选择自己的输入模型，计算真实rank/count/bytes、工具基本分配与等效用例；非零root/非sum须核对实际runner能力，测试预检不证明实现支持。按 [计划执行与证据汇总](ccu-automation.md#冻结和执行测试计划) 复用现有hvm plan.py及显式run汇总工具。角色报告引用机器生成的路径/哈希/统计，保留自身判断与覆盖缺口；调用时间来自运行器实际事件。

不通过增加并行构建/共享测试、删全量构建或缩减独立评审来节省时间。来源校验、同步预算和矩阵预检旨在消除重复认知与已知失败闭环，耗时收益以新任务同口径实测为准。


## 8. 修订与重绑定工作单

复用 [共享修订规则](aicpu-multi-agent-workflow.md#41-修订后的依赖工作单)，CCU使用自己的只读CLI：

```bash
python3 "$HCCL_WORKFLOW_DIR/scripts/validate_ccu_artifacts.py" \
  --task-dir "$TASK_DIR" --rebind-report TASK_SPEC TEST_PLAN --json

python3 "$HCCL_WORKFLOW_DIR/scripts/validate_ccu_artifacts.py" \
  --task-dir "$TASK_DIR" --verify-rebind --json
```

不需要Skill目录即可生成/审计依赖工作单。严格按拓扑层派发owner重新核对证据与生成产物，再取依赖的最新哈希；HCCLBot不自动改报告或恢复PASS。审核后仍更新索引/失效记录并运行带ccu-skill-dir的target-state门禁。来源、launch/sync或已采用知识基线变化时，可直接以SOURCE_REPORT、LAUNCH_CONTRACT、SYNC_CONTRACT、KNOWLEDGE_BASELINE为变化根生成工作单；可选checker-plan使用CHECKER_PLAN。工作单包含Architect对DESIGN/TEST_PLAN的复核及其下游闭包，审计同时检查附件绑定；不可拿变更前的中间哈希一次铺写所有报告。

已完成任务中的设计假设勘误可沉淀至Skill和完成记录，下次实质修订再处理；不为此重写完成链。本次Variable MUL/V1勘误即按此原则保留原任务证据。
