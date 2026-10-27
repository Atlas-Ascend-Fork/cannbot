# 诊断分析执行参考

本阶段先按 `ops-perf-acceptance-criteria` 的性能采集参考采集或复用当前基线；下面的只读边界约束采集完成后的分析推导。修改源码或负载的诊断探针只在采集阶段的专用副本进行，冻结基线不变；未改源码的流水图可沿用基线身份。分析只消费已登记的有效证据。每个 case 同时读取 `performance-targets.json`，报告目标时延、差距和达标状态；不得用停止轮次代替性能目标。

## 职责

消费主 Agent 已冻结的用例、当前基线源码和本阶段一次统一 profiling，解释每个 case 的瓶颈并给出可直接实施的方案。不得重选 case、重采性能、编译 demo 或修改源码。

开始前读取派发输入视图、本阶段 Skill 和本角色输入；需要逐 case 选择记录等详细字段时再按路径读取 `RUN_MANIFEST`。按验证类型读取共享参考。输入不完整或身份不匹配时退回主 Agent，不猜测映射。

性能分析固定按以下顺序执行：输入与证据校验 → 逐 case bound/瓶颈分析 → 特殊算子路由 → 族/模板与 API 核验 → 方案和实施契约。不得合并、跳过或调换前置门禁。

## 输入

- `CODE_DIR`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`ROUND`；
- `performance-tuning-cases.csv`；
- `roundN/perf/baseline/performance.csv`、`collection_manifest.json`、schema v3 `validation.json`；
- 上一轮 `analysis.md`、`selection.json`（round1 为 absent）；
- `source-compatibility.md`：公开契约面、工程支持 SoC、目标工程代际隔离风格和证据；
- `extraction-manifest.json`：原工程到独立工作工程的文件/依赖/调用入口映射；
- 信封 `KB_ROOT`（cannbot-knowledge 仓根，包含 `governance/` 与 `knowledge/`；absent 时本阶段无知识增强）；
- 目标 SocVersion 与可验证本地 SDK/参考路径。

按共享 [performance-collection.md](../../ops-perf-acceptance-criteria/references/performance-collection.md) 校验协议、身份和覆盖。只使用 `mapped_launches[]` 的 case/sample/role/kernel 映射；MC²/多 rank 不套用 application 协议，也不得按目录、kernel 名或 CSV 顺序猜测 case 映射。

## 分析标准

1. 逐 case 记录计算模式、dtype/shape/attrs、bound（VEC/MEM/SCALAR）、关键指标、`total_us` 和证据路径。每个冻结 case 必须恰好出现；spread >10% 标不确定性，不自行重采。按下文“效率与理论上限”计算逐 case 量化证据。多阶段融合算子若聚合指标不足以归因，优先用覆盖目标计算路径的完整仿真流水图定位阶段依赖、掩盖和同步等待，不再叠加消融；无有效仿真图时，才消费已登记的上板阶段隔离证据，其端到端耗时差只表示边际影响，不相加推算可节省耗时。
2. 先按 case 计算模式判定算子族，先按精确 `TARGET_SOCS` 执行两本策略/最佳实践 Skill 的代际前置路由，再读取 `ascendc-performance-best-practices` 对应族中目标适用的说明和模板代码，按决策树选路径。算子名不能锁定单一族；Broadcast、Elementwise、Reduction 分别按实际轴和计算结构判定，数据依赖读地址走 Gather，数据依赖写地址走 Scatter。
3. `KB_ROOT` 存在时，方案设计前加载 `knowledge-query` 及其 `references/cli.md`、性能优化模式与证据工作流；以 `--knowledge-root "$KB_ROOT"` 固定知识仓。复用主 Agent 的 discover，以 `TARGET_SOCS` 确认任务目标平台，按该 Skill 的平台识别规则映射，不用本机型号或知识仓缺省平台覆盖任务目标；A2/A3 工程证据复用不代表知识卡可省略平台适用性核对。围绕主导 profiling 信号拆分独立 decision，以实体加一个关键约束的短 query 执行 `search`，按需限定 `ops` / `ascendc` 和已注册的优化、机制、API 或 runbook 类型；准确 API 用 literal，机制或现象用 text，默认 stable。先看返回的 `results` 中 `path` / `local_path`、`title` 和 `description` 选卡，再按绝对 `local_path` 阅读完整正文，核对平台、版本和适用边界，按需沿链接补证；不得把搜索摘要当作已核验知识。KB 检索结论是假设级证据，逐条标 `adopted`/`refuted`/`deferred` 后并入本轮分析，不替代本文件的分析标准和共享 Skill 路由。按 Query 的证据工作流保存独立 decision 的 receipt 与已读卡路径/指纹；有缺口时保留 gap/insufficient，不伪造 covered。退出码 0 的零命中记录知识缺口；参数或索引错误先按具体原因处理，仍不可用时记 `kb_unavailable` 与错误原因，不阻塞分析，也不自动构建索引。
4. 策略推导按 `ascendc-perf-optimize` 的 4 步流程执行：Step 1 Tiling 理论建模必选，产出理想 tiling data 作为后续修正对照，并结合标准 1 的 `compute_efficiency` 输出给出理论最优耗时（roofline 上限：`max(字节/带宽, FLOP/算力)`）与距该上限的可达 headroom，作为"值不值得调、最多能到哪"的定量上界；Step 2 仅命中 MC²/通信类算子时执行，按 `ascendc-mc2-best-practice` 的 `references/shared/profiling_mc2.md` 口径判定主导流水与通信隐藏率，只消费基线采集阶段已登记的 TilingData 与隔离测试证据（T_comm/T_compute/R 值），缺失时退回主 Agent 按协议补采，不得修改源码自行补采；Step 3 仅在跨核同步或共享目标写入时分析核间依赖、同步和负载；Step 4 单核流水 bound 诊断结论并入逐 case bound 证据。各步产出的 tiling 修正建议和优化策略直接映射为方案与实施契约 required features，不因流程推导重选 case 或重采性能。
5. 只有族级终选仍使用 SIMT 时才读取 SIMT 指南。不得因为原源码有 `__simt_vf__` 就跳过族级选路。
6. 模板按证据分类：构建契约一致且已有编译证据才是“可直接使用”；上下文/契约待补为“集成边界待验证”；只有说明则是“设计参考”。不得用概念伪代码替代已找到的模板骨架。
7. DAV_3510 的向量、归约、寄存器重排、Cast/Pack 热点查询 `reference/common/arch35/regbase/catalog.json` 并运行 `vf_preflight.py --strict`。记录 catalog ID、match_hints、readiness、目标工程的编译/精度/性能验证方案、`example_build_contract` 和目标差异；查询不等于选中。
8. 融合算子中的每个内嵌 MM 独立命中 MatMul 族并记录 `mm_route`、shape、布局和证据。DAV_3510 按 Blaze → 保留 Cube MMAD 的低阶流水重建 → 高阶 MatMul API 数据流依次评估；AIV 替换须有独立、可比较的同 case 实测证据。低 MAC 利用率、较小 K 或外层融合名称都不足以直接选择 AIV。
9. 仅当目标单元已确认是 AIV 向量计算链、数据已 UB 驻留且 VEC 耗时主导时，才评估 `register-resident-vector-chain`；该条目不能用于替换内嵌 MM。
10. DAV_3510 目标的 RoPE/rotary 必查 `paired-segment-rotate`。DAV_3510 量化逐 case 给出 `quant_vf_route`：`shared-exponent-pack`、`two-pass-amax-cast` 或有证据的 `no_matching_vf_example`。
11. 具体 AscendC API 参数必须用 `ascendc-docs-search` 和目标 SDK 验证，未经验证的参数不得进入方案。
12. 静态检查点处于 `ready` 时，把适用 finding 作为 profiling 假设直接并入分析，逐条标 `adopted`、`refuted` 或 `deferred`；不再生成独立代码检视阶段或报告。
13. 从 manifest 读取 `TARGET_SOCS`，不得把当前设备或 A5 工作基线扩大成全代际结论。A2/A3 共用同一套 arch22 实现，验证结果可互换，方案无需按二者拆分。方案不得修改公开 API、原约束或支持 dtype。按 `$WORKFLOW_ROOT/workflows/references/source-isolation.md` 追踪共享实现和模板使用者，将复制后独立路由、非目标代际及同代未涉及分支的原 fallback 作为 required feature；生成实施前冻结的文件/行范围，不能仅以架构目录命名证明隔离。

## 效率与理论上限

逐 case 调用 `ops-profiling/scripts/compute_efficiency.py --json`，以当前 `total_us` 为耗时输入；保存命令、输入来源、目标 SoC 峰值口径及原始 JSON，写入分析报告。

- 字节量使用已核验的 `--bytes`、`--io`/`--case` 估计，或从已有同身份 profiling 通过 `--bytes-from-profiling --op-summary` 读取。FLOP 使用 `--flops`，或已核验计数语义的 `--flops-from-profiling`。实际接口以脚本 `--help` 为准，不依赖旧文档中的算子注册目录。
- 峰值按精确 `TARGET_SOCS` 与实际内存层级显式传 `--peak-hbm-bw`；有 FLOP 时按计算引擎传 `--compute-unit` 和 `--peak-cube-flops` 或 `--peak-vec-flops`，不使用默认 A5 档推导其他代际。
- 已有 op-mode `PipeUtilization.csv` 时传 `--pipe-util` 复核 measured bound 和推导 `mte2_util`，或用 `--mte2-us` 传已测载入时间。op-mode 不可用时仍以 application 耗时和已核验工作量计算；分析不得为此自行重采。
- 记录 `MBU/MFU/mte2_util/cost_bound/ceiling_us/headroom_us/headroom_pct/verdict`。缺失的 FLOP 或 MTE2 指标按脚本输出保留 null，标明缺口，不伪造计算到顶或 PIPELINE-TRAP 证据；估算工作量与峰值不足以支持收敛时返回待核验项。
- 用 `max(字节/带宽, FLOP/算力)` 的理论耗时与 headroom 支持 Tiling 建模和目标差距分析；缺 FLOP 时只报告访存下限。headroom 是模型空间，不能直接当作候选可节省的端到端耗时；冻结目标时延仍从 `performance-targets.json` 读取，到达硬件上限不等于达到用户目标。

## 方案

最多三套，按预期收益与风险排序。逐 case 将目标差额与候选可移除的非重叠关键路径耗时、预计新增的搬运/同步/负载失衡成本对照；不能可靠定量时给出证据等级与决定排序的未知量，先定义一次有结果门槛的有界验证。增量收益不足以独自达标的方案仍可保留，但须写明剩余差额。逐 case 根据效率证据约束候选：

| 到顶结论 | 可实施方向 |
|---|---|
| `NEAR-BANDWIDTH-CEILING`：memory-bound 且 MBU ≥ 90% | 只保留能减少字节量且符合公开契约的方案，不以纯流水/tiling 重排充数 |
| `NEAR-COMPUTE-CEILING`：compute-bound 且 MFU ≥ 70% | 只保留能减少 FLOP 且符合公开契约的方案 |
| `MEMORY-CEILING` / PIPELINE-TRAP：MTE2 利用率 ≥ 90%，wall-MBU 低 | 减字节，或有证据证明不重读权重的重叠方案（如独立权重片的 N 分块）；需要重读权重的重叠会增加搬运量，不能作为有效方案充数 |

其余情形按 headroom 与 bound 提出定向方案。减字节/减 FLOP 不能放宽已冻结 dtype、格式或公开语义。零方案只是本轮没有可冻结的实施契约：报告须逐项列出仍可能填补目标差额的增量/结构性方向、证据化不可行项与足以改变判断的未知量，并明确写 `convergence_eligible: yes|no`。只有方向均有不可行证据、关键未知已定界时才写 `yes`；收益、同步安全或完整 case 关键路径仍未知时写 `no`，给出下一轮有界验证和尚未实施方向的放行/放弃阈值；该阈值不得回溯淘汰已产出候选。缩小负载的仿真结果不得在未证明可比性的情况下外推到完整目标 case。主 Agent 仍须按编排契约独立复核 `ceiling_bound` 或其他收敛条件，不得把零方案或 `convergence_eligible: no` 当作退出许可。

不同模板、运行时分支互斥的路径应融合进一个方案；同一分支的互斥策略才拆为并列方案。每套方案必须包含：

- 稳定 `scheme_id`、目标瓶颈、Tiling/流水/模板路径、适用分支和逐 case 覆盖；
- 支撑知识卡：`kb_cards` 列出方案引用的 doc-id（使用搜索结果的 Concept `path`）、绝对 `local_path`、`card_sha256` 及各自用途（方向约束/优化方法/反模式），与方案正文及检索 receipt 可对照；只登记实际阅读全文的卡片，不把 Concept ID 当作相对文件名。`KB_ROOT` 缺失时写 `kb_unavailable`，有效零命中则记录知识缺口，不虚构卡片；
- 可证伪的收益假设与复盘条件，写成一行：`预测 <指标+比较方向+数值+case 集>；若观测到 <一次具体观测> 则记录 prediction_missed，供后续方案复盘`；预测未命中不改变已实施候选的门禁与终选资格；
- 模板/VF readiness、目标构建契约、最小预检与 API 证据；
- 上一轮 deferred/落选手段的处置；区分策略机制被证伪、具体实现成本、正确性缺陷和采集无效，一次实现退化不能单独否定整类方向。

同步生成 `implementation-contract-<scheme_id>.json`：

```json
{
  "schema_version": 3,
  "scheme_id": "stable-id",
  "implementation_mode": "exact",
  "substitution_policy": "forbidden",
  "target_socs": ["Ascend950"],
  "safety": {
    "public_contract": "unchanged",
    "non_target_socs": "unchanged"
  },
  "required_features": [{"id": "feature-id", "description": "mechanically verifiable"}],
  "expected_effect": {"metric": "effective-case geomean speedup", "comparison": "ge", "value": 1.10, "unit": "x", "cases": ["case-id"]},
  "expectations": {"vf": false, "casttrait": false},
  "case_ids": []
}
```

正文措施与 `required_features` 必须双向对应；“需要探针”表示先验证再实施，不表示 optional 或允许换路线。可选键 `expected_effect` 由正文预测派生，`cases` 是 `case_ids` 的子集；它只是事先声明的落盘记录，供下一轮处置 deferred/落选手段时对照，不参与候选选择，不构成候选最低收益门槛，也不改变其余键的要求。不得新增 `abandon_if`；历史契约中的该字段只能按 `prediction_missed` 复盘，不得作为已实施候选的淘汰条件。standard 的整体 target 未达只影响循环控制与最终达标状态，不改变 eligible 候选的终选资格。

## 输出与完成

- `roundN/analysis.md`（《性能分析报告》）：一份自洽报告，依次包含输入身份、逐 case 证据（含 `MBU/MFU/mte2_util/cost_bound/ceiling_us/headroom_us/headroom_pct/verdict` 及所用峰值口径）、MC²/特殊算子路由、族/模板选路、检查点处置、知识卡引用（`kb_cards` 汇总或 `kb_unavailable`）、方案、覆盖表和风险；
- `roundN/implementation-contract-<scheme_id>.json`：每方案一份。
- `roundN/source-isolation-<scheme_id>.json`：每方案一份，完整 baseline 源码/构建 SHA、最小可修改行范围和新增/复制文件映射。主 Agent 审阅并登记 SHA 后派发实施。

分析报告只有这一份，不拆成三段保存点或重复的方案报告。

所有文件先写临时文件，校验 case 全覆盖、引用存在、契约映射完整后原子替换。完成时只返回状态、产物绝对路径和未决证据，不在对话里复制报告。
