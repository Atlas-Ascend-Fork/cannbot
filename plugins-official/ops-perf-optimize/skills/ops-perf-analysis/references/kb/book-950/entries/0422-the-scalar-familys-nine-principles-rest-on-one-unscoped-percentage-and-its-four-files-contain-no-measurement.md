```
ID:        0422-the-scalar-familys-nine-principles-rest-on-one-unscoped-percentage-and-its-four-files-contain-no-measurement
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scalar/guide.md:5 —
           "Scalar 优化的核心结论：**主因不是 Scalar 计算指令多，而是 Load/Store 指令多**（典型占比超过
           30%），其根源是编译器寄存器 Spill。因此本类目下所有原则的共同目标是：**帮助编译器更好地完成
           寄存器分配、别名分析和常量传播，从而减少 Load/Store**。"
SOURCE:    same family, coding_principles.md:7 — "- **反例 / 正例**：可直接对照的代码模板
           （非真实算子代码，用于模式识别）" ; :3 — "本文给出 9 条编写 Scalar 高性能算子的编码原则。"
SOURCE:    same family, conv_scalar.md:87 — "### 优化效果示意" ; :95 — "  → 典型 Scalar Load/Store
           占比 > 30%" ; :101 — "  → Scalar Load/Store 占比可降到 < 15%"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a profiled Ascend C operator on a named 950 board whose scalar Load/Store instruction share
           is below 10% while it is nonetheless scalar-bound — the family's root-cause claim would then
           not hold for that operator, and "reduce Load/Store" would not be the lever the nine
           principles assume. Equally: a measured case set in which the share is routinely far above
           30%, which would make the headline figure an understatement rather than an unscoped one.
```

# 0422 · The scalar family's nine principles rest on one unscoped percentage, and its four files contain no measurement

## 1 · Claim
Upstream asserts a root cause for scalar-bound Ascend C operators: not the count of scalar compute
instructions but the count of Load/Store instructions, typically above 30 % of the total, arising from
compiler register spill — and asserts that every principle in the category shares one goal, helping the
compiler with register allocation, alias analysis and constant propagation so as to reduce Load/Store.
Upstream builds nine coding principles on that claim, each with a stated mechanism, recognition signals
and a paired counter-example and example. Upstream states that all of that code is illustrative rather
than drawn from real operators. Across the family's four files and 1 192 lines there is **no absolute
timing of any kind** — no µs, no ms, no speed-up ratio — and exactly four percentages, all of them
Load/Store share, none carrying a case identity, a board, a profiling tool or a repetition count. Not
established here.

## 2 · The wrong branch this removes
The nine principles are, individually, sound compiler-facing advice — shorten live ranges, avoid
dynamic subscripts into a struct that poison alias analysis, prefer `constexpr` to a runtime `const`,
do not take the address of a hot local. An agent will apply them, and should. The wrong branch is
applying them **as a performance intervention with a predicted magnitude**, because the family supplies
no magnitude for any of the nine. It supplies one aggregate figure for the category (`>30%` of
instructions are Load/Store) and one aggregate target (`<15%`), and never connects either to any
individual principle. So "apply P5 and expect X" is a sentence the family cannot support, and an agent
that reports one has invented the number.

The second wrong branch is the reverse: dismissing the family because it has no numbers. Its content is
a *diagnosis* — the metric to look at is scalar Load/Store share, not scalar instruction count — and a
diagnosis is falsifiable without being quantified. The family also supplies the one thing a numbers
table cannot: a mechanism per principle, which is what lets an agent tell whether a principle applies to
the code in front of it. The honest reading is that this is a **checklist with a stated metric and no
calibration**, and the operational consequence is that every application of it must be measured
locally, because the family cannot tell you in advance whether it is worth doing.

## 3 · Ground / Source
The root-cause claim, `reference/scalar/guide.md:3-5`:

```
Scalar 单元负责标量计算、地址计算、指令参数构造与指令分发。当它本身成为瓶颈、无法及时把指令发到 Cube / Vector / MTE 的 Issue 队列时，其他流水线会出现 bubble，整个算子被拖慢。这种现象称为 **ScalarBound**。
```
```
Scalar 优化的核心结论：**主因不是 Scalar 计算指令多，而是 Load/Store 指令多**（典型占比超过 30%），其根源是编译器寄存器 Spill。因此本类目下所有原则的共同目标是：**帮助编译器更好地完成寄存器分配、别名分析和常量传播，从而减少 Load/Store**。
```

Two claims in one sentence and they are different kinds. `主因不是…而是…` is a *diagnostic*
attribution — a statement about which metric discriminates — and it is testable by profiling a
scalar-bound operator. `其根源是编译器寄存器 Spill` is a *causal* attribution one level deeper, and
nothing in the family tests it. `典型占比超过 30%` is the only number, and `典型` is its entire
provenance.

The nine principles, `coding_principles.md:3`, with their disclaimer at `:7`:

```
本文给出 9 条编写 Scalar 高性能算子的编码原则。每条原则的格式统一为：
```
```
- **反例 / 正例**：可直接对照的代码模板（非真实算子代码，用于模式识别）
```

`非真实算子代码` is a blanket disclaimer scoping all nine: the paired examples are patterns for
recognition, not extracts from anything that ran. That is honest and it is also the reason no principle
carries a measurement — there was no operator to measure. Their one-line forms, `guide.md:11-19`, are
compiler-facing throughout: P1 dynamic subscripts into a struct array abandon constant propagation for
the whole struct; P2 a three-stage prologue / zero-branch hot loop / epilogue replaces three branch
tests per iteration; P3 nested `for` beats an implicit state machine because the loop back-edge uses
dedicated hardware and does not enter branch prediction; P4 member variables are suppressed by alias
analysis and must be reloaded after a call; P5 shorter live range means shorter register occupancy;
P6 each dereference level is a dependent load; P7 over 64 B crosses a cache line; P8 a `const` member
is still a runtime load; P9 constructors expand to initialisation stores and taking an address forces
a spill.

Three of the nine carry a number, and all three are bare. `coding_principles.md:114`:

```
> 适用边界：循环次数 < 5 次时，三段式带来的代码膨胀可能触发 I-Cache miss，需权衡。
```

`:123` gives `3–5 次连续 mispredict` for a state-machine tile switch and `数百行` for its code size,
while `:129`'s recognition threshold for the same condition is `>200 行` — a tension the file does not
address. And `:319`:

```
1. **缓存局部性差**：D-Cache cacheline 大小为 64 字节。结构体过大时，访问不同成员可能落在不同 cacheline 上，导致 D-Cache miss 增多。建议结构体 ≤ 64B（1 个 cacheline），最大不超过 128B。
```

The 64-byte cache line is stated as fact with no architecture, no source and no derivation, and the
128 B ceiling that follows has no stated relation to it beyond the implied two lines. This project's
own survey lists cache-line size among the constants that must be established from scratch because no
upstream authority supplies one; this family supplies a number without becoming an authority for it.
Recorded in `harvest/standing/950-td.md` as `Q-950td-10`.

The four percentages, and they do not agree. `guide.md:5` gives `典型占比超过 30%`.
`conv_scalar.md:95` and `:101`, inside a section headed `优化效果示意` (`:87` — *schematic*, not
measured), give:

```
  → 典型 Scalar Load/Store 占比 > 30%
```
```
  → Scalar Load/Store 占比可降到 < 15%
```

and `conv_scalar.md:158-159`, in the summary diagram of the same file:

```
                │  Scalar Load/Store 占比      │
                │  从 90%+ → 10% 以内          │
```

One metric, three baselines — 30 %, >30 %, 90 %+ — and two targets, 15 % and 10 %, in two files by one
author. The partial reconciliation the documents do not state is that `:159` covers all three
conv-specific techniques while `:95`/`:101` cover only the second; but 30 % cannot be a subset baseline
of 90 %+ for the same metric on the same code. Registered as `C-950td-028`.

What the family does not contain, verified by reading all four files at drafting time: no µs, no ms, no
speed-up ratio, no `×`, no board name, no profiler name, no repetition count, no `待实测` marker, and no
architecture marking of any kind — no `DAV_2201`, `DAV_3510`, `arch35`, `910`, `950`, `220x` or
`Atlas` anywhere in 1 192 lines. Every architecture-dependent constant in it — the 64 B cache line,
the L1/L0A/L0B/L0C/UB capacities in `buffer_management_conversion_guide.md:18-27`, `QUE_MAX_EVENT`
(通常为 8), `G_CV_SYNC_STRIDE` (通常为 16), `L0A_HALF = 32768` — is unlabelled. The capacity table's
own column header is `容量(典型)`, and its UB row reads 192 KB, which is not the value this book
records for DAV_3510 (`0209`: 248 KB). Under RULES.md Art. 1 none of those figures is carried here; they are
noted as unscoped, and the family's silence about which part they describe is the finding.

The one place the family scopes itself sharply is worth carrying as the counter-example to its own
habit, `guide.md:23`:

```
Scalar 优化与算子族优化**正交**：算子族优化决定"做什么计算和搬运"，Scalar 优化决定"这些指令能不能被及时分发出去"。两者都要做，但顺序上以算子族优化（tiling / MTE 策略）为先。
```

That is a clean ordering rule — do the tiling and movement work first, then the scalar work — and it is
the family's most transferable sentence.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The family's
central claim is a *diagnostic* one, so the procedure profiles rather than optimises, and the
optimisation arms come second.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs, 5 fresh-process runs.

**Arm 1 — is the metric the discriminator?** Assemble a case set of at least eight operators spanning
scalar-bound and non-scalar-bound (this book's `0017` gives the scalar-bound signature: very many tiny
tiles turning a fixed per-tile cost into a bound). For each, collect from `msprof` the scalar pipeline
share, the scalar **Load/Store instruction** share, and the scalar **compute instruction** share. The
family's claim predicts that Load/Store share separates the two groups and compute share does not.
Report both separations. This is the arm that tests `主因不是…而是…`, and it needs no code changes at
all.

**Arm 2 — where does the 30 % line fall?** From arm 1's data, report the distribution of Load/Store
share across the whole case set, and specifically its value on the scalar-bound subset. `30 %`, `>30 %`
and `90 %+` are three published answers (`C-950td-028`); this arm produces one measured distribution
against which all three can be placed. No threshold is adopted from upstream.

**Arm 3 — is spill the cause?** The deeper claim is that the Load/Store come from register spill.
Compile one scalar-bound kernel with the compiler's spill reporting enabled (or, failing that, count
stack-slot accesses in the disassembly) and correlate spill count with Load/Store share across a
sweep of one principle's variable — P7's struct size is the cleanest, since `coding_principles.md:319`
predicts spill above register capacity. Sweep the struct at 32 B, 64 B, 128 B, 256 B and report spill
count and Load/Store share at each. This arm is what separates upstream's diagnostic claim from its
causal one.

**Arm 4 — do the principles move the metric?** For the three principles with a stated mechanism that
can be varied without changing the algorithm — P1 (dynamic subscript into a struct array), P5 (live
range), P8 (`const` member versus `constexpr`) — build a matched pair per principle on one real kernel,
one compiler pin, distinct md5s, and record Load/Store share and `aiv_time` for each. Report per
principle. Upstream predicts direction and no magnitude, so the deliverable is the first magnitude any
of them has ever had.

**Arm 5 — the cache line, which the family asserts and this project needs.** Sweep a struct across
32/48/64/80/128/256 B and record D-Cache miss counts. `coding_principles.md:319`'s 64 B is testable
directly and is on this project's establish-from-scratch list (`Q-950td-10`).

Refuses to assume: that a free die stays free; that a die may be substituted; that the family's
capacity table describes this part (its UB row says 192 KB against `0209`'s 248 KB, and none of its
figures is carried); that `msprof`'s scalar counters distinguish Load/Store from compute (arm 1 reports
which counters exist, and if they do not exist the family's central metric is unmeasurable and that is
the finding); that the illustrative code compiles (it is disclaimed as non-real, so arm 4 builds
matched pairs on a real kernel instead).

## 5 · Checker — acceptance declared before the run
Verdict `ls_separation` and `compute_separation` from arm 1 = the gap between scalar-bound and
non-scalar-bound group means, in units of the pooled standard deviation, for each of the two metrics.
Declared before the run: the family's diagnostic claim is **supported** iff
`ls_separation > compute_separation` and `ls_separation` exceeds 1. The OVERTURN fires iff
`compute_separation ≥ ls_separation` — scalar instruction count would then discriminate at least as
well, and the family's `主因不是…而是…` would be wrong about which metric to look at.

Verdict `ls_share_distribution` from arm 2, reported as a distribution with its quartiles, never as a
single threshold.

Verdict `spill_correlation` from arm 3 = the correlation between spill count and Load/Store share
across the struct-size sweep. Declared now: upstream's causal claim predicts a strong positive
correlation; a weak one leaves the diagnostic claim standing and kills only the causal half, and the
report must say which of the two it is refuting.

Verdict `principle_delta(P1, P5, P8)` from arm 4, three pairs of (ΔLoad/Store share, Δ`aiv_time`), each
with the floor.

The exit code is not the verdict, and arms 1–3 have no pass/fail at all — they produce distributions.
Three guards. First, **the input that makes this checker go red**: arm 1's case set includes at least
two operators this book already characterises as bound elsewhere — one memory-bound and one
vector-bound (`0005`, `0011`, `0075`) — which **must** land in the non-scalar-bound group on both
metrics. If a known memory-bound operator reads as scalar-bound, the profiling setup is
misattributing pipelines and every separation in the study is void. A diagnostic study whose only
outcome is "the proposed metric separates the groups" cannot distinguish a real discriminator from a
mislabelled case set. Second, every profiled figure carries the counter name it was read from and the
`msprof` invocation; the family names no tool, so this study must name its own or it reproduces the
defect it documents. Third, arm 4's pairs are one source file with a compile-time switch, two md5s
echoed — a matched pair built from two files carries no attribution, which is the failure species this
book records.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and upstream supplies none
either: the four percentages are the family's only quantities of any kind, two of them sit under an
explicit `示意` (schematic) heading, and the family contains no timing, no ratio, no board, no tool and
no repetition count in 1 192 lines. The absence statements in §3 are the result of reading all four
files at drafting time, re-derivable by
`grep -rn 'us\|µs\|ms\|倍\|DAV_\|arch3\|910\|950\|待实测' upstream/skills-dev-main/ops/ascendc-performance-best-practices/reference/scalar/`.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that scalar Load/Store share is the
right diagnostic, that spill is its cause, or that any of the nine principles reduces it — it records
that upstream asserts all three and measures none. It does not establish the 30 %, 15 %, 90 % or 10 %
figures, and does not choose among the three baselines (`C-950td-028`); Art. 7 forbids resolving that
by preferring an author. It does not establish the 64 B cache line, the `<5` loop-count boundary, the
`3–5` mispredict figure, or the 200-line recognition threshold — all are bare, and the cache line is
recorded as owed (`Q-950td-10`). It does not carry any capacity from
`buffer_management_conversion_guide.md:18-27`: that table is headed `容量(典型)`, names no
architecture, and its UB row disagrees with what this book records for DAV_3510 (`0209`), so none of it
enters here. It does not establish that the illustrative code in `coding_principles.md` compiles or
corresponds to any shipped operator — upstream disclaims it at `:7`. It does not cover the family's
buffer-management ranking (`0423`) or its Conv-specific section beyond citing the percentages. No
architecture marking of any kind appears anywhere in the family, so BOARD is
`family-claimed(unverified)` on the weakest possible grounds — the family is placed in this book by the
shelf it sits in, not by anything it says about itself, and §7 records that as a real limit rather than
a formality. Nothing here is established for any 910-family board.
