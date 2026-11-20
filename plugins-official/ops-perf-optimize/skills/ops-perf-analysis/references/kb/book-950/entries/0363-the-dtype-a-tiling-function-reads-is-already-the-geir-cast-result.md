```
ID:        0363-the-dtype-a-tiling-function-reads-is-already-the-geir-cast-result
LABEL:     knowledge
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Upstream states the
           guarantee and names no mechanism that enforces it and no path on which it does not hold.
           Nothing was compiled and no graph was traced.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/tiling_input_validation.md:42-45
           — "> **GEIR cast 说明**：GEIR 图通路中编译器可能插入 Cast 节点将 dtype 转换为算子支持的类型。
           > Tiling 函数从 `TilingContext` 获取的 dtype **已经是 cast 后的结果**，必定落入 spec.yaml
           > §2.2 支持列表——因此 tiling 侧只需校验入口实际 dtype 是否在支持列表中，不需要额外容忍
           > 未 cast 的中间 dtype。"
SOURCE:    same file:260 — "- [ ] GEIR cast：tiling 侧只校验入口实际 dtype，不额外容忍未 cast 的 dtype"
           (the same rule restated as a checklist item, i.e. it is meant to be applied, not just known)
SOURCE:    same file:50 — "每个输入有独立的 dtype 支持范围（来自 spec.yaml §2.2，按 input 逐行列出）。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a dtype observed at `TilingContext::GetInputDesc(i)->GetDataType()` that is NOT in the
           operator's declared support list — on any invocation path. One such observation makes the
           guarantee conditional, and the tiling-side dtype check becomes a real gate rather than an
           assertion.
```

# 0363 · The dtype a tiling function reads is already the GEIR cast result

## 1 · Claim
Upstream asserts that on the GEIR graph path the compiler may insert `Cast` nodes converting a tensor's
dtype into a type the operator supports. Upstream asserts the consequence for the host: the dtype a
tiling function obtains from `TilingContext` is **already** the post-cast result, and必定 — necessarily —
falls inside the operator's `spec.yaml` §2.2 support list. Upstream asserts the resulting rule: the
tiling side need only verify that the dtype it sees is in the support list, and must not add tolerance
for un-cast intermediate dtypes. Upstream restates the same rule as a checklist item, so it is meant to
be applied rather than merely known. Not established here: nothing was compiled, no graph was traced,
and upstream names no mechanism that enforces the guarantee and no invocation path on which it might not
hold.

## 2 · The wrong branch this removes
The branch this removes is a defensive one, and defensive code is the hardest kind to argue against
because it is never observed failing.

An agent writing a tiling function knows the operator's math supports fp16, bf16 and fp32. It also knows
graphs contain fp64 tensors, int8 tensors, and types nobody planned for. So it writes a dtype switch
with a fallback: if the dtype is not one of the three, promote it, or select a generic path, or accept
it and let the kernel sort it out. That fallback is dead code on the GEIR path — the cast already
happened — and dead code in a dtype switch is not inert. It is a *second route* through the tiling
function that no test exercises, that no reviewer reads carefully because it "can't happen", and that
will be selected the first time the guarantee does not hold. When that day comes, the operator does not
fail loudly at the gate; it takes the untested branch.

The mirror error is the more common one, and upstream's checklist item is aimed at it: an agent that
believes un-cast dtypes arrive will *widen the support list* to make them pass, and a widened list is a
declaration to the framework that the operator handles types it does not. `spec.yaml` §2.2 is what the
framework consults to decide whether to insert the cast at all, so tolerating an un-cast dtype in the
tiling check tells the compiler it does not need to cast — and the tolerance becomes self-fulfilling.
That is the loop worth naming: a defensive tiling check can *disable* the guarantee it was written to
defend against.

The third thing this removes is a misreading of what the remaining check is for. If the dtype is
guaranteed in-list, why check at all? Because the guarantee is scoped to *the GEIR graph path*, and
upstream says so in its first clause and never enumerates the other paths. Direct-invoke and aclnn entry
points exist in the same repo (`tests/aclnn`, `tests/geir` sit side by side in this skill's own example
packages), and nothing in the quoted paragraph asserts that a directly-invoked operator gets a cast
node. So the check is the boundary between a path where it is an assertion and paths where it is a gate,
and the rule "check only in-list membership" is right in both cases while the *reason* differs.

And the per-input structure matters here. `:50` establishes that each input has its own support range,
listed per input in `spec.yaml` §2.2, and `CheckDtypeSupport`'s signature takes a
`std::vector<std::set<ge::DataType>>` for exactly that reason. So the guarantee is per input, not per
operator: input 0 being cast into range says nothing about input 1. An agent that flattens the per-input
sets into one union — which is what the file's own calling snippet does (0362, `C-950rem-009`) — has
weakened the check in precisely the dimension the guarantee does not cover.

## 3 · Ground / Source
`tiling_input_validation.md:42-45`, in full:

> **GEIR cast 说明**：GEIR 图通路中编译器可能插入 Cast 节点将 dtype 转换为算子支持的类型。
> Tiling 函数从 `TilingContext` 获取的 dtype **已经是 cast 后的结果**，必定落入 spec.yaml
> §2.2 支持列表——因此 tiling 侧只需校验入口实际 dtype 是否在支持列表中，不需要额外容忍
> 未 cast 的中间 dtype。

Three qualifiers in one paragraph and they do not agree in strength. 可能插入 — the compiler *may*
insert a cast. 已经是 cast 后的结果 — the dtype *is* the post-cast result. 必定落入 — it *necessarily*
falls in the list. A cast that may be inserted cannot yield a dtype that necessarily falls in the list
unless the un-cast case already did, which is the benign reading: the compiler inserts a cast only when
one is needed, so either way the result is in-list. That reading is coherent and upstream does not state
it. The other reading — that 可能 admits a case where no cast is inserted and the dtype is out of list —
is what the OVERTURN is written against.

The scope clause is the load-bearing one: **GEIR 图通路中**. The guarantee is asserted for the graph
path. The skill's own example operator packages ship `tests/aclnn/`, `tests/geir/` and `tests/tiling/`
as three sibling directories (e.g.
`paradigms/broadcast/example/xdivy_custom_package/tests/`), so at least three invocation routes exist in
this material and the paragraph names one.

The checklist restatement, `:260`, is what turns it from a note into a rule an agent applies:

> - [ ] GEIR cast：tiling 侧只校验入口实际 dtype，不额外容忍未 cast 的 dtype

The per-input structure, `:50`:

> 每个输入有独立的 dtype 支持范围（来自 spec.yaml §2.2，按 input 逐行列出）。

and the signature that implements it, `:53-55`:

> ```c++
> bool CheckDtypeSupport(
>     gert::TilingContext* ctx, int64_t numInputs,
>     const std::vector<std::set<ge::DataType>>& supportedDtypesPerInput)
> ```

What upstream does not supply: any mechanism. There is no statement of *where* the cast is inserted, what
decides whether it is needed, whether the operator's `spec.yaml` is what the compiler consults, or what
happens on a path with no graph compiler. The rule is asserted and the machinery behind it is entirely
outside this scope. `spec.yaml` itself does not exist in this harvest's material.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Host-side and framework-side; no device is needed for the decisive arms.

Arm A — the guarantee, observed on the graph path. Build one operator declaring support for
{fp16, bf16, fp32}, instrument its tiling function to log
`ctx->GetInputDesc(i)->GetDataType()` for every input, and drive it from a GEIR graph with an fp64 input
and separately with an int8 input. Record the logged dtype. The claim predicts fp32 (or another in-list
type) in both cases, never fp64 or int8. One out-of-list observation is the OVERTURN.

Arm B — the other paths, which upstream does not scope. Drive the same operator through the aclnn entry
point and through direct kernel invocation with the same out-of-list input, and log the same field. If
an out-of-list dtype appears on any non-GEIR path, the guarantee is path-conditional as §2 argues, and
the dtype check is a gate on those paths — which changes what a generated tiling function must do,
because a `GRAPH_FAILED` there is the only thing standing between the caller and an untested route.

Arm C — the per-input dimension. Drive a two-input operator whose declared support differs per input —
input 0 accepts {fp16, fp32}, input 1 accepts {fp32} only — with an fp16 tensor on both. Record both
logged dtypes. If input 1 arrives as fp16, the cast is not per-input and the per-input support vector is
decorative; if it arrives as fp32, the guarantee holds at the granularity the check assumes.

Arm D — the self-fulfilling loop §2 describes. Take one operator, widen its `spec.yaml` §2.2 list to
include a type the kernel cannot actually handle, and drive a graph with that type. Record whether a
cast node is inserted. If none is, the declaration is what suppresses the cast, and the loop is real: a
tolerant declaration removes the protection. This is the arm that would justify upstream's prohibition
with a mechanism rather than an assertion.

No die is required for Arms A, C or D; Arm B's direct-invoke variant may need one, and if so the operator
names the device index, the harness prints it back with `compiler/version.info` and the resolved SoC
string, occupancy is checked (shared machine, ≤4 dies), and no die is substituted between paths.

## 5 · Checker — acceptance declared before the run
`geir_dtype_in_list` (Arm A) — true iff every logged dtype on the GEIR path is in the declared support
list. Pass condition is **true**. A single false observation overturns the guarantee, and §7 records
that this entry's whole rule rests on it.

`nongeir_dtype_in_list` (Arm B) — the same predicate, reported **separately per path**. Never merged with
Arm A: the entire question is whether the guarantee is path-conditional, and one combined pass rate would
erase it. A false on any non-GEIR path is not an overturn — it is the scope clause being confirmed, and
it is the more likely outcome.

`cast_is_per_input` (Arm C) — true iff input 1's logged dtype is in input 1's own list. Reported.
Upstream implies this by shipping a per-input signature and never states it.

`declaration_suppresses_cast` (Arm D) — true iff no cast node is inserted for the widened declaration.
Reported, not gated. This is the mechanism behind the prohibition and upstream asserts the prohibition
without it.

The positive fixture, declared before the run: Arm A must include a control input whose dtype is
**already in the list** (fp32 into an fp32-supporting input) and whose logged dtype must be fp32
unchanged. If the log shows something else, the instrumentation is reading the wrong descriptor and every
observation in the arm is void. A second fixture: the logging must be shown to be able to report an
out-of-list value at all — inject a deliberately wrong dtype directly into a `TilingContext` in a unit
test and confirm the log shows it. Without that, "every dtype was in-list" is indistinguishable from a
logger that only prints in-list values, which is the exact blind species this book keeps recording: a
check that reads only the lines it expects.

Process exit codes are not the verdict: the informative readout is the logged dtype, and a tiling
function that returns `GRAPH_FAILED` in Arm B is the interesting outcome rather than a failure.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No operator was built, no graph
compiled, no dtype logged, no cast node observed, and no die contacted. The quoted passages are
re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or traced. The entry does not establish that a cast node is ever inserted, that the
dtype at `TilingContext` is post-cast, or that it is necessarily in the support list — Arms A through D
are all open, and upstream supplies **no mechanism** for the guarantee it asserts.

It establishes nothing outside the **GEIR graph path**, which is the only path the source scopes. The
aclnn and direct-invoke routes exist in this same skill's example packages and are not covered by the
quoted paragraph; whether the guarantee holds there is Arm B and is entirely open. Treating this rule as
path-independent is the misuse this section exists to prevent.

It does not resolve the paragraph's own strength mismatch: 可能插入 (may insert) against 必定落入
(necessarily falls in). §3 records the benign reading that reconciles them and notes upstream does not
state it; this entry does not adopt either as upstream's meaning.

It says nothing about `spec.yaml` §2.2 itself, which is not in this harvest's material — its format, its
per-input structure, and whether it is what the graph compiler consults are all unverified, and Arm D
exists because the last of those is the mechanism the whole rule depends on.

It says nothing about output dtypes, about format (which the neighbouring check covers and which has no
analogous cast guarantee stated anywhere), or about what happens when the inserted `Cast` itself loses
precision — a graph-inserted fp64→fp32 cast is a numerical event that no document in scope mentions and
that would arrive at the operator as ordinary input.

BOARD is `family-claimed(unverified)`: this is host-side and framework-side behaviour, no board is named
by the source, and no board was contacted.
