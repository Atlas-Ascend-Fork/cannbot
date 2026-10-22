---
id: PRC-SIMT-002
name: 串行/单线程扫描改 grid-stride 多线程并行
category: SIMT
applies_to: dav-3510（Ascend 950PR/950DT）kernel 侧；SIMT kernel 及可改造为 SIMT 的标量遍历热点
status: ready
---

# PRC-SIMT-002：串行/单线程扫描改 grid-stride 多线程并行

## 知识点

标量单元逐元素遍历（`for (i = 0; i < N; i++)` + GetValue）吞吐极低且完全串行，是 Scalar bound 的典型来源。SIMT 的 grid-stride 范式把同一循环改写为 `for (i = globalTid; i < N; i += totalThreads)`：数千线程各扫一个跨步子序列，硬件 warp 调度在访存等待期切换线程掩盖延迟。simt_histogram Case 0→1 整体 11840→255.8us（**46.3x**）——该步是"SIMD(UB+GetValue 串行)→纯 SIMT"的整体切换，含 SIMT 化 + grid-stride + 每 Warp 独立直方图（PRC-SIMT-003）三项，46.3x 不能全额记到 grid-stride 单项；Bound 从 Scalar 99.9% 切到 Vector 99%。注意纯 SIMT（`__global__` 无 `__aicore__`、`--enable-simt` 编译、`<<<grid, block>>>` 启动）环境下 MTE/TPipe/TQue 均不可用：GM 直接解引用读取，UB 用 `__ubuf__` 静态数组声明，线程栅栏用 `asc_syncthreads()`——检视时不要按 SIMD 习惯要求它补 DataCopy/EnQue。

## 错误写法

```cpp
// 反例：Scalar 逐元素串行遍历 UB，一次只有一个标量在算（GetValue/SetValue 循环）
// simt_histogram_story/src/0_serial_scalar.asc:158-166（cann-samples@6e6260c8）
for (int32_t i = 0; i < TILE_DATA_LENGTH; i++) {
    XType val = xLocal.GetValue(i);
    if (val >= minVal && val <= maxVal) {
        int32_t idx = static_cast<int32_t>(static_cast<float>(val - minVal) * bins / minMaxRange);
        ...
        yLocal.SetValue(idx, yLocal.GetValue(idx) + 1);
    }
}
```

## 正确写法

```cpp
// 正例：grid-stride——每线程从 globalTid 起按 totalThreads 跨步，覆盖全量数据
// simt_histogram_story/src/1_basic_simt.asc:76-84（cann-samples@6e6260c8）
for (int32_t i = globalTid; i < totalLength; i += totalThreads) {
    float val = x[i];                      // 纯 SIMT：GM 直接解引用，无 MTE
    if (val >= minVal && val <= maxVal) {
        int32_t idx = static_cast<int32_t>((val - minVal) * binsF / range);
        if (idx == bins) idx = bins - 1;
        asc_atomic_add(warpHistos[warpId] + idx, 1);
    }
}
asc_syncthreads();                          // 后续归并前的线程栅栏
```

## 识别方法

- 看什么：①SIMD kernel 里 O(N) 的标量 GetValue/SetValue 遍历（配合 msprof scalar 占比高即热点）；②已是 SIMT 的 kernel 里，循环步长不含 `threadNum`/`totalThreads`（如固定 `i++` 或只按 blockIdx 切段但单线程扫段内）。
- 命中条件：遍历体内各次迭代无循环携带依赖（每次迭代只依赖自己读到的元素），或依赖可拆为独立判据（拆法见 PRC-SIMT-006）；数据量足以喂饱线程数（N 远大于 totalThreads）。
- 误报边界：①迭代间有真串行依赖（累积状态传递）不能直接改，先看 PRC-SIMT-006 能否拆判据；②N 很小（与线程数同量级）时并行收益被启动开销吃掉；③标量循环若操作的是连续规则数据，正解可能是矢量化（SIMD API）而非 SIMT，先按 PRC-SIMT-001 选路。
- 改写后多线程写同一位置的冲突必须同步处理，见 PRC-SIMT-003。

## 证据要求

- 命中处 文件:行号 与摘录（串行遍历循环），以及"无循环携带依赖"的逐变量说明（哪些变量是迭代局部的、哪些跨迭代）。
- 有 profiling 时给出 scalar 时间/占比佐证是热点；无 profiling 时给出遍历次数量级估算。
- 排除误报：说明 N 的量级与线程数关系；确认改写后不违反纯 SIMT 环境约束（PRC-SIMT-001 所列）。

## 参考

- cann-samples：`Samples/2_Performance/simt_histogram_story/src/0_serial_scalar.asc` vs `1_basic_simt.asc`（46.3x）
- 关联：写冲突处理 PRC-SIMT-003；线程/Block 配置调优 PRC-SIMT-004；串行依赖拆解 PRC-SIMT-006
