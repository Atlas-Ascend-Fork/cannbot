```
ID:        0361-collapse-the-shape-before-computing-any-tile-number
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Upstream states the
           ordering and names no mechanism that enforces it. Nothing was compiled and no tiling was
           run.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/tiling_patterns.md:86-94
           — "## Pattern 4: Collapse Before You Tile / Before computing any tile numbers: / - collapse
           same-shape elementwise work to 1D / - collapse reduction axes into `A/R` form / - collapse
           broadcast flags into a smaller stride-zero representation / Do not compute tiling over the
           original high-rank shape if the branch route is determined by the collapsed representation."
SOURCE:    same file:35-37 — "Every usable tiling design answers five questions: / 1. What is the shape
           abstraction after collapse: linear, `AR`, `ARA`, or broadcasted multi-axis?"
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/tiling_input_validation.md:37
           — "> 异常值校验是 Tiling 入口的硬门禁，在输入预处理（如 `PadAndSqueeze`）之后、
           `FindSplitAxis` 之前执行。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 operator whose tile decision computed over the original high-rank shape equals the
           decision computed over the collapsed shape at every test shape, including a case with a
           unit-extent interior axis and a case with two adjacent contiguous axes — the ordering would
           then be an efficiency convention rather than a correctness one.
```

# 0361 · Collapse the shape before computing any tile number

## 1 · Claim
Upstream asserts an ordering: before any tile number is computed, the shape is collapsed — same-shape
elementwise work to 1D, reduction axes into `A`/`R` form, broadcast flags into a smaller stride-zero
representation. Upstream asserts the prohibition that follows: do not compute tiling over the original
high-rank shape if the branch route is determined by the collapsed representation. Upstream asserts, in
its list of five questions every tiling design answers, that the first is the shape abstraction *after*
collapse. Upstream asserts, in a sibling file, that the tiling entry's validation gate runs after input
preprocessing (`PadAndSqueeze`) and before `FindSplitAxis`. Not established here: nothing was compiled
and no tiling was run.

## 2 · The wrong branch this removes
The high-rank shape is the one the framework hands you, so computing over it is the path of no
resistance. Three things go wrong.

**The route is chosen on the wrong representation.** Every family in this book's 0101-0169 block routes
on a collapsed form: 0121 establishes that reduction collapses every shape to `A1 R A0` and that
`A0 == 1` decides the template family; 0147 establishes that gather collapses to four sizes; 0154 routes
broadcast by where the broadcast happens after collapse. A router given `[2, 1, 512, 1, 3]` and a router
given the collapsed `[1024, 3]` do not select the same template, and only one of them is looking at the
operator that will actually run. The failure is not an exception — it is a *legal* tile plan for a shape
the kernel never sees.

**Core count is computed against a phantom.** A rank-5 shape with unit-extent interior axes has a
different apparent parallelism from its collapsed form. Splitting the outermost axis of
`[2, 1, 512, 1, 3]` gives two blocks; collapsing first gives 1024 rows of 3 and a real choice about
where to cut. An agent that splits before collapsing has capped its core use at 2 on a machine with tens
of cores, and nothing reports an error. 0217 records that installed 950 SKUs span 4 to 36 cube cores, so
the cost of that cap is SKU-dependent and invisible in any single run.

**Alignment and burst length are computed on the wrong innermost extent.** The innermost contiguous
extent after collapse is what determines whether a copy is one long burst or many short ones. 0165
records the extreme version of this — a transposed last axis collapses NDDMA burst to one element — and
0133 records a stride-driven bank conflict costing 5.5×. Deciding the tile against an uncollapsed
innermost axis of 3 when the true contiguous run is 3072 elements is how a bandwidth-bound kernel gets
written by accident.

The prohibition's conditional clause is the part that gets misread. "*if the branch route is determined
by the collapsed representation*" is not a hedge that makes collapse optional — it is a statement that
the two must agree. Computing the route on one representation and the tile on the other is the specific
defect, and it is worse than consistently using either one, because the resulting design is internally
incoherent in a way neither reviewer notices: the route section reads correctly and the tile section
reads correctly.

Where this meets the validation gate: `tiling_input_validation.md:37` places the dtype/format/rank
checks after `PadAndSqueeze` and before `FindSplitAxis`. So the collapse (or at least a squeeze) happens
*before* validation, which means the rank the `CheckMaxDimensions` gate sees is the post-preprocessing
rank, not the caller's. An agent that sets `maxRank` from the operator's declared support and applies it
to a collapsed shape is checking a different quantity than it thinks. Upstream states the ordering and
never states that consequence; it is derived here and is flagged as such in §7.

## 3 · Ground / Source
`tiling_patterns.md:86-94`, in full:

> ## Pattern 4: Collapse Before You Tile
>
> Before computing any tile numbers:
>
> - collapse same-shape elementwise work to 1D
> - collapse reduction axes into `A/R` form
> - collapse broadcast flags into a smaller stride-zero representation
>
> Do not compute tiling over the original high-rank shape if the branch route is determined by the
> collapsed representation.

Three collapse rules, one per family, and no statement of what collapse *is* — no test for when two
axes may be merged, no treatment of unit extents, no statement about non-contiguous strides. The
mergeability condition is the whole content of a collapse and this file does not contain it. 0121 and
0125 carry the reduction family's version (and 0125 records the case that *cannot* be collapsed — an
interleaved `A`/`R` layout — routed by a narrow pre-gate before the five templates); 0147 carries
gather's. So the rule is stated generically in `patterns/` and implemented per-family elsewhere, which
is a reasonable division and leaves a generic reader with an imperative and no procedure.

The ordering statement at `:35-37` is the same rule expressed as a question, and it is the stronger form
because it makes the collapsed shape the *first* thing a design records: "What is the shape abstraction
after collapse". Pattern 5's recorded-fields list (`:98-107`, quoted at 0360 §3) opens with "collapsed
shape form" for the same reason.

The gate ordering, `tiling_input_validation.md:37`:

> 异常值校验是 Tiling 入口的硬门禁，在输入预处理（如 `PadAndSqueeze`）之后、`FindSplitAxis` 之前执行。

("Exception-value validation is a hard gate at the tiling entry, executed after input preprocessing —
such as `PadAndSqueeze` — and before `FindSplitAxis`.") `PadAndSqueeze` is named as the preprocessing
step, which is where a squeeze of unit extents happens; the file gives no other detail about it, and the
relationship between that squeeze and Pattern 4's collapse is stated nowhere.

Both files are `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
The claim is an ordering claim, so the procedure computes both orders and compares. No device is needed
for the decisive arm.

Arm A — decision divergence, host-side only. Take one tiling routine per family (elewise, reduction,
broadcast) and drive it twice per shape: once with the original shape, once with the collapsed shape.
Sweep a shape set built to stress collapse specifically — at minimum: two adjacent contiguous axes; a
unit-extent interior axis; a unit-extent leading axis; a non-contiguous stride that must *not* be
merged; a rank-8 shape at the family's declared `maxRank`. Record for each: selected template, core
count, `ubFormer`, tail behaviour. The number of shapes where any field differs is the readout, and the
*fields* that differ are more informative than the count.

Arm B — the `maxRank` interaction §2 derives and upstream does not state. For a shape whose original
rank exceeds the family's `maxRank` and whose collapsed rank does not, record whether the validation
gate rejects it. Both outcomes are findings: rejection means legal operators are refused; acceptance
means `maxRank` is a post-collapse limit and every operator's declared rank support means something
different from what its `spec.yaml` says.

Arm C — the consequence on a board. Take the family and shape where Arm A shows the largest core-count
divergence, build both tilings for `950PR`, and run them at that shape on one die in one session with
identical input. Record correctness and duration. §2 predicts the uncollapsed tiling is correct and
under-parallelised; if it is *incorrect*, the rule is a correctness boundary rather than an efficiency
one and this entry's LABEL is wrong.

Arm D — the mergeability condition, which is the missing procedure. For the non-contiguous-stride shape
in Arm A's set, record whether each family's collapse merges the axes it must not. A collapse that
merges a strided pair produces a tile plan for a contiguous buffer that does not exist, and the symptom
is wrong data rather than a slow kernel. This is the arm that tests the part of the rule upstream never
wrote.

Device selection, for Arm C: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and both builds run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`divergent_shapes` (Arm A) — the number of test shapes on which the two orders differ in any recorded
field, reported per family and per field, never as one total. A total would let a template-selection
divergence in one family average away against agreement in another, and template selection is the field
with the correctness consequence.

`maxrank_is_post_collapse` (Arm B) — true iff the over-rank-but-collapsible shape is accepted.
Reported, not gated: upstream states no answer, and both answers change what an operator's declared rank
support means.

`uncollapsed_penalty` (Arm C) — correctness (bit-compare against host reference) and duration ratio,
reported separately. Never merged: a correct-but-slow result and a wrong result are different verdicts
about the rule's LABEL, and one number cannot carry both.

`illegal_merge` (Arm D) — true iff any family's collapse merges the deliberately non-contiguous pair.
Pass condition is **false**. This checker is written to look for a defect the rule's own text cannot
prevent, because the text states no mergeability condition.

The positive fixture, declared before the run: Arm A must include one shape that is **already
collapsed** — a plain 1-D elementwise shape — for which the two orders must produce *identical* fields.
If they differ there, the harness is not driving one routine two ways but two different routines, and
every divergence it reported is an artefact. And Arm D must include a shape whose axes are contiguous
and *must* be merged; the collapse must merge them. Without both, the checker reads only "the two orders
differed sometimes", which does not distinguish a real ordering effect from a broken harness — the known
blind species.

Process exit codes are not the verdict for any arm: Arm B expects a rejection path that exits non-zero
by design.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No tiling routine was driven, no
shape swept, no kernel built, and no die contacted. The quoted passages are re-verified file reads of the
upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that collapsing changes any tile decision, that
computing over the high-rank shape costs anything, or that the ordering is a correctness rule rather than
an efficiency one — Arms A through D are all open and upstream states **no consequence** for violating
it.

It does not establish what a collapse *is*. Upstream gives three per-family imperatives and no
mergeability condition: no test for unit extents, no treatment of non-contiguous strides, no statement of
which axes may be merged. 0121, 0125 and 0147 carry per-family versions; the generic rule as harvested
here has an imperative and no procedure, and Arm D exists because of that gap.

The **`maxRank` interaction in §2 is derived here and stated by no source.** `tiling_input_validation.md`
places the gate after `PadAndSqueeze`, and `tiling_patterns.md` places the collapse before tiling; that
the rank checked is therefore a post-preprocessing rank is an inference from two files that never
reference each other. Arm B is what would establish it.

It says nothing about the relationship between `PadAndSqueeze` and Pattern 4's collapse — whether they
are the same operation, one a subset of the other, or two independent steps. No source in scope says, and
this entry does not guess.

It says nothing about whether collapse is reversible, which matters for output write-back: a kernel that
collapses for tiling still writes into the caller's high-rank layout, and no source in scope discusses
that direction.

BOARD is `family-claimed(unverified)`: the file's frontmatter says `platform: common`, it names no board
token this book recognises, and no board was contacted.
