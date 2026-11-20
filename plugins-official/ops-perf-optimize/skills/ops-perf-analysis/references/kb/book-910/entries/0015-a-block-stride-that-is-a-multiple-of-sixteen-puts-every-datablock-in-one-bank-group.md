```
ID:        0015-a-block-stride-that-is-a-multiple-of-sixteen-puts-every-datablock-in-one-bank-group
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:65-66 — "`blk_stride = 16`：相邻 DataBlock 地址差 = 16 × 32B = 512B。bank 编号差 = 16……即**所有 DataBlock 落入同一 bank group**，8 拍完成一个 Repeat" and "`blk_stride = 8`……4 拍完成一个 Repeat"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `blk_stride` sweep on a named DAV_2201 board shows the repeat cost flat across strides 1, 8 and 16 — or shows the 8-cycle and 4-cycle costs at strides other than 16 and 8.
```

# 0015 · A block stride that is a multiple of sixteen puts every DataBlock in one bank group

## 1 · Claim
Upstream asserts that on DAV_2201 a Vector instruction's `blk_stride` of 16 makes all eight
DataBlocks of one repeat land in a single bank group, costing 8 cycles per repeat instead of the
conflict-free 1–2, and that a `blk_stride` of 8 puts alternating DataBlocks in one group, costing
4. Upstream asserts the mechanism: adjacent 32 B rows map to adjacent banks, so a stride of `S`
DataBlocks gives a bank-number difference of `S`, and `S % 16 == 0` collapses the group. Not
established here.

## 2 · The wrong branch this removes
`blk_stride` is a natural thing to set: a kernel that processes every 16th row, or that walks a
column of a 512 B-pitch matrix, arrives at stride 16 for reasons that have nothing to do with
banks. The code is correct and the intent is legible. It is also, per upstream, the worst possible
stride on this architecture — an 8× serialisation of the repeat. The agent has no local signal:
the instruction count is unchanged, the data volume is unchanged, and the only symptom is that
Vector time is 8× the model. The most likely next action is to reduce the arithmetic or enable
double buffering, neither of which touches the cause.

The fix upstream names is not to pad but to restructure: "改为 `blk_stride = 1`（连续读），通过
`dst_gap/src_gap` 控制跨 Repeat 的地址增量" (line 88). Padding (0016) addresses the
different case of two *buffers* aliasing; this is one buffer's internal stride.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md` §2.2.3, the
mapping rule at lines 61-63:
"**映射的核心规律**（由官方示例推导，具体公式以芯片手册为准）：
- 地址上相邻的 32B 行通常映射到相邻的 bank（按 bank 总数循环）。
- 因此，**DataBlock 之间的地址差（由 `blk_stride` 决定）直接决定了它们是否落入同一 bank group**。"

Note the parenthetical: upstream marks its own mapping rule as derived from examples rather than
from a hardware manual, and hedges with 通常 ("usually"). That hedge is inherited here.

Worked cases, lines 65-66, verbatim:
"- `blk_stride = 16`：相邻 DataBlock 地址差 = 16 × 32B = 512B。bank 编号差 = 16（假设按 32B 行
轮询），16 % 16 = 0，即**所有 DataBlock 落入同一 bank group**，8 拍完成一个 Repeat。
- `blk_stride = 8`：bank 编号差 = 8，block0 和 block2 的 bank 差 = 16，16 % 16 = 0，落入同一
group，4 拍完成一个 Repeat。"

The eight-DataBlock repeat is from line 58 of the same file (see 0032): "一个 Vector 指令在一个
Repeat 内最多处理 **8 个 DataBlock**（block0~block7）". The 16 groups are from 0013.

Arithmetic performed here: stride 16 → all 8 blocks in one group → 8 serialised accesses → 8
cycles. Stride 8 → blocks {0,2,4,6} in one group and {1,3,5,7} in another → 4 each → 4 cycles.
Both reconstructions match upstream's stated cycle counts, which is a consistency check on the
model, not evidence for it.

The upstream code form, line 84-87:
```cpp
Adds(dst, src, scalar, MASK, 1, {1, 16, 1, 16});   // 8 拍
Adds(dst, src, scalar, MASK, 1, {1, 8, 1, 8});     // 4 拍
```

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Sweep `S` over {1, 2, 4, 8, 16, 32} in `Adds(dst, src, scalar, MASK, 1, {1, S, 1, S})` at a
   fixed element count, one build per `S`, md5-confirmed to differ only in the stride.
3. Record per `S`: `aiv_vec_ratio`, `aiv_vec_bankgroup_cflt_ratio`, and the raw
   `aiv_total_cycles` — the cycle count is the quantity upstream's claim is about, and the ratio
   alone cannot distinguish "more cycles in Vector" from "fewer cycles elsewhere".
4. Five repeats per `S`, first discarded. Report medians and spreads.
5. Include `S = 1` as the conflict-free reference and `S = 32` as a second predicted-bad point
   (32 % 16 == 0), so the claim's *periodicity* is tested and not just its worst case.

## 5 · Checker — acceptance declared before the run
Verdict variables `c1, c8, c16` — median `aiv_total_cycles` at strides 1, 8 and 16, all at
identical element counts.
PASS iff `c16 / c1` lies in [6, 10] AND `c8 / c1` lies in [3, 5] — a factor-of-8 and a
factor-of-4, with the windows declared now rather than fitted afterwards.
Red inputs: any ratio near 1 (no conflict — overturns), or `c8 > c16` (the ordering inverted,
which would refute the mapping model even if both are slow).
`S = 32` must also land in the `c16` window; if stride 32 is fast while stride 16 is slow, the
`% 16` periodicity is wrong and the entry is corrected even though its headline case passed. That
extra point is what stops this checker from confirming only what it went looking for.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. This entry does not establish the address-to-bank mapping —
upstream marks it as inferred, and the cycle counts would be consistent with several mappings.
It does not establish that the 8-cycle cost is the maximum; a case with more than one operand
conflicting is not covered. It does not cover strides that are non-multiples of 16 but share a
common factor with the bank count in other ways, nor DataBlock counts below 8 per repeat. It says
nothing about MTE-side strides — `blk_stride` here is a Vector instruction parameter, not a
DataCopy one, and the two are different mechanisms with the same word.
