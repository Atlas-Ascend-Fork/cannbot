# 诊断分析执行参考

本阶段先按 `ops-perf-acceptance-criteria` 的性能采集参考采集或复用当前基线；下面的只读边界约束采集完成后的分析推导。修改源码或负载的诊断探针只在采集阶段的专用副本进行，冻结基线不变；未改源码的流水图可沿用基线身份。分析只消费已登记的有效证据。每个 case 同时读取 `performance-targets.json`，报告目标时延、差距和达标状态；不得用停止轮次代替性能目标。

简单 profile 的聚合指标或 Duration 不足以支撑瓶颈分析时，必须在基线采集阶段按 `ops-profiling-report` 补齐流水图，定位依赖、重叠、气泡和同步等待；已有同身份有效图可复用。由报告入口选择可用的流水采集能力；不可用时记录缺口，聚合利用率不是流水图，图也不替代稳态计时验收。缺少必要证据时返回主 Agent 按采集协议补齐，不在只读分析中自行重采。

## 职责

消费主 Agent 已冻结的用例、当前基线源码和本阶段一次统一 profiling，解释每个 case 的瓶颈并给出可直接实施的方案。不得重选 case、重采性能、编译 demo 或修改源码。

开始前读取派发输入视图、本阶段 Skill 和本角色输入；需要逐 case 选择记录等详细字段时再按路径读取 `RUN_MANIFEST`。按验证类型读取共享参考。输入不完整或身份不匹配时退回主 Agent，不猜测映射。

性能分析固定按以下顺序执行：输入与证据校验 → 逐 case bound/瓶颈分析 → 特殊算子路由 → 族/模板与 API 核验 → 方案和实施契约。这里规定证据与交付的前置关系；本阶段 Skill「Agent 的参考输入」列出的各项资料概览、索引、检索方法和适用范围全部作为输入，各项之间没有固定优先顺序，按当前问题和证据自主选择并深读；平台、API、同步和特殊路线检查按实际源码及候选机制触发，不因参考资料的选择而豁免。

## 输入

- `CODE_DIR`、`RUN_MANIFEST`、`WORKFLOW_STATE`、`ROUND`；
- `performance-tuning-cases.csv`；
- `analysis/roundN/perf/baseline/performance.csv`、`collection.json`/诊断采集收据、`profile-report.json` 与专项报告；
- 上一轮 `analysis.md`、`selection.json`（round1 为 absent）；
- `source-compatibility.md`：公开契约面、工程支持 SoC、目标工程代际隔离风格和证据；
- `workspace-manifest.json`：仓库/基线 commit/worktree/构建入口/harness 身份与脏改动处置记录；
- 本技能内置[板卡事实库](kb/README.md)及目标册索引（[910](kb/book-910/INDEX.md) / [950](kb/book-950/INDEX.md)）；
- 信封 `KB_ROOT`（外部 cannbot-knowledge 仓根，包含 `governance/` 与 `knowledge/`；absent 时仍使用内置板卡事实库）；
- 信封 `KB_ROOT` 下的 `distill/book`（cann-refinery 的 book 只读软链；用 `demand/`、`guides/`、`claims/`、`obs/`；absent 时记录 `distill_unavailable`）；
- 目标 SocVersion 与可验证本地 SDK/参考路径；
- 本阶段 Skill 列出的各项参考概览：用途、覆盖关键词、真实入口/索引、目标适用范围；缺失来源的原因同样随输入提供。

按共享 [performance-collection.md](../../ops-perf-acceptance-criteria/references/performance-collection.md) 校验协议、身份和覆盖。使用注册 case/variant 身份与明确选中的 summary 收据核对目标。工具内部 replay 不算独立采集，不得把采样 Group 当完整物理核覆盖。MC²/多 rank 缺适配器时 pending，不套用 application 协议。

## 分析标准

1. 逐 case 记录计算模式、dtype/shape/attrs、bound（VEC/MEM/SCALAR）、关键指标、`total_us` 和证据路径。每个冻结 case 必须恰好出现。按下文“效率与理论上限”计算逐 case 量化证据。多阶段融合算子若聚合指标不足以归因，优先用覆盖目标计算路径的有效流水图定位阶段依赖、掩盖和同步等待，不再叠加消融；工具或调用路径无法产出有效图时记录缺口，再消费已登记的上板阶段隔离证据，其端到端耗时差只表示边际影响，不相加推算可节省耗时。
2. 按 case 计算模式判定算子族。选用 `ascendc-performance-best-practices` 时，按精确 `TARGET_SOCS` 和算子族查询目标适用的说明、模板与参考代码；实际采用的路线须核验其平台和接口约束。算子名不能锁定单一族；Broadcast、Elementwise、Reduction 分别按实际轴和计算结构判定，数据依赖读地址走 Gather，数据依赖写地址走 Scatter。
3. **知识检索。** 资料不是每轮必读，按当前瓶颈和证据选择：
   - 内置板卡事实库：按目标册 `INDEX.md` 检索条目，核对 `BOARD:`、版本和分层；引用按 [GOVERNANCE.md](kb/GOVERNANCE.md#1-引用)。
   - 精炼区：`$KB_ROOT/distill/book` 是 cann-refinery 的 `book/` 只读软链；用 `demand/` 和 `guides/` 找问题与路线，`claims/` 作为知识索引读卡，`obs/` 查证据；引用卡 id、路径和 sha256；不可用时记 `distill_unavailable`。
   - `knowledge-query` 用于补充缺口：加载其 Skill 与 `references/cli.md`，以 `--knowledge-root "$KB_ROOT"` 固定知识仓，按 `TARGET_SOCS` 确认平台后围绕瓶颈执行 `search`，按 `local_path` 阅读完整正文；方案 `kb_cards` 列出方案引用的 doc-id（Concept `path`）、绝对 `local_path` 和 `card_sha256`，并保存 receipt。检索结论是假设级证据，不替代本文件的分析标准和共享 Skill 路由；零命中记知识缺口，不可用时记 `kb_unavailable`，不虚构卡片。
4. **理论建模估算。** 在搜索、比较方案时评估建模价值；粗粒度 roofline 不足以解释差距或需比较融合、驻留、tiling、分核收益时，按本阶段 Skill 的[参考输入](../SKILL.md#agent-的参考输入)选择工具，尽早尝试最小可用模型或复用已有模型。比较覆盖相同完整 case、目标硬件的关键路径与新增成本，核对成本来源、适用范围和已有实测偏差；未知成本不按零值排名，未经核对的预测仅作探索性假设，单点拟合不证明新结构预测准确。模型无法可靠区分方案、现有证据已足够或建模价值有限时，说明依据并结合源码、profiling 和按原协议取得的实测继续，不为校准反复采集。模型运行成功或预测精度不作为实施前置条件，也不凭单一预测淘汰合法方向；最终收益由实测判定。模型下界不得改写性能目标或填补实测缺口，BELOW_FLOOR 先核对口径。
5. Agent 选用 `ascendc-perf-optimize` 的 4 步流程时，按该方法的适用条件执行：Step 1 Tiling 理论建模必选，产出理想 tiling data 作为后续修正对照，并结合标准 1 的 `compute_efficiency` 输出给出理论最优耗时（roofline 上限：`max(字节/带宽, FLOP/算力)`）与距该上限的可达 headroom，作为"值不值得调、最多能到哪"的定量上界；Step 2 仅命中 MC²/通信类算子时执行，按 `ascendc-mc2-best-practice` 的 `references/shared/profiling_mc2.md` 口径判定主导流水与通信隐藏率，只消费基线采集阶段已登记的 TilingData 与隔离测试证据（T_comm/T_compute/R 值），缺失时退回主 Agent 按协议补采，不得修改源码自行补采；Step 3 仅在跨核同步或共享目标写入时分析核间依赖、同步和负载；Step 4 单核流水 bound 诊断结论并入逐 case bound 证据。各步产出的 tiling 修正建议和优化策略直接映射为方案与实施契约 required features，不因流程推导重选 case 或重采性能。
6. 只有族级终选仍使用 SIMT 时才读取 SIMT 指南。不得因为原源码有 `__simt_vf__` 就跳过族级选路。
7. 模板按证据分类：构建契约一致且已有编译证据才是“可直接使用”；上下文/契约待补为“集成边界待验证”；只有说明则是“设计参考”。不得用概念伪代码替代已找到的模板骨架。
8. DAV_3510 的向量、归约、寄存器重排、Cast/Pack 热点查询 `reference/common/arch35/regbase/catalog.json`。记录 catalog ID、match_hints、readiness、目标工程的编译/精度/性能验证方案、`example_build_contract` 和目标差异；查询不等于选中。
9. 融合算子中的每个内嵌 MM 独立命中 MatMul 族并记录 `mm_route`、shape、布局和证据。DAV_3510 按 Blaze → 保留 Cube MMAD 的低阶流水重建 → 高阶 MatMul API 数据流依次评估；AIV 替换须有独立、可比较的同 case 实测证据。低 MAC 利用率、较小 K 或外层融合名称都不足以直接选择 AIV。
10. 仅当目标单元已确认是 AIV 向量计算链、数据已 UB 驻留且 VEC 耗时主导时，才评估 `register-resident-vector-chain`；该条目不能用于替换内嵌 MM。
11. DAV_3510 目标的 RoPE/rotary 必查 `paired-segment-rotate`。DAV_3510 量化逐 case 给出 `quant_vf_route`：`shared-exponent-pack`、`two-pass-amax-cast` 或有证据的 `no_matching_vf_example`。
12. 具体 AscendC API 参数必须用 `ascendc-docs-search` 和目标 SDK 验证，未经验证的参数不得进入方案。
13. 静态检查点处于 `ready` 时，把适用 finding 作为 profiling 假设直接并入分析，逐条标 `adopted`、`refuted` 或 `deferred`；不再生成独立代码检视阶段或报告。
14. 从 manifest 读取 `TARGET_SOCS`，不得把当前设备或 A5 工作基线扩大成全代际结论。A2/A3 共用同一套 arch22 实现，验证结果可互换，方案无需按二者拆分。方案不得修改公开 API、原约束或支持 dtype。按 `$WORKFLOW_ROOT/workflows/references/source-isolation.md` 追踪共享实现和模板使用者，将复制后独立路由、非目标代际及同代未涉及分支的原 fallback 作为 required feature；生成实施前冻结的文件/行范围，不能仅以架构目录命名证明隔离。

## 效率与理论上限

逐 case 调用 `ops-profiling-report/scripts/compute_efficiency.py --duration-us ... --bytes ... --flops ... --peak-bw ... --peak-flops ... --json`，保存真实命令、工作量来源、当前 SoC 峰值依据和原始 JSON。带宽单位 bytes/s、算力 FLOP/s；当前实现成本与内在最小成本分别计算。没有可靠峰值就省略该参数，不能写默认值或填零。

记录 `MBU/MFU/cost_bound/ceiling_us/headroom_us/verdict`。缺项保持 null；缺 FLOP/算力时只能给访存下限，不能建立完整 ceiling 或宣称收敛。真实零与未知分开。Pipeline 和 PMU 解释委托外部专项 Skill，不对不兼容的 CSV 套旧解析参数。headroom 是模型空间，不等于可直接节省的端到端耗时；冻结目标仍从 `performance-targets.json` 读取。

## 方案

每轮选定一个就绪方案。方案收益排序以逐 case 收敛账本（`inspect --stage <本轮分析键>` 的 `case_convergence.unresolved`）中**未达标 case** 为主键，geomean 等聚合指标只作防退化约束；拟以 `case-converge` 登记的逐 case verdict 须携带等于当前参考实现的 `reference_identity`，参考实现晋升后旧 verdict 失效需重推导。先比较可行方向的预期收益、风险和证据，再为最有依据的方向生成实施契约；其他方向留在分析报告的后续决策中。逐 case 将目标差额与候选可移除的非重叠关键路径耗时、预计新增的搬运/同步/负载失衡成本对照；不能可靠定量时给出证据等级与决定排序的未知量，先定义一次有结果门槛的有界验证。增量收益不足以独自达标的方案仍可保留，但须写明剩余差额。逐 case 根据效率证据约束候选：

| 到顶结论 | 可实施方向 |
|---|---|
| `NEAR-BANDWIDTH-CEILING`：memory-bound 且 MBU ≥ 90% | 只保留能减少字节量且符合公开契约的方案，不以纯流水/tiling 重排充数 |
| `NEAR-COMPUTE-CEILING`：compute-bound 且 MFU ≥ 70% | 只保留能减少 FLOP 且符合公开契约的方案 |
| `MEMORY-CEILING` / PIPELINE-TRAP：MTE2 利用率 ≥ 90%，wall-MBU 低 | 减字节，或有证据证明不重读权重的重叠方案（如独立权重片的 N 分块）；需要重读权重的重叠会增加搬运量，不能作为有效方案充数 |

其余情形按 headroom 与 bound 提出定向方案。减字节/减 FLOP 不能放宽已冻结 dtype、格式或公开语义。零方案只是本轮没有可冻结的实施契约：报告须逐项列出仍可能填补目标差额的增量/结构性方向、证据化不可行项与足以改变判断的未知量，并明确写 `convergence_eligible: yes|no`。只有方向均有不可行证据、关键未知已定界时才写 `yes`；收益、同步安全或完整 case 关键路径仍未知时写 `no`，给出下一轮有界验证和尚未实施方向的放行/放弃阈值；该阈值不得回溯淘汰已产出候选。缩小负载的仿真结果不得在未证明可比性的情况下外推到完整目标 case。主 Agent 仍须按编排契约独立复核 `ceiling_bound` 或其他收敛条件，不得把零方案或 `convergence_eligible: no` 当作退出许可。

不同模板、运行时分支互斥的路径应融合进一个方案；同一分支的互斥策略每轮选择一种。相互依赖的架构修改写入同一契约，避免单独评估不可用的中间状态。方案必须包含：

- 稳定 `scheme_id`、目标瓶颈、Tiling/流水/模板路径、适用分支和逐 case 覆盖；
- 采用知识卡时，`kb_cards` 列出方案引用的 doc-id（使用搜索结果的 Concept `path`）、绝对 `local_path`、`card_sha256` 及各自用途（方向约束/优化方法/反模式），与方案正文及检索 receipt 可对照；只登记实际阅读全文的卡片，不把 Concept ID 当作相对文件名。未采用知识卡时 `kb_cards` 留空，不要求为生成方案而补齐卡片数量；`KB_ROOT` 缺失时写 `kb_unavailable`，有效零命中则记录知识缺口，不虚构卡片；
- 可证伪的收益假设与复盘条件，写成一行：`预测 <指标+比较方向+数值+case 集>；若观测到 <一次具体观测> 则记录 prediction_missed，供后续方案复盘`；预测未命中不改变已实施候选的门禁与终选资格；
- 模板/VF readiness、目标构建契约、最小预检与 API 证据；
- 上一轮 deferred/落选手段的处置；区分策略机制被证伪、具体实现成本、正确性缺陷和采集无效，一次实现退化不能单独否定整类方向。

同步生成 `implementation-contract-<scheme_id>.json`：

启用 search_policy 时，按 [搜索决策契约](../../ops-perf-acceptance-criteria/references/architecture-search.md) 添加 `search` 元信息：真实父实现、冻结用例与基线性能、触发证据、机制验收条件及已接受依赖。读取前轮结果与重试条件；需要重规划时先完成有证据的架构复盘，由主 Agent 登记，再冻结本轮方案。纯耗时参考不能被解释为已观察到的参考架构。

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

## 搜索候选交接

使用候选前沿时，本阶段负责候选空间、模型预筛和本轮方案选择；字段与验收要求见 [搜索决策](../../ops-perf-acceptance-criteria/references/architecture-search.md#候选前沿与搜索执行frontier)。读取 `inspect.search` 的有效历史、当前参考和重试条件，按上文方案标准选定一个就绪方案。

### 候选空间与知识适配

`knowledge-query`、`ascendc-performance-best-practices`、`ascendc-perf-optimize` 和 `ops-opmodel-toolkit` 都是候选方向来源。按上文检索与适用范围规则，在本轮已有分析中，把各来源得出的有效方向直接写入 `candidate-space` 的轴、值、binding、constraints 和预期增益；同一方案合并来源证据，未选方向保留供后续搜索，排除或暂缓的原因记入原分析报告。不另开候选汇总轮次，不要求每个来源每轮都产出方案；输入身份、平台与模型版本等适用条件未变时复用已核验的资料和结果。

结构、DAG 或映射备选可用离散 `route` 轴表达，`contract_feature` binding 对应实施契约中的具体特征；互斥路线作为同一轴的不同值，避免无意义的交叉组合。可选 `axis.trigger` 按轴值的字符串形式附来源引用，例如：

```json
{
  "name": "route",
  "values": ["pipeline", "resident_dag"],
  "binding": {"kind": "contract_feature", "field": "dataflow_route"},
  "trigger": {
    "pipeline": [{"path": "/abs/analysis/round1/template-analysis.md", "sha256": "<sha256>"}],
    "resident_dag": [{"path": "/abs/analysis/round1/theory/dag-result.json", "sha256": "<sha256>"}]
  }
}
```

生成器将公共 `space.trigger` / `--trigger` 诊断证据与所选轴值的来源去重合并到节点 `trigger`；同一值可附多个来源。引用使用实际读取文件的绝对路径和 SHA，沿原保存点核验，包括剪枝后未进入前沿的方向。公共知识约束可继续用 `search_kb_space.py` 附到所有候选；仅支持某个方案的证据放在该值的 `axis.trigger`。适配器只核验并传递引用，不从检索关键词推断轴值或填充芯片参数：

```bash
python3 "$WORKFLOW_SCRIPTS/search_kb_space.py" \
  --space /abs/analysis/round1/axes.json \
  --knowledge /abs/analysis/round1/knowledge-decision.json \
  --manifest /abs/run/manifest.json \
  --out /abs/analysis/round1/candidate-space.json
```

`knowledge-decision.json` 引用本轮已采用的知识，示例中的平台与路径须替换为实际值：

```json
{
  "target_socs": ["Ascend950PR"],
  "kb_cards": [
    {
      "path": "<knowledge-query Concept path>",
      "local_path": "/abs/knowledge/full-card.md",
      "card_sha256": "<sha256>",
      "decision": "adopted",
      "purpose": "方向约束"
    }
  ],
  "evidence": [
    {"path": "/abs/ops-perf-analysis/references/kb/book-950/entries/entry.md", "sha256": "<sha256>"}
  ],
  "receipts": [
    {"path": "/abs/analysis/round1/query-receipt.json", "sha256": "<sha256>"}
  ]
}
```

`target_socs` 与冻结 manifest 一致；`kb_cards` 沿用上文外部卡字段，外部卡附原 Query 回执；内置条目通过 `evidence` 引用，沿用原编号与治理规则。适配器复用现有 SHA 引用验证器，传递证据及输入快照。无知识可用时这些引用列表可为空，继续记录 `kb_unavailable` 或 gap，候选轴仍须有分析依据。知识检索、索引和沉淀继续由原知识体系负责。

### 生成、预筛与选定

```bash
python3 "$WORKFLOW_SCRIPTS/search_round.py" \
  --state /abs/run/workflow-state.json \
  --space /abs/analysis/round1/candidate-space.json \
  --parent /abs/analysis/round1/parent-identity.json \
  --trigger /abs/analysis/round1/diagnosis.json \
  --round round1 --best-us 100 \
  --history-state /abs/run/workflow-state.json --soc Ascend950 \
  --combo-stage auto \
  --out-dir /abs/analysis/round1/search --dry-run
```

`--best-us` 使用当前参考的真实耗时，100 仅为示例。`--parent` 可指向目录/源文件，Git 模式传入含 `{commit, tree}` 的 JSON；须与本轮实施契约的父身份一致。参考只采用工作流已验收的实现。

`--history-state` 从已有工作流事件和可重算的 effect summary 恢复原搜索的历史先验与轴值代理排序；可重复指定先前 run 的 state，`--soc` 替换为本轮实际平台。`acquisition.json` 保留排序与原合同/效果引用，作为选方案的输入；无实测历史时退回探索先验。历史状态和证据必须仍有效，失败、失效或已重开的记录不作为实测样本。它不写独立历史库，不把 case 数当成重复采样数。可用 `--top-k` 限制候选预算，但必须保留前沿最小数量、类型覆盖与 open 节点；约束不满足则保留原前沿并记录原因。

组合探索复用原 PR 的单轴 → 双轴 → 多轴顺序：`--combo-stage auto` 按 `roundN`/`gen.roundN` 分别取 0、1、2（第三轮及以后）；也可显式指定 `0|1|2`。候选数量不足时记录补充节点。使用同一空间的首个轴值作为 `base_factors`；跨轮比较须保留各轮真实父实现与用例证据。多轮仍由既有工作流派发、验收和停止，不因组合尚未完成延长用户预算。

生成的 `scheme_id` 带轮次前缀，同一参数组合在后续轮次是新的决策；已登记的旧 ID 保持不变。`--state` 从原工作流读取已接受且未被重新打开的依赖，`candidate-space.depends_on` 只引用这些 ID；独立 `search_candidates.py` 入口使用同一参数。

`--dry-run` 展开候选并执行所配置的模型预筛，不构建或实测候选。OpModel 提出的新 DAG、映射或调度方案须在展开前按上述规则进入空间，直接复用已有模型结果，不为登记重复建模。之后的 `search_prefilter.py` / `opmodel_rank.py` 只评估、映射和排序已有节点，不负责发现新方向。按上文理论建模的适用范围使用 L0/L1，`l0_roofline.py` 适配既有理论性能引擎；组合阶段也在本阶段确定。记录实际命令、生成参数、模型输入与结果，保持 unsupported 或缺证状态。

L1 模型排序默认只提供建议。启用 `--prefilter-top-k` 前，复用 OpModel 的设备排序验证：同算子与模型在至少两个 shape（含一个 large-K、非方形或 skinny 压力场景）上，Spearman 显著为正且 top-3 重合至少 2/3。analysis 核对报告对应当前模型版本、参数映射、平台和候选适用域，通过后以 `--prefilter-validation <已有校准报告>` 传入。脚本检查报告存在并将 SHA 纳入原 L1 证据链；报告内容和适用性仍由 analysis 复核，原始实测依赖沿已有保存点登记。未附报告时保留全部候选并记录原因；未映射及 open 候选始终保留。

用 `workflow_state.py search-frontier --state <state.json> --frontier <frontier.json>` 消费既有事件并排序。选定方案后，把生成的 `candidate-frontier.json` 以 `candidate-frontier-<scheme_id>.json` 名称交接，并交付唯一实施契约及其冻结 scope；候选空间、父身份、trigger 和实际生成参数作为分析依据保留。implementation 直接消费已登记的 frontier。使用 holdout 时一并交接独立冻结的用例集，集合约束见共享搜索契约。

frontier 中其余节点保留为后续分析输入，本轮只派发选定方案。候选的构建、实测及选择记录由 implementation 完成；主 Agent 按原分析保存点登记 frontier 与依赖产物。

下一轮读取上一轮归因与落选方向的原始证据：实现未充分兑现收益时先定位额外开销并给出有界修正；组合退化而单项有效时拆分复测；统计未决时按冻结策略补证；只有机制证据确实反驳假设才放弃相应方向。同机制再试沿用 `search.retry`，记录新证据与条件变化。关闭搜索前，在现有分析报告核对候选轴与组合的实测/排除依据；生成过或被预算剪枝不算测过，未测且未有证据排除的方向保留为未决，不宣称空间耗尽。

用已有 `workflow_state.py search-frontier --state <state> --frontier <frontier> --contract <本轮契约> --out <覆盖报告>` 取得 `axis_coverage`。生成器保存剪枝前 `candidate_space` 的 SHA；统计仅采用同父实现、负载、平台、backend、机制和空间定义下，已验收且未重开的 `measured` 结果。候选生成、预算剪枝、编译/精度失败均不计作已测。旧前沿缺少空间引用时返回 unavailable，须在分析报告核对原空间，不能解释成全覆盖。

将 `untested` 逐项复核为待尝试方向或有证据的排除项，随覆盖报告交给主 Agent，沿用现有 `structural-direction` 台账登记 `untested_directions` 返回的 ID。ID 绑定父实现、负载、平台、机制、空间定义与轴值；排除说明须解释对应范围内为何不可行，不能仅凭一次慢实现排除整个轴值。宣布该空间 no-go 前，在上述 `search-frontier` 命令加 `--no-go`；未测且缺少有效排除依据时退出码为 2。轴值全测过也不证明组合耗尽，工具不自动关闭方向。预算耗尽按原工作流退出/驻留，不为补齐覆盖增加轮次。

`--no-go` 只审计覆盖，不要求仍有可选候选；缺排除依据时也输出 `axis_coverage`，指定 `--out` 可保存待处理项。分析阶段无就绪方案时，仍声明非空候选轴与明确 `mechanism`，交付 `candidate-frontier-audit.json`：保留 `schema_version: 1`、`round`、`parent`、`candidate_space`，增加冻结负载的 `workload: {path, sha256}`，令 `nodes: []`。平台和 backend 沿用 manifest；不创建实施契约。主 Agent 用原 `roundN.analysis` 保存点登记该前沿与分析证据，之后可省略 `--contract` 执行同一审计，并按原 `no_candidate` 流程保留基线。

## 回流所需过程数据

分析报告保留：逐 case 瓶颈与 bound、候选方案与预期效果、采用的精炼区卡/路径与排除理由、验证计划和知识缺口；实施契约保留 `required_features` 和 `expected_effect`。后处理直接使用这些文件整理回流材料，不另建知识文件。

## 输出与完成

- `analysis/roundN/analysis.md`（《性能分析报告》，**由诊断分析阶段产出**）：一份自洽报告，报告头标注"诊断分析阶段（ops-perf-analysis）roundN"与当轮输入基线身份，依次包含：
  - **分析流程**：基线复用/采集 → 逐 case bound/瓶颈分析 → 特殊算子路由 → 族/模板与 API 核验 → 方案和实施契约，每步引用实际使用的输入、工具与采集证据；
  - 输入身份与逐 case 当前性能数据（含来源 CSV/采集批次的 `total_us` 等实测值）；
  - 逐 case 瓶颈分析、该 case 采用的方案与优化手段、预期收益（收益区间或 unknown、目标差额贡献、证据可信度、处置）及 `MBU/MFU/mte2_util/cost_bound/ceiling_us/headroom_us/headroom_pct/verdict` 与所用峰值口径；
  - 理论建模的使用依据、结论可信度及其对方案与实施契约的影响；未采用时说明替代证据。实际运行或复用时引用 `analysis/roundN/theory/` 中的模型输入、报告、Skill/wheel 版本、硬件/成本来源及搜索/trace 证据，区分理论上限、调度合法性与性能预测；
  - 逐 case 前后对比：相对本轮开始前基线（round1 为冻结基线，roundN>1 为上一轮终选基线）的前后耗时、变化幅度和所用优化手段；无方案 case 显式标注 no-op 与原因；
  - MC²/特殊算子路由、族/模板选路、检查点处置、内置板卡事实库检索与条目引用（含分层、适用范围、采用/排除理由或缺口）、精炼区卡引用（`[refinery:<id>@<label|unlabeled>]` 汇总或 `distill_unavailable`）、外部知识卡引用（`kb_cards` 汇总或 `kb_unavailable`）、覆盖表和风险；
- `analysis/roundN/implementation-contract-<scheme_id>.json`：每方案一份。
- `analysis/roundN/source-isolation-<scheme_id>.json`：每方案一份，完整 baseline 源码/构建 SHA、最小可修改行范围和新增/复制文件映射。主 Agent 审阅并登记 SHA 后派发实施。

分析报告只有这一份，不拆成三段保存点或重复的方案报告。

所有文件先写临时文件，校验 case 全覆盖、引用存在、契约映射完整后原子替换。完成时只返回状态、产物绝对路径和未决证据，不在对话里复制报告。
