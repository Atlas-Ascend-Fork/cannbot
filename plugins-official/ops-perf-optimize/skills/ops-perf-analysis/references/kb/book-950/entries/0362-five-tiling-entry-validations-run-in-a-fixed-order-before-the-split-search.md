```
ID:        0362-five-tiling-entry-validations-run-in-a-fixed-order-before-the-split-search
LABEL:     procedure
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Upstream ships the
           five check bodies as host C++ and a call sequence; nothing was compiled, and the sequence's
           own snippet calls a function the file never defines.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/tiling_input_validation.md:37-40
           — "> 异常值校验是 Tiling 入口的硬门禁，在输入预处理（如 `PadAndSqueeze`）之后、
           `FindSplitAxis` 之前执行。 / > 每个校验函数返回 `bool`，通过 `OP_CHECK_IF` 拦截不合法输入
           并返回 `GRAPH_FAILED`。 / > / > **校验顺序**：dtype → format → 维度上限 → attr 值域 →
           shape（broadcast 兼容 or 一致性）。"
SOURCE:    same file:113 — "校验每个 input/output 的 rank 不超过 `maxRank`（与 TilingKey 模板划分一致，
           Broadcast 范式 `maxRank=8`）。"
SOURCE:    same file:180-181 — "**非 broadcast 算子**（输入 shape 必须完全一致）使用此函数替代
           `CheckBroadcastShape`。 / **Broadcast 算子**两者都保留：先 `CheckShapeConsistency`（若通过
           则无需广播），再 `CheckBroadcastShape`（处理需要广播的情况）。"
SOURCE:    same file:222 vs :53 — the calling-convention snippet invokes
           `CheckDtypeSupportAndCombination(ctx_, ..., SUPPORTED_DTYPES)` with a single flat dtype
           set, while the function the file actually defines is
           `CheckDtypeSupport(ctx, numInputs, const std::vector<std::set<ge::DataType>>& supportedDtypesPerInput)`
           taking a per-input vector. The name in the snippet is defined nowhere in the file.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 tiling implementation in which permuting the five checks changes no rejection outcome
           on any input in a set that includes a bad-dtype-and-bad-shape input and a bad-format-and-
           over-rank input — the fixed order would then be a convention rather than a gate; or a build
           in which `CheckDtypeSupportAndCombination` resolves, which would mean the file omits a
           definition rather than misnaming a call.
```

# 0362 · Five tiling-entry validations run in a fixed order before the split search

## 1 · Claim
Upstream asserts a hard gate at the tiling entry, positioned after input preprocessing (`PadAndSqueeze`)
and before `FindSplitAxis`. Upstream asserts its shape: five validation functions, each returning
`bool`, each wrapped in `OP_CHECK_IF` so a failure returns `GRAPH_FAILED`. Upstream asserts the order —
dtype, then format, then maximum rank, then attribute value range, then shape (broadcast compatibility
or consistency) — and describes it as 校验顺序, a required sequence rather than a list. Upstream asserts
the per-check scope: dtype support is per input, from `spec.yaml` §2.2; format covers inputs *and*
outputs; the rank limit is `maxRank`, aligned with the TilingKey template partition and equal to 8 for
the Broadcast paradigm; attribute checks are per attribute and skipped entirely for operators with no
attributes; shape checking is `CheckShapeConsistency` for non-broadcast operators and both
`CheckShapeConsistency` then `CheckBroadcastShape` for broadcast ones. Not established here: nothing was
compiled, and upstream's own call-sequence snippet invokes a function name the file never defines.

## 2 · The wrong branch this removes
Without a stated entry gate an agent generating a tiling function writes the checks it happens to think
of, in the order it thinks of them, and both choices have consequences it will not see.

**Missing checks look like passing tests.** The inputs a generated unit test uses are the supported
ones. An operator with no rank check passes every test and faults — or silently truncates — on the first
rank-9 tensor a real graph hands it. `tiling_input_validation.md`'s own `read_when` names the reason the
gate is written down at all: "L2 exception test cases need a corresponding tiling-side rejection path".
The rejection path is a *deliverable*, not a safety net, and an operator without one fails its exception
suite for a reason that reads as a framework problem.

**Order is not cosmetic, because the checks are not independent.** Reading a shape before validating a
format means interpreting dimensions under a layout that may not be the one the caller declared. Reading
an attribute before validating rank means an axis attribute may index past the tensor. Running the
broadcast-compatibility check before the rank check means the compatibility loop runs over a rank the
template cannot handle. Each of those is a read of one field under an assumption another check has not
yet established, and the failure mode is a crash or a nonsense diagnostic inside the *later* check —
which sends the debugging agent to the wrong function. The order is a dependency order and upstream
presents it as a list.

**The two shape checks are not alternatives.** The natural reading of "broadcast compatibility or
consistency" is a choice. Upstream's actual rule at `:180-181` is that a broadcast operator runs
**both**, consistency first as a fast path — "若通过则无需广播" — then compatibility for the cases that
need it. An agent that treats them as exclusive and keeps only `CheckBroadcastShape` for a broadcast
operator loses no correctness but loses the identical-shape short circuit; an agent that keeps only
`CheckShapeConsistency` rejects every legal broadcast. The second is the expensive error and the reading
that produces it is the more natural one.

**And the snippet does not match the file.** The calling convention at `:222` calls
`CheckDtypeSupportAndCombination(ctx_, (int64_t)rawInputShapes_.size(), SUPPORTED_DTYPES)` against a
single flat `std::set<ge::DataType>`; the function defined at `:53` is `CheckDtypeSupport` taking a
`std::vector<std::set<ge::DataType>>` — one set per input. So the copyable part of the document calls a
function with a different name *and* a different parameter type from the function the document supplies.
An agent that copies the call gets an unresolved name; an agent that copies the definition and adapts
the call has silently dropped the per-input dtype partition, which is exactly the "combination"
the missing name refers to. This is the same species as C-950arch-007 and C-950arch-009: a rule stated in
prose and violated in the executable block beside it, and the repair is one generator for both, not a
correction to one instance.

## 3 · Ground / Source
The gate, `tiling_input_validation.md:37-45`:

> 异常值校验是 Tiling 入口的硬门禁，在输入预处理（如 `PadAndSqueeze`）之后、`FindSplitAxis` 之前执行。
> 每个校验函数返回 `bool`，通过 `OP_CHECK_IF` 拦截不合法输入并返回 `GRAPH_FAILED`。
>
> **校验顺序**：dtype → format → 维度上限 → attr 值域 → shape（broadcast 兼容 or 一致性）。
>
> **GEIR cast 说明**：GEIR 图通路中编译器可能插入 Cast 节点将 dtype 转换为算子支持的类型。
> Tiling 函数从 `TilingContext` 获取的 dtype **已经是 cast 后的结果**，必定落入 spec.yaml
> §2.2 支持列表——因此 tiling 侧只需校验入口实际 dtype 是否在支持列表中，不需要额外容忍
> 未 cast 的中间 dtype。

The GEIR-cast paragraph is a separate claim with its own consequences and is carried by 0363, not here.

The five bodies are shipped as host C++ (`:52-69`, `:80-108`, `:115-138`, `:147-173`, `:183-206`) and
are quoted in this entry only where they carry a fact rather than a shape. Two do.

The rank limit's provenance, `:113`: "校验每个 input/output 的 rank 不超过 `maxRank`（与 TilingKey 模板
划分一致，Broadcast 范式 `maxRank=8`）" — the limit is not a hardware bound, it is *the TilingKey template
partition*. That is the honest provenance and it matters: 8 is a software constant chosen by whoever
enumerated the templates, and the same document's calling convention hardcodes `constexpr int64_t
MAX_RANK = 8;` at `:219` without repeating the caveat. So the number appears twice, once with its
provenance and once as a bare literal, and only the literal is in the copyable block. (Compare
`sort/topk_host_tiling.md:193`'s exemplary "这些数值是性能策略，不是架构能力边界", carried by 0142 — the
same distinction, stated better, in a different skill.)

The format API note, `:76-78`, is a concrete trap and is stated as an aside:

> **CANN API 注意**：`CompileTimeTensorDesc::GetFormat()` 返回 `const StorageFormat&`，
> 不是 `ge::Format`。需用 `GetStorageFormat()` 取运行时 format，或 `GetOriginFormat()`
> 取原始 format。Tiling 侧校验运行时 format 即可。

An agent that writes `desc->GetFormat()` and compares against a `std::set<ge::Format>` is comparing a
wrapper against an enum. Whether that fails to compile or silently converts is not stated, and it is the
difference between a caught error and a format check that always passes.

The attribute rule, `:143`: "有 attr 的算子（如 `lp_norm_v2` 的 `p`/`axes`/`keepdim`）必须实现；无 attr
的算子（如 `adam`/`xdivy`）跳过。" — so the fifth check is conditional on the operator, and the
`CheckAttrValueRange` body at `:156-173` defaults a missing attribute to `r.defaultVal` rather than
rejecting it, which means an absent required attribute passes validation as its default.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3). The
`CheckDtypeSupportAndCombination` mismatch is recorded as `C-950rem-009`.

## 4 · Procedure
Host-side throughout: no device is needed for any arm, which makes this one of the cheapest procedures
in this block.

Arm A — the snippet, compiled as given. Build the calling-convention block at `:215-249` against the five
definitions the file supplies, in a translation unit with the named headers. Record whether
`CheckDtypeSupportAndCombination` resolves. Predicted: it does not. If it does, some header in the
project supplies it and the file omits a definition rather than misnaming a call — a different defect
with a different repair, and the OVERTURN's second clause.

Arm B — order dependence, which is the claim. Build the five checks into one gate and run it over an
input set in which each input violates **two** rules at once: bad dtype and bad shape; bad format and
over-rank; out-of-range attribute and incompatible broadcast. Run all 120 permutations of the five
checks over that set and record, per input, which check fires and whether any permutation crashes or
produces a diagnostic naming the wrong field. Order matters iff the reported field changes with the
permutation. This is a pure host-side sweep and is the decisive arm.

Arm C — the two shape checks. For a broadcast operator, run three variants — consistency only,
compatibility only, both in upstream's order — over a set containing identical-shape inputs, legally
broadcastable inputs, and incompatible inputs. Record acceptances and rejections. §2 predicts
compatibility-only accepts everything legal (losing only the short circuit) and consistency-only rejects
legal broadcasts. Confirming the second is what makes the "both" rule worth stating.

Arm D — the default-valued attribute. Call `CheckAttrValueRange` with the attribute absent from the
context and a `defaultVal` inside the range, and record that it passes. Then repeat with `defaultVal`
*outside* the declared `[minVal, maxVal]`. The second case is a self-inconsistent declaration that the
function as written will reject — which is arguably right and is certainly undocumented, and an agent
that fills `defaultVal` from a spec that permits an out-of-range sentinel gets a validator that rejects
its own default.

Arm E — the format wrapper. Compile `desc->GetFormat()` compared against `std::set<ge::Format>::find`
and record whether it fails to compile or converts. If it converts, the note at `:76` is describing a
silent-wrong-result trap rather than a compile error, and the delivered skill must say which.

## 5 · Checker — acceptance declared before the run
`snippet_resolves` (Arm A) — false iff `CheckDtypeSupportAndCombination` is undefined. Pass condition is
**false**, stated inverted because the entry claims a defect and the checker must be able to report its
absence.

`order_changes_verdict` (Arm B) — the number of the 120 permutations whose reported failing field differs
from upstream's order, plus the number that crash. Two integers, reported separately: a crash and a
mislabelled diagnostic are different severities and one aggregate would let the crashes hide.

`consistency_only_rejects_broadcast` (Arm C) — true iff the consistency-only variant rejects a legally
broadcastable input. Pass condition is **true**; a false result would mean the two checks are
interchangeable and upstream's "both" rule is redundant.

`default_out_of_range_rejects` (Arm D) — reported, not gated. Upstream states no intent, and both
behaviours are defensible; the deliverable is knowing which one ships.

`getformat_compiles` (Arm E) — three-valued: fails to compile, compiles and compares correctly, compiles
and compares wrongly. The third is the dangerous one and is the reason the arm exists.

The positive fixture, declared before the run: Arm B's input set must include one input that is
**entirely valid**, and every one of the 120 permutations must accept it. If any permutation rejects it,
the gate harness is faulty and every field-attribution result in the arm is void. And Arm C must include
one input that every variant must reject (incompatible shapes); a variant that accepts it is not
checking shapes at all, which no per-input pass count would reveal. Without both, the checker reads only
"some inputs were rejected", which cannot distinguish a working gate from one that rejects everything —
the known blind species.

Process exit codes are not the verdict: `GRAPH_FAILED` is the expected return for most inputs in every
arm, and the *field named in the diagnostic* is the readout.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was compiled,
no gate was run, no input rejected, and no die contacted (none is needed). The quoted passages and the
`CheckDtypeSupportAndCombination` / `CheckDtypeSupport` mismatch are re-verified file reads of the
upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that the five checks compile as written, that
the order matters, that the two shape checks behave as §2 predicts, or that `GetFormat()` misbehaves —
Arms A through E are all open.

It does not establish that the order is a *dependency* order. §2 argues it is, from what each check reads
and what each earlier check establishes; upstream states the order and gives no reason for it. That
argument is reasoning about the shipped bodies, not upstream's claim, and Arm B is what would settle it.

It does not establish `maxRank = 8` as anything but a software constant. Upstream's own provenance is
"与 TilingKey 模板划分一致" — the template partition — and the number appears again nine lines from the end
as a bare `constexpr` with no caveat. This entry does not treat 8 as an architectural limit and neither
should any consumer.

It does not establish what `PadAndSqueeze` does, whether it is the same operation as Pattern 4's collapse
(0361), or what rank the gate therefore sees. `Q-950rem` records that; no source in scope answers it.

It says nothing about kernel-side validation, which the file's `not_for` explicitly excludes, nor about
what happens to an invalid input that reaches the kernel because the host gate was skipped.

It says nothing about `spec.yaml` §2.2 or DESIGN §2.1, the two documents the dtype and attribute checks
draw their ranges from; neither exists in this harvest's scope and both are cited by upstream as the
authority for the values a real gate would use.

BOARD is `family-claimed(unverified)`: the file's frontmatter says `platform: common`, host-side tiling
code names no board, and no board was contacted.
