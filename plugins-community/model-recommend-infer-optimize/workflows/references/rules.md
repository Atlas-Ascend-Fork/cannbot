# 判定细则（门禁 + 循环）

本文件是 `workflows/model-recommend-infer-workflow.md`「改动校验双门禁」与「持续优化循环」两节的展开，供 primary 裁决、implementer 自查、reviewer 复核共用。判定标准只有这一份。

---

# A. 改动校验双门禁

## A1. 触发范围

**触发**：任何会改变模型执行结果的改动落地前——图/模型改动、配置改动、GE 编译选项、算子实现变更、运行时修复中涉及上述任一项。

**不触发**：只读分析、采集、报告撰写、sweep 探测（未改配置）等分析类动作，不触发双门禁；结论一旦转化为改动即触发。

## A2. 精度门禁

| 项 | 要求 |
| --- | --- |
| 执行形态 | 串行单并发（`THREAD_NUM=1`）verify，全量输出对比 golden |
| 判定 | 整型/bool 精确相等；浮点 `allclose`（rtol/atol 按模型精度要求裁定并记录依据） |
| 非有限值 | 实际输出必须全部 finite；出现 NaN/Inf 一律判不过（不得用 `equal_nan` 让双侧 NaN 通过）；标杆自身含 NaN/Inf 视为无效标杆 |
| 标杆 | 用户 `reference/` 优先 → onnxruntime CPU 参考 → 无标杆时报错停下（bf16 与自定义算子模型必须用户提供） |
| 精度相关选项 | 额外记录误差指标（max_abs / max_rel / 余量倍数） |
| 低精度选项 | `FORCE_16` / `ENABLE_HF32` / `precision_mode` / `op_precision_mode` / 算子级低精度路由：**默认关闭**，启用须「用户确认 + 精度门禁记录误差」双前置 |
| 并发/限核参数 | 参数本身不改数值，但仍须做一次串行 verify 证明未被牵连 |
| 失败处置 | **直接回退，不进入性能测量** |

**假阳性防护**：看 verify 结论前先确认 `[GE RESULT] inference finished: success`，并确认产物是本轮新生成（历史环境出现过陈旧产物被判 PASS 的事故）。

## A3. 性能门禁

**同口径**才可比：同卡、同 batch、同 `THREAD_NUM` / `CORE_NUM`、同 CircleCount 与统计策略，对照基线或上一已验收配置。

**双口径强制**（两组数据都要有，只测其一视为测量未完成）：

| 口径 | 场景 | 指标 |
| --- | --- | --- |
| 时延 | 串行单并发 | avg / TP99 / TP999（ms） |
| 吞吐 | 目标并发/批量配置 | QPS（或业务口径）+ TP99 |

**噪声带**：以重复测量（≥3 次同口径运行，或复用 sweep 的重复段统计）的方差确定，典型 ±2%～±5%；本轮噪声带必须写进报告。

**判定**：

- 劣化超过噪声带 → 回退；
- 改善小于噪声带 → 不得宣称提升（记为「无收益」）；
- 算子级改动除算子级加速比外**必须补整图端到端对比**；
- 允许局部指标劣化换主指标显著改善，但必须显式声明、量化两者、经用户确认后记录。

## A4. 落地流程（四步不可跳）

```text
确认同口径对照基准（无则先采）
  -> 实施（可开关 / 可回退）
  -> 精度门禁 ── 不过 -> 回退 + 记录
  -> 性能门禁 ── 不过 -> 回退 + 记录
  -> 落地 + 写 perf_ledger（reverted=false）
```

## A5. 台账纪律

- 每笔改动一条 ledger 记录，`perf_before` / `perf_after` 必须同口径，`reverted` 如实标注；
- 分析类条目各性能字段填 `null` 并在 `note` 注明是分析动作；
- **台账中不存在「未过门禁但已合入」的项**；最终配置 = 台账中已验收项的组合。

## A6. 常见误判

| 现象 | 正确处理 |
| --- | --- |
| 单次测量看起来快了 5% | 噪声带内，复测后再判；不得单次定论 |
| 算子 benchmark 加速 3 倍 | 仍需整图端到端对比，端到端无收益则不入台账 |
| 并发下 QPS 涨了但 TP99 变差 | 属取舍项，量化 + 用户确认；未确认不得宣称收益 |
| 图 pass 生效但输出 NaN | 精度门禁不过，直接回退；限核配置须补串行 verify（历史出现过 FA pass 在低核数下 NaN/挂死） |
| 换配置后首次运行变慢 | 首次含编译耗时，正式计时在 warmup 之后 |

## A7. 复核清单（reviewer 用）

1. 本轮改动是否落在触发范围内？若无改动则是分析轮，不应有 ledger 性能字段。
2. 精度：verify 是否全新产物、是否全量输出、阈值依据是否在案、低精度是否有用户确认记录。
3. 性能：时延与吞吐是否都有数据？口径与对照是否一致？噪声带是否声明？
4. 归因：本轮是否只有一个变量（一轮一动作）？组合动作是否在动作表登记为一条？
5. 回退：失败项是否真的回退（开关关闭或文件还原），回退后是否复测确认恢复。

---

# B. 持续优化循环

## B1. 循环准入（四个前置缺一不可）

1. 条目 0-4 就绪：环境自检通过、结构档案在案、单卡基线已采、精度门禁已建立；
2. **性能目标由用户指定**：`目标指标`（latency_avg_ms / tp99_ms / qps）+ `方向与阈值`；缺失时必须提问确认，禁止自行设定；
   - 用户选择「以历史最优为回归基准」时，写 `target.mode="regression_guard"`、`value` 取历史值、`confirmed_by_user=true`，并在 `loop_state.note` 记来源；`mode` 只有 `target` / `regression_guard` 两值；
3. 噪声带已测定（未测定则首轮先测，不许边测边判）；
4. 初始 `next_actions.json` 存在。

## B2. 每轮动作选择（L1）

- 取 `next_actions.json` 中**优先级最高且前置依赖满足**的单个动作；
- 需用户确认的动作在 L1 前完成确认；被拒则标 `rejected_by_user` 并重选；
- 强关联的组合动作（如「限核 + 线程数」一起调）登记为一条，仍算一轮一动作；
- 不允许一轮内并行实施两个无关联动作。

## B3. 收益判定（L5）

- 主指标 = 目标指标的同口径复测（≥3 次重复或稳定段统计取稳定值）；
- 改善 ≤ 噪声带 → 本轮无收益，`no_gain_streak += 1`；
- 回退轮（落地后不达标被回退）**计入** `no_gain_streak`；
- 纯分析轮不计入，但连续 2 轮纯分析无新候选触发安全阀；
- 共享设备上「无收益」伴随他进程占用时，须复测一次再计数。

## B4. 终止条件（四选一）

| 原因码 | 判定 |
| --- | --- |
| `target_reached` | 目标指标连续 2 次同口径复测达标 |
| `converged_no_gain` | `no_gain_streak ≥ 3` |
| `no_actionable` | 动作表无可执行项且无可新增候选（含用户拒绝） |
| `budget_exhausted` | 达到用户指定最大轮次或时间预算（默认 10 轮） |

## B5. 轮次之间是否重采 profiling

不强制每轮重采，按依据判断：上一轮是否改变算子下发时序/图结构/dtype/layout（多流、融合、图模式、低精度通常要重采）；reviewer 是否反映现有 profile 不足；是否切到新方向/新热点；**最终方案验收前必须重采一次**与基线同口径对照。采集 circle 可与压测不同（50-100 次足够 op_summary 稳定），正式收益判定仍用压测口径。

## B6. 状态与文件分工

| 文件 | 作用 | 写者 |
| --- | --- | --- |
| `loop_state.json` | 轮次视图（iteration/no_gain_streak/history/终止原因） | primary（唯一轮次真相源） |
| `perf_ledger.json` | 动作视图（逐动作 before/after/reverted） | 执行者（reviewer 复核） |
| `workflow_status.md` | 执行矩阵（每轮 × 全部条目） | primary |
| `next_actions.json` | 下一轮动作队列 | primary（每轮 L7 重排） |
| `round{k}.md` | 每轮性能报告 | 执行者 + primary 汇总 |

`loop_state` 与 `perf_ledger` 必须对账一致；`delta_pct`/`gain_pct` 允许数字或对象，按 `latency → latency_avg_ms → tp99 → qps` 取主指标，不混用；`loop_state.json` 带 `schema_version`（当前 2），旧版先 `loop_state.py migrate`；sweep 不可用时记 `sweep_fallback`；profiling 结论必须进动作表（`loop_state.py check` 有 WARN）。

## B7. 中断恢复（幂等）

中断后重启：读 `loop_state.json`，从 `iteration + 1` 继续，已记录轮次不重做。若 `iteration` 与 `perf_ledger` 最后一行轮次不一致，以 ledger 为准回填并在 `note` 注明。

辅助脚本（只做机械校验，不做判定；路径以 `<配置根>` 表示）：

```bash
python3 <配置根>/workflows/scripts/loop_state.py init --log-dir data/{model_name}/optimization_log --metric qps --op '>=' --value 1500 --noise-band 3
python3 <配置根>/workflows/scripts/loop_state.py next  --log-dir data/{model_name}/optimization_log
python3 <配置根>/workflows/scripts/loop_state.py check --log-dir data/{model_name}/optimization_log
```

状态脚本自测（源仓内执行）：`python3 tests/test_loop_state.py`。

## B8. 变更触发重分析（循环外）

| 变更 | 动作 |
| --- | --- |
| 场景 / batch / TP99 上限 | 重做条目 3 |
| CANN / 框架版本 | 重采全量基线，`no_gain_streak` 归零并注明 |
| onnx / 配置变更 | 重跑受影响条目验收 |
| shape 策略切换 | 重跑精度门禁 + 相关性能对比 |
| 换卡（同机不同 die） | 整轮重采基线口径，台账注明 |
