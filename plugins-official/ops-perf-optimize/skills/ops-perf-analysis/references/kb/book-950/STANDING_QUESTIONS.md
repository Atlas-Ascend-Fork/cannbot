# Standing questions — book-950

Named measurements this book still owes: each row is a question raised while harvesting, answerable
only on the named board unless the row says otherwise. Duplicates across domains are consolidated at
first verification touch, never silently dropped. Slot discipline varies by register, and that is
disclosed per row rather than normalised away.

---

# Register: 950-core

# Standing questions — domain `950-core` (perf-optimize diagnosis / technique cards / comm-compute)

Per-agent file for the 950-core harvest block (`book-950/entries/0001-0099`), to be merged into
`book-950/STANDING_QUESTIONS.md` by the controller in wave 2. Block form follows the parent book's
`book/STANDING_QUESTIONS.md`: each question names a **measurement** and its **readout**, never a
subject heading.

```
## Ln · <one-line question>
MEASUREMENT: <one command, or one procedure runnable from the answering agent's ground>
READOUT:     <what to report: the value(s) and where they land>
POSED:       <date> · from <what raised it>
STATE:       UNANSWERED | answered → <entry ID, with date>
GATES:       <entries that cannot be promoted until this is answered>
```

Everything below is UNANSWERED: this domain's harvest touched no device (RULES.md Art. 6). Where a
question is answerable by read-only inspection of the installed toolkit
(`/usr/local/Ascend/cann-9.0.0-beta.2`), that is stated — those can be answered without a card, and
two of them already were during this harvest (recorded as answered, with the entry that carries them).

---

## L8 · Do `MulDstAdd` and `MulAddDst` both exist, and are they the same function?
MEASUREMENT: read-only grep of the installed toolkit headers (no execution):
             `grep -RIn "inline void MulDstAdd\|inline void MulAddDst" $T/arm64-linux/asc/impl`
READOUT:     every declaration with path:line, the implementation each forwards to, and each one's
             supported dtype set from its `SupportType<...>` static_assert
POSED:       2026-08-24 · from vec-03 using `MulDstAdd` against the regbase whitelist's `MulAddDst`
             plus its "absent from the lists → unavailable until verified in installed SDK headers"
STATE:       answered → 950:0246 (2026-08-24). Both exist, as different functions in `AscendC::Reg`:
             `MulDstAdd → FusedMulDstAddImpl` (emits `vmadd`; {half,float,bfloat16_t}; ZEROING only)
             and `MulAddDst → MulAddDstImpl` ({u,i}16/32/64 plus the float types); a third,
             LocalTensor-level `MulAddDst` exists at membase level. **Still open**: which operand
             order each implements — the two upstream documents state different ones.
GATES:       950:0022 (the vec-03 technique claim), 950:0246's semantics half

## L2 · What are the four `CacheMode` enumerators, and what do the two upstream never names do?
MEASUREMENT: read-only: `grep -RIn "enum class CacheMode" -A6 $T --include=*.h`; then, on a named
             950 board, the four-way variant of 950:0045's L2-bypass experiment
READOUT:     the enumerator list with values; per mode, `aiv_time`, L2 hit rate and DDR bytes in the
             one-shot and re-read regimes
POSED:       2026-08-24 · from mem-05 using two of them and deferring the enumeration to the header
STATE:       partially answered → 950:0047 (2026-08-24). Enum membership read from
             `arm64-linux/asc/impl/basic_api/utils/kernel_utils_macros.h:235-240`:
             `CACHE_MODE_DISABLE=0, CACHE_MODE_NORMAL=1, CACHE_MODE_LAST=2, CACHE_MODE_PERSISTENT=4`.
             **Still open**: what LAST and PERSISTENT do — a header cannot say.
GATES:       950:0045, 950:0047 promotion beyond `corroborated`

## L4 · Is `PipeBarrier<PIPE_V>` after a VF segment required on a 950 board?
MEASUREMENT: on a named 950 board, four builds from one source tree — barrier present/absent ×
             `--cce-auto-sync` on/off — nothing else changed; `md5sum` each object, disassemble and
             count emitted barriers; run ≥8 shapes incl. a narrow VF tail, 5 repetitions
READOUT:     per build: bit-exact comparison against a reference over full output buffers, and
             `aiv_time` median + spread. Which of the four declared outcomes in 950:0259 §5 obtains
POSED:       2026-08-24 · from the four-way disagreement C-950core-004 (verification queue B2)
STATE:       UNANSWERED — the unanswered state is itself a seed
GATES:       950:0259, and the stop-rule text of 950:0022

## L2 · What is the usable UB size on a named 950 board, and does DoubleBuffer halve it?
MEASUREMENT: arm 1 read-only — `grep -Rn "GetCoreMemSize\|CoreMemType" $T/arm64-linux/asc/include`,
             plus any `platform_config/*.ini` UB field; arm 2 on a named board — print
             `GetCoreMemSize(CoreMemType::UB)`, then bisect the largest `N` for
             `InitBuffer(que, 1, N)` and for `InitBuffer(que, 2, N)`
READOUT:     the queried byte count; the two bisection limits and their ratio; the board token from
             the driver readout (950PR or 950DT — a value for one is not a value for the other)
POSED:       2026-08-24 · from vec.md:102's bare "248KB / 950" against the reduction family's
             192 KB-under-a-measurement-banner (register row C-004) — verification queue B3
STATE:       UNANSWERED
GATES:       950:0018, and every tile-budget red line that depends on it (950:0020, 950:0027,
             950:0042, 950:0043, 950:0044)

## L2 · Does raising a TQue's depth consume UB, or only `InitBuffer`'s BUFFER_NUM?
MEASUREMENT: on a named 950 board, bisect the largest `size` for `InitBuffer(que, 2, size)` at queue
             depth 2 and at depth 4; then vary `BUFFER_NUM` 2→3 at fixed depth as the control
READOUT:     the four bisection limits; `depth_is_free` = (max_size(depth 4) == max_size(depth 2))
             exactly, and the control `buffernum_costs` which must be true for either to count
POSED:       2026-08-24 · from nobound-02:81 correcting nobound-01:35 without propagation
             (C-950core-009)
STATE:       UNANSWERED
GATES:       950:0019, 950:0052 (its queue-depth precondition)

## L4 · Does TQue allocation return buffers in FIFO order?
MEASUREMENT: on a named 950 board, three builds — unreordered, 950:0052's reordering, and the same
             reordering with the per-tile computation artificially lengthened — over ≥16 shapes,
             5 repetitions each; if the toolkit exposes it, log the address returned by each
             `AllocTensor`
READOUT:     bit-exact comparison of both reordered builds against the unreordered one, per shape
             **and per repetition** (a rare mismatch is the signal, not noise); the allocation-address
             sequence against the release order
POSED:       2026-08-24 · from nobound-02:84 — "这一点文档无保证"
STATE:       UNANSWERED
GATES:       950:0053, and the transfer of 950:0052 to any kernel other than the one measured

## L9 · Does the 0.52 lane cut separate "a bound" from "no bound"?
MEASUREMENT: on a named 950 board, ≥24 pre-labelled kernels spanning the four bound shapes; apply
             both treatments to every kernel — the highest lane's diagnosis-page technique, and the
             no-bound reordering of 950:0052 — 5 repetitions, randomised build order
READOUT:     per kernel: `max_lane_ratio`, gain under each treatment, and the run-to-run spread;
             the sign of (gain_lane − gain_reorder) plotted against `max_lane_ratio`, and where it
             crosses zero — if it crosses
POSED:       2026-08-24 · from metrics.md:57, the only numeric bound cut in the skill, stated once
             inside one worked example
STATE:       UNANSWERED
GATES:       950:0005, 950:0006

## L9 · Are the ratio thresholds decision lines or only routing hints?
MEASUREMENT: the same case set as the previous question; for each published cut — VEC 50/65/80,
             `aiv_vec_ratio` 90, Cast 20, transcendental 30, `aiv_mte3_wait_ratio` 0.4 — record the
             pre-change value and the sign of Δ`aiv_time` under the treatment that cut prescribes
READOUT:     per cut, the fraction of cases where the cut's side predicts the sign of Δ`aiv_time`,
             counting only cases whose |Δ| exceeds that case's spread, with the `indeterminate`
             count reported separately rather than dropped
POSED:       2026-08-24 · from metrics.md:63 — "阈值附近仍以 `aiv_time` 实测为准"
STATE:       UNANSWERED
GATES:       950:0009, 950:0011, 950:0015, 950:0016

## L9 · Is the ideal overlap bound Σ/max attainable, and what does attainment mean for a dependent kernel?
MEASUREMENT: on a named 950 board, two kernels with matched lane budgets (within 5%) and opposite
             dependency structure — four independent stages, and the same four chained element-wise;
             apply every available reordering to each and record the maximum attainment reached
READOUT:     `max_attainment` for both kernels with spreads; whether the independent one reaches
             ≥0.95 and whether the dependent one is capped below 0.75
POSED:       2026-08-24 · from metrics.md:43 stating a modelling assumption inside a fenced block of
             arithmetic (the measurement/inference split, RULES.md Art. 2)
STATE:       UNANSWERED
GATES:       950:0008, and the attainment language in 950:0007 and 950:0052

## L9 · Does the reordering of nobound-02 transfer beyond the operator it was measured on?
MEASUREMENT: on a named 950 board, reproduce the three configurations on the measured operator
             (RMSNorm+RoPE+KVCache paged scatter-write, T=10752, BlockDim 56), then repeat on two
             other operators with the same trigger signature; report all three timing conventions;
             sweep T ∈ {64, 512, 4096, 10752}; run the reversal ablation on every operator
READOUT:     per operator and convention: Δ vs the before-build with spread; `aiv_mte3_wait_ratio`
             and overlap factor before/after; the reversal's sign; and bit-exactness against the
             before-build (which is also the FIFO question above)
POSED:       2026-08-24 · from nobound-02 being the library's only measured card, on one operator
STATE:       UNANSWERED
GATES:       950:0052 promotion; 950:0054's convention claim

## L9 · Which timing convention should a reported gain use?
MEASUREMENT: on a named 950 board, three changes with different mechanisms (ordering, transfer
             volume, compute volume), each measured under all three conventions — msprof Task
             Duration, back-to-back, and L2-dirtied p50 with an unrelated streaming kernel between
             launches
READOUT:     a 3×3 table of relative gains with spreads; whether any two conventions disagree beyond
             spread; whether the three changes rank identically under all three
POSED:       2026-08-24 · from nobound-02:69-71,86 — the same change is −32.9%, −37.6% and −2.5%
STATE:       UNANSWERED
GATES:       950:0054, and the acceptance clause of every technique entry's §5

## L3 · Which alignment boundary actually costs, and is there one constant or several?
MEASUREMENT: arm 1 read-only — locate the alignment fields in the installed headers and any
             `platform_config/*.ini`; arm 2 on a named 950 board — time a fixed-size copy at every
             source/destination residue modulo 128
READOUT:     the timing curve against residue, and the set of residues at which it steps by more
             than the run spread; each step's granularity against the four values upstream uses
             (16 B, 32 B, 64 B, 128 B)
POSED:       2026-08-24 · from mem-01:43 — "950 历史提交中出现 16B、32B、64B、128B 等不同约束，不能抽成
             一个全局常量" — and mem-05:40's 128 B cache line
STATE:       UNANSWERED
GATES:       950:0039, 950:0040, 950:0041

## L5 · Is the 32-byte alignment penalty on RVEC load/store real, and how large?
MEASUREMENT: on a named 950 board, one rotate-half VF built two ways — whole-row contiguous copy
             (second segment misaligned) vs two `DataCopyPad` calls with the second at an aligned
             offset — swept over aligned and unaligned segment lengths and over row counts
READOUT:     `aiv_time` with spread; the count of aligned vs unaligned RVECLD/RVECST forms in the
             trace; peak UB for both builds (the pad is the price)
POSED:       2026-08-24 · from vec-14:14, the premise of that whole card, stated without measurement
STATE:       UNANSWERED
GATES:       950:0039

## L5 · What does an int64 RegTensor cost in physical registers, and where does spilling begin?
MEASUREMENT: on a named 950 board, compile a VF holding K live `RegTensor<int64_t>` and the same with
             `RegTensor<int32_t>`, sweeping K; read the disassembly for distinct physical vector
             registers referenced and for the first spill/reload pair
READOUT:     `phys_per_logical(dtype)` and `K_spill(dtype)`; whether
             `K_spill(int64) ≈ K_spill(int32)/2`
POSED:       2026-08-24 · from vec-12:9's "实际 preg 占用 ×2"; the *representation* half is already
             corroborated by the installed headers (950:0037), the *cost* half is not
STATE:       UNANSWERED
GATES:       950:0036; 950:0037 promotion beyond `corroborated`

## L5 · What does `Exp<T, 0, ...>` actually compute, and what does it cost in precision?
MEASUREMENT: on a named 950 board, build one exp-dominated kernel at expandLevel ∈ {0, 2, 10};
             count vector instructions per element from the disassembly; sweep inputs including
             near-zero and near-overflow arguments; compare against a double-precision host reference
READOUT:     `aiv_time` and instructions per element per level; max relative error per level and per
             dtype, with the argument at which it occurred
POSED:       2026-08-24 · from vec-11:14's LUT description against the installed header's delegation
             branch (C-950core-010)
STATE:       UNANSWERED
GATES:       950:0035

## L6 · Which form of the MC² balance condition is correct?
MEASUREMENT: on a named 950 board set, one compute-then-comm operator at measured R ≈ 3,
             `longBlockCnt` fixed at 3, sweeping `M_short / M_long` across both candidate boundaries
             (`1/R` and `R`) in ≥10 sixteen-byte-aligned steps, each with its own long/short tiling
             data; repeat at R ≈ 0.3
READOUT:     `argmax_ratio` — the ratio of the fastest split — with its neighbours and the spread;
             which of the three declared readings in 950:0065 §5 obtains
POSED:       2026-08-24 · from C-950core-001 (the diagram and the formula pair opposite operations)
STATE:       UNANSWERED
GATES:       950:0065, 950:0066 (the corrected-predicate proposal), 950:0067's region endpoints

## L6 · Does the published search emit any non-uniform split at all?
MEASUREMENT: transcribe `pipeline_balancing.md:330-368` verbatim into a script (no fixes) and run it
             over a grid: M ∈ {1024, 2048, 4096, 8192}, R ∈ {0.3, 0.5, 0.95, 1.0, 1.5, 3.0, 9.8},
             baseM/baseN ∈ {128, 256}, N_core ∈ {20, 24, 32}. No device needed.
READOUT:     per tuple: candidates emitted, how many have a non-zero tail, and prunes per rule (so
             an empty set is attributed to the rule that emptied it); the control is the same script
             with P4 deleted
POSED:       2026-08-24 · from C-950core-002 — `tail = M % hs < hs ≤ ρ × hs` makes P4 fire always
STATE:       UNANSWERED — and answerable today without a card
GATES:       950:0066

## L6 · Do the MC² pruning thresholds (TAIL_MIN 128, util 80/50, tcCap, Top-N 15) select the optimum?
MEASUREMENT: on a named 950 board set, for one compute-bound and one communication-bound operator,
             measure **every** candidate surviving pruning — not only the top fifteen — plus a sample
             of candidates each rule discards, per the ten-iteration multi-rank protocol
READOUT:     the rank correlation between `est_time` and measured time; the theoretical rank of the
             measured optimum; the median measured gap between adjacent candidates (against the
             claimed 5-10 μs); and, per rule, whether any discarded candidate beat the survivors
POSED:       2026-08-24 · from pipeline_balancing.md:284-316 — four thresholds, no derivation
STATE:       UNANSWERED
GATES:       950:0067, 950:0068, 950:0069, 950:0073

## L4 · Does the MTE2 pollution test detect communication wait, and which of its two forms governs?
MEASUREMENT: on a named 950 board set, from the isolation campaign extract `aic_mte2_ratio` for the
             full and compute-only builds at three problem sizes chosen so `ratio_full` falls below,
             near and above 0.5 (where the two stated forms disagree); independently establish
             whether communication is waiting, without using the MTE2 ratio
READOUT:     `gap = ratio_full − ratio_pure` and `frac = ratio_pure / ratio_full` per size, both
             verdicts, and whether they agree with the independent observation; the control is a
             non-MC² single-card operator, whose gap must be ≈ 0
POSED:       2026-08-24 · from bound_diagnosis.md:76 — the 0.1 and 0.8 forms coincide only at
             `ratio_full = 0.5`
STATE:       UNANSWERED
GATES:       950:0060, and the Step 0 branch of 950:0005

## L7 · Is the isolation decomposition closed — do the two isolated phases sum to the fused time?
MEASUREMENT: on a named 950 board set, at `tileCnt=1`, measure the full build, the
             communication-only build and the compute-only build per the ten-iteration protocol, at
             three problem sizes; check each isolated build's profile shows the *absence* of the
             removed phase
READOUT:     `closure_error = (T_comm + T_compute − T_full) / T_full` per size; the per-rank tables;
             and `md5sum` per build (identical hashes across configurations mean the isolation edit
             did not take effect)
POSED:       2026-08-24 · the assumption is nowhere stated upstream, and 950:0055's masking-ratio
             ceiling of 1.0 depends on it
STATE:       UNANSWERED
GATES:       950:0055, 950:0058, 950:0059, 950:0070

## L7 · What is the jitter of the MC² capture protocol, and does it bound the comparisons built on it?
MEASUREMENT: from the ten-iteration multi-rank capture already performed, retain all rows rather than
             the last five; compute per rank and metric Count/Min/Max/Mean/Std/CV/range, and the
             cross-rank spread of per-rank means at the same round index. No script is written into
             the user's tree and nothing is installed (this is 950:0074's side-effect-free arm)
READOUT:     `cv(rank, metric)`; whether the 5-10 μs candidate spacing the search must resolve
             exceeds `max(cv) × T`; whether five warm-up iterations suffice (mean of 6..10 against
             mean of 26..30) and whether the slowest rank is the same rank across repeated blocks
POSED:       2026-08-24 · from MC2_JitterDiagnose.md being the only jitter treatment in the skill and
             being unreachable (C-950core-017), while the capture protocol reports no spread at all
STATE:       UNANSWERED
GATES:       950:0057, 950:0069, 950:0073, 950:0074

## L8 · Are `npusim` and `cannsim` the same entry point on an installed toolkit?
MEASUREMENT: read-only — locate both names in the installed toolkit and compare targets
             (`command -v` is execution; use `find`/`ls -l` on the toolkit's `bin`/`tools` trees and
             read any wrapper script rather than running it)
READOUT:     both paths, whether one is a symlink or wrapper for the other, and the version each
             reports in its own help text as read from the file
POSED:       2026-08-24 · from nobound-02:11 — "cannsim 已更名 npusim，两名字同入口" — while the
             simulator skill documents only `cannsim`
STATE:       UNANSWERED — answerable without a card
GATES:       950:0010's simulator arm

## L1 · Is DoubleBuffer effective, and does the alternation signature detect when it is not?
MEASUREMENT: on a named 950 board, one kernel built three ways — BUFFER_NUM=1; BUFFER_NUM=2;
             BUFFER_NUM=2 with the loop body in nobound-02's "before" order — captured both as an
             instruction trace and as msprof `aiv_time`
READOUT:     `alternation` (fraction of kernel-span deciles containing both an MTE2 and a VECTOR
             segment) per build, the speed-up of BUFFER_NUM=2 over 1, and whether the third build
             classifies as non-alternating despite DB being configured
POSED:       2026-08-24 · DoubleBuffer is named ~90 times in this skill, is a routing criterion on
             three diagnosis pages and the precondition of its only measured card, and has no
             technique card of its own
STATE:       UNANSWERED
GATES:       950:0012, 950:0042, 950:0052's entry gate

---

## Establish-from-scratch (no upstream authority in this scope; needed by several entries)
These are not disagreements — no source in this domain states them at all, and entries above depend
on them. Each is a first-time establishment on a named board, per part.

- **Vector register width / `GetVecLen()`** — 950:0252 records the rule that the lane count is
  `GetVecLen()/sizeof(T)`; the value is nowhere established, and vec-03's aside "A5 fp32=64" would
  imply a 256-byte register. GATES 950:0252, 950:0029, 950:0038.
- **AIC and AIV core counts per board token** — every MC² utilisation rule divides by `N_core`
  (from the host print) and the single-core evidence is a "56-core mean"; no core count for 950PR or
  950DT is established here. GATES 950:0068, 950:0007, 950:0075.
- **L2 capacity per board token** — 950:0045's whole predicate is "working set below L2"; no value
  is established. GATES 950:0045, 950:0047, 950:0075.
- **Peak bandwidth and the machine balance point (Ops/Byte)** — memory.md's third judgement
  condition is "计算密度低（Ops/Byte 低于硬件能力）" and no bandwidth figure, balance point, or method
  for computing an operator's arithmetic intensity from msprof output exists anywhere in this scope.
  The measurement is 950:0075 §4 step 1 (sweep FMAs-per-loaded-element and find the knee).
  GATES 950:0075, and the memory arm of 950:0005.
- **Physical vector-register budget** — 950:0036's "×2 preg" has no denominator. GATES 950:0036.
- **`DataCopy` block granularity (32 B?) and repeat granularity (256 B?)** — assumed by the
  alignment cards. GATES 950:0039, 950:0040, 950:0041.

---

# Register: 950-tiling

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

---

# Register: 950-arch

# Standing questions — domain `950-arch`

Per-agent file for the 950-arch harvest block (`book-950/entries/0201-0299`), for merge into
`book-950/STANDING_QUESTIONS.md` by the controller in wave 2. Each question is a named measurement
owed, answerable only on a card, cross-linked to the entries it gates.

Nothing below has been run; harvest touches no device (RULES.md Art. 6).

---

## Q-950arch-01 · B1 is RESOLVED as far as headers can resolve it — what remains is a compile
`950:0246` establishes from the installed CANN 9.0.0-beta.2 headers that `MulAddDst` and `MulDstAdd`
are two distinct `AscendC::Reg::*` templates with different dtype sets and different lowerings
(`vmula` / `vmadd`). A header declaration is a second *origin*, not a run. Owed: compile a VF calling
each name for a 3510 target and confirm both resolve; instantiate each at `int32_t` and confirm the
dtype partition is enforced by the `static_assert`s rather than merely written in them.
Gates: `950:0246`, `950:0247`, `950:0248`, and every the delivered skill statement that names an FMA API.

## Q-950arch-02 · which operand of `MulDstAdd` is the destination (B1's second half)
`950:0247` rests on one upstream card plus vendor implementation *comments*. Owed: the crafted
evaluation with `dst=3, src0=5, src1=7` — 22.0 under vec-03's reading, 38.0 under the
instruction-cost JSON's. One run decides it and simultaneously settles `C-950arch-003`.
Gates: `950:0247`, `950:0248`.

## Q-950arch-03 · B2 — is a `PipeBarrier<PIPE_V>` needed after a VF on 950
`950:0259` lays out four upstream passages and three positions, all one origin. Owed: the isolated
toggle — bit-compare AND timing, barrier the only variable, auto-sync ON and OFF as a fourth build
pair, disassembly cross-check to confirm the compiler did not reinsert the barrier into the
no-barrier build. Without the auto-sync arm a null result is unattributable.
Gates: `950:0259`, `950:0260`, `950:0261`, and every generated VF epilogue.

## Q-950arch-04 · B3 — is 950 UB 248 KB, and how much of it is usable
`950:0209` finds `ub_size=253952` in all 32 installed DAV_3510 inis and in agreement with npu-arch;
192 KB and 256 KB appear in four other upstream documents. Owed: `GetCoreMemSize(UB)` on a full part,
**and** the allocation boundary, which is the only thing that distinguishes physical from usable and
would surface a reservation like `topk_host_tiling.md:209`'s "240 KiB usable of 248 KiB physical".
Gates: `950:0209`, `950:0238`, `950:0239`, C-003, C-004, C-006, and every reduction budget.

## Q-950arch-05 · what does `GetRuntimeUBSize()` return in each SIMT regime
Upstream states 216 KB mixed / 248 KB non-mixed; three upstream files derive 216 from a 256 KB base
that no installed 950 ini reports. The arithmetic coincidence `256−8−32 = 248−32 = 216` makes this
undecidable on paper. Owed: call the accessor in a mixed and a non-mixed SIMT kernel, and separately
bisect the allocation boundary in each — a reported size and an allocatable size differ by the 8 KB
compiler reservation, which is the whole question.
Gates: `950:0238`, `950:0237`, `950:0239`.

## Q-950arch-06 · what is a DCache reservation worth
Upstream states a 32 KB minimum and a 128 KB maximum, and its own recommended snippet reserves the
maximum without saying why. No source in scope prices the choice. Owed: the value curve (discrete
gather, residual swept 32/64/96/128 KB) **and** the cost curve (a kernel whose tiling actually
consumes UB), on one die in one session. Either curve alone is half the trade.
Gates: `950:0237`, `950:0239`.

## Q-950arch-07 · does the DCache compile check cover a runtime-computed residual
`950:0237` records upstream's claim that a build check fires when DCache falls below 32 KB. A
compile-time check cannot see a `SetLocalMemorySize` value computed on the host from shape. Owed: the
two-arm build — constant residual and runtime residual — and a record of what happens at launch for
the second. If the guard is compile-time-only, the delivered skill must say so.
Gates: `950:0237`, `950:0239`.

## Q-950arch-08 · is `arch35` used as a build selector anywhere, and what does it select
`950:0202` and `950:0205` establish that `arch35` names two `NpuArch` values in this install. What is
*not* established is whether any build system actually routes on the two-digit form rather than on
`__NPU_ARCH__ == 3510`. Owed: build one kernel behind each selector for a 950 target and compare
what is chosen. The risk is entirely in the answer to this question.
Gates: `950:0202`, `950:0203`, `950:0205`.

## Q-950arch-09 · does the per-dtype `[DtypeMKN]` table describe the Cube array
`950:0220` and `950:0221` read the ini section as array shapes, following upstream's own derivation.
Owed: throughput ratios fp8/fp16, int8/fp16, int4/fp16, fp32/fp16, int32/int8 on one die in one
session, plus the `baseK` plateau sweep that makes the ratios attributable to array width rather than
to anything else that scales with precision. HiF8, MXFP8, MXFP4 and HF32 have **no ini row at all**
and rest on one upstream assertion each.
Gates: `950:0214`, `950:0220`, `950:0221`, `950:0222`, and every Cube roofline.

## Q-950arch-10 · is the vector register 256 bytes or 256 bits
`950:0219` and `C-950arch-008`. The ini field carries no unit; three upstream sources say bytes and
one JSON suffix says bits. Owed: `GetVecLen()`, plus the poisoned-store lane count at two dtypes
(fp32 → 64 and half → 128 under bytes; 8 and 16 under bits), plus the overrun count beyond the
expected extent. The two dtypes must move together by a factor of two.
Gates: `950:0219`, `950:0273`, `950:0252`, and every VF loop bound.

## Q-950arch-11 · the warp width of 32 and the four warp schedulers
`950:0234`. Neither has an accessor and neither has an ini field; upstream marks the scheduler count
as a public-or-experience value and marks the warp width as nothing at all. Owed: the thread-count
staircase (steps at 33/65/97 under a 32-lane warp) with the divergence control that must flatten it,
and the warp-occupancy staircase with a second workload body — a knee at 4 that moves when the body
changes was never measuring schedulers.
Gates: `950:0234`, `950:0235`, `950:0240`.

## Q-950arch-12 · the register band edges and the SIMT register file
`950:0236`. The four bands multiply to ≈128 KB, which is upstream's own unverified register-file
figure, so the table is self-consistent and unsupported. Owed: the spill staircase at three live-
variable counts, gated on a disassembly showing stack traffic at the same points — a timing knee
without spill instructions is measuring something else.
Gates: `950:0236`, `950:0232`.

## Q-950arch-13 · establish-from-scratch items this harvest partially relocated
The 2026-08-24 deep-dive listed six figures with no upstream authority. Two moved:
**256 B vector-register width** now has an ini field (`vector_reg_width`, `950:0219`), and
**32 B block granularity** has a *neighbouring* field (`ubblock_size=32`) that is a UB block size and
**not** a DataCopy granularity — the two were deliberately not equated. Still unrelocated and owed
first-time establishment: 256 B repeat granularity, cache-line 128 / 256 B, DCache size,
`repeatTimes ≤ 255`. The installed ini additionally supplies `ubbank_size=4096`, `ubbank_num=16`,
`ubsubbank_num=64`, `ubburst_in_one_block=32`, `ubbank_group_num=8`, none of which any upstream
document in scope mentions and none of which is claimed by an entry.

## Q-950arch-14 · `predicate_reg_width=32` does not obviously fit a 128-lane mask
Recorded in `950:0219` §3 and deliberately left unclaimed. 128 b16 lanes would need 128 mask bits;
the field says 32. Either `MaskReg` is per-32-bit-group, or the field means something else, or one
of the two numbers is wrong. Owed: a `CreateMask`/`UpdateMask` probe at b16 and b32 recording how
many lanes one `MaskReg` can actually gate. No entry rests on this; it is logged so the next
harvester does not quietly assume one of the three readings.

## Q-950arch-15 · is `GetVecLen()` usable in a `constexpr` initialiser
`950:0253` records that the canonical VF loop template hardcodes `constexpr uint32_t kRepF32 =
256 / sizeof(float)` while `950:0252` (from another skill) forbids exactly that. **Which defect this is
depends on one file read**: if `GetVecLen()` is `__simd_callee__` rather than `constexpr`, the
substitution is ill-formed and the literal is forced, not careless — the entry then moves from `trap` to
`boundary` and 0252's rule is unimplementable as literally stated. Owed: locate `GetVecLen()`'s
declaration in `include/ascendc/basic_api/interface/reg_compute/` (`grep -R`, not `-r`) and compile the
substitution. Cheapest open item in this block.
Gates: `950:0252`, `950:0253`, `950:0219`.

## Q-950arch-16 · does `MicroAPI` RESOLVE to `Reg`, not merely share its names
`950:0244` located `namespace MicroAPI = Reg;` at `kernel_macros.h:136` in the installed CANN
9.0.0-beta.2, exactly where upstream said it would be — but a declaration read is not a compile. Owed:
the `static_assert(&Reg::X == &MicroAPI::X)` form, plus a symbol-by-symbol sweep of
`reg_compute/` under both spellings. Two namespaces carrying the same names is not an alias, and the
whole 950 card library is written in the `MicroAPI` spelling while the whitelist governs `Reg::*`.
Gates: `950:0244`, `950:0245`, `950:0250`.

## Q-950arch-17 · how much of the `reg_compute/` surface does the whitelist omit
`950:0245` records that the whitelist's absence rule is the correct procedure and that it worked twice
during this harvest (B1's `MulDstAdd`, the `MicroAPI` alias). What is unmeasured is how often it will be
needed: enumerate every symbol in `include/ascendc/basic_api/interface/reg_compute/` and diff against the
whitelist's VF-safe tables. A large difference means the escape hatch is the primary path rather than an
exception, which changes how the delivered skill should present the tables. File read; no device.
Gates: `950:0245`, `950:0246`, `950:0250`.

## Q-950arch-18 · are the twelve VF hard constraints enforced, and what happens when they are not
`950:0254`. Upstream calls them 硬约束 and names no mechanism for any of the twelve. Owed: one violation
per build, thirteen builds plus a control, recording for each whether it compiles, whether the diagnostic
names the constraint, and — the payload — whether it produces correct output. Constraints 3 (`uint16_t`
induction), 4 (no arrays) and 6 (no runtime `if/else`) have plausible silent-degradation shapes
(scalarisation, spill) that a compile-only check would miss. Compile-only plus disassembly; no device
needed for the decisive arms.
Gates: `950:0254`, `950:0253`.

## Q-950arch-19 · the `LocalMemBar` five-row partition, and keeping it apart from B2
`950:0258`. Three rows say "not needed" and two say "needed"; the over-application error is the one
upstream emphasises, so both directions must be exercised. **Do not share a run with Q-950arch-03**:
`LocalMemBar` is a VF-internal `__simd_callee__` primitive and `PipeBarrier<PIPE_V>` is a kernel-side pipe
barrier, and resolving one with the other's evidence is a live hazard — upstream's arch35 ordering
guarantee is stated for *between* VFs, not *within* one.
Gates: `950:0258`, `950:0259`.

## Q-950arch-20 · is the 950 Vector roofline actually a lower bound
`950:0264`. The model is `max(mte2, vector, mte3)` plus four calibrated corrections, and three of the
four only matter in the small-shape / few-tile / uneven-split regimes where operators actually get
written. Owed: the theory-versus-measurement sweep across nine operators and seven shapes, **with each
correction ablated in turn** — an unablated model that fits says nothing about which of its five terms did
the work. A measured latency below `theoretical` anywhere kills it.
Gates: `950:0264`, `950:0266`, `950:0267`, `950:0270`.

## Q-950arch-21 · re-derive the 56-row instruction cost table, per row
`950:0266`. Upstream ships the calibration instrument and its committed board data, so this is a
re-derivation rather than an invention. Two things a per-instruction sweep cannot reach and that need
their own arms: the **issue-slot contention** claim (a `1slot` reduction and a `1slot` Pack must degrade an
`Add` stream the same way — one mixed kernel being slow is an anecdote), and the **transcendental
overlap** claim, which is the one modelling assumption in the Vector time model that is not a
per-instruction number. Also owed: `uncovered_apis` — `Reg::*` symbols with no row at all.
Gates: `950:0266`, `950:0267`, `950:0264`.

## Q-950arch-22 · can `check_calibration.py` fail
`950:0272`. The calibration discipline ("绝不为让某个算子通过而调常量") is the strongest evidence-culture
statement in this scope, and its enforcement is unverified. Owed: run the shipped gate, then perturb one
constant in a scratch copy and require the gate to fail **naming that constant**. A gate observed only in
its passing state has not been shown to be a gate — and the audit arm has its own version of the same
trap: a history audit that finds zero unaccompanied constant edits counts only if it was first shown to
detect upstream's own documented 112-MB change-and-revert.
Gates: `950:0272`, `950:0266`, `950:0270`.

## Q-950arch-23 · does SIMT direct GM access actually beat a staged SIMD gather, and where
`950:0243`. Upstream gives two qualitative lists (Gather/Scatter/hash/sort vs dense matmul/long sequential)
and **no crossover point**. The capability and the benefit are separate claims: Arm A establishes that a
`__gm__` dereference in a `__simt_vf__` compiles and is correct; Arm C establishes where it wins. Owed
with the sweep: index locality contiguous → shuffled, and the DCache residual arm (32/64/128 KB), which
is the only thing that would tell a tiling routine what to reserve for a gather-shaped operator.
Gates: `950:0243`, `950:0237`, `950:0239`, `950:0270`.

## Q-950arch-24 · the MC² constraint rows and the A5 window offset
`950:0274` and `950:0277`. Two multi-card items, both needing ≥2 cards and both with predicted **hang**
outcomes, so a declared watchdog timeout and card release are mandatory — an un-timed arm holds the group
on a shared machine. For 0274: one violation per run across the five `headMSize` rows, recording where
each fails (host derivation / allocation / run time) or that it does not. For 0277: dump the first 2 MB of
`windowsIn[rankId]` against a known partner-written payload and read off the offset — the whole claim is
one number, and an offset of 0 would mean every kernel written to the rule is reading 1 MB into its own
payload. Capture protocol for both: ≥10 iterations, first 5 discarded, mean of last 5, **max across
ranks** (a mean would hide the straggler that sets the latency).
Gates: `950:0274`, `950:0277`.

## Q-950arch-25 · every published throughput figure is arithmetic — measure one and the pedigree tiers become visible
`950:0222` (Cube), `950:0223` (Vector), `950:0224` (bandwidth). These three have **different evidential
status and are printed in one table**: Cube TFLOPS is arithmetic over four ini fields (corroborated
inputs, no measurement); the Vector base is ini-derived but its ×2 dual-issue factor is a
public-or-experience value upstream itself qualifies ("并非所有 Vector 指令均支持双发"); bandwidth has no
ini field at all and is the weakest number in the hardware table. Owed, in priority order: the paired
`2slot`-vs-`1slot` instruction-mix ratio (`950:0223` Arm B — a single-arm throughput number attributes
nothing to dual issue), then single-core Cube MACs/cycle with the `baseK`-halving control, then sustained
streaming above L2. Note that upstream's own table marks the Vector rows `[¹]` and the Cube rows not,
which reads as a confidence claim the derivation does not support.
Gates: `950:0222`, `950:0223`, `950:0224`, `950:0214`, `950:0220`, `950:0221`, `950:0264`, `950:0270`.

## Q-950arch-26 · the three CV path changes, and the one that breaks ported kernels
`950:0225` (L0C→UB, UB→L1 added), `950:0226` (L1→GM, GM→L0A/L0B **deleted**), `950:0227` (SSBuffer).
The deletion is the item to run first: upstream states it in a trailing blockquote after three numbered
additions, and a port that relied on those paths fails in an unknown way. Owed for `950:0226`: attempt
both deleted paths and record which of three outcomes occurs — refused at build, refused at run, or
**silently substituted with the two-hop route**, which is the branch with no detector and which doubles
MTE traffic invisibly. For `950:0227`: search the headers for an SSBuffer API at all; `not-exposed` is a
live outcome and would make the tabulated 256 KB unaddressable. For `950:0225`: the GM-byte delta, not the
duration, is the attributable measurement.
Gates: `950:0225`, `950:0226`, `950:0227`, `950:0211`, `950:0212`, `950:0264`.

## Q-950arch-27 · does BufferID actually retire the SetFlag/WaitFlag pairing requirement
`950:0228`. `npu-arch` says BufferID 消除原 set/wait 强制配对需求; the regbase sync guidance a 950
implementer actually follows says **SetFlag/WaitFlag 必须成对出现** and is explicitly scoped to Ascend950
(`950:0262`). One repo, two layers, no reconciliation written anywhere. **Safe posture until measured:
keep the pairs** — that branch has a known failure mode and the other has an unknown one. Owed: search
the headers for a BufferID API (file read, cheapest step, decides whether the question is even live),
then the three-variant paired/unpaired kernel with a declared watchdog — a missing wait can deadlock and
an un-timed arm holds a die on the shared machine. Also owed: whether the seven queues upstream lists
reconcile with the four Vector-core pipes the regbase material names.
Gates: `950:0228`, `950:0262`, `950:0259`, `950:0264`.

## Q-950arch-28 · the SIMT execution-model claims that have no magnitude
`950:0235` (branch divergence serialises), `950:0240` (per-core share must be warp-aligned),
`950:0241` (VF declaration contract). All three state a rule and **no cost**: upstream never says what
divergence costs, what misalignment costs, or what violating the declaration contract produces. Each needs
a staircase with a control that isolates the named cause — for divergence, warp-uniform branching must
stay flat while intra-warp branching rises; for alignment, multiples of 32 must sit on one curve and
non-multiples off it. All three rest on the warp quantum being 32 (`Q-950arch-11`), which is itself
unverified with no ini backing — so run that first or the staircases attribute nothing. `950:0241` is
compile-only and is the cheapest of the three.
Gates: `950:0235`, `950:0240`, `950:0241`, `950:0234`, `950:0232`, `950:0243`.

## Q-950arch-29 · is the kernel-side / VF-side API partition enforced, per name
`950:0250`. Thirteen names appear in **both** whitelist tables — `Add`, `Sub`, `Mul`, `Max`, `Min`, `And`,
`Or`, `Xor`, `Adds`, `Muls`, `Compare`, `Select`, `Move` — differing only in a `Yes`/`No` column and a
header root. Owed: per name, compile the kernel-side form inside a `__simd_vf__` and record whether it is
rejected **and whether the diagnostic names the reason**; a name that compiles is a hole the toolchain is
not closing. Also owed (file read, no device): diff both declarations of each dual-listed name on the four
axes — namespace, parameter style, mask/control contract, and precision contract (`Reg::Div`'s 1-ULP
dagger, `950:0249`, is a fourth axis upstream's three do not name). That diff is the table a consuming
agent needs and no upstream document supplies.
Gates: `950:0250`, `950:0244`, `950:0245`, `950:0249`, `950:0258`.

## Q-950arch-30 · the b16 load consumes half a register, which collides with the lane-count rule
`950:0257`. `LoadAlign<T, DIST_UNPACK_B16>` 只加载 VL/2 字节 (64 half = 128B) — so a b16→f32 widening
path steps **64 elements per iteration, not 128**. A naive application of `950:0252`'s rule
(`GetVecLen()/sizeof(T)` = 128 for half) gives twice the correct stride and skips half the data. **No
source states this collision**; it is derived in `950:0257` §2 from a code comment. Owed: poison the
source past the expected extent and count consumed bytes (128, not 256), then run the loop both ways
against a host reference. Also owed: the alignment *symptom* — upstream states the 32-byte requirement and
never says what a misaligned `LoadAlign` does, and fault / shifted / truncated / garbage need different
repairs.
Gates: `950:0257`, `950:0252`, `950:0219`, `950:0253`.

## Q-950arch-31 · α is one data point, and the roofline applies it everywhere
`950:0271`. The read/write HBM contention constant α ≈ 0.3 rests on **one** reported measurement: 32 MB
each way, 1:1 ratio, one part, one date (copy 18.28 µs vs max(read,write) 14.19 µs → α = 0.288). The
roofline applies it at every size and every ratio. Owed: sweep transfer size 4→256 MB and recompute α at
each point (if it drifts, the correction is a curve and the scalar is a fit at one size); sweep the
read:write ratio 1:1→8:1 (the `max + α×min` form predicts the penalty vanishes as the ratio grows).
Also owed: whether `gm_rw_contention` and `l2_aware` **double-count** — upstream says the `l2_aware` curve
已含读写争用 and never says the two knobs are exclusive. Fixture: a pure-read and a pure-write arm must
show no contention penalty, or the harness is attributing something else to α.
Gates: `950:0271`, `950:0270`, `950:0264`, `950:0218`.

## Q-950arch-32 · L2 is the one buffer that is shared, and every figure for it is sole-tenant
`950:0218`. UB, L1, L0A/B, L0C and BT are invariant across all 32 installed 950 ini files; **L2 and the
core counts are the two that move** — L2 spans 16, 32, 96, 112 and 128 MB. Upstream publishes two of the
five. Worse, L2 is cross-core shared, so every residency figure in this block (`950:0270`'s knee included)
is implicitly a sole-tenant figure and neither origin says so. Owed: the knee sweep **per SKU**, plus the
co-tenant arm — run the sweep again with another kernel streaming on the same die and require the knee to
move down. If it does not move, the sweep was never measuring L2 residency. This matters directly for the
shared machine these runs happen on.
Gates: `950:0218`, `950:0270`, `950:0264`, `950:0217`.

---

## Method notes owed to the controller (not measurements)

**The form checker is line-oriented and a wrapped phrase evades it.** `tools/check_entries.sh:58`
requires the literal string `upstream asserts` in a harvested entry. Entry `950:0221` failed the
check with the phrase present but split as `Upstream\nasserts` across a line break; it passed after
the line was rewrapped, with no change of meaning. Same species for any other single-line predicate
in that checker (`INDEX: *none`, `NOT YET RUN`, the `## N ·` headings). Not repairable from this
block — `tools/` is outside its write partition — so it is reported rather than fixed. A checker that
can be satisfied or evaded by line wrapping is checking the wrapping.

**Two deep-dive claims failed re-verification** and are corrected inside `950:0259` §3 rather than
here: the `vf-microapi-patterns.md:347` position is about `PipeBarrier<PIPE_ALL>` *inside* a
`__VEC_SCOPE__`, not `PIPE_V` after a VF; and positions 2 and 4 of the four ("hardware guarantees
order" and "the compiler inserts barriers") are compatible, not mutually exclusive as the survey
stated. The survey located the material correctly and characterised two of the four passages more
sharply than the files support.

**A third re-verification correction, logged against my own entry rather than a survey.** The 2026-08-24
deep-dive listed "256 B vector-register width (hence VL_FP32=64)" among six figures with **no upstream
authority**, to be established from scratch. That is now partly wrong in two directions and both are
recorded in `950:0219`: the installed CANN 9.0.0-beta.2 ini carries a named `[AICoreSpec]` field
`vector_reg_width=256`, so the figure has a second origin; and three upstream files state VL = 256 B in
prose, so it had upstream authority the survey did not find. What the survey got right is that nothing
had *measured* it. The neighbouring `ubblock_size=32` was deliberately **not** equated with the
deep-dive's "32 B DataCopy block granularity" item — a UB block size and a copy granularity are different
quantities, and equating them would be the inference this book exists to refuse.

**One checker-satisfying rewrite, self-reported.** Entry `950:0221` failed `check_entries.sh` with the
required phrase present but wrapped as `Upstream\nasserts`. The fix was a line rewrap with no change of
meaning. Recorded because the *fix satisfying the marker* is not the same as the entry having been
wrong — and a checker a rewrap can satisfy is a checker that can be satisfied without the property.

> 2026-08-24 correction to Q-950arch-11 (from the 950-remainder miner, applied by the controller):
> "neither has an accessor" is half wrong — `GetWarpSize()` is declared at
> `kernel_simt_common_intf.h:28`, and `warpSize` defaults four shuffle primitives. Still true: no
> ini field, never measured. 950:0234 §4 corrected in place with a dated note.

---

# Register: 950-bp

# Standing questions — domain `950-bp`

Named measurements, undefined symbols and unresolved routing questions owed by the a later harvest pass harvest
of the 950 side of `upstream/skills-dev-main/ops/ascendc-performance-best-practices/**`
(book-950 entries 0301–0349). Per the phase-1 plan's 2026-08-24 amendment §7 this is a per-agent
file, for merge into `book-950/STANDING_QUESTIONS.md` by the controller in wave 2.

Nothing below has been run on a device. Harvest touches no device (RULES.md Art. 6). Questions marked
`[no-card]` need **no** device and are answerable in this phase; where one was answered during this
harvest it says so, and where one was left the omission is recorded rather than hidden — an unrun
question that cost nothing is a finding about this agent, not about upstream.

---

## Q-950bp-01 · `[no-card]` — the DAV_3510 UB bank geometry is corroborated; nothing about it is measured
`950:0314` establishes from upstream plus all 32 installed `NpuArch=3510` ini files that the UB is
16 banks in 8 groups of two, each bank 16 KB of 512 rows (as `ubsubbank_num=64 × ubbank_size=4096`),
and that the file's "256 KB" is physical bank capacity while `ub_size=253952` is what the allocator
exposes — the 8 KB gap being the same term `950:0238`'s SIMT budget subtracts.

Owed, and **all of it needs a card**: the aliasing-period sweep (`950:0314` §4 Arm A) that would make 16
and 8 measurements rather than ini fields; the allocation boundary (Arm B) that distinguishes
physical from available; and the read-read port question (`950:0315`, Arm C).
Gates: `950:0314`, `950:0315`, `950:0316`, `950:0317`, `C-950bp-001`, `C-950bp-006`.

## Q-950bp-02 · the DAV_3510 read-read conflict rule has ONE statement in the world
`950:0315`. `ub_resident_design.md:48-54` is the only place in the entire upstream repository that
states a DAV_3510 read-read conflict condition, and the two-read-port mechanism it rests on appears
in no ini field in the installed toolkit (searched: no `read_port`, `write_port` or equivalent in any
`NpuArch=3510` file). This is a single-source load-bearing claim, which is a different and in some
ways worse condition than a contradiction — there is nothing to compare it against.
Owed: `950:0315` §4's six-cell truth table on a named 950 board. Gates: `950:0315`, `950:0316`.

## Q-950bp-03 · there is no DAV_3510 padding constant anywhere
`950:0316`. Every avoidance recipe in the shelf — 256 B padding, the `64 * 1024 - (…)` sizing,
`blk_stride = 1` — is stated for NPU 220x, and their derivations use 16 groups of 4 KB banks. The
arithmetic does not carry to 8 groups of 16 KB. This book therefore hands a consuming skill a
**method** and deliberately no number.
Owed: `950:0316` §4 Arm C's padding sweep, whose curve minimum is the missing constant.

## Q-950bp-04 · the instruction queue depth has no value in any document or ini
`950:0304`. MTE2 Preload's entire mechanism is "the instruction count between PING and PONG exceeds
the chip's preset instruction queue depth", stated twice as a hardware constant that software cannot
raise. The depth's *value* appears nowhere in the family, nowhere else in the repository, and in no
field of the installed CANN 9.0.0-beta.2 `platform_config` set.
Owed: `950:0304` §4 Arm 2 — insert `N` independent instructions between PING and PONG for
`N = 0, 8, 16, 32, 64, 128` and find the knee. That knee is the first number anyone would have.

## Q-950bp-05 · undefined symbols in load-bearing formulas, matmul and conv families
Grouped by family, with the entry that carries each. This extends `harvest/standing/950-tiling.md`
S1, which found the same species in the analysis shelf; several symbols are undefined on **both**
shelves, which is recorded because it means neither can be resolved by consulting the other.

**matmul** (`950:0310`, `950:0311`) — `RPC_WORKSIZE` and `MB_SIZE` (an additive term in StreamK's workspace
request, also undefined in the analysis shelf per `950:0111`); `c₀` (the K alignment quantum in
Full-Load's capacity test, likewise undefined on both shelves); `N_pc`; `Bytes_total^{nl}`;
`isInnerAxisAlign` (`950:0307`, SWAT mechanism B's entry condition); `CalUsedCoreNum`, `preSplitMax`,
`secSplitMax` (`950:0308`, mechanism C's host search).

**matmul, MX variants** (`950:0312`, `950:0313`) — `MXFP_DIVISOR_SIZE_LOCAL` and
`MXFP_MULTI_BASE_SIZE_LOCAL` appear in every scale buffer-size expression in two files and are
defined in neither. `950:0312` §3's worked ladder only reconciles if the first is 32; that is an
inference, not a statement.

**conv** (`950:0348`, `950:0349`) — `cinAligned`, `kUbSize`, `srcKSize`, `co1Opt`, `GN0`, `K0_VAL`,
`BLOCK_BYTES`, `nStride`, and the enlarge factor's selection rule. `950:0349` infers `cinAligned = 16`
from `16 × 9 = 144` plus the fp16 K0; upstream never says it.

**elementwise** (`950:0321`) — `maxRow` and `rowPerHeadCore`, the two operands of the adaptive
double-buffer decision. The snippet cannot be lifted without resolving them.

**sort** (`950:0330`, `950:0332`) — `tile` in `optimized multi-core`'s condition `k × ⌈D/tile⌉ ≤ tile`;
`mode 8`; the special key values 900001/900002/900003; `SCHEM_MODE`, `DYN_UBUF_SIZE`,
`KERNEL_TYPE_MIX_AIV_1_0` (`950:0333`) — named without definitions, ranges or defaults.

**flash_attention** (`950:0334`, `950:0336`) — `SCALAR%` and `SCALARLDST%` have no denominator, no counter
and no tool named anywhere, and the whole sub-class routing rule is a comparison between them;
`PRE_LAUNCH`, `stackSeqCount`, `maxKVStackLen`, `coreWsBase_`, `blockStackNum_`; `CVSharedParams`'s
actual field set and `SYNC_MODE` (`950:0337`).

→ Owed: `[no-card]` a read-only header and source sweep over an installed 950-era CANN toolkit
(`grep -Rn`, not `-r` — these trees contain symlinked directories), recording value, path and
toolkit pin per symbol. **Not run.** Then, per board, a runtime query for the capacity symbols.

## Q-950bp-06 · `Atlas 350` is a product name used as an architecture label, defined outside the truth source
`950:0314` §3, `C-950bp-011`. The DAV_3510 column of the shelf's only bank-structure table is headed
`Atlas 350`. `npu-arch`'s 产品映射表 — the repository's self-declared 真源 — has no such row; it maps
ASCEND950 = DAV_3510 = **Atlas A5** = 950DT / 950PR. The name is defined in a third skill
(`ascendc-regbase-best-practice/.../cast-api.md:5`, "Atlas 350 加速卡（arch35 / DAV_3510）") and
appears 1042 times repo-wide.
Owed: `[no-card]` — a decision by the controller on whether `form/CONVENTIONS.md`'s board-token list
should record `Atlas 350` as a known alias, the way it already handles the operator's undefined
"910C". This book used `family-claimed(unverified)` and `950PR, 950DT` from ini filenames instead.

## Q-950bp-07 · `[no-card]` — the shelf-wide index-cell versus document-scope sweep
Three instances of one species were found by hand and each cost an entry: `950:0319` (a `DAV_3510` cell
routing to a document whose every capacity constant names a 910 part), `950:0329` (a
`DAV_2201 / DAV_3510` cell routing to a document that fences itself to A2 in its first paragraph),
and `950:0347` (a `DAV_3510` cell over seven files that name no chip at all).
Owed: the complete sweep across all thirteen families, producing a table of *index cell
architecture* against *document self-attribution*. It needs no device, it is one grep plus a read,
and it was **not** run. Its output is directly what `the delivered skill`'s pedigree rule needs.
Gates: `950:0319`, `950:0329`, `950:0347`, `C-950bp-007`, `C-950bp-010`.

## Q-950bp-08 · `[no-card]` — the shelf-wide evidence-register census
`950:0338` classifies five FlashAttention effect statements into three registers — measured with a
case, an expectation labelled as one, and a stated refusal to invent a number — and finds one row
mis-placed (`预期 SCALAR 下降 12% - 30%` under a heading reading `已验证效果`).
Owed: the same classification across every design document in the shelf, with the five classes
`950:0338` §4 defines. The distribution is what tells `the delivered skill` how much of this library may be
restated in measured voice at all. Needs no device; **not run**.

## Q-950bp-09 · `dav310` is a directory name that resolves to no architecture
`950:0346`, `C-950bp-008`. Four DAV_3510-marked families keep their device templates under
`dav310/`; two use `dav3510/`. `DAV_310` is not a DAV number; ASCEND310P is DAV_2002 and ASCEND310B
is DAV_3002. No definition exists anywhere in the repository (searched, with a positive control on
`DAV_3510` to validate the search). `SKILL.md:125` instructs the consumer to preserve the directory
name when copying templates into its own project, so the ambiguity propagates outward.
Owed: `[no-card]` — extend the search to build scripts, CMake fragments and conversion tooling to
find whether anything *consumes* the name; **not run**. Then, on a card: compile one `dav310`
template with `--npu-arch` set to a 310-family value and confirm it fails, which would make the name
affirmatively misleading rather than merely undefined.

## Q-950bp-10 · the FlashAttention sub-class table is not a partition and states no precedence
`950:0334` §3. A case at `SCALAR% = 97 %`, `SCALARLDST% = 96 %` satisfies the SCALAR row, the
SCALARLDST row and the MIXED row simultaneously; the table gives no ordering and the prose resolves
it only for MIXED. Separately, the shelf index (`SKILL.md:41`) and the family guide
(`flash_attention/guide.md:19-26`) state the SCALAR condition differently — `> SCALARLDST%` against
`≥ 80 % ∧ < SCALAR%` — so a case at 60/30 routes to SCALAR by one and to nothing by the other.
Owed: `950:0334` §4 Arm 1, which measures whether the table-selected branch is the branch that wins.
Same repo, one origin, so nothing here is resolvable by reading (RULES.md Art. 3, Art. 7).

## Q-950bp-11 · one arithmetic slip and three prose slips, recorded and not spent as entries
None of these is worth an entry and each would mislead an implementer, so they are parked here.

- `fullload_design.md:52` and `scale_coalescing_design.md:117` label an ASCII diagram
  `L1_SIZE = 524 KB`; 524288 B is 512 KiB. The inequalities in the same files use `524288 B`
  correctly. (`950:0301` §3.)
- `fullload_design.md:5` states the technique compresses **total** MTE2 bytes by `(T−1)/T`;
  its own §7 row states it correctly as `(T−1)/T × Bytes_side / Bytes_total`. The §7 form is the one
  consistent with the file's own headline (16–20 % at T=5, not 80 %). (`950:0311` §3.)
- `scale_coalescing_design.md:234` cross-references `modeling_reference.md §2.2` for A-Full-Load.
  No file of that name exists in the shelf; the document is `fullload_design.md`. (`950:0313` §3.)
- `conv_common_perf_experience.md` labels its two loop nests `4 层` and `8+ 层` while the code blocks
  beneath them show six and nine `for` statements. The *difference* — three axes removed — is stated
  identically by both. (`950:0348` §3.)
- `flash_attention/guide.md:32` writes `端到端耗时平均提升 14.74%` where the table shows time
  falling. Direction unambiguous from the numbers; the summary sentence is loose. (`950:0335` §3.)
- The `AXIS_LEN == 7` sorting network's four source lines are **not** independent, though the code
  comment above the neighbouring 17-element table claims per-line independence for that one; greedy
  layering gives 6 layers for 4 source lines. Correctness is unaffected — both networks pass the
  exhaustive zero-one check. (`950:0331` §3.)

## Q-950bp-12 · what a benefit-less design document is worth, and how `the delivered skill` should carry it
`950:0337` and `950:0338`. Two techniques in this shelf ship with a mechanism, disqualifying
conditions, named acceptance criteria — and no benefit figure, by explicit refusal. `the delivered skill`'s
pedigree rule (`CONTRACT.md`) distinguishes `verified` from `harvested` voice; it does not yet
distinguish "harvested with a number" from "harvested with a declared absence of one".
Owed: `[no-card]` — a controller decision on whether the skill's routing surface should carry a
third register for this case. This agent's view, for the record: it should, because the two
techniques are *more* honest than several that carry percentages, and flattening them into the same
"unverified" bucket loses that.

## Q-950bp-13 · measurements this shelf reports that nobody can evaluate
Every one of these is a real before/after on a real part, and not one carries a repeat count, a
variance figure, a board, a tool or a CANN pin. They are listed together because the omission is
systematic and because two of them are small enough that the missing spread carries the whole claim.

| figure | entry | why it cannot be evaluated |
|---|---|---|
| 66.000 → 63.288 µs, −4.1 % (MTE2 Preload) | `950:0304` | no spread; a −4 % effect against an unstated floor |
| 183.87 → 170.07 µs, −7.5 % (A-Full-Load) | `950:0311` | MTE2-segment and task deltas reported as the same −7.5 % |
| 34.4 → 31.27 µs, −9 % (scale coalescing) | `950:0312` | the same table's "before" cell contradicts the file's own ladder (`C-950bp-005`) |
| 42.4k → 30.2k cycles (pingpong) | `950:0302` | two variables changed; upstream itself says the gain is not what it looks like |
| 18353 → 18076 cycles, −1.51 % (SCALARLDST) | `950:0336` | **smallest effect in the shelf, three-decimal precision, no spread at all** |
| 8 cases, −33.22 % scalar / −14.74 % e2e | `950:0335` | cases identified by index only; four techniques applied together, none attributed |

Owed: each entry's §4, each of which establishes a variance floor **first** and reports it beside
every ratio. `950:0336` §5 goes further and declares that if the floor exceeds 1.51 % the comparison is
reported as `indistinguishable` and no verdict is issued — which is the only honest handling of a
number that small.

## Q-950bp-14 · deliberately unmined material, with reasons
Recorded so that a later agent does not re-derive the decision, and so that a wrong decision is
visible. Full reasoning per family is in `harvest/claims/ascendc-performance-best-practices--004…`.

- `reference/common/datacopy_optimization_design.md` — 351 lines, and every scoped figure in it
  names Ascend 910B (the 70 %/90 %/100 % alignment bandwidth ladder, the 512 B optimum, the DMA
  efficiency bands). Not this book's (RULES.md Art. 1). Card 004.
- `reference/common/tail_block_design.md` — carries no 950 marker; its GatherMask row is already
  carded (card 003) and routed to the other book.
- `reference/mc2/` — the analysis-layer twin of `ascendc-perf-optimize/references/comm-compute/`,
  already carried by `950:0055`–`950:0075`. Card 005 records the diff that was **not** performed.
- `reference/reduce/`, `reference/scan/`, `reference/gather/`, `reference/conversion/`,
  `reference/broadcast/`, `reference/scalar/`, `reference/elementwise/vector_efficiency_design.md`,
  `reference/regbase/` — mined only where they diverge from the block-0101 tiling twins or from the
  `950:0351`+ block another a later harvest pass agent owns. Cards 006–010 record what each was skipped for and what a
  later pass should look at first.

## Q-950bp-15 · things this agent left undone that cost nothing
Listed separately from the device-gated questions above, because the excuse is different: these
needed no card and were simply not done.

- The header sweep for the symbols in Q-950bp-05 (`950:0304`, `950:0311`, `950:0348`, `950:0349` all cite it).
- The `RoundMode` enumerator inventory (`950:0324` §4 Arm 2) — the semantics upstream asserts for
  `CAST_ROUND` and `CAST_RINT` are cited to no header.
- The `StridedSlice` operator-binary inventory per CANN package (`950:0325` §4 Arm 1). A partial read was
  done and is reported in that entry as *not* evidence about upstream's runner.
- Five of the ten rows in the Reg API rename table (`950:0344` §4 Arm 1); four were checked and hold, one
  is contradicted by this toolkit's layout.
- `GetUintDivMagicAndShift` / `Simt::UintDiv` were never located in any installed header (`950:0342`).
- The `float4` / `half4` type declarations were not located; the naming convention was corroborated
  only over the types the cache-hint sweep happened to cover (`950:0341`).

---

# Register: 950-rem

# Standing questions — domain `950-rem`

Per-agent file for the 950-remainder harvest block (`book-950/entries/0351-0399`), for merge into
`book-950/STANDING_QUESTIONS.md` by the controller in wave 2. Each question is a named measurement owed,
answerable only on a card (or, where marked, by a file read that was in scope and not done), cross-linked
to the entries it gates.

Nothing below has been run; harvest touches no device (RULES.md Art. 6).

Questions are ordered cheapest-first within each group, because several of the most consequential items in
this block are settled by a compile or a single dump rather than by a sweep.

---

## Group A — settled by a file read or a preprocessor run (no device)

## Q-950rem-01 · does `Reg::DataCopy` survive the project's real include set, and does it survive the next pin
`950:0351` establishes from the installed CANN 9.0.0-beta.2 headers that `Reg::DataCopy` and
`Reg::LoadAlign` are defined in adjacent pairs forwarding to identical `DataCopyImpl<...>` instantiations,
that only the `*Align` spelling is declared in the public interface header, and that the header defining
`DataCopy` announces itself as internal and "maybe removed in the future". Owed, and cheap: preprocess a
translation unit with the project's normal kernel prologue and confirm `Reg::DataCopy` resolves without
including the impl header directly; then repeat the two INDEX greps against every other CANN tree on this
machine (`cann-8.5.0`, `ascend-toolkit`, `cann`) and record per pin whether it is declared in the interface
header, defined only in the impl header, or **absent**. A pin where it is absent turns "internal" into
"removed" and settles what the delivered skill must emit.
Gates: `950:0351`, `950:0353`, and every generated VF load/store.

## Q-950rem-02 · what does the reg-compute architecture gate actually admit
`950:0352`. `kernel_reg_compute_intf.h:26-27` wraps all twenty-one includes in a conditional admitting
`__NPU_ARCH__` ∈ {3510, 5102, 3003, 3113} or `__ASC_NPU_HOST__`. Owed: six preprocessor runs over a one-line
file (each of the four values, unset, and the host macro) recording whether `Reg::LoadAlign` survives into
the output. No code generation, no device. The readout is a table, and a **larger** admitted set than the
guard's text is the interesting outcome — it would mean another header re-includes the surface unguarded and
the gate is decorative. Owed separately and equally cheap: the diagnostic an agent actually meets when the
gate is closed (predicted "no member named …", naming no architecture).
Gates: `950:0352`, `950:0351`, `950:0354`.

## Q-950rem-03 · how large is the VF-safe whitelist's gap, in both directions
`950:0354` records 76 `__simd_callee__` names in the public `reg_compute/` interface headers against the
whitelist's 50 function names: **27 declared-and-unlisted**, and **one listed-and-undeclared** (`Reg::Divs`,
0 hits in the reg-compute tree, present only in the kernel-side scalar header). Both numbers are grep-derived
bounds. Owed: an AST-derived enumeration (`clang -Xclang -ast-dump` over a TU with `__NPU_ARCH__=3510`) to
replace the lower bound, and a per-name compile of all 28 disputed names recording resolve / does-not-resolve
/ resolves-but-rejected-inside-`__VEC_SCOPE__` — the third outcome is what the `VF Function?` column is about
and no file read reaches it. This is `Q-950arch-17` with numbers attached; the reverse direction
(listed-and-absent) is new and is the one the whitelist's absence rule structurally cannot catch.
Gates: `950:0354`, `950:0353`, `950:0245`, `950:0250`.

## Q-950rem-04 · which SIMT headers actually declare the symbols the guide attributes to them
`950:0375` and `C-950rem-014`. `simt_api/common_functions.h` declares `asc_vf_call` and none of the four
index accessors; `simt_api/device_sync_functions.h` declares `asc_syncthreads`/`asc_threadfence`/
`asc_threadfence_block` and no `SyncAll`. Owed, all compiles: (a) do the documented includes resolve the
documented symbols, i.e. does transitive inclusion rescue the documentation; (b) is `SyncAll` reachable at
all from a realistic SIMT include set (`kernel_operator.h` + `kernel_simt_intf.h`), because if it is not,
`multi-core-sync.md`'s entire recipe is uncompilable as written; (c) the bisected minimal include set per
symbol, which is what the delivered skill should carry in place of upstream's two lines.
Gates: `950:0375`, `950:0374`, `950:0376`, `950:0377`.

## Q-950rem-05 · which of the eight absent `ASCRT_*` constants are really absent, and are the near-twins substitutes
`950:0388` and `C-950rem-010`. Eight documented names are defined in none of the three named headers; six
have near-twins under a terser scheme. Owed: compile a TU referencing all 38 documented names with only the
documented headers, then again with all of `simt_api/` (a name defined through another macro or a
`constexpr` would be missed by the grep — `math_constants.h:19` uses a `constexpr`); and, for each of the six
pairs, compare values **bit-for-bit**. If the twins are not identical they are not substitutes and the
repair is not a rename table. Also owed and cheap: the values of every resolving constant against a
correctly-rounded reference — `ASCRT_PIO4_F`'s nine-digit literal is the first to check.
Gates: `950:0388`.

## Q-950rem-06 · does the tiling-validation snippet compile, and does the order of the five checks matter
`950:0362` and `C-950rem-009`. The copyable calling-convention block invokes
`CheckDtypeSupportAndCombination` with a flat dtype set; the file defines `CheckDtypeSupport` taking a
per-input vector. Owed, host-side only, no device: compile the block as given; then run all 120 permutations
of the five checks over an input set in which each input violates **two** rules at once, recording per input
which check fires and whether any permutation crashes or names the wrong field. Order matters iff the
reported field changes with the permutation.
Gates: `950:0362`, `950:0363`.

## Q-950rem-07 · is `winAlignBytes` defined anywhere upstream
`950:0392` and `C-950rem-012`. The symbol occurs once in `window-memory-layout.md` and is defined nowhere in
it; the file's own 下一跳 section names `multi-core-formulas.md` and `double-buffer-protocol.md`, neither of
which this harvest opened. Owed: read those two files and grep the tree. A definition reduces the finding
from an undefined term to a missing cross-reference — a much smaller defect — and the search costs minutes.
Gates: `950:0392`.

## Q-950rem-08 · `GetWarpSize()` exists — a correction owed to `Q-950arch-11`, and what it does not settle
`Q-950arch-11`, recorded against `950:0234`, states that the warp width has no accessor. The installed CANN
9.0.0-beta.2 declares `__aicore__ inline int32_t GetWarpSize();` at
`asc/include/interface/simt_api/cpp/kernel_simt_common_intf.h:28`, and `kernel_simt_warp_level_intf.h:18-51`
uses a bare `warpSize` identifier as a default argument to four shuffle primitives. `950:0234` and
`book-950/STANDING_QUESTIONS.md` are outside this block's write partition and were **not** edited. Owed:
call the accessor and record the value — and then **do not stop there**. A returned constant is not a
measured warp quantum: `Q-950arch-11`'s thread-count staircase (steps at 33/65/97 under a 32-lane warp,
with the divergence control that must flatten it) is still owed and is what would establish the number.
The half of `Q-950arch-11` that stands is "no ini field and never measured".
Gates: `950:0234`, `950:0374`, `950:0235`, `950:0240`.

## Q-950rem-09 · fourteen warp-level primitives are declared and documented nowhere in scope
`asc/include/interface/simt_api/cpp/kernel_simt_warp_level_intf.h` declares `WarpAllSync`, `WarpAnySync`,
`Uni`, `WarpBallotSync`, `WarpActiveMask`, `WarpShflSync`, `WarpShflUpSync`, `WarpShflDownSync`,
`WarpShflXorSync`, `WarpReduceAddSync`, `WarpReduceMaxSync`, `WarpReduceMinSync`, `ThreadBarrier`,
`ThreadFence`. **No upstream document in this harvest's scope mentions any of them**, and no entry claims
them — a declaration list is not a capability. Owed, in order: confirm each resolves and is callable from a
`__simt_vf__` body; establish what `ThreadBarrier` synchronises (a warp, a block, or a core), because that
is the intra-block barrier `950:0378`'s row-2 correctness requirement needs and which no source in scope
names; then the shuffle and warp-reduce semantics. This is the largest single undocumented surface this
block found and it deserves its own number block, not a paragraph.
Gates: `950:0378`, `950:0379`, `950:0376`, `950:0375`.

---

## Group B — settled by one compile-and-run or one dump

## Q-950rem-10 · does a `VF_CALL` silently launch nothing in an ordinary 950 build
`950:0373` is the most consequential item in this block. `kernel_simt_utils.h:18-33` places `VF_CALL`'s
entire body inside `#if (__NPU_ARCH__ == 5102) || defined(SPLIT_CORE_VEC) || defined(ASCENDC_CPU_DEBUG)`,
and `sys_macros.h:61-63` defines `SPLIT_CORE_VEC` only when `__DAV_VEC__` is set. Upstream's SIMT guide
states **no** condition on `VF_CALL` anywhere. Owed: the twelve-configuration preprocessor sweep (which of
{3510, 5102, unset} × {`__DAV_VEC__` or not} × {CPU debug or not} keeps `cce::async_invoke`); then, on a
board, one trivial SIMT operator built in a body-present and a body-absent configuration with the output
buffer **poisoned first** — the poison surviving with a zero exit and no diagnostic is the whole claim.
Also owed: whether include order decides it, since `common_functions.h` defines `SPLIT_CORE_VEC` itself and
`kernel_simt_utils.h` merely tests it. **The question that decides whether this trap is common or
unreachable is whether a normal 950 SIMT toolchain invocation sets `__DAV_VEC__`, and nothing in this
harvest answers it.**
Gates: `950:0373`, `950:0374`, `950:0376`, `950:0378`, and every generated SIMT kernel.

## Q-950rem-11 · does `GetBaseWindAddrByRankId` return `windowsIn[rankId] + 1MB` or the raw field
`950:0389`, which NARROWS the hole `950:0277` §7 discloses (remaining terms supplied; composition still an
inference). The layout formulas start from the accessor;
`950:0277`'s rule says the A5 data base is `windowsIn[rankId] + A5_MTE_STATE_WIN_SIZE`; **no document states
the composition**, and the two errors are symmetric — adding the megabyte twice lands 1 MB into the data
region (silent, single-rank self-consistent), omitting it writes payload over the synchronisation state
(`950:0277`'s hang). Owed, and it is one printf: print the accessor's return, the state accessor's return,
and the raw `windowsIn[rankId]`, and record the two differences. Predicted 1048576 and 0. Note the accessors
are **sample/compat helpers, not a vendor API** (`mte-address-access.md:279`), so the answer is a property
of the consuming team's tree — which is exactly why the check compares a return value against a raw field
rather than trusting a name.
Gates: `950:0389`, `950:0277`, `950:0390`, `950:0391`, `950:0392`, `950:0393`.

## Q-950rem-12 · does the device-side TensorList walker stride by 9 words or by `1 + dim`
`950:0381` and `C-950rem-005`. Owed: invoke a dynamic-input operator with **three tensors of different
ranks** (2, 4, 8) whose dimensions are distinctive primes (17, 19, 23), dump the descriptor region, and read
off the actual per-descriptor stride. One dump decides which of the file's two halves is wrong, and the
primes are what stop a located value being confused with a length, an index or a count. Owed in the same
run: whether `*(ptr+1) & 0xffffffff` reads `dim` or `index` (a field-order and endianness assumption the
walker makes and the diagram does not confirm), and whether the vendor's own `ListTensorDesc` class parses
the same list correctly — if the supported path works where the hand-rolled one does not, the guidance that
routes *large* lists to the hand-rolled path is pointing at the broken one.
Gates: `950:0381`, `950:0382`.

## Q-950rem-13 · does `__trap` end the thread, the warp, or the operator
`950:0386` and `C-950rem-008`. Owed: build upstream's own documented example, fill the input with valid
floats except **one** NaN at a known index, poison the destination, run, and read back. Every non-NaN
element written → thread scope; nothing written → operator scope; a 32-element hole → **warp** scope, which
neither upstream sentence offers and which is the answer §2 of that entry argues is mechanically most
likely under `950:0235`'s divergence account. Sweep the NaN's position (0, 17, 32, a block boundary) to
locate the boundary rather than infer it. The control that makes the arm valid: a no-NaN run in which every
element **is** written — otherwise "nothing was written" is indistinguishable from `950:0373`'s silent
no-op launch.
Gates: `950:0386`, `950:0384`, `950:0235`.

## Q-950rem-14 · does a SIMT `assert` print the asserted condition or its negation
`950:0384` and `C-950rem-006`. Owed: fire one. `assert(v == 0)` with `v = 1`, and record the backtick-quoted
text verbatim; repeat with `assert(n > 7)`, `n = 3`, to confirm a transformation rather than read one line.
Three documented message formats exist across the page's five sections, so record the full format including
the doubled `: :` field, which the prose says carries "formatted supplied information" that neither example
supplies. Also owed and separable: does the always-true first example print anything at all (predicted: no,
which would mean the example demonstrates a failure its own code cannot produce), and does a failing
assertion print once, once per thread, or once per warp — at SIMT thread counts that is the difference
between a usable instrument and 1024 lines against `950:0383`'s 2 MB FIFO.
Gates: `950:0384`, `950:0385`, `950:0386`, `950:0387`.

## Q-950rem-15 · does including the system `assert.h` suppress the AscendC assert, and does `NDEBUG` do it silently
`950:0387`. Upstream states the collision in the **AI CPU** section's constraint list, not the SIMT one, so
the first thing owed is whether the rule applies to the SIMT macro at all. Then, per include order and with
and without `NDEBUG`: which macro is in effect (determined by expanding `assert(0)`, not by reading source),
and whether a deliberately false assertion still fires. The dangerous cell is *system macro wins under
`NDEBUG`*: the check is present in the source, absent from the binary, silent, and its silence reads as
evidence the fault does not occur. Cheap and owed first: read `utils/debug/asc_assert.h` for a `#ifndef
assert` guard, `NDEBUG` handling, and whether it stringises the condition or its negation — that last also
answers `Q-950rem-14` in advance.
Gates: `950:0387`, `950:0384`, `950:0386`.

## Q-950rem-16 · does an inplace `OpDef` bind one GM address, and does renaming the output silently unbind it
`950:0364`. Owed: build one minimal operator twice — `Input("var")` + `Output("var")`, and
`Input("var")` + `Output("var_out")` — and print both `GM_ADDR` values in the kernel. Equal in the first and
different in the second is the whole mechanism. Owed in the same run, because address equality is not a
write: poison the caller's tensor and confirm it is updated. The control that makes it valid is a
non-inplace operator whose two addresses must **differ** — two pointers printed equal is the commonest
instrumentation error when both are read through one accessor. Owed separately: the four-variant
`OpDef`×`REG_OP` cross (`950:0364` Arm C), because a mixed operator would be inplace on one invocation path
and not the other, which reproduces under aclnn and not under GEIR.
Gates: `950:0364`, `950:0365`, `950:0366`, `950:0367`.

---

## Group C — needs a sweep, a repetition protocol, or multiple cards

## Q-950rem-17 · does an inplace kernel need the `MTE3_MTE2` pair, and at what tile granularity
`950:0366`. Upstream states the hazard at **allocation** granularity ("同一块 GM 内存") while a normal tile
loop has consecutive rounds touching *different addresses* inside that allocation. That difference decides
whether every inplace kernel carries the pair or only a narrow subset. Owed: an accumulate-style inplace
operator with real MTE overlap, built with and without the pair, 1000 runs at three tile counts, plus a
disjoint-tile and an overlapping-tile arrangement. **The unguarded arm must fail at least once or the
experiment measured nothing** — a synchronisation experiment whose unsynchronised control passes is the
blind species. Owed alongside: the pair's duration cost, which is what `950:0359`'s over-application warning
would have to be weighed against.
Gates: `950:0366`, `950:0364`, `950:0359`, `950:0262`.

## Q-950rem-18 · are consecutive `VF_CALL`s unordered across cores, and what does half the remedy do
`950:0376`. Upstream states block-internal serialisation, denies all-core synchronisation, and prescribes
`SyncAll()` **and** `context->SetScheduleMode(1)` together. The two halves live in different files (kernel
and host), so an agent editing the kernel adds one. Owed: the four-build cross — neither, `SyncAll` only,
`SetScheduleMode(1)` only, both — with failure rate, hang/no-hang and duration for each. Whether
`SyncAll()` without the schedule mode blocks forever, returns immediately, or works is the question a
kernel-editing agent meets first and no source answers. **`SetScheduleMode` is named once in this entire
harvest's scope, with one argument value and a two-character comment**: what mode 0 is, what other modes
exist, and what the mode costs are unknown, and a separate arm must price it or the "both" configuration's
cost is unattributable.
Gates: `950:0376`, `950:0375`, `950:0378`.

## Q-950rem-19 · what is a SIMT `printf` worth, and where does its output stop
`950:0383`. Upstream gives the most precise cost model in this block — 2 MB GM FIFO by default,
`acl.json` `simt_printf_fifo_size`, 1 MB minimum, 64 MB maximum, plus SIMT stack consumption with no budget
and a simulation-time penalty. Owed: the reachable-line count per configured FIFO size (predicted monotone),
and **how output stops** — truncated mid-line, dropped lines, or a warning. `950:0383` §7 records that the
"超出则不会打印" consequence is quoted from the **AI CPU** sibling's 1 MB Dump ceiling and applying it to the
SIMT FIFO is reasoning by analogy. Owed separately: the stack limit, swept two ways (calls per thread at
fixed thread count; thread count at one call) because only the product distinguishes a per-thread limit from
an aggregate one.
Gates: `950:0383`, `950:0384`, `950:0386`.

## Q-950rem-20 · do concurrent same-address SIMT writes lose updates, and do the two atomic families agree
`950:0379`. Upstream names one atomic (`asc_atomic_add`) followed by 等; the toolkit ships **two** families —
eleven generic `AscendC::Simt::Atomic*` templates with `__ubuf__` and `__gm__` overloads each returning the
previous value, and a per-dtype lower-case `asc_atomic_*` family in the float-format headers, several of
whose members exist only for the packed `bfloat16x2_t` type. Owed: the lost-update count for a plain `+=`
against both atomic spellings, 500 runs at four thread counts, reported as a **distribution** (one lost
update and four hundred are different risks). Owed and undocumented anywhere: whether the return value is
the previous value — that is what makes a reservation pattern possible and upstream never mentions it — and
whether the guarantee spans **cores**, which `950:0378`'s direct-GM idiom needs and no source states.
Gates: `950:0379`, `950:0378`, `950:0376`.

## Q-950rem-21 · does the SIMT `/` operator differ from `fdividef`
`950:0380` and `C-950rem-004`. Owed: bit-compare both forms over ≥10⁶ input pairs stressing the exponent
range, subnormals, and near-zero denominators, **and** compare the two disassemblies. Both clauses are
required and the reason is recorded: bit-identical outputs alone cannot distinguish "same instruction" from
"this input set does not discriminate", which is the species this book records as certifying a claim with an
instrument that cannot see the difference. Owed alongside: ULP error per form against an fp64 reference, to
identify which form is the approximate one — the CUDA `f`-suffix convention suggests `fdividef`, which would
invert the guide's implication. Owed third: whether the operator form contracts into an FMA by default,
which would make the two spellings differ for a reason upstream never mentions and which changes with build
flags rather than source.
Gates: `950:0380`, `950:0249`.

## Q-950rem-22 · the MC² window layout, measured end to end
`950:0389`–`950:0393`, and it needs ≥2 cards. Four address formulas, four constant blocks, and a UB budget, none
measured. Owed as one campaign on one card group in one session, because they share a setup: the accessor
offsets (`Q-950rem-11`); one dispatch token dumped at an `H` whose raw payload size is **not** 32-aligned,
so the alignment term is visible; the token stride over `BS` tokens; the state slot's field positions and
32-byte stride, with `localExpertNum ≠ rankDim` so a transposed index is detectable; the combine slot
alignment at an `H_expand × sizeof(ExpandXType)` that is not a multiple of any candidate constant, so the
candidates are distinguishable; and the state-region UB reservation against the operator's tile size.
Two derived items no source states and that this block flagged: **the dispatch token stride is a multiple of
32 plus 12**, so only every eighth token's payload is 32-byte aligned (`950:0390` §3) against `950:0257`'s
`LoadAlign` requirement; and the combine slot carries **no** source triple and no token count where dispatch
carries both (`950:0392` §2). Capture protocol for anything timed: ≥10 iterations, first 5 discarded, mean
of the last 5, **max across ranks** — a mean hides the straggler that sets the latency. Predicted hangs in
several arms: declared watchdog and card release are mandatory.
Gates: `950:0389`, `950:0390`, `950:0391`, `950:0392`, `950:0393`, `950:0277`, `950:0257`.

## Q-950rem-23 · where is the register ceiling that the promotion rule points at
`950:0356` states upstream's rule — keep short-lived math in `RegTensor`, promote to UB only when reuse or
staging forces it — with **no cost in either direction** and no ceiling. `950:0357` adds that a narrow-dtype
route needs extra register state even when it needs no extra UB, again with no number. Owed: sweep live
`RegTensor` intermediates from 2 to 16 and locate the knee, **gated on a disassembly showing stack traffic
at the same point** — a timing knee without spill instructions is measuring something else, which is the
error `Q-950arch-12` records for the register-band table. Owed alongside: the tile size the host selects
under each build, because the UB consequence is a host-side fact that holds whether or not the duration
moved. Note `950:0356` §7 records the file disagreeing with itself about whether "reuse" means within one
VF loop or across chains — one arm decides it.
Gates: `950:0356`, `950:0357`, `950:0036`, `950:0236`.

## Q-950rem-24 · does the b16 widening path collide with the lane-count rule, in practice
`950:0357` §2 and `950:0257`'s Arm D, restated because this block found the collision from a second
direction. `950:0252` says derive the lane count from `GetVecLen()/sizeof(T)`; for `half` that is 128.
`950:0257` records that `DIST_UNPACK_B16` consumes only VL/2 source bytes — 64 half values. So the
dtype-split pattern `950:0357` harvests, applied with `950:0252`'s rule, steps twice as far as the load
consumed and skips half the data. **No upstream source states the collision.** Owed: poison the source past
the expected extent and count consumed bytes (128, not 256), then run the loop at both strides against a
host reference. Owed in the same build, because it is the ambiguity that decides how the pattern is written
at all: is step 3 of the six-step narrow-dtype pattern a `Reg::Cast` or a load distribution — the two differ
by an instruction and upstream's three files use both vocabularies.
Gates: `950:0357`, `950:0257`, `950:0252`, `950:0253`.

## Q-950rem-25 · do the three diagnostic rules discriminate, tested against planted defects
`950:0394`, `950:0395`, `950:0396` are the three pitfalls items this block entered rather than carded,
because each has a falsifiable discriminator. All three are **rules about instruments**, and an instrument
is validated by a pair of controls, not by one. Owed as one campaign: plant a synchronisation defect
(`950:0366`'s inplace pipeline without its pair) and a numerical defect (an fp16 accumulator past
`950:0397`'s safe length), run each 50 times, and confirm the failing set moves for the first and not the
second — **neither arm means anything without the other**. Owed for `950:0395`: a path-coverage measurement
per shape and a defect-detection matrix over four planted defects, reported as a matrix and never as a rate.
Owed for `950:0396`: the same kernel judged against a same-precision and an fp64 reference, with the gap
reported per input class. `950:0394`'s rule is **one-directional and upstream does not say so** — instability
rules numerics out, stability rules nothing out, and a deterministic race is the case that shows it.
Gates: `950:0394`, `950:0395`, `950:0396`, `950:0366`, `950:0397`.

## Q-950rem-26 · do the numerical-stability constants describe a tree reduction or a sequential one
`950:0397`. Upstream's safe accumulation lengths (< 10³ for fp16 and bf16, < 10⁶ for fp32) rest on an `n·ε`
error model, which is the **sequential** summation bound. `950:0030` records that the hardware tree
reduction replaces the scalar accumulate loop and reorders the sum, and tree summation grows like
`log(n)·ε`. So the tabulated figures may be worst-case bounds rather than descriptions of a reduction
written the recommended way — and until that is settled they must not be used to reject a shape. Owed: the
error curve against n for both summation orders, with the sequential variant **confirmed sequential by
disassembly** (if the compiler re-associated it, the two arms measure one thing). Owed alongside: the
dynamic-range axis, which the graded table indexes and which a length-only reading drops — at 10⁴-10⁶ terms
the strategy is fp32 below range 10¹⁰ and Kahan above it, same length, two answers. Noted for the auditor:
the table's three epsilon rows are **not internally consistent in convention** (bf16's 7.8e-3 is 2⁻⁷ where
fp32's and fp16's are 2⁻²³ and 2⁻¹⁰).
Gates: `950:0397`, `950:0398`, `950:0030`, `950:0031`.

## Q-950rem-27 · is a max-shifted softmax denominator ≥ 1 in the masked case
`950:0398`. Upstream states the denominator is ≥ 1 因为 the maximising element contributes `exp(0) = 1`, and
calls the eps a 常见误区. The guarantee has two thin spots upstream does not name, both derived in that
entry: it needs `exp(0)` to evaluate to **exactly** 1 in the implementation used (`950:0035` records that
`ExpandLevel` zero leaves the Taylor path), and it needs the maximising element to be **in the summed set**
— a masked softmax that takes `m` before masking and sums after can exclude it, and a fully-masked row can
give zero. **Every attention kernel meets the masked case and upstream's rule does not cover it.** Owed:
evaluate `exp(0)` on every available path; sweep mask density to fully-masked under both mask orderings and
record the minimum denominator; and measure the bias an unnecessary eps introduces (predicted a systematic
`S/(S+ε)` scaling — invisible at fp16, measurable at fp32, and surviving every algorithm fix, which is the
`950:0396` signature reached from a different cause).
Gates: `950:0398`, `950:0397`, `950:0035`.

---

## Coverage owed, not measurements

## Q-950rem-28 · the paradigm families are sampled, not mined
`references/paradigms/` carries roughly 3 800 lines across ten families — `elewise/` (261),
`broadcast/` (322 plus a template subtree and two worked example packages), `reduction/` (535 plus three
template subtrees and two example packages), `layout_transform/` (169 plus ten reference files),
`quantization/` (142 plus fourteen reference files), `matmul/` (188), `recurrence/` (1376),
`stateful/` (146), `numerical_stable/` (623), `design-check-lite/`, plus `general-methodology.md`,
`routes.yaml` and `PARADIGM_GUIDELINE/`. **This block took one file whole (`mask_predicate/patterns.md`,
`950:0399`) and three items from `numerical_stable/knowledge.md` (`950:0397`, `950:0398`).** Everything
else is unharvested. `recurrence/` alone is 1 376 lines and is the largest unmined single family in the
regbase skill. This is a number-block-sized job, not a residue: it needs its own allocation and its own
agent, and the books should not be read as covering the paradigm layer until it has one.

## Q-950rem-29 · four pitfalls files were outside this block's declared scope and were not read
The controller ruling named three files (`common_traps.md`, `api_misuse.md`,
`regbase_vs_membase_confusions.md`). The directory holds seven. **`precision_guide.md` (190 lines),
`precision_failures.md` (176), `symptom_to_cause.md` (58) and `index.md` (41) were not read.** The first two
are the subtree's dedicated numerical-verification material, and `950:0396` §7 records the consequence
explicitly: that entry states upstream supplies no tolerance and no reference precision, and it does not
know whether those two files supply exactly that. `symptom_to_cause.md` is the diagnostic-routing file both
other pitfalls files defer to. Owed: read all four, and re-check `950:0394`–`950:0396` against them before
the delivered skill quotes any of the three.

## Q-950rem-30 · `regbase_api_sync.md` is the destination of two routing rules and was never opened
`common_traps.md:158` and `api_misuse.md:82` both route a suspected synchronisation failure to
`../api/regbase_api_sync.md` as the first thing to read. That file is in the `knowledge/api/` subtree, which
was the wave-1 950-arch miner's territory rather than this block's, and no entry in either block cites it.
Owed: confirm whether it is mined; if not, it is the single highest-value unmined file for the
synchronisation cluster (`950:0358`, `950:0359`, `950:0366`, `950:0376`), all four of which currently rest
on `regbase_sync_patterns.md`'s layering and on scattered statements elsewhere.

---

# Register: 950-td (merged 2026-08-24, repair wave — audit F-4)

# Standing questions — domain `950-td` (wave 1.75)

Named measurements owed by this domain's entries, answerable only on a 950 board (RULES.md Art. 6),
plus deliberate skips and the batch ledger. IDs `Q-950td-NN`. Entry references written
`950:NNNN` per CONVENTIONS (this file is read from outside one book).

Domain: `ops/ascendc-tiling-design/` DAV_3510 / arch35 columns and 950-side methodology, plus the
`ascendc-performance-best-practices` twin families (gather, reduce, scan, conversion, broadcast,
scalar, elementwise) diffed against `book-950` entries 0101–0169.

---
## Self-reports (this domain's own errors, found and corrected by its drafter)

**SR-950td-01 · 2026-08-24 · a fabricated quote, caught before it left the drafting session.**
While drafting `950:0406` I transcribed `reduce_max_c310_impl.h`'s pattern `static_assert` message as
`"ReduceMin only support AR and RA pattern on current device!"` and built a contradiction row
(`C-950td-009`, "a copy-paste artifact in the shipped header") on that transcription. Re-verifying the
line before finalising showed the file says `ReduceMax`; `reduce_min_c310_impl.h` says `ReduceMin`; the
two files are a cleanly copied pair with correct strings throughout. The error came from reading two
`grep` outputs in one screen and attributing a line from the second file to the first. `C-950td-009` is
**withdrawn and never existed as a row** — the id is left permanently vacant rather than reused, so a
later reader who sees the gap finds this note. `950:0406` §3 now states the correct text and names this
self-report. Lesson, and it is the one this project already has on file: a quote assembled from a
multi-file grep is not re-verified until it has been read *from the file it is attributed to*.

---

## Standing questions

**Q-950td-01 · Is `repeatTimes ≤ 255` an upstream-authorityless constant, or a toolkit constant?**
`harvest/surveys/DEEPDIVE_20260824_perf-optimize.md:284-286` lists `repeatTimes≤255` under
"establish from scratch — no upstream authority, npu-arch does not supply them". That holds for the
skills repo, where the number appears only as an unexplained clamp (`ara-rowsplit.md:77`) and as a
script constant (`reduction_tiling.py:46`). It does **not** hold for the installed toolchain, where
`kernel_utils_constants.h:39` names `MAX_REPEAT_TIMES = 255` beside `MIN_REPEAT_TIMES = 0`. The
establish-from-scratch list should be re-scoped: the value has a named source, what is missing is the
demonstration that it binds any particular parameter. Gates `950:0404`. Owed measurement: `950:0404`
§4 arms 1–3 (arm 1 needs a device; arms are stated there).

**Q-950td-02 · Is the 950 backend's native narrow-dtype `ReduceMax` faster than upstream's
cast-to-FP32 policy?** The `c310` backend accepts eleven element types for `ReduceMax`/`ReduceMin`
including `half` and `bfloat16_t` (`950:0406`), while upstream's implementation shelf casts every
narrow input up to FP32 on load and back on store as a blanket rule
(`reduce/guide.md:76,231`). For a *sum* the cast has a numerical justification (`950:0397`); for a
*max* it has none, and nobody has measured whether the native path wins. Gates nothing yet; would
change `950:0406` §2's operational advice from "know the list exists" to a recommendation. Owed
measurement: `950:0406` §4 arm 3.

**SR-950td-02 · 2026-08-24 · a prior survey undercounted a divergence; corrected by re-verification.**
`harvest/surveys/DEEPDIVE_20260824_perf-optimize.md:162-165` records the broadcast `maxElemNum`
divergence as "tiling-design's copy has an extra branch `if shapeLen == 1`". Re-verifying both copies at
drafting time found **two** extra guards, not one: the `shapeLen == 1` special case *and* an `allFit`
flag with a post-loop branch (`patterns.md:104,110,113-114`), plus two initialisers the analysis shelf's
copy also lacks. Both guards fire in the same circumstance — the loop never breaking. Carried by
`950:0414`, registered as `C-950td-018`. The PLAN asks a harvester to correct a survey file with a dated
note when a survey claim fails re-verification; this domain's write partition (Amendment §7) forbids
touching `harvest/surveys/`, so the correction is recorded here and in the wave report instead. The
survey's finding was real and its count was low — which is exactly what "a survey locates material, it
does not certify it" means in practice.

**SR-950td-03 · 2026-08-24 · a prior wave's claim-card quotes a sentence that does not exist.**
`harvest/claims/ascendc-performance-best-practices--008-...md` quotes the broadcast family's NaN claim
as `选错直接慢甚至出错（nan）` and states it appears "twice in the family's opening". Re-verification:
`grep -rn 出错` over all eleven files of `reference/broadcast/` returns **nothing**; the actual sentence
is `选错直接慢甚至 nan，选对才快`, at `broadcast_design.md:3`, appearing **once**. The card's *reading*
of the sentence is correct — it is a correctness claim about a routing decision, and it was the right
item to flag as highest-value. Its transcription is not. The card is not edited (write partition); the
correct text is carried at `950:0416`. Same lesson as SR-950td-01: a quote is not re-verified until it
has been read from the file it is attributed to.

---

## Standing questions (continued)

**Q-950td-03 · What is `random_read_transaction_penalty`?** The LastDim gather cost model
(`reference/gather/templates/gather_elements_v2_last_dim.md:57-65`) compares `resident_cost` against
`direct_cost`, and `direct_cost`'s only free parameter is named and never valued anywhere in the shelf.
So the screen that `guide.md:235` and `:65` require before selecting LastDim cannot be evaluated as
published. Gates `950:0411`; `950:0411` §4 arm 3 derives it from a measured crossover.

**Q-950td-04 · A fourth site for the elementwise/broadcast UB-capacity formula.** `950:0151` records
three mutually inconsistent forms of `maxElemNum` across two families. The analysis shelf's broadcast
OneDim branch states a fourth at `tiling-flow.md:38` — `ubFormer = (ubSize / bufferNum) 对齐到 128B` —
with no `extraSize`, no `* 8` and no dtype width. Recorded, not analysed; noted in `950:0414` §3.

**Q-950td-05 · Does `dcache` denote one object across families?** `950:0148` records the analysis
shelf's gather family stating `DCache` inline as **128 KB**. `950:0415` records the broadcast family
stating `nddma dcache/2 ≈ 4096B` and the broadcast script substituting a 128-**byte** cache line. Three
values, two families, one name, and one of them explicitly qualifies the cache as the NDDMA engine's.
Owed: a runtime query, per `950:0207`.

**Q-950td-06 · Why does an empty broadcast produce NaN rather than a copy?** `950:0416` records six
statements of the proximate condition (`dShape==sShape`) and no mechanism anywhere in the family. The
distinction matters: if the NaN is uninitialised UB read back rather than generated, the same
mis-selection on a zeroed buffer yields silent zeros, which is worse than the documented failure.
`950:0416` §4 arm 2 is the pre-fill experiment that separates them.

**Q-950td-07 · Can the shipped broadcast `blockTail` go negative?** `950:0417` records that
`code/broadcast_common.h:325` ships the subtraction `onedim_design.md:109` forbids, in the
`blockFormer`-first order `advanced_tiling.md:59` prescribes — compliant under one prohibition and not
the other. Whether any reachable `(ubOuter, bn)` pair makes it non-positive is decidable by enumeration
with no device (`950:0417` §4 arm 4).

**Q-950td-08 · Scope correction owed to `950:0164`.** That entry carries the conversion family's
`6.25%` bandwidth figure in the flat form the analysis shelf uses. The implementation shelf derives it
as `2/32` for a **2-byte** element and tables it per dtype: int8 3.1%, fp16/bf16 6.25%, fp32/int32
12.5% (`transpose_small_shape.md:196,199-202`). `950:0164`'s §1 and §7 want narrowing to fp16/bf16.
Not applied here — `950:0164` is another wave's entry and this domain's partition forbids editing it.

**Q-950td-09 · Does TilingData size account for the conversion family's fastest row?**
`950:0420` records `TQueBind 4D` beating everything measured, with upstream attributing it to two
causes in one sentence: a 4-D formulation and a 128 B TilingData against 972 B. The same family
measures, in a *different* strategy, that a 972-byte TilingData copied byte-by-byte at kernel entry cost
about 10 µs (`transpose_small_shape.md:295`) — against totals of 13–25 µs. Nobody connects the two.
`950:0420` §4 arm 2 splits the sentence.

**Q-950td-10 · The D-Cache line size, asserted here without becoming an authority.**
`reference/scalar/coding_principles.md:319` states `D-Cache cacheline 大小为 64 字节` as fact, with no
architecture, no source and no derivation, and derives a `≤ 64B` struct-size recommendation plus an
unexplained `128B` ceiling from it. This project's survey lists cache-line size among the constants that
must be established from scratch. The figure is recorded at `950:0422` and not carried.

---

## Deliberate skips (this domain, with reasons)

- **`ascendc-tiling-design/references/flashattention/`** (3 files, 1 224 lines) and
  **`references/matmul/`** (2 files, 584 lines) — read for scope, not mined. Both are large enough to be
  a wave of their own, and the FlashAttention family in particular is a design methodology rather than a
  constant-and-gate corpus, so entries from it would not be diffs against anything currently in the
  book. Recommended as the next wave's first item.
- **`ascendc-tiling-design` reduction remainder** — `ar-fullload.md`, `ara-fullload.md`,
  `multi-axis-transform.md`, `multi-output-buffer.md`, `tiling-fields.md`, `with-index.md`,
  `alg-group-reduce.md`. The four taxonomy-bearing files were mined (`950:0401`–`0404`); the full-load
  arms largely restate budgets `950:0123` already carries from the analysis shelf, and `with-index`
  belongs with a `0122`-side diff rather than as new material.
- **`ascendc-tiling-design/references/{elewise,conversion}/patterns.md`** — read; their content is
  routing-tree material whose analysis-shelf twins are already entered at `950:0151`–`0153` and
  `950:0163`–`0165`, and the diffs found were smaller than the entries they would need.
- **bp `reference/reduce/templates/fused_attention_online_softmax_design.md`** — names Ascend 910B three
  times (per card `--008`); not this book's on those lines (RULES.md Art. 1).
- **bp `reference/scan/` remainder** — the eight-file family yielded far more than one entry's worth
  (three self-reported wrong conclusions, a net-negative optimisation with both sides costed, six
  disclosed template-extraction defects two of which are marked 致命, a runtime gate on an undefined
  symbol `gsS`, and one case measured at three different values in three files). One entry drafted
  (`950:0418`); the rest is the richest unmined seam this domain touched and is recommended next.
- **bp `reference/elementwise/`** (2 files) — `double_buffer_design.md` is already carried at
  `950:0319`–`0321`; `vector_efficiency_design.md`'s Counter-mode claim (card `--008`'s third priority)
  is unmined and remains owed.

---

## Batch ledger
- 2026-08-24 · wave 1.75, domain `950-td` · 23 entries drafted, `book-950/entries/0401`–`0423`, all at
  `harvested` stratum except `0405` and `0406` (`corroborated`, installed CANN toolchain as second
  origin). 29 contradiction rows (`C-950td-001`…`030`, 009 permanently vacant per `SR-950td-01`).
  10 standing questions, 3 self-reports. `tools/check_entries.sh book-950` passes on all 23.

---

# Register: 950-fin (merged 2026-08-24, repair wave — audit F-4)

# Standing questions — domain `950-fin` (wave 1.9, the final mining wave)

Named measurements owed, posed during harvest, answerable only on-card — plus, at the end, the
deliberate skips and the two card statements that failed re-verification. Cross-references use
`950:NNNN` (CONVENTIONS: this file is read from outside one book).

Sources mined this wave: `ops/ascendc-tiling-design/references/flashattention/` (overview 249 +
design 634 + subfamilies 341 = 1224 lines), `references/matmul/` (patterns 188 +
matmul-fusion-design-template 396 = 584 lines), `ops/ascendc-performance-best-practices/reference/
elementwise/vector_efficiency_design.md` (203 lines), `reference/scan/` (guide 280 + 8 template files
= 1298 lines). Installed toolkit at pin `cann-9.0.0-beta.2` consulted read-only for four entries.
Entries produced: `950:0451`–`950:0488` (38). Contradiction rows: `harvest/contradictions-950-fin.md`
(`C-950fin-001` … `C-950fin-031`).

---

## FlashAttention family

**Q-950fin-01 · Where between `gMaxPerTask = 1` and `= G` does invariant I2 start to bind?**
`flashattention/overview.md:122` requires the G query heads of one kv head to merge into one task;
`subfamilies.md:111` bounds the merge at `gMaxPerTask ≤ G` without requiring equality. So a partial
merge is permitted and its cost is unstated. Owed: KV traffic and time at
`gMaxPerTask ∈ {1, 2, 4, 8}` for `G = 8`. Gates `950:0452`.

**Q-950fin-02 · What is `跨核 fence 成本 >> 顺序 s2 累积成本`?**
`overview.md:151` justifies half of the s2-in-taskIdx prohibition with an unquantified inequality,
scoped to `totalTasks ≥ usedCoreNum` — the condition that fails in the decode case the alternative
strategy exists for. Owed: both costs, on one board, at a shape where the scoping condition holds and
one where it does not. Gates `950:0454`.

**Q-950fin-03 · Is the MX block quantisation group 32 elements, and is it dtype-independent?**
`overview.md:161` — `块量化的 scale 描述 reduction 沿线的 32 元素一组` — one bare literal covering
mxfp8, mxfp4 and mxfp6, in a family whose own `design.md:208` forbids bare numbers in formulas.
Owed: the accepted group sizes per format. Gates `950:0455`.

**Q-950fin-04 · What is the streaming UB mode's overhead, scoped?**
`design.md:80` — `实测开销小(典型 ≤ 5%；decode 长 KV 等少数场景可能略高)` — the only figure in the
FA family's 1224 lines presented as measured, with no case, shape, `D`, dtype, board, tool or
repetition count. Owed: the overhead surface over `D` × (prefill, decode). Gates `950:0456`.

**Q-950fin-05 · What is `L1_PORT_SIZE`?**
`design.md:286-290` makes the per-slot L1 budget `L1_PORT_SIZE / rotation_slots / sizeof(elem)` and
says the queried capacity is `≥ 该预算` — so it is a policy allocation the designer sets, never a
value. The corpus's L1 numbers (`950:0102`, the architecture block) are capacities, not budgets.
Owed: the queried `L1_A`/`L1_B` on a named board beside whatever budget a shipped design assumes.
Gates `950:0457`.

**Q-950fin-06 · Does an operator carry one chunk loop or two?**
`design.md:235` gives `mSplit = 单槽字节容量 / (cols × sizeof(elem))`; `:465` gives
`chunkRows = chunkBufferBytes / (D_align × sizeof(compute_T))`. They coincide only when
`cols == D_align`, which fails for a `[Bq, Bk]` score-matrix copy. Owed: the echoed values of both
from a build carrying both. Gates `950:0458`.

**Q-950fin-07 · What is `SoftMaxShapeInfo.srcM` for a partly-padded last chunk?**
Two obligations compose and upstream states neither composition: `srcM = mEff` not `mPad`
(`subfamilies.md:129`, `design.md:384`), and V1/V2 must chunk symmetrically including the
`SoftMaxShapeInfo.srcM` axis (`design.md:264`). The last chunk of a padded block has an effective row
count that is neither. Gates `950:0458`.

**Q-950fin-08 · At what shape does a `Sk_max` workspace reservation reach hundreds of megabytes?**
`design.md:377` states the figure with the formula `B × Hq × Bq × Sk_max × sizeof(elem)` and no shape.
Arithmetic at `Sk_max = 32768`, FP16 gives 64 KiB per unit of `B × Hq × Bq`, so hundreds of MB implies
a few thousand units — consistent, but not the shape upstream used. Owed: the echoed per-segment sizes
under both policies at a stated shape. Gates `950:0459`.

**Q-950fin-09 · What is the "official production implementation" the bf16 anti-patterns deviate from?**
`subfamilies.md:287`, `:291` justify two of five anti-patterns with `偏离官方生产实现` and a third with
`违反 development-guide §1.4`. The implementation is never identified and the deviation never
quantified. Owed: a measurement for each of the five, or an identification. Gates `950:0460`.

**Q-950fin-10 · What does the per-row `DataCopyPad` write-back cost?**
`subfamilies.md:120` mandates `curBq` separate calls in place of one `DataCopy`, and no document in the
family states a cost. Owed: MTE3 time for both forms across `curBq`. Gates `950:0461`.

**Q-950fin-11 · Is 16 the fractal height for every dtype?**
`subfamilies.md:122` writes `mPad > 16` as a literal; `design.md:386` states the same requirement as
`m 对齐维 > 单 fractal`, naming the quantity instead. Owed: the boundary at fp16 and bf16.
Gates `950:0462`.

**Q-950fin-12 · What does `mode=2` cost on a 950 board?**
`design.md:525` — `A2/A3 用 mode=2;A5 推荐 mode=4 + AIV1 早返回` — `用` for one family, `推荐` for the
other, with no consequence stated for using `mode=2` on A5 and a deferral to a platform API table not
quoted. Owed: correctness and time for both modes on a named 950 board. Gates `950:0463`.
(**The A2/A3 half of that line is book-910 material and is not this domain's; RULES.md Art. 1.**)

**Q-950fin-13 · Is the PipeBarrier redundancy accounting a check or a marker?**
`design.md:598`'s denominator — the number of contracted positions — is produced by the same team, at
the same time, as the numerator. A contract list written after the implementation gives a ratio of
zero by construction. Upstream places it in the design phase and never requires it to precede the
code. Gates `950:0464`. Same species as `Q-950fin-23` and `Q-950fin-24`.

**Q-950fin-14 · Which platform's contract list calibrated the 30% threshold?**
`design.md:594` makes one of the three barrier sources platform-specific (`某些平台的多 K-pass Mmad
隐式状态`), so the contract list's size is architecture-dependent and the ratio is not comparable
across boards. Gates `950:0464`.

**Q-950fin-15 · Is emitting V2 before V1 the only remedy, or is a deeper state slot the other?**
`design.md:509` prescribes the reordering for a write-after-read hazard that a deeper cross-task state
slot would also remove — a mechanism the same family's `§7.4` supplies and never connects. Owed: the
V1-first build at one extra state slot. Gates `950:0465`.

**Q-950fin-16 · Does the design's UB sum and the compiler's layout agree?**
`design.md:245` checks `Σ (单槽容量 × depth) ≤ GetCoreMemSize(UB)` from the design's own list, while
`:411` says `TBuf` member existence itself moves the compiler's layout. The two are computed from
different inputs and upstream never reconciles them. Owed: the echoed device-side offsets against the
design's sum. Gates `950:0466`.

**Q-950fin-17 · Where does GroupNorm's tiling knowledge live?**
Neither shelf routes it anywhere with content (`C-950fin-001`). `950:0169` identifies the reduction
family as the plausible home from the operator's `mean → var → normalize` structure — an inference
from mathematics, not an upstream statement. Owed: a measured comparison of a reduction-derived plan
against an FA-derived one. Gates `950:0468`.

---

## MatMul fusion family

**Q-950fin-18 · Is `usedCoreNum` clamped to the physical core count?**
`matmul/patterns.md:46` derives it as `CeilDiv(M, singleCoreM) × CeilDiv(N, singleCoreN)` with no
comparison against a queried count, while the FA family on the same shelf writes
`usedCoreNum = min(aicNum, totalTasks)` (`flashattention/design.md:189`). Two families, one quantity,
one clamp. Owed: the behaviour when the formula exceeds the physical count. Gates `950:0469`.

**Q-950fin-19 · What is SWAT?**
Named seven times across the two matmul files as the engine computing `singleCoreM`/`singleCoreN`,
`baseM`/`baseN`/`baseK` and `depthA1`/`depthB1`; never defined, located, or given an interface beyond
a header path in a reference project outside this shelf. Every tile-size decision in the family is
delegated to it. Owed: its outputs echoed from a build, and their reproducibility across builds.
Gates `950:0469`, and bears on `950:0472`'s budget formulas.

**Q-950fin-20 · Is `GetTaskRation()` fixed at 2 on every 950 SKU?**
`matmul-fusion-design-template.md:212` comments `SplitM 拆分比（=2）`; the whole `DUAL_DST_SPLIT_M`
arrangement assumes exactly two vector cores per cube core. `950:0216` records that pairing from the
architecture block — a different claim (hardware topology) about a different thing (not this API's
return value). Owed: the queried value on a named board. Gates `950:0470`.

**Q-950fin-21 · Why is mxfp8's K padded to a multiple of 64?**
`patterns.md:171` states it as `mxfp8 Cube 硬件要求` with no derivation; the template restates it for
`mxfp` generally (`:269`). Against `950:0455`'s 32-element MX block along the reduction axis, 64 is two
blocks — suggestive and stated nowhere. Owed: the coarsest padding that still produces a correct
result. Gates `950:0471`.

**Q-950fin-22 · Why may a fused epilogue not use `TPipe` for UB?**
Stated twice in bold (`patterns.md:144`, `template:207`) with no reason. The plausible one — the
Fixpipe landing region must sit where the cube side assumes, and a `TPipe` allocator would place it
elsewhere — is an inference from `950:0466` and is not promoted. Owed: the echoed device-side address
of that region under both management schemes. Gates `950:0473`.

**Q-950fin-23 · What verifies that the `[SAMPLE]` re-evaluation actions were taken?**
`template:369` is a checkbox; the register (`:382-395`) gives per-row *actions* and no per-row
*checks*, and every "risk" is a category (`不一致`, `错配`, `错误`, `不成立`, `漂移`) rather than an
observable. Owed: an instrument, or a demonstration that one row's unchanged value produces a
detectable failure. Gates `950:0474`. Same species as `Q-950fin-13` and `Q-950fin-24`.

**Q-950fin-24 · What verifies that the API semantic-verification table was filled?**
`template:87` requires it before every vector-side API call, `:95-100` lists five items and `:121`
states it as a formula whose last conjunct (`无更好选择`) is not checkable from a signature. Nothing
verifies it, and the same shelf-set contains two calls that match no shipped declaration
(`950:0477`, `950:0478`). Gates `950:0475`. Third instance of the species in this family alone.

**Q-950fin-25 · Does `CvSync::AIC_TO_AIV_FLAG + countId` fall under the custom-flag-ID prohibition?**
`template:138` forbids custom flag IDs and requires reuse of the shared header's constants; `:301`
adds a per-tile offset to one. The rule governs the base and says nothing about the offset, which is
how a rotating handshake is built. Owed: the platform-reserved ID range, which no family in this shelf
enumerates. Gates `950:0476`.

---

## Elementwise

**Q-950fin-26 · Why does a document with no other architectural marker carry a `RegTensor` budget?**
`vector_efficiency_design.md:202` — `- [ ] 寄存器预算 ≤ 32 RegTensor` — regbase-era vocabulary in a
file that names no architecture anywhere else, which by `form/CONVENTIONS.md`'s mechanism rule is what
lands material in book-950. Owed: whether 32 is the register file's size, a per-kernel budget, or a
convention. Gates `950:0479`.

---

## Scan family

**Q-950fin-27 · Two absolute bandwidth figures in one file, neither scoped.**
`cum_tile_resident_scan.md:34` — L2-served `2.1~2.7 TB/s`; `:58` — MTE3 ceiling `~1.2 TB/s`. No board,
no case, no method for either, and this book's architecture block holds no L2 or MTE3 bandwidth for any
950 board to check them against. Owed: both, measured, with their derivations. Gates `950:0481`,
`950:0488`.

**Q-950fin-28 · Which timing method produced which of the scan shelf's figures?**
The shelf documents a ~30 µs local-timing floor (`usage_guide.md:189-194`, carried at `950:0418`) and
recommends cann-bench device-side timing instead — and never says which was used for any given number.
The floor is comparable to the entire 34-59 µs spread of `C-950fin-031`. Owed: the floor for both
methods on a named board, before any of the shelf's figures is compared. Gates `950:0482`.

**Q-950fin-29 · Is the scan bank predicate about banks or bank groups?**
`950:0314` records DAV_3510's UB as 16 banks of 16 KB in 8 groups of two, and `950:0315` records that
two reads of one bank group do **not** conflict there — the one rule that differs from the other
architecture. Neither of the scan shelf's two predicates (`C-950fin-025`) mentions bank groups. Owed:
a stride chosen to pair lanes across one group. Gates `950:0483`.

**Q-950fin-30 · Is the gather bit-width path the cause of the lane-parallel fp16 reversal?**
`usage_guide.md:85` reaches `方向反了就只能是 gather 本身的位宽路径问题` by eliminating instruction
count (36 vs 68) and bank conflict (`bank_cflt` 0.1%), and states it in the same voice as the four
measured numbers above it. Owed: the 16-bit and 32-bit gather paths measured in isolation.
Gates `950:0486`.

**Q-950fin-31 · What is `gsS`?**
It gates the choice between the lane-parallel scan and Kogge-Stone inside `ScanRowRange`
(`usage_guide.md:288`, `cum_row_kogge_stone.md:109-110`), a decision the shelf's own defect register
values at 2.3× (`950:0485`). It is `gsS_` in the templates and `gsS` in the guide, is listed among the
members a consumer must add (`usage_guide.md:26`), and is never computed, typed or given a unit.
Third member of the species `950:0138` records (`VLC`, `VREG`) and the only one that selects an
algorithm. Gates `950:0487`.

**Q-950fin-32 · Are 100% and 130% thresholds or conventions?**
`cum_tile_resident_scan.md:30-31`. 100% is arithmetic (four occupancies summing to the whole means
nothing overlapped); 130% is a judgement with no case behind it, and the shelf's own post-change sums
are 132, 155, 168, 170, 170, 173% — the threshold sits just below the lowest observed value. Owed: the
gain-versus-sum curve and its knees. Gates `950:0488`.

---

## Deliberate skips — read for scope, not mined, with the reason

**1. `references/flashattention/` process obligations.** `design.md §4.1 Q1`/`§4.4 Q1` (the "list all
your buffers / segments" produce-lists), `§6.1`/`§6.2`/`§6.3` (the Host Tiling field roster and its
decision dimensions), `§8.1` (compile an asc-devkit reference example of the same kernel type before
writing your own), `§7.3` (semantic cache-slot naming), `subfamilies.md §2.1` (ConstInfo single-source)
and `§2.5`/`§5.1` (service-class naming and the subfamily-mixing ban). **Reason:** each is a real
obligation and none has a §4 that could falsify it — PLAN Stage 2's own test ("an entry whose §4 you
cannot write is not ready — leave it a card"). The load-bearing fragments are folded into
`950:0451`–`950:0466` where they bear on a testable claim; the rest is carded below.

**2. `references/reduction/` remainder on the tiling-design shelf.** `ar-fullload.md` (151),
`ara-fullload.md` (228), `multi-axis-transform.md` (83), `multi-output-buffer.md` (115),
`tiling-fields.md` (94), `with-index.md` (247), `alg-group-reduce.md` (101). **Reason:** outside this
wave's assignment (Amendment 4 named FA + matmul + elementwise + scan). Card
`ascendc-tiling-design--003` already names the three genuinely unmined ones (`with-index.md`,
`multi-axis-transform.md`, `multi-output-buffer.md`) and its assessment was not re-checked here.

**3. `references/matmul_fusion_kernel/` (the reference project).** Named repeatedly by
`matmul-fusion-design-template.md` and living in a sibling skill (`/ascendc-direct-invoke-template`)
outside this wave's scope. **Reason:** write partition. `950:0476` §4 arm 1 and `950:0474` §4 arm 1
both need it and both say so.

**4. `reference/scan/templates/*.template` source files.** The `.template` sources themselves
(`scan_tiling.template` 85 lines, `scan_tiling_data.template` 30, and the `dav310/` directory).
**Reason:** `Q-950fin-31` (`gsS`) and `C-950fin-028` (`mode 2`) are both resolvable by reading them,
and both are cheap. Not done here because the wave's budget went to the eight `.md` documents; this is
the highest-value cheap follow-up in the domain.

**5. `reference/scan/guide.md` beyond the four passages cited.** 280 lines, of which the eight tiling
keys, the ping-pong divergence, the three-values case and the bank predicate were mined. **Reason:**
`950:0132`–`950:0139` already carry the analysis shelf's scan family and much of `guide.md` is that
material's twin; per Amendment 2 an entered claim is cited, not re-entered.

**6. `reference/elementwise/double_buffer_design.md`.** **Reason: already mined** — `950:0319` and
`950:0321` carry it, including its 910-calibrated capacities (`C-950bp-010`). See the errata below.

---

## Errata — statements carried into this wave that failed re-verification

**E-1 · Card `ascendc-tiling-design--003`: "Nothing in the FA or matmul families names a chip."**
**FALSE.** `flashattention/design.md:94` (`典型 D ≥ 256 触发,A5 平台尤为关键`), `:525`
(`A2/A3 用 mode=2;A5 推荐 mode=4`), `:617` (`A5 平台 mode=4 同步基座`), `subfamilies.md:195`
(`GQA × mxfp8 推理,A5 平台`), and `matmul/matmul-fusion-design-template.md:30`
(`| 支持芯片 | Ascend950（mxfp8 仅 Ascend950 硬件支持） |`). Five sites. **The card disclaimed this
itself** — "Neither directory was read line by line, so this card's 'no measurements, no chips'
statement is a property of the shelf-level survey and not of a full read — a later pass must not
inherit it." So this is the card working as designed, and it is recorded rather than blamed. The card
is outside this domain's write partition and was not edited. `design.md:525` is additionally the FA
family's one genuine dual-architecture statement; its 910 half is book-910's and was not carried.

**E-2 · Card `ascendc-tiling-design--003`: "four of nine categories are empty."**
**Off by one.** `ops/ascendc-tiling-design/SKILL.md` carries nine rows of which **three** are
`📋 规划中` (Random `:16`, Convolution `:18`, NN-other `:20`), and `references/` holds six
directories — a clean 9 = 3 + 6. The card counted MatMul as a fourth because its content is scoped to
one fusion pattern, which is true (`C-950fin-014`) and is a different property from having no
directory. `950:0467` states the corrected count.

**E-3 · Work order: "`reference/elementwise/` — zero entries so far."**
**FALSE for the directory, true for the file.** `double_buffer_design.md` is mined at `950:0319` and
`950:0321`. Only `vector_efficiency_design.md` was unmined, and it is now `950:0477`–`950:0480`.

**E-4 · Card `ascendc-performance-best-practices--009`: two line pointers off by one.**
`guide.md:148` for the `4%~31%` ping-pong gain is actually `:147`; `usage_guide.md:126` for the
`约 3%` two-row interleave is actually `:125`. Both claims are correct; both pointers were one line
low. Every other pointer in that card re-verified exactly, including all five priority items.
The card is outside this domain's write partition and was not edited.

**E-5 · Card `ascendc-performance-best-practices--008`: already corrected by the controller.**
The card's invented broadcast NaN quote was corrected in place on 2026-08-24 before this wave. Its
third priority — the Counter-mode claim — re-verified exactly and is now `950:0477`.

---

## What this wave leaves for phase 2+
Mining freezes after this wave (Amendment 4). The cheapest remaining work, in order:
1. Read the four `.template` sources in `reference/scan/templates/` — closes `Q-950fin-31` and
   `C-950fin-028` by file read, no device.
2. Compile the four statements in `950:0477` §4 arm 1 and `950:0478` §4 arm 1 — closes `C-950fin-021`
   and `C-950fin-022`, no device.
3. Enumerate `WholeReduceSum<T, true, U>` acceptance for a DAV_3510 target — `950:0480` §4 arm 1,
   no device, and it is the only genuinely-950 capability this wave found.
4. Correct `form/CONVENTIONS.md`'s vocabulary map for the five unmapped `__NPU_ARCH__` values
   (`C-950fin-009`) — controller's call, outside this domain's partition.
