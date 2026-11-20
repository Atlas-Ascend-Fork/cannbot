```
ID:        0414-the-broadcast-ub-split-formula-loses-two-branches-in-the-analysis-shelfs-copy-and-both-are-the-degenerate-cases
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/broadcast/patterns.md:100-123 —
           "curProduct = 1 / ubSplitAxis = 0 / allFit = true / for i = shapeLen-1 downto 0:
           / curProduct *= dims[i] / if curProduct > maxElemNum: / ubSplitAxis = i
           / curProduct /= dims[i] / allFit = false / break / …
           / if allFit:                              # 所有维度都放得进 UB，ubSplitAxis 保持初始值 0
           /     curProduct /= dims[0]               # 在最外维上切分
           / if shapeLen == 1:                       # 单维场景（通常已被 OneDim 拦截）
           /     ubFormer = maxElemNum / else: / ubFormer = maxElemNum / curProduct"
SOURCE:    ops/ascendc-perf-optimize/references/tiling/broadcast/fallback/tiling-flow.md:79-93 —
           the same block without either branch (same repo — contrast, not corroboration)
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a broadcast whose collapsed shape fits UB entirely, tiled by the analysis shelf's formula as
           written, that produces a legal and correct plan on a named 950 board — showing `curProduct`
           left at the full product is harmless because some later stage clamps it. The missing
           `allFit` branch would then be a documentation simplification rather than a defect, and this
           entry's central claim would be wrong about which copy is complete.
```

# 0414 · The broadcast UB-split formula loses two branches in the analysis shelf's copy, and both are the degenerate cases

## 1 · Claim
Upstream asserts, in the design shelf, a UB-split procedure for broadcast: multiply the collapsed
output dimensions from the innermost outward until the running product exceeds `maxElemNum`, take that
axis as the split axis, and divide `maxElemNum` by the product of the axes inside it to get the
per-tile extent. Upstream's design-shelf copy carries **two further branches** the analysis shelf's copy
of the same procedure does not: an `allFit` flag set false only when the loop breaks, whose true case
divides `curProduct` by `dims[0]` so the split falls on the outermost axis; and a `shapeLen == 1`
special case setting `ubFormer = maxElemNum` directly rather than dividing. Both branches fire exactly
when the loop's `break` never executes. Not established here.

## 2 · The wrong branch this removes
The loop computes `ubSplitAxis` and `curProduct` together, and both are meaningless if it never breaks.
When every collapsed dimension fits — a small broadcast, which is common — the loop runs to completion,
`ubSplitAxis` is still its initialiser `0`, and `curProduct` holds the **entire** output element count.
The analysis shelf's copy then evaluates `ubFormer = maxElemNum / curProduct`, dividing a capacity by a
total that exceeds it, and in integer arithmetic that is `0`. `ubOuter = ceil(dims[0] / 0)` follows.
So the missing `allFit` branch is not a refinement for an edge case; it is the difference between a
plan and a division by zero, on the shapes most likely to be tried first.

The `shapeLen == 1` branch guards a second degenerate path. Upstream's own comment says it is normally
unreachable — `通常已被 OneDim 拦截` — because a single collapsed dimension routes to the OneDim branch
before this formula runs. `通常` is the word doing the work: the guard exists because the routing that
should make it unnecessary is not guaranteed, and an implementation that reproduces only the analysis
shelf's copy inherits the same trust in a route it does not control.

The over-correction worth naming: this is not evidence that the design shelf is the authoritative copy
of everything. It is evidence that the two copies were not kept in sync in the direction of *more*
detail, and the direction matters when deciding which to transcribe. A prior survey of this repository
recorded this divergence as one extra branch (`if shapeLen == 1`); re-verification at drafting time
found two. That correction is reported in `harvest/standing/950-td.md` as `SR-950td-02`, and it is a
reminder that a survey locates material and does not certify it.

## 3 · Ground / Source
The design shelf's copy, `ascendc-tiling-design/references/broadcast/patterns.md:98-129`, in full:

```
**UB 切分**：从最内轴向外累乘，找到第一个放不下的轴作为 ubSplitAxis：

curProduct = 1
ubSplitAxis = 0
allFit = true
for i = shapeLen-1 downto 0:
    curProduct *= dims[i]
    if curProduct > maxElemNum:
        ubSplitAxis = i
        curProduct /= dims[i]
        allFit = false
        break

if allFit:                              # 所有维度都放得进 UB，ubSplitAxis 保持初始值 0
    curProduct /= dims[0]               # 在最外维上切分

if shapeLen == 1:                       # 单维场景（通常已被 OneDim 拦截）
    ubFormer = maxElemNum
else:
    ubFormer = maxElemNum / curProduct

ubOuter = ceil(dims[ubSplitAxis] / ubFormer)
ubTail  = dims[ubSplitAxis] - (ubOuter-1) * ubFormer

其中 maxElemNum 计算：

maxElemNum = (ubSize - extraSize) * 8 / (bufferNum * maxDtypeBits)
maxElemNum = floor_align(maxElemNum, 256 * 8 / minDtypeBits)
```

The analysis shelf's copy, `ascendc-perf-optimize/references/tiling/broadcast/fallback/tiling-flow.md:79-93`,
in full:

```
## 5. 通用UB切分公式

maxElemNum = (ubSize - extraSize) * 8 / (bufferNum * maxDtypeBits)
maxElemNum = floor_align(maxElemNum, 256 * 8 / minDtypeBits)

从最内轴向外累乘outputDims:
  curProduct *= dims[i]
  if curProduct > maxElemNum:
    ubSplitAxis = i; curProduct /= dims[i]; break

ubFormer = maxElemNum / curProduct
ubOuter = ceil(dims[ubSplitAxis] / ubFormer)
ubTail = dims[ubSplitAxis] - (ubOuter-1) * ubFormer
```

Diffed line by line: `maxElemNum` identical in both, including the `* 8` and the `floor_align` to
`256 * 8 / minDtypeBits`. The loop identical in body. `ubOuter` and `ubTail` identical. Absent from the
analysis shelf: the `allFit` declaration, its assignment inside the loop, its post-loop branch, and the
whole `shapeLen == 1` conditional — four lines, two guards. Also absent: the initialisers
`curProduct = 1` and `ubSplitAxis = 0`, without which `ubSplitAxis`'s value in the no-break case is not
even stated. Registered as `C-950td-018`.

Trace the no-break case through both, with a concrete shape. Take a collapsed output `dims = [4, 24]`
(upstream's own worked example at `patterns.md:30`) and any `maxElemNum` above 96.

- Design shelf: loop multiplies to `24`, then `96`, never exceeds, ends with `curProduct = 96`,
  `allFit = true`, `ubSplitAxis = 0`. The branch fires: `curProduct = 96 / dims[0] = 24`. Then
  `shapeLen = 2 ≠ 1`, so `ubFormer = maxElemNum / 24` — the number of *rows* of 24 elements that fit,
  which is the right quantity to split axis 0 by.
- Analysis shelf: same loop, ends with `curProduct = 96`, `ubSplitAxis` unset. `ubFormer =
  maxElemNum / 96`. For `maxElemNum` between 96 and 191 that is `1`; the plan splits into 4 tiles of
  one row where one tile would do. For `maxElemNum ≥ 192` it is `≥ 2`, and `ubOuter = ceil(4 / 2) = 2`
  — a plan that is legal but silently coarser than the capacity allows.

So the analysis shelf's copy does not divide by zero at this shape; it under-uses UB. Division by zero
needs `curProduct > maxElemNum` while the loop never broke, which cannot happen — the loop breaks
exactly on that condition. §2's stronger reading is therefore **wrong**, and the honest statement is
the weaker one: without the `allFit` branch the split axis is unstated and the per-tile extent is
computed against the whole output rather than against the inner axes, giving a legal but conservative
plan. This correction was made at drafting time by working the example rather than by reading the code,
and it is exactly why §4 measures rather than argues.

`ubTail` is worth one line because it is identical in both and is the other half of the same trap:
`ubTail = dims[ubSplitAxis] - (ubOuter-1) * ubFormer` reads `dims[ubSplitAxis]`, so an unset
`ubSplitAxis` selects `dims[0]` by accident of initialisation in one copy and by nothing at all in the
other. This book records at `0029` that a tail length derived by subtraction can go negative and write
out of bounds; here the subtraction is guarded by `ubOuter`'s ceiling, but only if `ubFormer` is the
extent of the axis `ubSplitAxis` names.

Neither copy is the executable one. The analysis shelf's reference script is a third artifact, and
`0155` records that it preserves the chip-generation branch while dropping every constraint that branch
carries; `0151` records that this family's `maxElemNum` formula appears in three mutually inconsistent
forms across two families. This entry adds a fourth site to that picture: the analysis shelf's OneDim
branch states its own, simpler UB split at `tiling-flow.md:38` —
`ubFormer = (ubSize / bufferNum) 对齐到 128B` — with no `extraSize`, no `* 8`, and no dtype width, which
is neither of the two formulas above. Recorded, not analysed, in `harvest/standing/950-td.md` as
`Q-950td-04`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. Most of this
is host arithmetic and needs no device; only the last arm does.

**Arm 1 — device-free. Implement both copies verbatim and diff their outputs.** Transcribe the two
blocks above into two functions, changing nothing, and drive both over a shape sweep: collapsed
`dims` of rank 1 through 5, extents from 1 to 4096, and `maxElemNum` taken from the runtime-queried UB
(`0141`) through the design shelf's own `maxElemNum` formula at `bufferNum ∈ {2, 3, 4}` and
`maxDtypeBits ∈ {8, 16, 32}`. For every point record `ubSplitAxis`, `ubFormer`, `ubOuter`, `ubTail`
from each, and flag every disagreement. Classify each disagreement: `no_break` (the loop completed),
`rank_one`, or `other`. `other` would mean the two copies differ somewhere this entry has not
identified, which is the finding that would matter most.

**Arm 2 — device-free. Is the analysis shelf's copy ever illegal, or only conservative?** For every
disagreement from arm 1, check the analysis shelf's plan against the three legality conditions the
family states: `ubFormer ≥ 1`, `ubFormer × curProduct × maxDtypeBits / 8 ≤ ubSize − extraSize`, and
`ubOuter × ubFormer ≥ dims[ubSplitAxis]`. Report the count of illegal plans and the count of legal but
coarser plans, separately. §3 predicts the second and not the first; a nonzero first count overturns
§3's own correction.

**Arm 3 — on-card. Does the coarser plan cost anything?** Take the ten disagreements with the largest
ratio between the two `ubFormer` values and build a broadcast `Add` for each under both plans. One
compiler pin, two md5s, host echo of `ubSplitAxis`, `ubFormer`, `ubOuter`, `ubTail` and the queried UB.
Elementwise comparison against a CPU reference on both. Record `aiv_time` and MTE2 byte count under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped. Variance floor first: 30
in-process runs, 5 fresh-process runs.

Device selection for arm 3: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after; discard if
the die moved.

Refuses to assume: that `ubSize`, `extraSize`, `bufferNum`, `maxDtypeBits` or `minDtypeBits` have
values (only the first is queryable; the other three are swept and the sweep is reported as an
assumption, per `0151` which records none of them is valued upstream); that the analysis shelf's copy
was meant to be complete; that a legal plan is a good one (arm 3); that the transcription is faithful
(both functions are diffed against the quoted text character by character before the sweep runs).

## 5 · Checker — acceptance declared before the run
Verdict `disagree(point)` ∈ {`none`, `no_break`, `rank_one`, `other`} from arm 1. Declared before the
run: this entry is **supported** iff `disagree` is `no_break` for every point where the loop completes
and `none` for every point where it breaks — the two copies differ exactly on the degenerate cases and
nowhere else. Any `other` means the diff is wider than §3 describes and the entry is corrected in place.

Verdict `illegal_count` from arm 2. Declared before the run: §3 predicts `0`. A nonzero value is a
*stronger* result than this entry claims and is reported as such, with §2's original stronger reading
reinstated and §3's correction itself corrected.

Verdict `coarse_cost` = median `aiv_time`(analysis-shelf plan) / median `aiv_time`(design-shelf plan)
from arm 3, with the floor. The OVERTURN fires iff `coarse_cost ≤ 1 + floor` at every one of the ten
points **and** `illegal_count == 0`: the missing branches would then cost neither correctness nor time,
and the divergence would be a documentation simplification.

The exit code is not the verdict. Arms 1 and 2 are pure arithmetic that always completes; arm 3's
broadcast returns a full buffer whatever tiling produced it. Three guards. First, arm 3's every plan is
compared elementwise against a CPU reference and a point whose comparison did not run is `untestable`.
Second, **the input that makes this checker go red**: the sweep includes shapes that certainly break
the loop (rank 3 with every extent above `maxElemNum`), where the two copies **must** agree exactly on
all four outputs. If they disagree there, the transcription is wrong and every `no_break` disagreement
in the sweep is an artifact of a bad implementation rather than of the source text — a diff study whose
only outcome is "they differ" cannot distinguish a real divergence from two mistyped functions. Third,
no arm-3 point is reported without its floor, its two md5s and its four echoed tiling values.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The two code blocks are file
reads performed at drafting time and diffed by eye, line by line. The `dims = [4, 24]` trace in §3 is
arithmetic performed here on paper from upstream's own worked collapse example; it is what produced
this entry's correction to its own §2, and it is not an observation of any implementation's behaviour.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the analysis shelf's copy produces
a bad plan on any board — §3's own trace found the weaker outcome (a conservative plan) rather than the
failure §2 first proposed, and §5 declares which reading a run would support. It does not establish
which copy the shipped tiling actually implements: neither is executable, the family's reference script
is a third artifact recorded at `0155` as dropping constraints, and this entry did not read it for that
purpose. It does not establish `ubSize`, `extraSize`, `bufferNum`, `maxDtypeBits`, `minDtypeBits`, the
`* 8`, or the `floor_align` quantum — `0151` records that this formula family has three mutually
inconsistent forms and that none of its symbols is valued upstream, and this entry adds a fourth site
(`Q-950td-04`) without resolving any of them. It does not cover the multi-core split, the alignment
quanta or the NDDMA axis cap that follow in the same document (`0416`), nor the chip-generation branch
(`0154`, `0155`). It does not establish that `通常已被 OneDim 拦截` is true. No board token appears in
either copy — both name architectures, not boards — so BOARD is `family-claimed(unverified)`; §4 names
950PR/950DT only as where arm 3 would run. Nothing here is established for any 910-family board, and
the `DAV_2201` arm both documents carry is not carried into this book (RULES.md Art. 1).
