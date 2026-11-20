```
ID:        0157-scatter-tiling-decides-parallel-partition-and-conflict-resolution-not-a-ub-tile
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     950PR
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scatter/fallback/index.md:5-7 and
           scatter/fallback/tiling-flow.md:5-9 — "Scatter 的 Tiling 不是"怎么把数据切进 UB"——写地址
           由运行期 `indices` 决定，UB tile 化不成立。它切的是**并行划分方式** ... 与**冲突消解方式**
           ... 输出的"tiling data"主要是 **block 数 + 每 block 线程数 + workspace 尺寸**" ·
           "阈值与吞吐数字均为 **Ascend950PR 实测**（该实现评测 72.46 分 / 20-20 通过 / Scatter 算子榜第 1）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured scatter on a named 950 board where a UB-tiled formulation — staging updates in
           UB and writing them out in tiles — beats every one of the six paths on the same case; the
           "UB tile 化不成立" premise would then be false.
```

# 0157 · Scatter tiling decides parallel partition and conflict resolution, not a UB tile

## 1 · Claim
Upstream asserts that scatter tiling is categorically unlike every other family in this reference
set: because the write address is determined by runtime `indices` values, UB tiling does not apply,
and what the tiling actually decides is the parallel partition (does a thread own one fiber, or one
update element) and the conflict-resolution method (atomic-free, hardware atomic, or key
arbitration). Upstream asserts that the emitted tiling data is consequently block count, threads per
block and workspace size rather than `ubFactor` or `tileSize`. Upstream asserts six paths and states
that choosing wrongly is an order-of-magnitude matter, citing a measured 12602 µs against 3767 µs on
one case. Upstream asserts the measurement identity for this family's thresholds and throughput
figures: `Ascend950PR 实测`, with an implementation scoring 72.46, passing 20 of 20, and ranked first
on the Scatter operator leaderboard, with inferential conclusions explicitly marked as such. Not
established here — these are upstream's measurements on upstream's board, not ours.

## 2 · The wrong branch this removes
Every other family in this domain answers "how much fits in UB". An agent that has read three of them
arrives at scatter and looks for the UB budget. There isn't one, and the search is not merely
fruitless: the plausible answer — stage the updates in UB, tile them, write out — is wrong for a
reason that has nothing to do with capacity. The write addresses within one staged tile are scattered
across the output, so tiling the *input* buys no locality on the *output*, which is where the cost is.

The second wrong branch follows from the first. Having found no UB knob, an agent reaches for the
knob it has: block count. Upstream's answer is that the tunable is threads per block, that it
interacts with the partition choice, and that block count is always `min(coreNum, ...)` — `所有路径的
block 数都 min(coreNum, ...)`, with grid-stride loops covering the remainder, and explicitly no
attempt to over-subscribe blocks and let the scheduler queue them.

Third, and this is why the entry carries a board token: this family's numbers are real. `Ascend950PR
实测` with a score, a pass count and a leaderboard position is more measurement identity than any
other family in this domain offers, and its thresholds were calibrated rather than chosen. That
raises rather than lowers the obligation to record what the numbers do and do not cover — see §7.

## 3 · Ground / Source
The framing, `scatter/fallback/index.md:3-7`:

```
> Scatter 族算子的六路径 Tiling 算法。所有按轴 `dim` + 单值 `indices` 的 Scatter 算子共享同一套路径语言。
>
> **与其他族的根本差别**：Scatter 的 Tiling 不是"怎么把数据切进 UB"——写地址由运行期 `indices` 决定，UB tile 化不成立。
> 它切的是**并行划分方式**（一个线程认领一条纤维，还是认领一个更新元素）与**冲突消解方式**（免原子 / 硬件原子 / 键仲裁），
> 输出的"tiling data"主要是 **block 数 + 每 block 线程数 + workspace 尺寸**，而不是 ubFactor / tileSize。
```

restated in the flow document, `scatter/fallback/tiling-flow.md:5-9`:

```
> **重要**：本族的 Tiling 不切 UB。写地址由运行期 `indices` 决定，UB tile 化不成立；
> 真正要决定的是 **① 并行划分方式**（线程 = 一条纤维 还是 一个更新元素）与 **② 冲突消解方式**（免原子 / 硬件原子 / 键仲裁）。
> 选错是数量级差距——实测同一用例 **12602us ↔ 3767us**（`multiply` 被错误地排除在元素级原子路径外）。
>
> 阈值与吞吐数字均为 **Ascend950PR 实测**（该实现评测 72.46 分 / 20-20 通过 / Scatter 算子榜第 1），推断性结论已显式标注。
```

The six paths, `scatter/fallback/index.md:18-27`, in full:

```
`starved = numFibers < coreNum × 1024`（纤维路径铺不满核）

| 路径 | 触发条件 | 核心策略 | 散射趟数 | 原子 | workspace |
|------|---------|---------|---------|------|-----------|
| ① 纤维独占 | `!starved` | 线程认领一条纤维，输出集互不相交 | 1 | **无** | 无 |
| ② 打包键单趟 | `none` + `esize==2` + `sIdx+1 ≤ 65535` | `key=(j+1)<<16\|bits16(v)` 单次 `atomic_max` | 1 | 32 位 | `int32[numel]` |
| ③ 两趟胜者 | `none` + 键装不进 32 位 | 趟1 裁决 `atomic_max(win,i+1)`，趟2 比中才写 | 2(+1) | 32 位 | `int32[numel]` |
| ④ 直接原子 | `add`/`amin`/`amax`/`multiply` | 顺序无关，冲突交给硬件原子（乘用 CAS 循环） | 1 | 32 位 | 半精度累加类需 `float[numel]` |
| ⑤ warp 段末 | `none` + `esize==4` + 键 ≤31 位 + `numFibers ≥ 1024` | warp 内 15 级 bitonic，同 index 段末者写 | 1 | **无** | **无** |
| ⑥ 通用逐维 stride | 三张量**非 dim 维范围不等** | 按每维独立 stride 还原坐标，仲裁同 ③/④ | 同上 | 同上 | 同上 |
```

The axis-collapse formulas, `tiling-flow.md:30-47`:

```
d      = dim < 0 ? dim + rank : dim
inner  = prod(indices.shape[d+1 : rank])
outer  = prod(indices.shape[0 : d])
numFibers = outer * inner
sIdx   = indices.shape[d];  sUpd = updates.shape[d];  sVar = data.shape[d]
epTotal   = outer * sIdx * inner          // == indices.numel()
numelData = data.numel()
esize     = sizeof(dtype)

extentsMatch = ∀i:  indices.size(i) == updates.size(i)
                 && (i == d || indices.size(i) == data.size(i))
```

> **合轴只用 `indices` 的 shape**，不是 `data` 的。torch 语义只要求 `index.size(k) ≤ self.size(k)`，
> 非 dim 维 `indices`/`updates` 可以比 `data` 小；用 `data.shape` 合轴会算出错误的 `inner`。

The block-count rule, `:269-271`:

```
### 4.1 block 数上限一律是 `coreNum`

所有路径的 block 数都 `min(coreNum, ...)`，靠 grid-stride 循环覆盖余量。不做"超发 block 让调度器排队"的尝试。
```

The scope fence at the family's entrance, `scatter/index.md:5`, which is a routing restriction and
not a preference:

```
> **不含** ScatterNd / ScatterNdUpdate / ScatterUpdate / ScatterList —— 这些是多维联合索引或整行替换，寻址与一致性模型不同，本族的核心不变量（冲突只发生在纤维内）对它们不成立，不要套本目录的决策树。
```

And the family's own comparison against gather, `scatter/index.md:35-41`, which states the asymmetry
this entry's claim rests on:

```
| | Gather（读侧聚集） | Scatter（写侧散射） |
|---|---|---|
| 不规则在哪 | 读 | 写 |
| 能否变规则 | **能**：物理 / kernel 内 Transpose、full-load 把不规则读变连续 | **不能**：写地址由 index 值决定 |
| Tiling 决策什么 | 要不要转、转得下吗、转了划算吗（能力门控 + UB 容量 + 搬运成本） | **并行划分**（纤维 vs 元素）与**冲突消解**（免原子 / 原子 / 仲裁），以及由此决定的线程数、block 数、workspace |
```

Note that the family does have one genuine UB tiling, and upstream keeps it separate: the SIMD clone
and cast passes at `:248-263` use a conventional two-level split with
`tileSize = floor(ubSize / PIPELINE_DEPTH(2) / BUFFER_NUM(2) / 512) * 512`. So "does not tile UB"
applies to the scatter passes, not to the sequential passes around them, and upstream is precise
about which is which.

`BOARD: 950PR` here is the board upstream's evidence names. That is the only entry in this domain
with a specific board token, and it is warranted only because upstream writes `Ascend950PR` rather
than `Ascend 950` or `DAV_3510`.

## 4 · Procedure
Proposed, runnable later on Ascend950PR — the board upstream names, so a re-measurement is
comparable; a run on 950DT is a different claim and is recorded as such. Never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only if HBM-used and AICore-utilisation are at their idle floor in all three samples; export
`ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case if the die moved. Variance
floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — the premise, a poison arm. Build a UB-tiled scatter for one case: stage `updates` and
`indices` in UB tiles, compute destination addresses, and write out per tile. Compare against the
path upstream's tree selects for that case. One compiler pin; md5 each; host echo of the collapsed
sizes, the selected path, `blocks`, `threads` and any workspace request. Compare output elementwise
against a CPU reference implementing the declared last-write-wins semantics. Record `aiv_time`, GM
bytes written and cacheline-level write efficiency under `msprof --aic-metrics=PipeUtilization`,
≥10 iterations, first 5 dropped. This arm is retained in the report whether or not it bites — if a
UB-tiled formulation wins, the family's founding premise is wrong.

Arm 2 — the collapse rule. Construct a case where `indices` is smaller than `data` on a non-`dim`
dimension, compute `inner` from `indices.shape` and from `data.shape`, and run both plans. The
`data.shape` variant is expected to produce wrong output; the fraction of wrong elements and the
first wrong index are recorded.

Arm 3 — block over-subscription. On one case, sweep `blocks` from `min(coreNum, need)` up to
4 × `coreNum` and record `aiv_time`, so upstream's `不做超发` decision is measured rather than
inherited.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` is a
literal (queried, 0141 — and `starved` depends on it); that a path that builds was the path that ran
(host echo required); that a scatter producing plausible values is correct — the elementwise
comparison with duplicate indices is what tests last-write-wins.

## 5 · Checker — acceptance declared before the run
Verdict variable `ub_tiled_wins`: true iff arm 1's UB-tiled build is correct and faster than the
selected path by more than the variance floor. Declared acceptance: the premise holds iff
`ub_tiled_wins` is false. The OVERTURN fires iff it is true. Verdict `collapse_source_matters`: true
iff the `data.shape` collapse produces wrong output. Verdict `oversubscribe_gain` from arm 3,
reported with the variance floor; upstream predicts none.

The exit code is not the verdict: a scatter that picks the wrong winner among duplicate indices exits
0 with plausible values, and upstream states that the acceptance metric is a maximum relative error
that one wrong winner fails outright (`:59`). The instrument is therefore an elementwise comparison
on an input with deliberately duplicated indices, and the checker fails red if the input contained no
duplicates — a duplicate-free test cannot distinguish a correct arbitration from none, which is
exactly the reads-only-what-it-expects species. Second guard: path identity via host echo, since a
forced UB-tiled arm the host replaced would make `ub_tiled_wins` false by construction.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 12602 µs / 3767 µs pair,
the 72.46 score, the 20-of-20 pass and the leaderboard position are upstream's readouts on
Ascend950PR; this book has reproduced none of them.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. `BOARD: 950PR` records the board upstream's evidence names, not a board
this book has touched, and the stratum — not the board field — says who measured. The entry does not
establish that UB tiling is impossible for scatter; upstream asserts it and §4 arm 1 is what would
test it. It does not establish the six paths' individual gates (0158, 0159), the thread-count rules
(0160), the measured laws (0161) or the `multiply` case (0162). It does not establish that the 72.46
score, the 20-of-20 pass or the leaderboard rank transfer to any other case set — upstream names no
case set, no date and no harness version for them. It does not cover ScatterNd, ScatterNdUpdate,
ScatterUpdate or ScatterList, which upstream explicitly excludes because the fiber invariant does not
hold for them. Nothing here is established for 950DT — upstream names 950PR and Art. 2 forbids the
transfer — and nothing is established for any 910-family board.
