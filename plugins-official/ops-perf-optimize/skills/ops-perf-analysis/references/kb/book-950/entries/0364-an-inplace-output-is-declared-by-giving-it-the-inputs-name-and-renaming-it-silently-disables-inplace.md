```
ID:        0364-an-inplace-output-is-declared-by-giving-it-the-inputs-name-and-renaming-it-silently-disables-inplace
LABEL:     trap
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), whose card carries
           `verified: true` in its own frontmatter and names four shipped operators as evidence.
           That marker is upstream's, not ours; nothing was compiled and no address was compared.
BOARD:     family-claimed(unverified)
           # the card's frontmatter says `platform: 950-regbase`; it names no board token this book
           # recognises and no board was contacted.
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/inplace_operator_patterns.md:34
           — "Inplace 算子的核心特征是**输出复用输入的 GM 地址**（原地写回），而非分配独立输出内存。
           CANN 框架的 inplace 机制通过 **OpDef 中 `Output` 与 `Input` 同名**触发——框架据此自动把同一
           GM 地址绑定给该 Input 和 Output，运行时 kernel 收到的两个参数指向同一块 device 内存。"
SOURCE:    same file:54-66 — "inplace 输出的 `Output` 名称**必须等于**所 alias 的 `Input` 名称。框架据此
           同名关系绑定同一 GM 地址。" with "// ❌ 错误：Output 改名为 \"var_out\"，框架视为普通
           out-of-place 输出 / 分配独立内存，inplace 语义丢失" and "**禁止**把 inplace 输出命名为
           `<input_name>_out`、`<input_name>Out` 等变体。"
SOURCE:    same file:141,153-157 — the GEIR half: "**`OUTPUT` 与 `INPUT` 同名**：inplace 输出的
           `OUTPUT` 名称必须与所 alias 的 `INPUT` 名称相同。GE 框架据此识别 inplace 语义，绑定同一 GM
           地址。" and "// ❌ 错误：OUTPUT 改名为 \"var_out\"，GE 框架视为普通 out-of-place 输出"
SOURCE:    same file:70-73,166-169 — four named shipped operators: `MoeInplaceIndexAdd`
           (`Input("var")` / `Output("var")`), `QuantGroupedMatmulInplaceAdd` (`Input("y")` /
           `Output("y")`), `InplaceIndexAdd` and `InplaceMatmulAllReduceAddRmsNorm` (`.INPUT`/`.OUTPUT`
           same-named).
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 operator whose `Output` name differs from its `Input` name and whose kernel
           nevertheless receives one GM address for both — observable by printing the two `GM_ADDR`
           values and comparing them. Equal addresses under differing names would mean the binding
           comes from somewhere other than the name.
```

# 0364 · An inplace output is declared by giving it the input's name, and renaming it silently disables inplace

## 1 · Claim
Upstream asserts that an inplace operator is one whose output reuses the input's GM address rather than
receiving its own allocation. Upstream asserts the mechanism: the CANN framework triggers inplace by
`Output` and `Input` carrying **the same name** in the `OpDef`, and binds one GM address to both, so the
kernel's two parameters point at one block of device memory. Upstream asserts the same rule for the GEIR
prototype: `.OUTPUT` must be named identically to the `.INPUT` it aliases, and the GE framework
identifies inplace from that. Upstream asserts the failure: renaming the output — to `var_out`, `varOut`
or any variant — makes the framework treat it as an ordinary out-of-place output, allocate separate
memory, and lose the inplace semantics; upstream marks such variants 禁止. Upstream names four shipped
operators as evidence, two per prototype system. Not established here: nothing was compiled and no two
addresses were compared.

Upstream's own card carries `verified: true` in its frontmatter. That is upstream's marker on its own
document and is recorded, not adopted: it does not raise this entry's stratum, which is `harvested`.

## 2 · The wrong branch this removes
Every instinct an agent has about naming works against this rule.

An `OpDef` that declares `Input("var")` and `Output("var")` looks like a mistake. Two IO ports with one
name reads as a copy-paste error, and the C++ that follows *confirms the suspicion*, because the kernel
entry cannot have two parameters called `var` — so a real operator's signature genuinely does read
`GM_ADDR var, ..., GM_ADDR var_out`. An agent reading the kernel first and the `OpDef` second concludes
the `OpDef` should say `var_out` too, and "fixes" it. That single-token edit removes the inplace
semantics of the operator.

What makes it a trap rather than a bug is the failure mode. Nothing errors. The framework allocates a
second buffer, the kernel writes its result there, and the result is *correct* — as an out-of-place
operator. Every functional test comparing output to a reference passes. What is lost is invisible to
those tests: the caller's input tensor is no longer updated, so any downstream consumer reading the
original address sees stale data; and the operator now allocates memory the whole graph was written not
to need. For an optimiser state update — `InplaceApplyAdaMax` updating `var`, `m` and `v` — losing the
write-back means training silently does not progress, with every unit test green.

The second branch is the reverse and is subtler: an agent that *knows* the rule may try to reconcile the
`OpDef` and the kernel by renaming the **kernel** parameter to `var`, which does not compile, and then
conclude the rule is wrong. The rule holds at the `OpDef`/GEIR layer and the `_out` suffix belongs to the
kernel layer only; that separation is 0365's claim and is why the two are separate entries.

The third: the two prototype systems must agree. `OpDef` and `REG_OP` are separate declarations of the
same operator, and upstream states the same-name rule for both. An operator that gets it right in one and
wrong in the other is inplace on one invocation path and not on the other — which produces a bug that
reproduces under aclnn and not under GEIR, or the reverse, and that is among the hardest classes to
attribute.

The detection asymmetry is worth stating plainly: there is no positive signal for inplace anywhere in the
kernel source. The kernel receives two `GM_ADDR` values and cannot tell by inspection whether they are
equal. The only observable is a runtime address comparison, which no test in this material performs.

## 3 · Ground / Source
The mechanism, `inplace_operator_patterns.md:34`:

> Inplace 算子的核心特征是**输出复用输入的 GM 地址**（原地写回），而非分配独立输出内存。CANN 框架的
> inplace 机制通过 **OpDef 中 `Output` 与 `Input` 同名**触发——框架据此自动把同一 GM 地址绑定给该
> Input 和 Output，运行时 kernel 收到的两个参数指向同一块 device 内存。

The rule and its negative example, `:54-66`:

> inplace 输出的 `Output` 名称**必须等于**所 alias 的 `Input` 名称。框架据此同名关系绑定同一 GM 地址。
>
> ```cpp
> // ✅ 正确：inplace 算子，Output 与 Input 同名
> this->Input("var").ParamType(REQUIRED).DataType({...}).Format({...});
> this->Output("var").ParamType(REQUIRED).DataType({...}).Format({...});  // 同名 "var"
>
> // ❌ 错误：Output 改名为 "var_out"，框架视为普通 out-of-place 输出
> //        分配独立内存，inplace 语义丢失
> this->Output("var_out").ParamType(REQUIRED).DataType({...}).Format({...});
> ```
>
> **禁止**把 inplace 输出命名为 `<input_name>_out`、`<input_name>Out` 等变体。

and the GEIR restatement, `:141-157`, with the same ✅/❌ pair over `REG_OP(InplaceIndexAdd)`.

The determination rule, `:42-48`, is the part a generating agent needs first and it is deliberately
*not* a single test:

> 满足以下**任一**条件即判定为 inplace 算子：
>
> 1. **算子名含 `Inplace`**（如 `InplaceApplyAdaMax`、`InplaceIndexAdd`）——最直接的命名信号。
> 2. **需求文档明确声明**「输出复用输入地址」「原地写回」「inplace」等语义。
> 3. **`spec.yaml`** 某 output 的 `aliasing` 字段值为 `inplace_with(<input_name>)`（显式声明；注意
>    `generate_spec.py` 默认生成 `aliasing: none`，此值需 spec-generator 手动改写，不一定存在）。
>
> > 判定依据不唯一依赖 `aliasing` 字段——算子名和需求文档是更可靠的信号。

That parenthesis is the honest part and the one worth carrying: the machine-readable field
(`aliasing`) is the *least* reliable signal, because its generator defaults it to `none` and the correct
value requires a manual edit that may not have happened. So the authoritative determination is a
substring in the operator's name and a sentence in a requirements document — two human-readable signals
that no tool checks. An operator that is semantically inplace, whose author never renamed `aliasing`, and
whose name omits the word, has no signal at all.

The four named operators are the card's evidence and are quoted in SOURCE. They are file references
inside upstream's own wider repo (`ops-transformer/...`), not files in this harvest's scope, so they were
**not** re-verified: they are upstream's citations, recorded as such.

`InferShape`/`InferDataType` are explicitly outside the mechanism, `:173`: "inplace 只约束输入输出**共用
同一 GM 地址**，不约束 shape/dtype 的推导关系" — so an agent must not expect inplace to constrain the shape
inference, and an out-of-place-looking inference is not evidence against inplace.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on a named 950 board. The claim is an address-identity claim, so the procedure compares
addresses.

Arm A — the mechanism, observed. Build one minimal operator twice: `Input("var")` + `Output("var")`, and
`Input("var")` + `Output("var_out")`, identical in every other respect. In each kernel, print both
`GM_ADDR` parameters. Record whether they are equal. This is the whole claim in one comparison and it
needs no numerical reasoning at all.

Arm B — the silent-success problem, made visible. For both builds, after the kernel completes, read back
**the input tensor's original address** on the host and compare against the expected updated value. The
same-name build must show the update; the renamed build must show the original data unchanged while its
declared output buffer holds the correct result. That second observation is the entry's whole point: a
functional test comparing only the output passes in both cases.

Arm C — the two prototype systems, crossed. Build four variants: (OpDef same-name, REG_OP same-name),
(same, renamed), (renamed, same), (renamed, renamed). Drive each through both the aclnn path and the GEIR
path, and record address equality per path. §2 predicts the two mixed variants are inplace on one path
and not the other. Confirming that is what turns "keep them consistent" from tidiness into a named
failure.

Arm D — the determination signals, which is a repository measurement rather than a run. Over every
operator available in the upstream tree, record: does the name contain `Inplace`; does `spec.yaml` carry
a non-`none` `aliasing`; do `OpDef` `Input`/`Output` names collide. Cross-tabulate. Upstream states the
`aliasing` field is unreliable; the size of the disagreement between the three signals is the readout,
and the cell that matters is "names collide but `aliasing` says none".

Arm E — multi-output inplace, `:119`. Build an operator with three inplace pairs (`var`/`m`/`v`) and
confirm all three bind independently. Upstream asserts each group follows the rule independently and
gives no example; a framework that supports one alias and not three would fail here and nowhere else.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and all variants of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`addresses_equal_same_name` (Arm A) — true iff the two `GM_ADDR` values are equal in the same-name build.
Pass condition is **true**. Equality under the *renamed* build is the OVERTURN and is checked in the same
arm, reported as `addresses_equal_renamed`, pass condition **false**. Two variables, not one: a single
"inplace works" verdict could be satisfied by a framework that binds one address regardless of naming,
which is exactly the hypothesis under test.

`input_updated` (Arm B) — true iff the caller's original tensor holds the new value. Reported per build.
Separated from the address comparison on purpose: equal addresses and an observed write-back are
different facts, and an operator could receive one address and still not write to it.

`path_consistency` (Arm C) — for each of the four variants, the pair (aclnn inplace?, GEIR inplace?).
Reported as a 4×2 table, never summarised. The interesting cells are the two that disagree, and any
summary statistic erases them.

`signal_disagreement` (Arm D) — the count of operators for which the three determination signals do not
agree, broken out by which pair disagrees. Reported.

The positive fixture, declared before the run: Arm A must include a control operator that is
unambiguously **not** inplace — two differently-named IO ports with different shapes — whose addresses
must differ. If they are equal, the harness is printing the same pointer twice (a common instrumentation
error when both parameters are read through one accessor) and every equality result in the arm is void.
A second fixture for Arm B: the same-name build must be shown to change the input tensor's contents at
all — poison the buffer first and confirm the poison is gone — otherwise "input updated" cannot be
distinguished from "input already held that value". Without both, the checker reads only "two pointers
compared equal", which is the known blind species.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No operator was built, no address
printed or compared, no tensor read back, no die contacted. The quoted passages are re-verified file
reads of the upstream tree; the four named shipped operators are upstream's own citations into a repo
outside this harvest's scope and were **not** re-verified. Upstream's `verified: true` frontmatter marker
is upstream's claim about its own card and does not raise this entry's stratum.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that same-naming binds one address, that
renaming loses inplace, or that the failure is silent — Arms A through E are all open. It does not
establish that the four cited operators are named as upstream says: those files are outside this
harvest's scope and were not opened, so they are upstream's evidence for its claim and not this book's.

It does not establish anything about the `aliasing` field's semantics. Upstream states the field exists,
states its generator defaults it to `none`, and states it is the least reliable of three signals; whether
the framework reads it at all is unknown here.

It does not establish which layer performs the binding. "The framework" and "GE 框架" are named, and
whether the same-name rule is enforced at graph build, at kernel launch, or by the memory allocator is
stated nowhere — which matters, because it decides whether a mixed `OpDef`/`REG_OP` operator is inplace
on one path (Arm C).

It says nothing about **implicit** inplace — the `ForeachZeroInplace` family that declares no `OUTPUT`
at all — which is a different mechanism and is carried by 0367. Nothing here transfers to it: it does not
use the same-name rule, by upstream's own statement.

It says nothing about the kernel-side `_out` suffix, which is a C++ naming matter at a different layer
and is carried by 0365, nor about the read-after-write hazard that one address for input and output
creates, which is 0366.

BOARD is `family-claimed(unverified)`: the card says `platform: 950-regbase`, the mechanism is a
framework-level naming rule with no board dependence stated, and no board was contacted.
