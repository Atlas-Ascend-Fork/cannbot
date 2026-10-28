# 异步调度契约

本页是调度 schema、状态与交接的唯一解释入口。适用于新策略下的跨 tile、多 engine、异步缓冲复用及相关事件协议；原五阶段、角色、round/gen/state 不变。契约把原有依赖分析转成实施要消费的候选证据，不声称能证明任意 kernel 安全或预测速度。

## 策略、适用性与兼容

新请求默认 `schedule_policy={"id":"schedule_contract_v1","version":1}`，冻结到 `manifest.configuration.schedule_policy`。历史 request/manifest 缺字段保持旧流程；恢复不能静默补策略或重写旧报告。未知策略版本须拒绝，version 必须为整数 1；策略改变按输入身份变化处理。manifest 引用冻结 request 时，检查 request 文件 SHA 及两处策略一致性；不能删除 manifest 策略冒充旧任务。

主 Agent 依据真实代码、方案范围与已验收证据复核是否涉及调度，不由候选随意填写不适用。普通单流水局部修改可说明不涉及跨任务顺序/同步/复用的依据；复用已验收契约时必须核对相同 scope、源码/编译身份和覆盖条件。不能用“未改 API 名称”推定调度没变。no-op 也需对应实际保留实现的证据。

每份就绪实施契约使用以下引用；`path` 指向实际文件，`sha256` 为该文件内容摘要。model 检查报告先冻结；实施代码尚未生成时不能编造候选 SHA。

```json
{
  "schedule": {
    "contract": {"path": "/abs/analysis/roundN/schedule-contract-scheme.json", "sha256": "<actual sha256>"},
    "check": {"path": "/abs/analysis/roundN/schedule-check-scheme-model.json", "sha256": "<actual sha256>"}
  }
}
```

实施结果以 `schedule.check={path,sha256}` 引用当前候选的 runtime 检查报告。模型契约冻结后不随实施源码改写；lowering/runtime 外部 evidence 绑定实际候选源码快照与生成/编译/运行文件，防止把分析时的模型身份误当成实施源码身份。

## schema 1：schedule-contract

执行真源是 `$WORKFLOW_SCRIPTS/validate_schedule_contract.py`。字段名区分大小写；下面列出本版本接受的结构和解释。所有文件引用均为**仅有** `path` 与 `sha256` 的对象，使用 canonical 绝对路径和当前内容 SHA；证据数组必须非空。证据文档内部可用源码行号定位，不能把 `file:line` 作为文件路径。

| 顶层字段 | 类型与含义 |
|---|---|
| `schema_version`, `kind`, `scheme_id` | 固定 `1`、`"schedule-contract"`，非空方案 ID，与实施契约一致 |
| `candidate_root` | 冻结的候选目录绝对路径；model 层不冻结尚待修改的候选内容 |
| `scope` | `{collection, target_socs, case_ids, description}`；collection 为 `performance_tuning`、`performance_full` 或 `generalization_full`，必须存在于 manifest；case_ids 非空、唯一且精确覆盖该冻结集合全部 case。检查器读取集合文件并核对 SHA；SoC 列表与 manifest 完全一致，description 写覆盖范围 |
| `identities` | `baseline/model/compiler/workload` 为文件引用，分别绑定来源/源码身份清单、模型定义、编译环境身份和负载协议。`reference` 必须出现：有参考时为文件引用；无可比参考时写 null，并填写顶层 `reference_absence_reason`，不虚构参考实现 |
| `reference_absence_reason` | identities.reference 为 null 时必需的非空字符串，说明参考为何缺失或不可比；不因此阻止基于当前基线的分析 |
| `applicability` | `{required: bool, reason: string, evidence: [ref], features: {cross_tile: bool, multi_engine: bool, async_reuse: bool}}`；任一触发事实为 true 时 required 不可 false；全 false 仍须证据与主 Agent 复核 |
| `model` | `{version: string, boundaries: [string]}`；非空版本和边界列表，说明有限展开范围、未建模行为、资源模型假设 |
| `unknowns` | 数组，每项 `{kind: "safety"或"performance", question: string, status: "open"或"resolved", evidence: [ref]}`；resolved 必须有非空证据，open safety 阻止实施，open performance 不阻止 |
| `coverage_review` | `{complete: bool, evidence: [ref], blocking_issue_review: [ref]}`；两组引用均必填非空。evidence 审阅源代码与模型 task/edge/branch 完整性；blocking_issue_review 审阅 scalar/API 的阻塞提交语义，因为检查器不模拟阻塞 issue。未完成最多 MODEL_FEASIBLE，不能靠图无环冒充 complete |
| `tasks/programs/resources/buffers/branches/events/edges/capacities` | required=true 时按下表完整展开；不适用契约仍保留上述身份、审阅、未知项与 evidence，不能跳过策略引用和实施验收 |

所有具有 `id` 的数组，其 ID 在本数组内非空且唯一。这里用有限场景展开，不把一条符号化循环自动当作已检查全部迭代。

| 对象 | 必需字段与语义 |
|---|---|
| `programs[]` | `{id, submission_order: [task_id]}`；每个 task 恰好出现在所属程序一次；程序有序提交不自动增加前任务 complete → 后任务 start |
| `resources[]` | `{id, mode: "exclusive"}`；本版本仅支持明确排他的资源。同资源活动 task 必须有可达的完成顺序；同一 program、同一 resource 还须符合 submission_order 的 FIFO 顺序，跨 program 不强加该 FIFO 顺序。可并行 pipe 分开建资源，不能用虚构单一 Vector 资源掩盖硬件结构 |
| `tasks[]` | `{id, program, resource, coordinates: {query,tile,subtile}, branches: [branch_id], source: [ref], completion_event: string, reads: [access], writes: [access]}`；reads/writes 可空，branches/source 非空。coordinates 精确包含三键。completion_event 是完成语义标记，需要生成代码审阅；仅填写字符串不能证明真实事件存在 |
| `access` | `{buffer: buffer_id, view: view_id, generation: nonnegative_int}`；物理 slot 由 `generation % depth` 确定，generation 不等于本地循环 tick |
| `buffers[]` | `{id, memory, bytes, depth, alignment, initial_generations: [nonnegative_int], views: [view], initialization: string, drain: string}`；bytes 为**单槽物理字节**，depth/alignment 为正整数，bytes 须对齐；初始化代可无生产写入，必须审阅其真实初始化责任 |
| `view` | `{id, offset: nonnegative_int, bytes: positive_int}`；范围不得超出单槽。不同 view 共享字节范围即 alias；不得把同一物理存储伪装为独立 buffer |
| `capacities` | `{memory_id: positive_int_bytes}`；本版本按该层所有 buffer 的 `bytes * depth` 静态预留总量核验，**不做**动态生存区间装箱；每核独立空间须使用可区分的层级/资源 ID |
| `edges[]` | `{kind: "data"或"resource"或"reuse", from: task_id, to: task_id, from_phase: "complete", to_phase: "start", source: [ref]}`；保留边类别与证据。在分支中仅两端都活动时生效；跨分支义务不能靠被过滤的边满足 |
| `branches[]` | `{id, predicate: string, case_ids: [case_id]}`；case 非空且在 scope 内，所有分支并集覆盖 scope；每个分支需活动 task。predicate 是待源码复核的声明，checker 不求解任意表达式 |
| `events[]` | `{id, hardware_id: string, generation: nonnegative_int, initial_tokens: nonnegative_int, drain_tokens: 0, source: [ref], publishes: [endpoint], waits: [endpoint]}`；每分支 token 平衡，硬件 ID/generation 不可重复。端点可空但必须提供数组 |
| `endpoint` | `{task: task_id, pipe: resource_id, tokens: positive_int}`；pipe 必须等于端点 task 的 resource。当前模型保守地将每个 publish complete 连到每个 wait start；部分 token 唤醒必须拆成独立事件代，不把复杂计数协议强塞进单事件 |

模型检查每个 branch 的 submit/start/complete 图、数据写入覆盖、同资源顺序、同槽重叠字节读写顺序、代际复用及事件再次发布前的消费。所有权、全部消费者、最后读者从物理 access 与边推导，源码语义完整性由 coverage_review 负责。模型不是任意控制流解释器，不能证明未声明 task/alias/branch 正确。

## schema 1：外部 schedule evidence 与报告

lowering/runtime 的 `--evidence` 文件包含：

| 字段 | 内容 |
|---|---|
| `schema_version` | `1` |
| `contract`, `manifest` | 对应冻结文件引用 |
| `candidate` | `{path,sha256}` 源码目录快照，使用 checker 的 `source_identity(candidate_root)`；与普通文件 SHA 不同，不手算任意目录哈希替代 |
| `scope` | 与 contract.scope 完全相同 |
| `compiler` | 与 contract.identities.compiler 完全相同的文件引用 |
| `lowering` | `{status: "pass", generated_code: [ref], build: [ref], task_mapping: [ref], event_mapping: [ref], last_reader_review: [ref]}`；每项引用非空真实文件。映射文档记录源码/生成代码位置、事件 pipe/generation、分支计数、alias 与最后读者 |
| `runtime` | runtime 层必需：`{status: "pass", load: [ref], execution: [ref], precision: [ref], sequence_stress: [ref], covered_branches: [branch_id], coverage: [coverage_row]}`；分支 ID 列表与契约 branches 顺序相同。每项引用真实加载/运行/精度/序列证据；缺覆盖不可声明 pass |
| `coverage_row` | `{case_id, target_soc, branch, evidence: [ref]}`；逐 `branch.case_ids × scope.target_socs` 的组合精确覆盖，无重复或越界，每行非空真实证据。没有 branches 的不适用契约用 `branch: null`，覆盖 `scope.case_ids × scope.target_socs`；只列 covered_branches 不能代替逐例证据 |
| `integration` | 回集成验收时必需的外部 evidence 块：`{execution_identity: ref, postprocess_gates: [ref]}`；验证与提交方式见下节 |

不适用调度建模时依然提供对应当前候选的构建/加载和原功能证据；task/event mapping 等可引用经审阅的不适用说明，不能伪造任务或测试。修改候选前先确认目录快照排除项；证据不要随意放进会计入源码身份的目录造成自引用。构建/工具链变化需要新契约身份，不能在外部 evidence 中换 compiler 来沿用旧模型。

`schedule-check` 由工具生成，包含 schema/kind、scheme_id、level、status/decision、contract/manifest 引用、candidate_root、可选 candidate/integration、evidence、scope、dependencies、checked、errors、unknowns、limitations。dependencies 保存契约/manifest/checker 本身、冻结 case 集合、存在时的 request 及证据 SHA；恢复时重新计算并比较报告，不能只读 decision。`checked` 仅列已验证的任务/分支计数和静态预留字节。SHA 证明来源未变，不证明审阅文档的陈述为真。

## 回集成身份与全集门禁

启用 schedule_policy 时，phase.integration 除原 `VERIFY_REPORT.md`、源码隔离/安全和逐 SoC postprocess gates 外，必须提交**带 integration 链的当前集成实现 schedule runtime conformance gate**。不能把实施候选目录的旧 runtime gate 当作原工程回集成完成证明。

外部 evidence 的 integration 字段按上表引用已有 execution identity 与 postprocess gate 格式，不另造一套身份或性能规则。检查器执行以下交叉核验：

1. contract.scope.collection 为 `performance_full` 或 `generalization_full`，case_ids 精确匹配该冻结全集；runtime.coverage 仍逐 case × SoC × branch 对应实际证据。
2. execution_identity 沿现有 schema 1，其 source.path 必须是当前集成 candidate_root；原身份检查器实时核验源码快照、build/loaded SHA、构建收据与运行源材料，不能以文件存在代替同源链。
3. 每个目标 SoC 恰有一份 postprocess gate，按原 `validate_postprocess_performance.py` 重算并须 pass；该 gate 各集合的 candidate CSV 路径/SHA 必须出现在同 SoC execution identity 的 `runtime.source_artifacts`。因此功能/性能全集结果与真实集成运行相连。
4. 源码、运行材料、全集 CSV、effect proof 等依赖纳入报告 SHA；当前链有变更时旧 gate 失效。

换集成 root 即新候选身份：为实际原工程 root 形成对应的 model/runtime 和 implementation conformance 证据，按已冻结集成 scope 复验；不能只编辑旧报告的路径。相同 root、相同源码/构建/加载/覆盖身份可复核后复用，不为文档变化重复设备采集。回路由或编译分支变化仍须验证新身份。

## 显式补登记已冻结策略

常规新任务不调用本迁移。仅旧 state writer 漏存了**request/manifest 早已冻结**的 schedule_policy，且尚未开始分析或实施时，才可由主 Agent 使用：

```bash
python "$WORKFLOW_SCRIPTS/workflow_state.py" migrate-workflow \
  --state /abs/workflow-state.json --audit /abs/schedule-policy-migration.md \
  --workflow-version <current-workflow-version> --adopt-schedule-policy
```

审计文件必须非空。工具要求 state 原本没有 schedule_policy、manifest 文件身份与 state 原记录完全一致、request SHA 有效且 request/manifest 策略一致；stages、events 和 current_stage 中不得出现 analysis、implementation、round.complete、acceptance、selection 或 integration 等受策略约束活动。迁移只补登记遗漏字段，记录 `schedule_policy_adopted` 和 workflow_migration 事件；不允许更改已有策略、给历史缺策略任务偷偷升级、修改 manifest 后借迁移通过，或在后期补写已完成阶段的证据。常规版本迁移仍只失效受影响保存点。

## 证据状态与责任

| 状态 | 含义与下一步 |
|---|---|
| `MODEL_REJECTED` | 已声明模型内约束失败，不实施该模型；修正假设或约束后新建候选 |
| `MODEL_FEASIBLE` | 已建模约束通过，未证明实施就绪、runtime 安全或速度 |
| `needs_probe` | 关键 API、同步、事件或所有权事实未确认，先隔离探针补证 |
| `ready_for_implementation` | 必要模型检查通过且安全关键未知已解决，可冻结并实施；纯性能收益可 unknown |
| `lowering_verified` | 实际生成代码的任务/事件/复用与契约核对完成；仍需运行/精度/序列门禁 |
| `eligible` | 对应候选的 lowering 与运行证据及原符合性、功能、序列门禁完成，可以正式测速 |
| `selected` | 仅为原终选流程中的结果，由冻结性能采集和统计策略决定；调度 checker 不授予该结果 |

analysis 负责 A1 恢复、A2 约束、A3 候选，implementation 负责实现与生成代码/运行核对，主 Agent 复核与登记。模型、表和图都属于 roundN 派生证据，不另建第二份状态台账。

安全未知和性能未知分别记录。前者包括 API 完成语义、wait/set 是否覆盖正确 pipe、slot 是否仍被读、事件是否匹配等，未解决先 probe。后者包括可隐藏的等待、共享带宽、编译器调度效果和完整调用收益，可在合法候选上实测。模型合法不等于更快；不能靠抽象单位时长或固定 lag/depth 给性能排名。

## 检查器调用与身份

```bash
python "$WORKFLOW_SCRIPTS/validate_schedule_contract.py" \
  --contract /abs/analysis/roundN/schedule-contract-scheme.json \
  --manifest /abs/run-manifest.json --level model \
  --out /abs/analysis/roundN/schedule-check-scheme-model.json

python "$WORKFLOW_SCRIPTS/validate_schedule_contract.py" \
  --contract /abs/analysis/roundN/schedule-contract-scheme.json \
  --manifest /abs/run-manifest.json --level runtime \
  --evidence /abs/candidate/schedule-evidence.json \
  --out /abs/candidate/schedule-check-runtime.json
```

只核对 lowering 时用 `--level lowering` 与相应 evidence。复用报告使用同一组当前输入参数和 `--verify-existing <报告路径>`。不能用文件存在、旧 pass 或手写状态替代检查器验证。

候选源码快照采用既有 source-isolation snapshot 算法；生成代码/编译/运行证据各自绑定真实文件 SHA。源码、调度参数、模型、SDK/编译配置、实际加载产物或输入分支变化时，重新评估受影响证据。同身份且覆盖完全一致可复用已有结果；不同候选、不同生成代码或不同输入分支的报告不能借用。

## 模型边界与验收

模型必须区分真实微任务和独立程序：同一程序提交顺序不代表跨程序共享物理时刻。data 边连生产完成和消费者首读；resource 边表达真实 pipe/FIFO 与提交约束；reuse 边连前一代最后读完成和同物理区域下一代首写。所有别名视图、分片、两个 AIV 和最终写回都必须纳入最后读者判断。

容量按存储层级、物理字节/对齐/depth 与并发存活区间计算。事件需说明生产者、消费者、等待 pipe、ID/generation、初始 token、分支发布/消费次数、初始化和排空；无环 DAG 不足以证明条件事件协议正确。引用证据与机械检查覆盖范围以 checker 为准，报告 pass 不能证明未声明的边完整。

物理读域包含真实指令访问的 padding 与被后续 mask 丢弃的 lane；没有 ISA/API 并发语义证据时，不从“结果未使用”推定跨槽读写无冲突。`hardware.memory` 的容量依据须区分物理总量、SDK 可用量及 reserved/stack 占用；静态分配通过检查只说明未超过声明值，不证明该声明值可供当前产物使用。继承的基线证据不能自动支持新增分配或新的 alias。

lowering 核对必须引用当前生成代码中的 task/edge/buffer/event 映射；runtime 依据冻结支持范围覆盖满/单 tile、短长 query 交替、空 query、尾块、sink/LSE、两个 AIV 不均衡、槽位回绕和最终输出等待。不存在的路径记录真实接口依据；未运行不能写成已覆盖。通过调度检查也不能跳过原功能全集、精度、运行身份和性能协议。

冻结范围外的辅助边界诊断不得冒充主用例：`scope` 和 `branches.case_ids` 仍只引用冻结集合及其输入实际可达场景，`runtime.coverage` 也只登记这些真实运行。辅助报告使用独立 diagnostic ID，记录准确输入、实际分支、源码/编译/加载/进程及输出身份，可由 `coverage_review.evidence`、安全 unknown 的 evidence 和 runtime 的 precision/sequence_stress 引用绑定。`model.boundaries` 须说明这些辅助路径不在主图的机械覆盖声明内；`coverage_review.complete=true` 只表示声明的有限模型完成审阅，不能隐藏尚未解释的公共合同安全问题。辅助报告的 SHA 校验不等于机械证明其输入或分支覆盖。本版本没有独立辅助 case 注册与覆盖矩阵，若需要机械验证这些额外路径，必须显式扩展 schema/检查器，不能改写冻结 case 或填写虚假覆盖。

实例化工作表见 `ascendc-performance-review` 的算法/调度/后端三层模板 `references/async-schedule-templates.md`。模板只固定依赖与所有权原则，不固定历史 lag、depth、tiling 或性能数字；DSL 表达由本机真实源码、sample 与生成代码核验。
