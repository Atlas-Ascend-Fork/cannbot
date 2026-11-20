# CARD · ops-precision-standard 001 — the precision thresholds are verification methodology, not machine behaviour

**BOOK: NEITHER — deliberately not harvested into book-910. Recorded so the omission is visible and
reversible.**

## What the skill contains
`ops-precision-standard/SKILL.md:3`:

> description: 算子精度标准。描述 Ascend C 算子各种 dtype 输出对应的精度比对标准（atol/rtol）。
> 当需要（1）评估算子精度是否达标，（2）编写 ST 测试验证精度，（3）处理 FP16/FP32/BF16 等不同数据
> 类型精度问题，（4）确认算子精度验收标准时触发。

A routing tree (`SKILL.md:8-22`) over thirteen reference documents — `float_compute.md`,
`float_compute_community.md`, `integer_compute.md`, `quantization.md`, `random_generation.md`,
`non_compute.md`, `special_cases.md`, `benchmark_construction.md`, `test_case_generation.md`, plus
`golden/` — and nine Python checker scripts (`mare_mere_threshold.py`, `bitwise_match.py`,
`bootstrap_median.py`, `confidence_interval.py`, `inf_nan_check.py`, …).

The 2026-08-24 structural survey classifies this whole skill as **910B-only**
(`harvest/surveys/SURVEY_20260824_repo-structure.md` §3), which is why it was in book-910's scope.

## What WAS harvested from it
- Entry **0056** — inf comparison on 910B and later is governed by `INF_NAN_MODE_ENABLE`
  (`reference/special_cases.md:64-66`, `reference/golden/COMMERCIAL_OPS_PRECISION_DOCS.md:732-733`).
  A genuine 910-scoped semantic claim about what the machine and the checker do.
- Entry **0057** — the platform list naming "910C" against a truth source that does not define it
  (`reference/golden/COMMERCIAL_OPS_PRECISION_DOCS.md:268-269`), which is
  `harvest/contradictions-910.md` **C-910-005**.

## Why the rest was NOT harvested
The remaining content is **acceptance methodology, not machine knowledge**: atol/rtol tables per
dtype, MARE/MERE ratio rules, bootstrap-median and confidence-interval procedures, golden-reference
construction, random-distribution checks, test-case generation. These are statements about *how to
judge an operator*, not falsifiable claims about DAV_2201 behaviour.

`harvest/SOURCES.md`'s "Explicitly NOT mined" clause draws exactly this line — process instruction
rather than falsifiable machine knowledge — with the exception that embedded constraint tables may
still be cited. `0056` and `0057` are that exception exercised.

Two further reasons, specific to this book:

1. **A precision threshold is not board-scoped.** An atol of 2⁻⁸ for fp16 follows from the format,
   not from the chip; a book whose organising discipline is "every claim names the boards its
   evidence touched" (RULES.md Art. 2) adds nothing by restating format arithmetic with a BOARD field.
2. **The book-910 deliverable is a performance skill** (the delivered skill).
   Precision-acceptance methodology is a different skill's contract, and importing it would widen
   the book past what its consumer opens.

## What would change this
If a verification phase opens and a book-910 entry needs a *declared acceptance tolerance* for a
numerically-non-bit-exact comparison — 0007's L2 sweep, 0024's bandwidth grid, 0046's exactness
boundary, 0055's throughput plateau — then this skill's threshold tables become the natural source
for those tolerances, and the relevant rows should be harvested **then**, scoped to the entry that
needs them. Several book-910 §5 sections currently derive their thresholds from the run's own
repeat-to-repeat spread instead, which is defensible and needs no import.

Note also `reference/golden/OPS_PRECISION_STANDARDS.md` and
`reference/benchmark_construction.md` were not read line-by-line for this harvest — only the SKILL
routing tree, `special_cases.md`, and the `910C`/inf sections of `COMMERCIAL_OPS_PRECISION_DOCS.md`.
The omission is by scope decision, not by exhaustion.

## Disposition
`ops-precision-standard` is **mined-partial** for book-910: two entries taken, the methodology body
deliberately left. Reversible on the trigger above.
