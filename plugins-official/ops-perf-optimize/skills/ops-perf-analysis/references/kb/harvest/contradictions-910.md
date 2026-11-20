# Contradictions register — book-910 domain (DAV_2201 / Atlas A2+A3 / 910B family)

> **TRIAGED 2026-08-25**: every row below has a phase-2 disposition in
> `harvest/TRIAGE_DOMAIN_ROWS_20260825.md` (resolved / assigned-to-round / noted / blocked).

Same topic, different advice or numbers, across upstream sources — found by the 2026-08-24 book-910
harvest. Row format follows `harvest/CONTRADICTIONS.md`; IDs are domain-scoped (`C-910-NNN`) per the
plan's 2026-08-24 amendment item 7, and this file is merged into the shared register by the
controller in wave 2.

**Every quote below was re-verified against the file at harvest time** (line numbers included).
Pre-existing rows C-001…C-009 in the shared register are **cited, never re-filed** — C-001 is
carried by entry 0007 and C-003 by 0003.

Per RULES.md Art. 7 none of these is adjudicated here. Each names the procedure that would resolve it,
and each is cited from at least one entry.

---

## C-910-001 · UB bank structure: one geometry claimed for 910B *and* 950, contradicted by a per-arch table
- `ascendc-performance-analysis/references/metrics_reference.md:162-169` — heading
  "### 3.5 UB Bank 结构（910B/950/A2/A3）" over a **single** structure: "总 bank 数: 48 / bank group:
  16 组（每组 3 个 bank）/ 单 bank 大小: 128 行 × 32B = 4KB / 每周期访问: 每个 bank group 1 行（32B）"
- `ascendc-performance-best-practices/reference/common/ub_resident_design.md:37-38` — a **two-row**
  per-architecture table: "| DAV_2201 | 192 KB | 48 | 16 | 3 | 4 KB (128 行) | 32 B |" and
  "| DAV_3510 | 256 KB | 16 | 8 | 2 | 16 KB (512 行) | 32 B |"

The **910 rows agree exactly** (48 banks / 16 groups / 3 per group / 4 KB / 32 B). The conflict is
the *scope claim*: metrics_reference asserts one geometry covers 910B and 950 together, while
ub_resident gives 950 a different geometry entirely (16 banks of 16 KB, 8 groups of 2). One of the
two is wrong about 950, which withdraws metrics_reference §3.5 as a check on our 910 row even though
it states the same numbers — same repo made it one origin anyway (STRATA S2), and this makes it a
weak one.

Also visible in the same ub_resident row and **not this book's to resolve**: DAV_3510 UB stated as
**256 KB**, where `npu-arch` gives 248 KB. That is a new instance of the C-004 / C-006 family, in a
skill those rows do not cover. → book-950.

→ **910 side resolvable on-card**: the `blk_stride` conflict sweep of entry 0013 §4 locates the
conflict period; period 16 confirms the 910 geometry, period 8 would mean the per-arch table is
inverted. Cited by 0013, 0014.

## C-910-002 · 910B usable core count: a range that excludes the per-part figures
- `ops-profiling/SKILL.md:215` — "| **Block Dim** | 等于可用核数（**910B: 20~40 核**） | 远小于
  可用核数 | Block Dim = 1 |"
- `ascendc-performance-analysis/references/metrics_reference.md:130-131` — "| 910B1/B2 | **24** |
  **48** | 1:2 | 分离模式 |" and "| 910B3 | **20** | **40** | 1:2 | 分离模式 |"
- `npu-arch/references/npu-hardware-params.md:132` — "| DAV_2201 | Ascend910B2 | **24** | **48** |
  1.8 GHz | 192 MB | 64 GB |"

The 20–40 range spans 910B3's pair exactly and **excludes 910B1/B2's 24/48 at the upper end**. So
upstream carries three shapes of one fact: per-sub-model pairs, a single-SKU example, and a range
that contradicts the pairs. Whether "20~40" means AIV only, AIC only, or a span across sub-models is
not stated — and each reading gives a different answer.

→ resolvable on-card, but **needs more than one physical part**: entry 0009 §4 queries
`GetCoreNumAic/Aiv()` per named board with the `npu-smi` board string on the same line. A
single-part reading is consistent with every version above and must be recorded INCONCLUSIVE.
Cited by 0009; gates 0008 (whose checker deliberately tests the 1:2 ratio, not absolute counts),
**2026-08-25 (0009 §6):** measured on the one installed part: 910B2 → 24/48, NpuArch 2201; the installed
ini set says B1/B2/B2C 24/48 and B3/B4/B4-1 20/40 under NpuArch=2201 — resolved for the measured part
and for what the toolkit ships; the runtime reading of a 20/40 part is out of fleet (INCONCLUSIVE by 0009 §5).
0011, 0054. Standing question Q-910-07.

## C-910-003 · DCache size: "16K / 32K" and "32KB 限制" ninety lines apart in one file
- `ascendc-performance-analysis/references/metrics_reference.md:178` — "| DCache | **16K / 32K** |
  64B (Cache Line) | 数据段缓存（TilingData 等） |"
- `ascendc-performance-analysis/references/metrics_reference.md:412` — "| DCache | **32KB 限制** | — |"

Two values 2× apart, in one document, with **no architecture stated for either** — in a file whose
other hardware tables carry per-chip columns. The row at :412 has an empty remedy column, unusual in
that table and suggestive of a row completed from the ICache row above it.

A capacity that appears in a denominator must be a single number: an expression of the form
`usable = ubSize − DCACHE` has two answers.

**RESOLVED 2026-08-25 on 910B2 (0018 §6):** DCache = **16 KB** by working-set knee (flat to 16 KB, ×10 at
20 KB, saturated from 24 KB), line **64 B** by the streaming stride step. `usable = ubSize − 16 KB` on this part;
the "32KB 限制" row is wrong for 910B2 and unattributed elsewhere.

**Same defect, same table, for ICache** (`:177` "16K / 32K" vs `:411` and `:212` "32KB"): recorded
in entry 0017 §3 rather than as its own row, because both readings there produce the same advice
(split a large kernel), whereas the DCache pair changes a budget.

Not filed against, but adjacent and **950-side**:
`ascendc-performance-best-practices/reference/gather/templates/gather_tiling.template:59,62` defines
`DCACHE_SIZE = 128 * 1024` and `DCACHE = 32 * 1024` in one translation unit, 4× apart, with only the
second used at `:241` and `:617`. That family is marked DAV_3510 in the skill's 適用架構 column.

→ resolvable on-card: entry 0018 §4 arm 2, a scalar-strided working-set sweep 4 KB … 128 KB reading
`SCALARLDST` per-element cost; the knee is the capacity. Cited by 0018. Standing question Q-910-04.

## C-910-004 · Two measured claims inside upstream's best 910 document do not reconcile
- `ascendc-performance-best-practices/reference/sort/radix_sort.md:36` — the vectorised binary
  search alone: "**收益**：消除低位标量扫描瓶颈（**实测 -9.4ms，-46%**）"
- `ascendc-performance-best-practices/reference/sort/radix_sort.md:319-327` — the five-version
  ladder: 版本一 23.4ms → 版本二 20.5ms → 版本三 20.8ms → **版本四 15.0ms** (16-step vectorised
  binary search + one-shot transform) → 版本五 13.2ms

Arithmetic performed at harvest: −46 % of 20.5 ms **is** −9.4 ms, so the percentage and the absolute
agree with each other. But −9.4 ms from 20.5 gives **11.1 ms**, and from 20.8 gives 11.4 ms —
neither is the ladder's **15.0 ms** for the version that introduces that same optimisation. A 3.6–3.9
ms gap.

The two claims are reconcilable only if they come from **different cases** — which is exactly what
the missing case identity (no N, no K, no dtype, no core count, no tool, no repeat count) prevents
anyone from checking. This is the strongest available argument in this book that case identity is
not optional: a document disciplined enough to publish a regression (版本三 is *slower* than 版本二,
and was kept) still produces numbers that cannot be reconciled without it.

→ **not resolvable as stated** — the upstream measurement is not reproducible, because its cases are
unidentified. What IS resolvable is the *technique-class ranking*: entry 0049 §4 fixes a case
identity upstream did not (N = 2²⁸ fp16, K = 100, all AIV cores, `msprof op --warm-up=10`, ten
launches, mean of last five) and tests whether algorithmic restructuring dominates pipeline work.
0049 §5 declares the percentages out of scope of its verdict for this reason. Cited by 0049, 0050.

## C-910-005 · "910C" is named as a platform by one document and absent from the declared truth source
- `ops-precision-standard/reference/golden/COMMERCIAL_OPS_PRECISION_DOCS.md:268` — "- <strong>训练
  </strong>：<br>910A、910B2、910B3、**910C**及后续平台<br>"
- `npu-arch/references/npu-hardware-params.md:15-21` — the complete §0 product mapping table, which
  declares itself the shared truth source for the chip list (`:11` "需要修改芯片清单时仅在此处更新")
  and contains **no 910C row**: DAV_2201 is Ascend910B1~B4, Ascend910B2C, Ascend910_93.

The term is used and nowhere defined. `form/CONVENTIONS.md` already rules that 910C must never be
written in a BOARD line on upstream evidence alone; this row is the evidence behind that rule, so a
later reader who finds "910C" in a real upstream file does not conclude the convention was
over-cautious. Note the form checker **accepts** `910C` as a token, so nothing mechanical would stop
a wrong BOARD here.

Read literally the same list also treats 910B2 and 910B3 as distinct platforms — consistent with
C-910-002, inconsistent with treating DAV_2201 as one uniform target.

→ resolvable **without a card**: entry 0057 §4 greps the installed toolkit for the string and for a
mapping (`grep -R`, since these trees symlink). Three outcomes kept separate:
resolved-to-<SocVersion> / absent-from-toolkit / present-but-unmapped. Cited by 0057.

## C-910-006 · `blockLen` alignment: relaxed in one document, required in another
- `ascendc-api-best-practices/references/api-datacopy.md:123` — "`DataCopyPad(GM, UB, ...)` 与
  `DataCopyPad(UB, GM, ...)` 的 **UB 端起始地址必须 32 字节对齐**（**blockLen 可以非 32B 对齐**，
  但起始地址不能）"
- `ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:249` —
  "9. **列提取时 srcStride 和 blockLen 必须满足 32B 对齐**：每次提取一个子字段需多次搬运调用。"

One says `blockLen` may be unaligned and only the UB start address may not; the other requires both
`srcStride` and `blockLen` to be 32 B aligned. Compatible only if the column-extraction case is
special, which neither document says. The consequence is direct: `DataCopyPad` is the API an agent
adopts *specifically* to escape the length constraint of `DataCopy` (entry 0021), so whether that
escape holds in the strided case decides whether a whole class of column extractions is legal.

→ resolvable on-card: extend entry 0023 §4 with a strided-column arm sweeping `blockLen` across
non-multiples of 32 B at non-zero `srcStride`, destination poisoned, verifying every element and
reporting mismatch positions. 0023 as written tests the address constraint only and would leave this
open — stated in its §7. Cited by 0021, 0023.

## C-910-007 · Where GM bandwidth approaches peak: 65536 B or 16384 B, 4× apart
- `ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:53` —
  "| > **65536** bytes | 极佳 | 接近峰值吞吐 |" (under the `:45` caveat "以下阈值基于 Ascend 910B
  实测经验")
- `ascendc-performance-analysis/references/metrics_reference.md:150` — "| GM 搬运（最优） | **512B**
  | **≥16KB** 数据量时可达峰值带宽 |", restated at `:241` "小数据块搬运时实际带宽远低于理论峰值
  （≥16KB 时才接近峰值）" and `:408` "| GM 搬运效率 | 单次 **<16KB** 带宽利用率低 | 使用
  DataCopyParams 批量搬运 |"

Both describe the same knee in one curve and place it 4× apart. Neither states a shape, dtype,
direction or tool. "接近峰值" is not a defined tolerance, so the two are not strictly incompatible —
but that is the point: **neither number can be used as a gate**, and an agent choosing a tile size
by one of them is choosing by which document it opened.

→ resolvable on-card as a by-product of the shared bandwidth grid: entry 0025 §5 declares the
discriminating clause in advance — `bw(65536)/bw(16384)` below 1.1 favours the 16 KB reading, above
it the 64 KB reading. Cited by 0024, 0025, 0055. Standing question Q-910-10.

## C-910-008 · Bank-conflict padding granularity: 256 B or a multiple of 32 B
- `ascendc-performance-best-practices/reference/common/ub_resident_design.md:117` — "**规避**：在
  `xBuf` 后增加 **256B** padding，打破地址周期性，使 `x` 和 `y` 的 DataBlock 分散到不同 bank group",
  with the checklist at `:339` "相邻 buffer 间隔 **≥ 256B** 或 不在同一 bank group"
- `ops-profiling/references/optimization_quickref.md:145` — "| **bank** | `vec_bank_cflt_ratio` >3%
  | 操作数读写指针地址不合理 | 调整 UB tensor 起始地址，添加 padding（**32B 整数倍间隔**） |"

Not numerically incompatible — 256 is a multiple of 32 — but they are **not the same advice**, and an
agent following the profiling guide's version may under-pad by up to 8×. Neither states which
conflict class its granularity addresses; the design document's own worked fix uses *two* different
displacements for two different aliasing pairs (256 B for the read-read pair, a 64 KB span inflation
for the read-write pair), so even "256 B" understates it.

→ resolvable on-card: entry 0016 §4 arms P and P2 separate the two mechanisms (P2 pads `x` by 256 B
only, without the `y` inflation), and a padding *sweep* over 32, 64, 128, 256, 512 B would locate the
minimum sufficient displacement — which no source in scope states and which 0016 §7 records as
unestablished. Cited by 0016.

## C-910-009 · A2 cross-core synchronisation: "no hardware barrier" versus a documented CrossCore API
- `ascendc-performance-best-practices/reference/sort/radix_sort.md:253` — section heading
  "## 5. 跨核同步（**A2 无硬件 barrier**）", with `:311` "| Cross-core sync | 无硬件 barrier |
  GM 轮询实现 |" and `:146` "FullBarrier()  // **~200μs** GM 轮询，DMA 同时完成"
- `ascendc-performance-analysis/references/metrics_reference.md:438-449` — section
  "### 8.2 核间同步（**Atlas A2/A3**）" documenting three modes ("模式 0 | 所有 AIC 核间同步 /
  所有 AIV 核间同步", 模式 1, 模式 2), the `CrossCoreSetFlag` / `CrossCoreWaitFlag` pair, and
  `:448` "同一 flagId 计数器最多设置 15 次"

Both are upstream, both scoped to A2, and neither mentions the other. Whether "无硬件 barrier" means
*no global barrier primitive* (compatible with per-flag cross-core signalling existing) or something
stronger is not determined by either text. The stake is large: a GM-polling barrier at ~200 µs is
ten kernel launches' worth of overhead (entry 0054), and a 16-step algorithm pays it sixteen times.

**Third source, found in the end-of-harvest coverage sweep and largely reconciling the row**:
`ascendc-api-best-practices/references/api-crosscore-sync.md:127` — "| **A3 / 910b（DAV_2201）** |
**不生效**——CrossCoreWaitFlag **阻塞全部流水** | 参数无实际作用 |". So on DAV_2201 the cross-core
flags exist (contra radix_sort read literally) **and** the wait blocks every pipe, i.e. there is no
*fine-grained* cross-core barrier — which is what an author seeking MTE2/Vector overlap would call
"无硬件 barrier". Both statements can be true. That reconciliation is an inference drawn in entry
0060 §2 and is marked there as this book's, not upstream's.

The row stays open because the reconciliation is not stated by anyone upstream, and because the
cost question is untouched: whether a mode-0 `CrossCoreSetFlag` global sync is cheaper than the
~200 µs GM poll is still unmeasured.

→ resolvable on-card: entry 0041 §4 arm 4 times a mode-0 `CrossCoreSetFlag` global synchronisation
against the GM-polling FullBarrier on the same die at the same core count. If the flag path is
cheaper, 0041 §1 narrows to "the GM-polling barrier is what this implementation used" — materially
weaker than "A2 has no hardware barrier". Cited by 0041, 0042, 0060, 0061. Standing question Q-910-13.


## C-910-010 · L2 in the DAV_2201 family: a third value, and the question was posed wrong
- `npu-arch/references/npu-hardware-params.md:132`, `npu-arch/SKILL.md:52`,
  `npu-arch/references/npu-arch-guide.md:182` — Ascend910B2 L2 = **192 MB** (three files, one origin)
- `ascendc-performance-analysis/references/metrics_reference.md:122` — "910B1/B2" L2 = **32 MB**
- `npu-arch/references/npu-arch-guide.md:93` — "如 910B4 核数 20@1.5GHz / **L2 96MB** / Memory 32GB"

C-001 in the shared register poses this as "which of two numbers is the 910 L2". The third figure
shows the question is mis-posed: 96 MB is a **different part**, so it and 192 MB can both be right,
and L2 is in upstream's own by-SKU varying set (`npu-hardware-params.md:124`). What C-001 actually
needs is a per-board answer, not a winner.

This does **not** resolve C-001 — 192 MB and 32 MB are still both claimed for 910B1/B2 — but it
retires the assumption that one number can stand for the family, and it means a resolution measured
on one part establishes nothing about the others (RULES.md Art. 2).

Two further findings in the same sweep, recorded here because they bear on how much weight the
truth source carries: `npu-arch-guide.md:93`'s pointer to "详见 `npu-hardware-params.md` 典型SKU
示例" **does not resolve** — that file's SKU table lists only Ascend910B2 for DAV_2201 and has no
910B4 row. And `npu-arch-guide.md:76` adds a further reduction nobody quantifies: "vNPU 切分后单实例
可见值更低".

→ resolvable on-card, per board, with the accessor `npu-arch-guide.md:208` names
(`GetCoreMemSize(CoreMemType::L2, l2Size)`) — whose existence an earlier draft of this book wrongly
denied; see entry 0011 §7's correction note. Cited by 0062, 0007. Standing question Q-910-02.

## C-910-011 · Memory bandwidth: the truth source says 1.6 TB/s and marks it unverified; a downstream skill uses 1.8
- `npu-arch/references/npu-arch-guide.md:91` — "| Memory 带宽 | **1.6 TB/s** [¹](#unverified) | …"
  for Ascend910B2, with an explicit unverified footnote on every cell
- `ops-profiling/SKILL.md:243` — "Atlas A2: GM 峰值带宽约 **1.8 TB/s** = 1.8e12 Byte/s", unmarked,
  used as the denominator in the theoretical-transfer-time worked example at `:243`
- `ascendc-performance-analysis/references/metrics_reference.md:233` — the same 1.8 TB/s again, chip
  unnamed, in a worked example whose own arithmetic uses a decimal megabyte while writing "64 MB"
  (entry 0055 §3)

12.5 % apart, and the figure that appears in the formulas is the one the truth source does not
endorse. `npu-arch/references/npu-arch-guide.md:74` states the governance rule this violates:
"本节作为 NPU 架构知识在 skills 仓中的上游真源，下游 skill 应消费本节数据，**反向自引用即视为
风险**." Nothing mechanical enforces it, and a consuming agent meeting 1.8 TB/s in the profiling
skill cannot tell it is reading a downstream divergence.

The two claims do not even share a scope: 1.6 TB/s is stated for Ascend910B2 (a board), 1.8 TB/s
for "Atlas A2" (a product line spanning five parts). Upstream's own provenance table puts bandwidth
in its weakest evidence class — `npu-hardware-params.md:178`, under "以下信息无法从当前安装的 INI
直接推导，数据来源于公开资料或工程经验积累".

→ resolvable on-card as part of the shared bandwidth grid: entry 0064 §5 declares in advance that a
sustained figure landing **between** the two is NOT a resolution and must not be reported as
favouring the higher one. Only a sustained figure above 1.6 TB/s discriminates. Cited by 0064, 0055.
Standing question Q-910-10.


## C-910-012 · DataCopyPad blockCount: a 4095 cap against a uint16 field
- `ascendc-api-best-practices/references/api-buffer.md:279` — "constexpr uint32_t MAX_BLOCK_COUNT =
  **4095**;  // DataCopyPad blockCount 限制", acted on at `:286` as a hard clamp on tile rows, in a
  snippet whose own comment at `:277` scopes it "A2/A3 UB = 192KB"; restated at `:291`
- `ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:59-60` —
  `struct DataCopyExtParams { uint16_t blockCount;   // 块数量` — a field admitting **65535**

Sixteen times apart. Not strictly incompatible (a 16-bit field can carry a value the hardware clamps
at 4095), but an agent gets two ceilings and only the smaller one is ever acted on. 4095 = 2¹²−1
suggests a 12-bit hardware field behind a 16-bit software one — **arithmetic performed at harvest,
not an upstream claim**, and it predicts wrap-at-4096 rather than saturation.

This matters more than an ordinary cap because the type-width defence works elsewhere in this API
family and fails here: `rightPadding` is `uint8_t` capped at 255 (entry 0026) and `srcStride` is
`uint16_t` capped at 65535 DataBlocks (0027) — in both, the type IS the limit. An agent that audits
parameter widths computes 65535 for `blockCount` and concludes 5000 is safe.

→ resolvable on-card: entry 0069 §4 sweeps `blockCount` over 4094…8192 against a poisoned
destination and counts blocks actually delivered, distinguishing **wrap (0 arrive) / clamp (4095
arrive) / soft limit (4096 arrive)** as three separate outcomes rather than as "wrong". Cited by
0069.
