```
ID:        0397-the-safe-accumulation-length-is-a-per-format-constant-and-fp16-runs-out-three-decades-before-fp32
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Upstream tabulates the
           per-format figures and derives a rule from them; nothing was compiled and no sum was
           computed.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/numerical_stable/knowledge.md:18-26 —
           "### 1.2 浮点精度约束 / | 类型 | 有效位 | Machine Epsilon | 安全累加长度 | / | fp32 | ~7 位
           十进制 | 1.2e-7 | < 10⁶ | / | fp16 | ~3 位十进制 | 9.8e-4 | < 10³ | / | bf16 | ~2 位十进制 |
           7.8e-3 | < 10³ | / **推论**: fp16/bf16 输入的归约算子，累加器必须 ≥ fp32"
SOURCE:    same file:97-104 — the graded strategy: "| 长度 | 跨度 | 策略 | 开销 | / | < 10⁴ | 任意 |
           fp32 累加 | 无 | / | 10⁴ ~ 10⁶ | < 10¹⁰ | fp32（可选 pairwise） | 无 | / | 10⁴ ~ 10⁶ | ≥ 10¹⁰
           | Kahan 补偿 | +1 fp32 buffer | / | > 10⁶ | ≥ 10¹⁰ | 强烈推荐 Kahan | +1 fp32 buffer |"
SOURCE:    same file:89-95 — "### T3: 高精度累加器 / **解决问题**: fp16/bf16 累加误差快速累积 / **原理**:
           累加器提升到 fp32（或更高） / ``` / sum_fp16 += x_fp16[i]              // ❌ 误差累积 /
           sum_fp32 += Cast<fp32>(x_fp16[i])  // ✅ 稳定 / ```"
SOURCE:    same file:206-216,88 — the error model the figures rest on: "对浮点运算 `⊕`，存在相对误差
           ε ≤ machine epsilon: / ``` / fl(a ⊕ b) = (a ⊕ b)(1 + ε) / ``` / 推论: n 次加法累积误差约
           `n·ε`"; and the scoping counter-rule at `:82`: "❌ 误区 4: 所有 fp16 都升 fp32 … **正确**:
           仅涉及**归约累加**的算子需要 fp32 累加器"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an fp16 reduction on a 950 board that holds its stated accuracy well past 10³ terms — for
           instance because the hardware tree reduction's pairwise structure (950:0030) changes the error
           growth from n·ε to log(n)·ε — which would make the table's figures sequential-summation
           bounds rather than properties of the format on this hardware.
```

# 0397 · The safe accumulation length is a per-format constant, and fp16 runs out three decades before fp32

## 1 · Claim
Upstream asserts a per-format table of floating-point constraints: fp32 has about 7 decimal significant
digits, a machine epsilon of 1.2e-7 and a safe accumulation length below 10⁶; fp16 has about 3 digits,
9.8e-4, and below 10³; bf16 has about 2 digits, 7.8e-3, and below 10³. Upstream asserts the corollary: a
reduction operator with fp16 or bf16 inputs 必须 — must — use an accumulator of at least fp32. Upstream
asserts the underlying error model: for a floating-point operation the relative error is bounded by machine
epsilon, `fl(a ⊕ b) = (a ⊕ b)(1 + ε)`, and n additions accumulate roughly `n·ε`. Upstream asserts a graded
strategy indexed by length **and dynamic range**: below 10⁴ terms, fp32 accumulation at any range, no cost;
10⁴–10⁶ terms with range below 10¹⁰, fp32 with optional pairwise, no cost; 10⁴–10⁶ with range at or above
10¹⁰, Kahan compensation at the cost of one extra fp32 buffer; above 10⁶ with range at or above 10¹⁰,
Kahan strongly recommended. Upstream asserts the scope limit that keeps the rule from over-applying: only
operators involving **reduction accumulation** need an fp32 accumulator, and promoting every fp16 operator
is listed as a named misconception. Not established here: nothing was compiled and no sum was computed.

## 2 · The wrong branch this removes
Two branches, and they are opposite errors that the same table prevents.

**Under-promoting.** An fp16 reduction with an fp16 accumulator is the natural code: the tensor is fp16,
the register is fp16, the sum is fp16. At 10³ terms it is roughly at its limit; at a typical hidden
dimension of 4096 it is four times past it, and at a sequence-length reduction it is orders past. The
result is not garbage — it is a number with two correct digits, which passes a loose tolerance and fails a
tight one, and which drifts *with the shape*. That is the "scale-dependent accumulation drift" 0395's
trap 3 names as one of the three things a small shape hides, and it is why a long-axis test case exists.
And it is deterministic, so 0394's stability test correctly routes it to numerics rather than to
synchronisation — the two rules compose.

**Over-promoting.** The mirror error is the one upstream flags as 误区 4, and it is the more expensive one
in a register-based programming model. Promoting *every* fp16 operator to an fp32 compute stage costs
register state (0357 establishes that the narrow-dtype route already needs extra registers even when it
needs no extra UB), costs instructions, and buys nothing for an elementwise chain where no accumulation
occurs. The criterion is 归约累加 — reduction accumulation — not dtype. Upstream is unusually precise here
and it matters, because "widen everything to fp32" is exactly the reflex `common_traps.md:161-175` records
as trap 9 (0394 §3).

**The second axis is the one that gets dropped.** The graded table is indexed by length *and* 跨度 —
dynamic range — and the range column is what separates "fp32 is fine" from "you need Kahan" in the same
length band. At 10⁴–10⁶ terms the strategy is fp32 at range < 10¹⁰ and Kahan at range ≥ 10¹⁰: the same
length, two different answers. An agent that reads the safe-length column alone and ignores range will use
plain fp32 on a wide-range sum and lose the small terms entirely — which is the failure Kahan exists to
prevent and which no length-based rule would catch.

**Why the numbers may not transfer to this hardware, which is the entry's real caution.** The `n·ε` model
is the error growth of **sequential** summation. 0030 records that the hardware tree reduction replaces the
scalar accumulate loop and reorders the sum; pairwise or tree summation has error growing like `log(n)·ε`,
not `n·ε`. So a reduction executed by the hardware primitive may hold accuracy far past the table's
figures, and the table's own 10⁴–10⁶ row already names "可选 pairwise" as a mitigation — i.e. upstream knows
the distinction and states the safe lengths from the sequential model anyway. That is the OVERTURN, and it
means the table should be read as a bound on the *worst* summation order rather than as a property of the
format on this machine.

**And the accumulator claim and the compute claim are different.** 必须 ≥ fp32 is about the *accumulator*.
It says nothing about the input register width, the multiply width in a dot product, or the output. 0357's
six-step narrow-dtype pattern widens the whole compute stage; this rule requires only the accumulation
state. An agent that reads them together may widen more than either requires.

## 3 · Ground / Source
The constraint table, `knowledge.md:18-26`:

> ### 1.2 浮点精度约束
>
> | 类型 | 有效位 | Machine Epsilon | 安全累加长度 |
> |------|-------|----------------|------------|
> | fp32 | ~7 位十进制 | 1.2e-7 | < 10⁶ |
> | fp16 | ~3 位十进制 | 9.8e-4 | < 10³ |
> | bf16 | ~2 位十进制 | 7.8e-3 | < 10³ |
>
> **推论**: fp16/bf16 输入的归约算子，累加器必须 ≥ fp32

The three epsilons are the standard IEEE values (2⁻²³ ≈ 1.19e-7, 2⁻¹⁰ ≈ 9.77e-4, 2⁻⁸ ≈ 3.9e-3 for bf16's
8-bit significand — note bf16's stated 7.8e-3 is 2⁻⁷, i.e. the *unit in the last place* convention rather
than the half-ulp one used for the other two, or an off-by-one; the table does not say which convention it
uses and the three rows are not obviously consistent). That inconsistency is recorded rather than resolved:
it does not change the order of magnitude and it does mean the three figures were not produced by one
formula.

The safe lengths follow from `1 / ε` divided by a small factor: 1/1.2e-7 ≈ 8.3e6 against a stated < 10⁶;
1/9.8e-4 ≈ 1.0e3 against a stated < 10³. So fp16's figure is roughly `1/ε` and fp32's is roughly `1/ε ÷ 8`.
The table does not state its derivation, and the two rows are not derived the same way.

The error model, `:206-216`:

> ### 5.1 浮点运算误差界
>
> 对浮点运算 `⊕`，存在相对误差 ε ≤ machine epsilon:
> ```
> fl(a ⊕ b) = (a ⊕ b)(1 + ε)
> ```
>
> 推论: n 次加法累积误差约 `n·ε`

`n·ε` is the sequential bound, as §2 notes.

T3 and its graded strategy, `:87-106`, quoted in SOURCE. The final line, `:106`: "**Kahan 补偿求和**: 维护
compensation 追踪舍入误差" — named and not shown; no implementation appears in this file.

The scope limit, `:81-84`:

> ### ❌ 误区 4: 所有 fp16 都升 fp32
> **错误**: 所有 fp16 算子 Cast→fp32
> **正确**: 仅涉及**归约累加**的算子需要 fp32 累加器

and its two companions at `:73-79` (RMSNorm needs no Welford because `E[x²]` has no cancellation risk;
elementwise sigmoid/log/sqrt need range protection rather than a wide accumulator), which together make the
scope precise: the accumulator rule applies to reductions, and only to those.

The golden rule the file closes on, `:233`: "**黄金法则**: 理论等价不保证数值等价" — theoretical equivalence
does not guarantee numerical equivalence. That is the same principle 0380 records upstream violating in a
different skill, where the SIMT operator and `fdividef` are called 功能完全等价 and then separated by
rounding control.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3). The wider
`numerical_stable/` family — `patterns.md` (390 lines) and the rest of `knowledge.md`'s six techniques —
was sampled rather than mined in this block; that is recorded in §7 and in the final report.

## 4 · Procedure
Runnable later on `950PR`. The claim is a set of numbers, so the procedure measures the curve they describe.

Arm A — the error curve, per format. Sum n identical-magnitude values for n swept logarithmically from 10¹
to 10⁷, in fp16, bf16 and fp32 accumulators, against an fp64 host reference. Plot relative error against n.
The n at which error exceeds the format's own epsilon is the measured safe length. Compare against < 10³ /
< 10³ / < 10⁶.

Arm B — the summation order, which is the OVERTURN. Repeat Arm A twice: once with a sequential scalar
accumulate, once with the hardware tree reduction (0030). If the tree version's error grows like log(n)
rather than n, the table's figures do not describe reductions written the recommended way, and the entry is
corrected in place with both curves recorded. **This arm is the reason the others exist**: a safe length
measured only on sequential summation would confirm a bound nobody uses.

Arm C — the dynamic-range axis. At fixed n = 10⁵, sweep the input dynamic range from 10⁰ to 10¹² and record
fp32 error with and without Kahan compensation. The range at which plain fp32 diverges is the table's 10¹⁰
threshold, measured.

Arm D — the accumulator rule's necessity and its limit. For one fp16 reduction at n = 10⁴, build three
variants: fp16 accumulator, fp32 accumulator with fp16 inputs, and full fp32 compute. Compare error and
duration. The first pair establishes the rule; the second pair establishes 误区 4 — if full fp32 compute is
no more accurate than an fp32 accumulator over fp16 inputs, the over-promotion buys nothing and the cost is
measurable.

Arm E — Kahan's cost, which upstream states as "+1 fp32 buffer" and nothing else. Build the Kahan variant
and record its register usage from the disassembly (0356's method) and its duration. One extra fp32 buffer
is a UB statement; in a VF it is an extra `RegTensor` and possibly a spill, which is a different cost.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`measured_safe_length` (Arm A) — per format, the largest n whose relative error stays below that format's
epsilon. Pass iff within one decade of the tabulated figure. Reported per format, never as a single verdict:
the entry's claim is that the three differ, and one aggregate would erase the three-decade gap that is the
whole point.

`error_growth_exponent` (Arm B) — the fitted exponent of error against n, for sequential and tree
summation. Pass iff sequential ≈ 1. The tree exponent is **reported, not gated** — upstream states no
value for it, and a value near 0 (logarithmic) is the OVERTURN and the most useful outcome.

`range_threshold` (Arm C) — the dynamic range at which plain fp32 error exceeds the Kahan variant's by more
than 10×. Reported against the tabulated 10¹⁰.

`accumulator_vs_full_promotion` (Arm D) — two error figures and two durations, reported as four numbers.
Never collapsed into "promotion helps": the arm's purpose is to show that the *second* promotion does not.

`kahan_cost` (Arm E) — extra registers from the disassembly and the duration ratio. Both required: "+1 fp32
buffer" is a storage claim and the duration is what a tiling routine would weigh.

The positive fixture, declared before the run: Arm A must include a **sum of powers of two** at each n,
which is exact in every format and must produce **zero** error in all three accumulators. If it does not,
the comparison pipeline or the fp64 reference is wrong and every measured safe length is an artefact — the
same fixture 0396 §5 declares, required again here because this arm's entire output is an error curve. And
Arm B's sequential variant must be confirmed to be sequential by disassembly; if the compiler has
re-associated it into a tree, the two arms are measuring one thing and the exponent comparison is void.
Without both, the checker reads only "error grew with n", which is true of every summation and
distinguishes nothing.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no sum
computed, no error curve fitted, no register counted, no die contacted. The quoted table and passages are
re-verified file reads of the upstream tree performed during this harvest. The observation in §3 that
bf16's stated epsilon uses a different convention from the other two rows is arithmetic on upstream's own
table, not a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish any of the three safe lengths, the epsilon
values, the 10¹⁰ range threshold, or that an fp16 accumulator fails at 10³ terms — Arms A through E are all
open.

**The figures are stated for sequential summation and this hardware reduces in a tree.** `n·ε` is the
sequential bound; 0030 records that the hardware tree reduction reorders the sum, and tree summation grows
like `log(n)·ε`. So the tabulated safe lengths may be worst-case bounds rather than descriptions of a
reduction written the recommended way. Arm B is what would settle it, and until then this entry's numbers
must not be used to reject a shape.

The table's three epsilon rows are **not internally consistent in convention**: fp32's 1.2e-7 and fp16's
9.8e-4 are 2⁻²³ and 2⁻¹⁰ (half-ulp), while bf16's 7.8e-3 is 2⁻⁷ rather than 2⁻⁸. Nothing here resolves which
convention is intended, and the safe-length column is not derived uniformly from the epsilon column either
(fp16's figure is ≈ 1/ε, fp32's is ≈ 1/ε ÷ 8).

It does not establish Kahan compensation. Upstream names it, states its cost as one extra fp32 buffer, and
shows no implementation; whether a compensated sum survives a VF's register budget (0356, 0357) or is
spilled is unmeasured.

It says nothing about mixed-magnitude inputs beyond the 跨度 column's threshold, about integer
accumulation, or about the fp8 format the toolkit ships (0388 §2) and this table does not cover.

**The `numerical_stable/` family was sampled, not mined.** This entry draws on `knowledge.md`'s §1.2, T3
and §5.1; the file's other five techniques (max-shift/LogSumExp, eps protection, Welford, range protection,
piecewise formulas), its combination rules, and the 390-line `patterns.md` beside it are unharvested. 0398
takes one further item from the same file. What the rest contains is unknown to this book.

BOARD is `family-claimed(unverified)`: floating-point format properties are not board-dependent, but the
summation order that determines whether the figures apply *is*, and no board was contacted.
