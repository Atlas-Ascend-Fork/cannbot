```
ID:        0359-explicit-event-flags-belong-to-overlap-designs-and-cross-core-flags-to-cross-core-dependencies
LABEL:     boundary
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), stated in two of its
           own files. Upstream names no symptom for either misuse and no threshold for "advanced".
           Nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/regbase_sync_patterns.md:68-87
           — "## 4. Explicit Event Flags Belong To Advanced Overlap Patterns / Use `SetFlag` /
           `WaitFlag` when the design truly overlaps movement and compute manually and the reference
           implementation already uses that pattern. / Representative pattern: /
           ```cpp / SetFlag<HardEvent::V_MTE2>(pingPongID); / WaitFlag<HardEvent::V_MTE2>(pingPongID);
           / SetFlag<HardEvent::MTE2_V>(pingPongID); / WaitFlag<HardEvent::MTE2_V>(pingPongID); / ```
           / … Do not import this pattern into a light unary or short fused chain unless the operator
           really needs it."
SOURCE:    same file:89-98 — "## 5. Cross-Core Flags Are A Separate Layer / `CrossCoreSetFlag` and
           `CrossCoreWaitFlag` belong to true inter-core coordination. / Use them only when: / - one
           core depends on another core's progress / - the kernel design explicitly spans cross-core
           producer/consumer relationships / Do not use them to patch a local UB ordering issue."
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/regbase_kernel_case_notes.md:71-85
           — "## Case 3: Advanced Explicit Sync … What this case teaches: / - explicit `SetFlag` /
           `WaitFlag` belongs to advanced overlap scenarios, not to every regbase operator / - the
           moment you orchestrate multiple UB slices and ping-pong events manually, the sync model
           becomes part of the design itself"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a light unary regbase operator on a 950 board that is measurably faster or measurably more
           correct with an explicit `SetFlag`/`WaitFlag` pair than without one — the "advanced only"
           scoping would then be a default rather than a boundary; or a local UB ordering problem that
           `CrossCoreWaitFlag` actually fixes, which would make the cross-core prohibition advice
           rather than a layer statement.
```

# 0359 · Explicit event flags belong to overlap designs, and cross-core flags to cross-core dependencies

## 1 · Claim
Upstream asserts that explicit `SetFlag`/`WaitFlag` pairs are for designs that manually overlap data
movement and compute, and gives the representative form as a ping-pong-identified pair per direction
(`V_MTE2` and `MTE2_V`, each with a `pingPongID`). Upstream asserts two conditions on using them: the
design truly overlaps movement and compute manually, **and** an existing reference implementation
already uses that pattern. Upstream asserts they must not be imported into a light unary or short fused
chain unless the operator really needs it. Upstream asserts separately that `CrossCoreSetFlag` and
`CrossCoreWaitFlag` are a different layer, for one core depending on another core's progress, and must
not be used to patch a local UB ordering issue. Upstream asserts, in a third file, that once multiple UB
slices and ping-pong events are orchestrated manually the synchronisation model becomes part of the
design rather than an implementation detail. Not established here: nothing was compiled, and upstream
gives no symptom for either misuse and no threshold for "advanced".

## 2 · The wrong branch this removes
Both prohibitions guard against the same reflex — *reach for the strongest available primitive when the
output is wrong* — and both misuses are silent.

**Importing flags into a simple operator.** A unary elementwise kernel with a `CopyIn → Compute →
CopyOut` loop already has ordering from the queue lifecycle: `EnQue` publishes the tile, `DeQue` claims
it (`:37-51`). Adding a `SetFlag<HardEvent::MTE2_V>` / `WaitFlag` pair around the same handoff is not
wrong in the sense of producing wrong answers — it produces the same answers, more slowly, and adds a
resource the operator now has to manage. That resource is not free: 0262 establishes that event IDs are
pooled per `HardEvent` type with eight slots and that `FetchEventID` can return the same ID twice, so a
kernel that acquires flags it does not need is drawing from a pool that a *later* legitimate use will
find exhausted or aliased. The added pair is invisible in the output and visible only in a failure two
changes later, in a different part of the kernel.

The second condition is the one agents skip. Upstream requires not just "the design overlaps" but "the
reference implementation already uses that pattern" — an evidence condition, not a design one. It is
there because the correct event *direction* is not derivable from first principles: `V_MTE2` and
`MTE2_V` are opposite, and which one guards which hazard depends on which side is the producer at that
point in the loop. 0064 records the same reversal in a different setting (the sync direction reverses
with the order of compute and communication). An agent that reasons its way to a direction has a 50%
chance and a symptom — an intermittent wrong tile — that looks like precision drift
(`common_traps.md:145-159`).

**Cross-core flags as a local fix.** This is the sharper one. A local UB ordering bug and a cross-core
race produce the same surface symptom: values that are partially stale, changing between runs.
`CrossCoreWaitFlag` is reachable, sounds stronger, and — critically — *may make the symptom go away*,
because it introduces a delay long enough for the local hazard to resolve by accident. The agent
records a fix, ships a kernel that pays a cross-core synchronisation cost on every core for a local
problem, and the underlying hazard is still there for the next shape. Upstream's prohibition is
therefore not about tidiness; it is about a repair that appears to work.

The third branch is the one upstream states most weakly and matters most for generated code: "the sync
model becomes part of the design itself". A harness that adds a ping-pong pair as a local edit has
changed the kernel's contract without changing its design document, and every later reviewer reads a
design that no longer describes the code.

## 3 · Ground / Source
`regbase_sync_patterns.md:68-87`, in full:

> ## 4. Explicit Event Flags Belong To Advanced Overlap Patterns
>
> Use `SetFlag` / `WaitFlag` when the design truly overlaps movement and compute manually and the
> reference implementation already uses that pattern.
>
> Representative pattern:
>
> ```cpp
> SetFlag<HardEvent::V_MTE2>(pingPongID);
> WaitFlag<HardEvent::V_MTE2>(pingPongID);
> SetFlag<HardEvent::MTE2_V>(pingPongID);
> WaitFlag<HardEvent::MTE2_V>(pingPongID);
> ```
>
> This style appears in advanced transformer kernels where multiple UB slices, ping-pong buffers, and
> MTE/vector overlap are orchestrated explicitly.
>
> Reference shape:
>
> - a multi-slice or ping-pong implementation that already proves explicit overlap is required
>
> Do not import this pattern into a light unary or short fused chain unless the operator really needs it.

Two things about that code block are worth stating because they are easy to misread. It shows four
calls in sequence, which is not a runnable ordering — a `SetFlag` immediately followed by its own
`WaitFlag` waits on a flag the same thread just set. It is a *catalogue* of the four calls a ping-pong
loop uses, not a loop body, and an agent that copies it verbatim gets a kernel that synchronises with
itself. Upstream does not say so. And the `pingPongID` is the same in all four, which in a real
ping-pong loop it would not be — the whole point of the identifier is that it alternates.

The layer statement, `:89-98`:

> ## 5. Cross-Core Flags Are A Separate Layer
>
> `CrossCoreSetFlag` and `CrossCoreWaitFlag` belong to true inter-core coordination.
>
> Use them only when:
>
> - one core depends on another core's progress
> - the kernel design explicitly spans cross-core producer/consumer relationships
>
> Do not use them to patch a local UB ordering issue.

and the case note, `regbase_kernel_case_notes.md:79-85`:

> - explicit `SetFlag` / `WaitFlag` belongs to advanced overlap scenarios, not to every regbase operator
> - the moment you orchestrate multiple UB slices and ping-pong events manually, the sync model becomes
>   part of the design itself
>
> Why this matters:
>
> - many new regbase kernels do not need this complexity
> - reading one advanced case helps you recognize when not to over-engineer a small operator

All three passages are `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

What upstream does not supply: any threshold. "Advanced", "light unary", "short fused chain" and "really
needs it" are all undefined, so the rule as written cannot be applied to a borderline operator, which is
where it would be useful. There is also no symptom for the over-application case, in either direction.

The neighbouring facts this rests on and does not restate: 0262 (event IDs pooled per `HardEvent` type,
eight slots, `FetchEventID` can repeat), 0060 (a `CrossCoreWaitFlag` on MTE2 inflates the overlap ratio
and a 0.1 gap declares the measurement polluted — an independent record that cross-core flags have a
measurable cost), 0042 (prefetch the next tile into the other buffer while this one computes — the
legitimate ping-pong case), 0355 (the layer partition this section is organised on).

## 4 · Procedure
Runnable later on `950PR`. Two prohibitions, two arm groups, and a control that is the point of both.

Arm A — the cost of an unnecessary pair. One light unary operator built twice: queue lifecycle only, and
the same kernel with a `SetFlag<HardEvent::MTE2_V>`/`WaitFlag` pair added around the existing handoff.
Identical inputs, one die, one session, three tile sizes. Compare outputs bit-for-bit and durations.
Prediction: identical output, measurably slower with the pair. If the durations are identical, the
prohibition is stylistic and the delivered skill should say so rather than warning about it.

Arm B — the resource, which is the cost Arm A cannot see. Build a kernel that acquires event IDs for
several unnecessary pairs and then, in a later phase, needs a legitimate one. Record whether
`FetchEventID` returns a distinct ID and whether the legitimate pair still works (0262's hazard). This is
the arm that tests §2's claim that unnecessary flags are drawn from a shared pool; it needs no timing.

Arm C — the direction, which is the correctness half. Take a genuine ping-pong overlap kernel and build
it three ways: correct directions, the two event directions swapped, and no flags at all. Run each 50
times at a shape large enough to have real overlap. Record for each: how many runs differ from a host
reference, and *which elements* differ. Prediction: the swapped build fails intermittently and the
no-flag build fails more often. The per-run variability is the readout — a build that fails 3 times in
50 is the one that ships.

Arm D — the cross-core misuse, and whether it appears to work. Construct a genuine *local* UB ordering
hazard (a kept store-to-load round trip without `LocalMemBar`, per 0028) and build three variants: the
hazard alone, the hazard plus `CrossCoreSetFlag`/`CrossCoreWaitFlag`, and the hazard plus the correct
`LocalMemBar`. Run each 50 times. §2 claims the middle variant may *appear* to fix it. If it does, that
is the finding and it is the single most useful sentence this entry can hand a debugging agent; if it
does not, the prohibition is about cost rather than about a misleading repair, which is a weaker and
still worth-knowing claim.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session. Arms C and D have
missing-wait variants that can deadlock: a watchdog timeout and die release are declared before the run,
and an un-timed arm is not permitted on a shared machine.

## 5 · Checker — acceptance declared before the run
`redundant_pair_cost` (Arm A) — duration ratio, flagged build over unflagged, per tile size, never
averaged. Reported, not gated: upstream states no cost. A ratio of 1.00 at every tile size is a live
outcome and would demote the prohibition to style.

`event_pool_exhausted` (Arm B) — true iff the legitimate pair fails or receives a repeated ID after the
unnecessary acquisitions. Reported. Separated from Arm A because it is a different cost with a different
repair, and merging them would let a null timing result hide a real resource failure.

`swapped_direction_failure_rate` (Arm C) — failing runs out of 50, per variant. Pass iff the correct
build is 0/50 **and** the swapped build is > 0/50. Both clauses: a swapped build that passes 50/50 does
not establish that direction is irrelevant — it establishes that this shape does not exercise the
hazard, which is a statement about the probe.

`crosscore_masks_local_hazard` (Arm D) — true iff the cross-core variant is correct in ≥ 45 of 50 runs
while the un-fixed variant is not. Reported, not gated. This is deliberately a *fuzzy* threshold, because
the claim being tested is "appears to work", and an exact predicate would misrepresent a probabilistic
masking effect as a fix or a non-fix.

The positive fixture, declared before the run: Arm C's **no-flag** build must fail at least once in 50,
and Arm D's **un-fixed** build must fail at least once in 50. If either is clean, that arm has no hazard
in it and every result it produced — including the reassuring ones — is a statement about the harness and
not about flags. This is the arm's whole validity: a synchronisation experiment whose unsynchronised
control passes is measuring nothing, and it is the exact species this book keeps finding, so it is
declared first rather than checked afterwards.

Process exit codes are not the verdict for any arm: Arms C and D expect wrong values from processes that
exit zero, and a watchdog kill is an informative outcome rather than a failure.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no flag set
or waited, no event ID fetched, no die contacted, and no run counted. The three quoted passages are
re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that an unnecessary flag pair costs anything,
that swapping event directions fails, or that a cross-core flag can mask a local hazard — Arms A through
D are all open, and upstream supplies **no symptom and no threshold** for either prohibition.

It does not establish when an operator is "advanced" enough to need explicit overlap. Upstream's terms —
"light unary", "short fused chain", "really needs it" — are undefined, and this entry deliberately does
not manufacture a threshold from them. That absence is the reason the rule cannot be applied to the
borderline case, which is the only case where a rule is needed.

It does not establish that the quoted four-call block is a usable pattern. §3 records that it shows a
`SetFlag` immediately followed by its own `WaitFlag` with one unchanging `pingPongID`, which is a
catalogue rather than a loop body; whether a real ping-pong loop alternates the identifier, and how, is
stated by no source in scope.

It says nothing about which `HardEvent` values exist, how many there are, or how the eight-slot pool is
partitioned among them — 0262 carries what is known, and `Q-950arch-27` records that the seven queues
`npu-arch` lists have not been reconciled with the pipes the regbase material names.

It says nothing about `SyncAll`, which is a block-level primitive on a different mechanism (0377), nor
about the auto-sync mode that 0259 records as a fourth position in the barrier question.

BOARD is `family-claimed(unverified)`: none of the three files names a board token this book recognises
and no board was contacted.
