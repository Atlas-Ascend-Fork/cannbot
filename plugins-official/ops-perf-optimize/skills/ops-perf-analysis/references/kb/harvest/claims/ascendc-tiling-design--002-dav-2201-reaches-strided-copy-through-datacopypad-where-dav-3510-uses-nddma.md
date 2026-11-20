# CARD · ascendc-tiling-design 002 — DAV_2201 reaches strided copy through DataCopyPad where DAV_3510 uses NDDMA

**BOOK: 910 — fragment, folded into entry 0036's territory rather than given its own number.**

## Quotes (verbatim, re-verified 2026-08-24)
`ascendc-tiling-design/references/reduction/multi-axis-transform.md:81`:

> DAV_2201: DataCopyPad 的 blockCount/blockLen/srcStride 参数配置 stride copy

`ascendc-tiling-design/references/reduction/multi-output-buffer.md:102-109`:

> 方式A（推荐，DAV_2201/DAV_3510 通用）: 按通道遍历，外层 (n, c)，内层连续搬 H×W
> …
>   → DAV_2201 不支持 NDDMA
> 方式C（DAV_2201）: DataCopyPad 配置 stride 参数

`ascendc-tiling-design/references/reduction/multi-output-buffer.md:36`:

> ≤ UB_SIZE (DAV_2201: 192KB)

## Why this is a card and not an entry
The capability boundary itself — **DAV_2201 has no NDDMA** — is already book-910 entry **0036**,
sourced from the broadcast files that state it most directly
(`references/broadcast/nddma-broadcast.md:5,196`). These reduction-family lines are the *same claim*
reaching a different operator family, plus the consequent fallback (`DataCopyPad` with
`blockCount`/`blockLen`/`srcStride`).

Under book-910's merge test — two entries with the same §2 are one entry — this does not earn its
own number: the wrong branch it removes ("plan an NDDMA-based strided copy on a 910 part") is 0036's
wrong branch. The UB figure at `:36` is entry 0003.

What the card adds, and why it is worth keeping: it shows the boundary is **load-bearing across at
least two operator families** (broadcast and reduction), which strengthens the case that a 910-side
consumer must not mine NDDMA-based tiling material at all — 0036 §7 explicitly declines to make
that general claim, and this card is the beginning of the survey that would support it.

## Guessed level
L3 (data movement & layout).

## Evidence class
bare — per-architecture routing statements with no measurement and no cost comparison between the
NDDMA path and the `DataCopyPad` fallback.

## OVERTURN sketch
An NDDMA-based strided copy compiles and runs on a named DAV_2201 board (this is entry 0036's
OVERTURN, and this card inherits it). Separately and not covered by 0036: the `DataCopyPad` stride
fallback is shown to be no slower than the NDDMA path on a part that has both — which would mean
the boundary costs nothing and the routing distinction is bookkeeping rather than performance.

## Disposition
Card kept as coverage evidence for 0036 §7's open question (whether *all* NDDMA-dependent upstream
optimisation material is inapplicable to 910, or only the broadcast ones named). Not promoted.
