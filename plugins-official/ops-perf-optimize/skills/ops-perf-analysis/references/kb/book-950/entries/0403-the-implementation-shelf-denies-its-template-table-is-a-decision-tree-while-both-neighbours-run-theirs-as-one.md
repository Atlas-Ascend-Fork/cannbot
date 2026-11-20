```
ID:        0403-the-implementation-shelf-denies-its-template-table-is-a-decision-tree-while-both-neighbours-run-theirs-as-one
LABEL:     boundary
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/reduce/guide.md:7 —
           "> 本指南是**优秀实践目录**，而非选型决策树：每个模板列出其适用条件与解决的问题，由实现者
           根据实际 shape、UB 容量与带宽情况判断采用。Reduce 族算子形态多样，不存在普适的"唯一最优"，
           理解各模板的权衡是正确适配的前提。" ; :89 — "> 注：下表"适用条件"是模板的设计前提，
           非强制决策规则。边界 shape（如 R 刚好接近 UB 上限）可由实现者权衡带宽与空间。" ;
           :280 — "> 以上是"特征—模板"对应关系，非决策树。"
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:88 —
           "## 3. 五模板决策树（Step 1–2）" (same repo — contrast, not corroboration)
SOURCE:    ops/ascendc-tiling-design/references/reduction/patterns.md:19 — "## 场景判定流程"
           (same repo — contrast, not corroboration)
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a reduction case on a named 950 board, at a shape the analysis shelf's first-match tree
           routes unambiguously, where a second template the tree does not select measures faster
           than the selected one by more than the variance floor. The tree would then be demonstrably
           not a decision procedure at that shape, and the implementation shelf's refusal to call its
           table one would be the accurate description rather than a difference of authorial voice.
           Equally: a sweep across the family's shape space in which the tree's selection is fastest
           at every point would show the refusal is unnecessary.
```

# 0403 · The implementation shelf denies its template table is a decision tree while both neighbours run theirs as one

## 1 · Claim
Upstream asserts, three times in one file, that its reduction template table is **not** a selection
procedure: a catalogue of good practice rather than a decision tree, whose applicability column states
design premises rather than binding rules, and under which no universally optimal template exists so
the implementer weighs bandwidth against space for boundary shapes. Upstream asserts, in two sibling
skills covering the same five templates, the opposite structure: the analysis shelf heads its section
`五模板决策树` and lays out first-match arms with numeric predicates, and the design shelf heads its
`场景判定流程` and lays out first-match arms with capacity predicates. The three files agree
substantially about which templates exist and what each is for; they disagree about whether the table
obliges anything. Upstream nowhere reconciles this. Not established here.

## 2 · The wrong branch this removes
This is the difference an agent is least likely to notice and most likely to be judged on. Both
readings produce the same answer on the interior of the shape space — a huge `R` goes to the split
arm under any reading. They differ at the boundary, and the boundary is where tiling questions
actually arrive. The implementation shelf names the boundary explicitly: `边界 shape（如 R 刚好接近 UB
上限）`. At `R` just under the full-load capacity, the tree says FullLoad and stops; the catalogue says
FullLoad *and* the split arm are both admissible and the choice is a bandwidth-versus-space trade the
implementer must make and justify.

Without this entry a harness agent reads whichever file it opened, and its output inherits that file's
modality without ever stating it. An agent that read the tree emits "AR-FullLoad" as a determination.
An agent that read the catalogue emits "AR-FullLoad, and here is why not AR-Recompute". The second is
a better artifact and the first is indistinguishable from it in any automated check, because both name
a legal template. The wrong branch is therefore not a wrong template — it is a **missing
justification**, and missing justifications are invisible to every gate upstream ships.

The second wrong branch is treating the refusal as hedging and discarding it. It is not hedging: the
implementation shelf is the shelf that holds the actual kernel code and the measured EuclideanNorm
case set, and its three refusals are placed at the three points where a reader would otherwise start
obeying — before the document (`:7`), immediately above the offline table (`:89`), and immediately
below the Norm adaptation table (`:280`). A shelf that owns the measurements declining to publish a
decision rule is evidence about the shape space, not modesty. This book has an instance of the same
move being right: the sort family's `这些数值是性能策略，不是架构能力边界` (`0142`).

The third wrong branch is the over-correction — concluding the tree is worthless because its owner's
neighbour disowns it. The analysis shelf's tree carries numeric predicates the catalogue does not
supply anywhere (`r_small_threshold`, the UB budgets, `r_bin_size`), and those are the only thresholds
this family has. Deleting the tree deletes the numbers. The operational reading this entry supports is
narrow: **the tree's arms are admissibility tests, not an ordering** — a shape passing exactly one arm
has one answer, and a shape passing two has a choice that must be measured, not resolved by arm order.

## 3 · Ground / Source
The implementation shelf's three refusals, `ascendc-performance-best-practices/reference/reduce/guide.md`.
The first, `:7`, before any content:

```
> 本指南是**优秀实践目录**，而非选型决策树：每个模板列出其适用条件与解决的问题，由实现者根据实际
> shape、UB 容量与带宽情况判断采用。Reduce 族算子形态多样，不存在普适的"唯一最优"，理解各模板的
> 权衡是正确适配的前提。
```

The second, `:89`, sitting between the sentence that announces five templates (`:87`) and the table
that lists them (`:91-97`):

```
> 注：下表"适用条件"是模板的设计前提，非强制决策规则。边界 shape（如 R 刚好接近 UB 上限）可由
> 实现者权衡带宽与空间。
```

The third, `:280`, closing the Norm adaptation section:

```
> 以上是"特征—模板"对应关系，非决策树。实际选择还需结合 A1/A0 规模、UB 预算、是否需 affine、
> 是否与 matmul 融合等综合判断。
```

Three placements, one message, and the middle one is bound to the table it qualifies rather than to
the document as a whole — which is the placement that survives an agent reading only the table.

The analysis shelf's framing, `ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:88-90`:

```
## 3. 五模板决策树（Step 1–2）

> 前置：先过 [§3.1 多轴交错前置判定](#31-多轴交错前置判定step-05)。命中交错模板则直接返回；
> 未命中（合轴后是简单 AR/ARA，单个 R）才进入本节。
```

`决策树` in the heading, and `直接返回` in the note — first-match, short-circuit. The arms it then
lays out (`:92-129`, carried at `0122`) are `├─ ... → 【AR-SmallR】` form with `└─ 否则` fall-throughs.

The design shelf's framing, `ascendc-tiling-design/references/reduction/patterns.md:1-3,19`:

```
# Reduction 类算子场景路由

> 本文档用于**场景判定**和**策略选择**。确定场景后，按链接进入对应详细文档。
```
```
## 场景判定流程
```

`场景判定` — scenario determination — and its arms are the same `├─ / └─ 否则` shape (`:32-39`,
quoted at `0401`). Neither neighbour carries any sentence limiting the table's force; the word
`推荐` never qualifies an arm in either.

One further asymmetry, which is why the disagreement is not merely stylistic: the two shelves that
publish trees publish **no measurements of alternatives**, and the shelf that refuses to publish a
tree publishes the family's only measured case set. The analysis shelf's reduction anchors are
host-side compiles of its own tiling function (`0124` §7 records that they were never run on a
device); the implementation shelf's EuclideanNorm 20-case table is `msprof 上板实测` and includes
three disclosed misfires where a template selected by an earlier, wider gate lost by 28 % and by 10×
(`0127`). So the shelf with evidence about how badly template selection can go wrong is the shelf that
declines to state a rule. Registered as `C-950td-005`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The claim
under test is not "which template is best" but "does the tree's arm order carry information at shapes
where more than one arm is admissible". So the procedure must find the overlap region and measure
inside it.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs,
IQR over median, beside every point.

**Step 1 — locate the overlap analytically, then verify it empirically.** Query UB at runtime
(`0141`, `GetCoreMemSize(CoreMemType::UB)`) and evaluate the analysis shelf's own budget formulas
(`0123`) to obtain, for FP32 2-D ReduceSum at `A1 = 4096`, the `R` at which AR-FullLoad stops being
admissible (`rows_per_ub` falls below 1). Call it `R*`. Echo `R*` and the UB value it came from. The
overlap region is `R ∈ [R*/8, R*]`: every such `R` is admissible under FullLoad by the tree, and also
admissible under Recompute, which has no upper condition — `条件: R > AR-FullLoad 阈值` is the tree's
gate, not a property of the template, and the implementation shelf's catalogue phrasing is exactly
that both are buildable there.

**Step 2 — build both arms at every point in the overlap.** `R ∈ {R*/8, R*/4, R*/2, 0.75·R*, 0.9·R*,
0.98·R*}`. At each, build AR-FullLoad and AR-Recompute from the implementation shelf's two
`.template` files, one compiler pin, distinct md5s, host echo of the template name, `R`, `A1`, the
queried UB and the resulting `rows_per_ub` / `r_chunk`. Elementwise comparison against a CPU reference
on both arms. Record `aiv_time` and MTE2 bytes under `msprof --aic-metrics=PipeUtilization`, ≥10
iterations, first 5 dropped.

**Step 3 — the same on the 3-D pair.** `[A1, R, A0] = [8, R, 256]` FP32, ARA-FullLoad versus
ARA-Recompute, over the analogous overlap computed from `0123`'s ARA budgets. Included because the
implementation shelf's boundary example (`R 刚好接近 UB 上限`) is stated generally and a result on one
family is one family's result.

**Step 4 — the arm that tests the tree's other admissibility claim.** At `R` just *above* `R*`, build
AR-FullLoad anyway with the tile count forced so it still fits, and record whether it runs correctly
and what it costs. If it runs and is competitive, the tree's `否则` is a threshold on a formula rather
than on the hardware, which is the distinction `0104` makes load-bearing (chip-config constraint =
hard; hardcoded literal = searchable).

Refuses to assume: that a free die stays free; that a die may be substituted; that `ub_size` or
`core_num` are literals (both queried and echoed); that `R*` computed from upstream's formula is the
real capacity boundary (Step 4 is what tests that); that a build named for a template ran it (two
md5s, two echoes, else the point is discarded); that one operator family answers for the others (Step
3 exists for that reason).

## 5 · Checker — acceptance declared before the run
Verdict `overlap_flip` = true iff, at any `R` in the overlap region, the template the analysis shelf's
tree does **not** select has a median `aiv_time` lower than the selected one by more than the variance
floor. Declared before the run: this entry is **supported** iff `overlap_flip == true` in either Step
2 or Step 3 — the tree's arm order would then not be an ordering by performance, and the
implementation shelf's refusal would be the accurate description. The OVERTURN fires iff
`overlap_flip == false` at every point in both steps: the tree's selection would be fastest everywhere
it is defined, the refusal would be unnecessary caution, and this entry is corrected in place.

Verdict `margin(R)` = the signed relative gap between the two arms at each overlap point, reported
with its floor. Declared now so the result is a curve rather than a verdict: the interesting outcome
is `margin` crossing zero somewhere inside the region, which would locate the true boundary and show
the tree's boundary is elsewhere.

Verdict `above_R_star` from Step 4 ∈ {`ran_correct`, `ran_wrong`, `refused`}. `refused` or
`ran_wrong` supports reading `R*` as a hard capacity limit; `ran_correct` supports reading it as a
software literal, and the two readings have different consequences under `0104`.

The exit code is not the verdict — a reduction that read the wrong number of chunks exits 0. Three
guards. First, both arms are compared elementwise against a CPU reference at every point, and the
checker fails red if any comparison did not run. Second, **the input that makes this checker go red**:
the sweep includes `R = 16·R*`, far outside the overlap, where AR-FullLoad is not buildable at all.
The instrument must report that point as `refused`/unbuildable rather than producing a timing. If a
timing appears there, the harness is silently falling back to another template and every point in the
sweep is void — which is the failure mode that would otherwise let this study "discover" that the
non-selected arm wins everywhere. Third, no point is reported without its floor, its two md5s, its
echoed template names and the queried UB value; a point missing any of them is untestable, not
agreement.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The three refusal quotes and
the two tree headings in §3 are file reads performed at drafting time. The observation that the
refusing shelf is the shelf holding the measured case set is a reading of which files carry `上板实测`
banners (`0126`, `0127`) and which do not (`0124` §7), not a measurement made here.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that either modality is correct, and
under RULES.md Art. 7 deliberately does not choose — it records that three sibling documents covering one
template set disagree about whether the set constitutes a rule. It does not establish that an overlap
region exists on any board: `R*` is computed from upstream's own budget formula, which `0123` records
as resting on unmeasured reserves and `0131` records as resting on a UB capacity the family's own
sources give two values for. It does not establish that the tree's thresholds are wrong; it does not
supply any threshold of its own. It does not establish that the implementation shelf's catalogue is
complete — the same shelf adds a sixth template outside the five (`0401`), so "catalogue" does not
imply "exhaustive". It does not extend to the other families: this is the reduce family's
disagreement, and whether the scan, gather or conversion families' tables are trees or catalogues is a
separate reading per family. It does not establish that a consuming agent's output actually loses the
justification (§2's failure is predicted from the documents' modality, not observed). No board token
appears in any of the three files, so BOARD is `family-claimed(unverified)` and §4 names 950PR/950DT
only as where our run would happen. Nothing here is established for any 910-family board.
