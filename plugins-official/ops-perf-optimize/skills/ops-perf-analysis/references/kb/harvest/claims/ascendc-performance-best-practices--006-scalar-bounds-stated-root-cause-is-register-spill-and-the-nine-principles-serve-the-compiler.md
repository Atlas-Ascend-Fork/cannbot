# CARD · ascendc-performance-best-practices 006 — ScalarBound's stated root cause is register spill, and the nine principles all serve the compiler

**BOOK: BOTH (the family is marked `DAV_2201 / DAV_3510`). Held as a card by the 950-bp a later harvest pass
harvester: the material is strong and its 950 half is entry-worthy, but it collides with two
already-owned neighbourhoods and one already-filed card.**

## The claim, re-verified 2026-08-24
`reference/scalar/guide.md:3-5`:

> Scalar 单元负责标量计算、地址计算、指令参数构造与指令分发。当它本身成为瓶颈、无法及时把指令发到
> Cube / Vector / MTE 的 Issue 队列时，其他流水线会出现 bubble，整个算子被拖慢。这种现象称为
> **ScalarBound**。
>
> Scalar 优化的核心结论：**主因不是 Scalar 计算指令多，而是 Load/Store 指令多**（典型占比超过
> 30%），其根源是编译器寄存器 Spill。因此本类目下所有原则的共同目标是：**帮助编译器更好地完成
> 寄存器分配、别名分析和常量传播，从而减少 Load/Store**。

The nine principles (`:9-21`), each with its stated mechanism:

| # | principle | stated mechanism |
|---|---|---|
| P1 | 结构体内慎用数组 | 动态下标的结构体数组会让编译器放弃整个结构体的常量传播 |
| P2 | 循环主尾块分离 | Prologue / Hot Loop（零分支）/ Epilogue 三段式，避免热路径每轮 3 次分支判断 |
| P3 | 显式编写循环代码 | `for` 的回跳走专用硬件，不进分支预测 |
| P4 | 尽量使用局部变量 | 成员变量受别名分析压制；跨函数调用后必须从内存重新 Load |
| P5 | 变量定义贴近使用位置 | 缩短活跃范围 = 缩短寄存器占用 = 降低 Spill 概率 |
| P6 | 避免多级指针解引用 | 每级解引用都是带依赖的 Load |
| P7 | 避免使用超大结构体 | > 64B 跨 cacheline；超寄存器容量必 Spill；指针传递引入别名 |
| P8 | 用 `constexpr` / 模板参数承载编译期常量 | `const` 成员对编译器仍是 runtime Load |
| P9 | Hot Loop 内不构造对象、不取地址 | 构造/析构展开后是大量初始化 Store；取地址强制 Spill |

## Why this is a card and not an entry
Three collisions, any two of which would still leave it enterable; all three together make it a
card.

1. **`910:0018` already carries the 64 B D-Cache line from P7's own source**, and
   `harvest/claims/ascendc-performance-best-practices--002` already carded the ≤ 64 B / ≤ 128 B
   struct-size recommendation, with a stated reason (it bundles three mechanisms — cache-line
   straddling, register spill, pointer aliasing — each needing its own entry and none having its own
   evidence). Re-entering P7 in book-950 would repeat that decision without the reason changing.
2. **The 950-side scalar work is already in this block, at operator granularity.** `950:0334`–`950:0336`
   carry the FlashAttention family's SCALAR/SCALARLDST split, and `950:0336` §3 states the same root
   cause from the other end: `SCALARLDST 主导时，继续把 ALU 计算改成成员预计算可能只是在"少一次
   乘法"和"多一次成员 load"之间对冲`. The nine principles are the general form of what MR1–MR5 do
   specifically, and the specific form is the one with a measurement attached (−1.51 %, `950:0336`).
3. **`950:0348` carries the conv family's instance**, where the same three remedies appear (kill `TQue`,
   localise tiling fields, precompute `Load3D` config) with a *derivable* entry condition
   (`kL0 ≤ 48`) that the nine principles lack.

So the general statement would enter the book *after* two of its own applications, with no
measurement of its own, and would duplicate a decision already recorded on card 002.

## What is genuinely new here and would justify a later entry
The **root-cause claim itself**: that ScalarBound is dominated by Load/Store rather than by scalar
arithmetic, at a typical share above 30 %, and that the cause is compiler register spill. That is a
falsifiable statement about a machine and a toolchain, it is stated once in this shelf, and nothing
in book-950 carries it. It reframes every scalar optimisation from "do less arithmetic" to "help the
register allocator", which is a different search.

Its §4 would be: on a named 950 board, take a ScalarBound operator, measure the Load/Store share of
scalar time (not of total time), then apply P4/P5/P8/P9 — the four principles that are purely about
register pressure — and measure the share again alongside the compiler's own resource report. The
claim predicts the share falls and spill count falls together. A share that is *not* above 30 % on a
950 part would kill the "典型占比超过 30%" figure directly.

## Guessed level
L1 (core & pipe assignment), or L8 (toolchain & build) — the root cause named is a compiler
behaviour, not a hardware one, which is itself an argument for L8 and worth deciding before drafting.

## Evidence class
mechanism-with-one-unscoped-number. `典型占比超过 30%` carries no case, shape, board or tool. Nine
principles, nine stated mechanisms, zero measurements.

## OVERTURN sketch
A ScalarBound operator on a named 950 board whose profiled scalar Load/Store share is well below
30 %, or whose compiler resource report shows no spill while the scalar pipe is nonetheless the
bottleneck. Either would break the root-cause claim and leave the nine principles as coding
preferences.

## Disposition
Card kept. Enter only after deciding whether the root-cause claim belongs at L1 or L8, and only with
the Load/Store-share measurement in its §4 — the nine principles without it are advice, and this
book already carries two measured instances of the same advice (`950:0336`, `950:0348`).
