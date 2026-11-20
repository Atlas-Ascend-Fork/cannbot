```
ID:        0476-one-template-says-the-epilogue-waits-on-a-cross-core-flag-and-its-own-checklist-says-the-epilogue-contains-none
LABEL:     boundary
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/matmul/matmul-fusion-design-template.md:176-182 —
           "5. AIV Epilogue: /    5.1 CrossCoreWaitFlag(AIC→AIV)   — 等待数据就绪 /
           5.2 GM→UB: D 张量                 — DataCopy（单输入算子删除）/
           5.3 Eltwise 计算                  — ascendc API /
           5.4 UB→GM: 结果写回               — DataCopy /
           5.5 CrossCoreSetFlag(AIV→AIC)    — 通知消费完成"
SOURCE:    same file:377 — "- [ ] AIV Epilogue PipeBarrier 仅在跨 pipe 依赖处添加；Epilogue 内**无**
           `CrossCoreWaitFlag`" ; :300-302 — "// [PATTERN] AIC → AIV 同步（使用 cv_sync_constants.h
           常量） / CrossCoreSetFlag<mode, pipe>(CvSync::AIC_TO_AIV_FLAG + countId); /
           CrossCoreWaitFlag<mode, pipe>(CvSync::AIV_TO_AIC_FLAG + countId);" ; :138 —
           "> **重要**：CrossCoreFlag 常量必须复用参考工程 `cv_sync_constants.h`，禁止自定义 Flag ID。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a shipped fused epilogue class on a named 950 board that contains a `CrossCoreWaitFlag`
           call in its own body — the checklist's prohibition would then be describing something
           other than the code, and the two statements would not reconcile by layer. Equally: an
           epilogue class with no wait whose data is nevertheless ready when it runs would confirm the
           layer reading, and locating the wait that made it ready is what settles this entry.
```

# 0476 · One template says the epilogue waits on a cross-core flag, and its own checklist says the epilogue contains none

## 1 · Claim
Upstream asserts, in the computation-step listing of its matmul fusion design template, that step 5 is
the AIV epilogue and that its first sub-step is `CrossCoreWaitFlag(AIC→AIV)`, waiting for the data to
be ready, with its last sub-step being `CrossCoreSetFlag(AIV→AIC)`. Upstream asserts, in the fusion
checklist of the same file, that the AIV epilogue contains **no** `CrossCoreWaitFlag`. Upstream asserts,
in a `[PATTERN]`-annotated code snippet under the heading "AIC side", both a `CrossCoreSetFlag` and a
`CrossCoreWaitFlag`, using named constants from a shared header. Upstream asserts that cross-core flag
constants must be reused from that header and that defining custom flag IDs is forbidden. Not
established here; this entry records two statements a consumer must reconcile and the fact that
upstream never says which layer owns the wait.

## 2 · The wrong branch this removes
Without this entry an agent implementing a fused epilogue reads whichever statement it reaches first
and writes the other one's opposite. From the step listing it puts a `CrossCoreWaitFlag` at the top of
its epilogue class — and the checklist, which is the pre-review gate, then fails it. From the checklist
it writes an epilogue with no wait — and, if the wait does not exist anywhere else, reads UB before the
Fixpipe has landed, which is a race whose symptom is stale data from the previous tile.

**Both statements can be true, and that reading is the likely one.** The template separates a
`[PATTERN]` kernel/block layer from a `[USER]` epilogue class: the flags appear in the `[PATTERN]`
snippet at `:300-302`, and the three-interface epilogue contract the template points to
(`Init / GetTensor / operator()`, `:310`) has no synchronisation in it. So "step 5.1 is a wait" can
describe the AIV *phase* — what happens on the vector core before the epilogue's `operator()` is
entered — while "the epilogue contains no wait" describes the *class* the implementer writes. Under
that reading the checklist is telling the implementer not to add a second wait to code that is already
synchronised for it.

That reading is not stated anywhere. Upstream never says which layer owns the wait, and the one place
the flags appear in code is under a heading that says AIC. So the reconciliation is available and
unconfirmed, and Art. 7 forbids adjudicating it by which reading is more plausible. What this entry
removes is the third wrong branch: taking one of the two statements as the family's position and
implementing against it without noticing the other exists.

## 3 · Ground / Source
The step listing, `matmul-fusion-design-template.md:176-182`:

```
5. AIV Epilogue:
   5.1 CrossCoreWaitFlag(AIC→AIV)   — 等待数据就绪
   5.2 GM→UB: D 张量                 — DataCopy（单输入算子删除）
   5.3 Eltwise 计算                  — ascendc API
   5.4 UB→GM: 结果写回               — DataCopy
   5.5 CrossCoreSetFlag(AIV→AIC)    — 通知消费完成
```

The checklist, `:377`, inside `### 5.2 融合算子专项`:

```
- [ ] AIV Epilogue PipeBarrier 仅在跨 pipe 依赖处添加；Epilogue 内**无** `CrossCoreWaitFlag`
```

Note that the checklist item is compound: it makes a `PipeBarrier` placement rule and the
`CrossCoreWaitFlag` prohibition one tick. So a reviewer who agrees with the first half ticks the
second. That is a form defect independent of which reading is right — one checkbox cannot record two
verdicts — and it is the same species this book records at `0464` and `0474` on this same shelf.
Registered as `C-950fin-020`.

The code, `:298-302`, under the heading `#### AIC 侧（L0C → UB 恒定路径）`:

```cpp
auto ubTensor = Te::MakeTensor(Te::MakeUBmemPtr<float>(0), layoutUB);
Te::Fixpipe<FIXPIPE_TRAIT_SPLIT_M>(ubTensor, l0C, Te::FixpipeParams{FINAL_ACCUMULATION});
// [PATTERN] AIC → AIV 同步（使用 cv_sync_constants.h 常量）
CrossCoreSetFlag<mode, pipe>(CvSync::AIC_TO_AIV_FLAG + countId);
CrossCoreWaitFlag<mode, pipe>(CvSync::AIV_TO_AIC_FLAG + countId);
```

This is the only cross-core code in either matmul file, and it is on the cube side: the cube sets
`AIC_TO_AIV_FLAG` after Fixpipe and waits on `AIV_TO_AIC_FLAG` before the next tile. The vector side's
matching pair is nowhere in these two files — the template defers it to a guide in a sibling skill
(`:307-313`, `matmul_fusion_guide.md §3`, whose §3.5 is named `CV 同步机制`). So the file that
prohibits a wait in the epilogue does not show where the wait is.

Two details in the snippet are worth carrying. `mode` and `pipe` are left as template placeholders,
where the FA family on the same shelf fixes them by direction and platform (`0463`: `PIPE_FIX` for
cube-to-vector, `PIPE_MTE3` for vector-to-cube, `mode=2` on A2/A3 and `mode=4` recommended on A5). Two
families on one shelf, one specifying the arguments and one leaving them open. And `+ countId` makes
the flag ID a *base plus an offset*, so the "forbidden custom flag ID" rule at `:138`
(`CrossCoreFlag 常量必须复用参考工程 cv_sync_constants.h，禁止自定义 Flag ID`) governs the base while
the offset is computed per tile — which is how a rotating handshake is built, and which the rule's
wording does not cover. Recorded as `Q-950fin-25`.

One file, one repository: one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The first arm
needs only the reference project and no device.

**Arm 1 — where the wait is (no device).** Read the reference project the template names
(`references/matmul_fusion_kernel/` in the sibling skill) and locate every `CrossCoreWaitFlag` and
`CrossCoreSetFlag` call, recording for each the file, the class, and whether that class is annotated
`[PATTERN]` or `[USER]`. This settles the layer question by observation: if no wait appears in the
epilogue class and one appears in the kernel or block layer, the two statements reconcile as §2
describes, and the reconciliation is recorded rather than assumed.

**Arm 2 — the wait's necessity.** Build the fusion with the vector-side wait present and removed,
otherwise identical, and run at several tiles per core so the previous tile's data is available to be
read stale. Report per-tile agreement and the disagreeing-run fraction over ≥20 repetitions. If
removing it changes nothing, the handshake is carried elsewhere — by the cube's own wait on
`AIV_TO_AIC_FLAG`, which serialises the pair — and the epilogue genuinely needs none.

**Arm 3 — the flag ID rule.** Build with `CvSync::AIC_TO_AIV_FLAG` replaced by a custom base, at values
inside and outside whatever range the platform reserves. Report fault, hang or correct operation. The
FA family states the constraint as `不与平台保留 ID 冲突` (`0465`, `design.md:512`) and names no range;
this arm is where the range acquires ends, and it is the only arm that could turn `禁止自定义 Flag ID`
from a policy into a boundary.

**Arm 4 — `countId`'s rotation, retained because it may not bite.** Sweep the offset's modulus (1, 2,
4) at several tiles per core and report agreement. If a modulus of 1 — a single flag reused every
tile — is correct, the rotation is not load-bearing at this depth and `Q-950fin-25` is a documentation
gap rather than a hazard.

Refuses to assume: that a free die stays free, or that a die may be substituted; that the template's
step listing describes the code (arm 1 reads the code); that a race reproduces on one run (arms 2 and 4
report fractions over ≥20 repetitions); that a hang is a harness failure (arm 3 carries a hard timeout
and records it as an outcome); that `mode` and `pipe` are the FA family's values here — each build
echoes what it compiled with, because two families on one shelf specify them differently and this one
does not specify them at all.

## 5 · Checker — acceptance declared before the run
Verdict `wait_location` from arm 1 ∈ {`epilogue_class`, `pattern_layer`, `both`, `neither`}, declared
before the run. `pattern_layer` supports the layer reconciliation; `epilogue_class` means the checklist
does not describe the code and the OVERTURN's first half fires; `neither` means the wait is absent
entirely and arm 2 becomes the whole entry.

Verdict `wait_removal_breaks` from arm 2 ∈ {`yes`, `no`}, with the disagreeing-run fraction.

Verdict `custom_flag_outcome(id)` from arm 3 ∈ {`correct`, `fault`, `hang`}, per id, with the reserved
range inferred from the boundary between outcomes.

Verdict `rotation_required(modulus)` from arm 4, boolean per modulus.

**This checker cannot pick between the two statements and does not try.** Art. 7: the disagreement is
recorded, and what §5 declares is the *observation* that would make one reading correct — the location
of the wait in shipped code, plus whether removing the vector-side wait breaks anything.

The exit code is not the verdict: a stale-data read exits 0 with the previous tile's numbers, which at
many shapes are numerically plausible. Guards: (1) arm 2 writes a per-tile identifier into the output
so that a stale read is identified *as* the previous tile rather than as generic wrongness — an error
metric alone cannot distinguish stale data from a wrong computation; (2) **the input that makes this
checker go red**: arm 2 at one tile per core, where there is no previous tile and both builds must
agree exactly — if they differ there, the two builds differ in more than the wait and every fraction is
an artifact; (3) no result is reported without its tiles-per-core, repetition count, echoed `mode` and
`pipe`, echoed flag base and modulus, the CANN pin and the compiler command.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and no reference project was
opened. The step listing, the checklist item, the cube-side code snippet and the flag-constant rule are
file reads performed at drafting time. The observations that the checklist item is compound, that the
only cross-core code in these two files is on the cube side, that `mode` and `pipe` are left open where
the FA family fixes them, and that `+ countId` makes the ID a base plus a per-tile offset the
prohibition does not mention, are readings of upstream's own lines. **The reconciliation offered in §2
is a reading, not a finding: upstream never states which layer owns the wait, and §4 arm 1 is what
would settle it.**

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or run, and the reference project the template points to was not read —
this wave mined the tiling-design shelf, and `references/matmul_fusion_kernel/` lives in a sibling
skill outside it. The entry does not establish which of the two statements describes the shipped code;
it establishes that both are in one file and that upstream never reconciles them
(`C-950fin-020`). It does not establish that the layer reading is right, only that it is available. It
does not establish that a missing wait races — the cube's own wait on `AIV_TO_AIC_FLAG` may serialise
the pair, which arm 2 would show. It does not establish the platform-reserved flag ID range, which
neither family in this shelf enumerates. It does not establish whether the per-tile offset is permitted
under the custom-ID prohibition (`Q-950fin-25`). It does not carry `mode` or `pipe` values: this family
leaves them open, and the FA family's platform-dependent values (`0463`) are that family's and are not
restated here as if they governed this one. It covers the mxfp8 + eltwise fusion pattern only
(`0469`). No board token appears in any quoted passage, so BOARD is `family-claimed(unverified)`; §4
names 950PR/950DT only as where our run would happen. Nothing here is established for any 910-family
board.
