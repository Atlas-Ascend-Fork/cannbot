# CARD · ascendc-regbase-best-practice 002 — API misuse is seven misdiagnosis classes and one repair order

**BOOK: 950 — held as a card. Seven misuse classes, none with an observable of its own; the file's real
payload is a four-step repair ORDER, which is entered as part of `950:0394` rather than on its own.**

Second of the three files named in the controller ruling on `references/knowledge/pitfalls/`. Like
`common_traps.md` (card 001) it is symptom→check process; unlike it, two of its seven items are already
carried elsewhere in the book as mechanisms.

## The file's shape (re-verified 2026-08-24)
`ascendc-regbase-best-practice/references/knowledge/pitfalls/api_misuse.md`, 161 lines. Frontmatter:
`platform: ascend950-regbase`, `purpose: Catch wrong API-family and wrong execution-model decisions before
they are misdiagnosed as precision bugs.` Seven numbered classes in a four-part form — Misuse / Why it
fails / Visible symptom / (sometimes) First check — followed by a Repair Order.

Its opening thesis, `:30`:

> Many "precision bugs" are actually API-family or execution-model mistakes. This document focuses on
> misuse classes that should be ruled out before tuning tolerances or widening precision.

## Disposition, class by class

| # | Class | Disposition |
|---|-------|-------------|
| 1 | Mixing regbase and membase mental models | **card** — the disagreement it rests on is `C-950rem-002`, carried by `950:0372` |
| 2 | Skipping whitelist-first validation | **card** — the whitelist's own reliability is entered as `950:0353` and `950:0354` |
| 3 | Treating synchronization bugs as numeric noise | **ENTRY `950:0394`** — the rerun-stability discriminator is falsifiable |
| 4 | Assuming reduction validity across all shapes | **card** — subsumed by `950:0395`'s case-set claim |
| 5 | Casting based on convenience instead of contract | **card** — the reference half is quoted in `950:0396` §1; the cast-placement half in `950:0357` §2 |
| 6 | Repairing the final output only | **card** — restates `common_traps.md` trap 5 |
| 7 | Letting template scaffolding override regbase semantics | **card** — restates `common_traps.md` trap 6 and `regbase_vs_membase_confusions.md` §1 |

Three of the seven are restatements of items in the sibling file. That redundancy is itself worth
recording: the two files were evidently written from one experience base and split by angle (symptom-first
versus API-first), so **the pitfalls directory is not seven independent origins, it is one**.

## Quotes worth keeping (verbatim)
`:47-63` (class 2), which is the one with a concrete instruction:

> Misuse:
> - selecting an API because it looked familiar in another branch or example
>
> Why it fails:
> - the implementation can drift into unsupported or misleading usage before anyone verifies the regbase
>   contract
>
> Visible symptom:
> - design and code disagree on which primitive is actually supposed to exist or be used
>
> First check:
> - read `../api/regbase_api_whitelist.md` before debugging implementation detail

`:100-114` (class 5), the sharpest symptom description in either pitfalls file:

> Misuse:
> - downcasting early to simplify storage or reuse
> - comparing output against a reference that assumes a different cast mode
>
> Why it fails:
> - cast placement and rounding behavior can dominate the error budget
>
> Visible symptom:
> - stable systematic bias
> - "small but stubborn" mismatches that survive algorithm fixes

`:145-152`, the Repair Order — the file's most useful ten lines:

> Before making a precision-only fix:
>
> 1. validate branch and API family
> 2. validate whitelist and sync assumptions
> 3. identify the first bad intermediate
> 4. only then tune dtype, cast point, or stabilization logic

## Why this is a card and not an entry
The seven classes have symptoms and no observables. "Design and code disagree on which primitive is
supposed to exist" is a review finding, not a device readout; a §4 targeting it would be an instruction to
read a document.

The Repair Order is different in kind and *is* entered — as `950:0394` §2's justification. The reason it
earns entry there and not here: its force is not that steps 1-2 are more *likely* than step 4, it is that a
precision-only fix applied to a race **destroys the evidence**, because the widened build stops failing and
there is nothing left to bisect. That is a falsifiable claim about a repair's side effect
(`950:0394` Arm D), and it needs a kernel with a planted race to test. Standing alone as an ordering
preference it has no procedure.

**Class 2's instruction is now partly contradicted by this book's own findings.** "Read the whitelist before
debugging implementation detail" is good advice whose target is unreliable in both directions: `950:0353`
records the whitelist's `DataCopy | VF? No` row against the same skill's canonical VF body, and `950:0354`
records 27 header-declared names absent from its VF-safe tables plus one listed name (`Reg::Divs`) that is
declared nowhere. So the first check the file prescribes has a measured failure rate, and an agent following
class 2 literally will reject working code about a third of the time. That interaction is recorded here
because it is the kind of thing a merge should surface.

## Guessed level
L8 (toolchain & build) for classes 1, 2, 7; L4 for class 3; L5 for classes 4, 5; L7 for class 6.

## Evidence class
bare, all seven. No measurement, no shape, no board, no case reference. `regbase_api_sync.md` — the file
classes 3 and 7 route to — was **not read** in this block (`Q-950rem-30`), so the destination of the file's
main routing rule is unexamined.

## OVERTURN sketch
For the Repair Order, as entered at `950:0394`: a planted race whose evidence survives a precision-only
repair — i.e. the race remains detectable after widening — which would remove the ordering's justification
and leave it resting on base rates nobody has measured.

## Disposition
Card kept. Re-read after `regbase_api_sync.md` and the four unread pitfalls files (`Q-950rem-29`,
`Q-950rem-30`) are mined; class 3's routing target and class 5's cast-mode contract are the two most likely
to become entries once their destinations are known.
