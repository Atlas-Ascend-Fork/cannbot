# 性能回退抖动与有效 Case 统计规则

本文件是 `ops-perf-optimize-workflow` 的性能差异过滤与汇总真源。每轮候选选择、最终性能比较和多轮汇总都必须使用同一规则；不得按轮次或候选调整阈值。

## 1. 判定口径

以当前比较的基线耗时 `baseline_total_us` 决定阈值：

| 基线耗时 | 回退抖动范围（含边界） |
|---|---|
| `baseline_total_us <= 5us` | `abs(candidate_total_us - baseline_total_us) <= 0.25us` |
| `5us < baseline_total_us <= 20us` | `abs(candidate_total_us - baseline_total_us) <= 0.5us` |
| `20us < baseline_total_us <= 100us` | `abs(candidate_total_us - baseline_total_us) / baseline_total_us <= 3%` |
| `baseline_total_us > 100us` | `abs(candidate_total_us - baseline_total_us) <= max(3us, baseline_total_us * 1%)` |

恰好 `5us`、`20us`、`100us` 分别归入其左侧档位，所有边界都包含在回退抖动范围内。阈值只用于候选变慢的判定：所有 `candidate_total_us < baseline_total_us` 的提升均不按抖动过滤，直接计为 `effective_improvement`；候选持平或变慢但未超过阈值的 case 分类为 `jitter_no_effect`，不参与有效 case 数、有效提升/回退数和有效 case 几何加速比。

该默认阈值按同源码、同二进制重复采集的跨次中位数波动上界取整：微秒级使用绝对门槛，避免相对比例被固定启动开销放大；中长耗时使用相对门槛，`>100us` 额外保留 `3us` 绝对底噪。若后续稳定环境积累了更充分的同身份重复采集，可基于其 P95 重新校准整套全局规则，但不得只为单轮或单候选临时改阈值。

按方向和回退抖动范围分类：

- `candidate_total_us < baseline_total_us`：始终为 `effective_improvement`，提升幅度不设最小门槛；
- `candidate_total_us == baseline_total_us`，或候选变慢但未超过回退抖动范围：`jitter_no_effect`；
- 候选变慢且超过回退抖动范围：`effective_regression`。

抖动过滤只改变性能差异的统计与选择口径，不豁免采集有效性门禁。`ops-profiling` 判定采集不稳定、身份不完整或 launch 映射失败时，先按其规则处理，不能用本文件的阈值挽救无效采集。

## 2. 有效 case 指标

对每个 case 计算：

```text
delta_us = candidate_total_us - baseline_total_us
delta_percent = delta_us / baseline_total_us * 100
speedup = baseline_total_us / candidate_total_us
```

只在 `effective_improvement` 与 `effective_regression` 的并集上计算：

```text
effective_geomean_speedup = exp(mean(log(speedup_i)))
```

有效 case 数为 0 时，`effective_geomean_speedup` 必须写 `null` / `N/A`，不能伪造为 `1.0`。轮次报告、候选选择和最终汇总禁止再计算或展示完整 case 集合的几何加速比。

报告至少包含：总 case 数、抖动 case 数、有效 case 数、有效提升数、有效回退数、有效 case 几何加速比，以及所有有效 case 的基线/候选耗时、绝对差、相对差、加速比和分类。抖动 case 不进入有效明细，但必须保留数量并在机器可读结果中逐条记录，禁止静默删除。持续报告的“逐 case 当前性能”表同时展示有效与抖动 case，并明确分类；它不改变有效指标的统计集合。报告不得展示或比较各 case 耗时之和。

机器可读逐 case 结果中的 `threshold_value` 与 `threshold_unit` 固定表示用于回退判定的绝对抖动上限（微秒）；`threshold_percent` 同时记录该上限相对当前基线的百分比，便于复核不同档位。提升 case 保留这些阈值字段仅用于统一证据格式，不参与其分类。

## 3. 确定性工具

统一调用插件根脚本：

```bash
python3 <plugin-root>/scripts/summarize_performance_effects.py \
  --baseline <baseline-performance.csv> \
  --candidate <candidate-performance.csv> \
  --out-csv <effect-details.csv> \
  --out-json <effect-summary.json>
```

选择和报告必须直接读取这两个产物，不得手工重算、改变边界包含关系或从抖动 case 中挑选有利结果。

## 4. 多轮与最终口径

- 每轮：相对该轮当前基线为每个候选生成独立的 effect 产物；只用有效指标选择轮次最佳。
- 每轮结束：复用所保留实现的本轮 effect 产物，并用原始基线与该实现生成累计 effect 产物，立即刷新持续报告的逐 case 与总体结果；两种比较使用相同 case 集合。保留 baseline 也必须更新。登记命令与恢复规则见 `$PLUGIN_ROOT/workflows/references/state-reporting.md`。
- 最终端到端：用原始冻结基线与最终实现生成一份 effect 产物，作为多轮汇总的最终性能结论。
- 用户另有更严格的有效 case 目标时优先执行；用户只给普通性能目标时，本文件是默认且唯一的抖动过滤规则。
