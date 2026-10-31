# 持续优化循环 · 判定细则

本文件是 `workflows/model-recommend-infer-workflow.md`「持续优化循环」的展开。编排契约（循环骨架、L1-L7、产物）在 `skills/model-recommend-optimization-loop/SKILL.md`，本文件只写 primary 裁决时要用的判据。

## 1. 循环准入（四个前置缺一不可）

1. 条目 0-4 就绪：环境自检通过、结构档案在案、单卡基线已采、精度门禁已建立；
2. **性能目标由用户指定**：`目标指标`（latency_avg_ms / tp99_ms / qps）+ `方向与阈值`（如 `avg ≤ 1.0ms`、`QPS ≥ 1500`）；缺失时向用户确认，禁止自行设定；
   - **用户未给数值目标时**（例如只说「帮我优化」）：必须先提问确认，不允许留 `target=null` 或人工假设一个数；
   - 若用户选择「以历史最优为回归基准」，写 `target.mode="regression_guard"`、`value` 取该历史值、并把 `confirmed_by_user` 置 `true`，同时在 `loop_state.note` 记明基准来源（哪一轮/哪份报告）；此模式下 `target_reached` 判定为「恢复到历史最优」；`mode` 只有 `target` / `regression_guard` 两值，`loop_state.py next` 会对非法值直接判准入未通过（退出码 4）；
3. 噪声带已测定（未测定则首轮先测，不许边测边判）；
4. 初始 `next_actions.json` 存在（首轮收口产物，或基线后由条目 5 + 四项专项直接生成）。

## 2. 每轮动作选择（L1）

- 取 `next_actions.json` 中**优先级最高且前置依赖满足**的单个动作；
- 需要用户确认的动作（方案取舍、低精度授权、局部劣化换主指标）在 L1 前完成确认；被拒则标 `rejected_by_user` 并重选；
- 强关联的组合动作（如「限核 + 线程数」必须一起调）在动作表里登记为一条，仍算一轮一动作；
- 不允许一轮内并行实施两个无关联动作——归因会失去唯一性。

## 3. 收益判定（L5）

- 主指标 = 目标指标的同口径复测（≥3 次重复或框架稳定段统计取稳定值）；
- 改善 ≤ 噪声带 → 本轮记为无收益，`no_gain_streak += 1`；
- 回退轮（落地后不达标被回退）**计入** `no_gain_streak`；
- 纯分析轮（未实施动作，只做采集与分析）不计入 `no_gain_streak`，但连续 2 轮纯分析没产出新候选时触发安全阀；
- 共享设备上若「无收益」伴随其他进程占用（`npu-smi` 可见），须复测一次再计数，防止把干扰判成收敛。

## 4. 终止条件（满足其一即终止，四选一写入 `termination_reason`）

| 原因码 | 判定 |
| --- | --- |
| `target_reached` | 目标指标连续 2 次同口径复测达标（防单次波动误判） |
| `converged_no_gain` | `no_gain_streak ≥ 3` |
| `no_actionable` | 动作表无可执行项且无可新增候选（含用户确认被拒） |
| `budget_exhausted` | 达到用户指定最大轮次或时间预算（默认上限 10 轮） |

## 5. 轮次之间是否重采 profiling

不强制每轮重采。按下列依据判断：

- 上一轮是否改变**算子下发时序、计算图结构、dtype 或 layout**：多流、融合、图模式、低精度通常要重采；纯开关或参数微调可沿用现有 profile；
- reviewer 是否反映现有 profile 已不足以支撑收益判断；
- 是否切到新方向或新热点模块；
- **最终方案验收前必须重采一次**，与基线做同场景同口径对照。

采集的 circle 数与压测可不同（50-100 次足够让 op_summary 稳定）；正式收益判定仍用压测口径。

## 6. 状态与文件分工

| 文件 | 作用 | 写者 | 读写规则 |
| --- | --- | --- | --- |
| `data/{model_name}/optimization_log/loop_state.json` | 轮次视图：iteration / no_gain_streak / history / 终止原因 | primary | 每轮 L5 后更新，唯一轮次真相源 |
| `data/{model_name}/optimization_log/perf_ledger.json` | 动作视图：逐动作 before/after/reverted | 执行者（经 reviewer 复核） | 逐动作追加，不回改历史行 |
| `data/{model_name}/optimization_log/workflow_status.md` | 执行矩阵：每轮 × 全部条目（0-14） | primary | 每轮收口更新 |
| `data/{model_name}/regression-baseline-mgmt/next_actions.json` | 下一轮动作队列 | primary | 每轮 L7 重排 |
| `docs/{model_name}/performance-reports/round{k}.md` | 每轮性能报告 | 执行者 + primary 汇总 | 当轮落盘 |

`loop_state` 与 `perf_ledger` 必须对账一致：同一轮的动作在两侧都能找到，收益数字相同。

- `delta_pct` / `gain_pct` 允许两种写法：数字，或对象（如 `{"latency": -6.3, "qps": 6.7}`）。对账时按 `latency → latency_avg_ms → tp99 → qps` 的顺序取主指标，两种写法不要在同一条台账里混用。
- `loop_state.json` 带 `schema_version`（当前 2）。旧版文件（`round` / `rounds_executed` / `status` 字段）先跑 `loop_state.py migrate`，脚本会备份原文件再改写；JSON 语法损坏时 `check` 会直接报可读错误（退出码 1），不会抛栈。
- `sweep_fallback`：sweep 不可用而改用手工扫描时，在 `loop_state.json` 记 `"sweep_fallback": {"reason": "...", "rounds": [...]}`（schema 已声明该字段），便于事后区分配置来源；`check` 会对缺失 `reason` 的记录告警。
- **profiling 结论必须进动作表**：第 k 轮若产生 `data/{model_name}/profiling-deep-analysis/iter{k}/findings.json`，其中每个 `id` 至少要出现在 `next_actions.json` 一次（或明确写「不采纳 + 理由」）。`loop_state.py check` 会对该覆盖关系给出 WARN，报告提交前必须清零；若 `next_actions.json` 里一条 `id` 都没有（旧工作区），只提示一次「无法校验覆盖」而不是每轮告警，补 `id` 后告警自动生效。

## 7. 中断恢复（幂等）

中断后重启：读 `loop_state.json`，从 `iteration + 1` 继续；已记录轮次不重做。若 `iteration` 与 `perf_ledger` 最后一行轮次不一致，以 ledger 为准回填 `loop_state` 并在 `note` 注明修复。

辅助脚本（可选，只做机械校验，不做判定）：

> 路径说明：脚本随安装落在**配置根**下（project 级 opencode 为 `.opencode/`、claude 为 `.claude/`、codex 为 `.codex/`；global 级为 `~/.config/opencode` 等）。下文以 `<配置根>` 表示该目录，请替换为实际路径，例如 `.opencode/workflows/scripts/loop_state.py`。

```bash
# 生成骨架（目标确认后把 confirmed_by_user 改 true）
python3 <配置根>/workflows/scripts/loop_state.py init --log-dir data/{model_name}/optimization_log \
    --metric qps --op '>=' --value 1500 --noise-band 3

# 下一轮轮次与准入告警；已终止 / 轮次预算用尽 / 连续无收益达 3 轮 → 退出码 3
python3 <配置根>/workflows/scripts/loop_state.py next  --log-dir data/{model_name}/optimization_log

# loop_state 与 perf_ledger 对账（轮次 + gain_pct + 终止标记）；不一致退出码 2
python3 <配置根>/workflows/scripts/loop_state.py check --log-dir data/{model_name}/optimization_log
```

状态脚本自测（12 例：正常态 + 对账不一致 + 终止矛盾 + 准入未过 + 预算/无收益）。**`tests/` 不随安装落位**，需在插件源目录（`plugins-community/model-recommend-infer-optimize`）下执行：

```bash
python3 tests/test_loop_state.py
```

## 8. 变更触发重分析（循环外，但会影响轮次连续性）

| 变更 | 动作 |
| --- | --- |
| 场景 / batch / TP99 上限 | 重做条目 3 并发与限核策略分析 |
| CANN / 框架版本 | 重采全量基线，`no_gain_streak` 归零并注明 |
| onnx / 配置变更 | 重跑受影响条目验收 |
| shape 策略切换 | 重跑精度门禁 + 相关性能对比（编译产物不同） |
| 换卡（同机不同 die） | 整轮重采基线口径，台账注明 |
