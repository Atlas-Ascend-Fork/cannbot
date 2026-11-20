```
ID:        0050-a-vectorised-binary-search-replaces-the-scalar-tail-of-a-multi-level-histogram
LABEL:     procedure
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin, a document declaring itself A2-verified; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:22 — "低位级别元素匹配率低（<2%），向量化效率极差，退化为标量扫描"; ibid:24 — "在值域上做二分搜索。每步 1 次全量向量化扫描 + 1 次 Compare + 1 次 ReduceSum + 1 次全局同步"; ibid:38 — "**代价**：bit_width 次全量数据扫描（DMA 带宽）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  on a named Atlas A2 board, a multi-level histogram outperforms a vectorised binary search for a threshold-finding case whose MTE2 utilisation is low — i.e. the trade upstream describes does not favour the search where it says it should.
```

# 0050 · A vectorised binary search replaces the scalar tail of a multi-level histogram

## 1 · Claim
Upstream asserts that in a multi-level histogram used to locate a K-th largest threshold, the
low-order levels have element match rates below 2 %, which makes vectorisation ineffective and
degrades those levels into scalar scans. Upstream asserts an alternative: binary search over the
value range, each step costing one full vectorised scan, one Compare, one ReduceSum and one global
synchronisation. Upstream states the trade explicitly — the search's cost is `bit_width` full
passes over the data, so it suits cases with DMA bandwidth to spare (low MTE2 utilisation). Not
established here.

## 2 · The wrong branch this removes
The radix/histogram approach is the textbook answer for selection at scale and is correct. Its
failure here is structural rather than algorithmic: as levels narrow, the fraction of elements
matching each bucket falls, and a vector unit processing 256 B per repeat (0032) doing useful work
on 2 % of its lanes is a scalar loop with extra steps. The agent sees a Scalar-bound profile in an
operator it implemented with vector instructions, which is a confusing signal, and the natural
response — optimise the scalar code — treats the symptom.

The trade is what makes this a procedure entry rather than a recommendation. The binary search is
not universally better: it reads the whole dataset `bit_width` times, so on an already
MTE2-saturated case it is worse. Upstream states the selection criterion (spare DMA bandwidth) and
this entry keeps it in §1, because a technique carried without its precondition becomes a rule, and
a rule that fires in the wrong regime is worse than no rule.

The barrier count is the second half of the trade and points the opposite way: 16 search steps mean
16 global synchronisations at ~200 µs each (0041), against 4–6 for a histogram. Upstream's own
ladder (0049) has the search winning anyway, which means the scalar tail cost more than eleven
barriers — but that is one case, and the arithmetic is worth doing per case rather than assumed.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md` §1.1, lines 20-38.
The diagnosis, line 22: "**传统方案**：多级直方图（radix sort 思想），每级统计 bin counts，逐级
缩小范围。低位级别元素匹配率低（<2%），向量化效率极差，退化为标量扫描。"
The alternative, line 24 and the pseudocode at 27-33, verbatim:
```
lo = 值域下界, hi = 值域上界
for step = 0 to bit_width - 1:
    mid = (lo + hi) / 2
    globalCount = Σ CountGE(mid)    // 全核向量化
    if globalCount ≥ K: lo = mid
    else: hi = mid
threshold = lo
```
The benefit, line 36: "**收益**：消除低位标量扫描瓶颈（实测 -9.4ms，-46%）" — a measured figure
which §3 of 0049 shows does not reconcile with that document's own ladder (C-910-004), so it is
quoted here as a direction and not used as a magnitude.
The cost and the precondition, line 38: "**代价**：bit_width 次全量数据扫描（DMA 带宽）。适用于
DMA 带宽有余量（MTE2 占比偏低）的场景。"

The granularity trade table, lines 50-55, gives four bucketing schemes from 8+8 down to 16 × 1-bit,
with the selection rule at lines 58-60: "- 标量主导：增加二分步数，减少标量路径 - 向量主导：减少
每级 bins 数 - DMA 主导：减少扫描次数". Note the 16 × 1-bit row IS the binary search — upstream
presents the two as endpoints of one axis rather than as rival algorithms, which is the more useful
framing and is why this entry is `procedure`.

The generalisation, lines 41-44: Quantile (search for count = N × q), Median (K = N/2), KthValue,
histogram equalisation. And §7.2 (lines 331-339) extends the method to Sort/ArgSort, Unique,
NonZero, Histogram, ArgMax/Min, MaskedSelect.

Supporting techniques from the same document, each carried by its own entry: the order-preserving
transform done once (§1.3, whose inverse is not the forward path because of 0044's saturation), the
half-versus-float accumulator choice (0046), and the barrier-overlap prefetch (0041 §2).

## 4 · Procedure
Proposed, runnable later; not run. The claim is a selection rule with a stated precondition, so the
procedure must span the precondition rather than test one point.

1. Name the die; record the part; occupancy before and after; no substitution.
2. Implement both: a 4+4+4+4 multi-level histogram and a `bit_width`-step vectorised binary search,
   over the same declared case identity (N, K, dtype, core count) — stated before the run, as 0049
   §4 step 2 requires and upstream did not.
3. Sweep the regime, which is the point: vary arithmetic intensity so that MTE2 utilisation in the
   histogram arm spans low (< 30 %), medium and high (> 70 %). Upstream's rule predicts the search
   wins in the first regime and loses in the third; a sweep that only covers one regime cannot test
   a conditional claim.
4. Per arm and regime: total time, `aiv_vec_ratio`, `aic_mte2_ratio`/`aiv_mte2_time`,
   `ai*_scalar_ratio`, and the barrier count with measured barrier cost from 0041.
5. Report the crossover MTE2 utilisation, if one exists. That number — not the speed-up — is the
   deliverable, because it is what turns the rule into a gate.
6. Ten launches, first five discarded, mean of the last five, `msprof op --warm-up=10`.

## 5 · Checker — acceptance declared before the run
Verdict variable `crossover_mte2`: the MTE2 utilisation at which the two arms' times cross.
PASS (the conditional claim upheld) iff a crossover exists, with the search faster below it and
slower above.
The declared negatives, both meaningful: if the search wins in EVERY regime, upstream's stated
precondition is unnecessary and the entry is corrected to drop it — a strictly more useful rule. If
it loses in every regime, the technique does not transfer to this case and the entry is corrected
to say so, with the case identity that produced that result recorded.
A single-regime run yields NO verdict, because a conditional claim tested at one point is not
tested. This is declared before the run so that a convenient single point cannot be presented as
confirmation.
Scalar-ratio confirmation is the mechanism check: the histogram arm must show a rising
`ai*_scalar_ratio` in its low-order levels. If it does not, the diagnosis in §1 does not apply to
this implementation and the comparison, whatever it shows, is not about what the entry claims.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "A2" is a product line, not a board (0041 §7). The −9.4 ms
/ −46 % figure is quoted as a direction only: it carries no case identity and does not reconcile
with the same document's ladder (C-910-004). This entry does not establish the crossover point —
§4 step 5 exists to find it and no source in scope states one. It does not establish the < 2 % match
rate, which is upstream's characterisation of its own case and depends entirely on the data
distribution. It does not establish that the method transfers to the operators listed in §3's
generalisation; upstream asserts the extension and measures only TopK. It says nothing about A3 or
A5 (0047).
