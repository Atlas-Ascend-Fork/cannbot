```
ID:        0124-blocksplitr-cuts-the-reduction-axis-across-cores-when-a-is-too-small-to-fill-the-machine
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:143-203 —
           "ShouldUseGroup = (aLoopCntTotal <= coreNum/2) AND (rLoopCntTotal > 1)" ·
           "workspaceBytes = rGroupCnt × aTotal × 4" · "**验证锚点**（g++ 纯 host，coreNum=72,
           UB=192KB）：#1 `[64000,32]` axes[0] → `templateType=1`（group），`rGroupCnt=61`、
           `usedCoreNum=61`、`workspaceBytes=61×32×4=7808`"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured big-R small-A reduction on a named 950 board where the A-axis split (normal)
           matches or beats BlockSplitR despite using fewer cores — the SyncAll barrier and the
           Phase-2 pass would then cost more than the idle cores they buy back.
```

# 0124 · BlockSplitR cuts the reduction axis across cores when A is too small to fill the machine

## 1 · Claim
Upstream asserts that all five templates and both interleaved templates split the A (output)
dimension and never the reduction axis, and that this leaves the machine under-used whenever R is
too large for one core and the A product is smaller than the core count — the A split can then
occupy only A cores. For that regime upstream asserts a distinct multi-core strategy, R-axis
splitting (`group` / BlockSplitR): each core computes a partial sum over one R segment into
workspace, a `SyncAll` barrier follows, and a Phase-2 RA mini-kernel merges along the group
dimension and applies the final operation. Upstream asserts the gate as two conditions that must
*both* hold — `ShouldUseGroup = (aLoopCntTotal <= coreNum/2) AND (rLoopCntTotal > 1)` — the split
geometry `usedCoreNum = aLoopCntTotal × rGroupCnt` on a 2-D `[aLoopCntTotal, rGroupCnt]` grid, and
the workspace size `rGroupCnt × aTotal × 4` bytes as a dense FP32 `[rGroupCnt, aTotal]` layout.
Upstream also asserts that the strategy is only valid for commutative reductions. Not established
here.

## 2 · The wrong branch this removes
Two, and the second is the reason this entry exists. First: an agent that has learned "split the
output dimension" applies it to `[64000, 32]` reduced over axis 0, uses 32 cores out of the
machine's supply, and reports a plan whose profile shows nothing wrong — every core it used was
busy. The idle cores never appear in the metrics it looks at. Second, and worse: an agent that
*finds* BlockSplitR in the documentation will most likely find it filed as an optional enhancement,
because that is where the reference used to put it. Upstream corrected this in place and left the
correction visible at `:336-338` — `⚠️ Group Reduce（R 轴分核 / BlockSplitR）已从"可选增强"提升为
一等分支 ... 它不是叠加在单模板上的小优化，而是与"A 轴分核 normal"并列的多核策略选择`. An agent
reading the enhancement table alone will treat a first-class branch as a bolt-on and apply it after
choosing a template rather than as the multi-core decision itself.

The commutativity precondition removes a third wrong branch. Partial sums merged out of order are
only valid when the reduction is commutative — sum, square-sum, max. For a non-commutative
reduction the strategy is not a slow plan, it is a wrong answer, and no capacity check catches it.

## 3 · Ground / Source
`reduction/fallback/tiling-flow.md:143-170`, the branch statement and structure:

```
> **一等分支，不是"可选增强"。** 五模板/交错模板**都在切 A（行/输出维），不切 R**。但当 **R 大到单核放不下
> 且 A 维乘积 < core_num（单纯切 A 只能用满 A 个核，其余闲置）** 时，必须把**归约轴 R 本身跨核切分**，各核
> 算一段 R 的部分和再合并，才能用满核。

输入: aLoopCntTotal（A 维扁平计数）, rLoopCntTotal（R 分块后的外层 R loop 计数）, coreNum

┌─ aLoopCntTotal > coreNum / 2      → 【A 轴分核 normal】   // 切 A 已够满核，无需跨核切 R
├─ rLoopCntTotal <= 1               → 【A 轴分核 normal】   // R 未分块（R 全载 UB），无跨核 R 可切
└─ 否则（大 R + 小 A）             → 【R 轴分核 group / BlockSplitR】
      Phase1 各核部分和 → workspace → SyncAll → Phase2 合并 + 输出

**两段式结构（可交换归约才成立：平方和/求和/…）**：

分核网格: 2D [aLoopCntTotal, rGroupCnt]，usedCoreNum = aLoopCntTotal × rGroupCnt
Phase1（每核）: 处理分到本核的一段 R chunk → 局部部分和 → 写 workspace[rChunkIdx, 该A列]
SyncAll()                          # 跨核屏障，等所有核 workspace 写完
Phase2（RA mini-kernel）: workspace[rGroupCnt, aTotal] 沿 rGroupCnt 维 ReduceSum 合并 → sqrt → 输出
```

The formulas, `:172-199`, in full:

```
前置（五模板已算好）:
  aLoopCntTotal = ∏(外层 A 整根) × CeilDiv(A_split 轴, aUbFactor)   // A 维扁平计数
  rLoopCntTotal = ∏(外层 R 整根) × CeilDiv(R_split 轴, rUbFactor)   // R 分块后的外层 R loop 计数
  aTotal        = ∏(所有 A 轴 size)                                 // 输出元素数 = workspace 列数

门控（两条都不满足才用 group）:
  ShouldUseGroup = (aLoopCntTotal <= coreNum/2) AND (rLoopCntTotal > 1)

R 分核多核（ComputeGroupSplit）:
  totalOuter = aLoopCntTotal × rLoopCntTotal
  perCoreNum = CeilDiv(totalOuter, coreNum)
  numBlocks  = CeilDiv(totalOuter, perCoreNum)
  numBlocks  = (CeilAlign(numBlocks, aLoopCntTotal) <= coreNum)      // 对齐到 A 维整数倍
               ? CeilAlign(numBlocks, aLoopCntTotal)                 //   （每 A 列 rGroupCnt 相等，aPerCore=1）
               : FloorAlign(numBlocks, aLoopCntTotal)
  usedCoreNum = numBlocks
  rGroupCnt   = numBlocks / aLoopCntTotal                            // 每 A 列切成 rGroupCnt 个 R 分组

workspace:
  workspaceBytes = rGroupCnt × aTotal × 4          // fp32 dense，布局 [rGroupCnt, aTotal]

Phase2（kernel 侧现算，R 全载 rGroupCnt 行进 UB）:
  aUbFactorP2 = floor(preInElems / rGroupCnt) → FloorAlign(8) → clamp(outBuf/tmpBuf/aTotal 三上界)
  ReduceSum<fp32, RA, srcInnerPad=true>  srcShape={rGroupCnt, aUbFactorP2}  // 消解 rGroupCnt，保留 A
```

The verification anchors, `:201-203`, quoted exactly because they are reproducible self-checks that
need no device and that this book has not run:

```
> **验证锚点**（g++ 纯 host，coreNum=72, UB=192KB）：#1 `[64000,32]` axes[0] → `templateType=1`（group），
> `rGroupCnt=61`、`usedCoreNum=61`、`workspaceBytes=61×32×4=7808`；#6 `[4,3200,24]` axes[1] → `rGroupCnt=21`、
> ws=8064；#8 `[2,320,14,320]` axes[1,3] → `rGroupCnt=2`、ws=224。
```

Restated in the case file with a fuller table, `reduction/fallback/example/euclidean_norm/experience.md:91-98`:

```
host 自检（g++ 纯 host，coreNum=72, UB=192KB）：

| case | shape / axes | templateType | rGroupCnt | usedCoreNum | workspaceBytes |
|------|-------------|:-----------:|:---------:|:-----------:|---------------:|
| #1 ra_group_0001 | `[64000,32]` [0] | **1（group）** | 61 | 61 | 61×32×4 = 7808 |
| #6 ara_group_0001 | `[4,3200,24]` [1] | **1（group）** | 21 | 42 | 21×96×4 = 8064 |
| #8 arar_group_0001 | `[2,320,14,320]` [1,3] | **1（group）** | 2 | 56 | 2×28×4 = 224 |
```

Arithmetic re-derived here rather than trusted: `61 × 32 × 4 = 7808` ✓; `21 × 96 × 4 = 8064` ✓ (and
`aTotal = 4 × 24 = 96` ✓, with `usedCoreNum = aLoopCntTotal × rGroupCnt = 2 × 21 = 42`, implying
`aLoopCntTotal = 2` — which is *not* `∏(A axes) = 96`, so `aLoopCntTotal` is the flattened A *loop
count* after UB factoring, not the A element count; the two are distinct and the formula list says
so, but the distinction is easy to lose); `2 × 28 × 4 = 224` ✓ (`aTotal = 2 × 14 = 28` ✓, and
`usedCoreNum = 56 = 28 × 2`, so here `aLoopCntTotal = 28`). All three anchors are internally
consistent. Case #1 has `usedCoreNum = 61` with `aLoopCntTotal = 1`, i.e. 61 of 72 cores — the
alignment step at `:187-189` is what leaves 11 idle.

Upstream's own framing of the payoff, `experience.md:85-87`, is unusually restrained and is
preserved verbatim because the restraint is the teaching:

> **group 是 20 case 里最主力的路径——#1–9 共 9 个走它**（见 §5 选型表 "group" 行）：这些 case 都是**大 R + 小 A**
> （如 #1 `[64000,32]` axes[0]：R=64000 超单核容量、A=32≪coreNum=72，切 A 只能用 32 核 → 跨核切 R 用满 61 核）。
> group 加速温和（~1.0–1.1×），价值是**把大 R 摊到多核用满核**，而非病态点大赢。

The measured group rows from the 20-case table (`experience.md:117-125`) bear that out and include
a loss: #1 1.08×, #2 1.09×, #3 1.07×, #4 1.00×, #5 **0.91×**, #6 1.08×, #7 0.99×, #8 1.00×,
#9 1.02×. One of the nine is a 9 % regression and upstream published it in the same table as the
wins.

The gate's `coreNum` and `UB` are stated in the anchor as 72 and 192 KB, while this family's own
script defaults to `core_num = 64` and `ub_size = 248 * 1024`
(`reduction/fallback/script/reduction_tiling.py:57-58`). Both `rGroupCnt` and the gate
`aLoopCntTotal ≤ coreNum/2` depend on the core count, so the anchors are only reproducible at 72.
See 0131 and `harvest/contradictions-950-tiling.md` C-950tiling-009.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The claim
has a host-side half that needs no card and a device half that does.

Host-side arm (no device, permitted in this phase, not run): compile the tiling host with g++ only
— no device target — force `coreNum = 72` and `UB = 192 KB`, feed the three anchor cases, and
compare `templateType`, `rGroupCnt`, `usedCoreNum` and `workspaceBytes` against the table above,
field by field. Then repeat at `coreNum = 64` and `UB = 248 KB` (the script defaults) and record
how far the anchors move. This is the cheapest falsification available for this entry and it
establishes nothing about a board.

Device arm. Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at
20 s spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after
and discard the case if the die moved.

Gate-boundary sweep. Fix `R = 64000` and sweep A across values that carry `aLoopCntTotal` from well
under `coreNum/2` to well over it — A ∈ {8, 16, 32, 36, 48, 72, 128} at the queried core count.
At every A build both plans: BlockSplitR forced, and A-axis normal forced. One compiler pin; md5
per binary; host echo of `templateType`, `rGroupCnt`, `usedCoreNum`, `workspaceBytes`; output
checked against an fp64 reference within a tolerance declared in advance — partial-sum merging
changes float accumulation order, so bit-identity between the two plans is not expected and the
tolerance must say so. Record `aiv_time` and the `SyncAll` wait time separately under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Negative arm, retained whether or not it bites: run BlockSplitR on a case the gate refuses
(`aLoopCntTotal > coreNum/2`) and report the result — the gate's cost is only visible if the
refused side is measured.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` is 72
or 64 — it is queried and printed with every result; that `ub_size` is 192 KB or 248 KB, same
reason; that a plan that builds is the plan that ran (echo required); that the workspace allocation
succeeds — a case that cannot allocate `rGroupCnt × aTotal × 4` bytes is recorded as a failure at
that A, not dropped.

## 5 · Checker — acceptance declared before the run
Verdict variable `group_gain(A)` = (normal median `aiv_time` − group median `aiv_time`) / normal
median, at each swept A. Declared before the run: the gate is supported iff `group_gain > 0` for
every A with `aLoopCntTotal ≤ coreNum/2` and `group_gain ≤ 0` for every A above it. The OVERTURN
fires iff `group_gain ≤ 0` at any A inside the gate — BlockSplitR would then not pay for its
barrier there. Upstream's own `~1.0–1.1×` characterisation is checked separately: the median
`group_gain` inside the gate is expected in [0.00, 0.10], and a value outside that band in either
direction is reported as measured, including the case that reproduces #5's 0.91×. A second verdict
`anchors_match` is the host-side arm's field-by-field comparison, reported as a table.

The exit code is not the verdict. The blind mode: a forced-group arm that silently fell back to
normal would time identically and produce `group_gain ≈ 0` everywhere, which would read as a clean
overturn. The guards are structural and mandatory — the group arm must echo `templateType = 1`, a
non-zero `workspaceBytes`, and a non-zero `SyncAll` wait, and the checker goes red at any A where
it does not, rather than recording a gain. Third guard: the queried `coreNum` is printed with every
point and the checker fails if it changed between points, since both the gate and `rGroupCnt`
are functions of it.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The three anchor rows and
the nine measured group speed-ups quoted in §3 are upstream's readouts, not ours; this book has
run neither the host self-check nor any kernel.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. The entry does not establish that the two gate conditions are the right
ones, that `coreNum/2` is the right threshold, or that the alignment step at `:187-189` — which
leaves 11 of 72 cores idle in anchor #1 — is the best available. It does not establish the anchors:
they are reproducible in principle by a host-only compile that this book has not run, and they are
stated at `coreNum = 72, UB = 192 KB`, a configuration this family's own script contradicts (0131).
It does not establish that BlockSplitR is safe for non-commutative reductions — upstream restricts
it to commutative ones and this entry carries that restriction rather than testing it. The measured
speed-ups quoted from the 20-case table are upstream's, on their platform, for EuclideanNorm only;
they are not transferred to any other operator here. No board token appears in `tiling-flow.md`; the
case file says `Ascend 950 / arch35（dav-3510）`, which names a family and not a board, so BOARD is
`family-claimed(unverified)` and §7 records that no specific board is named. §4 names 950PR/950DT
because that is where our run would happen. Nothing here is established for any 910-family board.
