```
ID:        0413-torch-gather-lets-the-index-be-smaller-than-the-source-so-x-and-index-need-separate-shapes-and-separate-strides
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/gather/templates/
           gather_elements_v2_last_dim.md:67-71 — "torch.gather 允许非 gather 轴
           `index.shape[i] <= x.shape[i]`，因此适配 Host 模板时必须：
           / - 按 index 的非 gather 轴乘积计算 `output_rows` 和使用核数。
           / - 分别保存 x/index shape 与 stride，按 x stride 取源、按 index stride 取 index/写 y。
           / - 仅在对应非 gather 轴确实相等时合轴；不要用 x shape 代替 index shape。"
SOURCE:    same shelf, reference/gather/guide.md:53 — "索引 index: [outerSize, gatherSize,   innerSize]
           （torch.gather: index.shape[i] ≤ x.shape[i] for i ≠ dim）" ; :235 — "不要沿用按 x shape
           计算输出行数的模板假设。" ; :239 — "**outerSame 优化**：当 `index.shape[i] == x.shape[i]`
           for all `i != dim` 时，`innerI == innerX`，地址公式简化"
SOURCE:    same shelf, templates/gather_elements_small_gd_tiled.md:73 — "Host 和 device 必须分别传递
           `Gx` 与 `Gi`：x 的搬入 blockCount 使用 `Gx`，index/y 和计算循环使用 `Gi`，索引合法范围使用
           `Gx`。不要假设二者相等。" ; :81 — "多 batch/outer 场景必须使用 x 的独立 outer stride，
           不能用 index 输出步长替代。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `PER_ELEMENT` gather on a named 950 board with `index.shape[i] < x.shape[i]` on a
           non-gather axis, run through a kernel that uses the `x` stride for the index and the output,
           that nevertheless produces output matching a CPU reference elementwise. The two strides
           would then not be independently load-bearing at that shape, and the obligation this entry
           carries would be narrower than upstream states it.
```

# 0413 · torch.gather lets the index be smaller than the source, so x and index need separate shapes and separate strides

## 1 · Claim
Upstream asserts that `torch.gather` semantics permit the index tensor to be **smaller** than the
source on every non-gather axis — `index.shape[i] <= x.shape[i]` for `i != dim` — and asserts three
consequences a host template must obey: the output row count and the core count are computed from the
index's non-gather axes, not the source's; `x` and `index` keep separate shapes and separate strides,
with the source read by `x`'s stride and the index read and the output written by `index`'s stride; and
axis collapse is legal only where the corresponding non-gather axes are actually equal. Upstream
asserts the same separation for the experimental tiled mode as two distinct plane counts, `Gx` for the
source and `Gi` for the index and output, with `不要假设二者相等`, and asserts that a multi-batch case
must use the source's own outer stride rather than substituting the output's. Upstream names the
special case where the two shapes agree — `outerSame` — as an *optimisation*, not the norm. Not
established here.

## 2 · The wrong branch this removes
The wrong branch is not an error anyone makes on purpose; it is what happens when a template is written
against a case where the two shapes agree. Every quantity that must differ — output rows, core count,
index stride, output stride, plane count — is numerically identical when
`index.shape[i] == x.shape[i]`, so a kernel that conflates them is correct, fast, and tested. It stays
correct until a caller passes a smaller index, at which point the source stride is used to walk the
index, and the kernel reads past the end of the index tensor or reads the right memory at the wrong
positions. Both failures return numbers; neither raises. This book records the same shape at `0159`,
where omitting an extents check shipped a real two-element stride defect, and at `0395`, where a
passing small aligned shape established nothing about the tail.

The second wrong branch is over-collapsing. Axis merging is the standard first move — the family uses
`MergeAxis` before its LastDim tiering (`0411`) — and it is legal only per-axis and only where the two
tensors agree. Upstream's rule is conditional: `仅在对应非 gather 轴确实相等时合轴`. A collapse that
merges axes on the source's shape alone produces a smaller, cleaner problem whose index addressing is
silently wrong, and the collapse is the step that erases the evidence: after merging, the two shapes
are gone and only the merged extents remain.

## 3 · Ground / Source
The semantics, stated in the family's three-dimensional model, `reference/gather/guide.md:51-64`:

```
输入 x:    [outerSize, gatherDimSize, innerSize]
索引 index: [outerSize, gatherSize,   innerSize]  （torch.gather: index.shape[i] ≤ x.shape[i] for i ≠ dim）
输出 y:    [outerSize, gatherSize,   innerSize]

对每个输出元素 y[o, g, c]:
  idx = index[o, g, c]              // 从索引张量取值
  y[o, g, c] = x[o, idx, c]         // 从输入张量按索引取值
```

Read carefully, that block is doing two things at once. The `≤` is in a parenthesis, but the three
shape lines above it write `outerSize` and `innerSize` as if they were *shared* between `x` and
`index` — which is true only in the `outerSame` case. So the family's own opening model is written for
the special case and fences it in a parenthetical. `0147` carries the size collapse and the
`PER_ELEMENT` / `PER_SLICE` `ySize` arithmetic from the analysis shelf; what is new here is that the
*axes themselves* may differ in extent, which changes strides rather than counts.

The obligations, `templates/gather_elements_v2_last_dim.md:67-71`, in full:

```
torch.gather 允许非 gather 轴 `index.shape[i] <= x.shape[i]`，因此适配 Host 模板时必须：

- 按 index 的非 gather 轴乘积计算 `output_rows` 和使用核数。
- 分别保存 x/index shape 与 stride，按 x stride 取源、按 index stride 取 index/写 y。
- 仅在对应非 gather 轴确实相等时合轴；不要用 x shape 代替 index shape。
```

Three obligations, and they are not three statements of one rule. The first is about **work
partitioning** — get it wrong and the core count is wrong, which is a performance and a correctness
bug at once, because cores that should not exist write output rows that should not exist. The second is
about **addressing**. The third is about a **transformation** that destroys the information the second
needs.

Restated at index level with the failure named, `guide.md:235`:

```
> **LastDim Host 适配**：torch.gather 允许非 gather 轴 `index.shape[i] <= x.shape[i]`。输出行数必须按 index shape 计算，x/index 必须保存各自的 shape 和 stride；不要沿用按 x shape 计算输出行数的模板假设。启用 LastDim 前还要比较整行 resident 流量与 direct random GM 成本，不能只判断 `dim==last`。
```

`不要沿用……模板假设` — do not carry over the template's assumption — is upstream naming the mechanism
exactly: the defect arrives by inheritance from a template that was right in its original context.

The address model that the separation exists to protect, `guide.md:238-239`:

```
1. **地址模型**：`yIndex → (oOuter, g, c)`，`idx = index[yIndex]`，`xAddr = oOuter * G_x * innerX + idx * innerX + c`
2. **outerSame 优化**：当 `index.shape[i] == x.shape[i]` for all `i != dim` 时，`innerI == innerX`，地址公式简化
```

`innerI` and `innerX` are separate symbols in upstream's own notation, and `G_x` is subscripted to
distinguish it from the index's gather extent. The address formula uses `innerX` for the source stride;
the `yIndex → (oOuter, g, c)` decomposition uses `innerI`. When the two are equal the formula collapses
and the second symbol disappears — which is precisely how the distinction gets lost in an
implementation written at that case.

The same separation in the tiled mode, `templates/gather_elements_small_gd_tiled.md:73`:

```
Host 和 device 必须分别传递 `Gx` 与 `Gi`：x 的搬入 blockCount 使用 `Gx`，index/y 和计算循环使用 `Gi`，索引合法范围使用 `Gx`。不要假设二者相等。
```

Three distinct roles for two numbers: `Gx` sets the transfer's block count *and* the legal index range;
`Gi` sets the compute loop trip count and the output extent. A single `G` collapses all three, and the
index-range role is the one that turns a shape confusion into an out-of-bounds read. That is why
`0409` records upstream refusing to call the existing implementation general: its one measured case has
`Gx = Gi = 7`, so a static `gatherDim` in that code cannot distinguish the roles even in principle.

And the batch dimension, `:81`:

```
- 多 batch/outer 场景必须使用 x 的独立 outer stride，不能用 index 输出步长替代。
```

The shipped router keeps the separation structurally rather than by convention: its parameter block
carries `xPreDim`/`xGatherDim`/`xPostDim` *and* `idxPreDim`/`idxGatherDim`/`idxPostDim` as six distinct
fields plus two element counts (`gather_elements_v2_route.template:26-33`, quoted at `0407`), and its
cost model uses `xElementCount` and `indexElementCount` in different terms of the same inequality — so
conflating them would change the routing decision, not only the addressing. It also carries a
`nonGatherShapesEqual` boolean (`:39`) which, when false, **disqualifies** the in-kernel transpose
entirely (`:85`). So upstream's answer for the hardest path is not to handle unequal shapes but to
refuse them, and the entry-level consequence is that the unequal case has fewer templates available
than the equal case — a routing fact the selection tables do not state. Registered as `C-950td-017`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The claim is
about a silent wrong answer, so every arm's verdict is an elementwise comparison and no arm's verdict is
a timing.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved.

**Arm 1 — the poison arm, and it is the point of the entry.** Build one LastDim kernel with a
compile-time switch: `STRIDES_SEPARATE` uses `index`'s stride for the index read and the output write,
`STRIDES_CONFLATED` uses `x`'s stride for all three. Run both at
`x = [8, 4096, 1]`, `index = y = [8, 512, 1]`, `dim = 1` (equal outer, unequal gather — the control)
and at `x = [8, 4096, 1]`, `index = y = [4, 512, 1]`, `dim = 1` (unequal outer — the case). Expected:
both switches agree on the control and disagree on the case, with `STRIDES_CONFLATED` reading outside
the index tensor. Guard the index allocation with a poisoned margin (a known bit pattern past its end)
and report whether the poison appears in the output — that turns "wrong answer" into "read past the
end", which is a different and more serious finding than an addressing slip.

**Arm 2 — the collapse.** Same two shapes, with `MergeAxis` applied (a) per upstream's rule, only where
the extents match, and (b) on `x`'s shape alone. Elementwise comparison of both against a CPU
reference. Upstream predicts (b) is wrong on the unequal case and correct on the control.

**Arm 3 — work partitioning.** For the unequal case, echo `output_rows` and `usedCoreNum` from a host
that computes them from `index` and from a host that computes them from `x`, and record whether the
second launches cores that write rows outside the output tensor. Guard the output allocation the same
way as arm 1.

**Arm 4 — `Gx != Gi` in the tiled mode.** Where the small-GD implementation is available (`0409` records
it ships no `.template`, so its absence is a legitimate arm result), run at `Gx = 7, Gi = 7` and at
`Gx = 7, Gi = 5`, checking both output correctness and whether any index outside `[0, Gx)` is accepted.

**Arm 5 — the routing consequence.** Drive `SelectGatherElementsV2Route` with `nonGatherShapesEqual`
false and confirm the in-kernel transpose is refused. Device-free.

Refuses to assume: that a free die stays free; that a die may be substituted; that a wrong stride
faults (it is expected not to — hence the poison margins); that the control case exercises the
distinction (it does not, by construction, and that is why it is the control); that the small-GD
implementation exists in this tree.

## 5 · Checker — acceptance declared before the run
Verdict `matches(switch, case)` = elementwise agreement with a CPU reference, and
`poison_read(switch, case)` = whether the poisoned margin appeared in the output or was read.
Declared before the run: this entry is **supported** iff
`matches(SEPARATE, unequal) == true` and `matches(CONFLATED, unequal) == false`. The OVERTURN fires iff
`matches(CONFLATED, unequal) == true` — the conflated stride would then be harmless at that shape and
the obligation would be narrower than upstream states.

Verdict `merge_wrong` from arm 2, `rows_overrun` from arm 3, `gx_gi_wrong` from arm 4, `route_refused`
from arm 5, all booleans reported individually. None is averaged with any other: they are four
independent obligations and a template can satisfy three.

The exit code is not the verdict, emphatically. Every failure mode in this entry returns a full output
buffer and exit 0; a stride error is a fast wrong answer. Three guards. First, every arm's verdict is
an elementwise comparison against a CPU reference computed from the tensors' true shapes and strides,
and an arm whose comparison did not execute is `untestable`, never `matches`. Second — **the input
that makes this checker go red** — the control case (`equal outer`) must show
`matches(CONFLATED, control) == true`. If the conflated build is wrong even where the two shapes agree,
then it is broken for some unrelated reason and its failure on the unequal case attributes nothing;
the whole study is void. A poison study whose only outcome is "the deliberately-wrong build was wrong"
has not been shown able to isolate the cause. Third, both allocations carry poisoned margins and the
report distinguishes `wrong values` from `read past the end` — collapsing them would hide the more
serious of the two.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The four obligations, the
`outerSame` framing, the `Gx`/`Gi` role split and the router's `nonGatherShapesEqual` disqualification
are file reads performed at drafting time. The observation that the family's own opening shape model
writes `outerSize` and `innerSize` as shared between `x` and `index` while fencing the `≤` in a
parenthesis is a reading of one code block, not an observation of any implementation's behaviour.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that a conflated stride produces a wrong
answer on any board — it establishes that upstream states the obligation four times across three files
and structures its router to keep the two shapes apart. It does not establish that any shipped template
gets this wrong; upstream's warnings are about adaptation (`适配 Host 模板时必须`, `不要沿用……模板假设`),
which is a caution to the reader rather than a defect report. It does not establish `outerSame` as
common or rare, and gives no distribution. It does not cover `PER_SLICE` gathers, where the index rank
may be lower than `x`'s entirely and the relation is different (`0147`), nor the `ySize` arithmetic,
which `0147` already carries from the analysis shelf. It does not establish that `nonGatherShapesEqual
== false` removes only the in-kernel transpose from the candidate set — arm 5 tests one route and the
other templates' tolerance of unequal shapes is not documented anywhere in the family
(`C-950td-017` records that absence). It does not establish `innerI`/`innerX` or `Gx`/`Gi` as the
shipped variable names beyond upstream's own notation. No board token appears anywhere in the gather
family on either shelf, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where
our run would happen. Nothing here is established for any 910-family board.
