```
ID:        0009-no-metric-has-an-absolute-pass-line-the-verdict-is-before-versus-after-aiv-time
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/metrics.md:63 — "**没有"绝对达标 IPC/util"**。判定永远是**优化前 vs 优化后同一指标对比**：`aiv_time` 降即正收益。指标占比阈值（如 Cast >20%、`aiv_vec_ratio` >80%）是经验判定线，阈值附近仍以 `aiv_time` 实测为准"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a case set on a named 950 board in which a published cut's side predicts the sign of
           the `aiv_time` change under its prescribed treatment for at least 90% of cases pooled
           and at least 80% within every operator family, counting only cases whose |Δ| exceeds
           that case's measured run-to-run spread — the cut would then be a usable pass line, and
           this entry's counsel over-cautious.
```

# 0009 · No metric has an absolute pass line; the verdict is before-versus-after aiv_time

## 1 · Claim
Upstream asserts that there is no absolute target for IPC or unit utilisation on this
architecture; that the verdict is always the same metric compared before and after a change on
the same case, with a fall in `aiv_time` being the definition of a gain; and that every ratio
threshold it publishes — Cast >20%, `aiv_vec_ratio` >80%, and by the same sentence the rest —
is an experience line whose neighbourhood must still be settled by measured `aiv_time`. Not
established here; nothing was measured.

## 2 · The wrong branch this removes
An agent handed a table of thresholds will use them as acceptance criteria, because that is what
tables of numbers look like. It reports "aiv_vec_ratio 0.78, below the 0.80 deep-bound line,
therefore this kernel is healthy" — a verdict about the machine derived from a line drawn from
experience on other kernels. Worse, the same agent will accept a change that pushed a ratio
across a line while `aiv_time` rose, because the ratio is the thing it was told to watch.
Ratios are shares of a total that the change itself moves: a change that removes vector work
raises `aiv_mte2_ratio` without moving a byte. This entry is the reason every threshold in this
book carries the words "experience line" and every technique entry's §5 names `aiv_time` as the
verdict variable rather than a ratio.

## 3 · Ground / Source
`metrics.md:63`, standing alone between two horizontal rules — the position matters, since it
governs the ladders quoted on either side:

> **没有"绝对达标 IPC/util"**。判定永远是**优化前 vs 优化后同一指标对比**：`aiv_time` 降即正
> 收益。指标占比阈值（如 Cast >20%、`aiv_vec_ratio` >80%）是经验判定线，阈值附近仍以
> `aiv_time` 实测为准。

Consistent elsewhere in the same skill: `metrics.md:32` says of IPC 无绝对达标线，只做前后对比;
`metrics.md:26` designates `aiv_time` as 优化前后比这个; `metrics.md:59` says attainment
达成率没有硬阈值; every technique card's 性能数据 section names msprof `aiv_time` before/after as
the instrument (e.g. vec-01:34, vec-08:38, mem-02:48). The MC² side is stricter still and
insists on `Task Duration` from `op_summary_*.csv` (0057).

The tension to keep visible: the same document publishes seven numeric lines — VEC 50-65/65-80/
>80 (vec.md:17-21), Cast >20% and transcendental >30% (vec.md:58-59), `aiv_vec_ratio` >90%
(vec.md:87, vec-11:8), `aiv_mte3_wait_ratio` >0.4 (metrics.md:33), the 0.52 lane cut
(metrics.md:57) — and then declares all of them non-binding. Both halves are upstream's; the
lines are routing hints, and `aiv_time` is the verdict.

## 4 · Procedure
Later phase, needs a card. This is a claim about instruments, so the procedure tests whether a
threshold ever outperforms the paired comparison.
1. Device selection per 0010, board token from the driver, occupancy recorded before and after.
2. Use the labelled case set of 0005 (≥24 kernels, four bound shapes).
3. For each case, apply one fixed treatment appropriate to its shape and record: all four
   ratios and `aiv_time`, before and after; five repetitions of each build; median and spread.
4. Two predictors of the sign of Δ`aiv_time`: (P_abs) the pre-change value of the relevant
   ratio against its published line; (P_pair) the sign of Δ`aiv_time` itself, which is
   tautologically correct and serves as the reference for how much the ratio predictor loses.
   The informative output is P_abs's error rate, per family and pooled.

## 5 · Checker — acceptance declared before the run
Verdict variable `abs_line_predicts`: the fraction of cases in which the published line's side
correctly predicts the sign of Δ`aiv_time`, with a case counted only when |Δ`aiv_time`| exceeds
that case's measured run-to-run spread. Declared acceptance for treating any line as a pass
criterion: `abs_line_predicts >= 0.9` pooled AND no family below 0.8. Anything less and the
line stays a routing hint, as upstream says.

Exit code is not the verdict; the sweep exits 0 whatever it finds. Cases whose |Δ| falls inside
the spread are reported as `indeterminate` and counted in a separate column — they are not
silently dropped, because dropping them is how a threshold gets a flattering score.

Red input: a case treated with a change that moves a ratio the "right" way while `aiv_time`
rises — e.g. removing a Cast by widening the dtype, which lowers Cast share and raises total
work. Such a case must reduce `abs_line_predicts`, and one is included deliberately.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. This entry does not establish that the published lines are useless — they may
be excellent routing hints, and this book carries them as such (0015, 0016, 0011). It does not
establish that `aiv_time` is the right verdict variable for every question: it is an AIV-side
duration, it says nothing about AIC time, about end-to-end launch cost, or about the multi-rank
worst case that governs MC² operators (0057). It says nothing about how many repetitions are
enough — the spread that gates the comparison must itself be measured per case, and no such
measurement exists in this book.
