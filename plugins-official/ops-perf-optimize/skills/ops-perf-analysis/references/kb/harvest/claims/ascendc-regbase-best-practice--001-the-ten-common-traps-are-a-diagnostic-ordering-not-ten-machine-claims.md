# CARD · ascendc-regbase-best-practice 001 — the ten common traps are a diagnostic ordering, not ten machine claims

**BOOK: 950 — held as a card for seven of the ten. Three of the ten became entries
(`950:0394`, `950:0395`, `950:0396`); the other seven are symptom→check routing with no falsifiable
machine claim and no observable that a §4 procedure could target.**

This card exists because of the controller ruling on `references/knowledge/pitfalls/`: falsifiable machine
claims become entries, pure symptom→check diagnostic process becomes claim-cards. `common_traps.md` is
199 lines and is the clearest instance of the second kind in the subtree, so the split is recorded here in
full rather than as an omission.

## The file's shape (re-verified 2026-08-24)
`ascendc-regbase-best-practice/references/knowledge/pitfalls/common_traps.md` — ten numbered traps, each
in a fixed three-part form:

> ## N. <trap name>
>
> Signal:
> - …
>
> Why it happens:
> - …
>
> Check first:
> - …

The frontmatter scopes it: `platform: ascend950-regbase`, `topic_type: pitfall`, `depth: foundation`, and
`purpose: Surface the highest-frequency regbase debugging traps before repair work turns into blind trial
and error.`

## Disposition, trap by trap

| # | Trap | Disposition |
|---|------|-------------|
| 1 | Treating a branch error as a precision error | **card** — routes to two other files, no observable of its own |
| 2 | Promoting too late | **card** — the mechanism is entered as part of `950:0357` §2; the trap itself is an ordering heuristic |
| 3 | Assuming small-shape success proves correctness | **ENTRY `950:0395`** — names three required cases and a first-failure-locus diagnostic |
| 4 | Using a single failure metric | **ENTRY, folded into `950:0396`** — the metric rule is quoted there and drives its §5 |
| 5 | Chasing the final output instead of the first divergence | **card** — a debugging strategy, no predicate |
| 6 | Trusting the template as semantic truth | **card** — restates `regbase_vs_membase_confusions.md`; see card 003 |
| 7 | Ignoring hardware and shape constraints | **card** — quoted in `950:0395` §3 as a recognition signal; its four named causes are quantities this book records as disputed or unmeasured |
| 8 | Treating non-determinism as harmless noise | **ENTRY `950:0394`** — the stability discriminator is falsifiable |
| 9 | Blindly widening everything to `fp32` | **card** — the outcome trap 8 prevents; quoted in `950:0394` §3 |
| 10 | Using weak reference outputs | **ENTRY `950:0396`** — reference-strength claim is testable by a two-reference comparison |

## Quotes for the seven carded traps (verbatim)
`:32-46` (trap 1):

> Signal:
> - outputs are wildly wrong, all zero, or obviously off-scale
> - review mentions a default template or membase-style implementation showing through in a regbase task
>
> Why it happens:
> - the design borrowed the wrong API family or wrong execution mental model

`:48-62` (trap 2):

> Signal:
> - `fp32` patches are added but the failure barely improves
> - the first large diff appears before the promoted step
>
> Why it happens:
> - the code upgrades precision after an unstable low-precision reduction, subtract, or nonlinear
>   operation already destroyed signal
>
> Check first:
> - identify the earliest bad intermediate
> - move promotion in front of the risky step

`:96-111` (trap 5):

> Signal:
> - many speculative fixes, little understanding
> - every patch changes the surface symptom but not the root cause
>
> Check first:
> - stage the formula
> - compare the first unstable intermediate
> - if quick checks stall, switch to a binary-search style intermediate walk

`:113-126` (trap 6): "regbase code is forced into queue- or pipeline-centric design just because the default
direct-invoke template uses it" … "the template is an engineering skeleton, not the authoritative regbase
implementation model".

`:128-143` (trap 7): "only certain axis lengths or tile sizes fail / behavior flips around minimum-size
thresholds" … "reduction width, alignment, tail masks, or buffer limits were assumed instead of checked".

`:161-175` (trap 9): "the bug disappears but performance or design clarity collapses / no one can explain
which step actually needed wider precision" … "the fix was chosen for convenience, not diagnosis" …
"narrow the repair to the unstable sub-chain / prove which intermediate requires widening".

## Why these seven are cards and not entries
Each fails the plan's own test — "an entry whose §4 you cannot write is not ready" — for the same reason:
**there is no machine behaviour to target**. A §4 for trap 5 would be "compare intermediates instead of the
output", which is a description of debugging, not a procedure with a device, a readout and an acceptance
predicate. A §5 would have no verdict variable, and a §6 would have nothing to record.

Trap 7 is the closest to entry-worthy and still fails: its four named causes — reduction width, alignment,
tail masks, buffer limits — are quantities this book has separately recorded as **disputed or unmeasured**
(`950:0209` and `Q-950arch-04` for the UB limit, `950:0257` for the alignment requirement, `950:0360` for
the logical unit). So an agent following trap 7's advice to "check" them finds several have no established
value, and the trap's content is a pointer at open questions rather than a claim.

Trap 2 is entered *as a mechanism* inside `950:0357` §2 (promote before the destabilising step, not after)
because that entry has a pattern to attach it to. Standing alone it is an ordering heuristic.

## Guessed level
L7 (verification) for the set; individual traps span L4, L5 and L7.

## Evidence class
bare, all ten. No measurement, no shape, no board, no case reference anywhere in the file. The frontmatter
carries `platform: ascend950-regbase` and the body names no board.

## OVERTURN sketch (for the set, if it were ever entered)
A defect population in which the ten traps' "check first" order is measurably worse than a different
ordering — i.e. the routing costs cycles rather than saving them. That is a study of agents, not of a
device, which is a further reason these are cards.

## Disposition
Cards kept for the seven. Promote any one if a symptom, a threshold or an observable failure mode is found
in another source — `Q-950rem-29` records that four sibling files in the same directory
(`precision_guide.md`, `precision_failures.md`, `symptom_to_cause.md`, `index.md`) were **outside this
block's declared scope and were not read**, and two of them are the subtree's dedicated numerical material.
Any of the seven may be entry-worthy once those are mined.
