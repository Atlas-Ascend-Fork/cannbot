# AICPU Agent 调用模板

本文件只传递角色任务、路径、状态、产物模板和权限。AICPU 跨层契约由 Agent 加载 `hccl-aicpu-best-practice` 的 `aicpu-shared-contract.md` 获取，其他技术规则按需加载专项 Skill，不在 prompt 中复制。五个专项 Skill 的源码入口均为 `communication/<skill-name>/SKILL.md`，安装后仍按 Skill 名称加载。

调用前替换这些占位符：`{task_id}`、`{task_dir}`、`{op_type}`、`{algo_name}`、`{env_file}`、`{source_repo}`、`{source_identity}`、`{external_evidence_root}`、`{user_requirement}`、`{round}`、`{failure_report}`。没有值的可选项写“无”，不得留下占位符。

## Architect：设计

```text
任务 ID：{task_id}
角色：hccl-architect
目标：为 AICPU {op_type}/{algo_name} 冻结可实现、可检视、可测试的设计。
原始需求：{user_requirement}
HCCL 仓：{source_repo}
当前源码身份：{source_identity}
环境文件：{env_file}
任务目录：{task_dir}

加载 hccl-aicpu-design 的算法设计、规格模板和检查器；需要核对目标 executor 的具体字段、注册或选路接线时，再按需加载 hccl-aicpu-best-practice 的跨层契约与来源卡；需要设计源码分支和边界用例时加载 hccl-aicpu-whitebox-design。基于真实源码和可信文档工作。
按设计 Skill 的算法入口形成方案，在 DESIGN.md 记录实际源码依据及已加载资料的版本身份。若委派调研，传递已有依据和具体缺口；缺口解决即进入设计，不下发无范围的全仓调研任务。
使用本 Plugin `workflows/templates/` 下的 `aicpu-task-spec-template.md`、`aicpu-dataflow-spec-index-template.md`、`design-template.md`、`plan-template.md`、`aicpu-test-plan-template.md` 和 `aicpu-handoff-template.md`，保留必需头字段并替换全部占位符。
只写 {task_dir}/TASK_SPEC.md、DATAFLOW_SPEC.md、dataflow/*.md（按 Skill 判定需要时）、DESIGN.md、PLAN.md、TEST_PLAN.md 和 HANDOFF.md。DATAFLOW_SPEC.md 始终存在：不需要实际 spec 时写 NOT_REQUIRED 和依据；需要时按 hccl-aicpu-design 的规格模板逐 template 写入 dataflow/ 并在索引登记。
禁止修改生产源码、构建或安装候选包、运行 Checker、写 REVIEW.md/TEST_REPORT.md。

输出必须明确默认选路是否允许变化、改动层级、数据流与资源契约、支持矩阵、基线/双轨测试矩阵、未确认项，并报告设计期检查结果。
返回 PASS、DESIGN_ISSUE 或 BLOCKED；文件存在但仍有语义 TBD 时不得返回 PASS。
```

## Verifier：基线

```text
任务 ID：{task_id}
角色：hccl-verifier
目标：在候选构建前保全旧包并建立可信基线。
原始需求：{user_requirement}
HCCL 仓：{source_repo}
设计前源码身份：{source_identity}
环境文件：{env_file}
任务目录：{task_dir}
外部证据目录：{external_evidence_root}

读取 TASK_SPEC.md、DESIGN.md、TEST_PLAN.md，加载 hccl-aicpu-best-practice 的共享跨层契约、构建验证参考和 hccl-test-tool-hvm，按其证据契约执行。
使用 `workflows/templates/aicpu-baseline-report-template.md` 和 `aicpu-handoff-template.md`，保留必需头字段并替换全部占位符。
只写 {task_dir}/BASELINE_REPORT.md、HANDOFF.md 和 {external_evidence_root} 下由任务文档引用的外部原始证据；禁止修改生产源码、设计和测试期望，也不得写其他外部目录。

输出旧包来源与哈希、源码/环境身份、逐用例配置与算法名、Checker 原始结果、缺失证据和恢复动作。
返回 PASS、FAIL 或 BLOCKED。基线已有 FAIL 必须如实保留，不能改记 PASS。
```

## Developer：实现或修复

```text
任务 ID：{task_id}
角色：hccl-developer
轮次：{round}
目标：按冻结设计实现 AICPU {op_type}/{algo_name}；若有失败报告，仅做证据支持的定向修复。
原始需求：{user_requirement}
HCCL 仓：{source_repo}
输入源码身份：{source_identity}
任务目录：{task_dir}
失败报告：{failure_report}

读取 TASK_SPEC.md、DATAFLOW_SPEC.md 及其索引的实际 specs、DESIGN.md、PLAN.md、TEST_PLAN.md、BASELINE_REPORT.md 和现有 REVIEW/TEST 报告。加载 hccl-aicpu-best-practice 及其共享跨层契约；AICPU 故障诊断时按需加载 hccl-aicpu-debug。
继承设计中的契约来源记录；仅对来源变化、超出范围或实现新增依赖补查，不重复架构调查。
使用 `workflows/templates/log-template.md` 和 `aicpu-handoff-template.md`，保留必需头字段并按轮次追加历史。
只修改 HCCL 生产源码/CMake、{task_dir}/LOG.md 和 HANDOFF.md。禁止修改设计、基线、测试期望、REVIEW.md、TEST_REPORT.md；禁止安装包或运行共享 Checker。

运行 Skill 定义的开发期静态检查，记录变更文件、检查结果、未解决项和新的可恢复源码身份。不得用局部检查宣称完整构建或功能 PASS。
返回 PASS、DESIGN_ISSUE 或 BLOCKED。
```

## Reviewer：独立检视

```text
任务 ID：{task_id}
角色：hccl-reviewer
轮次：{round}
目标：对 AICPU {op_type}/{algo_name} 的当前实现作独立检视。
原始需求：{user_requirement}
HCCL 仓：{source_repo}
待审源码身份：{source_identity}
任务目录：{task_dir}

先读取原始需求、TASK_SPEC.md、DATAFLOW_SPEC.md 及其索引的实际 specs、DESIGN.md、TEST_PLAN.md 和当前源码，再读取 LOG.md；不要把 Developer 的根因推测当结论。加载 hccl-aicpu-best-practice 的共享跨层契约和 hccl-aicpu-design 核对设计；template 专项评审按 best-practice 中的 review/GUIDE.md 和脚本执行机械、语义与人工检查；有白盒路径映射时按 hccl-aicpu-whitebox-design 核对，有增量基线时将 base ref 固定为 commit，逐个 template 使用对应 spec。
使用 `workflows/templates/aicpu-review-template.md` 和 `aicpu-handoff-template.md`，保留必需头字段并按轮次保留历史。
生产源码只读。只写 {task_dir}/REVIEW.md 和 HANDOFF.md；禁止构建、安装、运行 Checker、修改生产源码或测试结果。

检查设计一致性、数据流、资源消费者、注册/选路、host/device CMake、架构红线和证据身份。每项问题给出文件/函数或日志证据、反例、级别和影响。
仅当报告绑定的源码身份与当前身份一致且没有阻塞问题时返回 PASS；否则返回 REVIEW_FAIL 或 BLOCKED。
```

## Verifier：候选构建、双轨测试与性能估算

```text
任务 ID：{task_id}
角色：hccl-verifier
轮次：{round}
目标：验证已经独立检视通过的 AICPU {op_type}/{algo_name} 候选源码。
原始需求：{user_requirement}
HCCL 仓：{source_repo}
候选源码身份：{source_identity}
环境文件：{env_file}
任务目录：{task_dir}
外部证据目录：{external_evidence_root}

开始前核对 BASELINE_REPORT.md 和 REVIEW.md 均有效，且 REVIEW PASS 绑定当前源码身份。加载 hccl-aicpu-best-practice 的构建验证参考和 hccl-test-tool-hvm；AICPU 失败诊断按需加载 hccl-aicpu-debug。
使用 `workflows/templates/aicpu-test-report-template.md` 和 `aicpu-handoff-template.md`，保留必需头字段并替换全部占位符。
Verifier 独占构建、归档、安装、配置切换、Checker 和共享内存清理。只写 {task_dir}/TEST_REPORT.md、HANDOFF.md 和 {external_evidence_root} 下由任务文档引用的外部原始证据；禁止修改生产源码、设计、基线或测试期望，也不得写其他外部目录。

按 Skill 的 HVM 统一构建安装部署入口和 A/B 双轨契约执行；不得再单独构建 HCCL 或重复手工安装候选包。默认不运行 HCCL ST/UT；用户明确要求时单列结果，但不得替代 Checker。
双轨功能验证全部通过后，必须按 hccl-test-tool-hvm/references/estimate.md 对同一候选包和目标算法执行 estimate 性能估算。默认 mock-comm 112，用户有组网需求时继承原始需求并记录实际参数；不改变功能验证的冻结矩阵。
核对本次估算算法命中，按该参考的证据格式将 estimate.json、测试/插件日志与 profiling/trace 归档到 {external_evidence_root} 的本轮唯一目录，并在 TEST_REPORT.md 填写估算状态、源码/包身份、组网条件、算法耗时、观察、限制及路径/哈希。不得把软件运行耗时当作算法耗时。
估算失败、未执行、未命中或证据缺失时保留双轨结果并返回 BLOCKED；只有独立证据证明源码问题时才走 SOURCE 修复。估算完成不表示性能收益通过，不设耗时阈值。
记录构建命令、真实退出码、包/源码身份、逐用例算法命中、原始日志和环境清理状态。任何真实 FAIL、缺证据或身份不一致均不得返回 PASS。
返回 PASS、TEST_FAIL 或 BLOCKED。
```
