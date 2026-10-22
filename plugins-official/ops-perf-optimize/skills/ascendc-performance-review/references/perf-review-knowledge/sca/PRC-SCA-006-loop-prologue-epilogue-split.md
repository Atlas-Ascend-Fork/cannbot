---
id: PRC-SCA-006
name: 循环主尾块分离
category: SCA
applies_to: 标量机制通用（各代 AI Core）；kernel 侧；对循环次数多的热循环（如 Cube 类 K 维 Reduce 循环）收益最大；来自 Ascend 950（scalar_story）
status: ready
---

# PRC-SCA-006：循环主尾块分离

## 知识点

热循环内用 `if(k==0)` / `if(k%N==0)` / `if(k==max-1)` 处理首块、周期事件、尾块，意味着每次迭代都执行 3 次分支判断。代价有二：每轮多付 3 条比较+分支指令，占用标量发射带宽；首/尾/周期"转变点"处条件翻转引发 mispredict（与 PRC-SCA-007 的 Tile 切换点 mispredict 同源）——恒为 false 的平段本身是易预测的，别把"低频分支"一律当 mispredict 热点。改为三段式：Prologue（首块，执行 1 次）+ 零分支 Hot Loop（纯计算与参数更新）+ Epilogue（尾块，执行 1 次），周期性事件可用分段内层循环（segmentEnd）表达。

## 错误写法

```cpp
// 反例（摘自 scalar_story README）：单一循环，每次迭代 3 个分支判断
for (uint64_t k = 0; k < maxK; k++) {
    if (k == 0) { SetInitialParams(); }
    if (k % self->multiKAL1 == 0) { MTE2_LoadAL1(); }
    UpdataParams(k);
    if (k == maxK - 1) { SetFinalParams(); }
    compute();
}
```

## 正确写法

```cpp
// 正例（依 scalar_story README 三段式重构）：Hot Loop 零分支。
// README 原文是示意节选，直接照抄有两个坑，此处已补：①segmentEnd 必须钳制到
// maxK-1，否则 loadAkIter 不整除时热段越过尾块多算；②首段 AL1 加载（反例中
// k==0 触发那次）要放进 Prologue。maxK<=1 需走独立路径。
uint64_t k = 0;
uint64_t segmentEnd = Min(self->ctx.loadAkIter, maxK - 1);
MTE2_LoadAL1();                                              // 首段加载
SetInitialParams(); UpdataParams(k); compute(); k++;         // Prologue（首块）
while (k < maxK - 1) {
    if unlikely(k == segmentEnd) {
        MTE2_LoadAL1();
        segmentEnd = Min(segmentEnd + self->ctx.loadAkIter, maxK - 1);
    }
    while (k < segmentEnd) { UpdataParams(k); compute(); k++; }   // 零分支热段
}
UpdataParams(k); SetFinalParams(); compute();                // Epilogue（尾块）
```

## 识别方法

- 看热循环体：是否存在只在首轮/末轮/周期轮为真的 if 判断（`k==0`、`k==max-1`、`k%N==0`、`isFirst/isLast` 标志位）混在每轮都执行的计算主体中。
- 命中条件：该循环是热路径（K 维 Reduce、tile 主循环等）且典型循环次数 ≥5（收益随次数增大，数十次以上最明显）。
- 误报边界：**循环次数 <5 时不报**——三段式代码膨胀可能反而触发 icache miss（见 PRC-SCA-001），得不偿失；分支条件在每轮都近似均匀真假（非首尾/周期模式）不属于本条；编译器可静态消除的分支（条件为编译期常量、constexpr if）不算命中；`k==0`/`k==maxK-1` 类分支是编译器 loop peeling 的标准目标，-O2 下可能已被消除——无法确认编译产物仍含该分支时降级为提示。

## 证据要求

- 热循环的文件:行号与摘录，标出每个首/尾/周期性分支及其触发模式。
- 循环次数的量级依据（来自 tiling 计算或典型 shape），证明 ≥5 且属热路径。
- 排除依据：分支条件非编译期常量、编译器无法自行消除。

## 参考

- cann-samples：`Samples/2_Performance/scalar_story/README.md` §7.2（Ascend 950 实测）
- 相关条目：PRC-SCA-001（代码膨胀与 icache 的权衡）、PRC-SCA-007（分支预测同族问题）
