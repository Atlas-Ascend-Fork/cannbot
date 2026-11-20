# 候选选择与交付

探索后暂不采用的版本，在 `selection.json` 记录源码、实际结果和原因；启用 search_policy 时使用 `search.outcome=screened`，当前基线保持不变。

## 拟保留候选

用原 golden 和阈值完成冻结 `functional_acceptance`，按共享精度规则记录 strict/conditional 结论。准备 `scheme-conformance.json`，包含 scheme、required features 的实现状态、源码位置及实际验证结果引用。

使用派发的绝对路径运行符合性检查：

```bash
python3 "$WORKFLOW_SCRIPTS/validate_implementation_conformance.py" \
  --manifest "$RUN_MANIFEST" --contract "$CONTRACT" --result "$RESULT" \
  --isolation-scope "$ISOLATION_SCOPE" --git-repo "$GIT_REPO" \
  --baseline-rev "$BASELINE_COMMIT" --candidate-rev "$CANDIDATE_COMMIT" \
  --candidate-root "$CODE_DIR" --out "$GATE"
```

`GATE` 为 `scheme-conformance-gate.json`，包含符合性、源码隔离与候选安全结果。恢复时可用相同输入和 `--verify-existing` 核验已有 gate。

按 [采集协议](../../ops-perf-acceptance-criteria/references/performance-collection.md) 与 [效果策略](../../ops-perf-acceptance-criteria/references/performance-jitter-policy.md) 比较当前基线与候选。按整体净收益选择，保留逐例变化；局部回路由使用真实输入属性，并对组合后的代码身份验收。

`selection.json` 记录候选与保留实现的 commit、parent、contract、scope、gate、effect_summary 和选择原因。`selection.json`、effect 摘要、构建/加载身份和原始测试/性能证据同时作为知识回流素材，不额外维护知识字段或文件。启用 search_policy 时按 [搜索决策](../../ops-perf-acceptance-criteria/references/architecture-search.md) 填写 `search`，正式实测使用 `outcome=measured`，引用已完成的 `roundN.impl.<scheme_id>` 与候选真实 effect。

启用 experience_policy 时，在本轮既有 selection 的说明中保存可提炼的复盘：适用/不适用条件、实际改动与新增成本、观察及原件字段定位、尚未证实的因果解释、下一次采用/避免/重试所需证据。失败轮同样记录；没有正式计时就明确未测，不用保留基线的1.0替代失败候选。下一轮读取这些说明以避免无新证据的重复尝试；后处理再按 [经验提炼与验收](../../ops-perf-postprocess/references/experience-reflux.md) 综合，仍不新增每轮知识文件，不改变当前性能终选规则。

显式置信策略需要暂定参考时，按搜索决策中的 `provisional:true` 分支提交诊断报告与完整候选门禁；最终效果仍须确认。median 按冻结样本的中位数直接比较，不额外要求置信 proof。

交付本轮与累计 effect 摘要；累计直接比较原始基线与同一保留实现，相同比较复用已有摘要。主 Agent 按 `$WORKFLOW_ROOT/workflows/references/state-reporting.md` 登记 `roundN.complete`。

## 搜索观测交接

收到 frontier 时，仅实施本轮已冻结契约对应的方案，在契约和 scope 内迭代。其余节点留给后续 analysis；需要改变方案、候选空间或 scope 时交回主 Agent。完成上文构建、功能、符合性和性能验证后，将当前方案的实际 effect summary 关联到 frontier。

`search-evidence.json` 使用已有 SHA 收据，`candidates` 只列本轮实际评估的契约方案，不为未实施节点补造结果：

```json
{
  "schema_version": 1,
  "manifest": {"path": "/abs/run/manifest.json", "sha256": "<sha256>"},
  "cases": {"path": "/abs/frozen-tuning.csv", "sha256": "<sha256>"},
  "candidates": [
    {"scheme_id": "<本轮契约的 scheme_id>",
     "effect_summary": {"path": "/abs/effect-summary.json", "sha256": "<sha256>"}}
  ]
}
```

使用 holdout 时，用相同结构引用 analysis 交接的独立冻结集合及真实汇总。采集和统计继续按 [性能证据](../../ops-perf-acceptance-criteria/references/profile-evidence.md) 执行。

用 `search_round.py --frontier` 直接消费 analysis 已登记的前沿，并传入本轮契约：

```bash
python3 "$WORKFLOW_SCRIPTS/search_round.py" \
  --state /abs/run/workflow-state.json \
  --frontier /abs/analysis/round1/candidate-frontier-s1.json \
  --contract /abs/analysis/round1/implementation-contract-s1.json \
  --evidence-index /abs/implementation/round1/search-evidence.json \
  --attribution \
  --out-dir /abs/implementation/round1/search
```

有 holdout 汇总时追加 `--holdout-evidence-index`。此模式校验 frontier 与契约的对应关系，仅接受本轮契约方案的结果，输出 `measurements.json` 和 `observation.json`；保留原 frontier，不重新展开候选或调用预筛模型。工具复用收据验证和效果重算，不采集性能、不修改源码，也不替代正式门禁；`ready_for_confirmation` 仅为建议。

`--attribution` 恢复原搜索的未提升归因，使用 analysis 前沿中的 `base_factors`、当前效果分类以及 `--state` 中同父实现、同冻结用例的有效历史，输出 `attribution.json`。它提示实现收益未兑现、统计未决或组合负交互，供下一轮 analysis 复盘；旧前沿缺少 `base_factors` 时省略该可选参数。归因沿用冻结效果策略，不另设噪声阈值或补造 CI。预期收益未达仍不影响实测有效候选的终选资格，慢一次也不能自动写 `mechanism.status=refuted`。具体机制结论与补证条件仍写入下文 selection，并随归因及其引用材料交接。

将本轮契约方案的观测附加到已有 `selection.json`，显式传入该 `scheme_id`：

```bash
python3 "$WORKFLOW_SCRIPTS/search_selection.py" \
  --selection /abs/implementation/round1/selection.json \
  --observations /abs/implementation/round1/search/observation.json \
  --scheme-id s1 \
  --conformance-gate /abs/implementation/round1/scheme-conformance-gate.json \
  --effect-summary /abs/effect-summary.json
```

适配器只写 `selection.json.search`，保留既有选择结果；已有 search 字段时先核对再显式使用 `--replace`。机制结论、证据与重试条件按 [搜索决策](../../ops-perf-acceptance-criteria/references/architecture-search.md) 补齐，对应参数为 `--mechanism-status`、`--mechanism-evidence`、`--evidence` 和 `--retry-condition`。随本轮实施/完成交接提交观测、索引及依赖证据，由主 Agent 按原保存点复核并登记。

编译、精度或证据失败且没有有效 effect summary 时，按共享契约直接记录对应失败 outcome、诊断证据和重试条件，保留基线；不调用实测结果适配器，也不为补齐观测而伪造性能数据。

## 最终交付

退出实施循环时，对保留实现完成功能与性能全集验收；同身份、同集合、同环境和协议的完整结果可复用。输出 `final-functional-regression.md`、`final-performance-comparison.md`、effect 摘要，登记 final 标签 `perf-opt/<run-id>/final` 与 `final.performance`。DSL 同时交付 stage=implementation、collection=performance_full 的 `dsl-compile-evidence.json`。

泛化模式按共享 [ratio 规则](../../ops-perf-acceptance-criteria/references/ratio.md) 选择：先满足 geomean ratio ≥1 且 min ratio ≥0.6，再比较整体、最差 ratio 和实现复杂度；内层最多3轮，外层全集最多2次。最终据实标记 ACHIEVED 或 NOT_FULLY_ACHIEVED。
