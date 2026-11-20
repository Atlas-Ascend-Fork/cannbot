```
ID:        0357-a-narrow-dtype-route-needs-extra-register-state-even-when-it-needs-no-extra-ub
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), which states the
           pattern in three of its own files. Nothing was compiled and no register count was observed.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/regbase_buffer_partitioning.md:79-95
           — "## 4. Dtype-Sensitive Buffer Planning / For fp16 / bf16 routes, separate: / - the UB
           storage type / - the compute-register type / Typical pattern: / 1. UB keeps packed
           fp16/bf16 tiles / 2. VF loads packed narrow values into a narrow `RegTensor` / 3. VF casts
           into fp32 `RegTensor` / 4. compute happens in fp32 / 5. result is cast back to narrow
           `RegTensor` / 6. VF stores packed narrow result back to UB / This means extra **register**
           state is often required even when extra **UB** state is not."
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/regbase_kernel_dataflow_patterns.md:122-135
           — "## 5. Dtype-Split Pattern / A stable regbase pattern is to keep the outer shell mostly
           unchanged while splitting the VF body by dtype. / Typical split: / - fp32 path: direct load
           and compute / - fp16 / bf16 path: / - load packed narrow type / - unpack or cast to fp32
           register state / - compute in fp32 if needed / - cast back and pack for store"
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/regbase_programming_notes.md:66-75
           — "## 5. Half Precision Usually Implies A Wider Compute Stage … - load or unpack the narrow
           type / - promote into a wider compute representation when the math is sensitive / - keep
           summaries local in fp32 when the post-process depends on them / - only cast back once the
           stable result is ready / This is a design choice, not a cosmetic optimization."
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 fp16 kernel in which the widened compute stage uses no more physical registers than
           the fp32 path at the same tile size — i.e. the narrow and wide `RegTensor` objects share
           storage — which would make the extra register state a source-level artefact rather than a
           real cost. Observable as identical register allocation in the two disassemblies.
```

# 0357 · A narrow-dtype route needs extra register state even when it needs no extra UB

## 1 · Claim
Upstream asserts that for fp16 and bf16 routes the UB storage type and the compute-register type must
be planned separately, and gives the six-step shape: UB holds packed narrow tiles; the VF loads them
into a narrow `RegTensor`; the VF casts to an fp32 `RegTensor`; compute happens in fp32; the result is
cast back to a narrow `RegTensor`; the VF stores packed narrow values back to UB. Upstream asserts the
consequence in one sentence: extra **register** state is often required even when extra **UB** state is
not. Upstream asserts the same shape as a dtype split of the VF body with the outer shell left
unchanged, and, in a third file, as a design choice rather than a cosmetic optimisation. Not
established here: nothing was compiled and no register allocation was observed.

## 2 · The wrong branch this removes
The budget an agent computes is a UB budget. Every tiling document in this book's 0101-0169 block
derives tile sizes from UB capacity against live buffer counts, and none of them counts registers. So
when an fp16 variant of an operator is added, the natural reasoning is: fp16 is half the bytes, the
same tile fits in half the UB, therefore the fp16 path is cheaper than the fp32 path and needs no
re-planning. The first half of that is true. The conclusion is wrong, because the resource that changed
is not the one being budgeted.

The concrete shape of the error: a chain that needs three `RegTensor` objects in fp32 needs *five* in
fp16 — narrow-in, wide-working ×3, narrow-out — or six if the cast is not in-place and the store is
masked separately. The tile got smaller and the register working set got larger, in the same change,
and only one of the two appears in any budget the harness computes. 0036 makes the counting worse:
source-level `RegTensor` declarations understate physical register use when the element is wider than
32 bits, so even an agent that decides to count registers is counting the wrong thing.

The **second** branch is the placement of the cast, and it is the one with a correctness consequence
rather than a performance one. `common_traps.md:48-62` names "Promoting too late" as a high-frequency
trap: "the code upgrades precision after an unstable low-precision reduction, subtract, or nonlinear
operation already destroyed signal". Upstream's six-step pattern puts the widening at step 3, *before*
any arithmetic — that ordering is the whole point, and an agent that reads the pattern as "cast where
convenient" gets the register cost without the numerical benefit. `regbase_programming_notes.md:73`
states the exit condition symmetrically: "only cast back once the stable result is ready", i.e. the
narrowing is also placed, not incidental.

The **third** branch is the one that interacts with a mechanism this book has already recorded and that
upstream never connects. 0257 establishes that a b16 load with `DIST_UNPACK_B16` consumes only half a
vector register's worth of source bytes — 64 half values, 128 bytes — so the widening path steps 64
elements per iteration rather than 128. An agent that adopts this dtype-split pattern and computes its
loop bound from 0252's `GetVecLen()/sizeof(T)` rule gets 128 for `half` and skips half its data. The
two rules are individually correct and jointly wrong for exactly this pattern, and this is the pattern
upstream recommends for every fp16 operator.

## 3 · Ground / Source
`regbase_buffer_partitioning.md:79-95`, the pattern and its consequence:

> ## 4. Dtype-Sensitive Buffer Planning
>
> For fp16 / bf16 routes, separate:
>
> - the UB storage type
> - the compute-register type
>
> Typical pattern:
>
> 1. UB keeps packed fp16/bf16 tiles
> 2. VF loads packed narrow values into a narrow `RegTensor`
> 3. VF casts into fp32 `RegTensor`
> 4. compute happens in fp32
> 5. result is cast back to narrow `RegTensor`
> 6. VF stores packed narrow result back to UB
>
> This means extra **register** state is often required even when extra **UB** state is not.

The last sentence is the claim. Note the hedge — "often" — which upstream does not qualify further: it
gives no condition under which the extra state is *not* required, so the exception it implies is
unstated.

`regbase_kernel_dataflow_patterns.md:122-135` restates it as a structural split and adds the piece the
buffer document leaves out, which is that the *outer shell does not change*: "A stable regbase pattern
is to keep the outer shell mostly unchanged while splitting the VF body by dtype … This keeps routing
visible and avoids mixing dtype-specific casts into the host packet." So the dtype route is a
`TILING_KEY_IS` branch at layer 1 (0355) selecting a layer-3 body, and the layer-2 tile flow is shared.
That is a real design statement and it is the reason the UB budget looks unchanged: it *is* unchanged,
by construction.

`regbase_programming_notes.md:66-75` supplies the placement rules and the framing ("a design choice, not
a cosmetic optimization"), and one extra clause the other two omit: "keep summaries local in fp32 when
the post-process depends on them", which extends the widened stage past the elementwise chain into any
reduction summary the operator carries.

All three files are `upstream/skills-dev-main` — one origin (RULES.md Art. 3). Note the vocabulary slip
across them: `:87` says "casts into fp32", `:130` says "unpack or cast to fp32 register state", and
0257 establishes that for b16 the operation is an unpacking *distribution* on the load
(`DIST_UNPACK_B16`), not a separate `Cast` call. Whether the pattern's step 3 is a `Reg::Cast` or a
load distribution is not settled by any of the three files, and it matters: the distribution form folds
the widening into the load and needs no extra instruction, while the `Cast` form needs one. 0021 records
the folding as a technique from a different skill; this entry records that the pattern document does not
say which of the two it means.

`Reg::Cast` itself is one of the twenty-seven names declared in the installed headers and absent from
the VF-safe whitelist (0354) — so an agent following the whitelist to implement step 3 in its `Cast`
form is told the API is unavailable.

## 4 · Procedure
Runnable later on `950PR`. Two separable claims: the register cost, and the placement.

Arm A — the register cost, measured where it exists. Compile one elementwise chain twice for a 3510
target: an fp32 build and an fp16 build following the six-step pattern, identical in every other
respect. Read the **register allocation from the disassembly**, not from the source: count physical
vector registers live at the widest point of the VF loop. The claim is that the fp16 build uses more.
This is a compile-and-read arm and needs no die.

Arm B — the UB non-cost, which is the other half of the sentence. For the same two builds, record the
UB bytes the host tiling routine reserves and the tile size it selects. The claim predicts the fp16
build reserves the same or fewer bytes. If it reserves more, the pattern as documented is not what the
implementation does, and the sentence's contrast collapses.

Arm C — the stride collision with 0257, which is the correctness arm and the one most likely to bite.
Implement the fp16 path twice: loop stride computed as `GetVecLen()/sizeof(half)` = 128 elements, and
as 64. Run both against a host fp32 reference at a shape that is not a multiple of either. Under 0257
the 128 form silently skips half the data. Recording *how* it fails — wrong values, stale values,
partially-correct output — is the deliverable, because upstream states neither the collision nor its
symptom.

Arm D — placement, which is a numerical arm and needs real data. Build three fp16 variants of one
reduction-bearing operator: widen before the chain (the documented pattern), widen after the first
subtract, and no widening at all. Compare max absolute and max relative error against an fp64 host
reference at three input distributions, including one designed to trigger catastrophic cancellation.
The documented ordering should dominate; the amount by which it does is the first number any source in
scope offers for "promote early".

Arm E — the ambiguity in step 3. Build the widening two ways — `LoadAlign` with `DIST_UNPACK_B16`, and
a plain narrow load followed by `Reg::Cast` — and compare instruction counts in the disassembly and
duration on one die. This is what decides which operation the pattern means, and neither document says.

Device selection, for Arms C, D and E: the operator names the device index, the harness prints it back
with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and all builds of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`register_delta` (Arm A) — physical vector registers live at the widest point, fp16 build minus fp32
build. Pass iff > 0. A delta of 0 overturns the claim and would mean the narrow and wide `RegTensor`
objects share storage; that is the OVERTURN condition and it is a live outcome, not a formality.

`ub_delta` (Arm B) — reserved UB bytes, fp16 minus fp32. Pass iff ≤ 0. Reported alongside
`register_delta` and never merged with it: the whole content of upstream's sentence is that the two move
in opposite directions, and a single "resource usage" number would erase exactly the fact being tested.

`stride_128_is_wrong` (Arm C) — true iff the 128-element-stride build differs from the host reference.
Pass condition is **true**. Stated inverted on purpose: this checker is built to confirm a defect, so a
green result here means the collision is real and 0257's Arm D is corroborated; a false result would
mean `DIST_UNPACK_B16` consumes a full register after all and 0257 is wrong.

`promotion_ordering_error` (Arm D) — max relative error per variant per distribution, reported as a
table, never averaged. Averaging across distributions is how a cancellation failure disappears: the
whole point of the third distribution is that it is the only one where the variants separate.

The positive fixture, declared before the run: Arm A must include a third build — fp16 with **no**
widening, computing in half throughout — whose register count must be lower than the widened fp16
build. If it is not, the disassembly register count is not tracking the working set and every delta in
the arm is void. A second fixture for Arm D: the fp32 build must show near-zero error against the fp64
reference on all three distributions; if it does not, the reference or the generator is wrong and every
fp16 error figure is uninterpretable. Without both, the arms read only "the numbers differed", which is
the known blind species.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No build was made, no
disassembly read, no register counted, no die contacted, and no error computed. The three quoted
passages are re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that the fp16 path uses more registers, that
it uses no more UB, or that early promotion reduces error — Arms A through E are all open, and upstream
supplies **no number** for any of them.

It does not establish what step 3 of the pattern is. `Cast` and an unpacking load distribution are
different instructions with different costs, upstream's three files use both vocabularies, and Arm E is
what would decide. Until then, an agent implementing the pattern is choosing without guidance.

It does not establish the hedge. "Extra register state is **often** required" names an exception and
never states it, so the conditions under which the pattern does not cost extra registers are unknown
and this entry does not invent them.

It does not establish anything about bf16 separately from fp16. Both are named throughout and neither is
distinguished; bf16's wider exponent and narrower mantissa make the error arm's answers potentially
different, and no source in scope separates them.

The **collision with 0252's lane-count rule** described in §2 is derived here from 0257 and is stated by
no upstream source. Arm C is what would establish it, and until then it is reasoning about two
independently harvested rules, not a documented interaction.

It says nothing about int8/uint8 routes, which upstream's neighbouring alignment rules cover with a
different distribution pair (`DIST_UNPACK4_B8` / `DIST_PACK4_B32`, 0257 §7) and which were not read.

BOARD is `family-claimed(unverified)`: none of the three files names a board token this book recognises
and no board was contacted.
