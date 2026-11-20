```
ID:        0054-a-reported-gain-names-its-cache-state-because-an-l2-dirty-run-dilutes-it
LABEL:     procedure
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     950PR
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-02-stage-order-rescheduling.md:86 — "**报收益要说清口径**：L2 被冲脏时（真实部署里调用间夹着别的算子）搬运绝对量成为主导，编排收益被稀释到 -2.5%"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-02-stage-order-rescheduling.md:69-71 — "| msprof Task Duration | 58.99 us | 52.86 us | **39.61 us** | **-32.9%** | | back-to-back | 54.46 us | 46.51 us | 33.99 us | -37.6% | | L2 冲脏后 p50 | 91.85 us | 89.99 us | 89.57 us | -2.5% |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured case on a named 950 board where the three timing conventions rank two
           candidate builds in the same order with the same magnitude — the convention would then
           not be a material property of a reported gain, at least for that operator class.
```

# 0054 · A reported gain names its cache state, because an L2-dirty run dilutes it

## 1 · Claim
Upstream asserts that a performance gain must be reported together with the measurement convention
it was obtained under, and demonstrates why on one operator: the same pair of changes is −32.9% by
msprof Task Duration, −37.6% back-to-back, and −2.5% when L2 has been dirtied between calls — the
last being the deployment-realistic case, where the absolute transfer volume dominates and the
scheduling gain is diluted. Not established here; the three readouts are upstream's, for one fused
operator on Ascend950PR at T=10752.

## 2 · The wrong branch this removes
Every technique in this library is accepted on a before/after `aiv_time` comparison (0009), and
nothing in the metrics page says which cache state that comparison is taken in. The default is a
warm repeat loop, because that is what a benchmark harness does: launch the same kernel many times,
discard the first, average the rest. That convention systematically favours changes that improve
pipeline ordering and systematically hides changes to transfer volume — and in production the same
operator runs with other operators between its calls, so the warm number is the one that will not
be reproduced.

The wrong branch is therefore not "measuring badly" but "reporting a real number as if it were the
only one". A single figure carries a hidden regime, and the next reader will compare it against a
figure taken under a different regime. This entry's content is that the convention is part of the
result, and that a 13× disagreement between conventions on one operator is not exotic.

## 3 · Ground / Source
`nobound-02:63-75`. Three conventions are reported side by side for the same three builds, quoted in
SOURCE. The mechanism-side readouts in the same block explain the dilution: `aiv_mte2_ratio` moves
0.497 → 0.814 across the change, with the comment 搬运接近饱和，瓶颈已从编排转为搬运量本身 — once
the ordering is fixed the operator is transfer-bound, so any state that raises transfer cost (a
dirty L2) leaves little for ordering to win.

`nobound-02:86` states the rule, quoted in SOURCE. Note its parenthesis — 真实部署里调用间夹着别的
算子 — which is the justification: the dirty-L2 convention is not a stress test but an approximation
of deployment.

Consistent elsewhere: `metrics.md:18` makes on-board msprof `aiv_time` before/after the final
verdict without naming a cache convention; `metrics.md:63` says thresholds are experience lines and
`aiv_time` decides; `mem-05:34` requires the L2-bypass experiment to cover both a full one-shot read
and a multi-tile/wave split, which is the same concern in another form — the cache state is part of
the case. The MC² side has its own convention and states it precisely (0057): at least ten
iterations, first five discarded as warm-up, mean of the last five, maximum across ranks — i.e. a
deliberately warm measurement, with no dirty-cache variant offered.

## 4 · Procedure
Later phase, needs a card. This is a procedure entry: what it defines is how a gain is to be
reported, and the procedure tests whether the three conventions can disagree enough to matter.
1. Device selection per 0010: explicit visible-devices, occupancy before and after, board token from
   the driver readout.
2. Take three candidate changes from this book with different mechanisms: an ordering change (0052),
   a transfer-volume change (0020 or 0043), and a compute-volume change (0035). Build each with its
   baseline from one source tree; record `md5sum` per build.
3. Measure every build under all three conventions, five repetitions each:
   - **Task Duration**: msprof, single launch per case, per 0010's per-case rule;
   - **back-to-back**: the same kernel launched repeatedly with no intervening work, first launches
     discarded;
   - **L2-dirty p50**: between launches, run an unrelated kernel that streams a working set larger
     than L2, and report the median of the resulting distribution rather than the mean.
4. Report a 3×3 table of relative gains, plus the spread of each cell.

## 5 · Checker — acceptance declared before the run
Verdict variable `convention_matters` = true iff, for at least one change, the gain under two
conventions differs by more than the pooled spread; and `rank_stable` = true iff the three changes
rank identically under all three conventions. The reporting rule this entry proposes is justified
when `convention_matters` is true, and is *strongly* justified when `rank_stable` is false, since
then the choice of convention changes which change one would ship.

Exit code is not the verdict. All nine cells are published with spreads, including the cells where
the conventions agree — retained because they did not bite. Any gain quoted without its convention
is a form error, and the checker's output format makes the convention a required field.

Red input: the compute-volume change measured under the dirty-L2 convention. A reduction in
arithmetic should survive cache pollution roughly intact; if it too collapses to a few percent, the
dirty-L2 harness is dominated by its own polluting kernel and the whole table is invalid — reported
as `harness_dominates`, not as a finding about the changes.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured by us. The three numbers are one operator, one shape, one board token (950PR), one
pair of changes; the 13× disagreement between conventions is not established as typical. It does not
establish that the dirty-L2 convention is the right one — it is one approximation of deployment, and
which convention should govern a decision depends on the deployment, which this book knows nothing
about. It does not define how dirty is dirty: upstream reports a p50 without stating what dirtied
the cache. No board other than the one named is implicated, and nothing here transfers to the 910
book.
