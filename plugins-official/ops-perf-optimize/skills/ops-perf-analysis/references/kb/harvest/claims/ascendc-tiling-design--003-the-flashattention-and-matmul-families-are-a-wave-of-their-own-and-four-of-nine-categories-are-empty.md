# CARD · ascendc-tiling-design 003 — the FlashAttention and matmul families are a wave of their own, and four of nine categories are empty

**BOOK: 950 — candidates, deliberately deferred by the a later harvest pass `950-td` harvester. This card records
what was read for scope and not mined, and why, so a later pass does not re-survey it.**

All paths relative to `ops/ascendc-tiling-design/`. Quotes below were read at card time; a later pass
re-verifies each against the file before building on it.

## The operator taxonomy, and what is genuinely absent

`SKILL.md:10-20` declares **nine** operator categories with a status marker each. Mined or already
covered elsewhere: Reduction (`950:0401`–`0404` from this shelf; `950:0121`–`0131` from the analysis
shelf), Elementwise, Broadcast (`950:0414`; `950:0154`–`0156`), Conversion (`950:0163`–`0165`).
**Four carry `📋 规划中` and have no content at all**: Random 随机类 (`:16`), Convolution 卷积类
(`:18`), NN 神经网络类（其它） (`:20`), and — partially — MatMul, whose row reads
`✅ [场景路由](references/matmul/patterns.md)（mxfp8 + eltwise 融合；其它 matmul 形态规划中）` (`:17`).
Conversion's own row is qualified too: `⚠️ …（当前仅 Transpose 部分支持）` (`:15`).

Recording the absence as an absence is this project's rule, and the absence here has a shape worth
stating: **the four empty categories are exactly the ones with no `references/<family>/` directory**,
so `ls references/` is a faithful index of what the skill covers. That is a filename-channel property
and it is worth an entry in its own right — the taxonomy table and the directory listing agree, which
is not true of the perf-optimize shelf (`950:0152`, `950:0156`, `950:0163` all record `占位` labels over
directories holding complete content).

## FlashAttention — 1 224 lines, unmined, and the reason

`references/flashattention/` is three files: `overview.md` (249), `design.md` (634),
`subfamilies.md` (341). `SKILL.md:19` marks it `✅` with a mandatory reading order
(`[分析](…overview.md)（⚠️ 必须先读） / [设计](…design.md) / [子族契约](…subfamilies.md)`).

**Why deferred, and it is not lack of value.** This domain's assignment was DAV_3510 columns and
twin-diffs against entries already in the book. The FA family is neither: it is a *design methodology*
for one operator family, it has no counterpart in the analysis shelf (whose `tiling/fa/` is the one
genuine stub — `950:0169`), and it has no counterpart in the implementation shelf either
(whose `reference/flash_attention/` is five scalar-optimisation design notes, already carried at
`950:0334`–`0337`). So entries from it would be **new material, not diffs**, and would need a reading
of all three files plus the `subfamilies.md` contract before the first entry could be scoped. That is a
wave, not a batch.

**What a later pass should expect.** `subfamilies.md` is named a 契约 (contract), which in this
repository has been a reliable marker for a document that states obligations a consumer can violate —
the class `950:0343` (build contract read off the compiler command) and `950:0142` (thresholds that are
policy, not capability) come from. `overview.md` being marked `必须先读` twice suggests a routing
document whose skip is the failure mode, which is the shape `950:0101` records for the analysis shelf's
two-level routing.

**One cross-family note already established.** `950:0169` records that the analysis shelf routes
GroupNorm into its FA stub, past a reduction family that covers it. This shelf's taxonomy puts
GroupNorm in `NN 神经网络类（其它）` (`SKILL.md:20`), which is `📋 规划中` — so the two shelves disagree
about where GroupNorm belongs, and both destinations are empty. That is a contradiction row a later
pass should file, and it needs only the two lines above.

## MatMul — 584 lines, unmined, and a scope trap

`references/matmul/` is `patterns.md` (188) and `matmul-fusion-design-template.md` (396).

**The scope trap is in the SKILL.md row itself**: `mxfp8 + eltwise 融合；其它 matmul 形态规划中`. So
this family's `✅` covers **one fusion pattern**, and every other matmul form is planned-not-present. An
agent reading the taxonomy table's tick and routing a plain matmul here gets a document about a fusion
it is not doing. The analysis shelf's matmul family is large and fully entered (`950:0107`–`0117`), and
`950:0347` records that it names no chip in any of its seven files — so a diff between the two would be
comparing a general tiling algebra against one fusion recipe, which is not a like-for-like comparison
and would produce misleading rows if attempted carelessly.

**What is likely genuinely new**: `matmul-fusion-design-template.md` is a *template* for writing a
fusion design, and this repository's other design-template documents have carried real obligations
(`950:0338` records two designs declining to state a benefit number and naming acceptance criteria
instead). A later pass should read it for the obligations it imposes, not for constants.

## Reduction remainder in this shelf, and why it was left

Mined: `patterns.md`, `algorithms.md`, `ar-colsplit.md`, `ara-rowsplit.md`, `alg-dichotomy.md`,
`alg-welford.md` → `950:0401`–`0404`. **Left**: `ar-fullload.md` (151), `ara-fullload.md` (228),
`multi-axis-transform.md` (83), `multi-output-buffer.md` (115), `tiling-fields.md` (94),
`with-index.md` (247), `alg-group-reduce.md` (101).

Reason: the two full-load arms restate UB budgets that `950:0123` already carries from the analysis
shelf in more detail, and `tiling-fields.md` is their field table. The three genuinely unmined ones
are `with-index.md` (247 lines — the index-tracking variant, which the analysis shelf treats as an
optional enhancement and this shelf treats as an orthogonal dimension; already implicated in
`950:0035`'s neighbourhood for the other book), `multi-axis-transform.md` (the three-step shape
transformation `950:0401` §3 cites but does not open), and `multi-output-buffer.md` (a buffer equation
with no counterpart anywhere).

## Evidence class
Recipe-and-methodology throughout, no measurements anywhere in this shelf, no board tokens. The DAV
vocabulary appears as dual-arch table columns (`SKILL.md:46` gives `DAV_2201: 192KB, DAV_3510: 248KB`,
whose 950 half is `950:0209` and whose 910 half is the other book's) and as branch conditions in the
broadcast family (`950:0154`). Nothing in the FA or matmul families names a chip.

## OVERTURN sketch (for the deferral)
A measured figure, a board token, or a constraint contradicting an entered claim, found anywhere in
`references/flashattention/` or `references/matmul/`. Neither directory was read line by line, so this
card's "no measurements, no chips" statement is a property of the shelf-level survey and not of a full
read — a later pass must not inherit it.

## Disposition
Deferred with named starting points. Recorded in `harvest/standing/950-td.md` under deliberate skips.
Priority for a later pass: FlashAttention (three files, contract-bearing, no counterpart anywhere) →
the four-empty-categories entry (cheap, and the filename-channel property is worth stating) →
GroupNorm's two empty destinations (a contradiction row needing two lines) → reduction remainder's
three unmined files → matmul fusion template's obligations.
