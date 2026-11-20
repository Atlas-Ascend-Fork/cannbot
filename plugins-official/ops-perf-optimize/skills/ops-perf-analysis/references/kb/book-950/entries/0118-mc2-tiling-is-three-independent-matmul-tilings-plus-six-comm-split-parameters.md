```
ID:        0118-mc2-tiling-is-three-independent-matmul-tilings-plus-six-comm-split-parameters
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/mc2/index.md:13-19,23-30 —
           "MC² 通算融合的 Tiling 分为三部分" ... "> 长块、短块、local 各有独立的完整 matmul
           tiling data，因为不同 M 大小导致不同的 L1/L0 切分策略" and the six-row parameter table
           (tileCnt / longBlockCnt / longMSize / shortBlockCnt / shortMSize / shortBlockPos)
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured MC² case on a named 950 board where reusing the long block's matmul tiling
           for the short block costs nothing beyond run variance — the three-tiling requirement
           would then be a modelling convenience, not a performance fact.
```

# 0118 · MC² tiling is three independent matmul tilings plus six comm-split parameters

## 1 · Claim
Upstream asserts that a communication-computation fused operator's tiling has three parts: the
base matmul tiling (reusing the matmul family's L1/L0 modelling), the comm-split parameters that
cut the M dimension into long and short blocks, and a Local Matmul tiling for this rank's own data
at full M scale. Upstream further asserts that the long block, the short block and the local
matmul each need their own complete matmul tiling data, because different M sizes lead to
different L1/L0 split strategies. The comm-split parameters are six: `tileCnt` (total block count
= `longBlockCnt + shortBlockCnt`, ≥ 1), `longBlockCnt` (`M / longMSize`, ≥ 0), `longMSize`
(constrained to keep Mac utilisation up), `shortBlockCnt` (usually 0 or 1), `shortMSize`
(`M % longMSize`), and `shortBlockPos` (0 = front, 1 = back, decided by execution order × bound
type). Not established here.

## 2 · The wrong branch this removes
The natural economy is to derive one matmul tiling and apply it to all three roles. It is wrong
for a specific reason upstream states and an agent will not infer: the three roles have different
M extents, and M drives `baseM`, which drives the block count, which drives core utilisation and
the whole L1 budget. A short block at `shortMSize = 256` given the long block's `baseM = 512` runs
one partial Cube block per core; the plan is legal, the operator is correct, and the short block —
which sits at the pipeline's drain end where it is least hidden — runs at a fraction of the
achievable rate. The failure is invisible to any correctness check and hard to see in a profile,
because it is a small fraction of total time on a block that is supposed to be small.

`shortBlockPos` removes a second wrong branch: treating block placement as arbitrary. Upstream
says the position is decided by execution order crossed with bound type, i.e. it is a scheduling
decision, and its default (`1`, the drain end) is a fallback, not a recommendation — the
`fallback/tiling-flow.md:158` note is explicit that the position `应根据执行顺序 × Bound 类型调整`
and that back is only the fallback default.

## 3 · Ground / Source
`mc2/index.md:11-19`:

```
## 建模方法

MC² 通算融合的 Tiling 分为三部分：

1. **基础 matmul tiling**：复用 [matmul/](../matmul/) 的建模方法（L1 split: baseM/baseN/baseK + L0 split + Buffer 规划）。
2. **通算切分参数**：在 matmul tiling 基础上，按 M 维度做长短块切分。
3. **Local matmul tiling**：本 rank 数据的独立 matmul tiling（以全量 M 为规模）。

> 长块、短块、local 各有独立的完整 matmul tiling data，因为不同 M 大小导致不同的 L1/L0 切分策略。
```

The six comm-split parameters, `mc2/index.md:23-30`:

```
| 参数 | 说明 | 约束 |
|------|------|------|
| `tileCnt` | 总块数 = longBlockCnt + shortBlockCnt | ≥ 1 |
| `longBlockCnt` | 长块数量 = M / longMSize | ≥ 0 |
| `longMSize` | 长块 M 维大小 | 需保证 Mac 利用率 |
| `shortBlockCnt` | 短块数量（通常 0 或 1） | ≥ 0 |
| `shortMSize` | 短块 M 维大小 = M % longMSize | 需保证 Mac 利用率下限 |
| `shortBlockPos` | 短块位置: 0=前(front), 1=后(back) | 由执行顺序 × Bound 类型决定 |
```

The emitted schema, `mc2/index.md:49-80` (communication-then-compute form), carries the three
tilings as three sibling blocks — `long_qbmm_tiling`, `short_qbmm_tiling`,
`local_qbmm_tiling` — with the short block's `base_m: 128` differing from the long block's
`base_m: 256`, which is the file's own demonstration of the point. The compute-then-communication
form at `:84-108` carries the same three under different names (`mm_long`, `mm_short`,
`mm_local`) with the comm parameters flattened to the top level rather than nested.

The `long_qbmm_tiling` block emits `step_k: 3` (`:64`), a value the matmul family's own field
table says the generator cannot produce — entry 0109, `harvest/CONTRADICTIONS.md` C-008.

Derived quantities and their field rules, `mc2/fallback/tiling-fields.md:13-18,26-30`:

```
| `tileCnt` | uint32 | 总块数（通算切分的 tile 数量） | 均分：`M / longMSize`；短块：`longBlockCnt + shortBlockCnt` | §3.2 / §3.3 |
| `longMSize` | uint32 | 长块的 M 维大小 | 满核下限：`minMBlockCnt × baseM`；均分取满足约束的最小值 | §3.2 |
| `shortBlockPos` | uint8 | 短块位置（0=前, 1=后） | 均分：`0`（无短块）；短块降级默认 `1`（drain 端） | §3.3 |
```

```
| `nBlockCnt` | `ceil(N / baseN)` | N 方向 block 数（固定） |
| `mBlockCnt` | `ceil(longMSize / baseM)` | 单 tile 的 M 方向 block 数 |
| `totalBlocks` | `mBlockCnt × nBlockCnt` | 单 tile 的总 block 数 |
| `utilization` | `min(totalBlocks, N_core) / N_core` | 单 tile 的核利用率 |
| `minMBlockCnt` | `max(1, ceil(N_core / nBlockCnt))` | 满核所需最小 M 方向 block 数 |
```

`utilization` is floored by `min(totalBlocks, N_core)` and can therefore never exceed 1 and never
report over-subscription; `minMBlockCnt` is floored by `max(1, …)` and can therefore never be
zero. Both are safe, and both are the shape of predicate that cannot fail — noted because
`fallback/tiling-flow.md:14` makes `利用率最高` the primary objective, and an objective computed
through two floors ranks fewer candidates apart than it appears to.

The three tilings' sources are named at `mc2/fallback/tiling-fields.md:40-42`: long and short from
`matmul/fallback/`, local from `comm-compute/local_matmul.md` — the last being outside this
domain and outside the tiling subtree.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. MC²
operators are multi-rank, so this procedure needs several dies and is bound by the shared-machine
budget: at most 4 dies, each checked for occupancy before binding, and no die substituted for
another once named.

Device selection: `npu-smi info -l`; for each candidate chip `npu-smi info -t usages -i <id> -c
<chip>` three times at 20 s spacing; bind only chips idle in all three samples; record the exact
chip ids used and re-sample all of them after the run, discarding the case if any moved. Never
exceed 4 dies. The rank count is whatever number of clean dies was obtained, recorded with the
result — a 2-rank result is not a 4-rank result.

Two-arm comparison on one `matmul_all_reduce` case with a deliberately awkward M (M = 5120,
N = 4096, K = 4096, BF16) so that a short block exists. Arm A: three independent matmul tilings,
each derived at its own M scale (`longMSize`, `shortMSize`, full M). Arm B: the long block's
tiling reused verbatim for the short block. Both arms use the same comm-split parameters, so the
only variable is the short block's matmul tiling. Build with one compiler pin; md5 both binaries;
host-print the full tiling data for all three roles in both arms per `mc2/index.md:36-41` — the
print is a precondition, not a convenience (0120). Verify output against an fp64 reference within
the declared tolerance. Capture per rank with ≥10 iterations, the first 5 as warm-up, the mean of
the last 5, and take the maximum across ranks as the case value; host-side timing is not used.

Third arm, for `shortBlockPos`: repeat arm A with `shortBlockPos` = 0 and = 1 and report both.
Upstream says the choice depends on execution order and bound type; this arm makes the cost of the
default visible on one case rather than assuming it.

Refuses to assume: that a die free before the run stayed free; that a die may be substituted for a
named one; that a rank count is interchangeable with another; that the mean-of-last-5 protocol
hides a drifting rank — the per-iteration values are retained and inspected for trend before the
mean is taken; that the same short-block penalty appears at other M values.

## 5 · Checker — acceptance declared before the run
Verdict variable `short_tiling_gain` = (arm B case time − arm A case time) / arm B case time.
Declared before the run: the three-independent-tilings requirement is supported iff
`short_tiling_gain > 0.02` on this case. The OVERTURN fires iff `|short_tiling_gain| ≤ 0.02`,
i.e. reusing the long block's tiling costs nothing measurable — the requirement is then a
modelling convenience. A negative value beyond −0.02 is reported as what it is: the independent
tiling is worse, which no one expects and which would be the most interesting outcome.

The exit code is not the verdict. Multi-rank runs make the blind failure specific: a rank that
crashed or stalled while others completed leaves a full-looking result whose max-across-ranks is
computed over fewer ranks than were launched. The checker therefore requires a completed
per-iteration series from every launched rank and goes red when any series is short, rather than
taking the max over what arrived. Second guard: the host print must show three distinct
`base_m` values in arm A and two identical ones in arm B — if arm A's short-block `base_m` equals
the long block's, the arms are the same experiment and the comparison is void.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no rank was launched. The entry does not establish that three independent
tilings are worth their derivation cost, does not establish any value for `longMSize` or
`shortMSize`, and does not establish the correct `shortBlockPos` for any bound type — upstream
defers that to a file outside this domain. It does not cover the Local Matmul tiling's own
derivation, which lives in `comm-compute/local_matmul.md`, outside the tiling subtree. The
`step_k: 3` in the emitted example is recorded, not resolved (0109). No board is named anywhere in
the MC² directory, so BOARD is `family-claimed(unverified)` and the chip is unstated; §4 names
950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.
