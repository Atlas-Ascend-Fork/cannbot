```
ID:        0355-the-three-regbase-layers-are-a-partition-of-concerns-not-a-description-of-one-file
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), which states the
           three-layer partition in two of its own files. Nothing was compiled and no kernel was
           structured this way and measured.
BOARD:     family-claimed(unverified)
           # both files carry `platform: 950-regbase` or `ascend950` in prose; neither names a board
           # token this book recognises and no board was contacted.
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/regbase_kernel_dataflow_patterns.md:29-47
           — "For kernel-side implementation, read the operator in three layers: 1. **Kernel shell**
           … 2. **UB tile flow** … 3. **VF body** …" and "Do not flatten these three layers into one
           description. The outer shell organizes work; the VF body performs the core register math."
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/regbase_programming_notes.md:49-64
           — "## 3. Do Not Collapse The Outer Shell Into The Compute Core … Real regbase kernels often
           still have an outer shell with: `TPipe` / `TQue` / `GlobalTensor` / `LocalTensor` /
           UB-level `CopyIn -> Compute -> CopyOut`. Those constructs do not automatically mean the
           operator has left the regbase path. The real question is: **where does the actual math
           happen?**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 kernel that is unambiguously regbase by every other criterion — `__VEC_SCOPE__`,
           `RegTensor`, `Reg::*` compute — and that has no distinguishable UB staging layer at all,
           the VF loading straight from `GlobalTensor`. The partition would then be a description of
           one common shape rather than a structural rule.
```

# 0355 · The three regbase layers are a partition of concerns, not a description of one file

## 1 · Claim
Upstream asserts that a regbase kernel is to be read in three layers, and names the constructs that
belong to each: the kernel shell (`__global__` entry, `TILING_KEY_IS`, `TPipe`, `Init`/`Process`); the
UB tile flow (`CopyIn → Compute → CopyOut` over `GlobalTensor`, `LocalTensor`, `TQue`); and the VF body
(`__VEC_SCOPE__`, `RegTensor`, `MaskReg`, VF-safe loads and stores, arithmetic, compare, cast, select).
Upstream asserts these must not be flattened into one description. Upstream asserts, separately, the
operational criterion for whether a kernel is still regbase: *where does the actual math happen* — if
the core math is in `__VEC_SCOPE__` over `RegTensor` with VF-safe calls, the presence of `TPipe`,
`TQue` and `LocalTensor` in the shell does **not** mean the operator has left the regbase path. Not
established here: nothing was compiled and no kernel was measured under either structure.

## 2 · The wrong branch this removes
Without the criterion, an agent has a vocabulary test and no structural one, and the vocabulary test is
wrong in both directions.

**Direction one: false alarm.** The neighbouring pitfalls documents in the same skill treat `TPipe`,
`TQue` and `DataCopyPad` as membase-leakage signals — `regbase_operator_patterns.md:109-118` says that
when a design "starts leaning on `TPipe` / `TQue` / `DataCopyPad` as the central execution model … stop
importing membase habits into the regbase design". An agent that has read that and not this will look
at a correct regbase kernel, see `TQue` in the shell, and conclude the branch is wrong. Its repair is a
rewrite of the staging layer, which is the one part that was fine, and the compute chain it does not
touch is the part that decides. That is a whole review cycle spent on the wrong layer, and it is a
documented failure shape: `api_misuse.md:143` records "queue- and buffer-oriented rewrites dominate the
fix even when the real issue is API choice or numeric stability".

**Direction two: false clearance.** The mirror case is a kernel that has `RegTensor` declared, a
`__VEC_SCOPE__` opened, and the actual arithmetic written over `LocalTensor` outside it — regbase
vocabulary applied to a membase compute path. Nothing about the file's imports distinguishes it from
the correct case. `regbase_programming_notes.md:56` names exactly this: "if the core math is written as
a `LocalTensor`-centric compute pipeline and the VF layer disappears, the design is drifting away".
The criterion is what makes the two distinguishable, and it is a criterion about *where the math is*,
not about which types appear.

**The flattening trap itself.** Beyond diagnosis, the partition has a design consequence: each layer
owns a different failure class and a different repair. Tail handling lives in the UB tile flow (the
`(i == tileNum_ - 1) ? tailTileElementNum_ : TILE_LENGTH` at `:77`); lane masking lives in the VF body
(`UpdateMask`); route selection lives in the shell (`TILING_KEY_IS`). An agent that reads the kernel as
one thing will fix a tail bug by adjusting a mask, or a routing bug by adjusting a tile count. The
partition is a debugging index as much as a design rule, and 0356 through 0359 depend on it: they are
statements about which layer a given mechanism belongs to.

## 3 · Ground / Source
`regbase_kernel_dataflow_patterns.md:29-47`, the partition in full:

> For kernel-side implementation, read the operator in three layers:
>
> 1. **Kernel shell**
>    - `__global__` entry
>    - `TILING_KEY_IS(...)`
>    - `TPipe`
>    - `Init` / `Process`
> 2. **UB tile flow**
>    - `CopyIn -> Compute -> CopyOut`
>    - `GlobalTensor`, `LocalTensor`, `TQue`
> 3. **VF body**
>    - `__VEC_SCOPE__`
>    - `RegTensor`
>    - `MaskReg`
>    - `Reg::*` / `MicroAPI::*` VF-safe loads such as `DataCopy<..., LoadDist::...>`
>    - arithmetic / compare / cast / select
>    - `Reg::*` / `MicroAPI::*` VF-safe stores such as `DataCopy<..., StoreDist::...>`
>
> Do not flatten these three layers into one description. The outer shell organizes work; the VF body
> performs the core register math.

with the minimal shell at `:51-63` and the minimal tile loop at `:72-81`:

> ```cpp
> __aicore__ inline void Process()
> {
>     for (uint32_t i = 0; i < tileNum_; i++) {
>         uint32_t count = (i == tileNum_ - 1) ? tailTileElementNum_ : TILE_LENGTH;
>         CopyIn(i, count);
>         Compute(count);
>         CopyOut(i, count);
>     }
> }
> ```

and the file's own statement of what each layer decides, `:84-90`: "This level decides: how the tile
loop runs / where the tail is handled / where UB-stage ownership changes. It does not yet explain the
register math."

The criterion, `regbase_programming_notes.md:49-64`, is in a different file and a different subtree
(`dev-experience/`, not `patterns/`), which is why an agent can easily read one without the other:

> Real regbase kernels often still have an outer shell with:
>
> - `TPipe`
> - `TQue`
> - `GlobalTensor`
> - `LocalTensor`
> - UB-level `CopyIn -> Compute -> CopyOut`
>
> Those constructs do not automatically mean the operator has left the regbase path.
>
> The real question is: **where does the actual math happen?**

Both files are `upstream/skills-dev-main` — one origin (RULES.md Art. 3). The tension with
`regbase_operator_patterns.md:105-121`'s membase-boundary framing is real and is recorded separately as
`C-950rem-002` and carried by 0372; this entry states the partition, not the disagreement.

The one point at which the partition is *not* clean, and upstream does not say so: the VF body's loads
take UB addresses (`inAddr`, `outAddr` at `:113`), so layer 3 reaches into layer 2's storage by raw
`__ubuf__` pointer, not through the `TQue` handoff that layer 2 otherwise owns. The boundary between
layers 2 and 3 is therefore an address, and 0257's 32-byte alignment requirement is a constraint that
crosses it. Upstream states the alignment rule in a third file and never connects it to the layer
boundary.

## 4 · Procedure
The partition is a structural claim, so most of it is settled by inspection rather than by a run — but
"structural claim" is not "unfalsifiable", and the arms below say what would move it.

Arm A — the criterion applied blind, which is the only way to test a diagnostic rule. Take six 950
kernels from the toolkit's own `asc/impl/adv_api/` tree and from any reference operators available,
strip identifying comments, and have two independent readers classify each as regbase or not, using
only the *where does the math happen* criterion. Record agreement. A criterion that two careful readers
apply to opposite conclusions is not a criterion; the disagreement cases are the readout, and they are
where the rule needs a clause it does not have.

Arm B — layer 3's real boundary. Compile one kernel in which the VF body is handed a `__ubuf__` pointer
obtained through `TQue`/`DeQue` and one in which it is handed a raw `TBuf` pointer, otherwise identical,
and compare. This is the arm that establishes whether the layer-2/layer-3 boundary is the address or
the queue — the partition as written is ambiguous about it, and the answer decides whether a queue is
part of the regbase design or an optional staging convenience.

Arm C — the flattening cost, which is the claim that would make the partition more than a filing
convention. Take one operator, implement it twice for `950PR` — once with a distinguishable UB tile
flow, once with the VF loading directly from GM through a `GlobalTensor` — and compare correctness and
duration at three shapes on one die in one session. If the second compiles and is correct, the
partition is a recommendation. If it is slower, the amount is the first measured reason to keep the
staging layer that any document in scope offers. If it does not compile, the partition is a hard
boundary and §7's OVERTURN is unreachable.

Device selection, for Arm C: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted between the two builds.

## 5 · Checker — acceptance declared before the run
`criterion_agreement` (Arm A) — the fraction of the six kernels on which two blind readers agree. Pass
iff 6/6. Anything less is the finding, and the disagreement cases are reported individually rather than
averaged: a rule that fails on one kernel out of six fails on the kernel that mattered.

`vf_source_is_ubuf_only` (Arm B) — true iff the raw-`TBuf` build compiles and produces correct output.
Reported, not gated: both outcomes are informative and upstream states neither.

`staging_layer_cost` (Arm C) — the duration ratio between the two implementations at each shape,
reported per shape, never averaged across shapes. Declared in advance: a ratio near 1.0 at every shape
means the staging layer is free and the partition is organisational; a ratio that moves with shape means
the layer is doing work and the partition has a performance basis nobody has written down.

The positive fixture, declared before the run: Arm A must include one kernel that is unambiguously
**not** regbase — a pure `LocalTensor` compute path with no `__VEC_SCOPE__` anywhere — and both readers
must classify it as not regbase. If either accepts it, the criterion is being applied as a vocabulary
test after all and every other classification in the arm is void. A second fixture for Arm C: the two
implementations must produce bit-identical output; if they do not, the comparison is between two
different computations and the duration ratio attributes nothing. Without both, the arms read only
"the readers mostly agreed and one build was faster", which is the known blind species.

Process exit codes are not the verdict for Arm B: a compile failure is a possible expected outcome and
the informative one.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was classified, no
translation unit compiled, no die contacted, and no duration recorded. The two quoted passages are
re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that the three-layer structure is required,
that flattening it costs anything, or that the *where does the math happen* criterion is decidable by
two readers on a real kernel — Arms A, B and C are all open. It does not establish where the boundary
between layers 2 and 3 actually is: upstream's example hands the VF a raw `__ubuf__` address, which
means the queue is not the boundary, and no source in scope says what is.

It does not resolve the tension with `regbase_operator_patterns.md`'s membase-boundary framing, which
treats the same constructs as leakage signals. That is one repo disagreeing with itself, recorded as
`C-950rem-002` and carried by 0372, and Art. 7 forbids settling it by preferring the file that reads
more authoritative.

It says nothing about when a kernel *should* grow past the three layers. Upstream lists four triggers
at `:146-152` — manual multi-tile synchronisation, manual MTE/vector overlap, a strong reduction or
transpose component, cross-core coordination — with no threshold for any of them, and this entry
deliberately does not turn a list of triggers into a rule.

It says nothing about whether the partition holds for SIMT kernels, which have no `TQue` layer at all
and reach GM directly from a thread (0378) — the vocabulary of the two models does not overlap and
nothing here transfers.

BOARD is `family-claimed(unverified)`: both files describe `ascend950 / regbase` in prose, neither names
a board token this book recognises, and no board was contacted.
