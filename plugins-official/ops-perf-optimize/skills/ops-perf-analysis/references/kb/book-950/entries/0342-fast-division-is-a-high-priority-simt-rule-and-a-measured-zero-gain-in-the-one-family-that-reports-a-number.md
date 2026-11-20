```
ID:        0342-fast-division-is-a-high-priority-simt-rule-and-a-measured-zero-gain-in-the-one-family-that-reports-a-number
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled.
           The two documents that disagree are two files of the SAME repo, so this is one origin
           disagreeing with itself and corroborates nothing (RULES.md Art. 3).
BOARD:     950PR
SOURCE:    ops/ascendc-performance-best-practices/reference/simt/optimization-guide.md:24 —
           "| Rule 007 | 高 | 用 fast-division 和特化降低地址计算成本 |" ; :235-241 — "**适用场景**：
           逐元素循环需要把线性下标拆成多维坐标，热点路径含多次整数除法和取模" · "运行期除数在 VF
           调用前已知时，先计算 magic/shift： GetUintDivMagicAndShift(magic, shift, divisor);"
SOURCE:    ops/ascendc-performance-best-practices/reference/scatter/scatter_design.md:166 —
           "**实测 quick-div 类标量优化在本族零收益**（§8），瓶颈在访存延迟不在标量流水" ;
           :175 — "| int64 → int32 索引运算宽度收窄 | **零收益**（+0.04 分）。连带 quick-div magic
           number、按 rank 特化 kernel 同属标量优化，**预期同样无用**——瓶颈是访存延迟 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured SIMT kernel on a named 950 board, outside the scatter family, where replacing
           integer division with the magic/shift form leaves kernel time unchanged outside the run
           spread while the scalar pipe share visibly falls — the rule would then be a scalar-share
           optimisation with no wall-clock consequence anywhere, not merely in one family.
```

# 0342 · Fast division is a high-priority SIMT rule and a measured zero gain in the one family that reports a number

## 1 · Claim
Upstream asserts, in its cross-cutting SIMT optimisation guide, that reducing address-computation
cost with fast division and dimensional specialisation is a **high**-priority rule, applicable when
an element-wise loop decomposes a linear index into multi-dimensional coordinates and the hot path
contains repeated integer divides and modulos. Upstream gives the recipe: when the runtime divisor
is known before the VF call, precompute `magic` and `shift` with `GetUintDivMagicAndShift`, then
inside the VF obtain the quotient with `Simt::UintDiv(index, magic, shift)` and the remainder by
`index − quotient × divisor`, reusing the quotient rather than calling `UintDiv` twice.

Upstream asserts, in the scatter family's own design document, that this class of change measured
**zero gain** in that family — `实测 quick-div 类标量优化在本族零收益` — with the stated reason that
the bottleneck is memory latency and not the scalar pipeline, and extends the expectation to
per-rank kernel specialisation, the guide's other named technique. The measured instance upstream
reports is a related narrowing (int64 → int32 index arithmetic) at `+0.04` on the score, from which
quick division and rank specialisation are predicted `同样无用`. Not established here.

The SIMT guide states no applicability condition. As written, the two documents conflict: a
high-priority rule with no gate, against a measured null in the family with the best evidence
culture in the shelf.

## 2 · The wrong branch this removes
A rule table with a `高` in the priority column is read as an instruction. An agent optimising a
memory-latency-bound SIMT kernel will implement magic/shift division, specialise by rank, verify
that the scalar instruction count fell, and report a success — because the scalar count *does* fall.
Whether the kernel got faster is a different question, and the scatter family answers it for its own
regime: no.

That is the entry's operational content, and it is a general shape rather than a fact about
division. **An optimisation that provably reduces work on pipe X changes wall time only if pipe X is
the critical path.** The scatter family knows its critical path — latency-bound memory, measured
three ways (`950:0161`) — so it can state the null with confidence. The SIMT guide does not scope
its rule, so it hands the same technique to every regime.

The second wrong branch is over-reading the null in the other direction: concluding that fast
division never pays on 950. Nothing supports that. Scatter's whole family is latency-bound by
measurement; a kernel whose address arithmetic genuinely is on the critical path — deep rank, many
divides per element, high arithmetic density — is exactly the case Rule 007 describes, and no one
has measured it.

So neither document is wrong about its own subject. What is missing is the condition that would let
a reader tell which subject it is in, and the entry's value is to make the missing condition
explicit rather than to pick a side (RULES.md Art. 7).

The third, smaller branch is the reuse detail, which survives either way: upstream's own recipe says
`先复用已有商值，不要为商和余数重复调用 UintDiv`. Calling `UintDiv` twice for quotient and remainder
doubles the cost of the technique that was supposed to reduce cost, and it is a plausible mistake
because the remainder has no dedicated call.

## 3 · Ground / Source
The rule, `simt/optimization-guide.md:24` in the summary table and `:235-262` in full:

```
### Rule 007：用 fast-division 和维度特化降低地址计算成本

- **分类**：指令优化
- **优先级**：高
- **适用场景**：逐元素循环需要把线性下标拆成多维坐标，热点路径含多次整数除法和取模

运行期除数在 VF 调用前已知时，先计算 magic/shift：

uint32_t magic;
uint32_t shift;
GetUintDivMagicAndShift(magic, shift, divisor);

VF 内复用商值，并用乘减得到余数：

uint32_t quotient = Simt::UintDiv(index, magic, shift);
uint32_t remainder = index - quotient * divisor;

进一步优化：

- 除数是编译期 2 的幂时使用移位和掩码，或让编译器完成强度削减。
- 2D/3D/4D 采用静态展开版本，避免 ND 运行时循环。
- 末维无需转置或无需拆分时，直接删除对应除法。
- magic/shift、shape 和 stride 移出逐元素循环。
- 先复用已有商值，不要为商和余数重复调用 `UintDiv`。
```

The measured null, `scatter/scatter_design.md:166`, in the comparison against the vendor's built-in
implementation:

```
| 多维寻址 | `GetUintDivMagicAndShift` + `Simt::UintDiv` quick-div，按 rank 特化 `SimtComputeDim1~8`
| 快路径压成 `(o, j, c)` 三段、`outer==1` 时省一次除法；通用路径逐维取模 | **实测 quick-div 类标量
优化在本族零收益**（§8），瓶颈在访存延迟不在标量流水 |
```

and in the falsification list, `:175`:

```
| int64 → int32 索引运算宽度收窄 | **零收益**（+0.04 分）。连带 quick-div magic number、按 rank
特化 kernel 同属标量优化，**预期同样无用**——瓶颈是访存延迟 |
```

Read the evidential structure carefully, because it is weaker than it first appears and the entry
must not overstate it. What was *measured* is the int64 → int32 narrowing, at `+0.04` on a scoring
harness. Quick division and rank specialisation are placed in the same class and marked
`预期同样无用` — a prediction, in upstream's own words. The `:166` sentence says `实测` of the
quick-div class directly, which reads as a measurement; the `:175` row says it was predicted. The two
sentences in one document give the same conclusion different evidential status, and this entry does
not reconcile them.

Note also that the built-in implementation upstream is comparing against *does* use quick division
and per-rank specialisation (`SimtComputeDim1~8`), and upstream's own implementation deliberately
does not — while scoring first on the leaderboard (`0326` §3). That is consistent with the null and
is not evidence for it: two implementations differ in many ways.

The regime that makes the null intelligible is carried by `950:0161`: scatter throughput scales with
total thread count, the streaming passes reach ~600 GB/s while the scatter passes run at a few
G updates/s, and upstream reads this as latency limitation. If that reading is right, scalar work is
not on the critical path in this family — and if it is wrong (`950:0161`'s own OVERTURN), so is the
explanation here.

Recorded as `C-950bp-009`. It is resolvable only by a procedure on a named board (RULES.md Art. 7), and
the resolution is not "which document wins" but "what is the condition".

Nothing here is measured by this book.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The disagreement is about a
missing condition, so the procedure sweeps the axis the condition should be written on.

The axis: **the scalar pipe's share of kernel time in the baseline**. Construct a family of SIMT
kernels over one shape and one access pattern, varying only how much address arithmetic each
element requires — rank 1 (no division), rank 2, rank 4, rank 8 with a runtime rank loop — so that
baseline scalar share sweeps from near zero to dominant.

Arm 1 — the intervention, at every point on the axis. Two builds per point: plain `/` and `%`, and
the magic/shift form with quotient reuse. Record kernel time, scalar pipe share, and generated
scalar instruction count for each. The output is a **curve of gain against baseline scalar share**,
and that curve *is* the missing applicability condition — its crossing point is the number Rule 007
needs and does not have.

Arm 2 — reproduce the null where it was reported. The same intervention on a scatter-shaped kernel
with the same measured characteristics `950:0161` records (thread-count-elastic, byte-inelastic).
Upstream predicts no gain. This anchors one end of Arm 1's curve to the one place a result exists.

Arm 3 — the class extension, which upstream predicted rather than measured. Per-rank static
specialisation (2D/3D/4D unrolled against an ND runtime loop) as a separate intervention from
magic/shift, at every point on the axis. Upstream lumps them; they are different changes with
different costs (specialisation multiplies binary size) and should be attributed separately.

Arm 4 — the double-call cost, which is cheap and settles the recipe's detail. Magic/shift with
quotient reuse against magic/shift calling `UintDiv` twice.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, with
`0327`'s same-path sibling check applied before any table is read — scatter's own reported effect
was `+0.04` on a score, which is at or below any plausible floor, and the whole disagreement turns
on whether a null is a null. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that `GetUintDivMagicAndShift` and `Simt::UintDiv` exist in the
installed toolkit — a `grep -Rn` over the include roots precedes every build and is marked
`[no-card]` and **not run**; that the compiler did not already strength-reduce the plain form (every
pair is disassembled, because a null between two builds the compiler made identical is not a result).

## 5 · Checker — acceptance declared before the run
Verdict `gain[s]` = the intervention's kernel-time gain at baseline scalar share `s`, with the
floor, for each point on Arm 1's axis. The deliverable is the curve.

Verdict `crossover` = the smallest `s` at which `gain[s]` leaves the floor. Declared before the run:
**this is the applicability condition Rule 007 lacks**, and producing it is the entry's purpose. A
curve with no crossover — gain inside the floor at every `s` up to scalar-dominant — is the strong
form of the OVERTURN and would say the rule has no regime at all.

Verdict `scatter_null_reproduced` = true iff Arm 2's gain is inside the floor.
Verdict `scalar_share_fell` per point — reported alongside `gain`, always. The two together are the
entry's whole subject: a point where the scalar share falls and the time does not is the
measurement/inference separation this book requires, made visible.
Verdict `specialisation_gain[s]` from Arm 3, reported separately from `gain[s]`.

The exit code is not the verdict. Three guards.

First, every build is compared elementwise against a CPU reference. Magic/shift division is exact
only within its derived range; an off-by-one in the magic constant produces wrong coordinates for a
subset of indices, and a subset-shaped error survives spot checks. The comparison covers the full
index space at every rank.

Second — the input that makes this checker go red — Arm 1 includes a point at rank 8 with a runtime
loop, where the baseline scalar share is by construction dominant. `gain` there **must** leave the
floor. If the intervention shows no gain even where address arithmetic is the majority of the
kernel, then either the intervention is not taking effect (checked by disassembly) or the harness
cannot resolve the effect at all — and every null in the sweep, including Arm 2's, is void rather
than confirming. A study whose only outcome is "no difference anywhere" is the known blind species,
and a deliberately scalar-dominant point is what excludes it.

Third, no `gain` is reported without `scalar_share_fell` beside it, and no point is interpreted
before the contamination check. Scatter's own reported figure sits inside any reasonable floor, and
this entry exists because a null was reported without one.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. `+0.04` is upstream's
scoring delta on Ascend950PR under a harness not present in this tree; the quick-division null is
stated as `实测` in one sentence and as `预期` in another, and this book has measured neither. No
kernel was built, no divide was replaced, and `GetUintDivMagicAndShift` was not located in any
installed header.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does **not** adjudicate the disagreement: both documents
are directories of one repository, two files in one repo are one origin (RULES.md Art. 3), and a
contradiction is resolved only by a procedure on a named board (RULES.md Art. 7). It does not establish
that fast division is useless — the null is reported for one family whose bottleneck is measured to
be elsewhere, and no result exists for any other regime. It does not establish that fast division
helps anywhere; nobody has published a positive case. The scatter null's own evidential status is
internally inconsistent in its source (`实测` at `:166`, `预期同样无用` at `:175`), and the only
figure attached to it — `+0.04` on a score — belongs to a *different* change (int64 → int32
narrowing) and carries no repeat count, variance, floor or time unit. Per-rank specialisation is
grouped with fast division by upstream and is a separate change with a separate cost, established by
neither. `GetUintDivMagicAndShift`, `Simt::UintDiv` and `SimtComputeDim1~8` are named without
signatures, headers or version pins, and none was located here. BOARD is `950PR` because the scatter
family's provenance note names that part; the SIMT guide names 950 generally and no board. Nothing
transfers to the other book (RULES.md Art. 1).
