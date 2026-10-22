# 工程剥离与隔离验证

仅在验证前处理或共享代码保护时读取。原仓库只读，输出放临时独立目录；以下路径相对用户提供的仓库根，具体 revision 和文件 SHA 在执行时记录，不把本机绝对路径写成依赖。

| 来源 | 场景 | 重点 |
|---|---|---|
| ops-nn | 选择有原注册测试入口的激活/归约算子 | 保留 host 注册、API 适配和公共 tiling/template 依赖 |
| ops-math | `math/` 中实际存在的算子或仓库 `add_example` 样例 | 自定义注册包、同名内置算子加载身份、独立构建闭包 |
| ops-transformer | `posembedding/inplace_partial_rotary_mul` | 多 tiling/架构分支与 opbase 公共依赖；不可只拷贝 arch35 kernel |
| 原有直调样例 | 用户指定的单算子 demo 或官方 kernel launch 样例 | 直调 ABI 不变，工程独立，无注册转换 |
| xllm-ops | `xllm_ops/layer_norm_fwd` | 多芯片共用 host/kernel；目标优化不得改公共函数、未涉及模式和模板 |

在当前可用的 xllm-ops 样本中，`layer_norm_fwd_def.cpp` 声明 ascend910b、ascend910_93、ascend950，kernel 同一文件包含 `__NPU_ARCH__ == 3510` 条件和多个模式。应按执行时源码重新核实，不能把已有宏当成所有改动都已隔离的证据。

前处理正向验收：分别用原入口与剥离入口运行同一冻结功能子集，核对输出、tiling 分派和二进制来源；记录自定义包/直调两条路线的真实构建与运行结果。在不提供原仓库构建路径的环境下复验依赖闭包。

隔离负向验收：在物理副本中故意修改公共 helper、非目标代际分支、用例未涉及模板或构建 source list，机器门禁必须拒绝；只复制目标实现并在预先登记的分派范围内接线可以通过静态门禁，但还需真实构建及功能门禁。没有非目标硬件时只报告静态不变/可达证据，不声称完成该代际动态回归。

## 已核对的构建差异

本次可用 SDK 中有两套不同的自定义工程骨架：`tools/op_project_templates/ascendc/customize/` 使用 `cmake/config.cmake`、`opbuild` 与 CMake presets；`tools/new_op_project_template/custom_op/` 使用 `find_package(ASC)` 和 `npu_op_*`。这些是定位线索，实际运行时须重新读取当前 SDK 文件，不混用两套构建宏或假设 `msopgen` 一定可执行。

`ops-transformer/posembedding/inplace_partial_rotary_mul/op_host/CMakeLists.txt` 含按目标计算单元设置的编译选项，以及与可重定位 kernel 构建有关的分支。剥离时不仅要带走 host/kernel 源码，也要保留目标路由真正需要的编译选项和生成步骤；裸拷贝 `op_host/`、`op_kernel/` 不能证明构建语义等价。
