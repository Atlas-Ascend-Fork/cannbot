```
ID:        0046-half-reducesum-is-exact-only-to-2048-which-caps-the-subchunk
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin, a document declaring itself A2-verified; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:239-241 — "half 尾数 10 bits → 精确整数范围 [0, 2048]。**规则**：`HIST_SUBCHUNK ≤ 2048`，保证每次 ReduceSum 结果 ≤ 2048"; ibid:243 — "float32 ReduceSum 精确到 2^24（16M），但 UB 占用翻倍"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a half `ReduceSum` on a named Atlas A2 board returns an exact integer result above 2048 — or returns an inexact result below it, which would move the boundary the other way.
```

# 0046 · Half ReduceSum is exact only to 2048, which caps the subchunk

## 1 · Claim
Upstream asserts that `half`'s 10-bit mantissa makes integers exactly representable only over
[0, 2048], and therefore imposes a design rule: the histogram subchunk must be at most 2048
elements, so that any single `ReduceSum` result stays inside the exact range. Upstream asserts
`float32` is exact to 2²⁴ but doubles UB consumption. Not established here.

## 2 · The wrong branch this removes
This is a precision limit that presents as a *tiling* parameter, which is why it is a trap. An
agent sizing a subchunk optimises for UB occupancy, DMA transfer size (0025 wants ≥ 4096 B), and
instruction count — every one of those pushes the subchunk *up*. Nothing in that optimisation
contains a term for mantissa width, and the constraint that caps it lives in a different discipline
entirely.

The failure is quiet and directional. Above 2048, a half accumulator's increments start rounding to
even: adding 1.0 to 2049.0 yields 2048.0 or 2050.0, so a count *stops advancing correctly* rather
than jumping. The result is a count that is slightly low, in a histogram that is slightly wrong, in
a threshold that is slightly off — output that is plausible everywhere and correct nowhere. A test
with a small dataset never reaches 2048 and passes.

The escape upstream offers is not free: float32 doubles the UB, which on a 192 KB budget (0003) may
cost the double buffering (0043) that the same design depends on. So the real decision is a
three-way trade — subchunk size, accumulator precision, buffer count — and this entry's job is to
put the third axis on the table.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md` §4.3 "half ReduceSum 精度
限制", lines 239-243, verbatim in full:
"half 尾数 10 bits → 精确整数范围 [0, 2048]。
**规则**：`HIST_SUBCHUNK ≤ 2048`，保证每次 ReduceSum 结果 ≤ 2048。
**替代**：float32 ReduceSum 精确到 2^24（16M），但 UB 占用翻倍。"

The A2 hardware summary, line 304: `| half 精度 | 精确整数 ≤ 2048 | SUBCHUNK ≤ 2048 |`.
The technique note, line 160: "| **合理 subchunk 大小** | half ReduceSum 精确到 2048；float
ReduceSum 精确到 2^24 | 精度保障 |".
The anti-pattern, line 354: "| half ReduceSum subchunk > 2048 | half 尾数 10 bits，累加结果丢精度 |
`SUBCHUNK ≤ 2048`，或换 float32 ReduceSum (§4.3) |".

Arithmetic check performed here, because the stated bound is off by one from the naive derivation:
IEEE half has a 10-bit stored mantissa plus an implicit leading bit, so consecutive integers are
exactly representable up to 2¹¹ = 2048, and 2049 is the first integer that is not. Upstream's
"[0, 2048]" is therefore correct and its "尾数 10 bits" is the stored-mantissa count. The same
derivation for float32 (23 stored bits) gives 2²⁴ = 16 777 216 ✓, matching upstream. Both figures
are internally consistent with IEEE 754, which is a strong plausibility check — this is one of the
few claims in this book whose ground can be verified without hardware at all.

This 2²⁴ figure is the same one 0035 §2 borrows for float-carried indices; the borrowing is that
entry's inference, not upstream's.

The restriction that forces half in the first place is 0045.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Boundary arm: a half `ReduceSum` over `N` lanes each holding exactly 1.0, `N` swept over 2040,
   2046, 2047, 2048, 2049, 2050, 2056, 4096. Compare the returned value against `N` exactly, not
   within a tolerance — the claim is about exactness and a tolerance would hide it.
3. Report the first `N` whose result differs from `N`, and by how much. The direction matters: the
   round-to-even model predicts the result stays at 2048 or steps by 2, not that it becomes
   arbitrary.
4. Float32 arm: the same sweep extended to 2²⁴ ± small, to test the second figure. This is a large
   allocation and may not fit UB; if it does not, say so and record the largest `N` tested rather
   than extrapolating.
5. Cost arm: peak UB and `aiv_vec_time` for the half and float32 versions of the same reduction, to
   quantify the "UB 占用翻倍" claim rather than accepting it.

## 5 · Checker — acceptance declared before the run
Verdict variable `exact_to_half`: the largest `N` for which the half reduction returns exactly `N`.
PASS iff `exact_to_half == 2048`.
Red inputs, both informative: a value below 2048 (the accumulation order costs precision earlier
than the representation limit predicts — a real possibility if the hardware reduces pairwise
through a tree, and one this entry does not currently account for), or above 2048 (the accumulator
is wider than half internally, which would make the design rule unnecessary).
`exact_to_float`: PASS iff 2²⁴, or reported as "not reached, largest tested N" — never
extrapolated.
`ub_ratio`: PASS iff the float32 arm's peak UB is within 10 % of twice the half arm's.
This checker compares for exact equality rather than against a tolerance, which is what lets it go
red at all: any tolerance wide enough to be robust would swallow the ±1 error the claim is about.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "A2" is a product line, not a board (0041 §7). This entry
does not establish the hardware's internal accumulation order or width — if the reduction
accumulates pairwise in a tree, the effective exact range could differ from the flat-sum
derivation in either direction, and §5's red inputs name that possibility without resolving it. It
does not establish anything for non-integer data, where the relevant question is relative error
rather than exactness. It does not establish the bf16 case, whose 7-bit mantissa would give a much
lower bound and which no source in scope mentions. It says nothing about A3 or A5 (0047).
