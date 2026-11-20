```
ID:        0479-three-of-this-sections-four-headline-numbers-are-unscoped-ranges-and-the-fourth-is-arithmetic-already-in-the-book
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/elementwise/vector_efficiency_design.md:7-12
           — "| 指标 | naive | optimized | 收益 | / | Scalar 控制指令 | 每条 Vector API 前手动计算
           repeat/mask | Counter 模式一次设置，全程自动 | Scalar 开销降低 30-50% | /
           | GM 搬运次数（n 步 Vector 链） | 2n 次（每步搬入+搬出） | 2 次（首次搬入 + 最终搬出） |
           搬运次数减少 n 倍 | / | 归约指令延迟 | WholeReduceSum 单条高延迟 | BlockReduceSum +
           WholeReduceSum 组合 | 延迟降低 20-40% | / | 指令级并行 | 循环体串行执行 | 循环展开暴露并行性 |
           ILP 提升 |"
SOURCE:    same file:186-193 — "if (profiling 显示 Scalar 时间占比高): / → 启用 Counter 模式 /
           elif (profiling 显示 MTE2/MTE3 中间搬运占比高，且有多步 Vector 链): / → 启用 UB 融合链
           （VECCALC 直通）/ elif (profiling 显示归约延迟高): / → 启用低延迟归约组合（BlockReduceSum +
           WholeReduceSum）/ else: / → 标准 Vector 实现即可" ; :179 —
           "| 循环展开后性能下降 | 展开因子过大导致 ICache miss | 展开因子 ≤ 4，默认推荐 2x |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a scoped measurement on a named 950 board landing any of `30-50%`, `20-40%` or the
           unroll-factor guidance outside its stated range at a case the document's own selection
           tree would route to that mechanism — the range would then be wrong for its own intended
           regime, not merely unscoped. Equally: finding the case, shape, dtype, board and tool behind
           any of the three ranges, anywhere upstream, removes this entry's subject for that row.
```

# 0479 · Three of this section's four headline numbers are unscoped ranges, and the fourth is arithmetic already in the book

## 1 · Claim
Upstream asserts a four-row benefit table for vector-efficiency optimisation, giving: a 30-50%
reduction in scalar overhead from counter mode; a reduction in GM transfer *count* from `2n` to 2 for
an `n`-step vector chain, stated as "n times fewer"; a 20-40% reduction in reduction-instruction
latency from a two-stage `BlockReduceSum + WholeReduceSum` combination; and an unquantified improvement
in instruction-level parallelism from loop unrolling. Upstream asserts a selection tree that routes to
each mechanism by which pipe a profile shows dominating. Upstream asserts an unroll-factor bound of 4
with 2× recommended, attributing larger factors to instruction-cache misses. Not established here;
this entry records the table's evidence class.

## 2 · The wrong branch this removes
Without this entry an agent treats the four rows as one kind of thing — four measured benefits — and
budgets from them. They are not one kind of thing. The `2n → 2` row is **arithmetic**: if an `n`-step
chain writes each intermediate to GM and reads it back, it makes `2n` transfers; if it keeps them in
UB it makes 2. Nothing was measured to know that, and nothing needs to be. The other three are
performance claims, and two of them are ranges with no case, no shape, no dtype, no board, no tool and
no repetition count attached anywhere in the 203-line document.

The specific wrong branch is planning against `30-50%` or `20-40%`. A range is a promise about a
distribution, and a range with no scope is a promise about an unnamed distribution. An agent that
budgets a 40% scalar-time reduction and gets 5% has not been misled by a wrong number; it has been
misled into believing a number was measured. This corpus records the same register elsewhere —
`950:0318` §7 for the residency document, `0422` for the scalar family's nine principles resting on one
unscoped percentage, `0419` for three conversion headline ratios each wider than the table below them.
This is the fourth instance and the pattern is the finding, not any single row.

The second wrong branch is over-correction: discarding the section because its numbers are unscoped.
The **mechanisms** are real and two of them are independently attested. The middle row is already this
book's `0020` — chain adjacent vector steps in UB so intermediates never round-trip through GM — mined
from the analysis shelf, and the `2n → 2` arithmetic is that entry's claim in another notation, so
this row is cited rather than re-entered (plan Amendment 2). Counter mode exists in the installed
toolkit (`0477`). The two-stage reduction's APIs exist (`0478`). What is missing is provenance for
three numbers, not the techniques.

## 3 · Ground / Source
The table, `reference/elementwise/vector_efficiency_design.md:7-12`:

```
| 指标 | naive | optimized | 收益 |
|------|-------|-----------|------|
| Scalar 控制指令 | 每条 Vector API 前手动计算 repeat/mask | Counter 模式一次设置，全程自动 | Scalar 开销降低 30-50% |
| GM 搬运次数（n 步 Vector 链） | 2n 次（每步搬入+搬出） | 2 次（首次搬入 + 最终搬出） | 搬运次数减少 n 倍 |
| 归约指令延迟 | WholeReduceSum 单条高延迟 | BlockReduceSum + WholeReduceSum 组合 | 延迟降低 20-40% |
| 指令级并行 | 循环体串行执行 | 循环展开暴露并行性 | ILP 提升 |
```

Four rows, four evidence classes, in one column:

- **Row 1, `30-50%`** — a range over a quantity ("scalar overhead") the document never defines as a
  measurable. Is it scalar *instruction count*, scalar *pipe time*, or the scalar fraction of total
  kernel time? The selection tree at `:187` says `profiling 显示 Scalar 时间占比高`, scalar *time
  share*, so the third reading is the intended one — but a 30-50% reduction in a *share* and in an
  *absolute time* are different claims and the table does not say which.
- **Row 2, `n 倍`** — arithmetic over the naive column's own `2n`, requiring no measurement. It is the
  only row whose derivation is fully contained in its own line.
- **Row 3, `20-40%`** — a range over `延迟`, latency. Latency of what: the instruction, the reduction,
  or the kernel? And the code that carries this row does not match the shipped API (`0478`), so
  whatever produced the figure was not the printed program.
- **Row 4, `ILP 提升`** — a direction with no magnitude, and the honest one.

Three of the four also lack a **baseline shape**. `n` appears in row 2 as a free parameter of the
chain; rows 1 and 3 have no parameter at all, so the ranges are stated as if they were constants of
the technique rather than functions of the case.

The one place the section attaches a number to a condition is the unroll factor, `:179`:

```
| 循环展开后性能下降 | 展开因子过大导致 ICache miss | 展开因子 ≤ 4，默认推荐 2x |
```

which is a *bound with a stated mechanism* — instruction-cache pressure — and is therefore a better
claim than the three ranges even though it too has no measurement. It is also the only one of the four
mechanisms with a documented failure mode of its own.

The selection tree, `:186-193`, is what makes the section usable despite the numbers:

```
if (profiling 显示 Scalar 时间占比高):
    → 启用 Counter 模式
elif (profiling 显示 MTE2/MTE3 中间搬运占比高，且有多步 Vector 链):
    → 启用 UB 融合链（VECCALC 直通）
elif (profiling 显示归约延迟高):
    → 启用低延迟归约组合（BlockReduceSum + WholeReduceSum）
else:
    → 标准 Vector 实现即可
```

Every branch is conditioned on a **profile**, not on a shape or a threshold — so the document routes by
measurement even though it publishes none, and the `else` branch says to do nothing. That is a better
epistemic posture than the table's headline column, and the two sit 180 lines apart in one file.

One further item the section carries without comment, `:202`: `- [ ] 寄存器预算 ≤ 32 RegTensor`, in a
self-check list of a document that never mentions the regbase programming model anywhere else. A
`RegTensor` budget is regbase-era vocabulary, which by this book's own mechanism rule
(`form/CONVENTIONS.md`) lands material in book-950 — so the section's own checklist carries the only
architectural marker in the file. Recorded as `Q-950fin-26`.

One file, one repository: one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. This entry's
procedure is a *scoping* procedure: it does not test whether the mechanisms work, it produces the
conditions the ranges lack.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first: 30 in-process and 5 fresh-process runs of each
baseline, IQR over median, beside every point.

**Arm 1 — row 1, with the quantity fixed first.** Before any build, declare which quantity `Scalar
开销` names, and measure all three: scalar instruction count, scalar-pipe time, and scalar time as a
fraction of kernel time. Then build one elementwise operator both ways (hand-computed `repeatTimes` and
tail versus counter mode per the *toolkit's* idiom, `0477`) across dtypes `{fp16, fp32}` and lengths
`2^10 … 2^22`. Report the reduction in each of the three quantities separately. The finding is the
surface, and whether `30-50%` describes any of the three.

**Arm 2 — row 3, likewise.** Single `WholeReduceSum` versus the two-stage pair, per `0478` arm 2, with
latency and wall time reported as distinct metrics. Cite `0478` rather than duplicating its design.

**Arm 3 — row 2, which needs no device for its arithmetic but does for its consequence.** An `n`-step
chain for `n ∈ {2, 3, 5}` with intermediates in GM and in `VECCALC`, reporting MTE2/MTE3 byte counts
and transfer counts. The `2n → 2` count is arithmetic and must come out exactly; the *time* ratio is
not `n` and is what an agent actually wants. Cite `0020` for the technique.

**Arm 4 — row 4 and the unroll bound.** Unroll factors `{1, 2, 4, 8, 16}` on the same operator, with
instruction-cache miss counters read where the profiler exposes them. Upstream bounds the factor at 4
and recommends 2; this arm is where that bound acquires a curve, and where `ICache miss` is confirmed
as the mechanism or replaced by another.

Refuses to assume: that a free die stays free, or that a die may be substituted; that "scalar overhead"
means one thing (arm 1 measures three); that latency and wall time are interchangeable; that the
shelf's code is the code (arms 1 and 2 build the toolkit's idiom, per `0477` and `0478`, because the
shelf's does not match the headers); that a range applies at every shape (every arm sweeps); that a
profiler metric measures what its name suggests (`0317`'s species — every metric is named in the
report).

## 5 · Checker — acceptance declared before the run
Verdict `scalar_reduction(quantity, dtype, len)` from arm 1, one surface per quantity, declared before
the run. Acceptance for row 1 **as a scoped claim**: some named quantity whose median reduction falls
in `[0.30, 0.50]` over a stated shape range. Note what is being accepted — not that the number is
right, but that a quantity exists for which it is right, which is what "unscoped" means and what this
procedure repairs.

Verdict `latency_reduction` from arm 2, per `0478` §5.

Verdict `transfer_count_ratio(n)` from arm 3: must equal `n` exactly, since it is arithmetic — a
non-integer result means the harness is not counting what it thinks it is. And `time_ratio(n)`
separately, which is the number that has no upstream statement at all.

Verdict `unroll_curve` from arm 4, with the factor at which time stops improving and the factor at
which it degrades.

The exit code is not the verdict: every build in every arm is correct, and this entry is entirely about
provenance. Guards: (1) every point carries its variance floor and its metric name, and a point
reported without both is `untestable` — a percentage without a floor cannot distinguish a 35%
improvement from noise, which is exactly the defect the entry records upstream having; (2) **the input
that makes this checker go red**: arm 3's `transfer_count_ratio` at `n = 1`, where the chain has one
step and the naive and fused forms are the same program, so the ratio must be exactly 1 — if it is not,
the counters are not measuring transfers and every other arm's profiler-derived number is suspect;
(3) no arm's result is reported without the dtype, length, board token, tool name and version,
repetition count and the CANN pin — the six things the table's three ranges lack, listed here so the
repair is explicit.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The four-row table, the
selection tree, the unroll bound and the register-budget checklist line are file reads performed at
drafting time. The classification of the four rows into arithmetic, two unscoped ranges and one
direction is a reading of upstream's own columns; the observation that row 2's `n 倍` follows from the
naive column's own `2n` is arithmetic over that same line, not a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that `30-50%` or `20-40%` are wrong —
only that neither carries a case, shape, dtype, board, tool or repetition count anywhere in the
document, and that this book therefore cannot state either in measured voice. It does not establish
that the mechanisms fail; two of the three are independently attested to exist (`0477`, `0478`) and the
middle one is already carried at `0020`, which this entry cites and does not re-enter. It does not
establish the `≤ 4` unroll bound or the ICache mechanism behind it. It does not establish that the
`2n → 2` arithmetic holds for a chain whose intermediates do not all fit in UB, which is the condition
`0020` and the document's own `:164` both attach and which the table's row does not. It does not
resolve what `Scalar 开销` names (arm 1 exists because the document does not say). It does not address
the `RegTensor` budget line (`Q-950fin-26`), which is regbase-era vocabulary in a document with no
other architectural marker. No board token appears anywhere in the file, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen, and the shelf's
sibling document in the same directory calibrates its capacities on a 910 part (`0319`, `C-950bp-010`),
so the family marking must not be read as scoping this file. Nothing here is established for any
910-family board.
