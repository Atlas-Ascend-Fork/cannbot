```
ID:        0405-the-reduce-pattern-namespace-declares-sixteen-layouts-and-the-installed-950-backend-static-asserts-every-reduce-op-down-to-two
LABEL:     boundary
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — upstream's skills repo (one origin) plus the installed CANN toolchain
           (independent origin: headers in the installed toolkit, STRATA S2). Nothing measured,
           nothing compiled; corroboration raises priority for verification, not trust.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/reduction/patterns.md:37,128-131 —
           "└─ A0 > 1 → ARA 模式（[R,A0] 块连续，用 Pattern::Reduce::RA）" ·
           "ReduceMax<float, Pattern::Reduce::RA>(resultLocal, xLocal, tmpLocal, srcShape, true);" ;
           :29 — "└─ 多轴（ARAR 等交替序列）→ Shape 三步变换（详见 multi-axis-transform.md）"
SOURCE:    /usr/local/Ascend/cann-9.0.0-beta.2/aarch64-linux/asc/include/adv_api/reduce/
           reduce_common.h:33 — "struct ARAR : private Detail::PatternConstInfo<Detail::PATTERN_ARAR,
           true, false, Detail::DIM_FOUR> {};" (one of 16 pattern structs, :29-45) ; and
           asc/impl/adv_api/detail/reduce/reduce_sum/reduce_sum_c310_impl.h:114-115 —
           "static_assert(std::is_same_v<pattern, Pattern::Reduce::AR> || std::is_same_v<pattern,
           Pattern::Reduce::RA>, / "ReduceSum only support AR and RA pattern on current device!");"
           (installed toolchain, read-only; independent origin of authority)
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read (no device):
           grep -c 'struct [A-Z]* : private Detail::PatternConstInfo' /usr/local/Ascend/cann-9.0.0-beta.2/aarch64-linux/asc/include/adv_api/reduce/reduce_common.h
           grep -Rn 'only support AR and RA pattern' /usr/local/Ascend/cann-9.0.0-beta.2/aarch64-linux/asc/impl/adv_api/detail/reduce/
OVERTURN:  a `Pattern::Reduce::ARAR` (or any non-AR/RA) instantiation of any `Reduce*` advanced API
           that compiles for a DAV_3510 target under this toolkit pin — the static assertions would
           then not be the ones selected for that target, and "declared sixteen, implemented two"
           would be wrong about which implementation the compiler picks. Equally: a later toolkit pin
           whose c310 implementation drops the pattern assertion.
```

# 0405 · The Reduce pattern namespace declares sixteen layouts and the installed 950 backend static-asserts every reduce op down to two

## 1 · Claim
Upstream asserts, in the design shelf's ARA branch, that a non-trailing-axis reduction is expressed by
passing `Pattern::Reduce::RA` to the Level-2 Reduce API, and asserts elsewhere in the same shelf that a
multi-axis alternating shape (`ARAR …`) is handled by a three-step *shape transformation* into nested
loops rather than by passing an alternating pattern. The installed CANN toolchain, at pin
`cann-9.0.0-beta.2`, declares in its public advanced-API header a `Pattern::Reduce` namespace of
**sixteen** pattern structs — `R`, `RA`, `AR`, `ARA`, and then the full alternating ladders `ARAR`,
`ARARA`, `ARARAR`, `ARARARA`, `ARARARAR`, `ARARARARA`, `RAR`, `RARA`, `RARAR`, `RARARA`, `RARARAR`,
`RARARARA` — up to nine dimensions, with a matching sixteen-value host-side `ReducePattern` enum. In
the same toolkit, every `Reduce*` advanced API's DAV_3510 (`c310`) implementation opens with a
`static_assert` restricting the `pattern` template parameter to `AR` or `RA`: `ReduceSum`,
`ReduceMean`, `ReduceMax`, `ReduceMin`, `ReduceProd`, `ReduceAll` and `ReduceAny`, seven for seven.
Not established here that a build for a 950 target selects that implementation, nor that any
alternating pattern fails to compile — nothing was compiled.

## 2 · The wrong branch this removes
The declared API surface reads like a capability. An agent planning a reduction over a shape that
collapses to `ARARA` finds `Pattern::Reduce::ARARA` in the header, finds the host enum row beside it,
finds `\tparam [in] pattern, reduce pattern of input tensor, each character is a dimension` in the
public doc comment — and designs a single-call plan. The plan does not survive the first compile, and
it fails as a `static_assert` message inside an implementation header the agent never opened, which is
the class of error this book records as attributed from the wrong place (`0345`). The wrong branch is
"the pattern exists, therefore the call is available": on this toolkit the declaration and the
implementation are in different files with different scopes, and only the second one is per-architecture.

The second wrong branch is more expensive because it costs design time rather than build time. If the
alternating patterns were usable, the whole apparatus this book carries at `0125`–`0128` — the
interleaved pre-gate, the two continuous-load templates, the two-step chained AR/RA decomposition
inside UB, the 16 KB shared temp — would be unnecessary. An agent that reads the header and concludes
the hardware handles `ARARARAR` natively will regard that machinery as over-engineering and delete it.
The header is what makes that mistake available; the `static_assert` is what makes it wrong; and
nothing in the header points at the `static_assert`.

The third wrong branch is over-reading in the other direction. This entry does **not** say the
alternating patterns are dead code. `PATTERN_ARAR` through `PATTERN_ARARARARA` have integer values, a
`PatternConstInfo` carries per-pattern dimension counts (`DIM_FOUR` … `DIM_NINE`) and two boolean
flags, and the host-side tiling entry point `GetReduceSumMaxMinTmpSize(const ge::Shape&, ge::DataType,
ReducePattern, …)` takes the enum by value rather than by template parameter — so the host side accepts
all sixteen at runtime and nothing in the header prevents a host from sizing a temp buffer for a
pattern the device cannot execute. Whether the host path rejects it, and where, is unknown from
reading; §4 arm 3 is what asks.

The operational content is one sentence: **on this toolkit the reduce pattern space is sixteen at
declaration, sixteen on the host tiling interface, and two in every DAV_3510 device implementation —
so a pattern is a shape descriptor, not a capability, and the only two that reach the hardware are the
two upstream's templates use.**

## 3 · Ground / Source
Upstream's usage, `ascendc-tiling-design/references/reduction/patterns.md:37` and `:127-131`:

```
  └─ A0 > 1 → ARA 模式（[R,A0] 块连续，用 Pattern::Reduce::RA）
```
```cpp
**关键 API 调用**:

uint32_t alignedCols = ((tileA0Len * sizeof(float) + 31) / 32) * 32 / sizeof(float);
uint32_t srcShape[] = {R, alignedCols};
ReduceMax<float, Pattern::Reduce::RA>(resultLocal, xLocal, tmpLocal, srcShape, true);
```

Note what upstream does *not* do at `:29`, where the alternating case arrives:

```
  └─ 多轴（ARAR 等交替序列）→ Shape 三步变换（详见 multi-axis-transform.md）
       展开为嵌套循环，每个 R 维的归约按 Step 2 判定
```

`ARAR` is named as a *shape*, and the response is to transform it away into nested loops each of which
is AR or ARA — never to pass `Pattern::Reduce::ARAR`. The design shelf therefore behaves consistently
with the restriction without ever stating it. The implementation shelf states it, and this book already
carries that statement as an unverified assertion at `0125`, whose §7 records it as "asserted as a
hardware fact with no reference, and it is the load-bearing premise of the two-step decomposition".
This entry is that premise's independent corroboration, with one scope correction (below).

The independent origin. `/usr/local/Ascend/cann-9.0.0-beta.2/aarch64-linux/asc/include/adv_api/reduce/
reduce_common.h:21-47`, in full:

```cpp
namespace AscendC {
namespace Pattern {
namespace Reduce {
/*
 * @brief Reduce pattern
 * R means reduce axis, A means non-reduce axis
 * each A/R represents a dimension
*/
struct R : private Detail::PatternConstInfo<Detail::PATTERN_R, true, false, 1> {};
struct RA : private Detail::PatternConstInfo<Detail::PATTERN_RA, false, true, Detail::DIM_TWO> {};
struct AR : private Detail::PatternConstInfo<Detail::PATTERN_AR, true, false, Detail::DIM_TWO> {};
struct ARA : private Detail::PatternConstInfo<Detail::PATTERN_ARA, true, true, Detail::DIM_THREE> {};
struct ARAR : private Detail::PatternConstInfo<Detail::PATTERN_ARAR, true, false, Detail::DIM_FOUR> {};
struct ARARA : private Detail::PatternConstInfo<Detail::PATTERN_ARARA, true, true, Detail::DIM_FIVE> {};
struct ARARAR : private Detail::PatternConstInfo<Detail::PATTERN_ARARAR, true, false, Detail::DIM_SIX> {};
struct ARARARA : private Detail::PatternConstInfo<Detail::PATTERN_ARARARA, true, true, Detail::DIM_SEVEN> {};
struct ARARARAR : private Detail::PatternConstInfo<Detail::PATTERN_ARARARAR, true, false, Detail::DIM_EIGHT> {};
struct ARARARARA : private Detail::PatternConstInfo<Detail::PATTERN_ARARARARA, true, true, Detail::DIM_NINE> {};
struct RAR : private Detail::PatternConstInfo<Detail::PATTERN_RAR, false, false, Detail::DIM_THREE> {};
struct RARA : private Detail::PatternConstInfo<Detail::PATTERN_RARA, false, true, Detail::DIM_FOUR> {};
struct RARAR : private Detail::PatternConstInfo<Detail::PATTERN_RARAR, false, false, Detail::DIM_FIVE> {};
struct RARARA : private Detail::PatternConstInfo<Detail::PATTERN_RARARA, false, true, Detail::DIM_SIX> {};
struct RARARAR : private Detail::PatternConstInfo<Detail::PATTERN_RARARAR, false, false, Detail::DIM_SEVEN> {};
struct RARARARA : private Detail::PatternConstInfo<Detail::PATTERN_RARARARA, false, true, Detail::DIM_EIGHT> {};
} // namespace Reduce
} // namespace Pattern
} // namespace AscendC
```

Sixteen structs. The host-side mirror, `asc/include/adv_api/reduce/reduce_tiling.h:35-52`, is a
sixteen-value `enum class ReducePattern : uint32_t` listing the same names in the same order, consumed
by `GetReduceSumMaxMinTmpSize(const ge::Shape& srcShape, const ge::DataType dataType, ReducePattern
pattern, …)` at `:82`.

The device side, `asc/impl/adv_api/detail/reduce/reduce_sum/reduce_sum_c310_impl.h:114-115`:

```cpp
    static_assert(std::is_same_v<pattern, Pattern::Reduce::AR> || std::is_same_v<pattern, Pattern::Reduce::RA>,
        "ReduceSum only support AR and RA pattern on current device!");
```

and the same assertion, in the same `_c310_impl.h` family, for six more operations — re-derivable by
the second INDEX grep, which returns exactly these seven lines:

```
reduce_sum/reduce_sum_c310_impl.h:115   "ReduceSum only support AR and RA pattern on current device!"
reduce_mean/reduce_mean_c310_impl.h:44  "ReduceMean only support AR and RA pattern on current device!"
reduce_max/reduce_max_c310_impl.h:133   "ReduceMax only support AR and RA pattern on current device!"
reduce_min/reduce_min_c310_impl.h:133   "ReduceMin only support AR and RA pattern on current device!"
reduce_prod/reduce_prod_c310_impl.h:136 "ReduceProd only support AR and RA pattern on current device!"
reduce_all/reduce_all_c310_impl.h:66    "ReduceAll only support AR and RA pattern on current device!"
reduce_any/reduce_any_c310_impl.h:66    "ReduceAny only support AR and RA pattern on current device!"
```

Seven operations, seven identical restrictions, phrased `on current device` — the toolkit's own words
for "this backend", and the file suffix `_c310_` is what selects it.

**The scope correction, and its Art. 1 fence.** Upstream attributes the restriction to `arch35`
specifically, in a table row contrasting the interleaved pattern against the regular one —
`ascendc-performance-best-practices/reference/reduce/guide.md:119`:

```
| 规约 | 一次 ReduceSum | arch35 `ReduceSum` **只支持 AR/RA 两级**，多维 `ARAR` 编译报错 → 需拆成两步 AR/RA 链式规约 |
```

which reads as a limitation of that generation. The same
toolkit ships a second backend implementation, `reduce_sum_v220_impl.h`, whose `:288-289` carries
`static_assert(SupportType<pattern, Pattern::Reduce::AR, Pattern::Reduce::RA>(), "failed to check the
reduce pattern, it only supports AR/RA pattern!")` — the same two-pattern restriction under a different
spelling. So within this toolkit the restriction is not what distinguishes the DAV_3510 backend from
the other one it ships, and upstream's `arch35` attribution is not supported by the headers as a
*distinguishing* property. **No fact about that other architecture enters this book** (RULES.md Art. 1): the
v220 file is quoted here solely to show that "arch35" is not the discriminator, and this book records
nothing about what any non-950 part does. Registered as `C-950td-007`.

The two origins are genuinely independent — upstream's skills repo and the vendor's installed
toolchain are different origins of authority (STRATA S2) — but two documents can copy one error, and a
header is not a machine. What the header establishes is what a compiler would refuse, not what silicon
can do.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The claim is
about compile-time refusal, so most of it needs **no device at all** — only a toolkit and a compiler
pin — and §5 marks which arms are device-free. That matters: it means the load-bearing half of this
entry is resolvable the moment a build is sanctioned, without touching a die (RULES.md Art. 6 still gates
the timing arm).

**Arm 1 — device-free. The refusal itself.** For each of the seven operations, compile a translation
unit instantiating it at `Pattern::Reduce::AR`, at `Pattern::Reduce::RA`, and at
`Pattern::Reduce::ARAR`, targeting a 950 SoC version, one compiler pin recorded by
`--version` and by the toolkit path from `readlink -f`. Record, per instantiation: exit status, and
the *first* diagnostic line, unclipped. Expected: AR and RA compile; ARAR fails with the recorded
`only support AR and RA pattern on current device!` text. The message text is the verdict, not the exit
status — a build can fail for a hundred reasons and attributing a failure to the wrong one is the
error species this book records at `0345`.

**Arm 2 — device-free. Which implementation was selected.** Repeat one ARAR instantiation with
preprocessed output kept (`-E`) and confirm by file provenance that the `_c310_impl.h` translation
unit is the one in the include set, not `_v220_impl.h`. Without this, arm 1 could be observing the
other backend's assertion and reporting it as the 950 one — which would make the entry's central
attribution wrong while every observation in it stayed true.

**Arm 3 — device-free. The host side.** Call `GetReduceSumMaxMinTmpSize` with `ReducePattern::ARAR` and
a four-dimensional `ge::Shape`, and record what it returns: a size, a zero, an error, or an abort. This
is the gap §2 names — the host enum admits sixteen and the device implements two — and the answer
determines whether a host tiling function can silently size a buffer for a pattern no kernel can use.

**Arm 4 — on-card, and the only arm that needs a die.** For the two patterns that do compile, confirm
they compute correctly and record `aiv_time`, so the entry's "these two reach the hardware" half is a
measurement rather than an inference from a header. `[A1, R] = [4096, 1024]` FP32 for AR and
`[R, A0] = [1024, 256]` FP32 for RA; elementwise comparison against a CPU reference; ≥10 iterations,
first 5 dropped. Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at
20 s spacing; bind only on three idle samples; re-sample after; discard if the die moved.

Refuses to assume: that the installed toolkit at run time is the one read at drafting time (the pin is
re-derived by `readlink -f` and compared against `cann-9.0.0-beta.2`, and a different pin makes this a
new measurement, not a confirmation); that a compile failure is *the* failure (the message text is
required); that the `_c310_` file is the selected one (arm 2 exists for that); that a free die stays
free; that a die may be substituted.

## 5 · Checker — acceptance declared before the run
Verdict `refuses(op)` for each of the seven operations ∈ {`refused_for_pattern`, `refused_other`,
`compiled`}, where the first requires the diagnostic to contain the string `only support AR and RA
pattern`. Declared before the run: this entry is **supported** iff `refuses(op) == refused_for_pattern`
for all seven and arm 2 confirms the `_c310_impl.h` provenance. The OVERTURN fires iff any operation
reports `compiled` at `ARAR` for a 950 target under this pin.

Verdict `host_admits` from arm 3 ∈ {`returns_size`, `returns_error`, `aborts`}. `returns_size` is the
finding that matters operationally — the host would then hand back a buffer size for a kernel that
cannot be built — and it is recorded as a result either way, not as a pass or fail of this entry.

Verdict `ar_ra_correct` from arm 4: true iff both compiled patterns match the CPU reference
elementwise.

The exit code is not the verdict, twice over, and in opposite directions. For arms 1–3 the compiler's
exit status is *expected* to be non-zero on the ARAR instantiations, so a naive "did it build" gate
would read every planted failure as a defect; the verdict is the diagnostic string plus the include
provenance. For arm 4 a reduction returns a plausible float regardless, so the verdict is the
elementwise comparison. Three guards. First, **the input that makes this checker go red**: arm 1
includes the `AR` and `RA` instantiations of all seven operations, which **must** compile. If any of
them fails, the harness is not building anything correctly and every `ARAR` refusal it reports is
uninformative — a compile study whose only outcome is "the thing I expected to fail, failed" has not
been shown able to distinguish a real restriction from a broken include path. Second, the diagnostic is
recorded unclipped and matched by its full text; a truncated log is reported as untestable, because
`refused_other` and `refused_for_pattern` are distinguishable only by the message. Third, the toolkit
pin is echoed with every result, and a run under a pin other than `cann-9.0.0-beta.2` is a separate
measurement recorded as such, never merged with this one.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The sixteen structs, the
sixteen enum values and the seven `static_assert`s are file reads of the installed toolkit performed at
drafting time, re-derivable by the two `grep` commands in INDEX; reading a `static_assert` is not
observing a compile failure, and nothing was compiled. The count "sixteen" is a count of `struct`
declarations in one header, not of patterns the hardware supports.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that any alternating pattern fails to
build for a 950 target — it establishes that the toolkit's `c310` implementations contain assertions
that would refuse them, and §4 arm 2 exists precisely because "the file contains it" and "the compiler
selected that file" are different statements. It does not establish that the restriction reflects a
hardware limit rather than an unimplemented software path; a `static_assert` records what the vendor
chose to implement at this pin, and the OVERTURN's second clause anticipates a later pin relaxing it.
It does not establish anything about any non-950 architecture: the `v220` file is quoted in §3 only to
show that upstream's `arch35` attribution is not a discriminator within this toolkit, and no fact about
that part enters this book (RULES.md Art. 1). It does not establish what the host-side tiling interface does
with a pattern the device cannot execute (arm 3 is unrun, and `returns_size` would be a real hazard
this entry currently only names). It does not establish the per-operation dtype restrictions, which are
a separate finding at `0406`. It does not establish that upstream's three-step multi-axis
transformation (`multi-axis-transform.md`) is correct or necessary, only that it is consistent with the
restriction. It supplies no reduction performance figure and does not compare AR against RA. BOARD is
`family-claimed(unverified)`: the toolkit header names an implementation family (`c310`) and no board
token, and the design shelf's reduction family names no chip at all; §4 names 950PR/950DT only as where
arm 4 would run. Nothing here is established for any 910-family board.
