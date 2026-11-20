# Contradictions register — domain `950-td` (wave 1.75)

> **TRIAGED 2026-08-25**: every row below has a phase-2 disposition in
> `harvest/TRIAGE_DOMAIN_ROWS_20260825.md` (resolved / assigned-to-round / noted / blocked).

Scope: `ops/ascendc-tiling-design/` (its DAV_3510 / arch35 columns and its arch-generic
methodology) and `ops/ascendc-performance-best-practices/reference/{gather,reduce,scan,conversion,
broadcast,scalar,elementwise}/` read as twin-diffs against the analysis shelf already entered in
`book-950/entries/0101`–`0169`.

Same rules as the other domain registers: a row records two or more upstream statements on one
topic that do not agree, both quoted, neither adjudicated. Resolution only by an Art. 7 procedure
on a named board. Entry references are written `950:NNNN` (this file is read from outside one book,
so the bare form would be a CONVENTIONS error).

Three shelves recur below and are named consistently:
- **design shelf** = `ops/ascendc-tiling-design/`
- **analysis shelf** = `ops/ascendc-perf-optimize/` (mined in waves 1 / 1.5, entries 0101–0169)
- **implementation shelf** = `ops/ascendc-performance-best-practices/`

All three are files in one repository, so under RULES.md Art. 3 / STRATA S2 they are **one origin**.
A disagreement between them is a contradiction, never a corroboration. The one independent origin
used in this domain is the installed toolchain, `/usr/local/Ascend/cann-9.0.0-beta.2/`, read-only.

---

## C-950td-001 · Reduction template count: four, five, or six
- **design shelf** `ascendc-tiling-design/references/reduction/patterns.md:32-39` — four templates:
  AR-FullLoad / AR-ColSplit / ARA-FullLoad / ARA-RowSplit. No small-R arm exists anywhere in the family.
- **analysis shelf** `ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-fields.md:3` —
  "五模板（AR-SmallR / AR-FullLoad / AR-Recompute / ARA-FullLoad / ARA-Recompute）"
- **implementation shelf** `ascendc-performance-best-practices/reference/reduce/guide.md:87,93-97` — the
  analysis shelf's five, plus `:210` a sixth, **ARA-Online**, filed under a separate heading (在线计算模板).
Carried by `950:0401`. → 950 book. Disposition: recorded; the naming difference is not merely
vocabulary because the split arms also differ mechanically (C-950td-002).

## C-950td-002 · The split arm's cross-chunk merge: scalar sequential vs binary fold
- **design shelf** `reduction/ar-colsplit.md:125-127` — "ReduceMax: 使用 `if` 或者 `三目运算` 取最大值 /
  ReduceSum: 使用 `+=` API 累加", implemented at `:99,116` as a C `float globalMax` updated per chunk
  after `chunkResultLocal.GetValue(0)` — a scalar round-trip out of UB, serial depth = chunk count.
- **analysis shelf** `tiling/reduction/fallback/tiling-flow.md:268-270` — "块间合并: 二分累加 /
  fold_base = 小于 r_loop_count 的最大 2 的幂 / fold_remain = …", with `binary_cache = 2048` reserved at `:259`.
- **implementation shelf** `reduce/guide.md:77-78,83,233` — the fold is shipped machinery
  (`UpdateCache` / `GetCacheID` / `FindNearestPower2`), "O(log N) 层而非 O(N) 串行".
Carried by `950:0402`. → 950 book. Disposition: recorded. Note the confound §2 of `950:0402` names —
the two arms are documented for different operator classes (one statistic vs three-pass Softmax) — which
is why the procedure varies only the merge inside one kernel.

## C-950td-003 · Why the binary fold exists: precision or latency
- **design shelf** `reduction/alg-dichotomy.md:3,5,40` — the fold is a **precision** device:
  "解决顺序累加中大数吃小数的精度问题"; its trade-off table's only performance column is UB cost, and it
  claims "无额外" buffer.
- **implementation shelf** `reduce/guide.md:83` — the fold is a **latency** device:
  "显著降低长 R 的归约串行延迟"; and it costs a real cache buffer (2048 B per the analysis shelf).
Two shelves recommend one mechanism for two unrelated reasons; neither mentions the other's, and they
disagree about whether it is free. Carried by `950:0402` §3 and §5's `ub_delta` verdict. → 950 book.

## C-950td-004 · Within the design shelf: 2-D split reads a scalar back, 3-D split does not
- `reduction/ar-colsplit.md:112,116` — `float chunkMax = chunkResultLocal.GetValue(0);` then a C `if`.
- `reduction/ara-rowsplit.md:179,188-190` — `Max<float>(globalResultLocal, globalResultLocal,
  chunkResultLocal, alignedCols);`, i.e. element-wise in UB, no scalar read-back; "使用 `Max<float>` 和
  `Add<float>` 而非 Reduce 操作" (`:220`).
One shelf, one family, two chunk-merge disciplines, no comment on the difference. Cited by `950:0402`.
→ 950 book.

## C-950td-005 · Is the template table a rule?
- **implementation shelf** `reduce/guide.md:7,89,280` — three times: "本指南是**优秀实践目录**，而非选型
  决策树"; "下表"适用条件"是模板的设计前提，非强制决策规则"; "以上是"特征—模板"对应关系，非决策树".
- **analysis shelf** `tiling/reduction/fallback/tiling-flow.md:88` — "## 3. 五模板决策树（Step 1–2）",
  with `直接返回` short-circuit semantics at `:90`.
- **design shelf** `reduction/patterns.md:19` — "## 场景判定流程", same first-match `├─ / └─ 否则` shape.
Asymmetry worth recording: the shelf that declines to publish a rule is the one that publishes the
family's only on-board measurements (`950:0126`, `950:0127`); the two that publish trees publish
host-side compiles only (`950:0124` §7). Carried by `950:0403`. → 950 book.

## C-950td-006 · The 255 row-chunk cap: literal, named, or absent
- **design shelf** `reduction/ara-rowsplit.md:77` — `R_max = std::min(R_max, 255u);` — bare literal, no
  name, no comment; the value reaches `DataCopyExtParams`'s `blockCount` at `:165-171`.
- **analysis shelf script** `tiling/reduction/fallback/script/reduction_tiling.py:46,281,364` —
  `REPEAT_MAX = 255`, applied at two sites.
- **analysis shelf markdown** `tiling/reduction/fallback/tiling-flow.md` — **no 255 anywhere**; its
  ARA-Recompute budget uses a fixed `r_bin_size = 128` and states no upper bound on `r_max`.
- **installed toolchain** (independent origin) `…/ascendc/include/basic_api/impl/utils/
  kernel_utils_constants.h:39` — `const int32_t MAX_REPEAT_TIMES = 255;`
Carried by `950:0404`. → 950 book. Disposition: the toolkit constant makes this the domain's one
`corroborated` numeric row; whether it *binds this quantity* is `950:0404` §4's question.

## C-950td-007 · "arch35 only supports AR/RA" — an attribution the headers do not distinguish
- **implementation shelf** `reduce/guide.md:119` — "arch35 `ReduceSum` **只支持 AR/RA 两级**，多维 `ARAR`
  编译报错 → 需拆成两步 AR/RA 链式规约" (entered as an unverified premise at `950:0125`).
- **installed toolchain** — the restriction is present in the DAV_3510 backend
  (`asc/impl/adv_api/detail/reduce/reduce_sum/reduce_sum_c310_impl.h:114-115`) **and** in the other
  backend implementation the same toolkit ships (`reduce_sum_v220_impl.h:288-289`), under a different
  spelling. So within this toolkit the restriction is not what distinguishes arch35.
Carried by `950:0405`. RULES.md Art. 1 fence: no fact about the non-950 architecture enters book-950; the
second file is cited only to show the attribution is not a discriminator. → 950 book.

## C-950td-008 · Reduce dtype sets: implementation header vs public doc comment (and one file vs itself)
Installed toolchain, `cann-9.0.0-beta.2`. Doc comment on the shared declaration vs the `c310`
`SupportType` list: `ReduceMax`/`ReduceMin` `float/half` (`reduce.h:101,152`) vs eleven types
(`*_c310_impl.h:127-131`); `ReduceSum` `float` (`:204`) vs five types (`reduce_sum_c310_impl.h:116-117`).
Separately, one file against itself: `ReduceAny`'s two overloads are documented `float/uint8_t` at
`reduce.h:306` and `float` at `:331`. Carried by `950:0406`. → 950 book. Disposition: `float` is a
consistent reading of the doc comments as a portable intersection; the row records the gap, not an error.

## C-950td-010 · 512 is a cache line in one gather formula and a workspace row cap in another
- **analysis shelf** `tiling/gather/fallback/tiling-flow.md:105` — `CACHELINE = 512  // 字节`, used to
  derive `carryNumAlign = CACHELINE / dtypeSize` inside the `needTrans` UB feasibility test (`950:0148`).
- **implementation shelf** `reference/gather/templates/gather_elements_v2_route.template:51,62-63` —
  `constexpr uint64_t kCachelineElementsBytes = 512;`, used to cap the per-core workspace row count at
  `min(512 / xDtypeSize, CeilDiv(idxPostDim, coresPerGroup))` inside the *cost* model.
One number, two formulas, two purposes, no cross-reference; neither file derives 512. Carried by
`950:0407`. → 950 book.

## C-950td-011 · The gather cost model changes units at its own branch
`reference/gather/templates/gather_elements_v2_route.template:66-77`. When
`idxPreDim × idxPostDim <= coreNum` the profitability test compares **element counts**
(`xElementCount > idxPreDim*idxPostDim*(idxGatherDim + xGatherDim)`), with no dtype size anywhere;
otherwise it compares **bytes** (`directTraffic > internalTraffic`, both scaled by dtype sizes). A case
sitting near the branch can flip sense for a reason unrelated to its data volume. Restated in prose at
`templates/gather_elements_v2_transpose.md:46-60`. Carried by `950:0407`. → 950 book.

## C-950td-012 · The gather router short-circuits on `dim == last` before the cost test its own template document demands
- `templates/gather_elements_v2_route.template:96-98` — `if (p.isLastDim) { return
  GatherElementsV2Route::LAST_DIM; }`, the router's first statement, before any cost model runs.
- `templates/gather_elements_v2_last_dim.md:57-65` — LastDim must be selected by comparing
  `resident_cost` against `direct_cost`, and "成本模型只用于筛选，不能替代代表 case A/B".
- `guide.md:235` — "启用 LastDim 前还要比较整行 resident 流量与 direct random GM 成本，不能只判断
  `dim==last`。"
The shipped router does exactly what two of its own documents forbid. Carried by `950:0407` and
`950:0411`. → 950 book.

## C-950td-013 · The gather index page's headline evidence and its companion file's per-case detail imply opposite recommendations
- `reference/gather/guide.md:116` — SIMT measured "P4(33.5M int32): 128ms→3.6ms (**35.7×**)；
  P6(67.1M int8): 231ms→5.3ms (**43.2×**)", presented as the family's evidence for SIMT.
- `templates/gather_elements_v2_transpose.md:79-83,96-100` — for what this book infers are the same two
  cases (case4, case6), the official path is a **physical** `Transpose×3`, at 1677.7 µs and ~2.10 ms —
  2.13× and 2.55× faster than the SIMT figures the index advertises.
Neither file references the other's numbers and neither states the case identity. Carried by `950:0408`.
→ 950 book. Note: the identification P4=case4 / P6=case6 is `950:0408`'s **inference**, not upstream's
statement, and `950:0408` §4 arm 3 is what would settle it.

## C-950td-014 · A fourth gather template count
`950:0150` records the analysis shelf calling its fallback `通用六模板` while tabling seven in one place
and nine in another. The implementation shelf's inventory (`reference/gather/guide.md:84-178`) is a
fourth answer: **eight numbered sections plus a ninth entry (LastDim) that appears only in the selection
table** — of which eight have kernel files and one (small-GD tiled full-load) explicitly has none
(`templates/gather_elements_small_gd_tiled.md:7`). Two of the nine — LastDim and small-GD — are named
nowhere in the analysis shelf's gather subtree. Carried by `950:0409`. → 950 book.

## C-950td-015 · The gather family's document order is the reverse of its own measured order
Document order for a `PER_ELEMENT` `dim != last` case that fails the transpose gate is
transpose → Scalar → SIMT (`templates/gather_elements_v2_scalar.md:1,25`). The one case the family
publishes for those paths measures `small-GD 7.10 µs < SIMT 16.99 µs << Scalar 388.69 µs`
(`gather_elements_v2_scalar.md:91`, restated `gather_elements_small_gd_tiled.md:87`) — Scalar is 22.9×
the SIMT time. Upstream states the rule that follows (`Transpose UB 不够只能说明 Scalar"可用"，不能说明
它"更快"`, `:27`) and forbids generalising the shape. Carried by `950:0410`. → 950 book.

## C-950td-016 · The gather router's own four constants fail the rule the family states four times
`950:0412` records four prohibitions on case-derived routing predicates. The shipped router
(`reference/gather/templates/gather_elements_v2_route.template:48-51`) hardcodes `kPostDimLimit = 32`,
`kTransposeLen = 16`, `kInternalUbLimitBytes = 120000`, `kCachelineElementsBytes = 512`, none with a
derivation from the six admissible sources the rule names (`guide.md:186`). `120000` is not a UB
fraction, not a power of two, and not a multiple of any alignment quantum in the family. By the rule's
provenance test all four are inadmissible; by its letter all four survive, since none is a case ID, an
output size in MiB, or a shape. Carried by `950:0412`. → 950 book.

## C-950td-017 · Unequal non-gather shapes disqualify one template and the selection tables never say so
`reference/gather/templates/gather_elements_v2_route.template:39,85` — `nonGatherShapesEqual` is a
routing input, and `false` disqualifies the in-kernel transpose outright. The family's selection tables
(`guide.md:163-178`, `:207-220`) route by `gatherMode`, `dim` position and size, and never mention the
shape relation. So a `torch.gather` with `index.shape[i] < x.shape[i]` on a non-gather axis has fewer
templates available than one with equal shapes, and no table states it. The other templates' tolerance
of unequal shapes is documented nowhere. Carried by `950:0413`. → 950 book.

## C-950td-018 · The broadcast UB-split formula: two guards present in one shelf's copy, absent in the other's
- **design shelf** `ascendc-tiling-design/references/broadcast/patterns.md:100-123` — carries
  `curProduct = 1`, `ubSplitAxis = 0`, an `allFit` flag with a post-loop branch dividing by `dims[0]`,
  and a `shapeLen == 1` special case setting `ubFormer = maxElemNum` directly.
- **analysis shelf** `ascendc-perf-optimize/references/tiling/broadcast/fallback/tiling-flow.md:79-93` —
  identical `maxElemNum`, identical loop body, identical `ubOuter`/`ubTail`; **neither guard**, and
  neither initialiser.
Both guards fire exactly when the loop's `break` never executes. Carried by `950:0414`. A prior survey
recorded this divergence as one extra branch; re-verification found two (`SR-950td-02`). → 950 book.

## C-950td-019 · The trailing-axis broadcast gate: a data cache, a cache line, and a units mismatch
- **design shelf** `references/broadcast/patterns.md:76` — "尾轴 >= dcache/2", no value, no units.
- **implementation shelf** `reference/broadcast/broadcast_design.md:30,132`,
  `ub_broadcast_design.md:17` — "尾轴字节 ≥ dcache/2(~4096B)", in **bytes**, the value attributed to a
  源码注释 rather than to a measurement; `code/broadcast_add_tiling.cpp:63` says "dcache 阈值用平台查询"
  and takes it as a caller parameter.
- **analysis shelf script** `tiling/broadcast/fallback/script/broadcast_tiling.py:31,354` —
  `output_dims[last_axis] >= CACHE_LINE // 2` with `CACHE_LINE = 128  # bytes, OneDim alignment`, i.e.
  an **element count** against half a cache line. `dcache` appears nowhere in that subtree.
Three divergences at once: constant (~4096 B vs 64), units (bytes vs elements), object (data cache vs
cache line). Carried by `950:0415`. → 950 book.

## C-950td-020 · Does the outer-axis broadcast case also produce NaN?
- `reference/broadcast/ub_broadcast_design.md:11` heads **both** listed counter-examples as
  "两种会出 nan 的反例", of which item 1 is `brcInTile=false` (broadcast axis strictly outer).
- `broadcast_design.md:94` gives item 1's justification with **no** mention of NaN
  ("UB/NDDMA 只在 tile 内展开，外层轴只能靠 offset 寻址"), and attributes NaN only to item 2 at `:95`.
One document attributes the NaN to two conditions, the other to one. The distinction decides whether a
mis-routed `!brcInTile` case is a correctness failure or a wasted Vector pass. Carried by `950:0416`.
→ 950 book.

## C-950td-021 · The broadcast sample violates two of its own family's buffer rules
- `reference/broadcast/ub_broadcast_design.md:66` requires the ③ compact source to be a
  `TQue<VECIN, 2>`, citing an unsynchronised MTE2↔V WAR and 非确定性 FAIL; `:65` requires one `bufSrc`
  per ③ input for binary operators.
- `code/broadcast_add_kernel.cpp:104` declares a single `TBuf<TPosition::VECCALC> bufSrc_`, obtained by
  `Get<T>()` inside the per-tile loop (`:94`), in a class that uses `TQue<..., 2>` for its other three
  buffers (`:102-103`).
Carried by `950:0417`. → 950 book.

## C-950td-022 · One failure, two incompatible prescribed fixes, and the shipped code satisfies only one
- `reference/broadcast/onedim_design.md:109` — "**永不靠减法反推末核长度**", prescribing a global
  `[blockStart, blockEnd)` clamp.
- `advanced_tiling.md:59` — the same negative-tail failure attributed to operation *order*, prescribing
  "必须先定 blockFormer 再回收核", with a worked counter-example (`totalTiles=100, coreNum=64 →
  blockTail=-26`, re-derived and correct).
- `code/broadcast_common.h:325` — ships the subtraction, in `blockFormer`-first order, with the comment
  "尾核块数 ∈[1, blockFormer]" asserting the property `advanced_tiling.md:59` shows can fail.
Compliant under one prohibition, non-compliant under the other. Carried by `950:0417`; reachability is
`Q-950td-07`. → 950 book.

## C-950td-023 · A measured optimisation table that overturns one of its own rows in place
`reference/scan/templates/usage_guide.md:50-51` — "注意倒数第三行**推翻了第五行**：`fp16/bf16 原生 16
位比较` 是在 Kogge-Stone 时代测出的收益，换成 lane 并行扫描后完全反转". The 12-row trajectory table at
`:33-46` therefore contains two rows whose conclusions are mutually exclusive, both presented as
measured steps, with the retraction stated only in a note below the table. Cited by `950:0418`.
→ 950 book. Disposition: the retraction is exemplary practice; the row remaining in the table is the
contradiction.

## C-950td-024 · Three conversion summary figures each over-reach the table printed beside them
- `conversion/transpose_small_shape.md:192` "慢 3-10 倍" vs its table `:288-293`, whose worst geomean
  `0.17x` inverts to **5.9×** and whose best is 3.1× — the 10 is produced by no row.
- `conversion/transpose_n_last.md:267` "慢 2-5 倍" vs its table `:262-263`, which gives **3.04×** and
  **5.04×** — the 2 is produced by no row.
- `conversion/transpose_small_shape.md:196` "6.25%" is derived as `2/32` for a 2-byte element, and the
  per-dtype table at `:199-202` gives 3.1% / 6.25% / 12.5%; three restatements
  (`guide.md:35`, `:61`, `transpose_small_shape.md:297`) drop the dtype.
Carried by `950:0419`. Scope correction owed to `950:0164`, which carries the flat form: `Q-950td-08`.
→ 950 book.

## C-950td-025 · The conversion family's fastest measured implementation is absent from its own roster
`conversion/transpose_n_last.md:265` — `TQueBind 4D` at 13.1 / 15.4 µs, the fastest of four rows,
beating the baseline (19.4 / 24.6), the shipped N_LAST (58.9 / 124.1) and the projected merged N_LAST
(~19 / ~25). It has no tilingKey, no template, no routing condition, and does not appear in
`guide.md:42-52`'s nine-strategy table. Carried by `950:0420`. → 950 book.

## C-950td-026 · `DAV_5102` — a token in a shipped gate constant that is defined nowhere
`conversion/transpose_vconv_021.md:81` and `transpose_small_shape.md:53` —
`SMALL_SHAPE_BYTES_THRES_HOLD_DAV_5102_021 = 70000`, one of four gates admitting the 021 VCONV
strategy. `grep -rn DAV_5102` over the whole shelf returns only those two lines. The family's other
architecture spellings are `DAV_3510` / `dav-3510` / `arch35` / `3510` / `dav3510`, plus `ascend950` in
its two measured tables. Under `950:0202`'s rule the token's first two digits would name `arch51`,
which no upstream document mentions. Carried by `950:0421`. → 950 book.

## C-950td-027 · A conversion reference file written against a directory layout that does not exist
`conversion/transpose_tiling_data.md:15-23` (and `:3`, `:7`, `:98`, `:141`, `:161`) links its nine
strategies to `kernel/arch35/*.h` and `templates/transpose_<strategy>.md`, and cites
`templates/transpose_README.md`. Verified at drafting time: no `kernel/` directory exists, no
`templates/*.md` files exist, and no `transpose_README.md` exists. The real documents are at
`conversion/*.md` and the real templates at `templates/dav3510/*.template`. Cited by `950:0421`.
→ 950 book.

## C-950td-028 · One scalar metric, three baselines and two targets, in two files by one author
- `reference/scalar/guide.md:5` — "典型占比超过 30%"
- `conv_scalar.md:95` — "→ 典型 Scalar Load/Store 占比 > 30%" (under the heading `优化效果示意`, `:87`)
- `conv_scalar.md:101` — "→ Scalar Load/Store 占比可降到 < 15%"
- `conv_scalar.md:158-159` — "Scalar Load/Store 占比 / 从 90%+ → 10% 以内"
30% cannot be a subset baseline of 90%+ for one metric on one code path. The partial mitigation
upstream does not state: `:159` covers three techniques and `:95`/`:101` cover one. Carried by
`950:0422`. → 950 book.

## C-950td-029 · A performance ranking whose bottom rung is the vendor's recommended usage
`reference/scalar/buffer_management_conversion_guide.md:126,128,165,194` ranks three buffer-management
styles "性能从高到低", placing `TPipe + TQue` last (`性能最低`). The same section calls that option
"AscendC 官方推荐用法" (`:215`), and the selection table recommends it for low-frequency loops
(`:221`). No quantity is attached to any rung, and the discriminating variable (loop frequency) is
itself unquantified. The middle rung additionally carries a correctness hazard the bottom rung does not
(`:366`). Carried by `950:0423`. → 950 book.

## C-950td-030 · Two internal inconsistencies in the scalar shelf's pipeline and event tables
- `buffer_management_conversion_guide.md:36` assigns `L0C→UB` to the `FIX` pipeline; `:37` assigns the
  same transfer to `MTE3`. Adjacent rows of one table.
- `:98` lists `MTE2_V → V_MTE2` and `:101` lists `V_MTE2 → MTE2_V`, each presented as the other's
  forward event, with no statement of which direction is canonical.
Cited by `950:0423`, which declines to rely on either table's directions. → 950 book.
