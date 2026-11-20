```
ID:        0137-ping-pong-is-required-in-the-tile-resident-scan-and-overlapping-its-buffers-corrupts-output-without-an-error
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scan/fallback/tiling-flow.md:47-49,272-288 —
           "**x/val/out 必须各开两份做 ping-pong** ... 不做的话四条流水占比之和只有 101%（全串行），
           实测慢 12~31%" · "⚠️ **不要为省 UB 让两个缓冲区叠用。** ... 加了 ping-pong 后这会在 MTE3
           搬出该输出区的同时被下一块的扫描写坏，**必须拆成独立分配**。这个坑不报错，只出错误结果"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a tile-resident scan on a named 950 board built with the int32 scan region overlaid on
           the int64 output region under ping-pong that produces correct output across a long run
           — the corruption would then not be reachable, and the mandatory separate allocation
           would be over-cautious.
```

# 0137 · Ping-pong is required in the tile-resident scan, and overlapping its buffers corrupts output without an error

## 1 · Claim
Upstream asserts that in the tile-resident scan (`N > 1`, index-carrying), the input, running-value
and output regions must each be allocated twice for ping-pong. Upstream states the reason as a
pipeline fact: carry between blocks is serial so the compute cannot overlap, but loading the next
block, computing the current one and storing the previous one can — and states the consequence of
not doing it as the four pipes' occupancy summing to 101 %, fully serial, `实测慢 12~31%`.
Upstream separately asserts a hazard created by the same ping-pong: a single-buffered
implementation commonly overlays the int32 scan region on the upper half of the int64 output
region, relying on `Cast` reading 4 B per element and writing 8 B per element to widen in place —
which upstream says is entirely valid single-buffered — and asserts that under ping-pong this gets
overwritten by the next block's scan while MTE3 is still moving that output region out, so the two
must be separately allocated. Upstream states the failure mode explicitly: `这个坑不报错，只出错误
结果`. Upstream also asserts the budget consequence — the doubling halves `rChunk` and doubles the
block count, `这正是流水需要的，不必回调`, and at least two blocks are needed for any overlap at all.
Not established here.

## 2 · The wrong branch this removes
Two wrong branches, and they pull in opposite directions, which is why upstream states both.

The first is skipping ping-pong to keep `rChunk` large. It is the natural instinct — a bigger chunk
means fewer blocks, fewer carries, less per-block overhead — and it produces a kernel whose profile
looks fully utilised: every pipe is busy, and the occupancies sum to 101 %, which reads as healthy
until you notice that 101 % across four pipes means nothing ever overlaps. Upstream's framing is
worth keeping: the sum of pipe occupancies is the diagnostic, and a sum near 100 % on a four-pipe
kernel is the signature of complete serialisation, not of good utilisation.

The second is adopting ping-pong and keeping the buffer overlay, which is the memory-saving trick
that made the single-buffered version fit. This one does not show up in any profile at all. It
produces wrong output, intermittently, on the blocks where MTE3's store of block *n* is still in
flight when block *n+1*'s scan writes. A correctness test on a small shape — one or two blocks —
passes, because the overlap window only exists when there are enough blocks to pipeline. The bug
therefore appears exactly when the kernel starts working well.

The third, smaller: reacting to the halved `rChunk` by tuning it back up. Upstream pre-empts this —
the halving is what creates the block count that the overlap needs.

## 3 · Ground / Source
The requirement, stated inside the routing tree, `scan/fallback/tiling-flow.md:47-50`:

```
│    │      并且 **x/val/out 必须各开两份做 ping-pong**：块间 carry 串行、
│    │      计算无法重叠，但「搬入下一块 / 算当前块 / 搬出上一块」可以。
│    │      不做的话四条流水占比之和只有 101%（全串行），实测慢 12~31%。UB 预算见 §5.2
│    │      若 lane 数用不满（如 M=1 且 N 只切得出十几个元素宽的 tile）→ 转 §4.1
```

The budget and the hazard, `:272-288`, in full:

```
### 5.2 tile 常驻 + ping-pong（含索引，`N > 1`）

slotT      = CeilAlign(nCnt * eb, 32) / eb        # 每行槽位元素数（32B 对齐）
computeLen = mFold * slotT                        # 每个 r 步的 lane 数
bytesPerR  = computeLen * (2*eb + 2*eb + 4 + 2*8)
                           x双份  val双份 int32扫描区 int64输出区双份
rChunk     = UB_BUDGET / bytesPerR

相对单缓冲正好翻倍，于是 `rChunk` 减半、块数加倍——**这正是流水需要的，不必回调**。
块数至少 2 才有重叠（R 一块装得下时双缓冲自然失效）。

> ⚠️ **不要为省 UB 让两个缓冲区叠用。** 单缓冲时常把 int32 扫描区叠在 int64 输出区的
> 高半段上，靠 Cast「读指针 4B/元素、写指针 8B/元素」的错位就地展宽（完全成立）。
> 加了 ping-pong 后这会在 MTE3 搬出该输出区的同时被下一块的扫描写坏，**必须拆成独立分配**。
> 这个坑不报错，只出错误结果——所以上面公式里 int32 扫描区那项是单独的 `+4`。
```

The same formula appears in the mode-0 pseudocode, `:178-181`:

```
    slotT = CeilAlign(nLen * eb, 32) / eb
    computeLen = mFold * slotT
    bytesPerR = computeLen * (2*eb + 2*eb + 4 + 2*8)    // x双份 val双份 int32扫描区 int64输出区双份
    rChunk = UB_BUDGET / bytesPerR
```

Reading the per-`r` byte cost term by term: `2*eb` for two input copies, `2*eb` for two
running-value copies, a bare `4` for one int32 scan region — one copy, not two, and upstream says
in the warning that this term being separate is the whole point — and `2*8` for two int64 output
copies. At fp32 (`eb = 4`) that is `8 + 8 + 4 + 16 = 36` bytes per lane per `r` step; at fp16
(`eb = 2`), `4 + 4 + 4 + 16 = 28`. The int64 output dominates at both, and the int32 scan region
that must not be overlaid is the smallest term — 11 % of the cost at fp32. That asymmetry is the
reason the overlay is tempting and the reason it is not worth it.

`UB_BUDGET` is defined once, in the mode-selection pseudocode at `:135`:
`UB_BUDGET = ub_size - 8KB   // 留余量给框架与对齐`. So the tile-resident budget subtracts a flat
8 KB before anything else, a reserve whose size is stated once with no derivation. Under 0104's
rule that 8 KB is a hardcoded literal — software 经验值, searchable — while `ub_size` is a chip
specification field.

A related WAR hazard of the same species is recorded two sections later, `:344`, and is quoted
because it is the same failure shape at a different scope:

```
2. **一核多 work-item 的 WAR 屏障**：本 item 末次 CopyOut(MTE3) 读 running-(min,idx)，下一 item InitRunning(V) 覆写；`MTE3_MTE2` 不约束 MTE3→V，须补 `MTE3→V` 屏障，否则每 work-item 最后一个 r 的 idx 被覆写成 0（值走独立缓冲正确，掩盖问题，仅"一核多 item + 大 R"暴露）。
```

Note the disclosure inside it: the value is correct because it uses a separate buffer, which masks
the problem, and only "one core, many work-items, large R" exposes it. Both hazards in this entry
share that structure — correct on small cases, wrong on the cases the optimisation is for.

The `12~31%` figure carries no board, shape, dtype, core count, tool or repetition count. It is a
range spanning a factor of 2.6.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first: one build, 30 in-process runs and 5
fresh-process runs, interquartile range over median.

Arm 1 — the ping-pong benefit. Take a Cummin case with `N > 1` and R large enough for at least 8
blocks (`M=64, R=8192, N=512`, fp32). Build two kernels from one source with one compiler pin,
single-buffered and ping-pong, sized by the respective budgets. md5 both; host echo of `rChunk`,
`computeLen`, `slotT` and the resulting block count. Require bit-identical output between the two
arms and against a CPU reference. Record `aiv_time` and the four pipe occupancies under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case. The occupancy
sum is recorded per arm — upstream's `101%` is a prediction about the single-buffered arm and is
checked as such.

Arm 2 — the corruption, which is the arm this entry exists for and is a poison arm by construction.
Build a third kernel: ping-pong enabled, with the int32 scan region overlaid on the upper half of
the int64 output region as the single-buffered version does. Run it 200 times on the same input,
comparing every run's output elementwise against the CPU reference, and record the number of runs
with any mismatch, the distribution of first-mismatch indices, and whether mismatches cluster at
block boundaries. A single run is not evidence here: upstream describes a race, and a race that
fires rarely still fires.

Arm 3 — block-count dependence. Repeat arm 2 at R giving 1, 2, 4, 8 and 32 blocks. Upstream's
mechanism predicts zero mismatches at 1 block (no overlap exists) and a rising rate with block
count. That prediction is what distinguishes "a race in the overlap window" from "a bug somewhere
else".

Refuses to assume: that a free die stays free; that a die may be substituted; that `ub_size` is any
literal (queried, and `UB_BUDGET = ub_size − 8KB` is derived from it); that one clean run means the
race does not exist — the 200-run count is fixed in advance; that a mismatch is the described race
rather than another bug — arm 3's block-count dependence is what tests the mechanism.

## 5 · Checker — acceptance declared before the run
Verdict variable `pp_gain` = single-buffered median `aiv_time` / ping-pong median `aiv_time`, and
`occ_sum(arm)` = the sum of the four pipe occupancies. Declared before the run: upstream's benefit
claim is supported iff `pp_gain ∈ [1.12, 1.31]` and `occ_sum(single) ≈ 100 %` while
`occ_sum(pingpong) > 130 %`. Values outside those bands are reported as measured, in either
direction. Verdict variable `corrupt_rate(blocks)` = mismatching runs / 200 at each block count.
Declared before the run: the hazard is confirmed iff `corrupt_rate > 0` at 8 or 32 blocks and
`corrupt_rate = 0` at 1 block. The OVERTURN fires iff `corrupt_rate = 0` at every block count
across all 200 runs — the overlay would then be safe here, and the mandatory separate allocation
over-cautious on this board.

The exit code is not the verdict, and in arm 2 that is the whole point: the corrupting kernel exits
0 and produces wrong numbers, which is exactly what upstream says (`这个坑不报错，只出错误结果`).
The instrument is the elementwise comparison over every one of the 200 runs, and the checker fails
red if fewer than 200 comparisons were performed rather than reporting the rate over the runs that
completed. Second guard: arms 1 and 2 must echo different buffer layouts and different `rChunk`
values; if the build collapsed them, no comparison exists. Third: the bit-identity requirement
between arm 1's two arms — a ping-pong build that changes the result is broken, and its timing is
meaningless.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `12~31%` and `101%`
figures are upstream's, unconditioned.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish the 12–31 % ping-pong benefit — a range spanning
2.6× with no board, shape, dtype or repetition count — and does not establish the 101 % occupancy
signature. It does not establish that the overlay corruption occurs on any board; upstream
describes a mechanism and this book has not reproduced it, which is why §4 arm 2 is written as a
poison arm with a fixed run count. It does not establish the 8 KB `UB_BUDGET` reserve. It does not
cover the WAR barrier hazard quoted in §3 beyond recording it — that is a synchronisation claim
about kernel code, and the barrier's necessity is not tested here. It says nothing about the
`N == 1` modes, whose buffering is a different structure (0134). No chip is named anywhere in the
scan family, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT because that is where
our run would happen. Nothing here is established for any 910-family board.
