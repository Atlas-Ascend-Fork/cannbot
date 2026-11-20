# 性能效果判定

新请求默认 `median_v1`（两个后端一致）；用户显式选择优先。旧 request/manifest 缺字段仍为 `legacy_jitter_v1`，已冻结策略、历史摘要与 SHA 不改写。CLI 使用 `--manifest` 或显式 `--policy`，冲突和未知版本拒绝。`summarize(base, candidate)` 的历史 API 默认值不变。

## median_v1（默认）

采集按 [采集协议](performance-collection.md) 执行。直接比较每例固定样本的中位数，保留原始样本与离散度。

每个 case 计算 `speedup = baseline_median / candidate_median`，全部 case（包括持平、小收益和小回退）等权参与 `exp(mean(log(speedup)))`。`effective_geomean_speedup` 为兼容字段名，在本策略中表示完整比较集合的几何加速比；`effective_case_count` 等于总 case 数，持平分类为 `unchanged`。

候选按整体净收益选择，并展示所有单例变化。局部回路由按真实输入条件验证。集成时两个全集分别按几何加速比 ≥1 验收，单例退化保留明细；用户明确给定的更严格约束优先。泛化 ratio 契约独立保留。

## 历史策略与显式置信策略

`legacy_jitter_v1` 保持现有代码算法：`abs(candidate-baseline)` 在下列阈值内（含边界）的提升或回退均为 `jitter_no_effect`，只在其余 case 上计算有效几何平均；无有效 case 时为 `null`。

| 基线耗时 | 绝对抖动阈值 |
|---|---|
| ≤5us | 0.25us |
| >5至20us | 0.5us |
| >20至100us | baseline ×3% |
| >100us | max(3us, baseline ×1%) |

`confidence_effect_v1` 仅在显式选择或旧任务已冻结时使用：合法 proof 的候选减基线 95% 区间上界 <0 为提升，下界 >0 为回退，跨0为 `inconclusive`。未确认项不参与有效指标；该策略的最终/集成验收仍需合法确认或 byte-identical no-op，不能仅改标签为通过。

- 新采集通过 `ops-profiling-report`，使用 [profile-evidence.md](profile-evidence.md) 的 `profile10_independent_v1` proof；历史 `npu_compute10_independent_v1` 兼容。旧 [canonical10/application](performance-confidence-policy.md) 和 msprof op 收据可按原 kind 复核，不能与新协议混样本。
- 计划先于采集登记，绑定 case、SoC、物理卡、输入、原精度标准、源码/构建/加载身份、样本和完整 launch 映射。统计方法、seed、draws 事前冻结；原频率与10% spread 检查仅适用于此置信策略。
- 支持的方法是 `python_mt19937_percentile_median_v1`、`python_mt19937_independent_medians_v1` 及历史 `numpy_pcg64_percentile_median_v1`；bootstrap 区间不宣称 exact95% coverage。
- application proof 使用 `performance_effect_evidence.py --plan --registration --collection --baseline --candidate --case-id --baseline-variant --candidate-variant --out`；msprof op 的完整接口见 [msprof-op-effect-evidence.md](msprof-op-effect-evidence.md)。
- `--evidence` 可重复，每 case 一个 proof，必须属于当前 baseline/candidate 比较。`--same-implementation` 使用 schema1 `byte_identical_noop`，由 `validate_execution_identity` 验证两侧 source/build/loaded 与相同耗时收据；相等耗时本身不能证明同一实现。

## 摘要、选择与报告

```bash
python3 "$WORKFLOW_SCRIPTS/summarize_performance_effects.py" \
  --manifest "$RUN_MANIFEST" --baseline <baseline-performance.csv> \
  --candidate <candidate-performance.csv> \
  --out-csv <effect-details.csv> --out-json <effect-summary.json>
```

schema2 摘要按 legacy 原算法复核；schema3 记录 `policy_id/policy_version/classification_basis`，median 不需要额外 proof，confidence 保留其原依赖。postprocess schema1 为历史 legacy，schema2 记录显式策略。不得把新口径套到旧摘要。

每轮复用候选 effect，累计直接比较原始基线与保留实现，不连乘逐轮加速比。两种比较相同时复用同一摘要；未更换保留实现时复用已有累计摘要。选择和报告消费脚本产物。状态登记与恢复见 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。
