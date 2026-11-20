```
ID:        0372-the-queue-constructs-in-a-regbase-outer-shell-are-membase-leakage-in-one-file-and-normal-in-another
LABEL:     trap
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), which states both
           positions in three of its own files. One repo cannot settle this by reading more (RULES.md
           Art. 3); resolution needs a procedure (Art. 7). Nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/regbase_operator_patterns.md:105-121
           — "## Pattern 5: Membase Compatibility Boundary … When a design starts leaning on: /
           - `TPipe` / - `TQue` / - `DataCopyPad` as the central execution model / - membase-style queue
           choreography / then the task is no longer choosing a regbase pattern. At that point: / - stop
           importing membase habits into the regbase design / - re-check whether the branch or platform
           assumption is wrong"
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/regbase_programming_notes.md:49-64
           — "## 3. Do Not Collapse The Outer Shell Into The Compute Core / Real regbase kernels often
           still have an outer shell with: / - `TPipe` / - `TQue` / - `GlobalTensor` / - `LocalTensor` /
           - UB-level `CopyIn -> Compute -> CopyOut` / Those constructs do not automatically mean the
           operator has left the regbase path. / The real question is: **where does the actual math
           happen?**"
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/pitfalls/regbase_vs_membase_confusions.md:47-48
           — the confusion table: "| \"I can port a membase queue flow directly and optimize later.\" |
           That changes semantics before correctness is proven. | Re-derive the compute path from
           regbase docs, then use the template only for project skeleton concerns. |"
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/regbase_kernel_dataflow_patterns.md:36-38
           — layer 2 of the canonical structure is "**UB tile flow** / - `CopyIn -> Compute -> CopyOut`
           / - `GlobalTensor`, `LocalTensor`, `TQue`" — i.e. `TQue` is a named component of the
           canonical regbase kernel.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a compile or run in which the presence of `TPipe`/`TQue` in the outer shell changes what the
           VF body is permitted to do or what it produces — the constructs would then carry a semantic
           consequence and the disagreement would have a machine answer. Absent that, no observation
           settles it and the resolution is editorial, which is itself the finding.
```

# 0372 · The queue constructs in a regbase outer shell are membase leakage in one file and normal in another

## 1 · Claim
Upstream asserts, in its Regbase operator-patterns file, that a design leaning on `TPipe`, `TQue`,
`DataCopyPad` as the central execution model, or membase-style queue choreography has stopped choosing a
regbase pattern, and that the response is to stop importing membase habits and re-check the branch or
platform assumption. Upstream asserts, in its Regbase programming-notes file, that real regbase kernels
often still have an outer shell containing `TPipe`, `TQue`, `GlobalTensor`, `LocalTensor` and a UB-level
`CopyIn → Compute → CopyOut`, that those constructs **do not automatically mean** the operator has left
the regbase path, and that the deciding question is where the actual math happens. Upstream asserts, in
its canonical dataflow structure, that `TQue` is a named component of layer 2 of a regbase kernel. Not
established here: nothing was compiled, and the two positions are stated by one repo, which cannot settle
them by being read further.

## 2 · The wrong branch this removes
The two positions are not reconcilable by an agent reading either one alone, and they prescribe opposite
actions on the same observation.

An agent holding only Pattern 5 sees `TQue` in a kernel's outer shell and concludes the branch assumption
is wrong. Its prescribed response — "re-check whether the branch or platform assumption is wrong" — is a
*design-level* re-examination, so the repair is not a small edit. It rewrites the staging layer, or
re-routes the operator away from regbase entirely. Applied to a kernel whose VF body is a clean `Reg::*`
chain, that is a rewrite of the correct part, and `api_misuse.md:143` records exactly this outcome:
"queue- and buffer-oriented rewrites dominate the fix even when the real issue is API choice or numeric
stability".

An agent holding only the programming notes sees the same `TQue`, applies the *where does the math happen*
criterion, finds `__VEC_SCOPE__` and `RegTensor`, and passes the kernel. That is right when the math is in
the VF and wrong when the `TQue` really is the execution model — and the criterion cannot be applied
mechanically, because a kernel can contain a `__VEC_SCOPE__` doing something trivial while the real
computation is a `LocalTensor` chain around it. The programming notes name that case at `:56` and give it
no test.

So the two files disagree about what a *signal* means, and both are describing the same construct in the
same layer. The disagreement is not about a fact — it is about whether presence is evidence. Pattern 5
treats the constructs as a symptom; the programming notes treat them as normal furniture and locate the
symptom elsewhere.

Three details sharpen it rather than dissolving it.

Pattern 5's phrase is "**as the central execution model**" for `DataCopyPad`, and "leaning on" for the
list as a whole — degree words. The programming notes' phrase is "do not **automatically** mean" — also a
degree word, in the opposite direction. Both authors were hedging toward the same middle, and neither
supplied the threshold, so the hedges do not meet. An agent needs a test and gets two adjectives.

The dataflow file settles nothing but raises the stakes: `TQue` is listed as a component of layer 2 of the
*canonical* regbase kernel (0355). A construct that is canonical in one file of a subtree and a leakage
signal in another is not a matter of degree in the reader's experience; it is a contradiction at the point
of use.

And `regbase_vs_membase_confusions.md:47-48` sits on the Pattern 5 side while phrasing the object of the
prohibition more carefully: what it forbids is porting a *queue flow* — the compute path — and its
prescribed repair explicitly preserves the template "for project skeleton concerns". That is close to the
programming notes' position and is stated in the file whose whole purpose is to catch membase leakage. So
the confusions file, read carefully, splits the difference the other two do not.

**What this entry is for**: an agent meeting `TQue` in a regbase shell must know that its two available
authorities disagree, so that it applies the *where does the math happen* question rather than the
presence test — and knows that doing so is a choice between upstream positions, not a settled reading.

## 3 · Ground / Source
Pattern 5, `regbase_operator_patterns.md:105-121`, in full:

> ## Pattern 5: Membase Compatibility Boundary
>
> `ascend910b / membase` remains a compatibility context, but this document is not a membase design guide.
>
> When a design starts leaning on:
>
> - `TPipe`
> - `TQue`
> - `DataCopyPad` as the central execution model
> - membase-style queue choreography
>
> then the task is no longer choosing a regbase pattern. At that point:
>
> - stop importing membase habits into the regbase design
> - re-check whether the branch or platform assumption is wrong
> - fall back to the local regbase references first: `../api/index.md`, `tiling_patterns.md`, and
>   `../pitfalls/regbase_vs_membase_confusions.md`

The programming notes, `regbase_programming_notes.md:49-64`, quoted in SOURCE, with the criterion's two
arms at `:54-56`:

> - if the core math is expressed through `__VEC_SCOPE__`, `RegTensor`, `MaskReg`, and VF-safe `Reg` /
>   `MicroAPI` calls, the design is still aligned with regbase
> - if the core math is written as a `LocalTensor`-centric compute pipeline and the VF layer disappears,
>   the design is drifting away from the regbase writing style

and its own boundary list at `:66-72`, which is closer to Pattern 5 and is stated as a re-check trigger
rather than a verdict — "That does not automatically make the design wrong, but it does mean the branch
assumption should be re-checked instead of silently mixed."

The confusions table row, `regbase_vs_membase_confusions.md:47-48`, quoted in SOURCE, and its neighbour at
`:40-41`: "for regbase tasks, the template is an engineering scaffold / regbase knowledge, whitelist, and
pattern notes are the authoritative source for implementation semantics". Scaffold-versus-semantics is the
distinction that would resolve the disagreement if any of the three files applied it to `TQue` by name.
None does.

The canonical structure, `regbase_kernel_dataflow_patterns.md:36-38`, quoted in SOURCE.

All four files are `upstream/skills-dev-main` — one origin (RULES.md Art. 3). Recorded as `C-950rem-002`.
Under Art. 7 this is not adjudicated here by preferring the more authoritative-looking file; the
programming notes' criterion is *reported* in §2 as the more operational of the two positions, which is a
statement about its form, not a ruling on its correctness.

## 4 · Procedure
The disagreement is editorial unless the constructs carry a machine consequence, so the first arm asks
whether they do. If they do not, the honest outcome is that no measurement settles it — and that is a real
result, not a failed procedure.

Arm A — is there a machine answer at all. Build one operator four ways for a 3510 target: (i) `TPipe` +
`TQue` shell with a `Reg::*` VF body; (ii) raw `TBuf`/`__ubuf__` shell with the same VF body; (iii)
`TPipe` + `TQue` shell with a `LocalTensor` compute path and no VF; (iv) raw shell with a `LocalTensor`
compute path. Compare compilation, output, and disassembly of the compute region. If (i) and (ii) produce
identical compute-region instructions, the shell constructs carry no consequence for the VF and the
disagreement has no machine content — which is the predicted outcome and which makes the resolution
editorial.

Arm B — the criterion's decidability, which is 0355 Arm A applied here. Take six kernels spanning the four
shapes above plus two real ones, strip identifying comments, and have two independent readers classify each
as regbase or not using only *where does the math happen*. Record agreement. A criterion two careful
readers apply to opposite conclusions cannot resolve a disagreement between two documents.

Arm C — the presence test's error rate, which is what Pattern 5 implies. Classify the same six kernels by
the presence test alone (does the file contain `TQue` or `TPipe`). Compare against Arm B's classifications.
The disagreement count is the cost of the presence test, and it is the number a reviewer needs to decide
which authority to follow.

Arm D — the cost of the shell, which is the only quantity that could favour one position on grounds other
than taste. Run (i) and (ii) at three shapes on one die in one session with identical inputs and compare
durations and UB reservations. If the queue shell costs nothing, Pattern 5's concern is about design
clarity; if it costs, that is an argument Pattern 5 does not currently make and could.

Arm E — the editorial resolution, recorded as a proposal rather than performed. If Arm A shows no machine
consequence, the resolution belongs to upstream and the deliverable from this book is the contradiction
row plus a stated recommendation: adopt the *where does the math happen* criterion, and rewrite Pattern 5's
list as a trigger for applying it rather than as a verdict. That recommendation is what the delivered skill would
carry; it is not a finding and is marked as such.

Device selection, for Arm D: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and both builds run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`shell_affects_vf` (Arm A) — true iff builds (i) and (ii) differ in compute-region disassembly. Pass
condition is **false** — predicted. A `true` result is the OVERTURN and would mean the disagreement has a
machine answer, which would be the more interesting outcome and is named now so it cannot be dismissed as
noise.

`criterion_agreement` (Arm B) — the fraction of six kernels on which two blind readers agree using the
math-location criterion. Reported with the disagreement cases listed individually. Not averaged with Arm C.

`presence_test_error_count` (Arm C) — the number of kernels the presence test classifies differently from
Arm B's agreed classifications, reported in both directions (false leakage alarms, missed real leakage).
Both directions are required: a test that never misses and always over-flags is a different problem from
one that does the reverse, and they have opposite repairs.

`shell_cost_ratio` (Arm D) — duration ratio and UB delta, per shape, never averaged.

The positive fixture, declared before the run: Arm B must include one kernel that is unambiguously **not**
regbase — a pure `LocalTensor` compute path with no `__VEC_SCOPE__` — and both readers must classify it as
not regbase; and one that is unambiguously regbase with a raw shell, which both must accept. If either
control is misclassified, the criterion is being applied as a vocabulary test and every classification in
the arm is void. And Arm A's disassembly comparison must be shown sensitive by including a fifth build
whose VF body differs by one instruction, which **must** compare different. Without both, the checker reads
only "the readers mostly agreed and the builds looked the same", which is the known blind species — a null
result from an instrument never shown able to produce a non-null one.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no
disassembly compared, no reader classified anything, no die contacted. The four quoted passages are
re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish which upstream position is right, and by Art. 7
it must not: all four passages are one origin, and a disagreement inside one repo is resolved by a
procedure on a named board or by upstream's own revision, never by preferring the file that reads more
authoritative. §2 reports that the programming notes' criterion is the more *operational* of the two —
that is a statement about its form, not a ruling.

It does not establish that the disagreement has a machine answer. Arm A predicts it does not, in which
case no measurement settles it and the resolution is editorial. An entry whose central procedure predicts
its own inapplicability is disclosing a limit, not failing: what the book can supply here is the recorded
contradiction and a stated recommendation, and Arm E is marked a proposal rather than a finding for
exactly that reason.

It does not establish that the *where does the math happen* criterion is decidable. Arm B is open, and it
is the same open arm as 0355's — the criterion is quoted by two entries and tested by neither.

It does not establish any threshold. Pattern 5 says "leaning on" and "as the central execution model"; the
programming notes say "do not automatically mean". Neither supplies a degree, and this entry does not
manufacture one from the two hedges.

It says nothing about `DataCopyPad`, which appears in Pattern 5's list with its own qualifier and which is
a kernel-side data-movement API whose relationship to the VF-side surface is a separate matter (0351,
0354). It says nothing about whether the queue shell costs anything (Arm D, open), and it says nothing
about SIMT kernels, which have no `TQue` layer at all (0378) and to which none of the four passages
applies.

BOARD is `family-claimed(unverified)`: the disagreement is between documents, none names a board token this
book recognises, and no board was contacted.
