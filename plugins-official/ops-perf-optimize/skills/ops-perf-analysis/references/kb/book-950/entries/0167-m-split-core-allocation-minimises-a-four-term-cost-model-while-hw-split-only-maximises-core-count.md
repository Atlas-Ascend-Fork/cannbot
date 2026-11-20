```
ID:        0167-m-split-core-allocation-minimises-a-four-term-cost-model-while-hw-split-only-maximises-core-count
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/convolution/fallback/tiling-flow.md:63-83 —
           "TotalCost = (loadFMCost + loadWtCost × BW_coeff + loadOutCost) / 128 + cubeCost" ·
           "`BW_coeff = 4`（NCHW 格式非 group 卷积），否则 `= 1`" · "回溯搜索四维因子组合
           (batchDim, mDim, nDim, groupDim)，选择总代价最小的组合" · "HW-split 采用简化策略：在
           batch × ho × wo × n × group 五维因子空间中回溯搜索，最大化 `total = batchDim × hoDim ×
           woDim × nDim × groupDim`（接近 aicoreNum），同分值时选 waste 最小的"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured Conv2D sweep on a named 950 board where the minimum-cost factor combination is
           not the fastest among legal combinations — the cost model would then not rank, and every
           M-split core allocation derived from it would be arbitrary.
```

# 0167 · M-split core allocation minimises a four-term cost model; HW-split only maximises core count

## 1 · Claim
Upstream asserts two different multi-core allocation objectives for the two split modes. M-split
backtrack-searches the four-dimensional factor space `(batchDim, mDim, nDim, groupDim)` and selects
the combination minimising
`TotalCost = (loadFMCost + loadWtCost × BW_coeff + loadOutCost) / 128 + cubeCost`, with the four terms
given as products of ceiling divisions over `batch`, `groups`, `m1`, `ci1`, `k0`, `kh`, `kw`, `co1`
and `n0`, and `BW_coeff = 4` for NCHW-format non-group convolution and `1` otherwise. HW-split uses
what upstream calls a simplified strategy: backtrack-search the five-dimensional space
`(batchDim, hoDim, woDim, nDim, groupDim)` maximising the product `total`, aiming close to
`aicoreNum`, breaking ties toward the smallest waste. Upstream asserts the factor-generation rule:
`CalcCommFactor(num, aicoreNum)` yields every factor dividing `num` and not exceeding `aicoreNum`,
and for `batch`/`groups`, if `batch ≥ 2 × aicoreNum`, all factors of `aicoreNum` are admitted rather
than only factors of `batch`. Not established here.

## 2 · The wrong branch this removes
The two objectives are not two spellings of one idea, and an agent that transfers either to the other
mode gets a different plan. Core-count maximisation ignores data movement entirely: it will pick a
factorisation that fills the machine while re-loading the weight tensor many more times than a
lower-occupancy split would. Cost minimisation ignores occupancy explicitly: nothing in `TotalCost`
rewards using more cores, so it can select a combination leaving cores idle if that moves fewer bytes.
Upstream applies the first to HW-split and the second to M-split, and calls the first `简化策略` —
simplified — which is upstream's own signal that it is the weaker of the two.

`BW_coeff = 4` is the piece an agent will not invent. It multiplies only the weight-load term, and
only for NCHW non-group convolution, which means the model treats weight movement as four times as
expensive as feature-map movement in that one layout. An agent that omits it will systematically
under-weight weight reloading and pick factorisations that re-fetch the filter.

The `/128` divisor is the piece an agent will misread. It divides the three movement terms and not
`cubeCost`, so it is a unit conversion between a byte-ish quantity and a cycle-ish quantity — the
model is comparing movement against compute on a fixed exchange rate of 128. Change the divisor and
the balance between the two shifts; upstream states the number and not its origin.

The factor-generation exception removes a third wrong branch. When `batch ≥ 2 × aicoreNum`, admitting
all factors of `aicoreNum` rather than only factors of `batch` widens the search — an agent that
enumerates only divisors of the dimension will miss the combinations upstream reaches, and will do so
silently, since the narrower set is a subset.

## 3 · Ground / Source
The factor generation, `convolution/fallback/tiling-flow.md:61-65`:

```
### 2.1 因子生成

对每个可切分维度，调用 `CalcCommFactor(num, aicoreNum)` 生成该维度的所有合法因子（能整除 num 且 ≤ aicoreNum）。

对于 batch/groups 维度，若 batch ≥ 2×aicoreNum，允许使用 aicoreNum 的全部因子；否则只使用 batch 自身的因子。
```

The M-split cost model, `:67-79`, in full:

```
### 2.2 M-split 代价模型

TotalCost = (loadFMCost + loadWtCost × BW_coeff + loadOutCost) / 128 + cubeCost

- `loadFMCost = CeilDiv(batch,batchDim) × CeilDiv(groups,groupDim) × m1 × ci1 × k0`
- `loadWtCost = CeilDiv(groups,groupDim) × ci1 × kh × kw × k0 × CeilDiv(batch,batchDim)`（非 opt-group 时再乘 N 维度）
- `loadOutCost = CeilDiv(batch,batchDim) × CeilDiv(groups,groupDim) × CeilDiv(co1×n0,nDim) × m1`
- `cubeCost = CeilDiv(batch,batchDim) × CeilDiv(groups,groupDim) × CeilDiv(co1,nDim) × ci1 × kh × kw × m1`
- `BW_coeff = 4`（NCHW 格式非 group 卷积），否则 `= 1`

回溯搜索四维因子组合 (batchDim, mDim, nDim, groupDim)，选择总代价最小的组合。
```

The HW-split objective, `:81-83`:

```
### 2.3 HW-split

HW-split 采用简化策略：在 batch × ho × wo × n × group 五维因子空间中回溯搜索，最大化 `total = batchDim × hoDim × woDim × nDim × groupDim`（接近 aicoreNum），同分值时选 waste 最小的。
```

The single-core shapes the allocation feeds, `:29-33`:

```
Step 3 — 单核 Shape 计算（Conv2dApiTilingSetShape）：
  ├─ M-split: singleCoreM = CeilDiv(Align(Ho×Wo, m0), mDim)
  │           singleCoreCo = Align(CeilDiv(Align(Co, n0), nDim), n0)
  └─ HW-split: singleCoreHo = CeilDiv(Ho, hoDim), singleCoreWo = CeilDiv(Wo, woDim)
  └─ singleCoreBatch = CeilDiv(Batch, batchDim)
```

Observations recorded against the model as written, not adjudicated.

`mDim` appears in the search space and in `singleCoreM`, but in none of the four cost terms — the
terms contain `m1`, which is not defined in this file, and `nDim` and `groupDim` and `batchDim` all
appear explicitly. So either `m1` depends on `mDim` (making the model's `mDim` sensitivity implicit)
or `TotalCost` is insensitive to `mDim`, in which case a four-dimensional search is optimising over a
variable the objective does not see. Neither reading is stated. Registered as C-950tiling-034.

Five symbols in the cost terms are undefined in this family: `m1`, `ci1`, `co1`, `k0`, `n0`. Two of
them appear as script constants — `N0 = 16`, and `k0` as `B16_K0 = 16` / `B8_K0 = 32` by dtype
(`convolution/fallback/script/conv_tiling.py:51-55`) — and `m1`, `ci1`, `co1` appear nowhere with a
definition. `m0` in `singleCoreM` likewise: the script has `M0 = 16`.

`BW_coeff = 4` matches the script's `BAND_WIDTH_COEFF = 4` at `:63`, so the markdown and the script
agree on that one value. The `/128` divisor has no counterpart named in the script constants list and
no stated origin. `MIN_BURST_SIZE = 128` is a script constant, and whether the divisor is that
quantity is not stated — recorded as an open reading.

The HW-split objective's `waste` tie-breaker is not defined either: `同分值时选 waste 最小的` names a
quantity that appears nowhere else in the family.

Every quantity in this section is unscoped: no board, no architecture, no measurement anywhere in the
convolution family.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — does the cost model rank? This is the entry's claim and the same shape as 0112's test for
matmul's composite score. Take three M-split Conv2D shapes (NCHW non-group so `BW_coeff = 4` applies;
one grouped so it is 1). For each, enumerate every legal `(batchDim, mDim, nDim, groupDim)` under
`CalcCommFactor`, compute `TotalCost` for all of them, and **record the ranking before building
anything**. Then build and run the minimum-cost combination, the maximum-cost one, and four sampled
across the cost range. One compiler pin; md5 each; host echo of the four factors and the derived
single-core shapes; output checked against an fp64 reference within the operator's declared tolerance;
`aic_time` and MTE2 bytes under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5
dropped.

Arm 2 — `BW_coeff` and the `/128` divisor. Re-rank the same candidates with `BW_coeff = 1` and with
divisors of 64, 128 and 256, and record whether the argmin moves. Where it does, build the alternative
argmin and compare. This turns two unexplained constants into measured sensitivities.

Arm 3 — the `mDim` question (C-950tiling-034). Hold `batchDim`, `nDim` and `groupDim` fixed and vary
`mDim` alone across its legal factors, recording `TotalCost` and `aic_time` at each. If `TotalCost` is
flat while `aic_time` is not, the objective is blind to a search dimension and the entry's §3
observation is confirmed behaviourally.

Arm 4 — the two objectives compared. On a shape where both split modes are legal (0166 arm 1), apply
the M-split cost model to the HW-split factor space as an alternative allocation and compare it against
upstream's core-count maximisation. This tests whether `简化策略` is a simplification with a cost.

Refuses to assume: that a free die stays free; that a die may be substituted; that `aicoreNum` is 32
(the script's literal — queried instead, 0141); that `m1`, `ci1`, `co1` have the definitions a reader
guesses — arm 1 evaluates `TotalCost` from the host's own intermediate values where they are exposed,
and where they are not, the arm records the model as unevaluable and stops rather than substituting;
that a factor combination that builds was the one used (host echo required).

## 5 · Checker — acceptance declared before the run
Verdict variables `cost_top1` (does the minimum-cost combination have the lowest median `aic_time`
among those built) and `cost_spearman` (rank correlation between `TotalCost` and measured time over
the six built points), one pair per shape. Declared before the run: the model is a selector iff
`cost_top1` holds on all three shapes; a useful heuristic iff `cost_spearman > 0.7` everywhere while
`cost_top1` fails somewhere; overturned iff `cost_top1` fails by more than 5 % of the best time or
`cost_spearman < 0.3` on any shape.

Verdict `coeff_sensitivity` from arm 2: whether the argmin moves under each alternative constant.
Verdict `mdim_blind` from arm 3: true iff `TotalCost` varies by less than 1 % while `aic_time` varies
by more than the variance floor. Verdict `simplified_cost` from arm 4.

The exit code is not the verdict: a convolution with a wrong factor mapping produces plausible values
and exits 0. The numeric comparison runs on every point and the checker fails red if it did not.
Second guard, and the one this experiment most needs: the ranking must be recorded before any build,
and the checker fails if the prediction file is absent or timestamped after the first measurement —
a cost model ranked after the fact would confirm itself. Third: factor identity via host echo, since a
combination the tiling engine silently replaced would be timed under the wrong label.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The convolution family
contains no measured number at all.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. **Every constant here is unscoped**: `BW_coeff = 4`, the `/128` divisor,
`aicore_num = 32`, `M0 = N0 = 16`, `B16_K0 = 16`, `B8_K0 = 32`, `MIN_BURST_SIZE = 128` — no board, no
architecture, no derivation, no measurement, and the convolution family names no chip anywhere. The
entry does not establish that the cost model ranks correctly, that its four terms are the right terms,
or that `/128` is the right exchange rate between movement and compute. It does not define `m1`,
`ci1`, `co1` or `waste`, none of which the family defines. It does not resolve whether `TotalCost` is
sensitive to `mDim` (C-950tiling-034). It does not establish that HW-split's core-count maximisation
is adequate; upstream calls it simplified and gives no comparison. BOARD is
`family-claimed(unverified)` because no chip is named; §4 names 950PR/950DT because that is where our
run would happen. Nothing here is established for any 910-family board.
