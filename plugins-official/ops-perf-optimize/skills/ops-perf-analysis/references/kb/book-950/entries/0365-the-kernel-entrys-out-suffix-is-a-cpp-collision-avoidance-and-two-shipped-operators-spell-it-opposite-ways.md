```
ID:        0365-the-kernel-entrys-out-suffix-is-a-cpp-collision-avoidance-and-two-shipped-operators-spell-it-opposite-ways
LABEL:     trap
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Upstream names two
           shipped operators using opposite conventions, so the convention is upstream's own evidence
           that it is a convention. Nothing was compiled and no parameter list was resolved.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/inplace_operator_patterns.md:79-88
           — "OpDef 中 Input/Output 同名后，kernel 入口函数的 C++ 参数列表会出现同名参数——C++ 不允许同名
           参数，因此 **inplace Output 对应的 kernel 参数在 Input 参数名后加 `_out` 后缀**以区分。" …
           "- **`_out` 后缀仅是 C++ 命名层面的避让**，不改变 inplace 语义：运行时框架仍把同一 GM 地址传给
           `var` 和 `var_out`。 / - **非 inplace 的 Output 参数名**直接用 OpDef 中的 Output 名，不加后缀。
           / - 也有真实算子采用在 Input 侧加 `In` 后缀的策略（如 `yIn` + `y`），效果相同——`_out` 后缀是
           更常见的约定。"
SOURCE:    same file:92-106 — the two shipped operators, spelled oppositely:
           `moe_inplace_index_add` → `GM_ADDR var, ..., GM_ADDR var_out` (suffix on the OUTPUT);
           `quant_grouped_matmul_inplace_add` → `GM_ADDR yIn, ..., GM_ADDR y` (suffix on the INPUT),
           with both full `extern "C" __global__ __aicore__` signatures given.
SOURCE:    same file:131 — "**§3 kernel 函数签名**：inplace Output 参数加 `_out` 后缀以避 C++ 同名冲突."
           (the same convention restated as a proto.md generation rule)
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 build in which the kernel parameter name affects the binding — i.e. renaming
           `var_out` to something else, with the `OpDef` unchanged, changes which GM address the
           parameter receives. The suffix would then be part of the contract rather than a C++
           collision avoidance.
```

# 0365 · The kernel entry's `_out` suffix is a C++ collision avoidance, and two shipped operators spell it opposite ways

## 1 · Claim
Upstream asserts that once an `OpDef` names an `Output` identically to an `Input` (0364), the generated
kernel entry would need two parameters with one name, which C++ forbids — and that the convention is
therefore to suffix the inplace output's *kernel parameter* with `_out`. Upstream asserts the suffix's
status explicitly: it is a C++ naming avoidance only, it does not change the inplace semantics, and the
framework still passes the same GM address to both `var` and `var_out`. Upstream asserts that non-inplace
outputs take the `OpDef` output name unchanged, with no suffix. Upstream asserts that a second convention
exists in shipped code — suffixing the *input* side instead (`yIn` + `y`) — with the same effect, and
names `_out` as the more common of the two. Upstream gives both full kernel signatures. Not established
here: nothing was compiled and no parameter binding was observed.

## 2 · The wrong branch this removes
The suffix looks like a contract and is not one, and the two shipped operators are the proof upstream
itself supplies.

**Reading the suffix as the mechanism.** An agent that has learned "inplace outputs end in `_out`" will
use the suffix as a *detector*: scan the kernel signature, find `_out`, conclude inplace. Applied to
`quant_grouped_matmul_inplace_add` — signature `GM_ADDR x1, GM_ADDR x2, GM_ADDR scale2, GM_ADDR
groupList, GM_ADDR yIn, GM_ADDR scale1, GM_ADDR y, GM_ADDR workspace, GM_ADDR tiling` — that detector
returns *not inplace*, on an operator whose name contains `Inplace`. There is no `_out` anywhere; the
disambiguation happened on the input side. So a suffix-based detector fails on a shipped operator, and it
fails silently, returning a plausible negative.

**Reading it as writable in the other direction.** The mirror error is worse: an agent generating a
kernel signature that adds `_out` and then, "for consistency", adds it to the `OpDef` output too. That is
0364's failure — inplace silently disabled — reached through a naming-consistency instinct rather than
through a misunderstanding of the mechanism. The two entries are separate because the layers are separate
and the edits are opposite: the `OpDef` must have the collision, the kernel must not.

**Reading the parameter position as fixed.** The two signatures disagree structurally, not just
lexically. In `moe_inplace_index_add` the inplace pair is `var` (first parameter) and `var_out`
(fifth, immediately before `workspace`) — the aliased output sits with the outputs. In
`quant_grouped_matmul_inplace_add`, `yIn` is the fifth parameter and `y` is the seventh, with `scale1`
between them — an *input* appears after other inputs and its alias appears among the outputs, and the
naming does not mark which is which. A harness that infers the alias pair from adjacency, or from
position, gets the second one wrong.

**And the underlying invariant is unobservable.** Both parameters hold the same address (0364). The
suffix is the only textual difference between an inplace pair and two unrelated tensors, and it is a
convention with two spellings. There is no type, no attribute, and no comment that carries the relation
into the kernel. So the kernel author must *know* the pair, and a generated kernel that does not know it
will treat `var` and `var_out` as independent buffers — which is exactly the read-after-write hazard 0366
records.

## 3 · Ground / Source
`inplace_operator_patterns.md:79-88`, in full:

> OpDef 中 Input/Output 同名后，kernel 入口函数的 C++ 参数列表会出现同名参数——C++ 不允许同名参数，
> 因此 **inplace Output 对应的 kernel 参数在 Input 参数名后加 `_out` 后缀**以区分。
>
> ```
> OpDef:  Input("var")  +  Output("var")       // 同名 = inplace
> Kernel: GM_ADDR var, ..., GM_ADDR var_out     // Output 参数加 _out 后缀避 C++ 冲突
> ```
>
> - **`_out` 后缀仅是 C++ 命名层面的避让**，不改变 inplace 语义：运行时框架仍把同一 GM 地址传给 `var`
>   和 `var_out`。
> - **非 inplace 的 Output 参数名**直接用 OpDef 中的 Output 名，不加后缀。
> - 也有真实算子采用在 Input 侧加 `In` 后缀的策略（如 `yIn` + `y`），效果相同——`_out` 后缀是更常见的约定。

The third bullet is the one that changes the rule's status. Upstream does not present the `In` variant as
an error or a legacy form; it says 效果相同 — same effect — and calls `_out` merely 更常见, more common. So
both are correct and neither is canonical, which is the definition of a convention rather than a
contract.

The two signatures, `:97-106`:

> ```cpp
> // moe_inplace_index_add — OpDef Input("var") + Output("var") → kernel 参数 var + var_out
> extern "C" __global__ __aicore__ void moe_inplace_index_add(
>     GM_ADDR var, GM_ADDR indices, GM_ADDR updates, GM_ADDR alpha,
>     GM_ADDR var_out, GM_ADDR workspace, GM_ADDR tiling)
>
> // quant_grouped_matmul_inplace_add — OpDef Input("y") + Output("y") → kernel 参数 yIn + y
> __global__ __aicore__ void quant_grouped_matmul_inplace_add(
>     GM_ADDR x1, GM_ADDR x2, GM_ADDR scale2, GM_ADDR groupList,
>     GM_ADDR yIn, GM_ADDR scale1, GM_ADDR y, GM_ADDR workspace, GM_ADDR tiling)
> ```

Note a second, smaller difference the card does not comment on: the first carries `extern "C"` and the
second does not. Whether that is an authoring slip in the card or a real difference between the two
operators is not established, and it is recorded because a missing `extern "C"` on a kernel entry is not
a cosmetic matter.

The proto.md generation rule, `:127-131`, makes the layer separation explicit and is the cleanest
statement of it in the file:

> 1. **§1 OpDef**：inplace 输出的 `Output` 名称与 Input 同名（无 `_out` 后缀）。
> 2. **§2 dtype 组合列表**：表头列名 = OpDef 中的 IO 名（inplace 输出列名与对应 Input 列名相同）。
> 3. **§3 kernel 函数签名**：inplace Output 参数加 `_out` 后缀以避 C++ 同名冲突。

Three sections of one generated document, two naming rules, and the boundary between them is the C++
parameter list. That is the fact worth transmitting.

The two named operators are upstream's citations into `ops-transformer/`, outside this harvest's scope,
and were **not** re-verified. All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on a named 950 board; Arm A needs only a build.

Arm A — the suffix's irrelevance to binding, which is the claim. Build one inplace operator three times
with the `OpDef` unchanged and only the kernel parameter name varied: `var_out`, `varOut`, and
`somethingEntirelyDifferent`. In each, print both `GM_ADDR` values. All three must show equal addresses.
If any does not, the parameter name participates in the binding and the entry is overturned.

Arm B — the input-side convention, built rather than cited. Build a second operator following the `yIn` +
`y` form and confirm the same address equality. Upstream asserts 效果相同 and cites one shipped operator;
this arm is what makes it this book's fact rather than upstream's.

Arm C — the detector, tested against both conventions. Implement the suffix-based inplace detector §2
describes (scan the signature for `_out`) and run it over both operators. It must return inplace for the
first and — predicted — not-inplace for the second. Recording the false negative is the deliverable,
because it is the concrete argument against every tool that would otherwise be built this way.

Arm D — the alias pair, recovered correctly. Implement the detector the right way: read the `OpDef`,
find the `Input`/`Output` name collision, and map it onto the kernel signature by position. Run over both
operators and confirm it identifies `var`/`var_out` and `yIn`/`y`. This is the procedure a generating
harness actually needs and no upstream document states it; the arm is what shows it is sufficient.

Arm E — the `extern "C"` difference §3 records. Build both signatures as given and record whether the
one without `extern "C"` links against the framework's expected symbol. If it does not, the card's second
example is not copyable and that is worth knowing before it is copied.

Device selection: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`binding_independent_of_param_name` (Arm A) — true iff all three parameter-name variants produce equal
`GM_ADDR` pairs. Pass condition **true**. A false result is the OVERTURN.

`input_side_convention_works` (Arm B) — true iff the `yIn`/`y` build produces equal addresses. Reported
separately from Arm A: upstream asserts equivalence and this is the first arm that would test it, so
folding it into a combined "conventions work" verdict would hide exactly the case being checked.

`suffix_detector_false_negative` (Arm C) — true iff the suffix detector reports not-inplace for the
`yIn`/`y` operator. Pass condition **true**, stated inverted: the checker is built to confirm a defect in
a plausible tool, and a false result would mean the detector is more robust than §2 claims.

`opdef_detector_correct` (Arm D) — true iff the `OpDef`-based detector identifies the alias pair in both
operators. Pass condition **true**. This is the only arm whose green result is a recommendation rather
than a warning.

`extern_c_required` (Arm E) — reported, three-valued: links, fails to link, links with a mangled symbol
the framework does not find. The third is the silent one.

The positive fixture, declared before the run: Arms A and B must each include a **non-inplace** control
operator — differently-named `Input` and `Output`, no collision — whose two addresses must **differ**. If
they do not, the harness is printing one pointer twice and every equality result is void. And Arm C's
detector must be shown to return inplace for at least one operator, or it is returning not-inplace
unconditionally and its false negative is not a finding about suffixes. Without both, the checker reads
only "addresses matched and a detector said no", which cannot distinguish the claim from a broken
instrument — the known blind species.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No operator was built, no
parameter renamed, no address printed, no symbol linked, no die contacted. The quoted passages are
re-verified file reads of the upstream tree; the two named shipped operators are upstream's citations into
a repo outside this harvest's scope and were not re-verified.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that the parameter name is irrelevant to
binding, that the input-side convention works, or that a suffix-based detector fails on it — Arms A
through E are all open.

It does not establish that the two cited operators have the signatures upstream shows. Those files are
outside this harvest's scope; the *disagreement between the two conventions* is upstream's own statement
(`:88`, 效果相同 / 更常见) and does not depend on re-verifying the citations, but the exact parameter
lists do.

It does not establish what a generating harness should emit. Upstream calls `_out` "more common" and
names no rule; this entry does not convert a frequency observation into a directive, and Arm D's
`OpDef`-based recovery is a proposal, not upstream's practice.

It does not resolve the `extern "C"` difference between the two quoted signatures. That may be an
authoring slip in the card or a real difference; Arm E is what would say, and a kernel entry without
`extern "C"` is not obviously a cosmetic variation.

It says nothing about the `OpDef`-layer rule, which is 0364, nor about the read-after-write hazard that
one address for two parameters creates, which is 0366 — this entry is only about the naming layer, and
that narrowness is the point: the layers were separated because upstream's own generation rules separate
them.

BOARD is `family-claimed(unverified)`: a C++ parameter name is not board-dependent, the card names no
board token this book recognises, and no board was contacted.
