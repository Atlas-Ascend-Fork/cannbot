```
ID:        0486-a-twelve-step-optimisation-table-contains-a-row-that-a-later-row-in-the-same-table-reverses
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scan/templates/usage_guide.md:33-46 —
           the twelve-row trajectory table, "| 改动 | 综合得分 | 平均加速比 |" from
           "| 逐 r 流式扫描（起点） | 54.89 | 0.13x |" to
           "| 借 R 的 phase B 复用行内扫描 | 82.59 | 1.93x |", including
           "| fp16/bf16 原生 16 位比较 | 69.84 | 0.74x |" and
           "| **16 位输入改用 fp32 比较类型** | 81.63 | 1.85x |"
SOURCE:    same file:50-51 — "> 注意倒数第三行**推翻了第五行**：`fp16/bf16 原生 16 位比较` 是在
           Kogge-Stone 时代测出的收益， / 换成 lane 并行扫描后完全反转（见 §2 的更正）。
           **换扫描算法后必须重测比较类型的选型。**" ; :75-87 — the two-by-two table
           "| fp16（原生 16 位比较） | 18.55µs | 15.05µs | / | fp32 | 28.58µs | **9.27µs** |" with
           "Kogge-Stone 下 fp16 比 fp32 快 1.54 倍…lane 并行下却慢 1.62 倍" and
           "排查时先用 `ResourceConflictRatio` 排除了 bank 冲突（`bank_cflt` 仅 0.1%）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a run on a named 950 board in which the 16-bit native comparison is faster than the fp32
           promotion under a lane-parallel scan at the shape upstream measured — the reversal would
           then not occur, and the table's own retraction would be wrong rather than the row it
           retracts. Equally: a mechanism other than the gather path's bit-width — measured, not
           inferred — that accounts for the 1.62× reversal would replace upstream's stated cause.
```

# 0486 · A twelve-step optimisation table contains a row that a later row in the same table reverses

## 1 · Claim
Upstream asserts a twelve-step optimisation trajectory for one operator on one benchmark suite, each
step with a composite score and an average speedup, running from 54.89 / 0.13× to 82.59 / 1.93×.
Upstream asserts, in a note immediately below the table, that the third-from-last row **overturns the
fifth**: the fifth row's gain — using native 16-bit comparison for fp16 and bf16 — was measured in the
Kogge-Stone era and reverses completely once the scan algorithm changes to lane-parallel. Upstream
asserts the rule that follows: after changing the scan algorithm, the comparison-type selection must be
re-measured. Upstream asserts a two-by-two measurement behind the reversal, at `1152 × 1024` elements:
under Kogge-Stone, fp16 18.55 µs against fp32 28.58 µs; under lane-parallel, fp16 15.05 µs against
fp32 9.27 µs — 1.54× the one way and 1.62× the other. Upstream asserts the cause is the 16-bit
gather/scatter path lacking a full-speed route, and asserts that a bank conflict was excluded first by
`ResourceConflictRatio` at 0.1%. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent mines a published optimisation trajectory the way trajectories are usually
mined: as a list of independent wins to apply. Each row has a score and a speedup, the scores increase
monotonically, and nothing in the table's own columns says any row is conditional. So "use native
16-bit comparison" reads as a technique with a measured 0.74× — and it is, for the algorithm it was
measured under, and it is a 1.62× **loss** under the algorithm the table adopts seven rows later.

The normal checks do not catch it because the table is *correct*. Every row's score was real when it
was taken. The scores are cumulative, so the fifth row's 69.84 genuinely included the 16-bit gain, and
the tenth row's 81.63 genuinely includes its removal. A reader reconstructing "what should I do" from
the final score cannot see which of the twelve changes survived into it.

The second wrong branch is generalising the retraction into "published trajectories are unreliable".
The opposite is the lesson upstream draws and states as a rule: `换扫描算法后必须重测比较类型的选型`.
A dtype choice is not a property of the dtype; it is a property of the dtype *and the instruction path
that consumes it*. This book records the same structure from a different direction at `0134` (the scan
template is picked by index tracking first, then by width) and at `0402` (a design shelf's split
reduction merges by the accumulate its own algorithm page calls a hazard) — the pattern being that a
choice made under one regime is carried into another where its premise is gone.

## 3 · Ground / Source
The trajectory, `templates/usage_guide.md:33-46`:

```
| 改动 | 综合得分 | 平均加速比 |
|------|---------|-----------|
| 逐 r 流式扫描（起点） | 54.89 | 0.13x |
| tile 常驻 + 行内 Kogge-Stone | 66.98 | 0.58x |
| int64 索引在 UB 内 Cast 后直写 | 68.93 | 0.70x |
| 跨核借 R（修 1D 超长用例） | 69.29 | 0.71x |
| fp16/bf16 原生 16 位比较 | 69.84 | 0.74x |
| 行批处理 + 双缓冲（N==1） | 73.37 | 0.91x |
| 借 R 合成单次 launch（SyncAll） | 73.75 | 0.93x |
| **Gather 虚拟转置 + lane 并行顺序扫描** | 79.38 | 1.59x |
| 两行交错填延迟 | 79.95 | 1.69x |
| **16 位输入改用 fp32 比较类型** | 81.63 | 1.85x |
| **mode 0（N>1）加 ping-pong 双缓冲** | 82.41 | 1.92x |
| 借 R 的 phase B 复用行内扫描 | 82.59 | 1.93x |
```

Twelve rows, two cumulative columns, and a single-point-of-largest-gain note at `:48`: the
lane-parallel row alone accounts for 0.66× of the 1.80× total gain.

The retraction, `:50-51`:

```
> 注意倒数第三行**推翻了第五行**：`fp16/bf16 原生 16 位比较` 是在 Kogge-Stone 时代测出的收益，
> 换成 lane 并行扫描后完全反转（见 §2 的更正）。**换扫描算法后必须重测比较类型的选型。**
```

**A published table that annotates its own row as overturned by a later row of the same table is,
across this whole corpus, unique.** Every other retraction this book has found is implicit — a script
contradicting its document, a number restated differently elsewhere. This one is marked.

The measurement behind it, `:75-87`:

```
> **⚠️ 这条结论只对 Kogge-Stone 成立，走 lane 并行扫描时必须反过来（一律升 fp32）。**
> 16 位的 `DataCopyGather`/`DataCopyScatter` 没有全速路径。同为 `1152×1024` 个元素的实测：
>
> | | Kogge-Stone | lane 并行 |
> |---|---|---|
> | fp16（原生 16 位比较） | 18.55µs | 15.05µs |
> | fp32 | 28.58µs | **9.27µs** |
>
> Kogge-Stone 下 fp16 比 fp32 快 1.54 倍（符合 128 vs 64 lane 的预期），
> lane 并行下却慢 1.62 倍。注意 fp16 的 gather 指令数只有 fp32 的一半（36 vs 68）、
> 元素触达数也相当，却慢近两倍——**方向反了就只能是 gather 本身的位宽路径问题**。
> 改成一律升 fp32 后 fp16 降到 9.39µs，与 fp32 打平；6 个 16 位用例快 25~38%。
> 排查时先用 `ResourceConflictRatio` 排除了 bank 冲突（`bank_cflt` 仅 0.1%）。
```

This is the best-evidenced passage in the scan shelf and it is worth saying why. It is a **2×2**, not a
pair — the same two dtypes under both algorithms, at one fixed element count, so the interaction is
visible rather than inferred. It reports a *prediction confirmed* (1.54× matching the 128-versus-64
lane ratio) alongside the anomaly, which is what makes the anomaly credible. It reports a
**counter-indication** — fp16 issues half the gather instructions (36 versus 68) and touches a
comparable number of elements, yet is nearly twice as slow — which is the observation that rules out
instruction count as the cause. And it **excludes an alternative hypothesis by measurement**, naming
the metric and its value (`bank_cflt` 0.1%), which is the discipline this book's `0317` demands.

What it does not have: a repetition count, a variance, a board, and — for the concluding mechanism — a
measurement. `方向反了就只能是 gather 本身的位宽路径问题` is an inference by elimination from two
excluded alternatives, stated in the same voice as the four measured numbers above it. Under this
book's own rule, that is a measurement and an inference in one passage, and the passage's scope covers
only the two alternatives that were checked. Recorded as `Q-950fin-30`.

The reversal also propagates into two other claims of this shelf. `usage_guide.md:118-120` says the
index type must match the comparison type in width and that since the comparison type is now uniformly
4 bytes, indices are int32 throughout — so the retracted row's removal is what makes the index design
simple. And the bank-conflict predicate (`0483`) is stated over `S * sizeof(C)`, whose `sizeof(C)`
changed from 2 to 4 with this reversal, so the same segment length crosses the predicate differently
before and after. Neither document notes that.

One file, one repository: one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first — the whole 2×2 spans 9.27 to 28.58 µs and
`0418` records a ~30 µs dispatch floor on the local timing path, so the timing method is decided
before any number is taken.

**Arm 1 — the 2×2, reproduced.** `1152 × 1024` elements, four builds: {Kogge-Stone, lane-parallel} ×
{16-bit native comparison, fp32 promotion}. Report median and IQR of ≥20 runs each, plus gather
instruction counts and elements touched, plus `bank_cflt`. Upstream's four numbers and both ratios are
the prediction.

**Arm 2 — the mechanism, which upstream infers.** For the lane-parallel fp16 build, measure the gather
path directly: issue the same `DataCopyGather` pattern with no scan around it, at 16 and 32 bits, and
report per-instruction throughput. `Q-950fin-30` asks whether the bit-width path is the cause; this
arm answers it by measuring the suspect rather than by eliminating others.

**Arm 3 — the reversal's boundary.** Sweep the element count and the row count around `1152 × 1024`
and report where the 16-bit build stops losing under lane-parallel. Upstream gives one point and a
blanket rule (`一律升 fp32`); the boundary is what a consumer needs and what nobody has.

**Arm 4 — the propagation, retained because it may not bite.** With `sizeof(C)` set to 2 and to 4,
report whether the same segment length `S` lands on opposite sides of the bank predicate (`0483`) and
whether the measured conflict follows. If it does, the retracted row and the bank rule are coupled and
neither document says so.

Refuses to assume: that a free die stays free, or that a die may be substituted; that the local timing
path is usable at these magnitudes (`0418` — the method is chosen and reported); that instruction count
predicts time (arm 1 reports both because upstream's own counter-indication is that it does not); that
eliminating two hypotheses establishes a third (arm 2 measures the third); that one element count
characterises the reversal (arm 3).

## 5 · Checker — acceptance declared before the run
Verdict `ratio(algorithm) = t(fp16) / t(fp32)` for both algorithms, declared before the run with IQRs.
Acceptance for the reversal: `ratio(Kogge-Stone) < 1` and `ratio(lane-parallel) > 1`, with both
outside the floor. The OVERTURN fires iff `ratio(lane-parallel) < 1` at upstream's shape.

Verdict `gather_throughput(bits)` from arm 2, per instruction. Declared now: upstream's stated
mechanism is supported iff the 16-bit gather's throughput is materially below the 32-bit one's in
isolation. If it is not, the cause is elsewhere and upstream's elimination was incomplete — which is a
finding about the reasoning, not about the reversal, and the two are reported separately.

Verdict `reversal_boundary` from arm 3: the element count at which `ratio(lane-parallel)` crosses 1.

The exit code is not the verdict: all four builds are correct and differ only in time. Guards: (1)
every point carries its IQR and its timing method, and a point reported without both is `untestable` —
a 1.62× ratio between two numbers with no spread is not a ratio; (2) **the input that makes this
checker go red**: the Kogge-Stone column, whose 1.54× upstream predicts from the 128-versus-64 lane
ratio — if that column does not reproduce, the harness is not building the two comparison types
differently at all and the lane-parallel column's reversal is an artifact; (3) no point is reported
without its element count, row count, dtype, algorithm, gather instruction count, `bank_cflt`, floor
and CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The twelve-row table, the
retraction note, the 2×2 with its two ratios, the instruction counts, the bank-conflict exclusion and
the concluding mechanism are file reads performed at drafting time, each re-verified against the file.
The observation that the table's columns are cumulative and therefore cannot show which rows survived,
and the observation that upstream's mechanism sentence is an inference by elimination sitting in the
same voice as four measured numbers, are readings of upstream's own lines, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish any of the twelve scores, the four
timings, or the two ratios; upstream names a tool (cann-bench) and a suite but no board, no repetition
count and no variance. It does not establish the gather bit-width mechanism, which upstream reaches by
eliminating instruction count and bank conflict and does not measure (`Q-950fin-30`). It does not
establish where the reversal begins or ends — one element count is reported and a blanket rule is
drawn from it. It does not establish that the other eleven rows survived into the final score; the
table's cumulative form cannot show that and upstream annotates only one reversal. It does not
establish the `25~38%` gain on the six 16-bit cases, or the 9.39 µs figure, both stated in the same
passage without shapes. It does not carry the index-width consequence or the bank-predicate coupling
beyond naming them (`0483`). No board token appears in the file, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
