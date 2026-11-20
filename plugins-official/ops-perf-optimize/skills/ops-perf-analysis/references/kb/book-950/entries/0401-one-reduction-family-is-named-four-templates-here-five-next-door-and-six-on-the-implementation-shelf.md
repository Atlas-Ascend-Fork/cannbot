```
ID:        0401-one-reduction-family-is-named-four-templates-here-five-next-door-and-six-on-the-implementation-shelf
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/reduction/patterns.md:32-39 —
           "Step 2: A0 决定模式 / ├─ A0 = 1 → AR 模式（每行 R 个元素连续，用 Level 2 Reduce API）
           / │   ├─ 可以在UB中至少处理1整行数据 → AR-FullLoad    → [ar-fullload.md]
           / │   └─ 否则 → AR-ColSplit    → [ar-colsplit.md] / │
           / └─ A0 > 1 → ARA 模式（[R,A0] 块连续，用 Pattern::Reduce::RA）
           / ├─ 可以在UB中处理所有R*tileA0Len数据（32字节对齐） → ARA-FullLoad  → [ara-fullload.md]
           / └─ 否则 → ARA-RowSplit  → [ara-rowsplit.md]"
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-fields.md:3 —
           "五模板（AR-SmallR / AR-FullLoad / AR-Recompute / ARA-FullLoad / ARA-Recompute）的
           TilingData 字段并集。" (same repo — contrast, not corroboration)
SOURCE:    ops/ascendc-performance-best-practices/reference/reduce/guide.md:87,93-97,210 —
           "离线模板针对**独立 Kernel** 的 Reduce 算子……按 R 能否载入 UB 与输入维数分为 5 个。" ·
           "| **ARA-Online** | 3D `[A1,R,A0]` | 沿 R 分 chunk 在线更新 running max/sum，输入读 2 次 |"
           (same repo — contrast, not corroboration)
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a case, built on a named 950 board, that the design shelf's tree routes to AR-ColSplit and
           the analysis shelf's tree routes to AR-SmallR (any `R` at or below `r_small_threshold` that
           does not fit one row in UB is impossible, so the discriminating case is the reverse: an
           `R ≤ 16` FP32 reduction, which the design tree sends to AR-FullLoad and the analysis tree
           sends to AR-SmallR), built and timed both ways, in which the two plans measure the same
           within the variance floor. The naming difference would then be vocabulary only, and this
           entry's claim that the shelves partition the space differently would be wrong.
```

# 0401 · One reduction family is named four templates here, five next door, and six on the implementation shelf

## 1 · Claim
Upstream asserts three different template vocabularies for one operator family, in three of its own
skills. The design shelf (`ascendc-tiling-design`) asserts **four**: after collapsing to `(A1, R, A0)`
and splitting on `A0 == 1`, each family has a full-load arm and a split arm — AR-FullLoad /
AR-ColSplit and ARA-FullLoad / ARA-RowSplit. The analysis shelf (`ascendc-perf-optimize`) asserts
**five**, calling the split arms *Recompute* instead of ColSplit/RowSplit and adding a third AR arm,
AR-SmallR, for a reduction axis too short to fill a vector register. The implementation shelf
(`ascendc-performance-best-practices`) asserts the analysis shelf's five under the analysis shelf's
names, and adds a **sixth**, ARA-Online, which it files under a separate heading (在线计算模板) rather
than inside the five. Upstream nowhere states that these are the same taxonomy under different names,
and nowhere maps one onto another. Not established here.

## 2 · The wrong branch this removes
The names are the interface. A consuming agent is told to produce a tiling plan and a `templateType`,
and its output is read by whoever owns the kernel. If the agent read the design shelf it emits
`ARA-RowSplit`; if it read the analysis shelf it emits `ARA-Recompute`; the implementation shelf's
`softmax_v2_ara_recompute.h` is what actually exists as code. Two of those three strings do not name
a file anybody ships. That is a routing failure that no correctness test catches, because the tiling
numbers may be perfectly good.

The subtler wrong branch is the missing arm. The design shelf's AR tree has **no small-R arm at all**.
An agent that has read only `reduction/patterns.md` meets an `R = 16` FP32 LayerNorm, asks "can I hold
one whole row in UB?", answers yes trivially, and routes to AR-FullLoad. It never learns that a
transposed `(R, A1)` layout exists, and it does not know it is leaving vector lanes empty — the
analysis shelf gives the reason (`R 极小时通过转置布局优化访存`, `tiling-flow.md:19`) and the
implementation shelf gives the magnitude (`VReg 利用率从 R/64 拉到 ~100%`,
`reduce/guide.md:236`). The design shelf's tree is not wrong at that shape; it is *silent*, and a
first-match decision tree that is silent produces a confident answer.

The third wrong branch is the opposite over-correction: reading the three vocabularies as three
disagreements to be reconciled by picking one. They are not all the same kind of difference.
ColSplit-vs-Recompute is a name over two arms that also differ mechanically (0402). SmallR is an arm
one shelf has and another lacks. ARA-Online is an arm that exists as shipped code on one shelf and
is named nowhere on the other two. An agent that "resolves" this by adopting one vocabulary silently
deletes whichever arms that vocabulary lacks.

## 3 · Ground / Source
The design shelf's tree, `ascendc-tiling-design/references/reduction/patterns.md:19-45`, in full:

```
## 场景判定流程

给定: shape, axes (归约轴)

Step 0: 合轴（见上节）
  标记 A/R → 消除冗余维 → 合并相邻同类型轴

Step 1: 合轴后是单轴还是多轴？
  ├─ 单轴（AR 或 ARA）→ Step 2
  └─ 多轴（ARAR 等交替序列）→ Shape 三步变换（详见 multi-axis-transform.md）
       展开为嵌套循环，每个 R 维的归约按 Step 2 判定

Step 2: A0 决定模式
  ├─ A0 = 1 → AR 模式（每行 R 个元素连续，用 Level 2 Reduce API）
  │   ├─ 可以在UB中至少处理1整行数据 → AR-FullLoad    → [ar-fullload.md]
  │   └─ 否则 → AR-ColSplit    → [ar-colsplit.md]
  │
  └─ A0 > 1 → ARA 模式（[R,A0] 块连续，用 Pattern::Reduce::RA）
      ├─ 可以在UB中处理所有R*tileA0Len数据（32字节对齐） → ARA-FullLoad  → [ara-fullload.md]
      └─ 否则 → ARA-RowSplit  → [ara-rowsplit.md]
```

Four leaves, and four files behind them (`ar-fullload.md`, `ar-colsplit.md`, `ara-fullload.md`,
`ara-rowsplit.md`) — the directory listing confirms all four exist and no fifth reduction-branch file
does. The branch tables at `:97-100` and `:153-156` repeat the same four under the labels 全载 and
分载.

The analysis shelf's five, `ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:132-138`:

```
### 模板速查

| 模板 | 维度 | R 条件 | 关键策略 |
|------|------|--------|---------|
| AR-SmallR | A0=1 | R 极小 | 转置布局，沿 A1 切 tile |
| AR-FullLoad | A0=1 | R 可全载 | R 驻留 UB，A1 切分 |
| AR-Recompute | A0=1 | R 过大 | R 分块 + 块间合并 |
| ARA-FullLoad | A0>1 | R 可全载 | A0 切 tile，R 全载 |
| ARA-Recompute | A0>1 | R 过大 | A0 切 tile，R 分块循环 |
```

and its glossary rows at `:15-19` defining the three words the design shelf does not use:

```
| **FullLoad** | R 方向数据一次全部载入 UB |
| **Recompute** | R 方向超出 UB 容量，分块处理并在块间合并 |
| **SmallR** | R 极小时通过转置布局优化访存（仅 AR 模式） |
```

That vocabulary is already carried by this book at `0122` (selection) and `0123` (budgets), so nothing
from the analysis shelf is re-entered here; it is quoted as the other side of the disagreement.

The implementation shelf's six, `ascendc-performance-best-practices/reference/reduce/guide.md`. Its
offline table at `:87-97` carries the analysis shelf's five names verbatim:

```
离线模板针对**独立 Kernel** 的 Reduce 算子，输入已完整存在于 GM，按 R 能否载入 UB 与输入维数分为 5 个。

| 模板 | 输入 | R 与 UB 关系 | 核心策略 |
| **AR-SmallR** | 2D `[A1,R]` | R 极小（FP32≤16/FP16≤32） | 转置为 `(R,A1)`，沿 A1 向量化 |
| **AR-FullLoad** | 2D `[A1,R]` | R 全量载入 UB | 多行批量载入，单 pass VF 计算 |
| **AR-Recompute** | 2D `[A1,R]` | R 超出 UB | R 切 chunk，3 阶段重读 GM + 二分累加树 |
| **ARA-FullLoad** | 3D `[A1,R,A0]` | R 全量载入 UB | 沿 A0 切 tile，跨 R 逐列 VF |
| **ARA-Recompute** | 3D `[A1,R,A0]` | R 超出 UB | R 切 bin，3 阶段跨 bin 二分折叠 |
```

and its sixth sits under a different heading, `:204-212`:

```
## 在线计算模板

### 独立 ARA Online Softmax

| 模板 | 输入 | 核心策略 |
| **ARA-Online** | 3D `[A1,R,A0]` | 沿 R 分 chunk 在线更新 running max/sum，输入读 2 次 |
```

The sixth is not a rename of anything the other shelves carry, and it is not the Welford Online
algorithm the design shelf lists as an orthogonal dimension (`patterns.md:51`,
`algorithms.md:13-14`): Welford is a single-pass update of two *correlated statistics* (mean and M2)
for var/std, whereas ARA-Online maintains a running max and a running sum for Softmax, and the
implementation shelf's own comparison table (`softmax_v2_ara_online.md:90-96`) contrasts it only
against ARA-Recompute, never against Welford. Three shelves, three different answers to "what is the
sixth thing".

The three shelves are three directories in one repository, so under RULES.md Art. 3 none of them
corroborates another and the disagreement is a contradiction, not a majority vote. Registered as
`C-950td-001` (four-vs-five-vs-six) and `C-950td-002` (ColSplit/RowSplit vs Recompute as names over
mechanically different arms — see 0402).

One asymmetry is worth recording because it changes how the disagreement should be read. The
implementation shelf explicitly denies that its table is a decision procedure — `guide.md:7`:

```
> 本指南是**优秀实践目录**，而非选型决策树：每个模板列出其适用条件与解决的问题，由实现者根据实际
> shape、UB 容量与带宽情况判断采用。Reduce 族算子形态多样，不存在普适的"唯一最优"，理解各模板的
> 权衡是正确适配的前提。
```

repeated at `:89` (`下表"适用条件"是模板的设计前提，非强制决策规则`) and `:280`
(`以上是"特征—模板"对应关系，非决策树`). Both other shelves present their tables as trees with
first-match arms. So the shelves differ not only in how many templates there are but in whether the
table is a rule at all. That is carried separately at 0403.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first, before any comparison: one build, 30 in-process runs and
5 fresh-process runs, IQR over median, reported beside every number below.

This entry's claim is that the three vocabularies partition the space differently, so the procedure
must find a shape where the partitions disagree and show the disagreement costs something.

**Arm 1 — the SmallR gap, which is the only gap that produces two different plans for one shape.**
Fix a 2-D ReduceSum, FP32, `A1 = 65536`, and sweep `R` over `{4, 8, 12, 16, 24, 32, 64, 128}` — a
range that straddles the analysis shelf's `r_small_threshold` (`FP32 约 16`, `tiling-flow.md:98`).
At every `R`, build two kernels: (a) the design shelf's answer, AR-FullLoad per `ar-fullload.md`,
and (b) the analysis shelf's answer, AR-SmallR per `tiling-flow.md:212` §4.1 with its transposed
`(R, A1)` layout and `a0_tile_unit = 64`. One compiler pin, md5 each binary, host echo of the
selected template name and of `R`, `A1`, `ub_size` and `core_num` as the kernel actually received
them. Compare both outputs elementwise against a CPU reference. Record `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped.

**Arm 2 — ColSplit versus Recompute on one shape, which is 0402's subject but is built here so the
two arms share a baseline.** Fix a 2-D ReduceSum, FP32, `A1 = 4096`, `R` chosen so that one row does
not fit UB at the runtime-queried capacity (`0141`, `GetCoreMemSize(CoreMemType::UB)`) — take
`R = 4 × (queried usable elements)`. Build the design shelf's AR-ColSplit (scalar `globalMax`/`+=`
merge, `ar-colsplit.md:101-121`) and the analysis shelf's AR-Recompute (binary fold with
`binary_cache = 2048`, `tiling-flow.md:253-277`). Record `aiv_time` and, because the merge order
differs, the elementwise max absolute error of each against a **float64** CPU reference — not against
each other, and not against a float32 reference, which cannot expose either one's accumulation error.

**Arm 3 — does the sixth template exist as a distinguishable plan?** For a 3-D Softmax
`[A1, R, A0] = [8, 8192, 256]`, FP32, build ARA-Recompute and ARA-Online from the implementation
shelf's two `.template` files and record `aiv_time` plus the MTE2 byte count. Upstream predicts
2 R-reads versus 3 (`softmax_v2_ara_online.md:90-96`), so the MTE2 byte counts should stand in a
ratio near 2:3; if they do not, the sixth template is not doing what its own table says and the
"six" count is a documentation artifact.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ub_size` or
`core_num` are literals (both are queried at runtime and echoed, per `0141` / `0207`); that a build
labelled with a template name ran that template (the host echo is required, and an arm without a
distinct md5 and a distinct echoed name is discarded, not interpreted); that the three shelves' names
denote the same code (each arm is built from the shelf's own file, and the file path is echoed).

## 5 · Checker — acceptance declared before the run
Verdict `smallr_gap(R)` = median `aiv_time` of AR-FullLoad divided by median `aiv_time` of AR-SmallR
at that `R`, with the variance floor. Declared before the run: this entry is **supported** iff
`smallr_gap(R) > 1 + floor` for at least one `R ≤ 16` — i.e. the arm the design shelf does not have
is faster somewhere inside the range where only the analysis shelf offers it, so the design shelf's
silence costs time. The OVERTURN fires iff `smallr_gap(R) ≤ 1 + floor` for **every** `R` in the
sweep: SmallR would then buy nothing on this board, the design shelf's four-template tree would be
complete rather than silent, and the count difference would be vocabulary. The entry is corrected in
place in that case.

Verdict `merge_err` = the pair (max abs error of ColSplit, max abs error of Recompute) against the
float64 reference, from Arm 2. Declared before the run: 0402's prediction is
`merge_err(ColSplit) > merge_err(Recompute)`. Reported here as an input to 0402, not as this entry's
pass condition.

Verdict `online_ratio` = MTE2 bytes(ARA-Online) / MTE2 bytes(ARA-Recompute) from Arm 3. Declared
before the run: upstream's table predicts `0.60 ≤ online_ratio ≤ 0.73` (2/3 ± 10 %). A value outside
that band means the two templates do not differ as documented.

The exit code is not the verdict. Three guards, because a template-selection study is unusually easy
to confirm by construction. First, every arm is compared elementwise against a CPU reference and the
checker fails red if any arm's comparison did not run — a reduction with a wrong merge exits 0 and
returns a plausible number. Second, **the input that makes this checker go red**: Arm 1 includes
`R = 128`, well above the small-R threshold, where AR-SmallR's transposed layout is expected to be
*slower* than AR-FullLoad. If `smallr_gap(128) > 1`, the instrument is reporting SmallR as faster
everywhere, which means it is measuring something other than the template (a build difference, a
wrong echo, a mis-set `A1`), and every point in the sweep is void. That planted negative is
mandatory: a sweep whose only outcome is "the extra template always wins" has not been shown able to
say otherwise. Third, no `aiv_time` is reported without its floor, its md5 and its echoed template
name and file path; an arm missing any of the three is reported as untestable, never as agreement.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The template counts (four,
five, six) and the file-existence statements in §3 are file reads of upstream's own tree performed at
drafting time, re-derivable by
`ls upstream/skills-dev-main/ops/ascendc-tiling-design/references/reduction/` and
`ls upstream/skills-dev-main/ops/ascendc-performance-best-practices/reference/reduce/templates/`.
No kernel was built and no reduction was run.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that any of the three taxonomies is
correct, and deliberately does not choose between them (RULES.md Art. 7 — a contradiction is resolved by a
procedure on a named board, never by preferring an author). It does not establish that AR-ColSplit and
AR-Recompute are the same algorithm or different ones; that comparison is 0402's, and this entry only
records that the two shelves give the arm different names. It does not establish that ARA-Online is
absent from the analysis shelf's code, only that the analysis shelf's documents never name it. It
does not establish that Welford Online and ARA-Online are different mechanisms beyond what the two
documents state about themselves — neither shelf compares them, and §3's separation is read off their
own descriptions, not measured. It does not establish `r_small_threshold`, `ub_size` or `core_num` for
any board (`0122`, `0131` record that the family's own sources disagree about the last two). It does
not cover the interleaved templates or BlockSplitR, which sit outside all three tables and are already
carried at `0125`–`0128` and `0124`. No board token appears anywhere in the design shelf's reduction
family; the analysis shelf's reduction anchors name `Ascend 950 / arch35（dav-3510）`, which is a
family, not a board — so BOARD is `family-claimed(unverified)` and §4 names 950PR/950DT only because
that is where our run would happen. Nothing here is established for any 910-family board.
