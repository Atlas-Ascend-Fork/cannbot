```
ID:        0369-a-950-route-failure-is-more-often-a-config-mismatch-than-a-compute-error
LABEL:     procedure
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), stated in two of its
           own files as distilled project experience. Upstream gives a frequency claim ("a large
           share") with no count, no denominator and no case list. Nothing was compiled and no defect
           population was surveyed.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/working_vs_failed_950_cases.md:59-68
           — "## 4. Many “Kernel” Failures Are Actually Configuration Failures / A large share of broken
           950 work comes from: / - `simplified_key.ini` not matching the route / - TilingKey branches
           not matching runtime registration / - missing or inconsistent config updates / - operator
           support declarations drifting away from the code path / When the math seems fine but the
           route still breaks, inspect config before redesigning computation."
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/tiling_review_notes.md:30-38
           — "## 3. TilingKey Drift Breaks Otherwise Valid Routes / A correct tiling decision is still
           broken if: / - host sets one key / - kernel branches on another / - binary metadata
           advertises a third set / Review TilingKey as a three-part contract: generation, dispatch,
           registration."
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/working_vs_failed_950_cases.md:70-78
           — "## 5. A Practical 950 Review Habit / Before trusting a new 950 implementation, ask: / -
           Is this really a DAG-shaped problem or a regbase-shaped problem? / - Did we keep one
           execution family all the way through? / - Does TilingKey routing agree with config and dtype
           coverage? / - Is any “framework mixing” happening under a different name?"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a surveyed population of 950 defects in which configuration mismatches are a minority — the
           frequency claim would fall, and with it the ordering advice that rests on it. Separately: a
           TilingKey mismatch between host generation and kernel dispatch that produces a loud, named
           diagnostic rather than a silently unselected branch would remove the mechanism §2 depends
           on.
```

# 0369 · A 950 route failure is more often a config mismatch than a compute error

## 1 · Claim
Upstream asserts that a large share of broken 950 work originates in configuration rather than in
computation, and names four sources: `simplified_key.ini` not matching the route; TilingKey branches not
matching runtime registration; missing or inconsistent config updates; and operator support declarations
drifting away from the code path. Upstream asserts the resulting ordering rule: when the math seems fine
and the route still breaks, inspect configuration before redesigning computation. Upstream asserts,
separately, that TilingKey is a three-part contract — generation on the host, dispatch in the kernel,
registration in binary metadata — and that a correct tiling decision is still broken if any two of the
three disagree. Upstream asserts a four-question review habit that places the TilingKey/config/dtype
agreement question alongside the execution-family questions. Not established here: nothing was compiled,
no defect population was surveyed, and upstream's frequency claim carries **no count and no denominator**.

## 2 · The wrong branch this removes
The debugging order an agent adopts by default is the order of the layers it can see, and the compute
path is the one it just wrote.

So the sequence is: output is wrong → read the VF body → check the arithmetic → widen a dtype → adjust a
mask → re-derive the tiling formula. Every one of those is a real thing that can be wrong, and every one
of them is *below* the layer where the defect actually is. The compute code being examined may not even
be the compute code that ran, because a TilingKey mismatch means a different branch was selected — or no
branch was, and the kernel fell through.

That is the mechanism worth stating precisely, because it explains why the symptom misleads. A
`TILING_KEY_IS(101UL)` dispatch (0355 §3's shell pattern) is a *conditional*. If the host emits key 102
and the kernel tests 101, the guarded block does not run. The kernel returns having done nothing, or
having run a fallback branch, and the output is uninitialised memory or a stale buffer — which looks
exactly like a compute bug producing garbage. Nothing errors, because a conditional that is false is not
an error. This is 0368's species one layer up: a request that matched nothing, reported as success.

The four sources upstream names are four different two-place disagreements, and they fail differently:

- `simplified_key.ini` vs the route — the compiled kernel binary set does not contain a kernel for the
  key the host emits, so the failure is at launch and may name the key.
- host key vs kernel branch — a silent no-op, as above; the worst of the four.
- config updates missing — the operator is not registered for the case, so the framework does not
  dispatch to it at all and may fall back to another implementation, which produces *correct but
  unexplained* results and is the hardest to notice.
- support declarations vs code path — the operator advertises a dtype or format the code path does not
  handle; the failure appears only for the advertised-but-unimplemented case, i.e. never in the tests
  written from the code.

`tiling_review_notes.md:30-38`'s three-part framing is what makes the second and third detectable:
generation, dispatch, registration are three artifacts, and the review is a three-way comparison, not two.
An agent that checks host against kernel and stops has verified two of three and can still be defeated by
the binary metadata advertising a different set.

The **counter-branch** this entry must also remove: taking "inspect config first" as "the compute is
probably fine". It is an ordering claim about where to look, not a probability claim about any particular
defect, and upstream supplies no denominator. An agent that stops looking at compute because a config
audit came back clean has misread it.

## 3 · Ground / Source
The frequency claim and the four sources, `working_vs_failed_950_cases.md:59-68`:

> ## 4. Many “Kernel” Failures Are Actually Configuration Failures
>
> A large share of broken 950 work comes from:
>
> - `simplified_key.ini` not matching the route
> - TilingKey branches not matching runtime registration
> - missing or inconsistent config updates
> - operator support declarations drifting away from the code path
>
> When the math seems fine but the route still breaks, inspect config before redesigning computation.

"A large share" is the entire quantification. There is no count, no denominator, no case list, and no
statement of what population was observed — the file's own header says it distils
`knowledge_cards/kernel_code_patterns_950.md`, which is not in this harvest's scope. So the frequency
claim is an experience report about a population this book cannot see, and the *ordering advice* is what
survives independently of it: the ordering is defensible from the mechanism in §2 whether the share is
large or small, because config defects are cheap to check and expensive to misdiagnose.

The three-part contract, `tiling_review_notes.md:30-38`:

> ## 3. TilingKey Drift Breaks Otherwise Valid Routes
>
> A correct tiling decision is still broken if:
>
> - host sets one key
> - kernel branches on another
> - binary metadata advertises a third set
>
> Review TilingKey as a three-part contract: generation, dispatch, registration.

That file's neighbouring items are the same discipline applied to other artifacts and are recorded here
because they share the mechanism: `:8-18` treats includes as part of the contract and says to "review
includes by file role, not by memory" (host tiling header, host tiling implementation, kernel entry,
kernel-side struct, kernel implementation header — five roles); `:40-42` treats namespace mismatches
across `_struct.h`, `_tiling_arch35.*` and `_apt.cpp` as a symptom that "the route was assembled by
copy-paste rather than by a stable mental model"; `:44-56` separates `TilingPrepare` (platform facts)
from `Tiling` (runtime shape and dtype facts) and says to review any code that blurs the boundary;
`:58-60` warns that host-side macro serialisation and kernel-side plain structs being "almost aligned"
rather than exactly aligned hides the bug until much later.

Those five are one claim in five places: **the operator is defined by an agreement among files, and no
tool checks the agreement.** That is the generalisation this entry carries, and the repair it points at
is placement — a checkable contract — rather than diligence.

The review habit, `:70-78`, is quoted in SOURCE. Its third question ("Does TilingKey routing agree with
config and dtype coverage?") is the only one of the four that names an artifact rather than a judgement,
and it is therefore the only one that could be automated.

Both files are `upstream/skills-dev-main` — one origin (RULES.md Art. 3). `simplified_key.ini` does not appear
anywhere else in this harvest's scope and its format is not documented in any file read here.

## 4 · Procedure
No device is needed for the decisive arms. The claim has an unverifiable half (the frequency) and a
verifiable half (the mechanism), and the procedure attacks the second.

Arm A — the silent no-op, provoked. Build one operator whose host tiling emits key 101 and whose kernel
tests `TILING_KEY_IS(102UL)`, with no fallback branch. Run it against a poisoned output buffer. Record:
does anything error; what is in the output buffer; does any log line name a key. §2 predicts a clean run
and untouched poison. The *poison surviving* is the deliverable — it distinguishes "the kernel wrote
garbage" from "the kernel wrote nothing", which are different repairs and look identical without a poison.

Arm B — the three-part contract, made checkable. Write a script that extracts the key set from (i) the
host tiling source, (ii) every `TILING_KEY_IS` in the kernel, and (iii) the compiled binary's registered
metadata, and reports the three-way diff. Run it over the example packages in this skill
(`euclidean_norm_package`, `xdivy_custom_package`) and over Arm A's deliberately broken build. This is the
artifact the five review items in §3 all wanted and none of them is.

Arm C — the registration-fallback case, which is the "correct but unexplained" one. Deregister the
operator from the installed config and run the same graph. Record whether the framework errors or
dispatches to another implementation. If it silently substitutes, the four-source list's third item has a
failure mode with no symptom at all, and that is the single most useful sentence this entry can produce.

Arm D — the advertised-but-unimplemented case. Declare support for a dtype the kernel's dispatch does not
handle, and run that dtype. Record the outcome class: rejected at tiling, unselected branch, or wrong
output.

Arm E — the frequency claim, addressed honestly rather than assumed. Over whatever 950 defect record is
reachable (commit messages, issue text, the upstream repo's own history), classify each fixed defect as
config-layer or compute-layer, with the classification rule fixed *before* looking. Report both counts and
the ambiguous count. This does not verify upstream's population — that population is not visible from
here — and it is the only way to get a denominator of any kind rather than repeating "a large share".

Device selection: Arms A, C and D require a run; the operator names the device index, the harness prints
it back with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run
(shared machine, ≤4 dies), and no die is substituted between arms.

## 5 · Checker — acceptance declared before the run
`key_mismatch_is_silent` (Arm A) — true iff the run exits zero, emits no line naming a key, and leaves
the poison intact. Three clauses, all required: exiting zero with garbage in the buffer is a different
(and less alarming) finding than exiting zero with the buffer untouched.

`three_way_diff_detects` (Arm B) — true iff the script reports a difference for Arm A's broken build.
Pass condition **true**.

`deregistered_operator_outcome` (Arm C) — three-valued: error, silent substitution, silent no-op.
Reported, not gated; upstream states no outcome and the class is the deliverable.

`unimplemented_dtype_outcome` (Arm D) — three-valued as in §4. Reported.

`config_share` (Arm E) — three integers (config, compute, ambiguous) plus the population's provenance.
Reported, never as a percentage without the denominator beside it. Declared this way because "a large
share" with no denominator is precisely the form this entry is trying not to reproduce.

The positive fixture, declared before the run: Arm B's script must report **no difference** for the two
unmodified example packages. If it reports differences there, it is diffing incomparable things — a
regex over the wrong file, a metadata reader returning nothing — and its detection of Arm A's planted
mismatch means only that it reports differences always. And Arm A's poison must be shown to be
overwritten by a *correctly keyed* build of the same kernel; if the poison survives that too, the kernel
never writes the buffer at all and the arm is measuring nothing. Without both, the checker reads only
"the script flagged something and the buffer was unchanged", which cannot distinguish the claim from a
broken harness — the known blind species.

Process exit codes are not the verdict for any arm: every failure mode in this entry exits zero, which is
the entry's subject.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No operator was built, no key
mismatched, no config deregistered, no defect population classified, no die contacted. The quoted
passages are re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that a TilingKey mismatch is silent, that a
deregistered operator falls back, or that any of the four named sources occurs on this toolchain — Arms A
through E are all open.

**It does not establish the frequency claim, and cannot.** "A large share" has no count, no denominator,
and no visible population: the file distils a knowledge-card source outside this harvest's scope. What
this entry carries is the *ordering advice* and the *mechanism* behind it; the share is upstream's
experience report and is recorded as one. Arm E would produce a number for a different population, not a
verification of upstream's.

It does not establish anything about `simplified_key.ini`. The file is named once in upstream and
appears nowhere else in this harvest's scope; its format, its relationship to the compiled kernel set,
and how a mismatch presents are all unknown here.

It does not establish that configuration defects are *cheaper* to find than compute defects, which is the
implicit argument for checking them first. That is plausible from §2's mechanism and is not measured.

It says nothing about how binary metadata is produced or read, which Arm B's third source requires and
which no source in scope documents.

It says nothing about the other four review items quoted in §3 (include roles, namespace hygiene,
`TilingPrepare`/`Tiling` separation, serialisation alignment) beyond recording that they share the
mechanism — none of them has an arm here and each would need its own.

BOARD is `family-claimed(unverified)`: configuration and registration are framework-layer facts, neither
file names a board token this book recognises, and no board was contacted.
