# AICPU 四 Agent 协作工作流

## 1. 适用范围与真源

本文件是 `hccl-op-generator` 中 **AICPU** 算法开发的唯一流程控制真源，定义角色调用、状态流转、交接、失效和完成判定。它不复制 AICPU API、目录、算法或构建细节。

| 内容 | 真源 |
|---|---|
| AICPU 技术能力、跨层约束和客观验收规则 | `communication/` 下五个同级专项 Skill；共享契约与构建验证见 `hccl-aicpu-best-practice` |
| Architect、Developer、Verifier、Reviewer 的职责和权限 | `agents/hccl-*.md` |
| AICPU 状态机和失败回退 | 本文件 |
| Agent 调用参数 | [aicpu-task-prompts.md](aicpu-task-prompts.md) |
| CCU 能力状态 | 暂不对外支持；`workflow_policy.py route` 返回 `CCU_OUT_OF_SCOPE` |

HCCLBot 只编排和维护任务状态，不代替任何 Agent 设计、修改生产代码、检视或执行共享验证。

## 2. 任务目录与产物 owner

每个任务使用独立目录：

```text
${HCCL_ROOT}/src/ops/<op>/docs/<task-id>/
├── task-index.json
├── environment.md
├── TASK_SPEC.md
├── DATAFLOW_SPEC.md
├── dataflow/
│   └── <template>.md
├── DESIGN.md
├── PLAN.md
├── TEST_PLAN.md
├── BASELINE_REPORT.md
├── LOG.md
├── REVIEW.md
├── TEST_REPORT.md
└── HANDOFF.md
```

`DATAFLOW_SPEC.md` 始终存在，作为适用性与实际 spec 的索引。Skill 判定不需要 Dataflow Spec 时写 `status=NOT_REQUIRED` 和依据；需要时，每个 template 在 `dataflow/` 下保存一份实际 spec，索引状态必须为 `PASS`。候选包、源码快照和大体积原始日志放在 HCCL 构建清理目录之外，任务文档只记录绝对路径、哈希和身份。

| 产物 | 唯一写入 owner | 允许读取者 |
|---|---|---|
| `task-index.json`、`environment.md` | HCCLBot | 四个 Agent |
| `TASK_SPEC.md`、`DATAFLOW_SPEC.md`、`dataflow/*.md`、`DESIGN.md`、`PLAN.md`、`TEST_PLAN.md` | Architect | Developer、Verifier、Reviewer |
| HCCL 生产源码、CMake、`LOG.md` | Developer | HCCLBot、Verifier、Reviewer |
| `BASELINE_REPORT.md`、`TEST_REPORT.md`、构建和测试证据 | Verifier | HCCLBot、Reviewer |
| `REVIEW.md` | Reviewer | HCCLBot、Developer、Verifier |
| `HANDOFF.md` | 当前执行阶段的 Agent | HCCLBot、下一阶段 Agent |

同一文件同一时刻只有一个写入者。`HANDOFF.md` 由当前阶段 Agent 更新 `latest_*` 并追加记录，禁止覆盖历史；其余产物使用表中的固定 owner。HCCLBot 不在 Agent 产物中追加仲裁内容；争议和状态决定写入 `task-index.json`。

### 2.1 产物模板与有效状态

| 产物 | 模板 | 有效状态 |
|---|---|---|
| `task-index.json` | [aicpu-task-index-template.json](templates/aicpu-task-index-template.json) | `current_state` 为已通过门禁的状态 |
| `environment.md` | [environment-template.md](templates/environment-template.md) | `PASS` |
| `TASK_SPEC.md` | [aicpu-task-spec-template.md](templates/aicpu-task-spec-template.md) | `FROZEN` |
| `DATAFLOW_SPEC.md` | [aicpu-dataflow-spec-index-template.md](templates/aicpu-dataflow-spec-index-template.md) | `PASS` 或 `NOT_REQUIRED` |
| `DESIGN.md` | [design-template.md](templates/design-template.md) | `FROZEN` |
| `PLAN.md` | [plan-template.md](templates/plan-template.md) | `FROZEN` |
| `TEST_PLAN.md` | [aicpu-test-plan-template.md](templates/aicpu-test-plan-template.md) | `FROZEN` |
| `BASELINE_REPORT.md` | [aicpu-baseline-report-template.md](templates/aicpu-baseline-report-template.md) | `PASS` |
| `LOG.md` | [log-template.md](templates/log-template.md) | `PASS` |
| `REVIEW.md` | [aicpu-review-template.md](templates/aicpu-review-template.md) | `PASS` |
| `TEST_REPORT.md` | [aicpu-test-report-template.md](templates/aicpu-test-report-template.md) | `PASS` |
| `HANDOFF.md` | [aicpu-handoff-template.md](templates/aicpu-handoff-template.md) | `latest_status` 与本次 Agent 返回一致 |

模板中的 `schema_version`、`artifact`、`engine`、`owner`/`owner_policy`、`task_id`、`status`/`latest_status` 和源码身份字段不得删除。所有 `{...}` 必须替换，报告中的路径和 SHA-256 必须指向真实产物。只有状态值正确还不够，正文证据、身份和哈希也必须满足对应门禁。

`task-index.json` 的 `calls` 逐次追加真实 Agent 调用，至少包含 `call_id`、`role`、`target_state`、`status`、`source_identity`、`started_at`、`ended_at` 和 `outputs`。源码仓内的 `outputs` 使用相对 `source_repo` 的路径；Verifier 外部证据使用绝对路径，并且必须位于 `external_evidence_roots` 白名单下。调用失败也保留，禁止用后续 PASS 覆盖。`artifacts` 和 `dataflow_specs` 保存当前文件 SHA-256 与 `valid` 状态，`invalidated_artifacts` 保存失效原因。

HCCLBot 在首次调用 Verifier 前创建本任务专属证据目录，并把其绝对路径写入 `external_evidence_roots` 和 Verifier prompt。目录必须位于 `source_repo` 与 `task_dir` 之外，不能使用 `/` 或能够覆盖源码仓的父目录。HCCLBot 对任务目录、源码仓和这些白名单目录做调用前后快照；只有 Verifier 可以写白名单目录，其他 Agent 及 Verifier 对未登记外部路径的写入都会被门禁拒绝。

## 3. 状态机

```text
ENV_READY
  → DESIGN_READY
  → BASELINE_READY
  → IMPLEMENTED
  → REVIEW_PASS
  → TEST_PASS
  → COMPLETE

DESIGN_ISSUE → Architect
REVIEW_FAIL  → Developer → Reviewer
TEST_FAIL    → Developer → Reviewer → Verifier
BLOCKED      → HCCLBot 汇报证据与未完成范围
```

| 目标状态 | 执行角色 | 必要输入 | 有效输出与门禁 |
|---|---|---|---|
| `ENV_READY` | HCCLBot | 用户需求 | `environment.status=PASS`；记录仓库、具名分支、HEAD 和工作区状态 |
| `DESIGN_READY` | Architect | 原始需求、环境记录 | `TASK_SPEC/DESIGN/PLAN/TEST_PLAN.status=FROZEN`；`DATAFLOW_SPEC.status=PASS|NOT_REQUIRED`；无语义 TBD，实际 specs 的检查和哈希齐全 |
| `BASELINE_READY` | Verifier | 冻结的测试计划、旧包 | `BASELINE_REPORT.status=PASS` 且绑定冻结 `TEST_PLAN` 哈希；旧包、矩阵、算法名/次数、原始日志和就绪证据完整 |
| `IMPLEMENTED` | Developer | 冻结设计、基线报告 | `LOG.status=PASS`；生产源码/CMake 变更、静态证据和新的可恢复源码身份已记录 |
| `REVIEW_PASS` | Reviewer | 原始需求、设计、当前源码身份 | `REVIEW.status=PASS`，且 `source_identity` 与当前源码一致；文件或状态字段单独存在不算通过 |
| `TEST_PASS` | Verifier | 同身份 Review PASS、基线、测试计划 | `TEST_REPORT.status=PASS`，且 `source_identity=review_source_identity=estimate_source_identity=当前源码身份`；HVM 统一候选构建安装部署、归档、双轨、estimate 和环境清理满足 Skill 判据，估算状态为 `SUCCESS` 且原始证据完整 |
| `COMPLETE` | HCCLBot | Review/Test 报告 | Review PASS 与 Test PASS 绑定同一源码身份，且没有未解决阻塞项 |

HCCLBot 只在检查门禁证据后更新 `task-index.json`。Agent 自报“完成”或产物文件存在，都不能单独推进状态。

候选 Verifier 在 A/B 功能验证全部通过后必须执行 estimate，基线阶段不追加候选估算。默认 `mock-comm 112`，用户指定组网时继承其需求；执行参数和结果解释以 `hccl-test-tool-hvm/references/estimate.md` 为真源。性能估算写入既有 `TEST_REPORT.md`，原始证据和 `estimate.json` 归档到本轮任务专属外部证据目录。`TEST_PASS` 和 `COMPLETE` 门禁检查估算状态、当前源码身份、算法命中、固定参数、有限正数耗时、真实退出码及证据文件哈希；缺少估算的旧报告不能继续通过门禁。估算成功只表示得到可信仿真结果，不设性能收益阈值。

### 3.1 自动流转策略

HCCLBot 把本文件所在 `workflows/` 目录的绝对路径记为 `HCCL_AICPU_WORKFLOW_DIR`。每个正常阶段的角色返回后，先执行策略校验：

```bash
HCCL_AICPU_WORKFLOW_DIR="/absolute/path/to/hccl-op-generator/workflows"

python3 "$HCCL_AICPU_WORKFLOW_DIR/scripts/workflow_policy.py" transition \
  --engine AICPU \
  --state IMPLEMENTED \
  --actor hccl-reviewer \
  --result REVIEW_FAIL \
  --repair-round 0 \
  --json
```

只有 `ok=true` 才能采用决策。`ADVANCE` 才允许进入目标状态产物门禁；`REPAIR` 或 `REDESIGN` 时，把返回的 `repair_round`、`pending_action`、`next_roles` 分别写入 task-index 的同名字段，并严格按 `pending_roles` 首项调用下一角色。恢复链中每个角色返回后执行：

```bash
python3 "$HCCL_AICPU_WORKFLOW_DIR/scripts/workflow_policy.py" recovery \
  --engine AICPU \
  --state IMPLEMENTED \
  --pending-action REPAIR \
  --pending-roles hccl-developer hccl-reviewer \
  --actor hccl-developer \
  --result PASS \
  --repair-round 1 \
  --json
```

恢复链必须逐项消费，不能跳过、调换或并行执行。只有返回 `RECOVERY_COMPLETE` 后才能把 `pending_action` 置为 `NONE` 并运行状态门禁。`BLOCK` 必须保留当前状态和证据并停止；`REJECT` 表示角色、状态或结果不符合工作流，不能由 HCCLBot自行改写结果重试。

### 3.2 自动产物门禁

每次角色返回后，HCCLBot 先用调用前后的真实文件快照生成 changed paths，不直接信任 Agent 自报文件清单。Verifier 的快照范围还必须包含 `external_evidence_roots`。更新 `task-index.json` 的调用记录、产物哈希和失效记录后，依次执行：

```bash
HCCL_AICPU_WORKFLOW_DIR="/absolute/path/to/hccl-op-generator/workflows"

python3 "$HCCL_AICPU_WORKFLOW_DIR/scripts/validate_aicpu_artifacts.py" \
  --task-dir "${HCCL_ROOT}/src/ops/${op_type}/docs/${task_id}" \
  --actor hccl-architect \
  --changed <相对 source_repo 的实际变更路径...>

python3 "$HCCL_AICPU_WORKFLOW_DIR/scripts/validate_aicpu_artifacts.py" \
  --task-dir "${HCCL_ROOT}/src/ops/${op_type}/docs/${task_id}" \
  --target-state DESIGN_READY
```

`--actor` 替换为本轮实际角色，`--target-state` 替换为将进入的状态。两个命令都返回 0 后，HCCLBot 才更新 `current_state`，并以新状态再运行一次目标状态门禁；任一非零都不得推进。环境阶段使用 `--actor hcclbot --changed ...` 和 `--target-state ENV_READY`。最终 `COMPLETE` 只运行目标状态门禁，不产生伪 Agent 调用。

门禁自动检查必需产物、头字段、owner、状态、占位符、源码身份、依赖哈希、Dataflow 实际 Spec、Agent 调用、角色写入边界和 Review/Test 失效标记。它检查结构与证据一致性，不代替 Reviewer 的技术检视或 Verifier 的真实构建和双轨测试。

## 4. 源码身份与结论失效

源码身份至少包含仓库路径、分支、HEAD、工作区差异或可恢复快照标识。优先使用 `hccl-aicpu-best-practice/scripts/` 下的 `workflow.py preflight` 和 `source_snapshot.py` 产物，不用聊天描述替代未提交改动身份。

| 变化 | 必须失效的状态 | 重新执行 |
|---|---|---|
| 生产源码、CMake 或生成输入变化 | `REVIEW_PASS`、`TEST_PASS` | Reviewer 复审；Verifier 按影响重建和重验 |
| `TASK_SPEC.md`、`DESIGN.md`、`DATAFLOW_SPEC.md`/实际 specs 或 `PLAN.md` 语义变化 | `DESIGN_READY` 之后全部状态 | Architect 重新冻结，随后基线/实现/审查/测试按影响重走 |
| 测试矩阵、默认选路许可或 Checker 配置变化 | `BASELINE_READY`、`TEST_PASS` | Verifier 以同一新矩阵补齐基线和回归 |
| 仅报告排版变化，且内容哈希与源码身份不变 | 不自动失效 | HCCLBot 记录变更原因 |

旧报告必须保留原身份，不得覆盖成新版本 PASS。HCCLBot 在 `task-index.json` 中记录当前有效报告及被取代报告。

## 5. 角色权限边界

| 角色 | 可执行 | 禁止 |
|---|---|---|
| Architect | 澄清需求，冻结设计、Dataflow Spec 和测试矩阵，运行设计期只读/静态检查 | 修改生产源码，构建候选包，安装，运行 Checker，给代码 Review PASS |
| Developer | 按冻结设计修改生产源码和 CMake，运行不占用共享环境的静态检查，记录变更 | 修改基线/测试期望，安装包，运行共享 Checker，写 Review/Test PASS |
| Reviewer | 从原始需求独立检视当前源码、Spec、跨层契约和证据身份，写 `REVIEW.md` | 修改生产源码，运行共享构建或 Checker，改写测试结果，用静态结论替代功能验证 |
| Verifier | 独占旧包保全、基线、构建、归档、安装、配置切换、Checker 和证据固化 | 修改生产源码，改变冻结测试期望，豁免失败，代替 Reviewer 作质量裁决 |
| HCCLBot | 路由、调用 Agent、检查门禁、更新 `task-index.json`、汇报 | 直接承担上述四种角色，修改 Agent 产物以制造 PASS |

## 6. 调用与共享环境规则

1. AICPU 的每次角色调用必须读取 [aicpu-task-prompts.md](aicpu-task-prompts.md) 的对应模板，并向 Agent 提供 §2.1 对应产物模板路径；只替换列出的占位符，不把 Skill 技术正文复制进 prompt。
2. 输入必须包含任务 ID、任务目录、原始需求、当前源码身份、所需产物路径和权限边界；Reviewer 首次输入不得携带 Developer 的推测结论。
3. 四个角色必须实际由运行器调用并记录任务/会话标识；能力不可用时进入 `BLOCKED`，不得声称完成了独立检视或验证。
4. Agent 不递归创建同职责 Agent。只读分析可在输入互不依赖时并行，但不能提前假设尚未返回的结论。
5. 共用构建目录、CANN 安装、mock-comm、Checker、配置切换和共享内存清理只由 Verifier 串行操作。进程内 `-j` 并行不属于多 Agent 争用。
6. 构建、安装或 Checker 运行期间冻结其输入源码；日志诊断读取带 run-id/case-id 的已完成证据副本。
7. 默认不编写、构建或运行 HCCL 仓内 ST/UT。用户明确要求时由 Verifier 执行并单独报告，但不能替代双轨 Checker。

## 7. 失败、冲突与修复循环

| 结果 | 流转规则 |
|---|---|
| Architect 返回 `DESIGN_ISSUE` | 保持在设计阶段，补充用户输入或重新调用 Architect |
| Reviewer 返回 `REVIEW_FAIL` | Developer 定向修复；源码身份更新后 Reviewer 独立复审 |
| Verifier 返回 `TEST_FAIL` 且定位为源码问题 | 固化失败证据，Developer 定向修复，再 Reviewer 复审和 Verifier 重验 |
| Verifier 返回环境阻塞 | 保持失败事实；只在有新环境证据时由 Verifier 做最小区分实验，不调用 Developer 猜修源码 |
| 双轨已通过但 estimate 失败、未执行、未命中或缺证据 | 保留功能验证结果并返回 `BLOCKED`；报告实际限制与下一项所需输入。只有独立证据证明源码问题时才按 `SOURCE` 修复，不因估算值较高自动修复 |
| Agent 结论冲突 | HCCLBot 对齐输入版本和对象身份，调用对应角色用最小证据区分；不投票、不改写报告 |

Review/Test 修复使用同一个 `repair_round`，合计最多 3 轮：初始为 0，每次策略返回 `REPAIR` 时加 1；值为 3 后再次失败必须进入 `BLOCKED`。达到上限仍未通过时报告原始证据、已验证范围和下一项所需输入。相同条件没有新证据时不得循环重试到 PASS。

## 8. 交接最小字段

每次 `HANDOFF.md` 按 [交接模板](templates/aicpu-handoff-template.md) 追加，至少记录：

- 任务 ID、当前 Agent、输入状态和输出状态
- 输入源码身份、输入产物及其哈希/路径
- 新增或更新的输出产物
- 结论：PASS、FAIL、DESIGN_ISSUE、REVIEW_FAIL、TEST_FAIL 或 BLOCKED
- 未确认项、阻塞证据和建议下一阶段
- 是否触发 Review、Test 或 Baseline 失效

当前阶段 Agent 只能修改顶部 `latest_*` 字段并追加自己的记录，不得改写既有条目。HCCLBot 将角色、调用 ID、开始/结束时间、状态、当前源码身份和有效报告路径同步到 `task-index.json`。

## 9. 完成判定

只有同时满足以下条件才进入 `COMPLETE`：

1. 设计和测试矩阵已冻结，基线证据完整。
2. Reviewer 对当前源码身份给出 PASS。
3. Verifier 对同一源码身份完成 HVM 统一候选构建安装部署和 A/B 双轨 Checker，全部满足 `hccl-aicpu-best-practice/aicpu-shared-contract.md` 的客观判据。
4. 默认选路变化没有超出用户批准范围；任何 FAIL、SKIP 或未验证项均被如实列出且不冒充 PASS。
5. 没有遗留后台测试、临时配置覆盖或共享环境清理项。
6. Verifier 对同一候选包、源码身份和目标算法完成 estimate，`estimate_status=SUCCESS`；算法命中、估算条件、算法耗时、原始日志与 profiling/trace 证据已归档，并在 `TEST_REPORT.md` 中明确记录观察和限制。

最终汇报区分已验证行为、独立检视结论和未验证范围，不用“流程已走完”替代证据。
最终汇报必须包含“算法性能估算”，从有效 `TEST_REPORT.md` 呈现实际算法、组网、数据量/类型、估算耗时、观察和证据路径；明确其为该条件下的仿真估算。失败或未执行时呈现原因和阻塞状态，不省略本节或复用示例数值。
