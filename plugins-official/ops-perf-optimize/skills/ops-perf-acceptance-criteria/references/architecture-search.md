# 单方案搜索决策

每轮实现一个决策，架构决策作为原子单元评估；停滞后重新审视架构，已接受实现成为下一轮参考，正反经验随证据传递。本契约规定跨阶段证据；搜索由主工作流的 analysis/implementation 循环执行，`$WORKFLOW_SCRIPTS/search_policy.py` 只检查证据与推导下一动作。

## 输入与状态

新请求冻结 `search_policy={"id":"architecture_search_v1","version":1}`。request、manifest、state 的策略必须一致；缺字段的输入保持原协议，未知版本或显式 null 拒绝。每轮最多冻结一份实施契约；没有就绪方案时仍提交分析、保留基线和后续诊断依据。

契约是决策真源，`selection.json` 是评估真源；搜索事件写入现有 `workflow-state.json.events`。状态脚本持锁、原子提交并重绘报告，搜索模块不另写状态文件。`inspect.search` 从事件推导当前参考、连续无新最优次数、机制结论和重新尝试条件。重复提交同一保存点不重复计数，改变已登记内容须使用新身份，不能覆盖证据。

方案搜索、比较与架构重规划时，按分析 Skill 的[分析标准](../../ops-perf-analysis/references/analysis-execution.md#分析标准)评估并按需使用理论建模；模型仅作辅助证据，不以预测收益作为实施门槛，候选实测、参考晋升和停止规则不变。

## 实施契约的 search 字段

在现有 schema 3 `implementation-contract-<scheme_id>.json` 中添加 `search` 字段。以下示例为字段模板，机制、证据路径、验证结论和重试条件均须根据当前算子与本轮证据填写：

### git 模式（两个后端统一使用）

```json
{
  "search": {
    "kind": "architecture",
    "mechanism": "<本轮待验证的机制标识>",
    "parent": {"commit": "<基线 commit 全 SHA>", "tree": "<基线树哈希>"},
    "workload": {"path": "/abs/frozen-tuning-cases.csv", "sha256": "<file sha256>"},
    "baseline_performance": {"path": "/abs/baseline/performance.csv", "sha256": "<file sha256>"},
    "depends_on": [],
    "trigger": [{"path": "/abs/diagnostic-evidence.json", "sha256": "<file sha256>"}],
    "mechanism_check": "<由本轮诊断确定、可在实施后检验的机制条件>"
  }
}
```

### 关键约束（两种模式通用）

- **`trigger` 必须是 list**（`[{"path": ..., "sha256": ...}]`），不能是单个 dict。
- **`workload` 必须引用冻结调优集合 CSV**（`run/baseline/performance-tuning-cases.csv`），不能自建副本。
- **`baseline_performance` 的 case_id 顺序必须与 `workload` 完全一致**。TTK 输出顺序通常不同于冻结调优集，agent 必须重排。
- **`case_ids` 必须从 `workload` CSV 读取**（与冻结调优集同序），不能从 TTK 输出或自建 CSV 读取。
- `parent` 的值必须与 conformance gate 的 `evidence_identity.baseline` 逐键相等（两个后端统一为 git 模式：`{"commit","tree"}`）。

- `scheme_id` 是全 run 唯一的决策 ID，使用字母、数字、下划线或连字符；一份契约的全部 required features 作为一个原子单元。一个方案可覆盖多个真实输入分支，但不能藏入多种待比较的互斥实现。
- `kind=architecture|local` 区分结构性决策与既定结构上的局部优化。动作、目的、成本、收益假设及后续方向写入已有 `analysis.md`；未就绪方向不生成可派发契约。
- `parent` 使用基线评估定稿的基线 commit 的 `{"commit","tree"}`（两个后端统一 git 模式）。首次由主 Agent 对照基线评估定稿的真实基线验收；之后必须是当前保留实现。它不替代构建与实际加载身份链。
- `workload` 引用本轮冻结的用例 CSV；契约 `case_ids` 与其顺序完全一致，baseline performance 也覆盖同序 case。**TTK 输出的 case 顺序通常与冻结调优集不同，必须重排后再写入 baseline_performance CSV**。standard 使用冻结调优集合，generalization 使用从冻结全集选出的本轮子集。选择子集仍属于 analysis，搜索不重选用例。泛化收敛轮（无不达标 case、跳过内层新优化）不构造空调优子集：`workload`/`baseline_performance` 允许引用冻结全集作为证据映射（按 workflow-contract 第 5 节证据映射处置），机械校验按全集身份判定，不得为通过非空校验虚构调优子集。
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

`outcome` 为 `screened`、`measured`、`implementation_failed`、`precision_failed`、`evidence_invalid` 或 `no_candidate`。没有实施契约时使用 `no_candidate`，`scheme_id=null`。screened 的探索记录及 measured 的晋升条件见 [终选参考](../../ops-perf-implementation/references/selection-and-final.md)。

`mechanism.status=verified|refuted|unknown`。verified/refuted 须引用非空机制证据；unknown 不得被解释为机制无效。`retry_condition` 记录改变哪些条件或补什么证据后才值得重试；无适用重试时说明原因。

正式 measured 结果在 `roundN.complete` 自动核验：合同归属、已接受的 `roundN.impl.<scheme_id>`、重算的 conformance gate、候选源码、冻结效果策略、完整 effect/proof 依赖与 case 覆盖。已接受的实施保存点须引用 gate 及真实构建/加载、功能、序列材料。

- 晋升只发生在本轮唯一终选后：保留候选必须有实测净收益，其当前摘要与 `--performance-summary` 相同。`expected_effect` 不参与收益判定。
- 候选落选时，`search.effect_summary` 仍引用该候选的真实评估；`--performance-summary` 则引用保留基线的自比较。不能用 baseline vs baseline 推断候选失败。
- 原始基线、外部性能目标和当前搜索参考各有用途；晋升仅更新当前参考。累计摘要仍直接比较原始基线，不连乘逐轮加速比。
- 已有效的采集和身份链直接复用；效果按冻结策略判定。

显式 confidence 策略可用 `screened`、`provisional:true` 和逐 case 双方 `screening_evidence` 暂定参考；通过候选符合性与实施验收、身份核验且观察到净收益后晋升，正式效果待最终确认。字段见 [性能证据](profile-evidence.md)。median 比较使用 `measured`。

## 候选前沿与搜索执行（frontier）

使用 frontier 时，analysis 交付候选前沿和本轮唯一实施契约，implementation 交付该契约方案的真实观测。初始候选数量至少为 `ceil(n / p_pass)`，剪枝后至少保留 `n` 个；前沿节点数量不等于本轮实施数量。候选生成与结果适配的操作分别由各阶段 Skill 管理。

`candidate-frontier-<scheme_id>.json` 由 `search_policy.validate_frontier` 核验：

- 轮次与父身份绑定本轮契约；`parent` 沿用既有 Git/目录身份格式。
- `n/p_pass/epsilon` 定义生成与剪枝预算；`prefilter.l0/l1/l2` 记录模型范围、覆盖、证据或不可用原因。
- `nodes[]` 包含唯一 `scheme_id`、`kind/level`、`mechanism`、`optimization_type`、`trigger`、`expected_gain_range`、`cost/risk`、`fidelity/status`、`explore_tag`、`depends_on` 和可选 `factors/bindings`；保留至少两种优化类型和一个 `open` 节点。
- 选中节点与契约的 `search.frontier_parent/fidelity/expected_gain_range/cost` 一致；声明 `candidate_factors/candidate_bindings` 时也须与节点一致。这是声明一致性检查，实际源码、构建和运行实现仍由原 conformance gate 验证。

生成器另保存可选 `base_factors`，供单轴/组合归因解释参数变化。历史先验与代理排序只消费已验证的工作流记录；归因报告只是后续诊断建议，不替代 `mechanism.status` 的证据要求，不写 no-go、不晋升参考。具体操作分别见 analysis 和 implementation 的搜索交接。

生成器的可选 `candidate_space` 收据绑定剪枝前轴定义，供原 `search-frontier` 命令统计真实实测覆盖；缺失时保持 unknown。L1 实际剪枝（`budget_skipped>0`）须附 `ranking_validation` 收据，其 SHA 与原 L1 证据一并核验；校准报告的内容、模型适用范围及覆盖结果的方向处置由 analysis 按本阶段参考复核。

`workflow_state.py search-frontier` 从现有事件读取有效历史，调用统一策略排序、检查探索配额和剪枝，不写状态。frontier 在 `roundN.analysis` 的原 `mark --artifact` 保存点登记；结果和辅助证据随原实施/轮次保存点登记。

探索与确认复用 [统一采集协议](performance-collection.md) 和 [性能证据](profile-evidence.md)。搜索适配已有 effect summary，`score_distribution.unit=case_median_ratio` 表示逐 case 中位数之比，其摘要引用须与 `selection.json.search.effect_summary` 一致，Pareto 层级用于排序；CI 只携带原 proof 统计，不将 case 中位数作为独立重复样本。holdout 在 analysis 阶段冻结且与调优集分离，回退/补证结论沿用冻结性能策略。`ready_for_confirmation` 只是建议，正式晋升条件见上文。

## 下一动作与架构重规划

计数单位是一次已完成、可比较的候选评估。相同父实现、负载、backend 和目标 SoC 下连续三次未刷新最优，返回 `next_action=replan`。候选真正被接受后清零；泛化子集或参考身份改变后重新计数。一次记录或报告重绘不等于一次尝试。

编译/精度失败返回 `repair_candidate`，无效采集返回 `repair_evidence`，都不增加停滞次数。已关闭失败轮次的诊断和补证由下一轮 analysis 消费；同机制重试必须满足下文的新证据要求。无就绪决策、验收僵局或架构限制可提前要求重规划，不必等三次。

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

**失败记忆按 case 桶隔离**：frontier 节点、实施契约 `search` 块和 selection 观察可携带可选 `case_bucket`（shape 档位等稳定分桶键）。带桶观察只在同桶节点上计数（`attempts`/`prior` 等）；无桶观察保持原全集语义，作用于全部节点。对某档位失败的机制不得据此封锁其他档位或未分桶方向的重新尝试——跨桶重试不必推翻原失败记录，但须在 `retry.reason` 写明目标桶与原记录的负载差异。

下一轮通过 `inspect.search.observations` 找到结论，再按历史合同/selection 路径读取原件。机制 verified 的实测记录才可整理为知识仓待入库材料，包含平台、触发症状、最小 probe、已知限制和证据引用；性能变快本身不认证解释。跨算子复用沿已有 cannbot-knowledge 流程，调优阶段保持其只读 consumer 边界。
