```
ID:        0122-the-five-reduction-templates-are-selected-by-r-against-ub-capacity-not-by-operator-name
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:92-139 —
           "r_small_threshold = dtype 相关的小 R 阈值（FP32 约 16，FP16 约 32）" ·
           "├─ R ≤ r_small_threshold 且 UB 预算通过 → 【AR-SmallR】" ·
           "├─ R 可整段载入 UB（FullLoad 预算 ≥ 1） → 【AR-FullLoad】" ·
           "└─ R 超出 UB 容量 → 【AR-Recompute】" ; "R ≤ 8: 直接多行累加 / R > 8: 启用二分累加"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured reduction case on a named 950 board where AR-Recompute beats AR-FullLoad at
           an R that fits UB, or AR-FullLoad beats AR-SmallR below the small-R threshold — the
           ladder would then not be monotone and template choice could not be read off R alone.
```

# 0122 · The five reduction templates are selected by R against UB capacity, not by operator name

## 1 · Claim
Upstream asserts a five-template decision tree driven by one comparison — the reduction length R
against what UB can hold — after the family split on `A0` (0121). In the AR family: `R ≤
r_small_threshold` with the UB budget passing selects AR-SmallR, which transposes to an `(R, A1)`
layout and tiles along A1; R that fits UB entirely selects AR-FullLoad, R resident in UB with A1
split across cores; R exceeding UB selects AR-Recompute, R chunked with inter-chunk merging inside
UB. In the ARA family there are two rungs, not three: R that fits selects ARA-FullLoad, tiling
along A0 with each tile's R rows resident; R that does not selects ARA-Recompute, tiling along A0
with R chunked at a default granularity of 128 rows and cross-chunk merging through a cache buffer.
Upstream states the small-R threshold as dtype-dependent — `FP32 约 16，FP16 约 32` in the tree
and `r_small_threshold = r_tile_unit × 2` with `r_tile_unit = 8 (FP32) / 16 (FP16)` in the budget
section — and states a second, independent threshold inside ARA-FullLoad: `R ≤ 8` accumulates rows
directly, `R > 8` switches to a binary (tree) add. Not established here.

## 2 · The wrong branch this removes
An agent asked to tile a Softmax looks for a Softmax template. Upstream's structure says there
isn't one: `softmax/experience.md:44` states `Softmax 使用通用决策树，无额外分支`, and the operator
enters only through the buffer count in the budget denominator (0130). Without this entry the agent
either invents per-operator templates — losing the shared reasoning and, more importantly, losing
the R-versus-UB comparison that actually decides the plan — or picks FullLoad because it sounds
best, which is a launch failure or a silent fallback whenever R does not fit.

The two thresholds remove subtler wrong branches. The small-R threshold exists because at very
small R the natural layout wastes vector lanes: transposing to `(R, A1)` makes A1 the vectorised
direction. An agent that treats SmallR as an optimisation to skip runs a 16-element reduction
through a template designed for thousands. And the `R ≤ 8` / `R > 8` split inside ARA-FullLoad is
not about capacity at all — it is about whether a tree reduction pays for its own setup — so an
agent that reads every threshold in this family as a UB-capacity question will apply the wrong
model to it.

## 3 · Ground / Source
`reduction/fallback/tiling-flow.md:92-129`, the decision tree in full:

```
输入: (A1, R, A0), dtype, ub_size, core_num

┌─ A0 == 1 ──→ AR 族（最内维归约，等价 2D [A1, R]）
│
│   r_align = R 按 32B 对齐后的长度
│   r_small_threshold = dtype 相关的小 R 阈值（FP32 约 16，FP16 约 32）
│
│   ├─ R ≤ r_small_threshold 且 UB 预算通过
│   │     → 【AR-SmallR】
│   │       转置为 (R, A1) 布局，沿 A1 方向切 tile
│   │       适用: R 极小、A1 较大，转置后可向量化处理
│   │
│   ├─ R 可整段载入 UB（FullLoad 预算 ≥ 1）
│   │     → 【AR-FullLoad】
│   │       R 全量驻留 UB，A1 方向多核切分
│   │       适用: 标准归约、Softmax 等 R 中等的场景
│   │
│   └─ R 超出 UB 容量
│         → 【AR-Recompute】
│           R 方向分块，每块独立归约后在 UB 内合并
│           适用: 大 R 归约；Softmax 等需分轮重读原数据
│
└─ A0 > 1 ──→ ARA 族（非尾轴归约，等价 3D [A1, R, A0]）
    │
    │   a0_tile_unit = 64(FP32) / 128(FP16)  // 向量寄存器宽度对应的元素数
    │
    ├─ R 可整段载入 UB（FullLoad 预算 > 0）
    │     → 【ARA-FullLoad】
    │       沿 A0 切 tile，每个 tile 内 R 行全量驻留
    │       R ≤ 8: 直接多行累加
    │       R > 8: 启用二分累加（BinaryAdd）做行归约
    │
    └─ R 超出 UB 容量
          → 【ARA-Recompute】
            沿 A0 切 tile，R 方向按固定粒度（默认 128 行）分块循环
            跨块用 cache buffer 做二分累加合并
```

The summary table, `:133-139`:

```
| 模板 | 维度 | R 条件 | 关键策略 |
|------|------|--------|---------|
| AR-SmallR | A0=1 | R 极小 | 转置布局，沿 A1 切 tile |
| AR-FullLoad | A0=1 | R 可全载 | R 驻留 UB，A1 切分 |
| AR-Recompute | A0=1 | R 过大 | R 分块 + 块间合并 |
| ARA-FullLoad | A0>1 | R 可全载 | A0 切 tile，R 全载 |
| ARA-Recompute | A0>1 | R 过大 | A0 切 tile，R 分块循环 |
```

Two statements of the small-R threshold, in the same file. The tree at `:98` says
`FP32 约 16，FP16 约 32`; the budget section at `:217-218` says
`r_small_threshold = r_tile_unit × 2` with `r_tile_unit = 8 (FP32) / 16 (FP16)`, i.e. 16 and 32.
They agree, and the second is the derivation of the first — noted because "约" (approximately) in
the tree would otherwise read as an unspecified value.

The multi-core split axis per template, `:314-322`:

```
| 模板 | 切分轴 | 分配方式 |
|------|--------|---------|
| AR-SmallR | A1（转置后的"列"） | `tiles_per_core = ceil(a1_outer / core_num)` |
| AR-FullLoad | A1 | `rows_per_core = ceil(A1 / core_num)` |
| AR-Recompute | A1 | 同 AR-FullLoad |
| ARA-FullLoad / ARA-Recompute | A1 × A0 tile | `total_tiles = A1 × a0_outer`，均分到 core_num |
| **group / BlockSplitR** | **R（跨核切 R）** | 2D 网格 `[aLoopCntTotal, rGroupCnt]` |

`used_core_num = ceil(total_work / per_core_work)`，保证 ≥ 1。
```

`used_core_num ≥ 1` is guaranteed by construction, so a self-check that asserts it — and
`softmax/experience.md:194` and `euclidean_norm/experience.md:175` both do — is a check that cannot
fail. Recorded, not adjudicated; the same family also ships checks that *can* fail
(`euclidean_norm/experience.md:169-174` asserts specific gate values and a specific
`workspaceBytes` formula), which is the counter-example worth imitating.

Softmax's own mapping onto the same tree, `softmax/experience.md:42-44`, confirms there is no
operator-specific branch: `Softmax 使用通用决策树，无额外分支。以下说明各模板下 Softmax 的具体行为。`

Note that the tree names five templates but the family has seven paths in total: the two
interleaved templates (0125-0128) sit before this tree, and BlockSplitR (0124) sits after it.
`tiling-fields.md:3` calls the five a `TilingData 字段并集`, so an agent that treats the five as
exhaustive will miss both.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Threshold-crossing sweeps, three of them, each isolating one boundary.
(a) SmallR boundary: fix `A1 = 8192`, `A0 = 1`, dtype FP32, sweep
`R ∈ {4, 8, 12, 16, 20, 24, 32, 48}` and build both AR-SmallR and AR-FullLoad at every R where
both are legal. Repeat at FP16 with the boundary at 32.
(b) FullLoad/Recompute boundary: fix `A1 = 512`, `A0 = 1`, sweep R upward through the value at
which the FullLoad budget (`rows_per_ub ≥ 1`, `tiling-flow.md:234-243`) first fails against the
*queried* UB capacity, building both templates on either side while both remain legal.
(c) ARA `R ≤ 8` boundary: fix `A1 = 64`, `A0 = 256`, sweep `R ∈ {4, 6, 8, 10, 16, 32}` and build
ARA-FullLoad with the direct accumulation and with BinaryAdd forced, at each R.

For every point: one compiler pin, md5 the binary, host echo of `(A1, R, A0)`, `template`,
`used_core_num` and the derived tile fields, output checked against an fp64 reference within a
tolerance declared in advance — note that BinaryAdd changes float accumulation order, so the two
arms of sweep (c) are not expected to be bit-identical and the tolerance must accommodate that.
`aiv_time` under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ub_size` is
248 KB or 192 KB — it is queried, and this family states both (0131); that `core_num` is 64 or 72,
same reason; that a template the host refuses is a template that would have lost — a refusal is
recorded as a refusal.

## 5 · Checker — acceptance declared before the run
Verdict variables `smallr_cross`, `fullload_cross` and `binadd_cross`: for each sweep, the value of
R at which the two arms' median `aiv_time` curves intersect. Declared before the run: the ladder is
supported iff `smallr_cross ∈ [12, 24]` at FP32 (upstream says 16) and `[24, 48]` at FP16 (upstream
says 32); iff `fullload_cross` lies within one sweep step of the R at which the budget formula
first fails; and iff `binadd_cross ∈ [6, 12]` (upstream says 8). The OVERTURN fires iff any arm is
*non-monotone* — AR-Recompute beating AR-FullLoad at an R that fits, or AR-FullLoad beating
AR-SmallR below the threshold — because template choice could then not be read off R at all.

The exit code is not the verdict. The blind mode: the host may refuse to emit a template outside
its own gate, so the "both arms" requirement silently degrades to one arm and the curves never
cross, which would read as a clean confirmation. The checker therefore requires two distinct md5s
and two distinct echoed `template` values at every R in the overlap region, and goes red where it
has only one — a boundary with no overlap region is reported as untestable, not as confirmed. It
also fails red if the queried `ub_size` differs from the value used to compute the predicted
`fullload_cross`, since the prediction would then be for a different machine.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish any of the three thresholds, does not establish
that five templates are enough (they are not — two interleaved templates and BlockSplitR are
outside this tree), and does not establish that the AR/ARA rungs are ordered as upstream implies.
It does not establish `ub_size` or `core_num` for any board, and the FullLoad/Recompute boundary is
a function of both. It says nothing about which template is best for a case that is legal under
two of them — upstream's tree is first-match, and whether first-match is best is exactly what §4
would measure. No board is named in `tiling-flow.md`, so BOARD is `family-claimed(unverified)` and
the chip is unstated there; §4 names 950PR/950DT because that is where our run would happen.
Nothing here is established for any 910-family board.
