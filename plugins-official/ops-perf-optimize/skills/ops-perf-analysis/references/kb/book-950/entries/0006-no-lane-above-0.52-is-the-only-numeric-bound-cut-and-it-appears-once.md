```
ID:        0006-no-lane-above-0.52-is-the-only-numeric-bound-cut-and-it-appears-once
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/metrics.md:57 — "**没有单一泳道超过 0.52**，所以不是任何一种 bound，是编排问题 → 走 `no-bound.md`"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a case set on a named 950 board in which cases with a maximum lane ratio just above
           0.52 respond to the bound-specific strategy of that lane, and cases just below it do
           not respond to reordering — i.e. the cut separates nothing. Equally fatal in the
           other direction: a cut that reproduces the labels only after being refitted per
           operator family, which would make 0.52 an artefact of one fused operator.
```

# 0006 · "No lane above 0.52" is the only numeric bound cut, and it appears once

## 1 · Claim
Upstream asserts that in its worked example no single lane ratio exceeds 0.52, and that this is
the reason the operator is classified as no-bound rather than as any single bound. Not
established here. A grep over the whole skill finds the value 0.52 exactly once, in that one
sentence, inside one worked example over one fused operator; upstream never states it as a
threshold, never gives it a scope, and never repeats it in the routing tree that consumes it.

## 2 · The wrong branch this removes
Two opposite wrong branches, and this entry exists to keep both visible. The first: an agent
that never finds this number routes the example by lane ranking and lands on memory bound (see
0005) — the cut is load-bearing and buried. The second: an agent that finds it promotes it to a
hardware constant and writes `if max_ratio <= 0.52: no_bound` into a replacement skill, giving
a one-operator observation the authority of an architectural limit. The skill itself warns
against exactly this promotion two lines below, at `metrics.md:63`, where all such ratio cuts
are called 经验判定线 whose neighbourhood must be decided by measured `aiv_time`. The value is
worth carrying; it is not worth believing.

## 3 · Ground / Source
`metrics.md:47-57`. The measured table (A5, mean over 56 cores, an RMSNorm+RoPE+KVCache fused
operator before optimisation):

> | 泳道 | 耗时 | ratio |
> | MTE2 | 29.52 us | 0.513 |
> | VEC | 27.73 us | 0.483 |
> | SCALAR | 27.57 us | 0.480 |
> | MTE3 | 9.15 us | 0.159 |
> | 合计 | **93.97 us** | **1.634** |

and the verdict sentence at `:57`:

> `aiv_time = 57.52 us`（Task Duration 60.08 us）。重叠因子 1.634、上界 `1.634/0.513 = 3.186`、
> **达成率 51%**——四条泳道忙了 93.97us 却只压缩到 57.52us，全并行本应收敛到最长的 29.52us。
> **没有单一泳道超过 0.52**，所以不是任何一种 bound，是编排问题 → 走 `no-bound.md`。

The table is internally consistent and was re-derived here from the published numbers alone:
Σ = 29.52+27.73+27.57+9.15 = 93.97 us; 93.97/57.52 = 1.634; each ratio equals its lane time
over 57.52 (29.52/57.52 = 0.5132, 9.15/57.52 = 0.1591). So the ratios and the overlap factor
are one measurement re-expressed, not two. The 0.52 cut is not derived from anything in the
table: it sits 0.007 above the largest observed ratio, and no sentence explains its origin.

Occurrence count, mechanically: one, `metrics.md:57`, over all of `SKILL.md`,
`references/single-core-pipeline/**`, `references/comm-compute/**`,
`references/inter-core-pipeline/**` and `evals/`. The neighbouring cuts (`aiv_vec_ratio` >80%,
Cast >20%, transcendental >30%, `aiv_mte3_wait_ratio` >0.4) are stated in the same voice and
carry the same warning at `metrics.md:63`.

## 4 · Procedure
Later phase, needs a card. Board: named from the driver readout (950PR or 950DT), never assumed.
This procedure is a threshold calibration, and it is designed so that the number can lose.

1. Device selection as in 0005; refuse to run with an unset visible-devices variable; record the
   SoC readout and the die occupancy before and after.
2. Take the labelled case set of 0005 and, for each case, record `max_lane_ratio` and the
   overlap-factor attainment (0007).
3. For each case, apply BOTH treatments, in randomised order, rebuilt from the same source
   tree: (T1) the strategy of its highest lane's diagnosis page — for MTE2, one `mem-*` card;
   for VEC, one `vec-*` card; (T2) the no-bound reordering of 0052. Record `aiv_time` before and
   after each treatment, five repetitions, and report the median and the spread.
4. Fit nothing. Plot response to T1 minus response to T2 against `max_lane_ratio`, and read off
   where the sign changes — if it changes at all.

## 5 · Checker — acceptance declared before the run
Verdict variable `cut_separates`, declared now. Let `d(c) = gain_T1(c) - gain_T2(c)` in percent
of baseline `aiv_time`. The cut at 0.52 is accepted as a decision line iff, over the case set,
`d(c) > 0` for every case with `max_lane_ratio > 0.52` and `d(c) < 0` for every case with
`max_lane_ratio <= 0.52`, with each `d(c)` larger in magnitude than the measured run-to-run
spread of that case. Any case that straddles is reported by name.

The exit code is not the verdict. The verdict is `cut_separates` plus the full table of
`(case, max_lane_ratio, d, spread)` — including the cases where the two treatments tie, which
are retained and reported as ties rather than dropped for being uninformative.

Red input, stated now: the metrics.md example itself, whose `max_lane_ratio` is 0.513. If the
reordering treatment wins there — as upstream's own before/after in 0052 suggests it does — the
case supports the cut. If the memory treatment wins there, the cut is refuted by the very case
that produced it, and this entry is restratified overturned with that readout in §6. A checker
that only asked "did some treatment help?" could not tell these apart; this one compares two
treatments on the same case, so it can return the unflattering answer.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
The number is not established as anything — not as a hardware property, not as a threshold, not
even as upstream's considered opinion, since upstream states it inside a worked example and
never lifts it into the routing tree. No board was touched. The observation behind it is one
operator (RMSNorm+RoPE+KVCache fused), one shape family, one 56-core configuration, one
pre-optimisation state. Nothing here says what the cut should be for AIC lanes, for Cube-bearing
operators, or for MC² operators, whose MTE2 ratio may be polluted by communication wait (0060)
and whose lane ratios therefore are not comparable to these. A calibration on 950PR would say
nothing about 950DT.
