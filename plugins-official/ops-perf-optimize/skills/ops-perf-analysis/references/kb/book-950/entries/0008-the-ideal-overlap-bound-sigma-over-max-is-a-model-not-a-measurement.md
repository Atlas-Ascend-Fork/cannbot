```
ID:        0008-the-ideal-overlap-bound-sigma-over-max-is-a-model-not-a-measurement
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/metrics.md:43 — "理想上界 = Σ / max(各 ratio)  # 全并行时墙钟收敛到最长那条泳道"
           ops/ascendc-perf-optimize/references/single-core-pipeline/metrics.md:57 — "全并行本应收敛到最长的 29.52us"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  one kernel on a named 950 board, with a true serial data dependency between two
           lanes, whose attainment cannot be driven above a value strictly below 100% by any
           reordering — the bound is then unreachable by construction and is not an "ideal", or
           the converse: a kernel that exceeds Σ/max, which would falsify it as an upper bound.
```

# 0008 · The ideal overlap bound Σ/max is a model, not a measurement

## 1 · Claim
Upstream asserts that the ideal upper bound on the overlap factor is Σ(ratios) / max(ratio),
on the reasoning that under full parallelism the wall clock converges to the longest lane; and
that attainment = overlap factor / this bound. The lane times entering the formula are measured.
The step from "the longest lane is 29.52 us" to "full parallelism should converge to 29.52 us"
is a modelling assumption — it presumes every other lane's work can be hidden behind the longest
one, which a true data dependency forbids. Not established here that the bound is attainable
for any operator, and nothing was measured.

## 2 · The wrong branch this removes
The formula is presented as arithmetic inside a fenced block, next to a quantity that really is
arithmetic (0007). An agent that treats both lines alike will report "attainment 51%, therefore
half the machine time is being wasted and reordering should roughly double throughput". For the
one operator upstream measured, reordering did deliver a large part of that (factor 1.63 → 2.58,
`aiv_time` −32.9%, entry 0052) — which is exactly why the trap is dangerous: the model is
useful and it will be believed the next time, for an operator whose lanes are serially
dependent, where the headroom implied by Σ/max does not exist. The agent then spends its budget
reordering a pipeline that cannot overlap, and reports the shortfall as an unexplained gap.

The narrow discipline this entry encodes: a sentence may not contain a measurement and an
inference joined by "so" or "therefore". `metrics.md:57` contains both — 四条泳道忙了 93.97us
却只压缩到 57.52us (measurement) 全并行本应收敛到最长的 29.52us (model) — and both halves are
true statements of different kinds.

## 3 · Ground / Source
`metrics.md:43` states the bound inside the same fenced block as the measured factor:

> 理想上界 = Σ / max(各 ratio)                               # 全并行时墙钟收敛到最长那条泳道
> 达成率   = 重叠因子 / 理想上界

`metrics.md:57` applies it: 上界 `1.634/0.513 = 3.186`、**达成率 51%**. Re-derived here:
1.634/0.513 = 3.1852; upstream prints 3.186, which is 1.635/0.513 — the difference is which
rounding of Σ(ratios) is used, and is not material. The attainment 1.634/3.186 = 0.5128.

`metrics.md:59` immediately qualifies the quantity in a way that supports this entry's split:

> 达成率没有硬阈值，但**接近 100% 说明已经排满、再调顺序无收益**；50% 量级说明一半时间在互相
> 等，值得下钻。

so upstream itself treats attainment as a direction indicator rather than a target. `no-bound.md:10`
nevertheless promotes it to 本页主判据. The identical measurement-plus-model fusion occurs at
`vec.md:21` (>80% VEC → 微架构调优收益有限, an inference from a ratio) and at `vec-11:9`.

## 4 · Procedure
Later phase, needs a card. Board named from the driver readout.
1. Device selection per 0010; record occupancy before and after; refuse to proceed on an
   unnamed device.
2. Construct two kernels with identical lane budgets — same four lane times to within 5% — but
   opposite dependency structure: (K_indep) four stages with no cross-stage data dependency,
   arranged so any order is legal; (K_dep) the same four stages chained so each consumes the
   previous stage's output element-wise.
3. For each, measure the overlap factor and attainment as built, then apply every reordering
   available (0052's two moves; queue depths; DB on/off) and record the maximum attainment
   reached, five repetitions each, reporting median and spread.
4. Report `max_attainment(K_indep)` and `max_attainment(K_dep)` with their spreads.

## 5 · Checker — acceptance declared before the run
Verdict variable `bound_attainable`, declared before the runs:
`bound_attainable = (max_attainment(K_indep) >= 0.95)`. The bound is a usable ideal only if the
independent kernel can approach it. Second verdict `bound_misleading` =
`(max_attainment(K_dep) <= 0.75)` — if the dependent kernel is capped well below the bound, then
attainment on an arbitrary operator does not measure lost opportunity, and the replacement skill
must say so wherever it reports attainment.

Exit code is not the verdict. Both numbers are reported with their spreads, and a kernel pair
whose lane budgets failed to match within 5% is reported as `pair_invalid` rather than being
compared anyway.

Red input: K_dep. If a checker of this claim reported only "attainment was computed", it would
pass on both kernels and learn nothing; this one is built around the case that must behave
differently, and it names in advance which case that is.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board; no kernel pair built. It does not establish that Σ/max is wrong —
it is a correct upper bound on the *factor* if lanes may overlap freely, and the entry's point
is only that free overlap is an assumption about the kernel, not a property read from the CSV.
It does not give the corrected bound for a dependent kernel; deriving one (a critical-path
bound rather than a max-lane bound) is new work and belongs in a later phase. It says nothing
about AIC lanes, about multi-core effects — every number here is a 56-core mean — or about
whether attainment behaves the same way at other shapes.
