```
ID:        0056-mc2-timings-come-from-msprof-task-duration-never-from-a-host-side-clock
LABEL:     trap
LEVEL:     L7 (verification)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/index.md:42 — "⚠️ **禁止使用 host 侧计时（std::chrono / gettimeofday 等）替代 msprof 采集**。MC² 算子的所有性能数据（基线、隔离测试、方案对比）**必须**通过 msprof 采集，从 `op_summary_*.csv` 的 `Task Duration(us)` 字段提取。host 侧计时包含 launch 开销且精度不足，不得作为性能指标"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired capture on a named 950 board in which host-side wall-clock timing and msprof
           `Task Duration` rank a candidate set identically and differ by a constant offset — the
           prohibition would then be about precision rather than about validity, and the cheaper
           instrument would be admissible for ranking.
```

# 0056 · MC² timings come from msprof Task Duration, never from a host-side clock

## 1 · Claim
Upstream asserts that every MC² performance datum — baseline, isolation test, candidate comparison —
must be captured with msprof and read from the `Task Duration(us)` column of `op_summary_*.csv`, and
that host-side timing (`std::chrono`, `gettimeofday`) is forbidden as a substitute because it
includes launch overhead and lacks precision. Not established here; nothing was captured.

## 2 · The wrong branch this removes
Host timing is the path of least resistance for a multi-rank program: the harness already forks the
ranks, so wrapping the call in a clock is three lines and needs no profiling tools, no extra
storage and no post-processing. It produces a number that moves in the right direction when the
kernel improves, which is why it survives review. What it silently includes is launch overhead and
host-side synchronisation, both of which are large relative to the differences this analysis is
trying to resolve — the search of 0069 distinguishes candidates by 5-10 microseconds, and it
compares fifteen of them.

The second harm is comparability. Every number upstream reports, and every threshold in the MC²
chain (0058's R bands, 0060's pollution gap, 0068's utilisation cuts), is defined against
`Task Duration`. A campaign measured with a host clock cannot be compared with any of them, and the
mismatch is invisible because both quantities are in microseconds.

## 3 · Ground / Source
`comm-compute/index.md:38-46`, the 性能采集方法 preamble and the prohibition quoted in SOURCE. The
preamble states the reason MC² capture differs from single-card capture at all:

> MC² 算子是多 rank 协同的通算融合算子，其性能采集与单卡算子有本质区别——通信开销需要跨卡交互才能
> 真实体现，且多 rank 间的同步（BarrierAll / CrossCoreFlag）使整体性能受制于最慢的 rank。

The capture command, `:48-57`, names the flags that make `Task Duration` and the pipe metrics
available: `msprof --output={prof_dir} --ai-core=on --aic-mode=task-based
--aic-metrics=PipeUtilization --task-time=on --ascendcl=on {exe} {m} {k} {n} {rankNum} perf {tileCnt}`.
`:67` states where the column lives — `PROF_*/mindstudio_profiler_output/op_summary_*.csv`, one row
per kernel launch — and `:77` extends the same protocol to the isolation tests and candidate
comparisons.

Note the difference from the single-core half of this skill, which reads `aiv_time` from
`kernel_details.csv` (0010): the MC² path uses `Task Duration` from `op_summary_*.csv`. Two
conventions, two files, one skill — a replacement must not silently unify them, since
`Task Duration` includes more than the AIV-side duration.

## 4 · Procedure
Later phase, needs cards on all ranks. Board token from each rank's driver readout; device selection
per 0057.
1. Instrument one MC² operator both ways in a single run: host-side `std::chrono` around the launch,
   and msprof capture of the same launches.
2. Run the ten-iteration protocol of 0057 and extract, per rank: the host-side per-iteration times
   and the `Task Duration` rows.
3. Build a candidate set of at least five splits differing by a few microseconds in expected time
   (from 0069's Top-N), and rank them under both instruments.
4. Report both rankings, the per-candidate difference, and the launch overhead implied by the gap.

## 5 · Checker — acceptance declared before the run
Verdict variables `rank_agreement` (Kendall's tau between the two rankings over the candidate set)
and `offset_constant` (the spread of the host-minus-msprof difference across candidates).
Acceptance of the prohibition as stated: either `rank_agreement` materially below 1, or
`offset_constant` large relative to the candidate spacing — either shows host timing cannot resolve
the decisions this chain makes. If both come out favourable to host timing, the prohibition is about
precision only and the entry is corrected in place.

Exit code is not the verdict. Both instruments' raw per-iteration values are published, per rank,
including the warm-up iterations that the protocol discards — because the launch-overhead claim is
most visible there.

Red input: two candidates whose msprof times differ by less than the measured host-side spread. The
host instrument must fail to separate them; if it separates them consistently, it is more precise
than the prohibition assumes and that is the finding.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. No board, no rank count, no operator. It does not establish the magnitude of
launch overhead, nor msprof's own accuracy — `Task Duration` is treated as the reference by
convention, not by calibration. It says nothing about whether `Task Duration` and `aiv_time` are
interchangeable, and the two halves of this skill use different columns. Nothing here licenses host
timing for any purpose, including rough triage, since no measurement supports either position yet.
