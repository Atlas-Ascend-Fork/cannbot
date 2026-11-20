```
ID:        0067-the-balance-feasible-region-is-scanned-not-solved-and-16-byte-alignment-truncates-it
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:194 — "可行域内所有满足条件的 (M_long, M_short) 组合均为候选解。增大 M_short（减小 M_long）会提高掩盖率但可能增大 drain 开销；减小 M_short（增大 M_long）会降低掩盖率但提升长块 Mac 利用率。需在可行域内扫描所有候选解，按总时间择优"
           ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:203-209 — "M_long_aligned = floor(M_long / 16) × 16 M_short_aligned = M - longBlockCnt × M_long_aligned … 若 M_short < 16，则减小 M_long 直到 M_short ≥ 16"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board where the closed-form balance initial value is the
           best split in the feasible region — the scan would then be unnecessary, and upstream's
           own warning that the initial value is not the optimum would be over-cautious.
```

# 0067 · The balance feasible region is scanned, not solved, and 16-byte alignment truncates it

## 1 · Claim
Upstream asserts that because the balance condition is an inequality, its solutions form a feasible
region rather than a single point; that the closed-form initial value obtained by taking the equality
is only one solution and not necessarily optimal; that within the region there is a trade — a larger
short block raises the masking ratio but increases drain cost, a smaller one lowers masking but
improves the long block's Mac utilisation — so all candidates must be scanned and chosen by total
time; and that M is aligned to 16 bytes by `M_long_aligned = floor(M_long / 16) × 16` with the short
block taking the remainder, reducing `M_long` until `M_short ≥ 16`. Not established here.

## 2 · The wrong branch this removes
Solving the balance equation gives a clean pair of numbers, and a clean number invites delivery. It
is a point on the boundary of the region, chosen for algebraic convenience rather than for time, and
upstream says so explicitly — 配平初值仅为满足配平条件的一个解，不代表全局最优. Delivering it skips the
trade the region exists to express, and the trade is not monotone: masking ratio and Mac utilisation
move in opposite directions as the short block grows, so the optimum is interior and cannot be
reached by improving either one.

The second wrong branch is alignment applied to the wrong quantity. The rule aligns the *long* block
down and gives the remainder to the short block, so the short block absorbs all the misalignment.
An agent that aligns both blocks independently produces a split whose sizes do not sum to M, and one
that aligns the short block down instead moves the truncation into the long blocks, multiplied by
their count.

## 3 · Ground / Source
`pipeline_balancing.md:158-209`, the 配平公式 section. The balance condition (`:160-166`) is entry
0065's subject and is internally contradictory; this entry takes the region *structure* from it,
which both versions share.

Initial value, `:169-178`: solving `longBlockCnt × M_long + shortBlockCnt × M_short = M` together with
the balance condition at equality gives, for the compute-bound single-short-block case,
`M_long = α × M / (α × longBlockCnt + β) = M / (longBlockCnt + R)` and
`M_short = β × M / (α × longBlockCnt + β) = R × M / (longBlockCnt + R)` — algebraically consistent
with version B of the condition — closed by the warning 配平初值仅为满足配平条件的一个解，不代表全局
最优.

Feasible region, `:180-200`: 配平条件是 `≥` … 因此满足配平条件的解为一个**可行域**而非单一值, with the
compute-bound instantiation `M_short ≥ R × M_long`, the constraint
`longBlockCnt × M_long + M_short = M`, and the derived bounds `M_long ≤ M / (longBlockCnt + R)`,
`M_short = M - longBlockCnt × M_long ≥ R × M_long`; the trade sentence quoted in SOURCE; and the
symmetric communication-bound form 配平条件: β × M_short ≥ α × M_long → M_short ≥ (1/R) × M_long.

Alignment, `:202-209`, quoted in SOURCE.

Core-utilisation correction, `:213-234`, gives the other boundary of the region:
`mBlockCnt = ceil(longMSize / baseM)`, `nBlockCnt = ceil(N / baseN)`,
`totalBlocks = mBlockCnt × nBlockCnt`, `effectiveCores = min(totalBlocks, N_core)`,
`utilization = effectiveCores / N_core`, then the interval derivation
`M_long_min = (feasible_mBlk - 1) × baseM + 16` and
`M_long_max = floor((M - 16) / longBlockCnt / 16) × 16`, with 当核利用率不足时，向下回退 mBlockCnt，
找到最大可行值.

Two defects recorded rather than repaired. `feasible_mBlk` in the `M_long_min` formula is never
defined anywhere in the file — the reader is left to infer it from the utilisation text. And
`M_long_max` depends on `longBlockCnt`, which is itself determined by `M_long` (`hc = M / hs` in the
search), so the bound is stated in terms of a quantity derived from what it bounds. Both go to
C-950core-014.

## 4 · Procedure
Later phase, needs one card per rank; capture per 0057, R per 0059, TilingData per 0062.
1. Device selection per 0057; board token per rank from the driver readout; occupancy either side.
2. One operator at R ≈ 3, `longBlockCnt` fixed at 3. Compute the closed-form initial value and the
   feasible region's endpoints from the printed `baseM`/`baseN`/`usedCoreNum`.
3. Enumerate every 16-byte-aligned split in the region, plus the initial value, plus two splits just
   outside each endpoint — the outside points are what show whether the endpoints bind.
4. Measure each per the ten-iteration protocol, recording T_total, the masking ratio (0055) and the
   long block's core utilisation.
5. Repeat with `longBlockCnt` ∈ {2, 4} to check that the region's shape, not just its optimum, behaves
   as described.

## 5 · Checker — acceptance declared before the run
Verdict variables `T(split)` over the enumeration, `argmin` (the fastest split), `T(initial_value)`,
and `interior` = whether `argmin` lies strictly inside the region. Acceptance of upstream's claim
that the scan is necessary: `T(argmin) < T(initial_value)` beyond run spread. Acceptance of the
region's endpoints: the two outside points are slower than the nearest inside point.

Exit code is not the verdict. The full curve is published, with masking ratio and utilisation
alongside T_total, so the stated trade can be seen directly — masking rising and utilisation falling
as the short block grows — rather than inferred from the total alone.

Red input: the two splits outside the region. If they are as fast as the interior ones, the region's
boundary is not binding and the balance condition is not the constraint that matters for this
operator — which would also be the outcome 0065's sweep is designed to detect.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board, operator or rank count. The region's algebra inherits 0065's unresolved
contradiction, so the endpoints written here are version B's; under version A they invert. The 16-byte
alignment unit has no derivation and no scope — it is one of the four alignment constants this
library refuses to unify (0041). `feasible_mBlk` is undefined and `M_long_max` is circular, so the
core-utilisation interval as printed is not evaluable without an interpretation this book does not
supply. Nothing here covers more than one short block.
