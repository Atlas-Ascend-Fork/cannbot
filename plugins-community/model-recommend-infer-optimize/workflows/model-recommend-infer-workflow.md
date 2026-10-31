# 推荐模型整网推理优化 · 工作流

本工作流由 `model-recommend-infer-optimize` plugin 的 primary agent 在每次收到「推荐模型（搜索/推荐/排序/视觉编码类网络）在昇腾 NPU 上的推理优化」请求时强制 Read，并严格按其推进。它以 **GE 图模式为核心优化基座**（onnx 直接进入；pytorch/HF 经 torchair 转入），先把模型跑通到可复现精度的单卡基线，再在基线上按「性能分析 → 分层优化（图 / 算子 / 并发 / 访存 / 融合 / kernel）→ 双门禁验收 → 动作表更新」持续循环，直到性能目标达成或收益枯竭。

> 路径约定：`skills/<skill-name>/SKILL.md`（安装后目录；源仓为 cannbot-skills `community/model/<skill-name>/`）为各条目承接的原子 skill，判定标准、昇腾专属要点、参考实现与依据都在 skill 内，本文档只写编排；`workflows/references/` 放门禁/循环/产物/派发细则；`workflows/templates/` 放强制交付件模板。
>
> Subagent 映射：文中的 runner / analyzer / implementer / reviewer 分别对应本插件 subagent `model-recommend-infer-runner` / `model-recommend-infer-analyzer` / `model-recommend-infer-implementer` / `model-recommend-infer-reviewer`，由 primary 按对应 `subagent_type` 派发，各自角色定义见 `agents/`。
>
> 依据标注约定：【实测】= 本机实际执行命令获取；【框架】= 内置 GE_SESSION_DEMO 与随 CANN 安装的文档/头文件；【插件】= 插件内 skill 与 references 的判定与经验沉淀。本工作流不引用任何外部链接，判定依据全部来自以上三类。

## 流程总览

```text
+---------------------------------------------------------------------------------+
| 0. 环境基线与路由                                                               |
|     npu-smi / CANN / GE v2 / 工具链自检；识别输入格式 → 定执行基座与约束        |
|     onnx 路径：GE_SESSION_DEMO　｜　pytorch/HF 路径：模型脚本 + torch_npu       |
+------------------------------------+--------------------------------------------+
                                     |
                                     v
+---------------------------------------------------------------------------------+
| 1. 模型分析   结构档案 + 算子构成 + 模块链路 + 显存估算 + 单卡可执行判定        |
+------------------------------------+--------------------------------------------+
                                     |
                                     v
+---------------------------------------------------------------------------------+
| 2. 单卡基线运行   决策逐项确认 → 冒烟 → 首基线（时延/QPS/HBM/profile/精度）     |
+------------------------------------+--------------------------------------------+
                                     |
                                     v
+---------------------------------------------------------------------------------+
| 3. 并发与限核策略分析（只分析不改代码）                                         |
+------------------------------------+--------------------------------------------+
                                     |
                                     v
+---------------------------------------------------------------------------------+
| 4. 精度基线门禁（此后每个改动都必须过此门禁）                                   |
+------------------------------------+--------------------------------------------+
                                     |
                                     v
+---------------------------------------------------------------------------------+
| 5. 性能分析与四项专项   三表 + bound 判定 + A/B/C/D → 初始 next_actions         |
+------------------------------------+--------------------------------------------+
                                     |
                                     v
     +----------------------------------------------------------------------------+
     |  持续优化循环（一轮一动作，双门禁全程有效）                                |
     |                                                                            |
     |   L1 选动作 ──> L2 执行优化（条目 6-12 择一）──> L3 采集                   |
     |        ^                                            |                      |
     |        |                                            v                      |
     |   L7 交付件同步 <── L6 终止检查 <── L5 收益判定 <── L4 深度分析（条目 5）  |
     |        |                                                                   |
     |        +--> 未终止则回 L1 下一轮；终止则进入条目 14 收口                   |
     +----------------------------------------------------------------------------+
                                     |
                                     v
+---------------------------------------------------------------------------------+
| 14. 回归验收与基线管理   最终报告 + 下一步动作表 + 回归结论（下一轮入口）       |
+---------------------------------------------------------------------------------+
```

> **L1-L7 各做什么**（图里只标名字，含义看这里）：
>
> - **L1 选动作**：取 `next_actions` 顶部可执行项，需用户拍板的先问清
> - **L2 执行优化**：条目 6-12 择一实施（新算子走 10→11），过双门禁
> - **L3 采集**：`--prof msprof` 同口径采集，归档 `prof/{model_name}/iter{k}/`
> - **L4 深度分析**：条目 5 四项专项（算子执行 / 多流掩盖 / H2D-D2H / host）
> - **L5 收益判定**：主指标同口径复测比上轮，改善 ≤ 噪声带记无收益
> - **L6 终止检查**：目标达成 / 连续 3 轮无收益 / 无动作 / 轮次预算 → 退出
> - **L7 交付件同步**：台账 + `round{k}.md` + 状态矩阵 + 动作表当轮落盘

> 读图要点：**条目 5 有两重身份**——首轮它作为循环入口产出初始 `next_actions`（4 之后的方框），此后每轮作为 **L4** 的固定分析动作重复执行。**条目 6-12 不单独画框**：它们不按顺序全跑，而是由 L1 从动作表择一、在 L2 执行（一轮只做一个）；其中条目 10 是条目 11 的唯一入口（新算子先规划后开发）。**条目 13（运行时诊断）**不占轮次，0-14 任一环节故障时插入。

## 执行规则

进入本 skill 后，先按「TaskList 骨架」建任务，再逐条目推进。每次派 subagent 前按 [`references/subagent-prompt-templates.md`](references/subagent-prompt-templates.md) 选模板、替换占位符；subagent 因不能与用户对话而缺的交互，由 primary 在派发前问清并作为 spec 传下去。

### 适用范围与输入格式（条目 0 首先识别）

| 输入格式 | 执行 / 采集基座 | 优化约束 |
| --- | --- | --- |
| **onnx 图** | **GE_SESSION_DEMO**：`aclgrphParseONNX` 解析、配置驱动、C++ 无模型分支；`prepare.sh` / `run.sh` / `tools/*.py` 一条链 | **任何优化不得修改原始 onnx 图**。合法手段：GE 内存图 pass、GE 编译选项、并发/限核参数、精度模式开关；onnx 落盘改写/算子替换重写文件禁止 |
| **pytorch 脚本** | 模型自身脚本 + `torch_npu` 执行与采集（`torch_npu.profiler`）；**torchair 转 GE 引擎为必选优化项** | 可修改脚本（git 可回退 + 开关保护）；可使能 torch.compile；torchair 动转静接入 |
| **HuggingFace 模型** | 同 pytorch 脚本（权重与实现脚本均在仓内） | 同 pytorch 脚本 |

**GE_SESSION_DEMO 只服务 onnx 路径**：它提供 onnx 的解析、编译、运行与精度校验入口（含 `compile.sh` 与 `tools/*.py` 工具链）。pytorch / HuggingFace 路径**不需要它**，也不需要 `g++` 与 `nlohmann/json.hpp`，改用模型自身脚本 + `torch_npu` 执行与采集。三条路径共用的是 CANN / GE v2 运行时、`msprof` / `atc` 等机器侧能力，以及同一套双门禁与产物目录约定。

> **能力边界（重要）**：**onnx 路径为完整支持**。**pytorch / HuggingFace 路径当前为实验性**——条目 0/6/7/8/9 可直接复用，但条目 1（结构档案）、条目 2（基线运行）、条目 3（并发校准）与条目 5（三表采集）目前只有 onnx/GE 侧实现；pytorch 侧需由用户提供等价脚本（结构导出、基线脚本、并发压测、`torch_npu.profiler` 采集），工作流不代为生成。以实验能力使用前先与用户确认。

onnx 输入经 GE_SESSION_DEMO 的 `prepare.sh` / `compile.sh` / `run.sh` / `test.sh` 入口运行，**禁止绕过脚本直接执行二进制**（会破坏工作目录与缓存治理）。

### 外部依赖（运行前提，条目 0 逐项核对）

| 类别 | 依赖 | 要求 | 缺失后果 |
| --- | --- | --- | --- |
| 硬件/系统 | NPU、驱动固件、Linux aarch64 | Ascend910B 系列单卡可见、Health OK | 全流程不可执行 |
| CANN 软件栈 | CANN Toolkit、GE v2（`libge_runner_v2.so`）、`atc` / `msopgen` / `msprof` | CANN 9.1.0，工具均可 `which` | 无法编译运行、无 profiling、无法建算子工程 |
| 编译工具链 | `g++`、`nlohmann/json.hpp` | C++17；**仅 onnx 路径**（框架 `compile.sh`）与条目 11/12 算子工程需要 | onnx 路径框架编译与算子工程失败；pytorch/HF 不受影响 |
| 执行框架 | **GE_SESSION_DEMO**（插件内置 `framework/GE_SESSION_DEMO/`） | 编译产出 `GEsession_test_acl`；**仅 onnx 路径需要** | onnx 路径不可执行；pytorch/HF 不依赖 |
| Python 侧 | `python3`、`numpy`；onnx 路径另需 `onnx`、`onnxruntime`（CPU golden）；pytorch/HF 路径另需 `torch`、`torch_npu` | onnx 1.22.0 参考值；onnxruntime 缺失需用户提供标杆 | onnx 路径解析/标杆失效；pytorch/HF 路径缺 `torch_npu` 则无法执行 |
| 算子开发 | AscendC（经 `msopgen`）、`cannbot-dsl`（A5）、插件内算子适配要点 | A2/A3 走 AscendC；当前环境 cannbot-dsl 不可用 | 条目 11/12 能力受限 |
| 数据资产 | `model.onnx` + 外部权重（或 pytorch/HF 权重与脚本）、`input_data/`、`reference/` 标杆 | 用户提供，或工具自动构造/生成 | 无输入或无精度门禁 |

**GE_SESSION_DEMO 是 onnx 路径的标准执行入口，已随插件内置**（`framework/GE_SESSION_DEMO/`）。**是否自动落到工程根取决于安装方式**：project 级 `init.sh` 自动复制；`init.sh global` 不复制；仓库统一安装器（`cannbot install` / npm 包）只把框架放进 `.cannbot/plugins/model-recommend-infer-optimize/framework/`，需手工复制。pytorch / HuggingFace 路径不需要它：

```bash
# 手工补齐（global 安装、统一安装器安装，或 project 级重装时）；统一安装器安装后 <插件目录> 为 .cannbot/plugins/model-recommend-infer-optimize
cp -r <插件目录>/framework/GE_SESSION_DEMO <工程根>/GE_SESSION_DEMO
cd <工程根>/GE_SESSION_DEMO && bash compile.sh                        # 产出 ./GEsession_test_acl（仅 onnx 路径）
```

全量清单（25 项，含核对命令、获取方式、缺失处置矩阵与当前已知限制）见 [`references/external-dependencies.md`](references/external-dependencies.md)。依赖缺失时按该文档的处置矩阵执行，**不得用「假设可用」替代自检**。

### 全局约束（全文只声明一次）

- **单卡执行**：`DEVICE_NUM` 恒为 1；卡选择经 `GE_DEVICE_ID` / `START_DEVICE`。
- **精度验证仅串行单并发**（`THREAD_NUM=1`）；并发（`THREAD_NUM>1`）仅做性能压测，不做 dump 与精度验证。
- **不做量化**：性能手段为图优化、算子融合、并发/限核、访存优化、自定义算子、torchair/torch.compile；精度手段仅 fp16/hf32 精度模式开关，启用必须过精度门禁。
- **默认保持原精度**：一切优化默认在原图/原始脚本精度下进行；低精度选项（`FORCE_16` / `ENABLE_HF32` / `precision_mode` / `op_precision_mode` / 算子级低精度路由等）默认关闭，启用须「**用户人工确认** + 精度门禁（记录误差指标）」双重前置，缺一不可；未经确认的低精度收益不得纳入已验收配置。
- **自定义算子语言按平台路由**：A2/A3 平台用 **AscendC**（msopgen 工程）；A5 平台推荐 **cannbot-dsl**。
- **硬件基准实测锚定**：算力（TFLOPS）与带宽（TB/s）以本机小规模 matmul + HBM copy 实测为准，供 bound 判定与 Roofline 使用。
- **所有优化必须可开关、可回退**；不可回退的改动禁止实施（框架侧需求记录移交，不擅自改）。
- **primary 只编排不替工**：负责条目推进、一切用户交互（决策清单、低精度授权、动作取舍）、prompt 组装、台账/状态表维护与收口核验，不亲自跑采集、不亲自改模型。
- **一轮一动作**：循环内每轮只执行一个动作，保证归因唯一；强关联的组合动作在动作表中登记为一条。
- **文档格式**：Markdown 禁止裸单波浪线（GFM 会渲染为删除线），数值区间用 `～` 或 `-`/`至`，约数用 `≈`；交付前 grep 确认。

### 全局强制门禁：改动校验双门禁

**任何对模型执行的改动，落地前必须同时通过「精度门禁」与「性能门禁」，任一不通过即回退。** 适用范围：图/模型改动、配置改动、编译选项、算子实现变更、运行时修复中涉及上述任何一项的改动。分析类只读动作不触发；结论转化为改动时即触发。

1. **精度门禁**：串行单并发（`THREAD_NUM=1`）verify 全部输出 pass（整型/bool 精确相等；浮点 `allclose`，阈值按模型精度要求裁定并记录依据）；精度相关选项须额外记录误差指标，且低精度选项启用前须用户人工确认。并发/限核参数仍须做一次串行 verify。精度不过 → **直接回退，不进入性能测量**。
2. **性能门禁**：同口径对比（同卡/同 batch/同 `THREAD_NUM`/`CORE_NUM`/同 CircleCount 与统计策略，对照基线或上一已验收配置）；目标场景主指标（单并发看 avg/TP99；吞吐场景看 QPS/TP99）**不得劣化超过噪声带**（以重复测量方差确定，典型 ±2%～±5%）；改善小于噪声带不得宣称提升；允许局部指标劣化换主指标显著改善，但必须显式声明、量化、经用户确认；算子级改动除算子级加速比外**必须补整图端到端对比**。**性能结论双口径强制**：时延（单并发 avg/TP99/TP999）与吞吐（目标并发/批量配置的 QPS 与 TP99）两组数据均须产出（吞吐口径取当前已验收配置或用户指定场景），只测其一视为测量未完成。

**落地流程**：改动前确认同口径对照基准（无则先采）→ 实施（可开关/可回退）→ 精度门禁 →（过）→ 性能门禁 →（过）→ 落地并写 perf_ledger（`reverted=false`）；任一不过 → 回退并记录原因。判定细则见 [`references/gate-rules.md`](references/gate-rules.md)。

### 全局强制产物

| 产物 | 路径 | 时机                                                              |
| --- | --- | ---                                                                 |
| **perf_ledger.json**（动作台账） | `data/{model_name}/optimization_log/perf_ledger.json` | 每条目/每动作执行完毕追加，schema 见 [`templates/perf-ledger-schema.json`](templates/perf-ledger-schema.json)|
| **loop_state.json**（循环状态） | `data/{model_name}/optimization_log/loop_state.json` | 每轮 L5 后更新，唯一轮次真相源|
| **workflow_status.md**（执行矩阵） | `data/{model_name}/optimization_log/workflow_status.md` | 每轮收口更新，按 [`templates/workflow-status-template.md`](templates/workflow-status-template.md)|
| **每轮性能报告** | `docs/{model_name}/performance-reports/round{k}.md` | 每轮动作完成后当轮落盘，按 [`templates/performance-report-template.md`](templates/performance-report-template.md) 八章齐全|
| **最终优化报告** | `docs/{model_name}/final_optimization_report.md` | 循环轨迹逐轮追加（primary 写），条目 14 收口成文，含下一步动作表|
| **下一步动作表**（机器可读） | `data/{model_name}/regression-baseline-mgmt/next_actions.json` | 首轮收口与每轮 L7 更新，循环 L1 的唯一输入|

产物目录约定（全局强制）：`docs/{model_name}/{skill}/` 放人读文档，`data/{model_name}/...` 放机器可读数据，`prof/{model_name}/...` 放 profiling 归档（完整 `PROF_*` 目录 + kernel 汇总），`ops/{op_name}/` 放算子工程，`tmp/{model_name}/{skill}/` 放可再生的中间产物。`{model_name}` 取工作区标识（onnx 输入为 GE_SESSION_DEMO 编号 `M<id>`；pytorch/hf 输入为工作区模型名）。禁止中间产物写入 docs/data/ops，禁止交付件散落 tmp/ 或工作目录根；GE_SESSION_DEMO 自管理目录（`models/M<id>/{output,report,.cache,sweep}`）不挪动。全量定义见 `model-recommend-ascend-env-baseline` skill 与 [`references/artifact-conventions.md`](references/artifact-conventions.md)。

### TaskList 骨架

```text
T0. 环境自检并识别输入格式，确定执行路径与优化约束
T1. 模型分析：结构档案 + 算子构成 + 模块链路 + 显存估算 + 单卡可执行判定
T2. 与用户逐项确认关键决策，跑通单卡基线并归档 profile
T3. 并发与限核策略分析，输出推荐配置（只分析不改代码）
T4. 建立精度基线门禁（golden 标杆 + 判定阈值）
T5. 性能分析与四项专项深度分析，产出 findings 并入动作表
T6. 逐条目实施优化（6/7/8/9/11/12），每项过双门禁并写台账
T7. 收口：最终报告 + 下一步动作表 + 回归结论
```

T4 之后进入循环，**每轮新建一组 TR{k} 任务**（k 为递增轮次号），本轮做完即逐项关闭，再为下一轮建新组——用每组任务表达循环，不要用一个长驻任务覆盖整个循环：

```text
TR{k}.1  L1 选动作：取 next_actions 顶部可执行项，完成用户确认
TR{k}.2  L2 执行优化：按动作的 workflow_entry 派 implementer，过双门禁
TR{k}.3  L3 采集 + L4 深度分析：派 runner 采集、派 analyzer 分析四项专项
TR{k}.4  L5 收益判定（reviewer 复核验收口径）
TR{k}.5  L6 终止检查 + L7 交付件与 action table 同步更新
```

## 0. 环境基线与路由

**目标**：确认本机满足推荐模型分析与优化前提，并定下后续所有条目的执行路径与产物目录。

**输入**：目标机器（单卡可见）+ 待分析模型工作区。

**输出**：环境基线记录（`data/env-baseline/`）、输入格式判定、执行路径与约束声明、后续条目的路由结论。

**执行步骤**：
1. 设备与容量：`npu-smi info` 取型号、HBM、健康状态；核心形态记录 AIC/AIV 分离形态（限核写法 `CORE_NUM="AIC|AIV"`，默认 `24|48`，实际核心数运行时经 `PlatformAscendC` 获取，禁止硬编码）。
2. 软件栈：CANN 版本（`$ASCEND_HOME_PATH`）、GE Session v2 组件（`libge_runner_v2.so`）、工具链（`atc` / `msopgen` / `msprof`，A5 平台加查 cannbot-dsl）、Python 侧（onnx / onnxruntime / torch / torch_npu / torchair）。
3. 识别输入格式并声明优化约束（见「适用范围与输入格式」）：onnx → GE_SESSION_DEMO；pytorch / HuggingFace → 模型自身脚本 + `torch_npu`。后续条目的执行与采集命令按此路径取用。
4. 执行框架（**仅 onnx 路径**）：`GE_SESSION_DEMO` 存在且 `bash compile.sh` 通过、产出 `GEsession_test_acl`；缺失时从插件 `framework/GE_SESSION_DEMO/` 复制（见 [`references/external-dependencies.md`](references/external-dependencies.md) §2），并把框架路径与 `GEsession_test_acl` 的编译时间、校验和写入环境基线（供后续判断框架是否被改动）；编译失败转条目 13。pytorch/HF 路径本步记 `not_applicable`，不因此阻塞。
5. 依赖台账：按 [`references/external-dependencies.md`](references/external-dependencies.md) §1 逐项记录核对结果与版本号（25 项），缺失项按 §3 处置矩阵标注「阻塞 / 能力受限 / 可继续」，连同环境基线一起落 `data/env-baseline/`。**阻塞项按输入格式判定**：onnx 路径含执行框架与 `g++`/`nlohmann/json.hpp`；pytorch/HF 路径不含这两项、但含 `torch_npu`。**阻塞项未清零不得进入条目 1**。
6. 硬件锚定：小规模 matmul 测算力、HBM copy 测带宽，结果入 `data/env-baseline/`（bound 判定与 Roofline 的唯一基准）；任一项自检失败即停止下游条目并报告。

**承接 skill**：`model-recommend-ascend-env-baseline`

## 1. 模型分析

**目标**：产出「结构档案 + 算子构成 + 模块链路 + 显存估算 + 单卡可执行判定」，作为条目 3/6/7/10 的公共输入。

**输入**：模型工作区（onnx 文件 / pytorch 脚本 / hf 仓；onnx 外部权重须与模型文件同目录）。

**输出**：结构档案（输入输出清单 name/dtype/shape/动态维、opset/框架版本、图规模）；算子构成（AIC/AIV 计数与占比、频次 Top-N、超大 initializer、dtype/domain/bool 预警）；模块链路清单（按 AIC/AIV/访存/控制归属）；显存估算（权重 + 激活 + workspace + 并发叠加）；单卡可执行判定。

**执行步骤**：
1. 识别输入格式（onnx / pytorch / hf），确定执行路径与优化约束。
2. 结构参数提取：onnx 经 `prepare.sh <id> --config-only` 生成配置；pytorch/hf 解析脚本模块组成，产出等价结构档案。
3. 算子构成统计与兼容性预警（dtype 支持集合、非标 domain、bool 输入算子、动态输出）。
4. 模块链路拆解并标注归属（直接支撑条目 3 限核配比与条目 10 融合规划）。
5. 显存静态估算（数值经脚本核验，脚本入 tmp/，结果入 data/）。
6. 单卡可执行判定：可执行 → 流转条目 2；放不下 → 如实输出问题清单与结论（分片/稀疏化超出范围，需用户决策）。

**承接 skill**：`model-recommend-structure-analysis`

## 2. 单卡基线运行

**目标**：模型单卡跑通并采集首基线（时延 avg/TP99/TP999、QPS、HBM 峰值、profiling、精度结论），作为一切优化的同口径对照。

**输入**：条目 1 判定可执行的模型工作区 + 与用户逐项确认的决策清单。

**输出**：`data/{model_name}/baseline/baseline_metadata.json`（配置 + 口径 + 计时 + HBM + 精度 + prof 归档指针）、基线报告、`prof/{model_name}/baseline/` 归档。

**执行步骤**：
1. 关键决策与用户逐项确认（禁止默认拍板）：输入来源、shape 策略、batch、标杆来源、采集内容、目标卡。其中 **batch>1 与 `all_dynamic` 只有在条目 1 的 `feasibility.json` 判定为支持时才进入候选**（判定为 `no` 时不得写入决策清单，也不得进 sweep）。
2. 设备空闲确认；首次执行时完成算力/带宽实测锚定。
3. 模型准备与配置校验（onnx：`prepare.sh` + `inspect_config.py` 全绿；pytorch/HF：脚本可加载、权重与 dtype 正确、首帧输出合理）。
4. 冒烟测试（小 circle 跑通建图/编译/执行/落盘全链路；失败转条目 13）。
5. 正式基线：串行单并发，HBM 后台采样，记录编译产物状态；onnx 用 `CircleCount ≥ 1000`，pytorch/HF 用脚本固定迭代或压测工具，统计口径与次数一并记录。
6. 精度验证（仅串行；标杆优先级：用户 `reference/` → onnxruntime 生成 → 报错；bf16 与自定义算子模型必须用户提供标杆）。
7. profiling 采集与归档（onnx：`--prof ge|msprof`，含 `mindstudio_profiler_output` 汇总；pytorch/HF：`torch_npu.profiler`，导出 kernel 明细与 trace），统一归档到 `prof/{model_name}/baseline/`。
8. 报告落盘（含口径记录与流转结论 → 条目 3/4/5）。

**承接 skill**：`model-recommend-baseline-run`

## 3. 并发与限核策略分析

**目标**：输出 `THREAD_NUM` / `CORE_NUM`（AIC|AIV）/ `GRAPH_MAX_PARALLEL` / `batch_size` 推荐组合及定量依据。**只分析不改代码**（实施由条目 8 承接）。

**输入**：条目 1 算子构成；目标场景（高吞吐 QPS / 低时延 TP99 / 均衡）；基线 HBM 占用。

**输出**：结构化并发配置推荐 + 方案文档（限核配比理由、图实例显存估算、线程收益上限、TP99 影响分析）。

**执行步骤**：
1. 复用结构档案：AIC 主导 vs AIV 主导判定。
2. 定性分类：图粒度（单请求计算量大小 → 多线程收益方向）、限核配比方向、batch 与并发权衡。
3. 定量估算：图实例显存（workspace 随 `GRAPH_MAX_PARALLEL` 增长，对照 HBM 余量）、线程数上限、限核对时延与 QPS 的影响。
4. 方案审查 → 输出单套推荐配置（含 TP99 上限约束下的最优 QPS 组合）。
5. sweep 校准（必做）：`tools/sweep.py` 三阶段（限核寻优 → 并发 1..8 → 可选 batch），回修估算并说明误差。batch 阶段仅在 `feasibility.json` 判定支持时执行。**sweep 不可用时**（如 `device_occupied` 误判、进程崩溃；误判可先试 `--skip-device-check`）：改用手工 `run.sh --threads/--cores` 逐点扫描，扫描点与结果按同一格式记入台账，并在 `loop_state.json` 记 `sweep_fallback=true` 与失败原因；不得省略校准直接给推荐值。
6. 变更触发重分析：场景 / batch / TP99 上限变更，或优化项改变核资源画像（如 FA 融合后）。

**承接 skill**：`model-recommend-concurrency-strategy-analysis`

## 4. 精度基线门禁

**目标**：建立 golden 标杆与判定标准（**先于一切优化**），并作为此后每个改动项的验证门禁。所有精度判定基于与标杆的数值对比，不可凭直觉；**每次只改一个变量**。

**输入**：基线输出（`output_i.bin` + `output_shapes.json`）、优化后输出、优化阶段记录。

**输出**：精度验证结论（通过/不通过 + 指标）；不通过时输出定位报告（首个偏差节点 → 参数）与修复验证。

**执行步骤**：
1. 收集信息：症状、优化阶段、精度模式（fp16/hf32/precision_mode）、标杆来源。
2. 快速诊断：症状分类表匹配 → 快速验证清单 → 发现问题直接修复。
3. 分节点定位：`--dump_data` 开启 GE 数据 dump → 与 CPU 参考逐节点对比 → 定位首个偏差节点。
4. 精细定位（按需）：暴露中间输出逐步缩小范围（onnx 输入时仅限内存图/临时副本，不改原图文件）。
5. 修复与全量精度重验。
6. 输出调试报告（问题概要/根因/修复/验证/遗留风险）。

**承接 skill**：`model-recommend-precision-comparison`

## 5. 性能分析与四项专项深度分析

**目标**：端到端与算子级性能采集、瓶颈定位（bound 分类）、四项专项深度分析，产出结构化优化点并入动作表，驱动条目 6-12 迭代。

**输入**：可运行基线 + 采集场景定义（batch / `THREAD_NUM` / `CORE_NUM` / CircleCount）。

**输出**：性能报告（时延/QPS 分场景数据、三表、bound 结论）；`data/{model_name}/profiling-deep-analysis/iter{k}/findings.json`（结构化优化点：id/category/finding/evidence/suggestion/expected_gain/confidence/workflow_entry），**必须并入 next_actions**（去重标注）。

**执行步骤**：
1. 定义采集场景：单并发时延基线与目标并发吞吐基线**分开采集且均须产出**（双口径强制）；CircleCount 足够大保证打点稳定。
2. 模型级采集：onnx 路径 `run.sh <id> --prof ge|msprof`；pytorch/HF 路径 `torch_npu.profiler` 导出同等数据。统一归档 `prof/{model_name}/{case}/`（完整采集目录 + 提取 kernel 汇总）；采集前确认卡空闲。
3. 算子级深度采集：onnx 路径用 msprof（aic-metrics 覆盖 Cube/Vector/MTE 流水）；pytorch/HF 路径用 `torch_npu.profiler` 的 kernel 明细与算子耗时，口径对齐后同表分析。
4. 三表分析：kernel 表（耗时 Top-N，累计 ≥1%）、overlap 机会表（多线程下利用率/间隙/拷贝窗口）、融合模式表（source-backed 对照 GE 融合结果判定「应融合未融合」）。
5. bound 判定与归因：compute-bound（利用率 vs 实测锚定峰值）/ memory-bound（带宽利用率 vs 实测 copy 带宽）/ host-launch-bound（kernel 总时长 ÷ 墙钟）/ 排队争抢（并发 TP99 劣化但 avg 改善）。
6. 四项专项（全部必做，数据源 op_summary / api_statistic / fusion_op / step_trace）：**A 算子执行时间**（类型聚合、AIC/AIV 分列、碎片化分布、单 kernel Roofline 效率）；**B 多流掩盖**（流分布、时间线重叠度、串行化链、并发流争抢）；**C H2D/D2H**（拷贝分解、固定开销判定、关键路径占比）；**D host 瓶颈**（kernel/墙钟 < 80% 时触发：墙钟缺口量化 + host API 耗时分解 + 同步等待分解；未触发时给判定依据）。
7. 对比与回修：优化前后同口径对比；结论回修条目 3 并发分析与条目 10 融合规划估算模型；数据对账（kernels + H2D/D2H + host 缺口 ≈ 墙钟）。

**承接 skill**：`model-recommend-performance-analysis`、`model-recommend-profiling-deep-analysis`

## 6. GE 图模式与 shape 策略优化

**目标**：为模型选定最优 shape 策略与图/编译选项组合，最大化执行性能并控制编译开销；pytorch/hf 输入完成 torchair 转 GE 引擎（**必选**）与 torch.compile 评估。

**输入**：基线跑通的模型；条目 1 动态维分布；条目 5 性能数据。

**输出**：部署配置 + 前后性能对比 + 图编译质量验证记录（dump_graph / 融合统计）。

**执行步骤**：
1. shape 策略决策：onnx 三模式（`all_static` / `all_dynamic` / `custom`）；**`all_dynamic` 需先由 `feasibility.json` 判定动态 shape 可跑通**，否则退回 `all_static` 或 `custom` 并记录原因；pytorch/hf 输入走 torchair 动转静接入（必选优化项，过双门禁）+ torch.compile 使能评估。
2. GE 编译选项调优（逐项单变量）：`CORE_NUM` / `FORCE_16` / `ENABLE_HF32` / `ge.exec.precision_mode` / `op_precision_mode` / 融合开关文件 / `GRAPH_MAX_PARALLEL`；精度相关选项须过精度门禁并记录误差。
3. **自动融合增强评估（必做）**：GE 场景尝试开启 autofuse 自动融合（torchair 场景 `experimental_config.auto_fusion_pass`；onnx/GE 场景经融合开关文件与相关编译选项验证自动融合增开空间）；torch.compile 场景尝试 **inductor + autofuse** 组合（`inductor_config.enable_inductor` + `auto_fusion_pass`）；逐项与默认配置对比，过双门禁后记录收益（环境/版本不支持时如实记录原因并归档结论，不阻塞流水）。
4. 图编译质量验证：dump_graph 查看编译各阶段图，确认预期 pass 生效；`fusion_result.json` 量化融合命中。
5. 重编译控制评估：形状集合有限时 kernel_meta 同配置复用；形状多变场景评估编译耗时占比，必要时转 custom/all_dynamic。
6. 双门禁验收落地；切换策略后 `--show` 与 io_config 一致性确认。

**承接 skill**：`model-recommend-ge-graph-optimization`

## 7. 既有算子与图优化适配（含 FA 族融合）

**目标**：以**不新增算子实现**为前提落地可替换/可改善的计算模式。手段分两类：① 零开发——GE 图编译内置优化开关、等价改写、精度模式路由；② **一次性框架扩展**——图融合 pass（含 FA 族），框架当前未含 pass 实现，需写 C++，**不计入零开发清单**，须开关保护、默认关闭。

**输入**：条目 1 算子构成与链路清单；条目 5 热点数据。

**输出**：逐模块适配方案（模块 → 手段 + 约束核对）；分开关归因数据；替换前后 profiling 对比 + op_improvement 归档；**未适配项清单**（模块/链路 → 失败原因分类【无算子/硬约束/语义不匹配/精度未达标】→ 所需算子能力 → 已排查候选），性能替换型并入条目 10，功能补齐型转条目 12。**本条目禁止自行启动新算子开发**。

**执行步骤**：
1. 模块拆解（复用条目 1）到可替换链路级。
2. 逐链路匹配：GE/ACL 支持算子清单（随 CANN 提供）+ 插件内适配要点（`model-recommend-fusion-operator-adaptation` / `model-recommend-flash-attention-fusion`）查证 + 随包文档校验（记录文档路径与参数约束）。
3. FA 族融合确认（attention 链为热点时必做）：功能确认用最小验证模型实证参数矩阵（序列长/头数/头维/dtype/布局/mask/scale）。
4. 图融合 pass 接入：在 `aclgrphParseONNX` 之后、`AddGraph` 之前的 GE 内存图上做模式匹配与算子替换（不依赖 onnx 融合算子表达）；**onnx 输入禁止改原图**，一切改写仅发生在内存图；开关独立、默认关闭。
5. 等价改写：onnx 输入仅限 GE 内存图 pass 或运行时副本；pytorch/hf 输入可直接修改脚本（git 可回退 + 逐项 enable 开关）。
6. 精度模式路由：`FORCE_16` / `ENABLE_HF32` / `op_precision_mode` 逐项评估。
7. 分开关隔离归因（必做）：逐项单独启用测端到端 + kernel 时间再组合；融合收益是 shape/并发相关的，单并发与目标并发分别测。
8. 双门禁验收（逐项 verify 全 pass + 端到端主指标不劣化，回退项如实记录）+ 未适配项移交条目 10/12。

**承接 skill**：`model-recommend-fusion-operator-adaptation`、`model-recommend-flash-attention-fusion`

## 8. 多线程与图并行优化

**目标**：按条目 3 推荐配置实施并发/限核组合，用 sweep 与 profiling 验收 QPS/TP99 收益（推荐模型单请求计算量通常不大，QPS 主靠并发变现）。

**输入**：条目 3 推荐配置；条目 5 overlap 机会表。

**输出**：`docs/{model_name}/multi-thread-optimization/multi-thread-analysis.md` 分析报告 + 验收数据（QPS/TP99/TP999 前后对比）。

**执行步骤**：
1. 先分析后实施：整网 DAG 确认请求间独立；图内 AIC/AIV 资源画像决定限核配比。
2. sweep 三阶段实施（`tools/sweep.py`），或按条目 3 推荐直接验证。
3. 参数天然可回退；先证明正确（单并发精度 + 并发结果稳定性，无异常尖刺）再追性能；overlap ≠ 收益（资源争抢/拖尾/TP99 劣化需继续调限核与线程数）。
4. 调试期 profiling 确认多线程下 AIC/AIV 利用率变化与 kernel 排队。
5. 双门禁验收：配置组合串行 verify 全 pass；目标场景 QPS/TP99 不劣化超过噪声带。

**承接 skill**：`model-recommend-multi-thread-optimization`

## 9. 访存优化

**目标**：对条目 5 确认的 memory-bound 热点（查表/大 GEMM 权重读取/密集 elementwise 访存链）实施访存优化：搬运与计算重叠、减少 GM 往返。

**输入**：memory-bound 热点清单 + 依赖窗口分析。

**输出**：带开关保护的优化实现 + 性能报告（目标算子耗时、关键路径、带宽利用率前后对比）。

**执行步骤**：
1. 方案设计：热点 + 依赖窗口分析（前序算子不能同为 memory-bound）→ 用户确认。
2. 手段分层：图结构侧（脚本改写减少 GM 往返，零开发，首选；GE 内存图 pass 属一次性框架扩展，复用条目 7 已建的 pass）→ kernel 侧（自定义算子内双缓冲/预取，`DataCopy` 与计算重叠）→ 精度模式联动（fp16 减少搬运字节，须过精度门禁）→ 框架侧需求（GE 无图级显式 stream prefetch，记录移交）。
3. 实施（enable 开关保护，默认关闭）。
4. 验证：**单点先行**（先一个热点，成功再扩展）；目标算子耗时 + 端到端 + 精度。
5. 双门禁验收。

**承接 skill**：`model-recommend-memory-access-optimize`

## 10. 算子融合规划与理论性能估计

**目标**：对无现成解法的热点链路**和算子适配失败项**规划融合/自定义算子方案，并在动手开发前给出理论收益排序（决定条目 11 开发优先级）。**本条目是条目 11 新算子开发的唯一入口。**

**输入**：条目 5 算子级耗时分布（kernel 表 + 融合模式表）+ 条目 7 未适配项清单 + 条目 1 AIC/AIV 归属。

**输出**：融合候选清单（链路 → 方案 → 理论收益区间 → bound 判定 → 开发路径 → 来源标记），按收益/成本比排序，**双轨分流**：既有算子可解（改写/调用修正/参数组合）回流条目 7；需新算子形成条目 11 开发清单；功能补齐型（图跑不起来）转条目 12。

**执行步骤**：
1. 热点链路识别与未适配项并入：从 profiling 提取相邻 kernel 序列，识别「小算子串」（launch 开销主导）与「GM 往返链路」（中间张量落回 HBM）；条目 7 未适配项逐项核对（有 profiling 证据用实测锚定，无证据用结构推导并标注来源）。
2. bound 判定（Roofline）：对每个候选链路计算算术强度（FLOPs/Bytes），对照本机实测锚定判定 compute/memory-bound。
3. 理论收益估计：融合收益 = 消除的 launch 开销 + 减少的 GM 读写 + 减少的 dtype 转换，给出保守/乐观区间。
4. 融合机制选型：GE 图内融合 pass / 等价改写 / AscendC·cannbot-dsl 纯 Vector 融合算子 / Matmul 高阶 API Cube 融合 / AIC-AIV 协同 kernel（按平台路由）。
5. 排序输出 Top-N 开发清单（结合模板复用度等开发成本）。

**承接 skill**：`model-recommend-fusion-planning-estimation`

## 11. Kernel 生成

**目标**：为条目 10 选定的融合候选生成可运行的融合 kernel，并完成精度/性能验证。**唯一合法入口 = 条目 10 开发清单**（例外：纯 bug 修复、既有算子调用修正、精度修复，属条目 7/4 范畴）。

**输入**：开发项（算法规格、bound 判定、理论收益区间、来源标记）+ 目标交付形态。

**输出**：算子工程 + 精度测试 + benchmark（vs 原算子串加速比，对照理论收益区间复核）+ GE 集成产物。

**执行步骤**：
1. 需求理解 → 设计文档（API 映射、精度路由、Tiling 推导、循环结构、数据流）。
2. 路径决策：A2/A3 → 标准 AscendC（纯 Vector 逐元素/归约/查表走常规 kernel；Matmul 族走 Matmul 高阶 API；Cube+Vector 融合按标准编程模型，从已验证模板改造不裸写）；A5 → cannbot-dsl。
3. 工程实现（A2/A3：msopgen 生成工程，`--soc-version` 以本机为准；硬件参数运行时经 `PlatformAscendC` 获取，禁止硬编码）。
4. 精度验证：对照 golden（numpy / CPU onnxruntime 参考），按 dtype 的 atol/rtol 标准判定；尺寸覆盖 batch 1/2/N 与动态维边界。
5. 性能测试：msprof 采集 vs 原算子串标杆，输出加速比报告（geomean/mean/min/max）。
6. 交付集成（算子包部署 + 图接入，见条目 12）+ 双门禁（整图 verify 全 pass + 端到端主指标不劣化，profiling 确认融合 kernel 真实替换原算子串）。

**承接 skill**：`model-recommend-kernel-generation`

## 12. 自定义算子开发与 GE 接入

**目标**：补齐 GE parser 无法解析或无原生实现的算子（**功能补齐向**：图跑不起来直接进入本条目），完成「实现 → 算子包部署 → 图接入」全链路。性能替换型必须走条目 10 → 11。

**输入**：含无法解析/无原生实现算子的模型。

**输出**：算子工程源码 + DESIGN.md（强制）+ `test_*.py` + benchmark + GE 接入说明（部署与环境注入配置）。

**执行步骤**：
1. 方案设计：算法规格（shape/dtype/公式/FLOPs）、分解策略（Cube 段 / Vector 段），输出 DESIGN.md。
2. 实现路径（先组合后下沉）：v1 优先现有算子组合 / 脚本改写（pytorch/hf 输入）验证语义；不满足再下沉自定义算子（语言按平台路由）。
3. GE 接入：算子包编译部署（经 `ASCEND_CUSTOM_OPP_PATH` 或模型环境 `M<id>_env.sh` 注入）；onnx 输入经 GE 内存图 pass 插入对应节点（**不改原图**，命名与注册信息严格一致）；pytorch/hf 输入经脚本注册接入。
4. 精度门禁（强制）：golden 真源为 CPU 参考实现；用例覆盖 batch/动态维/边界；按 dtype atol/rtol 判定，全量通过后才进性能阶段。
5. 性能门禁（强制）：底线不低于原等价算子串；达标按 Roofline（有效 TFLOPS 或带宽利用率 ≥ 0.8，峰值取实测锚定）；未达标输出瓶颈分析。
6. 交付件清单核验 + 端到端双门禁（vs v1 组合与改动前整图分别对比）。

**承接 skill**：`model-recommend-custom-op-development`

## 13. 运行时问题诊断（贯穿全流程）

**目标**：任一环节报错/卡死时按标准路径快速定界修复，不阻塞主流程。本条目不被顺序调用，而是在 0-14 任一环节出现故障时插入。

**输入**：故障现象（有明确报错 / 无输出卡死）。

**输出**：修复方案；案例沉淀为可检索的排查记录。

**执行步骤**：
1. 有明确错误：error.log（`GE_ERROR_LOG`）+ plog（`--info` 等级 2 / `--debug` 等级 0，自动落 report/）→ 按类别归因：初始化失败（PYTHONPATH）/ onnx 解析失败（自定义算子、非标 domain → 条目 12）/ dtype 越界 / aicore timeout（二分法定位）/ OOM（降 `GRAPH_MAX_PARALLEL`/`THREAD_NUM`/batch）/ shape 不匹配 / aclnn 错误码（环境/Tiling/Kernel 三类）。
2. 无明确错误：npu-smi 状态判定（有进程 + HBM 不变 + CPU 高 = 建图编译中；HBM 不变 + CPU 0 = hang → 查残留 → plog；0 进程 → error.log）。
3. 修复实施；若改动模型执行（图/配置/选项/算子），同样过双门禁后才关闭案例。
4. 同类错误二次出现按路径直达根因；排查记录回写 `model-recommend-runtime-debug` skill。

**承接 skill**：`model-recommend-runtime-debug`

## 14. 优化回归验收与基线管理（收口环节）

**目标**：建立统一基线与逐项验收机制，管理所有优化开关；收口产出最终优化报告与下一步动作表（下一轮执行入口）。

**输入**：全部已实施优化项与台账。

**输出**：最终配置（= 已验收项组合）、`final_optimization_report.md`、`next_actions.json`、全量回归结论。

**执行步骤**：
1. 基线标准化：每阶段 `baseline_metadata.json`（配置 + 输出摘要 + 性能数据 + 采集命令与场景记录，保证可复现）。
2. 优化项台账：每个优化项登记（开关名/参数、默认状态、依赖前置项、验收数据、回退路径）。
3. 逐项验收门禁：精度（条目 4 verify 全 pass）+ 性能（条目 5 同口径对比）+ 功能一致（输出 shape/数值分布合理）三关全过才可合入；失败项回退并记录。
4. 变更触发重分析：场景 / batch / TP99 上限变更 → 重做条目 3；CANN / 框架版本变更 → 重采全量基线；图 / 配置变更 → 重跑受影响项验收。
5. 经验沉淀：新算子约束、等价改写陷阱、排错案例按模板回写对应 skill。
6. 下一步动作表产出（来源六类逐类核对，见「下一步动作表规则」）。
7. 收口核验：任意优化项可单独开关并复现收益；每笔改动有双门禁记录；perf_ledger 完整覆盖所有已执行条目；最终报告与动作表已产出。

### 下一步动作表规则（强制）

每行字段：优先级（P0/P1/P2）/ 优化动作（具体可执行，禁止空话）/ 手段类型 / 依据（可追溯数据源）/ 预期收益（量化区间 + 推导方法，不与已实施项重复计算）/ 置信度 / 对应工作流（条目 + skill）/ 前置依赖。排序依据 = 预期收益 × 置信度 ÷ 实施成本。

动作来源六类逐类核对（缺失须说明）：① 条目 10 未实施候选；② 台账回退项（含重试条件）；③ 未实施机会；④ 条目 5 四项专项 findings；⑤ 条目 7 未适配项；⑥ 框架需求（标注移交，不入执行队列）。空表必须给出理由。

**承接 skill**：`model-recommend-regression-baseline-mgmt`

## 持续优化循环

首轮线性执行 0→14 后，按「选动作 → 执行优化（双门禁）→ profiling 采集 → 深度分析（四项专项）→ 收益判定 → 终止检查 → 动作表更新」迭代。编排契约见 `model-recommend-optimization-loop`，判定细则见 [`references/loop-rules.md`](references/loop-rules.md)。

**终止条件（满足其一）**：

1. 达到指定性能目标：目标指标（用户指定 avg/TP99/QPS 阈值）连续 2 次同口径复测达标。
2. 连续 3 轮无收益（主指标改善 ≤ 噪声带；回退轮计入，纯分析轮不计但连续 2 轮无新候选触发安全阀）。
3. 安全阀：无可执行动作 / 轮次预算上限（默认 10 轮）。

循环状态落 `data/{model_name}/optimization_log/loop_state.json`（支持中断后幂等恢复），schema 见 [`templates/loop-state-schema.json`](templates/loop-state-schema.json)。每轮纪律：**一轮一动作**（归因唯一）、双门禁全程有效、同口径复测、四项专项必做且优化点并入动作表、交付件当轮同步更新（台账实时写、每轮性能报告当轮落盘、workflow_status.md 当轮更新、禁止事后批量补写）。

**性能目标必须由用户指定**（`目标指标` + `方向与阈值`，如 `avg ≤ 1.0ms`、`QPS ≥ 1500`）；缺失时向用户确认，禁止自行设定。噪声带未测定则首轮先测。

## 参考文档索引

- **双门禁判定细则（精度/性能/噪声带/取舍声明）**：[`references/gate-rules.md`](references/gate-rules.md)
- **外部依赖全量清单（25 项 + 获取方式 + 缺失处置）**：[`references/external-dependencies.md`](references/external-dependencies.md)
- **内置框架说明（目录布局、使用方式、维护约定）**：[`../framework/README.md`](../framework/README.md)
- **循环终止、重采与重分析触发、幂等恢复**：[`references/loop-rules.md`](references/loop-rules.md)
- **产物目录与台账/动作表/状态表结构**：[`references/artifact-conventions.md`](references/artifact-conventions.md)
- **Subagent prompt 模板与派发字段**：[`references/subagent-prompt-templates.md`](references/subagent-prompt-templates.md)
- **每轮性能报告模板**：[`templates/performance-report-template.md`](templates/performance-report-template.md)
- **工作流执行状态检查表模板**：[`templates/workflow-status-template.md`](templates/workflow-status-template.md)
- **台账与循环状态 schema**：[`templates/perf-ledger-schema.json`](templates/perf-ledger-schema.json)、[`templates/loop-state-schema.json`](templates/loop-state-schema.json)
- **循环状态辅助脚本（幂等恢复与对账）**：[`scripts/loop_state.py`](scripts/loop_state.py)（`next` / `check` / `init` / `migrate`）
- **内置框架工具**（`framework/GE_SESSION_DEMO/tools/`）：`prepare.sh --input-shape` / `prepare_input.py --input-shape`（显式指定动态维，缺失即报错；`GEN_INPUT_SHAPE` 亦可）、`verify.py`（`--gate` 逐输出精度门禁）、`check_provenance.py`（模型/输入/标杆指纹，`--write` 记录、默认比对）、`sweep.py`（限核/并发/batch 三阶段扫描）
