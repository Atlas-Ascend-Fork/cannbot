# 候选验证、终选与 demo 全集验收

单次功能通过不足以排除连续发射、跨 case 分配或时序引起的缺陷。统一性能采集前必须先做序列压测：对每个 eligible 候选，以与真实采集相同的 case 顺序、发射次数和 samples 数整序列连跑功能验收子集，再与其它路线 case 混序重复一遍。压测或采集中出现设备级崩溃时立即停采，按 `ops-perf-acceptance-criteria` 的精度规则路由 `ascendc-precision-debug` 定位，未定位前不得进入性能选择。

实施验证代理对本轮通过序列压测的 eligible 候选按基线同协议采一次，生成 `effect-details.csv`、`effect-summary.json`，在该候选与当前基线之间做唯一选择。任一有效回退 case 的加速比（当前基线 `total_us` ÷ 候选 `total_us`）低于 0.70 时淘汰候选；其余情况按有效 case 几何加速比判断净收益，有有效净收益则保留候选，无有效改善则保留基线。置信策略下尚不能判断净收益的结果先完成合法确认；等效实现保留基线。`selection.json` 记录本轮下限、候选最差单 case 比值、保留原因及相对原始基线的累计最差比值，使跨轮回退在终验前可见。泛化模式另按下文 ratio 规则选择。`expected_effect`、历史 `abandon_if` 和整体目标不作为最低保留收益；整体目标未达不等于候选落选。已确认的微小净收益可保留，不另设最小收益门槛。任何组合代码都是新候选；组合或换方向时，在下一轮重新冻结并通过完整门禁。

启用 search_policy 时，按 [搜索决策契约](../../ops-perf-acceptance-criteria/references/architecture-search.md) 在同一 `selection.json` 写 `search` 结果。候选落选也保留其真实 effect、门禁及机制证据；保留基线的自比较摘要不能充当候选“无提升”的证据。本轮方案对应的规范 `roundN.impl.<scheme_id>` 完成保存点应含已复核的符合性 gate、真实构建/加载、完整功能和序列压测材料。主 Agent 登记 `roundN.complete` 时由脚本消费结果，不单独维护停滞计数。

每轮只保留 `analysis/roundN/analysis.md`（及契约、隔离 scope）、`implementation/roundN/` 下的候选证据目录与 `selection.json`；本轮与累计 effect 摘要保存在对应性能证据目录。按`$WORKFLOW_ROOT/workflows/references/state-reporting.md`刷新报告并登记 `roundN.complete` 后，下一轮直接复用终选身份和已有采集作为当前基线。

性能 CSV 落到最终证据路径后，再用 `$WORKFLOW_SCRIPTS/summarize_performance_effects.py --manifest "$RUN_MANIFEST"` 生成 effect 摘要；不手写或复制修改摘要中的路径。证据搬迁时从搬迁后的同一组 CSV 重生成摘要并更新引用，不重新采集。

## 最终 demo 验收

最终实现运行功能全集。原始基线和最终实现分别在性能全集上最多采一次；已有同身份、同集合、同环境、同协议的完整证据直接复用。输出 `final-functional-regression.md`、`final-performance-comparison.md`、effect 明细与摘要，并归档 `final_optimized/`。按`$WORKFLOW_ROOT/workflows/references/state-reporting.md`登记 `final.performance`，两份摘要参数均可引用本次原始基线 vs 最终实现的全集 effect 摘要，使报告刷新为最终全集结果。confidence终验不得留 `inconclusive`；待确认case须完成合法确认，或以两侧source/build/runtime完全相同的no-op收据证明 `same_implementation`。无需把每个case都固定做十轮，但无证据不得声称PASS。

## 泛化终选与全集验证

内层候选流程沿用本阶段候选门禁与共享采集协议。选择顺序为：先满足 geomean ratio ≥ 1.0 且 min ratio ≥ 0.6，再比较 geomean ratio、最差 ratio、按冻结policy确认分类的有效case指标和实现复杂度。未实测代码组合仍是新候选，必须重新走功能门禁和一次性能采集。

内层达到 ratio 门限、没有不达标 case 或完成第 3 轮后进入外层全集验证。外层全集达到门限即进入最终回归；未达到且尚未完成第 2 次外层验证时，回到内层并基于最新全集 ratio 重新选择；第 2 次仍未达到时交付当前可信最佳实现并标记 `NOT_FULLY_ACHIEVED`，不得标记完全达标。
