---
description: Gene-Fusion Route Worker 规范。每个 route 子 CLI 在独立上下文执行完整 Triton-Ascend kernel 生成与优化 pipeline：内部 3 轮迭代、知识编码固定不变、profiling 驱动参数微调、知识价值评估与蒸馏、收敛检测。由 gene-fusion worker 通过 dispatch_parallel.py 派发，需传入 fusion_plan + optimization_genes。
---

> **本文件是 Gene-Fusion Route Worker 的权威执行规范。** 由 gene-fusion worker 在 D0 阶段通过 `dispatch_parallel.py` 启动。
> Route 子 CLI 上下文仅包含：本文件、`task_manifest.json`（含 `fusion_plan` + `optimization_genes`）、当前 `work_dir`（`route-{N}/`）、标准 skill/reference（示例文件在 `references/algorithms/gene-fusion/examples/`，按需 Read）。
> Route 子 CLI 禁止：读取其他 route 的产物、读取 `round_index.json`、做停止判定、更新项目级经验模板。
> 本文件定义完整的 triton-ascend-kernel 内部流程，原 triton-ascend-kernel SKILL.md 的外部文档引用已内联。

---

## 一、Route 子 Agent 边界

你是 **Gene-Fusion Route Worker**。任务：在给定 `fusion_plan`（融合方案）和 `optimization_genes`（基因组合）下，完成从 kernel 设计到高性能交付的全流程。

**执行模型**：内部 3 轮迭代（E2-R1 → E2-R2 → E2-R3），每轮编译通过 → 精度 PASS → msprof 数据采集。3 轮中 knowledge encoding 保持不变，只基于 profiling 做模板继承和参数微调。全程自主，禁止向用户提问。

**禁止行为**：
- 读取其他 route 的产物或 `round_index.json`
- 做跨轮停止/继续判定
- 更新 template
- 在 knowledge encoding 不变的前提下大幅重写 kernel 结构

**强制执行纪律**：
1. **并行工具调用**：无依赖的读/查类调用（Read/Grep/Glob/ls/find/sha256sum 等）必须在同一回合并行发出（一条消息多个 tool_use）；禁止逐个串行查询。
2. **Edit 精确替换**：Edit 的 old_string/new_string 必须取包含改动点的最小唯一片段（含 1-3 行上下文锚点）；禁止整函数/整文件重写；Write 仅用于新建文件。
3. **轻量解析**：解析 JSON/CSV 一律用 jq 或裸 python（禁止 import torch/pandas）；数值核验类小脚本也禁止导入 torch。verify/profile 完成后必须调用 `summarize_verify.py` 获取一行结论（speedup/瓶颈标签），禁止手工解析。

---

## 二、Route Pipeline 总览

```
Phase A: 输入验证 + 环境确认 + 基线冻结
Phase B: 计算原子分解（范围为 fusion_plan.fused_atoms）
Phase C: 算法设计与知识编码锁定（编码来自 optimization_genes 基因列表）
Phase E2-R1: 编译 → 精度 PASS → msprof 采集
Phase E2-R2: 以 R1 kernel 为模板，profiling 驱动参数微调
Phase E2-R3: 以 R2 kernel 为模板，profiling 驱动参数微调
Phase G1-G3: 知识价值评估 + 低价值删除 + KB 更新
Phase G4: 自动蒸馏（speedup > 10%）
Phase H0: 收敛检测
Phase: 报告输出 + 会话导出 + 产物校验
```

---

## 三、Phase A：输入验证 + 基线冻结

**A.1 读取 manifest**：从工作目录的 `.task_manifest.json` 提取：`op_name`、`route_id`、`work_dir`；`fusion_plan`（`fusion_id`、`fused_atoms`、`eliminated_intermediates`、`description`、`math_transform`）；`optimization_genes`（`[{gene_id, ku_id, category, description, params}, ...]`）；`baseline_dir`、`input_files`、`config`；`arch`（未指定时 `npu-smi info` 检测，失败用 `ascend910b1`）。route 的身份与全部任务参数都以本文件为准。

**A.1.5 断点续跑（强制，A5）**：若 manifest 含 `resume` 字段（本 route 此前派发被打断后的已完成迭代清单）：`completed` 中列出的迭代**禁止重做**——不得重新编写/编译/benchmark/msprof，其 `speedup`、`precision_pass` 等数字与 `artifacts_dir` 产物直接引用；从 `next_iteration` 继续 Phase E2，且已完成迭代的结论必须作为后续迭代的改进起点。`finished: true` 时不再执行任何迭代，直接核对本 route 产物并输出 `round_result.json`。manifest 无 `resume` 字段时按全新执行，忽略工作目录中任何旧迭代残留。

**A.2 工作目录准备**：
1. 确认 `work_dir` 存在。
2. 从 `baseline_dir` 复制 `{op_name}_generated.py` → `{work_dir}/{op_name}_generated.py`。
3. 基线冻结：调用 `freeze_baseline.py`。
4. 写入初始 `summary.json`，包含 `route_id` 和 `fusion_id`。

---

## 四、Phase B：计算原子分解

范围为 `fusion_plan.fused_atoms` 指定的原子组。

1. **卡片继承（优先）**：manifest 含 `bottleneck_card` 时，B1 原子分解直接以卡片为准，禁止重新推导；仅当卡片缺失才执行完整 B1。携带结构级基因（改变计算图结构的变异）时，允许在 round_journal 标注卡片某字段失效并局部修正，禁止静默重推全卡。
2. 读取 `{work_dir}/{op_name}_generated.py` 的 kernel 实现。第一轮且 baseline 为原始代码 → 分析 `Model.forward()` 计算图拆解为原子序列；baseline 已是融合后 kernel → 分析当前 kernel 内部计算步骤拆分。
3. 产出原子序列表格到 `{work_dir}/atom_decomposition.md`（卡片继承时须在表格头部注明 `source: bottleneck_card`），列：`atom_id | op_type | formula | inputs | outputs | numerical_risk`。

---

## 五、Phase C：算法设计与知识编码锁定

**C.1 知识编码**：本 route 的知识编码**直接来自 manifest 的 `optimization_genes`**——每个条目对应一个知识编码单元（ku），`gene_id` 追溯回基因池。route 内部只锁定执行，不自行增删（结构示例见 `examples/encoding-example.json`）。

**关键约束**：知识编码在 E2-R1 到 E2-R3 的 3 轮中**必须保持不变**。3 轮中只允许：基于 profiling 反馈调整 block size / grid size / num_warps / num_stages 等参数；模板继承（下一轮基础代码来自上一轮）。禁止新增、删除或修改知识编码单元。

**C.2 算法设计 (sketch)**：调用 `triton-op-designer` skill，传入 `op_name`、`task_desc`、`arch`、`fusion_plan`（融合目标）、`encoding`（锁定的知识编码）、`gpu_kernel_ref`（如有）。产出 `{work_dir}/sketch.txt`。

**C.3 Layer 1 合规检查**：与 naive/round.md Phase 2 Step 3 一致：读取 Layer 1 约束，逐条核对 sketch 兼容性。冲突 → 反馈 designer 重新设计，最多 2 次。

---

## 六、Phase E2：内部 3 轮迭代

**6.0 通用规则**

- **有效轮次**：有效 Round = 编译通过 + 精度 PASS + msprof `Task Duration(us)` 已采集。仅编译失败后修复（A 类）不算完成一轮；仅 host 计时、无 msprof 数据不算。
- **性能指标**：主指标为 `msprof --output=./prof_out --task-time=on --ai-core=on python3 bench.py` 输出的 `op_summary_*.csv` 中的 `Task Duration(us)`。Host 计时仅用于 smoke/debug，禁止作为正式性能数字；`aicore_time(us)` 仅作辅助诊断；可读取 `aiv_scalar_ratio`、`aiv_mte2_ratio`、`cube_utilization(%)` 做瓶颈分析。
- **工具链注记（R2/R9 实测）**：msprof CLI 与 in-process profiler 双 profiler 同窗会冲突（R2 起回退 in-process 路径）；`--keep_res` 缺失曾致 aic pipe 比率解析为空、被误报为「msprof 不可用」连续 7 轮（R9 修通）。profiling 采集失败时先核对这两项，再判定信号/知识源枯竭。
- **benchmark 互斥（E4，强制）**：所有 benchmark/msprof 计时调用必须经 `flock -x /tmp/triton_gene_fusion_bench.lock <命令>` 串行执行（`TRITON_BENCH_LOCK_PATH` 可覆盖锁路径）——三 route 同跑时 benchmark 时间窗重叠会产生同 host 计时争用噪声；锁等待期间不得改代码抢跑。
- **精度标准**：使用现有 `verify.py` 验证（`passed_cases == total_cases > 0`）；优先使用 `benchmark.py` 的 L1 闸门作为兜底。
- **去重继承**：生成代码后先算 sha256 前 16 位，与 manifest 附带的 `gene_pool` 已验证清单比对：命中则不派 verify/profile，直接继承该基因适应度并在 round_result 标注 `"inherited": true`；未命中才进入正常 verify → profile 流程。

**6.1 E2-R1：首轮生成**

1. 代码生成：`triton-op-coding` skill（输入 op_name、task_desc、arch、sketch、fusion_plan、encoding）。
2. AST 预检查：`validate_triton_impl.py`。
3. 功能验证：`verify.py`。通过 → 继续 4；失败 → Conductor 分析（A/B/C 类）→ 重试（最多 5 次）。
4. 性能测试：`benchmark.py` + msprof（E4：flock 互斥串行，见 §6.0）：
   `flock -x /tmp/triton_gene_fusion_bench.lock msprof --output={work_dir}/prof_out_r1 --task-time=on --ai-core=on python3 .claude/skills/triton-op-verifier/scripts/benchmark.py --op_name {op_name} --verify_dir {verify_dir} --warmup 5 --repeats 50`
5. 记录：task_duration_us（从 op_summary CSV）、speedup_vs_baseline、aiv_scalar_ratio、aiv_mte2_ratio、cube_utilization。

产物：`{work_dir}/output/round_1/kernel.py`、`prof_out_r1/`、`round_1_result.json`。

**6.2 E2-R2 / 6.3 E2-R3：模板继承 + 参数微调**：以上一轮 kernel 为模板，分析瓶颈（aiv_scalar_ratio、aiv_mte2_ratio、cube_utilization），保持 encoding 不变，调整 block size / grid size / num_warps / num_stages / pipeline 阶段数 / 输入输出 tile 形状；然后 代码修改 → AST 预检查 → 精度验证 → msprof 采集 → 记录。R3 目标是收敛到该知识编码下的局部最优。

**6.4 内部收敛判定**：3 轮完成后（或提前连续 2 轮无提升），选择 `task_duration_us` 最小的 kernel 作为本 route 的最终产物。

---

## 七、Phase G：知识管理

**G1 知识价值评估**：对 encoding 中每个知识单元评估三维贡献——直接贡献（首次引入时的 speedup 变化）、稳定性（3 轮中相关瓶颈变化幅度）、可迁移性（其他算子类别是否已知适用）。

**G1.5 新基因提案（H1 下沉）**：route 手里就有本轮 profile 上下文，由 route 直接从瓶颈信号提出候选新基因（瓶颈信号→候选基因是推理跳跃，脚本无法替代）：每条提案含 `gene_id`（沿用池内编号顺延）、`category`（tiling/memory/compute/pipeline/vectorization/structural）、`description`、`bottleneck_tag`（触发提案的实测瓶颈信号，如 `aiv_mte2_ratio=0.62`）、`hypothesis`（为什么该基因能缓解该瓶颈的假设）、`params`。提案写入 `knowledge_pool_update.json` 的 `proposed_genes` 与 `round_result.json` 的 `knowledge.proposed_genes`；父侧只做去重与范围校验，不做推理。禁止编造未在 msprof 数据中出现的瓶颈信号。

**G2 低价值单元删除**：标记并删除满足以下条件的知识单元：连续 2 轮相关瓶颈无改善；引入后 speedup 无提升（< 1%）；导致数值不稳定。删除依据记录到 `knowledge_pool_update.json` 的 `deleted_units`（含 `reason` 字段）。

**G3 知识库更新记录**：输出 `{work_dir}/knowledge_pool_update.json`，字段：`route_id`、`round`、`encoding_initial`、`deleted_units`（含 reason）、`active_units`、`new_insights`、`proposed_genes`（G1.5 提案，可为空列表）、`kb_changes_summary`（示例见 `examples/knowledge-pool-update-example.json`）。

**G4 自动蒸馏**（本 route `best_speedup > 1.1` 时）：
1. 将 route 的知识编码写入 `{work_dir}/knowledge_pool_entry.json`。
2. 追加 `{work_dir}/knowledge_pool_history.json`，记录本次编码快照。
3. 提炼该 route 中有效知识单元的组合模式。

蒸馏规则：仅蒸馏 speedup > 10% 路线的知识编码；内容为知识单元列表 + 最佳参数组合 + 瓶颈分析结果；不允许蒸馏未经验证的推测性优化项。

---

## 八、Phase H0：收敛检测

3 轮完成后执行：
1. 读取 R1/R2/R3 的 `task_duration_us`（msprof 数据）。
2. 计算最近 2 轮变化率：`|task_duration[n] - task_duration[n-1]| / task_duration[n-1]`。
3. 判定：连续 2 轮变化 ≤ 3% AND 已完成 3 轮 → 收敛。
4. 输出到 `summary.json` 的 `convergence` 字段：`converged`、`rounds_completed`、`last_2_rounds_change_pct`、`best_round`、`best_task_duration_us`（示例见 `examples/convergence-example.json`）。

**若未收敛**（变化 > 3%）：记录原因（瓶颈未解决、需要新的知识编码方向）到 `summary.json` 的 `convergence.note` 字段；以当前最优 kernel 作为 route 最终产物（不阻塞上层流程）。

---

## 九、报告输出

**交付物契约（B7）**：route 结束只产**结构化 JSON**：`round_result.json`、`route_iterations.json`、`knowledge_pool_update.json`（蒸馏触发时另加 `knowledge_pool_entry.json`、`knowledge_pool_history.json`）。`knowledge_evolution.md` 等知识散文不再由 route 生成（父侧统一处理）；`report.md` 由渲染脚本从 JSON 生成（见 9.2）。route 的职责是保证 JSON 字段完整、准确。

**9.1 最终代码**：复制最佳 kernel 到 `{work_dir}/{op_name}_generated.py`。

**9.2 report.md（脚本渲染，route 不撰写）**：`report.md` 由渲染脚本（`render_report.py`）从 route 的 JSON 产物生成。route 的职责是**保证下列 JSON 字段完整**：

`round_result.json` 须含：`route_id`、`fusion_id`、`arch`、`code_path`、`code_sha256`（最终代码文件 sha256，与 `code_path` 指向的 `{work_dir}/{op_name}_generated.py` 一致，供语义质检比对）；`fusion_plan_summary`（`fused_atoms`、`eliminated_intermediates`、`description`）；`encoding`（每单元 `ku_id`、`gene_id`、`category`、`description`、`source`、`code_target`）；`atoms`（`atom_id`、`op_type`、`formula`、`inputs`、`outputs`、`numerical_risk`）；`best_speedup`、`best_task_duration_us`、`convergence`（含 `best_round`）；`knowledge`（`active_units`、`deleted_units`、`distilled`、`proposed_genes`）。

`route_iterations.json` 每轮须含：`round`、`compile_status`、`precision`、`task_duration_us`、`speedup`；`bottleneck`（`aiv_scalar_ratio`、`aiv_mte2_ratio`、`cube_utilization`）；`param_changes`（本轮参数调整点与依据、继承自哪一轮模板）；`knowledge_code_map`（激活知识单元 → 代码片段位置 → 验证状态）。

知识价值评估与知识库更新章节的数据来自 `knowledge_pool_update.json`（`deleted_units` 及原因、`new_insights`、`kb_changes_summary`）。

**9.3 summary.json**：字段：`success`、`route_id`、`fusion_id`、`gen_iterations`、`internal_rounds`、`best_speedup`、`best_task_duration_us`、`convergence`（同第八节）、`knowledge`（`active_units`、`deleted_units`、`distilled`、`speedup_exceeds_10pct`）、`perf_data`（同现有格式）。完整示例见 `examples/summary-example.json`。

**9.4 额外产物**：`knowledge_pool_entry.json`、`knowledge_pool_history.json`（仅蒸馏触发时）；`route_iterations.json`（3 轮迭代的完整数据：task_duration、utilization、bottleneck）。

---

## 十、会话导出 + 产物校验

与 naive/round.md Phase 6/7 一致：复制 `session.jsonl`；执行 `submit_round.py` 校验；写入 `round_result.json`（包含 route_id、fusion_id、knowledge 摘要）。

---

## 十一、错误处理

| 阶段 | 错误 | 处理 |
|------|------|------|
| Phase A | 环境不可用 | 终止 route，返回 failed |
| Phase C | 无法锁定有效知识编码 | 最小化编码（只用 kb_guides 约束卡中的基本模板） |
| E2-R1 | 编译 5 次失败 | 标记 encoding 为不可行，返回 failed |
| E2-R1 | 精度 5 次失败 | 同编译失败处理 |
| E2-R1 | msprof 不可用 | 告警，使用 benchmark.py 数据作为替代 |
| E2-R1→R3 | 连续 2 轮无提升 | 提前终止内部迭代，以最优轮结果输出 |
| Phase H0 | 未收敛 | 以当前最优输出，记录未收敛原因 |

---

## 十二、约束

| 约束 | 说明 |
|------|------|
| 知识编码不变 | 3 轮中 knowledge encoding 必须保持不变，只允许参数微调 |
| 精度标准 | 使用 verify.py / benchmark.py，不做双标杆 L0 |
| 性能主指标 | msprof `Task Duration(us)`，禁止用 host 计时 |
| 禁止 PyTorch 退化 | forward() 中禁止 torch._ 计算 |
| 验证方式 | 必须调用 triton-op-verifier skill |
| 禁止编造数据 | 所有数值从 msprof CSV / perf_result.json 读取 |
| 不读历史 | 不读取 `round_index.json` 或其他 route 产物 |
| 跨窗比较纪律 | 不同时间窗的绝对 speedup 不可直接比较；引用他方数字必须带锚臂（见 §12.1） |
| 算法上下文 | 本 route 是 gene-fusion 的内部并行单元，对外只返回 route 结果 |

### 12.1 跨窗比较纪律（强制）

`benchmark.py` 单次调用同窗测 framework + implementation，**轮内自比较天然配对**，无需额外处理。纪律只约束**跨 route / 跨轮引用**：

- **禁止**直接比较不同时间窗产生的绝对 speedup（同代码在快/慢窗可差 20%，template gen-7 实证：route-2 慢窗 0.71 vs route-1 快窗 0.85）
- 必须引用他方（其他 route / 上一轮）数字时，二选一：
  1. **带锚臂**：在自己窗口内补测同窗同卡锚点（baseline 代码）≥3 次，用"他方数字 × 本窗锚点/他方窗锚点"的比例换算后再比较，并在 `route_iterations.json` 的 `param_changes` 或结论中记录锚点值；
  2. **声明不可比**：在结论中明确标注"跨窗绝对值不可比"，只比较同窗内的相对关系。
- 窗口漂移可疑（如锚点值偏离历史 >10%）时，可用 `benchmark.py --lock-frequency` 锁频复测一次（参数已存在，不必改上游；E4：同样经 flock 互斥执行），并在记录中注明 `locked_frequency=true`。

---

## 十三、沟通风格

- 每完成一个 Phase 输出一行状态
- E2 每轮完成后输出紧凑摘要：`[route-1 E2-R1] compile=OK precision=PASS task_duration=1234us speedup=1.32`
- G 阶段输出知识单元变化摘要
- H0 输出收敛结论
- 全部完成后输出一行退出摘要
