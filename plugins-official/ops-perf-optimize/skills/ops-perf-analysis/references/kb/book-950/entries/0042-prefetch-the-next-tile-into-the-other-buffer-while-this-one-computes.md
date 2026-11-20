```
ID:        0042-prefetch-the-next-tile-into-the-other-buffer-while-this-one-computes
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-02-ping-pong-prefetch.md:14 — "关键不在多开一个 buffer，而在把下一轮的 copy 发射提到当前轮 compute 之前，并严格维护 MTE 与消费方的事件配对"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-02-ping-pong-prefetch.md:44 — "Tiling 侧同时验证 `2 * inputTileBytes + workspaceBytes + outputTileBytes`。若以 queue 实现，`InitBuffer` 的深度和 host UB 预算必须使用同一份 `bufferNum`，不能只改 kernel"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board in which issuing the next tile's copy before the
           current tile's compute yields no steady-state overlap — MTE2 still fully preceding
           VECTOR in the trace — which would mean the issue order is not what realises the overlap.
```

# 0042 · Prefetch the next tile into the other buffer while this one computes

## 1 · Claim
Upstream asserts (card mem-02, evidence: five named arch35 commits, no numbers) that with two
physical buffers alternating ownership — copy writes only the idle buffer, compute reads only the
ready one — tile t's compute overlaps tile t+1's load after a prologue; that the essential move is
not adding a buffer but issuing the next round's copy *before* the current round's compute, with
strictly paired MTE and consumer events; and that the tiling side must verify
`2 * inputTileBytes + workspaceBytes + outputTileBytes` against the budget, with kernel and host
using one `bufferNum`. Not established here.

## 2 · The wrong branch this removes
Adding a second buffer and leaving the loop body as it was — copy, wait, compute — changes nothing
except UB consumption: the wait still separates the two, and the trace still shows MTE2 fully
before VECTOR. That is the "DB configured but not effective" state that 0012 detects and that 0052
exists to repair. An agent that measures no gain from double buffering usually has this shape and
concludes that double buffering does not help this operator.

The second wrong branch is budgetary: raising `bufferNum` in the kernel without raising it in the
host tiling produces either an over-subscribed UB or a tile budget computed on the wrong
denominator. The card states one number as the thing to verify, which is what makes it checkable.

## 3 · Ground / Source
`mem-02:6-10` diagnostic: every round waits for MTE2 or an L1 buffer before computing, with copy
and compute timelines end-to-end and rarely overlapping; consecutive tiles have no data
dependency and the current tile's compute does not write the next tile's destination; single-buffer
tiles are already at reasonable granularity and UB/L1 has room for a second input.

`mem-02:20-41` before/after: the after-loop pre-warms tile 0, then for each t computes
`cur = t & 1`, `next = cur ^ 1`, waits for `next` to be reusable, issues `CopyIn(buf[next], t+1)`
*before* `Compute(buf[cur])`, and marks the current buffer reusable afterwards.

Stop rules, `mem-02:50-55`: with very small tiles, or copy much longer than compute or vice versa,
double buffering may not repay the extra UB/L1 — measure a single-buffer baseline first; the last
round must not prefetch a non-existent tile, and buffer reuse must wait for the original consumer,
with event type and ID paired; data still being read by the current compute must not be overwritten
in the next buffer, and cross-stage temporaries need mem-04's lifetime analysis first; when memory
is short, reduce the tile or fall back to a single buffer rather than taking space from alignment
padding.

Evidence, `mem-02:48`: the card names the check — the msprof steady-state window should show MTE2
covering part of Vector/Cube rather than serialising, comparing `aiv_time` and MTE wait gaps, and
warns against reading the prologue/epilogue as irreducible steady-state cost — but gives no
numbers. Commits at `:59`: five arch35 changes (Conv2D cin-block prefetch into a second L1 buffer,
BatchNorm BlockSplitR pipelining, QKV tile reordering, MegaMoE dynamic wave pipeline, MegaMoE
buffer/batch sizing to the UB budget).

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one tiled operator three ways from a common tree: (S) single buffer; (D0) two buffers,
   copy issued after compute (the ineffective form); (D1) two buffers, copy issued before compute.
   Record `md5sum` of all three.
2. Sweep the tile size across a range where compute duration crosses copy duration in both
   directions, so the stop rule's regime is covered.
3. Capture `aiv_time` and, from the instruction trace, the alternation metric of 0012; five
   repetitions, median and spread; record peak UB for each build.
4. Verify the tiling budget expression by allocating exactly
   `2*inputTileBytes + workspaceBytes + outputTileBytes` and confirming the kernel initialises.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(D1 vs S)`, `gain(D1 vs D0)`, `alternation(build)`. Acceptance:
`alternation(D1) > alternation(D0)` and `gain(D1 vs D0) > spread` — that pair isolates the card's
actual claim, which is about issue order and not about buffer count. `gain(D1 vs S)` may be
negative at extreme tile sizes; that is the stop rule and is reported, not excluded.

Exit code is not the verdict. Outputs of all three builds are compared element-wise against a
reference: a prefetch that overwrites live data produces wrong results, not slow ones, and the
last-round prefetch of a non-existent tile may read out of range without failing.

Red input: build D0. If D0 and D1 have the same alternation, the reordering is being undone
somewhere — by the compiler or by the queue — and no conclusion about issue order follows.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured, by us or upstream — this card too promises 性能数据 and supplies a method
instead. No board, tile size, or operator family is established. It does not establish the
relationship between this manual ping-pong and `InitBuffer`-driven DoubleBuffer, which upstream
treats as related but never compares — and the DoubleBuffer mechanism has no card of its own
(0012). The budget expression is asserted, not verified, and it does not include the queue-depth
question of 0019. Per RULES.md Art. 1 nothing transfers to the 910 book.
