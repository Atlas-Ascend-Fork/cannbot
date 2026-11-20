```
ID:        0057-the-steady-value-is-the-mean-of-the-last-five-of-ten-and-the-metric-is-the-slowest-rank
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/index.md:65 — "perf 模式下循环执行至少 10 次算子调用，**前 5 次为 warm-up**（L2 cache 预热、DVFS 频率爬升），**取后 5 次 Task Duration 的均值**作为该 rank 的稳态性能"
           ops/ascendc-perf-optimize/references/comm-compute/index.md:71-74 — "多 rank 协同算子存在**木桶效应** … 因此最终性能指标取所有 rank 稳态均值的**最大值**，而非平均值。T_task = max(rank_0_steady_avg, …, rank_N_steady_avg)"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a capture on a named 950 board set showing that five warm-up iterations are insufficient
           — the sixth through tenth still trending — or that the cross-rank maximum is unstable
           across repeats of the whole ten-iteration block, which would make the reported metric
           a sample of a jittering distribution rather than a steady value.
```

# 0057 · The steady value is the mean of the last five of ten, and the metric is the slowest rank

## 1 · Claim
Upstream asserts a multi-rank capture protocol: each rank is bound to one NPU, all ranks start in
parallel (typically forked), and msprof produces one `PROF_` directory per active device with its
own `op_summary_*.csv`; at least ten operator invocations are run in perf mode, the first five are
discarded as warm-up because L2 is cold and DVFS frequency is still climbing, and the mean of the
last five `Task Duration` values is that rank's steady performance; and because all ranks
synchronise through `BarrierAll`/`CrossCoreFlag`, the operator's performance is the *maximum* of
the per-rank steady means, not their average. Not established here; nothing was captured.

## 2 · The wrong branch this removes
Two averaging errors, both natural. The first is averaging across ranks: it is what a statistician
would do with N samples of one quantity, and it is wrong here because the ranks are not samples —
they are stages of one barrier-synchronised system, so the slowest determines the whole. Averaging
hides exactly the imbalance the analysis is looking for, and it improves as the spread grows.

The second is skipping warm-up, or discarding only the first iteration. With a cold L2 and a
climbing clock, early iterations are slower for reasons that have nothing to do with the split being
evaluated; including them adds a bias that differs between candidates, since a candidate with more
tiles warms differently. The protocol's cost is ten launches per candidate against fifteen
candidates (0069), which is why it is stated as a minimum rather than a target.

## 3 · Ground / Source
`comm-compute/index.md:44-77`, the whole 性能采集方法 section. Multi-rank capture, `:44-61`: msprof
wrapping a fork-based multi-rank program produces profiling data per active device automatically,
one `PROF_` directory each with an independent `op_summary_*.csv`; every rank binds one card and all
start in parallel, each running the complete operator logic.

Steady value, `:63-67`, quoted in SOURCE, with the extraction detail: the CSV has one row per kernel
launch (ten rounds = ten rows), the first five rows are discarded and the last five averaged.

Bucket effect, `:69-75`, quoted in SOURCE, with the formula
`T_task = max(rank_0_steady_avg, rank_1_steady_avg, ..., rank_N_steady_avg)`.

Scope of the protocol, `:77`: 此采集方法适用于 MC² 算子的所有性能测试场景：基线 profiling、隔离测试
（COMM_ONLY / COMPUTE_ONLY）、方案对比测试 — so the isolation tests of 0059 and the candidate
comparisons of 0069 use the same ten-iteration, cross-rank-maximum rule.

Per-case recording, `:162-174`: TilingData parameters (with long and short block data separately),
isolation results (T_comm / T_compute / R) and `aiv_time` / bound type / key bottleneck metrics must
be recorded per case, 不得仅归组汇总 — the same per-case discipline as the single-core half (0010).

Note one asymmetry with the single-core convention: the steady value here is a *mean* of five, while
0054's L2-dirty convention reports a *median* — and this protocol has no dirty-cache variant at all,
which is a gap worth carrying rather than filling.

## 4 · Procedure
Later phase, needs one card per rank; this is the protocol whose own properties are being tested.
1. Device selection: one rank per device from an explicit `ASCEND_RT_VISIBLE_DEVICES` list; refuse
   to run if the list is shorter than the rank count; record each rank's driver readout, board token
   and occupancy before and after. The procedure refuses to assume the ranks' boards are identical,
   and a heterogeneous set is reported rather than averaged.
2. Run one MC² operator for 30 iterations instead of 10, capturing all rows per rank.
3. From the 30 rows per rank, compute: the per-iteration curve; the mean of iterations 6-10 (the
   protocol's value); the mean of 26-30; and the mean of five consecutive iterations at three other
   offsets.
4. Repeat the whole 30-iteration block five times, so the *stability* of the protocol's output can be
   measured rather than assumed.

## 5 · Checker — acceptance declared before the run
Verdict variables, declared now: `warmup_sufficient` = |mean(6..10) − mean(26..30)| within the
within-block spread; `block_stable` = the spread of the protocol's reported value across the five
repeated blocks; `argmax_stable` = whether the same rank is the maximum in all five blocks.
Acceptance of the protocol as written: `warmup_sufficient` true and `block_stable` small relative to
the candidate spacing that 0069 must resolve.

`argmax_stable` is reported whatever it shows: if the slowest rank changes between blocks, the
maximum is a noisy statistic and the protocol's output inherits that noise, which matters for every
comparison built on it.

Exit code is not the verdict. All rows for all ranks are published; a rank whose CSV has fewer rows
than expected is reported `rank_undersampled` rather than averaged over what it has — a
silently-short CSV would otherwise produce a confident number from three iterations.

Red input: iterations 1-5 included in the mean. That must shift the value materially; if it does not,
there is no warm-up transient on this operator and the discard rule is inert for it — a legitimate
finding, reported as such.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. No board, no rank count, no operator. It does not establish that five warm-up
iterations suffice, nor that ten iterations resolve the differences the search needs; both are
asserted. It says nothing about jitter across ranks beyond the maximum rule — upstream ships a
separate, orphaned jitter analysis (0073) that this protocol does not reference. It does not
establish that per-rank binding is one-to-one on any real system, nor what happens when a rank
shares a die with another tenant.
