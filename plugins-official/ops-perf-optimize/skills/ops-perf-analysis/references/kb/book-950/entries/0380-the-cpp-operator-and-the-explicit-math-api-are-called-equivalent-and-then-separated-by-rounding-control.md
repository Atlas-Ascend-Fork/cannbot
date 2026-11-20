```
ID:        0380-the-cpp-operator-and-the-explicit-math-api-are-called-equivalent-and-then-separated-by-rounding-control
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (ops/ascendc-simt-programming-best-practices), which states
           both halves of the contradiction in one file eight lines apart. Nothing was compiled and no
           result was compared bit-for-bit.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-programming-best-practices/references/compute-operators.md:5 — "SIMT 支持直接
           使用 C++ 基本运算符，运算符本质是底层 API 的重载，**优先使用运算符写法**"
SOURCE:    same file:17-22 — "## 运算符 vs 显式 API / - C++ 运算符是 SIMT 底层函数 API 的重载封装，
           **功能完全等价** / - **优先使用运算符写法**（如 `a / b` 而非 `fdividef(a, b)`），更简洁易读 /
           - 显式 API（如 `fdividef`、`fmaf`、`__hfma` 等）主要用于： / - 需要精确控制舍入模式 /
           - 混合精度运算 / - 运算符无法覆盖的场景"
SOURCE:    same file:26-33 — "// ✅ 推荐：运算符写法 / y[i] = x1[i] + x2[i]; / y[i] = a[i] / b[i]; /
           y[i] = cond[i] ? x1[i] : x2[i]; / // 仅在特殊需求时使用显式 API / y[i] = fdividef(a[i], b[i]);
           // 需要特定舍入模式时" — the same pair, `a / b` and `fdividef(a, b)`, presented first as
           equivalent and then as differing in rounding.
SOURCE:    same file:7-13 — the mapping table: "| 算术运算 | +, -, *, / , % | fdividef, fmaf 等 | /
           | 位运算 | &, \|, ^, ~, <<, >> | | / | 比较运算 | ==, !=, <, >, <=, >= | | / | 逻辑运算 |
           &&, \|\|, ! | | / | 条件选择 | condition ? a : b | |" — four of the five rows name no
           underlying API at all.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 SIMT build in which `a / b` and `fdividef(a, b)` produce bit-identical results over a
           swept input range AND emit identical instructions — 功能完全等价 would then be literally true
           and the rounding-control sentence would be describing a capability the pair does not have.
           Equally overturning in the other direction: a documented statement of which rounding mode
           each form uses, which would resolve the contradiction editorially.
```

# 0380 · The C++ operator and the explicit math API are called equivalent, and then separated by rounding control

## 1 · Claim
Upstream asserts that SIMT supports the C++ built-in operators directly, that an operator is an overload
wrapper over the underlying function API, and that operator form is **功能完全等价** — functionally
completely equivalent — to the explicit API. Upstream asserts, eight lines later, that the explicit APIs
(`fdividef`, `fmaf`, `__hfma` and others) are used mainly when precise control of the rounding mode is
needed, for mixed-precision arithmetic, or where an operator cannot express the case. Upstream uses the
same pair as its worked example of both statements: `a / b` versus `fdividef(a, b)`, recommended as
interchangeable at `:18` and annotated "需要特定舍入模式时" at `:33`. Not established here: nothing was
compiled and no result was compared.

Two functions cannot be completely equivalent and differ in rounding mode. One repo states both, so
reading further cannot settle it (RULES.md Art. 3); resolution is a procedure (Art. 7).

## 2 · The wrong branch this removes
The two halves prescribe the same action — write the operator — and imply opposite things about what that
action costs.

Under 完全等价, an agent writes `a / b` everywhere and has lost nothing. Under the rounding sentence, an
agent that writes `a / b` in a precision-sensitive chain has silently accepted whatever rounding the
operator lowers to, in a kernel whose whole numerical budget may depend on it. The operator form is the
*recommended* one, so the guide's advice points at the branch whose cost it elsewhere admits exists.

That matters here more than it would in most languages, because this book has already recorded that a
division on this hardware has a mode. `Reg::Div` defaults to an `INTRINSIC` mode with up to 1 ULP of error
and requires an explicit `DivSpecificMode{precisionMode=true, algo=PRECISION_0ULP_FTZ_FALSE}` for
correctly-rounded division (0249, from the Regbase whitelist's dagger note). That is the SIMD-side API,
not the SIMT one, and nothing transfers between them — but it establishes that "which division you called"
is a real question on this family, and it makes the operator/`fdividef` pair exactly the shape where a
1 ULP difference would live. An agent that has read 0249 and then reads 完全等价 has two upstream
statements that do not obviously coexist.

The **naming** is the second signal upstream does not read. `fdividef` follows the CUDA convention where
the `f` suffix marks a *fast, lower-precision* variant — `__fdividef` in CUDA trades accuracy for speed.
If the same convention holds here, then `fdividef` is the *approximate* form and `a / b` the accurate one,
which inverts the guide's implication that the explicit API is the precision-controlled choice. If it does
not hold, the name is misleading in the other direction. Either way the guide's one worked example is the
one operation where the answer is least obvious, and the guide asserts equivalence about it twice.

The **debugging consequence** is the one that costs cycles. `common_traps.md:100-114` records "Chasing the
final output instead of the first divergence" and `:177-191` records "Using weak reference outputs". An
agent chasing a small systematic bias in a SIMT kernel will not suspect the `/` it wrote, because the guide
told it the operator is equivalent. It will suspect the accumulation order, the dtype, the reference. The
one hypothesis with a documented basis — that the two division spellings differ — is the one the document
talked it out of.

**The empty table cells are a separate gap.** Of five rows in the mapping table, only the arithmetic row
names any underlying API, and it names two (`fdividef`, `fmaf`) followed by 等. Bitwise, comparison,
logical and conditional-select rows have an empty API column. So for four of five categories, an agent that
wants the explicit form — for rounding control, mixed precision, or a case the operator cannot express —
has no name to reach for and no way to find one from this document. The escape hatch the third bullet
promises is unnavigable for most of the table.

## 3 · Ground / Source
The equivalence claim, `compute-operators.md:5` and `:17-18`:

> SIMT 支持直接使用 C++ 基本运算符，运算符本质是底层 API 的重载，**优先使用运算符写法**：

> - C++ 运算符是 SIMT 底层函数 API 的重载封装，**功能完全等价**
> - **优先使用运算符写法**（如 `a / b` 而非 `fdividef(a, b)`），更简洁易读

The separation, `:19-22`:

> - 显式 API（如 `fdividef`、`fmaf`、`__hfma` 等）主要用于：
>   - 需要精确控制舍入模式
>   - 混合精度运算
>   - 运算符无法覆盖的场景

and the example block, `:26-33`:

> ```cpp
> // ✅ 推荐：运算符写法
> y[i] = x1[i] + x2[i];
> y[i] = a[i] / b[i];
> y[i] = cond[i] ? x1[i] : x2[i];
>
> // 仅在特殊需求时使用显式 API
> y[i] = fdividef(a[i], b[i]);  // 需要特定舍入模式时
> ```

The same expression pair appears in both bullets. At `:18` `a / b` is preferred *over* `fdividef(a, b)` on
readability grounds, which presupposes they are interchangeable; at `:33` `fdividef` is annotated as the
form to use when a specific rounding mode is needed, which presupposes they are not. Eight lines apart, one
file, one worked pair.

Recorded as `C-950rem-004`.

The mapping table, `:7-13`, is quoted in SOURCE. Four of its five API cells are empty.

A third, weaker reading deserves recording rather than dismissal: 功能完全等价 might mean "computes the
same mathematical function" rather than "produces the same bits" — i.e. the operator and the API both
divide, and the rounding sentence is about *which* division. Under that reading the file is not
self-contradictory, merely imprecise, and the correct repair is one word. The reading is available and
upstream does not state it; §2 prefers the strict reading because 完全 (completely) is doing the opposite
of hedging, and because the agent-facing consequence is identical either way — an agent told the forms are
equivalent will not check.

What upstream does not supply: which rounding mode the operator lowers to; which mode `fdividef` uses;
whether `fmaf` and `__hfma` differ from `a * b + c`; whether the compiler is permitted to contract an
operator expression into an FMA (which would change results without either spelling changing); and any
name for the bitwise, comparison, logical or select families.

`__hfma` appears once and is not explained; the `__h` prefix suggests a half-precision form by CUDA
convention, which would make the third bullet's "混合精度运算" its home. That is inference from a name and
is marked as such.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3). Nothing here rests on 0249,
which is a SIMD-side (`Reg::Div`) claim cited only as evidence that division mode is a live question on
this family, not as evidence about SIMT.

## 4 · Procedure
Runnable later on `950PR`. The contradiction is decidable in one comparison, and the comparison must be
bit-level.

Arm A — the pair, bit-compared. One SIMT kernel computing `y[i] = a[i] / b[i]` and another computing
`y[i] = fdividef(a[i], b[i])`, identical otherwise, over a swept input set of at least 10⁶ pairs chosen to
stress the exponent range: normals across the full range, subnormals, values near powers of two, and
denominators near zero. Compare outputs **bit-for-bit** and record the number of differing results and the
maximum ULP difference. Bit-identical over that set is the OVERTURN's first clause.

Arm B — the instructions. Disassemble both builds and compare the generated instruction sequences. This is
the arm that decides the weak reading in §3: identical instructions mean the two spellings genuinely lower
to one operation and 完全等价 is literally true; different instructions with identical results mean the
inputs did not discriminate, which is a statement about Arm A's sweep and not about the pair.

Arm C — accuracy against a reference. Compute the same divisions in fp64 on the host and report the ULP
error distribution for each form. This is what identifies *which* form is the approximate one, which the
naming convention argument in §2 cannot settle. Predicted under the CUDA convention: `fdividef` has the
larger error. If `a / b` does, the guide's example is backwards.

Arm D — contraction. Build `y[i] = a[i] * b[i] + c[i]` and `y[i] = fmaf(a[i], b[i], c[i])` with and without
the compiler's FMA-contraction flag, and bit-compare all four. If the operator form contracts by default,
then operator and explicit-API results differ for a *third* reason — compiler policy — that upstream does
not mention at all, and that changes with build flags rather than with source.

Arm E — the empty cells. For each of the four categories with no named API, search the installed
`simt_api/` headers for a function form and report what exists. The deliverable is the table upstream's
mapping table is missing; it is a file read and needs no device.

Device selection, for Arms A through D: the operator names the device index, the harness prints it back
with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and all builds of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`differing_results` (Arm A) — the count of inputs where the two forms differ, and the maximum ULP
difference. Two numbers, reported together: one differing result at 1 ULP and a million at 4 ULP are
different findings and a single "they differ" boolean carries neither.

`identical_instructions` (Arm B) — true iff the two disassemblies match after symbol renaming. Reported
alongside `differing_results` and **never** merged with it. The combination is what carries meaning:
identical instructions and identical results confirm equivalence; different instructions and identical
results mean the sweep is inadequate; identical instructions and different results would mean the harness
is wrong.

`ulp_error_by_form` (Arm C) — the error distribution per form against the fp64 reference, reported as a
distribution and never as a mean. Which form is more accurate is the readout.

`operator_contracts` (Arm D) — true iff the operator form's result changes with the contraction flag.
Reported.

`unnamed_category_apis` (Arm E) — per category, the list of function forms found in the headers. Reported.

The positive fixture, declared before the run: Arm A must include a **control pair** — two builds of
`a / b` from identical source — whose outputs must be bit-identical. If they are not, the harness has
run-to-run nondeterminism and every difference count in the arm is uninterpretable. And Arm A's sweep must
be shown able to discriminate at all, by including a third build computing `a / b * 1.0000001f`, which
**must** differ from the control. Without that, "bit-identical" cannot be distinguished from "the
comparison is not reading the buffer" — the exact species this book records as certifying a claim with an
instrument that cannot see the difference it is testing for. Both fixtures are declared before the run,
not added after a null result.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no division
computed, no disassembly read, no ULP counted, no die contacted. The quoted passages are re-verified file
reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that `a / b` and `fdividef(a, b)` differ, that
either is more accurate, or that the operator form contracts — Arms A through E are all open. It does not
establish which rounding mode either form uses, because no source in scope states one for either.

**It does not resolve the contradiction**, and by Art. 7 it must not: both statements are one origin, eight
lines apart, and preferring one because it sounds more careful is exactly the adjudication-by-taste the law
forbids. §3 records a third, weaker reading (功能完全等价 meaning "computes the same function" rather than
"produces the same bits") under which the file is imprecise rather than contradictory; that reading is
available, upstream does not state it, and Arm B is what would decide between them.

It does not establish anything about `fmaf` or `__hfma` beyond quoting their names. The `__h` prefix
reading in §3 is inference from a naming convention borrowed from another vendor's toolkit and is marked as
such; neither function was located in a header during this harvest.

**Nothing here transfers from 0249.** That entry is about `Reg::Div`, the SIMD-side register-compute API,
and its 1 ULP default mode. It is cited only as evidence that division mode is a live question on this
family. The SIMT operator's lowering is a different mechanism and no origin in scope connects them.

It does not establish the missing API names for bitwise, comparison, logical or conditional-select
operations. Four of five table cells are empty, Arm E would fill them from headers, and until then an agent
needing an explicit form in those categories has nothing to reach for.

It says nothing about integer division, the `%` operator, or mixed-precision arithmetic — the second of
upstream's three explicit-API justifications, which this entry quotes and does not probe.

BOARD is `family-claimed(unverified)`: the file names no board token this book recognises and no board was
contacted.
