# 新增直调算子

采用 Tensor API 路线时，仍保留 direct launch 工程结构和 op_kernel/op_plugin 分层；API 分工、Layout、内存预算、构建和排障以 ascendc-tensor-api-best-practice 为权威源。

以当前 checkout 中 `examples/direct_launch_example/csrc/ops/add/` 或 `sqrt/` 的真实文件为结构参考，复制到 `source_dir/csrc/ops/<op>/` 后调整名称与实现，保留许可头。

| 文件 | 必须完成的内容 |
|------|----------------|
| `op_kernel/<op>_kernel.cpp` | Ascend C kernel、Tiling 与 `<<<>>>` 启动函数，bisheng 编译 |
| `op_kernel/<op>_launch.h` | g++ 可见的声明，保持参数、类型和 `extern "C"` 链接一致 |
| `op_plugin/<op>_plugin.cpp` | schema、Meta/输出分配、PrivateUse1 注册、当前设备 stream 与自有 kernel 调用 |
| `CMakeLists.txt` | 通过 `register_direct_launch_op` 注册源码和 include 目录 |
| `cann_bench/__init__.py` | 加载 `_C`，增加与目标函数匹配的 Python callable，转发到 `torch.ops.cann_bench` |

注册宏有四个参数：kernel 源文件、kernel include 目录、plugin 源文件、plugin include 目录。使用官方同版本示例中的调用，不能把它缩写成只有两个源码参数的伪接口。

schema 以本次任务 `proto.yaml` 的 `operator.schema` 为准：参数次序、可选值、attrs 默认值、输出结构都应一致。C++ 注册和 Python 导出同步更新；禁止保留示例的 Add/Sqrt 符号却声称实现了新算子。

包装层可以查询 shape/dtype、做参数和 Tiling 计算、分配输出、获取 stream 并启动 kernel；不在这里调用 Torch/CANN 内置算子代算，也不对输入输出做实质性搬运、类型转换或布局变换。Meta 只定义输出元信息，不执行目标计算。

API、Buffer、尾块、非对齐和 dtype 分派必须按目标算子验证。不能把示例只覆盖的类型和规模扩写成已支持范围；未知平台 API 用目标版本官方资料核实，缺少能力时记录限制。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；运行时记录实际 checkout 版本，版本变化时核对相关接口。

- [examples/direct_launch_example/csrc/ops/add/CMakeLists.txt](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/direct_launch_example/csrc/ops/add/CMakeLists.txt)
- [examples/direct_launch_example/csrc/ops/add/op_plugin/add_plugin.cpp](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/direct_launch_example/csrc/ops/add/op_plugin/add_plugin.cpp)
- [examples/direct_launch_example/cann_bench/__init__.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/direct_launch_example/cann_bench/__init__.py)
