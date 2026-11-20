```
ID:        0356-a-register-temp-is-promoted-to-ub-only-when-reuse-or-staging-forces-it
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). The rule is stated as
           a preference with two named conditions and no cost for violating it; nothing was compiled
           and no UB or register pressure was measured.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/regbase_buffer_partitioning.md:56-77
           — "Prefer **register temps** when the value: / - only exists inside one VF loop / - is
           consumed immediately by the next register instruction / - does not need to survive across
           queue handoff or tile boundary" … "Prefer **UB temps** when the value: / - is reused by more
           than one VF sub-step / - must be shared across different local stages / - needs to be
           revisited after another asynchronous or staged action" … "Bad habit: / - materializing every
           intermediate into UB because the VF chain feels unfamiliar / Better habit: / - keep
           short-lived math in `RegTensor` / - promote to UB only when reuse or staging actually
           requires it"
SOURCE:    same file:29-33 — the three-domain table: "| GM | `GlobalTensor<T>` | full inputs, full
           outputs, persistent tensor state | / | UB | `LocalTensor<T>`, `TQue`, raw `__ubuf__`
           pointers | tile-sized staged data, ping-pong buffers, reusable tile-local scratch | /
           | Registers | `RegTensor<T>`, `MaskReg` | VF-local operands, masks, cast temporaries,
           compare results, fused arithmetic intermediates |"
SOURCE:    same file:54 — "Only materialize an extra UB temp if the same tile-local result must be
           reused across multiple VF chains or multiple output writes."
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 kernel in which moving a single-use VF intermediate from `RegTensor` to a UB temp
           makes it FASTER at some shape — the promotion rule would then be a register-pressure
           heuristic with a crossover rather than a directional preference; or a case where the
           register form produces wrong results that the UB form does not, which would make it a
           correctness boundary and not a preference at all.
```

# 0356 · A register temp is promoted to UB only when reuse or staging forces it

## 1 · Claim
Upstream asserts a three-domain partition for regbase data — GM for whole tensors and persistent state,
UB for tile-sized staged data and reusable tile-local scratch, registers for VF-local operands, masks,
cast temporaries, compare results and fused-arithmetic intermediates. Upstream asserts a directional
rule between the last two: keep short-lived math in `RegTensor`, and promote a value to a UB temp only
when reuse or staging actually requires it. Upstream names the two qualifying conditions — the value is
reused by more than one VF sub-step, or it must survive a queue handoff or tile boundary — and names
the failure it is guarding against: materialising every intermediate into UB because the VF chain feels
unfamiliar. Upstream states no cost for the violation. Not established here: nothing was compiled and
no register or UB pressure was measured.

## 2 · The wrong branch this removes
The default an agent brings to a new instruction set is *make the state visible*, and in AscendC that
means a `LocalTensor`. Every intermediate gets a UB buffer because a UB buffer can be dumped, compared
against a host reference, and reasoned about at the tile level. Register state can be done none of
those things. So the unfamiliar path is also the opaque one, and the pressure to materialise is a
debugging pressure, not a design one.

Three things go wrong when it wins.

The **budget** goes first, and it goes quietly. UB is 248 KB on this family (0209) and every extra temp
is charged against the tile size the tiling routine can afford. A chain of five intermediates
materialised at full tile width costs five times the tile, which the tiling search will absorb by
shrinking the tile — so the operator still works, still produces correct output, and runs on tiles small
enough that the fixed per-tile cost dominates (0017). Nothing fails; the kernel is just slow, and the
cause is three layers away from the symptom.

The **round trip** goes second. A materialised intermediate is a `StoreAlign` followed by a `LoadAlign`
for the next step, so a two-instruction register chain becomes four instructions plus a UB dependency
that may need ordering. 0027 carries the positive form of this claim from a different source; the
relation here is that this entry says *when* it is allowed to be otherwise, which 0027 does not.

The **third** is subtler and is the reason the rule has two conditions rather than one. "Reused by more
than one VF sub-step" and "must survive a stage boundary" are different tests, and only the second is
about correctness. A value that is reused three times inside one VF loop is still a legitimate register
temp if the register file can hold it; the reuse condition is about *register pressure*, not about
lifetime. An agent that reads the two conditions as one rule ("reuse → UB") will promote values whose
only problem is that they are used twice, and will pay the round trip for nothing. Upstream's own
sharper form at `:54` is the lifetime-and-fan-out one: "reused across multiple VF chains or multiple
output writes" — across chains, not within one.

The mirror error exists and upstream does not name it: keeping too much in registers spills. 0036
establishes that an `int64` `RegTensor` occupies two physical registers, so source-level counts
understate pressure, and 0236 records that the per-thread register count falls in steps as thread count
rises. There is a ceiling and this rule points straight at it, with no stated location. That is the gap
§4 exists to fill.

## 3 · Ground / Source
The three-domain table, `regbase_buffer_partitioning.md:27-33`:

> ## 1. The Three Storage Domains
>
> | Domain | Typical Objects | What Belongs Here |
> |---|---|---|
> | GM | `GlobalTensor<T>` | full inputs, full outputs, persistent tensor state |
> | UB | `LocalTensor<T>`, `TQue`, raw `__ubuf__` pointers | tile-sized staged data, ping-pong buffers, reusable tile-local scratch |
> | Registers | `RegTensor<T>`, `MaskReg` | VF-local operands, masks, cast temporaries, compare results, fused arithmetic intermediates |

and the rule, `:56-77`:

> ## 3. Register Temp Versus UB Temp
>
> Prefer **register temps** when the value:
>
> - only exists inside one VF loop
> - is consumed immediately by the next register instruction
> - does not need to survive across queue handoff or tile boundary
>
> Prefer **UB temps** when the value:
>
> - is reused by more than one VF sub-step
> - must be shared across different local stages
> - needs to be revisited after another asynchronous or staged action
>
> Bad habit:
>
> - materializing every intermediate into UB because the VF chain feels unfamiliar
>
> Better habit:
>
> - keep short-lived math in `RegTensor`
> - promote to UB only when reuse or staging actually requires it

The baseline the rule sits on, `:37-53`, is worth quoting because it fixes what "no extra temp" means:
a unary operator gets one input UB tile and one output UB tile; a binary operator gets two in and one
out; and "Only materialize an extra UB temp if the same tile-local result must be reused across
multiple VF chains or multiple output writes." So the rule's zero point is *the number of tensors*, and
every intermediate above that count is the thing being argued about.

What upstream does not supply, and what makes this a preference rather than a boundary: no cost, in
either direction. There is no statement of what a materialised intermediate costs, no register-file
size, no spill threshold, no shape at which the trade reverses. The file's own §6 "Reference Cases"
(`:110-115`) names "a fused register-chain implementation — more register intermediates, but not a
general outer-shell template" without naming the implementation, so even the exemplar is unciteable.

The neighbouring entries this depends on and does not restate: 0019 (queue depth and physical buffer
count are different and only one costs UB), 0027 (keep intermediates in vector registers instead of
staging them through UB — the same direction, from `ascendc-perf-optimize`, one origin with this one),
0036 (an int64 `RegTensor` is two physical registers), 0044 (reuse a UB buffer instead of detouring
through GM). This entry adds the *promotion condition*, which none of them states.

## 4 · Procedure
Runnable later on `950PR`. The rule is directional with no stated crossover, so the procedure looks for
the crossover.

Arm A — the round trip's cost, isolated. One elementwise operator with a five-step VF chain, built
twice: all four intermediates in `RegTensor`, and all four materialised through UB temps with
`StoreAlign`/`LoadAlign` between steps. Identical inputs, one die, one session, three tile sizes.
The duration difference at fixed tile size is the round-trip cost. This arm alone does not establish
the rule — it establishes the cost of the extreme it warns against.

Arm B — the crossover, which is the missing number. Sweep the number of live `RegTensor` intermediates
from 2 to 16 in the all-register build and record duration at each. The rule predicts monotone benefit
from keeping values in registers; §2 predicts a knee where spilling starts. The knee's location is what
a tiling routine actually needs and no document in scope supplies. **Gate the timing on disassembly**:
a duration knee without stack traffic in the generated code is measuring something other than spill,
which is the mistake `Q-950arch-12` records for the register-band table.

Arm C — the reuse condition, tested as written. Build the same chain three ways: an intermediate used
once, used twice inside one VF loop, and used by two separate VF chains. Under upstream's two
conditions the first two should stay in registers and only the third should be promoted. If promoting
the twice-used value helps, the reuse condition as written at `:60` is right and the sharper form at
`:54` is wrong; if it hurts, the reverse. The two statements are in one file and disagree about a
concrete case, which is what makes this arm decidable.

Arm D — the UB budget consequence, the one that is not a duration. For each build, record the tile size
the host tiling routine selects under a fixed UB budget. §2 claims the materialised build gets smaller
tiles; the tile count, not the duration, is the attributable measurement, because it is computed on the
host and does not depend on anything the die does.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and all builds of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`roundtrip_cost_ratio` (Arm A) — duration of the materialised build over the register build, per tile
size, never averaged across tile sizes. Pass iff > 1.0 at every tile size. A ratio ≤ 1.0 anywhere
overturns the rule's direction at that shape and is the finding.

`spill_knee_intermediates` (Arm B) — the smallest live-intermediate count at which duration rises
**and** the disassembly shows stack traffic. Both clauses required. Reported, not gated: upstream states
no ceiling, so there is no value to pass against, and the number is the deliverable.

`reuse_condition_is_across_chains` (Arm C) — true iff promoting the twice-used-within-one-loop value
does not help while promoting the across-chains value does. This is the verdict that adjudicates the
file against itself; either outcome corrects one of its two sentences in place and is logged.

`tile_size_penalty` (Arm D) — the ratio of selected tile sizes. Reported. Separated from the duration
verdicts deliberately: a build could be slower for reasons unrelated to tiling, and a smaller tile is a
host-side fact that holds whether or not the duration moved.

The positive fixture, declared before the run: Arm A must include a third build with **one** extra UB
temp rather than four, and its duration must fall between the other two. If it does not — if one temp
costs as much as four, or nothing at all — the harness is not resolving the effect it claims to measure
and every ratio it produced is void. A second fixture for Arm B: the sweep must include a deliberately
over-allocated build (32 intermediates) that **must** show stack traffic; if it does not, the
disassembly gate cannot detect spill and the knee is unattributable. Without both, the checker reads
only "more temps was slower", which does not distinguish the round trip from register pressure from
tile-size loss — three different causes with three different repairs.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no die was
contacted, no duration recorded, and no disassembly read. The quoted passages are re-verified file reads
of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that register temps are faster, that
materialising costs anything, or that the two named promotion conditions are the right ones — Arms A
through D are all open, and upstream states the rule with **no cost in either direction**.

It does not establish where the register ceiling is. The rule points at a resource whose size is
unverified: 0236 records upstream's four-band per-thread register table as self-consistent and
unsupported, and 0036 records that an eight-byte element occupies two physical registers, so a
source-level count of `RegTensor` declarations is not a register count. Arm B's knee is the missing
number and it has not been measured.

It does not resolve the file's disagreement with itself: `:60` says "reused by more than one VF sub-step"
and `:54` says "reused across multiple VF chains or multiple output writes", and those admit different
answers for a value used twice inside one loop. Arm C is what decides it; until then both readings are
live and §2 states which one this entry finds sharper without claiming it is upstream's.

It says nothing about `MaskReg` pressure, which the domain table places in the register column and which
no source in scope budgets separately — `Q-950arch-14` records that the predicate register width does not
obviously fit a 128-lane mask, so mask state may not scale the way `RegTensor` state does.

It says nothing about the GM row of the three-domain table, which was not probed at all, nor about
ping-pong buffers, which the UB row names and which are a separate claim (0042).

BOARD is `family-claimed(unverified)`: the file names no board token this book recognises and no board
was contacted.
