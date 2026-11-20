```
ID:        0068-core-utilization-must-reach-80-percent-when-compute-bound-and-50-percent-when-comm-bound
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:285 — "| P2 | **核利用率硬约束**：长块 totalBlocks / N_core < 阈值直接排除 | 用核不满的切分实际性能必然劣化 | 计算 bound ≥ 80%，通信 bound ≥ 50% |"
           ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:301 — "utilThreshold = (R >= 1) ? 0.80 : 0.50    // 计算 bound 硬约束 80%，通信 bound 软约束 50%"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board in which a split whose long-block core utilisation
           is below 80% at R > 1 is the fastest of the candidate set — the "hard" constraint would
           then be excluding the optimum, which is the worst thing a pruning rule can do.
```

# 0068 · Core utilisation must reach 80% when compute bound and 50% when communication bound

## 1 · Claim
Upstream asserts that a candidate split whose long block leaves cores idle is necessarily worse in
practice, and prunes on it: the long block's `totalBlocks / N_core` must reach 80% for a
compute-bound operator (R ≥ 1) and 50% for a communication-bound one (R < 1), where
`totalBlocks = ceil(longMSize / baseM) × ceil(N / baseN)` and `N_core = usedCoreNum` from the printed
TilingData. Upstream asserts this same threshold pair drives the search's lower bound on the
long-block size. Upstream calls the compute-bound threshold a hard constraint in one place and the
communication-bound one soft in another. Not established here.

## 2 · The wrong branch this removes
The balance condition and the masking ratio both push toward smaller long blocks: more tiles, finer
overlap, higher masking. Nothing in that reasoning notices that a matmul block smaller than the core
count leaves cores idle inside every tile — so the pipeline looks better and the machine does less
work. This threshold is the counterweight, and it is the reason the R-value table's recommendations
differ between "satisfies full cores" and "does not" at the same R (0073). Without it an agent
converges on the most finely split candidate the balance condition allows.

The wrong branch inside the rule is treating utilisation as a property of the operator rather than of
the split *and* the tiling. `totalBlocks` depends on `baseM` and `baseN`, which the host tiling engine
chooses per block and re-chooses when M changes (0062) — so utilisation must be recomputed per
candidate from that candidate's own printed tiling data, not once from the baseline's.

## 3 · Ground / Source
`pipeline_balancing.md:213-234`, the mechanism: matmul is split to cores at `baseM × baseN` block
granularity, `mBlockCnt = ceil(longMSize / baseM)`, `nBlockCnt = ceil(N / baseN)`,
`totalBlocks = mBlockCnt × nBlockCnt`, `effectiveCores = min(totalBlocks, N_core)`,
`utilization = effectiveCores / N_core`, with N_core the AIC core count.

The rule, `:285`, quoted in SOURCE, with its stated rationale 用核不满的切分实际性能必然劣化 — an
assertion about hardware, given without measurement. The search's use of the same thresholds,
`:299-305`:

> utilThreshold = (R >= 1) ? 0.80 : 0.50    // 计算 bound 硬约束 80%，通信 bound 软约束 50%
> minTotalBlocks = ceil(utilThreshold × N_core)
> minMBlockCnt   = max(1, ceil(minTotalBlocks / nBlockCnt))
> hs_min = max(baseM, (minMBlockCnt - 1) × baseM + 16)   // 保证 mBlockCnt ≥ minMBlockCnt
> hs_min = align16(hs_min)

and again in the enumeration at `:354-359`, where the same computation is applied per candidate as a
`continue`.

Note the inconsistency in modality: the P2 table row calls both thresholds a 硬约束 while the
range-derivation comment calls the 50% one a 软约束, and the pseudocode implements both as hard
`continue`s. Recorded as C-950core-015. Note also that the utilisation formula saturates:
`min(totalBlocks, N_core)` means every candidate with `totalBlocks ≥ N_core` scores exactly 1.0, so
the rule cannot distinguish a split that fills the cores once from one that fills them three times
over — the load-balance question inside a wave is invisible to it.

Related statements: `expansion_analysis.md:16` names 核利用率降低 as one of three causes of compute
inflation — longMSize 过小时 mBlockCnt 不足，mac_ratio 下降 — and `:58` says that for a compute-bound
operator with unfilled cores, adjusting `longMSize` so the block count approaches the core count is
usually worth far more than the balancing bubble (核利用率收益通常远大于配平气泡收益). That is a
priority claim between two effects, and it is also unmeasured.

## 4 · Procedure
Later phase, needs one card per rank; capture per 0057, R per 0059, TilingData per 0062 for every
candidate.
1. Device selection per 0057; board token per rank from the driver readout; occupancy either side;
   record `usedCoreNum` from the print rather than assuming a core count.
2. One operator at R ≈ 3 and one at R ≈ 0.3. For each, enumerate long-block sizes so that the
   computed utilisation sweeps 0.3 to 1.0 in at least eight steps, recomputing `baseM`/`baseN` per
   candidate from its own printed tiling data.
3. Measure every candidate per the ten-iteration protocol — including the ones P2 would prune, which
   is the point: a pruning rule can only be validated by measuring what it discards.
4. Record T_total, the long block's `mac_ratio` if available, and the masking ratio.

## 5 · Checker — acceptance declared before the run
Verdict variables `T(util)` over the sweep and `argmin_util` = the utilisation of the fastest
candidate. Acceptance of the 80% threshold at R ≥ 1: `argmin_util ≥ 0.80`, and every candidate below
0.80 slower than the best one beyond spread. Acceptance of 50% at R < 1: the same with 0.50. A
threshold is refuted the moment the fastest candidate sits below it.

Exit code is not the verdict. The whole curve is published including the pruned region, and the
utilisation values are reported both saturated (as the formula computes them) and unsaturated
(`totalBlocks / N_core` without the `min`), since the saturated form cannot distinguish candidates
above 1.0 and the difference between them may be where the real structure is.

Red input: a candidate with `totalBlocks` far above `N_core` — several waves per tile. Its saturated
utilisation is 1.0, so P2 admits it; if it is slow, P2's metric is insufficient rather than wrong,
and that distinction is recorded.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. The two thresholds have no derivation, no board, no operator family, and no case
identity anywhere upstream, and their modality is stated inconsistently. `N_core` is whatever the
host print says; this book has established no core count for any 950 board. The utilisation formula's
saturation is not a defect this entry resolves. Nothing here covers the AIV side, which has its own
core count and no stated utilisation rule, and nothing covers short-block utilisation — the rule is
applied to the long block only, by upstream's own comment 主轮 = 长块.
