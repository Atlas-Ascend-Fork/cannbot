```
ID:        0358-masks-and-load-store-distributions-are-lane-and-layout-controls-and-never-synchronisation
LABEL:     boundary
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Upstream states the
           prohibition and names no enforcement mechanism and no symptom for violating it. Nothing was
           compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/regbase_sync_patterns.md:52-66
           — "## 3. VF-Level “Synchronization” Is Usually Not Event Sync / Inside `__VEC_SCOPE__`: /
           - `MaskReg` controls active lanes / - `LoadDist` controls how UB data is loaded into
           registers / - `StoreDist` controls how register results are written back / None of those
           are event synchronization primitives. / That means: / - do not describe `MaskReg` as a sync
           mechanism / - do not use `LoadDist` / `StoreDist` as if they were barriers / - do not add
           `PipeBarrier` just because a VF loop has multiple instructions"
SOURCE:    same file:27-35 — "## 1. Default Rule / Start with the lightest synchronization model that
           matches the layer you are working in. / In many regbase operators: / - UB stage handoff is
           handled by queue lifecycle or straightforward stage ordering / - VF internals need lane
           control, not event synchronization / - explicit `SetFlag` / `WaitFlag` only appear in more
           advanced overlap or ping-pong designs"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 VF in which changing only the `MaskReg` value, the `LoadDist`, or the `StoreDist`
           changes the ORDER in which two register instructions become visible to each other — i.e.
           one of the three does carry ordering semantics; or a VF whose multi-instruction loop
           produces wrong results without a `PipeBarrier` between its instructions, which would make
           the third prohibition false.
```

# 0358 · Masks and load/store distributions are lane and layout controls, and never synchronisation

## 1 · Claim
Upstream asserts that inside `__VEC_SCOPE__` three mechanisms are commonly mistaken for
synchronisation and are not: `MaskReg` controls which lanes are active, `LoadDist` controls how UB data
is distributed into registers on load, and `StoreDist` controls how register results are written back.
Upstream asserts that none of the three is an event-synchronisation primitive, and states three
prohibitions: do not describe `MaskReg` as a sync mechanism, do not use `LoadDist`/`StoreDist` as if
they were barriers, and do not add a `PipeBarrier` merely because a VF loop contains several
instructions. Upstream asserts a layering default around this: VF internals need lane control rather
than event synchronisation, UB stage handoff is queue lifecycle or stage ordering, and explicit
`SetFlag`/`WaitFlag` appear only in advanced overlap designs. Not established here: nothing was
compiled, and upstream names no enforcement mechanism and no symptom for any of the three
prohibitions.

## 2 · The wrong branch this removes
This entry is about a *category error*, which is a harder thing to catch than a wrong value, because
the code that expresses it compiles and usually works.

The error's shape: an agent debugging a non-deterministic VF result reaches for the mechanisms it can
see. Inside `__VEC_SCOPE__` the only knobs visible are the mask and the two distributions. So it
narrows the mask, or switches `DIST_NORM` for something else, the symptom moves — because the data
being touched changed — and the agent records a synchronisation fix that fixed nothing. The next shape
brings it back. This is the loop `common_traps.md:96-111` describes as "Chasing the final output
instead of the first divergence", specialised to the one scope where the usual instruments are absent.

The **third prohibition** is the one with a cost attached, and it points the other way. Adding a
`PipeBarrier` inside a VF loop because the loop has several instructions is a reflex imported from
kernel-side pipe reasoning, where consecutive `PIPE_V` operations on overlapping buffers genuinely need
one. It is not free: a barrier in the hot loop serialises what the VF exists to pipeline. And it is
*unfalsifiable from the inside* — the kernel gets slower and stays correct, so nothing ever flags it.
This is upstream's version of an over-application error, and it is the direction `Q-950arch-19` warns
must also be exercised: the reason 0258's `LocalMemBar` question insists on testing both directions is
that the over-applied barrier has no detector.

**What this entry does not license.** There *are* ordering requirements inside and around a VF, and
denying that would be worse than the error being corrected. 0258 establishes `LocalMemBar` as needed
when consecutive iterations touch the same address; 0028 records a kept store-to-load round trip
without `LocalMemBar` returning `maxAbsErr = inf`; 0261 establishes that overlapping MTE destination
addresses need a manual `PipeBarrier` because the hardware does not serialise them; 0259 records four
upstream passages giving three answers on whether a `PipeBarrier<PIPE_V>` is needed *after* a VF. So
the correct reading of upstream's third prohibition is narrow: not "a VF needs no barriers", but "the
number of instructions in the loop is not the criterion". The criterion is address overlap, and it lives
in a different file.

That narrowness is exactly what makes the prohibition dangerous to quote out of context. An agent that
takes "do not add `PipeBarrier` just because a VF loop has multiple instructions" as licence to remove
barriers will remove the one 0261 requires, and the failure is a silent wrong answer rather than a
compile error.

## 3 · Ground / Source
`regbase_sync_patterns.md:52-66`, the section in full:

> ## 3. VF-Level “Synchronization” Is Usually Not Event Sync
>
> Inside `__VEC_SCOPE__`:
>
> - `MaskReg` controls active lanes
> - `LoadDist` controls how UB data is loaded into registers
> - `StoreDist` controls how register results are written back
>
> None of those are event synchronization primitives.
>
> That means:
>
> - do not describe `MaskReg` as a sync mechanism
> - do not use `LoadDist` / `StoreDist` as if they were barriers
> - do not add `PipeBarrier` just because a VF loop has multiple instructions

Note the hedge in the heading — "Usually Not" — against the flat "None of those are" three lines below.
The heading admits an exception the body denies. Neither states what the exception would be, and this
entry follows the body because it is the specific statement; the discrepancy is recorded rather than
resolved.

The layering it sits inside, `:27-35`, and the decision path at `:100-106`:

> 1. Ask whether the issue is local stage readiness, VF lane control, explicit overlap, or cross-core
>    coordination.
> 2. For local stage readiness, start from queue lifecycle or stable stage ordering.
> 3. For VF internals, use `MaskReg` and correct `LoadDist` / `StoreDist` semantics, not barriers.
> 4. For explicit overlap, verify an existing regbase reference before introducing `SetFlag` / `WaitFlag`.
> 5. For cross-core logic, only then consider cross-core flags.

That is a four-way partition of synchronisation concerns onto the three-layer kernel structure (0355),
and it is the useful part: it tells a debugging agent *which layer to look at first* given a symptom
class. What it does not do is give any of the four a test.

What upstream does not supply anywhere in this file: a symptom. There is no statement of what happens
when `MaskReg` is used as if it ordered anything, what a redundant in-loop `PipeBarrier` costs, or how
to tell a lane-control bug from an ordering bug from the outside. Both are unfalsifiable as written,
which is what makes §4's arms worth running rather than obvious.

The file also omits `LocalMemBar` entirely — the one genuinely VF-internal ordering primitive, which the
whitelist lists in the same row as `MaskReg`, `CreateMask` and `UpdateMask`
(`regbase_api_whitelist.md:81`). So the section that says "VF internals need lane control, not event
synchronization" is silent about the VF-internal barrier that does exist. 0258 carries it. That silence
is the strongest reason to read the third prohibition narrowly.

## 4 · Procedure
Runnable later on `950PR`. The claim is a negative — three mechanisms do not carry ordering — and a
negative needs a probe that would have detected the positive.

Arm A — mask independence. Build one VF whose loop has a genuine intra-loop dependency across
iterations (iteration *i* reads the UB address iteration *i−1* wrote, per 0258's shape) and run it at
four `MaskReg` values covering all lanes, half, one, and none. If `MaskReg` carried ordering, the
failure would appear or disappear with the mask. Prediction: the failure tracks the *addresses touched*
and not the mask width, i.e. the full-lane and half-lane runs both fail while a mask that stops the
overlap does not — and the distinction between those two explanations is what the arm must report, not
merely whether it failed.

Arm B — distribution independence. Same kernel, mask fixed, sweeping `LoadDist` over `DIST_NORM` and
`DIST_UNPACK_B16` at a `half` dtype. If the distributions carried barrier semantics, one of them would
fix the dependency. Prediction: neither does, and the outputs differ only in the widening (0257).

Arm C — the third prohibition, which is a cost measurement rather than a correctness one. One VF loop
with several instructions and **no** address overlap, built with and without a `PipeBarrier<PIPE_V>`
inside the loop. Identical inputs, one die, one session, three tile sizes. Compare outputs bit-for-bit
and durations. Prediction: identical output, slower with the barrier. The size of the slowdown is the
first number any source in scope offers for the over-application error, and it is what makes the
prohibition actionable rather than stylistic.

Arm D — the positive control that makes A through C mean anything: the same probe with a genuine
ordering fix. Take Arm A's dependent kernel and add `LocalMemBar` per 0258. It must become correct. If
it does not, the harness's dependency is not a real ordering dependency and every negative result in
Arms A and B is a negative about nothing.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and all builds of one comparison run on one named die in one session. Arm A's
failing builds are expected to produce wrong values rather than hang, but a watchdog is declared anyway.

## 5 · Checker — acceptance declared before the run
`mask_changes_ordering` (Arm A) — true iff any mask value makes the dependent kernel correct *without*
removing the address overlap. Pass condition is **false**. Stated inverted deliberately: the entry
claims a negative, so the checker must be able to report the positive, and the "without removing the
overlap" clause is what stops a narrowed mask from being mistaken for a barrier.

`dist_changes_ordering` (Arm B) — same shape, same pass condition, reported separately from Arm A. Not
merged: `MaskReg` and the distributions are different mechanisms and upstream prohibits them for
different reasons, so one aggregate verdict would let a positive in one hide behind a negative in the
other.

`redundant_barrier_cost` (Arm C) — duration ratio, barrier build over no-barrier build, per tile size,
never averaged. Reported, not gated; upstream states no cost, so there is no value to pass against and
the number is the deliverable. A ratio of 1.00 at every tile size would mean the barrier is free and
the third prohibition is stylistic — a live outcome, named now.

The positive fixture, declared before the run: **Arm D is the fixture.** The `LocalMemBar` build must
turn Arm A's failing kernel correct. If it does not, the probe has no ordering dependency in it,
`mask_changes_ordering = false` means only "nothing changed anything", and the whole negative result is
void. A checker that can only observe "the mask made no difference" cannot distinguish a mask with no
ordering semantics from a test with no ordering to order — the known blind species, in its purest form,
which is why the control is the first thing declared rather than an afterthought.

A second fixture for Arm C: the bit-comparison must be shown to be sensitive, by including a third build
whose mask differs, which **must** produce different output. Without it, "identical output" is
indistinguishable from "the comparison is not reading the buffer".

Process exit codes are not the verdict for any arm: Arm A expects wrong values from a process that exits
zero.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No VF was compiled, no mask
swept, no barrier inserted or removed, no die contacted, and no duration recorded. The quoted passages
are re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that `MaskReg`, `LoadDist` or `StoreDist` lack
ordering semantics — it records that upstream says so and names Arms A and B as what would test it. It
does not establish that a redundant in-loop `PipeBarrier` costs anything; Arm C is open and upstream
states no cost.

It does **not** license removing barriers. Three separately harvested claims establish that ordering
requirements exist in and around a VF — 0258 (`LocalMemBar` when consecutive iterations touch the same
address), 0261 (a manual `PipeBarrier` for overlapping MTE destinations), 0028 (a kept round trip
without `LocalMemBar` returning `inf`) — and 0259 records that upstream gives three different answers
about a `PipeBarrier<PIPE_V>` after a VF. The prohibition harvested here is narrow: instruction count is
not the criterion. Any wider reading is this entry being misused.

It does not resolve the file's internal hedge: the heading says VF-level synchronisation is "Usually
Not" event sync and the body says "None of those are". The exception the heading admits is unstated and
this entry does not invent one.

It says nothing about `LocalMemBar`, which this file omits entirely despite it being the VF-internal
ordering primitive the whitelist lists beside `MaskReg`. That omission is recorded in §3 as a reason for
the narrow reading and is not itself a claim about the primitive.

It says nothing about the correctness of the four-way layering at `:100-106` beyond quoting it: no arm
tests whether "which layer" is decidable from a symptom, and `Q-950arch-19`'s warning applies — resolving
a VF-internal question with kernel-side pipe evidence, or the reverse, is a live hazard.

BOARD is `family-claimed(unverified)`: the file names no board token this book recognises and no board
was contacted.
