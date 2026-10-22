---
id: PRC-SIMT-005
name: 二维线程布局分摊行/列并行 + UintDiv 魔数替代整数除法
category: SIMT
applies_to: dav-3510（Ascend 950PR/950DT）kernel 侧；行×列两级结构的 SIMT 算子（Gather/Scatter 行拷贝类）
status: ready
---

# PRC-SIMT-005：二维线程布局分摊行/列并行 + UintDiv 魔数替代整数除法

## 知识点

行×列结构（外层离散选行、内层连续扫列）的 SIMT kernel，一维布局会让每线程串行扫完整行内层循环：行数少于线程数时并行度浪费，行内列数大时单线程拖长。二维布局把两级并行分开：x 维线程分行、y 维线程跨步扫列（如 moe_init_routing Gather 用 `Dim3{64, 32}`，scatter story 用 `Dim3{256, 8}`），同行内相邻线程访问连续地址还改善访存合并。另一个高频标量热点是循环体内的整数除法/取模（如 `rowIdx / k`）：除法指令延迟高且每线程每迭代都付一次，除数为运行期不变量时应在 VF 外一次性算出魔数（`GetUintDivMagicAndShift`），循环内用 `Simt::UintDiv(v, magic, shift)`（乘法+移位）替代。moe Step5（SIMT 实现，内含二维布局与魔数除法）相对 Step4 SIMD 版整体：scalar 23→4us、mte2 16.5→0.5us，68→60us（1.13x）——这是整机切换 SIMT 的数字（选路收益见 PRC-SIMT-001），二维布局/UintDiv 两项没有单项 A/B，不得把整体加速全额记到本条。

## 错误写法

```cpp
// 反例：一维布局，行内列循环由单线程串行扫完（col 从 0 递增，无线程跨步）
// simt_scatter_story/src/1_grouped_conflict.asc:28-38（cann-samples@6e6260c8）
for (int32_t row = tid + coreId * threadNum; row < updateRows; row += coreNum * threadNum) {
    ...
    for (int32_t col = 0; col < innerDim; ++col) {      // 整行由一个线程搬
        y[dstOffset + col] = updates[srcOffset + col];
    }
}
```

## 正确写法

```cpp
// 正例：x 维分行、y 维跨步扫列；行偏移用预算好的魔数快除
// moe_init_routing_story/src/5_simt.asc:670-688 + 806-808（cann-samples@6e6260c8）
__simt_vf__ LAUNCH_BOUND(SIMT_THREAD_NUM) inline void GatherOutSimt(
    int32_t curLoopElements, int32_t cols, uint64_t magic, uint64_t shift, ...) {
    auto threadIdx0 = static_cast<int32_t>(Simt::GetThreadIdx<0>());   // 行维
    auto threadIdx1 = static_cast<int32_t>(Simt::GetThreadIdx<1>());   // 列维
    for (auto i = threadIdx0; i < curLoopElements; i += threadNum0) {
        int64_t rowIdx = expandedRowIdxLocalAddr[i];
        // rowIdx / k * cols 的快除写法（magic/shift 由 VF 外 GetUintDivMagicAndShift 预算）
        int64_t xSrcOffset = static_cast<int64_t>(Simt::UintDiv(static_cast<uint64_t>(rowIdx), magic, shift)) * cols;
        for (auto j = threadIdx1; j < cols; j += threadNum1) {
            xLocalAddr[i * cols + j] = xGmAddr[xSrcOffset + j];
        }
    }
}   // 启动：Simt::VF_CALL<GatherOutSimt>(Simt::Dim3{SIMT_X_THREAD_NUM /*64*/, SIMT_Y_THREAD_NUM /*32*/, 1}, ...)
```

## 识别方法

- 看什么：`VF_CALL`/`asc_vf_call` 的 Dim3 是否只用了一维；VF 体内的嵌套循环内层是否为 `col = 0; ...; ++col` 单线程串行；循环体内的 `/`、`%` 运算及其除数是否为循环不变量。
- 命中条件：①外层行数 < 总线程数（并行度浪费）或内层列数大（单线程长尾），且内层循环无 `GetThreadIdx<1>` 跨步——建议二维布局；②每迭代执行的整数除法其除数在整个 VF 调用期不变——建议魔数快除。
- 误报边界：①内层列数很小（个位数）时二维布局的 y 维大多空转，收益有限，两维乘积仍受 Block≤2048 线程约束（PRC-SIMT-001）；②除数是编译期常量时编译器通常已自动做强度削减，`Simt::UintDiv` 只对运行期变量除数有意义；③覆盖语义 scatter 的组尾判定（isLastInGroup）必须留在行维判定（PRC-SIMT-003），列维只并行数据搬运，不能把仲裁逻辑摊进列维。

## 证据要求

- 命中处 文件:行号 与摘录（一维 Dim3 + 串行内层循环，或循环内除法语句）。
- 并行度核算：行数、列数与线程布局的乘积关系，说明当前布局浪费在哪一维。
- 排除误报：除法命中需写明除数为何是运行期不变量（来源于 tiling/attr）而非编译期常量。

## 参考

- cann-samples：`Samples/2_Performance/simt_scatter_story/src/1_grouped_conflict.asc` vs `2_grouped_conflict_2d.asc`；`Samples/2_Performance/moe_init_routing_story/src/5_simt.asc`（GatherOutSimt）
- 关联：选路边界 PRC-SIMT-001（H 大时 SIMD 多 Buffer 可能整体更优）；写冲突仲裁 PRC-SIMT-003
