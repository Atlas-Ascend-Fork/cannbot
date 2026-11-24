# 推荐模型整网推理优化 · 工作流

> 本文件是 `model-recommend-infer-optimize` 插件的主编排。primary agent 收到「推荐模型整网推理优化」请求时强制 Read，并严格按条目推进。细节判定在承接 skill 与 `references/`，本文件只写编排。

## 新手 30 秒

- **这是什么**：推荐/搜索/排序/视觉编码类模型在昇腾 NPU 上的推理整网优化流程——先跑通到可复现精度的单卡基线，再按「分析 → 实施 → 双门禁 → 循环」持续收敛。
- **我该走哪条路**：
  - 只做某一专项（FA 融合 / 精度定位 / profiling）→ 直接调对应原子 skill，不进本流程。
  - 从零优化一个模型 → 条目 0 起全流程。
  - 已有基线、继续压 → 条目 5 起，进循环。
- **三步上手**：
  1. 环境自检：`npu-smi info` + `$ASCEND_HOME_PATH` + `bash GE_SESSION_DEMO/compile.sh`。
  2. 跑通样例：`cd GE_SESSION_DEMO && bash prepare.sh M001_sample && bash run.sh M001_sample && bash run.sh M001_sample --verify`。
  3. 说需求：如「优化 M001_sample 的推理性能，目标 avg ≤ X ms」。
- **导航**：门禁 → [`references/rules.md`](references/rules.md)；循环 → [`references/rules.md`](references/rules.md)；产物 → [`references/artifact-conventions.md`](references/artifact-conventions.md)；依赖 → [`references/external-dependencies.md`](references/external-dependencies.md)。

> 路径约定：`skills/<skill-name>/SKILL.md` 为各条目承接的原子 skill（源仓 cannbot-skills `community/model/`），本文件只写编排。Subagent：runner / analyzer / implementer / reviewer 对应 `agents/model-recommend-infer-*.md`。依据标注：【实测】本机执行；【框架】GE_SESSION_DEMO 与 CANN 文档/头文件；【插件】skill 与 references。

## 全局硬性约束（先于全部条目）

1. **禁止主动修改原始模型图**：不切分、删除、改写、替换原图；建议须经用户单独确认，默认只在 GE 内存图或工作副本操作。
2. **禁止修改 GE_SESSION_DEMO 框架代码**：只能通过 `run.sh` / `test.sh` 的传入参数与环境变量驱动；自定义优化以独立交付件（插件/Pass `.so`、算子 `.run`）实现；框架需求记录为「移交」。
3. **交付件完整并产出模型交付说明书**：每个自定义交付件含源码、安装包、README、开关与默认值、精度模式、验收结论、回退方式；收口产出 `docs/{model_name}/{model_name}_model_delivery_manual.md`。

## 流程总览

```text
0 环境基线与路由
  → 1 模型分析 → 2 单卡基线 → 3 并发与限核策略 → 4 精度基线门禁
  → 持续优化循环（一轮一动作，双门禁全程有效）
       L1 选动作 → L2 执行优化(条目 6-12 择一) → L3 采集 → L4 深度分析
       → L5 收益判定 → L6 终止检查 → L7 交付件同步 → 回 L1
  → 14 回归验收与基线管理（最终报告 + 动作表）
```

- 条目 5 两重身份：首轮作为循环入口产出初始 `next_actions`，此后每轮作为 L4 固定分析动作。
- 条目 6-12 不按序全跑，由 L1 从动作表择一执行；其中条目 10 是条目 11 的唯一入口。
- 条目 13（运行时诊断）不占轮次，0-14 任一环节故障时插入。
- L1-L7 细则见 [`references/rules.md`](references/rules.md)。

## 适用范围与输入格式

| 输入格式 | 执行/采集基座 | 优化约束 |
| --- | --- | --- |
| **onnx** | GE_SESSION_DEMO（`aclgrphParseONNX` + `prepare.sh`/`run.sh`/`tools/*.py`） | 不得改原始 onnx；合法手段：GE 内存图 pass、编译选项、并发/限核参数、精度开关 |
| **pytorch** | 模型脚本 + `torch_npu`（`torch_npu.profiler`） | 可改脚本（git 可回退 + 开关）；torchair 转 GE 为必选；可评估 torch.compile |
| **HuggingFace** | 同 pytorch | 同 pytorch |

- **onnx 路径为完整支持**；pytorch/HF 路径为实验性，条目 1/2/3/5 需用户提供等价脚本。
- 禁止绕过脚本直接执行二进制（破坏工作目录与缓存治理）。

## 全局约束

- **单卡执行**：`DEVICE_NUM=1`；选卡经 `GE_DEVICE_ID` / `START_DEVICE`。
- **精度验证仅串行单并发**（`THREAD_NUM=1`）；并发仅压测，不做 dump 与精度验证。
- **不做量化**；**默认保持原精度**：`FORCE_16` / `ENABLE_HF32` / `precision_mode` / `op_precision_mode` 默认关闭，启用须「用户确认 + 精度门禁」双前置。
- **HF32 属 `runtime_config` 优化项**（非精度模式），固定由限核 Stage 1 前置执行。
- **自定义算子语言按平台路由**：A2/A3 用 AscendC（msopgen）；A5 用 cannbot-dsl（当前环境不可用）。
- **硬件基准实测锚定**：算力/带宽以本机 matmul + HBM copy 实测为准，供 bound 与 Roofline。
- **所有优化可开关、可回退**；不可回退的改动不实施。
- **一轮一动作**：组合动作在动作表中登记为一条。
- **文档格式**：Markdown 禁止裸单波浪线（GFM 删除线），数值区间用 `～`/`-`/`至`，约数用 `≈`。

## 改动校验双门禁

任何改变模型执行结果的改动，落地前必须同时通过精度门禁与性能门禁，任一不过即回退。判定细则、触发范围、常见误判见 [`references/rules.md`](references/rules.md)。

## 全局强制产物

| 产物 | 路径 | 时机 |
| --- | --- | --- |
| perf_ledger.json | `data/{model_name}/optimization_log/perf_ledger.json` | 每个动作执行完追加 |
| loop_state.json | `data/{model_name}/optimization_log/loop_state.json` | 每轮 L5 后更新（唯一轮次真相源） |
| workflow_status.md | `data/{model_name}/optimization_log/workflow_status.md` | 每轮收口更新 |
| 每轮性能报告 | `docs/{model_name}/performance-reports/round{k}.md` | 当轮落盘 |
| 最终优化报告 | `docs/{model_name}/final_optimization_report.md` | 循环轨迹逐轮追加，条目 14 收口 |
| 模型交付说明书 | `docs/{model_name}/{model_name}_model_delivery_manual.md` | 条目 14 收口 |
| next_actions.json | `data/{model_name}/regression-baseline-mgmt/next_actions.json` | 首轮收口与每轮 L7 |

- 目录约定、schema 与模板见 [`references/artifact-conventions.md`](references/artifact-conventions.md)。
- 中间产物只进 `tmp/`；GE_SESSION_DEMO 自管理目录（`models/M<id>/{output,report,.cache,sweep}`）不挪动。

## TaskList 骨架

```text
T0 环境自检 + 输入格式路由
T1 模型分析（结构/算子构成/链路/显存/可执行判定）
T2 决策确认 + 单卡基线 + profiling 归档
T3 并发与限核策略分析（只分析）
T4 精度基线门禁（golden + 阈值）
T5 性能分析 + 四项专项 → 初始 next_actions
T6 循环实施（6-12 择一，双门禁 + 台账）
T7 收口（最终报告 + 动作表 + 交付说明书）
```

## 条目明细

> 每节只写编排（目标/输入/输出/承接）；方法与判定在承接 skill。

### 0. 环境基线与路由
- **目标**：确认本机满足前提，定下执行路径与产物目录。
- **输入**：单卡设备 + 模型工作区。
- **输出**：环境基线（`data/env-baseline/`）、输入格式判定、路由结论、实测锚定。
- **承接 skill**：`model-recommend-ascend-env-baseline`

### 1. 模型分析
- **目标**：产出结构档案 + 算子构成 + 模块链路 + 显存估算 + 单卡可执行判定。
- **输入**：模型工作区（onnx 外部权重须同目录）。
- **输出**：结构档案、算子构成（AIC/AIV、Top-N、预警）、链路清单、显存估算、可执行判定。
- **承接 skill**：`model-recommend-adaptation`

### 2. 单卡基线运行
- **目标**：单卡跑通并采集首基线（时延 avg/TP99/TP999、QPS、HBM、profiling、精度）。
- **输入**：条目 1 判定可执行的模型 + 用户决策清单。
- **输出**：`baseline_metadata.json`、基线报告、`prof/{model_name}/baseline/`。
- **承接 skill**：`model-recommend-baseline-run`

### 3. 并发与限核策略分析
- **目标**：输出 `THREAD_NUM`/`CORE_NUM`/`GRAPH_MAX_PARALLEL`/`batch_size` 推荐及依据（只分析）。
- **输入**：条目 1 算子构成；目标场景；基线 HBM。
- **输出**：结构化并发配置推荐 + 方案文档（sweep 校准）。
- **承接 skill**：`model-recommend-core-limit-stress`

### 4. 精度基线门禁
- **目标**：建立 golden 与判定标准（先于一切优化），作为此后每个改动的门禁。
- **输入**：基线输出（`output_i.bin` + `output_shapes.json`）、优化后输出、阶段记录。
- **输出**：精度结论；不通过时定位报告（首个偏差节点）+ 修复验证。
- **承接 skill**：`model-recommend-precision-comparison`

### 5. 性能分析与四项专项深度分析
- **目标**：端到端 + 算子级采集、bound 判定、四项专项，产出优化点并入动作表。
- **输入**：可运行基线 + 采集场景（batch/threads/cores/CircleCount）。
- **输出**：三表 + bound 结论；`data/{model_name}/profiling-deep-analysis/iter{k}/findings.json`（须并入 next_actions）。
- **承接 skill**：`model-recommend-analysis`

### 6. GE 图模式与 shape 策略优化
- **目标**：选定 shape 策略与编译选项组合，控制编译开销，验证图质量。
- **输入**：基线跑通的模型；条目 1 动态维分布；条目 5 性能数据。
- **输出**：部署配置 + 前后性能对比 + dump_graph 验证记录。
- **承接 skill**：`model-recommend-ge-graph-optimization`

### 7. 既有算子与图优化适配（含 FA 族融合）
- **目标**：以不新增算子实现为前提落地可替换/可改善模式（内置优化/等价改写/精度路由 + 一次性 Pass 扩展）。
- **输入**：条目 1 链路清单；条目 5 热点。
- **输出**：逐模块适配方案 + 分开关归因数据 + **未适配项清单**（移交条目 10/12）。
- **承接 skill**：`model-recommend-fusion-pass-dev`
- Pass 开发、验证与交付规则见该 skill 的 `SKILL.md`；选型与 ROI 见 [`references/ge-custom-dev-routing.md`](references/ge-custom-dev-routing.md)。

### 8. 多线程与图并行优化
- **目标**：按条目 3 推荐实施并发/限核组合，用 sweep + profiling 验收 QPS/TP99。
- **输入**：条目 3 推荐配置；条目 5 overlap 机会表。
- **输出**：`multi-thread-analysis.md` + 验收数据（QPS/TP99/TP999 前后对比）+ 最终配置。
- **承接 skill**：`model-recommend-core-limit-stress`

### 9. 访存优化
- **目标**：对 memory-bound 热点实施访存优化（重叠搬运、减少 GM 往返）。
- **输入**：memory-bound 热点清单 + 依赖窗口。
- **输出**：带开关的优化实现 + 性能报告（算子耗时/关键路径/带宽利用率）。
- **承接 skill**：`model-recommend-memory-access-optimize`

### 10. 算子融合规划与理论性能估计
- **目标**：对无现成解法的热点链路与适配失败项做 bound 判定与收益排序。**条目 11 唯一入口**。
- **输入**：条目 5 耗时分布 + 条目 7 未适配项 + 条目 1 AIC/AIV 归属。
- **输出**：融合候选清单（方案/收益区间/bound/开发路径/来源），双轨分流（回流条目 7 / 进条目 11 / 转条目 12）。
- **承接 skill**：`model-recommend-analysis`

### 11. Kernel 生成
- **目标**：为条目 10 选定候选生成可运行 kernel 并完成精度/性能验证。
- **输入**：开发项（算法规格、bound、收益区间、来源）+ 交付形态。
- **输出**：算子工程 + 精度测试 + benchmark + GE 集成产物。
- **承接 skill**：`model-recommend-custom-op-dev`
- 标准工程结构与模板见该 skill 的 `assets/`。

### 12. 自定义算子开发与 GE 接入
- **目标**：补齐无法解析或无原生实现的算子（功能补齐向），完成「实现 → 部署 → 图接入」。
- **输入**：含未解析/无原生算子的模型。
- **输出**：算子工程 + DESIGN.md + test_*.py + benchmark + GE 接入说明。
- **承接 skill**：`model-recommend-plugin-dev`（需新内核时与 `model-recommend-custom-op-dev` 配套）
- 解析期「算子不支持」先走 ONNX 插件，需新能力再下沉 AscendC。

### 13. 运行时问题诊断（贯穿）
- **目标**：任一环节报错/卡死时快速定界修复，不阻塞主流程。
- **输入**：故障现象（明确报错 / 无输出卡死）。
- **输出**：修复方案 + 可检索的排查记录。
- **承接 skill**：`model-recommend-runtime-debug`

### 14. 优化回归验收与基线管理（收口）
- **目标**：统一基线与逐项验收，管理开关；产出最终报告、交付说明书与动作表。
- **输入**：全部已实施项与台账。
- **输出**：最终配置、`final_optimization_report.md`、交付说明书、`next_actions.json`、回归结论。
- **承接 skill**：`model-recommend-regression-baseline-mgmt`

## 持续优化循环

首轮线性执行 0→14 后，按「选动作 → 优化（双门禁）→ 采集 → 深度分析 → 收益判定 → 终止检查 → 动作表更新」迭代。

- **终止**：目标达成（连续 2 次复测）/ 连续 3 轮无收益 / 无可执行动作 / 轮次预算（默认 10）。
- **一轮一动作**；双门禁全程有效；同口径复测；四项专项必做且优化点并入动作表。
- **性能目标必须由用户指定**（指标 + 阈值），缺失时向用户确认。
- 细则见 [`references/rules.md`](references/rules.md)。

## 中止与上报

出现以下情况立即停止当前动作并上报用户，不得自行假设或降级绕过：

- 设备不可用 / `npu-smi` 显示他人进程长期占用且无法隔离；
- 性能目标或关键决策（低精度、改图、越界范围）未确认；
- 精度门禁或性能门禁无法建立（缺 golden、缺 profiling 且无法补采）；
- 同一阻塞连续 2 轮无法推进，或所需能力超出本工作流范围（量化/训练/多卡等）。

## 参考文档索引

- 双门禁判定细则：[`references/rules.md`](references/rules.md)
- 外部依赖清单（25 项 + 缺失处置）：[`references/external-dependencies.md`](references/external-dependencies.md)
- 循环终止、重采与幂等恢复：[`references/rules.md`](references/rules.md)
- 产物目录与 schema/模板：[`references/artifact-conventions.md`](references/artifact-conventions.md)
- Subagent prompt 模板：[`references/subagent-prompt-templates.md`](references/subagent-prompt-templates.md)
- GE 运行时与图优化（shape/编译选项/采集）：[`references/ge-runtime.md`](references/ge-runtime.md)
- GE 自定义交付件路由（插件/Pass/算子）：[`references/ge-custom-dev-routing.md`](references/ge-custom-dev-routing.md)
- GE/ACL 错误与故障分层：[`references/ge-errors.md`](references/ge-errors.md)
- 内置框架说明：[`../framework/README.md`](../framework/README.md)
- 循环状态脚本：[`scripts/loop_state.py`](scripts/loop_state.py)
