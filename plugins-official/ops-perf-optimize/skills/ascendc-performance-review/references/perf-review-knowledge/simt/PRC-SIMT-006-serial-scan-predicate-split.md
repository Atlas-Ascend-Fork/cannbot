---
id: PRC-SIMT-006
name: 串行依赖扫描拆成无依赖判据并行
category: SIMT
applies_to: dav-3510（Ascend 950PR/950DT）kernel 侧；边界检测/分段统计类扫描（排序后计数、run-length、分组定界）
status: ready
---

# PRC-SIMT-006：串行依赖扫描拆成无依赖判据并行

## 知识点

"扫描并传递状态"的循环（如遍历排序后的专家 ID，用 `lastIndex`/`lastExpertId` 记录上一段起点、遇跳变时结算段长）存在循环携带依赖，既不可矢量化也不能直接套 grid-stride（PRC-SIMT-002）。但许多这类扫描的**每个位置的判定其实只依赖相邻元素**，可等价改写为无状态判据：段首 ⟺ `cur != prev`，段尾 ⟺ `cur != next`，段长 = 尾位置 − 首位置 + 1。每个判据都是逐元素独立的，可各用一个 SIMT kernel grid-stride 并行扫描（先并行写各段首下标，再并行在段尾处用 `尾下标+1−首下标` 结算计数）。moe_init_routing Step 4→5 用此改写直方图统计，局部耗时 20.267→8.447（**2.40x**）。本质是把"状态传递"重写成"相邻比较"，是串行扫描 SIMT 化的通用前置变换。

## 错误写法

```cpp
// 反例：lastExpertId/lastIndex 跨迭代传递状态，循环携带依赖只能标量串行
// moe_init_routing_story/src/4_ub_utilization.asc:583-597（cann-samples@6e6260c8）
int32_t lastExpertId = sortedExpertIdxInLocal.GetValue(0);
int32_t lastIndex = 0;
for (i = 1; i < curLoopElements; i++) {
    ...
    int32_t curExpertId = sortedExpertIdxInLocal.GetValue(i);
    if (curExpertId != lastExpertId || curExpertId >= expertEnd_) {
        expertCountOutLocal.SetValue(lastExpertId - expertStart_, i - lastIndex);
        lastIndex = i;                // 状态传递：下一迭代依赖本迭代结果
        lastExpertId = curExpertId;
    }
}
```

## 正确写法

```cpp
// 正例：拆成 cur!=prev（段首）与 cur!=next（段尾）两个独立判据，各自 grid-stride 并行
// moe_init_routing_story/src/5_simt.asc:467-500（cann-samples@6e6260c8，节选）
__simt_vf__ LAUNCH_BOUND(SIMT_THREAD_NUM) inline void ComputeExpertFirstIndexSimt(...) {
    for (auto i = threadIdx; i < elementNum; i += threadNum) {
        auto currExpertId = sortedExpertIdGmAddr[i];
        auto prevExpertId = (i == 0 ? -1 : sortedExpertIdGmAddr[i - 1]);
        if (currExpertId != prevExpertId) {                    // 判据 1：段首，无跨迭代状态
            expertFirstIndexLocalAddr[currExpertId - expertStart] = i;
        }
    }
}
__simt_vf__ LAUNCH_BOUND(SIMT_THREAD_NUM) inline void ComputeExpertCountOutSimt(...) {
    ...
        if (i == elementNum - 1 || currExpertId != sortedExpertIdGmAddr[i + 1]) {   // 判据 2：段尾
            expertCountOutLocalAddr[...] = i + 1 - expertFirstIndexLocalAddr[...];  // 结算段长
        }
}
```

## 识别方法

- 看什么：标量循环里跨迭代存活的"上一个值/上一个位置"变量（`last*`/`prev*`），其更新点在条件分支内；循环处理的数据是否已排序/分组（同段元素连续）。
- 命中条件：状态变量的语义可用相邻元素比较等价重建（段首/段尾/跳变点检测都可以），且数据已保证同段连续（排序或上游分组）——命中即可拆为独立判据并行。
- 误报边界：①真前缀依赖（如前缀和、携带进位）不能只靠相邻比较重建，属误报，需 scan 类算法而非本条；②两个判据 kernel 间有先后依赖（段长结算要读段首结果）时，两次 `VF_CALL` 顺序发射即可（同核顺序执行），但检视要确认没有把两判据塞进同一无同步 kernel 里读写竞争；③数据未排序时判据不成立，先确认上游排序保证再建议。
- 结算写入若落在共享缓冲，写者天然唯一（每段只有一个段尾线程），无需原子；若语义变为多写者则回到 PRC-SIMT-003。

## 证据要求

- 命中处 文件:行号 与摘录（含状态传递变量的循环），并写出状态变量到相邻比较判据的等价改写（段首/段尾判据各一行）。
- 前提证据：数据"同段连续"的来源（上游排序/分组代码位置）。
- 排除误报：说明该状态不是前缀累积量（或指出是、并标注本条不适用）。

## 参考

- cann-samples：`Samples/2_Performance/moe_init_routing_story/src/4_ub_utilization.asc` vs `5_simt.asc`（直方图局部 2.40x）
- 关联：并行范式 PRC-SIMT-002；scatter 组尾单写者判定是同一判据思想的应用 PRC-SIMT-003
