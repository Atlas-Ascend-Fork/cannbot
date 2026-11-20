```
ID:        0307-swat-mechanism-b-rebalances-tail-tile-sizes-and-never-changes-the-tile-count
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/swat_design.md:148 —
           "机制 B 把**最后若干个 tile（含薄片）的 M 尺寸重新等分**，让它们变得均匀。**tile 数量
           保持不变**，变的只是尺寸分布。"
SOURCE:    same file:186-191 — "newTailMain = Align16( ceil((mergeLen * baseM + mTailSize) /
           (mergeLen + 1)) )" · "**上界 `baseTailCntMax = (baseM - mTailSize) / 16`**：再往上
           `newTailMain` 被 16 对齐拉到 `baseM`，合并不再有收益。" · "**成本函数**：`curPerf =
           (未合并窗口数) * baseM + mergeWindowNum * newTailMain`，即所有 serpentine 窗口的关键
           路径之和。用 `<=` 接受新解，平局偏好更深合并（tile 更均匀）。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured matmul on a named 950 board where mechanism B's rebalanced layout is slower
           than the unmerged layout at the same shape — the cost function `curPerf` would then not
           be tracking the quantity that sets wall time, and the search would be optimising the
           wrong objective.
```

# 0307 · SWAT mechanism B rebalances tail tile sizes and never changes the tile count

## 1 · Claim
Upstream asserts that SWAT's tail-merge mechanism redistributes the M (or N) extents of the last
few tiles so that a thin edge sliver becomes several near-equal tiles, and that the *number* of
tiles is invariant under the transform — only the size distribution changes. Upstream asserts the
host-side search: start with the merge region covering one whole serpentine window
(`mergeLen = tailWindowSize − 1`), grow it one window at a time (`mergeLen += windowSize`), and at
each step compute `newTailMain = Align16(⌈(mergeLen × baseM + mTailSize) / (mergeLen + 1)⌉)` and a
cost `curPerf = (mainWindowNum + 1 − mergeWindowNum) × baseM + mergeWindowNum × newTailMain`, which
upstream describes as the sum of every serpentine window's critical path. Upstream asserts the
search's upper bound `baseTailCntMax = (baseM − mTailSize) / 16`, with the reason that beyond it the
16-alignment pulls `newTailMain` back up to `baseM` and merging stops paying. Upstream asserts the
acceptance test is `<=`, so ties prefer deeper merging. Not established here.

## 2 · The wrong branch this removes
The reflex response to a thin edge tile is to change the tile *count* — split the sliver into the
neighbour, or drop `baseM` so the division comes out even. Both move the whole schedule. Dropping
`baseM` changes every tile in the problem and re-enters the basic-block search; folding the sliver
into a neighbour makes one tile larger than `baseM`, which the L0 budget was sized against.

Mechanism B's move is narrower and is the part worth carrying: **hold the count, move the
boundaries**. Nothing upstream of the tail region changes, the L0 tile never exceeds `baseM`, and
the serpentine window structure is untouched — which is what lets it compose with mechanisms A and
C (`0306`).

The second wrong branch is arithmetic and will bite an implementer. Because the merged tiles are no
longer multiples of `baseM`, the GM offset of every tile past the merge boundary is wrong unless
corrected. Upstream carries the correction (`:222-226`) and it is easy to omit: the tile's GM start
is `mTileIdx × baseM` **minus** the accumulated shrinkage `(mTileIdx − mBaseNormCnt_) × (baseM −
mBaseTailMain_)`. Omitting it produces a kernel that reads the right shapes from the wrong
addresses — correct-looking tiling, silently wrong output.

## 3 · Ground / Source
The invariant, `swat_design.md:148`:

```
如果 `m % baseM` 产生一个明显小于 `baseM` 的薄片，行窗口的关键路径被它周围的满块拖到 `baseM`。
机制 B 把**最后若干个 tile（含薄片）的 M 尺寸重新等分**，让它们变得均匀。**tile 数量保持不变**，
变的只是尺寸分布。
```

The host search, `:152-175`, in full:

```cpp
if (mTailSize > 0UL && isInnerAxisAlign) {
    uint64_t baseTailCntMax = std::min((runInfo_.baseM - mTailSize) / BASIC_BLOCK_SIZE_16,
                                       runInfo_.mBlockCnt);
    uint64_t windowSize    = std::min(WINDOW_LEN, runInfo_.mBlockCnt);
    uint64_t mainWindowNum = runInfo_.mBlockCnt / windowSize - 1UL;
    uint64_t tailWindowSize = runInfo_.mBlockCnt - mainWindowNum * windowSize;
    uint64_t perfRes       = (mainWindowNum + 1UL) * runInfo_.baseM;
    uint64_t mergeWindowNum = 1UL;

    for (uint64_t mergeLen = tailWindowSize - 1UL; mergeLen < baseTailCntMax;
         mergeLen += windowSize, ++mergeWindowNum) {
        uint64_t newTailMain =
            Align(CeilDiv((mergeLen * runInfo_.baseM + mTailSize), mergeLen + 1UL),
                  BASIC_BLOCK_SIZE_16);
        uint64_t curPerf =
            (mainWindowNum + 1UL - mergeWindowNum) * runInfo_.baseM + mergeWindowNum * newTailMain;
        if (curPerf <= perfRes) {
            perfRes = curPerf;
            runInfo_.mTailMain       = newTailMain;
            runInfo_.mBaseTailSplitCnt = mergeLen + 1UL;
        }
    }
}
```

The device-side reconstruction, `:196-199`, and the resulting layout, `:203-208`: `mBaseNormCnt_`
tiles of `baseM_`, then `mBaseTailSplitCnt − 1` tiles of `mBaseTailMain_`, then one
`mBaseTailLast_`, summing to `m_` with the count still `mCnt_`.

The worked example, `:230-243`, re-derived here term by term because it is the only concrete
instance upstream gives:

```
`baseM=256, m=2404, mCnt=10`：
- `mTailSize = 100, mainWindowNum = 1, tailWindowSize = 6, baseTailCntMax = 9`。
- 迭代 1：`mergeLen=5 → newTailMain=Align16(230)=240`，`curPerf=1·256+1·240=496 < 512`，
  接受 `mBaseTailSplitCnt=6, mTailMain=240`。
- 迭代 2：`mergeLen=9 → newTailMain=256`（饱和），`curPerf=512`，拒绝。

[256][256][256][256][240][240][240][240][240][180]
 └─ mBaseNormCnt_=4 ─┘└──── mBaseTailSplitCnt=6 ────┘
```

Re-derivation: `mCnt = ⌈2404/256⌉ = ⌈9.39⌉ = 10` ✓. `mTailSize = 2404 − 9 × 256 = 100` ✓.
`baseTailCntMax = min((256 − 100)/16, 10) = min(9, 10) = 9` ✓.
`windowSize = min(4, 10) = 4`; `mainWindowNum = 10/4 − 1 = 1` ✓; `tailWindowSize = 10 − 4 = 6` ✓;
`perfRes = 2 × 256 = 512` ✓. Iteration 1: `mergeLen = 5`,
`⌈(5×256 + 100)/6⌉ = ⌈1380/6⌉ = 230`, `Align16(230) = 240` ✓;
`curPerf = (1 + 1 − 1)×256 + 1×240 = 496 ≤ 512` → accept ✓. Iteration 2: `mergeLen = 9`,
`mergeWindowNum = 2`, `⌈2404/10⌉ = 241`, `Align16(241) = 256` ✓;
`curPerf = (1 + 1 − 2)×256 + 2×256 = 512`, and `512 ≤ 496` is false → reject ✓ (the loop's `<=`
compares against the *updated* `perfRes`, which is what makes the rejection correct).
Final layout: `mBaseNormCnt_ = 10 − 6 = 4`; `mMergeSize = 2404 − 4×256 = 1380`;
`mBaseTailMain_ = 240`; `mBaseTailLast_ = 1380 − 5×240 = 180` ✓.
Sum `4×256 + 5×240 + 180 = 1024 + 1200 + 180 = 2404` ✓. Count `4 + 5 + 1 = 10` ✓.

Every step of upstream's worked example checks out. That is worth stating explicitly: in this shelf
it is not the default (`950:0114` records a matmul worked example in the sibling skill that gets a
`CeilDiv` wrong and contradicts its own heading).

What upstream does **not** supply: any measurement that the rebalanced layout is faster. `curPerf`
is a model of the sum of window critical paths, and upstream presents it as the objective without
ever showing it tracks wall time.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — the invariant, cheap and decisive. Build the family's matmul at `baseM = 256, m = 2404`
with mechanism B on and off, and echo from the kernel every tile's `(mTileIdx, singleCoreM, mPos)`.
Check: the count is 10 in both; the sizes with B on are `4×256, 5×240, 1×180`; the sizes sum to
2404 in both; and every `mPos` is the exact prefix sum of the sizes before it. That last check is
the one that catches the omitted GM-offset correction §2 warns about, and it is a property of the
echo, not of any timing.

Arm 2 — does the cost function track wall time? Force `mBaseTailSplitCnt` to each value the search
considered (1, 6, 10) rather than accepting the search's pick, time all three, and compare the
ordering against `curPerf`'s ordering. Upstream's model predicts 6 is best. If 1 or 10 wins, the
model is not tracking the right quantity and the OVERTURN fires. Record per-core busy times as well
as kernel time — mechanism B's claim is specifically about the *window critical path*, so the
discriminating readout is the max-over-cores within a window, not the total.

Arm 3 — the alignment bound. Sweep `mTailSize` (by varying `m`) so that `baseTailCntMax` crosses
zero, and confirm that the search declines to merge when `baseM − mTailSize < 16`. This is the arm
that checks upstream's stated reason for the bound rather than the bound itself.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, beside
every figure. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard if the die moved. Refuses to assume: that a free die stays free; that a die
may be substituted; that the host's `mTailMain` reached the kernel (it is echoed, not read from the
tiling struct); that `WINDOW_LEN` is 4 in the build under test — it is echoed too, because the
search's `windowSize` and the scheduler's window height must be the same 4 (`0306`).

## 5 · Checker — acceptance declared before the run
Verdict `count_invariant` = true iff Arm 1's echoed tile count is identical with B on and off.
Declared before the run: `count_invariant == false` deletes §1's central sentence outright.

Verdict `layout_exact` = true iff the echoed sizes are exactly `[256,256,256,256,240,240,240,240,
240,180]` and every `mPos` equals the prefix sum. Exact, not approximate — these are integer
extents, and an approximate match is a bug.

Verdict `model_ranks` = true iff the wall-time ordering over `mBaseTailSplitCnt ∈ {1, 6, 10}`
matches the `curPerf` ordering, outside the floor. The OVERTURN fires iff `model_ranks == false`
with `curPerf` favouring a slower configuration.

The exit code is not the verdict. Three guards. First, every arm is compared elementwise against one
CPU reference — the GM-offset correction is exactly the kind of error that leaves shapes right and
data wrong, and a timing-only checker cannot see it. Second — the input that makes this checker go
red — Arm 1 is repeated with the `mPos -= (mTileIdx - mBaseNormCnt_) * (baseM_ - mBaseTailMain_)`
correction deliberately deleted. `layout_exact` **must** go false on the `mPos` half while the size
half still passes, and the precision comparison **must** fail. If either stays green, the echo is
not reading the addresses the kernel actually uses and every green from Arm 1 is void. That fixture
is a planted positive the checker has to find. Third, no ordering in Arm 2 is reported without the
floor: three configurations within run spread of each other rank nothing.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The layout
`[256,256,256,256,240,240,240,240,240,180]` is upstream's worked arithmetic, re-derived here on
paper; re-deriving arithmetic is not measuring it, and no kernel has echoed a tile size.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Upstream supplies no timing for mechanism B at any shape, so
nothing here establishes that rebalancing is faster, only that the transform preserves tile count
and sums to `m`. `curPerf` is a model whose correspondence to wall time is asserted and never
shown; §4 Arm 2 is the only thing here that would test it. The worked example is one shape
(`baseM = 256, m = 2404`) in one dimension; the N direction is stated to be symmetric and is not
shown. `isInnerAxisAlign`, the search's other entry condition, is never defined in the file and is
recorded in `harvest/standing/950-bp.md`. The `16` in `Align16` and in `baseTailCntMax` is
`BASIC_BLOCK_SIZE_16`, which the sibling shelf's constant table calls the cube minimum granularity
(`CUBE_BLOCK = 16`) — same repo, one origin, so that is a cross-reference and not corroboration.
BOARD is `family-claimed(unverified)`: no file in this family names a chip (`0347`). Nothing
transfers to the other book (RULES.md Art. 1).
