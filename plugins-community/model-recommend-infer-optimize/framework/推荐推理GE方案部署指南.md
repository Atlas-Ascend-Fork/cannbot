# 推荐推理GE方案部署指南

> GE_SESSION 在线推理部署方案指南
>
> 本文介绍 GE Session 在线推理方案（第 3～5、6～8 章），覆盖模型接入、精度验证、性能调优与交付。

## 目录

- [0. 文档说明](#0-文档说明)
- [1. 端到端总览](#1-端到端总览)
- [2. 环境与工程准备](#2-环境与工程准备)
- [3. GE Session 在线路径](#3-ge-session-在线路径)
- [4. 精度验证与标杆](#4-精度验证与标杆)
- [5. 自定义优化组件开发](#5-自定义优化组件开发)
- [6. 运行时与性能调优](#6-运行时与性能调优)
- [7. 自定义组件交付与工程实践](#7-自定义组件交付与工程实践)
- [8. 端到端实战 SOP](#8-端到端实战-sop)
- [9. 附录](#9-附录)

## 0. 文档说明

### 0.1 目的

本文说明：当客户只提供一个 `model.onnx`（没有输入样例、没有精度标杆、没有部署脚本）时，在昇腾上完成模型部署会遇到哪些问题，以及可以用哪些手段解决。解决手段按昇腾图引擎（GE）推理流水线的阶段组织：解析、图优化、算子内核、运行时执行。想直接上手，可先看第 8 章的端到端 SOP，再按需回看对应章节。

### 0.2 适用范围

- 昇腾 NPU 上的在线推理。
- 一个模型对应一个工作区，单设备执行。
- 覆盖 ONNX/TensorFlow 等 GE 可解析的模型格式。
- 不涉及模型训练、模型结构改写、权重修改。

### 0.3 术语

| 术语 | 含义 |
| --- | --- |
| GE | 昇腾图引擎（GraphEngine），负责图解析、图优化、算子选型、内核生成 |
| GE Session 在线 | 使用 `GEInitializeV2` + `ge::GeSession` + `RunGraphAsync`，模型在进程运行期解析和编译 |
| ONNX 插件（onnx_plugin） | 在图解析阶段把原始算子翻译成 GE 内部算子或子图 |
| 自定义 Pass（CustomPass） | 在图优化阶段改写图结构的自定义 Pass |
| AscendC | 昇腾算子内核的编程语言 |

### 0.4 部署方式

GE Session 在线路径在进程运行期解析和编译模型，模型接入完全由配置文件驱动，适合方案验证与压测。自定义插件、自定义算子等优化组件随进程加载，可先完成接入与性能调整，确认精度与性能后再固化交付。

---

## 1. 端到端总览

### 1.1 只给一个 ONNX 模型时的信息缺口

客户只提供 `model.onnx` 时，通常缺少以下信息：

| 缺口 | 带来的问题 |
| --- | --- |
| 没有输入样例 | 无法构造请求数据，无法确定实际 shape、batch、dtype |
| 没有精度标杆 | 无法判断 NPU 输出是否正确 |
| 没有场景说明 | 不知道动态维度取什么值、batch 多大 |
| 缺少外置权重文件 | `model.onnx` 依赖同目录的 `.data` 外部权重文件，缺少该文件时无法加载 |
| 没有环境信息 | 不知道 CANN 版本、芯片型号 |
| 没有性能目标 | 无法判断是否达到要求 |

这些缺口可以由工具和配置补齐，下文逐项说明。

### 1.2 推理流水线各阶段的问题与手段

模型从原始格式到设备执行，经过以下阶段：

```
图解析 Parse ──▶ 图优化/编译 Compile ──▶ 内核生成 Kernel ──▶ 运行时执行 Runtime
```

| 阶段 | 常见问题 | 对应手段 |
| --- | --- | --- |
| 解析 | 报错：不支持算子、未知 domain、opset 差异导致语义错误 | 自定义插件 |
| 编译/优化 | 能跑但慢、小算子多、无融合、数据格式转换多、int64 慢 | 自定义 Pass、官方融合、AutoFuse |
| 内核 | 报错：无对应内核、需要特殊 dtype/layout | 自定义算子 |
| 运行时 | 输入输出管理、内存、动态 shape、dump、profiling | 运行时配置、dump 与 profiling |

### 1.3 从“跑不通/跑不快”出发的决策路径

```
模型跑不通 / 跑不快
   │
   ├─ 解析报错：不支持算子 / 未知 domain ─────────▶ 自定义插件
   │
   ├─ 能解析能编译，但图中有可融合的子结构，
   │  官方融合覆盖不到 ─────────────────────────▶ 自定义 Pass
   │
   └─ 解析通过，但编译或运行时报错：无对应内核，
      或某组算子过慢且 Pass 无法表达 ────────────▶ 自定义算子
```

默认先用官方内置的解析、图优化和算子。只有在模型跑不通或跑不快时，才按“插件 → Pass → 自定义算子”的顺序引入自定义组件。

---

## 2. 环境与工程准备

### 2.1 环境初始化

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
```

需要确认：

| 检查项 | 方法 |
| --- | --- |
| CANN 是否可用 | `echo $ASCEND_HOME_PATH` 非空 |
| 芯片型号 | `npu-smi info`，A3 系列可用 `npu-smi info -t board -i <id> -c <chip_id>` |

C++ 侧使用系统头文件 `nlohmann/json.hpp`，首次编译前安装：

```bash
dnf install -y nlohmann-json-devel
```

### 2.2 工作区规划

推荐按模型划分工作区：

```
models/M<id>/
├── model/model.onnx
├── input_data/
├── config/
├── output/
├── reference/
└── .cache/
```

- 模型权重必须自包含。如果 `model.onnx` 使用 external data，生成配置时只需读图结构和 shape，运行 GE 时会重新完整加载权重。
- 不同模型的专用环境（例如自定义算子的库路径）放在 `models/M<id>/M<id>_env.sh`，运行该模型时自动 source，避免修改全局环境。
- 工作区统一为 `models/M<id>/`（一个模型一个目录），目录名与配置字段与本文档其余章节一致。

---

## 3. GE Session 在线路径

GE Session 在线路径的参考实现是 `GE_SESSION_DEMO`，基于 GE v2（`GeSession` + `RunGraphAsync`），模型接入完全由配置文件驱动，C++ 代码中不含模型分支。

### 3.1 运行层结构

| 文件 | 职责 |
| --- | --- |
| `src/main.cc` | 读取 `MODEL_ID`/环境变量，加载 `io_config`，`GEInitializeV2`/`aclInit`，建 Session、起线程、回收 |
| `src/common_util.{h,cc}` | 环境变量读取、JSON 判断、shape 打印、计时统计 |
| `src/io_config.{h,cc}` | `InputCfg`/`OutputCfg`/`IoConfig` 与加载、dtype 映射 |
| `src/input_data.{h,cc}` | 把 JSON 数值数组转换为 host 缓冲 |
| `src/graph_build.{h,cc}` | 由 `io_config` 生成 `INPUT_SHAPE`/`OUT_NODES` 与 hint，调用 `aclgrphParseONNX`/`aclgrphParseTensorFlow` 得到 `ge::Graph` |
| `src/inference_acl.{h,cc}` | 执行器：输入解析、`RunGraphAsync` 循环、统计、串行末轮输出落盘 |

### 3.2 运行时调用时序

```
main: GEInitializeV2 + aclInit
      ├─ new ge::GeSession(device)
      │  └─ BuildGraph: aclgrphParseONNX(model, INPUT_SHAPE, OUT_NODES)
      │     └─ AddGraph(graph_id=0) 重复 THREAD_NUM 次
      │        └─ 每线程 InferenceAcl.Execute()
      │           ├─ aclrtSetDevice
      │           ├─ ParseInput: batch_list -> host 张量
      │           ├─ Warmup: RunGraphAsync 一次（不计时）
      │           └─ 循环 CircleCount 次 RunGraphAsync + 等待回调
      ├─ 串行且末轮时落盘 output_i.bin / output_shapes.json
      └─ GEFinalizeV2 + aclFinalize
```

要点（行号基于 `GE_SESSION_DEMO` 当前版本，可能随版本变化）：

- 建图只解析一次，随后在同一个 `graph_id=0` 上按并发数重复 `AddGraph`（main.cc:190-198）。
- 输入张量以 `gert::kOnHost` 放置，H2D 拷贝由 GE 内部完成（inference_acl.cc:185）。
- warmup 单独执行一次触发编译，不计入统计；warmup 等待超时 120s，正式执行等待超时 300s（inference_acl.cc:260、306）。
- 输出只在“串行单并发（`THREAD_NUM=1`）+ 末轮 + `PrintOutput=True`”时落盘（inference_acl.cc:362-371）。

### 3.3 配置驱动

配置文件由工具生成，运行层只读配置，不解析 ONNX。

| 文件 | 生成者 | 作用 |
| --- | --- | --- |
| `model_config.json` | `prepare_model.py` | 记录 ONNX 输入输出清单、dtype、动态维、opset，只读参考 |
| `shape_config.json` | `prepare_model.py`，用户可改 | 动静态策略、batch、输出 shape 覆盖 |
| `batch_list.json` | `prepare_input.py` | 按 ONNX 输入顺序排列的内联数据 |
| `io_config.json` | `prepare_input.py` | 运行时唯一入口配置 |

`shape_config.json` 的 `mode`：

| mode | parser_shape | 是否传 INPUT_SHAPE |
| --- | --- | --- |
| `all_static` | 全部取运行时 shape | 是 |
| `all_dynamic` | 动态维填占位值（默认 -1） | 否 |
| `custom` | 按 `overrides`，未列出项回退 ONNX 动态维 | 是 |

`io_config.json` 是运行时唯一入口：`inputs[].parser_shape`/`hint_shape` 用于拼 `INPUT_SHAPE` 与 hint，`outputs[].name` 用于确定输出节点，`outputs[].shape`、`size_bytes` 等字段供工具校验。

### 3.4 运行入口与 GE 初始化参数

```bash
bash run.sh <model_id> [options]

--threads N        --cores "A|V"     --circle N      --debug-freq N
--device N         --batch N
--print-output     --no-print-output
--prof off|msprof|ge                 --verify
--graph-max-parallel N
--info             --debug           --dump_graph    --dump_data
--show             --help
```

`main.cc` 中设置的 GE 初始化参数：

| 参数 | 含义 |
| --- | --- |
| `ge.exec.deviceId` | 设备号 |
| `ge.exec.precision_mode` | `force_fp16` 或 `must_keep_origin_dtype` |
| `ge.exec.allow_hf32` | 是否允许 HF32 |
| `ge.aicoreNum` | 限核配置 |
| `ge.graphMaxParallelModelNum` | 图实例并行上限（默认 8，仅上限参考） |
| `ge.inputBatchCpy` | 置为 1 |
| `ge.exec.op_precision_mode` / `ge.fusionSwitchFile` | 可选 |

### 3.5 输入输出处理

支持的输入 dtype：`float32`、`float16`、`bfloat16`、`int32`、`int64`、`bool`。

| dtype | JSON 数值键 | C++ 容器 | GE dtype |
| --- | --- | --- | --- |
| float32 | `float_val` | `float` | DT_FLOAT |
| float16 | `float16_bits` | `uint16_t`（位模式） | DT_FLOAT16 |
| bfloat16 | `bfloat16_bits` | `uint16_t`（位模式） | DT_BF16 |
| int32 | `int32_val` | `int32_t` | DT_INT32 |
| int64 | `int64_val` | `int64_t` | DT_INT64 |
| bool | `bool_val` | `uint8_t` | DT_BOOL |

float16 与 bfloat16 以位模式传递，避免浮点往返。不支持的 dtype 在 `prepare_model.py` 阶段告警，在 `prepare_input.py` 阶段报错终止。

输出 shape 取自 `RunGraphAsync` 回调返回张量的实际 shape，用 `elem_bytes` 计算字节数后落盘，因此动态输出不依赖配置中写死的 shape。

---

## 4. 精度验证与标杆

本章使用的 `gen_golden.py`、`verify.py` 是 `GE_SESSION_DEMO/tools/` 下的工具。

### 4.1 标杆来源

`gen_golden.py` 从 `batch_list.json` 还原输入，用 CPU onnxruntime 推理，标杆写入 `models/M<id>/reference/output_i.npy`。

`verify.py` 的标杆解析顺序：

1. 用户提供的 `reference/output_i.npy`（其次 `.bin`）。
2. 用 onnxruntime 生成。
3. 报错。

### 4.2 没有标杆的情况

- 模型含自定义算子：onnxruntime 无法执行该算子，需要用户提供标杆。
- 模型使用 bfloat16：CPU onnxruntime 不可用，需要用户提供标杆。

### 4.3 比对口径

- 整型与 bool 精确相等。
- 浮点使用 `allclose`，默认 `rtol=atol=1e-3`。
- 对自定义算子等存在实现差异的浮点计算，可用余弦相似度，或将阈值放宽到 2e-3 量级，不要直接用 1e-3 判失败。

报告写入 `output/verify_report.json`（简述）与 `output/verify_table.log`（误差区间统计与误差最大的元素明细）。

---

## 5. 自定义优化组件开发

### 5.1 什么时候需要自定义插件

当 GE 解析器遇到无法识别的算子时报错时，需要开发自定义插件。常见两类原因：

- 算子来自第三方 domain 或客户自定义 domain，例如 `com.microsoft` 的 `Attention`、`MultiHeadAttention`、`SkipLayerNormalization`。
- 同一个 ONNX 算子在某个 opset 版本下属性变成了输入，而内置解析只覆盖了部分版本，例如 `ReduceSum`、`ReduceMax` 的 `axes`，`Shape` 的 `start/end`。

插件位于 ONNX 图解析的最前端，把原始算子翻译成 GE 内部图能理解的算子或节点组合，解决的是“模型能不能解析进来”。

### 5.2 什么时候需要自定义 Pass

模型能编译执行，但图结构还可以优化且官方融合覆盖不到时，需要开发自定义 Pass。Pass 只改图结构和组织方式，不改变算子的数学正确性。常见动机：

- 算子融合：把序列融合成一个复合算子，减少中间张量的全局内存往返。
- 模式替换：把小算子组合替换为等价的、算子更少或搬运更少的组合。
- 类型下压：在确认不溢出的前提下把 int64 运算降到 int32。
- 覆盖融合未处理的结构：内置融合引擎覆盖不到的特殊子图。

### 5.3 什么时候需要自定义算子

出现下列情况时，需要开发自定义算子：

- 昇腾算子库没有该计算，不实现就无法编译通过。
- 把需要多个基础算子拼出来的复合计算做成单个算子，省掉中间张量落全局内存的开销。
- 内置算子不支持特殊的 dtype、布局或精度语义。
- 需要满足特殊约束，例如搬运类算子的确定性实现。

决策顺序：先确认官方算子库确实没有，再确认无法用内置算子组合加 Pass 替代，最后才自行实现。生产级算子要保证多核切分的正确性，成本较高。

---

## 6. 运行时与性能调优

### 6.1 编译期参数

| 参数 | 作用 |
| --- | --- |
| `ge.aicoreNum` | 限核，控制 AIC/AIV 核数 |
| `ge.graphMaxParallelModelNum` | 图实例并行上限 |
| `ge.exec.precision_mode` | `force_fp16`、`must_keep_origin_dtype` 等 |
| `ge.exec.allow_hf32` | 是否允许 HF32 |
| `ge.fusionSwitchFile` | 融合开关文件 |
| `ge.inputBatchCpy` | 批拷贝开关 |

### 6.2 性能采集

- 单次时延、QPS、TP99/TP999 由运行日志输出。
- `sweep.py` 做限核、并发、batch 扫描，产物为 CSV 与 Markdown。

### 6.3 瓶颈判定

常用指标：

| 指标 | 含义 |
| --- | --- |
| `aic_mac_ratio` | Cube MAC 利用率，偏低说明计算稀疏 |
| `aic_mte2_ratio` | HBM 数据加载占比，偏高说明访存瓶颈 |
| `cube_utilization` | Cube 忙碌率 |
| 设备算子耗时和 / 迭代耗时 | 例如小于约 90% 时，通常说明是调度/Host bound |

针对调度 bound（小算子多、单算子耗时短），优先考虑开启算子自动融合（AutoFuse）和用 Pass 融合重复子结构。针对算力 bound，考虑矩阵乘重组和数据格式优化。

### 6.4 调试手段

| 开关 | 作用 |
| --- | --- |
| `--info` / `--debug` | 打开 GE plog，普通/DEBUG 日志 |
| `--dump_graph` | 导出图结构（`DUMP_GE_GRAPH`、`DUMP_GRAPH_LEVEL`、`PRINT_MODEL`） |
| `--dump_data` | 开启 GE 数据 dump |
| `--prof ge\|msprof` | 采集 profiling |

---

## 7. 自定义组件交付与工程实践

### 7.1 vendor 目录与安装顺序

- 自定义插件：`.so` 放到 `opp/vendors/<vendor>/framework/onnx/`，或用 `ASCEND_CUSTOM_OPP_PATH` 挂载。
- 自定义 Pass：`.so` 放到 `opp/vendors/<vendor>/custom_fusion_passes/`。
- 自定义算子：用 `.run` 安装包安装到 `opp/vendors/`，与配套插件一起交付。

### 7.2 版本与兼容

- 不同 CANN 版本下算子头文件可能变化，换版本时需按该版本重新编译插件/算子。
- 插件编译的 ABI 必须与 `libgraph.so` 一致。
- 多个独立插件产物可能同名，需要评估 `ASCEND_CUSTOM_OPP_PATH` 顺序或合并 vendor。

### 7.3 可复现与隔离

- 运行目录限定在模型工作区 `.cache` 内，GE 产物不落到根目录。
- 模型专用环境通过 `M<id>_env.sh` 注入，不修改全局环境。
- 临时区有清理和保留策略：`.cache/run` 每次启动清理（同配置重复扫描时保留编译结果供复用），`dump_graph` 与 `dump_data` 各保留最新 3 份，profiling 产物不限制。

---

## 8. 端到端实战 SOP

### 8.1 跑通

```bash
# 1. 放置模型与输入
#    models/M<id>/model/model.onnx
#    models/M<id>/input_data/<ONNX 输入名>.npy

# 2. 分析模型
python3 tools/prepare_model.py <id>

# 3. 按需编辑动静态策略
vi models/M<id>/config/shape_config.json

# 4. 规范化输入
python3 tools/prepare_input.py <id>

# 5. 编译
bash compile.sh

# 6. 运行
MODEL_ID=<id> bash test.sh
```

### 8.2 跑不通

```
打开 --info/--debug 日志
  → 定位报错算子
  → 判断是未知 domain/opset 差异，还是无对应内核
  → 未知 domain/opset：写或安装 ONNX 插件
  → 无对应内核：写或安装自定义算子，并配套插件
  → 重新运行
```

### 8.3 跑不快

```
--prof 或 dump_graph 采集
  → 判断瓶颈类型（调度 bound / 算力 bound / 访存 bound）
  → 调度 bound：开启 AutoFuse，叠加融合/重组 Pass
  → 算力 bound：矩阵乘重组、数据格式优化（NZ + MatMulV3）
  → 类型问题：int64 降为 int32
  → 用 sweep.py 扫描限核、并发、batch
  → 复测并对比
```

### 8.4 精度不过

```
dump_data 逐算子比对，定位第一个出现偏差的算子
  → 检查精度模式（force_fp16 / must_keep_origin_dtype / allow_hf32）
  → 检查算子语义（例如 mask 维度、负索引、空 axes）
  → 必要时用插件修正语义
  → 重新验证
```

---

## 9. 附录

### 9.1 资料位置

| 主题 | 位置 |
| --- | --- |
| GE Session 在线推理 demo | 本目录 `framework/GE_SESSION_DEMO/`，主手册 `GE_SESSION_DEMO/README.md` |
| 自定义算子 / 插件 / 融合 Pass 参考实现 | 同名 skills `model-recommend-custom-op-development`、`model-recommend-fusion-operator-adaptation`、`model-recommend-flash-attention-fusion` |
| 环境与依赖核对 | 本插件 `workflows/references/external-dependencies.md` |