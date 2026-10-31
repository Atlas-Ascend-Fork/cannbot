# 外部依赖清单（运行前提）

本工作流的 skill 只承担编排与判定，真正执行依赖机器环境。**onnx 路径的执行框架（GE_SESSION_DEMO）已随插件内置，工作流不引用任何外部链接**；pytorch / HuggingFace 路径不使用该框架，依赖模型自身脚本 + `torch_npu`。其余依赖为机器侧能力或用户数据资产。下表为全量清单，条目 0 必须逐项核对，缺失按 §3 处置矩阵处理，不得用「假设可用」替代自检。

> 标注：【实测】= 本机实际执行命令获取；【框架】= 内置框架文档声明。

## 1. 依赖总表

### A. 硬件与操作系统

| 编号 | 依赖 | 版本或要求 | 核对命令 | 缺失影响 | 获取方式 |
| --- | --- | --- | --- | --- | --- |
| A1 | NPU 设备 | Ascend910B 系列，容器内单卡可见，Health OK | `npu-smi info` | 全流程不可执行，条目 0 直接终止 | 硬件侧提供；`GE_DEVICE_ID` 指定卡 |
| A2 | 驱动与固件 | 与 CANN 9.1.0 匹配，`npu-smi` 可用 | `npu-smi info` | 设备不可见、GE 初始化失败 | 随 CANN 版本配套安装 |
| A3 | 操作系统与架构 | Linux aarch64（框架脚本自动适配 x86_64） | `uname -m` | 编译脚本取不到 CANN 库路径 | 标准镜像 |

### B. CANN 软件栈

| 编号 | 依赖 | 版本或要求 | 核对命令 | 缺失影响 | 获取方式 |
| --- | --- | --- | --- | --- | --- |
| B1 | CANN Toolkit | 9.1.0（aarch64-linux），`$ASCEND_HOME_PATH` 可解析 | `echo $ASCEND_HOME_PATH` | 全部编译与运行失败 | 随机器镜像安装；`source set_env.sh` |
| B2 | GE v2 运行组件 | `libge_runner_v2.so` 存在，含 `GeSession` / `RunGraphAsync` / `aclgrphParseONNX` | `ls $ASCEND_HOME_PATH/$(uname -m)-linux/lib64/libge_runner_v2.so` | onnx 路径无法执行；pytorch/HF 路径的 torchair 转 GE 同样依赖它 | 随 CANN Toolkit 安装；缺失即安装不完整，先修复 |
| B3 | `atc` 模型转换工具 | 可用 | `which atc` | 算子/模型转换类诊断与对照失效 | 随 CANN Toolkit 安装 |
| B4 | `msopgen` 算子工程生成 | 可用 | `which msopgen` | 条目 12 自定义算子无法建工程 | 随 CANN Toolkit 安装 |
| B5 | `msprof` profiling | 可用 | `which msprof` | 条目 5 四项专项无 profiling 数据，循环无法归因 | 随 CANN Toolkit 安装 |

### C. 编译工具链（编译执行框架与自定义算子）

| 编号 | 依赖 | 版本或要求 | 核对命令 | 缺失影响 | 获取方式 |
| --- | --- | --- | --- | --- | --- |
| C1 | `g++` | 支持 C++17（框架 `compile.sh` 用 `-std=c++17`） | `g++ --version` | `compile.sh` 失败，条目 0 第 3 步不通过 | 系统包管理器 |
| C2 | `nlohmann/json.hpp` | 单头文件 JSON 库 | `ls /usr/include/nlohmann/json.hpp` | `compile.sh` 失败（缺头文件） | `dnf install -y nlohmann-json-devel`（或对应发行版包名） |

### D. 执行框架（onnx 路径的标准入口，随插件内置）

> 仅 onnx 输入需要本节；pytorch / HuggingFace 输入走模型自身脚本 + `torch_npu`，不依赖 D1。

| 编号 | 依赖 | 版本或要求 | 核对命令 | 缺失影响 | 获取方式 |
| --- | --- | --- | --- | --- | --- |
| D1 | **GE_SESSION_DEMO** 执行框架（**仅 onnx 路径**） | 插件内置 `framework/GE_SESSION_DEMO/`（随插件维护）；project 级 `init.sh` 自动复制到工程根，global 级与统一安装器需手工复制 | `cd GE_SESSION_DEMO && bash compile.sh` 产出 `GEsession_test_acl` | onnx 路径不可执行（条目 0/1/2/5/6/7/8/9/11/12 依赖）；pytorch/HF 路径不受影响 | 见 §2：project 级自动复制；global 与统一安装器手工复制 |

### E. Python 侧（onnx 工具链 / pytorch 运行时 / golden）

| 编号 | 依赖 | 版本或要求 | 核对命令 | 缺失影响 | 获取方式 |
| --- | --- | --- | --- | --- | --- |
| E1 | Python 3 | 3.x，`python3` 在 PATH | `python3 --version` | `tools/*.py` 与 `prepare.sh` 全失败 | 系统安装 |
| E2 | `onnx`（**仅 onnx 路径**） | 参考值 1.22.0【实测】 | `python3 -c "import onnx; print(onnx.__version__)"` | onnx 路径无法解析模型，条目 1 结构档案缺失；pytorch/HF 不受影响 | `pip install onnx`（按环境可用源） |
| E3 | `numpy` | 与 onnx 配套 | `python3 -c "import numpy; print(numpy.__version__)"` | 输入构造、golden、数据分析脚本失效 | `pip install numpy` |
| E4 | `onnxruntime`（CPU 版，onnx 路径 golden） | 参考值 1.31.0（历史标杆口径）；当前环境未安装，可用用户标杆替代 | `python3 -c "import onnxruntime; print(onnxruntime.__version__)"` | `gen_golden.py` 无法生成 golden；条目 4 精度门禁只能依赖用户提供 `reference/` | `pip install onnxruntime`（按环境可用源） |
| E5 | `torch` / `torch_npu` | 参考值 torch_npu 2.9.0.post6；**pytorch/HuggingFace 路径的执行与采集基座**（`torch_npu.profiler`）；onnx 路径仅作辅助（torchair 未编译，不是 onnx 执行路径） | `python3 -c "import torch_npu; print(torch_npu.__version__)"` | pytorch/HF 路径无法执行与采集；onnx 路径仅影响辅助小工具 | 随 CANN 版本配套安装 |

### F. 算子开发与参考实现

| 编号 | 依赖 | 版本或要求 | 核对命令 | 缺失影响 | 获取方式 |
| --- | --- | --- | --- | --- | --- |
| F1 | AscendC 算子开发能力 | 经 `msopgen` 生成的算子工程；A2/A3 平台标准路径 | `which msopgen` | 条目 12 无法产出算子 | 随 CANN Toolkit |
| F2 | `cannbot-dsl` | A5 平台推荐路径；**当前环境不可用**【实测】 | 按平台文档自检 | 仅影响 A5 平台的 DSL 写法；当前环境一律走 AscendC | 平台侧提供；不可用时按 F1 降级 |
| F3 | 算子参考实现 | 同名 skill `model-recommend-custom-op-development`、`model-recommend-fusion-operator-adaptation`、`model-recommend-flash-attention-fusion` 的判定与实现要点；机器侧算子库随 CANN 提供 | 目录存在性检查 | 条目 7/11/12 只能凭经验实现，风险升高 | 随插件与 CANN 提供，无需外部获取 |

### G. 用户提供的数据资产（非安装项）

| 编号 | 依赖 | 版本或要求 | 核对命令 | 缺失影响 | 获取方式 |
| --- | --- | --- | --- | --- | --- |
| G1 | 模型文件 | `model.onnx` + 外部权重（同目录），或 pytorch/HF 仓 | 文件存在且 `prepare_model.py` 可解析 | 无输入，工作流无法启动 | 用户提供 |
| G2 | 请求输入数据 | `input_data/*.npy` 或 `*.bin`；为空时 `prepare_input.py --gen-input` 可自动构造 | `ls input_data/` | 无法跑基线 | 用户提供或工具自动构造 |
| G3 | 精度标杆 | `reference/output_i.npy`（或 `.bin`）；缺失时用 CPU onnxruntime 生成 | 文件存在 | 无 E4 且无 G3 时无法建立精度门禁，条目 4 阻塞 | 用户提供或用 E4 生成 |

### H. 本地信息渠道（离线可用）

| 编号 | 依赖 | 版本或要求 | 核对命令 | 缺失影响 | 获取方式 |
| --- | --- | --- | --- | --- | --- |
| H1 | 内置框架手册 | `GE_SESSION_DEMO/README.md`（目录结构/工具/运行环境/能力表）、`doc/README_EN.md`、`framework/推荐推理GE方案部署指南.md` | 文件存在 | 框架行为只能靠试错 | 随插件内置，无需外部访问 |
| H2 | 经验沉淀 | 安装后 `skills/*/SKILL.md`（源仓 cannbot-skills `community/model/`）、`workflows/references/*.md` | 文件存在 | 判定依据不足 | 随插件内置 |
| H3 | `drawio`（可选） | 用于条目 1 结构图集产物（单文件多页） | 本机可打开 `*.drawio` | 图集产物改为文字/表格描述 | 桌面客户端或直接生成 XML |

## 2. 内置执行框架的位置与使用（onnx 路径）

**仅 onnx 输入适用本节；pytorch / HuggingFace 输入跳过**（改用模型自身脚本 + `torch_npu`，不需要 `compile.sh` 与 `nlohmann/json.hpp`）。框架随插件分发，不依赖任何外部下载。

| 项 | 内容 |
| --- | --- |
| 插件内路径 | `<插件目录>/framework/GE_SESSION_DEMO/` |
| 许可 | `framework/LICENSE`、`framework/NOTICE`（Apache License 2.0） |
| 安装行为 | `bash init.sh <project/global> <tool>` 时自动复制到 `./GE_SESSION_DEMO`（global 级复制到安装根目录），已存在则保留不覆盖 |
| 手工复制 | `cp -r <插件目录>/framework/GE_SESSION_DEMO <工程根>/GE_SESSION_DEMO` |
| 编译 | `cd <工程根>/GE_SESSION_DEMO && bash compile.sh`，产出 `./GEsession_test_acl` |
| 版本记录 | 目录布局与维护约定见 `framework/README.md`；安装后路径写入 `cannbot-manifest.json` 的 `framework_dir` |

**目录约定**：框架必须位于工程根，与 `docs/`、`data/`、`prof/`、`ops/`、`tmp/` 同级。

```text
<工程根>/
├── GE_SESSION_DEMO/           # 框架（编译与运行入口）
│   ├── README.md              # 主手册
│   ├── compile.sh             # 编译入口
│   ├── src/                   # C++ 运行层
│   ├── tools/                 # prepare_model / prepare_input / inspect_config / gen_golden / verify / sweep
│   └── models/M<id>/          # 框架自管理工作区（编号即 {model_name}）
├── docs/  data/  prof/  ops/  tmp/
```

**边界纪律**：框架属「只读依赖 + 允许新增组件」。新增图融合 pass 等写在 `src/` 并保持开关默认关闭；不得改写框架既有行为与脚本入口（会破坏跨模型可比性）。工程内新增或修改的组件须回写插件 `framework/GE_SESSION_DEMO/` 后随插件提交——框架唯一真源在插件内，工程内的只是安装副本。

**当前已知限制**

| 差异 | 影响 | 处置 |
| --- | --- | --- |
| 框架当前未包含 `src/graph_fusion_pass.{h,cc}`（无 FA / GELU 图融合 pass 实现） | 条目 7 的 FA 族融合无可直接复用的实现 | 按 GE graph pass API 在 `src/` 新增，图构建集成参考 `src/graph_build.cc`；实现后回写插件 `framework/GE_SESSION_DEMO/src/` 并过双门禁 |
| 手册为 `README.md` 与 `doc/README_EN.md`（无 `doc/DESIGN.md`） | 旧引用失效 | 统一引用 `GE_SESSION_DEMO/README.md`（运行环境第 10 章、能力表第 11 章） |
| `models/` 仅含 `M001_sample` 样例 | 新模型需按 `M<id>` 自建工作区 | 用 `prepare_model.py` 生成配置，不手工拷贝样例 |

## 3. 缺失处置矩阵

| 缺失项 | 处置 | 是否可继续 |
| --- | --- | --- |
| A1/A2 NPU 不可用 | 停止全部下游条目，报告环境问题 | 否 |
| B1/B2 CANN 或 GE v2 不完整 | 修复 CANN 安装，重跑条目 0 | 否 |
| B3/B4/B5 工具缺失 | 记录缺口；涉及条目标记为「能力受限」，产出中标注 | 部分 |
| C1/C2 编译失败 | 按 §1-C 补齐后重试；仍失败转条目 13 | 否（onnx 路径） |
| D1 框架缺失或被删改 | 从插件 `framework/GE_SESSION_DEMO/` 重新复制（自建 pass 需先备份 `src/`） | 否（onnx 路径） |
| E2/E3 缺失 | 补装；无法安装则模型分析降级为人工读图并显式声明 | 部分 |
| E4 缺失且无 G3 | 精度门禁无法建立 → 条目 4 阻塞，禁止进入优化循环 | 否（优化循环） |
| E5 缺失 | 仅 pytorch/HF 输入受影响，onnx 路径不受影响 | 是（onnx 路径） |
| F2 缺失 | 走 AscendC（F1） | 是 |
| G1/G2 缺失 | 无输入，工作流无法启动 | 否 |
