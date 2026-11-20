# Standing questions — book-910

Named measurements this book owes. Each is a question upstream does not answer, posed during the
2026-08-24 harvest and answerable only on a real 910-family board (or, where marked, by read-only
inspection of an installed toolkit). Format per question: the question in one line · MEASUREMENT
(what to run) · READOUT (the quantity that answers it) · POSED · STATE · GATES (the entries whose
scope depends on the answer).

**These are not gaps to be filled by inference.** Where the 950 book will carry a technique or a
threshold and no 910 authority exists anywhere upstream, that absence is recorded here rather than
invented. A question with STATE UNANSWERED is this book working, not this book failing.

Sole writer: the book-910 harvester. Merged into the shared queue by the controller in wave 2.

---

## Q-910-01 · What is the vector register width on DAV_2201, and hence VL for each dtype?

Every `VRegSize = 256B` / `VL_FP32 = 64` statement in the sources surveyed is scoped to
**dav-3510 / Ascend950**, not to DAV_2201.

- MEASUREMENT · `Ops::Base::GetVRegSize()` (or the installed SDK's equivalent) queried on a named
  DAV_2201 part, printed alongside `GetCurNpuArch()` on one line. Read-only arm first:
  `grep -Rn "GetVRegSize\|VRegSize" "$ASCEND_HOME_PATH"/*/include` and record whether the symbol
  exists at all for a 2201 target, and whether it is arch-guarded.
- READOUT · register width in bytes; the derived element count per dtype; and whether the accessor
  exists on this architecture at all — a negative is a complete answer.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · nothing in this book currently claims a register width. **This is the one item on the
  deep-dive §5.3 "establish from scratch" list that survived re-verification for the 910 side**:
  the other five (32 B DataCopy granularity, 256 B repeat granularity, cache line, DCache size,
  repeatTimes ≤ 255) all have upstream authority and became entries 0021/0022, 0032, 0018/0020,
  0018, 0031. See this book's harvest report.
- NOTE · the closest DAV_2201-scoped quantity that exists is the 256 B Vector *repeat* coverage of
  0032 (8 DataBlocks × 32 B, stated in an Atlas A2/A3-scoped passage). A repeat's coverage and a
  register's width are not the same quantity and must not be substituted for one another, even
  when they happen to share a number on another architecture.

## Q-910-02 · What is L2 capacity on a named Ascend910B2 part — 32 MB or 192 MB?

Upstream states both, 6× apart, in two documents that do not cite each other. `harvest/CONTRADICTIONS.md` C-001.

- MEASUREMENT · the four arms of 0007 §4: record the physical part; enumerate `l2_size` across
  every `platform_config/*.ini` (read-only, no card needed); query at runtime if any accessor
  exists; then the behavioural arm — a streaming read swept over 8 MB … 256 MB with `hit_rate` from
  `L2Cache.csv`, three repeats, on the named die.
- READOUT · `l2_knee_bytes`, the working-set size at which L2 hit rate collapses; and `l2_ini_bytes`
  per INI, reported separately and never averaged.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0007 (which claims the disagreement, and is written to be overturned by this answer);
  0062; any future L2-residency or `SetL2CacheHint` recommendation in the delivered skill.
- NOTE 1 · a candidate provenance for the 32 MB figure — it is exactly npu-arch's own **DAV_1001**
  `l2_size` — is recorded in 0007 §3 as a lead for the procedure, explicitly not as a resolution.
- NOTE 2 · **the question as posed above is too narrow.** A third figure exists —
  `npu-arch/references/npu-arch-guide.md:93` gives 910B4 **96 MB** — so L2 varies by sub-model and
  "the 910 L2" is not a quantity. The answer owed is a **per-board table**, not a winner between two
  numbers. See `harvest/contradictions-910.md` C-910-010 and entry 0062.
- NOTE 3 · **an accessor exists**: `GetCoreMemSize(platform_ascendc::CoreMemType::L2, l2Size)`,
  `npu-arch/references/npu-arch-guide.md:208`. An earlier draft of this book recorded its absence;
  that error is self-reported in entry 0011 §7. The runtime arm is therefore cheap and should be run
  first.

## Q-910-03 · Is there a DAV_2201 hardware repeat ceiling independent of the uint8 parameter type?

Upstream's 255 limit is stated conditionally — "当 `repeatTime` 为 `uint8_t` 类型时" — which makes
it a statement about an API signature, not about silicon (0031).

- MEASUREMENT · read-only first: `grep -Rn "repeatTimes\|repeatTime" "$ASCEND_HOME_PATH"/*/include`
  and record the declared parameter type for every API in 0031 §3's list, with header path and
  toolkit version. If any API carries a wider parameter, drive it past 255 on a named die and find
  where correctness or throughput breaks.
- READOUT · the parameter type per API; and, where a wider one exists, the repeat count at which
  results or throughput change.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0031, whose §1 deliberately claims only the type limit.
- NOTE · "every listed API is `uint8_t`, so a hardware ceiling is unreachable from AscendC" is a
  complete and final answer to this question and should be written as one rather than left open.

## Q-910-04 · Is DCache 16 KB or 32 KB on DAV_2201?

One upstream file says "16K / 32K" in its cache table and "32KB 限制" in its constraint table,
ninety lines apart, with no architecture stated for either. `harvest/contradictions-910.md` C-910-003.

- MEASUREMENT · 0018 §4 arm 2: a scalar-only kernel striding a GM array at 64 B, working set swept
  4 KB … 128 KB in powers of two, `SCALARLDST` time per element, on a named die.
- READOUT · `dcache_knee`, the working-set size at which per-element scalar read cost steps up.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0018. Any UB budget expression of the form `usable = ubSize − DCACHE` needs one number,
  and currently there are two.

## Q-910-05 · What separates Atlas A3 from Atlas A2 at build time or at runtime?

`__NPU_ARCH__` is 2201 for both (0001). `GetCurNpuArch()` returns `DAV_2201` for both.
`GetSocVersion()` returns `ASCEND910B` for both, the dedicated `ASCEND910_93` enumerator being
unused by the conversion map (0002). Every identifier an agent can query collapses.

- MEASUREMENT · on one Atlas A2 part and one Ascend910_93 part, both named, occupancy checked on
  each, no substitution: print `__NPU_ARCH__`, `GetCurNpuArch()`, `GetSocVersion()` as an integer,
  the `npu-smi info -t board` string, and `GetCoreNumAic/Aiv()`. Then enumerate every
  `PlatformAscendC` accessor the installed SDK exposes and diff the full result vectors.
- READOUT · the set of queryable values that differ between the two parts — possibly empty, which
  would itself be the answer and a significant one.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0001 §7, 0002 §7, 0047. Every entry in this book whose BOARD is
  `family-claimed(unverified)` on the strength of a DAV_2201 or "A2" source inherits this question.
- NOTE · upstream's most-measured 910 document refuses to carry its A2 results to A3 (0047), which
  means someone upstream believed the parts differ materially. What differs is not recorded
  anywhere in scope.

## Q-910-06 · Do the A2-verified sort findings hold on Ascend910_93?

`radix_sort.md` declares itself A2-verified and explicitly declines to extend: "A3、A5 等架构的
硬件细节差异需另行验证后再套用."

- MEASUREMENT · 0047 §4: run the arms of 0041 (barrier cost), 0042 (TBuf/TQue overlap), 0044
  (int16 saturation), 0045 (ReduceSum dtypes) and 0046 (half exactness) on one A2 part and one A3
  part, same binary where the toolchain permits, results recorded twice and never merged.
- READOUT · per sub-claim, the pair (result_A2, result_A3) and whether they agree.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0041, 0042, 0044, 0045, 0046, 0048 — every one of which carries BOARD
  `family-claimed(unverified)` because "A2" is a product line, not a board.
- NOTE · a single-part run answers nothing here and must be recorded as NOT ATTEMPTED rather than
  as a partial pass. This is the question most likely to be quietly answered wrong.

## Q-910-07 · What are the core counts on 910B4, Ascend910B2C and Ascend910_93?

Upstream gives 24/48 for 910B1/B2 and 20/40 for 910B3 (0009) — a 17 % difference inside one
NpuArch — and gives nothing for the other three DAV_2201 parts. A third upstream statement puts the
910B usable range at 20–40, which excludes 910B1/B2's own figures. `harvest/contradictions-910.md`
C-910-002.

- MEASUREMENT · `GetCoreNumAic()` / `GetCoreNumAiv()` on each available part, printed with the
  `npu-smi info -t board` string and `GetCurNpuArch()` on one line. Read-only arm:
  `grep -Rn "cube_core_cnt\|vector_core_cnt\|ai_core_cnt" "$ASCEND_HOME_PATH"/*/data/platform_config/`
  recording every 910B-family INI found, whether or not it matches an installed part.
- READOUT · the (aic, aiv) pair per named board.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0008 (whose checker deliberately tests the 1:2 *ratio* rather than absolute counts, for
  this reason), 0009, 0011, 0054 (where "满核" names a different number on different parts).

## Q-910-08 · Does `form/CONVENTIONS.md` need a board token for Ascend910B3?

Two upstream files scope claims to Ascend910B3 by name — a core-count row
(`metrics_reference.md:131`) and a UB budget example
(`elementwise/double_buffer_design.md:80`) — and the accepted board-token list has no spelling for
it. Entries 0009 and 0043 therefore carry `family-claimed(unverified)`, which under-states what
their sources say.

- MEASUREMENT · none required; this is a form decision for the controller, recorded here because
  the book cannot edit `form/`. The evidence is the two citations above plus npu-arch's product row
  "Ascend910B1~B4" (`npu-hardware-params.md:17`), which includes B3 in the family.
- READOUT · a token added to CONVENTIONS and to `tools/check_entries.sh` in the same change, or a
  ruling that B3 claims stay family-scoped.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0009 §3, 0043 §3. Also 910B4 and 910B2C, which have tokens but no upstream data.

## Q-910-09 · Do the unscoped bottleneck thresholds hold on DAV_2201?

The utilisation ladder (>80 % / 50–80 % / 10–50 % / <10 %), the VEC severity bands (50–65 / 65–80 /
>80), SCALAR > 30 %, core-time spread > 10 %, and the conflict gates (3 % / 5 % / 15 %) are stated
with **no architecture, no board, no case and no derivation** (0053, 0052).

- MEASUREMENT · 0053 §4: a family of kernels whose `aiv_vec_ratio` spans 20–95 % in ~5-point steps
  at fixed data volume; apply one fixed optimisation (UB fusion) to each; plot speed-up against
  baseline ratio; fit the step location rather than testing only the quoted value.
- READOUT · `yield(ratio)`, and the fitted boundary if a step exists.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0053, 0054's 30 % rule, 0058's L2 hit-rate gate, 0059's 10 % imbalance rule,
  0052's conflict gates.
- NOTE · the likely outcome is a smooth curve with no step, which would mean the ladder is a
  continuum. That is a different instruction to a consuming agent than "optimise above 80 %", and
  is a real answer, not a null result.

## Q-910-10 · What is the achievable GM bandwidth curve on a named DAV_2201 board?

Upstream quotes a 1.8 TB/s peak (0055) and, separately, that 32 B-aligned access reaches ~70 % of
512 B-aligned (0024) and that transfers below 256 B are setup-dominated (0025) — none with a
shape, dtype, tool or repeat count, and two upstream documents disagree about whether peak is
approached at 16 KB or 64 KB.

- MEASUREMENT · one shared 6×6 grid, run once for 0024, 0025 and 0055: alignment {32, 64, 128, 256,
  512, 1024} B × transfer size {256 B, 1 KB, 4 KB, 16 KB, 64 KB, 256 KB}, GM→UB, fixed dtype, five
  repeats per cell with the first discarded, on a named die.
- READOUT · achieved GB/s per cell; `ratio(size) = bw(32B) / bw(512B)` per size; the maximum
  sustained figure and its ratio to the quoted 1.8 TB/s.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0020, 0024, 0025, 0055.
- NOTE · if `ratio(size)` varies across the size axis by more than the measurement spread, then no
  single "70 %" exists and 0024's claim is the wrong *shape* of claim, not merely wrong. That
  outcome is declared in advance in 0024 §5.

## Q-910-11 · What does the FixPipe inline path on DAV_2201 actually support?

Upstream states one gap — no int32→bf16 (0040) — in a single line, with no enumeration of what IS
supported. A capability known only by one of its holes cannot be planned against.

- MEASUREMENT · read-only, no card:
  `grep -Rn "FixPipe\|QuantMode\|fixpipe" "$ASCEND_HOME_PATH"/*/include` for the supported
  source/destination dtype enumerations, with header path and toolkit version. Then a compile
  matrix over the plausible pairs targeting `__NPU_ARCH__` 2201, with a known-supported pair as the
  positive control.
- READOUT · `supported_pairs`, the full enumeration.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0040, which can currently only tell an agent what to avoid.

## Q-910-12 · Does "220x" have a defined place in the upstream vocabulary map?

`ub_resident_design.md:34` uses "NPU 架构版本 220x（Atlas A2/A3 系列）" — a fourth spelling for this
architecture alongside `DAV_2201`, `__NPU_ARCH__` 2201 and arch22 — and npu-arch's §0 vocabulary
map does not define it.

- MEASUREMENT · none on a device. `grep -Rn "220x\|350\b" upstream/skills-dev-main/ops/` to
  establish how widely the spelling is used and whether it is ever defined; and whether "Atlas 350",
  used in the same table as DAV_2201's contrast, maps to DAV_3510 or to something else.
- READOUT · the set of files using each spelling, and any definition.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0014 and 0032, both of which take their DAV_2201 attribution from that parenthetical.
  The parenthetical makes the intent unambiguous in that one file; the concern is that another file
  might use "220x" without it.

## Q-910-13 · Is there a hardware cross-core barrier on A2 after all?

`radix_sort.md` says "A2 无硬件 barrier" and implements global sync by GM polling at ~200 µs
(0041). `metrics_reference.md` §8.2, headed "核间同步（Atlas A2/A3）", documents three cross-core
synchronisation modes and a `CrossCoreSetFlag`/`CrossCoreWaitFlag` API with a flagId counter
limited to 15 settings. Both are upstream; neither mentions the other.

- MEASUREMENT · 0041 §4 arm 4: time a global synchronisation built on `CrossCoreSetFlag` in mode 0
  (documented as all-AIC or all-AIV) against the GM-polling FullBarrier, same die, same core count,
  five repeats each.
- READOUT · `crosscore_us` against `barrier_us`.
- POSED 2026-08-24 · STATE UNANSWERED — but **substantially narrowed** by a third source found in
  the end-of-harvest coverage sweep.
- GATES · 0041, whose §1 would narrow to "the GM-polling barrier is what this implementation used"
  if a hardware path proves cheaper — a materially weaker claim than "A2 has no hardware barrier";
  also 0060, 0061.
- NOTE · `ascendc-api-best-practices/references/api-crosscore-sync.md:127` states that on DAV_2201
  the `modeId`/`pipe` template parameters **do not take effect** and `CrossCoreWaitFlag` **blocks
  every pipeline** (entry 0060). Both upstream statements can then be true at once: the flags exist,
  and there is no *fine-grained* cross-core barrier — which is what an author seeking MTE2/Vector
  overlap would call "无硬件 barrier". **That reconciliation is this book's inference, not
  upstream's**, and the cost question is still untouched: nobody has timed a mode-0
  `CrossCoreSetFlag` global sync against the ~200 µs GM poll.

## Q-910-14 · What is the default value of `INF_NAN_MODE_ENABLE`, and does it change hardware output?

An accuracy verdict that depends on an environment variable can differ between two machines running
identical code on identical silicon (0056). No source in scope states the default.

- MEASUREMENT · 0056 §4: one inf-producing kernel run twice on the same named die with the variable
  at 0 and at 1, same binary md5-confirmed, comparing **raw device outputs bitwise before applying
  any comparison rule** — that step separates "the hardware behaves differently" from "the checker
  accepts differently". Read the variable back from inside the run rather than trusting that it was
  set.
- READOUT · `outputs_differ` (bitwise, raw) and `verdicts_differ` (after
  `check_inf_nan_consistency`), reported separately; plus the observed default on the installation.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0056.

## Q-910-15 · Does the 4:2 structured sparsity of DAV_2201 have a reachable API?

`sparsity = 1` is asserted as an INI field (0010) and **no upstream file in scope teaches how to
use it** — no API, no tiling constraint, no measured speed-up. A capability bit with no
documentation is indistinguishable from an absent capability at the point of use.

- MEASUREMENT · read-only first:
  `grep -Rn "sparse\|sparsity\|Sparse" "$ASCEND_HOME_PATH"/*/include` for a Matmul sparse path.
  Then 0010 §4: a 4:2 structured-sparse Matmul against its dense twin at identical shape, dtype and
  tiling, alternating arms, five repeats, first discarded, on a named die.
- READOUT · whether an API exists at all; and if so `dense_time / sparse_time` against the dense
  arm's own repeat-to-repeat spread.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0010.
- NOTE · "the bit is set and nothing in AscendC reaches it" is a complete answer and is worth more
  to a consuming agent than a speed-up number. A speed-up of 1.0 does not overturn 0010 — the claim
  is support, not benefit — and 0010 §5 declares that split in advance.


## Q-910-16 · Does FP32 Vector run at half the FP16 rate on DAV_2201?

`npu-arch-guide.md:161` derives 910B2 Vector **FP16** peak as 128 × 48 × 1800 × 2 ÷ 10⁶ = **22
TFLOPS**. `ops-profiling/SKILL.md:252` quotes **FP32** Vector peak as ~**11.06 TOPS**. 22/2 = 11.
The two are consistent under "FP32 runs at half the FP16 rate" — **and neither document says so**.

- MEASUREMENT · entry 0063 §4 arms 3 and 4: a dense UB-resident Vector kernel at high arithmetic
  intensity, swept upward until throughput plateaus, run at FP16 and at FP32 on a named die
  (occupancy before and after, no substitution), five repeats with the first discarded.
- READOUT · `fp32_ratio` = FP32 plateau ÷ FP16 plateau, and both absolute plateaus in TFLOPS.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0055 (whose §7 names the per-core-versus-whole-chip ambiguity as its largest unknown —
  the derivation settles that half, since 48 cores are inside the formula), 0063.
- NOTE · this is a question about **this book's arithmetic**, not upstream's claim. 0063 §5 labels
  the verdict as such so that a failure corrects our §2 and leaves upstream's derivation standing.

## Q-910-17 · What does a bfloat16 Vector operation actually do on DAV_2201?

`npu-arch-guide.md:123` asserts "Vector 不支持 bfloat16" in a single parenthetical sentence, with no
corroboration and no elaboration anywhere in scope (entry 0065). Compile error, silent cast to
fp16, wrong result, and correct-but-half-rate are all consistent with "不支持" — and they call for
completely different handling in a BF16 training pipeline.

- MEASUREMENT · entry 0065 §4: compile `Add`, `Mul`, `ReduceSum` over `bfloat16_t` for
  `__NPU_ARCH__` 2201 with the same three over `half` as a mandatory positive control; for whatever
  compiles, compare against a host bf16 reference **bitwise** (not within a tolerance — a silent
  fp16 round-trip would pass any robust tolerance); then time bf16 against fp16 at identical shapes;
  then inspect the device `.text` for cast instructions bracketing the operation.
- READOUT · three outcomes kept separate — does-not-compile / compiles-and-exact /
  **compiles-and-inexact** — plus `bf16_rate_ratio`. The middle outcome is the dangerous one and a
  boolean check would hide it.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0065. Compounds with 0040 (Cube inline quantisation cannot go int32→bf16) and 0035
  (Select cannot write int32): three dtype restrictions on this family, each a single line in a
  different document, together constraining a quantised BF16 epilogue tightly.

## Q-910-18 · Is `npu-arch`'s own 1.6 TB/s or ops-profiling's 1.8 TB/s the right bandwidth denominator?

Two figures 12.5 % apart for one quantity, at two different scopes (a board versus a product line),
where the one used in every theoretical-time formula is the one the truth source does **not**
endorse — `npu-arch-guide.md:91` marks its 1.6 TB/s `[¹](#unverified)` (entry 0064, C-910-011).

- MEASUREMENT · folded into the Q-910-10 bandwidth grid: an all-core, 512 B-aligned streaming read
  at the largest transfer size, plus a mixed read+write arm to test whether upstream's shared-
  bandwidth sum model holds at all.
- READOUT · `bw_sustained` in GB/s, reported as two ratios (against 1.6 and against 1.8), never one;
  and `mixed_model_error`.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0055, 0064.
- NOTE · 0064 §5 declares **in advance** that a sustained figure landing *between* the two is not a
  resolution and must not be narrated as favouring the higher. Only a sustained figure above
  1.6 TB/s discriminates. This is the outcome most open to convenient reading.

## Q-910-19 · Do the arch22-only scatter reduce modes work, and what is a fair baseline?

`scatter_design.md:153` asserts that CANN's built-in scatter accepts `max`/`min`/`mean` only on the
arch22 (910B / 910_93) branch, while the 950 branch is limited to `none`/`add`/`mul` — a capability
the older family has and the newer does not, like 0010's 4:2 sparsity. The same line asserts that
PyTorch's `scatter_reduce_` has **no NPU binding at all** and falls back to CPU.

- MEASUREMENT · entry 0066 §4: call the built-in with each of the six `reduction` values on a named
  DAV_2201 part, recording acceptance and the exact rejection message; grep the installed toolkit for
  `REGBASE_DTYPE_SUPPORT_LIST` and the arch guard around it; verify accepted modes against a host
  reference; and record whether the PyTorch baseline executes on NPU or CPU.
- READOUT · `accepted_modes(2201)`, and `baseline_device` ∈ {npu, cpu}.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0066.
- NOTE · `baseline_device` is the verdict most likely to be dropped as uninteresting and the one that
  decides whether any speed-up measured against that baseline means anything. A DAV_3510 control is
  needed for the *branch* half; without it only the 910 half is established, and 0066 §5 says so.


## Q-910-20 · Do the reserved TEventIDs come out of the same eight that bound the TQue count?

`api-buffer.md:87` gives Atlas A2/A3 **8 event IDs and a maximum of 8 TQues** (4 under double
buffering) — entry 0067. `metrics_reference.md:436` says TEventID **6 and 7 are system-reserved**
("不建议手动插入"). If those are the same eight, the usable ceiling is 6, not 8. Upstream reconciles
the two nowhere.

- MEASUREMENT · entry 0067 §4: allocate N `TQue` with `InitBuffer(que, 1, small)` for N = 7, 8, 9
  and locate the ceiling, with total UB held far below 192 KB so memory is never the binding
  constraint; then repeat while explicitly consuming TEventID 6 and 7 via `AllocEventID` and see
  whether the ceiling drops.
- READOUT · `max_tque(num=1)`, `max_tque(num=2)`, and the ceiling under deliberate reservation.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0067, and the claim-card `ascendc-performance-analysis--001` (which holds the reservation
  fragment and was not promoted to an entry precisely because of this tension).
- NOTE · the UB-far-below-capacity gate is what separates an event-ID ceiling from a memory ceiling;
  without it the experiment cannot attribute the failure.

## Q-910-21 · Is DataCopyPad's blockCount cap 4095 or the uint16 field's 65535?

Two ceilings 16× apart (C-910-012, entry 0069), only the smaller of which upstream ever acts on, in
an API family where the parameter type is the limit for two neighbouring fields (0026, 0027) and is
not here.

- MEASUREMENT · entry 0069 §4: read-only header arm first
  (`grep -Rn "blockCount" "$ASCEND_HOME_PATH"/*/include` for the declared type and any documented
  range); then `blockCount` swept over 4094, 4095, 4096, 4097, 8191, 8192 at small `blockLen`
  against a destination poisoned to 0xDEADBEEF, counting blocks actually delivered.
- READOUT · `blocks_arrived(blockCount)`, and the mechanism as a **three-way** verdict — wrap (0
  arrive) / clamp (4095 arrive) / soft limit (4096 arrive).
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0069, and any batched multi-row copy whose tile row count can exceed 4095 — which for a
  narrow row inside 192 KB of UB is reachable without any other constraint objecting.

## Q-910-22 · What is the magnitude of float atomic-accumulation jitter, and how does it scale with mantissa width?

Upstream asserts that float atomic accumulation is order-dependent and jitters run to run
(`api-atomic.md:49`, entry 0073) and supports `float`, `half` and `bfloat16_t` for it
(`:129-137`, entry 0074) — without quantifying the jitter for any of them.

- MEASUREMENT · entry 0073 §4: a multi-core float atomic accumulation over **identical** input,
  200 launches, output hashed each time; then max − min per element across runs, in absolute terms
  and in ULPs; repeated for `half` and `bfloat16_t`; with a single-writer-plus-explicit-reduce arm
  as the determinism control and a timing arm so the price of determinism is recorded.
- READOUT · `distinct_hashes(variant, dtype)` and `jitter_ulps(dtype)`.
- POSED 2026-08-24 · STATE UNANSWERED
- GATES · 0073, 0074. **And a constraint on the rest of this book**: several §4 procedures here
  require "bitwise identical against the control arm" (0021, 0023, 0027, 0065). Applied to a
  float-atomic kernel, any such comparison must switch to a tolerance derived from this answer, or
  it will report a difference that is not one.
- NOTE · `distinct_hashes == 1` after 200 launches does **not** establish determinism and is
  recorded as "did not bite, retained" — 0073 §5 declares that asymmetry in advance so a clean sweep
  cannot be narrated as a refutation.
