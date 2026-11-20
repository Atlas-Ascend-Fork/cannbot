# 状态与报告

`workflow-state.json` 使用事件化 schema：

- `stages.<name>`：`status`、`started_at`、`completed_at`、`elapsed_seconds`、artifacts、context；性能保存点另有 `performance`，只记录保留实现、统计范围及两份 effect 摘要的路径，不复制逐 case 数据；
- `events[]`：阶段变化、进度、诊断、人工决策和迁移审计；
- `precision`：原始基线失败、候选新增/恶化失败、当前假设、已排除假设、下一步；
- `operator`：是否等待人工、问题和安全恢复点。

`$WORKFLOW_SCRIPTS/workflow_state.py` 的每次写入都加锁、原子替换状态并重绘同目录 `性能调优报告.md`。长任务至少在开始、每个可验证假设完成、候选状态变化和阶段结束时调用 `progress`；不要用固定频率刷无意义心跳。主 Agent 派发每个阶段时必须先 `mark --status in_progress`，产物就绪后再标 `complete`；未标 `in_progress` 的阶段无法记录 `started_at`/`elapsed_seconds`，报告中如实显示 `-`，禁止事后伪造 0 耗时。

保存点的 artifact 必须已存在；状态记录其 SHA。恢复前 `verify` 复核 manifest 和 completed artifact，失效的保存点转为 `invalid`。只有真实完成的产物可以标 `complete`。

### 保存点与报告刷新

主 Agent 使用 `workflow_state.py mark` 命令串行登记阶段状态、证据与性能摘要，形成保存点；状态提交时同步重绘报告，不另设刷新命令或报告状态。

- 派发前 `mark --status in_progress --next-action <本阶段动作>`：刷新当前阶段与下一动作，继续展示最近已验收结论和性能，注明性能所属保存点。
- 验收后 `mark --status complete --message <验收结论> --next-action <后续动作>`：刷新结论和恢复点；轮次完成同时登记下述性能摘要。未指定下一动作时显示阶段对应提示，不沿用上一阶段动作。
- `progress` 记录执行进展，不替代验收结论或性能保存点。下一轮派发前先完成上一轮终选登记；未验收候选不得写入当前性能结果。

当前性能按完成时间选取，同一时间戳按完成事件顺序确定；重新加载、派发和重绘不改变选择。失效保存点明确标记待复核，不退回历史结果冒充当前验收。

读取当前上下文使用 `$WORKFLOW_SCRIPTS/workflow_state.py inspect --state <path> --stage <key> [--stage <前置阶段键>] [--recent 3]`。它只读并校验 manifest SHA，输出配置、集合路径/SHA/数量、阶段状态和选定阶段最近事件，不展开全量选择记录与历史；详细 case、诊断和证据仍按路径读取。该视图不替代 `verify` 或阶段门禁。写操作已重绘报告，无需紧接着再 `render` 或整份读回状态。

### 五阶段保存点

新 manifest 记录 `configuration.workflow_layout=four-stage-v1`。沿用原来的细粒度阶段键，并在四个阶段出口登记 `phase.baseline`、`phase.analysis`、`phase.implementation`、`phase.integration`；基线评估两次派发共用 `phase.baseline`（派发间主 Agent 机械调用 harness 建 worktree 后登记事件，不另立阶段键）。使用现有 `mark --status in_progress|complete --artifact ...`：主 Agent 派发前登记开始，代理返回后复核并登记完成，不让多个代理并发改 manifest。轮内 analysis/implementation 循环继续使用原 round/gen 键；`phase.analysis` 记录初次诊断交接，阶段恢复期间通过细粒度键追踪当前分析，不删除历史完成记录。最终 `phase.implementation` 在全集验收完成后登记。

- baseline artifacts：`preflight-report.json`、`环境检查报告.md`、`performance-targets.json`、`性能目标.md`。脚本重算目标并冻结全部来源 SHA，报告 warn 可保留但 fail 不得通过。
- baseline artifacts（派发 2）：`workspace-manifest.json`、`source-compatibility.md`、`functional-acceptance.md` 及 worktree/基线 commit 身份与构建/TTK 原始证据，与派发 1 的定稿产物、环境/集合/目标产物同在 `phase.baseline` 登记。
- analysis artifacts：`analysis.md`、实施契约和每方案冻结 scope；无需优化时也记录逐 case 达标/无方案证据。
- implementation artifacts：`final-functional-regression.md`、`final-performance-comparison.md`、归档、全部候选及逐轮 gate/selection/effect 证据。
- integration artifacts：`VERIFY_REPORT.md`、每 SoC `postprocess-performance-<soc>.json`、源码/构建/路由/精度门禁。状态脚本重算两类全集的性能 gate，拒绝缺失目标 SoC、回退和过期 CSV。
- manifest 启用 experience_policy 时，integration 还必须显式登记 `experience-lessons.json`、`experience-material.md`、`experience-review.json` 和 `knowledge-reflux.json`；程序重算来源SHA、候选实测数值、完成轮次覆盖、正文一致性、独立阅读评分及实际回流卡完整正文，并登记来源闭包。`verify`/`finish` 重核，不接受只有自报pass的质量文件，也不接受缩水的导出卡。历史 manifest 缺字段时维持原完成语义。

五阶段必须按顺序首次交接；缺少前置阶段或必要产物会拒绝完成。`finish --status success` 还校验五阶段均完成且 artifacts SHA 未变。旧 manifest 没有 layout 时继续保留旧键可恢复性，迁移审计须补齐新门禁后才按新版完成定义交付。

### 单方案诊断与搜索交接

每轮 `roundN.analysis` 冻结一个实施契约；`roundN.impl.<scheme_id>` 只验收该方案。契约内的诊断与修复用 `progress --kind diagnosis` 和有实际产物的保存点记录，候选拟晋升时完成正式验收和选择；探索后暂不采用可记 screened 并保留基线。两者均登记本轮/累计摘要及 `roundN.complete`。改变方向、依赖或源码修改范围时，保留本轮证据和可信实现，下一轮重新冻结。正式计划注册后不能将慢样本改称探索后择优重采。

启用搜索策略（`search_policy`）后，主 Agent 通过 `workflow_state.py mark` 登记分析完成或轮次完成保存点时，脚本从实施契约、可选的 `candidate-frontier-<scheme_id>.json` 和 `selection.json` 追加 `search_plan/search_frontier/search_result` 事件。`inspect.search` 与报告从这些事件推导参考、连续有效评估次数、候选前沿与下一动作；同一轮重复登记不重复计数。frontier 和辅助证据使用该保存点已有的 `--artifact` 参数登记。

零方案分析也用 `mark --stage roundN.analysis --status complete --artifact <candidate-frontier-audit.json> --artifact <分析报告>` 登记空间；前沿携带非空空间引用、父身份、冻结负载 `workload` 和 `nodes: []`，格式见 analysis 的搜索交接说明。此时只登记原 `search_frontier` 事件与输入依赖，不生成 `search_plan` 或增加实测次数；`no_candidate` 及最终阶段验收规则不变。

搜索证据与源码身份纳入状态校验命令 `verify`，不另设状态文件。字段和架构重规划命令 `search-replan` 见 [搜索决策](../../../ops-perf-acceptance-criteria/references/architecture-search.md)。`phase.analysis` 记录首次交接，轮内契约归属始终使用规范 `roundN.analysis`。

analysis 交接 `search-frontier` 的 `axis_coverage` 后，主 Agent 将复核后的未测方向以现有 `structural-direction --id <untested_directions中的ID> --status not_attempted --description <机制与待测轴值> --evidence <覆盖报告路径>` 登记；受 scope 阻塞则用 `blocked_by_scope`。有依据排除时用同一 ID、`--status infeasible_evidenced|blocked_by_precision --evidence <排除证据文件>` 更新，命令将原文件 SHA 固定在该台账项中。分析报告和原始依赖仍用阶段 `mark --artifact` 登记。

上述排除证据同时纳入原 `verify`；文件丢失或变更时报告 `search_exclusion`，搜索视图提示修复证据。恢复原文件，或复核后用原台账命令重新登记；未决状态不作为有效排除。

启用搜索时，`finish --reason-code no_material_improvement|ceiling_bound` 自动重算所有已登记空间的轴覆盖，未测项须逐项匹配上述排除记录并通过证据 SHA 校验，否则退出码为 2 且不写终态；漏登记方向、缺空间引用、证据丢失/变更均不能放行。单个方向声明 no-go 前，用只读 `search-frontier --no-go` 执行同一检查。工具核验覆盖、适用范围与文件身份，排除论证是否充分仍由 analysis 复核；通过不证明组合或空间外路线耗尽。普通 `completed` 和 `awaiting_operator/structural_headroom_unrealized` 继续遵循原退出规则，预算停止须保留未决说明，不冒充 no-go，也不自动增加轮次。`pursue_optimal` 的既有未决方向门禁保持生效。

`progress --evidence` 只记录路径；需要恢复时校验 SHA 的诊断原件，应通过 `mark --artifact` 或已有门禁消费的依赖链登记。不要修改旧路径内容或依靠一份自报索引替代实际依赖核验。

### 每轮结束刷新性能

完成唯一终选后、进入下一轮或结束任务前，主 Agent 必须登记所保留实现的两种比较：

- **本轮**：轮初基线 vs 本轮保留实现，复用该实现的 `effect-summary.json`。
- **累计**：原始冻结基线 vs 同一保留实现，用 `$WORKFLOW_SCRIPTS/summarize_performance_effects.py --manifest "$RUN_MANIFEST"` 从已有 CSV 生成 `cumulative-effect-details.csv` 与 `cumulative-effect-summary.json`，存于该轮保留实现的性能证据目录。两种比较相同或保留实现未变时复用已有摘要。

两份摘要必须引用同一份所选实现的性能 CSV，case 集合与顺序一致。累计基线必须是原始实现，不能误用上一轮基线或连乘各轮加速比。保留 baseline 时，本轮用轮初基线与自身生成摘要（median 为1；legacy 无有效变化时为 `N/A`），累计仍展示此前已取得的收益；不得登记被淘汰候选的性能。

```bash
python3 "$WORKFLOW_SCRIPTS/workflow_state.py" mark \
  --state "$OUTPUT_DIR/workflow-state.json" \
  --stage "round${ROUND}.complete" --status complete \
  --message "$ROUND_CONCLUSION" --next-action "$NEXT_ACTION" \
  --artifact "$ROUND_DIR/selection.json" \
  --selected-candidate "$SELECTED_IMPLEMENTATION" \
  --performance-summary "$SELECTED_EFFECT_SUMMARY" \
  --cumulative-performance-summary "$CUMULATIVE_EFFECT_SUMMARY" \
  --performance-scope tuning_subset
```

`SELECTED_IMPLEMENTATION` 应可从 `selection.json` 追溯到实际保留代码/二进制身份；其 attempt 字段（attempt_id、branch、commit、revert_of，AscendC）是 commit 与终选结果的唯一关联记录，随本保存点一并登记，机器校验属可优化项。`roundN.complete`、`gen.roundN.complete`、`gen.outerM.exit` 和 `final.performance` 缺少两份摘要或保留实现时，脚本拒绝标记完成。脚本按摘要schema及manifest冻结的效果版本复算，校验摘要与源CSV及proof一致，自动登记摘要、源CSV、plan/registration/原样本/完整mapping/输入/源码/构建/加载/精度/频率的全部依赖SHA，并立即重绘同一份报告；不需要再手动调用 `render`。

报告展示全部实测 case 的原始/轮初/当前耗时、本轮与累计差值、变化百分比、加速比及分类；总体按冻结policy展示总case、legacy抖动数、新版待确认数、有效数、有效提升/回退数及有效case几何加速比，不展示也不比较各 case 耗时之和。median 全部 case 参与几何平均；legacy 抖动和 confidence 待确认 case 仍按旧策略展示。

每次刷新替换“当前性能结果”，保留各轮汇总与证据路径。调优子集只代表本轮实测范围，不拼接不同轮次/不同实现的 case 冒充全集性能。泛化模式累计比较也只覆盖本轮同一子集，必要时从原始全集基线按本轮 ID 和顺序提取已有数据，不重新采集。泛化外层 `gen.outerM.exit` 及 standard 最终性能保存点 `final.performance` 使用同一组参数、`--performance-scope full`，刷新为实测全集结果；外层的本轮比较使用上次全集基线，首次可用原始全集基线。

后续进度、恢复和终态重绘继续保留最近性能结果；摘要或源 CSV 丢失、SHA 变化、保存点失效时明确显示结果不可用，不把旧数据展示为当前可信性能。仅缺报告字段时从已有证据补齐即可。

## 泛化状态、恢复与报告

竞品 SHA 未变时可用已有 NPU 性能重新计算 ratio；NPU 身份、全集 SHA 或竞品 SHA 变化会失效对应 ratio 及其下游选择。恢复时从最后一个有效 `gen.roundN.complete` 或 `gen.outerM.exit` 继续，内外层计数不得因重启清零。`optimized-involved-cases.csv` 可从已完成轮次的选择 artifact 重建，不依赖进程内存。

持续报告除上述通用字段外，还必须显示模式、竞品来源与 SHA、目标用例数、ratio 门限、逐 case ratio artifact、当前内/外层次数、涉及优化用例数和最终达标状态。每个 `gen.roundN.complete` 和 `gen.outerM.exit` 都按“每轮结束刷新性能”刷新当前逐 case 性能及本轮/累计总体指标，分别注明调优子集与全集范围；ratio 结论仍按 `ops-perf-acceptance-criteria` 的 `references/ratio.md`保留独立证据。

## 测量修复与判断

未终选轮次发生采集或证据问题时，在原契约、scope 和采集协议内修复；需要重测时，事前明确有限的补测次数与采样计划。保留全部已有样本与原始记录，达到次数上限后仍测不准时，结合已有数据、离散度及实现/诊断证据完成本轮判断与选择，保留全部实测结果并说明不确定性，不继续追加重测。

不确定性说明仅作分析参考，不作为废除本轮结果、撤销本轮结论或延长重测的依据。正式收益与最终验收结论仍遵循冻结性能策略。

已关闭的失败轮次保留结论，诊断和补证由下一轮 analysis 消费，同机制重试附带新的证据。
