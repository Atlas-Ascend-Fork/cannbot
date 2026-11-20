# CARD · ascendc-regbase-best-practice 005 — five tiling review items and six performance habits, with no numbers

**BOOK: 950 — held as a card. Covers `dev-experience/tiling_review_notes.md` and
`dev-experience/regbase_performance_practices.md`, ~180 lines, one entry between them (`950:0369`, from the
TilingKey three-part contract).**

Both files are distilled engineering experience with a real subject and no quantities. They belong in a
card because every claim in them is directional — do more of this, less of that — and none names a
threshold, a shape, a board or a readout.

## `tiling_review_notes.md` (87 lines, re-verified 2026-08-24)

Six review items. One became an entry.

| # | Item | Disposition |
|---|------|-------------|
| 1 | Treat includes as part of the contract — review by file role, not by memory | card |
| 2 | `StorageShape` confusion is a logic smell, not a method-call error | card |
| 3 | TilingKey drift: host sets one key, kernel branches on another, binary metadata advertises a third | **ENTRY `950:0369`** |
| 4 | Namespace hygiene across `_struct.h`, `_tiling_arch35.*`, `_apt.cpp` | card |
| 5 | `TilingPrepare` captures platform facts, `Tiling` consumes shape/dtype facts | card |
| 6 | Serialisation rules need their own review pass — macros host-side, plain structs kernel-side | card |

The five carded items are one claim in five places, and the card exists to say so: **an operator is defined
by an agreement among files, and no tool checks the agreement.** `:8-18` lists five file roles (host tiling
header, host tiling implementation, kernel entry, kernel-side struct, kernel implementation header);
`:40-42` says a namespace mismatch across three of them "is usually a sign that the route was assembled by
copy-paste rather than by a stable mental model"; `:58-60` says host macros and kernel plain structs being
"almost aligned rather than exactly aligned" hides the bug until much later.

Item 5 verbatim, `:44-56`, because it names a boundary an agent can actually check:

> Repeated failure pattern:
>
> - platform-only logic leaks into runtime shape logic
> - or runtime assumptions are incorrectly pushed into prepare-time code
>
> The stable habit is:
>
> - `TilingPrepare` captures platform facts
> - `Tiling` consumes real shape/dtype facts
>
> Review any code that blurs that boundary.

That is the closest item to entry-worthy and it still fails the §4 test: the observable would be "platform
facts appear in the wrong function", which is a code-reading verdict, not a device readout. It is recorded
here because it bears directly on `950:0207` (every capacity and core count must be queried at runtime) —
`TilingPrepare` is evidently where that query belongs, and no source in scope says so outright.

## `regbase_performance_practices.md` (92 lines, re-verified 2026-08-24)

Six habits, none entered.

`:26-36` — full-load versus non-full-load is a **design** split, not a late optimisation: "can the real
working set stay resident locally?" and, when scale is unknown, "design with both routes in mind". This is
the performance-side statement of `950:0360`'s Pattern 2 and adds no number.

`:38-49` — vectorised reduction is non-negotiable: "if the problem is a reduction, start from vectorized
reduction assumptions / scalar accumulation is only acceptable for the tiny cross-segment summary layer,
not the main body". Related mechanisms are entered from other skills (`950:0030` the hardware tree
reduction, `950:0031` independent accumulators); this file adds the *design rule* and no cost.

`:51-59` — double buffering must earn its space: helps when movement dominates, when there is memory for two
useful stages, and when there is steady work to hide the transfer. "Do not add it by reflex." Compare
`950:0042` and `950:0012` (double buffering is effective only when MTE2 and vector alternate in the trace),
which is the same claim with a diagnostic attached, from `ascendc-perf-optimize`.

`:61-69` — MTE efficiency is about shape, not API choice: block size, address alignment, fragmentation.
"If the route is copy-bound, revisit transfer shape before revisiting math."

`:71-79` — **`__VEC_SCOPE__` placement affects real performance**, verbatim:

> On 950, `__VEC_SCOPE__` is not just syntax. Poor placement can:
>
> - repeatedly re-enter vector context
> - fragment a stable compute chain
> - increase register and scheduling overhead
>
> The working habit is to keep the hot path contiguous unless a real dataflow break forces a split.

This is the one item in either file that names a **950-specific machine effect** — a per-scope entry cost —
and it is the strongest candidate for future promotion. It fails now only for lack of a magnitude: nothing
in scope says what re-entering vector context costs, so a §5 could not state what red looks like.

`:81-83` — multi-row batching is often the real optimisation when rows are naturally small. Compare
`950:0029` (load the loop-invariant once and pack short rows into one vector length).

## Why these are cards and not entries
Every claim is a direction with no threshold. "Do not add double buffering by reflex" has no procedure that
could fail; "keep the hot path contiguous" has no measured cost; "start from vectorised reduction
assumptions" is a design default. The plan's test applies: no writable §4, no verdict variable, nothing for
§6 to record.

The two files are also **secondary sources by their own admission** — `tiling_review_notes.md:6` says it
"turns the 950 tiling checklist into review-oriented engineering experience" and
`regbase_performance_practices.md:6` says it "extracts the most reusable engineering lessons from the 950
performance cards". Neither the checklist nor the performance cards are in this harvest's scope, so these
files are distillations of material the books cannot see, which is a further reason not to enter them as
though they were the evidence.

## Guessed level
L6 (tiling & scheduling) for `tiling_review_notes.md`; L9 (performance) for
`regbase_performance_practices.md`, except the `__VEC_SCOPE__` item which is L1.

## Evidence class
recipe-no-numbers throughout. Not `待实测` — neither file marks anything as pending measurement; they are
written as settled experience with the numbers omitted.

## OVERTURN sketch
For the `__VEC_SCOPE__` placement claim, which is the one worth promoting: one kernel built with its VF body
as a single contiguous `__VEC_SCOPE__` and again split into several, identical arithmetic, compared on one
die in one session at three tile sizes. If the durations agree, scope entry is free and the habit is
stylistic. If they differ, the per-entry cost is the number this file needed and did not have — and it
should then be entered with a real §4.

## Disposition
Cards kept for both files. **`__VEC_SCOPE__` placement is the one item flagged for promotion**: it names a
concrete, board-specific, measurable effect and lacks only a magnitude. Recorded for the controller: the
`TilingPrepare`/`Tiling` boundary (item 5) is where `950:0207`'s runtime-query rule would live, and no
source in scope states that connection.
