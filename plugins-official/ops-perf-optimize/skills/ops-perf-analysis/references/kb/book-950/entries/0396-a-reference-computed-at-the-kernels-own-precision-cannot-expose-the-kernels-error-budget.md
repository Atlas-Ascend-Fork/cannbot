```
ID:        0396-a-reference-computed-at-the-kernels-own-precision-cannot-expose-the-kernels-error-budget
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), which states the rule
           and its companion metric rule in one pitfalls file. Upstream names the failure and gives no
           tolerance, no reference precision and no metric threshold. Nothing was compiled and no
           comparison was run.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/pitfalls/common_traps.md:177-191 —
           "## 10. Using weak reference outputs / Signal: / - NPU output is compared against a reference
           that shares the same numerical weakness / - `fp16` and `bf16` are judged against another
           reduced-precision path / Why it happens: / - the golden path is not strong enough to expose
           the real error budget / Check first: / - prefer a higher-precision reference / - verify
           rounding and cast behavior assumptions before claiming 1 ULP bugs"
SOURCE:    same file:80-94 — "## 4. Using a single failure metric / Signal: / - mean error looks fine but
           a few samples explode / - relative error looks huge only around zero / Why it happens: / -
           the chosen metric hides the real failure mode / Check first: / - inspect absolute and
           relative error together / - print worst-case samples and their neighborhoods"
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/pitfalls/api_misuse.md:100-114 —
           "## 5. Casting based on convenience instead of contract / Misuse: / - downcasting early to
           simplify storage or reuse / - comparing output against a reference that assumes a different
           cast mode / Why it fails: / - cast placement and rounding behavior can dominate the error
           budget / Visible symptom: / - stable systematic bias / - \"small but stubborn\" mismatches
           that survive algorithm fixes"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 fp16 or bf16 kernel whose error against a same-precision reference and against an fp64
           reference agree to within the comparison tolerance across a swept input range including
           cancellation-prone and near-zero cases — the weak reference would then be adequate for that
           operator, identifying a class where the rule does not bind.
```

# 0396 · A reference computed at the kernel's own precision cannot expose the kernel's error budget

## 1 · Claim
Upstream asserts a verification failure: comparing NPU output against a reference that shares the same
numerical weakness, specifically judging fp16 and bf16 results against another reduced-precision path.
Upstream asserts the reason — the golden path is not strong enough to expose the real error budget — and
two remedies: prefer a higher-precision reference, and verify rounding and cast-behaviour assumptions
before claiming 1 ULP bugs. Upstream asserts a companion rule about metrics: a single failure metric hides
the real failure mode, with mean error looking fine while a few samples explode, and relative error looking
huge only around zero; the remedy is to inspect absolute and relative error together and to print
worst-case samples with their neighbourhoods. Upstream asserts, in a second file, that comparing against a
reference assuming a different cast mode produces a stable systematic bias and "small but stubborn"
mismatches that survive algorithm fixes. Not established here: nothing was compiled, no comparison was run,
and upstream gives **no tolerance, no reference precision and no metric threshold**.

## 2 · The wrong branch this removes
A weak reference does not report a wrong answer. It reports agreement — and agreement is the outcome
everyone is looking for, so nobody audits it.

**The mechanism is correlated error, not absent error.** An fp16 reference implementing the same algorithm
in the same order makes the *same* rounding decisions at the same steps. So its output tracks the kernel's,
including where both are wrong. The comparison measures the difference between two similarly-wrong
numbers, which is small. The kernel then ships with an error budget nobody has measured, and the first
honest measurement happens downstream, where the operator's output is one term in something else.

**It is worst exactly where it matters most.** Correlation is highest where the algorithm is most
determined — an elementwise chain, where both paths do the same three operations. It is lowest where the
paths diverge — a reduction whose tree order differs from the reference's sequential sum (0030 records that
the hardware tree reduction reorders the sum), or a fused multiply-add that the kernel contracts and the
reference does not (0380 Arm D). So the weak reference is *most* misleading on the simple operators, where
an agent is least inclined to question it, and *least* misleading on the complex ones. That inverts the
attention an agent would naturally allocate.

**The two remedies are separate and the second is the sharper one.** "Prefer a higher-precision reference"
is the structural fix. "Verify rounding and cast behavior assumptions before claiming 1 ULP bugs" is a
warning about the opposite error: with a strong reference, a 1 ULP difference is *expected* for any
operation whose rounding mode is not pinned — and this book records two live instances. 0249: `Reg::Div`
defaults to an `INTRINSIC` mode with up to 1 ULP of error and needs an explicit mode for correctly-rounded
division. 0380: upstream's own SIMT guide calls the `/` operator and `fdividef` 功能完全等价 and then
separates them by rounding control. So an agent that upgrades its reference to fp64 and then reports every
1 ULP difference as a defect will file bugs against documented behaviour — and, worse, may "fix" them by
forcing a slower precision mode that the operator's contract never required.

**The metric rule closes the other half.** A strong reference with a mean-error metric is still blind: the
mean absorbs a handful of exploded samples, and relative error near zero is unbounded by construction
(dividing by a denormal). Upstream's remedy — absolute and relative together, plus the worst-case samples
*and their neighbourhoods* — is the part that turns a number into a diagnosis. The neighbourhood matters
because a single bad element and a run of bad elements have different causes: an isolated outlier suggests
a data-dependent path (a NaN, a subnormal, a cancellation), a contiguous run suggests a tile boundary or a
tail (0395's diagnostic).

**And the cast-mode variant is the one that survives every algorithm fix.** `api_misuse.md`'s symptom —
"stable systematic bias" and mismatches that survive algorithm fixes — is the signature of a reference that
rounds differently from the kernel, not one that is merely weaker. It is stable across runs, so 0394's
instability test says "not a race" and points at numerics; it is small, so it looks like tolerance; and it
does not move when the algorithm changes, because it was never in the algorithm. That combination sends an
agent through the entire numerical hypothesis space before anyone questions the reference.

## 3 · Ground / Source
`common_traps.md:177-191`, trap 10 in full:

> ## 10. Using weak reference outputs
>
> Signal:
>
> - NPU output is compared against a reference that shares the same numerical weakness
> - `fp16` and `bf16` are judged against another reduced-precision path
>
> Why it happens:
>
> - the golden path is not strong enough to expose the real error budget
>
> Check first:
>
> - prefer a higher-precision reference
> - verify rounding and cast behavior assumptions before claiming 1 ULP bugs

"Prefer" is weaker than the rest of the file's modality, and no precision is named — fp32 against an fp16
kernel is higher-precision and may still be too weak for a long reduction (0397 records fp32's own safe
accumulation length as < 10⁶). So the remedy as stated is a direction, not a specification.

`common_traps.md:80-94`, trap 4, quoted in SOURCE. Its two signals are the two ways a scalar metric fails,
and they fail in opposite directions: the mean under-reports concentrated error, and the relative metric
over-reports near zero. So neither is safe alone and upstream's remedy is to carry both — which is why §5
below refuses to aggregate them.

`api_misuse.md:100-114`, quoted in SOURCE, and its repair-order context at `:145-152` (0394 §3): the
reference is validated at step 3-4, after branch and synchronisation, which places reference quality inside
the numerical phase rather than before it. That ordering is defensible and worth noting: an agent should
not audit its reference until 0394's stability test has ruled out an ordering defect, or it will be
comparing a raced output against a perfect reference and blaming the reference.

The neighbouring precision documents in the same subtree — `precision_guide.md` (190 lines) and
`precision_failures.md` (176 lines) — were **not** mined during this harvest; they are outside the three
pitfalls files this block was scoped to, and their omission is recorded here and in the final report rather
than left silent. So the numerical-verification material this entry draws on is the three passages above,
and the subtree's dedicated precision documents are unexamined.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

**What upstream does not supply**: what precision a reference must have; what tolerance is acceptable at
each dtype; how many worst-case samples to print; what neighbourhood radius; and how to distinguish an
expected 1 ULP difference from a defect, which is precisely the judgement the second remedy demands.

This entry is one of the few drawn from `pitfalls/`, whose files are predominantly symptom→check diagnostic
process. It is entered rather than carded because its central claim is falsifiable by a two-reference
comparison — the OVERTURN names one — and because the metric rule prescribes a readout that a claim-card
could not carry.

## 4 · Procedure
Runnable later on `950PR`. The claim is that two references disagree about a kernel's error, so the
procedure computes both.

Arm A — the two references, on one kernel. Take one fp16 elementwise chain and one fp16 reduction. For
each, compute a same-precision reference (fp16, same operation order) and an fp64 reference. Report max
absolute error, max relative error, and the 99.9th percentile of each, against **both** references, over a
swept input set: uniform normals, values spanning six exponent decades, near-zero values, and a
cancellation-prone pair set. The gap between the two references' verdicts is the measurement.

Arm B — where the gap is largest. Compare the elementwise and reduction results from Arm A. §2 predicts the
gap is *smaller* for the elementwise chain (higher correlation) and larger for the reduction (divergent
summation order, 0030). If the prediction inverts, the correlation account is wrong and the rule needs a
different justification.

Arm C — the 1 ULP question, made decidable. For an operator containing a division, run it against an fp64
reference twice: once with `Reg::Div`'s default `INTRINSIC` mode and once with the correctly-rounded mode
0249 records. Record the error in each. This establishes what fraction of the observed 1 ULP difference is
documented behaviour rather than defect — which is what upstream's second remedy asks an agent to verify
and gives it no way to do.

Arm D — the metric rule. For the worst case in Arm A, report mean absolute error, max absolute error, mean
relative error, max relative error, and the index list of the worst 20 samples with their five neighbours
each. Confirm whether the mean would have passed a plausible tolerance while the max failed. This is the
arm that turns trap 4 from advice into a demonstrated case.

Arm E — the cast-mode bias. Build the same kernel with two cast modes at the narrowing step (whatever
`RoundMode` values the reg-compute traits expose) and compare each against one fp64 reference. A stable
offset between the two is the "systematic bias" `api_misuse.md` describes, and observing it makes the
symptom recognisable.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`error_by_reference` (Arm A) — four numbers per operator per input class: max absolute and max relative
error against each of the two references. **Reported as a table and never aggregated across input classes
or across the two references.** Aggregating is the failure this entry is about; a checker that reports one
"error" figure has committed the trap it is testing for.

`reference_gap` (Arms A, B) — the ratio of the fp64-reference error to the fp16-reference error, per
operator per input class. Pass iff > 1 everywhere, i.e. the weak reference always under-reports. A ratio ≤ 1
anywhere means the weak reference over-reports there, which no source predicts and would be the interesting
result.

`ulp_attributable_to_mode` (Arm C) — the error difference between the default and correctly-rounded division
modes. Reported. Declared in advance so a 1 ULP residue can be attributed rather than argued about.

`mean_would_have_passed` (Arm D) — true iff the mean absolute error is inside a stated plausible tolerance
while the max is outside it. The tolerance is fixed **before** the run and recorded; choosing it afterwards
would make this variable unfalsifiable.

`cast_mode_bias` (Arm E) — the mean signed difference between the two cast-mode builds. A non-zero mean
signed difference is a bias; a zero mean with non-zero variance is not. Signed, not absolute, on purpose:
absolute error cannot show a bias.

The positive fixture, declared before the run: Arm A must include an **fp32 kernel** compared against both
an fp32 reference and the fp64 one. For a well-conditioned elementwise chain the two verdicts should agree
closely — if they do not, the fp64 reference or the input generator is wrong and every gap measured in the
arm is an artefact of the harness rather than of reference weakness. And the fp64 reference must be
validated on a case with a known closed-form answer (a sum of powers of two, exact in every format) where
**all** references must report zero error; if any does not, the comparison pipeline is broken and no result
in any arm is interpretable. Without both, the checker reads only "the two references disagreed", which is
equally consistent with a broken reference — the known blind species.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no reference
computed, no error measured, no sample printed, no die contacted. The quoted passages are re-verified file
reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that a same-precision reference under-reports
error, by how much, or for which operator classes — Arms A through E are all open, and upstream supplies
**no tolerance, no reference precision and no metric threshold**.

It does not establish what precision a reference needs. "Higher-precision" is a direction; fp32 is higher
than fp16 and is itself limited (0397 records fp32's safe accumulation length as < 10⁶), so "higher" and
"sufficient" are different properties and no source in scope names the second.

**It does not establish how to tell an expected 1 ULP difference from a defect.** Upstream's second remedy
demands that judgement and supplies nothing to make it with. 0249 records one documented 1 ULP source
(`Reg::Div`'s default mode) and 0380 records an unresolved one (the SIMT operator versus `fdividef`); how
many others exist is unknown, and Arm C would price only the first.

**Two neighbouring upstream documents were not read.** `precision_guide.md` and `precision_failures.md` sit
in the same `pitfalls/` directory, total 366 lines, and are outside the three files this block was scoped
to. They are the subtree's dedicated numerical-verification material and this entry does not know what they
contain — including whether they supply the tolerances and reference precisions this entry records as
missing. That omission is deliberate and is reported rather than left silent.

It says nothing about the correlation account in §2 beyond naming it: that a same-precision reference errs
*in the same direction* as the kernel because it makes the same rounding decisions is an argument, and Arm B
is what would test its main prediction.

It says nothing about how a reference should be built — host fp64, a framework operator, a symbolic
evaluation — nor about what to do when no higher-precision reference exists for an operator, which is the
case upstream's remedy does not cover.

BOARD is `family-claimed(unverified)`: numerical verification practice names no board, the files name no
board token this book recognises, and no board was contacted.
