```
ID:        0073-the-r-value-table-lists-typical-configs-that-may-not-be-shipped-without-a-search
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:434-440 — "| R 范围 | 核利用率 | 参考策略 | 典型配置 | | ≈1 (0.9~1.1) | 满核 | 等分 n=4 | longMSize=512, tc=4 | | 1.3~2.0 | **不满 (<80%)** | 长短块，longMSize 使 mBlk 增大 | longMSize=576, tc=4 | | 1.3~2.0 | 满核 | 长短块，增大 tileCnt | longMSize=352~432, tc=5~6 | | >2 且恒满核 | 满核 | 等分 n=2 | longMSize=1024, tc=2 | | >2 且不满 | 不满 | 长短块，longMSize 使 mBlk 增大 | longMSize=576, tc=4 |"
           ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:444 — "所有场景**必须执行完整搜索**，不得跳过。上表中的"典型配置"仅作为 R 值区间的参考预期，实际 longMSize 须由搜索算法在配平可行域内系统遍历后取 Top-N 候选 msprof 实测确定"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured campaign on a named 950 board in which the table's typical configuration is the
           measured optimum in every R band — the mandatory-search rule would then be pure cost, and
           the table could be used as a lookup after all.
```

# 0073 · The R-value table lists typical configurations that may not be shipped without a search

## 1 · Claim
Upstream asserts a five-row decision table indexed by R band and by whether the cores are filled,
giving a reference strategy and a typical configuration for each — including specific values,
`longMSize` 512 with tileCnt 4 at R ≈ 1, 576 with 4 when cores are unfilled, 352-432 with 5-6 when
filled at R 1.3-2.0, and 1024 with 2 when R > 2 with cores always filled. Upstream asserts, in the
paragraph immediately following, that every scenario must run the full search regardless, that the
typical configurations are only reference expectations for their band, and that even at R ≈ 1 or
R > 2 with full cores the search must still run, because it may find that the core-utilisation
constraint or the balance condition excludes the expected plan. Not established here; none of the
values has a case identity, a shape or a board.

## 2 · The wrong branch this removes
A table of concrete values sitting next to a rule that forbids using them as values is a trap by
construction. The values are what an agent will remember and produce — `longMSize=512, tileCnt=4` is
exactly the shape of answer that reads as expert, and it is the very value MC-C2 names as forbidden
when delivered without a search (0061). The failure is invisible in the conversation: the number is
plausible, it is in the document, and it is in the right R band.

The second, subtler branch: the table is indexed on a quantity the agent may not have. Three of the
five rows are conditioned on core utilisation, which requires `baseM`, `baseN` and `usedCoreNum` from
the host print (0062) — so an agent that has R but not the TilingData cannot even select a row, and
two rows share the same R range and differ only by the condition it cannot evaluate.

## 3 · Ground / Source
`pipeline_balancing.md:430-446`, the whole R 值策略决策表 section. The table is quoted in SOURCE. The
enforcement paragraph, `:442-446`:

> ### 搜索强制执行
> 所有场景**必须执行完整搜索**，不得跳过。上表中的"典型配置"仅作为 R 值区间的参考预期，实际 longMSize
> 须由搜索算法在配平可行域内系统遍历后取 Top-N 候选 msprof 实测确定。即使 R ≈ 1 或 R > 2 且恒满核，
> 搜索仍须执行——搜索过程中可能发现核利用率约束或配平条件排除了预期方案，理论最优与实际最优常有偏差。
> 搜索的 Top-N 候选须全部 msprof 实测后择优。

Three observations that a consumer needs and that the table does not supply. The R bands here are not
the bands of the bound-diagnosis table (0058): this table uses ≈1 (0.9-1.1), 1.3-2.0, and >2, leaving
1.1-1.3 unassigned and omitting the communication-bound side entirely — every row has R ≥ 0.9, so an
operator at R = 0.3, which upstream reports having measured, has no row. The 典型配置 values are
absolute row counts with no M attached, so `longMSize=512` is meaningful only for whichever M the
table's author had in mind. And the last sentence of the enforcement paragraph is the same sentence an
agent will reach for to explain an empty candidate set — which is exactly what P4 as published
produces (0066), so the document supplies a ready rationalisation for its own defect.

Consistent statements elsewhere: MC-C2 at `comm-compute/index.md:181` forbids delivering one or two
remembered values, naming `longMSize=512`; `pipeline_balancing.md:405` says theory only ranks (0069);
`:491` requires all Top-N candidates to be measured.

## 4 · Procedure
Later phase, needs one card per rank; capture per 0057, R per 0059, TilingData per 0062, search per
0069.
1. Device selection per 0057; board token per rank from the driver readout; occupancy either side.
2. For each of the four R bands the table covers, construct a problem instance whose measured R lands
   in that band, and record both R and the core utilisation of the table's typical configuration.
3. Measure three configurations per instance: the table's typical configuration; the search's rank-1
   candidate; and the measured optimum over all surviving candidates (0069's full sweep).
4. Record T_total for all three, and the rank of the table's configuration inside the measured
   ordering.

## 5 · Checker — acceptance declared before the run
Verdict variables `T_table`, `T_rank1`, `T_best`, and `table_rank` = the position of the table's
configuration in the measured ordering. Acceptance of the mandatory-search rule: `T_table > T_best`
beyond spread in at least one band — that is what makes the search necessary rather than ceremonial.
Acceptance of the table as a *reference expectation*, which is all upstream claims for it:
`table_rank` in the top quartile of the candidate set.

Exit code is not the verdict. All three times and the full ordering are published per band, including
any band where the table's configuration wins — retained and named, because a table that is right in
one band and wrong in another is more useful information than an average.

Red input: an instance at R ≈ 0.3, for which the table has no row. The procedure must report
`no_applicable_row` rather than selecting the nearest one; a checker that silently extended the
nearest band would hide the table's actual coverage.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. None of the five typical configurations has an M, a shape, an operator, a board or a
rank count attached, so none of them is a claim this book can even scope. The table covers no
communication-bound band and leaves R ∈ (1.1, 1.3) unassigned. The core-utilisation column depends on
values only the host print supplies (0062) and on the saturating formula of 0068. Nothing here
establishes that the search finds a better configuration — that is the procedure's question, and the
search itself is defective as published (0066).
