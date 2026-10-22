---
id: PRC-SIMT-003
name: SIMT 写冲突处理——原子加分级归约或分组单写者
category: SIMT
applies_to: dav-3510（Ascend 950PR/950DT）kernel 侧；多线程可能写同一地址的 SIMT 算子（直方图/Scatter/计数类）
status: ready
---

# PRC-SIMT-003：SIMT 写冲突处理——原子加分级归约或分组单写者

## 知识点

grid-stride 并行化后，多线程写同一目标地址即数据竞争：普通写会丢更新且结果不可复现。两种确定性方案按语义选：①**规约语义**（Add/Max 等，直方图/计数）：用原子操作，且分级归约摊薄冲突——每 Warp 一份独立 UB 副本承接高频 `asc_atomic_add`，块内跨 Warp 求和后再一次性原子写 GM，冲突域从全局缩到 Warp 内；②**覆盖语义**（Scatter，last-writer-wins）：不用原子写（原子写也不保证"最后一个"是谁），改为输入按 (dst, 原始位置) 预排序使同目标行连续，kernel 只让每组末行线程写出（单写者），无锁且结果确定。精度红线：`asc_atomic_add(__gm__ half*)` 存在但每次累加都舍回 fp16，累加次数多时误差累积，累加类慎用 fp16 原子加（fp32 累加或改分块归约；amin/amax 无此问题）。

## 错误写法

```cpp
// 反例：重复 index 下所有命中线程都直接写 y[dst]，多写者无序覆盖，结果不可复现
// simt_scatter_story/src/0_direct_unique.asc:30-39（cann-samples@6e6260c8；该版仅在 index 唯一时正确）
for (int32_t row = rowTid + coreId * rowThreadNum; row < updateRows; row += coreNum * rowThreadNum) {
    int32_t dst = indices[row];
    if (dst < 0 || dst >= dstRows) { continue; }
    ...
    for (int32_t col = colTid; col < innerDim; col += colThreadNum) {
        y[dstOffset + col] = updates[srcOffset + col];   // 冲突写，无仲裁
    }
}
```

## 正确写法

```cpp
// 正例 A（规约语义）：Warp 级 UB 副本原子累加 → 块内合并 → 原子写 GM
// simt_histogram_story/src/1_basic_simt.asc:61-96（cann-samples@6e6260c8；节选，
// 清零段省略——原样例清零后与归并前各有一次 asc_syncthreads()，两处栅栏都不能省）
__ubuf__ OutType warpHistos[WARPS_PER_BLOCK][PADDED_BINS];       // 每 Warp 一份，缩小冲突域
// ...多线程清零 warpHistos... 然后：
asc_syncthreads();                                                // 栅栏①：清零完成后才能开始累加
    asc_atomic_add(warpHistos[warpId] + idx, 1);                  // 高频更新只打本 Warp 副本
asc_syncthreads();                                                // 栅栏②：全部累加完成后才能跨 Warp 归并
for (int32_t i = tid; i < bins; i += blockThreads) {
    OutType sum = 0;
    for (int32_t w = 0; w < WARPS_PER_BLOCK; w++) { sum += warpHistos[w][i]; }
    asc_atomic_add(y + i, sum);                                   // 每 bin 每 Block 仅一次 GM 原子加
}
// 正例 B（覆盖语义）：预排序后仅组尾行写出，每目标行单写者
// simt_scatter_story/src/1_grouped_conflict.asc:30-31
bool isLastInGroup = (row == updateRows - 1) || (dst != indices[row + 1]);
if (!isLastInGroup || dst < 0 || dst >= dstRows) { continue; }
```

## 识别方法

- 看什么：SIMT 循环体内目标地址含运行期索引（`y[indices[i]]`、`hist[idx]`）的写操作；写的是普通赋值、`asc_atomic_add` 还是带单写者判定。
- 命中条件：写地址由数据决定且多线程可达同一地址，而代码用普通写（覆盖语义下还缺排序+单写者仲裁）；或规约语义下每次更新都直接原子写 GM（无 UB 分级，全局冲突域+GM 原子延迟）；或 half 类型走 `asc_atomic_add` 做长链累加。
- 误报边界：①index 由构造保证唯一（如上游去重/一一映射，需指出保证来源）时直接写是对的；②冲突率极低且性能达标时，分级归约的额外 UB 与合并开销可能不划算——只在有 profiling 或冲突率论据时才建议；③覆盖语义算子若输入未排序，加"排序预处理"本身可能成新瓶颈，finding 须连预处理成本一起评估。

## 证据要求

- 命中处 文件:行号 与摘录（冲突写语句），并写明判定为竞争的依据：索引值域与线程映射为何允许两个线程算出同一地址。
- 语义判定：该算子是规约语义还是覆盖语义（引用算子定义/golden 语义），据此说明推荐方案 A 还是 B。
- 排除误报：说明为何不存在"index 唯一"的上游保证；fp16 原子加命中时给出累加链长估算。

## 参考

- cann-samples：`Samples/2_Performance/simt_histogram_story/src/1_basic_simt.asc`、`Samples/2_Performance/simt_scatter_story/src/0_direct_unique.asc` vs `1_grouped_conflict.asc`
- 关联：并行化来源 PRC-SIMT-002；组尾判定的两判据拆法同 PRC-SIMT-006；列维并行化见 PRC-SIMT-005
