---
id: PRC-MEM-003
name: DoubleBuffer 使能与时机
category: MEM
applies_to: 机制通用（各代 AI Core）；kernel 侧；循环 ≥2 轮的搬-算-搬结构；性能数字来自 dav-3510（rms_norm_quant 1.55x cannsim；moe_init_routing 1.47x）
status: ready
---

# PRC-MEM-003：DoubleBuffer 使能与时机

## 知识点

MTE2/Vector/MTE3 是独立流水，但单缓冲下同一块 UB 的搬入-计算-搬出只能串行。开双缓冲（buffer 数 1→2）后计算第 i 批时预取第 i+1 批，纯调度重排、指令数不变：rms_norm_quant 仅改 `BUF_NUM 1→2` 单步 1.55x（vec+mte2 占比和 96%→166%，重叠发生的直接证据）。手工 `SetWaitFlag` 串联搬入搬出等价于强制单缓冲，改用经项目验证的 TQue/TQueBind EnQue/DeQue 生命周期即可重叠：moe_init_routing Gather 段 1.47x。

**概念边界**：`TQue<..., depth>` 的模板 depth 与 `InitBuffer(queue, bufferNum, size)` 的 bufferNum 是两个不同参数，模板 depth 不代表是否使能 DoubleBuffer。判断 DB 应查看 `InitBuffer`/tiling 的 bufferNum，以及 Alloc/EnQue/DeQue/FreeTensor 的实际流水生命周期；不能从模板 depth 单独推导，也不能因修改 bufferNum 就机械联动模板参数。

## 错误写法

```cpp
// 反例（摘自 moe_init_routing_story/src/1_multi_core.asc CopyX()）：
// 手工事件把 MTE2→MTE3 焊死成串行，无法预取下一批
DataCopyPad(xLocal, xGm_[xSrcOffset], copyInParams, padParams);
SetWaitFlag<HardEvent::MTE2_MTE3>(HardEvent::MTE2_MTE3);
DataCopyPad(expandedXGm_[xDstOffset], xLocal, copyOutParams);
```

## 正确写法

```cpp
// 正例（摘自 moe_init_routing_story/src/2_double_buffer.asc）：
// 队列深度 2 + EnQue/DeQue 自动信号，MTE3 搬出本批时 MTE2 预取下批
TQueBind<TPosition::VECIN, TPosition::VECOUT, DOUBLE_BUFFER> xCopyInQueue_;
// CopyXIn: AllocTensor → DataCopyPad(GM→UB) → EnQue
// CopyXOut: DeQue → DataCopyPad(UB→GM) → FreeTensor
```

rms_norm_quant 版仅一行差异：`static constexpr size_t BUF_NUM = 2;`（`InitBuffer(queue, BUF_NUM, size)`）。

下面的写法只用于说明模板 depth 与 bufferNum 可以不同，是否形成 DB 仍以实际初始化和流水为准：

```cpp
TQue<QuePosition::VECIN, 1> inQueue_;
pipe.InitBuffer(inQueue_, DOUBLE_BUFFER, tileBytes);
```

## 识别方法

在被检视源码中看：

1. `InitBuffer(queue, N, size)` 的第二参数：主数据通路队列 N==1 且主循环 ≥2 轮，命中；单独记录模板 depth，不用它代替 N 判断 DB。
2. 同一 LocalTensor 上 DataCopy 进出之间的手工 `SetFlag/WaitFlag`（`MTE2_MTE3`、`MTE3_MTE2` 等）替代队列同步——等效单缓冲，命中。
3. 开 DB 的时机（防过早误报）：先看计算链是否已压缩。静态口径：按每批搬运字节数与该批计算链矢量指令量估算两者量级——计算链明显重于搬运（如长依赖链、多次遍历同批数据）时瓶颈在计算，开 DB 收益甚微，应先报计算链问题（VF 融合等，见 PRC-VF-001）；搬运与计算量级相当才是开 DB 的正确时机（rms Step3→4 的"先压缩后重叠"次序）。有 profiling 数据时以 ratio 为强证据（VEC 显著高于 MTE2、如 >65% 且主导，属计算 bound）。

误报边界：数据量小到一次搬入即可算完（无第二轮循环）时强开 DB 反而浪费 UB 且引入队列开销，官方 0033 明示"适得其反"，不报；搬运时间远短于计算时间的场景收益有限，降级提示；共享参数常驻 buffer（如 gamma 的 `InitBuffer` buffer 数 1）不是命中对象。

## 证据要求

finding 必须给出：

- `InitBuffer`/队列声明处的文件:行号与摘录（深度参数值）；或手工 SetWaitFlag 串联处摘录；
- 主循环轮数 ≥2 的依据（循环上界表达式）；
- plain TQue 模板声明与 `InitBuffer` bufferNum 的前后值，分别说明两者含义，不用模板 depth 代替 bufferNum 判断 DB；
- 时机依据：说明该算子搬运与计算量级相当（或 profiling 中 MTE2 占比接近 VEC），排除"计算链未压缩先开 DB"与"单轮循环"两类误报。

## 参考

- cann-samples：`Samples/2_Performance/rms_norm_quant_story/src/3_vf.asc → 4_double_buffer.asc`（1.55x）；`Samples/2_Performance/moe_init_routing_story/src/1_multi_core.asc → 2_double_buffer.asc`（1.47x）。
- 官方使能 DoubleBuffer：`atlas_ascendc_best_practices_10_0033`（小数据量强开反效果的边界即出自此页）。
- 关联知识点：缓冲深度进一步加深见 PRC-MEM-004；纯搬运路径的队列复用见 PRC-MEM-006；同步原语选型总则与热路径 PIPE_ALL 红线见 PRC-MEM-015。
