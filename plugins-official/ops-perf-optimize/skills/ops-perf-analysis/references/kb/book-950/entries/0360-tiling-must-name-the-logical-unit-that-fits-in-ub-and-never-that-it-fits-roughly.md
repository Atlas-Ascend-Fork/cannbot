```
ID:        0360-tiling-must-name-the-logical-unit-that-fits-in-ub-and-never-that-it-fits-roughly
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). The rule is stated as
           a design discipline with five red flags and no enforcement mechanism. Nothing was compiled
           and no tiling was run.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/tiling_patterns.md:60-74
           — "## Pattern 2: Full-Load Versus Split-Load / For reduction or broadcast work, the first
           branch is usually: / - can one full logical unit fit into UB with all required temporary
           state? / - if yes, choose full-load / - if no, choose split-load and make merge behavior
           explicit / Examples: / - `AR` reduction: can one full row fit? / - `ARA` reduction: can one
           `[R, tileA0Len]` block fit? / - broadcast: can one collapsed multi-axis output slice fit
           after accounting for all live inputs and outputs? / Never describe this as “fits roughly”.
           The design should name the logical unit that fits or does not fit."
SOURCE:    same file:109-115 — "## Tiling Red Flags / - The design gives formulas but never states the
           logical unit being loaded. / - Tail handling is omitted for either block or UB loops. / -
           The split axis changes between design and code comments. / - UB capacity is computed
           without counting live buffers or temporary storage. / - The design mixes regbase execution
           assumptions with membase queue choreography."
SOURCE:    same file:96-107 — "## Pattern 5: Record the Contract, Not Just the Numbers / A good regbase
           tiling section records: / - collapsed shape form / - branch key: full-load vs split-load,
           `AR` vs `ARA`, one-dim vs multi-dim broadcast / - core split fields: core count, block
           size, tail block behavior / - UB split fields: `ubFormer`, loop count, tail tile behavior /
           - alignment-sensitive lengths / - any workspace requirement"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 tiling implementation that passes every functional and performance test while stating
           only formulas and no logical unit — i.e. the named unit carries no information the formulas
           do not — which would make the rule a documentation preference rather than a design gate.
           Concretely observable: two independent implementers given only the formulas produce
           identical tile decisions.
```

# 0360 · Tiling must name the logical unit that fits in UB, and never that it fits roughly

## 1 · Claim
Upstream asserts that the first tiling branch for reduction and broadcast work is a full-load question —
can one full logical unit fit into UB *with all required temporary state* — and that the answer selects
full-load or split-load, with split-load obliged to make its merge behaviour explicit. Upstream asserts
a prohibition on how the answer may be written: "Never describe this as 'fits roughly'. The design
should name the logical unit that fits or does not fit." Upstream names three example units — one full
row for an `AR` reduction, one `[R, tileA0Len]` block for `ARA`, one collapsed multi-axis output slice
for broadcast. Upstream asserts a six-field record of what a tiling section must state, and five red
flags, the first of which is a design that gives formulas and never states the unit. Not established
here: nothing was compiled and no tiling was run.

## 2 · The wrong branch this removes
A tiling section that contains only formulas looks complete. It has numbers, the numbers are derived,
and the derivation can be checked. What it lacks is the one fact that makes the numbers auditable: what
quantity was being fitted.

The failure that produces is specific. `ubFormer × sizeof(T) × liveBuffers ≤ ubSize` is satisfiable by
many tuples, and the tuple a search returns is the one that maximises the objective the search was
given. If nobody wrote down that the unit is *one full reduction row*, the search is free to return a
tile that holds two-thirds of a row — arithmetically valid, semantically a split-load, and the merge
step it now requires does not exist anywhere in the design. The kernel is correct at shapes where the
row happens to fit and silently wrong, or silently degraded to a partial reduction, where it does not.
That is the shape 0123 records for the reduction family: each template carries its own UB budget with
named fixed reserves, and the reserve only means anything against a named unit.

"Fits roughly" is worse than a wrong number because it is unfalsifiable. A design that says the tile
"comfortably fits" cannot be checked against a capacity, cannot be re-derived when the capacity changes,
and cannot be reviewed — a reviewer has nothing to disagree with. And the capacity *does* change: this
book records four different UB figures in upstream documents for one family (C-004, C-006, 0131), so
every tiling built on an unnamed unit is built on an unnamed capacity too, and neither error is visible.

The fourth red flag — "UB capacity is computed without counting live buffers or temporary storage" — is
where this rule meets 0356. A design that names its unit and then sizes it against input tiles only,
ignoring the register-widening temporaries an fp16 route requires (0357), has done the discipline and
still got the number wrong. The rule and the count are two separate obligations, and upstream lists them
as two separate red flags for that reason.

The third red flag — "the split axis changes between design and code comments" — is the drift detector,
and it only works if the design named an axis in the first place. A design of formulas has nothing for
the code to drift from.

## 3 · Ground / Source
`tiling_patterns.md:33-41` sets up what a tiling design owes before Pattern 2 states the rule:

> Every usable tiling design answers five questions:
>
> 1. What is the shape abstraction after collapse: linear, `AR`, `ARA`, or broadcasted multi-axis?
> 2. How many cores can do meaningful work without creating tiny blocks?
> 3. Which unit is the first stable split: block, row group, tile, or broadcast slice?
> 4. What is the UB processing unit and how is its tail handled?
> 5. Which fields must be recorded so implementation and review use the same branch assumptions?

Questions 3 and 4 are the ones this entry is about, and the rule at `:74` is their acceptance criterion.
Pattern 2 is quoted in full in SOURCE; the operative sentence is the last one, and it is the only
imperative in the file's Pattern sections.

Pattern 3, `:76-84`, adds the criterion for choosing *which* axis when full-load fails, and it is a
semantic criterion rather than a size one:

> When full-load is impossible, split the axis whose merge semantics are easiest to reason about:
>
> - split `R` for streaming reductions when chunk merge is associative enough
> - split the output tile axis for broadcast when stride-zero reconstruction stays simple
> - keep the retained `A` axes as the identity side of the computation whenever possible
>
> This matters more than raw tile size. A slightly smaller but semantically stable split is safer than a
> larger tile with unclear merge rules.

"Associative enough" is undefined and is a real gap: 0132 records that scan is ordered, so splitting its
`R` axis across cores must propagate carry rather than sum partials — an instance where the merge is not
associative and the file's own heuristic would mislead. This entry does not extend the heuristic; it
records that upstream states it without a test.

Pattern 4, `:86-94`, orders collapse before tiling and is carried separately by 0361.

The soft figures in Pattern 1, `:54-58`, are deliberately **not** claimed here:

> - per-core work should stay above the small-work threshold
> - linear block splits often align to 512-element style boundaries
> - UB tiles align to 256B, while one-dim broadcast can use a 128B-oriented inner split

"the small-work threshold" is named and never given; "512-element style" and "256B" carry no chip scope
and no provenance in this file. 0153 carries the 512-element alignment and the 4 KB per-core floor from
the elewise family's own documents, which is where they have a source. Repeating them here from a file
that states them without provenance would be exactly the hardcoded-constant defect F4 exists to stop.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
The claim is that naming the unit changes outcomes, so the procedure compares outcomes with and without
the naming. Arms A and B need no device.

Arm A — the information content of the unit, tested directly. Take three real tiling designs from the
0101-0169 block's families (one `AR` reduction, one `ARA`, one broadcast). For each, produce two
briefs: the formulas alone, and the formulas plus the named logical unit. Give each brief to an
independent implementer and record the tile decision each returns. If the formula-only implementers
converge on the same decision as the unit-informed ones, the unit adds nothing and the rule is
documentation preference — the OVERTURN condition. If they diverge, the divergence cases are the
readout, and they are the concrete argument for the rule.

Arm B — the red flags as a mechanical check. Implement the five red flags as a lint over a tiling
design document: does it name a unit; does it state tail behaviour for both loops; does the split axis
in the design match the one in the code comments; does the capacity computation enumerate live buffers;
does it mix queue choreography into a regbase design. Run it over every tiling document in the upstream
`tiling/` subtree and report hits per flag. The count per flag is the finding: a flag that never fires
is either satisfied everywhere or unimplementable, and those need different responses.

Arm C — the consequence, on a board. Take one `AR` reduction whose design names "one full row" as the
unit. Build it twice for `950PR`: once with the tile sized to hold a full row plus the template's named
reserves (0123), once with the tile sized by an unconstrained search over the capacity inequality alone.
Run both at a shape where a full row does *not* fit under the second sizing. Record correctness and
duration. §2 predicts the second is silently a partial reduction or silently slower; which of the two it
is, is what the arm reports.

Arm D — the capacity the rule is applied against, which is unresolved. Repeat Arm C's sizing under each
of the four UB figures this book records for the family (192 KB, 240 KB, 248 KB, 256 KB — C-004, C-006,
0131, 0140) and record which shapes change branch. This is the arm that shows whether the full-load
decision is robust to the capacity disagreement or sits on top of it.

Device selection, for Arms C and D: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and all builds of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`unit_changes_decision` (Arm A) — the number of the three designs on which the formula-only and
unit-informed implementers return different tile decisions. Pass iff ≥ 1. Zero is the OVERTURN and is a
live outcome, named now rather than explained away later.

`red_flag_hits` (Arm B) — five integers, one per flag, reported separately and never summed. Summing
would let four dead flags hide behind one that fires; the per-flag zero is itself the interesting
result, because a flag that never fires over the whole upstream subtree has not been shown to be able
to fire.

`unnamed_unit_consequence` (Arm C) — three-valued: wrong output, correct-but-slower, or
indistinguishable. Reported, not gated. Upstream states no consequence, so there is nothing to pass
against, and the *class* of failure is what a debugging agent needs — a partial reduction and a slow
reduction need different repairs.

`branch_flips_with_capacity` (Arm D) — the number of test shapes whose full-load/split-load branch
changes across the four capacity figures. Reported. Declared in advance so the arm cannot be summarised
as "capacity did not matter much".

The positive fixture, declared before the run: Arm B's lint must be given a control document in which
each of the five defects is deliberately planted, and must find all five. If it finds four, the missing
flag's zero count over the upstream subtree means nothing. A lint validated only against clean documents
is the known blind species — a checker pinned to "these files come up clean" cannot discover that it
cannot see. A second fixture for Arm C: the correctly-sized build must produce output matching a host
reference at every test shape; if it does not, the comparison has no baseline and the second build's
result attributes nothing.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No lint was written, no design
was briefed to an implementer, no kernel built, no die contacted, and no shape run. The quoted passages
are re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that naming the logical unit changes any
outcome, that the five red flags are detectable, or that an unnamed unit produces the failure §2
describes — Arms A through D are all open, and upstream states the rule with **no mechanism and no
consequence**.

It does not establish any of the numeric guidance in Pattern 1. The "small-work threshold" is named and
never given; "512-element style boundaries" and "256B" carry no chip scope and no provenance in this
file, and are deliberately not repeated as claims here — 0153 carries the versions that have a source.

It does not establish Pattern 3's split-axis heuristic. "Associative enough" is undefined, and 0132
records a family (scan) where the merge is not associative and the heuristic would mislead; this entry
records the heuristic's existence without extending it.

It does not establish the UB capacity the rule is applied against. Four figures are in circulation for
this family across upstream documents (C-004, C-006, 0131, 0140) and `Q-950arch-04` records that the
allocation boundary — the only thing distinguishing physical from usable — has never been measured. A
full-load decision is only as good as that number.

It says nothing about the six recorded fields of Pattern 5 beyond quoting them: whether a design missing
any one of them actually fails is untested, and the fields are a checklist upstream supplies without a
consequence for omission.

BOARD is `family-claimed(unverified)`: the file's frontmatter says `platform: common`, it names no board
token this book recognises, and no board was contacted. `common` lands this in book-950 by the regbase
mechanism vocabulary alone, which is a routing decision and not evidence of scope.
