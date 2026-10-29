# 单方案搜索决策

每轮实现一个决策，架构决策作为原子单元评估；停滞后重新审视架构，已接受实现成为下一轮参考，正反经验随证据传递。本契约规定跨阶段证据；搜索由主工作流的 analysis/implementation 循环执行，`$WORKFLOW_SCRIPTS/search_policy.py` 只检查证据与推导下一动作。

## 输入与状态

新请求冻结 `search_policy={"id":"architecture_search_v1","version":1}`。request、manifest、state 的策略必须一致；缺字段的输入保持原协议，未知版本或显式 null 拒绝。每轮最多冻结一份实施契约；没有就绪方案时仍提交分析、保留基线和后续诊断依据。

契约是决策真源，`selection.json` 是评估真源；搜索事件写入现有 `workflow-state.json.events`。状态脚本持锁、原子提交并重绘报告，搜索模块不另写状态文件。`inspect.search` 从事件推导当前参考、连续无新最优次数、机制结论和重新尝试条件。重复提交同一保存点不重复计数，改变已登记内容须使用新身份，不能覆盖证据。

## 实施契约的 search 字段

在现有 schema 3 `implementation-contract-<scheme_id>.json` 中添加 `search` 字段。以下示例为字段模板，机制、证据路径、验证结论和重试条件均须根据当前算子与本轮证据填写：

```json
{
  "search": {
    "kind": "architecture",
    "mechanism": "<本轮待验证的机制标识>",
    "parent": {"path": "/abs/current-baseline", "sha256": "<source identity>"},
    "workload": {"path": "/abs/frozen-tuning-cases.csv", "sha256": "<file sha256>"},
    "baseline_performance": {"path": "/abs/baseline/performance.csv", "sha256": "<file sha256>"},
    "depends_on": [],
    "trigger": [{"path": "/abs/diagnostic-evidence.json", "sha256": "<file sha256>"}],
    "mechanism_check": "<由本轮诊断确定、可在实施后检验的机制条件>"
  }
}
```

- `scheme_id` 是全 run 唯一的决策 ID，使用字母、数字、下划线或连字符；一份契约的全部 required features 作为一个原子单元。一个方案可覆盖多个真实输入分支，但不能藏入多种待比较的互斥实现。
- `kind=architecture|local` 区分结构性决策与既定结构上的局部优化。动作、目的、成本、收益假设及后续方向写入已有 `analysis.md`；未就绪方向不生成可派发契约。
- `parent` 使用现有 `validate_schedule_contract.source_identity(Path(...))` 的源码/构建输入快照算法，与 conformance gate 的 baseline 身份一致。首次由主 Agent 对照 preparation 的真实基线验收；之后必须是当前保留实现。它不替代构建与实际加载身份链。
- `workload` 引用本轮冻结的用例 CSV；契约 `case_ids` 与其顺序完全一致，baseline performance 也覆盖同序 case。standard 使用冻结调优集合，generalization 使用从冻结全集选出的本轮子集。选择子集仍属于 analysis，搜索不重选用例。
- `depends_on` 只引用已接受且未被重新打开的决策。架构与局部优化形成可追溯依赖；自依赖、未知依赖、尚未接受或已重开的依赖不能放行。
- `trigger` 必须是实际读取的测量/诊断证据。`mechanism_check` 写可检验的机制条件，实施后用流水、生成代码或隔离 probe 检查；单个速度数值不能证明架构或机制成立。

主 Agent 验收后，以规范 `roundN.analysis`（泛化为 `gen.roundN.analysis`）登记该契约；首次阶段交接另记 `phase.analysis`。实施必须消费该轮合同和已冻结 scope。上一轮完成之前不派发下一轮方案。

## 评估与参考晋升

在该轮已有的 `selection.json` 中加入：

```json
{
  "search": {
    "scheme_id": "<本轮实施契约的 scheme_id>",
    "outcome": "measured",
    "conformance_gate": {"path": "/abs/scheme-conformance-gate.json", "sha256": "<file sha256>"},
    "effect_summary": {"path": "/abs/candidate/effect-summary.json", "sha256": "<file sha256>"},
    "evidence": [{"path": "/abs/functional-and-sequence-acceptance.md", "sha256": "<file sha256>"}],
    "mechanism": {
      "status": "verified",
      "evidence": [{"path": "/abs/mechanism-probe.json", "sha256": "<file sha256>"}]
    },
    "retry_condition": "<重试所需的条件变化或补充证据；不适用时说明原因>"
  }
}
```

`outcome` 为 `measured`、`implementation_failed`、`precision_failed`、`evidence_invalid` 或 `no_candidate`。没有实施契约时使用 `no_candidate`，`scheme_id=null`。非 measured 结果保留实际故障/缺口证据，不提供虚假的 effect 或通过 gate。

`mechanism.status=verified|refuted|unknown`。verified/refuted 须引用非空机制证据；unknown 不得被解释为机制无效。`retry_condition` 记录改变哪些条件或补什么证据后才值得重试；无适用重试时说明原因。SHA 只证明材料未改，主 Agent 仍需审阅证据是否支持谓词、候选是否真实构建并完成原功能/序列门禁。

`roundN.complete` 自动核验：合同归属、已接受的 `roundN.impl.<scheme_id>`、重算的 conformance gate、候选源码、冻结效果策略、完整 effect/proof 依赖与 case 覆盖。已接受的实施保存点须引用 gate 及真实构建/加载、功能、序列材料。

- 晋升只发生在本轮唯一终选后：保留候选必须有实测净收益，其当前摘要与 `--performance-summary` 相同。`expected_effect` 不参与收益判定。
- 候选落选时，`search.effect_summary` 仍引用该候选的真实评估；`--performance-summary` 则引用保留基线的自比较。不能用 baseline vs baseline 推断候选失败。
- 原始基线、外部性能目标和当前搜索参考各有用途；晋升仅更新当前参考。累计摘要仍直接比较原始基线，不连乘逐轮加速比。
- 已有效的采集和身份链直接复用；近噪声边界按冻结 confidence 策略确认，不引入固定百分比收益门槛。

## 下一动作与架构重规划

计数单位是一次已完成、可比较的候选评估。相同父实现、负载、backend 和目标 SoC 下连续三次未刷新最优，返回 `next_action=replan`。候选真正被接受后清零；泛化子集或参考身份改变后重新计数。一次记录或报告重绘不等于一次尝试。

编译/精度失败返回 `repair_candidate`，无效采集返回 `repair_evidence`，都不增加停滞次数。已关闭失败轮次的诊断和补证由下一轮 analysis 消费；同机制重试必须满足下文的新证据要求。统计不足以确认净收益时先完成合法确认，再结束本轮。无就绪决策、验收僵局或架构限制可提前要求重规划，不必等三次。

analysis 对参考的测量特征、剩余目标差额、关键未知与可改变的拓扑重新分析，交付实际诊断证据。主 Agent 据此登记：

```bash
python3 "$WORKFLOW_SCRIPTS/workflow_state.py" search-replan \
  --state "$WORKFLOW_STATE" --reason "<本轮触发原因>" \
  --reopen "<最早受影响的已接受决策 ID>" \
  --evidence "/abs/analysis/<round>/architecture-review.md" \
  --message "<本轮证据支持的诊断结论与需重新评估的决策范围>"
```

`--reason` 为 `plateau|graph_exhausted|gate_impasse|architecture_limit`，按本轮实际触发条件选择。`--message` 概括所引证据支持的诊断与重评范围；证据尚不足以定位瓶颈时记录已知现象与待验证问题。

`--reopen` 指向最早受影响的决策，可重复；脚本沿依赖标记其后继需重评，保留历史证据与当前可信实现。只是重新审视方向、尚无需要重开的已接受决策时可省略。先关闭当前轮次并保留其结果，再登记重规划；新方案在下一轮使用新的方案标识（`scheme_id`）并重新冻结源码修改范围，不能在一轮内换方案。重规划不代替源码范围审批、结构方向台账或同步/精度验收。

当前轮数、目标和泛化内外层上限始终有效。三次停滞只能说明需要改变搜索方向，不能证明物理上限；预算已结束时记录尚有重规划方向并完成应有交付，不自动增加轮数。

## 失败记忆与机制知识

相同上下文和机制已有落选/实现失败/精度失败/采集无效记录时，新的实施契约须补 `search.retry={decision_id,reason,evidence:[ref]}`，指向最近一次相关决策并给出条件变化的新证据。实现缺陷、额外成本、机制证伪与采集无效分别记录；一次失败不永久封禁整类优化。

下一轮通过 `inspect.search.observations` 找到结论，再按历史合同/selection 路径读取原件。机制 verified 的实测记录才可整理为知识仓待入库材料，包含平台、触发症状、最小 probe、已知限制和证据引用；性能变快本身不认证解释。跨算子复用沿已有 cannbot-knowledge 流程，调优阶段保持其只读 consumer 边界。
