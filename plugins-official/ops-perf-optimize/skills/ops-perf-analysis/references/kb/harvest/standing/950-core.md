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
