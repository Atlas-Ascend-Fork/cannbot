---
id: PRC-MEM-004
name: 缓冲深度 bufferNum 自适应加深
category: MEM
applies_to: 机制通用（各代 AI Core）；kernel+tiling 侧；单次 DMA 数据量小、循环次数多且 UB 有富余的场景；性能数字来自 dav-3510（moe_init_routing 1.45x）
status: ready
---

# PRC-MEM-004：缓冲深度 bufferNum 自适应加深

## 知识点

单次搬运数据量小（cols 小、单行只有几十字节）时，双缓冲的两级流水重叠不充分：每次 DMA 传输时间短、启动延迟占比高，bufferNum 2 藏不住相邻批次的间隙。UB 有富余时按余量把 `InitBuffer`/tiling 的 bufferNum 从 2 抬到 4 或更高，更深的流水让 In/Out 重叠更满。moe_init_routing Gather 段 bufferNum 自适应后 1.45x（mte2 44→23us）。收益有上限：流水只能重叠传输时间，消不掉每次 DMA 的固定启动延迟（数十 cycle），bufferNum ≥6~8 后趋平——根治小 DMA 要靠合并搬运（PRC-MEM-005）。

## 错误写法

```cpp
// 反例（摘自 moe_init_routing_story/src/2_double_buffer.asc）：
// 小 cols 场景下固定 DOUBLE_BUFFER=2，UB 大量闲置而流水重叠不满
TQueBind<TPosition::VECIN, TPosition::VECOUT, DOUBLE_BUFFER> xCopyInQueue_;
```

## 正确写法

```cpp
// 正例（摘自 moe_init_routing_story/src/3_bandwidth_utilization.asc，host tiling）：
// 数据一轮装得下仍有 UB 余量时逐步抬深度，kernel 侧 InitBuffer 用 tiling 传入的 bufferNum
int64_t bufferNum = DOUBLE_BUFFER;
while (perLoopMaxIndicesElements > perCoreIndicesElements && bufferNum < MAX_BUFFER_NUM) {
    bufferNum++;
    perLoopMaxIndicesElements =
        (tilingData->ubSize / bufferNum - inputXSize - inputScaleSize) / static_cast<int64_t>(sizeof(int32_t));
}
gatherOutTiling->bufferNum = bufferNum;
```

## 识别方法

在被检视源码中看：

1. 单次搬运字节数的量级：由搬运参数估算（`DataCopyExtParams.blockLen` 已是字节；`DataCopyParams.blockLen` 是 32B datablock 数需 ×32；均不再乘 dtype），明显小于带宽拐点（参考 16KB，PRC-MEM-005）且循环次数多，为候选。
2. 队列深度是否写死为 2 而 UB 占用估算远未用满（各 buffer 大小 × 深度 ≪ 可用 UB）；tiling 中无 bufferNum 类自适应字段，命中。
3. 优先级判断：若小 DMA 可以直接合并成大搬运（源/目标连续），应先报 PRC-MEM-005；只有源地址离散、单次搬运量无法增大时，加深 bufferNum 才是正解。

误报边界：bufferNum 加深收益 ≥6~8 后趋平，当前深度已 ≥4 的不再报加深；单次 DMA 已 ≥16KB 量级的场景加深收益微小，不报；重叠比单次 DMA 尺寸更重要——softmax_regbase Case5 实测 tileRow 8 单缓冲 64KB 大 DMA 反而全场最慢，故"把深度降为 1 换单次更大 DMA"的写法应反向报出（保住 ≥2 的 ping-pong 是底线）。

## 证据要求

finding 必须给出：

- 队列声明/InitBuffer 处文件:行号与摘录（当前深度），及单次搬运量的估算式（blockLen 单位见识别方法 1）；
- UB 余量估算：各 buffer 尺寸合计 vs 平台 UB 容量；
- 排除依据：说明源地址离散无法走 PRC-MEM-005 合并，且当前深度 <4（与误报边界一致）。

## 参考

- cann-samples：`Samples/2_Performance/moe_init_routing_story/src/2_double_buffer.asc → 3_bandwidth_utilization.asc`（1.45x，含 ≥6~8 趋平边界）；`Samples/2_Performance/softmax_regbase_story/src/5_bigtile.asc`（ping-pong 优先于 DMA 尺寸的实测）。
- 关联知识点：PRC-MEM-003（深度 2 的基础形态）、PRC-MEM-005（根治小 DMA）。
