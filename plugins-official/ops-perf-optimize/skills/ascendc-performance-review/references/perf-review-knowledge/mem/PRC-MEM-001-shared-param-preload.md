---
id: PRC-MEM-001
name: 共享只读参数循环外预加载
category: MEM
applies_to: 机制通用（各代 AI Core）；kernel 侧；适用于跨行/跨迭代共享只读参数（gamma/beta/scale 等）的算子；性能数字来自 dav-3510（rms_norm_quant_story，cannsim）
status: ready
---

# PRC-MEM-001：共享只读参数循环外预加载

## 知识点

归一化类算子的 gamma/beta、量化类的 scale 等参数对所有行都相同且只读。若放在行循环内每轮重复搬入，则每行都付一次冗余 MTE2 搬运（外加可能的 Cast 与队列调度），这些指令数随行数线性放大却不产生新信息。将其移到循环外一次搬入、常驻 UB 后，每行只剩 x 本身的搬运。rms_norm_quant（x[4096,8192] fp16）中 gamma 每行重复搬入共产生 4095 次冗余 MTE2，预加载后单步 1.13x（7693→6790us）。

## 错误写法

```cpp
// 反例（摘自 rms_norm_quant_story/src/0_naive.asc Process()）：
// gamma 与 x 无关却在每行循环内重复 CopyInGamma
for (int64_t loop = 0; loop < tilingData_->a; loop++) {
    CopyInGamma();   // 每行都搬一次相同的 gamma
    CopyInX(loop);
    Compute();
    CopyOut(loop);
}
```

## 正确写法

```cpp
// 正例（摘自 rms_norm_quant_story/src/1_preload_gamma.asc Process()）：
// 循环外一次搬入，gamma 常驻 UB
CopyInGamma();
for (int64_t loop = 0; loop < tilingData_->a; loop++) {
    CopyInX(loop);
    Compute();
    CopyOut(loop);
}
```

## 识别方法

在被检视源码中看：

1. 主处理循环（`Process`/`for (loop...)`）体内的 CopyIn 类调用，逐个核对其 GM 源地址是否随循环变量变化。源地址不含循环变量（如 `gammaGm_` 无 `[loop*...]` 偏移）即为共享参数重复搬入，命中。
2. 同一 LocalTensor 每轮 `AllocTensor/FreeTensor` 且内容不变的模式（配套的重复 Cast 也一并计入收益）。

误报边界（跷跷板判据）：共享参数体量大到挤压行处理空间时不应预加载——若常驻 gamma 占用的 UB 使每次可处理的行数/列块显著变小、反而增加 x 的搬运批次，预加载是负优化。检视时估算 `共享参数字节数 / 可用 UB`，占比高（如同量级于单行处理所需空间）且行循环本就受 UB 紧约束的，不报。已在循环外搬入、或参数逐行不同（如 per-row scale）的，不报。

## 证据要求

finding 必须给出：

- 循环内重复搬入处的文件:行号与摘录（含循环头，证明搬入在循环体内）；
- 该搬运 GM 源地址不随循环变量变化的依据（地址表达式摘录）；
- 排除误报的依据：估算共享参数占 UB 比例，说明预加载后仍有足够行处理空间。

## 参考

- cann-samples：`Samples/2_Performance/rms_norm_quant_story/src/0_naive.asc`（反例）、`1_preload_gamma.asc`（正例），单步 1.13x（cannsim，dav-3510）。
- 相关：官方"较小矩阵长驻 L1"（`atlas_ascendc_best_practices_10_0024`）为同思想的 Cube 版。
- 关联知识点：预加载后共享参数占 UB 的建模并入 PRC-MEM-005 的 ubFactor 方程 fixedSize 项。
