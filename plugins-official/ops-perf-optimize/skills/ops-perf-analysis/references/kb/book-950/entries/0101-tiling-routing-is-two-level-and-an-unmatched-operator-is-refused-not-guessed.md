```
ID:        0101-tiling-routing-is-two-level-and-an-unmatched-operator-is-refused-not-guessed
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/index.md:9-24,53-60 —
           "两级路由：1. tiling/index.md（本文件）→ 按算子范式路由到 tiling/<范式>/index.md
           2. tiling/<范式>/index.md → 按 shape/dtype 条件路由到具体算法" and
           "未匹配 → 返回「该算子 pattern 暂未收录，请提供更多信息」"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a documented case where an operator that matches no row of the 12-family table is
           nevertheless given a tiling recommendation by this reference set, or a measured run
           showing the family a name routes to produces a worse plan than the family the
           operator's memory-access pattern belongs to.
```

# 0101 · Tiling routing is two-level, and an unmatched operator is refused rather than guessed

## 1 · Claim
Upstream asserts that tiling selection is a two-level routing decision and not a search: level 1
maps the operator name to one of exactly twelve pattern directories, level 2 maps shape/dtype to
one algorithm inside that directory, taking the first contributed algorithm whose condition
matches in descending priority order and otherwise the family's `fallback/` default. Upstream
further asserts that an operator matching no family is answered with a refusal string
(`该算子 pattern 暂未收录，请提供更多信息`), not with a nearest-neighbour guess. Not established
here — nothing in this entry was measured, and upstream gives no evidence that the twelve-way
partition is the right one for any board.

## 2 · The wrong branch this removes
Without this entry a harness agent treats the tiling references as a library to browse and
assembles advice from whichever family file looks relevant — typically reading `matmul/` for
anything with a GEMM in it, or reading two families and averaging. That produces plans whose
buffer budget formulas come from one family and whose entry gates come from another, and no
normal check catches it: the resulting tiling data is schema-valid, the numbers are all
plausible, and the operator still runs. The failure only shows up as a performance number nobody
can attribute. The second half of the claim removes a subtler wrong branch: with no explicit
refusal path, an agent asked about an uncovered operator invents a plan, and the invention is
indistinguishable in form from the eleven grounded ones.

## 3 · Ground / Source
`ops/ascendc-perf-optimize/references/tiling/index.md:11-24` — the routing table, verbatim:

```
| 算子类别 | 典型算子 | 建模目录 |
|---------|---------|---------|
| MatMul 矩阵乘类 | MatMul, BatchMatMul, MatMul_MXFP4, MatMul_A16W16 | [matmul/](matmul/) |
| MC² 通算融合类 | matmul_all_reduce, allgather_matmul, matmul_reducescatter, alltoall_matmul | [mc2/](mc2/) |
| Reduction 归约类 | ReduceSum, Softmax, LayerNorm, ArgMax | [reduction/](reduction/) |
| Scan / Cum 前缀扫描类 | Cumsum, Cummin, Cummax, Cumprod, LogCumsumExp | [scan/](scan/) |
| Gather 索引类 | GatherV2, Gather, torch.gather, Embedding | [gather/](gather/) |
| Sort / Select 排序选择类 | TopK, Sort, ArgSort, KthValue | [sort/](sort/) |
| Elementwise 逐元素类 | Sin, Cos, Abs, Exp | [elewise/](elewise/) |
| Broadcast 广播类 | Add, Mul, Sub | [broadcast/](broadcast/) |
| Scatter 按轴散射类 | Scatter, ScatterAdd, ScatterReduce（ScatterElementsV2） | [scatter/](scatter/) |
| Conversion 数据转换类 | Transpose, Concat, Split | [conversion/](conversion/) |
| Convolution 卷积类 | Conv2D, DepthwiseConv | [convolution/](convolution/) |
| FA FlashAttention 类 | FlashAttention, GroupNorm | [fa/](fa/) |
```

`:44` closes the Step-0 flow with `└─ 未匹配 → 返回「该算子 pattern 暂未收录，请提供更多信息」`.
`:57-60` states the selection logic: `1. 遍历该算子族的所有贡献算法，按优先级从高到低匹配条件
2. 首个条件匹配的贡献算法被选中 3. 无匹配时回退到默认参考算法`.

Two facts about this table are recorded here because they are properties of the routing contract
itself, not opinions about it. First, the twelve rows are populated by name, not by access
pattern: `GroupNorm` is routed to `fa/` (see 0169), which is the only family directory that is a
genuine stub, while `reduction/` next door carries the LayerNorm-class templates. Second, the
registry at `:62-77` marks four families' fallbacks `占位` (elewise, broadcast, conversion, fa) —
three of those labels are wrong, and the real content sits in the same directory (see 0152, 0156,
0163, and `harvest/contradictions-950-tiling.md` C-950tiling-001 with C-950tiling-026 … C-950tiling-028).

No second origin: everything above is one repo. Per RULES.md Art. 3 this entry cannot rise above
`harvested` on further reading inside `upstream/skills-dev-main/`.

## 4 · Procedure
The claim has a routing half and a refusal half; only the routing half is measurable on a board,
and this procedure targets it. Proposed, runnable later, never run in this phase.

Device selection: enumerate with `npu-smi info -l`, then for the candidate chip
`npu-smi info -t usages -i <id> -c <chip>` three times at 20 s spacing; require HBM-used and
AICore-utilisation both at their idle floor in all three samples before binding, then export
`ASCEND_RT_VISIBLE_DEVICES=<id>`. Re-sample after the run and discard the case if the die moved.
Board is named explicitly as 950PR (or 950DT, recorded as such); a run on one is not a result for
the other.

Cross-routing test, one operator per boundary pair. Pick three operators that sit on a family
boundary — `LogCumsumExp` (scan vs reduction), `GroupNorm` (fa vs reduction), `Concat` along a
non-innermost axis (conversion vs elewise). For each: generate two tiling plans, one from the
family `index.md` routes it to and one from the neighbouring family, using each family's own
`tiling-flow.md` derivation with the same shape/dtype set; build both kernels with the same
compiler pin; run both under `msprof --application=... --aic-metrics=PipeUtilization`; record
per-case `aiv_time` for every case, with no representative sampling.

The refusal half is checked by construction, not by a run: present the router with an operator in
none of the twelve rows (`Roll`, `Diagonal`, `Unique`) and record whether the reference set yields
a refusal or a plan. That check is textual and must be reported as such — it establishes nothing
about a board.

What the procedure refuses to assume: that a die free before the run stayed free; that a
different die may be substituted for the named one; that a boundary result for `LogCumsumExp`
transfers to any other scan operator; and that the winner on 950PR wins on 950DT.

## 5 · Checker — acceptance declared before the run
Verdict variable `routed_faster`, one boolean per boundary pair, computed as
`median(aiv_time_routed_family) < median(aiv_time_neighbour_family)` over ≥10 repetitions per
case with the first 5 discarded as warm-up. Declared acceptance for "routing is load-bearing":
`routed_faster` is true for all three pairs AND the median gap exceeds 10 % of the routed
family's median. Declared falsification: `routed_faster` false for any pair with a gap over 10 %
in the other direction — that names a mis-route, and the pair is written into §6 with its
numbers whether or not it is flattering.

The process exit code is NOT the verdict: `msprof` exits 0 on runs that produced no
`PipeUtilization.csv` at all. The verdict is read from the parsed CSV, and the checker fails
loudly if the expected row count is not present, rather than treating an absent row as a pass.
This checker can go red in three distinct ways — wrong-direction gap, missing CSV rows, and a
case whose two builds do not produce bit-comparable outputs (which would mean the two plans are
not computing the same thing and the timing comparison is void).

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
No board was touched; no operator was routed, built, or timed. The entry establishes only what
upstream's text says the routing contract is. It does not establish that the twelve-family
partition is correct, that the priority-ordered first-match rule beats an exhaustive comparison,
or that the refusal string is ever actually emitted by a consuming agent — upstream states the
refusal as a routing-tree leaf, and no mechanism enforces it. The chip is unstated in
`index.md`: the file names no board, no arch, and no `__NPU_ARCH__` guard anywhere, so BOARD is
`family-claimed(unverified)` even though the surrounding skill declares itself A5/arch3510-first.
§4 names 950PR/950DT because that is where our future run would happen, not because upstream's
evidence touched them — upstream has no evidence here at all. Nothing in this entry is claimed
for any 910-family board; that book gets nothing from this file.
