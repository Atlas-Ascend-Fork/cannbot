```
ID:        0241-a-simt-vf-must-return-void-and-accept-only-listed-scalars-and-gm-or-ubuf-pointers
LABEL:     boundary
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — three upstream files state the contract, all `upstream/skills-dev-main`,
           therefore ONE origin (RULES.md Art. 3). Nothing was compiled; upstream names no enforcement
           mechanism.
BOARD:     950PR, 950DT
SOURCE:    ops/ascendc-simt-programming-best-practices/references/vf-declaration.md:5-19 —
           "`__simt_vf__ __aicore__ LAUNCH_BOUND(thread_num) inline void YourKernel(...);` /
           - 必须使用 `__simt_vf__` 标记 / - `LAUNCH_BOUND(thread_num)` 可选，默认 1024 /
           - 线程数必须是编译期常量" and the parameter table: "| 指针类型 | `__gm__ T*`, `__ubuf__ T*` |
           | 标量类型 | bool, int8_t, int16_t, int32_t, int64_t, uint8_t, uint16_t, uint32_t,
           uint64_t, float, half, bfloat16_t | | 返回值 | 必须是 void |"
SOURCE:    ops/ascendc-simt-api-reference/references/overview.md:39 — "注意：asc_vf_call 启动 SIMT VF
           子任务时，子任务函数不能是类的成员函数，推荐使用普通函数或类静态函数，且入口函数必须使用
           \_\_simt\_vf\_\_ 修饰宏。传递的参数只支持裸指针和常见基本数据类型，不支持传递结构体、数组等。"
SOURCE:    ops/npu-arch/references/simt-arch-guide.md:164-177 — the same scalar list and
           "#### 返回值 / 必须是 `void`"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a SIMT VF that compiles and runs correctly with a struct parameter, an array parameter,
           or a non-void return — the contract would then be advice rather than a boundary.
```

# 0241 · A SIMT VF must return `void` and accept only listed scalars and `__gm__`/`__ubuf__` pointers

## 1 · Claim
Upstream asserts a declaration contract for a SIMT vector function: it carries the `__simt_vf__` marker,
optionally `LAUNCH_BOUND(thread_num)` defaulting to 1024 with the thread count a compile-time constant
(0232), and it **must return `void`**. Upstream asserts the permitted parameter set: pointers only in the
`__gm__` and `__ubuf__` address spaces, and scalars drawn from a named list — bool, the signed and
unsigned 8/16/32/64-bit integers, float, half, bfloat16_t. Upstream asserts what is excluded: structs and
arrays are not passable, and the entry function may not be a class member function (a plain function or a
static member is recommended). Not established here: nothing was compiled, and upstream names no
enforcement mechanism for any part of the contract.

## 2 · The wrong branch this removes
Every one of these restrictions is invisible from the call site and each is something an agent writes by
default.

The parameter restriction bites first and hardest. Operator code in this repo is class-shaped and
tiling-driven: the natural signature takes a `TilingData*` or a small config struct, because that is how
every host-to-kernel handoff in the surrounding material works. A SIMT VF cannot take it. The remedy —
unpack the struct at the `asc_vf_call` site and pass the fields as scalars — is a mechanical change, but
only if you know it is required; otherwise the agent produces a signature that looks exactly like every
other kernel signature it has seen.

The member-function prohibition is the same shape. The obvious home for a VF is a private method of the
operator class, and it is forbidden. Upstream names the alternatives (free function or static member),
which is what makes the rule actionable rather than merely restrictive.

The `void` return is the one that looks most like a style preference and is not. A VF runs across
thousands of threads; there is no single value to return, so a return type is not a thing the model can
express. An agent writing `__simt_vf__ inline float Reduce(...)` has written something whose meaning does
not exist — and if the toolchain accepts it, whatever it returns is one thread's value, silently.

The address-space restriction is the subtlest. A bare `T*` is not `__gm__ T*` or `__ubuf__ T*`, and in
ordinary C++ the qualifier is easy to drop through a template parameter or an `auto`. The SIMD side has
the identical rule (0254's `__ubuf__` requirement, and vec-03's separate prohibition on `LocalTensor`
wrappers), so an agent that has internalised it once has it for both models — but the two are *different*
lists: SIMD VF helpers take `__ubuf__` only, while SIMT VFs take `__gm__` as well, because SIMT reads GM
directly (0243). Merging the two contracts is a live hazard in both directions.

The unifying observation is that **all three restrictions exist because the parameters are marshalled
across a launch boundary into a thousand-thread context**. Pointers survive because they are addresses;
scalars survive because they are copyable; structs and arrays do not because there is no per-thread
storage discipline for them; and a return value has nowhere to go. Knowing the reason lets an agent
predict the boundary instead of memorising it.

## 3 · Ground / Source
`ascendc-simt-programming-best-practices/references/vf-declaration.md:1-39` — the whole file, which is
short and is the canonical statement:

> # VF 函数声明模式
>
> ## 声明规范
>
> ```cpp
> __simt_vf__ __aicore__ LAUNCH_BOUND(thread_num) inline void YourKernel(...);
> ```
>
> - 必须使用 `__simt_vf__` 标记
> - `LAUNCH_BOUND(thread_num)` 可选，默认 1024
> - 线程数必须是编译期常量（`constexpr` 或字面量）
>
> ## 参数类型支持
>
> | 类型类别 | 支持类型 |
> |---------|---------|
> | 指针类型 | `__gm__ T*`, `__ubuf__ T*` |
> | 标量类型 | bool, int8_t, int16_t, int32_t, int64_t, uint8_t, uint16_t, uint32_t, uint64_t, float, half, bfloat16_t |
> | 返回值 | 必须是 void |
>
> ## 完整声明示例
>
> ```cpp
> template <typename T>
> __simt_vf__ __aicore__ LAUNCH_BOUND(512) inline void OpComputeSimt(
>     uint64_t count, __gm__ T* x1, __gm__ T* x2, __gm__ T* y) {
>     // SIMT kernel 实现
> }
> ```
>
> ## 常量线程数声明
>
> ```cpp
> constexpr uint32_t THREAD_NUM = 512;
>
> __simt_vf__ __aicore__ LAUNCH_BOUND(THREAD_NUM) inline void OpComputeSimt(...);
> ```
>
> - `LAUNCH_BOUND(THREAD_NUM)` 与 `Simt::Dim3(THREAD_NUM)` 必须使用同一个 `constexpr` 常量

The worked example is the artefact that transmits: a free function template, `uint64_t count` as a
scalar, three `__gm__ T*` pointers, `void` return, `LAUNCH_BOUND(512)` matching a `constexpr`. Every rule
in the file is visible in six lines.

The exclusions, stated only in a different skill —
`ascendc-simt-api-reference/references/overview.md:39`:

> > 注意：asc_vf_call启动SIMT VF子任务时，子任务函数不能是类的成员函数，推荐使用普通函数或类静态函数，
> > 且入口函数必须使用 \_\_simt\_vf\_\_ 修饰宏。传递的参数只支持裸指针和常见基本数据类型，不支持传递
> > 结构体、数组等。

This is the only place the **negative** half appears — no structs, no arrays, no member functions. The
declaration file lists what is allowed and never says what happens to anything else, so an agent reading
only `vf-declaration.md` may reasonably read the table as illustrative rather than exhaustive. The two
halves of the contract live in two skills.

The third statement, `npu-arch/references/simt-arch-guide.md:164-177`, repeats the scalar list and the
`void` requirement under 数据类型速查, and `:229-253` places the VF in the call hierarchy with its own
constraint:

> #### __simt_callee__ 子函数
> ```cpp
> __simt_callee__ inline void HelperFunc(...)
> ```
> - SIMT VF 内部的辅助函数
> - 必须带 `__simt_callee__` 修饰符
>
> ### 调用约束
> - `__simt_vf__` 内只能调用 `__simt_callee__` 函数和 `constexpr` 函数
> - `__simd_vf__` 内只能调用 `__simd_callee__` 函数和 `constexpr` 函数
> - 不可跨模式调用（SIMT VF 不能调用 SIMD callee，反之亦然）

So the contract extends inward as well: a SIMT VF's *callees* are restricted too, and the two modes cannot
call across. That cross-mode prohibition is the sharpest boundary in the SIMT/SIMD relationship and it is
stated once, in a bullet list, in the architecture skill.

All three files are `upstream/skills-dev-main` — **one origin** (RULES.md Art. 3). The launch path differs
between them (`asc_vf_call` in the API reference, `Simt::VF_CALL` in the tiling design), and no source in
this scope reconciles the two names.

What upstream does not supply: any statement of what happens when the contract is violated. No
diagnostic, no error text, no compiler flag.

## 4 · Procedure
Runnable later; every arm is compile-only and needs no device, which makes this among the cheapest
verifiable entries in the block.

Arm A — one violation per build. Start from the `vf-declaration.md:23-28` worked example as the control,
which must compile. Then produce one variant per rule, each violating exactly one thing: a non-void
return type; a struct parameter; an array parameter; a bare `T*` with no address-space qualifier; a
`__simt_vf__` declared as a non-static class member; a scalar type outside the list (e.g. `double`, or a
`long double`); a missing `__simt_vf__` marker. For each record three things, not one: does it compile;
if not, does the diagnostic name the violated rule; if it does compile, does it produce correct output.
The third column is the payload — a rule that compiles is a rule whose failure mode is unknown.

Arm B — the exhaustiveness question §3 raises. The scalar table lists twelve types. Compile a VF taking
each listed type in turn (all must succeed) and then several unlisted ones — `double`, `float16` under a
different spelling, a `bfloat16x2_t`, an enum, a pointer-to-pointer. Whether unlisted types are rejected
or silently accepted determines whether the table is a whitelist or an illustration, which is exactly the
ambiguity a reader of one file is left with.

Arm C — the cross-mode prohibition, which is the sharpest rule and is stated once. Compile a
`__simt_vf__` calling a `__simd_callee__` function, and a `__simd_vf__` calling a `__simt_callee__`.
Both must fail. If either compiles, the two callee families are not disjoint and every design that
assumes they are is unguarded.

Arm D — the two launch spellings. Compile the same VF launched via `asc_vf_call` and via
`Simt::VF_CALL` and record whether both resolve and whether they impose the same parameter restrictions.
No source in this scope reconciles the two names, and a contract that differs between launch paths is
worth knowing before generating either.

No device is needed for any arm. If a board is used later to check that a tolerated violation produces
correct output, device selection is explicit: the operator names the device index, the probe prints it
back with `compiler/version.info`, occupancy is checked first (shared machine, ≤4 dies), and no die is
substituted for another.

## 5 · Checker — acceptance declared before the run
Verdict variable `rule_enforced[r]`, one per rule, **never aggregated**. Seven independent restrictions
behind one boolean is the shape that lets six enforced rules hide the one that is silently tolerated, and
the tolerated one is where the damage is.

Per rule, three declared outcomes, none reinterpretable afterwards. `enforced` — the violating build fails
**and** its diagnostic names the construct (the return type, the struct, the address space, the member
function). The checker matches diagnostic text, not exit status: "it did not compile" and "it did not
compile for the stated reason" are different results and only the second establishes enforcement.
`tolerated-wrong` — it compiles and output is wrong; reported first regardless of which rule produced it,
because a silently accepted struct parameter or non-void return is the worst case in this entry.
`tolerated-silent` — it compiles and output is correct; the rule is unsupported by anything observable
and cannot be relied on as a guard.

`scalar_table_is_whitelist` (Arm B) — pass iff all twelve listed types compile and at least one unlisted
type is rejected. If no unlisted type is rejected, the table is illustrative and the delivered skill must say so
rather than presenting it as a boundary.

`cross_mode_blocked` (Arm C) — pass iff both directions fail. This is reported separately and prominently:
it is the one rule whose violation silently mixes two execution models.

The positive fixture, declared before the run: the control build must compile **and**, when run, produce
output bit-matching a host reference. If the control fails, every "the violating build failed" result is
an artefact of the harness rather than evidence of enforcement, and all seven verdicts are void. A second
fixture: introduce a deliberate unrelated syntax error into one variant and require the harness to report
it as a *different* failure from a contract violation — if it cannot distinguish a typo from an enforced
rule, its `enforced` verdicts mean nothing. Without both, the checker reads only "some builds failed",
which is the known blind species.

Process exit codes are not the verdict anywhere: for most of these builds a non-zero exit is the expected
outcome.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was compiled,
no diagnostic was collected, and no device was contacted. Upstream states the contract and names no
enforcement mechanism, so there is not even an upstream claim about what violation produces.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that any part of the contract is enforced, or what
happens on violation — Arm A is open for all seven rules, and the `tolerated-silent` outcome is live for
every one of them. It does not establish whether the twelve-type scalar table is exhaustive or
illustrative; §3 records that the permitted list and the exclusions live in two different skills, and Arm
B is what settles it. There is **no second origin**: all three quoted files are one repo, and no installed
header was read for any of it — unlike 0244 and 0246 where the toolkit answered, and locating the
`__simt_vf__` macro's definition would be a cheap first step nobody took here. It does not reconcile the
two launch spellings, `asc_vf_call` and `Simt::VF_CALL`, which appear in different skills for what appears
to be the same operation (Arm D). It says nothing about the **SIMD** VF contract, which is 0254 and has a
different parameter rule (`__ubuf__` only, no `__gm__`) — the two contracts are similar enough to merge by
accident and upstream forbids calling across them at all. It says nothing about `LAUNCH_BOUND`'s register
consequence (0236) or its pairing with `Simt::Dim3` (0232), both of which are separate claims on separate
evidence. BOARD is 950PR and 950DT because upstream scopes SIMT to the DAV_3510 parts; a declaration
contract is plausibly board-independent, which is itself untested. Nothing transfers to the other book
(RULES.md Art. 1): upstream states SIMT hardware does not exist before DAV_3510.
