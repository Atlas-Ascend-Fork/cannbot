# 工程工作区与隔离验证

仅在验证 git 原生基线评估或共享代码保护时读取。git 模式验证真实工程仓的 worktree 流程（两个后端统一）；目录模式仅为 validator 对拍 oracle 验证。以下路径相对用户提供的仓库根，具体 revision 和 commit 身份在执行时记录，不把本机绝对路径写成依赖。

| 来源 | 场景 | 重点 |
|---|---|---|
| ops-nn | 选择有原注册测试入口的激活/归约算子 | 保留 host 注册、API 适配和公共 tiling/template 依赖 |
| ops-math | `math/` 中实际存在的算子或仓库 `add_example` 样例 | 自定义注册包、同名内置算子加载身份、独立构建闭包 |
| ops-transformer | `posembedding/inplace_partial_rotary_mul` | 多 tiling/架构分支与 opbase 公共依赖；不可只拷贝 arch35 kernel |
| 原有直调样例 | 用户指定的单算子 demo 或官方 kernel launch 样例 | 直调 ABI 不变，工程独立，无注册转换 |
| xllm-ops | `xllm_ops/layer_norm_fwd` | 多芯片共用 host/kernel；目标优化不得改公共函数、未涉及模式和模板 |

在当前可用的 xllm-ops 样本中，`layer_norm_fwd_def.cpp` 声明 ascend910b、ascend910_93、ascend950，kernel 同一文件包含 `__NPU_ARCH__ == 3510` 条件和多个模式。应按执行时源码重新核实，不能把已有宏当成所有改动都已隔离的证据。

基线评估（派发 2）正向验收：在 worktree 基线 commit 上以真实构建入口（repo-native 或 SDK 骨架）运行同一冻结功能子集，核对输出、tiling 分派和二进制来源；记录自定义包/直调两条路线的真实构建与运行结果；确认原工程目标分支与用户工作树零改动、staging 区无代码修改。目录模式仅验证对拍 oracle 的一致性（非交付路径）。

隔离负向验收：在 worktree/副本中故意修改公共 helper、非目标代际分支、用例未涉及模板或构建 source list，机器门禁（git 模式或目录模式）必须拒绝；只新增目标副本实现并在预先登记的分派范围内接线可以通过静态门禁，但还需真实构建及功能门禁。没有非目标硬件时只报告静态不变/可达证据，不声称完成该代际动态回归。

## 已核对的构建差异

本次可用 SDK 中有两套不同的自定义工程骨架：`tools/op_project_templates/ascendc/customize/` 使用 `cmake/config.cmake`、`opbuild` 与 CMake presets；`tools/new_op_project_template/custom_op/` 使用 `find_package(ASC)` 和 `npu_op_*`。这些是定位线索，实际运行时须重新读取当前 SDK 文件，不混用两套构建宏或假设 `msopgen` 一定可执行。

`ops-transformer/posembedding/inplace_partial_rotary_mul/op_host/CMakeLists.txt` 含按目标计算单元设置的编译选项，以及与可重定位 kernel 构建有关的分支。SDK 骨架接线时不仅要引用 host/kernel 源码，也要保留目标路由真正需要的编译选项和生成步骤；裸拷贝 `op_host/`、`op_kernel/` 不能证明构建语义等价。
