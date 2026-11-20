# Contradictions register — domain `950-rem` (regbase patterns/dev-experience/pitfalls · SIMT · MC² layout)

> **TRIAGED 2026-08-25**: every row below has a phase-2 disposition in
> `harvest/TRIAGE_DOMAIN_ROWS_20260825.md` (resolved / assigned-to-round / noted / blocked).
> C-950rem-012 was resolved by reading during the triage: `winAlignBytes` is undefined upstream
> (one occurrence in the whole skill = the use site; the three 下一跳 files carry no alignment rule).

Per-agent register for the 950-remainder harvest block (`book-950/entries/0351-0399`), to be merged into
`harvest/CONTRADICTIONS.md` by the controller in wave 2. Row format follows that file.

Same topic, different advice or numbers, across upstream sources — or between an upstream source and the
vendor's installed CANN toolkit read under the phase-1 read-only exception. Recorded here and in the
affected entries' §3; resolved only by a procedure run on a named board (RULES.md Art. 7). Every quote below was
re-verified against the file during this harvest.

Toolkit pin used throughout, where "installed toolkit" appears:
`/usr/local/Ascend/cann-9.0.0-beta.2`, `Version=9.0.0-beta.2`,
`innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, `arch=aarch64`.
`arm64-linux` is a symlink to `aarch64-linux`; `include/ascendc` resolves to `aarch64-linux/asc/include`,
so the whitelist's declared header root and the paths read here are the same files. Read-only: no
execution, no compilation, no device contact.

Several rows below are **one repo disagreeing with itself, sometimes inside one file**. That is still a
contradiction under Art. 7 and still cannot be settled by reading more of that repo.

---

## C-950rem-001 · the canonical VF body calls the load by the spelling the whitelist marks kernel-side-only
- `ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:64` — the Data-movement
  row lists `DataCopy` with `VF Function? = No`, header root `basic_api/interface/`; `:80` lists the
  VF-safe load/store family as `LoadAlign`, `StoreAlign`, `Load`, `Store`, `Gather`, `Scatter` and the
  UnAlign forms — no `DataCopy`. The file's own gate at `:26`: "If an API is absent from the lists below,
  treat it as unavailable until you verify it in the installed SDK headers".
- `ascendc-regbase-best-practice/references/knowledge/patterns/regbase_kernel_dataflow_patterns.md:102,106`
  — the canonical minimal VF body calls `DataCopy<float, LoadDist::DIST_NORM>(vin, inAddr + i * VL);` and
  `DataCopy<float, StoreDist::DIST_NORM_B32>(outAddr + i * VL, vout, mask);` inside `__VEC_SCOPE__`, and
  `:43,45` calls those "VF-safe loads/stores".
- `ascendc-regbase-best-practice/references/paradigms/common/vf-programming-rules.md:15` — a third
  position: "新代码统一走 `LoadAlign` / `StoreAlign`".
→ 950 book. Carried by `950:0353`; the underlying API fact is `950:0351`.
The installed toolkit settles the *factual* half and not this one: `Reg::DataCopy` exists (see
C-950rem-002 below is a different row — see `950:0351` SOURCE) but what a whitelist *means* is not in a
header. Note the whitelist's own guardrail at `:102` ("Check the VF-capable header first when the code path
uses `RegTensor`, `MaskReg`, `LoadDist`, or `StoreDist`") would have resolved the case and points the
opposite way from its tables.

## C-950rem-002 · queue constructs in a regbase outer shell are membase leakage in one file and normal in another
- `ascendc-regbase-best-practice/references/knowledge/patterns/regbase_operator_patterns.md:109-118` —
  "When a design starts leaning on: / - `TPipe` / - `TQue` / - `DataCopyPad` as the central execution model
  / - membase-style queue choreography / then the task is no longer choosing a regbase pattern … re-check
  whether the branch or platform assumption is wrong".
- `ascendc-regbase-best-practice/references/knowledge/dev-experience/regbase_programming_notes.md:49-56` —
  "Real regbase kernels often still have an outer shell with: `TPipe` / `TQue` / `GlobalTensor` /
  `LocalTensor` … Those constructs do not automatically mean the operator has left the regbase path. The
  real question is: **where does the actual math happen?**"
- `ascendc-regbase-best-practice/references/knowledge/patterns/regbase_kernel_dataflow_patterns.md:36-38` —
  `TQue` is a named component of layer 2 of the *canonical* regbase kernel.
→ 950 book. Carried by `950:0372`; the layer partition itself is `950:0355`.
Both authors hedge ("leaning on", "not automatically mean") toward a middle neither supplies, so the hedges
do not meet. `950:0372` Arm A predicts the disagreement has **no machine answer**, in which case the
resolution is editorial — which is itself the finding.

## C-950rem-003 · the SIMT index accessors return `int32_t` and the guide's table says `uint64_t`
- `ascendc-simt-programming-best-practices/references/index-calculation.md:5-10` — the API table gives
  `GetThreadIdx()`, `GetThreadNum()`, `GetBlockIdx()`, `GetBlockNum()` a return type of `uint64_t`, and
  `:14-19` computes `uint64_t globalIdx = GetBlockIdx() * GetThreadNum() + GetThreadIdx();` uncast.
- installed toolkit — `asc/include/interface/simt_api/cpp/kernel_simt_common_intf.h:28-38` declares all
  four as `int32_t`, and the two thread accessors as **templates** over an `int32_t dim` defaulting to 0.
  A fifth accessor, `GetWarpSize()`, is declared beside them.
- `ascendc-simt-programming-best-practices/references/vf-call.md:21-24` — the same expression, here wrapped
  in `static_cast<uint64_t>(...)`; the only place in the skill that acknowledges the types.
→ 950 book. Carried by `950:0374`. Under the header's types the documented expression evaluates in signed
32-bit arithmetic and widens only at assignment. The undocumented `dim` template parameter is the larger
half: an undecorated `GetThreadIdx()` under a multi-dimensional launch returns dimension 0 only.
**Also a re-verification correction owed to `Q-950arch-11`** — see the method notes below.

## C-950rem-004 · the C++ operator and the explicit math API are called equivalent and then separated by rounding control
- `ascendc-simt-programming-best-practices/references/compute-operators.md:17-18` — "C++ 运算符是 SIMT
  底层函数 API 的重载封装，**功能完全等价**" and "**优先使用运算符写法**（如 `a / b` 而非 `fdividef(a, b)`）".
- same file `:19-22` — "显式 API（如 `fdividef`、`fmaf`、`__hfma` 等）主要用于：/ - 需要精确控制舍入模式 …".
- same file `:33` — the worked example annotates `y[i] = fdividef(a[i], b[i]);` with "需要特定舍入模式时".
→ 950 book. Carried by `950:0380`. Eight lines apart, one file, the same worked pair. A weaker reading —
功能完全等价 meaning "computes the same function" rather than "produces the same bits" — is available and
upstream does not state it; `950:0380` Arm B (disassembly comparison) is what decides. Four of the five rows
of the same file's mapping table name **no** underlying API at all, so the escape hatch the third bullet
promises is unnavigable for bitwise, comparison, logical and select operations.

## C-950rem-005 · the TensorList walker strides by a runtime dim count over a fixed eight-slot shape array
- `ascendc-simt-programming-best-practices/references/tensorlist-handling.md:9-18` — the declared layout:
  each `TensorDesc` is `dim (uint32_t)` + `index (uint32_t)` + `shape[SHAPE_DIM] (uint64_t[])` with
  "SHAPE_DIM 固定为 8" — i.e. 9 sixty-four-bit words, fixed.
- same file `:58-64` — the shipped device-side walker computes
  `uint32_t dimSize = *(ptr + 1) & 0xffffffff; uint32_t descStructSize = 1 + dimSize;` and strides by
  `descStructSize * idx` — i.e. `1 + dim` words, variable.
→ 950 book. Carried by `950:0381`. The two agree only when `dim == 8`; a list of rank-2 tensors gives a
stride of 3 words against a layout of 9, so `idx ≥ 1` reads another tensor's shape value — a plausible
positive integer, not a fault. One dump of a rank-mixed list decides which half is wrong. The same file's
*address* walker (`:50-55`) avoids the question entirely by reading an explicit `ptrOffset`.

## C-950rem-006 · the two `assert` examples in one reference disagree about whether the printed condition is the asserted one
- `ascendc-simt-api-reference/references/debug-api.md:52-61` — `assert(assertFlag == 10)` with
  `assertFlag = 10`, and the shown output ``Assertion `assertFlag != 10' failed.`` — the negation, from a
  condition that is **true**.
- same file `:111-123` — `assert(!isnan(x[idx]))` and the shown output
  ``Assertion `!isnan(x[idx])' failed.`` — the condition itself, unnegated.
- same file `:47` — the prose: "如果assert的内部条件判断不为真，则会输出assert条件".
- same file `:36-42` — the AI CPU sibling's example gives a **third** message format:
  ``[ASSERT]` assertFlag == 12 ' at /home/.../test.cpp:36`` — different prefix, different quoting,
  different ordering, condition unnegated, and self-consistent (10 == 12 is genuinely false).
→ 950 book. Carried by `950:0384`. The two readings point at **opposite states of the same variable** when
an agent reads a real assertion log. One fired assertion settles it. Note both SIMT examples print
`add_custom.cpp:44` for snippets of different lengths, which lowers the evidential weight of both output
blocks equally.

## C-950rem-007 · the debug reference documents five interfaces under three index rows
- `ascendc-simt-api-reference/references/debug-api.md:7-15` — one header line
  (`simt_api/asc_simt.h`), one scope line ("SIMT VF函数内使用的调试接口"), and three index rows with
  prototypes `void printf(const __gm__ char* fmt, ...)`, `void assert(bool condition)`, `void __trap()`.
- same file `:24,129,228,347,464` — **five** detail sections: `assert-177` (SIMT VF, fusion compilation
  only, `utils/debug/asc_assert.h`), `assert-179` (AI CPU, `aicpu_api.h`, `<<<...>>>` invocation,
  heterogeneous compilation), `printf-176` (SIMT VF, variadic **template**, `__simt_callee__`,
  `utils/debug/asc_printf.h`), `printf-178` (AI CPU, C variadic, `AscendC::printf`, 1 MB per-core Dump
  ceiling, bisheng linking recipe), `__trap`.
- the index's prototypes match **neither** detail section: both asserts document `assert(expr)` (a macro),
  and `printf-176` is a template, not a C variadic.
→ 950 book. Carried by `950:0385`. Two of the five sections describe an execution unit (AI CPU) outside
this page's stated scope and outside this book's. The page's single header line matches none of the five
sections' own 需要包含的头文件 statements.

## C-950rem-008 · `__trap` ends the thread in the index row and ends the operator in its own section
- `ascendc-simt-api-reference/references/debug-api.md:15` — "立即终止当前线程执行" (current thread).
- same file `:487` — "在SIMT VF实现代码中调用此接口会中断算子的运行" (the operator's run).
- same file `:503` — 约束说明: 无; `:468-476` — this section's 产品支持情况 table is **empty**, uniquely
  among the five sections on the page.
→ 950 book. Carried by `950:0386`. Thread-scoped and operator-scoped termination are different primitives
with opposite usage patterns (a production guard versus a debug abort). Upstream's own worked example is
consistent with both. One run of that example with a single NaN in the input settles it by reading the
extent of unwritten output — and a *warp*-scoped result, which neither sentence offers, is a live third
answer.

## C-950rem-009 · the tiling-validation snippet calls a function the same file never defines
- `ascendc-regbase-best-practice/references/knowledge/patterns/tiling_input_validation.md:53-55` — the
  defined function: `bool CheckDtypeSupport(gert::TilingContext* ctx, int64_t numInputs, const
  std::vector<std::set<ge::DataType>>& supportedDtypesPerInput)` — a **per-input** vector of dtype sets.
- same file `:222` — the copyable calling-convention block invokes
  `CheckDtypeSupportAndCombination(ctx_, (int64_t)rawInputShapes_.size(), SUPPORTED_DTYPES)` against a
  single flat `std::set<ge::DataType>` declared at `:217`. That name is defined nowhere in the file.
→ 950 book. Carried by `950:0362`; the per-input dtype guarantee it weakens is `950:0363`. An agent that
copies the call gets an unresolved name; one that adapts the call to the defined function has silently
dropped the per-input dtype partition, which is what "AndCombination" evidently refers to. Same species as
`C-950arch-007` and `C-950arch-009` — a rule stated in prose and violated in the executable block beside
it; the repair is one generator for both, not a correction to the instance.

## C-950rem-010 · the SIMT macro reference names eight constants that do not exist and omits thirty that do
- `ascendc-simt-api-reference/references/macro-api.md:45-65` — the 数学常数 table names `ASCRT_TWOPI_F`,
  `ASCRT_ONE_OVER_PI_F`, `ASCRT_TWO_OVER_PI_F`, `ASCRT_LN10_F`, `ASCRT_LOG2E_F`, `ASCRT_LOG10E_F`,
  `ASCRT_LN2_HI_F`, `ASCRT_LN2_LO_F` among seventeen rows.
- installed toolkit — `asc/include/simt_api/{math_constants.h,asc_bf16.h,asc_fp16.h}` define **60**
  distinct `ASCRT_*` macros. **None of those eight is defined.** Six have near-twins under a terser scheme
  (`ASCRT_L2E_F`, `ASCRT_LNT_F`, `ASCRT_LGE_F`, `ASCRT_2_OVER_PI_F`, `ASCRT_2OPI_F`, `ASCRT_LG2_F`);
  `ASCRT_LN2_HI_F`/`_LO_F` have none, though the analogous `ASCRT_MINUS_PIO2_HI_F`/`_LO_F` pair exists.
  **Thirty** defined macros appear in no upstream table, including the boundary constants the reference's
  own scope line claims to cover (`ASCRT_TWO_TO_M126_F`, `ASCRT_TWO_TO_{23,24,31,32,126}_F`,
  `ASCRT_NORM_HUGE_F`), `ASCRT_TRIG_PLOSS_F`, `ASCRT_REMQUO_{BITS,MASK}_F`, and six integer bit-pattern
  macros. All 21 **special-value** names match exactly.
- same toolkit — `asc/include/simt_api/asc_fp8.h` ships and defines zero `ASCRT_*` macros; the reference
  declares coverage of three float formats.
→ 950 book. Carried by `950:0388`. The special-value tables were evidently produced against these headers
and the mathematical-constants table was not. Counts are bounds, not measurements: the grep predicate
matches `#define` at line start and would miss a `constexpr` (`math_constants.h:19` uses one) or a macro in
an unenumerated header — so **8 is an upper bound on the absences and 30 a lower bound on the omissions**.

## C-950rem-011 · the MC² window layout sizes the data region by `epWorldSize` and the state region by `rankDim`
- `ascendc-mc2-best-practice/references/moe-dispatch-combine/tiling-scheme/window-memory-layout.md:31` —
  `rankDataBytes = epWorldSize * sourceRankRegionBytes`.
- same file `:83` — `totalStateBytes = localExpertNum * rankDim * STATE_SLOT_BYTES`, and the state address
  formula at `:91` uses `rankDim` as the stride multiplier.
- neither symbol is defined anywhere in the file; the two address formulas at `:38-42` and `:89-92` treat
  them as one rank dimension.
→ 950 book. Carried by `950:0390`; the state-region UB budget that depends on it is `950:0393`. If they are
one quantity the file has a naming defect; if they differ (an expert-parallel world size versus a
communication-domain size) then a kernel using one for both mis-sizes a region. Adjacent blocks, eight lines
apart.

## C-950rem-012 · the combine slot aligns to a constant the layout document never defines
- `ascendc-mc2-best-practice/.../window-memory-layout.md:119` —
  `slotBytes = AlignUp(payloadBytes, winAlignBytes)`. `winAlignBytes` occurs **once** in the file and is
  defined nowhere in it.
- same file `:26` — the dispatch counterpart uses a literal: `payloadBytes = AlignUp(H * sizeof(dtype), 32)
  // 32B 对齐`.
→ 950 book. Carried by `950:0392`. A writer and a reader that pick different values disagree about every
slot after the first, by an amount that accumulates with `slotIdx` and again with `srcTokenIdx`, on the
*return* path where no intermediate check exists. The file's own 下一跳 section (`:195-199`) names two
further documents this harvest did not open, so "undefined here" is not yet "undefined upstream" — that
search is `950:0392` Arm A.

## C-950rem-013 · the combine state slot size is implementation-defined in the prose and fixed at 32 in the code two lines later
- `ascendc-mc2-best-practice/.../window-memory-layout.md:145` — "每个状态槽大小由实现决定，最小为 32B。"
- same file `:150` — `stateStrideBytes      = 32    // 单个状态槽`.
→ 950 book. Carried by `950:0392`. Third instance in this reconstruction of the rule-stated-then-fixed-in-
adjacent-code species (`C-950arch-007`, `C-950rem-009`). An agent reading the prose implements a
configurable stride and must find the value somewhere; one reading the code hardcodes 32 and has made an
implementation choice the prose says is open. Both are following the document.

## C-950rem-014 · the SIMT guide attributes its two central symbol groups to headers that declare neither
- `ascendc-simt-programming-best-practices/references/index-calculation.md:34-38` — "#include
  \"simt_api/common_functions.h\"" given as the header for the four index accessors.
- `ascendc-simt-programming-best-practices/references/multi-core-sync.md:35-39` — "#include
  \"simt_api/device_sync_functions.h\"" given as the header for `AscendC::SyncAll()`.
- installed toolkit — `asc/include/simt_api/common_functions.h` declares `asc_vf_call` and
  `using dim3 = cce::dim3` and none of the four accessors; `asc/include/simt_api/device_sync_functions.h:20-24`
  declares `asc_syncthreads()`, `asc_threadfence()`, `asc_threadfence_block()` and no `SyncAll`. The four
  accessors are in `interface/simt_api/cpp/kernel_simt_common_intf.h`; `SyncAll()` is in
  `basic_api/interface/kernel_operator_block_sync_intf.h:76-84` — neither header is named by either file.
→ 950 book. Carried by `950:0375`. Both named headers carry a **sibling** surface for the same job, which
is the substitution hazard: `asc_syncthreads` is a CUDA-shaped intra-**block** barrier where `SyncAll` is a
block-level **all-core** one, and an agent that includes the documented header and uses what it finds has
replaced a cross-core barrier with an intra-core one. Underlying cause is visible: the toolkit carries two
parallel SIMT surfaces (lower-case at namespace scope under `simt_api/`, CamelCase inside `AscendC::Simt`
under `interface/simt_api/cpp/`) and the guide documents one while citing the other's headers.

## C-950rem-015 · the SIMT UB reservation accessor is spelled two ways nine lines apart
- `ascendc-simt-programming-best-practices/references/data-transfer.md:20` — step 1 of the numbered recipe:
  "**tiling 侧**：设置 `SetLocalMemory` 分配动态 UB".
- same file `:29` — the code block below it: `context->SetLocalMemorySize(ubsize - DCACHE_SIZE);`.
- `ascendc-simt-programming-best-practices/references/intra-core-shared.md:45` — the sibling file uses only
  the second spelling.
- neither name is defined anywhere in this harvest's scope; the tiling-context API was not located in the
  installed toolkit trees read here.
→ 950 book. Carried by `950:0377`. The two names also differ in what their argument plausibly is — a memory
versus a size — and the snippet's own `ubsize - DCACHE_SIZE` shows the argument is a residual, not a total.

## C-950rem-016 · a THIRD upstream location of the 256 KB / 128 KB DCache snippet (extends C-950arch-007)
- `ascendc-simt-programming-best-practices/references/data-transfer.md:27-29` —
  `constexpr uint64_t DCACHE_SIZE = 128 * 1024; uint64_t ubsize = 256 * 1024;
  context->SetLocalMemorySize(ubsize - DCACHE_SIZE);`
- the two already-recorded locations: `npu-arch/references/simt-arch-guide.md:138-142` and
  `ascendc-simt-tiling-design/references/guide.md:63-73` (`C-950arch-007`, carried by `950:0239`).
→ 950 book. Recorded by `950:0377`; the numeric claim itself stays with `950:0239` and is **not**
re-entered. What this third copy adds: it carries **none** of the surrounding rule — no 32 KB minimum, no
216 KB arithmetic, no explanation of either literal — so the copy that reaches a SIMT kernel author through
the programming guide is the one with the least context and is presented as the recipe. Three copies in
three skills is the signature of a copied constant rather than a derived one; the repair is a generator, not
three edits.

---

### Rows checked and NOT opened
- **`Reg::DataCopy` versus `Reg::LoadAlign`** is *not* a contradiction row. The installed toolkit shows both
  names defined in `asc/impl/basic_api/reg_compute/kernel_reg_compute_datacopy_intf_impl.h`, in adjacent
  pairs forwarding to identical `DataCopyImpl<...>` instantiations — so they are one operation under two
  spellings, which is a fact (`950:0351`), not a disagreement. What *is* a disagreement is what the
  whitelist means by omitting one of them (C-950rem-001).
- **`Reg::Divs`** is a one-sided defect, not a conflict: the whitelist lists it in the VF-safe Scalar row and
  it is declared in no reg-compute header (0 hits), while its six row-mates are each declared once. Carried
  by `950:0354`; recorded here so a merge does not lose it. The same entry records **27** header-declared
  names absent from the whitelist's VF-safe tables — an omission, not a contradiction, and a lower bound.
- **The reg-compute architecture gate** (`kernel_reg_compute_intf.h:26-27` admits `__NPU_ARCH__` ∈ {3510,
  5102, 3003, 3113}, three of which have no row in `npu-hardware-params.md`'s 产品映射表) is the same species
  as `C-950arch-001` and is carried by `950:0352` as a boundary rather than opened as a numeric conflict.
  The SIMT interface is gated separately on {3510, 5102} (`kernel_simt_intf.h:30`), and `VF_CALL`'s body on
  `5102 || SPLIT_CORE_VEC || ASCENDC_CPU_DEBUG` (`950:0373`) — three gates, three different value sets.
- **`asc_atomic_*` versus `Simt::Atomic*`** (`950:0379`): two parallel atomic families, one per-dtype at
  namespace scope and one generic inside `AscendC::Simt`. Recorded as a coverage and naming finding, not a
  contradiction — upstream names one and the toolkit ships two, which is an omission until a run shows they
  differ in effect.
- **`SHAPE_DIM` = 8 versus the toolkit's `K_MAX_SHAPE_DIM 8`** (`asc/impl/utils/sys_macros.h:53-55`):
  deliberately **not** equated. A maximum shape rank and a fixed descriptor array width are different
  quantities, and equating them on a coincidence of value is the inference this book refuses. Noted in
  `950:0381` §3 so the next harvester does not quietly assume it.

---

## Method notes owed to the controller (not measurements)

**A re-verification correction against an existing entry, outside this block's write partition.**
`Q-950arch-11`, recorded against `950:0234`, states of the 32-thread warp width and the four warp
schedulers that "Neither has an accessor and neither has an ini field". The first half is **wrong**: the
installed CANN 9.0.0-beta.2 declares `__aicore__ inline int32_t GetWarpSize();` at
`asc/include/interface/simt_api/cpp/kernel_simt_common_intf.h:28`, and
`kernel_simt_warp_level_intf.h:18-51` uses a bare identifier `warpSize` as a default argument to four
shuffle primitives. `950:0234` and `book-950/STANDING_QUESTIONS.md` are outside this block's write
partition and were **not** edited; the correction is recorded here, in `harvest/standing/950-rem.md`
(`Q-950rem-08`), and in this block's final report. What survives of `Q-950arch-11` is that the warp width
has **no ini field and has never been measured** — an accessor is a declaration, not a value.

**A whole undocumented API family, found while checking the above.**
`asc/include/interface/simt_api/cpp/kernel_simt_warp_level_intf.h` declares fourteen warp-level cooperative
primitives — `WarpAllSync`, `WarpAnySync`, `Uni`, `WarpBallotSync`, `WarpActiveMask`, `WarpShflSync`,
`WarpShflUpSync`, `WarpShflDownSync`, `WarpShflXorSync`, `WarpReduceAddSync`, `WarpReduceMaxSync`,
`WarpReduceMinSync`, `ThreadBarrier`, `ThreadFence`. **None appears in any upstream document in this
harvest's scope.** Recorded as `Q-950rem-09`; no entry claims them, because a declaration list is not a
capability and this block had no slot left to establish one properly.

**Enumeration predicates and their known blind spots, stated so the counts can be audited.** Three counts
in this register and in `950:0354`/`950:0388` come from greps, and each has a stated bound rather than a
value: `__simd_callee__ inline <ret> <Name>(` at line start over `reg_compute/*.h` (76 names — misses
impl-header-only symbols such as `Reg::DataCopy`, and any other declaration form); `#define ASCRT_<name>` at
line start over the three named `simt_api/` headers (60 names — misses `constexpr` definitions, of which
`math_constants.h:19` is one, and any unenumerated header). Every derived difference is therefore a bound in
a stated direction, and the entries say which.

**Two pitfalls files in scope were deliberately left uncarded as contradictions.**
`common_traps.md`, `api_misuse.md` and `regbase_vs_membase_confusions.md` are almost entirely symptom→check
diagnostic process and contain no numeric or advisory conflicts with each other or with the rest of the
repo. Three of their traps became entries (`950:0394`, `950:0395`, `950:0396`) on the strength of a
falsifiable discriminator; the rest became claim-cards. Their four sibling files in the same directory
(`precision_guide.md`, `precision_failures.md`, `symptom_to_cause.md`, `index.md`) were **outside this
block's declared scope and were not read** — so this register makes no claim about whether they contain
conflicts.

> 2026-08-24 repair-wave dispositions (audit acceptance-criterion 3): C-950rem-003 is CARRIED by
> entry 950:0374; C-950rem-015 by 950:0377; C-950rem-016 by 950:0377 (which also carries the DCache
> ceiling) extending C-950arch-007. Rows retained; the entry linkage is now explicit both ways.
