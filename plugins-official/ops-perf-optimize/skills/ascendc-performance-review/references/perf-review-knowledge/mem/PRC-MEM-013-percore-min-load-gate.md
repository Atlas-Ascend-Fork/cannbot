---
id: PRC-MEM-013
name: 每核最小负载门限与调度核数收敛
category: MEM
applies_to: 机制通用（各代 AI Core）；tiling/host 侧为主，kernel 侧看空转核是否仍执行 Init；elementwise/展平类切分算子高发；命中判定为结构判定；收益为机制推断（每核固定开销摊销），未单独上板量化
status: ready
---

# PRC-MEM-013：每核最小负载门限与调度核数收敛

## 知识点

PRC-MEM-002 管"有没有分核"，PRC-MEM-011 管"关键路径均不均"；本条管反方向——**小 shape 下分核过度**。每个被调度的核都要付一份与数据量无关的固定开销：核启动调度、tiling 读取、`Init`/`InitBuffer`，有的实现还包括每核重复的共享参数装载（见 PRC-MEM-001）与整管 barrier。均分公式没有下限时，小 shape 会被切到对齐底（每核仅几十个元素量级），核数越多总固定开销越大，而计算量不变——收益为负。

两种命中形态：

- **形态① 无每核最小负载门限**：核数只由 `total/coreNum` 与对齐底决定，任意小的数据量都会摊开到尽量多的核。正确结构是先用"每核最小数据量"算出核数上限，再与平台核数取小：`actualCoreNum = min(total / minPerCore, 平台核数)`。**门限值不是常量规范，而是按机制定标**：每核数据量至少要达到（a）单次 DMA 接近带宽峰值的量级（官方带宽曲线，见 PRC-MEM-005）且（b）使每核固定开销占比可忽略。在库实现取值分散在数 KB 到十几 KB 一档，只作量级参考，检视时不得把某个具体字节数当标准答案。
- **形态② 调度核数 > 工作核数**：host `SetBlockDim(平台全量核数)`，kernel 里 `if (blockIdx >= 工作核数) return` 裁剪。空转核仍被调度、仍执行提前返回之前的全部代码；若裁剪判断放在 UB 分配**之后**，空转核还白付一次 InitBuffer。正确结构是 `SetBlockDim(usedCoreNum)` 与工作核数强绑定（`usedCoreNum = CeilDiv(total, blockFactor)`），被调度核恒有活干。

## 错误写法

```cpp
// 反例（形态①）：均分无下限，小 shape 把块切到对齐底
blockFactor = CeilAlign(CeilDiv(totalNum, coreNum), alignElems);  // 底 = 对齐元素数
usedCoreNum = CeilDiv(totalNum, blockFactor);
// 小 total 时：几十个核各分到一个对齐底大小的块，每核固定开销占主导
```

```cpp
// 反例（形态②）：起飞全量核，kernel 内裁剪，且裁剪在 Init 之后
context->SetBlockDim(coreNum_);            // 平台全量
// kernel：
Init(...);                                  // 空转核也分配了 UB
if (blockIdx_ >= tilingData_->numCore) {    // 到这才退出
    return;
}
```

## 正确写法

```cpp
// 正例（形态①）：数据量先决定核数上限，再与平台核数取小
int64_t minPerCoreElems  = CeilDiv(minPerCoreBytes, sizeofT);    // 门限按机制定标，见知识点
int64_t maxCoreNumByData = totalElements / minPerCoreElems;
int64_t actualCoreNum = maxCoreNumByData <= 0 ? 1
                      : std::min(maxCoreNumByData, coreNum);     // coreNum 来自平台接口
int64_t blockFactor = CeilDiv(totalElements, actualCoreNum);   // 对齐档位从略，见 PRC-MEM-014
int64_t usedCoreNum = CeilDiv(totalElements, blockFactor);
context->SetBlockDim(usedCoreNum);                               // 形态②：调度=工作核数
```

## 识别方法

**结构判定，与具体 shape 无关。**

1. **看均分公式有没有数据量项**（形态①）：`blockFactor`/核数的求解链里除了 `total/coreNum` 与对齐，是否存在"每核最小数据量"参与核数上限计算。完全没有 → 命中候选；再看用例集是否含小 shape（每核数据量与固定开销同量级的 case），有则报出。
2. **对比 SetBlockDim 实参与工作核数**（形态②）：host 侧 `SetBlockDim(X)` 的 X 与"实际有活干的核数"是否同一个量。X 为平台全量而工作核数另有字段 → 命中；再看 kernel 侧裁剪位置，裁剪在 UB 分配之后的提级。
3. 每核固定开销的放大项要一并列出：Init 期标量 GM 读、整管 barrier、per-core 重复装载的共享参数（联动 PRC-MEM-001）。

误报边界：

- **门限的具体数值不构成 finding**：在库不同算子取值不同，只要存在机制上说得通的门限就不报；只报"完全无门限"。
- 用例集全部是大 shape（每核负载远超固定开销量级）时，形态①记录不报——收益只在小 shape 场景兑现。
- 标准三行式 `blockFactor=CeilDiv(total,coreNum); usedCoreNum=CeilDiv(total,blockFactor); SetBlockDim(usedCoreNum)` 在 total 小时自动缩核（每核至少 1 个单元），已是可接受写法；有无门限只影响"1 个单元"是否够摊固定开销，按第 1 条判。
- 形态②若 kernel 裁剪在任何 UB 分配/标量读**之前**（入口第一句 return），浪费仅剩调度槽位，降级为记录项，不单独成 finding。
- 与 PRC-MEM-011 不冲突：本条是"核太多每核太少"，MEM-011 是"核不均/核太少"；小 shape 场景先看本条。

## 证据要求

finding 必须给出：

- `blockFactor`/核数求解链的文件:行号与摘录，证明无最小负载门限（或 SetBlockDim 实参 ≠ 工作核数字段）；
- 用例集中受影响 case 的核数与每核数据量（代入公式计算，不需上板）；
- 每核固定开销清单（Init 期标量读/barrier/InitBuffer）的文件:行号；
- 形态②需给出 kernel 裁剪语句位置及其与 UB 分配的先后关系。

## 参考

- 在库对照（dav-3510，2026-08-27 源码分析，仅作例证）：activation 类（数据量先决定核数上限的正例）、loss 类（bits 口径门限正例）、optim 类（无门限、且每核 Init 期含标量 GM 读+整管 barrier 的反例）、quant 类（SetBlockDim 全量+kernel 在 Init 后裁剪的反例）。
- 官方带宽曲线（单次搬运接近峰值的量级）：见 PRC-MEM-005。
- 关联知识点：PRC-MEM-002（有没有分核）、PRC-MEM-011（分核后的均衡）、PRC-MEM-001（每核重复装载共享参数）。
