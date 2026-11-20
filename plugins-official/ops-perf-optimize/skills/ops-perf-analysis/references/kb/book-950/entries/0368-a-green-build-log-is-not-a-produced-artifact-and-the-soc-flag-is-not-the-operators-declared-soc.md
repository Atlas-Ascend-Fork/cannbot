```
ID:        0368-a-green-build-log-is-not-a-produced-artifact-and-the-soc-flag-is-not-the-operators-declared-soc
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), which states the
           pattern in two of its own files. Upstream names four false-progress shapes and no
           diagnostic for any of them. Nothing was built.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/regbase_build_notes.md:71-80
           — "## 5. Common False-Progress Patterns / Watch for these: / - `--soc=ascend950` passed, but
           the operator does not advertise `ascend950` / - `_def.cpp` or config registration disagrees
           with CMake support / - build completes, but no fresh kernel artifact is produced / -
           package installs, but the operator is absent from the installed config / Treat each of these
           as a structural problem, not as a numeric or API problem."
SOURCE:    same file:60-69 — "## 4. Verify Artifacts, Not Just Exit Codes / After a “successful” build,
           inspect: / - expected files in `build_out/` / - generated kernel binaries or objects / -
           installable package presence / - config entries for the target operator after installation /
           This catches the common failure mode where the log is green but the operator route was
           skipped or never registered."
SOURCE:    same file:38-47 — "## 2. Remember The `ascend950` Source Layout … - regbase kernel entry
           usually lives in `_apt.cpp` / - host tiling lives under `op_host/arch35/` / - operator CMake
           must declare `ascend950` / - the config path that registers the operator must agree with the
           same SoC assumption / If these files disagree, the build can look partially healthy while
           the target route is actually absent."
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/process_memory_cards.md:50-59
           — "## Card 3: Compile Success Is Not Artifact Success / Compilation logs can claim success
           while the actual artifact set is incomplete. Re-check: / - kernel objects or generated
           binaries really exist / - the expected output directory contains fresh files / - the
           targeted operator was actually included in the build scope / - the selected SoC is supported
           by the maintainer's config / The practical lesson is simple: trust produced files and
           installable artifacts more than a green-looking console line."
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build in which `--soc=ascend950` is passed to an operator whose `_def.cpp` and CMake do NOT
           declare `ascend950`, and which nevertheless fails loudly — naming the SoC mismatch — rather
           than completing green with no kernel artifact. The false-progress pattern would then be a
           property of an older toolchain rather than of the build system.
```

# 0368 · A green build log is not a produced artifact, and the SoC flag is not the operator's declared SoC

## 1 · Claim
Upstream asserts that a build's exit status is not evidence that the intended kernel was built. Upstream
asserts four specific false-progress shapes: `--soc=ascend950` is passed while the operator does not
advertise `ascend950`; `_def.cpp` or the config registration disagrees with what CMake declares as
supported; the build completes with no fresh kernel artifact produced; the package installs while the
operator is absent from the installed config. Upstream asserts the corresponding check list — inspect
`build_out/`, the generated kernel binaries or objects, the installable package, and the post-install
config entry for the target operator — and states the failure it catches: the log is green while the
operator route was skipped or never registered. Upstream asserts, in a second file, the same rule as a
context-recovery card, adding that the targeted operator must be confirmed to have been *in the build
scope*. Upstream asserts a four-part source-layout agreement for `ascend950` — kernel entry in
`_apt.cpp`, host tiling under `op_host/arch35/`, CMake declaring `ascend950`, and the registration config
agreeing with the same SoC — and asserts that disagreement leaves the build looking partially healthy
while the target route is absent. Not established here: nothing was built, and upstream names **no
diagnostic** for any of the four shapes.

## 2 · The wrong branch this removes
The branch is not a coding error. It is an epistemic one: an agent treats a zero exit status as evidence
about a kernel, when it is evidence about a build system.

The reason it holds so firmly is that the inference is normally sound. In an ordinary project the build
either produces the artifact or fails. What breaks it here is that an AscendC operator's "is this
operator in scope" decision is data — a SoC list in `_def.cpp`, a CMake declaration, a registration
config — and a build that finds no operator matching the requested SoC has nothing to compile and nothing
to complain about. The correct behaviour for a build system asked to build an empty set is success.

The consequences compound in a way that is worth spelling out, because the agent is *far* from the cause
by the time it notices.

Round one: the kernel is not rebuilt. The agent's source edit is not in the binary, so its behavioural
test reproduces the old behaviour exactly. The natural reading is "my change had no effect", which sends
it back to the source to make a bigger change.

Round two: with a stale artifact present from an earlier build, the tests do not merely fail to change —
they *pass*, if the old build was correct. So a broken change can be certified as working. This is the
species this book records elsewhere as a checker that reads only the lines it expects, applied to a whole
pipeline: the test is reading a binary that predates the change under test.

Round three: the operator is absent from the installed config. The runtime cannot find it and either
falls back or errors at launch, which reads as a framework problem or a registration problem, and the
agent debugs the wrong layer. `working_vs_failed_950_cases.md:59-68` records this as a major share of
broken 950 work — "When the math seems fine but the route still breaks, inspect config before redesigning
computation" (0369).

The SoC shape is the sharpest of the four because the flag and the declaration are in different files
maintained by different concerns. `--soc=ascend950` on the command line looks authoritative — it is the
thing the operator typed — and it is a *request*, not a fact about the operator. The operator's own
answer lives in `_def.cpp` and CMake. Upstream's four-part layout rule exists precisely because those
four places must agree and nothing checks that they do.

What this entry does **not** claim, and must not be read as claiming: that a green build means the kernel
was skipped. The four shapes are failure modes, not the normal case. The rule is that the exit code does
not *distinguish* them, so the artifact check is what does.

## 3 · Ground / Source
The four false-progress patterns, `regbase_build_notes.md:71-80`:

> ## 5. Common False-Progress Patterns
>
> Watch for these:
>
> - `--soc=ascend950` passed, but the operator does not advertise `ascend950`
> - `_def.cpp` or config registration disagrees with CMake support
> - build completes, but no fresh kernel artifact is produced
> - package installs, but the operator is absent from the installed config
>
> Treat each of these as a structural problem, not as a numeric or API problem.

The last line is the diagnostic advice and it is the useful half: all four present as behavioural or
numerical anomalies and none of them is one.

The check list, `:60-69`, quoted in SOURCE, and the layout agreement, `:38-47`:

> For `ascend950`, the high-value mental model is:
>
> - regbase kernel entry usually lives in `_apt.cpp`
> - host tiling lives under `op_host/arch35/`
> - operator CMake must declare `ascend950`
> - the config path that registers the operator must agree with the same SoC assumption
>
> If these files disagree, the build can look partially healthy while the target route is actually absent.

Note "usually" on the first item and "must" on the third: the file distinguishes convention from
requirement within one list, which is more care than most of this subtree shows. `op_host/arch35/` is
corroborated in structure by this skill's own example packages — `paradigms/reduction/example/
euclidean_norm_package/op_host/arch35/euclidean_norm_tiling_arch35.cpp` and the parallel `xdivy` package
both have exactly that layout, and both ship an `op_kernel/<name>_apt.cpp` — so the layout claim is at
least consistent with the shipped examples. That is one repo agreeing with itself, not corroboration.

The preflight list, `:27-36`, is the same discipline one step earlier — `ASCEND_HOME_PATH` set and
pointing at the intended CANN installation, the include and library directories reachable under it, the
operator in the intended repo and directory, and "the selected SoC really matches the operator's
supported compute units" — with the summary: "Build problems discovered after packaging are usually just
preflight problems found too late."

The command-selection rule, `:49-58`, is the piece that makes the artifact check affordable: full package
build, kernel-only build, debug build, clean rebuild, matched to the uncertainty — "Do not use full
packaging when the real question is whether the kernel route compiles."

`process_memory_cards.md:50-59` restates the artifact rule as a recovery card and adds one item the build
notes omit: "the targeted operator was actually included in the build scope". That is the SoC shape
stated as a scope question rather than a flag question, and it is the more general form.

Both files are `upstream/skills-dev-main` — one origin (RULES.md Art. 3). `$ASCEND_HOME_PATH` on this machine
resolves under `/usr/local/Ascend/cann-9.0.0-beta.2`, whose `compiler/version.info` reads
`Version=9.0.0-beta.2`; that is a file read establishing an installation exists, and nothing more —
no build was attempted.

## 4 · Procedure
Runnable later; no device is needed for any arm, which makes this the cheapest procedure in this block.

Arm A — the SoC shape, provoked. Take one operator whose `_def.cpp` and CMake declare `ascend950` and
build it with `--soc=ascend950`. Record the exit status, the contents of `build_out/`, and the mtime of
every produced kernel object. Then build a second copy whose `_def.cpp` declares only a different SoC,
with the same flag. Record the same three. The claim predicts: exit status identical, `build_out/`
missing the kernel object in the second case. The *pair* is the readout; the second build alone proves
nothing without the first.

Arm B — staleness, which is round two of §2. Build the operator successfully, then break the SoC
declaration and rebuild **without cleaning**. Record whether the old kernel object survives with an old
mtime, and whether any test harness in the tree would notice. This is the arm that establishes the
dangerous case: not a missing artifact, but a present and stale one.

Arm C — the diagnostic, recorded verbatim. For each of the four false-progress shapes, capture the full
build log and search it for any line naming the SoC, the operator, or the word `skip`. Upstream implies
there is none. If there is one, the whole discipline is unnecessary for that shape and the delivered skill should
point at the line instead of at a check list.

Arm D — the post-install config. Install the package from Arm A's second build and search the installed
config for the operator. Record whether it is absent, present-but-wrong-SoC, or present. §2's round three
depends on which.

Arm E — the check list, mechanised. Implement upstream's four checks as a script that runs after any
build and reports pass/fail per item. Run it over both Arm A builds. The deliverable is a check that can
be attached to a build rather than remembered, which is the form the rule needs to survive handover —
a rule that lives only in a notes file is a rule that exists only when someone reads the notes file.

No device is contacted in any arm. If a build is run on the shared machine, no die is claimed and none is
needed; that is stated so a later reader does not add a device step by analogy with the other procedures
in this block.

## 5 · Checker — acceptance declared before the run
`exit_status_distinguishes` (Arm A) — true iff the two builds' exit statuses differ. Pass condition is
**false**. Stated inverted deliberately: the entry claims the exit status carries no information here, so
the checker must be able to report that it does.

`artifact_absent_on_soc_mismatch` (Arm A) — true iff the second build produces no fresh kernel object.
Pass condition **true**. Reported separately from the exit-status verdict, because the entire claim is
that those two facts come apart, and one combined "build failed correctly" verdict would erase it.

`stale_artifact_survives` (Arm B) — true iff a kernel object from the earlier build is still present with
an unchanged mtime after the failing rebuild. Reported. This is the finding with the worst consequence
and it is a file-system observation, not a build observation.

`log_names_cause` (Arm C) — per shape, true iff the log contains a line naming the SoC, the operator, or
a skip. Reported per shape, never aggregated: one shape being diagnosed and three not is a much more
useful result than "the logs were mostly silent".

`config_state` (Arm D) — three-valued: absent, present-with-wrong-SoC, present. Reported.

The positive fixture, declared before the run: Arm A's **first** build must produce a fresh kernel object
with a current mtime. If it does not, the artifact check is looking in the wrong directory and every
"absent" result in the arm is an artefact of the check rather than of the build. And Arm E's script must
be run once against a deliberately broken build in which each of the four items is violated in turn, and
must report all four; a script validated only against a healthy build is the known blind species — a
checker pinned to "this build comes up clean" has not been shown able to go red.

Process exit codes are explicitly **not** the verdict for any arm. That is not a formality here — it is
the entry's subject.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No build was attempted, no
artifact inspected, no package installed, no config searched, no log captured. The quoted passages are
re-verified file reads of the upstream tree performed during this harvest, and the observation that this
skill's own example packages carry `op_host/arch35/` and `<name>_apt.cpp` is a directory listing of the
upstream tree — one repo agreeing with itself, not corroboration.

## 7 · Scope limits — what this entry does NOT establish
Nothing was built. The entry does not establish that any of the four false-progress shapes occurs on this
toolchain, that a SoC mismatch produces a green exit, or that stale artifacts survive a failing rebuild —
Arms A through E are all open, and upstream names **no diagnostic** for any shape, which is why every arm
is about what the build *says* as much as what it produces.

It does not establish the source layout as a requirement. Upstream writes "usually" for the `_apt.cpp`
location and "must" for the CMake declaration, and this entry preserves that difference rather than
flattening it. The example packages agreeing with the layout is one repo agreeing with itself.

It does not establish anything about which SoC string a 950 build should carry. `--soc=ascend950` is
quoted from upstream; `form/CONVENTIONS.md`'s board tokens are `950PR` and `950DT`, and the relationship
between the build-system SoC string, those tokens, and `__NPU_ARCH__` (0201, 0352) is not established by
any origin in scope.

It does not establish that the artifact check is *sufficient*. Upstream's four items check presence, not
correctness: a fresh kernel object built from the wrong source, or for the wrong architecture, passes
every one of them. Freshness and existence are the axes upstream names, and content is not.

It says nothing about the runtime behaviour of a missing operator — whether the framework falls back,
errors, or selects a different implementation — which is what §2's round three actually depends on and
which no source in scope describes. 0208 records the analogous silent-fallback shape one layer down, for
an unchecked `GetCurNpuArch()` return.

BOARD is `family-claimed(unverified)`: build-system behaviour names no board, and no board was contacted.
