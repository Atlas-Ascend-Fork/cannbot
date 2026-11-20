```
ID:        0007-the-overlap-factor-is-the-lane-time-sum-divided-by-aiv-time
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/metrics.md:41-42 — "重叠因子 = Σ(aiv_vec_time + aiv_scalar_time + aiv_mte2_time + aiv_mte3_time) / aiv_time = Σ(各 ratio)  # 两式等价，ratio 本就是 time/aiv_time"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a PipeUtilization.csv from a named 950 board in which Σ(各 ratio) and
           Σ(各泳道耗时)/aiv_time differ by more than float rounding — the two forms are
           asserted equivalent, and their equivalence is an assumption about how msprof defines
           the ratio columns, not a theorem.
```

# 0007 · The overlap factor is the lane-time sum divided by aiv_time

## 1 · Claim
Upstream asserts that the overlap factor of a kernel is Σ(aiv_vec_time + aiv_scalar_time +
aiv_mte2_time + aiv_mte3_time) / aiv_time, that this equals the sum of the four msprof ratio
columns because each ratio is already that lane's time over `aiv_time`, and that it can be
computed on a board from `PipeUtilization.csv` alone with no simulation. Not established here.
The arithmetic in upstream's worked example was re-derived from its own published numbers and
is self-consistent; that is a check of their table, not a measurement by us.

## 2 · The wrong branch this removes
Without this, an agent facing a kernel with no dominant lane has no instrument at all. It will
either declare "no bottleneck found, performance is as good as it gets" and stop, or it will
pick the largest ratio and optimise a lane that is not the constraint. The overlap factor is
cheap — one CSV, four columns, no simulator, no rebuild — and it converts "nothing looks wrong"
into a number that can be small. It is the entry point to the whole no-bound branch: 0052's
32.9% gain is on an operator whose every lane sat near 0.5.

The second wrong branch this removes is arithmetic. An agent that computes the factor from lane
*times* on one board and compares it to a factor computed from *ratios* on another has assumed
the two definitions coincide; upstream asserts they do, but that assertion is about msprof's
column semantics and is the first thing to check on a new toolkit.

## 3 · Ground / Source
`metrics.md:36-45`, in full:

> ### 2.1 重叠因子：判"流水并行够不够"的入口指标
> 只用 `PipeUtilization.csv` 一张表即可，**上板随时能算，不需要仿真**：
> ```
> 重叠因子 = Σ(aiv_vec_time + aiv_scalar_time + aiv_mte2_time + aiv_mte3_time) / aiv_time
>          = Σ(各 ratio)                                    # 两式等价，ratio 本就是 time/aiv_time
> 理想上界 = Σ / max(各 ratio)                               # 全并行时墙钟收敛到最长那条泳道
> 达成率   = 重叠因子 / 理想上界
> ```

The second and third lines are a different kind of statement and are split out into entry 0008 —
the factor is measured, the ideal bound is modelled. The metric row at `metrics.md:34` names the
source table: 重叠因子 = 各泳道忙碌时长之和 / 实际耗时, read from `PipeUtilization.csv`.

Worked example, `:47-57`: four lanes 29.52 / 27.73 / 27.57 / 9.15 us, Σ = 93.97 us, `aiv_time`
57.52 us, factor 1.634. Re-derived here from the quoted numbers: 93.97 / 57.52 = 1.6337, and
0.513+0.483+0.480+0.159 = 1.635 — the two forms agree to the published precision, which is
consistent with upstream's equivalence claim on this one dataset. `no-bound.md:10` names the
factor as its own primary predicate (本页主判据). `nobound-02:17` uses "1.6 量级、达成率约 50%"
as a trigger condition, and `:73` reports the factor moving 1.63 → 1.90 → 2.58 across two
changes.

## 4 · Procedure
Later phase, needs a card; the arithmetic arm needs only a CSV that already exists.
1. Device selection per 0010; board token from the driver readout, not from this file.
2. Capture one kernel with msprof, `--aic-metrics=PipeUtilization`, producing
   `PipeUtilization.csv` and `kernel_details.csv` for the same launch.
3. Compute the factor twice, independently: (a) from the four `*_time` columns divided by
   `aiv_time`; (b) from the four `*_ratio` columns summed. Do not reuse intermediate values
   between the two computations, and take `aiv_time` for (a) from `kernel_details.csv` rather
   than from the ratio table, so the two paths share no input but the launch.
4. Repeat over at least ten kernels spanning factors from ~1 (fully serial) to ~3.

## 5 · Checker — acceptance declared before the run
Verdict variable `factor_defs_agree`: for every kernel, `|a - b| <= 0.01 + 4*eps_col`, where
`eps_col` is the printing precision of the ratio columns as observed in the CSV header, not a
number chosen after seeing the disagreement. A single kernel outside the band fails the whole
check and is reported with both values.

Exit code is not the verdict; a CSV parse that finds no rows exits 0. The checker asserts
`rows_parsed >= 1` per kernel and reports `no_data` otherwise — the failure species this guards
against is a reader that scans for the four expected column names, finds none, sums nothing,
and reports 0.0 as agreement.

Red input: a kernel profiled with a metrics mode that does not populate `PipeUtilization.csv`.
The columns are absent, `rows_parsed` is 0, and the checker must say `no_data`, not `pass`.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured by us; the re-derivation above is arithmetic over upstream's own printed
numbers and establishes only their internal consistency. The factor counts four AIV lanes; it
says nothing about AIC/Cube occupancy, and an operator whose Cube lane dominates is invisible
to it. It does not establish what value of the factor is "good" — that is the attainment
question of 0008 and 0009, and upstream explicitly declines to give a hard threshold. It does
not establish that `PipeUtilization.csv` carries these columns on any particular CANN version;
the column set is a property of the toolkit, and this book has bound no toolkit yet.
