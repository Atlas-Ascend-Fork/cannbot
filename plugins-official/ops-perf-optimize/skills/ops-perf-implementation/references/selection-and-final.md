# 候选验证、终选与 demo 全集验收

单次功能通过不足以排除连续发射、跨 case 分配或时序引起的缺陷。统一性能采集前必须先做序列压测：对每个 eligible 候选，以与真实采集相同的 case 顺序、发射次数和 samples 数整序列连跑功能验收子集，再与其它路线 case 混序重复一遍。压测或采集中出现设备级崩溃时立即停采，按 `ops-perf-acceptance-criteria` 的精度规则路由 `ascendc-precision-debug` 定位，未定位前不得进入性能选择。

实施验证代理只对通过序列压测的 eligible 候选按基线同协议各采一次。然后按抖动策略生成 `effect-details.csv`、`effect-summary.json`，只比较有效 case 数、有效提升/回退、有效 case 几何加速比、最差回退和复杂度，顺序为：任一有效回退 case 相对当前基线的加速比（当前基线 `total_us` ÷ 候选 `total_us`）低于 0.70 的候选先出局；其余候选以有效 case 几何加速比最大化为选择准则，两个候选的有效 case 集合不同时，该指标只在共同的有效 case 上比较；差异落在抖动策略判定的等效范围内（以有效 case 几何加速比较低的一方为基线，对另一方运行同一效果脚本，其有效 case 数为 0，即逐 case 差异都在抖动范围内）时，依次比较最差回退、有效 case 数与有效提升/回退 case 数、实现复杂度。在上述下限之上，最差回退不单独构成否决。`selection.json` 记录本轮生效的下限、每个候选的最差单 case 比值，另记所保留实现的最差单 case 比值相对原始基线的累计值，使跨轮累计的回退在终验之前可见。泛化模式的选择顺序另见下文「泛化终选与全集验证」。`expected_effect`、历史 `abandon_if` 和整体优化目标不参与候选选择，也不得设为最低保留收益。baseline 也参加选择；无有效改善时保留 baseline。提升不按抖动过滤，有有效净收益的候选仍可胜出并进入下一轮；整体目标未达不等于候选落选。不得重复 profiling、事后按 case 拼候选或把未实测组合声明为最佳；任何组合代码都是新候选，必须重新走完整门禁。

每轮只保留 `roundN/analysis.md`、候选证据目录、`selection.json`；本轮与累计 effect 摘要保存在对应性能证据目录。按`$PLUGIN_ROOT/workflows/references/state-reporting.md`刷新报告并登记 `roundN.complete` 后，下一轮直接复用终选身份和已有采集作为当前基线。

性能 CSV 落到最终证据路径后，再用 `summarize_performance_effects.py` 生成 effect 摘要；不手写或复制修改摘要中的路径。证据搬迁时从搬迁后的同一组 CSV 重生成摘要并更新引用，不重新采集。

## 最终 demo 验收

最终实现运行功能全集。原始基线和最终实现分别在性能全集上最多采一次；已有同身份、同集合、同环境、同协议的完整证据直接复用。输出 `final-functional-regression.md`、`final-performance-comparison.md`、effect 明细与摘要，并归档 `final_optimized/`。按`$PLUGIN_ROOT/workflows/references/state-reporting.md`登记 `final.performance`，两份摘要参数均可引用本次原始基线 vs 最终实现的全集 effect 摘要，使报告刷新为最终全集结果。

## 泛化终选与全集验证

内层候选流程沿用本阶段候选门禁与共享采集协议。选择顺序为：先满足 geomean ratio ≥ 1.0 且 min ratio ≥ 0.6，再比较 geomean ratio、最差 ratio、抖动过滤后的有效 case 指标和实现复杂度。未实测代码组合仍是新候选，必须重新走功能门禁和一次性能采集。

内层达到 ratio 门限、没有不达标 case 或完成第 3 轮后进入外层全集验证。外层全集达到门限即进入最终回归；未达到且尚未完成第 2 次外层验证时，回到内层并基于最新全集 ratio 重新选择；第 2 次仍未达到时交付当前可信最佳实现并标记 `NOT_FULLY_ACHIEVED`，不得标记完全达标。
