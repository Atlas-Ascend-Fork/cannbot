```
ID:        0011-aiv-mte3-wait-ratio-above-0.4-says-write-back-is-waiting-on-the-compute-just-issued
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/metrics.md:33 — "`aiv_mte3_wait_ratio` | 写回泳道处于等待的时间占比 | msprof `ResourceConflictRatio.csv`；> 0.4 多为消费阶段紧跟异步计算（nobound-02）"
           ops/ascendc-perf-optimize/references/single-core-pipeline/no-bound.md:12 — "**写回泳道在等计算**：`aiv_mte3_wait_ratio` > 0.4，多半是消费阶段紧跟发起它的异步计算"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a kernel on a named 950 board with `aiv_mte3_wait_ratio` above 0.4 whose write-back
           stage does not consume a just-issued asynchronous computation — e.g. one waiting on
           a GM bank conflict or on an unrelated event — which would show the ratio does not
           carry the diagnosis it is credited with.
```

# 0011 · aiv_mte3_wait_ratio above 0.4 says write-back is waiting on the compute just issued

## 1 · Claim
Upstream asserts that `aiv_mte3_wait_ratio` is the fraction of time the write-back lane spends
waiting, that it is read from msprof's `ResourceConflictRatio.csv`, and that a value above 0.4
is usually the signature of a consuming stage placed immediately after the asynchronous
computation that produces its data. Not established here. The number 0.4 is stated twice in the
skill, in two files, with no derivation; the one measured instance moves from 0.47 to 0.06 under
the reordering of 0052.

## 2 · The wrong branch this removes
An agent looking at a kernel whose lanes are all around 0.5 has, from the ratio columns alone,
no way to tell an ordering problem from a genuine bandwidth problem, and will reach for a
memory technique. This ratio is the one cheap discriminator upstream offers: it does not measure
how much data moves, it measures how long the mover sat idle waiting for a producer. High value
plus low lane ratios means the fix is in the ordering of the loop body, not in the number of
bytes — and the ordering fix (0052) is free of data-layout risk, while a memory fix is not.

The second wrong branch: reading the ratio as a bandwidth signal. `aiv_mte3_ratio` (busy share)
and `aiv_mte3_wait_ratio` (waiting share) differ by one word and live in different CSV files.
An agent that conflates them will report a saturated write-back path for a kernel whose
write-back path is idle.

## 3 · Ground / Source
`metrics.md:33`, the vocabulary table row, verbatim:

> | `aiv_mte3_wait_ratio` | 写回泳道处于等待的时间占比 | msprof `ResourceConflictRatio.csv`；
>   > 0.4 多为消费阶段紧跟异步计算（nobound-02） |

`no-bound.md:12` repeats the line as one of that page's判定条件. `nobound-02:18` uses it as one
of three msprof triggers: `aiv_mte3_wait_ratio`（或对应写回泳道的 wait 比例）**高于 0.4**——
写回在等计算. The mechanism is stated at `nobound-02:29`: `DeQue()` 等的是**刚刚发出、还在跑**
的那次异步计算.

The one measured instance in the whole library, `nobound-02:73`: `aiv_mte3_wait_ratio` 0.47 →
0.06 across the two reorderings, on A5/arch3510/Ascend950PR, BlockDim 56, T=10752. The reversal
ablation at `:80` moves it back: mte3_wait 从 0.05 弹回 0.22~0.28 when only the delayed write-back
is undone. That pair — one direction and its reversal — is the strongest evidence in the skill
that the ratio tracks the ordering rather than the workload, and it is still one operator.

## 4 · Procedure
Later phase, needs a card. Board token from the driver readout, never assumed.
1. Device selection per 0010: explicit visible-devices, occupancy recorded before and after,
   refusal to run on an unnamed die.
2. Build three kernels that all write back the same number of bytes per tile, differing only in
   the placement of the write-back relative to the producing computation: (A) write-back
   immediately after the compute that produces it; (B) write-back delayed by one tile, as in
   0052; (C) write-back immediately after compute, but with the produced data coming from a
   synchronous path so no asynchronous wait is possible.
3. Capture each with msprof including `ResourceConflictRatio.csv`; record
   `aiv_mte3_wait_ratio`, `aiv_mte3_ratio` and `aiv_time`, five repetitions, median and spread.
4. Sweep tile size so that the compute duration per tile crosses the write-back duration in both
   directions, and record the ratio as a function of that crossing.

## 5 · Checker — acceptance declared before the run
Verdict variable `wait_ratio_diagnoses_order`, declared now: the ratio carries the claimed
diagnosis iff `wait(A) > 0.4`, `wait(B) < 0.2`, and `wait(C) < 0.2`, with each gap larger than
the measured spread. Kernel C is the discriminating arm: it has the same textual shape as A —
a write-back right after a compute — and must NOT trip the ratio, because there is nothing
asynchronous to wait for. If C also exceeds 0.4, the ratio is measuring adjacency rather than
waiting, and the diagnosis attached to it is wrong.

Exit code is not the verdict. All three ratios are printed with spreads, and the sweep curve is
published whole, including the region where A and B coincide.

Red input: kernel C, by construction. A checker that read only kernel A would confirm the claim
by finding what it went looking for; this one is built so that a specific, named case must come
out low, and the check fails if it does not.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured by us. The 0.4 line has no derivation anywhere upstream and no scope: it is not
established for any shape, any operator family, or any board — the single supporting observation
is one fused operator at T=10752 on 950PR. It says nothing about the AIC-side write-back path,
nor about `ResourceConflictRatio.csv` being present on any particular CANN version. It does not
establish that a low ratio means the ordering is right; a kernel with no overlap at all can have
a low wait ratio because nothing is ever waited on.
