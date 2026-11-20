```
ID:        0370-mixing-the-dag-abstraction-with-raw-register-primitives-is-the-named-high-probability-950-failure
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), stated as distilled
           project experience. Upstream calls it "one of the most expensive 950 mistakes" and names no
           case, no diagnostic and no frequency. Nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/working_vs_failed_950_cases.md:49-57
           — "## 3. Mixing DAG And Regbase Is A High-Probability Failure Mode / One of the most
           expensive 950 mistakes is hybrid code that: / - borrows DAG structure / - then injects raw
           MicroAPI assumptions inside it / - or assumes a Vec wrapper and a MicroAPI primitive are
           interchangeable / This produces code that is neither a clean DAG path nor a clean regbase
           path. The result is usually API mismatch, configuration mismatch, or both."
SOURCE:    same file:38-47 — "## 2. Regbase Works Best When You Commit To It / Successful regbase paths
           usually look like this: / - explicit class-based kernel organization / - direct regbase
           compute chain / - deliberate buffer and dtype handling / - no attempt to hide imperative
           logic under a half-DAG abstraction / The common success signal is commitment. The
           implementation chooses regbase and then stays regbase."
SOURCE:    same file:27-36 — "## 1. Simple DAG Routes Succeed When The Problem Really Is Simple …
           The lesson is not “always use DAG”. The lesson is that DAG works well when the operator
           shape really matches it."
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 operator that borrows DAG structure, injects `Reg`/`MicroAPI` primitives inside it,
           and is correct and competitive — measured against clean-DAG and clean-regbase
           implementations of the same operator at the same shapes. The "high-probability failure"
           framing would then be an authoring preference rather than a mechanism.
```

# 0370 · Mixing the DAG abstraction with raw register primitives is the named high-probability 950 failure

## 1 · Claim
Upstream asserts that hybrid code is one of the most expensive 950 mistakes, and names its three shapes:
borrowing DAG structure and then injecting raw `MicroAPI` assumptions inside it, or assuming that a `Vec`
wrapper and a `MicroAPI` primitive are interchangeable. Upstream asserts the outcome — code that is
neither a clean DAG path nor a clean regbase path — and the two consequence classes it usually produces:
API mismatch, configuration mismatch, or both. Upstream asserts the positive form: successful regbase
paths show explicit class-based kernel organisation, a direct regbase compute chain, deliberate buffer
and dtype handling, and no attempt to hide imperative logic under a half-DAG abstraction, with the common
success signal being **commitment** — the implementation chooses regbase and stays regbase. Upstream
asserts symmetrically that DAG routes succeed when the operator shape really matches them, and that the
lesson is not "always use DAG". Not established here: nothing was compiled, and upstream names no case,
no diagnostic and no frequency.

## 2 · The wrong branch this removes
Hybridisation is not a decision anybody makes. It is what happens when two correct impulses meet.

The first impulse is reuse: a DAG-based implementation of a similar operator exists, it is shorter, and
its structure is obviously borrowable. The second is capability: the operator needs one thing the DAG
abstraction does not express — a fused multiply-add, a mask-driven select, a widening load — and the
`Reg`/`MicroAPI` primitive that expresses it is right there, in the same namespace family the whitelist
lists. Neither impulse is wrong. Acting on both in one file produces the hybrid, and no single edit in
that sequence looks like the mistake.

The third shape upstream names — assuming a `Vec` wrapper and a `MicroAPI` primitive are interchangeable
— is the one with a mechanism this book has already established. 0250 records that a kernel-side API and
its VF-side namesake are not interchangeable, over thirteen names the whitelist lists in *both* tables:
`Add`, `Sub`, `Mul`, `Max`, `Min`, `And`, `Or`, `Xor`, `Adds`, `Muls`, `Compare`, `Select`, `Move`. Those
thirteen are exactly the names a hybrid reaches for, because they are the ones that appear to exist on
both sides. 0351 adds a fourteenth that the whitelist does not dual-list (`DataCopy`) and 0354 adds
twenty-seven more that exist in headers and in no table. So the interchangeability assumption has a large
surface and no gate over it.

The failure classes upstream names are worth separating because they surface at different times.

**API mismatch** is the loud half — a kernel-side signature called with VF-side arguments, or a
`LocalTensor` where a `RegTensor` is expected — and it usually fails to compile. When it compiles anyway
(same name, compatible-looking arguments) it is 0250's silent case.

**Configuration mismatch** is the quiet half, and it is where this entry meets 0369. A hybrid route is a
route nobody enumerated: the TilingKey branches were written for the DAG shape, the `simplified_key.ini`
was generated for it, and the injected regbase path is reachable only under conditions the key set does
not encode. The result is a route that exists in source and not in the compiled kernel set — which
presents as the silent no-op 0369 §2 describes, not as an API error. That is why upstream lists the two
consequences together: they are one defect observed at two layers.

The **counter-branch** matters as much as the branch, and upstream is careful about it: `:36` says the
lesson is not "always use DAG", and `:27-36` says DAG works when the operator shape really matches it.
An agent that reads this entry as "avoid DAG" has taken a claim about *mixing* and turned it into a claim
about one of the things mixed. The claim is about commitment, and it is symmetric.

What upstream does not say, and what an agent most needs: **where the boundary is**. If a regbase kernel
may keep `TPipe`, `TQue` and `LocalTensor` in its outer shell without leaving the regbase path — which
0355 records upstream asserting, from a different file — then some structure-borrowing is legitimate and
some is hybridisation, and no source in scope draws the line. 0355's criterion (*where does the actual
math happen*) is the closest thing to one, and it is stated in `dev-experience/regbase_programming_notes.md`
rather than here.

## 3 · Ground / Source
The failure, `working_vs_failed_950_cases.md:49-57`:

> ## 3. Mixing DAG And Regbase Is A High-Probability Failure Mode
>
> One of the most expensive 950 mistakes is hybrid code that:
>
> - borrows DAG structure
> - then injects raw MicroAPI assumptions inside it
> - or assumes a Vec wrapper and a MicroAPI primitive are interchangeable
>
> This produces code that is neither a clean DAG path nor a clean regbase path. The result is usually API
> mismatch, configuration mismatch, or both.

"High-probability", "most expensive", "usually" — three unquantified terms in nine lines, and no case
reference. The file's own header (`:25`) says it distils `knowledge_cards/kernel_code_patterns_950.md`
and that "The goal is not to catalog every operator, but to show what repeatedly separates stable 950
implementations from broken ones", so the underlying case population is outside this harvest's scope and
this entry cannot see it.

The positive form, `:38-47`, quoted in SOURCE, and the symmetric caution, `:27-36`:

> Successful elementwise operators on `ascend950` tend to share these traits:
>
> - the operator is genuinely short and local
> - the route stays inside the DAG abstraction cleanly
> - dtype handling is explicit
> - tiling keys, config, and kernel branches line up
>
> The lesson is not “always use DAG”. The lesson is that DAG works well when the operator shape really
> matches it.

Note the fourth trait — "tiling keys, config, and kernel branches line up" — which is 0369's three-part
contract stated as a success condition rather than a failure mode, in a different file of the same skill.

The review habit at `:70-78` turns the claim into two questions an agent can ask: "Did we keep one
execution family all the way through?" and "Is any 'framework mixing' happening under a different name?"
The second is the more useful, because hybridisation rarely announces itself — it appears as a helper, a
wrapper, or a "just this one primitive" exception.

`MicroAPI` is `Reg` (0244, corroborated against the installed `kernel_macros.h:136`), so "raw MicroAPI
assumptions" and "regbase primitives" name one surface under two spellings. That matters for §4: a
detector looking for `MicroAPI::` misses every file that spells it `Reg::`, and 0244 establishes that both
spellings are in circulation in exactly this material.

Neither the DAG abstraction nor the `Vec` wrapper is defined anywhere in this harvest's scope. Upstream
names both as known things and this entry does not reconstruct them; that absence is the main limit on
§4 and is recorded in §7.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on `950PR`. The claim is comparative, so the procedure needs all three implementations of
one operator, not a hybrid in isolation.

Arm A — the three-way build. Choose one operator that both abstractions can express (a short fused
elementwise chain). Implement it three times: clean DAG, clean regbase, and a hybrid that borrows the DAG
structure and injects a `Reg::` primitive for the fused step. Compile all three for a 3510 target.
Record, per implementation: does it compile; what diagnostics appear; how many `TILING_KEY_IS` branches
exist and whether each is reachable. Compilation alone answers upstream's "API mismatch" half.

Arm B — the configuration half, which is the quiet one. For all three, run 0369's three-way key diff
(host generation, kernel dispatch, binary metadata). §2 predicts the hybrid's injected path is present in
source and absent from the compiled key set. If the diff is clean for the hybrid too, upstream's
"configuration mismatch" consequence has no mechanism here and the claim narrows to API mismatch alone.

Arm C — correctness and cost, on a die. Run all three at three shapes with identical inputs on one die in
one session, comparing against a host reference. Record correctness and duration. The OVERTURN is a
hybrid that is correct and competitive; this arm is what would produce it. Note that a hybrid being
*slower* is not the claim — upstream says it produces mismatches, not slow code — so duration is reported
and not gated.

Arm D — the interchangeability shape, isolated. For each of the thirteen dual-listed names (0250), write
the kernel-side form inside a `__VEC_SCOPE__` and the VF-side form outside one, and record for each
whether it compiles and whether the diagnostic names the reason. This is `Q-950arch-29` and it is the
arm that turns "assumes a Vec wrapper and a MicroAPI primitive are interchangeable" from a warning into a
per-name table. No device needed.

Arm E — the detector, and its blind spot. Write a hybrid detector: a file that contains both DAG
constructs and `Reg::`/`MicroAPI::` calls in the same compute path. Run it over the upstream tree and over
Arm A's three builds. Then run it again searching only for `MicroAPI::`. The difference between the two
runs is the size of the spelling blind spot 0244 predicts, and it is the reason a naive detector
under-reports.

Device selection, for Arm C: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all three builds run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`hybrid_compiles` (Arm A) — reported, not gated. Both outcomes are informative: a hybrid that fails to
compile is the benign case, and the claim is about the one that does not.

`hybrid_key_gap` (Arm B) — true iff the hybrid's three-way key diff shows a source path absent from the
compiled key set, while both clean builds show none. Both clauses required: a diff that is dirty for all
three is measuring the harness, not the hybrid.

`hybrid_correct` and `hybrid_duration_ratio` (Arm C) — reported separately, per shape, never averaged
across shapes. Correctness is the verdict; duration is context. Merging them would let a correct-but-slow
hybrid read as a failure, which is not upstream's claim.

`dual_listed_confusion` (Arm D) — a thirteen-row table: name, kernel-side-in-VF result, VF-side-outside
result, and whether the diagnostic named the reason. The third column is the deliverable — a name that
compiles in the wrong scope is a hole the toolchain is not closing, and it is invisible in any pass count.

`detector_spelling_gap` (Arm E) — two integers: hits searching both spellings, hits searching
`MicroAPI::` only. Reported.

The positive fixture, declared before the run: Arm A must include a **deliberately broken** fourth build
in which a kernel-side `Add` over `LocalTensor` is called inside `__VEC_SCOPE__`, and the compiler must
reject it. If it does not, the toolchain is not enforcing the scope distinction at all, and every "the
hybrid compiled" result is uninformative because everything compiles. And Arm E's detector must be given
one file that is unambiguously clean regbase and one that is unambiguously clean DAG, and must flag
neither; a detector that flags clean files is reporting co-occurrence, not hybridisation. Without both,
the checker reads only "the hybrid built and something was flagged", which is the known blind species.

Process exit codes are not the verdict: Arms A and D expect compile failures as informative outcomes.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No operator was implemented three
ways, no build compiled, no key diff run, no name tested in the wrong scope, no die contacted. The quoted
passages are re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that hybrid code fails more often, that it fails
at all, or that either named consequence follows — Arms A through E are all open, and upstream supplies
**no case, no diagnostic and no frequency**.

**It does not define either abstraction.** Neither "the DAG abstraction" nor "a Vec wrapper" is defined
anywhere in this harvest's scope; upstream names both as known things. So the boundary between legitimate
structure reuse and hybridisation is undrawn here, and §4's Arm A requires reconstructing a DAG
implementation from material this harvest does not have. That is the largest limit on the procedure and it
is the reason this entry is a trap rather than a boundary: it names a hazard whose edge is unlocated.

It does not reconcile with 0355. That entry records upstream asserting, from a different file, that a
regbase kernel may keep `TPipe`, `TQue`, `GlobalTensor` and `LocalTensor` in its outer shell without
leaving the regbase path. Some structure-borrowing is therefore legitimate. Which borrowings are
hybridisation is stated by no source, and 0355's *where does the actual math happen* criterion is the
nearest available test — untested, in Arm A of that entry.

It does not establish the frequency framing. "High-probability", "most expensive" and "usually" are
upstream's terms over a case population outside this harvest's scope, and no arm here would verify them —
Arm C would compare three implementations of one operator, which is a mechanism test, not a frequency
measurement.

It says nothing about the thirteen dual-listed names beyond citing 0250: their per-name behaviour is
`Q-950arch-29` and Arm D is a proposal, not a result.

BOARD is `family-claimed(unverified)`: the file describes `ascend950` work in prose, names no board token
this book recognises, and no board was contacted.
