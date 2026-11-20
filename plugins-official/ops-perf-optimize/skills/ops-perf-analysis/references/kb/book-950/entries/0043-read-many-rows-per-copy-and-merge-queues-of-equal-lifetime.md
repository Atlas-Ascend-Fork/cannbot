```
ID:        0043-read-many-rows-per-copy-and-merge-queues-of-equal-lifetime
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-03-batched-row-copy.md:14 — "批量化先减少传输描述符和同步次数，再让 MTE 处理更长的连续块。合并队列将成对数据放在一个已对齐的物理 buffer 的不同 offset，使用一次 Alloc/EnQue/DeQue 管理；它只改变物理布局，不改变两个逻辑张量各自的计算语义"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board where copying many rows per `DataCopyPad` does not
           reduce `aiv_time` against per-row copies at a shape with many short contiguous rows —
           descriptor and synchronisation cost would then not dominate as claimed.
```

# 0043 · Read many rows per copy and merge queues of equal lifetime

## 1 · Claim
Upstream asserts (card mem-03, evidence: four named arch35 commits, no numbers) two batching
moves: issue one multi-row `DataCopyPad` sized by the UB budget instead of one copy per row; and
place two logical tensors that share a lifetime at different offsets of one aligned physical
buffer, managed by a single Alloc/EnQue/DeQue. Upstream asserts the merge changes physical layout
only, not either tensor's computation semantics, and that batch size, queue depth and the space
left for indices and temporaries must be solved together in tiling. Not established here.

## 2 · The wrong branch this removes
Per-row copies and per-tensor queues are the readable decomposition, and their cost is not in the
bytes but in the count: one descriptor, one EnQue and one DeQue per row per tensor. The profile
shows a modest MTE utilisation with a busy scalar lane and many short copies — which the routing
tree (0005) may not call a memory bound at all, and which the scalar page will attribute to
per-tile fixed cost (0017). An agent looking at bytes moved will conclude the copies are already
efficient.

The wrong branch inside the repair is the merge: two tensors in one buffer is a lifetime claim. If
one outlives the other, or one is written while the other is read, the merge is a correctness bug
that appears only under specific interleavings.

## 3 · Ground / Source
`mem-03:6-10` diagnostic: a loop copying one row or one logical tensor at a time while neighbouring
rows are regularly laid out in GM and are consumed in the same stage; dense small
`DataCopyPad`/`DataCopyExt` in the trace with several short-lived queues, MTE utilisation low but
instruction and synchronisation overhead visible; input rows fitting UB whole, or several outputs
accumulable in UB before one write-back.

`mem-03:27-37` after-form: `rowsPerCopy = ChooseRowsPerCopy(availableUb, rowBytes, indexBytes,
bufferNum)`; one `pair` tensor allocated from a queue with `a = pair` and `b = pair[alignedRowElems]`;
a multi-row `DataCopyPad(xUb, xGm[rowBase], {rowsPerCopy, rowBytes, srcStride, dstStride}, pad)`;
one `EnQue`; a matching batched write-back. `mem-03:39` says the maximum batch is derived backwards
from `rowsPerCopy * rowBytes`, the index/scale temporary area, the output area and `bufferNum`, and
that the output batch needs a byte ceiling so a single large copy does not evict UB-resident data.

Stop rules, `mem-03:45-50`: merged tensors must share a lifetime, with offsets, lengths and
alignment computed from one host/kernel layout, and neither may overwrite the other; `srcStride`
and `dstStride` are derived from the GM and UB physical pitches respectively and element counts
must not be confused with byte counts; increasing queue depth must be deducted from the host's
available UB (cf. 0019, which says the deduction depends on whether depth and buffer count are
coupled); and rows that will not be consumed must not be dragged in by the batch.

Evidence, `mem-03:43`: compare MTE copy count, queue operation count and `aiv_time`, focusing on
short rows, repeated rows and paired results — no values given. Commits at `:54`: MoE
`xCopyInQueueBufferNum` selection by UB headroom, BatchNormGrad paired `dbeta`/`dgamma` queue
merge with multi-row `DataCopyPad`, `unique_dim` copy-granularity increase, `scatter_update`
column split with multiple updates per copy.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one row-wise operator three ways from a common tree: (P) per-row copy, separate queues;
   (B) batched multi-row copy, separate queues; (M) batched copy plus merged paired queue. Record
   `md5sum` of each.
2. Sweep `rowsPerCopy` over powers of two up to the UB budget, at two row widths — one short
   enough that descriptor cost dominates, one wide enough that it cannot.
3. Capture `aiv_time`, copy instruction count, queue operation count, `aiv_mte2_ratio`; five
   repetitions, median and spread; record peak UB per build.
4. Compare outputs element-wise against a reference, including a case where the two merged tensors
   have deliberately different lifetimes, built as a fourth variant (M') to exercise the stop rule.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(rowsPerCopy, width)`, `copies(build)`, `queue_ops(build)`,
`correct(build)`. Acceptance: `copies(B)` ≈ `copies(P)/rowsPerCopy`; `queue_ops(M)` ≈ half
`queue_ops(B)`; `gain` positive at the short width and decreasing with width. A gain at the wide
row width without a reduction in `copies` is unattributed and reported as such.

Exit code is not the verdict. Correctness is element-wise over both merged tensors; a merge bug
typically corrupts one tensor's tail, which a spot check on the first rows would miss.

Red input: variant M' with mismatched lifetimes. It must fail the element-wise comparison; if it
passes, the interleaving that exposes the hazard was not exercised and the merge result is not
admissible as evidence of safety.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured, by us or upstream. No board, shape or operator family is established. It does
not establish `ChooseRowsPerCopy`'s form — the card leaves the solver to tiling — nor the UB
deduction for queue depth, which depends on the open question in 0019. It says nothing about
non-contiguous rows in GM, where the batched descriptor's stride form may not apply.
