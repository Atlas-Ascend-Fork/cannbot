---
id: PRC-MEM-005
name: 小 DMA 合并为大搬运
category: MEM
applies_to: 机制通用（各代 AI Core）；kernel+tiling 侧；单次搬运 ≥16KB 才接近带宽峰值（官方带宽曲线）；性能数字来自 dav-3510（rms_norm_quant 1.11x cannsim；moe_init_routing 1.09x）
status: ready
---

# PRC-MEM-005：小 DMA 合并为大搬运

## 知识点

每次 DMA 有固定启动延迟，且单次搬运量小时带宽利用率低（官方带宽曲线：单次 ≥16KB 才接近峰值）。三种合并形态：①UB 装得下多行时按 `UB = fixedSize + ubFactor × linearCoef` 解出每批最大行数 ubFactor，`blockCount=ubFactor` 一条指令搬多行——rms_norm_quant 单步 1.11x（SCALAR -56%、MTE2 发起次数 -71%）；②源不连续只能逐行搬入、但目标 GM 连续时，在 UB 累积多行后一次大 DMA 写出，启动次数 2N→N+1——moe_init_routing 1.09x（mte3 21→2us）；③固定间隔多行用 `DataCopyParams(blockCount/blockLen/srcStride/dstStride)` 一条指令替代 for 循环逐次 DataCopy（官方 0015，指令数 16→1）。

## 错误写法

```cpp
// 反例（摘自 moe_init_routing_story/src/2_double_buffer.asc Process()）：
// 每行一进一出，2N 次小 DMA，启动延迟随行数线性累积
for (int64_t colsLoop = 0; colsLoop < colsLoops_; colsLoop++) {
    CopyXIn(xSrcOffset + colsLoopOffset, curLoopCols);   // 每行 GM→UB
    CopyXOut(xDstOffset + colsLoopOffset, curLoopCols);  // 每行 UB→GM
}
```

## 正确写法

```cpp
// 正例（摘自 moe_init_routing_story/src/4_ub_utilization.asc）：
// 源离散只能分批搬入，但目标连续 → UB 累积多行后一次搬出
CopyXIn(xSrcOffset + colsLoopOffset, xLocalOffset + colsLoopOffset, curLoopCols, xLocal); // 分批搬入
// ... 循环结束后
CopyXOut(curExpertLoopOffset * cols_, curLoopElements * cols_);  // 一次搬出
```

```cpp
// 正例（摘自 rms_norm_quant_story/src/5_ub_utilization.asc，host 建模 + blockCount 合并）：
int64_t fixedSize = rAlign * (sizeof(dataType) + sizeof(float)) + BLOCK_BYTES;
int64_t linearCoef = rAlign * (sizeof(dataType) * BUF_NUM + sizeof(outputType) * BUF_NUM) + sizeof(float);
int64_t maxUbFactor = (ubSize - fixedSize) / linearCoef;
// kernel: dataCopyParams.blockCount = ubFactor;  一条指令搬 ubFactor 行
```

## 识别方法

在被检视源码中看：

1. 主循环内 `DataCopy/DataCopyPad` 的单次字节数：远小于 16KB 且循环次数多，为候选。注意 blockLen 单位——`DataCopyParams.blockLen` 是 32B datablock 数（字节数 = blockCount×blockLen×32），`DataCopyExtParams.blockLen` 已是字节（字节数 = blockCount×blockLen，不再乘 dtype）。
2. `blockCount` 恒为 1 而 UB 明显装得下多行（估算 fixedSize+行大小×N vs UB 容量），命中形态①。
3. 循环内成对出现的搬入+搬出，核对目标 GM 地址是否随循环连续递增——连续则可累积一次搬出，命中形态②。
4. for 循环逐段 DataCopy 且各段等间隔——可用 srcStride/dstStride 一条指令表达，命中形态③。

误报边界：源与目标都离散且间隔不规则的（真随机 gather/scatter）无法合并，不报（考虑 SIMT 路线）；单行本身已 ≥16KB 的不报；UB 已被计算 buffer 占满、ubFactor 解出 ≤1 的不报（这正是方程的排除功能）；合并后单批过大挤掉双缓冲（深度 <2）是反向劣化，见 PRC-MEM-004 的 ping-pong 优先边界。

## 证据要求

finding 必须给出：

- 循环内搬运处文件:行号与摘录，单次搬运字节数计算式（按参数结构写明 blockLen 单位：Ext 为字节 / 非 Ext 为 32B 块）；
- 可合并性的依据：UB 余量估算（形态①）、目标地址连续性推导（形态②）或等间隔模式（形态③）；
- 排除依据：合并后仍能保住 ≥2 缓冲深度。

## 参考

- cann-samples：`Samples/2_Performance/rms_norm_quant_story/src/4_double_buffer.asc → 5_ub_utilization.asc`（1.11x）；`Samples/2_Performance/moe_init_routing_story/src/3_bandwidth_utilization.asc → 4_ub_utilization.asc`（1.09x）。
- 官方：`atlas_ascendc_best_practices_10_0013`（≥16KB 带宽拐点，优先级高）、`10_0015`（DataCopyParams 替代 for 循环）。
- 关联知识点：PRC-MEM-004（无法合并时加深缓冲）、PRC-MEM-001（共享参数计入 fixedSize）。
