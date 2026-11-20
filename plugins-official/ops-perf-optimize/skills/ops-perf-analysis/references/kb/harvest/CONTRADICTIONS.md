# Contradictions register

Same topic, different advice or numbers, across upstream sources. Recorded here and in the
affected entries' §3; resolved only by a procedure run on the named board (Art. 7). Each row
below was found by the 2026-08-24 structural survey; a phase-1 harvester must re-verify every
quote against the file before building a claim-card on it (a survey is one contact, not a
measurement).

## C-001 · L2 cache size, 910B1/B2
- `ascendc-performance-analysis/references/metrics_reference.md:122` — 910B1/B2 L2 = **32 MB** (pointer corrected :117→:122, 2026-08-24, per 910 miner re-verification)
- `npu-arch/SKILL.md` — Ascend910B2 L2 = **192 MB**
Neither cites the other; `npu-arch` declares itself the 真源. → resolvable on-card (910 book).
**MEASURED 2026-08-24 (910B2 NPU 0, CANN 9.1.0 — 910:0077, killing run in 910:0007 §6):**
RESOLVED for the measured part — 192 MB by all three arms (interface 201326592; every B1/B2/B2C/B3
ini; behavioural knee: 100 % warm-hit through 160 MB, 0 % at 256 MB). The 32 MB is the PREVIOUS
generation's value, found verbatim in the installed `Ascend910B.ini` (`NpuArch=1001`). Note the
family is per-SKU: B4/B4-1 inis carry 96/168 MB, unmeasured.

## C-002 · BT size, 950 / DAV_3510
- `ascendc-performance-analysis/references/metrics_reference.md:123` — 950 BT = **1 KB** (pointer corrected :117→:123, 2026-08-24, per 910 miner re-verification)
- `npu-arch/SKILL.md` — DAV_3510 BT = **4 KB**
→ 950 book.
- **RESOLVED for the measured part 2026-08-24 (950:0210, verified on 950PR)**: BT = **4096 B**
  by four tiers — interface (GetCoreMemSize(BT)=4096, FB queried separately in the same probe),
  ini (36/36 NpuArch=3510 files on the bound 9.1.0), compile-time software constant
  (ASC_BT_SIZE = 4*1024 for 3510, sys_constants.h), and the behavioural boundary (single
  install: 4096 B granted with every output column bit-exact through the mmad bias path,
  4160 B refused, runtime error 507015; boundary moves by exactly a 2048 B install offset).
  metrics_reference.md's 1 KB is measured-wrong on 950PR. 950DT: ini-enumerated only, not run.

## C-003 · UB / L1 / L0C capacities, chip-agnostic table vs per-arch truth source
- `ascendc-code-review/references/ascendc-perf.md:578` — "典型容量" UB **256 KB**, L1 **1 MB**, L0C **256 KB**
  (line 611 hard-codes `UB_SIZE(256KB)` as a crash threshold)
- `npu-arch` — DAV_2201: 192 KB / 512 KB / 128 KB; DAV_3510: 248 KB / 512 KB / 256 KB
The agnostic table matches NEITHER family. → both books, separately.
- **Measured state 2026-08-24**: UB — resolved against the 256 KB reading on BOTH measured
  parts (910B2: three tiers around 192 KB, 910:0003; 950PR: 248/256 KB two-tier split,
  950:0209). **L1 on 950PR — resolved by 950:0212 (verified)**: ceiling 524288 exactly at 64 B
  granularity, two-tenant total 524288 bit-exact; the agnostic 1 MB is measured-wrong there
  (2× over-budget for a reviewer applying it). L1 on 910B2: API=524032 (ini−256) measured at
  interface tier (910:0004), enforcement boundary arm still open. L0C: ini/interface tiers only
  (950 l0_c 262144 read, 910 131072) — no boundary run yet, row stays open for L0C.

## C-004 · UB capacity, intra-skill inside ascendc-perf-optimize itself
- `ascendc-perf-optimize/references/single-core-pipeline/vec.md:102` — UB **192KB / 910B2, 248KB / 950**
- `ascendc-perf-optimize/references/tiling/reduction/fallback/example/euclidean_norm/experience.md:5` —
  "Ascend 950 / arch35 (dav-3510) ... UB≈**192KB**"
Error, or deliberately conservative host-side model? The documents do not say. → 950 book.
**MEASURED 2026-08-24 (950PR, CANN 9.1.0 — 950:0209 §6):** `GetCoreMemSize(UB)`=253952 (248 KB),
single-`InitBuffer` enforcement boundary = 262144 (256 KB), delta 8192. 192 KB got no support from
any arm — the euclidean_norm anchor does not even reproduce from its shipped script (any budget,
any dtype). RESOLVED for 950PR against 192 KB; vec.md:102's 248 KB stands as the API tier.

## C-005 · SIMT usable-UB budget, 950
- `ascendc-simt-tiling-design/SKILL.md` and `ascendc-code-review/references/simt-constraints.md:225` —
  可用 UB = 256KB − 8KB − 32KB = **216 KB** (note: starts from 256 KB, cf. C-003)
- `ascendc-simt-api-reference/references/overview.md:99` — 216 KB applies to SIMD/SIMT **mixed**
  scenarios; non-mixed returns **248 KB**
→ 950 book.
**MEASURED 2026-08-25 (950:0238 §6, direct launch):** plain kernel `GetRuntimeUBSize()` = 253952 at every grant;
VF-bearing kernel = the launch's DYN_UBUF grant, whose ceiling is 221184 = 216 KB; access ceilings 262144 (plain) vs
grant + 8192 (VF; 229376 at the cap) — difference 32768. All three figures are real, for three different quantities.

## C-006 · UB size as script default, four values inside ascendc-perf-optimize/references/tiling/ (extends C-004)
- `tiling/convolution/fallback/script/conv_tiling.py:245` — `ub_size: int = 262144` (**256 KB**, no chip)
- six scripts (elewise, conversion, reduction, broadcast, sort/fallback, sort/topk) — `248 * 1024` (no chip)
- `tiling/scan/fallback/script/scan_tiling.py:103` — `192 * 1024` (no chip)
- `tiling/sort/topk_host_tiling.md:209` — **240 KiB usable of 248 KiB physical, DAV_3510** (the only chip-scoped one)
Every hardware constant in that subtree is a script default nobody scoped. → 950 book (subtree is A5-first).
**MEASURED 2026-08-24 (950:0209 §6):** the API tier is 253952 = 248*1024 — the six `248 * 1024`
scripts carry the correct API-tier value; `262144` is the runtime enforcement boundary measured on
950PR (granted; 262176 refused); `192*1024` matches nothing measured. The 240-KiB-usable figure
remains untested (a further reservation below the API tier).

## C-007 · coreNum as script default, same subtree, five values, none chip-scoped
`64` (six script defaults, incl. reduction_tiling.py:58) · `72` (euclidean_norm experience.md; also scan's __main__ demo call — NOT a script default) · `32` (`aicore_num`, conv) · `8`/`24`
(matmul/mc2 worked examples). → 950 book; the true per-board core counts come from `npu-arch`.
- **Adjudicated for the measured parts 2026-08-24** (interface readouts, RUNS ledger; no new
  runs needed): the measured 950PR_9579 has aic=28 / aiv=56 and the measured 910B2 has 24 / 48 —
  NONE of the five script literals (64/72/32/8/24-as-950) matches either measured part, and the
  installed 3510 ini set spans five configurations (4,8)…(36,72) (950:0217, one measured), so no
  single literal CAN be right family-wide. The row's residual question was never "which literal
  is correct" but "why literals at all"; that is 950:0207 / 910:0011 territory (query at
  runtime), already carried by those entries. Nothing further is measurable here — the C-row is
  CLOSED as adjudicated-against-every-literal for the measured parts.

## C-008 · matmul stepK limit, five statements, one self-refuting
**BLOCKED 2026-08-25 (terminal for this phase):** requires upstream's op-framework matmul tiling generator to force StreamK vs SWAT (the seven StreamK constants + a non-zero `tailInfo.kCnt`); the hand-tiled round-2 vehicle cannot express the gate, and 0108/0109 §5 make a forced, md5-distinct build with the constants echoed mandatory.
- `tiling/matmul/fallback/tiling-flow.md:159` — "stepK的最大值为8"
- `tiling/matmul/fallback/tiling-fields.md:24` — "上限 4"
- `tiling-fields.md:186` — "`stepK ∈ {1, 2, 4}`"
- `tiling-flow.md:375` — "{1, 2, 4}（StreamK 有例外 stepK=3）" (contradicts the constant table in its own file)
- `mc2/index.md:64` — emits `step_k: 3` as recommended output
→ 950 book.

## C-009 · StreamK entry gate, stated twice one way and computed another (8× apart)
**BLOCKED 2026-08-25 (terminal for this phase):** requires upstream's op-framework matmul tiling generator to force StreamK vs SWAT (the seven StreamK constants + a non-zero `tailInfo.kCnt`); the hand-tiled round-2 vehicle cannot express the gate, and 0108/0109 §5 make a forced, md5-distinct build with the constants echoed mandatory.
- `tiling/matmul/fallback/tiling-flow.md:21` and `fallback-algorithm.md:35` — "K ≥ 32768 且 B=1 且无 group"
- `tiling-flow.md:283` — `Align(K,256) ≥ max(8192, aicNum×256) / sizeof(FP16)` → K ≥ **4096** at aicNum=24
- the file's own worked example (`:351`, K=16384 → SK) satisfies the formula and violates the stated rule
→ 950 book. (Same file also: `:344` heading declares "→ A-FullLoad" while `:346` computes 不开;
`:352` reports `skSingleCoreK = 2732` where `CeilDiv(16384,6) = 2731`.)

> 2026-08-24 note: C-007's original attribution of 72 to "scan, reduction" script defaults was
> wrong (found by the 950-tiling miner); corrected above. The contradiction itself stands.

---

## Domain registers (wave 1 + 1.5) — the full record lives in these six files
The nine C-rows above are the survey-era seeds. Mining found far more; each miner filed its own
register (write partitions, plan Amendment §7). Row counts re-derived mechanically 2026-08-24
(repair wave, audit F-6 — the earlier "104" was a stale hand count): 9 seeds + 161 in eight
domain registers = 170 total:
- `contradictions-950-core.md` — 17 (C-950core-001…017; 008 deliberately vacant, documented)
- `contradictions-950-tiling.md` — 36 (C-950tiling-001…036)
- `contradictions-950-arch.md` — 9 (C-950arch-001…009)
- `contradictions-950-bp.md` — 11 (C-950bp-001…011; 001 is a DISSOLUTION: two quantities, not two answers)
- `contradictions-910.md` — 12 (C-910-001…012)
- `contradictions-950-rem.md` — 16 (C-950rem-001…016, plus a checked-and-not-opened section)
- `contradictions-950-td.md` — 29 (C-950td-001…030; 009 permanently vacant by self-withdrawal)
- `contradictions-950-fin.md` — 31 (C-950fin-001…031)
Re-derive: `grep -cE '^#{2,3} +C-' harvest/CONTRADICTIONS.md harvest/contradictions-*.md`.
Dispositions recorded in-register; resolution only by Art. 7. C-001 is MIS-POSED per C-910-010
(L2 varies by sub-model; a per-board table is owed, not a two-way verdict).
