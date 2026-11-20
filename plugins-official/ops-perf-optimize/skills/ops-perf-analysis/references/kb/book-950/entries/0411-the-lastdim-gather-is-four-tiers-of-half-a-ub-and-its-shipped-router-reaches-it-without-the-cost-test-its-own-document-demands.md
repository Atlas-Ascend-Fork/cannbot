```
ID:        0411-the-lastdim-gather-is-four-tiers-of-half-a-ub-and-its-shipped-router-reaches-it-without-the-cost-test-its-own-document-demands
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/gather/guide.md:212-216 —
           "1. **dim==last（末轴 gather）** → **LastDim 路径**（TILING_KEY=2）：内部 4 级分层
           / - `batchProcess`：x 行 + index + y 放得下 UB/2 → 多行批量 DataCopyGather 向量化
           / - `singleRow + indexSlice`：x 行放得下 UB/2 但 index 放不下 → 单行 x + index 切片
           / - `singleRow + xSlice`：x 行放不下 UB/2 → x 切片 + mask 筛选 + Gather
           / - `scalarMode`：xSliceNum > 5 或 ratio > 256 → 标量兜底（index DMA + x GM GetValue）"
SOURCE:    same shelf, templates/gather_elements_v2_last_dim.md:57-65 — the resident/direct cost pair,
           and "成本模型只用于筛选，不能替代代表 case A/B。不要使用 case ID、64 MiB/128 MiB 等固定输出阈值。"
SOURCE:    same shelf, templates/gather_elements_v2_route.template:96-98 —
           "if (p.isLastDim) { / return GatherElementsV2Route::LAST_DIM; / }"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a last-axis `PER_ELEMENT` gather on a named 950 board at which the LastDim template is
           slower than the SIMT template by more than the variance floor — the router's unconditional
           `isLastDim` short-circuit would then be demonstrably wrong, not merely inconsistent with its
           own documents. Equally, and in the other direction: a sweep in which LastDim wins at every
           shape including a deliberately hostile one would show the cost test the documents demand is
           unnecessary and the short-circuit is right.
```

# 0411 · The LastDim gather is four tiers of half a UB, and its shipped router reaches it without the cost test its own document demands

## 1 · Claim
Upstream asserts a dedicated last-axis `PER_ELEMENT` gather path carrying `TILING_KEY=2` and an
internal four-tier hierarchy selected by how much of UB the working set needs: everything (an `x` row,
the index and the output) fitting in **half** of UB selects multi-row batched `DataCopyGather`; the `x`
row fitting but the index not selects a single `x` row with the index sliced; the `x` row not fitting
selects `x` sliced with mask filtering; and `xSliceNum > 5` or a ratio above 256 drops to a scalar
fallback that reads `x` from GM by `GetValue`. Upstream asserts, in the template's own document and
again in the family index, that LastDim must not be chosen on `dim == last` alone — a resident-traffic
cost must be compared against a direct-random-read cost first, and the cost model only screens
candidates rather than replacing an A/B on representative cases. Upstream's shipped router returns
`LAST_DIM` as its first statement, on `isLastDim` alone, before any cost model runs. Not established
here.

## 2 · The wrong branch this removes
Without this entry an agent planning a last-axis `torch.gather` does what the router does: sees
`dim == last`, emits the LastDim path, and stops. That is not obviously wrong — LastDim is the
purpose-built template and it usually is right — but it discards the one comparison the family says is
load-bearing. `resident_cost` scales with **output rows** times the whole `x` row; `direct_cost` scales
with **output elements**. When the index selects only a few positions per row, the resident path pays
for an entire `x` row to serve a handful of gathers, and a direct random read is cheaper. The router
cannot see that, because the ratio it would need is not among the inputs it tests.

The second wrong branch is the over-correction: treating the four tiers as a UB-capacity ladder to be
descended mechanically. Three of the four boundaries are capacity tests, but the fourth is not.
`scalarMode` fires on `xSliceNum > 5` **or** `xAxisSize / indexAxisSize > 256` — a slice *count* and a
shape *ratio*, neither of which is a capacity question, and the second of which is the same
resident-versus-direct trade the router skipped, appearing four tiers down as a bare constant. An agent
that reads all four as "does it fit" will apply the wrong model to the one that decides when the
purpose-built path stops paying.

## 3 · Ground / Source
The four tiers, `reference/gather/guide.md:212-216`:

```
1. **dim==last（末轴 gather）** → **LastDim 路径**（TILING_KEY=2）：内部 4 级分层
   - `batchProcess`：x 行 + index + y 放得下 UB/2 → 多行批量 DataCopyGather 向量化
   - `singleRow + indexSlice`：x 行放得下 UB/2 但 index 放不下 → 单行 x + index 切片
   - `singleRow + xSlice`：x 行放不下 UB/2 → x 切片 + mask 筛选 + Gather
   - `scalarMode`：xSliceNum > 5 或 ratio > 256 → 标量兜底（index DMA + x GM GetValue）
```

and the host functions that implement them, `:228-233`:

```
> **LastDim 路径的 4 级分层（参考 ops-nn `GatherElementsV2LastDimTiling`）**：
> - 合轴（`MergeAxis`）：将相邻同尺寸轴合并，降低维度复杂度
> - `IfEnableBatch`：判断 x 行 + index + y 是否放得下 UB/2 → `batchProcess_` 标志
> - `DoUBSlice`：根据 batchProcess / xAlignSize / UB 容量选择 4 级策略
> - `DoScalarMode`：xSliceNum > 5 或 xAxisSize/indexAxisSize > 256 时降级为标量模式
```

The second listing names the ratio the first abbreviates: `ratio` is `xAxisSize / indexAxisSize`, the
gather-axis length of `x` over that of `index`. So `> 256` means *the source row is more than 256×
longer than the number of positions gathered from it* — which is exactly the regime in which loading a
whole resident row to serve a few gathers stops paying. The tier boundary and the cost model are the
same question in two notations, and only one of them carries a number.

Three constants, none derived anywhere in the family: the `UB/2` fraction (used twice), `5`, and `256`.
Under `0104` all three trace to literals rather than to a chip-configuration chain, so all three are
software 经验值 a search may cross — a disposition worth stating because the surrounding prose forbids
crossing them by shape (`0412`).

The device side, `templates/gather_elements_v2_last_dim.md:18-35`, showing what the tiers select
between:

```
Device (每核):
  三种子模式:
    ProcessScalarMode: scalarMode==1 时, 标量逐元素 (小规模兜底)
    ProcessMultRow: eachCalculationLines>1 时, 多行并行 gather
    ProcessSingleRow: 默认, 单行 gather

  ProcessSingleRow / ProcessMultRow:
    对每个 preDim × postDimBlock:
      CopyInX: DataCopyPad(连续读 x 行 from GM → UB, GD 个元素)
      CopyInIdx: DataCopyPad(连续读 index 行 from GM → UB)
      Compute:
        Muls(idxLocal, idxLocal, sizeof(T_X))  // 索引转字节偏移
        Gather(yLocal, xLocal, offsetLocal, 0, count)  // UB 内向量化 gather
      CopyOutY: DataCopyPad(UB → GM)
```

Note that the four *tiling* tiers collapse to **three** device sub-modes: `indexSlice` and `xSlice`
both run `ProcessSingleRow`, differing in what the host sliced. So the "4 级分层" is four host
decisions over three kernels.

The cost model the tiers sit under, `templates/gather_elements_v2_last_dim.md:53-65`:

```
## 6. Host 成本门控与 shape 语义

先按 SoC UB、对齐和 buffer 布局生成可行 tiling，再用下式筛选候选：

resident_cost = output_rows ×
  (x_last_dim × xBytes + index_last_dim × (indexBytes + xBytes))

direct_cost = output_elements ×
  (indexBytes + xBytes + random_read_transaction_penalty)

成本模型只用于筛选，不能替代代表 case A/B。不要使用 case ID、64 MiB/128 MiB 等固定输出阈值。
```

`random_read_transaction_penalty` is the model's only free parameter and the family never gives it a
value, so `direct_cost` cannot be evaluated as written — which means the screen the router skips is
also, as published, not runnable. That is the sharper half of this entry: the missing test is not
merely bypassed, it is under-specified. Recorded in `harvest/standing/950-td.md` as `Q-950td-03`.

Restated at the index level, `guide.md:235`:

```
> **LastDim Host 适配**：torch.gather 允许非 gather 轴 `index.shape[i] <= x.shape[i]`。输出行数必须按 index shape 计算，x/index 必须保存各自的 shape 和 stride；不要沿用按 x shape 计算输出行数的模板假设。启用 LastDim 前还要比较整行 resident 流量与 direct random GM 成本，不能只判断 `dim==last`。
```

`不能只判断 dim==last` — do not decide on `dim == last` alone. And the shipped router,
`templates/gather_elements_v2_route.template:94-99`:

```cpp
inline GatherElementsV2Route SelectGatherElementsV2Route(const GatherElementsV2RouteParams& p)
{
    if (p.isLastDim) {
        return GatherElementsV2Route::LAST_DIM;
    }
    if (CanUseInternalTranspose(p)) {
```

decides on `dim == last` alone, in its first statement. Its parameter struct carries `xGatherDim` and
`idxGatherDim` — the two quantities `ratio` is built from — so the inputs for the test are present and
unused. Registered as `C-950td-012` (also cited by `0407`).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over
median, beside every point.

**Arm 1 — the tier boundaries.** Query UB at runtime (`0141`) and construct last-axis `PER_ELEMENT`
FP16 gathers that land on each of the four tiers by construction, plus a point on each side of each
boundary: around `x row + index + y == UB/2`, around `x row == UB/2`, at `xSliceNum ∈ {4, 5, 6}`, and
at `xAxisSize/indexAxisSize ∈ {200, 256, 300}`. One compiler pin, host echo of the selected tier,
`batchProcess_`, `xSliceNum`, the two axis sizes, the queried UB, and `eachCalculationLines`. Confirm
the tier flips at exactly the stated constant. Record `aiv_time`, ≥10 iterations, first 5 dropped, and
elementwise correctness against a CPU reference at every point.

**Arm 2 — the skipped test, which is this entry's reason.** Along a sweep of
`ratio = xAxisSize / indexAxisSize` from 1 to 4096 at fixed output size, build LastDim (all four tiers
as selected) **and** SIMT, and record both. The router sends every one of these to LastDim. Upstream's
cost model predicts a crossover; this arm is where it is or is not. If a crossover exists, report the
`ratio` at which it occurs and compare it against the `256` that `scalarMode` uses — upstream's own
tier boundary is a candidate answer to the question its router does not ask, and the two numbers
agreeing would be a real result.

**Arm 3 — pin down the free parameter.** `random_read_transaction_penalty` has no value upstream. From
arm 2's crossover, solve `resident_cost = direct_cost` for it and report the implied value with its
uncertainty. This converts an unusable model into a usable one, or shows that no single value fits the
sweep — which would be the finding that the model's form is wrong, not just its constant.

**Arm 4 — the three-kernel/four-tier gap.** Confirm from the echo that `indexSlice` and `xSlice` both
enter `ProcessSingleRow` and differ only in host-computed slice parameters. Retained because it is
expected to confirm §3's reading; if the two tiers enter different device code, §3 is wrong about the
structure even though every quote in it is right.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ub_size` is a
literal (queried and echoed); that the tier the host selected is the tier the kernel ran (the echo is
required, and a point whose echoed tier differs from the predicted one is a *finding*, not a discard);
that `random_read_transaction_penalty` has any value (arm 3 derives it rather than assuming one); that
a fast result is a correct one.

## 5 · Checker — acceptance declared before the run
Verdict `tier(point)` — the echoed tier — and `tier_flips_at_constant`: true iff each of the four
boundaries flips the tier at exactly the stated constant (`UB/2` twice, `xSliceNum = 5`, `ratio = 256`),
within one sweep step. Declared before the run: a boundary that flips elsewhere means the constant in
the document is not the constant in the code, which is a finding of its own.

Verdict `lastdim_loses` from arm 2: true iff SIMT's median `aiv_time` is below LastDim's by more than
the floor at any `ratio` in the sweep. Declared before the run: this entry is **supported** iff
`lastdim_loses == true` — the unconditional `isLastDim` short-circuit then demonstrably selects a
losing path somewhere, and the cost test the documents demand is load-bearing. The OVERTURN fires iff
`lastdim_loses == false` across the whole sweep including the hostile end: LastDim would then win
everywhere on `dim == last`, and the router's short-circuit would be correct despite contradicting its
own documents.

Verdict `penalty_fit` from arm 3 ∈ {`single_value`, `no_consistent_value`}, with the fitted value and
its range when `single_value`.

The exit code is not the verdict: a gather with wrong indices exits 0 and is fast. Three guards.
First, every point is compared elementwise against a CPU reference and the checker fails red if any
comparison did not execute. Second, **the input that makes this checker go red**: arm 2's sweep
includes `ratio = 1` (index as long as the source row), where the resident path serves every element it
loads and LastDim must win. If SIMT wins even there, the harness is not building LastDim correctly and
every crossover in the sweep is an artifact — a sweep whose only outcome is "the dedicated template
loses" cannot distinguish a real crossover from a broken build. Third, no point is reported without its
floor, its md5s, its echoed tier and the queried UB; a point missing any of them is untestable, never
agreement.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The tier listing, the two
constants, the cost pair and the router's first statement are file reads performed at drafting time.
The observation that four tiling tiers map onto three device sub-modes is a reading of upstream's own
flow block, not an observation of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that LastDim ever loses — it establishes
that two of the family's documents require a comparison the shipped router does not make, and that the
comparison as published cannot be evaluated because `random_read_transaction_penalty` has no value. It
does not establish `UB/2`, `5`, or `256`, and does not establish that `ratio` means
`xAxisSize / indexAxisSize` beyond the second listing saying so. It does not establish `TILING_KEY=2`
as the shipped key. It does not establish that the four tiers are exhaustive or correctly ordered. It
does not resolve whether the router's short-circuit is a defect or a deliberate simplification —
upstream never comments on the inconsistency, and §5 declares the outcome under which the router is
right. It does not extend to `PER_SLICE` last-axis gathers, which route to SIMD last-axis Gather or GA
full-load instead (`0147`, `0409`), or to `dim != last` (`0407`, `0410`). It does not cover the
`MergeAxis` collapse step beyond naming it, or the shape-separation obligation stated in the same
paragraph (`0413`). No board token appears anywhere in the gather family on either shelf, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
