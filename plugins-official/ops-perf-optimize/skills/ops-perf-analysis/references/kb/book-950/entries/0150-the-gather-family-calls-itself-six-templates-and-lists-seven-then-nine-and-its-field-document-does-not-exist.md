```
ID:        0150-the-gather-family-calls-itself-six-templates-and-lists-seven-then-nine-and-its-field-document-does-not-exist
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/gather/index.md:11,13 —
           "| 0（兜底） | 通用六模板 | 无条件（回退保障） |" · "必须深入 fallback/ 子目录读取
           `tiling-flow.md`（六模板决策树 + UB 预算公式）、`tiling-fields.md`（TilingData 字段语义）" ;
           gather/fallback/index.md:3,10,14-22 — "Gather 族算子的六模板 Tiling 算法" ·
           "| [tiling-fields.md](tiling-fields.md) | TilingData 字段语义（规划中） |" ; a 7-row
           template table ; gather/fallback/tiling-flow.md:155-165 — a 9-row template table
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build of the gather family's tiling from these documents alone that produces a working
           plan for every template the decision tree can select — the missing field document would
           then not be load-bearing, and the count mismatch would be cosmetic.
```

# 0150 · The gather family calls itself six templates, lists seven then nine, and its field document does not exist

## 1 · Claim
Upstream asserts that its gather fallback is a `通用六模板` — a six-template algorithm — labelling it
so in the family routing table and twice more in prose, while it
lists seven templates in the fallback overview table (SIMD two-dimensional, SIMT two-dimensional, SIMD
last-axis gather, GA full-load, Full-Load, SIMD row-copy, SIMT scalar), and lists nine in the flow
document's quick-reference table (the same seven plus in-kernel Transpose+Gather and physical
Transpose+last-axis gather). The decision tree itself has ten leaves, counting the `EMPTY` template for
`gatherDimSize == 0`. Upstream instructs the consumer to read `tiling-fields.md` for TilingData field
semantics, marks that file `规划中` in its own index, and the file does not exist in the directory —
gather is the only family in this domain without one. Not established here; this entry records a
documentation state, and its overturn condition is about whether that state matters.

## 2 · The wrong branch this removes
"Six templates" is what a consuming agent carries away from the routing table, and it is the number
that will appear in whatever the agent writes. It is wrong by three or four depending on how you
count, and the templates it omits are not minor: the two transpose paths are the entire answer for
non-last-axis `PER_ELEMENT` gather (0149), which is `torch.gather` — the most commonly requested
member of the family. An agent that believes there are six will look for the `PER_ELEMENT`
non-last-axis answer among the six, not find it, and either refuse or route to the SIMT fallback,
which is the arm upstream says the transpose paths exist to beat.

The missing field document is the more concrete gap. The flow document defines the templates and their
UB budgets in symbols — `xAlign`, `idxAlign`, `minIdxSlice`, `MIN_OUT_UB`, `MIN_INDICES_UB`,
`carryNumAlign`, `INDEX_SIZE_T` — and the file that would give them field names, types and derivations
is the one that is absent. Every other family in this domain carries a `tiling-fields.md` that does
exactly that. So an agent following upstream's own mandatory-reading instruction
(`必须深入 fallback/ 子目录读取 ... tiling-fields.md`) hits a dead link, and then has to guess the
TilingData layout that the kernel contract depends on. A prior survey recorded the broken link from
`fallback/index.md:10`; re-reading the directory confirms the file is absent, and confirms that
`gather/index.md:13` instructs reading it as mandatory.

The third wrong branch is subtler and worth stating because it generalises: a count in a routing table
is a *contract summary*, and when it disagrees with the body the agent trusts the summary, because the
summary is what it read first and what it will paraphrase. This is the same placement failure as the
scan script emitting a forbidden template (0136) and the elewise/broadcast placeholder labels (0152,
0156) — the artifact a consumer opens first says something the body contradicts, and no mechanism
reconciles them.

## 3 · Ground / Source
The count, three times. `gather/index.md:11`:

```
| 0（兜底） | 通用六模板 | 无条件（回退保障） | [fallback/index.md](fallback/index.md) → [fallback/tiling-flow.md](fallback/tiling-flow.md) |
```

`gather/index.md:13`:

```
> ⚠️ 路由命中后**必须深入 fallback/ 子目录**读取 `tiling-flow.md`（六模板决策树 + UB 预算公式）、`tiling-fields.md`（TilingData 字段语义）。禁止仅读本文件的表格后停止。
```

`gather/fallback/index.md:3`:

```
> Gather 族算子的六模板 Tiling 算法。所有 Gather 算子共享同一套模板语言。
```

The seven-row table, `gather/fallback/index.md:14-22`:

```
| 模板 | 触发条件 | 核心策略 |
|------|---------|---------|
| SIMD 两维 | 2D + innerSize ≥ SIMD 阈值 | gatherSize 分核，innerSize 行向量化 |
| SIMT 两维 | 2D（兜底） | SIMT 2048 线程标量并行 |
| SIMD 末轴 Gather | innerSize==1 + GD 全载 UB | DataCopyGather 向量化 |
| GA 全载 | inner 小 + GA 全载 UB | DataCopyGather / VF gather |
| Full-Load | GD×inner 全载 UB + 2D | x 全载，逐索引 copy |
| SIMD 行拷贝 | inner 大 | DataCopyPad 逐行 + index 缓存 |
| SIMT 标量 | 兜底 | SIMT 2048 线程 + fast-div |
```

The nine-row table, `gather/fallback/tiling-flow.md:155-165`:

```
| 模板 | gatherMode | 维度条件 | UB 策略 | 关键技术 |
|------|-----------|---------|---------|---------|
| **kernel 内 Transpose + Gather** | **PER_ELEMENT only** | **dim!=last + 能力/UB/成本门控全部通过** | **transpose buffer + gather buffer + workspace GM** | **stride DMA + TransDataTo5HD + Gather指令 + ReTranspose** |
| **物理 Transpose + 末轴 Gather** | **PER_ELEMENT only** | **非末轴 + 平台能力/成本门控通过** | 各独立算子自行 tiling | Transpose(x/index/y) + LastDim Gather |
| SIMD 末轴 Gather | 通用 | inner==1 + GD 全载 | x 行全载 + index + out | DataCopyGather MicroAPI |
| GA 全载 | 通用 | inner 小 + GA 全载 | x GA 块全载 + index + out | DataCopyGather / VF gather |
| Full-Load | 通用 | GD×inner 全载 + 2D | x 全载 + out | 逐索引 DataCopyPad |
| SIMD 两维 | **PER_SLICE only** | 2D + inner 大 | index 缓存 + x 行 tile | DataCopyPad 逐行 |
| SIMD 行拷贝 | **PER_SLICE only** | inner 大 | index 缓存 + x 行 tile | DataCopyPad 逐行 + index 滑窗 |
| SIMT 两维 | 通用 | 2D + inner 小 | 无 UB（直接 GM） | SIMT 2048 线程 |
| SIMT 标量 | 通用 | 兜底 | 无 UB | SIMT 2048 线程 + fast-div |
```

The decision tree at `:62-116` has ten selectable outcomes: the `EMPTY` guard at `:68`, then the eight
branches, with the `PER_ELEMENT` non-last branch itself splitting three ways (in-kernel transpose,
physical transpose, Scalar/SIMT), which is where the count from seven to nine comes from.

The missing file. `gather/fallback/index.md:5-10`:

```
## 文档索引

| 文档 | 内容 |
|------|------|
| [tiling-flow.md](tiling-flow.md) | 六模板决策树 + 合轴公式 + UB 预算公式 + 多核切分 |
| [tiling-fields.md](tiling-fields.md) | TilingData 字段语义（规划中） |
```

The directory contains `index.md`, `fallback/index.md` and `fallback/tiling-flow.md` and nothing else.
So `gather/index.md:13` marks as mandatory reading a file that its own sibling marks as planned and
that does not exist. Registered as C-950tiling-023 (the missing field document) and C-950tiling-024
(the template count stated as six and listed as seven and nine).

Two consistency notes recorded rather than adjudicated. The seven-row table's trigger column omits
`gatherMode` entirely — `SIMD 两维 | 2D + innerSize ≥ SIMD 阈值` with no mode restriction — while the
nine-row table marks the same template `PER_SLICE only`. An agent reading the overview table alone gets
a legality rule that the flow document contradicts, which is 0147's subject seen from the other side.
And the overview's `SIMD 行拷贝 | inner 大` gives no threshold where the flow document gives four
(0148).

## 4 · Procedure
This claim is about a document set, so the falsifying test is a construction rather than a measurement,
and one arm needs no device. Neither has been run.

Arm 1 — closure check, no device, permitted in this phase. Attempt to write a complete host tiling for
each of the ten decision-tree outcomes using only `gather/index.md`, `gather/fallback/index.md` and
`gather/fallback/tiling-flow.md`. For each outcome record: whether every symbol in its UB budget has a
value or a stated derivation; whether the TilingData field set can be named; and which symbol first
blocks the construction. The expected blockers are the six undefined symbols listed in 0148 §3 plus the
absent field document. Confirm the file's absence mechanically:
`ls upstream/skills-dev-main/ops/ascendc-perf-optimize/references/tiling/gather/fallback/` — read-only,
no device, no execution.

Arm 2 — the templates the count omits, on a named 950 board (950PR or 950DT); never run in this phase.
Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved.

Take one `PER_ELEMENT` non-last-axis case that passes 0149's gates. Build the plan a "six-template"
reader would produce — which cannot be either transpose path, so it is SIMT scalar — and the plan a
"nine-template" reader would produce. One compiler pin; md5 each; host echo of the selected template;
elementwise comparison against a CPU reference; `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case, against a variance
floor measured first. The gap between those two plans is the cost of the wrong count, as a number.

Refuses to assume: that a free die stays free; that a die may be substituted; that the missing symbols
are unavailable elsewhere — arm 1 records where it looked; that the six-template reader would
necessarily reach SIMT (if the overview's seven rows admit a different fallback for this shape, that is
recorded and used instead).

## 5 · Checker — acceptance declared before the run
Verdict variable `closure_blockers`, the list of outcomes in arm 1 that could not be fully specified,
with the first blocking symbol for each. Declared before the run: the missing field document is
load-bearing iff `closure_blockers` is non-empty. The OVERTURN fires iff `closure_blockers` is empty —
every template can be fully specified from the three surviving files, and the missing document is then
not load-bearing, whatever the count says.

Verdict variable `count_cost` = SIMT-plan median `aiv_time` / best-transpose-plan median `aiv_time` from
arm 2, reported with the variance floor. This quantifies the omission rather than asserting it matters.

The exit code is not the verdict. Arm 1's instrument is the per-outcome specification table, and the
checker fails red if that table has fewer than ten rows — a closure check that silently skipped the
outcomes it could not attempt would report an empty blocker list and produce a false overturn, which is
exactly the reads-only-what-it-expects species. Arm 2's guard is template identity via host echo, plus
the elementwise comparison, since a gather that returns wrong elements exits 0.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Arm 1 needs no device and has
not been run either, so no closure table and no directory listing is recorded in this entry.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, and no construction was attempted. The entry does not establish that the missing
field document is load-bearing — arm 1 exists because that is unknown, and an empty blocker list would
overturn it. It does not establish the correct template count; it records that upstream states six,
lists seven in one table and nine in another, and has ten decision-tree outcomes, and it does not pick
one. It does not establish the cost of the omission. It does not resolve the seven-row table's missing
`gatherMode` restrictions (0147) or its missing thresholds (0148), beyond noting that the two tables
disagree. No chip is named anywhere in the gather family, so BOARD is `family-claimed(unverified)` and
the chip is unstated; §4 arm 2 names 950PR/950DT because that is where our run would happen. Nothing
here is established for any 910-family board.
