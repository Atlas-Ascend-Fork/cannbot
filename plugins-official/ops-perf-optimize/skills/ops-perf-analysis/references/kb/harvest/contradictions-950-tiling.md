# Contradictions register — domain 950-tiling

> **TRIAGED 2026-08-25**: every row below has a phase-2 disposition in
> `harvest/TRIAGE_DOMAIN_ROWS_20260825.md` (resolved / assigned-to-round / noted / blocked).

Scope: `upstream/skills-dev-main/ops/ascendc-perf-optimize/references/tiling/**` (index,
parameter-analysis, 12 families, all `fallback/` bodies, all 9 Python scripts). Same row format as
`harvest/CONTRADICTIONS.md`; IDs `C-950tiling-NNN`. Per the phase-1 plan's 2026-08-24 amendment §7
this is a per-agent file, merged by the controller in wave 2 — `harvest/CONTRADICTIONS.md` itself is
not edited by this agent.

Every row below was found by reading the file, not by trusting a survey. Where a row extends an
existing `C-0NN` row in the shared register, the extension is stated and the shared row is cited, not
duplicated. Resolution is by a §4 procedure on a named board (RULES.md Art. 7), never by preferring the
more plausible author — each row names the entry that carries it and whose §4 would settle it.

Paths are relative to `upstream/skills-dev-main/ops/ascendc-perf-optimize/references/tiling/`.

---

## C-950tiling-001 · Four family fallbacks labelled `占位`, three of them wrongly
- `index.md:73-77` — the registry marks the elewise, broadcast, conversion and fa fallbacks `（占位）`
- `elewise/fallback/` and `broadcast/fallback/` — each holds a complete `tiling-flow.md` +
  `tiling-fields.md` + script behind a placeholder index of its own
- `conversion/fallback/index.md:3` — states accurately that Transpose is covered and only Concat/Split
  are outstanding; only the registry row is wrong
- `fa/fallback/` — genuinely a stub: two files, 35 lines, no flow, no fields, no script
→ 950 book. Carried by 0152 / 0156 / 0163 / 0169; per-family rows C-950tiling-026…028.

## C-950tiling-002 · StreamK entry gate, prose vs formula (extends `CONTRADICTIONS.md` C-009)
- `matmul/fallback/tiling-flow.md:21` and `matmul/fallback/fallback-algorithm.md:35` —
  "K ≥ 32768 且 B=1 且无 group"
- `matmul/fallback/tiling-flow.md:283` — `Align(K,256) ≥ max(8192, aicNum×256) / sizeof(FP16)`,
  which at `aicNum = 24` evaluates to **K ≥ 4096**
- `matmul/fallback/tiling-flow.md:351` — the file's own worked example (K=16384 → SK) satisfies the
  formula and violates the prose
**What this adds to C-009**: the formula's threshold *scales with `aicNum`* above 32 cores (9216 at
aicNum=72) and *falls* as element width grows, because it divides by `sizeof(FP16)` as a literal. So
"which gate" is a per-core-count and per-dtype question, not one number.
→ 950 book. Carried by 0108.

## C-950tiling-003 · `stepK` upper bound, five statements (extends `CONTRADICTIONS.md` C-008)
- `matmul/fallback/tiling-flow.md:35` — `STEPKA_THRESHOLD | 4`
- `matmul/fallback/tiling-flow.md:159` — "stepK的最大值为8"
- `matmul/fallback/tiling-fields.md:24` — "上限 4，且只能取 2 的幂"
- `matmul/fallback/tiling-fields.md:186` — "stepK ∈ {1, 2, 4}（受上限 4 约束）"
- `matmul/fallback/tiling-flow.md:375` — "{1, 2, 4} … StreamK 有例外 stepK=3", contradicting `:35`
  and `:305` (`kL1 = baseK × min(stepKa, stepKb, **4**)`) in the same file
- `mc2/index.md:64` — emits `step_k: 3`
**What this adds to C-008**: `:305`'s StreamK truncation at 4, and upstream's own L1-utilisation table
(`tiling-fields.md:193-197`) showing `L1_BUFFER_NUM = 3` at 80 % utilisation against 53 % at 2 and
overflow at 4 — i.e. the value the generator cannot emit is the one its own arithmetic prefers.
→ 950 book. Carried by 0109.

## C-950tiling-004 · FullLoad MTE2 bandwidth gates leave [70 %, 85 %) unrouted
- `matmul/fallback/tiling-flow.md:265` — "真 MTE2 bound (带宽 ≥ 85%) → FullLoad"
- `matmul/fallback/tiling-flow.md:266` — "假 MTE2 bound (带宽 < 70%) → SWAT"
- no row, and no default clause, covers utilisation in [70 %, 85 %)
Not two sources disagreeing — one table that does not cover its own input domain. Neither threshold
carries a capture method, a counter name or a board.
→ 950 book. Carried by 0117, cited by 0110.

## C-950tiling-005 · `(al1Size + bl1Size)*sizeof(dtype)` double-counts the element width
- `matmul/fallback/tiling-flow.md:144-145` — `al1Size = ml1 * kl1 * sizeof(dtype)`,
  `bl1Size = nl1 * kl1 * sizeof(dtype)` — already byte counts
- `matmul/fallback/tiling-flow.md:158` — `(al1Size + bl1Size)*sizeof(dtype)要超过48KB`
The stated 48 KB floor is off by a factor of `sizeof(dtype)`: 2× at FP16, 0.5× at FP4.
→ 950 book. Carried by 0111.

## C-950tiling-006 · `nBufferNum` capacity test, strict vs non-strict at equality
- `matmul/fallback/tiling-flow.md:171` — `nBufferNum = (used_4buf < l1Size) ? 4 : 2`
- `matmul/fallback/tiling-fields.md:170-171` — "占用 ≤ `l1_size` → `nBufferNum = 4`"
Different answers at exact equality.
→ 950 book. Carried by 0113.

## C-950tiling-007 · MatMul worked examples: heading vs body, and a CeilDiv off by one
- `matmul/fallback/tiling-flow.md:344` — heading "**M=128, N=81920, K=4096 … → A-FullLoad**"
- `matmul/fallback/tiling-flow.md:346` — the body computes `1 MB > L1/2(=256 KB) ✘ → 不开`
- `matmul/fallback/tiling-flow.md:354` — "kCnt = 24/4 = 6, skSingleCoreK = 2732", where
  `tiling-fields.md:38` defines `skSingleCoreK = CeilDiv(K, aicNum/(mCnt·nCnt))` = `CeilDiv(16384,6)`
  = **2731**
→ 950 book. Carried by 0114. (The unremoved English authoring aside at `:349` is not a contradiction
row — it is a provenance disclosure and is recorded in `harvest/standing/950-tiling.md`.)

## C-950tiling-008 · MC² degradation ladder: prose order vs script order
- `mc2/fallback/tiling-flow.md:130-170` — ladder stated unconditionally as A (16-align) → B (short
  block) → C (relax utilisation to 80 %)
- `mc2/fallback/script/mc2_tiling.py:239-240` — the short-block result is accepted **only if**
  `result.utilization >= UTIL_THRESHOLD_RELAXED (0.80)`, otherwise a relaxed-utilisation uniform
  solution is tried first
The B-before-C order is unconditional in the text and conditional in the code.
→ 950 book. Carried by 0119.

## C-950tiling-009 · Reduction's measured anchors assume 192 KB / 72 cores; its own script says 248 KB / 64 (extends `CONTRADICTIONS.md` C-004, C-006, C-007)
- `reduction/fallback/example/euclidean_norm/experience.md:5,91` — "coreNum=72，UB≈192KB", msprof
  on-board
- `reduction/fallback/tiling-flow.md:201` — the same figures anchor `rGroupCnt=61` /
  `workspaceBytes=7808`
- `reduction/fallback/script/reduction_tiling.py:57-58` — `ub_size: int = 248 * 1024`,
  `core_num: int = 64`
- `reduction/fallback/example/softmax/experience.md:146-147` — "假设 ub_size=248KB",
  `ceil(32/64) = 1` implying 64 cores
**What this adds to C-004**: the 192 KB figure is not a stray sentence — it is the calibration point
of five template budgets, two interleaved budgets, a routing gate and three published self-check
anchors, so it is the value that would have to move or all of them would.
**Re-verification note on C-007**: that row attributes `72` to the reduction *script*. It is not
there — `reduction_tiling.py:58` is `core_num: int = 64`; the 72 comes from the experience file.
`scan/fallback/script/scan_tiling.py:103` does pass 72, but in a `__main__` demo call, not as a
dataclass default.
→ 950 book. Carried by 0131.

## C-950tiling-010 · The two disclosed reduction misfires are quoted against different denominators
- `reduction/fallback/example/euclidean_norm/experience.md:150` — #13 "92.6µs（慢 **28%**）" against
  a fallback of 75.2 µs; `92.6/75.2 = 1.23`, while `92.6/72.9` (row #13's *baseline*) = 1.27
- same file `:151` — #15 "**229µs（慢 10×!**）" against 22.8 µs, which is row #15's `merged` value
So one factor is stated against the baseline and the other against the fallback, inside one table.
→ 950 book. Carried by 0127.

## C-950tiling-011 · `tmp_buf_size` present in all templates or only in AR-FullLoad
- `reduction/fallback/tiling-fields.md:42` — "| `tmp_buf_size` | Reduce API 临时缓冲字节数 | 所有模板 |"
- `reduction/fallback/tiling-fields.md:105` — the template cross-table marks it ✅ for AR-FullLoad and
  ➖ for the other four
→ 950 book. Carried by 0129.

## C-950tiling-012 · Softmax AR-FullLoad denominator: prose vs formula, one FP32 copy apart
- `reduction/fallback/example/softmax/experience.md:93` — "每行 UB 开销 = r_align × (输入×2 + 输出×2 +
  FP32中间量×2)"
- same file `:96` — `rows_per_ub = (ub_size - 1536) / (r_align × (4 + 4×dtype_bytes))`, in which the
  bare `4` covers one FP32 intermediate, not two
20 vs 24 bytes/element at FP32; 12 vs 20 at FP16. This is the file an agent copies when deriving
LayerNorm.
→ 950 book. Carried by 0130.

## C-950tiling-013 · Scan cross-core workspace, two formulas a factor of 4 apart
- `scan/fallback/tiling-flow.md:238` — `workspaceBytes = rBorrow × W × (sizeof(P)+4)`
- `scan/fallback/tiling-flow.md:203-204` — `workspaceBytes = M * wsSegs * WS_SLOT_I32 * sizeof(int32_t)`
  with `WS_SLOT_I32 = 8` (a 32 B slot per segment, 8 B used)
Same workspace, same path; dense vs slot-padded.
→ 950 book. Carried by 0132.

## C-950tiling-014 · Scan cross-core borrow-R trigger, 4096 vs 16384
- `scan/fallback/tiling-flow.md:212` — "R 超长（如 R≥4096）"
- `scan/fallback/tiling-flow.md:158-159` — `MIN_SEG = 8192`; `R >= MIN_SEG * 2` → 16384
- `scan/fallback/tiling-flow.md:191` — mode table: "R >= 16384"
- `scan/fallback/script/scan_tiling.py:81` — `r >= 4096`
→ 950 book. Carried by 0135.

## C-950tiling-015 · Scan minimum segment length, 8192 vs 1024
- `scan/fallback/tiling-flow.md:158` — `MIN_SEG = 8192`, with `segs = min(segs, R / MIN_SEG)`
- `scan/fallback/script/scan_tiling.py:82` — `rBorrow = min(core_num, ceil_div(r, 1024))`
At R = 100000 with 72 cores: at most 12 segments by the first rule, 72 by the second.
→ 950 book. Carried by 0135.

## C-950tiling-016 · The scan script emits the template its own flow document forbids
- `scan/fallback/tiling-flow.md:121` — the streaming template is "仅作参考实现，**勿用于性能路径**"
- `scan/fallback/script/scan_tiling.py:36,87` — the script's four template values are
  `streaming | oneway | twoway | core_partition`, and it returns `streaming` for every indexed
  operator; the tile-resident, lane-parallel and Kogge-Stone templates are absent from its vocabulary
→ 950 book. Carried by 0136.

## C-950tiling-017 · `VREG` used in two unit systems in one file
- `scan/fallback/tiling-flow.md:57` — "alignN > VREG/4=16 元素 fp32", implying `VREG = 64` elements
- `scan/fallback/tiling-flow.md:145` — `guardC = 256 / cBytes  // 哨兵区 = 1 vreg`, implying
  1 vreg = 256 bytes
Consistent only under an fp32 assumption the text never supplies; at fp16 the two readings of the
oneway/twoway gate differ by 2×. (`VLC`, used five times and defined nowhere, is recorded in
`harvest/standing/950-tiling.md` — nothing disagrees with it, it is simply absent.)
→ 950 book. Carried by 0138.

## C-950tiling-018 · TopK fallback budget 240 KiB against a stated usable ceiling of 216 KiB
- `sort/topk_host_tiling.md:209` — "fallback UB budget | 240 KiB（DAV_3510 物理 UB 248 KiB）"
- `sort/topk_host_tiling.md:85` — "fallback 按 240 KiB 预算搜索，但不得超过平台 UB 扣除保留区后的
  可用容量", with the reserve stated as 32 KiB at `:208`
- `sort/topk_host_tiling.md:389,402` — `ubSize - 32KiB` / `usableUb = physicalUb - 32KiB` applied
  generally
248 − 32 = 216 < 240: the constant and the constraint cannot both bind.
**RESOLVED 2026-08-25 (0238 §6):** measured ceilings on 950PR — plain kernel access 262144 (240 KiB fits); kernel
with a SIMT VF: grant cap 221184, access ceiling 229376 (240 KiB = 245760 overruns both). The constraint binds only in
the VF regime; the constant is safe only in the plain one.
→ 950 book. Carried by 0140.

## C-950tiling-019 · The common-tiler routing table has eight rows in one file and nine in another
- `sort/topk.md:240-249` — eight templates, priority 1–8
- `sort/topk_host_tiling.md:185-189` — nine rows, splitting fp32 merge into inter-core and intra-core,
  with a separate `modeType` column whose values (7, 1, 4, 2, 5 …) do not follow the priority order
→ 950 book. Carried by 0143.

## C-950tiling-020 · Sort fallback phase-3 merge rounds: `coreNum` in the docs, `total_tiles` in the script
- `sort/fallback/tiling-flow.md:76` and `sort/fallback/tiling-fields.md:36` —
  `ceil(log_M(coreNum)) - 1`
- `sort/fallback/script/sort_tiling.py:226` — `ceil(log(core_num, M_WAY)) - 1`
- `sort/fallback/script/sort_tiling.py:259` — `ceil(log(total_tiles, M_WAY)) - 1`
The script computes it both ways; Pattern C exists exactly when `total_tiles > coreNum`, so the two
differ on every Pattern C case.
→ 950 book. Carried by 0146.

## C-950tiling-021 · Gather `Dtype Improve`: definition says 32 B, the rule tests 8/4/2 B
- `gather/fallback/tiling-flow.md:19` — "小 dtype 的 innerSize×dtypeSize 若 **32B 对齐**，提升为更大
  dtype"
- `gather/fallback/tiling-flow.md:48-52` — the rule tests `lastAxisBytes % 8`, `% 4`, `% 2`
→ 950 book. Carried by 0147.

## C-950tiling-022 · Gather SIMD threshold: table header says `innerSize × dtypeSize`, gates test `innerSize × improveDtypeSize`
- `gather/fallback/tiling-flow.md:146` — column header "SIMD 阈值 (innerSize × dtypeSize)"
- `gather/fallback/tiling-flow.md:91,106` — both gates test `innerSize × improveDtypeSize`
Equal in bytes only if the gate uses the *improved* `innerSize`; the decision tree's input list at
`:63` carries both without saying which. Up to 8× apart.
→ 950 book. Carried by 0148.

## C-950tiling-023 · Gather's `tiling-fields.md` is mandatory reading and does not exist
- `gather/index.md:13` — "必须深入 fallback/ 子目录读取 … `tiling-fields.md`（TilingData 字段语义）"
- `gather/fallback/index.md:10` — links it, marked "（规划中）"
- `gather/fallback/` contains only `index.md` and `tiling-flow.md`
The only family in this domain without a field document; six symbols in its UB budgets are undefined
as a result.
→ 950 book. Carried by 0148, 0150.

## C-950tiling-024 · Gather calls itself six templates, lists seven, then nine
- `gather/index.md:11,13` and `gather/fallback/index.md:3` — "通用六模板" ×3
- `gather/fallback/index.md:14-22` — a seven-row table, with no `gatherMode` column
- `gather/fallback/tiling-flow.md:155-165` — a nine-row table, marking four templates mode-exclusive
- the decision tree at `:62-116` has ten selectable outcomes including the `EMPTY` guard
The two omitted from the count are the two transpose paths — the whole answer for non-last-axis
`torch.gather`.
→ 950 book. Carried by 0150.

## C-950tiling-025 · One UB-capacity formula in three forms, one dimensionally unclosed
- `elewise/fallback/tiling-flow.md:46,51` — `bufferDivisor = bufferNum * elemBytes` (bytes) with
  `maxElemNum = (ubSize - extraSize) * 8 / bufferDivisor` (bits numerator)
- `elewise/fallback/script/elewise_tiling.py:170-175` — `double_buffer(2) * buffer_num * elem_bytes`,
  no `× 8` — dimensionally closed, and the only copy charging double buffering
- `broadcast/fallback/tiling-flow.md:82` and `broadcast/fallback/script/broadcast_tiling.py:221` —
  `(ubSize - extraSize) * 8 / (bufferNum * maxDtypeBits)` — dimensionally closed
At 248 KiB / fp16 / bufferNum 2 the markdown elewise form yields 507 904 elements against 31 744
(script) and 63 488 (broadcast): an 8× overshoot scaling as `8 / elemBytes`.
→ 950 book. Carried by 0151.

## C-950tiling-026 · elewise fallback index says `占位` over a complete tiling
- `elewise/fallback/index.md:3,18` — "当前为占位文档，内容待补充"; "当前返回：「Elementwise Tiling
  建模暂未收录。」"
- `elewise/fallback/tiling-flow.md`, `tiling-fields.md`, `script/elewise_tiling.py` — same directory,
  covering three of the four bullets the placeholder lists as missing (the fourth, `分支覆盖` in the
  schema sense of 0103, is genuinely absent)
→ 950 book. Carried by 0152.

## C-950tiling-027 · broadcast fallback index says `占位` over a four-branch tiling and a 590-line script
- `broadcast/fallback/index.md:3,18` — placeholder text and refusal string
- `broadcast/fallback/tiling-flow.md`, `tiling-fields.md`, `script/broadcast_tiling.py` — four-branch
  decision tree with a chip-generation split, general UB and multi-core formulas, three alignment
  regimes, and a core-feeding shrink (`script:320`) that appears in no markdown
Three of the four bullets are answered in a *more general* form than stated; the separate
large-tensor/broadcast-tensor buffer plan is not answered at all.
→ 950 book. Carried by 0156.

## C-950tiling-028 · conversion: the registry says `占位`, the family's own index does not
- `index.md:76` — "| Conversion | … | [fallback/](conversion/fallback/)（占位） |"
- `conversion/fallback/index.md:3` — "Transpose 已收录参考策略；Concat/Split 待补充"
- `conversion/index.md:49-131` — a five-step strategy tree, a six-row applicability table and five
  numbered principles carrying four measured penalties
Distinct from 026/027: here only the registry is wrong, and the one document that states the position
accurately is the one the mislabel prevents reaching.
→ 950 book. Carried by 0163.

## C-950tiling-029 · broadcast's DAV_2201 constraints are stated in the document and absent from the script
- `broadcast/fallback/tiling-flow.md:19` — "DAV_2201 → UB Broadcast 静态接口 (rank=1/2, 32B对齐约束)"
- `broadcast/fallback/script/broadcast_tiling.py:373-374` — `if not is_dav3510: return
  "ub_broadcast", 0`; no rank test, no alignment test on that path
- `:57` and `:584` — `is_dav3510` defaults to `True` and the demo hardcodes `True`, so the path is
  never exercised by anything shipped
**Re-verification note**: the 2026-08-24 deep-dive recorded these constraints as "dropped
unconditionally by `broadcast_tiling.py:373`". The line number is right and the description overstates
— the *branch* is preserved and routes correctly; the two *constraints* are absent.
→ 950 book. Carried by 0155. **Art. 1**: the DAV_2201 arm is a 950-era document's statement about
another architecture; it is unverified and does not enter book-910.

## C-950tiling-030 · Scatter thread count restricted to five values, three passes specify a sixth
- `scatter/fallback/tiling-fields.md:45` — "`threads` … **只能取 `{1024, 512, 128, 32, 8}`** ——
  `LAUNCH_BOUND` / `dim3` 要求编译期常量"
- `scatter/fallback/tiling-fields.md:50` and `scatter/fallback/tiling-flow.md:184-186` — ② arb,
  ③ win and ④ `add` use **256**
- `scatter/fallback/tiling-flow.md:163` — section heading "固定 1024 线程" against `:180`
  "**每 block 线程数按 pass 定，不是一律 1024**（实测值，非推导）", seventeen lines apart
→ 950 book. Carried by 0160.

## C-950tiling-031 · Scatter block count divides by a literal 1024 regardless of the pass's thread count
- `scatter/fallback/tiling-flow.md:166-169` — `calc_scatter_blocks(count)` computes
  `need = ceil(count / 1024)` for every element-level pass
- `scatter/fallback/tiling-flow.md:184-186` — three of those passes run 256 threads per block
Blocks are provisioned as if each held 1024 threads; the grid-stride loop covers the remainder.
Upstream does not comment.
→ 950 book. Carried by 0160.

## C-950tiling-032 · Conversion: a decision node whose arms agree, and a leaf naming two strategies
- `conversion/index.md:95-102` — "Step 4: 末轴长度 C 是否 ≥ 32？ ├─ C ≥ 32: → N_LAST ★ 推荐
  └─ C < 32: → N_LAST ★ 推荐 (配合维度合并)"
- `conversion/index.md:112` — "否则: → N_LAST 或 CUT_ONCE", with no discriminator
The node's arms agree deliberately — it exists to override the original template's
`MOVEALIGN_LAST_MIN_ELE = 32` (`:127`) — but nothing in the code block says so, and the reason lives in
a numbered principle 25 lines away.
→ 950 book. Carried by 0164.

## C-950tiling-033 · Convolution's `outputOrder` selects between two whole algorithms and has no stated derivation
- `convolution/fallback/tiling-flow.md:19-21` — "Step 1 — 切分模式决策（GetTilingSplitMode）：
  ├─ outputOrder = M → M-split └─ outputOrder = HW → HW-split"
- no rule, threshold or shape predicate for choosing M over HW appears in `fallback-algorithm.md`,
  `tiling-flow.md` or `tiling-fields.md`
Not two sources disagreeing — the family's most consequential routing input is undefined. Recorded
here because it is a decision-surface defect of the same species as C-950tiling-004.
→ 950 book. Carried by 0166, 0168.

## C-950tiling-034 · The M-split cost model searches over `mDim` and does not contain it
- `convolution/fallback/tiling-flow.md:79` — "回溯搜索四维因子组合 (batchDim, mDim, nDim, groupDim)"
- `convolution/fallback/tiling-flow.md:73-76` — the four cost terms contain `batchDim`, `groupDim`,
  `nDim` and `m1`; `mDim` appears in none of them, and `m1` is undefined in the family
Either `m1` depends on `mDim` (making the sensitivity implicit) or the search optimises over a
variable the objective cannot see.
→ 950 book. Carried by 0167.

## C-950tiling-035 · Convolution L1 full-load levels: `K-only FullLoad` in prose, `ONLY_M/N_FULLLOAD` in the key
- `convolution/fallback/tiling-flow.md:92` — "策略层次：FullLoad → K-only FullLoad → No FullLoad"
- `convolution/fallback/tiling-flow.md:110-111` — `fmpTiling`: 0=FULLLOAD_AL1, 1=ONLY_M_FULLLOAD,
  2=OTHER; `weightTiling`: 0=FULLLOAD_BL1, 1=ONLY_N_FULLLOAD, 2=OTHER
Three levels in both, named differently, with no statement that the middle ones correspond.
→ 950 book. Carried by 0168.

## C-950tiling-036 · GroupNorm is routed to a stub past a family whose procedure covers its computation
- `index.md:24` and `fa/index.md:3` — GroupNorm is an FA-family operator
- `fa/fallback/index.md:3,18` — that family is a genuine placeholder returning
  "FA Tiling 建模暂未收录"
- `fa/fallback/index.md:11` — the placeholder nonetheless sketches GroupNorm's split as
  "Batch 切分 + Group 内归约", a reduction-family sentence
- `reduction/fallback/index.md:14` and `reduction/fallback/tiling-flow.md:350` — LayerNorm/RMSNorm
  (`mean → var → normalize`) are covered with a stated derivation procedure
→ 950 book. Carried by 0169. Whether GroupNorm collapses into `(A1, R, A0)` is that entry's §4 arm 1
and is not assumed here.

---

## Rows deliberately NOT opened

- **Script capacity/core defaults** (four UB values, five `coreNum` values across this subtree) —
  already `CONTRADICTIONS.md` C-006 and C-007. Cited from 0104, 0131, 0141, 0146, 0166 and not
  duplicated. C-950tiling-009 extends them with the reduction family's internal case and corrects
  C-007's attribution of `72` to the reduction script.
- **`matmul/fallback/tiling-flow.md:349`**, an unremoved English authoring aside in a shipped
  reference file. Not a contradiction — one document disclosing its own unfinished edit. Recorded in
  `harvest/standing/950-tiling.md` and carried by 0114.
- **Undefined symbols** (`c0`, `L1_SIZE`, `RPC_WORKSIZE`, `MB_SIZE`, `VLC`, `szA0`, `MIN_OUT_UB`,
  `xAlign`, `minIdxSlice`, `m1`, `ci1`, `co1`, `waste`, `dcache`, `K`, …). Nothing disagrees with
  them; they are absences, recorded in `harvest/standing/950-tiling.md` and carried by 0111, 0128,
  0138, 0148, 0154, 0167.
- **The sort `merge_bytes_per_elem` "contradiction"** reported by the 2026-08-24 deep-dive (64 B in
  the `.md` vs ~104–112 B in the script). Re-verified and **withdrawn**: 64 B is the *merge* phase
  cost and 104/112 B the *output* phase cost, both stated in both artifacts and both agreeing
  (`sort/fallback/tiling-flow.md:69-70`; `sort/fallback/script/sort_tiling.py:121,201`). Two
  different quantities, conflated by the survey. See 0146 §3.
