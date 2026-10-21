# ReLU 算子需求（PyPTO 实现）

## 功能描述

逐元素 ReLU 激活：

```text
out[b, d] = max(x[b, d], 0)
```

## 输入输出规格

**输入**：

| # | name | shape | dtype |
|---|------|-------|-------|
| 0 | `x0` | `[16, 16384]` | `float32` |

**输出**：

| # | name | shape | dtype |
|---|------|-------|-------|
| 0 | `y0` | `[16, 16384]` | `float32` |

- 动态轴：`B`（batch 维，shape 第一维需支持动态）。

## 数值精度容差

- `rtol = 1e-3`，`atol = 1e-3`（float32）。
- 验证通过条件：精度测试脚本输出全量 `all_close: true`。

## 性能目标

- 硬性目标：`perf_target_us = 2.85`（参考基线：Ascend 910B3 上
  `torch_npu.profiler` 实测，warmup=3、runs=5）。
- 调优轮次：`tune_rounds = 3`。

## 接口约定

- 导出 `relu_wrapper(...) -> torch.Tensor`；
- 调用面分两段：构造参数由 `get_init_inputs()` 给出、前向输入由
  `get_inputs()` 给出，外层以 `Model(*get_init_inputs()).forward(*get_inputs())`
  约定调用；
- 若 wrapper 需要消费 init 参数，由外层包装类的 `__init__` 保存并在
  `forward` 内按正确顺序转发；不要求调用方把 init 参数和前向输入拍平成
  一个外部调用接口。

## 开发约束

1. golden / impl / test 三文件分离；
2. 输入 / 输出 dtype 与上述规格一致；
3. 设备号由调用方以 `device_id` 指定（缺省按 `TILE_FWK_DEVICE_ID` 或默认
   设备执行）。
