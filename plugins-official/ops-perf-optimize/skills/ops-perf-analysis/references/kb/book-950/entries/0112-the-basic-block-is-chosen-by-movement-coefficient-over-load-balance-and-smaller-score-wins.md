```
ID:        0112-the-basic-block-is-chosen-by-movement-coefficient-over-load-balance-and-smaller-score-wins
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:84-114 —
           "计算访存系数：(1 / baseM) + (1 / baseN)" · "负载均衡率：单核平均计算量 / 单核计算最大量"
           · "将两个指标归一为 综合评分 = 计算访存系数 / 负载均衡率 综合评分越小 → 越优" ·
           "本节筛选结果作为 §3.3-§3.6 的**唯一输入**。不可跳过本节直接进入尾块拆分或 L1 切分。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board where the enumerated (baseM, baseN) pair with the
           lowest composite score is not the fastest legal pair for that shape — the score is then
           a heuristic that does not rank, and every plan derived from it inherits the error.
```

# 0112 · The basic block is chosen by movement coefficient over load balance, and the smaller score wins

## 1 · Claim
Upstream asserts a single scalar objective for choosing the Cube basic block. Two indices are
defined: a compute-to-movement coefficient `(1 / baseM) + (1 / baseN)`, smaller meaning less data
movement per unit of compute; and a load-balance rate, single-core average work over single-core
maximum work, with `单核平均计算量 = m * k * n / aicNum`,
`单核最大计算量 = Ceil(totalBlockCnt / aicNum) * baseM * baseN` and
`totalBlockCnt = Ceil(m / baseM) * Ceil(n / baseN)`, closer to 1 meaning better balance. They are
combined as `综合评分 = 计算访存系数 / 负载均衡率`, and the smaller composite score wins. The
enumeration runs `baseM ∈ [16, Align(M,16)]` and `baseN ∈ [16, Align(N,16)]` at step 16, subject
to the L0A/L0B/L0C capacity constraints, and `baseK` is then set to fill L0A/L0B. Upstream further
asserts that this selection is the sole input to the four downstream steps and may not be skipped.
Not established here.

## 2 · The wrong branch this removes
The tradeoff itself is the wrong branch. Larger `baseM`/`baseN` reduce movement — upstream states
it plainly at `:84`: `baseM/baseN 越大 → 计算访存系数越小（搬运少），但 tile 总数减少 → 负载均衡率
可能下降`. An agent optimising either index alone lands at an extreme: maximise the block and a
64-core machine runs 9 tiles with most cores idle; maximise tile count and every core is busy
moving the same operands repeatedly. Both extremes produce correct kernels with unremarkable
times, and the profiler shows a different symptom in each case (low occupancy vs MTE2 saturation),
so an agent that fixes the symptom it sees walks to the opposite extreme on the next iteration.
The composite score exists to stop that oscillation with one number.

The `唯一输入` sentence removes a second wrong branch: re-deriving `baseM`/`baseN` inside tail
splitting or L1 splitting, which is tempting because both later steps have their own capacity
pressure. Upstream forbids it — the block chosen here is what the later steps consume, and a step
that quietly re-optimises breaks the score that justified the block.

## 3 · Ground / Source
`matmul/fallback/tiling-flow.md:82-114`, §3.2 in full:

```
### 3.2 基本快筛选解集

**核心 tradeoff**：baseM/baseN 越大 → 计算访存系数越小（搬运少），但 tile 总数减少 → 负载均衡率可能下降。大 base 块利于算力发挥，小 base 块利于多核负载均衡，需量化取舍。

用两个指标描述基本块能力：

计算访存系数：(1 / baseM) + (1 / baseN)
效果：系数越小，搬运量越小，越容易发挥算力；

负载均衡率：单核平均计算量 / 单核计算最大量
单核平均计算量 = m * k * n / aicNum
单核最大计算量 = Ceil(totalBlockCnt / aicNum) * baseM * baseN
totalBlockCnt = Ceil(m / baseM) * Ceil(n / baseN)
效果：结果越接近1，多核负载均衡越好，反之则越差

上述指标综合考虑获取最优的baseM，baseN，并在用满L0A/L0B的情况下确认baseK；

筛选策略：
   将两个指标归一为 综合评分 = 计算访存系数 / 负载均衡率
   综合评分越小 → 越优（计算访存比好 且 负载均衡）

   枚举范围：
   baseM ∈ [16, Align(M, 16)]，步长16
   baseN ∈ [16, Align(N, 16)]，步长16
   满足 §3.1 的 L0A/L0B/L0C 容量约束

> **输入下游**：本节筛选结果作为 §3.3-§3.6 的**唯一输入**。不可跳过本节直接进入尾块拆分或 L1 切分。
```

Two observations recorded against the definitions as written. First, the load-balance rate's
numerator is a work volume in `m·k·n` elements while its denominator is
`Ceil(totalBlockCnt/aicNum) · baseM · baseN`, which has no `k` factor — the ratio is therefore not
dimensionless unless a `k` is implied in the denominator. Read literally it scales with `k`, and
the composite score then depends on K even though neither index is supposed to. Whether `k` is
implied is not stated; both readings are recorded and neither is adopted.

Second, the affinity constraints from §3.1 (`:76-80`) restrict the enumeration further and are
dtype-dependent: `左矩阵转置时，要求baseM * sizeof(dtype)是128Bit对齐`,
`右矩阵不转置时，要求baseN * sizeof(dtype)是128Bit对齐`. At FP16 that is `baseM % 8 == 0`, which
the step-16 enumeration already satisfies; at FP4 it is `baseM % 32 == 0`, which the step-16
enumeration does not, so half the enumerated candidates are illegal for the MX variants and
upstream does not say they are filtered.

The upper bound `BASEM_BASEN_RATIO = 2` (`:34`, `:374` — `baseM/baseN 最大比例，防止维度失衡`)
constrains the pair further and is not mentioned in §3.2's enumeration text.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Exhaustive rank test. Pick three shapes spanning the tradeoff: balanced (M=N=2048, K=2048),
tile-starved (M=N=256, K=8192), and movement-heavy (M=8192, N=128, K=2048), all BF16. For each,
enumerate every legal `(baseM, baseN)` at step 16 under the §3.1 capacity constraints with
capacities read at runtime (0141), apply the `BASEM_BASEN_RATIO ≤ 2` filter, and compute the
composite score for each candidate — recording the score table before any kernel is built, so the
prediction is on record ahead of the measurement. Then build and run every candidate: one compiler
pin, md5 per binary, host echo of `baseM`/`baseN`/`baseK`, fp64 reference check within the
declared tolerance, `aic_time` under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first
5 dropped, per case with no representative sampling. Where the candidate count exceeds a
practical build budget, sample the score range uniformly rather than the parameter range, and
record the sampling rule.

Second arm, for the `k` ambiguity in §3: repeat the balanced shape at K ∈ {512, 2048, 8192} and
check whether the score's argmin moves with K. Under the literal reading it does; under the
implied-`k` reading it does not. This arm settles a reading of upstream's formula, not a fact
about hardware, and is labelled as such.

Refuses to assume: that a free die stays free; that a die may be substituted; that the capacity
constraints use any literal capacity; that the enumerated candidate is the one that ran (host echo
required); that a rank established at BF16 holds at FP4, where the affinity constraints bite
differently.

## 5 · Checker — acceptance declared before the run
Verdict variables `rank_top1` (does the lowest-score candidate have the lowest median `aic_time`)
and `rank_spearman` (Spearman correlation between score rank and time rank over the built
candidates), one pair per shape. Declared before the run: the score is a selector iff `rank_top1`
holds on all three shapes; it is a useful heuristic but not a selector iff `rank_top1` fails
somewhere while `rank_spearman > 0.7` everywhere; it is overturned — the OVERTURN condition — iff
`rank_top1` fails on any shape by more than 5 % of the best time, or `rank_spearman < 0.3` on any
shape.

The exit code is not the verdict. The blind mode this checker must avoid: a build whose
`baseM`/`baseN` were re-derived downstream (exactly what `唯一输入` forbids) would run a different
block than the one scored, and the correlation would then be measuring nothing while looking
healthy. The host echo of the actual `baseM`/`baseN`/`baseK` is therefore compared against the
enumerated candidate for every point, any mismatch marks the point `substituted` and excludes it,
and the checker goes red if any point is `substituted` — a silently re-derived block is a finding
about the generator, not a data point to average over.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no candidate was scored against a clock. The entry does not establish that
the composite score ranks correctly, that division is the right combination of the two indices
(upstream offers no derivation and no alternative), or that the two indices are the right two. It
does not resolve the `k`-dimension ambiguity in the load-balance rate — both readings are recorded
and §4 arm 2 is what would settle it. It does not establish the L0A/L0B/L0C capacities that bound
the enumeration (0111). It does not establish how the MX variants' 128-bit affinity constraint
interacts with the step-16 enumeration; upstream does not say. No board is named in the source
file, so BOARD is `family-claimed(unverified)` and the chip is unstated; §4 names 950PR/950DT
because that is where our run would happen. Nothing here is established for any 910-family board.
