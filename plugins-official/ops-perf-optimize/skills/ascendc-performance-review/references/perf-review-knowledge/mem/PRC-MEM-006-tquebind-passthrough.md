---
id: PRC-MEM-006
name: 纯搬运路径 TQueBind 复用 VECIN/VECOUT
category: MEM
applies_to: 机制通用（各代 AI Core）；kernel 侧；限数据在 UB 内不做（或几乎不做）Vector 计算的纯搬运/重排路径；官方数据"aiv_vec_time≈0"，dav-3510 实证见 moe_init_routing
status: ready
---

# PRC-MEM-006：纯搬运路径 TQueBind 复用 VECIN/VECOUT

## 知识点

数据只是从 GM 经 UB 中转到 GM（gather/重排/切片类路径）时，若沿用"VECIN 队列 + VECOUT 队列"标准结构，就要插入一次 LocalTensor→LocalTensor 的 `DataCopy` 把数据从输入 buffer 拷到输出 buffer——这次 UB 内拷贝走 Vector 流水，纯属浪费。改用 `TQueBind<TPosition::VECIN, TPosition::VECOUT>` 把同一块 LocalTensor 同时当输入与输出，搬入后直接搬出，官方实测 aiv_vec_time 几乎缩减为 0。moe_init_routing 的 Gather 数据通路即为实证。

## 错误写法

```cpp
// 反例（依官方文档 10_0027 示例重构）：分离队列 + UB 内中转拷贝
TQue<QuePosition::VECIN, 1> inQueue;
TQue<QuePosition::VECOUT, 1> outQueue;
// ...
LocalTensor<T> iLocal = inQueue.DeQue<T>();
LocalTensor<T> oLocal = outQueue.AllocTensor<T>();
AscendC::DataCopy(oLocal, iLocal, size);   // 冗余的 UB→UB 拷贝，占 Vector 流水
outQueue.EnQue(oLocal);
```

## 正确写法

```cpp
// 正例（摘自 moe_init_routing_story/src/2_double_buffer.asc）：
// 绑定队列，同一块 LocalTensor 搬入后直接搬出，无 UB 内拷贝
TQueBind<TPosition::VECIN, TPosition::VECOUT, DOUBLE_BUFFER> xCopyInQueue_;
// CopyXIn:  xLocal = AllocTensor → DataCopyPad(xLocal, xGm_[...]) → EnQue(xLocal)
// CopyXOut: xLocal = DeQue → DataCopyPad(expandedXGm_[...], xLocal) → FreeTensor(xLocal)
```

## 识别方法

在被检视源码中看：

1. 找出 UB 内无计算（或仅地址计算）的数据通路：DeQue 出的 LocalTensor 上没有任何 Vector API 调用就进了输出侧。
2. 该通路上是否存在 LocalTensor→LocalTensor 的 `DataCopy`（src/dst 均为 UB 张量），且分别挂在 VECIN/VECOUT 两个独立 TQue 上，命中。
3. 变体：即使没有显式 UB 内拷贝，分离双队列也白占一倍 UB（挤压 PRC-MEM-004/005 的空间），可一并指出。

误报边界：通路上有真实 Vector 计算（Cast、Muls、Select 等会改写数据）的不属纯搬运，不报；GM→GM 且无需经 UB 重排的场景应直接质疑是否需要该算子，不属本条；TBuf 中转做 Vector 计算再输出属正常结构。

## 证据要求

finding 必须给出：

- 两个队列声明与 UB 内 `DataCopy(oLocal, iLocal, ...)` 处的文件:行号与摘录；
- 纯搬运判定依据：列出该 LocalTensor 从 DeQue 到 EnQue 之间的全部操作，证明无数据变换；
- 改写可行性：说明输入输出 dtype/布局一致（TQueBind 复用同一块内存的前提）。

## 参考

- 官方：`atlas_ascendc_best_practices_10_0027`（优先级高，aiv_vec_time≈0）。
- cann-samples 实证：`Samples/2_Performance/moe_init_routing_story/src/2_double_buffer.asc`。
- 关联知识点：PRC-MEM-003（DoubleBuffer 的 bufferNum 与流水生命周期）。
