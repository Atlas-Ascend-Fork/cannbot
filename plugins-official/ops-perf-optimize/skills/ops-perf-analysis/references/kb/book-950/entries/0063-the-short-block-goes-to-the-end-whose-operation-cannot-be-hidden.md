```
ID:        0063-the-short-block-goes-to-the-end-whose-operation-cannot-be-hidden
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:78-82 — "短块放在 fill 端或 drain 端，取决于哪种操作无法被掩盖： - **计算 Bound**（计算掩盖通信）：首/尾块的**通信**无法被掩盖，短块放在通信不可掩盖的一端，使该端通信耗时最小 - **通信 Bound**（通信掩盖计算）：首/尾块的**计算**无法被掩盖，短块放在计算不可掩盖的一端"
           ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:148-154 — "| 计算后通信 | 计算 Bound | 后（drain 端） | compute[N] ≥ comm[N-1]，尾通信尽量短 | | 计算后通信 | 通信 Bound | 前（fill 端） | comm[N] ≥ compute[N+1]，首计算尽量短 | | 通信后计算 | 计算 Bound | 后（drain 端） | local_matmul ≥ comm[1]; compute[N] ≥ comm[N+1] | | 通信后计算 | 通信 Bound | 后（drain 端） | comm 连发不中断，尾 matmul 最小但保 Mac 利用率 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board in which, for a compute-bound compute-then-comm
           operator, placing the short block at the fill end is at least as fast as placing it at
           the drain end — the placement matrix's first row would then be selecting nothing.
```

# 0063 · The short block goes to the end whose operation cannot be hidden

## 1 · Claim
Upstream asserts that an MC² operator is split along the M dimension of the matmul result into a
number of long blocks plus one short block, with a flag choosing whether the short block leads or
trails; that the total pipeline time is T_fill + T_steady + T_drain, where the first and last blocks'
work cannot overlap with anything; and that the short block therefore belongs at whichever end
carries the operation that cannot be hidden — for a compute-bound operator the unmaskable
communication, for a communication-bound operator the unmaskable computation. Upstream asserts a
four-row placement matrix over execution order × bound type, and that long and short blocks carry
independent complete matmul tiling data. Not established here; nothing was measured.

## 2 · The wrong branch this removes
The default is a uniform split, which is what a tiling model produces when asked for N tiles. A
uniform split makes the first and last blocks the same size as the middle ones, so the unmaskable
head and tail cost a full block each. The asymmetric split is a small idea with a specific shape:
make the block at the unmaskable end small, so that what cannot be overlapped is as short as
possible, while the middle blocks stay large enough to keep the cube busy.

The wrong branch inside the idea is choosing the end by intuition. The matrix's two
communication-bound rows put the short block at *different* ends depending on execution order — fill
for compute-then-comm, drain for comm-then-compute — and the reason is Local Matmul (0071): when
communication comes first, there is local work available to cover the first communication, so the
head is no longer the unmaskable end. An agent that reasons "communication bound, so protect the
communication end" gets one of the two rows wrong.

## 3 · Ground / Source
`pipeline_balancing.md:7-22`, the splitting principle: MC² operators split by the M rows of the
matmul result, communication and computation masking each other; non-uniform splitting (long plus
short) aims to make the short block and the adjacent long block completely cover each other so the
pipeline total is minimal. The TilingData carries 长块数量、长块长度、短块数量、短块长度、短块在前或
在后的 flag, and `:22` states that long and short blocks use 各自独立的完整 matmul tiling data
（baseM/baseN/baseK/L1 参数等均不同）— which is why 0062 requires two prints.

The three-段 model, `:64-82`: `T_total = T_fill + T_steady + T_drain` with T_fill = 首块操作 × M_first,
T_steady = max(α, β) × M_steady, T_drain = 尾块操作 × M_last; then the placement rule quoted in
SOURCE, and `:82`: 配平的目标是使短块与相邻长块完全掩盖——即短块的被掩盖操作耗时 ≥ 相邻长块的瓶颈
操作耗时.

The four cases are then given individually with diagrams, `:86-140`. Compute-then-comm, compute
bound (`:92-101`): short block last, with the diagram pairing 短块计算 against 长块N通信 and the
constraint 约束：compute[long_k] ≥ comm[long_k-1]，短块 comm 尽量短. Compute-then-comm, comm bound
(`:103-112`): short block first, 约束：comm[k] ≥ compute[k+1]，短块 compute 尽量短. Comm-then-compute,
compute bound (`:118-130`): short block last, with two constraints — `local_matmul ≥ comm[1]` and
`compute[k] ≥ comm[k+1]`. Comm-then-compute, comm bound (`:132-140`): short block last, communication
issued back-to-back, 尾块 matmul 最小化但保 Mac 利用率. Balanced (`:142-144`): split freely, keeping
the minimum granularity large enough for Mac utilisation. The speed-look-up table is quoted in
SOURCE.

One inconsistency, recorded here and carried in full by 0065: the balance *condition* stated at
`:165` (`α × M_short ≥ β × M_long` for compute bound) is inverted with respect to the diagrams and
the look-up table quoted above, which pair the short block's *compute* against a long block's
*communication*. This entry states the placement; 0065 states the contradiction; 0066 states what the
search does with it.

## 4 · Procedure
Later phase, needs one card per rank; capture per 0057, R per 0058, TilingData per 0062.
1. Device selection per 0057; board token per rank from the driver readout; occupancy either side.
2. Choose two operators, one compute-then-comm and one comm-then-compute, and two problem sizes each
   giving R > 2 and R < 0.5 (four configurations).
3. For each configuration, build both placements — short block at fill, short block at drain — at the
   same long-block size, with the correct independent tiling data for each block, and measure both
   per the ten-iteration protocol.
4. Record T_total, and from the trace the fill and drain durations separately, so the mechanism (the
   unmaskable end shrank) is checked rather than inferred from the total.

## 5 · Checker — acceptance declared before the run
Verdict variables `dt(config) = T(prescribed placement) − T(other placement)` and
`drain_share`/`fill_share` per placement. Acceptance of the matrix: `dt < 0` beyond run spread for
all four configurations, and the shrinking end is the one the matrix names — a total that improves
while the *other* end shrank is reported as unattributed.

Exit code is not the verdict. Both placements' full per-rank tables are published for every
configuration, including configurations where the two placements tie, which are retained and named.

Red input: the balanced case, R ≈ 1. Neither placement should win there beyond spread; if one does,
the mechanism is not the maskability asymmetry and the matrix's reasoning does not explain the data.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. No board, operator, rank count or shape. The matrix assumes exactly one short
block; nothing here covers two or more. It assumes the two phases are the only stages, so it says
nothing about operators with a third phase. The Local Matmul premise in the comm-then-compute rows
depends on 0071 and 0072, both unverified. The balance condition that this placement is supposed to
satisfy is internally contradictory upstream (0065), so the *sizes* of the blocks are not settled by
this entry even where the placement is.
