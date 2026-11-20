# Standing questions — domain 950-tiling

Named measurements and unresolved definitions owed by the `950-tiling` domain
(`upstream/skills-dev-main/ops/ascendc-perf-optimize/references/tiling/**`). Per the phase-1 plan's
2026-08-24 amendment §7 this is a per-agent file, merged by the controller in wave 2.

Each question names the entries it gates and, where the answer needs a board, says so. Questions that
need **no** device are marked `[no-card]` — they are answerable in this phase and have **not** been
run; that is itself part of the record.

---

## S1 · Undefined symbols in load-bearing formulas

Upstream writes capacity inequalities, gates and budgets in symbols it never assigns. Grouped by
family, with the entry that carries each.

**matmul** (0111) — `c0` (the K alignment quantum in FullLoad's capacity test; flips the gate for any
K not already aligned), `L1_SIZE`, `L0aSize`, `L0cSize`, `biasTableSize`, and `RPC_WORKSIZE × MB_SIZE`
(an additive term in StreamK's workspace request that the file's own worked example silently drops).
Upstream names two headers as their home — `conv_api_tiling_util.h` / `conv_template_utils.h`
(`matmul/fallback/tiling-flow.md:9`) — neither present in this tree.

**reduction** (0123, 0128) — `szA0` (used in `tiling-fields.md:73` without definition; context makes
it the inner block's A0 extent), the split of `固定预留 = 1024 + 512` (what the general 1024 reserves
is unstated), and the literal `11` in ARA-Recompute's `FP32 × (11 + cache_layers)` term.

**scan** (0138) — `VLC`, used five times (`tiling-flow.md:85,86,109,111,197`) in an algorithm gate, a
segment-length formula, a buffer-provisioning rule and a cost argument, and defined nowhere. The only
reading consistent with all four uses and with the script's `VL = 64  # 256B / 4B` is "vector length
in elements of the comparison type", which would make `VLC = guardC` — two names for one quantity in
one file. Also `sizeof(C)`'s default in the bank rule (0133).

**gather** (0148, 0149) — `xAlign`, `idxAlign`, `minIdxSlice`, `MIN_OUT_UB`, `MIN_INDICES_UB`, the
2048-byte UB reserve in `availableUb = ubSize - 2048`, and `R` in the VCONV_5HD gate (`R > 5`,
`conversion/index.md:57` — what `R` denotes is not stated). `DCache` and `INDICES_SIZE` are given
inline as 128 KB and 8 KB in single conditions and nowhere else.

**broadcast** (0154) — `dcache`, used in decision-chain condition ② (`尾轴 ≥ dcache/2`,
`tiling-flow.md:24`) and defined nowhere in the family. Whether it is the same quantity as gather's
inline `DCache(128KB)` is not stated and is not assumed.

**convolution** (0167) — `m1`, `ci1`, `co1` (all three in the cost model's four terms), `waste` (the
HW-split tie-breaker), and the `/128` divisor separating movement from compute in `TotalCost`.

**elewise** (0151, 0153) — `extraSize`, `bufferNum`, `K` (the promotion branch's extra-FP32-buffer
count, sourced to "API 别名约束" with no API named), and how `输入量级未知` is decided host-side.

→ Owed: `[no-card]` a read-only header sweep over an installed 950-era CANN toolkit
(`grep -Rn`, not `-r` — these trees contain symlinked directories), recording value, path and toolkit
pin per symbol. Then, per board, a runtime query for the capacity symbols (0141). Gates 0102, 0103,
0110, 0111, 0112, 0113, 0123, 0128, 0133, 0138, 0148, 0149, 0154, 0167.

## S2 · The one L1 capacity figure in the subtree has no board and no provenance
`matmul/fallback/tiling-fields.md:193-197` gives `vs L1 (524 288)` as a column header inside a FAQ
about `L1_BUFFER_NUM`. Its arithmetic is self-consistent (53 % / 80 % / overflow at buffer depths
2/3/4, re-derived in 0109 §3) and it is the only place `L1_SIZE` is effectively valued anywhere in
`references/tiling/`. → Owed: runtime query plus an allocation probe on a named board. Gates 0109,
0110, 0111, 0113.

## S3 · UB capacity: three different answers inside one skill
248 KiB physical with a 32 KiB SIMT reserve and a 240 KiB fallback budget (sort, DAV_3510-scoped —
0140, and internally inconsistent, C-950tiling-018); ≈192 KB under a msprof on-board banner
(reduction — 0131); `248 * 1024` in six scripts, `262144` in conv, `192 * 1024` in scan
(`CONTRADICTIONS.md` C-006). → Owed: a query **and** a write-read-back allocation probe on a named
board, reported as the pair `(queried, allocatable)`, plus the same with SIMT features in use. Gates
every UB budget in the domain. This is the domain's single highest-leverage measurement.

## S4 · Vector register width and the granularities derived from it
`256 B` per vector register appears as `a0_tile_unit = 64(FP32) / 128(FP16)`
(`reduction/fallback/tiling-flow.md:376`), as `elements_per_repeat = 256 / dtype_bytes`
(`:362`), as `guardC = 256 / cBytes` (`scan/fallback/tiling-flow.md:145`), as `VL = 64 # 256B / 4B`
(`scan/fallback/script/scan_tiling.py:11`) and as `VGATHER_REGISTER_SIZE = 256`
(`convolution/fallback/script/conv_tiling.py:62`). Five consistent statements, none with a board, in
a project whose survey lists the 256 B register among the quantities with **no** upstream authority
anywhere. Likewise `32 B` as the memory block granularity, stated family-wide and never sourced. →
Owed: first-time establishment per Art. 2, plus a runtime `GetVecLen()`-family query (0141). Gates
0129, 0133, 0138.

## S5 · The unremoved authoring aside in a shipped reference file
`matmul/fallback/tiling-flow.md:349` reads, in the middle of the worked-example block:
`Wait, that example from the mxfp4 doc won't work for FP16. Let me use correct numbers.` First person,
English, in a Chinese reference file that four sibling skills link into. It is not a contradiction —
it is one document disclosing its own unfinished edit, and it is evidence about the provenance of the
surrounding arithmetic (the section was adapted from another dtype's document and the adaptation was
not finished). No prior survey of this skill reported it. → Owed: nothing measurable; recorded so the
replacement skill does not inherit the passage, and so the neighbouring numbers are re-derived rather
than copied. Carried by 0114.

## S6 · Files upstream defers to that are absent from this tree
- `matmul/fallback/tiling-fields.md:91,100` → `batch_matmul.md §2`, `group_matmul.md §3.2` — the
  derivations for `batchAxisCoreNum` and split-N's tail structure (0115).
- `matmul/fallback/tiling-fields.md:65` → `scale_coalescing_tiling.md §2.2` — the `[16, 8, 4, 2]`
  fallback ladder's formula (0116).
- `convolution/fallback/fallback-algorithm.md:38` and `tiling-flow.md:5` → `demo/` with
  `main.cpp` carrying per-step source correspondence; the directory does not exist, so the TilingKey's
  `固定格式` bit layout is unrecoverable here (0166, 0168).
- `gather/fallback/tiling-flow.md:142` → `reference/gather/templates/gather_elements_v2_route.template`
  in a **sibling skill** — the complete capability and workspace cost gates, without which this
  family's most-documented path is routed but not decidable (0148, 0149).
- `gather/fallback/index.md:10` → `tiling-fields.md`, marked 规划中 and absent (C-950tiling-023).
→ Owed: `[no-card]` record whether each exists elsewhere in `upstream/skills-dev-main/`; where it does
not, the corresponding entry's §7 stands as the limit.

## S7 · Dual-maintenance obligations with no enforcement
- `scatter/fallback/tiling-flow.md:305` — "本节数字与最佳实践货架的 scatter_design.md §5 **同源**，
  改动请同步两处". The three measured laws of 0161 live in two skills and nothing checks they stay
  equal.
- `scan/fallback/tiling-flow.md:199-201` — `LaneSegLen` / `GsSegLen` must be the *same function* on
  host and kernel or the UB budget is wrong (0133). Stated as a rule; enforced by nothing.
→ Owed: `[no-card]` a mechanical equality check between the two scatter copies, and a note in
the delivered skill's NOTES.md that the replacement must not reproduce an unenforced obligation.

## S8 · Measurements upstream states without conditions
Recorded because each is quotable and none is reproducible as stated — no repetition count, no
variance, no date, and in most cases no case identity. Grouped by family, with the entry that carries
each.

- **scan** (0132, 0134, 0137): `kernel launch 固定开销约 9 µs`; `实测省 38%`; `100 万点约 230µs`;
  `实测慢 8~50 倍` (a range spanning 6×); `实测慢 12~31%`; `四条流水占比之和只有 101%`;
  `实测慢 5.5 倍` (the bank rule, 0133 — the sole justification for a formula change);
  `fp16 比 fp32 慢 1.6~1.9 倍`; `反超 1.6 倍`; `快 1.5 倍`.
- **reduction** (0126, 0127): a 20-case table in which 15 of 20 rows lie between 0.91× and 1.09× with
  no variance figure stated anywhere; `8.29×`; `1.39×`; `-9%`; `28%` and `10×` (quoted against
  different denominators, C-950tiling-010).
- **matmul** (0110): `Task 时间降低 5%~15%` — the family's only outcome number, with no shape, dtype,
  core count, board or tool.
- **conversion** (0163, 0164): `3-10 倍`; `2-5 倍`; `6.25%`; `≥50%`; `~4us`; `~10KB`.
- **scatter** (0160, 0161, 0162): `0.5 / 1.7 / 3.3 / 10~27 G updates/s` (the last a 2.7× range in one
  cell); `~600 GB/s`; `11~18` vs `4.7~5.0 G/s`; `4.81×`; `2805/583/562 µs`; `133.67`/`295.94 µs`;
  `8.51 µs`; `1565→89 µs`; `0.02×`; `3767`/`12602 µs`; `8~24%`; MARE `0.020576`. These are the
  best-identified numbers in the domain — `Ascend950PR`, a score of 72.46, 20/20 passes — and still
  carry no repetition count or date.
→ Owed: a variance floor measured before any of them is re-checked (declared in every §4 in this
block), then per-figure re-measurement on a named board. Until then none is a fact this book asserts.

## S9 · Version-scoped claims with no version
- `sort/topk.md:214` — "当前高阶 TopK 的 16 位 index 收集存在已验证缺陷"; `:219` — vendor b64 TopK
  "在目标版本存在 crash 风险". Two workarounds justified by defects in unnamed CANN versions (0145).
- `scan/fallback/tiling-flow.md:94` — "编译器不支持 16 位标量比较"; `:97` — "int16→int64 一步 Cast
  编译得过但结果错". Toolchain claims with no compiler version (0139).
- `scatter/fallback/tiling-flow.md:186` — "换硬件/CANN 版本应重测", attached to the 256-thread choice,
  naming neither the hardware nor the version it was measured under (0160).
The reduction family does state one (`CANN 9.0.0`, `euclidean_norm/experience.md:5`) — for a different
family, so Art. 2 forbids carrying it. → Owed: pin the toolkit and re-test each; every result is
scoped to the pin.

## S10 · Decision surfaces that do not cover their input domain
- `convolution` — `outputOrder` selects between two whole algorithms with no stated derivation
  (C-950tiling-033); `iterOrder` (M_FIRST / N_FIRST) appears only as a TilingKey field, with no rule
  anywhere (0168).
- `matmul` — MTE2 bandwidth in [70 %, 85 %) is routed by no arm (C-950tiling-004).
- `conversion` — `N_LAST 或 CUT_ONCE` with no discriminator (C-950tiling-032).
- `scatter` — the conflict-density criterion upstream names as the right one and does not write,
  approximated by `starved` (0162).
→ Owed: each entry's §4 produces the missing rule as a measured table, not as a judgement. These are
the four places where a *derivation* is owed rather than a verification.

## S11 · Claims whose §4 needs more than one die
MC² (0118, 0119, 0120) is multi-rank. Every procedure in that family is written for at most 4 dies
under the shared-machine budget, with per-die occupancy checked before binding and re-checked after,
no die substituted for a named one, and the rank count recorded with the result. → Owed at
verification time: operator confirmation that a multi-die window is available, before those three
entries' procedures are scheduled.

---

## What this domain cannot answer for book-910
`references/tiling/` names no 910-family board anywhere; the only chip-generation branch is
broadcast's `DAV_2201` arm (0154, 0155), which is a 950-era document's unverified statement about
another architecture and whose constraints its own reference implementation does not enforce. Under
RULES.md Art. 1 nothing in this domain enters book-910. The 910 book's broadcast, elementwise and
reduction tiling must be derived from its own sources.
