```
ID:        0126-the-interleaved-template-pays-only-when-the-baseline-innermost-burst-is-pathologically-small
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:516-546 —
           "| tail-R（fast） | 基线最内 burst 大小（=内块最内 R 长度×dtypeSize）+ rows 轴规模 |
           burst **≤16B** 且 **rowsSize≥8** 才大赢 | #18 burst 8B, rows=640 → **8.29×** |" ·
           "| tail-A（fast-RARA） | 内块每行大小 innerRowElems | **≥ 512 元素（≥1KB fp16 /
           ≥2KB fp32）** 才值得 | #11 4320 元素 → 1.39×；#12 3840 → 微赢 |" ;
           reduction/fallback/example/euclidean_norm/experience.md:111-138 — the 20-case table
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured interleaved case on a named 950 board with baseline innermost burst well
           above 16 B that still gains more than 20 % from the tail-R template — the burst
           criterion would then not be the thing that decides.
```

# 0126 · The interleaved template pays only when the baseline innermost burst is pathologically small

## 1 · Claim
Upstream asserts, on the strength of a 20-case on-board measurement set, that the interleaved
continuous-load templates are a precision instrument rather than a general improvement: of 20
EuclideanNorm cases, only three benefit (#11, #12, #18), one of which is a large win (#18, 8.29×)
and the other two modest (1.39× and 1.03×); nine take the R-axis-split group path, and the
remaining eight take the ordinary A-axis path. Upstream asserts the deciding quantities per
template: for tail-R, the baseline's innermost burst size (innermost inner-block R length ×
`dtypeSize`) must be at most 16 B and the `rows` axis must have at least 8 elements; for tail-A,
the inner block's per-row element count `innerRowElems` must be at least 512 elements — upstream
glosses this as ≥1 KB at fp16 and ≥2 KB at fp32. Upstream states the design intent directly:
`交错模板是"精准打击"型优化 ... 其余 17 个必须干净回退，零退化`. Not established here.

## 2 · The wrong branch this removes
An agent that reads only the mechanism (0125) concludes that interleaved layouts should always take
the interleaved template, since the mechanism — larger bursts, less scattered reading — sounds
unconditionally good. The measured table says otherwise: 17 of 20 interleaved-or-adjacent cases
must fall back, and two of them regress badly when they do not (0127). The reason is stated at
`:539-540` and is the transferable lesson: the template's fixed overheads (chunking barriers,
per-plane reductions, per-slab step-2 barriers with small reductions) are constant, so they are
recovered only where the baseline is pathological. At a moderate 64 B burst or a small 320 B inner
block, the baseline is not pathological enough and the overheads dominate.

The second wrong branch this removes is a modelling one, and it is the reason upstream's numbers
are worth carrying verbatim rather than summarising. `#18 1128.5 → 136.1 µs` is not a
representative improvement — it is the one case in twenty where the baseline was broken. An agent
that quotes 8.29× as the template's benefit is quoting the maximum of a distribution whose median
is 1.00×. Upstream itself does not do this: it publishes the whole table, including the rows where
its own optimisation loses.

## 3 · Ground / Source
The criteria table, `reduction/fallback/tiling-flow.md:516-529`:

```
> 全部经 arch35 上板实测校准（EuclideanNorm 20 case，见
> [example/euclidean_norm/experience.md](example/euclidean_norm/experience.md) §5）。

**核心判据：`mte2_ratio` 单指标会误导，不能作为选型依据。** 真正决定赢面的是：

| 路径 | 真实判据 | 阈值 | 依据 case |
|------|---------|------|----------|
| tail-R（fast） | 基线最内 burst 大小（=内块最内 R 长度×dtypeSize）+ rows 轴规模 | burst **≤16B** 且 **rowsSize≥8** 才大赢 | #18 burst 8B, rows=640 → **8.29×** |
| tail-A（fast-RARA） | 内块每行大小 innerRowElems | **≥ 512 元素（≥1KB fp16 / ≥2KB fp32）** 才值得 | #11 4320 元素 → 1.39×；#12 3840 → 微赢 |

> 两条路径还要求 `innerElems×dtypeSize`（tail-R）/ `innerRowElems×dtypeSize`（tail-A）32B 对齐（kernel 连续 `DataCopy` 载入要求），非对齐直接回退。
```

The full measured table, `reduction/fallback/example/euclidean_norm/experience.md:111-138`, quoted
whole because a partial quotation of an evidence table is what this book exists to prevent:

```
> 单位 µs；加速 = baseline / merged；merged 模板即最终选型（数据源 `PERF_TUNING_REPORT.md §2`）。

| # | case | 合轴/布局 | baseline | merged | 加速 | 选型 |
|---|------|----------|--------:|------:|-----:|------|
| 1 | ra_group_0001 | RA 大R | 14.3 | 13.3 | 1.08× | group（五模板） |
| 2 | ra_group_0002 | RA fp16 | 13.3 | 12.2 | 1.09× | group |
| 3 | ra_group_0003 | RA bf16 | 13.4 | 12.5 | 1.07× | group |
| 4 | ra_group_0004 | RA | 17.3 | 17.4 | 1.00× | group |
| 5 | r_group_0005 | R fp16 | 9.9 | 10.9 | 0.91× | group |
| 6 | ara_group_0001 | ARA | 11.4 | 10.5 | 1.08× | group |
| 7 | ara_group_0002 | ARA fp16 | 10.9 | 10.9 | 0.99× | group |
| 8 | arar_group_0001 | ARAR（4轴） | 16.7 | 16.8 | 1.00× | group |
| 9 | ararara_0002 | 7轴 tail-A，slabCnt=8 | 61.8 | 60.4 | 1.02× | group（slab 太少回退） |
| 10 | ararara_0003 | 7轴，内块 5MB | 63.9 | 59.7 | 1.07× | normal |
| **11** | **ararara_0004** | **7轴 tail-A，内块 17KB** | **171.0** | **123.2** | **1.39×** | **交错-tail-A（fast-RARA）** |
| 12 | ararara_0005 | 7轴 tail-A，内块 15KB | 31.9 | 31.1 | 1.03× | **交错-tail-A（fast-RARA）** |
| 13 | ararara_0006 | 7轴，内块 320B | 72.9 | 75.2 | 0.97× | group（回退，见 §6） |
| 14 | ararara_0007 | 7轴 | 120.5 | 124.4 | 0.97× | group |
| 15 | ararara_0008 | 7轴，内块 32B，slabCnt=18000 | 24.4 | 22.8 | 1.07× | normal（回退，见 §6） |
| 16 | ararara_0009 | 7轴 | 61.1 | 62.0 | 0.99× | normal |
| 17 | arararar_0001 | 8轴，burst 64B | 100.9 | 99.4 | 1.01× | normal（回退，见 §6） |
| **18** | **arararar_0002** | **8轴 tail-R，burst 8B** | **1128.5** | **136.1** | **8.29×** | **交错-tail-R（fast）** |
| 19 | arararar_1007 | 8轴 fp16 | 17.0 | 16.5 | 1.03× | normal（fp16，门控未命中回退†） |
| 20 | ra_3004 | RA int32 | 7.8 | 7.5 | 1.04× | normal |

**结论**：20 个 case 里 **仅 #11 / #12 / #18** 真正需要交错模板（#18 8.29× 是唯一大赢家）；**#1–9 共 9 个走 R 轴分核 group（BlockSplitR，最主力路径）**，#10/#15/#16/#17/#19/#20 走 A 轴分核 normal——都是现成模板，三种引擎差异 ≤10%。
```

Observations recorded against the table rather than inferred beyond it. The distribution: 15 of 20
rows lie between 0.91× and 1.09×, i.e. within a band a run-to-run variance study could plausibly
cover, and upstream states no variance figure and no repetition count anywhere. Three rows are
outside it: #11 (1.39×), #18 (8.29×) and #5 (0.91×, a regression on the group path). The `加速`
column is defined as `baseline / merged` at `:113`, so values above 1 are improvements; #5 at
0.91× is therefore 9 % slower after merging, published in the same table.

Upstream's own summary of the design philosophy, `tiling-flow.md:542`:
`交错模板是"精准打击"型优化：20 case 里仅 #11/#12/#18 真正获益，其余 17 个必须干净回退，零退化。
**任一门控不满足即 `return false` 落回五模板/group，回退安全。**`

The gloss `≥ 512 元素（≥1KB fp16 / ≥2KB fp32）` is arithmetically consistent: 512 × 2 = 1024 B and
512 × 4 = 2048 B. It also means the threshold is stated in *elements*, so the byte size at which it
bites differs by dtype by 2× — a case at 512 fp16 elements (1 KB/row) passes while a 1 KB fp32 row
(256 elements) fails. Whether that is intended is not stated.

The measurement's identity, `experience.md:5`:
`平台：Ascend 950 / arch35（dav-3510），CANN 9.0.0，coreNum=72，UB≈192KB。数据全部 msprof 上板实测。`
That is a real platform statement — arch family, toolkit version, core count, UB size and tool —
and it is more identity than any other family in this domain provides. It still names no board:
`Ascend 950` covers both 950PR and 950DT, so BOARD stays `family-claimed(unverified)`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. What is
missing from upstream's table is a variance figure, and without one 15 of its 20 rows cannot be
told from noise. This procedure supplies that first and the thresholds second.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Arm 0 — the variance floor, run before anything else. Take three cases spanning the time range
(≈10 µs, ≈100 µs, ≈1000 µs), build each once, and run it 30 times in the same process and 5 times
across fresh processes. Report the interquartile range as a fraction of the median, per case. Every
subsequent comparison in this entry is reported against that floor, and a difference inside it is
called a null.

Arm 1 — the burst ladder for tail-R. Construct interleaved 8-axis cases whose innermost inner-block
R length gives bursts of {8, 16, 32, 64, 128, 256} bytes at fp32, holding total element count and
`rowsSize` fixed. At each burst build both the five-template baseline and the tail-R template, one
compiler pin, md5 each, host echo of the interleaved fields, fp64 reference check within a
tolerance declared in advance (accumulation order differs), and `aiv_time` plus measured innermost
burst under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Arm 2 — the `innerRowElems` ladder for tail-A. Construct 7-axis cases with
`innerRowElems ∈ {8, 80, 256, 512, 1024, 4320}` at fp32 and at fp16, the first two reproducing #15
and #13 (0127). Same build and capture protocol.

Arm 3 — `rowsSize`. Hold burst at 8 B and sweep `rowsSize ∈ {2, 4, 8, 16, 640}`.

Refuses to assume: that a free die stays free; that a die may be substituted; that upstream's
`coreNum = 72` and `UB ≈ 192 KB` are this machine's values — both are queried and printed, and the
gates `groupCnt ≤ coreNum` and `slabCnt × 2 ≥ coreNum` move with the first; that a single run is a
measurement (arm 0 is a precondition for reading any other arm); that the 20-case table transfers
— it is upstream's platform, upstream's operator, and upstream declares its fp16/bf16 rows out of
date.

## 5 · Checker — acceptance declared before the run
Verdict variables `burst_cross` (the burst size at which tail-R's advantage falls below 1.20×) and
`rowelems_cross` (the `innerRowElems` at which tail-A's advantage falls below 1.05×), each reported
with the arm-0 variance floor beside it. Declared before the run: the 16 B criterion is supported
iff `burst_cross ∈ [16, 64]`; the 512-element criterion is supported iff
`rowelems_cross ∈ [256, 1024]`; the `rowsSize ≥ 8` floor is supported iff the advantage at
`rowsSize = 4` is below 1.20× while at 8 it is above. The OVERTURN fires iff a case with burst
above 64 B gains more than 20 % from tail-R. Any comparison whose difference is inside the arm-0
floor is reported as a null and is not counted toward any of these.

The exit code is not the verdict. Three guards. First, arm 0 must have run and produced a floor;
without it the checker refuses to issue any verdict rather than reporting ratios — a ratio without
a variance floor is the failure this arm exists to prevent, and 15 of upstream's 20 rows are
exactly that shape. Second, template identity: the fast arm must echo non-zero `fastGroupCnt` or
`raraSlabCnt`; a silent fallback would produce ratios of 1.00 across the ladder and read as a clean
threshold. Third, the measured innermost burst must match the constructed one at every rung, and
the checker goes red where it does not — otherwise the ladder's x-axis is fictional.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Every number in §3 is
upstream's readout on upstream's platform, quoted; this book has run nothing and has not reproduced
a single row.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. The entry does not establish the 16 B burst criterion, the 512-element
criterion, or the `rowsSize ≥ 8` floor — it records that upstream calibrated them on 20
EuclideanNorm cases. It does not establish that upstream's table separates signal from noise: no
repetition count, no variance and no confidence interval is given anywhere in the source, and 15 of
20 rows fall within ±9 %. It does not establish that the results transfer to any operator other
than EuclideanNorm, to any dtype other than fp32 (upstream declares its fp16/bf16 rows superseded),
or to any core count other than 72. It does not establish the platform's UB capacity, which
upstream states as ≈192 KB here and 248 KB in its own script (0131). `Ascend 950 / arch35
(dav-3510)` names a family, not a board, so BOARD is `family-claimed(unverified)`; §4 names
950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.
