# 性能效果判定规则（版本化真源）

本文件维护收益判定的唯一规则；summary、候选选择、状态复核及集成全集 gate 使用 manifest 冻结的同一版本。采集有效性、收益方向与是否值得保留分别判定。不存在默认 3% 或 1us 的最小有效收益；用户接受约 0.7us 不产生 1us 下限。精度、身份、频率、完整映射、10% spread 和泛化 ratio 门禁均独立保留。

## 策略选择与历史兼容

新 `create-request` 默认冻结 `performance_effect_policy={"id":"confidence_effect_v1","version":1}`；用户显式 `--performance-effect-policy legacy_jitter_v1` 优先。旧 request/manifest 没有该字段时保持 legacy，不在读取、恢复或安装更新时补写新版。API `summarize(base,candidate)` 仍为 legacy；CLI 必须提供 `--manifest` 或显式 `--policy`，两者冲突拒绝。未知策略/版本/schema 拒绝。

- schema2 effect summary 使用 `legacy_jitter_v1` 原算法复核，历史报告、SHA 和判断不变。
- schema3 使用 `confidence_effect_v1`，记录 `policy_id/policy_version/classification_basis`、配对统计、proof 路径和完整依赖 SHA。新确认结论另存，不改旧摘要。
- postprocess legacy gate schema1 继续识别；confidence gate schema2 记录相同策略、proof 与 no-op 引用，并按该版本机械复算。

## confidence_effect_v1

canonical10 首先初筛：每次 target 全部 kernel 求和后取10样本中位数。下节历史四档阈值仅产生 `screening_signal`，不能否决已确认的小收益。无合法 proof 时，无论初筛变化大小都为 `inconclusive`，小变化依据 `needs_confirmation`，大变化依据 `screening_only_needs_confirmation`；大变化也不冒充统计确认。

事前登记同卡、同输入、相同预热与精度、平衡 AB/BA 的固定轮数和统计方法。针对待确认 case 采集一次完整计划；不是给每个全集 case 默认加十轮。每轮每版仍为 canonical10。禁止看到结果后加轮、删样本、重采择优。当前单卡 application proof v1 支持至少6个固定配对轮；MC²、多 rank 仍走原采集契约，尚无合法配对适配器时保持待确认，不能套单卡收据。

配对差值固定为候选轮中位数减基线轮中位数，重算冻结95%区间：

| 经机械验证的区间 | 正式分类 |
|---|---|
| 上界 < 0 | `effective_improvement` |
| 下界 > 0 | `effective_regression` |
| 包含或跨0 | `inconclusive` |

小回退与小收益对称；无证据不等同无收益或无回退。`inconclusive` 不参与有效指标，也不得因“有效回退数为0”让最终验收 PASS。最终和集成需要补齐确认，或使用有身份依据的 byte-identical no-op。后处理有有效回退时 `route_required`；无有效回退但有待确认时 `confirmation_required`；两者均不存在才 `pass`。

### 强变化的canonical10独立确认（不重复轮）

超出历史四档初筛范围的case，可使用 `kind=canonical10_independent` proof：两侧各一次原canonical10样本，在已冻结 `python_mt19937_independent_medians_v1` 下独立有放回重抽各10样本，统计候选median减基线median并线性取95%区间。method含 `statistic=difference_of_medians/confidence=0.95/quantile=linear/seed/draws`。该方法是percentile bootstrap、不保证exact95% coverage。它假设两侧相同卡/输入/环境/预热/活动频率，样本可交换且每侧分布代表该次采集；发现serial相关、热漂移或顺序偏差时转平衡配对验证；十个样本不能证明跨会话无漂移。因此只对强变化使用，初筛阈值仍不充当CI。CI排除0且全部原收据有效才正式分类，依据 `canonical10_independent_confidence`；跨0待确认。小变化即使该独立CI排除0，也为 `small_change_requires_paired_confirmation`，须平衡AB/BA控制顺序/会话噪声。

计划保留 `effect_case_id/baseline_variant/candidate_variant/soc/physical_device/snapshot/original_precision_contract/statistical_method`，另含 `baseline_collection/candidate_collection`，各侧固定 `manifest` 输出路径、`case_id`（该收据内执行ID）、完整 `case_order`、`expected_relevant_launches/expected_identity`。baseline可绑定既有收据SHA；candidate计划只声明未来输出路径（结果后proof登记SHA），registration必须早于candidate采集。每侧collection必须只标识一个实际source variant，或其actual execution case_run显式 `variant/confirmation.variant` 匹配绑定，不能从case ID名字或同名kernel推测变体。两侧皆可同一次两case初筛会话，或按相同协议的独立采集；合法自动split多session完整消费各session原execution/raw并核有序全集覆盖，不能丢split样本或只读第一会话。配对确认仍要求单同卡会话；不将独立样本伪称配对差值。原10样本由raw/map重算，headline必须正好是该10样本median。此路让强变化case无需默认十轮；byte-identical分支可直接no-op。没有任何适用完整收据的case仍待确认，不能无证据终验PASS。

### 证据与统计方法

`performance_effect_evidence.py` schema1 proof 绑定当前比较的两个 headline CSV（绝对路径及 SHA）、唯一 case、baseline/candidate variant、SoC、输入及两侧源码/正常编译/generated/build/live 身份。它核对事前 registration 的计划 SHA 和时间、固定轮/顺序、原始 op_summary、完整 ordered launch mapping、10个原样本、全部按原冻结标准判定的精度与必备输出文件、活动频率、source-tree 完整性及正常编译/实际加载 SHA；不接受仅填一个 PASS 字符串或 CI。任何依赖改变、错 case/SoC/比较、缺/重复轮、错映射、方法未知均拒绝。

新计划必须冻结 `original_precision_contract={status,rtol,atol}`，每sample/prime结果必须为PASS且逐项精确等于原标准、每项输出artifact路径/SHA存在；原标准可以非0，不能擅自放宽或统一改0。本次历史adapter自动使用原strict_pass/rtol0/atol0契约。

新配对计划字段 `statistical_method`：`id=python_mt19937_percentile_median_v1`、`statistic=median`、`confidence=0.95`、`quantile=linear`、整数 `seed` 和事前 `draws`（1000至1000000）。标准库 `random.Random(seed).choices` 对原配对轮差值 bootstrap，统计每次重抽轮差值的中位数，再线性取2.5/97.5百分位。它是 percentile bootstrap，不宣称 exact95% coverage；同时报告 omit-zero ties 的 exact 双侧 sign p 值作为辅助。

历史适配仅识别原计划完整方法声明：NumPy `default_rng` PCG64、seed2026、100000 draws、linear quantile；以 `numpy_pcg64_percentile_median_v1` 原算法复算，不换 RNG 或把 sign 改称原 primary。需要该环境的 NumPy；缺依赖报错。标记 `historical_adapter=true`，保留原计划与注册收据。禁止用事后新增方法冒称预注册方法。

原计划 JSON：`cases=[{case_id,round,variant,position}]`（round 从0起、每轮两项、position0/1），另含 `round_count/samples_per_case/expected_relevant_launches/effect_case_id/baseline_variant/candidate_variant/soc/physical_device/snapshot/expected_identity/statistical_method`。事前 registration 为 `issued_at` 与 `artifacts` 中计划路径/SHA；时间必须早于 collection.started_at。当前适配器的源码—构建—加载布局明确为：collection.identity.variant_sources 与 plan.expected_identity 的逐variant正常参考身份；`evidence/compile-identity.json` 含variants及source/generated/built/live收据，`inputs.json/device.json/precision-results.json/frequency/<case>-{0,9}.json` 及必备输出文件。这是本次已验证DSL正常编译取证布局，不声称标准collector的flat identity/任意TTK或MC²收据都能自动适配；缺原收据保持待确认，先提供保留原标准/身份的显式适配器。

新collector的planned-topology与效果计划是两个schema：`paired_confirmation.effect_plan`引用已注册effect-plan路径/SHA；其statistical_method与round_count须相同，`case_runs[].confirmation`使用round_id/order/position/variant/input_sha256。collector只核拓扑标签，proof builder逐项将已排序round_id映射到effect-plan.cases.round，核对AB/BA、variant、position及snapshotSHA，再核实际源/二进制证据。原始flat标签不是二进制身份；工具不自动生成事后统计计划或改写标签。

```bash
python3 "$WORKFLOW_SCRIPTS/performance_effect_evidence.py" \
  --plan "$PLAN" --registration "$REGISTRATION" --collection "$COLLECTION_MANIFEST" \
  --baseline "$BASELINE_CSV" --candidate "$CANDIDATE_CSV" \
  --case-id "$CASE_ID" --baseline-variant baseline --candidate-variant candidate --out "$PROOF"
python3 "$WORKFLOW_SCRIPTS/summarize_performance_effects.py" \
  --manifest "$RUN_MANIFEST" --baseline "$BASELINE_CSV" --candidate "$CANDIDATE_CSV" \
  --evidence "$PROOF" --out-csv "$DETAILS" --out-json "$SUMMARY"
```

`--evidence` 可重复，每 case 一个 proof。A/base proof 不能挪到 A/B，也不能用不同基线的 proof 确认累计比较。只有比较的 baseline/candidate CSV 及身份、集合完全相同才复用。

byte-identical no-op 用 `--same-implementation` 引用 schema1 `kind=byte_identical_noop`：`baseline/candidate` CSV收据、完整有序 `case_ids`、`baseline_execution/candidate_execution` 各含 `manifest/identity` 收据。调用原 `validate_execution_identity` 核验两侧 source/build/loaded 实际身份和完整目标SoC；签名相同且复用完全相同耗时收据时才分类 `same_implementation`。同收据 before=after 可接受；未知不同实现不能靠相等点估计或同 CSV 隐瞒回退。

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
