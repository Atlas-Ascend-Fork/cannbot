```
ID:        0395-a-passing-small-aligned-shape-establishes-nothing-about-the-tail
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), which states the case
           set in two of its own files. Upstream gives three required cases and no threshold for
           "small" or "long". Nothing was compiled and no shape was run.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/pitfalls/common_traps.md:64-78 —
           "## 3. Assuming small-shape success proves correctness / Signal: / - unit tests on tiny or
           aligned shapes pass / - production shapes, long axes, or tails fail / Why it happens: / -
           small aligned cases hide tail handling, partial-tile masking, and scale-dependent
           accumulation drift / Check first: / - add one aligned case, one non-aligned case, and one
           long-axis case / - inspect whether the first failure starts at a tail or merge boundary"
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/kernel_design_patterns.md:97-107
           — "## Pattern 6: Minimal but Complete Test Boundaries / At minimum, design and implementation
           should cover: / - compile viability / - tail block and tail tile behavior / - non-aligned copy
           boundaries / - precision-sensitive shapes / - branch-specific edge cases such as split-load
           reduction or broadcast degenerating to scalar / These are pattern tests, not just example
           tests. They prove the route, not only the sample input."
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/pitfalls/common_traps.md:128-143 —
           "## 7. Ignoring hardware and shape constraints / Signal: / - only certain axis lengths or tile
           sizes fail / - behavior flips around minimum-size thresholds / Why it happens: / - reduction
           width, alignment, tail masks, or buffer limits were assumed instead of checked"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 operator that passes a tiny aligned shape and is subsequently shown correct at every
           non-aligned and long-axis shape in its declared support range, with the tail path exercised
           and verified — which would make the small-shape result sufficient for that operator, i.e.
           would identify a class where the rule does not bind. The rule is a claim about what a test
           establishes, so its overturn is a demonstration of sufficiency, not of failure.
```

# 0395 · A passing small aligned shape establishes nothing about the tail

## 1 · Claim
Upstream asserts a failure pattern: unit tests on tiny or aligned shapes pass while production shapes, long
axes and tails fail. Upstream asserts the reason — small aligned cases hide tail handling, partial-tile
masking and scale-dependent accumulation drift. Upstream asserts the minimum case set: one aligned case,
one non-aligned case, and one long-axis case; and the diagnostic to apply when a failure appears —
inspect whether the first failure starts at a tail or a merge boundary. Upstream asserts, in a second file,
a five-item minimum test boundary covering compile viability, tail block and tail tile behaviour,
non-aligned copy boundaries, precision-sensitive shapes, and branch-specific edge cases such as a split-load
reduction or a broadcast degenerating to scalar — and asserts that these are pattern tests that prove the
route rather than the sample. Upstream asserts, in a third passage, the companion signal: only certain axis
lengths or tile sizes failing, and behaviour flipping around minimum-size thresholds, because reduction
width, alignment, tail masks or buffer limits were assumed instead of checked. Not established here:
nothing was compiled, no shape was run, and upstream gives **no threshold** for "tiny", "small" or "long".

## 2 · The wrong branch this removes
The trap is not that agents forget to test. It is that the shape they naturally pick to test with is the
one that exercises the fewest code paths in the kernel they just wrote.

**A small aligned shape is a path-coverage minimum, not a convenience.** Consider what it skips in a
regbase kernel of the canonical shape (0355): if the tensor fits one tile, `tileNum_` is 1 and the
`(i == tileNum_ - 1) ? tailTileElementNum_ : TILE_LENGTH` ternary never takes its first branch — the tail
expression is evaluated but the *multi-tile* path is not. If the element count is a multiple of the vector
length, `UpdateMask` never produces a partial mask and the masked-store path never runs. If the buffer is
32-byte aligned at every tile boundary, `LoadAlign`'s requirement (0257) is satisfied for free. If the
reduction axis fits UB, the split-load merge (0360's Pattern 2) is never taken. Four distinct code paths,
all dark, and the test is green.

**And the small shape is *chosen* for the properties that make it dark.** An agent writing a unit test
picks 256 elements of fp32 because it is easy to write a reference for by hand, easy to print, and fast.
Every one of those reasons correlates with alignment and single-tile residency. So the bias is systematic,
not accidental, and it will not be corrected by testing more small shapes.

**The three named cases attack three different mechanisms and are not interchangeable.** The non-aligned
case exercises the mask and the unaligned copy path; the long-axis case exercises multi-tile iteration,
the tail block, and accumulation drift (0397); and the aligned case is the control that says the other two
are being compared against a working baseline. An agent that adds "a bigger shape" has added one of the
three.

**The diagnostic is the part that saves the most time and is stated in one line.** "Inspect whether the
first failure starts at a tail or merge boundary" turns a list of failing indices into a hypothesis: if the
first bad index is at `k * TILE_LENGTH` the fault is at a tile boundary; if it is at the last partial tile
it is the tail; if it is scattered it is neither and 0394's stability test applies instead. That is a
free classification from data the comparison already produced, and it is the difference between debugging
the tail path and debugging the arithmetic.

**Where this rule meets the rest of this block.** 0362's tiling-entry validation is the host-side mirror —
rank, dtype, format and shape rejected at the gate — and this is the kernel-side one: the gate says which
shapes are *legal*, and this rule says which of the legal ones must be *run*. An operator whose declared
support (via `maxRank`, its dtype list, its `spec.yaml`) is wider than its tested set has advertised
behaviour it has not exercised, which `working_vs_failed_950_cases.md:62` names as "operator support
declarations drifting away from the code path" (0369).

## 3 · Ground / Source
`common_traps.md:64-78`, trap 3 in full:

> ## 3. Assuming small-shape success proves correctness
>
> Signal:
>
> - unit tests on tiny or aligned shapes pass
> - production shapes, long axes, or tails fail
>
> Why it happens:
>
> - small aligned cases hide tail handling, partial-tile masking, and scale-dependent accumulation drift
>
> Check first:
>
> - add one aligned case, one non-aligned case, and one long-axis case
> - inspect whether the first failure starts at a tail or merge boundary

Three named hidden mechanisms — tail handling, partial-tile masking, scale-dependent accumulation drift —
and the third is a *numerical* mechanism in a list otherwise about control flow. That matters: a long-axis
case is not merely a bigger version of a small one, it is where fp16 accumulation runs out (0397 records
the per-format safe lengths), so the long-axis case tests two independent things and a failure there needs
0394's stability test to tell which.

`kernel_design_patterns.md:97-107`, Pattern 6, quoted in SOURCE. Its five items are a superset of trap 3's
three: it adds compile viability and branch-specific edge cases, and it splits tail into "tail block and
tail tile" — two different loops (the block loop across cores and the tile loop within a core), which trap
3's single "tail" elides. The distinction is real and consequential: a tail block is a core with less work,
a tail tile is a partial mask, and an operator can handle one and not the other.

The closing sentence is the strongest line in either passage: "These are pattern tests, not just example
tests. They prove the route, not only the sample input." That is the claim — a test's value is the set of
paths it forces, and a case set is chosen against the route rather than against the input space.

`common_traps.md:128-143`, trap 7, quoted in SOURCE, supplies the recognition signal from the other
direction: behaviour flipping around minimum-size thresholds. Its named causes — reduction width,
alignment, tail masks, buffer limits — are four quantities this book records as disputed or unmeasured
(0209/`Q-950arch-04` for the UB limit, 0257 for alignment, 0360 for the logical unit), so an agent that
follows trap 7's advice to "check" them finds that several have no established value.

All three passages are `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

**What upstream does not supply**: any threshold. "Tiny", "small", "long axis" and "production shapes" are
all undefined, so the case set cannot be generated automatically from an operator's declared support — an
agent must choose the three shapes itself, and the choice is exactly the judgement the trap says agents get
wrong. That gap is the reason §4's Arm A derives the shapes from the *kernel's own constants* rather than
from an adjective.

This entry is one of the few in this block drawn from `pitfalls/`, whose files are predominantly
symptom→check diagnostic process. It is entered rather than carded because the claim is falsifiable in a
specific sense — it asserts that a particular test set is *insufficient*, and a demonstration of sufficiency
would overturn it — and because the tail/merge-boundary diagnostic is a procedure with a stated readout.

## 4 · Procedure
Runnable later on `950PR`. The claim is about test-set sufficiency, so the procedure measures path coverage
and the failures each case set catches.

Arm A — the case set, derived rather than guessed. For one regbase operator, read its own constants —
`TILE_LENGTH`, the vector length (0252), the block split — and generate four shapes: exactly one tile,
aligned; one tile plus one element; several tiles with a partial last tile; and a long axis exceeding the
per-format safe accumulation length (0397). Record which shapes each of the four exercises: multi-tile
iteration, partial mask, unaligned address, split-load merge.

Arm B — path coverage, measured rather than argued. Instrument the kernel (a per-path counter in GM, or a
disassembly-guided branch trace) and run each shape. Report the set of paths each shape reaches. §2 claims
the small aligned shape reaches a strict subset; the coverage table is the measurement, and it is the arm
that converts an argument into a number.

Arm C — planted-defect detection, which is what a test set is for. Plant four defects, one per hidden
mechanism: an off-by-one tail tile count; a mask that ignores the partial beat; an unaligned copy through
`LoadAlign`; an fp16 accumulator. Run the full case set against each. Report which cases catch which
defects. A case set that catches four of four is sufficient for these defects; the cells that stay empty are
the finding.

Arm D — the diagnostic. For each caught defect, record the first failing index and whether it lies at a
tile boundary, at the last partial tile, or elsewhere. Upstream's one-line diagnostic predicts the first
two are distinguishable by index alone; the arm establishes whether the mapping from index to mechanism is
actually one-to-one, or whether two mechanisms produce first failures at the same place.

Arm E — the long-axis case's two jobs. For the long-axis shape, apply 0394's stability test (50 identical
runs) to separate an accumulation-drift failure from an ordering failure. §3 notes the long-axis case tests
two independent things; without this arm a failure there is unattributed.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all shapes of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`path_coverage_by_shape` (Arm B) — per shape, the set of paths reached. Pass iff the small aligned shape's
set is a **strict subset** of the union of the others. Reported as sets, not as a percentage: a coverage
figure of "75%" says nothing about which quarter is dark, and the dark quarter is the entry's subject.

`defect_detection_matrix` (Arm C) — a 4×4 table, defect × case. Reported in full, never as a detection
rate. The empty cells are the deliverable; a rate of 12/16 would be reported by a sufficient case set and by
an insufficient one that happens to overlap differently.

`first_failure_locus` (Arm D) — per defect, three-valued: tile boundary, last partial tile, elsewhere. Pass
iff the mapping from defect to locus is injective. A collision means upstream's diagnostic cannot separate
those two mechanisms and the entry must say so.

`long_axis_failure_class` (Arm E) — for the fp16-accumulator defect, the number of distinct failing sets
over 50 runs. Expected 1 (deterministic, therefore numerical, per 0394). A moving set would mean the
long-axis shape is catching an ordering defect instead and the attribution is wrong.

The positive fixture, declared before the run: **the clean build must pass every shape in the case set.**
If it does not, the reference or the harness is wrong and every detection result is void — a defect-detection
matrix built on a failing baseline reports the baseline. And Arm C must include a **fifth, undefected**
build run against all four cases, which must produce an empty row; a case set that reports failures against
a correct kernel is over-sensitive, and its detections are not evidence of the defects. Without both, the
checker reads only "some cases failed", which cannot distinguish a working test set from a broken one — the
known blind species, and the one this entry's whole subject is an instance of.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no shape run,
no path counted, no defect planted, no die contacted. The quoted passages are re-verified file reads of the
upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that a small aligned shape reaches fewer paths,
that the three named cases catch the three named mechanisms, or that the first-failure locus identifies the
mechanism — Arms A through E are all open.

**It supplies no threshold, because upstream supplies none.** "Tiny", "small", "long axis" and "production
shapes" are undefined in every passage quoted, so the rule cannot be applied mechanically to an operator's
declared support range, and §4's Arm A derives shapes from the kernel's own constants precisely because no
adjective in the source is actionable. An agent still has to choose, which is the judgement the trap says
gets made badly.

It does not establish that the case set is *sufficient*. Three cases (or Pattern 6's five items) is a stated
minimum with no argument that it is complete; Arm C's matrix would show what it catches among four planted
defects, which is a statement about those four.

It does not establish that the long-axis case's two jobs — control flow and accumulation drift — can be
separated by any single observation. Arm E proposes 0394's stability test as the separator; whether it works
here is untested, and 0394 §7 records that the test is one-directional.

It does not establish the "tail block versus tail tile" distinction as a real difference in behaviour;
Pattern 6 names both and trap 3 names one, and no source in scope gives an operator that handles one and
fails the other.

It says nothing about how a case set relates to an operator's *declared* support — the host-side gate
(0362) and the drift between declaration and code path (0369) are the neighbouring claims, and nothing here
establishes that a passing case set covers a declared range.

BOARD is `family-claimed(unverified)`: all three passages describe regbase testing practice, none names a
board token this book recognises, and no board was contacted.
