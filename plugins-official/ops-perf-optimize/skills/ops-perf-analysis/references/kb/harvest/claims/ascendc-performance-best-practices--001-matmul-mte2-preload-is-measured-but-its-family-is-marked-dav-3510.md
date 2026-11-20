# CARD · ascendc-performance-best-practices 001 — matmul MTE2 preload: measured with a shape, but its family is marked DAV_3510

**BOOK: UNDECIDED — routing conflict, deliberately not made a book-910 entry.**

## Quote (verbatim, re-verified 2026-08-24)
`ascendc-performance-best-practices/reference/matmul/mte2_preload_design.md:7`:

> 典型收益：Task 时间 **−3%–10%**（对应 `matmul` BF16 `M=1024, K=4096, N=2048` 实测
> `66.0μs → 63.3μs`，约 **−4%**；MTE2 段 `37.6μs → 32.7μs`，约 **−13%**）。

Mechanism, `:15`: pingpong double buffering is enabled but `MTE2_PONG` issue is blocked because the
instruction count inserted between PING and PONG exceeds the chip's preset instruction queue depth
("硬件参数，不可软件调大"); the fix preloads two A/B tiles to L1 in the first round so `MTE2_PONG`
issues early.

## Why this is a card and not an entry
The task brief named these numbers as a book-910 harvest target. **The evidence routes them
elsewhere**, and the routing rule (RULES.md Art. 1 + `form/CONVENTIONS.md`) is not overridable by a
brief:

- `ascendc-performance-best-practices/SKILL.md:30` assigns the whole matmul family
  適用架構 **`DAV_3510`** — "| MatMul 矩阵乘类 | MatMul, BatchMatMul, MatMul_MXFP4, MatMul_A16W16 |
  DAV_3510 | ✅ [性能优化指南](reference/matmul/guide.md) |".
- The file itself names **no chip anywhere**: `grep -niE "910|dav|arch|A2|A3|950|平台"` over
  `mte2_preload_design.md` returns only the measurement line above (no chip), a scalar-busy note at
  `:194`, and a section heading at `:259`.

So: a DAV_3510-marked family, a chip-silent file, and a measured number. Under the routing rule,
`DAV_3510` → **not book-910**. Under the "names neither" branch it would be a `family-claimed(unverified)`
910 entry with a §7 arch note — but the family marking is not "neither", it is 950.

Writing it into book-910 would attach a real measurement to the wrong book, which is the leakage
RULES.md Art. 1 exists to prevent. Writing it into book-950 is another agent's decision.

## Interesting independently of routing
The mechanism is an **instruction-queue-depth** limit, which is the same class of constraint as
book-910's 0039 (MTE1/MMAD queue depth 32, from `ascendc-performance-analysis`). If the 910-side
queue depth is 32 and this 950-side blocking is the same phenomenon, the preload technique may have
a 910 analogue that no upstream document describes. That is a *derivation* opportunity, not a
harvest — consistent with the deep-dive §5.4 conclusion that 910 work is derivation, not
verification.

## Guessed level (if it ever enters a book)
L1 (core & pipe assignment) or L9 (performance).

## Evidence class
measured-with-conditions — dtype BF16, shape M=1024 K=4096 N=2048, two timings and a pipe-segment
breakdown. **Missing**: board, core count, tool, repeat count, and any statement of run-to-run
spread on a −4 % effect.

## OVERTURN sketch
A paired run (preload vs baseline) at the stated BF16 shape on the *named* board, tiling and
TilingData held identical (the document asserts no TilingData fields change), shows no Task-time
difference beyond the baseline arm's own repeat-to-repeat spread — established from its repeats
before the arms are compared. A −4 % claim without a stated spread cannot be evaluated, and a
two-point comparison of two builds carries no attribution.

## Disposition
Left as a card. Flagged to the controller: the book-910 brief and the upstream 適用架構 column
disagree about this file, and the column won.

## Disposition amended 2026-08-24 — SUPERSEDED by `950:0304`
The open half of this card ("Writing it into book-950 is another agent's decision") is now closed.
The 950-bp a later harvest pass harvester took the decision the card deferred: **this card's routing stands, and
the claim has entered book-950 as
`0304-the-instruction-queue-depth-is-a-hardware-constant-and-mte2-preload-routes-around-it-rather-than-raising-it`.**

`950:0304` carries the full seven-column measured table (`mte2_preload_design.md:263-267`), of which
this card quoted only the summary line, and re-derives every cell. It also records something this
card could not: the seven segment deltas do **not** sum to the kernel delta, so they are overlapping
pipe occupancies and not an additive decomposition, and a reader who tries to reconcile them will
fail.

The card's routing argument is **kept, not rewritten** (RULES.md Art. 9): it is the record of why a
measured number did not go into book-910. `950:0347` now carries the underlying condition as a book
entry — the matmul family names no chip in any of its seven files (2011 lines, zero architecture
tokens), so the architecture attribution for thirteen entries (`950:0301`–`950:0313`) rests on the
single `SKILL.md:30` cell this card identified. `BOOK: UNDECIDED` at the head of this file should be
read as decided-by-`950:0304` and retained as history, not as a live question.

This card's OVERTURN sketch is superseded by `950:0304`'s, which is stricter in two ways: it
requires the variance floor to be established on the baseline arm *before* the arms are compared,
and it adds a second, independent kill condition — any documented or measured way to raise the
instruction queue depth from software, which would make the whole technique a workaround for a
misconfiguration.
