# Contradictions register — domain `950-bp`

> **TRIAGED 2026-08-25**: every row below has a phase-2 disposition in
> `harvest/TRIAGE_DOMAIN_ROWS_20260825.md` (resolved / assigned-to-round / noted / blocked).

Same topic, different advice or numbers, found while harvesting the 950 side of
`upstream/skills-dev-main/ops/ascendc-performance-best-practices/**` (book-950 entries 0301–0349).
Row format follows `harvest/CONTRADICTIONS.md`; IDs are `C-950bp-NNN`, per the phase-1 plan's
2026-08-24 amendment §7. For merge into the shared register by the controller in wave 2.

**Standing caution for every row below.** The two shelves that most often disagree here —
`ascendc-performance-best-practices` (implementation) and `ascendc-perf-optimize` (analysis) — are
two directories of ONE repository. Two files in one repo are one origin (RULES.md Art. 3), so a 2-vs-1
count of statements is a count of statements, never of authorities, and no row below is resolved by
majority. Resolution is by a §4 procedure on a named board (RULES.md Art. 7).

Every quote was re-verified against the file at harvest time (2026-08-24).

---

## C-950bp-001 · UB capacity on DAV_3510: 256 KB and 248 KB are two different quantities
- `ascendc-performance-best-practices/reference/common/ub_resident_design.md:38` — bank table row
  "| DAV_3510 | **256 KB** | 16 | 8 | 2 | 16 KB (512 行) | 32 B |"; restated `:304`
  "Atlas 350：256KB = 16 bank × 16KB = 8 group × 2 bank".
- `950:0209` / `ops/npu-arch` / the installed CANN 9.0.0-beta.2 `platform_config` set — UB is
  **248 KB** (`ub_size=253952`).

**Disposition: not a numeric conflict — a units-of-account conflict, resolved on paper, pending
measurement.** The installed ini carries `ubsubbank_num=64` and `ubbank_size=4096`, and
`64 × 4096 = 262144 = 256 KB`, which is the physical bank array; `ub_size=253952` is what the
allocator exposes. `262144 − 253952 = 8192`, and that 8 KB is the same term `950:0238`'s SIMT budget
subtracts (`256 KB − 8 KB − 32 KB = 216 KB`, equal to `253952 − 32768`). So this file is removed
from the list of documents that disagree with `950:0209`, and the reading supplies the arithmetic
that makes C-003's and C-005's 256 KB legible. It does **not** close C-003 (`ascendc-code-review`
uses 256 KB as an *allocation* threshold, which is the user-visible quantity and is still wrong) or
C-004 (192 KB under a measurement banner). Carried by `950:0314`; the distinguishing measurement is
that entry's §4 Arm B.

## C-950bp-002 · L1 K-depth: a two-rung power-of-two ladder against "the largest integer that fits"
- `ascendc-performance-best-practices/reference/matmul/pingpong_design.md:163` —
  `L1_BUFFER_NUM` is "满足 `2 × singleBufferSize ≤ l1_size` 的**最大整数值**", worked to **3**;
  and "`tiling_gen.py` 输出的 `stepK=2` ... 与本文档的 `L1_BUFFER_NUM=3` 是两个独立概念。
  **实施时应以本文档的 `L1_BUFFER_NUM=3` 为准**".
- `ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-fields.md:24` — "上限 4，且只能取
  2 的幂"; `tiling-flow.md:165-179` — `nBufferNum = (used_4buf < l1Size) ? 4 : 2`, a two-rung ladder
  (carried by `950:0113`).

The implementation shelf's answer (3) is unreachable in the analysis shelf's admissible set
`{4, 2}` / `{1, 2, 4}`. Upstream's own reconciliation is that the two names denote different
quantities; it states this and defines neither. → resolvable on a named 950 board.
Carried by `950:0303`; also touches `950:0109`, `950:0113`.

## C-950bp-003 · StreamK entry gate: `K ≥ 32768` (prose) vs `K ≥ 4096` FP16 columns (formula and code)
- `ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:21` — "K ≥ 32768 且 B=1
  且无 group".
- same file `:283` — SK gate `Align(K, 256) ≥ max(8192, aicNum×256) / sizeof(FP16)`, which evaluates
  to **4096** at `aicNum ≤ 32` and **4608** at `aicNum = 36`.
- `ascendc-performance-best-practices/reference/matmul/streamk_design.md:16` — "SK ... `K ≥ 4096
  (FP16 列)`"; `:17` — "DP+SK ... `K ≥ 8192/FP16`" (also 4096 columns); `:332` — the shipped error
  string `[ERROR] StreamK requires: K >= 4096 and MN split count <= half of core number`.

Two distinct defects in one row. (a) The prose rule is 8× the computed one — this extends C-009,
which found the same gap inside the analysis shelf alone; the implementation shelf now agrees with
the *formula*. (b) The implementation shelf **froze an `aicNum`-dependent threshold into a literal**,
including into a user-visible error string, so on a 36-cube-core part (`950:0217`) the literal is
permissive by 512 columns. Separately, `B = 1` and `无 group` appear only on the prose side and
nowhere in the implementation shelf; `M/N 256 对齐` appears on both. → resolvable on a named 950
board. Carried by `950:0309`; also touches `950:0108`.

## C-950bp-004 · StreamK workspace: 256 KiB per core by formula, 128 KB per core by note
- `ascendc-performance-best-practices/reference/matmul/streamk_design.md:127` —
  `GetWorkSpace() = aicNum * BLOCK_BASE_M * BLOCK_BASE_N * sizeof(FP32) + RPC_WORKSIZE * MB_SIZE`,
  with `BLOCK_BASE_M = BLOCK_BASE_N = 256` at `:90-91` → `256 × 256 × 4 = 262144 B = 256 KiB`.
- same file `:275` — "**Workspace 容量开销**：约 `aicNum × 128KB = 3MB+`（FP32），需确认 HBM 预算。"

A factor of two between two statements 148 lines apart in one file. The `3MB+` total is not
evaluated here: `aicNum` is unbound in the source, and no installed 950 SKU this book records has
12 cube cores (`950:0217` lists 4, 8, 28, 32, 36). `RPC_WORKSIZE` and `MB_SIZE` are undefined in
both shelves (also `950:0111`). → resolvable on a named 950 board by reading back the actual
workspace request. Carried by `950:0310`.

## C-950bp-005 · Scale coalescing's own before/after cell contradicts its own worked ladder
- `ascendc-performance-best-practices/reference/matmul/scale_coalescing_design.md:82-86` — at
  `baseM = 128, |dtype_scale| = 1 B`: `SCALE_L1_BUFFER_NUM = 1` → 2 KB, `= 2` → **4 KB**,
  `= 10` → 20 KB, `= 16` → 32 KB.
- same file `:255` — "| 单次 scale MTE2 搬运量 | **1024 B** | 8192–32768 B | **+10×** |", where the
  "before" column is labelled `SCALE_L1_BUFFER_NUM=2`.

4 KB by the file's own formula against 1024 B in its own results table for the same configuration;
and `32768/4096 = 8×`, `32768/1024 = 32×`, neither of which is the stated `+10×`. The threshold
claim the file exists to support (`0312`) is unaffected; the `+10×` figure is not carried by any
entry. → resolvable by echoing the per-transfer scale byte count from the kernel
(`950:0312` §4 Arm 3). Carried by `950:0312` §3.

## C-950bp-006 · Read-read bank conflict: the DAV_3510 rule differs from 220x and only one file says so
- `ascendc-performance-best-practices/reference/common/ub_resident_design.md:48-54` — conflict table
  giving read-read as "同一 **bank group**" for NPU 220x but "同一 **bank**（两个读操作），或**两个
  以上**读操作同一 bank group" for Atlas 350, with the stated cause "Atlas 350 的 bank group 上有
  两组读口和写口".
- No other file in the whole upstream repo states a DAV_3510 read-read conflict condition. The
  installed ini set carries bank/group counts (`C-950bp-001`) and no port count.

This is not a disagreement between documents; it is a **single-source load-bearing rule with no
second statement anywhere**, recorded here because the padding recipes that follow from it are
stated only in their 220x form (`:96`, `:117`, `:130-137` are all `220x 官方推荐`) and an agent will
carry them across. → resolvable on a named 950 board. Carried by `950:0315`, `950:0316`.

## C-950bp-007 · The RadixSort family is marked dual-arch in the index and fences itself to A2 in its own guide
- `ascendc-performance-best-practices/SKILL.md:33` — "| RadixSort 基数排序类 | TopK, KthValue, Sort,
  ArgSort, ArgMax/Min | **DAV_2201 / DAV_3510** | ✅ [性能优化指南](reference/sort/radix_sort.md) |".
- `reference/sort/radix_sort.md:5` — "本文档基于 **A2 大规模数据** 实战验证；A3、A5 等架构的硬件
  细节差异需另行验证后再套用。"; `:8` — "**不要把本文的 A2 二分搜索/直方图方案当作 A5 TopK 的默认
  实现。**"

The index cell routes a DAV_3510 reader to a document that refuses the routing in its first
paragraph. The actual 950 authority for this family is `reference/sort/templates/usage_guide.md`,
whose `:5` reads "本文用于后续重新实现或优化 Ascend 950 / DAV_3510 TopK", and which the index cell
does not name. → no measurement needed; this is a routing defect, resolvable by reading. Carried by
`950:0329`.

## C-950bp-008 · Four DAV_3510 families keep their templates in a directory named `dav310`
- `reference/{conv,gather,reduce,scan}/templates/dav310/` — 152 references across the shelf's
  markdown.
- `reference/{conversion,sort}/templates/dav3510/` — same architecture, the unambiguous spelling.
- `ops/npu-arch/references/npu-hardware-params.md:16,19` — `ASCEND310P = DAV_2002` and
  `ASCEND310B = DAV_3002` are real, different, non-950 architectures.

`dav310` is not a DAV number that exists. An agent routing by directory name — which this book's own
measured finding says agents do — lands on an inference part. → no measurement needed; resolvable by
reading. Carried by `950:0346`.

## C-950bp-009 · Fast division is a high-priority SIMT rule and a measured zero-gain change in the one family that reports a number
- `reference/simt/optimization-guide.md:24` — "| Rule 007 | **高** | 用 fast-division 和特化降低
  地址计算成本 |"; `:241-254` gives the `GetUintDivMagicAndShift` / `Simt::UintDiv` recipe.
- `reference/scatter/scatter_design.md:166` — "**实测 quick-div 类标量优化在本族零收益**（§8），
  瓶颈在访存延迟不在标量流水"; `:175` — "int64 → int32 索引运算宽度收窄 | **零收益**（+0.04 分）。
  连带 quick-div magic number、按 rank 特化 kernel 同属标量优化，**预期同样无用**".

A cross-cutting rule marked 高 priority against a measured null in the family with the best evidence
culture in the shelf. Not necessarily a contradiction — scatter is latency-bound (`950:0161`) and the
rule may hold where address arithmetic is on the critical path — but the SIMT guide states no
applicability condition, so as written the two conflict. → resolvable on a named 950 board by
measuring address-arithmetic share before and after in a non-scatter SIMT kernel. Carried by
`950:0342`.

## C-950bp-010 · The DoubleBuffer authority for a DAV_3510 family calibrates every capacity number on a 910 part
- `ascendc-performance-best-practices/SKILL.md:37` — "| Elementwise 逐元素类 | Sin, Cos, Abs, Exp |
  **DAV_3510** | ✅ [双缓冲设计](reference/elementwise/double_buffer_design.md) ... |".
- `reference/elementwise/double_buffer_design.md:80` — "Available UB = 192KB (**Ascend 910B3**)";
  `:247-249` — QUE-buffer-per-`TPosition` limits given only for "Atlas A2 训练系列产品（如 910B1）"
  (≤ 8) and "Atlas 训练/推理系列产品" (≤ 4), with no 950 figure anywhere in the file.

The only DoubleBuffer design document in the shelf sits in a 950-marked family and contains no 950
number. Its *mechanism* claims are architecture-neutral; its *budget* claims are 910-attributed and
are not carried into this book (RULES.md Art. 1). → the 950 figures must be established, not translated.
Carried by `950:0319`.

## C-950bp-011 · `Atlas 350` is a product name used as an architecture label and defined in neither mapping table
- `reference/common/ub_resident_design.md:31,48,54,304` — "Atlas 350" used as the column head for
  the DAV_3510 conflict rules.
- `ops/npu-arch/references/npu-hardware-params.md:20-21` — the declared truth source maps ASCEND950 =
  DAV_3510 = **Atlas A5** = Ascend950DT / Ascend950PR. It has no row for "Atlas 350".
- `ascendc-regbase-best-practice/references/paradigms/quantization/references/cast-api.md:5` —
  "**适用平台**：Atlas 350 加速卡（arch35 / DAV_3510）" — a definition, in a third skill, of a name
  the truth source does not carry. 1042 occurrences repo-wide.

Not a numeric conflict; a vocabulary one, and it is the kind `form/CONVENTIONS.md` already handles
for "910C": write the token the source names, or `family-claimed(unverified)`. Recorded because a
load-bearing hardware table is headed by a name that the repo's own 真源 does not define. → no
measurement needed. Carried by `950:0314` §3 and `harvest/standing/950-bp.md`.
