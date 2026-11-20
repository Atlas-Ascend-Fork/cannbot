# CARD · perf-optimize-core 005 — a Cast round trip can be 30 to 50 percent of vector time

**BOOK: 950 (fragment) — held as a card: a magnitude claim with no case identity, quoted inside the
entry it motivates.**

## Quotes (verbatim, re-verified 2026-08-24)
`ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-02-reduce-cast.md:9`:

> - 计算本身只有 1–2 条指令，却夹着一进一出两次 Cast——Cast 可占总 VEC 时间 30–50%。

`ibid:47`:

> msprof `aiv_time`：省掉的 Cast 指令占比即为直接收益。**待实测**（预期：Cast 占 VEC 30–50% 的场景，
> 去掉往返可省该占比）。

Neighbouring cut, `vec.md:58`: Cast 占比 >20% → 类型转换密集场景，优化 Cast 有高收益.

## Why this is a card and not an entry
The range is the diagnostic *motivation* for entry **950:0021** (fold the cast into load and store)
and the routing cut it feeds is entry **950:0016**; both quote it. On its own it has no §4 distinct
from theirs — measuring the Cast share is step 3 of 950:0016's procedure and a reported quantity in
950:0021's.

The reason to keep it visible: the second quote makes the whole card's expected benefit *equal* to
this share ("省掉的 Cast 指令占比即为直接收益"), which is an identity between a share and a gain that
holds only if the removed instructions were not overlapping anything else. That is a modelling
assumption of the same species as the Σ/max bound in **950:0008**, and it is stated as arithmetic.

## Guessed level
L5 (compute & numerics).

## Evidence class
measured-unscoped — a range with no operator, shape, dtype or board; the card's own 性能数据 line
says 待实测.

## OVERTURN sketch
On a named 950 board, an operator whose measured Cast share is inside 30–50% and whose `aiv_time`
falls by materially *less* than that share when the round trip is removed — the share-equals-gain
identity would then be false, which is the more interesting half of this fragment.

## Disposition
Card kept; the share-equals-gain identity is flagged in 950:0021 §5, which requires the conversion
share to fall as well as the time, so a gain from elsewhere cannot be credited to the Cast removal.
