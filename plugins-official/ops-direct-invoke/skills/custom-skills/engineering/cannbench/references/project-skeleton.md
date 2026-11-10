# direct launch 工程骨架

## 获取与复用

优先使用本轮输入指定的 cann-bench checkout；插件依赖位置为 `<目标仓>/.cannbot/dependencies/ops-direct-invoke/cann-bench/`。读取其 commit 与 `examples/direct_launch_example/README.md`。来源缺失时，取得官方仓库到一个新目录并记录版本，不从文档中的省略代码拼造工程；下载和依赖准备不能阻塞首次需求问卷。

新建工程时将 `examples/direct_launch_example/` 复制到已授权的 `source_dir`。现有工程只引入缺失部分，保留原来的算子和用户改动。官方示例源码与许可头一并保留；新增代码也带仓库 license 头，Python 输出使用 logging。

## 应保留的文件

```text
source_dir/
├── build.sh
├── setup.py
├── CMakeLists.txt
├── cmake/                      # func、ascend、python、torch、torch_npu
├── scripts/build_wheel.sh
├── cann_bench/__init__.py       # 加载 _C，导出候选函数
├── csrc/extension.cpp
├── csrc/CMakeLists.txt
├── csrc/ops/CMakeLists.txt      # 自动发现算子目录
├── csrc/ops/<op>/
│   ├── CMakeLists.txt
│   ├── op_kernel/
│   └── op_plugin/
└── tests/                      # pytest 仅作本地快速自检
```

`cann_bench` 包名和导出接口是 CANN 评测输入的一部分，不做统一重命名。保留双编译器设置、平台映射、链接依赖和 ABI3 打包；不要用手写的近似 CMake/setup.py 取代现成工程。是否保留 Add/Sqrt 示例依据本次交付范围决定；在新复制的工程中去除示例时同步去除注册、Python 导出和对应测试，不能留下失效 import。

构建和评测在 `$WORK_DIR/<节点ID>-构建工程/` 的本轮源码快照执行，避免官方脚本把 `build/`、`_compile.log` 等中间文件写到交付源码中。快照记录来源与哈希，排除 `.cannbot/`，不递归复制本轮工作目录，也不包含旧 `build/`、`dist/`、`*.egg-info` 或本地 `_C*.so`；已完成的源码仍交付在授权目录，构建快照不作为第二份源码继续独立修改。

正式测试使用 cann-bench 任务目录与评测器；复制示例的 `tests/` 或执行其 `test.sh` 不能自动产生目标算子的完整评测用例。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；运行时记录实际 checkout 版本，版本变化时核对相关接口。

- [examples/direct_launch_example/README.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/direct_launch_example/README.md)
- [examples/direct_launch_example/setup.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/direct_launch_example/setup.py)
- [examples/direct_launch_example/CMakeLists.txt](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/direct_launch_example/CMakeLists.txt)
