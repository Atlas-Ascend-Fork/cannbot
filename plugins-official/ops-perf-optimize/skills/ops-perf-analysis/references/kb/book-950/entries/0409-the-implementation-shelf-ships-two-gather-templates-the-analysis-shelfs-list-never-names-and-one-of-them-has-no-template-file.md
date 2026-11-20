```
ID:        0409-the-implementation-shelf-ships-two-gather-templates-the-analysis-shelfs-list-never-names-and-one-of-them-has-no-template-file
LABEL:     boundary
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/gather/guide.md:212 —
           "1. **dim==last（末轴 gather）** → **LastDim 路径**（TILING_KEY=2）：内部 4 级分层" ;
           :98 — "### 1a. small-GD tiled full-load（PER_ELEMENT 实验性模式）" ; :76 —
           "| dim!=last 候选路径 | 物理 Transpose×3；kernel 内 Transpose；small-GD tiled full-load；
           不满足门控时 Scalar/SIMT | SIMD 行拷贝 / GA 全载 |"
SOURCE:    ops/ascendc-performance-best-practices/reference/gather/templates/
           gather_elements_small_gd_tiled.md:7 — "这是实验性实现模式，当前不提供可直接复制的通用
           `.template`。已有实现若把 gatherDim 写成静态常量，只能作为单一 specialization 使用；
           参数化 `Gx/Gi` 并完成跨 shape 验证前，不得宣称通用。"
SOURCE:    ops/ascendc-perf-optimize/references/tiling/gather/index.md:11 —
           "| 0（兜底） | 通用六模板 | 无条件（回退保障） |" (same repo — contrast, not corroboration)
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `PER_ELEMENT` last-axis gather on a named 950 board where the analysis shelf's routing —
           which has no LastDim arm — selects a template that matches or beats the implementation
           shelf's LastDim template within the variance floor. The missing arm would then cost nothing,
           and the count divergence would be catalogue bookkeeping rather than a capability gap.
```

# 0409 · The implementation shelf ships two gather templates the analysis shelf's list never names, and one of them has no template file

## 1 · Claim
Upstream asserts, in the analysis shelf, a `通用六模板` gather fallback — six templates, listed as
seven in one table and nine in another (`0150`). Upstream asserts, in the implementation shelf's gather
index, a set that includes two the analysis shelf names nowhere: a **LastDim** path carrying
`TILING_KEY=2` with an internal four-tier hierarchy, and a **small-GD tiled full-load** mode marked
`实验性` (experimental) and routed as a first-class `dim != last` candidate alongside the two transpose
paths. Upstream asserts of the second that no reusable `.template` exists for it, that an existing
implementation with a static `gatherDim` is one specialisation only, and that it may not be called
general before `Gx`/`Gi` are parameterised and validated across shapes. Not established here.

## 2 · The wrong branch this removes
`0150` records that this family cannot agree on how many templates it has, and treats that as a
documentation state. This entry is the part that is not bookkeeping. Two of the names are missing from
one shelf and present as shipped artifacts on the other, and the two absences bite in opposite ways.

**LastDim is a missing arm on the commonest case.** `dim == last` is the ordinary `torch.gather`, and
the implementation shelf routes it to a dedicated template with four internal tiers, an
implementation file, a host tiling file, and its own cost model (`0411`). The analysis shelf's tree
has no such arm: a last-axis `PER_ELEMENT` gather lands in its SIMD last-axis / GA full-load /
SIMT-scalar space, gated by the four underived byte thresholds `0148` records. An agent that plans from
the analysis shelf produces a legal plan and never learns that a purpose-built path exists. The failure
is invisible — the plan works.

**small-GD is the opposite: a name that reads like a template and is not one.** It appears in the
index's numbered template list as `1a`, in the `dim != last` candidate row, and in the selection
table — three placements that all say "choose this". Its own file then says there is no `.template` to
copy, that the existing code hardcodes `gatherDim`, and that calling it general is forbidden. An agent
that reads the index and not the detail file will look for a template that does not exist, or worse,
will copy the single specialisation and ship a kernel correct only at one `gatherDim`. Upstream builds
the fence — `不得宣称通用` — one file below where the invitation is issued.

The third wrong branch is treating the count divergence as a merge problem: taking the union and
calling it eleven. The two shelves' lists are not two attempts at one enumeration. The analysis shelf's
list is a *tiling* taxonomy (what UB split and multi-core split to compute), and the implementation
shelf's is a *kernel* catalogue (what code to instantiate). LastDim has a `TILING_KEY`, so it is both;
small-GD has neither a template nor a tiling key, so it is neither yet. A union flattens a working
template, an experimental pattern, and a tiling-only distinction into one list of peers.

The operational content: **the implementation shelf is where the gather kernel inventory lives, the
analysis shelf is where the tiling algebra lives, and the inventory is larger. Check both before
concluding a case has no purpose-built path — and check whether the named path has a file.**

## 3 · Ground / Source
The analysis shelf's count, `ops/ascendc-perf-optimize/references/tiling/gather/index.md:11,13,21,23`:

```
| 0（兜底） | 通用六模板 | 无条件（回退保障） | [fallback/index.md](fallback/index.md) → [fallback/tiling-flow.md](fallback/tiling-flow.md) |
```
```
> ⚠️ 路由命中后**必须深入 fallback/ 子目录**读取 `tiling-flow.md`（六模板决策树 + UB 预算公式）、`tiling-fields.md`（TilingData 字段语义）。禁止仅读本文件的表格后停止。
```

`通用六模板` three times in one file, plus `fallback/index.md:3` (`Gather 族算子的六模板 Tiling 算法。
所有 Gather 算子共享同一套模板语言。`). `0150` records the seven-row and nine-row tables that follow.
Neither `LastDim` nor `small-GD` appears anywhere in that shelf's gather subtree.

The implementation shelf's inventory, `reference/gather/guide.md:84-161`, is eight numbered sections —
`1. Transpose + Gather`, `1a. small-GD tiled full-load`, `2. SIMT 标量并行`, `3. SIMD 末轴 Gather`,
`4. SIMD 行拷贝`, `5. GA 全载`, `6. Full-Load`, `7. SIMT 两维` — and its selection table at `:163-178`
introduces a ninth entry the numbered list does not have:

```
| 条件 | 倾向模板 |
|------|---------|
| **torch.gather dim==last** | **LastDim 路径**（4 级分层：batchProcess / indexSlice / xSlice+mask / scalarMode） |
| **torch.gather dim!=last，内部 Transpose 能力门控与成本门控均通过** | **kernel 内 Transpose + Gather** |
| **torch.gather dim!=last，内部路径不划算，且物理 Transpose 能力/成本门控通过** | **物理 Transpose(x/index) + 末轴 Gather + Transpose(y)** |
| **torch.gather dim!=last，small-GD tile 的 UB/成本门控通过** | **small-GD tiled full-load**；保持 PER_ELEMENT，参数化 Gx/Gi 后再推广 |
```

LastDim's status as a real path is settled by artifacts, not by the table: the directory holds
`gather_elements_v2_last_dim.md`, `gather_elements_v2_last_dim_tiling.template`, and
`dav310/gather_elements_v2_last_dim.template`, and `guide.md:212` gives it a tiling key:

```
1. **dim==last（末轴 gather）** → **LastDim 路径**（TILING_KEY=2）：内部 4 级分层
   - `batchProcess`：x 行 + index + y 放得下 UB/2 → 多行批量 DataCopyGather 向量化
   - `singleRow + indexSlice`：x 行放得下 UB/2 但 index 放不下 → 单行 x + index 切片
   - `singleRow + xSlice`：x 行放不下 UB/2 → x 切片 + mask 筛选 + Gather
   - `scalarMode`：xSliceNum > 5 或 ratio > 256 → 标量兜底（index DMA + x GM GetValue）
```

(the four tiers are `0411`'s subject). `TILING_KEY=1` is the in-kernel transpose, per `:217`.

small-GD's status is settled the other way, `templates/gather_elements_small_gd_tiled.md:7`:

```
这是实验性实现模式，当前不提供可直接复制的通用 `.template`。已有实现若把 gatherDim 写成静态常量，只能作为单一 specialization 使用；参数化 `Gx/Gi` 并完成跨 shape 验证前，不得宣称通用。
```

and its promotion criteria, `:89-94`, are the clearest statement in this family of what separates a
pattern from a template:

```
满足以下条件后才把实现升级为正式模板：

1. device kernel 已参数化 `Gx/Gi`，没有 case/shape 常量。
2. 覆盖 `Gx!=Gi`、多 outer、主尾 tile、负索引以及支持的 dtype/index 组合。
3. 代表 shape A/B 不劣于 SIMT/Scalar，完整用例集无不可解释回退。
4. 模板、Host tiling、TilingData 和 usage guide 成套提供。
```

Four conditions, all observable, none satisfiable by assertion. That is a promotion gate of the kind
this project's own STRATA describes, written by upstream for its own artifacts, and it is worth
carrying into `the delivered skill` as a pattern independent of gather.

The `Gx` / `Gi` distinction that makes small-GD hard to generalise, `:73`:

```
Host 和 device 必须分别传递 `Gx` 与 `Gi`：x 的搬入 blockCount 使用 `Gx`，index/y 和计算循环使用 `Gi`，索引合法范围使用 `Gx`。不要假设二者相等。
```

`Gx` is the number of x gather-axis planes; `Gi` the number of index/output planes. `torch.gather`
permits them to differ (`0413`), the one observed case has `Gx = Gi = 7` (`:87`), and a
specialisation written at that case cannot distinguish the two roles — which is exactly why upstream
refuses to call it general.

So the fourth count of this family's template set is: **nine entries on the implementation shelf, of
which eight have kernel files and one does not**, against the analysis shelf's stated six / tabled
seven / tabled nine (`0150`). Registered as `C-950td-014`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs, 5 fresh-process runs.

**Arm 1 — does the missing LastDim arm cost anything?** Take four `PER_ELEMENT` last-axis gathers
spanning the four tiers `guide.md:213-216` describes (one where `x` row + index + `y` fit in half of the
runtime-queried UB; one where the `x` row fits and the index does not; one where the `x` row does not
fit; one with `xSliceNum > 5`). At each, build (a) the implementation shelf's LastDim template and
(b) whatever the analysis shelf's tree selects for that shape, evaluated by hand from
`tiling-flow.md`'s decision tree and echoed. One compiler pin, distinct md5s, host echo of the selected
template and every gate input. Elementwise comparison against a CPU reference. Record `aiv_time`,
≥10 iterations, first 5 dropped. If (b) matches (a) within the floor at every tier, the missing arm is
free and the OVERTURN fires.

**Arm 2 — the small-GD generality claim, which needs no board to start.** Read the existing
specialisation (upstream says it exists but ships no `.template`; if it is not in this tree, that
absence is the arm's result and is reported as such). Where it is available, compile it at
`Gx = Gi = 7` and at `Gx = 7, Gi = 5`. Upstream predicts the second fails or silently mis-indexes,
because a static `gatherDim` cannot carry two roles. Correctness against a CPU reference decides;
a *fast wrong answer* is the expected failure mode and the elementwise check is the only thing that
sees it.

**Arm 3 — promote or don't.** Run upstream's own four promotion conditions against the artifact as a
checklist with observable outcomes: (1) grep the device kernel for case/shape constants; (2) run the
`Gx != Gi`, multi-outer, main/tail-tile, negative-index and dtype-combination matrix; (3) A/B against
SIMT and Scalar on representative shapes plus the full case set; (4) enumerate which of template,
host tiling, TilingData and usage guide exist. Report the four verdicts. This arm exists because
upstream wrote a promotion gate and nobody has published its result.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ub_size` is a
literal (queried and echoed, `0141`); that the analysis shelf's tree has a defined answer for every
last-axis shape (where it does not, arm 1 records `unrouted`, not a substitute); that a
specialisation compiled at `Gx = Gi` is correct at `Gx != Gi` (arm 2 is the test); that "no
`.template` in the tree" means the implementation does not exist elsewhere.

## 5 · Checker — acceptance declared before the run
Verdict `lastdim_gain(tier)` = median `aiv_time` of the analysis shelf's selection divided by median
`aiv_time` of LastDim, with the floor. Declared before the run: this entry is **supported** iff
`lastdim_gain(tier) > 1 + floor` for at least one of the four tiers. The OVERTURN fires iff
`lastdim_gain(tier) ≤ 1 + floor` at all four — the arm the analysis shelf lacks would then buy nothing.

Verdict `smallgd_general` from arm 2 ∈ {`correct_at_both`, `wrong_at_gx_ne_gi`, `refused`,
`unavailable`}. Upstream predicts `wrong_at_gx_ne_gi` or `refused`; `correct_at_both` would mean the
existing implementation is already more general than its own document claims.

Verdict `promotion(1..4)` from arm 3, four booleans, reported individually. A template promoted on
three of four is not promoted.

The exit code is not the verdict: a gather with wrong indices exits 0 and is fast, and arm 2's expected
outcome is a wrong answer rather than a crash. Three guards. First, every arm is compared elementwise
against a CPU reference and the checker fails red if any comparison did not execute. Second, **the
input that makes this checker go red**: arm 1 includes a `dim != last` shape, on which LastDim must
**not** be buildable at all. If the harness produces a LastDim timing for a non-last-axis gather, it is
not selecting templates by the tiling key and every `lastdim_gain` in the sweep is void — a comparison
whose only outcome is "the extra template wins" has not been shown able to say otherwise. Third, no
tier is reported without its floor, both md5s and both echoed template names; a tier where the analysis
shelf's tree gives no answer is reported `unrouted` and excluded from the verdict rather than scored as
a win.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The section counts, the file
existence statements and the absence of `LastDim` / `small-GD` from the analysis shelf's gather subtree
are file reads and greps performed at drafting time, re-derivable by
`ls upstream/skills-dev-main/ops/ascendc-performance-best-practices/reference/gather/templates/` and
`grep -Rn 'LastDim\|small-GD' upstream/skills-dev-main/ops/ascendc-perf-optimize/references/tiling/gather/`.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that LastDim is faster than anything —
it establishes that one shelf ships it with a tiling key and three files and the other never names it.
It does not establish that small-GD works, is general, or is worth promoting; upstream's one observed
case for it is `0412`'s subject and is a single unrepeated triple. It does not establish the correct
template count for this family and does not adjudicate between six, seven, nine and this entry's nine
(`0150` holds that question). It does not establish `TILING_KEY=1`/`=2` as the shipped key values
beyond upstream's statement. It does not establish that the analysis shelf's omission is an error
rather than a scope decision — a tiling taxonomy may legitimately not enumerate kernels — and §2 states
that reading. It does not cover the four LastDim tiers' thresholds (`0411`) or the `Gx`/`Gi` shape
relation (`0413`). No board token appears anywhere in the gather family on either shelf, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
