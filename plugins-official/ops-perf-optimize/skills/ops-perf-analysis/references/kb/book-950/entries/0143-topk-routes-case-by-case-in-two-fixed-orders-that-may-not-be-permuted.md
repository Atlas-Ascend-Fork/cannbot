```
ID:        0143-topk-routes-case-by-case-in-two-fixed-orders-that-may-not-be-permuted
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/sort/topk.md:47-57,236-253 —
           "## 3. Step 1：一级路由，顺序不可交换" · "1. fixed small-axis (tilingKey 900001)
           2. fallback candidate 2.1 transpose-fallback (900003) 2.2 batched fallback L/S (900002)
           3. common tiler" · "不要交换 inter/intra 或 radix 各模式的判断顺序；modeType
           1/2/4/5/6/7/8 是 host-kernel 契约。" ; sort/index.md:3-4 — "TopK 必须按 `outer / D /
           inner / rows / k / dtype / UB / coreNum` 做 case 级路由，不能只按 dtype 选择算法。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured TopK case on a named 950 board where a later template in either priority
           order beats the first one whose gate the case satisfies — the fixed order would then not
           be a performance order, and permuting it would be an improvement rather than a defect.
```

# 0143 · TopK routes case by case in two fixed orders that may not be permuted

## 1 · Claim
Upstream asserts that TopK selection is case-level routing over eight normalised inputs — `outer`,
`D`, `inner`, `rows`, `k`, `dtype`, `UB`, `coreNum` — and explicitly not a choice by dtype. Upstream
asserts two priority orders, each taking the first template whose gate the case satisfies, and states
that neither may be permuted. The first-level order: fixed small-axis (tilingKey 900001), then the
fallback candidate region — transpose-fallback (900003) before batched fallback L/S (900002) — then
the common tiler. The common tiler's internal order: non-last mode 8, small-axis MergeSort,
single-block radix, fp32 merge, single-core radix, optimised multi-core radix, general multi-core
radix, SortAndTopK. Upstream asserts that `modeType 1/2/4/5/6/7/8` is a host-kernel contract and that
the inter-core / intra-core and radix mode orderings must not be exchanged. Upstream asserts a shape
normalisation that all gates must use: `outer = product(shape[:dim])`, `D = shape[dim]`,
`inner = product(shape[dim+1:])`, `rows = outer * inner`, `nonLast = (dim + 1 < rank)`, and that no
gate may be re-derived from the original rank. Not established here.

## 2 · The wrong branch this removes
The natural design is one algorithm per dtype, and upstream's first sentence forbids it:
`不能只按 dtype 选择算法`. A dtype-keyed tiler gets the fp16 small-axis case (D ∈ {7, 17}, k == D)
routed to a general radix path and loses the fixed compare-exchange network entirely; upstream flags
that exact miss — `例如 D=17 的整轴排序不应因 non-last 再进入通用路径`.

The order matters in a way an agent will not infer. Both `fixed small-axis` and `fallback candidate`
can match the same case, and only the stated order gives the small-axis network its chance.
Similarly, `transpose-fallback` sits *inside* the fallback region and must be tried before the
batched L/S branch, so an agent that treats them as siblings and picks by shape gets the S branch on
cases where three extra transposes would have paid for themselves.

The normalisation rule removes a third, quieter branch. `nonLast` is a rank-position property and
`inner` is a product; when the trailing dimensions are all 1 a case can satisfy `nonLast == true` and
`inner == 1` simultaneously, and upstream states that the first-level candidate test uses `nonLast`
while the fallback's L/S layout choice uses `inner` — `两个判据不能合并`. An agent that merges them
picks the wrong layout on exactly the degenerate shapes that look equivalent.

Fourth: the arithmetic-safety rule. Products, byte counts, workspace offsets and the ratio tests
`4*k <= D` and `3*k <= D` are to be evaluated in 128-bit intermediates with a range check before
narrowing. An overflow there is a workspace offset, i.e. a wrong-memory bug rather than a slow one.

## 3 · Ground / Source
The normalisation, `sort/topk.md:27-43`:

```
先归一化负 `dim`，再计算：

outer = product(shape[:dim])
D     = shape[dim]
inner = product(shape[dim + 1:])
rows  = outer * inner
nonLast = (dim + 1 < rank)   # host 一级路由按 dim 的 rank 位置判断

校验 rank、shape、`1 <= k <= D`、dtype 和乘法溢出。shape 乘积、workspace 字节数以及
`4*k <= D`、`3*k <= D` 一类比例判断使用 128 位中间值。后续所有门控都使用归一化后的
`outer / D / inner / rows / k / dtype / coreNum / ubSize`，不能从原 rank 特判推导。注意尾部维度全为
1 时可能同时满足 `nonLast == true` 和 `inner == 1`；一级 special/fallback 候选仍看 `nonLast`，fallback
内部 L/S 布局选择看 `inner`，两个判据不能合并。
```

The first-level order, `:47-57`:

```
## 3. Step 1：一级路由，顺序不可交换

按下列顺序选择第一个命中的路径：

1. fixed small-axis (tilingKey 900001)
2. fallback candidate
   2.1 transpose-fallback (tilingKey 900003)
   2.2 batched fallback L/S (tilingKey 900002)
3. common tiler
```

The fixed small-axis gate, `:59-71`:

```
以下条件必须全部满足：

nonLast
k == D
D in {7, 17}
dtype in {fp16, bf16}

`largest` 和 `smallest` 都由同一模板在运行时支持。该路径必须先于 fallback；例如 D=17 的整轴
排序不应因 non-last 再进入通用路径。
```

The transpose-fallback gate and its workspace gate, `:87-109`:

```
仅在已经是 fallback candidate 后，且以下条件全部满足时尝试：

outer == 1
nonLast
dtype in {int32, fp32}
D > 2048
inner >= coreNum * 32
3*k <= D

递归计算 `[inner, D]` 尾轴 TopK 的 tiling，然后再执行 workspace 门禁：

- 内部 tiling 成功，且不得再次返回 900003；
- `inputBytes = D * inner * 4`；values 和 int64 indices 中间区按 512B 对齐；
- `innerWorkspaceOffset <= 2 * inputBytes`；
- `innerWorkspaceOffset + innerWorkspaceBytes` 不溢出 `int64`。

通过后执行 `transpose input -> 尾轴 TopK -> transpose values -> transpose indices`。任一门禁失败
必须回到 900002 S 分支，不得报错或继续放宽 workspace。该路径的本质是让足够大的
`[D, inner]` 用三次额外搬运换取连续行 TopK；"non-last"本身不是 transpose 的充分条件。
```

The common tiler's internal order, `:236-253`:

```
一级未命中时，保持下列首个可行模板顺序：

| 顺序 | 模板 | 条件摘要 |
|---:|---|---|
| 1 | non-last mode 8 | non-last 且 D<=2048；UB 内重排连续行，浮点优先 merge，其余 radix |
| 2 | 小轴 MergeSort | 尾轴、D<=1024、dtype 为 fp16/fp32/bf16；bf16 以 fp32 计算 |
| 3 | single-block radix | 完整行和 API tmp 同时放入 UB |
| 4 | fp32 merge | `0.25 <= k/D < 0.50`；先 inter-core，再 intra-core |
| 5 | single-core radix | `rows >= coreNum` 且存在合法 tile |
| 6 | optimized multi-core radix | `tile < D` 且 `k * ceil(D/tile) <= tile` |
| 7 | general multi-core radix | D<10,000,000 且存在合法 radix tile |
| 8 | SortAndTopK | 超大 D 或前述 tile 均失败；全轴多核 radix sort 后复制前 k |

fp32 inter-core merge 还要求 `splitCoreNum=ceil(D/2048)>1` 且
`rows*splitCoreNum<=coreNum`。否则在 rows 足够、block 数 2 到 256 且 UB 可容纳时尝试 intra-core。
不要交换 inter/intra 或 radix 各模式的判断顺序；modeType 1/2/4/5/6/7/8 是 host-kernel 契约。
```

Note that `modeType` skips 3: the contract lists `1/2/4/5/6/7/8` for eight templates, so the
`modeType` numbering and the priority numbering are different sequences. The Host-tiling spec's own
table, `topk_host_tiling.md:185-189`, carries both columns and shows nine priority rows against
`modeType` values 7, 1, 4, 2, 5 for rows 5–9 — i.e. the priority order and the `modeType` values are
independent, and the two documents' row counts differ (eight in `topk.md`, nine in
`topk_host_tiling.md`, which splits fp32 merge into inter-core and intra-core rows). Registered as
C-950tiling-019: the same routing table is stated with eight rows in one file and nine in the other.

The reproduction principle that carries both orders, `sort/index.md:29-30`, is quoted in 0142 §3.
The four-layer completeness requirement, `sort/topk.md:12-19`, states that routing, tiling, kernel
and launch must all be migrated together and that
`不要只复制当前 kernel 后重写一个"等价"的简化 tiler；现有性能主要来自选对模板和参数`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Order-is-a-performance-order test. Construct cases that satisfy more than one gate, one per
contested pair: (a) `D = 17`, `k = 17`, fp16, non-last — satisfies both fixed small-axis and the
fallback candidate region; (b) `outer = 1`, non-last, fp32, `D = 4096`, `inner = coreNum * 64`,
`k = 512` — satisfies transpose-fallback and batched L/S; (c) non-last, `D = 1024`, fp32,
`0.25 ≤ k/D < 0.5` — satisfies common rows 1, 3 and 4. For each case force every satisfying template
in turn: one compiler pin, md5 per binary, host echo of tilingKey, `modeType` and the derived tile
fields. Compare values *and* indices elementwise against a CPU reference for every arm — upstream's
pair invariant makes an index-only failure the likely one. Record `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Normalisation arm. Construct a shape whose trailing dimensions are all 1 so that
`nonLast == true` and `inner == 1` hold together, and run it through the router; record which
first-level candidate and which L/S branch are chosen, and whether merging the two predicates (a
deliberately wrong variant) changes the result. This arm needs the host only and is the cheapest
falsification of the `两个判据不能合并` claim.

Overflow arm, host only: feed shapes whose products exceed 64-bit when multiplied naively and record
whether the 128-bit intermediate path holds. A failure here is a memory-safety finding, not a
performance one.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` or
`ubSize` are literals (queried per 0141 — `inner >= coreNum * 32` and `rows*splitCoreNum<=coreNum`
both depend on the first); that a forced template was used (tilingKey echo required); that value
correctness implies index correctness.

## 5 · Checker — acceptance declared before the run
Verdict variable `order_is_optimal(case)`: true iff the first template in upstream's order among
those satisfying the case has the lowest median `aiv_time`, by more than the variance floor.
Declared acceptance: the fixed orders are performance orders iff `order_is_optimal` holds on all
three contested cases. The OVERTURN fires iff a later template wins on any case by more than the
variance floor. Verdict variable `predicates_separable`: true iff merging `nonLast` and `inner == 1`
changes the chosen branch on the degenerate shape — which is what upstream's prohibition implies.
`overflow_safe` is a boolean from the host-only arm.

The exit code is not the verdict: a TopK returning correct values with wrong indices exits 0, and
this family's pair invariant is about exactly that. The instrument is an elementwise comparison of
both outputs, and the checker fails red if only one was compared. Second guard: tilingKey and
`modeType` identity — every arm must echo the template it was forced to, and where the host overrode
the force the arm is excluded and reported rather than counted, since a collapsed pair of arms would
make `order_is_optimal` true by construction.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no case was routed, built or timed. The entry does not establish that either
priority order is optimal, does not establish any gate threshold (those are 0142's subject and
upstream fences them as policy), and does not establish the `modeType` contract — it records that
upstream calls it one. It does not resolve the eight-row versus nine-row disagreement between the two
documents (C-950tiling-019). It does not establish that the 128-bit intermediate rule is necessary,
only that upstream requires it. It says nothing about the kernel-side templates the tilingKeys
dispatch to, which are outside this reference set. `Ascend 950 / DAV_3510` names an architecture, not
a board, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT because that is where our run
would happen. Nothing here is established for any 910-family board.
