---
id: PRC-SCA-007
name: 显式 for 循环替代隐式状态机
category: SCA
applies_to: 标量机制通用（各代 AI Core）；kernel 侧；多维嵌套 tile 遍历场景（Conv/Matmul 类常见）；来自 Ascend 950（scalar_story）
status: ready
---

# PRC-SCA-007：显式 for 循环替代隐式状态机

## 知识点

用 `while(Iterate())` 式隐式状态机（返回值控制的多维迭代器）实现嵌套循环时，每次 Tile 切换要做多层进位判断，嵌套越深连续 mispredict 越多——一次 Tile 切换可引发 3-5 次连续分支预测失败；且状态机函数为处理各维 Tail/边界，体积常达数百行，本身易触发 icache miss。显式 for 循环两头占优：硬件层面，for 的回跳走专用循环硬件、不经分支预测器、不会 flush（scalar_story README 原文表述，主要覆盖迭代结构规整的循环）；编译器层面，显式循环更易做展开与循环无关变量外提。

## 错误写法

```cpp
// 反例（摘自 scalar_story README，节选）：返回值控制的状态机，进位判断层层嵌套
while (IterateMFirstMMode(self, enPartialSum)) {
    LoadAL1(...);
    IterateK(self, ...);
    FreeTensor();
}
__aicore__ inline bool IterateMFirstMMode(Intf *self) {
    if (IterateL0MFirstMMode<Intf>(self)) { return true; }
    self->ctx.mAL1Iter++;
    if (self->ctx.mAL1Iter != self->ctx.ddr2l1LoopM) { ... return true; }
    // ... 数百行多层进位判断（batchIter/dOutIter/...），逐层 return ...
}
```

## 正确写法

```cpp
// 正例（摘自 scalar_story README，节选）：显式嵌套 for，控制流线性、回跳走循环硬件
for (uint64_t nBL1 = 0; nBL1 < self->ctx.ddr2l1LoopN; ++nBL1) {
    for (uint64_t batch = 0; batch < self->ctx.ddr2l1LoopBatch; ++batch) {
        for (uint64_t mAL1 = 0; mAL1 < self->ctx.ddr2l1LoopM; ++mAL1) {
            self->ctx.nBL1Iter = nBL1;
            self->ctx.batchIter = batch;
            self->ctx.mAL1Iter = mAL1;
            CalcMDirectionVar(self);
            // ... L0 层循环与实际计算 ...
        }
    }
}
```

## 识别方法

- 看主流程：`while(Xxx())` / `do {...} while(Next())` 形态，其中被调函数通过维护多个 iter 计数器 + 逐层进位 if/return 表达嵌套遍历。
- 加重信号：状态机函数体巨大（数百行）、含大量维度 Tail 特判；profiling 显示 Scalar bound 且分支预测失败率高（scalar_story 诊断流程 Step 4c）。
- 误报边界：迭代空间确实运行期不规则（数据依赖的提前退出、动态维度增减）无法写成计数 for 的不报；循环边界全部可从 ctx/tiling 预先取出时才可等价改写，改写须保证与原状态机的迭代序、flag 副作用（如 loadAL1Flag）完全等价，无法证明等价时降为建议而非缺陷。

## 证据要求

- 状态机函数与调用点的文件:行号与摘录，列出各维计数器与进位判断链，估算一次 Tile 切换经过的分支数。
- 说明各维循环边界均为循环前已知量（可显式 for 化）的依据。
- 有条件时附分支预测失败率或 Scalar 停顿数据。

## 参考

- cann-samples：`Samples/2_Performance/scalar_story/README.md` §7.3（Ascend 950 实测）
- 相关条目：PRC-SCA-006（分支预测同族）、PRC-SCA-001（大函数体 icache miss）
