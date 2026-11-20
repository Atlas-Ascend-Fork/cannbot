```
ID:        0017-tens-of-thousands-of-tiny-tiles-turn-fixed-per-tile-cost-into-a-scalar-bound
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/scalar.md:10 — "**tile 数巨大、每 tile 计算量小**：每 tile 的固定开销（DataCopyPad/Broadcast/EnQue/launch 等）摊不开 → `scalar_ratio` 高、发射 bound，**甚至慢于更粗粒度的基线**（典型：小 shape 广播每 tile 只含一个小平面、`totalTiles` 上万）"
           ops/ascendc-perf-optimize/references/single-core-pipeline/scalar.md:30 — "**每 tile 打包多 batch**：小 tile 过多致固定开销 bound 时，一个 tile 装多个 batch（`batchPerTile = elemNum/plane`）、整块一次计算/搬运，把 `totalTiles` 降一个量级（准入 `plane % 对齐 == 0`，非对齐回落）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a sweep on a named 950 board in which `aiv_time` is flat or falling as `totalTiles`
           rises past ten thousand at fixed total element count — the fixed per-tile cost would
           then not dominate, and the packing remedy would have no target.
```

# 0017 · Tens of thousands of tiny tiles turn fixed per-tile cost into a scalar bound

## 1 · Claim
Upstream asserts that when the tile count is very large and the per-tile computation is small,
the fixed cost of each tile — DataCopyPad, Broadcast, EnQue, launch — fails to amortise, so
`scalar_ratio` rises, the kernel becomes issue-bound, and it can run *slower than a coarser
baseline*; the typical shape is a small-shape broadcast where each tile holds one small plane
and `totalTiles` is in the tens of thousands. Upstream asserts the remedy is to pack several
batches into one tile — `batchPerTile = elemNum/plane`, computing and moving the block at once —
lowering `totalTiles` by an order of magnitude, admitted only when `plane % alignment == 0`,
with a fall-back for the unaligned case. Not established here.

## 2 · The wrong branch this removes
A tiling model that minimises per-tile UB residency will happily produce tens of thousands of
tiny tiles: every tile fits, every constraint is satisfied, the model reports success. The
kernel is then slower than the naive version it replaced, and the profile blames SCALAR — a lane
nobody optimises, because the four bound pages route scalar to a placeholder card (0050). An
agent that reads "scalar bound" and looks for redundant scalar arithmetic will find none: the
scalar work is the per-tile fixed cost, and it is a *tiling* defect visible only as a *scalar*
symptom. This entry is the bridge between the two, and it is the only place in the single-core
half of the skill where a diagnosis page prescribes a change to the tiling rather than to the
kernel body.

## 3 · Ground / Source
`scalar.md:5-10`, the page's 判定条件, whose fourth bullet is the one that carries content:

> - 总计算量极小（如 element count < 阈值）
> - Scalar 指令占比高，Vector/Cube 单元空闲
> - 指令发射率低，IPC 偏低
> - **tile 数巨大、每 tile 计算量小**：每 tile 的固定开销（DataCopyPad/Broadcast/EnQue/launch
>   等）摊不开 → `scalar_ratio` 高、发射 bound，**甚至慢于更粗粒度的基线**（典型：小 shape
>   广播每 tile 只含一个小平面、`totalTiles` 上万）

and `scalar.md:26-30`, the Tiling 修正建议, whose third bullet is the remedy quoted in SOURCE.
The first two bullets — 适当增大单次处理粒度，减少循环次数 and 考虑与其他 kernel 融合以减少
launch 开销 — are stated without conditions.

The 阈值 in the first bullet is never given a value anywhere in the skill; 上万 in the fourth is
the only magnitude offered, and it is an example rather than a cut. The admission predicate for
packing, `plane % 对齐 == 0`, does not say which alignment — and per 0041 the alignment constant
in this family is not one number. The related issue-side mechanism, where a tile's copy
instructions exceed the hardware queue depth and back-pressure the scalar core, is described
from the other direction at `nobound-02:30`.

## 4 · Procedure
Later phase, needs a card. Board token from the driver readout.
1. Device selection per 0010; explicit visible-devices; occupancy recorded either side; refusal
   to run on an unnamed die.
2. Fix a total element count and a small-shape broadcast operator. Sweep `batchPerTile` over
   powers of two so that `totalTiles` spans 4 orders of magnitude, from tens to tens of
   thousands, holding the computation itself identical.
3. At each point record `aiv_time`, `aiv_scalar_ratio`, `aiv_vec_ratio`, and the coarse baseline
   — a single-tile-per-core implementation of the same operator — as the reference line.
4. Repeat the sweep at one aligned and one deliberately unaligned `plane` value, to exercise the
   admission predicate and its fall-back.

## 5 · Checker — acceptance declared before the run
Verdict variables declared before the sweep. `slower_than_coarse` = true iff there exists a
point in the sweep whose median `aiv_time` exceeds the coarse baseline's by more than the pooled
spread — that is upstream's strongest claim and the one worth being able to refute.
`scalar_tracks` = the sign of the correlation between `totalTiles` and `aiv_scalar_ratio` across
the sweep, required positive. `packing_gain` = the `aiv_time` ratio between the worst point and
the best packed point.

Exit code is not the verdict; the sweep completes whatever the shape of the curve. The full
curve is published, including the flat region if there is one, and the unaligned arm is reported
even when it falls back and therefore shows no gain — retained because it did not bite.

Red input: the coarse baseline itself, entered as a sweep point with `totalTiles` at its
minimum. If it does not come out fastest, the sweep is not measuring what the claim is about and
the run is reported `baseline_anomalous` rather than being read as a refutation.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board; no shape probed. It does not establish where the crossover is — the
threshold in 总计算量极小（如 element count < 阈值）has no value upstream and none is invented
here. It does not establish that the four named fixed costs (DataCopyPad/Broadcast/EnQue/launch)
are the dominant ones, or in what proportion; that decomposition is unmeasured. The alignment in
the admission predicate is unspecified, so the predicate as written is not executable. It says
nothing about multi-core interactions: `totalTiles` is a per-kernel quantity here, and the
distribution of tiles across 56 cores is not part of the claim.
