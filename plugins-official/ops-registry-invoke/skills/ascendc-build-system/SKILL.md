---
name: ascendc-build-system
description: Ascend C 算子的构建与排错。用于编写或修改算子 kernel/host 代码、创建算子工程、改 CMakeLists.txt；排查构建失败、.o 产物缺失或数量不符、追踪 codegen 实际编译了什么；理解从 .cpp 到设备二进制的编译管线。
disable-model-invocation: true
---

# Ascend C 构建系统

## 心智模型

**真正的编译单元是副本。** 你打开的 `op_kernel/*_apt.cpp` 从不被直接编译：codegen 先生成 `<OpType>.py`，由它驱动 `asc_opc` 去编译源码副本。报错行号属于这条链路上的某一层，定位前先建立 source map——这个行号是哪一层的。

**`DTYPE_X` 是构建系统注入的宏。** 值由 `_param.json` 决定，编译时以 `-DDTYPE_X=float|half|bfloat16_t` 注入，源码里查不到它展开成什么。同一个 `.cpp` 按 dtype 数量编译多次，每次宏值不同。

**编译是二重枚举，外层 dtype、内层 TPL。** 外层来自 `op_host/*_def.cpp` 的 `.DataType({...})`，每个 dtype 产出一个 `.o`；内层来自 `op_kernel/*_struct.h` 的 `ASCENDC_TPL_SEL`，每行产出 `.o` 内的一个 sub-kernel。

```text
.o 数量       = 外层        = DataType 列表长度
sub-kernel 数 = 外层 × 内层 = DataType 列表长度 × ASCENDC_TPL_SEL 行数
```

## 完成判据

每次构建之后：

```bash
bash build.sh 2>&1 | tee build.log
python3 scripts/inspect_build.py build
```

两条都满足才算完成：

- `inspect_build.py` 退出码 0 且打印 `✅ COMPLETE`——`.o` 数量等于外层枚举数
- 它逐个打印的**每个** `.o` 的 sub-kernel 数，都等于内层枚举数

## 新建或修改算子工程

加载 **references/project-layout.md**：目录布局、三种命名形式（PascalCase / snake_case / UPPER_SNAKE）的对应关系、各关键文件的职责与写法、CMake 宏用法，以及按修改类型（改 dtype / 改 TPL / 改 kernel 逻辑）逐文件的检查清单。

改完跑完成判据。

## 构建失败

**失败现场会被清理。** codegen 产物（`<OpType>.py`、各 dtype 的 `_param.json`、`.sh` 编译脚本）只在构建失败时留存，一旦构建成功就被删除。先勘查现场，再改代码或重跑 build。

1. `python3 scripts/inspect_build.py build` —— 哪些 `.o` 缺失，即外层的哪个 dtype 编译失败
2. `python3 scripts/trace_codegen.py build` —— 现场：实际下发的 asc_opc 命令、注入的宏值、每个变体的 `_param.json`
3. 拿报错信息对照 **references/build-pipeline.md** 的调试决策树，定位失败在哪一层
4. 修复后跑完成判据

## 部署后验收

`build/` 是构建期产物，`vendors/` 是安装后产物。部署完（`./build.sh` 装包或 `custom_opp_*.run` 安装）要确认**安装到芯片侧的 `.o` 与构建期一致**——别只看 build 过了。

```bash
./scripts/inspect_kernel_binaries.sh <kernel_install_root>
# 例:
./scripts/inspect_kernel_binaries.sh \
  /home/developer/Ascend/cann-9.1.0/opp/vendors/<OpType>/op_impl/ai_core/tbe/kernel
```

脚本扫该目录下所有 `.o`，用同名 `.json` 读 dtype 与 `kernelList`，逐个报 sub-kernel 名与总数。判据：

- `.o` 数量 = 外层 dtype 枚举数（与 `inspect_build.py` 一致）
- 每个 `.o` 的 sub-kernel 数 = 内层 `ASCENDC_TPL_SEL` 行数

与 `inspect_build.py` 的差异：本脚本读**已安装**的 `vendors/.../kernel/`，不依赖 `build/`；适合装包后、或脱离源码树的环境上做最终核对。

## 理解管线

**references/build-pipeline.md**：5 层变换全图、9 个中间产物的路径与存活期、dtype→宏映射表、运行时 dispatch 的两级路由、`.o` 文件名的 MD5 生成规则、4 个脚本速查表、调试决策树。

**references/tiling-key-encoding.md**：`GET_TPL_TILING_KEY` 的位域编码机制、BOOL/UINT 两类参数的处理差异、sub-kernel 后缀 `_N` 的由来与空位成因、常见误解。
