```
ID:        0394-a-mismatch-that-moves-between-runs-is-a-synchronisation-defect-and-not-precision-drift
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), which states the rule in
           two of its own pitfalls files. Upstream gives a symptom and a routing decision and no
           mechanism. Nothing was compiled and no run was repeated.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/pitfalls/common_traps.md:145-159 —
           "## 8. Treating non-determinism as harmless noise / Signal: / - identical input produces
           different mismatches / - re-running the same case changes which elements fail / Why it
           happens: / - synchronization or branch-selection problems are masquerading as precision drift
           / Check first: / - [[../api/regbase_api_sync]] / - branch and API-family correctness"
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/pitfalls/api_misuse.md:65-83 —
           "## 3. Treating synchronization bugs as numeric noise / Misuse: / - blaming dtype or tolerance
           when the failure is unstable between runs / Why it fails: / - synchronization and event misuse
           often produce outputs that look like random numeric corruption / Visible symptom: / - repeated
           runs fail at different indices / - intermediate tensors look partially old or partially
           uninitialized / First check: / - read `../api/regbase_api_sync.md` / - determine whether the
           first bad value is stable across reruns"
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/pitfalls/api_misuse.md:145-152 —
           "## Repair Order / Before making a precision-only fix: / 1. validate branch and API family /
           2. validate whitelist and sync assumptions / 3. identify the first bad intermediate / 4. only
           then tune dtype, cast point, or stabilization logic"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 kernel whose failing element set changes between identical runs and whose cause is
           demonstrably numerical rather than ordering — for instance a reduction whose hardware tree
           order is itself run-dependent — which would make the stability test route a real numeric
           defect to the synchronisation path.
```

# 0394 · A mismatch that moves between runs is a synchronisation defect, and not precision drift

## 1 · Claim
Upstream asserts a discriminating test between two failure classes that present alike. The signal:
identical input producing different mismatches, and re-running the same case changing *which* elements
fail. Upstream asserts the attribution — synchronisation or branch-selection problems masquerading as
precision drift — and the routing: check the synchronisation guidance and the branch and API-family
correctness first. Upstream asserts, in a second pitfalls file, the same rule with a sharper diagnostic
question — whether the first bad value is stable across reruns — and a second symptom: intermediate
tensors that look partially old or partially uninitialised. Upstream asserts a four-step repair order in
which dtype, cast point and stabilisation logic are touched only after branch, API family, whitelist and
synchronisation assumptions have been validated and the first bad intermediate identified. Not established
here: nothing was compiled, no run was repeated, and upstream names **no mechanism** for the
masquerade.

## 2 · The wrong branch this removes
The two classes look identical in the only artifact an agent normally has: a comparison report listing
failing indices and error magnitudes.

**Why precision is the default hypothesis.** The report is numerical. It says elements 4172, 8891 and
19204 exceed tolerance by 3e-3. Every affordance an agent has — tolerance thresholds, dtype promotion,
accumulator width — is numerical. And the numerical hypothesis has an immediate, cheap, satisfying test:
widen to fp32 and see if it goes away. It usually does, because widening changes the timing as much as the
arithmetic. So the agent gets a green run, records a precision fix, and ships a kernel whose race is still
there and now costs twice the registers (0357) for no reason.

**The discriminator is free and nobody runs it.** Run the same input twice. If the failing set is
identical, the failure is deterministic and a numerical explanation is admissible; if it moves, no
numerical explanation survives — the arithmetic did not change between runs. That is a *one-command* test
and it is decisive in one direction, which is a rare property in debugging. Upstream's contribution here is
not a mechanism; it is the observation that the test exists and that the ordering of hypotheses should
depend on it.

**The second symptom is the one that names the mechanism.** "Intermediate tensors look partially old or
partially uninitialized" is not what numerical error produces — numerical error perturbs values, it does
not leave *previous iteration's* values in place. Partially-stale data is a read that beat a write, and in
this book's material there are named instances of exactly that: 0366's inplace kernel where MTE2 reads a
tile before MTE3's write-back completes; 0376's second `VF_CALL` starting before another core's first one
finished; 0028's kept store-to-load round trip without `LocalMemBar` returning `inf`; 0379's concurrent
same-address writes without an atomic. So the class this rule routes to is populated, and the routing has
somewhere to go.

**The repair order is the load-bearing half and it is easy to read as advice.** Steps 1 and 2 — branch and
API family, then whitelist and sync assumptions — come *before* step 3, identifying the first bad
intermediate, which is itself before any dtype change. That ordering is not about likelihood; it is about
**cost of a wrong answer**. A precision fix applied to a race is not neutral: it consumes the budget, it
makes the run slower, and — worst — it *removes the evidence*, because the widened build no longer fails
and the agent has nothing left to bisect. An ordering rule whose justification is evidence preservation is
stronger than one whose justification is base rates, and upstream states the ordering without the
justification.

**What the rule does not license.** A *stable* failing set does not establish a numerical cause. A
deterministic race — one whose interleaving is fixed by the schedule at a given shape — produces a stable
failure, and so does a genuine numerical bug. The test is one-directional: instability rules numerics out;
stability rules nothing out. Upstream's phrasing ("Check first") is consistent with that and does not say
it, and an agent that reads the rule as a two-way classifier will treat a stable failure as evidence *for*
precision, which it is not.

## 3 · Ground / Source
`common_traps.md:145-159`, trap 8 in full:

> ## 8. Treating non-determinism as harmless noise
>
> Signal:
>
> - identical input produces different mismatches
> - re-running the same case changes which elements fail
>
> Why it happens:
>
> - synchronization or branch-selection problems are masquerading as precision drift
>
> Check first:
>
> - [[../api/regbase_api_sync]]
> - branch and API-family correctness

Note 分支选择 — branch selection — as a second cause alongside synchronisation. A TilingKey mismatch (0369)
selecting no branch, or an uninitialised route, produces stale or untouched output too, and it is not a
race. So the rule routes to two mechanisms, and upstream lists them together because they share the
symptom, not because they share a repair.

`api_misuse.md:65-83`, the same rule from the API-misuse angle, quoted in SOURCE. Its sharper form is the
question at `:83`: "determine whether the first bad value is stable across reruns" — first bad value, not
failing set. That is a better instrument: the first divergence is where the cause is (`common_traps.md`
trap 5, `:96-111`), and its stability is a cleaner signal than the stability of a downstream failure
pattern that may be smeared by subsequent arithmetic.

The repair order, `:145-152`, quoted in SOURCE.

The neighbouring traps that make the ordering coherent, `common_traps.md:161-175` (trap 9, "Blindly
widening everything to `fp32`"):

> Signal:
>
> - the bug disappears but performance or design clarity collapses
> - no one can explain which step actually needed wider precision
>
> Why it happens:
>
> - the fix was chosen for convenience, not diagnosis

That is the outcome trap 8 exists to prevent, stated one section later as its own trap. The two are one
argument split across two entries in upstream's list.

Both files are `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

**What upstream does not supply, and what makes this `harvested` rather than stronger**: no mechanism for
any masquerade, no statement of how many reruns constitute evidence, no treatment of the deterministic-race
case, and no acknowledgement that the test is one-directional. `regbase_api_sync.md`, the file both
passages route to, was not read during this harvest.

This entry is one of the few in this block drawn from `pitfalls/`, whose files are predominantly
symptom→check diagnostic process rather than falsifiable machine claims. It is entered rather than
carded because the discriminator is falsifiable — the OVERTURN names a concrete observation — and because
the repair-order rule has a consequence (evidence destruction) that a claim-card could not carry.

## 4 · Procedure
Runnable later on `950PR`. The claim is about a diagnostic test, so the procedure calibrates the test
against known causes.

Arm A — the discriminator against a known race. Take a kernel with a *planted* synchronisation defect —
0366's inplace pipeline without its `MTE3_MTE2` pair is the cleanest available — and run it 50 times on one
input. Record the failing index set per run and whether the first bad index is stable. Prediction: the set
moves. This establishes that the test fires on a true positive.

Arm B — the discriminator against a known numerical defect. Take a kernel with a *planted* precision
defect — an fp16 accumulator over a long axis, per 0397's regime — and run it 50 times on one input.
Prediction: the failing set is identical every run. This establishes that the test does not fire on a true
negative, which Arm A alone cannot show.

Arm C — the deterministic-race case §2 raises and upstream does not. Construct a race whose interleaving is
fixed by the launch configuration (a fixed core count, a fixed tile order) and run it 50 times. If the
failing set is stable, the test yields a false negative on a real synchronisation defect, and the rule's
one-directionality is demonstrated rather than argued.

Arm D — the repair order's evidence claim. On Arm A's raced kernel, apply the precision-only repair (widen
to fp32) and run 50 times. Record whether the failure disappears and whether the underlying race is still
detectable by any other means. §2 claims the widened build destroys the evidence; if the race remains
visible, the ordering rule's justification is weaker than stated and should be re-argued from base rates
instead.

Arm E — the first-bad-value refinement. For all three planted defects, record both the stability of the
failing *set* and the stability of the *first bad index*. `api_misuse.md`'s sharper form predicts the first
bad index is the better signal; whether it is, over three known causes, is measurable.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all 50 repetitions of one arm run on one named die in one session — **a die change between
repetitions would introduce exactly the variation being measured.**

## 5 · Checker — acceptance declared before the run
`set_instability` (Arms A, B, C) — per planted defect, the number of distinct failing index sets over 50
runs. Pass condition: > 1 for the race (Arm A), exactly 1 for the numerical defect (Arm B). Reported per
defect, never combined into an accuracy figure — the two directions are different claims and one number
would hide a failure in either.

`first_bad_index_stability` (Arm E) — per defect, the number of distinct first-bad-indices over 50 runs.
Reported beside `set_instability` so the two instruments can be compared on the same data.

`deterministic_race_detected` (Arm C) — true iff the fixed-interleaving race shows an unstable set. Expected
**false**. This checker is written to confirm a limitation, so a false result is the finding and a true
result would mean the rule is stronger than §2 credits.

`evidence_survives_widening` (Arm D) — true iff the race remains detectable after the precision-only repair.
Expected **false**. Reported.

The positive fixture, declared before the run: **Arm B is the fixture for Arm A and Arm A is the fixture
for Arm B.** Neither alone means anything — a test that reports instability for everything and a test that
reports stability for everything are both useless, and only the pair distinguishes a working discriminator
from a broken one. This is stated as the checker's structure rather than as an addendum because the failure
mode being guarded against is precisely a rule validated only on the cases it was written for. In addition,
each arm must include a **clean** build of the same kernel with no planted defect, which must produce zero
failures in all 50 runs; if the clean build fails, the comparison harness or the reference is wrong and
every stability measurement is void.

Process exit codes are not the verdict for any arm: every planted defect here exits zero.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no defect
planted, no run repeated, no failing set recorded, no die contacted. The quoted passages are re-verified
file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that instability implies a synchronisation
defect, that stability implies anything, or that the repair order preserves evidence — Arms A through E are
all open, and upstream states the rule with **no mechanism at all**.

**The test is one-directional and upstream does not say so.** An unstable failing set rules out a purely
numerical cause; a stable one rules out nothing, because a deterministic race produces a stable failure.
§2 states this and Arm C is what would demonstrate it; reading the rule as a two-way classifier is the
misuse this section exists to prevent.

It does not establish how many reruns are enough. Fifty is this procedure's choice; a race that fires once
in a thousand runs is invisible at fifty and is exactly the kind that reaches production. No source in scope
gives a number.

It does not establish the mechanism of any masquerade. Upstream names two causes — synchronisation and
branch selection — that share a symptom and have entirely different repairs (0366, 0376, 0379 for the first;
0369 for the second), and nothing in scope tells an agent which of the two it is once the test has fired.

It does not establish anything about `regbase_api_sync.md`, the file both passages route to as the first
thing to read. That file was not read during this harvest, so the destination of this rule's routing is
unexamined.

It says nothing about tolerance selection, metric choice, or reference quality — neighbouring traps in the
same file (0395, 0396) that share this one's subject and are separate claims.

BOARD is `family-claimed(unverified)`: both files describe regbase debugging practice, neither names a board
token this book recognises, and no board was contacted.
