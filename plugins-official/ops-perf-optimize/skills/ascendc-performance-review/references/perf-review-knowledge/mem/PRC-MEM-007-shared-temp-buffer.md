---
id: PRC-MEM-007
name: 时间不重叠操作共享临时 Buffer
category: MEM
applies_to: 机制通用（各代 AI Core）；kernel 侧；多个计算/高阶 API 各自申请临时空间且执行时序不重叠的场景；官方数据为搬运次数 16→8（口径为次数非实测耗时）
status: ready
---

# PRC-MEM-007：时间不重叠操作共享临时 Buffer

## 知识点

高阶 API（SoftMax 等）和自写计算各自独立申请临时 Buffer 时，UB 按"各需求之和"被占用；但这些操作在时间上先后执行、临时空间生命周期互不重叠，实际只需"各需求的最大值"。求和式分配挤占主数据通路的 UB，迫使单次搬运批量变小、搬运次数增多——官方示例中独立分配 tmpSoftmaxBuf 与 tmpSumBuf 使搬运 16 次，共享一块取 MAX 的 Buffer 后降为 8 次。本质是把 UB 省出来还给 PRC-MEM-005 的 ubFactor。

## 错误写法

```cpp
// 反例（依官方文档 10_0017 示例重构）：两个时序不重叠的操作各占一块临时区
pipe.InitBuffer(tmpSoftmaxBuf_, softmaxTmpSize);   // 仅 SoftMax 期间使用
pipe.InitBuffer(tmpSumBuf_, sumTmpSize);           // 仅其后的求和期间使用
// UB 被占 softmaxTmpSize + sumTmpSize，主数据 buffer 被迫变小
```

## 正确写法

```cpp
// 正例（依官方文档 10_0017 示例重构）：共享一块，大小取 MAX 而非求和
// （device 代码不依赖 std::，取 MAX 用条件表达式或在 host/tiling 侧算好传入）
uint32_t tmpSharedSize = softmaxTmpSize > sumTmpSize ? softmaxTmpSize : sumTmpSize;
pipe.InitBuffer(tmpSharedBuf_, tmpSharedSize);
auto tmp = tmpSharedBuf_.Get<uint8_t>();
SoftMax<...>(dst1, src1, tmp, ...);   // 时段一
// SoftMax 完成后同一块作为求和的临时区                // 时段二
ReduceLikeCompute(dst2, src2, tmp, ...);
```

## 识别方法

在被检视源码中看：

1. 汇总所有 `InitBuffer` 的 TBuf/临时区，标注各自被使用的代码区间（首次 Get 到最后一次使用）。
2. 两块及以上临时区的使用区间互不重叠（前者最后使用点在后者首次使用点之前，且无跨迭代保留数据的需求），却分别占 UB，命中。
3. 关注高阶 API 的 sharedTmpBuffer/calcBuf 参数：多个调用各传独立 buffer 而时序串行，命中。

误报边界：双缓冲/流水场景下"看似串行"的两块可能在相邻迭代间并发存活（前一批的 tmp 还在被 MTE3 读、后一批已开算），需确认生命周期真不重叠才报；临时区之间有数据传递（前者输出即后者输入）的不是临时区复用问题，不报；节省量相对 UB 总量可忽略（<5%）时降级提示。

## 证据要求

finding 必须给出：

- 各 InitBuffer 处文件:行号与摘录、各临时区大小；
- 时序不重叠的证据：两块 buffer 各自首末使用点的行号与调用序；
- 收益估算：MAX 与 SUM 的差值及其占可用 UB 比例（可折算为 ubFactor 提升）。

## 参考

- 官方：`atlas_ascendc_best_practices_10_0017`（搬运次数 16→8）。
- 关联知识点：省出的 UB 用途见 PRC-MEM-005（增大 ubFactor）与 PRC-MEM-004（加深 bufferNum）。
