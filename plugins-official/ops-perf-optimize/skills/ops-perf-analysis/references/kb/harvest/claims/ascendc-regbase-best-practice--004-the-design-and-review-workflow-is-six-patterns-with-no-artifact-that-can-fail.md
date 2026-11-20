# CARD · ascendc-regbase-best-practice 004 — the design and review workflow is six patterns with no artifact that can fail

**BOOK: 950 — held as a card. Covers `patterns/kernel_design_patterns.md`,
`dev-experience/process_memory_cards.md`, `dev-experience/requirements_analysis_patterns.md` and
`dev-experience/complexity_and_route_selection.md` — four process files, ~430 lines, one entry between
them (`950:0395`, from Pattern 6's test-boundary list).**

These four are the workflow layer of the regbase knowledge tree: what to write down before coding, how to
recover context after compression, what to lock in the requirements, and how to classify the operator.
They are genuinely useful and they contain no falsifiable machine claim, so they are carded together
rather than left as an unexplained omission.

## What each file contains (re-verified 2026-08-24)

**`patterns/kernel_design_patterns.md` (117 lines).** Six patterns: a branch packet before code (target
platform and branch, mathematical route, shape abstraction and tiling route, reference-operator status,
precision-sensitive stages, expected API families — `:35-44`); skeleton before logic, in five ordered steps
(`:46-56`); API semantic verification before commitment, four checks (`:58-67`); walkthrough uses pattern
evidence (`:69-84`); repair preserves branch context (`:86-95`); and minimal-but-complete test boundaries
(`:97-107`).

The sixth is the one that produced an entry. Verbatim, `:99-107`:

> At minimum, design and implementation should cover:
>
> - compile viability
> - tail block and tail tile behavior
> - non-aligned copy boundaries
> - precision-sensitive shapes
> - branch-specific edge cases such as split-load reduction or broadcast degenerating to scalar
>
> These are pattern tests, not just example tests. They prove the route, not only the sample input.

That last sentence is the whole reason `950:0395` exists, and it is quoted there.

Pattern 4's contribution is a vocabulary for review comments, `:79-84`:

> A good walkthrough comment is not "this feels wrong". It names the pattern mismatch:
>
> - wrong branch
> - wrong split axis
> - unsupported reuse claim
> - precision-sensitive state dropped too early

**`dev-experience/process_memory_cards.md` (90 lines).** Five cards for long sessions, context compression
and handoff. Card 3 is the one with machine content and it is entered elsewhere — `:50-59`, "Compile Success
Is Not Artifact Success", is carried by `950:0368` together with `regbase_build_notes.md`'s four
false-progress patterns. The other four cards are process: reload the routed context after memory loss
(`:27-36`), separate structural from mathematical progress as five distinct milestones (`:38-48`), re-read
API semantics before explaining or fixing (`:61-69`), and keep phase boundaries sharp — fix the first broken
phase rather than editing every layer (`:71-82`).

Card 4's closing line, `:69`, is worth preserving verbatim:

> The expensive mistakes in Ascend C often come from "pattern memory" rather than from syntax. Regbase and
> membase can make similar-looking code imply different execution models.

**`dev-experience/requirements_analysis_patterns.md` (97 lines).** What to lock before freezing a design
packet: input and output dtypes, whether accumulation or post-process must stay fp32, whether dtype
conversion is part of the operator contract or an implementation detail (`:28-37`); and whether the working
set always fits a local tile or sometimes exceeds UB and needs split execution (`:39-46`).

The first list is the requirements-side mirror of `950:0357` (a narrow-dtype route needs extra register
state) and `950:0397` (fp16/bf16 reductions need an fp32 accumulator); the second is the requirements-side
mirror of `950:0360` (name the logical unit that fits).

**`dev-experience/complexity_and_route_selection.md` (113 lines).** A five-level operator taxonomy —
L0 single-step elementwise (`abs`, `exp`, `sqrt`), L1 short fused chain (`silu`, `swish`), L2 matrix-oriented
or framework-heavy, L3 performance-sensitive scale, L4 global aggregation / normalisation / attention-like
(`softmax`, `layer_norm`, `rms_norm`) — each with an experience rule, plus four route-selection heuristics
and a closing observation, `:96-106`:

> Complexity Is About Failure Risk, Not Just Code Length
>
> The useful question is: what can silently go wrong here?
>
> - a tiny elementwise op can still become Level 3 if the real challenge is throughput and GM traffic
> - a seemingly moderate fused op can be Level 4 if it hides a true global aggregation dependency

## Why these are cards and not entries
The plan's test decides it: "an entry whose §4 you cannot write is not ready — leave it a card." A §4 for
"lock the dtypes before design" or "reload the routed context after compression" has no device, no readout
and no acceptance predicate. A §5 would have no verdict variable and a §6 nothing to record.

The taxonomy is the closest call. Five levels with named example operators looks classifiable, and it is
not falsifiable: nothing observable distinguishes a Level 1 operator from a Level 3 one except a judgement
about what dominates, and the file says so in the section quoted above. A procedure could measure whether
two readers agree on a classification — that is the shape of `950:0355` Arm A — but agreement between
readers is a fact about readers, and the entry it would support would be about the taxonomy's usability
rather than about the machine.

**One thing these four files do carry that the books need, and that a card is the right home for**: they are
where the design *artifacts* are named. Branch packet, design packet, walkthrough, proto.md, spec.yaml,
DESIGN.md, TilingKey contract. Several of those are referenced as authorities by files this block did enter
— `950:0362` cites `spec.yaml` §2.2 for dtype support and DESIGN §2.1 for attribute ranges; `950:0364` cites
`spec.yaml`'s `aliasing` field; `950:0399` routes on `spec.yaml`'s `paradigms` field — and **none of those
documents exists in this harvest's scope**. So this card also records that the regbase knowledge tree
assumes a document set the books cannot see.

## Guessed level
L0 (launch & host) and L7 (verification) for the set; no single level fits a workflow taxonomy.

## Evidence class
bare, throughout all four files. No measurement, no shape, no board, no named case with a readout. The
`complexity_and_route_selection.md` levels name real operators and attach no numbers to any of them.

## OVERTURN sketch
For Pattern 6, as entered at `950:0395`: an operator that passes a tiny aligned shape and is subsequently
shown correct across its whole declared support range with the tail path exercised — which would identify a
class where the minimum test boundary is not minimal but sufficient.

For the taxonomy, if it were ever entered: two independent readers classifying the same six operators to
different levels, which would show the five labels are not decidable from an operator's definition.

## Disposition
Cards kept for all four files. The one machine claim in the set (Card 3, compile success ≠ artifact
success) is entered at `950:0368`; the one testable discipline (Pattern 6's boundaries) is entered at
`950:0395`. Nothing else here should be promoted without a source that attaches an observable to it.
Recorded for the merge: **`spec.yaml`, DESIGN.md, proto.md and the branch/design packet are cited as
authorities by four entries in this block and exist in no file this harvest read** — that is a coverage gap
for the controller, not a defect in these four files.
