# CARD · perf-optimize-core 004 — a VF is not worth starting below 32 active lanes

**BOOK: 950 (fragment) — held as a card: one number, stated twice as a stop rule, with no derivation
and no measurement; it is quoted inside the entries it bounds rather than standing alone.**

## Quotes (verbatim, re-verified 2026-08-24)
`ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-03-fused-instr.md:55`:

> - 尾段单次 lane < 32 的短向量不值得改（VF 启动有固定开销）。

`ibid/vec-09-loop-sink-into-vf.md:37`:

> - 尾段单次 lane < 32 的短向量不值得起 VF（VF 启动有固定开销）。

## Why this is a card and not an entry
It is a threshold on the same axis as the entries that already carry it: **950:0022** (vec-03) and
**950:0033** (vec-09) both quote it in §3 and both make the short-vector regime an explicit arm of
their §4 sweeps — the procedures already test it, as the point where the predicted gain must cross
zero. Lifting it into its own entry would duplicate those procedures without adding a distinct §4.

What keeps it on a card rather than being dropped: 32 is a lane count, and the lane count itself is
not established for any board (`GetVecLen()/sizeof(T)`, entry **950:0252**), so "32 lanes" is
half of one register at fp32 *if* the aside "A5 fp32=64" holds. Both statements of the rule are about
a **tail** segment, which is also where the unified-mask technique (**950:0038**) claims the tail
should be folded into the main loop rather than given its own path — so the two pieces of advice meet
at exactly this boundary and neither is measured.

## Guessed level
L5 (compute & numerics).

## Evidence class
measured-unscoped — a specific integer, twice, with no case, no board and no derivation.

## OVERTURN sketch
On a named 950 board, a VF invoked on a tail of 16 or 24 active lanes that is faster than the
high-level path it replaces — the fixed start-up cost would then not dominate at that width, and the
32 is not a boundary.

## Disposition
Card kept as the pointer that ties 950:0022, 950:0033 and 950:0038 to one unmeasured number.
