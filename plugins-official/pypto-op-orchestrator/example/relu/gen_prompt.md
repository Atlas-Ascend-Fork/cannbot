# 用例事实与桥接约定：ReLU

> 本文件由调用方撰写（插件不渲染其内容），是三个预写输入之一。
> 内容格式自由，以下为示范写法。占位符：`<work_dir>` = 本次运行工作目录。

## 用例事实

- 算子名：`ReLU`
- 产物目录（$OP_DIR）：`<work_dir>/custom/ReLU/`
- 需求文档：`$OP_DIR/REQUIRE.md`（作为 Stage 1 的需求输入）
- 参考用例：`$OP_DIR/task_desc.py`（校准包装接口与输入生成）
- 数值容差：`rtol = 1e-3`，`atol = 1e-3`
- Stage 7 性能目标：kernel 时间 ≤ 2.85 us
- Stage 7 调优轮次：3

## 桥接约定

- 对外暴露 `relu_wrapper(...) -> torch.Tensor`；
- 调用面分两段：`Model(*get_init_inputs()).forward(*get_inputs())`；init 参数
  由包装类 `__init__` 保存并在 `forward` 内按序转发，不与前向输入拍平；
- Stage 5 除 `<op>_impl.py` 外，额外在同一目录产出 `ReLU_pypto_impl.py`
  （含 `ModelNew` 包装类），作为下游消费入口。
