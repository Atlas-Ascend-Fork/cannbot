```
ID:        0069-the-theoretical-time-only-ranks-candidates-and-the-top-15-must-be-measured
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:405 — "理论时间仅为排序用代理指标，实际性能受 cache、流水 stall 等硬件因素影响。**必须对 Top-N 候选做 msprof 实测**才能确定最优解——理论最优不一定是实测最优"
           ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:409-413 — "搜索算法输出 Top-N（默认 15）个候选切分方案，而非仅返回理论最优。原因：1. 理论模型未考虑计算膨胀（流水断流、L1 cache miss）和通信膨胀（头开销、带宽下降）的精确量 2. 不同 hs 值的膨胀特性不同，理论时间相近的候选实测可能差异显著 3. Top-N 候选已通过四条剪枝规则过滤，均为可行解，msprof 实测成本可控"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured campaign on a named 950 board in which the theoretically best candidate is the
           measured best in every case — the Top-N protocol would then be pure cost, and the model
           could be trusted to decide rather than only to rank.
```

# 0069 · The theoretical time only ranks candidates, and the top 15 must be measured

## 1 · Claim
Upstream asserts a three-branch analytical time model for a split — compute-bound with the short
block at the drain end, communication-bound with it at the fill end, and the no-short-block uniform
case — built from α, β, the long-block size and the block counts; and asserts that this model is only
a proxy for ranking, because it omits computation inflation (pipeline breaks, L1 misses) and
communication inflation (per-transfer head cost, bandwidth loss), which differ between candidates, so
theoretically close candidates can differ substantially in measurement. Upstream therefore asserts
that the search returns the best fifteen candidates rather than one, that all fifteen must be measured
with msprof, and that the host code must accept `longMSize` on the command line so they can be swept.
Not established here.

## 2 · The wrong branch this removes
A closed-form time model invites a single answer, and the answer will be the most finely split
candidate the constraints allow — because the model's steady-state term falls monotonically with more
overlap while the costs that punish fine splitting are precisely the ones it omits (0070). So the
model is not merely imprecise, it is biased in a known direction, and an agent that trusts it ships
the candidate whose real cost the model cannot see.

The second wrong branch is measuring one or two remembered values instead, which is what MC-C2
forbids (0061). Both errors have the same shape — a decision made without the fifteen measurements —
and the protocol's whole content is that the model narrows the field and the board decides.

## 3 · Ground / Source
The model, `pipeline_balancing.md:375-403`. Compute bound (β > α, short block at drain):

> T_fill      = α × hs                              // 首块通信（无重叠）
> T_steady    = (hc - 1) × β × hs                   // 稳态：计算为瓶颈
> T_transition = max(α × shortMSize, β × hs)        // 末长块→短块切换
> T_drain     = β × shortMSize                       // 短块计算（无重叠）
> T_total     = T_fill + T_steady + T_transition + T_drain

Communication bound (α > β, short block at fill) is the mirror image, and the no-short-block case is
`T_total = α × hs + (tc - 1) × max(α, β) × hs + max(α, β) × hs`.

The proxy warning is quoted in SOURCE, as is the Top-N rationale. The implementation requirement,
`:415-428`: host code must support a command-line `longMSize`, with the shown derivation
`longBlockCnt = m / longMSize; shortMSize = m % longMSize; shortBlockCnt = (shortMSize > 0) ? 1 : 0;
tileCnt = longBlockCnt + shortBlockCnt` — the same remainder construction whose interaction with P4
is entry 0066 — and `:428`: 实施阶段对 Top-N 候选分别设置 longMSize 参数运行 msprof，按实测 aiv_time
选最优. Note that this last line says `aiv_time` while the MC² capture protocol (0056, 0057) says
`Task Duration` from `op_summary_*.csv`; the two are not the same column. Recorded as C-950core-016.

The claimed spacing, `:316`: 搜索空间通常缩减到 10-50 个候选解（而非 M/16 ≈ 数百个），每个候选的性能
差异可达 5-10us，只取几个代表点会遗漏最优点 — a magnitude claim with no case identity, and one that
sets the precision the measurement protocol must achieve (0056's concern).

Output schema, `:450-491`: the emitted block carries `operator_order`, `bound_type`, R, α, β, the
`tiling_data_ref` (baseM/baseN/N_core, each marked 从 host 打印获取), `search_params` (hs_min, hs_max,
tcFloor, tcCap, utilThreshold, candidate_count) and `top_candidates` with per-rank fields
(long_m_size, long_block_cnt, short_block_cnt, short_m_size, tile_cnt, short_block_pos, est_time,
utilization, key_constraint), plus `recommended` and a `tiling_correction` list. The schema is worth
carrying because it names exactly which quantities a recommendation must expose — including
`est_time`, which the same file says must not be trusted alone.

## 4 · Procedure
Later phase, needs one card per rank; capture per 0056/0057, R per 0059, TilingData per 0062 for each
candidate.
1. Device selection per 0057; board token per rank from the driver readout; occupancy either side.
2. For one operator, run the search (with P4 handled per 0066's arms) and record the full ranked
   candidate list with `est_time`.
3. Measure *all* candidates that survive pruning — not only the top fifteen — so the protocol's own
   cut-off can be evaluated. Ten iterations each, cross-rank maximum.
4. Record the rank correlation between `est_time` and measured time, the measured optimum's rank in
   the theoretical ordering, and the measured spread between adjacent candidates.
5. Repeat for a second operator with a different bound direction.

## 5 · Checker — acceptance declared before the run
Verdict variables `rank_corr` (Spearman between `est_time` and measured), `opt_rank` (the theoretical
rank of the measured optimum), and `adjacent_gap` (median measured difference between adjacent
candidates). Acceptance of the Top-15 protocol: `opt_rank ≤ 15` in every case. Acceptance of the
model as a ranking proxy: `rank_corr` positive and substantial. And the honesty check on the stated
magnitude: `adjacent_gap` in the 5-10 μs range upstream claims, or else that claim is corrected in
place.

Exit code is not the verdict. The full candidate table is published with both times, including
candidates whose measured time is far from their estimate — those are the evidence for the omission
the model admits, and they are named individually rather than summarised.

Red input: the candidate the model ranks last among survivors. If it is the measured optimum,
`opt_rank` exceeds 15 and the protocol's cut-off is refuted — the check is built so that outcome is
reachable, which is why all survivors are measured and not only the top fifteen.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. No board, operator or rank count. The model's three branches assume linear per-row
costs (0059) and no inflation (0070), both unverified; N = 15 and the 5-10 μs spacing have no
derivation. The `aiv_time` versus `Task Duration` inconsistency in the implementation note is
recorded, not resolved. It does not establish that the candidate set contains the true optimum at all
— the enumeration is 16-byte-aligned and single-short-block, so a better split outside those
constraints would never be measured.
