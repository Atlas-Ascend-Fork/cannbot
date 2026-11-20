```
ID:        0049-the-a2-radix-topk-ladder-includes-a-version-that-came-out-slower
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   harvested — an upstream measured ladder reported with its regression intact; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:319-327 — the five-version RadixTopk table, "版本二 | 20.5ms", "版本三 | 20.8ms", "总提升：23.4ms → 13.2ms（**-44%**，1.79x vs torch.topk）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  the ladder is shown to be unreproducible on a named Atlas A2 board — in particular if version three is not slower than version two, which would mean the disclosed regression was a measurement artefact.
```

# 0049 · The A2 RadixTopk ladder includes a version that came out slower

## 1 · Claim
Upstream asserts a five-version optimisation ladder for a RadixTopk kernel on A2: 23.4 ms baseline
(4+4+4+4 histogram), 20.5 ms (3+3+5+5 bucketing), **20.8 ms** (cumulative GE plus a precision fix),
15.0 ms (16-step vectorised binary search plus one-shot transform), 13.2 ms (TQue double buffer) —
a total of −44 % and 1.79× against `torch.topk`. Version three is slower than version two and is
reported anyway. Upstream states no shape, dtype, K, core count, tool or repeat count. Not
established here.

## 2 · The wrong branch this removes
Two, and they pull in opposite directions.

The first is using the numbers. They cannot be used: a TopK time with no N, no K, no dtype and no
core count is not comparable to anything, and 1.79× against `torch.topk` is a comparison against an
unstated baseline on unstated hardware. An agent that adopts "TQue double buffering buys 12 %" from
row five has taken a number out of a case whose identity is missing.

The second is discarding them. What the ladder *does* establish is the ordering of technique
classes on this part — algorithmic restructuring (23.4 → 15.0) dominates pipeline work
(15.0 → 13.2) by a wide margin, and instruction-level tuning (version three) bought nothing at all.
That ranking is robust to the missing conditions in a way the percentages are not, and it is
directly actionable: it says where to spend effort first.

The third thing, and the reason this is an entry rather than a note: **version three is a
disclosed regression**. 20.8 ms follows 20.5 ms. Upstream could have dropped the row, merged it
into version four, or reported the pair as a net gain. It kept the unflattering number in a
published ladder, which is the behaviour this book's form exists to encourage, and the entry is
here partly to put an example of it in front of a consuming agent.

Note that version three combined an instruction-level optimisation with a *precision fix* — the
cross-half correction of 0044. So the 0.3 ms is plausibly the cost of correctness, not a failed
optimisation. Upstream does not say, and this entry does not resolve it; the honest reading is that
a row got slower and the reason is not recorded.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md` §7.1 实战案例, lines 319-327,
verbatim in full:
```
| 版本 | Kernel | 核心优化 | 优化类型 |
|------|--------|---------|---------|
| 版本一 | 23.4ms | 4+4+4+4 直方图 | baseline |
| 版本二 | 20.5ms | 3+3+5+5 分桶 | 算法重构 (§1.2) |
| 版本三 | 20.8ms | 累积 GE + 精度修复 | 指令级 (§3.1) + 精度 (§4) |
| 版本四 | 15.0ms | 16 步向量化二分搜索 + 一次性 VtS | 算法重构 (§1.1, §1.3) |
| 版本五 | 13.2ms | TQue Double Buffer | 流水线并行 (§2.1) |
```
"**总提升**：23.4ms → 13.2ms（**-44%**，1.79x vs torch.topk）"

Arithmetic checked here: 13.2 / 23.4 = 0.564, so −43.6 %, consistent with the stated −44 % ✓.
The step-by-step deltas are −12.4 %, +1.5 %, −27.7 %, −12.0 %.

A second measured figure in the same document, line 36: "**收益**：消除低位标量扫描瓶颈（实测
-9.4ms，-46%）" for the vectorised binary search alone. Cross-check performed here: −9.4 ms from
20.5 would give 11.1 ms, and −9.4 from 20.8 gives 11.4 — neither matches the ladder's 15.0 ms at
version four. And −46 % of 20.5 is −9.4 ms ✓ arithmetically, so the percentage and the absolute
agree with each other but not with the ladder. **The two measured claims in this document are
mutually inconsistent**, unless they come from different cases — which is exactly what the missing
case identity prevents anyone from checking. Filed as `harvest/contradictions-910.md` **C-910-004**.

That inconsistency does not diminish the disclosure point in §2; it sharpens it. A document
disciplined enough to publish a regression is still one whose numbers cannot be reconciled without
case identity, which is the strongest available argument that case identity is not optional.

The document's A2 scope is at line 5 (0047).

## 4 · Procedure
Proposed, runnable later; not run. Reproducing an unidentified case is impossible, so the procedure
tests the *ordering*, which is what §2 says is usable.

1. Name the die; record the part; occupancy before and after; no substitution.
2. Fix a case identity that upstream did not: N = 2²⁸ fp16 elements, K = 100, on all available AIV
   cores, `msprof op` with `--warm-up=10`, ten launches, first five discarded, mean of the last
   five — the capture protocol stated before the run, not chosen after.
3. Implement the five versions as described in the ladder's 核心优化 column and time each on that
   one case.
4. Report all five, including any that come out slower than their predecessor, and including the
   ordering of the four deltas. Report against `torch.topk` on the same case only if a comparable
   PyTorch path exists on the same part; otherwise omit the comparison rather than substituting a
   different baseline.
5. Report the absolute times, which upstream's figures cannot be compared against, and say so.

## 5 · Checker — acceptance declared before the run
Verdict: the ordered vector of four deltas.
PASS (the usable claim upheld) iff the two algorithmic-restructuring deltas together exceed the
pipeline delta in magnitude — that is, the technique-class ranking of §2 reproduces.
The percentages are NOT part of the verdict, and stating that before the run is the point: a run
that reproduces the ranking but lands at −30 % instead of −44 % confirms this entry, because this
entry claims the ranking and explicitly disclaims the magnitudes.
A version three that comes out *faster* than version two is reported as such and would mean either
the regression was case-specific or the precision fix is free on this case — recorded as a finding
about the ladder, not scored as a failure of the run.
The declared negative: if the ranking inverts (pipeline work dominating restructuring), §2's usable
claim is overturned and this entry is corrected in place.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "A2" is a product line, not a board (0041 §7). **None of
the quoted times is usable as a number**: no shape, K, dtype, core count, tool, repeat count or
board is given, and the document's two measured claims do not reconcile with each other (§3,
C-910-004). This entry does not establish that any single technique buys any particular fraction.
It does not establish the `torch.topk` comparison, whose baseline hardware and version are unstated.
It does not establish why version three regressed. It says nothing about A3 or A5 (0047).
