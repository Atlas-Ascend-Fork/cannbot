# Contradictions register — domain `950-fin` (wave 1.9, the final mining wave)

> **TRIAGED 2026-08-25**: every row below has a phase-2 disposition in
> `harvest/TRIAGE_DOMAIN_ROWS_20260825.md` (resolved / assigned-to-round / noted / blocked).
> Two rows were resolved by reading during the triage: C-950fin-027 (the duplicate class line IS
> present, template lines 245/248) and — in the rem register — C-950rem-012.

Same topic, different advice or numbers, across upstream sources — or across an upstream source and
the installed CANN toolchain. Recorded here and in the affected entries' §3; resolved only by a
procedure run on the named board (RULES.md Art. 7). **Every quote below was re-verified against its file at
drafting time**, not inherited from a card or a survey.

Scope of this register: `ops/ascendc-tiling-design/references/flashattention/` (3 files),
`references/matmul/` (2 files), `ops/ascendc-performance-best-practices/reference/elementwise/vector_efficiency_design.md`,
and `reference/scan/` (8 files), plus the installed toolkit at pin `cann-9.0.0-beta.2` where it was
consulted read-only. Entries carrying these rows are `950:0451`–`950:0488`.

Two rows are cross-origin (upstream vs the installed toolchain): `C-950fin-021` and `C-950fin-022`.
The rest are intra-repository, which per RULES.md Art. 3 means one origin disagreeing with itself — those
gain no authority from repetition and none is resolved by counting sites.

---

## FlashAttention family (tiling-design shelf)

### C-950fin-002 · The GQA row-order label and its formula point opposite ways
`references/flashattention/subfamilies.md:113` — `**mEff 行排布约定**(**Bq-major**)：
`row(g, i) = g × Bq + i`,即按 qHead 外、Sq 内排布`. The label says Bq-major; the formula makes `g`
slow-varying and `i` fast-varying, which by the usual convention is `g`-major; the prose
(`按 qHead 外、Sq 内`) agrees with the formula. One line, two conventions.
→ carried by `950:0452`. Resolvable by reading a shipped implementation, or on-card by `950:0452` §4 arm 3.

### C-950fin-003 · The family enumerates four slot semantics in one place and three in another
`design.md:114-117` lists four (cross-stage handshake, cross-task state, cross-loop self-read/write,
L1 rotation); `design.md §7.4`'s formula table (`:554-558`) governs three and omits L1 rotation;
`subfamilies.md:332-338` prohibits sharing across a *different* three (cross-core handshake, L1
rotation, V2 self-read/write). An implementation that separates exactly `§7.4`'s three and shares a
constant with the L1 rotation depth satisfies one statement and violates another.
→ carried by `950:0453`. On-card by `950:0453` §4 arm 4.

### C-950fin-004 · A matmul-wide invariant is parked in the attention file by upstream's own admission
`overview.md:176` — `本不变量根源在 Mmad 硬件约束,所有用 MX 类格式做 MatMul 的算子(不限 attention)
都受其约束。当前暂放本文件,理想归属是独立的 MatMul methodology(暂未建)。` The shelf's own matmul
family (`references/matmul/`) is scoped to mxfp8 + eltwise fusion and does not carry the rule, so the
document that most needs it does not have it.
→ carried by `950:0455`. On-card by `950:0455` §4 arm 4 (the same Mmad outside an attention harness).

### C-950fin-005 · The FA family forbids bare numbers in formulas and states its only measured figure as one
`design.md:208` — `所有 buffer 公式中只允许出现:运行时查询的硬件常量、Tiling 决策出的基本块、dtype
字节宽——**禁止**直接写数字。` against `design.md:80` — `streaming 在小 D 下退化为单 chunk loop,
实测开销小(典型 ≤ 5%…)`, and `subfamilies.md:122` — `mPad > 16`, a bare fractal height. The rule
governs buffer formulas and the numbers are elsewhere, so this is a register mismatch rather than a
direct violation; it is filed because the same document is the corpus's strictest on this point.
→ carried by `950:0456`, `950:0462`.

### C-950fin-006 · The one quoted toolchain error in the FA family has its architecture redacted
`subfamilies.md:295` — `错误归因为"DAV-XXXX builtin 不接受 bf16 ptr"是反模式`. `DAV-XXXX` is
upstream's own redaction. The family names `A5` at `design.md:94`, `:525`, `:617` and
`subfamilies.md:195`, so the one place a real architecture token would be evidence is the one place it
is removed.
→ carried by `950:0460`. On-card by `950:0460` §4 arm 1 (capture the verbatim diagnostic).

### C-950fin-007 · Open one dimension at a time, and also test two at once
`design.md:487` — `**禁止**:多维度同时打开,精度回归出错时无法定位维度。` against
`subfamilies.md:122-127` — the mandatory three-case set whose case (c) is `两者同时打开`. They
reconcile only under a reading neither states ("one at a time, then also the product").
→ carried by `950:0462`.

### C-950fin-008 · The fire-and-forget property is stated for the mode this book does not use
`design.md:533` — `` `mode=2 CrossCoreSetFlag` 是 fire-and-forget,不阻塞后续操作 → 不能依赖它做
back-pressure `` — while `design.md:525` recommends `mode=4` on A5. Whether `mode=4` blocks is not
stated anywhere, so the back-pressure warning's scope on 950 boards is unknown.
→ carried by `950:0463`. On-card by `950:0463` §4 arm 3.

### C-950fin-009 · The shipped toolchain gates on architecture numbers our vocabulary map does not list
`/usr/local/Ascend/cann-9.0.0-beta.2/asc/include/interface/kernel_operator_common_intf.h:43` gates on
`__NPU_ARCH__ != 1001 && __NPU_ARCH__ != 2002`;
`asc/include/interface/kernel_operator_vec_reduce_intf.h:143` gates on
`__NPU_ARCH__ == 3510 || == 5102 || == 3003 || == 3113`. `form/CONVENTIONS.md` maps 2201 → DAV_2201
and 3510 → DAV_3510 and knows none of 1001, 2002, 5102, 3003, 3113. Five identifiers in the shipped
toolchain are unmapped by our own table.
→ carried by `950:0463`, `950:0480`; neighbours `950:0203`, `950:0421`, `C-950bp-011`.
Resolvable by file read: no device needed, and no procedure is proposed because the resolution is a
correction to `form/CONVENTIONS.md` (wave-2 controller's call, not this domain's write partition).

### C-950fin-010 · The PipeBarrier acceptance thresholds are bare numbers in the document that forbids them
`design.md:598` — `冗余率 `(实际 / 设计 - 1) < 30%`,达到 50% 视为性能阻塞项` — no derivation, no
case, no board, no utilisation figure, in the same file as `:208`'s prohibition (see `C-950fin-005`).
→ carried by `950:0464`.

### C-950fin-011 · One notation is used once and never defined, at the point the stage order looks illegal
`design.md:517` — `loop body 内 stage 顺序 `C1(本轮) → V2(上两轮) → V1(上一轮) + C2(上一轮)``. The
`+` joins two stages of the same round on two core types; `overview.md:110`'s invariant I1 requires
`V1` before `C2` within a block. Consistent if the `+` means "issued in the same beat with the
cross-core handshake enforcing order", which upstream does not say.
→ carried by `950:0465`. On-card by `950:0465` §4 arm 4.

### C-950fin-012 · The dtype case is filed under a test it does not need
`design.md:414` files `dtype`(fp16/bf16) under the "introduces or removes a TBuf member" criterion,
but gives its reason as `影响 typedef 与 Mmad 模板参数同型链` — a template-parameter constraint
(`950:0460`), not a buffer one, and one that cannot be a runtime `if` at all.
→ carried by `950:0466`. On-card by `950:0466` §4 arm 3.

### C-950fin-013 · One cross-reference sentence carries two bad section pointers, one of them circular
`overview.md:225` — `此清单决定 design.md §6 编译宏分类…与 §1.6 校验门禁规划`. Compile-macro
classification is `design.md` **§5** (`design.md:390`); its §6 is Host Tiling (`:424`). And `§1.6`
does not exist — `design.md`'s §1 is a nine-row table whose precision-gate row points back to
`overview §4.4`.
→ carried by `950:0466`. Resolvable by file read.

### C-950fin-014 · One taxonomy tick over-reports, and it is the most-requested operator's row
`ops/ascendc-tiling-design/SKILL.md:17` — `| MatMul 矩阵乘类 | … | MatMul, BatchMatMul |
✅ [场景路由](references/matmul/patterns.md)（mxfp8 + eltwise 融合；其它 matmul 形态规划中） |` — the
`✅` is the same glyph as the fully-covered rows, and only the parenthetical says the two named example
operators are out of scope. The Conversion row (`:15`) marks the same situation `⚠️`.
→ carried by `950:0467`, cited by `950:0469`. On-card only as a routing experiment (`950:0467` §4 arm 3).

---

## Cross-shelf

### C-950fin-001 · GroupNorm has two family assignments and both destinations are empty
`ops/ascendc-tiling-design/SKILL.md:20` — `| NN 神经网络类（其它）| … | GroupNorm 等非 attention |
📋 规划中 |` (explicitly **non**-attention, no directory) against
`ops/ascendc-perf-optimize/references/tiling/index.md:24` — `| FA FlashAttention 类 |
FlashAttention, GroupNorm | [fa/](fa/) |`, whose target declares itself a placeholder
(`references/tiling/fa/fallback/index.md:3`, already carried at `950:0169`). The FA family's own
subfamily selection criteria (`flashattention/overview.md:191`) are all attention shape parameters and
cannot classify a normalisation operator.
→ carried by `950:0468`; cites `950:0169`. On-card by `950:0468` §4 arms 1-2.

---

## MatMul fusion family (tiling-design shelf)

### C-950fin-015 · One alignment is a literal in one file and dtype-derived in the other
`references/matmul/patterns.md:79` — `curNUbAlign = AlignUp(curN, 8)` with `:90`'s
`32B（即 8 个 float）`, against `matmul-fusion-design-template.md:389` — `| S4 |
`ALIGN_ELEM = 32/sizeof(float)` | dtype 改变后对齐错误 | 改为 `sizeof(DataType)` |`. The two also
apply to different quantities (`curN`, a per-tile extent, versus `baseN`, a tiling base block); whether
they must agree is not stated.
→ carried by `950:0471`. On-card by `950:0471` §4 arm 4.

### C-950fin-016 · A UB budget in element counts is compared against a byte capacity
`patterns.md:104-109` — `UB 总用量 = matmulArea + stageNum × stageSize_` … `必须满足 `UB 总用量 ≤
TOTAL_UB_SIZE``. `matmulArea` is `CeilDiv(baseM, taskRation) × baseNAlign`, a product of two extents;
`matmul-fusion-design-template.md:214` states its unit explicitly — `matmul 结果占用 UB 元素数`.
`TOTAL_UB_SIZE` is used as bytes at `template:219` and `:231`. Dimensionally unsound as written; at
FP32 it under-reports occupancy fourfold.
→ carried by `950:0472`. On-card by `950:0472` §4 arm 2.

### C-950fin-017 · One area is charged `sizeof(DataType)` in one line and `sizeof(float)` two lines later
`matmul-fusion-design-template.md:219` — `lastUBBytes = UB_SIZE - matmulArea × sizeof(DataType)`
against `:231` — `matmulArea × sizeof(float) + stageNum × stageSize_ × sizeof(DataType) ≤
TOTAL_UB_SIZE`. The layout diagram (`patterns.md:74-83`) and the AIV buffer table (`:140`) both put
that region at `sizeof(float)`, so `:231` matches the layout — but Art. 7 leaves the resolution to a
run, not a reading.
→ carried by `950:0472`. On-card by `950:0472` §4 arm 1 (echo the region's device-side extent).

### C-950fin-018 · Two buffer naming schemes for one UB layout, with no mapping
`patterns.md:146-149` names `resultLocal_`, `secondLocal_`, `thirdLocal_`;
`matmul-fusion-design-template.md:226-229` names `cLocal_`, `dLocal_`, `dLocal1_`, `dLocal2_`,
`cLocalTmp_`; the template's own buffer table (`:201-205`) maps to the second list and not the first.
The two lists also disagree on the partition *count* per `stageNum`.
→ carried by `950:0473`. On-card by `950:0473` §4 arm 3.

### C-950fin-019 · `DataCopyPad`'s length parameter must be a 32-byte multiple, and must be the effective length
`matmul-fusion-design-template.md:91` — `DataCopyPad 要求 `blockLen` 为 dataBlock（32B）倍数` against
`:126` — `| DataCopyPad blockLen / 计算 API count | ✓ 用有效长度 | ✗ 用对齐长度 |` and
`patterns.md:93` — `rowBytes = curN × sizeof(float)` for a `curN` expressly not a multiple of 8
floats. At `curN = 15`, `rowBytes` is 60 bytes: an effective length that is not a multiple of 32.
→ carried by `950:0475`. On-card by `950:0475` §4 arm 2. **If this resolves to `:91`, `950:0471`'s
ODD-N path is unimplementable as written and that entry acquires a scope limit it does not carry.**

### C-950fin-020 · The epilogue waits on a cross-core flag, and contains none
`matmul-fusion-design-template.md:177` — `5.1 CrossCoreWaitFlag(AIC→AIV)   — 等待数据就绪` under the
heading `5. AIV Epilogue`, against `:377` — `- [ ] AIV Epilogue PipeBarrier 仅在跨 pipe 依赖处添加；
Epilogue 内**无** `CrossCoreWaitFlag``. A layer reading reconciles them (the flags live in the
`[PATTERN]` kernel/block layer, visible at `:300-302`; the `[USER]` epilogue class has none) and
upstream never states which layer owns the wait. Separately, `:377` is a **compound checkbox** — a
`PipeBarrier` placement rule and the wait prohibition on one tick.
→ carried by `950:0476`. On-card by `950:0476` §4 arms 1-2. **Not asserted as a self-contradiction.**

---

## Elementwise (performance-best-practices shelf) — cross-origin

### C-950fin-021 · Counter mode: every call spelling in the shelf matches no symbol in the installed toolkit
`reference/elementwise/vector_efficiency_design.md:21`, `:106-110`, `:162` use
`SetMaskCount(dataSize)` and `SetMaskMode(NORMAL)`. Installed toolkit at pin `cann-9.0.0-beta.2`:
`asc/include/interface/kernel_common.h:169` declares `SetMaskCount()` with **no parameters** and `:174`
declares `SetMaskNorm()`; a search for `SetMaskMode` across the whole installed tree returns **zero
files**. The shipped idiom
(`asc/impl/adv_api/detail/quantization/quant/ascend_quant_pre_impl.h:345,353,382-383`) is five calls —
`SetMaskCount()`, `SetVectorMask<T, MaskMode::COUNTER>(0, n)`, the operation, `SetMaskNorm()`,
`ResetMask()` — with a `splitSize` loop and a remainder, the structure the shelf says counter mode
removes.
→ carried by `950:0477`. **Cross-origin.** The two origins agree the mechanism exists.
On-card-free: resolvable by compiling three statements (`950:0477` §4 arm 1, no device).

### C-950fin-022 · The two-stage reduction's reference code calls two void APIs as value-returning functions
`vector_efficiency_design.md:99-100` — `float sum = WholeReduceSum(src, dataSize);` and `:139-140` —
`blockSums[i] = BlockReduceSum(src + i * blockSize, blockSize);`. Installed toolkit,
`asc/include/interface/kernel_operator_vec_reduce_intf.h:46-49` and `:143-153`: both are `void`
templates taking dst and src `LocalTensor`s plus five integers, including a `repeatTime` that makes the
printed per-block loop unnecessary. No overload takes a pointer and a length; none returns a value.
`repeatTime` is asserted to `[0, 255]` (`asc/impl/basic_api/kernel_operator_vec_reduce_intf_impl.h:342`).
→ carried by `950:0478`. **Cross-origin.** The 20-40% latency claim stands or falls separately and is
not touched by this row. Resolvable by compiling (`950:0478` §4 arm 1, no device).

---

## Scan family (performance-best-practices shelf)

### C-950fin-031 · One optimisation of one case is published as 34, 56 and 59 µs
Same case (`R = 1000003`), same baseline (2002 µs), same change (phase A made read-only), three files:
`reference/scan/guide.md:214` — `降到 34 µs`; `templates/cum_core_partition_scan.md:49` — `降到 56 µs`;
`templates/usage_guide.md:177` — `降到 59 µs（0.01x → 0.22x）`. The second and third are near-identical
sentences differing in one number. No configuration, date, repetition count or variance accompanies
any of them, and the shelf's own local-timing floor is ~30 µs (`950:0418`), comparable to the spread.
→ carried by `950:0482` (this is that entry's primary row). On-card by `950:0482` §4 arms 0-2.

### C-950fin-023 · One ping-pong gain is `12~31%` in the template and `4%~31%` in the index
`templates/cum_row_kogge_stone.md:112` — `实测快 12~31%` against `guide.md:147` — `实测快 4%~31%`,
in sentences whose occupancy figures (101%, 132-173%) agree exactly. The shelf's own six-case table
(`cum_tile_resident_scan.md:38-45`) gives −25, −31, −31, −12, −2, −0.3%: `12~31%` is exactly the top
four rows' range; `4%~31%` matches no subset — there is no 4% row.
→ carried by `950:0482`. On-card by `950:0482` §4 arm 3.

### C-950fin-024 · One two-row-interleave gain is `8%~18%` in two files and `约 3%` in a third
`templates/cum_lane_parallel_scan.md:131` — `实测再快 8%~18%（R 越小、行数越多收益越大）`;
`guide.md:271` — `再快 8%~18%`; `templates/usage_guide.md:125` — `实测再快约 3%`. The file that differs
is the integration guide a consumer reads first, and it is the only one without the parameter
dependence.
→ carried by `950:0482`. On-card by `950:0482` §4 arm 3.

### C-950fin-025 · The bank-conflict predicate is power-of-two in three places and 16-byte-multiple in three
Power-of-two: `templates/cum_lane_parallel_scan.md:82` (`步长取 2 的幂时…全撞在同一批 bank 上`),
`guide.md:187`, `guide.md:270`. Multiple-of-16: the same template's remedy rule at `:86`, its shipped
code at `:94` (`return (s * cBytes % 16 == 0) ? (s | 1) : s;`), and `templates/usage_guide.md:121-122`.
Every power of two above 16 bytes is a multiple of 16, so the two differ on strides of 48, 80, 112
bytes. **The single measurement adjudicates neither**: `R=4096` bf16 `S=32` gives a stride of 64 or
128 bytes depending on the comparison type, and both values satisfy both predicates.
→ carried by `950:0483`; `950:0133` carries the 16-byte form alone, from the analysis shelf.
On-card by `950:0483` §4 arm 1 (the 48/80/112 group).

### C-950fin-026 · One template says `Compare` makes NaN sticky, and its own guide records that failing a case
`templates/cum_streaming_scan.md:31` — `| **NaN 传播** | `Compare` 对 NaN 返回 false → NaN 被取用并
向后传播，对齐 torch |`, with `GT` and nothing else (`:29`, `:30`, `:38`, `:43`). Against
`templates/usage_guide.md:236-239` — `NaN 必须显式粘滞：只写 `Compare` 不够…正解是再加一路
`Compare<NE>(x, x)`…（实测：只用 `GT` 时 20 用例中 case 14 精度失败。）`. The third template
implements the guide's form (`cum_tile_resident_scan.md:103`, `takeB = (x <= curMin) || isNaN(x)`).
Tie semantics diverge too: `GT` (`cum_streaming_scan.md:30`) vs `LE` (`usage_guide.md:235`).
And the template the guide marks `勿用于性能路径` (`:14`) is the one its own `CUMMIN_ENTRY` macro
instantiates four times (`:204-210`) — the second instance in this repository of the species
`950:0136` records.
→ carried by `950:0484`; `950:0139` carries the make-NaN-sticky rule from the analysis shelf.
On-card by `950:0484` §4 arms 1-2.

### C-950fin-027 · The template register says the defects are fixed, and its last item says one may still be present
`templates/usage_guide.md:274` — `模板文件中已修复` against `:309` — `cum_tile_resident_scan.template
中**可能有**重复的 `class TileResidentScan {` 行，使用前删除重复行。`
→ carried by `950:0485`. Resolvable by file read (`950:0485` §4 arm 1).

### C-950fin-028 · Six modes are claimed and five are named; `mode 2` appears nowhere in the shelf
`templates/usage_guide.md:299` — `使用 `scan_cummin_tiling.h` 的 `CalcTiling()`（含 6 种 mode 选择…）`.
Named across the shelf: mode 0 (`:45`), mode 1 (`:287`, `:304`), mode 3 and 4 (`:162-163`), mode 5
(`:302`). A search of the whole scan shelf for `mode 2` returns nothing.
→ carried by `950:0487`. Resolvable by reading a shipped `CalcTiling()` (`950:0487` §4 arm 2).

### C-950fin-029 · The header the guide says to use is in no roster row and no directory of the shelf
`templates/usage_guide.md:299` names `scan_cummin_tiling.h`. The roster (`:9-19`) has
`scan_tiling.template` → `scan_tiling.h` (`host 侧流式 tiling 选型`) and no `scan_cummin_tiling`.
Filed with the shelf's two other dangling references: `:60` cites a `§1.2` that its own section
numbering does not contain, and `templates/cum_tile_resident_scan.md:121-123` sends the reader to
`cum_core_partition_scan.md` for an `N > 1` generalisation, in a file whose trigger is stated
`（N == 1 分支内）` at `:27` and which has no such section.
→ carried by `950:0487`. Resolvable by file read.

### C-950fin-030 · Three architecture spellings in one file, one of them a path a consumer copies
`templates/usage_guide.md:5` — `保留 `dav310/` 子目录结构` (a directory name carried into the
consumer's tree); `:198` — `用 `__NPU_ARCH__` 把 arch35 引入`; `:217` — `先核对 `--npu-arch=dav-3510``.
`dav310` against `dav-3510` is the fourth instance of this species in the corpus and the only one where
the mismatched spelling is a path.
→ carried by `950:0487`; neighbours `950:0346`, `950:0421`, `C-950fin-009`.

---

## Register summary
31 rows, `C-950fin-001` … `C-950fin-031`. Two are cross-origin (021, 022); the rest are
intra-repository. Nine are resolvable by file read or by a compile with no device (009, 013, 021, 022,
027, 028, 029, and partly 002, 030); the rest need a run on a named 950 board and each names the entry
whose §4 proposes it. **No row is resolved here.** Art. 7: the disagreement is recorded, and the
resolution is a procedure on a named board — never the more plausible author.
