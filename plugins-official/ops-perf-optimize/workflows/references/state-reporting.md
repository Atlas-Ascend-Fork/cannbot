# 状态与报告

`workflow-state.json` 使用事件化 schema：

- `stages.<name>`：`status`、`started_at`、`completed_at`、`elapsed_seconds`、artifacts、context；性能保存点另有 `performance`，只记录保留实现、统计范围及两份 effect 摘要的路径，不复制逐 case 数据；
- `events[]`：阶段变化、进度、诊断、人工决策和迁移审计；
- `precision`：原始基线失败、候选新增/恶化失败、当前假设、已排除假设、下一步；
- `operator`：是否等待人工、问题和安全恢复点。

`workflow_state.py` 的每次写入都加锁、原子替换状态并重绘同目录 `性能调优报告.md`。长任务至少在开始、每个可验证假设完成、候选状态变化和阶段结束时调用 `progress`；不要用固定频率刷无意义心跳。主 Agent 派发每个阶段时必须先 `mark --status in_progress`，产物就绪后再标 `complete`；未标 `in_progress` 的阶段无法记录 `started_at`/`elapsed_seconds`，报告中如实显示 `-`，禁止事后伪造 0 耗时。

报告固定包含：输入与集合身份、当前阶段、最近进展、精度异常与已知基线失败、当前/排除假设、下一动作、候选门禁与性能、逐轮选择、当前逐 case 性能与本轮/累计总体指标、各轮性能汇总、最终验收、是否等待人工、安全恢复点。它从 Stage 0 存在到终态；不另建进度 JSON、双份多轮汇总或逐轮同名报告。

保存点的 artifact 必须已存在；状态记录其 SHA。恢复前 `verify` 复核 manifest 和 completed artifact，失效的保存点转为 `invalid`。只有真实完成的产物可以标 `complete`。

### 保存点与报告刷新

沿用 `mark` 保存点，由主 Agent 串行登记；状态提交时同步重绘报告，不另设刷新命令或报告状态。

- 派发前 `mark --status in_progress --next-action <本阶段动作>`：刷新当前阶段与下一动作，继续展示最近已验收结论和性能，注明性能所属保存点。
- 验收后 `mark --status complete --message <验收结论> --next-action <后续动作>`：刷新结论和恢复点；轮次完成同时登记下述性能摘要。未指定下一动作时显示阶段对应提示，不沿用上一阶段动作。
- `progress` 记录执行进展，不替代验收结论或性能保存点。下一轮派发前先完成上一轮终选登记；未验收候选不得写入当前性能结果。

当前性能按完成时间选取，同一时间戳按完成事件顺序确定；重新加载、派发和重绘不改变选择。失效保存点明确标记待复核，不退回历史结果冒充当前验收。

读取当前上下文使用 `workflow_state.py inspect --state <path> --stage <key> [--stage <前置阶段键>] [--recent 3]`。它只读并校验 manifest SHA，输出配置、集合路径/SHA/数量、阶段状态和选定阶段最近事件，不展开全量选择记录与历史；详细 case、诊断和证据仍按路径读取。该视图不替代 `verify` 或阶段门禁。写操作已重绘报告，无需紧接着再 `render` 或整份读回状态。

### 五阶段保存点

新 manifest 记录 `configuration.workflow_layout=five-stage-v1`。沿用原来的细粒度阶段键，并在五个阶段出口登记 `phase.baseline`、`phase.preparation`、`phase.analysis`、`phase.implementation`、`phase.integration`。使用现有 `mark --status in_progress|complete --artifact ...`：主 Agent 派发前登记开始，代理返回后复核并登记完成，不让多个代理并发改 manifest。轮内 analysis/implementation 循环继续使用原 round/gen 键；`phase.analysis` 记录初次诊断交接，阶段恢复期间通过细粒度键追踪当前分析，不删除历史完成记录。最终 `phase.implementation` 在 demo 全集验收完成后登记。

- baseline artifacts：`preflight-report.json`、`环境检查报告.md`、`performance-targets.json`、`性能目标.md`。脚本重算目标并冻结全部来源 SHA，报告 warn 可保留但 fail 不得通过。
- preparation artifacts：`extraction-manifest.json`、`source-compatibility.md`、`functional-acceptance.md` 及构建/TTK 原始证据。
- analysis artifacts：`analysis.md`、实施契约和每方案冻结 scope；无需优化时也记录逐 case 达标/无方案证据。
- implementation artifacts：`final-functional-regression.md`、`final-performance-comparison.md`、归档、全部候选及逐轮 gate/selection/effect 证据。
- integration artifacts：`VERIFY_REPORT.md`、每 SoC `postprocess-performance-<soc>.json`、源码/构建/路由/精度门禁。状态脚本重算两类全集的性能 gate，拒绝缺失目标 SoC、回退和过期 CSV。

五阶段必须按顺序首次交接；缺少前置阶段或必要产物会拒绝完成。`finish --status success` 还校验五阶段均完成且 artifacts SHA 未变。数值门禁只证明集合与性能，不代替真实硬件/二进制/路由审阅；主 Agent 必须复核这些证据。旧 manifest 没有 layout 时继续保留旧键可恢复性，迁移审计须补齐新门禁后才按新版完成定义交付。

### 每轮结束刷新性能

完成唯一终选后、进入下一轮或结束任务前，主 Agent 必须登记所保留实现的两种比较：

- **本轮**：轮初基线 vs 本轮保留实现，复用该实现的 `effect-summary.json`。
- **累计**：原始冻结基线 vs 同一保留实现，用 `summarize_performance_effects.py` 从已有 CSV 生成 `cumulative-effect-details.csv` 与 `cumulative-effect-summary.json`，存于该轮保留实现的性能证据目录。第一轮两种基线相同时可复用同一摘要。

两份摘要必须引用同一份所选实现的性能 CSV，case 集合与顺序一致。累计基线必须是原始实现，不能误用上一轮基线或连乘各轮加速比。保留 baseline 时，本轮用轮初基线与自身生成摘要（有效几何加速比为 `N/A`），累计仍展示此前已取得的收益；不得登记被淘汰候选的性能。

```bash
python3 "$PLUGIN_ROOT/scripts/workflow_state.py" mark \
  --state "$OUTPUT_DIR/workflow-state.json" \
  --stage "round${ROUND}.complete" --status complete \
  --message "$ROUND_CONCLUSION" --next-action "$NEXT_ACTION" \
  --artifact "$ROUND_DIR/selection.json" \
  --selected-candidate "$SELECTED_IMPLEMENTATION" \
  --performance-summary "$SELECTED_EFFECT_SUMMARY" \
  --cumulative-performance-summary "$CUMULATIVE_EFFECT_SUMMARY" \
  --performance-scope tuning_subset
```

`SELECTED_IMPLEMENTATION` 应可从 `selection.json` 追溯到实际保留代码/二进制身份。`roundN.complete`、`gen.roundN.complete`、`gen.outerM.exit` 和 `final.performance` 缺少两份摘要或保留实现时，脚本拒绝标记完成。脚本校验摘要与源 CSV、抖动策略一致，自动登记摘要和源 CSV 的 SHA，并立即重绘同一份报告；不需要再手动调用 `render`。

报告展示全部实测 case 的原始/轮初/当前耗时、本轮与累计差值、变化百分比、加速比及分类；总体展示总 case 数、抖动数、有效数、有效提升/回退数及有效 case 几何加速比，不展示也不比较各 case 耗时之和。抖动 case 保留在逐 case 表，但不计入有效指标。

每次刷新替换“当前性能结果”，保留各轮汇总与证据路径。调优子集只代表本轮实测范围，不拼接不同轮次/不同实现的 case 冒充全集性能。泛化模式累计比较也只覆盖本轮同一子集，必要时从原始全集基线按本轮 ID 和顺序提取已有数据，不重新采集。泛化外层 `gen.outerM.exit` 及 standard 最终性能保存点 `final.performance` 使用同一组参数、`--performance-scope full`，刷新为实测全集结果；外层的本轮比较使用上次全集基线，首次可用原始全集基线。

后续进度、恢复和终态重绘继续保留最近性能结果；摘要或源 CSV 丢失、SHA 变化、保存点失效时明确显示结果不可用，不把旧数据展示为当前可信性能。仅缺报告字段时从已有证据补齐即可。

## 泛化状态、恢复与报告

推荐阶段键：

- `gen.prepare.cases`、`gen.prepare.competitor`、`gen.prepare.acceptance`；
- `gen.baseline.extract`、`gen.baseline.profile`、`gen.baseline.ratio`、`gen.baseline.acceptance`；
- `gen.roundN.tuning.select`、`gen.roundN.profile.baseline`、`gen.roundN.analysis`、`gen.roundN.impl.<scheme>`、`gen.roundN.acceptance.<scheme>`、`gen.roundN.profile.<scheme>`、`gen.roundN.selection`、`gen.roundN.complete`；
- `gen.outerM.full.profile`、`gen.outerM.full.ratio`、`gen.outerM.exit`；
- `gen.final.functional`、`gen.final.archive`、`gen.integrate.involved`、`gen.integrate.uninvolved`。

竞品 SHA 未变时可用已有 NPU 性能重新计算 ratio；NPU 身份、全集 SHA 或竞品 SHA 变化会失效对应 ratio 及其下游选择。恢复时从最后一个有效 `gen.roundN.complete` 或 `gen.outerM.exit` 继续，内外层计数不得因重启清零。`optimized-involved-cases.csv` 可从已完成轮次的选择 artifact 重建，不依赖进程内存。

持续报告除上述通用字段外，还必须显示模式、竞品来源与 SHA、目标用例数、ratio 门限、逐 case ratio artifact、当前内/外层次数、涉及优化用例数和最终达标状态。每个 `gen.roundN.complete` 和 `gen.outerM.exit` 都按“每轮结束刷新性能”刷新当前逐 case 性能及本轮/累计总体指标，分别注明调优子集与全集范围；ratio 结论仍按 `ops-perf-acceptance-criteria` 的 `references/ratio.md`保留独立证据。
