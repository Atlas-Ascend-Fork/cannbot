# 性能效果判定规则（版本化真源）

本文件维护收益判定的唯一规则；summary、候选选择、状态复核及集成全集 gate 使用 manifest 冻结的同一版本。采集有效性、收益方向与是否值得保留分别判定。不存在默认 3% 或 1us 的最小有效收益；用户接受约 0.7us 不产生 1us 下限。精度、身份、频率、完整映射、10% spread 和泛化 ratio 门禁均独立保留。

## 策略选择与历史兼容

新请求默认策略：AscendC 走 `legacy_jitter_v1`，DSL 走 `confidence_effect_v1`；版本均为 1，显式 `--performance-effect-policy` 优先。旧 request/manifest 没有该字段时保持 legacy，不在读取、恢复或安装更新时补写新版。API `summarize(base,candidate)` 仍为 legacy；CLI 必须提供 `--manifest` 或显式 `--policy`，两者冲突拒绝。未知策略/版本/schema 拒绝。

- schema2 effect summary 使用 `legacy_jitter_v1` 原算法复核，历史报告、SHA 和判断不变。
- schema3 使用 `confidence_effect_v1`，记录 `policy_id/policy_version/classification_basis`、配对统计、proof 路径和完整依赖 SHA。新确认结论另存，不改旧摘要。
- postprocess legacy gate schema1 继续识别；confidence gate schema2 记录相同策略、proof 与 no-op 引用，并按该版本机械复算。

## confidence_effect_v1

仅冻结策略为 `confidence_effect_v1` 时读取 [确认与 proof 细则](performance-confidence-policy.md)。

## legacy_jitter_v1（历史原规则，不重新解释）

| 基线耗时 | 回退抖动范围（含边界） |
|---|---|
| <=5us | abs(delta_us) <=0.25us |
| >5至20us | abs(delta_us) <=0.5us |
| >20至100us | abs(delta_us)/baseline <=3% |
| >100us | abs(delta_us) <=max(3us,baseline*1%) |

恰好 `5us`、`20us`、`100us` 分别归入其左侧档位，所有边界都包含在回退抖动范围内。阈值只用于候选变慢的判定：所有 `candidate_total_us < baseline_total_us` 的提升均不按抖动过滤，直接计为 `effective_improvement`；候选持平或变慢但未超过阈值的 case 分类为 `jitter_no_effect`，不参与有效 case 数、有效提升/回退数和有效 case 几何加速比。

## 指标与多轮

按方向和回退抖动范围分类：

- 提升与回退对称判定：`|delta_us|` 在回退抖动范围内（含边界）为 `jitter_no_effect`；超出范围的提升为 `effective_improvement`、回退为 `effective_regression`；
- 初筛带只作用于无 proof 的筛选分类；已证实（配对/独立 proof）的小收益不否决（`effective_improvement`），即确认结论不引入最小收益门槛；
- 历史已存储的 summary/gate 保持其记录口径，不在恢复时按新规则重解释。

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

统一调用工作流共享脚本：

```bash
python3 "$WORKFLOW_SCRIPTS/summarize_performance_effects.py" \
  --baseline <baseline-performance.csv> \
  --candidate <candidate-performance.csv> \
  --out-csv <effect-details.csv> \
  --out-json <effect-summary.json>
```

选择和报告必须直接读取这两个产物，不得手工重算、改变边界包含关系或从抖动 case 中挑选有利结果。

## 4. 多轮与最终口径

- 每轮：相对该轮当前基线为每个候选生成独立的 effect 产物；只用有效指标选择轮次最佳。
- 每轮结束：复用所保留实现的本轮 effect 产物，并用原始基线与该实现生成累计 effect 产物，立即刷新持续报告的逐 case 与总体结果；两种比较使用相同 case 集合。保留 baseline 也必须更新。登记命令与恢复规则见 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。
- 最终端到端：用原始冻结基线与最终实现生成一份 effect 产物，作为多轮汇总的最终性能结论。
- 用户另有更严格的有效 case 目标时优先执行；用户只给普通性能目标时，本文件是默认且唯一的抖动过滤规则。
