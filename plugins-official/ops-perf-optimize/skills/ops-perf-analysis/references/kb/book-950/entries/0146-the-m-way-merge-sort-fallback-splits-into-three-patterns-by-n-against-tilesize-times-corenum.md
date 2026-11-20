```
ID:        0146-the-m-way-merge-sort-fallback-splits-into-three-patterns-by-n-against-tilesize-times-corenum
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/sort/fallback/tiling-flow.md:9-30,53-95 and
           sort/fallback/script/sort_tiling.py:31-33,113-121 —
           "sortBytesPerElem = sizeof(dtype) + sizeof(float) + sizeof(uint32) + PROPOSAL_SIZE +
           concatTmpPerElem + sortTmpPerElem; tileSize = min(ubSize / sortBytesPerElem, 4096) 对齐到32"
           · "N ≤ tileSize → Pattern A / N ≤ tileSize × coreNum → Pattern B / else Pattern C" ·
           "M_WAY = 4" · "PROPOSAL_SIZE = 8" · "TOPK_SORT_NUM = 32"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sort on a named 950 board where Pattern C beats Pattern B at an N below
           `tileSize × coreNum`, or Pattern B beats Pattern A below `tileSize` — the pattern ladder
           would then not be ordered by N and the boundaries would not be boundaries.
```

# 0146 · The M-way merge-sort fallback splits into three patterns by N against tileSize × coreNum

## 1 · Claim
Upstream asserts a three-pattern M-way merge sort as the Sort-family fallback, selected by one
comparison. The tile size comes first:
`sortBytesPerElem = sizeof(dtype) + sizeof(float) + sizeof(uint32) + PROPOSAL_SIZE +
concatTmpPerElem + sortTmpPerElem` and `tileSize = min(ubSize / sortBytesPerElem, 4096)` aligned to
32. Then `N ≤ tileSize` selects Pattern A, a single-core sort completed by one Sort call;
`N ≤ tileSize × coreNum` selects Pattern B, multi-core with one level of merging; and larger N
selects Pattern C, multi-core with two levels. Upstream asserts Pattern C's four phases: all cores
sort their tiles into workspace; all cores independently merge their own tiles down to one sorted run
with no synchronisation, looping `while listNum != 1`; the core count then decreases across rounds of
cross-core merging with a `SyncAll` each round, looping `while listNum > M`; and core 0 performs the
final ≤M-way merge, extracts values from indices and writes GM. Upstream asserts the merge-round
counts `ceil(log_M(S_c))` and `ceil(log_M(coreNum)) - 1`, a total `SyncAll` count of
`ceil(log_M(coreNum)) + 1`, a per-phase UB cost of ~34 B/element for the sort phase, 64 B for merge
and 104 B (fp16) for output, a double-buffered workspace of `E_c × 8B × 2` per core aligned to 32 B,
and a Top-K truncation optimisation that engages when `currentElements × M ≥ K`. Not established here.

## 2 · The wrong branch this removes
The pattern boundary is not the obvious one. An agent asked to sort `N` elements on `coreNum` cores
will split `N` by `coreNum` and merge; that is Pattern B, and it is wrong above
`tileSize × coreNum` because each core then holds more than one tile and needs its own intra-core
merge *before* any cross-core work. Skipping that produces a cross-core merge over `totalTiles` runs
instead of `coreNum` runs, so the `SyncAll` count goes from `ceil(log_M(coreNum)) + 1` to
`ceil(log_M(totalTiles)) + 1` — every extra round is a full-machine barrier. The phase-2 loop
condition (`while listNum != 1`, no synchronisation) versus phase 3's (`while listNum > M`, one
`SyncAll` per round) is the whole point: intra-core merging is free of barriers, so it is done to
completion first.

The truncation rule removes a second wrong branch: sorting all of `N` when only `K` is wanted.
Upstream's condition `currentElements × M ≥ K` with a `truncationFlag` persisted across phases 2 and
3, reading the full data on first trigger and truncated lengths thereafter, is the mechanism that
makes this a Top-K algorithm rather than a full sort with a slice at the end.

Third, `sortBytesPerElem`. Six terms, of which two — `concatTmpPerElem` and `sortTmpPerElem` — are
API scratch quantities the formula does not give values for. An agent that budgets only the visible
four (dtype + float + uint32 + proposal) underestimates and gets a `tileSize` that does not fit. The
script's own computation is explicit: `dsize + 4 + 4 + PROPOSAL_SIZE + 8 + 8` for fp16 and
`dsize + 4 + PROPOSAL_SIZE + 8 + 8` for fp32, i.e. the two scratch terms are 8 B each.

## 3 · Ground / Source
The decision tree, `sort/fallback/tiling-flow.md:9-30`:

```
给定: N, K, dtype, ubSize, coreNum

Step 1: 计算 tileSize
  sortBytesPerElem = sizeof(dtype) + sizeof(float) + sizeof(uint32)
                     + PROPOSAL_SIZE + concatTmpPerElem + sortTmpPerElem
  tileSize = min(ubSize / sortBytesPerElem, 4096)  对齐到32

Step 2: 比较 N 与 tileSize
  ├─ N ≤ tileSize
  │   → Pattern A: 单核排序
  │     直接 Sort API 完成
  │
  └─ N > tileSize
      └─ 比较 N 与 tileSize × coreNum
          ├─ N ≤ tileSize × coreNum
          │   → Pattern B: 多核一级归并
          │     每核≤1个tile, 无需核内多tile归并
          │
          └─ N > tileSize × coreNum
              → Pattern C: 多核两级归并
                每核>1个tile, 需两阶段归并
```

Pattern C's phases, `:37-51`:

```
Phase 1 — tile排序 (全核并行):
  各核将GM数据读入UB → Cast+ArithProgression+Concat → Sort → workspace[0]

Phase 2 — 核内多tile归并 (全核并行, 无同步):
  各核独立将S_c个有序tile通过M-way归并合并为1个有序数列
  循环条件: while listNum != 1

Phase 3 — 跨核归并 (递减核数, 每轮SyncAll):
  将coreNum路逐步归并至≤M路
  循环条件: while listNum > M

Phase 4 — 最终归并+输出 (仅Core 0):
  将≤M路归并为最终结果 → Extract分离value/index → GM
```

The tile split, merge rounds, UB budget, truncation and workspace, `:53-95`:

```
totalTiles      = CeilDiv(N, tileSize)
frontCoreTiles  = CeilDiv(totalTiles, coreNum)
usedCore        = CeilDiv(totalTiles, frontCoreTiles)
lastCoreTiles   = totalTiles - (usedCore-1) × frontCoreTiles
lastTileSize    = N - tileSize × (totalTiles-1)
elementsPerCore = frontCoreTiles × tileSize
```

```
| Phase | Buffer数 | bytes/elem | onceMaxElements |
|-------|:------:|-----------|----------------|
| Phase 1 (Sort) | 6 | ~34B (fp16) | = tileSize = 4096 |
| Phase 2/3 (Merge) | 2 | 64B | `(ubSize/64)/32×32` |
| Phase 4 (Output) | 5 | 104B (fp16) | `(ubSize/BPE)/32×32` |
```

```
Phase 2 归并轮次 = ceil(log_M(S_c))
Phase 3 归并轮次 = ceil(log_M(coreNum)) - 1  (最后一轮由Phase 4完成)
Phase 4          = 1轮 ≤M-way归并
总SyncAll次数 = ceil(log_M(coreNum)) + 1
```

```
当 `currentElements × M ≥ K` 时启用截断:
- 归并输出≥K时, 后续只处理前K个有效元素
- 截断标志 `truncationFlag` 跨Phase 2/3持久化
- 首次触发时读入完整数据, 下一轮开始读截断长度
```

```
wsPerCore = E_c × 8B × 2  (32B对齐, 双缓存)
workspace[0]: 写缓存
workspace[1]: 读缓存
每轮归并后 workSpaceFlag = 1 - workSpaceFlag (交替)
```

The script's constants and per-element formulas,
`sort/fallback/script/sort_tiling.py:31-33,101-121`:

```python
M_WAY = 4                       # M-way merge (MrgSort API constant)
PROPOSAL_SIZE = 8               # proposal format: 4B value + 4B index
TOPK_SORT_NUM = 32              # Sort API alignment granularity
```
```python
        return dsize + 4 + 4 + PROPOSAL_SIZE + 8 + 8
    return dsize + 4 + PROPOSAL_SIZE + 8 + 8
```
```python
    return 2 * M_WAY * PROPOSAL_SIZE + M_WAY * (4 + 4 + dsize)
```

Re-derived here rather than trusted. `sortBytesPerElem` at fp16: `2 + 4 + 4 + 8 + 8 + 8 = 34`,
matching the table's `~34B (fp16)`; at fp32 the script drops one 4-byte term giving
`4 + 4 + 8 + 8 + 8 = 32`, matching the script's own comment `~32B (fp32)`.
`merge_bytes_per_elem = 2 × M_WAY × PROPOSAL_SIZE = 2 × 4 × 8 = 64`, matching the table's 64 B.
`output_bytes_per_elem = 2 × 4 × 8 + 4 × (4 + 4 + dsize)`, which is `64 + 40 = 104` at fp16 and
`64 + 48 = 112` at fp32 — 104 matching the table's `104B (fp16)`.

This re-derivation corrects a claim in the 2026-08-24 deep-dive survey of this skill, which recorded
"sort merge bytes-per-element 64 B (.md) vs ~104-112 B (script)" as a contradiction. It is not one:
64 B is the *merge* phase cost and 104/112 B is the *output* phase cost, both stated in both artifacts
and both agreeing. The survey conflated two different quantities. Reported as a failed
re-verification rather than entered as a contradiction row.

One genuine disagreement is present. `sort/fallback/tiling-fields.md:36` gives
`merge_rounds_phase3 = ceil(log_M(coreNum)) - 1`, matching `tiling-flow.md:76`; the script computes
it twice, at `:226` as `ceil(log(max(core_num,2), M_WAY)) - 1` and at `:259` as
`ceil(log(max(total_tiles,2), M_WAY)) - 1` — `total_tiles`, not `core_num`. Since Pattern C exists
precisely when `total_tiles > coreNum`, the two script lines differ on every Pattern C case.
Registered as C-950tiling-020.

A second, smaller one: `sort/fallback/tiling-fields.md:73` lists `- [ ] tileSize = 4096?` as a
constraint check. `tileSize = min(ubSize / sortBytesPerElem, 4096)`, so at any plausible UB the min
selects 4096 and the check cannot fail — the same cannot-fail-checklist species this book records
elsewhere. `:76` in the same list (`GetCoreWsOffset(i) = i × E_c × 2 (直接乘法)`) and `:77`
(`truncationFlag在归并执行后设置`) *can* fail, so the list is not uniformly vacuous.

`M_WAY = 4` is annotated as an `MrgSort API constant` — the only constant in this family with a
stated origin outside the file. `TOPK_SORT_NUM = 32` is annotated as the Sort API alignment
granularity, which is the same 32 B that appears family-wide as the memory block granularity;
whether the two are the same quantity is not stated.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Pattern-boundary sweep. Query `ubSize` and `coreNum` (0141), compute `tileSize` from the six-term
formula, and sweep `N` across both boundaries: {0.5, 0.9, 1.0, 1.1, 2} × `tileSize` and
{0.9, 1.0, 1.1, 4} × `tileSize × coreNum`, at fp16 and fp32. At every N build every legal pattern —
A, B and C where each applies — with one compiler pin, md5 per binary, host echo of `pattern`,
`tile_size`, `total_tiles`, `core_num`, `tiles_per_core`, `merge_rounds_phase2/3` and
`workspace_bytes`. Compare values *and* indices elementwise against a CPU reference, since Phase 4
extracts them separately and a mismatched pair is the likely failure. Record `aiv_time` and the
observed `SyncAll` count under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5
dropped, per case.

Merge-round arm, which settles C-950tiling-020. On a Pattern C case with `total_tiles ≫ coreNum`,
record the *observed* number of cross-core merge rounds (from the `SyncAll` count, since
`总SyncAll次数 = ceil(log_M(coreNum)) + 1` predicts it) and compare against both formulas. The
observation distinguishes them without preferring either author.

Truncation arm: at fixed large N, sweep `K` from 1 to `tileSize` and record `aiv_time` plus the
`truncationFlag` trigger round. Upstream's condition predicts a step where truncation first engages;
if the curve is flat, the optimisation is not firing.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ubSize` or
`coreNum` are literals (the script defaults `core_num=64`, `ub_size=0` at `:70` and `248*1024` at
`:298` — both queried instead, per 0141 and C-006/C-007); that `concatTmpPerElem` and
`sortTmpPerElem` are 8 B each (the script assumes it; the real API query is used where available, per
0141); that a forced pattern was used (host echo required).

## 5 · Checker — acceptance declared before the run
Verdict variable `pattern_ladder_ordered`: true iff at every swept N the pattern upstream selects has
the lowest median `aiv_time` among the legal patterns, by more than the variance floor. Declared
acceptance: the boundaries are boundaries iff `pattern_ladder_ordered` holds at all swept N. The
OVERTURN fires iff Pattern C wins below `tileSize × coreNum` or Pattern B wins below `tileSize` by
more than the variance floor. Verdict `phase3_formula ∈ {coreNum, total_tiles, neither}` from the
merge-round arm. Verdict `truncation_engages`: true iff the `K` sweep shows a step at the predicted
`currentElements × M ≥ K` point.

The exit code is not the verdict: a merge that loses an index pair exits 0 with correctly sorted
values, so the instrument is an elementwise comparison of both outputs and the checker fails red if
only one was compared. Second guard: the `SyncAll` count must be observed, not assumed — the
merge-round arm's whole verdict rests on it, and if the profile cannot expose it the arm returns
`void` rather than inferring the round count from timing, which would be a measurement whose scope
does not cover the sentence. Third: pattern identity via host echo, since a forced pattern the host
overrode would make `pattern_ladder_ordered` true by construction.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `~34B`, `64B` and `104B`
figures are upstream's stated per-element costs, re-derived arithmetically in §3 but not measured.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish the pattern boundaries, the per-phase byte costs,
`M_WAY = 4`, `TOPK_SORT_NUM = 32`, or the values of `concatTmpPerElem` and `sortTmpPerElem` — the
script assumes 8 B each and upstream's formula leaves them symbolic. It does not resolve
C-950tiling-020 (the two phase-3 formulas). It does not establish that the truncation optimisation
fires. It does not establish `ubSize` or `coreNum`. This fallback is explicitly *not* a substitute for
the DAV_3510 TopK routing — `sort/topk.md:285` says so — so nothing here transfers to that path
(0142, 0143). No chip is named anywhere in `sort/fallback/`, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT because that is where our run would happen.
Nothing here is established for any 910-family board.
