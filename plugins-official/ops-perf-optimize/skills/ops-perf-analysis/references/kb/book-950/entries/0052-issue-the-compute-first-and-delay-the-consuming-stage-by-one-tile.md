```
ID:        0052-issue-the-compute-first-and-delay-the-consuming-stage-by-one-tile
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin, but the only card in this library carrying a full
           measurement (platform, shape, BlockDim, md5-checked rebuilds, per-shape sweep and a
           reversal ablation); still nothing measured by us
BOARD:     950PR
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-02-stage-order-rescheduling.md:65 — "A5（arch3510，Ascend950PR，BlockDim 56）上的 RMSNorm+RoPE+KV Cache 分页散射写融合算子，T=10752、heads (8,1,1)。交替换包各两轮、每轮复核 kernel `.o` md5"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-02-stage-order-rescheduling.md:80 — "在计算发射优先的基础上把写出改回不延后，实测 39.83 → 42.72us（**+7.3%**）、`mte3_wait` 从 0.05 弹回 0.22~0.28"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired run on a named 950 board, on an operator other than the one measured, in which
           issuing the compute before the bulk copy and delaying the consuming stage by one tile
           leaves `aiv_time` unchanged beyond run spread while `aiv_mte3_wait_ratio` stays above
           0.4 — the reordering would then not be the mechanism, and the single measured operator
           would be the boundary of the claim rather than an instance of it.
```

# 0052 · Issue the compute first and delay the consuming stage by one tile

## 1 · Claim
Upstream asserts that when DoubleBuffer is enabled and the pipeline still does not overlap, the
cause is usually the scalar core — the single, in-order issue source for every pipe — being
blocked, so that later instructions cannot be issued at all; and that two orthogonal reorderings of
the loop body fix it without changing a line of computation: issue the compute before the bulk
copy, and delay the consuming stage by one tile so it writes back the *previous* tile, whose
asynchronous computation has already finished. Upstream reports, for one fused operator on
Ascend950PR, 58.99 → 52.86 → 39.61 us (−32.9%), with a reversal ablation costing +7.3%. Not
established here: no board was touched by this book, and the measurement is upstream's.

## 2 · The wrong branch this removes
The agent has already done everything the standard advice asks. DoubleBuffer is enabled; the tile
fits; no lane exceeds the bound cut (0006); the overlap factor says half the time is spent
waiting (0007). Every diagnosis page it can reach describes a bottleneck it does not have. Without
this card the next move is to enlarge tiles or re-tile, which changes the shape of the problem
rather than its ordering, and typically produces a small regression.

The specific misreading this removes is about DoubleBuffer itself: two buffers *permit* overlap,
they do not create it. What creates it is instructions being issued, and every pipe's instructions
are issued by one in-order scalar stream. So a loop whose first statement is a burst of copy
instructions can back-pressure that stream and delay the compute that was supposed to overlap with
the copies — the buffers are idle and the pipeline is serial, which looks exactly like DoubleBuffer
not being enabled.

## 3 · Ground / Source
Trigger conditions, `nobound-02:8-21`, in two stages. First msprof: DoubleBuffer enabled but load
and compute still not overlapping (the trace signature of 0012); all units around 0.5 with no
single bound; overlap factor around 1.6 with attainment near 50%; `aiv_mte3_wait_ratio` above 0.4.
Then simulation, because — and this is the sentence worth carrying —

> msprof 的 ratio 是时间占比、不含因果，说明得了"重叠不够"，说明不了"谁挡住谁"

so the instruction-level trace is needed to see, during a scalar-lane gap, which lane is busy:

> - **计算泳道满负荷** → 消费阻塞
> - **搬运泳道满负荷、但每次只放行 1 条指令**（单条耗时可低至 1ns） → 发射阻塞

Mechanism, `nobound-02:25-32`: address computation, DataCopy issue and VF parameter packing all sit
on the same scalar instruction stream; two ways for it to stall — a `DeQue()` waiting on the
asynchronous computation just issued (consumption blocking), and a tile's copy instruction count
exceeding the hardware queue depth so the queue back-pressures the issuer (issue blocking). The two
are orthogonal: 计算提前发出后**仍要跑完**，所以消费阶段该延后还得延后.

The change, `nobound-02:36-58`: `CopyIn(next); Compute(cur); CopyOut(cur);` becomes
`Compute(cur); if (next.Valid()) CopyIn(next); if (pend.Valid()) CopyOut(pend); pend = cur;` with a
final flush. Support, `:61`: output queue depth 2, and the cross-tile index/metadata window must
hold three tiles simultaneously — pend, in-flight and prefetch.

Measurement, `nobound-02:63-75`, quoted as the exemplar of evidence style this book asks entries to
imitate. Platform and shape are named; the builds were alternated in two rounds each with the
kernel `.o` md5 re-checked per round; three timing conventions are reported, not one:

> | 口径 | 改前 | 仅延后写出 | 两处都改 | 总变化 |
> | msprof Task Duration | 58.99 us | 52.86 us | **39.61 us** | **-32.9%** |
> | back-to-back | 54.46 us | 46.51 us | 33.99 us | -37.6% |
> | L2 冲脏后 p50 | 91.85 us | 89.99 us | 89.57 us | -2.5% |

with mechanism-side readouts — `aiv_mte3_wait_ratio` 0.47 → 0.06, overlap factor 1.63 → 1.90 →
2.58, `aiv_mte2_ratio` 0.497 → 0.814 (搬运接近饱和，瓶颈已从编排转为搬运量本身) — and a per-shape
sweep in which the change is neutral at T=64 and T=512, −24.6% at T=4096 and −35.3% at T=10752.

Stop rules, `nobound-02:77-86`, each of which is a disclosed limit rather than a caveat: do not
hand-schedule as a general method — confirm DB is on and genuinely not working first, since
hand-scheduling spreads tile-boundary state through `Process`; the two changes are orthogonal and
undoing only the delayed write-back costs +7.3% (the reversal ablation, quoted in SOURCE); confirm
that raising queue depth does not consume UB (0019); widen the metadata window and change the
kernel-side and host-side `static_assert` together; expect nothing at small shapes, where
`T < coreNum × ubFactor` leaves one tile per core and no pipeline forms; buffer-reuse safety rests
on TQue FIFO allocation, which no document guarantees (0053); the simulator's core count differs
from the machine so only relative occupancy is admissible (0010); and a reported gain must state
its cache state, since an L2-dirty run dilutes it to −2.5% (0054).

## 4 · Procedure
Later phase, needs a card. The point of the procedure is transfer: the measurement exists for one
operator, and what is unestablished is whether the reordering generalises.
1. Device selection per 0010: `ASCEND_RT_VISIBLE_DEVICES` explicit, occupancy read before and
   after, board token taken from the driver readout — 950PR in the source measurement, but this
   procedure does not assume the board it gets is the board upstream used, and a run on 950DT
   would be recorded as a different board, establishing nothing about 950PR.
2. Reproduce first: build the named operator (RMSNorm+RoPE+KVCache paged scatter-write fusion) in
   the three configurations of the table — before, write-back delayed only, both changes — from one
   source tree, alternating the packages in two rounds and re-checking each kernel `.o` md5 per
   round, exactly as upstream describes.
3. Transfer second: repeat the three configurations on two other operators with the same trigger
   signature (DB enabled, overlap factor near 1.6, `aiv_mte3_wait_ratio` > 0.4) but different
   structure — one without a scatter write, one with a longer computation per tile.
4. Report all three timing conventions per configuration — msprof Task Duration, back-to-back, and
   L2-dirty p50 — plus `aiv_mte3_wait_ratio`, the overlap factor and `aiv_mte2_ratio`; five
   repetitions each, median and spread.
5. Sweep T over 64, 512, 4096, 10752 for every operator, so the small-shape null result is
   reproduced or refuted rather than assumed.
6. Run the reversal ablation on every operator: from the both-changed build, undo only the
   write-back delay.
7. Compare outputs bit-exactly against the before-build, per the card's own requirement that the
   FIFO-reuse assumption be underwritten by 结果与改前逐位一致.

## 5 · Checker — acceptance declared before the run
Verdict variables, declared before any run: `dt_both`, `dt_delay_only`, `dt_reversal` (each as a
percentage of the before-build's median, per timing convention), `wait_before`/`wait_after`,
`overlap_before`/`overlap_after`, and `bitexact` against the before-build.

Acceptance for reproduction: `dt_both` within ±5 percentage points of −32.9% on Task Duration for
the named operator at T=10752, with `wait_after` below 0.1 and `overlap_after` above 2.4.
Acceptance for transfer: on each new operator, `dt_both` more negative than the run spread, and
`dt_reversal` positive — the ablation is what distinguishes "the reordering did it" from "the
rebuild did it". Acceptance for the disclosed null: T=64 and T=512 within spread of zero.

The process exit code is not the verdict, and neither is the fastest number: all three timing
conventions are reported together, and a result quoted without its cache state is not a result
(0054). Bit-exactness is a gate, not a bonus — a faster build that is not bit-identical to the
before-build has changed the computation and the timing comparison is void.

This checker can go red, and the inputs that do it are named in advance. The reversal build must be
slower; if it is not, the attribution to stage ordering fails even though the headline number
reproduced. The small shapes must show nothing; if they show a large gain, the mechanism is not
pipeline formation and the explanation is wrong. And a rebuild of an unchanged configuration must
reproduce its own md5 — if it does not, the build is not deterministic and no two-point comparison
between builds carries attribution at all.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
This book measured nothing. Upstream's readouts are for exactly one operator, one shape family, one
BlockDim (56) and one board token (Ascend950PR); they establish nothing for 950DT, nothing for a
different fusion, and — by upstream's own sweep — nothing at T=64 or T=512, where the change is
neutral. The −32.9% is a Task Duration figure on a warm cache; the same change is −2.5% when L2 is
dirty, which is the deployment-realistic case whenever another operator runs between calls, and
neither number is "the" gain. The mechanism (scalar-core issue blocking) is a reading of a
simulator trace whose core count differs from the machine's, so it is a qualitative attribution.
The queue-depth precondition is unverified (0019), the FIFO-reuse assumption is undocumented
(0053), and the technique presupposes that DoubleBuffer is enabled and ineffective — a state this
book has no procedure for confirming beyond the visual predicate of 0012.
