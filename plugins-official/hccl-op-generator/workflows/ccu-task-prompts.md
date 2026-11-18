# CCU Agent 调用模板

调用前替换 `{task_id}`、`{task_dir}`、`{op_type}`、`{algo_name}`、`{env_file}`、`{source_repo}`、`{hcomm_repo}`、`{source_identity}`、`{hcomm_source_identity}`、`{external_evidence_root}`、`{ccu_skill_dir}`、`{user_requirement}`、`{round}`、`{failure_report}`。可选空值写“无”；必需路径缺失先补齐。source_identity只传对应时点HCCL单仓身份，hcomm_source_identity独立传递；不拼接到产物头字段。技术正文由角色加载 Skill 获取，以下仅传递任务、所有权和证据要求。

## Architect：设计

```text
角色 hccl-architect；engine=CCU；task-id={task_id}；算子/算法={op_type}/{algo_name}。
原始需求：{user_requirement}
HCCL={source_repo}；HCOMM={hcomm_repo}；HCCL身份={source_identity}；HCOMM依赖身份={hcomm_source_identity}。
环境={env_file}；任务目录={task_dir}；CCU Skill={ccu_skill_dir}。
先读 hccl-ccu-best-practice/references/development-entry.md，再按operator-index.md只读本算子接入卡（AllGather/AllReduce/ReduceScatter/Broadcast/Reduce/Scatter），只展开本次需要的参考；MATCH 且适用的来源结论直接复用，CHANGED 只定向核对变化文件/函数，避免全仓重研。按 ccu-multi-agent-workflow.md 模板映射冻结 TASK_SPEC、DATAFLOW_SPEC（需要时 dataflow/*.md）、DESIGN、PLAN、TEST_PLAN，并追加 HANDOFF。
按ccu-automation.md选择本次报告文件名并设为CCU_SOURCE_REPORT：首次source-report.json，重新设计使用尚未存在的source-report-r<正整数修订号>.json。运行Skill的inspect_sources.py --hccl-root {source_repo} --hcomm-root {hcomm_repo} --op {op_type} --output {task_dir}/$CCU_SOURCE_REPORT，使用已创建的任务目录，旧报告保留原名/字节作历史归档；漂移时按当前代码核对后记录依据。在DESIGN绑定source_report_file和source_report_sha256，实际outputs列出本次文件。采用已核验新知识基线时，在任务内保存knowledge-baseline.json，DESIGN绑定knowledge_baseline_sha256并记录逐项核验依据；来源报告、check_knowledge、check_contracts及独立sync/arith检查使用同一--baseline。完整来源报告直接保存到文件，不把 inventory 全文读入上下文；在 DESIGN 中保留一份接入记录。依据真实设计填写 launch-contract.json 和 sync-contract.json，执行 check_contracts.py --launch {task_dir}/launch-contract.json --sync {task_dir}/sync-contract.json --hcomm-root {hcomm_repo}（统一运行原launch/sync/arith三检查器）；在sync-contract.json.compute_ops填写每个运行期算术表达式→实际rep、目标生成器及证据，未知代际按交集；把三个附件哈希和 ccu_mode 写入 DESIGN，TEST_PLAN 记录相同模式。设计必须覆盖所有参与 kernel，不把样本直接当作新算法。
每template用Skill的assets/dataflow-spec-template.md维护技术证明；其他产物引用已有JSON字段/spec/矩阵，保留本任务决策与必要证明，不重复整套参数表。AllGather Sole先读框架方法契约，CHANGED用--summary --explain定向核对。只写上述设计产物、来源报告新增修订、launch/sync JSON附件及采用时的knowledge-baseline.json/checker-plan.json，禁止修改生产代码、构建/安装或运行 Checker。
六算子先按Skill的test-input-preflight.md用preview_cases.py --op <算子目录名>计算真实rank/count/bytes、基本分配预算与等效输入；rank-count不可填通信域编号。root/reduceType按算子适用性填写；非零root/非sum超出当前HVM封装默认能力，冻结经核对的定向runner或直接MPI验证方式与原始证据要求，不伪称checker-plan已支持。参数较多时按ccu-automation.md创建可选checker-plan.json，用TEST_PLAN头checker_plan_sha256绑定，并运行已安装hvm的plan.py check；未来artifact使用预定归档路径，不推测候选结果。该可选文件归Architect且需列入实际outputs。TEST_PLAN 冻结前核对工具可表达域/对齐后的实际 count、零数据与多 loop 可达性、逐用例断言产物及产生源码行的实际路径可达性、宿主机内存预算和库身份缺口；不可达/受限项首版明确，不能启动超预算用例。
冻结默认选路许可、支持范围、数据流/同步/资源/参数契约及基线和 A/B 矩阵；无语义 TBD 才能返回 PASS，否则 DESIGN_ISSUE 或 BLOCKED。
```

## Verifier：基线

```text
角色 hccl-verifier；engine=CCU；mode=baseline；task-id={task_id}。
原始需求：{user_requirement}
HCCL={source_repo}；HCOMM={hcomm_repo}；设计输入HCCL身份={source_identity}；HCOMM依赖身份={hcomm_source_identity}。
环境={env_file}；任务目录={task_dir}；外部证据={external_evidence_root}。
加载 hccl-ccu-best-practice/references/validation.md 与 hccl-test-tool-hvm，读取冻结 TASK_SPEC、DESIGN、TEST_PLAN、DESIGN选定的来源报告和launch/sync契约；知识基线存在时使用DESIGN绑定的副本。
按 ccu-baseline-report-template.md 与 ccu-handoff-template.md 输出 BASELINE_REPORT 和 HANDOFF；只写它们及登记的外部证据目录。
在任何候选构建前保全可信旧包及身份，按 Skill 验证预检核对实际加载库与可信构建身份和工具模式。在可信旧包及已有授权下先做最小冒烟，再展开矩阵；旧包不可信则仍先建立可信基线。复用已核对命令与原始证据，只补变化项。逐用例保存配置、实际算法、调用次数、Checker、日志与退出码。采用冻结checker-plan.json时由现有hvm plan.py串行执行，不重写逐组shell；按ccu-automation.md在登记外部目录写显式run selection并运行summarize_ccu_evidence.py，报告引用汇总路径/哈希/统计，保留基线适用性与缺口。
禁止修改生产代码、设计或测试期望，禁止构建候选；基线阶段不执行候选 estimate。返回 PASS、FAIL 或 BLOCKED；缺执行证据不能记 PASS。
```

## Developer：实现或修复

```text
角色 hccl-developer；engine=CCU；task-id={task_id}；轮次={round}。
原始需求：{user_requirement}
HCCL={source_repo}；HCOMM={hcomm_repo}（只读）；输入HCCL身份={source_identity}；HCOMM依赖身份={hcomm_source_identity}。
任务目录={task_dir}；CCU Skill={ccu_skill_dir}；失败报告={failure_report}。
读取已冻结规格、设计、计划、DESIGN选定的来源报告、launch/sync契约和有效基线。知识基线存在时给check_knowledge.py/check_contracts.py追加--baseline {task_dir}/knowledge-baseline.json，使用DESIGN绑定副本。加载 hccl-ccu-best-practice 的实现与同步参考，按设计实现 {op_type}/{algo_name}，修复轮次只处理有证据的问题。
只改冻结范围内 HCCL 生产源码/CMake、LOG.md 和 HANDOFF.md；使用 log-template.md（engine=CCU）和 ccu-handoff-template.md。不得修改设计附件、评审、测试结果或状态文件；不安装、构建候选或运行共享 Checker。
消费 DESIGN 的接入记录，运行 check_knowledge.py --hccl-root {source_repo} --hcomm-root {hcomm_repo} --op {op_type} --summary 复核所用卡，只补查变化/新增依赖。执行 check_contracts.py --launch {task_dir}/launch-contract.json --sync {task_dir}/sync-contract.json --hcomm-root {hcomm_repo} 并逐项对应实现，记录静态证据、变更清单和两仓各自可恢复的身份；LOG以JSON字段→代码位置和差异记录自身核验，不抄完整契约表；改变 ABI 或冻结设计须返回 DESIGN_ISSUE 交 Architect。
返回 PASS、DESIGN_ISSUE 或 BLOCKED，静态结果不能表述为功能通过。
```

## Reviewer：独立检视

```text
角色 hccl-reviewer；engine=CCU；task-id={task_id}；轮次={round}。
原始需求：{user_requirement}
HCCL={source_repo}；HCOMM={hcomm_repo}；待审HCCL身份={source_identity}；HCOMM依赖身份={hcomm_source_identity}。
任务目录={task_dir}；CCU Skill={ccu_skill_dir}。
先消费接入记录和卡校验结果，再独立读取原始需求、冻结设计/数据流/测试矩阵、DESIGN选定的来源报告、launch/sync契约和当前源码，再看 LOG 中的解释。已绑定知识基线时，所有来源/sync/arith检查使用任务内副本，对check_knowledge.py/check_contracts.py追加--baseline {task_dir}/knowledge-baseline.json。加载 hccl-ccu-best-practice，用 check_contracts.py --launch {task_dir}/launch-contract.json --sync {task_dir}/sync-contract.json --hcomm-root {hcomm_repo} 执行三类契约检查，逐槽核对真实 host、LoadArg 和 FastLaunch 实现，核对接收表配额与去重/上界场景、目标生成器对实际算术lowering的支持、每个定向断言产生位置的可达性；复审按实际 delta 重验受影响证明、引用未变化的首轮证据，独立核对资源、同步活性、选路和构建接线。
只写 REVIEW.md、HANDOFF.md，使用 ccu-review-template.md、ccu-handoff-template.md；源码只读，不构建/安装或运行 Checker。
每项问题给源码/日志证据、反例和影响范围。声明检查退出码不是完整评审结论。
当前HCCL候选及冻结HCOMM依赖无阻塞问题才返回 PASS，否则 REVIEW_FAIL 或 BLOCKED。
```

## Verifier：候选构建、双轨测试与性能估算

```text
角色 hccl-verifier；engine=CCU；mode=candidate；task-id={task_id}；轮次={round}。
原始需求：{user_requirement}
HCCL={source_repo}；HCOMM={hcomm_repo}；候选HCCL身份={source_identity}；HCOMM依赖身份={hcomm_source_identity}。
环境={env_file}；任务目录={task_dir}；外部证据={external_evidence_root}。
读取有效基线、冻结 TEST_PLAN 和绑定当前HCCL候选与冻结HCOMM依赖的 REVIEW PASS。加载 hccl-ccu-best-practice/references/validation.md 与 hccl-test-tool-hvm，核对实际 CCU 模式和能力。
按目标版本 CCU 构建链路进行一次可追溯候选全量构建、归档与安装，再执行 A 定向算法命中 + B 同矩阵默认回归。保存真实命令、退出码、两仓/包/工具身份、逐用例日志与环境恢复状态。按ccu-automation.md复用冻结checker-plan.json和已有hvm plan.py；先创建输出目录再写日志，不另造执行脚本。在登记外部目录按冻结计划与真实构建身份写selection，运行summarize_ccu_evidence.py核对原始日志/身份及基线compare；报告引用汇总而非重抄统计，工具结果不替代本角色结论。
A/B 全部通过后，必须按 hccl-test-tool-hvm/references/estimate.md 串行启动独立 estimate 会话；复用同一候选包、HCCL/HCOMM 身份、冻结 CCU 模式和显式选路配置，记录本次实际算法命中。默认 mock-comm 112，用户指定组网时继承需求；按共享参考准备 CCU/DFS 环境，固定 -np 1、-b 1G -e 1G -w 0 -n 1 -c 0，不套用功能测试的rank数，不使用run.sh/plan.py执行估算。
将 estimate.json、测试/插件日志和 profiling/trace 归档到 {external_evidence_root} 的本轮唯一目录，填写 TEST_REPORT 的 estimate_* 头字段及性能估算部分。estimate.json 额外写 engine=CCU、冻结的 ccu_mode 与本次 hcomm_source_identity；算法耗时读取 makespan，不使用软件运行耗时。
estimate 失败、未执行、未命中或缺证据时保留 A/B 结果并返回 BLOCKED；仅独立证据证明源码问题时进入 SOURCE 修复，不因估算值较高自动修复。估算成功不代表性能收益 PASS，不设耗时阈值。
使用 ccu-test-report-template.md 和 ccu-handoff-template.md；只写 TEST_REPORT、HANDOFF 和登记的外部证据，禁止修改生产源码、冻结设计/附件、基线或测试期望。
默认不运行 ST/UT；缺工具/硬件或真实失败不得用静态结果补 PASS。返回 PASS、TEST_FAIL 或 BLOCKED；TEST_FAIL 必须标记 SOURCE 或 ENVIRONMENT，保留原始证据。VM 功能通过不声称 NPU 性能收益。
```
