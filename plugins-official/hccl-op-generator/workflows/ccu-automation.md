# CCU 初始化与证据工具

HCCLBot使用初始化工具；Architect冻结可执行计划；Verifier使用现有测试计划执行器与只读汇总。工具处理目录、字段、哈希和统计，角色保留技术判断与报告，原状态流和门禁继续执行。

## 任务初始化

在已确认 HCCL/HCOMM 路径、具名分支和用户原始需求后：

```bash
python3 "$HCCL_WORKFLOW_DIR/scripts/init_ccu_task.py" init \
  --source-repo /path/to/hccl --hcomm-repo /path/to/hcomm \
  --op-type all_gather --task-id allgather-ring-ccu-example \
  --requirement-file /path/to/request.txt \
  --evidence-root /path/to/tasks/allgather-ring-ccu-example/evidence
```

只读查询 Git，创建新的任务目录、证据目录、`environment.md` 草稿与 `task-index.json`；已有目录拒绝覆盖。不建分支、不构建/安装，不自动写环境PASS。索引的ENV_READY标签是待校验目标，草稿环境`BLOCKED/valid=false`不能通过门禁。

脏仓必须追加已经确认的 `--source-identity` / `--hcomm-source-identity`，包含当前完整HEAD与DIRTY，并另保留可恢复快照；工具不猜清洁身份，不替代快照。工具记录内容指纹，绑定环境时复查两仓；HCCL排除本次任务文档目录，生产源码、HCOMM内容仍参与检查。

HCCLBot按`hccl-env-check`核对并完善自己拥有的环境报告。报告已经明确PASS且身份一致后，绑定其实际哈希：

```bash
python3 "$HCCL_WORKFLOW_DIR/scripts/init_ccu_task.py" bind-environment --task-dir "$TASK_DIR"
python3 "$HCCL_WORKFLOW_DIR/scripts/validate_ccu_artifacts.py" \
  --task-dir "$TASK_DIR" --ccu-skill-dir "$CCU_SKILL_DIR" --target-state ENV_READY --json
```

绑定只更新初始索引的ENVIRONMENT条目和时间，不改报告、状态或调用记录；已有下游调用/产物时拒绝。任务仍需原权限与环境门禁。调用开始/结束时间从运行器实际事件记录，不能用文档创建时间或估计时间填充。

## 保存设计来源报告

Architect在已创建的任务目录运行，`OP_TYPE`取HCCL目录名（例如`all_reduce`，不是HVM的`allreduce`）：

```bash
python3 "$CCU_SKILL_DIR/scripts/inspect_sources.py" \
  --hccl-root "$HCCL_ROOT" --hcomm-root "$HCOMM_ROOT" --op "$OP_TYPE" \
  --output "$TASK_DIR/source-report.json" --summary
```

仓内仅允许当前算子任务目录中的 `source-report.json` 或 `source-report-r<正整数>.json`，拒绝覆盖已有修订和写生产源码/HCOMM；其他输出可放仓外。知识卡检查同时查看operator.checked_cards/status，拼错目录名返回2，暂无算子卡时不把公共卡MATCH当成接入已核验。FastLaunch契约可用cache_launch_offset声明缓存中的启动起点，默认0兼容旧契约，Reduce带长度头的样本为1；物理缓存更新索引保持原下标。

### 重新设计与历史来源证据

来源变化需要重新设计时，由 Architect 选择尚未使用的修订号，例如：

```bash
CCU_SOURCE_REPORT=source-report-r2.json
python3 "$CCU_SKILL_DIR/scripts/inspect_sources.py" \
  --hccl-root "$HCCL_ROOT" --hcomm-root "$HCOMM_ROOT" --op "$OP_TYPE" \
  --output "$TASK_DIR/$CCU_SOURCE_REPORT" --summary
sha256sum "$TASK_DIR/$CCU_SOURCE_REPORT"
```

旧 `source-report.json` 和已生成的修订报告保留原文件名与字节，作为历史归档；不要删除或覆盖它们。Architect 将 DESIGN 的 `source_report_file` 改为新文件名，并绑定实际 `source_report_sha256`，在接入记录中保留旧报告文件名/哈希与本次变化依据。缺省文件名的历史任务继续使用初版报告。实际调用 outputs 必须包含所选新报告；生产实现后的候选身份仍记录到 LOG/REVIEW/TEST_REPORT，不让 Developer 重写设计输入报告。

HCCLBot 按失效/REDESIGN 流程更新索引，保留原始调用与失效记录，再执行附件对应的重绑定工作单：

```bash
python3 "$HCCL_WORKFLOW_DIR/scripts/validate_ccu_artifacts.py" \
  --task-dir "$TASK_DIR" --rebind-report SOURCE_REPORT --json
python3 "$HCCL_WORKFLOW_DIR/scripts/validate_ccu_artifacts.py" \
  --task-dir "$TASK_DIR" --verify-rebind --json
```

工作单按 SOURCE_REPORT→DESIGN→下游报告排序；每个 owner 完成实际复核后才绑定父项当前哈希。审计核对来源、launch/sync 契约及采用时的知识基线和 checker-plan，不自动恢复索引 valid、角色结果或状态。仍须执行对应目标状态门禁。

### 采用已重新核验的知识基线

源码漂移由 Architect 定向核对并在 DESIGN 记录方法、差异与核验依据；需要采用新的知识基线时，使用任务内 `knowledge-baseline.json` 副本，保留 Skill 自带基线。复制或修改哈希本身不构成核验。维护方法见技能仓的 `docs/hccl-ccu-skill-maintenance.md`，Reviewer 继续独立检查适用性。

生成新修订来源报告时给 `inspect_sources.py` 追加 `--baseline "$TASK_DIR/knowledge-baseline.json"`；`check_knowledge.py`、`check_contracts.py` 及独立 sync/arith 检查器也使用同一 `--baseline`。在 DESIGN 头绑定 `knowledge_baseline_sha256`，并在 Architect 实际 outputs 中列出该文件。门禁校验附件哈希及来源报告中的基线摘要，再向同步和算术检查器传递 `--baseline`；缺文件、未绑定、漂移或使用了另一份基线均阻断。未选择新基线的历史任务沿用既有规则。

基线修订用 `--rebind-report KNOWLEDGE_BASELINE SOURCE_REPORT` 生成 owner 工作单，随后运行 `--verify-rebind` 和目标状态门禁；不得通过仅刷新知识卡哈希来消除真实漂移。

## 冻结和执行测试计划

六算子先运行CCU Skill的`preview_cases.py --op <算子目录名>`，用真实rank、dtype和数据量计算实际count/bytes与基本分配；按operator-index.md区分目录、DSL和HVM算子名。源模型只核验公共文件和本算子文件。rooted算子可预检--root-rank，归约算子可预检--reduce-op；当前HVM封装固定sum/默认root0，非默认值须使用经验证的定向runner或直接MPI命令，保存同等证据，不能直接放入不支持这些参数的checker-plan.json。非默认案例单独保存含root/reduceType的ID与原始命令，当前HVM的case key/compare不区分这些维度，不用默认case汇总代替覆盖。覆盖目的、源码分支、完整内存预算与不可达项留在TEST_PLAN。

参数较多时，Architect使用已安装`hccl-test-tool-hvm/references/test-plan.md`的schema创建可选`checker-plan.json`，在TEST_PLAN头写`checker_plan_sha256`。该文件归Architect所有，路径和哈希经TEST_PLAN依赖链传播；版本3门禁在附件存在/声明时核对，不要求历史任务补文件。运行`plan.py check`检查完整格式。未来包身份可用预定artifact.json路径，在Verifier实际构建后填充对应归档文件，不能改冻结用例或预期。

机器计划只存批次参数和覆盖case-id；TEST_PLAN记录目的与可达性，引用批次，不把完整矩阵在多处复写。基线/回归矩阵保持一致，定向批次明确DSL与expect_algo，冒烟独立成单用例。计划冻结后不由Verifier补写或改期望。

```bash
python3 "$HVM_SKILL_DIR/plan.py" check "$TASK_DIR/checker-plan.json"
python3 "$HVM_SKILL_DIR/plan.py" run "$TASK_DIR/checker-plan.json" \
  --role baseline --output "$EXTERNAL_EVIDENCE_ROOT/baseline-run"
```

候选依次用`--role directed`与`--role regression`和各自全新输出目录执行；只由Verifier在原授权、可信包和对应状态下运行。现有执行器先创建批次目录再打开console.log、串行执行、记录命令/时间和统计、失败后停止，不自动重试、安装或改计划。`--dry-run`只能检查命令，不作测试证据。不向尚未创建的输出目录重定向执行器stdout。

## 功能验证后的性能估算

候选 directed/regression 全部通过后，由 Verifier 按已安装 `hccl-test-tool-hvm/references/estimate.md` 串行执行独立 estimate。`plan.py`、checker-plan.json 和下面的汇总工具仅处理功能轨道，不执行或验收 estimate。复用已验证候选包、两仓身份与冻结 CCU 模式；在本轮登记外部目录归档共享格式的 estimate.json，额外填 `engine=CCU`、`ccu_mode`、`hcomm_source_identity`，并保留真实命令、退出码与原始文件哈希。报告引用证据路径和估算结果，HCCLBot 使用 CCU 的 TEST_PASS/COMPLETE 门禁校验。

## 汇总原始证据

Verifier在登记的外部证据目录写显式`selection.json`。每条记录来自冻结计划：id、唯一run目录、role、应匹配的实际构建source_id、完整expected_cases；directed还需expect_algo。不要从观察到的结果反推期望，不按目录通配符挑PASS或忽略失败。

```json
{
  "schema_version": 1,
  "runs": [
    {"id": "base", "path": "/path/to/baseline/run_id", "role": "baseline", "source_id": "BASE_COMMIT:CLEAN", "expected_cases": ["CCU_SCHED|allgather|int32|64|112"]},
    {"id": "target", "path": "/path/to/directed/run_id", "role": "directed", "source_id": "CANDIDATE_COMMIT:CLEAN", "expect_algo": "CcuSchedAllGatherSoleRing", "expected_cases": ["CCU_SCHED|allgather|int32|64|112"]},
    {"id": "default", "path": "/path/to/regression/run_id", "role": "regression", "source_id": "CANDIDATE_COMMIT:CLEAN", "expected_cases": ["CCU_SCHED|allgather|int32|64|112"]}
  ],
  "comparisons": [{"baseline": "base", "regression": "default"}]
}
```

```bash
python3 "$HCCL_WORKFLOW_DIR/scripts/summarize_ccu_evidence.py" \
  --selection "$EXTERNAL_EVIDENCE_ROOT/selection.json" --hvm-skill-dir "$HVM_SKILL_DIR" \
  > "$EXTERNAL_EVIDENCE_ROOT/evidence-summary.json"
```

只读调用实际工具的validate/parse_log/compare，核对原始日志和结果、角色、用例集合、目标算法、包/库身份和默认选路。原始日志含明确ERROR/FATAL级别时保留为问题，不能由成功汇总覆盖；不把error_count=0等普通文本误作错误。所有regression必须显式配对基线；directed/regression必须属于同一候选包。输出各run的manifest/results哈希（包括读取成功的失败run）、通过完整性核对的分轨与totals例次/用例秒数、算法调用数及每组compare结果。recorded_totals另统计选定结果文件中的全部记录与耗时，包含失败，但不证明其完整性；不能把它当作验收通过数。失败run仍列出问题且不计入validated totals；任一失败返回非零并保留问题。基线阶段可仅选baseline，不要求候选尚未存在。

同一路径重复选择拒绝。同角色跨批次重复case默认报错；冻结计划确有独立冒烟/重复实验时，在相应run明确`allow_case_overlap: true`和`overlap_basis`，按实际例次统计，不静默去重。同有效输入不同CLI键仍由输入预检提示，不能拿来扩大覆盖声明。角色报告继续列覆盖缺口和独立结论；`evidence_checks_ok`不是TEST_PASS或COMPLETE，环境恢复、构建可追溯性和完整性仍由Verifier与原门禁裁决。

报告/HANDOFF引用汇总路径、SHA-256和具体字段，不复写完整日志或JSON表。输入/输出身份、真实调用ID和时间、依赖绑定与必要证明继续保留。耗时区分用例duration之和、批次墙钟、角色窗口；差额不能自动归为模型思考。
