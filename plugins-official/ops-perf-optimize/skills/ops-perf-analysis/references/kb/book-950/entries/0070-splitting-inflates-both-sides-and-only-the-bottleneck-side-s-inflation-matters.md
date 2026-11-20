```
ID:        0070-splitting-inflates-both-sides-and-only-the-bottleneck-side-s-inflation-matters
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/expansion_analysis.md:30 — "膨胀的影响取决于 Bound 类型——**被掩盖方的膨胀对端到端性能影响较小**，应优先最小化瓶颈方的膨胀"
           ops/ascendc-perf-optimize/references/comm-compute/expansion_analysis.md:13-24 — "**根因**： - 流水断流：每次切分边界处 MTE2/MTE1/CUBE 流水需要重新填充，产生气泡。 - 用核不满 … - 核利用率降低：longMSize 过小时 mBlockCnt 不足，mac_ratio 下降。… - 头开销分摊：每次通信发起有固定开销（BarrierAll + CrossCoreFlag），切分次数越多总头开销越大。 - 带宽利用率下降：单次通信数据量变小，无法达到峰值带宽"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board where inflating the masked side degrades end-to-end
           time as much as inflating the bottleneck side — the asymmetry that the whole priority rule
           rests on would then not exist.
```

# 0070 · Splitting inflates both sides, and only the bottleneck side's inflation matters

## 1 · Claim
Upstream asserts that splitting an MC² operator inflates both phases: computation inflates from
pipeline refills at every split boundary, from block counts below the core count, and from
`mac_ratio` falling when `longMSize` is too small; communication inflates from the fixed per-transfer
head cost (`BarrierAll` plus `CrossCoreFlag`) accumulating with the number of transfers, and from each
transfer being too small to reach peak bandwidth. Upstream asserts that inflation on the *masked* side
matters little end-to-end, so the inflation of the bottleneck side should be minimised first — for a
compute-bound operator, minimise matmul inflation; for a communication-bound one, minimise
communication inflation; when balanced, weigh both. Not established here.

## 2 · The wrong branch this removes
Every other part of the MC² chain pushes toward more splitting: masking improves, the steady-state
term of the time model falls, the balance condition becomes easier to satisfy. This entry is the
counter-pressure, and without it the search's theoretical optimum is systematically too fine (0069).

The specific wrong branch is symmetric accounting. An agent that knows splitting has costs will try
to minimise total inflation, and will spend its effort wherever inflation is largest — which is often
the masked side, because the masked side is the one with slack. Reducing an inflation that is hidden
behind the other phase buys nothing. The rule's content is that the objective is not "less
inflation" but "less inflation on the side that determines the wall clock", and which side that is
comes from R (0058).

## 3 · Ground / Source
`expansion_analysis.md:7-26`, the two inflation types with their causes, quoted in SOURCE. Note that
the compute-inflation causes are three different mechanisms — refill bubbles at boundaries, idle cores
when `totalBlocks < N_core`, and falling `mac_ratio` at small `longMSize` — of which only the second
and third are captured by the core-utilisation rule of 0068; the refill bubble is named nowhere else
and is modelled nowhere.

`expansion_analysis.md:28-36`, the priority rule quoted in SOURCE, with its table: compute bound →
bottleneck matmul, masked communication, 通信膨胀影响较小，应**最小化 matmul 膨胀**; communication
bound → the mirror; balanced → 综合平衡两侧膨胀，以端到端整体最优为目标.

`expansion_analysis.md:40-53`, the output schema: `expansion_assessment` with `bound_type`, a
`compute_expansion` block (level low/medium/high plus cause) , a `comm_expansion` block, a
`minimize_priority` ∈ {compute, comm, balanced} and a `recommendation`. The levels are qualitative and
no rule maps a measurement onto them — a gap worth noting, since the schema is what a consuming agent
will fill in.

`expansion_analysis.md:55-60`, the granularity advice, which is where this file makes its sharpest and
least supported claim: 计算 Bound + 恒满核 → keep the matmul block large enough for Mac utilisation,
tileCnt 不宜过大（R>2 时倾向少切分，须搜索确认）; 计算 Bound + 核不满 → adjust `longMSize` so the block
count approaches the core count, 核利用率收益通常远大于配平气泡收益; 通信 Bound → keep each transfer
large enough for bandwidth, search from the short block maximising tileCnt; 完美平衡 → split freely
subject to Mac utilisation on both sides.

That middle sentence — core-utilisation gain usually far exceeds balancing-bubble gain — is a
quantitative priority claim between two effects, stated without a single number, and it is the one
this entry's procedure is built to test.

## 4 · Procedure
Later phase, needs one card per rank; capture per 0057, R per 0059, TilingData per 0062.
1. Device selection per 0057; board token per rank from the driver readout; occupancy either side.
2. Isolate the two inflations by measuring *uniform* splits only, so balancing plays no part: for one
   operator, sweep tileCnt from 1 to 16 with equal blocks, and record T_total, T_compute-only and
   T_comm-only at each tileCnt (three builds per point, per 0059).
3. The compute-only curve against tileCnt is computation inflation; the comm-only curve is
   communication inflation. Record both in absolute microseconds and as a fraction of the tileCnt=1
   value.
4. Repeat at R ≈ 3 (compute bound) and R ≈ 0.3 (communication bound), and compare each regime's
   end-to-end curve against the two inflation curves.
5. Separately, for the priority claim: at a fixed R > 1 and a fixed tileCnt, compare two candidates —
   one chosen to maximise core utilisation, one chosen to satisfy the balance condition exactly — and
   measure both.

## 5 · Checker — acceptance declared before the run
Verdict variables `infl_compute(tc)`, `infl_comm(tc)` (each as a ratio to tileCnt=1), and
`dT_total(tc)`. Acceptance of the asymmetry claim: at R ≈ 3, `dT_total` tracks `infl_compute` and is
insensitive to `infl_comm` — operationally, the correlation of `dT_total` with `infl_compute` exceeds
its correlation with `infl_comm`, and the mirror holds at R ≈ 0.3. Acceptance of the priority claim
from step 5: the utilisation-maximising candidate is faster beyond spread.

Exit code is not the verdict. All three curves are published per regime; the case where both
inflations rise together — which is the expected shape and makes the two correlations hard to
separate — is reported as `inflations_collinear` rather than resolved by picking the larger
correlation.

Red input: tileCnt = 1, where by construction there is no inflation of either kind. Both inflation
ratios must be exactly 1.0 there; if they are not, the three-build decomposition is not stable enough
to support any of the curves.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. No board, operator, rank count or shape. None of the five named inflation causes is
quantified anywhere upstream, and the low/medium/high levels in the output schema have no mapping to
any measurement. The priority claim (core utilisation over balancing bubbles) is stated without
numbers and is not established. The decomposition in the procedure inherits 0059's closure problem:
if the isolated builds do not sum to the fused time, the two inflation curves are not additive
components of the end-to-end one.
