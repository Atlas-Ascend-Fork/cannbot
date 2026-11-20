```
ID:        0382-tensor-addresses-must-be-parsed-on-the-device-and-never-carried-in-tiling-data
LABEL:     boundary
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (ops/ascendc-simt-programming-best-practices). Upstream
           states the prohibition with 禁止 and gives no reason, no mechanism and no symptom. Nothing
           was compiled and no address was passed either way.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-programming-best-practices/references/tensorlist-handling.md:92 — "> **注意**：
           tensor 的地址信息必须在 kernel 侧进行解析，禁止在 host 侧解析后通过 tilingdata 传递。"
SOURCE:    same file:85-90 — the selection table it sits under: "## 选择建议 / | tensor 个数 | 推荐方式 |
           原因 | / | 有限且已知 | host 侧获取 shape → tilingdata 传递 | 简单直接 | / | 不限或大量 |
           kernel 内直接解析 | 避免 tilingdata 传递大量 shape |" — the table permits host-side passing
           for SHAPE, and the note forbids it for ADDRESSES.
SOURCE:    same file:21-34 — the host-side APIs upstream does supply, all of which return shape or dtype
           and none of which returns an address: "`GetInputInstanceInfo(ir_index)`", "`GetInstanceNum()`",
           "`GetDynamicInputShape(dynamicInputIndex, tensorIndex)`", "`GetDynamicInputDataType(
           dynamicInputIndex, tensorIndex)`".
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 operator that reads a tensor address on the host, passes it through tiling data, and
           dereferences it correctly on the device over repeated runs with the framework free to
           reallocate between tiling and launch — the prohibition would then be a convention rather
           than a boundary. Conversely, an observed address change between tiling time and launch time
           would supply the mechanism upstream omits.
```

# 0382 · Tensor addresses must be parsed on the device and never carried in tiling data

## 1 · Claim
Upstream asserts a prohibition marked 禁止 — forbidden, not discouraged: a tensor's address information
must be parsed on the kernel side, and parsing it on the host and passing it through tiling data is
forbidden. Upstream asserts this immediately after a selection table that *permits* host-side handling of
the neighbouring quantity — for a small, known number of tensors, obtaining shape on the host and passing
it through tiling data is the recommended route. Upstream supplies four host-side APIs for dynamic inputs,
and all four return shape, dtype or instance count; none returns an address. Not established here: nothing
was compiled, no address was passed either way, and upstream gives **no reason, no mechanism and no
symptom**.

## 2 · The wrong branch this removes
The prohibition cuts directly against the pattern the same page recommends one line earlier, and that is
what makes it easy to violate.

An agent reading the selection table learns the principle: for a small list, do the work on the host and
hand the kernel a filled-in `TilingData`. Host-side work is easier to write, easier to test, and easier to
debug; the kernel receives numbers instead of doing pointer arithmetic over a vendor structure it must
re-derive (0381 records how badly that arithmetic can go). Having accepted that principle for shape, an
agent extends it to addresses without noticing it has crossed a line — `GM_ADDR ptrs[8]` in the tiling
struct looks exactly like `uint64_t dims[8]`.

**What upstream does not say is the whole problem.** There is no stated reason, so an agent that
"understands" the rule cannot generalise it and an agent that violates it cannot recognise the symptom.
Two mechanisms would each explain the rule and they imply very different failure modes:

- *Lifetime.* Tiling runs at a different time from launch, and the framework may allocate or reallocate
  device memory between them. An address captured at tiling time then points at freed or reassigned
  memory. Failure: a fault at a valid-looking address, or silent reads of another tensor's data —
  intermittent, allocation-order dependent, and not reproducible under a debugger that changes timing.
- *Availability.* The address may simply not exist yet at tiling time — the host-side context may expose
  shape and dtype metadata without a device pointer at all. Failure: a null or sentinel value captured and
  dereferenced, i.e. an immediate fault, which is loud.

The first is a silent-corruption class; the second is a crash class. The repair for the first is "never
capture"; the repair for the second is "capture later". An agent that guesses wrong builds the wrong
mitigation, and the evidence for which one holds is the four host-side APIs upstream lists — **none of
which returns an address** — which is weak support for the availability reading and is not a statement.

**The rule's scope is also unstated.** It says "tensor 的地址信息" in a file about `ListTensorDesc`
dynamic inputs. Ordinary (non-dynamic) operator inputs arrive at the kernel as `GM_ADDR` parameters and
nobody passes those through tiling data, so the rule may be specific to the list case — where the
*pointer array* is the thing being parsed — or it may be a general statement about device addresses. Those
have different consequences for a harness generating tiling structs, and no source in scope distinguishes
them.

**And it interacts with 0381.** The prohibition forces every dynamic-input operator onto the device-side
walker, and 0381 records that the shipped device-side walker's stride arithmetic contradicts its own layout
diagram. So the rule closes the only route that would have avoided the disputed arithmetic. That is not an
argument against the rule — a lifetime hazard is worse than a stride bug — but it means an agent obeying
this entry must also carry 0381, and the delivered skill must present them together rather than as two independent
cautions.

## 3 · Ground / Source
The prohibition, `tensorlist-handling.md:92`, in full — it is a single blockquoted line, the last line of
the file:

> > **注意**：tensor 的地址信息必须在 kernel 侧进行解析，禁止在 host 侧解析后通过 tilingdata 传递。

必须 and 禁止 in one sentence: must, and forbidden. That is the strongest modality this file uses
anywhere. It is also the only sentence in the file with no code, no table and no elaboration.

The table it follows, `:85-90`:

> ## 选择建议
>
> | tensor 个数 | 推荐方式 | 原因 |
> |------------|---------|------|
> | 有限且已知 | host 侧获取 shape → tilingdata 传递 | 简单直接 |
> | 不限或大量 | kernel 内直接解析 | 避免 tilingdata 传递大量 shape |

Note that the table's reason for the second row is 避免 tilingdata 传递大量 shape — *avoid passing a
large amount of shape through tiling data*, a size argument, not a correctness one. So the table routes by
volume and the note forbids by category, and the note's category (addresses) is not the table's quantity
(shape). Read carelessly, the two together say "pass small things on the host"; read carefully, they say
"pass shape by volume, never pass addresses at all".

The host-side APIs, `:39-44`:

> | API | 说明 |
> |-----|------|
> | `GetInputInstanceInfo(ir_index)` | 获取输入实例化对象 |
> | `GetInstanceNum()` | 获取动态输入中实际 tensor 个数 |
> | `GetDynamicInputShape(dynamicInputIndex, tensorIndex)` | 获取指定 tensor 的 shape |
> | `GetDynamicInputDataType(dynamicInputIndex, tensorIndex)` | 获取指定 tensor 的 dtype |

Four APIs, no address accessor. The worked host code at `:24-34` uses `GetComputeNodeInfo()`,
`GetInputInstanceInfo(INPUT_IDX)`, `GetInstanceNum()`, `GetDynamicInputShape(...)->GetStorageShape()` and
`GetDynamicInputDesc(...)->GetDataType()` — and again touches no pointer. (The table names
`GetDynamicInputDataType` while the code calls `GetDynamicInputDesc(...)->GetDataType()`; that is a small
mismatch in the same file, noted at 0381 §7 and not claimed here.)

That absence is the closest thing to a mechanism the file offers, and it is an absence, not a statement.
Nothing says the host *cannot* obtain an address by another route — the `TilingContext` surface is much
larger than these four calls — so the availability reading in §2 is supported by what upstream chose to
document, not by what upstream said.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on `950PR` with a dynamic-input operator. The rule has no stated mechanism, so the procedure
is built to identify which mechanism it is.

Arm A — availability. In a tiling function, attempt to obtain a device address for a dynamic input by every
route the `TilingContext` surface offers, and record for each whether it returns a pointer, a null, or does
not exist. If no route yields an address, the rule is an availability rule and §2's second mechanism holds;
the arm is a compile-and-print and needs no die beyond a launch.

Arm B — lifetime, if Arm A finds an address. Capture it at tiling time, pass it through `TilingData`, and
in the kernel compare it against the `GM_ADDR` the framework actually supplies for the same tensor. Run
200 times, interleaved with other allocations, and record how often they differ. A difference rate above
zero establishes the lifetime mechanism and gives it a magnitude; a rate of zero over 200 runs on an
otherwise idle die is **not** evidence of safety and must be reported as "not provoked", because
allocation reuse is exactly the kind of hazard an idle machine hides.

Arm C — the consequence, if Arm B shows drift. Dereference the stale address and record what happens:
fault, another tensor's data, or the correct data by luck. The class is the deliverable — §2's two
mechanisms predict different classes and a debugging agent needs to know which symptom means what.

Arm D — scope. Repeat Arms A and B for an **ordinary** (non-dynamic) input. If the address is unavailable
or unstable there too, the rule is general and applies to every operator; if ordinary inputs behave
differently, the rule is specific to the `ListTensorDesc` path and the delivered skill can scope it.

Arm E — the pressure test that decides whether Arm B's null result means anything. Repeat Arm B with the
die under concurrent allocation pressure from a second process, so that the allocator is forced to reuse
freed regions. This is the arm that turns "we did not observe drift" into either "drift occurs under
pressure" or "the address is stable even under pressure", and without it the entry's central question stays
open regardless of how many clean runs Arm B produces.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all arms of one comparison run on one named die in one session. Arm C dereferences a
possibly-stale pointer: the run is watchdogged and the die released on fault or timeout, and Arm E's
co-tenant process is started and stopped by the harness rather than left running.

## 5 · Checker — acceptance declared before the run
`host_address_available` (Arm A) — true iff any documented `TilingContext` route returns a non-null device
address for a dynamic input. Reported, not gated: this is the variable that selects which mechanism the
rest of the procedure is testing, and both values are informative.

`address_drift_rate` (Arm B) — differing runs out of 200. Reported with the explicit three-valued
interpretation declared now: > 0 establishes the lifetime mechanism; 0 is reported as **not provoked**, not
as "safe"; and a drift rate that changes between Arm B and Arm E is the finding rather than either number
alone.

`stale_deref_class` (Arm C) — three-valued: fault, wrong data, correct data. Reported. Correct data is a
live outcome and is the most dangerous one, because it is what makes the violation survive testing.

`rule_is_general` (Arm D) — true iff ordinary inputs behave the same as dynamic ones. Reported; decides the
rule's scope, which upstream does not state.

`drift_under_pressure` (Arm E) — differing runs out of 200 with a co-tenant allocator. Reported beside Arm
B's number, never merged: the pair is the measurement and either alone is not.

The positive fixture, declared before the run: Arm B's comparison must be shown able to detect a
difference, by including one run in which a deliberately wrong address (the correct one plus 4096) is
passed through `TilingData` and **must** be reported as differing. If it is not, the comparison is reading
the same value twice — the commonest instrumentation error when both sides are obtained through one
accessor — and every "no drift" result is void. And Arm E must be shown to have actually created
allocation pressure, by recording the co-tenant's allocation count; an arm labelled "under pressure" whose
co-tenant did nothing is the same null result as Arm B wearing a different name. Without both, the checker
reads only "the addresses matched", which is precisely the blind species this book keeps recording: an
instrument never shown able to produce the non-null result it is being used to rule out.

Process exit codes are not the verdict for any arm: Arm C expects a possible fault as the informative
outcome.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No tiling function was compiled, no
address obtained or passed, no pointer dereferenced, no die contacted. The quoted passages are re-verified
file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that a host-captured address goes stale, that one
is unavailable at tiling time, or that dereferencing one fails — Arms A through E are all open.

**It does not establish the rule's mechanism, and upstream states none.** §2 names two candidates —
lifetime and availability — with different failure classes and different mitigations, and the only evidence
distinguishing them is that the four host-side APIs upstream documents all return shape or dtype and none
returns an address. That is an argument from what upstream chose to document, not a statement about the
framework, and the `TilingContext` surface is larger than those four calls.

It does not establish the rule's scope. Whether 禁止 covers only `ListTensorDesc` dynamic-input addresses
or every device address is unstated, and Arm D is what would say.

It does not establish that the prohibition is enforced. Nothing in the framework is claimed to reject a
`GM_ADDR` in a `TilingData` struct; the rule is a written prohibition with no gate, which is why a
generating harness will violate it silently.

It says nothing about the *shape* half of the selection table, which permits host-side passing by volume
and whose threshold ("有限且已知" versus "不限或大量") is undefined — a routing rule with no number, of the
species 0360 records for tiling.

**It must be read with 0381.** This rule forces every dynamic-input operator onto the device-side walker,
whose stride arithmetic contradicts its own layout diagram. Obeying this entry without carrying 0381 sends
an agent onto a documented-defective path, and neither entry alone says so.

BOARD is `family-claimed(unverified)`: address lifetime is a framework and allocator property, the file
names no board token this book recognises, and no board was contacted.
