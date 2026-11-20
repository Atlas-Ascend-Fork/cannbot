# Domain contradiction-row triage — 2026-08-25 (phase-2 round-2 residue)

One-pass triage of every row in the eight `harvest/contradictions-*.md` registers, per the
the close-out route
no card time. **160 rows under 161 IDs** (130 `## C-` IDs across seven files, of which
`C-950core-008` is deliberately vacant per its register, + 31 `### C-950fin-`; the route's "~139"
was an estimate, the enumerated count governs).

## Classes (terminal states per the close criterion)

- **resolved** — terminal now. The resolving evidence exists and is named: a measurement already
  taken on a named board, or a completed read whose result is stated in this file's row.
- **assigned-r3 / r4 / r5** — runnable on this fleet; assigned to that round's named vehicle.
  Rows so marked become terminal when the assigned arm runs (or its blocked-note is written,
  per the round-5 rule).
- **r3-nodevice** — adjudicable by a host-side compile or toolkit grep with zero device time;
  collected into one batch job (see "No-device adjudication batch" below), scheduled as the
  opening act of round 3.
- **noted** — terminal as a written note. Basis is one of: (a) doc-vs-doc inside one origin,
  provable by the reading already quoted in the register row; (b) the conflict touches no claim
  any book entry carries; (c) a resolving procedure exists but only in the §4 of a
  harvested-stratum entry outside the ratified corroborated cut (TRACE∩corroborated) — the
  procedure is preserved there and is NOT scheduled in phase 2. Per the ratified plan item 4,
  verifying all non-terminal entries is not a phase-2 obligation; the operator can promote any
  `noted(c)` row to a round by saying so.
- **blocked** — a written note naming the missing resource.

Dispositions here do not edit the registers' rows; each register now carries a head pointer to
this file. Two rows were RESOLVED BY READING during this triage (evidence below): C-950rem-012
and C-950fin-027.

---

## contradictions-910.md (12 rows)

| row | class | disposition |
|---|---|---|
| C-910-001 | resolved | 2026-08-25 (0013 verified(910B2)): bank-group counter rises at every S with gcd(S,16)>1 (S=4/12 0.45, 8/24 0.66, 16/32 0.84), time 1.65× at S≡8, 2.62× at S≡0 (mod 16) — 16-group mapping confirmed; on 950PR the same form conflicts nowhere (0314). |
| C-910-002 | resolved (measured part) / out-of-fleet | 2026-08-25: 910B2 measured 24/48 (`GetCoreNumAic/Aiv`, `aclrtGetSocName`=Ascend910B2, NpuArch 2201); installed ini census: B1/B2/B2C 24/48, B3/B4/B4-1 20/40, all NpuArch=2201 — upstream's split is the ini's split. 0009 → corroborated; runtime verdict INCONCLUSIVE (one SKU) by its own §5. |
| C-910-003 | resolved | 2026-08-25 on 910B2: scalar working-set knee between 16 and 20 KB (0.29 → 2.8 → 4.6 sys-cycles/access), line 64 B (cost doubles per stride doubling to 64 B, flat after) — DCache = 16 KB on this part; the flat "32KB" is wrong here. 0018 → verified(910B2). |
| C-910-004 | noted (b,c) | Not resolvable as stated — upstream's cases are unidentified, by the row's own analysis. The technique-class question lives in 0049 §4 (outside cut). Terminal note. |
| C-910-005 | resolved | BATCH-EXECUTED 2026-08-25 (0057 §4's third outcome): **present-but-unmapped**. The installed 910 toolkit ships `ASCEND_910C = "Ascend910C"` (asc_op_compile_base cce_params.py:65, + AIC/VEC engine variants), `bool is910C` tiling fields in shipped transformer ops, a `// 910C 950` grouping comment, a dav_c220 coreid-fix comment naming 910C, and pypto's `ASCEND_910C4` enum — and NO `Ascend910C*.ini` in platform_config, no mapping row. The CONVENTIONS rule (never write 910C in a BOARD line on upstream evidence) STANDS, sharpened: the vendor ships code for the token, but no installable part answers to it. |
| C-910-006 | resolved | 2026-08-25 (0023 verified(910B2), corrected): misaligned UB start (4/8/16 B) ABORTS 507035; aligned starts place every block 32-B-pitched regardless of a 4-B blockLen; the 32-B-pitch control is clean. |
| C-910-007 | resolved | 2026-08-25 (0025 verified(910B2)): bw(65536)/bw(16384) = 1.011 (one core) / 0.994 (48 cores) — below 1.1: the 16 KB and 64 KB thresholds are the same threshold; per-core saturation is reached by 4 KB and nothing is gained above it. |
| C-910-008 | resolved (256-B side) | 2026-08-25 (0016 verified(910B2)): 256 B on x alone zeroes the group counter (0.48 → 0.0) but leaves a bank conflict (0.416) until y is inflated (upstream's two displacements confirmed, 1.9× faster). The 32-B-multiple alternative of the profiling guide is untested. |
| C-910-009 | blocked | 2026-08-25 (0041 arm 4 RAN, instrument-blocked): both GM-polling FullBarrier (507046) and CrossCoreSetFlag<0,PIPE_S> mode 0 (507035) abort in a bare direct-launch AIV kernel on every config incl. 2 cores; needs a __mix__/op-framework context. Terminal for this phase; Q-910-13 open. |
| C-910-010 | resolved | Resolved-for-measured-part in round 1: 910B2 L2 = 192 MB by knee + ini + interface (0077, verified). Other sub-models (96 MB = 910B4 etc.): out of fleet, recorded as scope not debt. C-001's per-board framing stands answered for every board the fleet has. |
| C-910-011 | resolved (as measured) | 2026-08-25 (0064 verified(910B2)): sustained read 1.537 TB/s, write 1.495, copy 1.258 (both directions) — below 1.6 AND 1.8: neither peak reached, so per the declared rule no peak is picked; the sustained figure is the denominator to use. |
| C-910-012 | resolved | 2026-08-25 (0069 verified(910B2)): blockCount cap 4095 with WRAP mod 4096 (4096 → 0 blocks, 5000 → 904, 8191 → 4095); the uint16 range is not operative; no header range check. |

## contradictions-950-arch.md (9 rows)

| row | class | disposition |
|---|---|---|
| C-950arch-001 | noted (a) | Scope defect (`arch35` covers NpuArch 3505 too), established by toolkit enumeration at harvest. BATCH-CONFIRMED 2026-08-25 on 9.1.0: three `Ascend035*.ini`, all `NpuArch=3505`. Stands on the deliverable pin. |
| C-950arch-002 | resolved | Existence half by toolkit witness (B1); semantics half RUN 2026-08-25: MulDstAdd = dst·s0+s1 (22/11), MulAddDst = s0·s1+dst (38/17), int32 partition with verbatim SupportType diagnostic — 0246/0247 verified. |
| C-950arch-003 | resolved | RUN 2026-08-25: `MulDstAdd(3,5,7)` = **22** — vec-03 is right, the evaluation JSON's row is measured-wrong (its MulAddDst row measured-right). 0247/0248 verified; the declared reference fixture reported "1 0". |
| C-950arch-004 | resolved | 2026-08-25 (0259 verified(950PR)): two dependent `__VEC_SCOPE__` segments byte-identical with and without `PipeBarrier<PIPE_V>` in 1100+ launches under `--cce-auto-sync=on` and `=off`; the harness catches a real V→MTE3 race (fixture red). Position 2 (hardware orders consecutive vector segments) holds on this part; position 1 buys 0.22 µs per kernel at 512 fp32 (18.6 %), 0.6 % at 24576. Auto-sync defaults on; it does NOT cover a hand-written DataCopy after a scope. |
| C-950arch-005 | noted (b) | Coverage gap, not a conflict; the ini `[DtypeMKN]` is the sole and vendor-side source. A timed fp32-vs-fp16 Cube-throughput arm is possible on the mm vehicle but not scheduled. |
| C-950arch-006 | resolved | 2026-08-25 (0238 verified): three quantities, not one — plain kernel `GetRuntimeUBSize`=253952 (ini/API), VF-bearing kernel = the launch grant (cap 221184 = 216 KB), access ceilings plain 262144 / VF grant+8192 (229376 at the cap); 256−8−32 names the right terms; 248 is the API figure, neither ceiling. |
| C-950arch-007 | noted (a) | Rule stated and violated in adjacent executable code — provable by the quoted read; repair is upstream's (one generator). The enforcement question (is a <32 KB DCache reservation actually refused) MAY piggyback on the round-3 op-framework vehicle; noted, not owed. |
| C-950arch-008 | resolved | RUN 2026-08-25: VL = 256 BYTES — one full-mask store writes 64 fp32 / 128 half elements; device GetVecLen()=256. The `_bits` suffix in ascend950pr.json is measured-wrong; its own sibling file ("B/instruction") was right. 0219/0273 verified. |
| C-950arch-009 | resolved | Q-950arch-15 answered (GetVecLen constexpr; substitution legal, literal avoidable) AND the arms RAN 2026-08-25: expression tracks hardware (64/128, 2:1), borrowed constants diverge (B32=64 wrong at half; ONE_BLK_SIZE/sizeof wrong at both), and the borrowed build silently writes 64 halves beyond the task window. 0252/0253 verified. |

## contradictions-950-bp.md (11 rows)

| row | class | disposition |
|---|---|---|
| C-950bp-001 | resolved | This round's measurements close it: API/ini 253952 + InitBuffer enforcement 262144 (0209 verified, re-confirmed by 0212/0314 lanes) = the bank table's 256 KB is the physical array, `ub_size` the allocator's figure. 0314 §4 Arm B disposed by the same data (entry §4 as-run note, 2026-08-24). |
| C-950bp-002 | blocked | L1 K-depth needs the StreamK/stepK sweep (0109), which needs upstream's op-framework matmul tiling generator to force stepK into the tiling struct — the hand-tiled round-2 vehicle cannot express it. Terminal for this phase. |
| C-950bp-003 | blocked | StreamK gate needs the generator-forced StreamK-vs-SWAT build (0108). Terminal. |
| C-950bp-004 | blocked | Workspace read-back rides the generator-dependent StreamK vehicle (0108). Terminal. |
| C-950bp-005 | noted (b,c) | The file's self-contradiction touches no carried claim (the +10× figure is carried by no entry; 0312's threshold claim unaffected). Procedure preserved in 0312 §4 Arm 3. |
| C-950bp-006 | resolved | 2026-08-25 (0489 verified(950PR)): the per-lane gather read-conflict geometry IS measured — penalty = 2-adic part of the byte stride × lane count (four tiers), alias period 128 B, 64-B pair-offset relieves; the vendor bank-conflict counter stays ≈0 throughout (the counter does not see it). |
| C-950bp-007 | resolved | Routing defect resolved by reading: the index routes DAV_3510 to a document that refuses the routing; the real 950 authority (`sort/templates/usage_guide.md`) is named. Nothing to measure. |
| C-950bp-008 | resolved | Resolved by reading: `dav310` is not a DAV number that exists (mapping table witness); 152 references counted. Vocabulary/routing note stands in 0346. |
| C-950bp-009 | noted (a,c) | The defect is the missing applicability condition, already demonstrated by the two quotes. A discriminating run needs a non-latency-bound SIMT kernel — procedure sketch preserved in 0342; not scheduled. |
| C-950bp-010 | resolved | 2026-08-25 (0019 verified(950PR)): TQue depth 2 vs 4 → identical per-buffer ceiling (131072 at BUF 2; 87360 at BUF 3); BUFFER_NUM costs UB, depth does not. |
| C-950bp-011 | noted (a) | Vocabulary row; `form/CONVENTIONS.md` already handles the species (as for "910C"). Folded into the close-out vocabulary item. |

## contradictions-950-core.md (17 IDs, 1 vacant)

| row | class | disposition |
|---|---|---|
| C-950core-001 | blocked | 0065 §4 states "needs one card per rank"; the fleet has ONE 950PR. Missing resource: a second 950 rank. Terminal blocked-note. |
| C-950core-002 | resolved | Provable by the quoted read: with `tail = M % hs` and ρ ≥ 1, the hard `continue` excludes every non-divisor split — arithmetic, not measurement. 0066 keeps the corrected predicate as a clearly-labelled proposal. |
| C-950core-003 | resolved | Existence by toolkit witness; semantics RUN 2026-08-25 (22 vs 38, two operand sets, swap arm 26). Fully closed with C-950arch-002/003. |
| C-950core-004 | resolved | = B2, resolved 2026-08-25 by 0259 verified(950PR) (no PipeBarrier<PIPE_V> needed between dependent vector segments; position 2 holds). |
| C-950core-005 | resolved | Read is the resolution: SKILL.md's "empty" is false against the 41-line framework in the directory; both quoted. CONTRACT defect F2 recorded in 0002. |
| C-950core-006 | resolved | Read is the resolution: the eval instantiates 误解2 by its own SKILL.md. F1 in 0003/0001. |
| C-950core-007 | resolved | Read is the resolution: A2 and A5 are disjoint per upstream's own map. F3 in 0004. |
| C-950core-008 | (vacant) | Deliberately unallocated per the register header. |
| C-950core-009 | resolved | 2026-08-25 (0019 verified(950PR)): depth is free (exact equality at 32-B granularity), BUFFER_NUM is the UB cost. |
| C-950core-010 | resolved | Toolkit witness at the harvest pin: `expandLevel==0` delegates to basic `Exp<T>` (constexpr branch read); no LUT branch in the impl files. 9.1.0 note (batch 2026-08-25): the impl set is now `exp_3510_impl.h`/`exp_common_impl.h`, the parameter is stored as "taylor param expand level" (common:74); the level-0 delegation branch was NOT re-derived on 9.1.0 — resolution stands on the harvest-pin witness for the delegation shape, both pins for the Taylor identity. |
| C-950core-011 | resolved | Double-pinned by batch 2026-08-25: default `expandLevel = 10` on 9.1.0 too (`exp_common_impl.h:41,77`), matching the harvest pin; the card's implied default of 2 matches neither. |
| C-950core-012 | noted (a) | Numeric vs qualitative voice for one decision; both quoted. |
| C-950core-013 | noted (a) | Overlapping R bands with no precedence + a second inconsistent band table — provable by the quotes. |
| C-950core-014 | noted (a) | Undefined symbol + circular bound — provable by the quotes. |
| C-950core-015 | noted (a) | "Hard" vs "soft" both implemented as hard `continue`s — provable by the quotes. |
| C-950core-016 | noted (a) | `Task Duration` and `aiv_time` are different columns of different files — schema fact, reinforced by this round's measured msprof sqlite readout (RUNS 2026-08-24). |
| C-950core-017 | noted (a) | Packaging defect (orphan tool-frontmatter file); CONTRACT F6 in 0074. |

## contradictions-950-fin.md (31 rows)

| row | class | disposition |
|---|---|---|
| C-950fin-001 | noted (a) | Both destination directories verified empty at harvest; routing defect stands as read. 0468 arms preserved. |
| C-950fin-002 | noted (c) | Label-vs-formula; procedure in 0452 §4 arm 3 (outside cut). |
| C-950fin-003 | noted (c) | Slot-semantics enumerations; 0453 §4 arm 4. |
| C-950fin-004 | noted (c) | Parked invariant, admitted by upstream; 0455 §4 arm 4. |
| C-950fin-005 | noted (a) | Register mismatch (rule scope vs number sites) — as read. |
| C-950fin-006 | noted (c) | Redacted architecture in the one evidential place; 0460 §4 arm 1 (capture verbatim diagnostic) preserved. |
| C-950fin-007 | noted (a) | Reconcilable only under a reading neither states — as read. |
| C-950fin-008 | noted (c) | mode=4 blocking unstated; 0463 §4 arm 3 preserved. |
| C-950fin-009 | resolved | Read is the resolution: five toolkit arch tokens unmapped by `form/CONVENTIONS.md`. Residual action = vocabulary correction to CONVENTIONS at close-out (with C-950td-026, C-950bp-011). |
| C-950fin-010 | noted (a) | Bare thresholds in the document that forbids them — as read. |
| C-950fin-011 | noted (c) | Undefined `+` notation; 0465 §4 arm 4. |
| C-950fin-012 | noted (c) | Mis-filed dtype criterion; 0466 §4 arm 3. |
| C-950fin-013 | resolved | Read is the resolution: both pointers verified bad (§6 is Host Tiling; §1.6 does not exist). |
| C-950fin-014 | noted (a) | Glyph-vs-parenthetical over-report — as read. |
| C-950fin-015 | noted (c) | Literal vs dtype-derived alignment; 0471 §4 arm 4. |
| C-950fin-016 | noted (c) | Elements-vs-bytes budget, dimensionally unsound as written; 0472 §4 arm 2. |
| C-950fin-017 | noted (c) | sizeof(DataType) vs sizeof(float); 0472 §4 arm 1 (Art. 7 leaves it to a run). |
| C-950fin-018 | noted (c) | Two naming schemes, no mapping; 0473 §4 arm 3. |
| C-950fin-019 | noted (c) | 32B-multiple vs effective length; 0475 §4 arm 2. Cross-ref C-910-006 (same species; its 910 arm is assigned-r5) — if a 950 twin of 0023's arm ever runs, it resolves this row too. |
| C-950fin-020 | noted (a,c) | Layer reading reconciles; not asserted as self-contradiction. 0476 §4 arms 1-2. |
| C-950fin-021 | resolved | BATCH-EXECUTED 2026-08-25 on 9.1.0: `SetMaskCount(dataSize)` REFUSED ("too many arguments…expected 0", decl kernel_common.h:188); `SetMaskMode(NORMAL)` REFUSED (no such symbol; only `enum class MaskMode`); the shipped five-call idiom COMPILE-ACCEPTED. Both origins + a compile witness on the deliverable pin now agree: the shelf's spellings match no symbol. |
| C-950fin-022 | resolved | BATCH-EXECUTED 2026-08-25 on 9.1.0: the value-returning 2-arg calls REFUSED — `WholeReduceSum` is a void template requiring 7 arguments (dst, src + 5 ints), verbatim from the diagnostic. The shelf's reference code cannot compile. |
| C-950fin-023 | noted (c) | 12~31% vs 4~31%; 0482 §4 arm 3 (timed scan, outside cut). |
| C-950fin-024 | noted (c) | 8~18% vs ~3%; same vehicle. |
| C-950fin-025 | resolved | 2026-08-25 (0489 verified(950PR)): the 48/80/112/144-byte stride group IS separated from the powers of two — it pays 1.14× (float, 64 lanes) / 1.35× (half, 128 lanes) against a severe 5.4–10.7× at 64/128 B; a real but sub-severe tier set by the 2-adic part of the stride, not by "multiple of 16" as one class. |
| C-950fin-026 | noted (c) | NaN stickiness; upstream's own guide already records the GT-only failure (case 14); 0484 §4 arms 1-2 preserved. |
| C-950fin-027 | resolved | RESOLVED BY READING (this triage, 2026-08-25): the duplicate `class TileResidentScan {` block IS present at `templates/dav310/cum_tile_resident_scan.template:245,248` (a doubled 4-line header block). `usage_guide.md:274` "已修复" is false; `:309` "可能有" understates — it does. (The file also sits in `dav310/`, confirming C-950bp-008's path.) |
| C-950fin-028 | noted / blocked | The claim ("6 modes") is unverifiable as stated: the referenced `CalcTiling()` lives in a header no roster row or directory carries (C-950fin-029). Missing resource named; terminal. |
| C-950fin-029 | resolved | Read is the resolution: roster and directory verified to lack `scan_cummin_tiling.h`; two further dangling refs recorded. |
| C-950fin-030 | noted (a) | Three spellings incl. a copyable path — vocabulary species; folded into the close-out vocabulary item. |
| C-950fin-031 | noted (c) | 34/56/59 µs for one case; 0482 §4 arms 0-2 (timed, outside cut; spread ≈ the shelf's own timing floor). |

## contradictions-950-rem.md (16 rows)

| row | class | disposition |
|---|---|---|
| C-950rem-001 | resolved + noted | Availability half BATCH-EXECUTED 2026-08-25: `AscendC::Reg::DataCopy<float, Reg::LoadDist::DIST_NORM>(vin, inAddr)` inside `__VEC_SCOPE__` COMPILE-ACCEPTED on 9.1.0 — the whitelist's treat-as-unavailable default is wrong for this API; the canonical pattern file's usage compiles. (9.1.0 spelling note: the reg surface lives in namespace `AscendC::Reg::`; the bare `AscendC::RegTensor` spelling is refused with a did-you-mean.) Compile-accepted ≠ runs-correct; the run tier, if ever needed, rides a round-3 VF probe. Meaning-of-whitelist half: editorial, noted. |
| C-950rem-002 | noted (a) | 0372 Arm A already predicts "no machine answer"; the resolution is editorial, which is itself the finding. |
| C-950rem-003 | resolved | BATCH-EXECUTED 2026-08-25, and the answer is THREE-WAY: the doc's `uint64_t` is wrong on both pins; the harvest pin (9.0.0-beta.2) declares int32_t; the deliverable pin (9.1.0, `asc/include/simt_api/cpp/kernel_simt_common_intf.h:29-42`) declares GetThreadIdx/GetThreadNum/GetBlockIdx/GetBlockNum ALL `uint32_t` (compile-witnessed: static_assert vs int32_t FAILS with "unsigned int, int") and only GetWarpSize `int32_t`. The undocumented `template <int32_t dim = 0>` parameter persists on both thread accessors on 9.1.0. The accessor return type CHANGED SIGN BETWEEN PINS — any signed-arithmetic analysis of the doc's uncast expression is pin-specific. |
| C-950rem-004 | noted (c) | "功能完全等价" vs rounding control; 0380 Arm B (disassembly compare) preserved, not scheduled. |
| C-950rem-005 | noted (c) | Walker stride 1+dim vs fixed 9 words; one rank-mixed dump decides (0381 §4), device-side, outside cut. |
| C-950rem-006 | resolved | RUN 2026-08-25: a genuinely-false assert prints the condition AS WRITTEN, unnegated — `[ASSERT] file:line: sig: Assertion `cond' failed.`, once per thread (32/32) — matching the AI CPU example's format; the SIMT example's negated output is wrong on this pin. Side-fact: the fired assert returns rc=507035 (the code is a generic vector-side abort, not UB-overflow-specific). Carried 0384. |
| C-950rem-007 | noted (a) | Five sections under three index rows, prototypes matching neither — as read. |
| C-950rem-008 | noted (c) | Thread- vs operator-scoped `__trap`; a one-NaN run on the SIMT vehicle would settle it (0386 §4) — optional piggyback, not owed. |
| C-950rem-009 | noted (a) | Undefined `CheckDtypeSupportAndCombination` — provable by the quotes; species of C-950arch-007/009. |
| C-950rem-010 | resolved | Toolkit enumeration with stated directional bounds: 8 named constants undefined (upper bound), ≥30 defined-but-undocumented. The grep predicates and their blind spots are recorded with the row. |
| C-950rem-011 | blocked | MoE dispatch/combine window layout needs a multi-rank run; ONE 950PR in fleet. Missing resource: a second 950 rank. (Same block as C-950core-001.) |
| C-950rem-012 | resolved | RESOLVED BY READING (this triage, 2026-08-25): `winAlignBytes` occurs exactly ONCE in the entire mc2 skill (the use site, `window-memory-layout.md:119`); the three next-hop documents (`multi-core-formulas.md`, `mte-address-access.md`, `double-buffer-protocol.md`) contain no alignment statement. "Undefined here" is now "undefined upstream". 0392 Arm A executed and closed. |
| C-950rem-013 | noted (a) | Implementation-defined in prose, 32 fixed in code two lines later — third instance of the species; as read. |
| C-950rem-014 | resolved | Toolkit witness: both documented headers declare sibling surfaces, not the documented symbols; real headers named. The `asc_syncthreads` vs `SyncAll` substitution hazard stands as the note. |
| C-950rem-015 | resolved | Spelling half from this round's VF-lane survey: the real API is `SetLocalMemorySize` (exe_graph `tiling_context.h:496`, 9.1.0), already deprecated toward `SetDynUBufSize`. Residual grep BATCH-EXECUTED 2026-08-25: bare `SetLocalMemory(` matches ZERO lines across include/asc/compiler trees on 9.1.0 — the doc's step-1 spelling is a non-symbol. Fully closed. |
| C-950rem-016 | noted (a) | Third copy of the 256/128 KB snippet, least context; numeric claim stays with 0239 (C-950arch-007). Generator repair is upstream's. |

## contradictions-950-td.md (29 rows)

| row | class | disposition |
|---|---|---|
| C-950td-001 | noted (a) | Four/five/six template counts — as read; mechanical half is C-950td-002. |
| C-950td-002 | noted (c) | Scalar-serial vs binary-fold merge; 0402 §4 (vary merge inside one kernel) preserved, outside cut. |
| C-950td-003 | noted (c) | Precision-vs-latency rationale; follows 0402's `ub_delta` verdict if it ever runs. |
| C-950td-004 | noted (a) | Two chunk-merge disciplines in one shelf — as read. |
| C-950td-005 | noted (a) | Catalogue-vs-decision-tree asymmetry — as read; the measuring shelf is the one that declines to publish a rule. |
| C-950td-006 | noted (c) | 255 cap: toolkit constant `MAX_REPEAT_TIMES = 255` corroborates the value; whether it binds `DataCopyExtParams.blockCount` is 0404 §4's question. Cross-ref C-910-012's assigned-r5 sweep (same species on 910; its wrap/clamp taxonomy will inform this row). |
| C-950td-007 | resolved | Attribution half by reading at the harvest pin: the restriction exists in BOTH shipped backends there, so it does not distinguish arch35 (Art. 1 fence respected). Compile-claim half BATCH-WITNESSED 2026-08-25 on 9.1.0: `reduce_sum_3510_impl.h:109-111` is a verbatim `static_assert(AR || RA, "ReduceSum only support AR and RA pattern on current device!")` — and `pattern` is a TYPE parameter (Pattern::Reduce::AR/RA), so "ARAR" is not even spellable; upstream's 编译报错 is real and is this assert. (9.1.0 v220 impl shape not re-enumerated — the attribution half rests on the harvest-pin read.) |
| C-950td-008 | noted (a) + r3-nodevice (optional) | Doc-comment vs SupportType gap recorded, not an error; one optional compile probe (e.g. `ReduceMax<int8>`) may ride the batch if slots allow. |
| C-950td-010 | noted (a) | One underived 512 in two formulas with two purposes — as read. |
| C-950td-011 | noted (a) | Units change at the branch — provable by the quoted code. |
| C-950td-012 | noted (a) | Router short-circuits before the cost test two of its own documents demand — provable by the quotes. |
| C-950td-013 | noted (c) | SIMT-vs-transpose numbers; the case identification is 0408's inference and its §4 arm 3 is preserved, outside cut. |
| C-950td-014 | noted (a) | A fourth template count — as read. |
| C-950td-015 | noted (a) | Document order vs the family's own measured order — as read; upstream itself forbids generalising. |
| C-950td-016 | noted (a) | Four underived router constants pass the letter and fail the provenance test of the family's own rule — as read. |
| C-950td-017 | noted (a) | `nonGatherShapesEqual` absent from every selection table — as read. |
| C-950td-018 | noted (a) | Two guards present in one shelf's copy, absent in the other's — as read. |
| C-950td-019 | noted (a) | Constant/units/object three-way divergence on the trailing-axis gate — as read. |
| C-950td-020 | noted (c) | Outer-axis NaN attribution; one mis-routed case decides (0416 §4), outside cut. |
| C-950td-021 | noted (a) | Sample violates two of its own family's buffer rules — provable by the quotes. |
| C-950td-022 | noted (a) | Two incompatible fixes, shipped code satisfies one — as read; reachability stays Q-950td-07. |
| C-950td-023 | resolved | The retraction is stated by upstream itself; verified at harvest. The row records the residue (the overturned row remains in the table). |
| C-950td-024 | noted (a) | Three summary figures over-reach their own tables — arithmetic done at harvest. Scope correction owed to 0164 stays Q-950td-08. |
| C-950td-025 | noted (a) | Fastest measured implementation absent from its own roster — as read. |
| C-950td-026 | noted (a) | `DAV_5102` defined nowhere upstream; toolkit gates DO carry 5102 (C-950fin-009) — folded into the close-out CONVENTIONS vocabulary item. |
| C-950td-027 | resolved | Verified at drafting: the referenced `kernel/` layout does not exist; real paths named. |
| C-950td-028 | noted (a) | 30%/90% baselines for one metric — partial mitigation stated in the row. |
| C-950td-029 | noted (a) | Bottom-ranked style is the vendor-recommended one, no quantity attached — as read. |
| C-950td-030 | noted (a,c) | FIX vs MTE3 for L0C→UB + reversed event names; adjacent-row table defect as read. The pipe question could piggyback on the mm vehicle (event-witness readout) — optional, not owed. |

## contradictions-950-tiling.md (36 rows)

| row | class | disposition |
|---|---|---|
| C-950tiling-001 | resolved | Verified by reading at harvest: three of four `占位` labels false, one true (fa). Per-family rows 026-028. |
| C-950tiling-002 | blocked | Extends C-009 (0108 K-sweep, generator-dependent). Terminal. |
| C-950tiling-003 | blocked | Extends C-008 (0109 stepK, generator-dependent). Terminal. |
| C-950tiling-004 | noted (a) | [70%,85%) unrouted — one table not covering its own domain; as read. |
| C-950tiling-005 | noted (a) | `sizeof(dtype)` double-count — arithmetic provable. |
| C-950tiling-006 | noted (a) | Strict vs non-strict at equality — as read. Adjacent hardware fact now measured: InitBuffer grants at exactly l1Size (0212, this round); the generator predicate is host-side doc. |
| C-950tiling-007 | noted (a) | Heading vs body + CeilDiv off-by-one — arithmetic provable. |
| C-950tiling-008 | noted (a) | Unconditional prose vs conditional code ladder — as read. |
| C-950tiling-009 | resolved | Resolved by C-007's closure this round: the 192 KB / 72-core anchors match NO installed ini on either machine and no measured part (RUNS 2026-08-24). The row's calibration-point analysis and its C-007 attribution correction stand recorded. Which real part has 72 cores: out of fleet, scope not debt. |
| C-950tiling-010 | noted (a) | Two denominators in one table — arithmetic done at harvest. |
| C-950tiling-011 | noted (a) | 所有模板 vs ✅/➖ cross-table — as read. |
| C-950tiling-012 | noted (a) | Prose vs formula, one FP32 copy apart — arithmetic provable. |
| C-950tiling-013 | noted (a) | Two workspace formulas 4× apart — as read. |
| C-950tiling-014 | noted (a) | Borrow trigger 4096 vs 16384 (×2 more statements) — as read. |
| C-950tiling-015 | noted (a) | MIN_SEG 8192 vs 1024 — as read. |
| C-950tiling-016 | noted (a) | Script emits the template its own flow forbids — as read. |
| C-950tiling-017 | resolved | RUN 2026-08-25: 1 vreg = 256 BYTES (behavioural, 0219/0252 readouts) — the `:145` byte reading is right, `:57`'s "VREG/4=16 元素 fp32" arithmetic is wrong on this part (256/4=64). Intra-file inconsistency stays noted. |
| C-950tiling-018 | resolved | 2026-08-25 (0238 §6): a 240 KiB (245760) fallback budget fits the plain access ceiling (262144) but exceeds both the VF regime's grant cap (221184) and its access ceiling (229376) — for a kernel with a SIMT VF the 216 KiB constraint binds and 240 KiB overruns; for a plain kernel it fits. The constant and the constraint apply to different regimes. |
| C-950tiling-019 | noted (a) | Eight vs nine routing rows — as read. |
| C-950tiling-020 | noted (a) | The script computes it both ways — as read; differs exactly on Pattern C. |
| C-950tiling-021 | noted (a) | Definition 32 B vs rule 8/4/2 B — as read. |
| C-950tiling-022 | noted (a) | Header vs gates on improveDtypeSize — as read. |
| C-950tiling-023 | resolved | Verified at harvest: the mandatory `tiling-fields.md` does not exist; six undefined symbols recorded. |
| C-950tiling-024 | noted (a) | Six/seven/nine/ten counts — as read; the two omitted are the transpose paths. |
| C-950tiling-025 | noted (a) | 8× overshoot in the markdown form — arithmetic done at harvest. |
| C-950tiling-026 | resolved | Verified: complete tiling behind a placeholder index. |
| C-950tiling-027 | resolved | Verified: four-branch tiling + 590-line script behind a placeholder. |
| C-950tiling-028 | resolved | Verified: only the registry row is wrong. |
| C-950tiling-029 | noted (a) | Constraints stated in doc, absent from the (never-exercised) script path — as read, with the survey overstatement already corrected in the row. Art. 1 fence stands. |
| C-950tiling-030 | resolved (compile tier) | BATCH-EXECUTED 2026-08-25: `LAUNCH_BOUND(256)` + `VF_CALL(Dim3(256))` COMPILE-ACCEPTED on 9.1.0 — the claimed set {1024,512,128,32,8} is NOT a compiler restriction at 256 (the compile-time-constant requirement itself is real). Runtime validity of 256 is untested (no device in the batch); if a later VF run uses 256 threads it completes the tier. The three-passes-use-256 statements stop being a contradiction and become the doc's own counterexample to its set claim. |
| C-950tiling-031 | noted (a) | Blocks provisioned at /1024 regardless of per-pass threads; grid-stride covers — as read. |
| C-950tiling-032 | noted (a) | A node whose arms agree, deliberately, undocumented in place — as read. |
| C-950tiling-033 | noted (a) | `outputOrder` undefined — decision-surface defect, species of 004. |
| C-950tiling-034 | noted (a) | Search variable absent from the objective — as read (`m1` undefined). |
| C-950tiling-035 | noted (a) | Three levels, two naming schemes, no stated correspondence — as read. |
| C-950tiling-036 | noted (c) | GroupNorm routed to a stub; whether it collapses to (A1,R,A0) is 0169 §4 arm 1 / 0468, outside cut. |

---

## Tally (160 rows; sums to 160) — UPDATED after the batch ran (2026-08-25, same day)

| class | count |
|---|---|
| resolved (2 in-triage reads, 6 no-device batch, 7 round-3 card lane 1 [2026-08-25], 25 prior/other) | 40 |
| resolved | 55 |
| blocked | 7 |
| noted | 96 |
| vacant (C-950core-008) | 1 |
| **total IDs** | **161 (160 rows)** |

All rows terminal as of 2026-08-25: 55 resolved (on-card or by reading), 7 blocked (2 multi-rank
resource: C-950core-001, C-950rem-011; 5 op-framework-generator: the StreamK/stepK family
C-950bp-002/003/004 + C-950tiling-002/003; plus C-910-009 instrument-blocked), 96 noted (structural /
cross-ref / no-device), 1 vacant. No row remains assigned.
| noted (terminal) | 96 |
| blocked (missing resource named) | 2 |

Counting rule: rows with a split disposition (resolved + residual arm) are counted once under the
class of the OPEN half if any half is open (e.g. C-950arch-002 → assigned-r3).
resolved = C-910-005/010; C-950arch-002/003/008/009; C-950bp-001/007/008;
C-950core-002/003/005/006/007/010/011; C-950fin-009/013/021/022/027/029;
C-950rem-001/003/006/010/012/014/015; C-950td-007/023/027;
C-950tiling-001/009/017/023/026/027/028/030 — 40.
Per-class rows: r3 card = C-910-002/003; C-950arch-004/006; C-950bp-006; C-950core-004;
C-950fin-025; C-950tiling-018. (Moved to resolved by round-3 card lane 1, 2026-08-25:
C-950arch-002/003/008/009, C-950core-003, C-950tiling-017, C-950rem-006.)
r4 = C-910-007/009/011; C-950bp-002/003/004; C-950tiling-002/003.
r5 = C-910-001/006/008/012; C-950bp-010; C-950core-009.
blocked = C-950core-001; C-950rem-011.

## No-device adjudication batch — EXECUTED 2026-08-25 (host compile/grep only, zero card time; all outcomes folded into the rows above)

1. C-950fin-021 — counter-mode: compile shelf spelling (expect refused) vs shipped idiom (expect accepted).
2. C-950fin-022 — value-returning WholeReduceSum/BlockReduceSum (expect refused).
3. C-950td-007 — multi-dim ARAR ReduceSum compile (claim: refused).
4. C-950rem-003 — static_assert on SIMT accessor return types (int32_t) + the `dim` template parameter.
5. C-950rem-001 — `Reg::DataCopy` inside a VF body (availability half).
6. C-950rem-015 — grep: bare `SetLocalMemory(` symbol anywhere in 9.1.0 (expect absent).
7. Q-950arch-15 (for C-950arch-009) — `GetVecLen()` as constexpr loop bound (compile).
8. 9.1.0 re-greps: Ascend035*.ini NpuArch (C-950arch-001); Exp expandLevel default + delegation (C-950core-010/011).
9. C-950tiling-030 — `LAUNCH_BOUND(256)` compile.
10. C-910-005 — `grep -R` for `910C` + mapping on the 910 machine's toolkit (separate job there).
(Optional if trivial: C-950td-008 dtype probes.)

## Feeds into the ratified rounds (delta only — items the triage ADDS to the already-queued lists)

- **Round 3 (card)**: VF semantics probe for MulDstAdd/MulAddDst operand order (C-950arch-002/003,
  C-950core-003) — small, same build lane as 0252 arms; one fired `assert` polarity check riding the
  SIMT vehicle (C-950rem-006); the 48/80/112 stride group as the gather vehicle's first readout
  (C-950fin-025); VREG/GetVecLen readout adjudicates C-950arch-008 + C-950tiling-017; 0238's verdict
  additionally grounds C-950tiling-018.
- **Round 4 (timed)**: StreamK vehicle additionally reads back the workspace request (C-950bp-004);
  the two bandwidth-grid discriminators (C-910-007, C-910-011) with their pre-declared clauses;
  CrossCore timed arm (C-910-009).
- **Round 5 (cheap arms)**: TQue depth/buffer-count probe on 950 (C-950bp-010 + C-950core-009);
  blockCount wrap/clamp sweep (C-910-012, informs C-950td-006); strided-column blockLen arm
  (C-910-006); padding sweep (C-910-008); blk_stride geometry sweep (C-910-001).
- **Close-out**: one CONVENTIONS vocabulary correction covering the unmapped arch tokens
  (1001/2002/5102/3003/3113 — C-950fin-009), `Atlas 350` (C-950bp-011), `DAV_5102` (C-950td-026),
  and the `dav310`/`dav-3510` path species (C-950fin-030, C-950bp-008-resolved).

## Evidence produced during this triage (reading only)

- C-950rem-012: `grep -rn winAlign` over the whole `ascendc-mc2-best-practice` skill → exactly 1 hit,
  the use site (`window-memory-layout.md:119`); the three 下一跳 files contain no alignment statement.
- C-950fin-027: `grep -n 'class TileResidentScan'` on
  `reference/scan/templates/dav310/cum_tile_resident_scan.template` → lines 245 AND 248; sed of
  243-252 shows a doubled `template<...> class TileResidentScan { public:` block.
- C-950core-001 block basis: `book-950/entries/0065-*.md` §4 line 88 — "needs one card per rank".

## Tally correction — 2026-08-25 close-out recount (supersedes the terminal-tally block above)

The terminal-tally block above miscounts its own rows. Recounted mechanically from the table rows
(`grep -E '^\| C-'`, disposition = column 2): **161 distinct IDs in 161 table rows, no duplicates** —
the "161 IDs (160 rows)" line was wrong about the row count.

| class | count | rows |
|---|---|---|
| resolved | 55 | as listed above |
| resolved + noted (hybrid) | 1 | C-950rem-001 (availability half resolved on-compile; spelling half noted) |
| noted (terminal) | 95 | — |
| noted / blocked (hybrid) | 1 | C-950fin-028 (unverifiable as stated; missing resource named) |
| blocked | 8 | C-950bp-002/003/004 + C-950tiling-002/003 (op-framework tiling generator); C-950core-001, C-950rem-011 (second 950 rank); C-910-009 (instrument: bare direct-launch kernel has no working cross-core barrier) |
| vacant | 1 | C-950core-008 |
| **total** | **161** | |

The prose sentence "7 blocked" undercounted by one — its own enumeration names 8 IDs; "96 noted"
reached 96 only by folding the noted/blocked hybrid in silently. **No disposition changed in this
recount — only the counting.** All rows remain terminal; no row is assigned.
