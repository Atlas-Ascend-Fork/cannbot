```
ID:        0388-the-simt-macro-reference-names-eight-constants-that-do-not-exist-and-omits-thirty-that-do
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — two independent origins: upstream's SIMT macro reference, which tabulates the
           built-in constants, and the INSTALLED CANN 9.0.0-beta.2 headers on this machine, enumerated
           by file read. Nothing was compiled; no macro was expanded by a toolchain.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-api-reference/references/macro-api.md:7 — "涵盖 bfloat16、half、float 三种
           浮点类型的特殊值、数学常数和边界值。" — the reference declares its own coverage as three float
           formats.
SOURCE:    same file:9-43 — three special-value tables of seven macros each (`ASCRT_INF_*`,
           `ASCRT_MAX_NORMAL_*`, `ASCRT_MIN_DENORM_*`, `ASCRT_NAN_*`, `ASCRT_NEG_ZERO_*`, `ASCRT_ONE_*`,
           `ASCRT_ZERO_*` for BF16, FP16 and F), attributed to `asc_bf16.h`, `asc_fp16.h` and
           `math_constants.h`.
SOURCE:    same file:45-65 — the 数学常数 table, seventeen rows: `ASCRT_SQRT_HALF_F`,
           `ASCRT_SQRT_HALF_HI_F`, `ASCRT_SQRT_HALF_LO_F`, `ASCRT_SQRT_TWO_F`, `ASCRT_THIRD_F`,
           `ASCRT_PIO4_F`, `ASCRT_PIO2_F`, `ASCRT_PI_F`, `ASCRT_TWOPI_F`, `ASCRT_ONE_OVER_PI_F`,
           `ASCRT_TWO_OVER_PI_F`, `ASCRT_LN2_F`, `ASCRT_LN10_F`, `ASCRT_LOG2E_F`, `ASCRT_LOG10E_F`,
           `ASCRT_LN2_HI_F`, `ASCRT_LN2_LO_F`.
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, aarch64 —
           `asc/include/simt_api/{math_constants.h,asc_bf16.h,asc_fp16.h}` define **60** distinct
           `ASCRT_*` macros (46 + 7 + 7). Against upstream's 38 documented names:
           **8 documented names are defined nowhere** — `ASCRT_TWOPI_F`, `ASCRT_ONE_OVER_PI_F`,
           `ASCRT_TWO_OVER_PI_F`, `ASCRT_LN10_F`, `ASCRT_LOG2E_F`, `ASCRT_LOG10E_F`, `ASCRT_LN2_HI_F`,
           `ASCRT_LN2_LO_F` — and **30 defined names are undocumented**, including near-twins of six of
           the eight (`ASCRT_2_OVER_PI_F`, `ASCRT_2OPI_F`, `ASCRT_LNT_F`, `ASCRT_L2E_F`, `ASCRT_LGE_F`,
           `ASCRT_LG2_F`, `ASCRT_L2T_F`), plus `ASCRT_TWO_TO_{23,24,31,32,126,M126}_F`,
           `ASCRT_TRIG_PLOSS_F`, `ASCRT_REMQUO_{BITS,MASK}_F`, `ASCRT_MINUS_PIO2_{HI,LO}_F`,
           `ASCRT_3PIO4_F`, `ASCRT_PIO8_F`, `ASCRT_LNPI_F`, `ASCRT_SQRT_2_OVER_PI_F`,
           `ASCRT_NORM_HUGE_F`, `ASCRT_SCALAR_LN2_F`, and six non-float bit-pattern macros
           (`ASCRT_MAN_BIT_FLOAT_U`, `ASCRT_EXP_BIT_FLOAT_U`, `ASCRT_NEG_SIGN_BIT_U`, `ASCRT_INF_U`,
           `ASCRT_MIN_VAL_S`, `ASCRT_INT32_INF_S`). All 21 special-value names match exactly.
SOURCE:    same toolkit — `asc/include/simt_api/asc_fp8.h` exists and defines zero `ASCRT_*` macros; a
           fourth float format ships with no entry in a reference that declares three.
INDEX:     none — nothing measured; see SOURCE. Both diffs are re-derivable by file read:
           grep -hoP '#define \KASCRT_\w+' $ASCEND_HOME_PATH/asc/include/simt_api/{math_constants.h,asc_bf16.h,asc_fp16.h} | sort -u
OVERTURN:  a toolkit pin in which any of the eight documented-but-absent names is defined — the
           mismatch would then be version skew rather than a reference error; or a compile in which one
           of the eight resolves through a header not enumerated here.
```

# 0388 · The SIMT macro reference names eight constants that do not exist and omits thirty that do

## 1 · Claim
Upstream asserts a reference for the SIMT built-in macros covering three float formats — bfloat16, half
and float — with their special values, mathematical constants and boundary values. Upstream tabulates 38
names: three seven-row special-value tables and a seventeen-row mathematical-constants table. Not
established here: nothing was compiled.

Read in the installed CANN 9.0.0-beta.2 headers, an independent origin, by file read: the three named
headers define 60 distinct `ASCRT_*` macros. All 21 special-value names in upstream's three tables match
the headers exactly. Of the seventeen mathematical constants, **eight are defined in none of the three
headers**, and **30 defined macros appear in no upstream table**. A fourth float-format header,
`asc_fp8.h`, ships and defines no `ASCRT_*` macros at all.

The inference, stated separately: the special-value tables were produced against these headers and the
mathematical-constants table was not. Not established here — no other provenance was examined and no other
toolkit pin was read.

## 2 · The wrong branch this removes
A named constant is the safest thing in a numerical kernel, and this table makes eight of them a build
failure and hides thirty that would have been useful.

**The eight absent names fail loudly, and that is the good half.** `ASCRT_LOG2E_F` in a source file is an
unresolved identifier; the agent finds out immediately. The cost is one cycle plus the wrong conclusion
that follows: an agent that finds `ASCRT_LOG2E_F` missing concludes the toolkit has no log₂(e) constant and
writes `1.4426950408889634f` inline. The constant **is** there, as `ASCRT_L2E_F`. So the failure mode is a
hardcoded literal introduced *because* the documentation was wrong, which is precisely the defect class
F4 exists to stop, arriving through a documentation channel rather than a coding one.

**The near-twins make the guess unreliable in a specific direction.** Six of the eight have a defined
counterpart under a different naming scheme: `ASCRT_LOG2E_F` ↔ `ASCRT_L2E_F`, `ASCRT_LN10_F` ↔
`ASCRT_LNT_F`, `ASCRT_LOG10E_F` ↔ `ASCRT_LGE_F`, `ASCRT_TWO_OVER_PI_F` ↔ `ASCRT_2_OVER_PI_F`. An agent
that goes looking will probably find them; an agent that does not will inline a literal. And two of the
eight — `ASCRT_LN2_HI_F` and `ASCRT_LN2_LO_F`, the high and low halves of a double-double ln(2) — have
**no** twin, while the analogous pair for π/2 does exist as `ASCRT_MINUS_PIO2_HI_F` / `_LO_F`. So the
split-constant idiom is real in this toolkit and the specific pair upstream documents is not, which is the
worst case for an agent implementing an argument-reduction: it knows the technique is supported, it has a
documented name for the constants, and the name does not exist.

**The thirty omissions are the larger loss and they fail silently.** They are not miscellaneous. They are
the working set of a serious math library: `ASCRT_TWO_TO_M126_F` (the smallest normal float),
`ASCRT_TWO_TO_{23,24,31,32}_F` (the rounding and integer-range breakpoints), `ASCRT_TRIG_PLOSS_F` (the
argument magnitude past which trigonometric precision is lost), `ASCRT_REMQUO_{BITS,MASK}_F`,
`ASCRT_MINUS_PIO2_{HI,LO}_F`, `ASCRT_3PIO4_F`, `ASCRT_PIO8_F`, and six bit-pattern macros for mantissa,
exponent and sign masks. An agent writing a range reduction, a `frexp`-style decomposition, or a
saturating cast needs exactly these, and the reference it was pointed at says the toolkit's constants are
the seventeen listed. It will reconstruct them by hand — `0x7F800000`, `1.0f / 8388608.0f`, a magic
threshold for `sin` — and every one of those is a literal that nobody can re-derive later.

**The bit-pattern macros are a category the reference does not admit.** `ASCRT_MAN_BIT_FLOAT_U`,
`ASCRT_INF_U`, `ASCRT_MIN_VAL_S`, `ASCRT_INT32_INF_S` are unsigned and signed integer constants, not
floats. The reference's own scope line says it covers three *floating-point* types, so these fall outside
its declared coverage — which is a defensible editorial choice and leaves an agent with no pointer to them
at all. Being out of scope and being absent look identical from the reader's side.

**And `asc_fp8.h` exists.** The reference declares coverage of three formats; the toolkit ships a fourth.
Whether fp8 has special-value constants under some other prefix, or genuinely has none, is unestablished —
but an agent working on an fp8 quantisation path (a live 950 topic, per this book's 0116 and the
quantization paradigm material) will find nothing in the macro reference and cannot tell from the reference
whether that is because none exist.

## 3 · Ground / Source
The scope line, `macro-api.md:7`:

> 涵盖 bfloat16、half、float 三种浮点类型的特殊值、数学常数和边界值。

Three formats, three categories: special values, mathematical constants, boundary values. Note that
"边界值" — boundary values — is declared as covered, and the boundary constants the headers actually carry
(`ASCRT_TWO_TO_M126_F`, `ASCRT_NORM_HUGE_F`, `ASCRT_TWO_TO_126_F`) are among the thirty omissions. So the
table is short of its own declared scope, not merely short of the headers.

The three special-value tables, `:9-43`, each attributed to a header (`asc_bf16.h`, `asc_fp16.h`,
`math_constants.h`), each seven rows: 正无穷大, 最大表示值, 最小表示值, NaN, 负零, 1.0, 正零. All 21 names
match the headers exactly — a clean, correct table, which is why the reference reads as reliable.

The mathematical-constants table, `:45-65`, quoted in SOURCE. Seventeen rows, nine of which resolve.

The enumeration method, stated so it can be checked: the predicate is `#define ASCRT_<name>` at the start
of a line in `asc/include/simt_api/{math_constants.h,asc_bf16.h,asc_fp16.h}` on this machine, where
`$ASCEND_HOME_PATH/asc/include` and `arm64-linux/asc/include` resolve to the same files
(`arm64-linux` is a symlink to `aarch64-linux`). Counts: 46 + 7 + 7 = 60 distinct names. The predicate has
one known blind spot and it bounds the result: a macro defined through another macro, or defined in a
header not in this set, is missed — so **30 is a lower bound on the omissions and 8 an upper bound on the
absences**, since an absent name might be defined elsewhere. `math_constants.h:19` shows the pattern that
makes this non-trivial: `constexpr int ASCRT_NAN_F_VALUE = 0x7fffffffU;` is a `constexpr`, not a `#define`,
and the macro `ASCRT_NAN_F` at `:24` is defined in terms of it. A name defined only as a `constexpr` would
not appear in this enumeration.

Two representative definitions, quoted because they show the value form differs by family:

> `#define ASCRT_INF_F            __builtin_inff()`
> `#define ASCRT_PIO4_F           0.785398163F`
> `#define ASCRT_INF_BF16 __ushort_as_bfloat16((unsigned short)0x7F80U)`

The float constants are literals or builtins; the bf16 and fp16 ones are bit patterns passed through a
conversion function. `ASCRT_PIO4_F`'s `0.785398163F` is nine significant digits — fewer than float's
~7.2 decimal digits require for the nearest representable value to be unambiguous at every bit, which is
worth a check (§4 Arm C) and is not claimed here.

Recorded as `C-950rem-010`. Upstream's file is `upstream/skills-dev-main` — one origin; the toolkit is the
second.

The naming scheme of the eight absent names (`LOG2E`, `TWOPI`, `ONE_OVER_PI`, `LN10`) matches another
vendor's math-constants header convention rather than this toolkit's terse one (`L2E`, `LNT`, `LGE`,
`2OPI`). That is a plausible account of how the table was produced and it is not evidence; §7 marks it.

## 4 · Procedure
Arms A through C are compiles and file reads; none needs a device.

Arm A — resolution, per name. Compile a translation unit that references all 38 documented names and
records which resolve, with only the three documented headers included. Predicted: 30 resolve, 8 do not.
Then repeat with the toolkit's whole `simt_api/` tree included, to catch any of the eight defined in a
header outside the enumerated set — that is the OVERTURN's second clause and the enumeration's known blind
spot.

Arm B — the omissions, enumerated by the compiler rather than by grep. Preprocess a TU including all of
`simt_api/` and dump every `ASCRT_*` macro the preprocessor knows (`-dM`). Compare against the grep-derived
60. Any excess is a name defined through another macro or a `constexpr` and is the correction to §3's
lower bound.

Arm C — the values. For every resolving name, print the value at full precision on the host and compare
against a correctly-rounded reference computed in extended precision. This is the arm that turns "the name
exists" into "the constant is right", and it is where `ASCRT_PIO4_F`'s nine-digit literal gets checked.
An error of even one ULP in a constant used for argument reduction propagates into every transcendental
built on it.

Arm D — the near-twin correspondence. For each of the eight absent names, determine whether the twin
identified in §2 has the same value to the last bit. If it does, the correspondence table is the repair
the delivered skill should carry: documented name → real name. If it does not — for instance if `ASCRT_L2E_F` is a
different rounding of log₂(e) — the twins are not substitutes and the repair is different.

Arm E — fp8. Enumerate `asc_fp8.h` for constants under any prefix and record what a fp8 kernel has
available. The reference declares three formats; establishing whether the fourth has constants at all is
what tells an fp8 author to stop looking.

## 5 · Checker — acceptance declared before the run
`unresolved_documented_names` (Arm A) — the list of documented names that fail to resolve. Pass iff it is
empty; predicted to contain 8. Reported as a list rather than a count, because *which* names fail decides
what an agent must substitute.

`undocumented_defined_names` (Arm A, B) — the list of defined names absent from upstream's tables, with the
preprocessor-derived count beside the grep-derived one. Two counts, reported separately: their difference
measures §3's stated blind spot and is the honest bound on the enumeration.

`value_ulp_error` (Arm C) — per constant, the ULP difference from a correctly-rounded reference. Reported
as a per-name table, never as a maximum or a mean. A single 1-ULP constant in an argument-reduction pair is
a correctness issue and would vanish in any aggregate.

`twin_is_identical` (Arm D) — per pair, true iff the bits match. Reported. A false anywhere means the
substitution table is unsafe and the delivered skill must say so rather than mapping the names.

`fp8_constants` (Arm E) — the list of constants `asc_fp8.h` defines, under any prefix. Reported, possibly
empty; an empty list is a finding, not a null result.

The positive fixture, declared before the run: Arm A must include one name that is **known to resolve**
(`ASCRT_INF_F`, from the special-value table that matches the headers exactly) and one that **cannot**
(`ASCRT_NO_SUCH_CONSTANT_F`). The first must compile and the second must fail. If the first fails, the
include set is wrong and every "unresolved" result in the arm is an artefact; if the second compiles, the
TU is not actually referencing the names and every "resolved" result is an artefact. Both directions are
required — a fixture that only checks the good name cannot distinguish a working probe from one that
accepts everything, and that is the blind species this book keeps recording. A second fixture for Arm C:
the reference computation must be validated against a constant whose exact value is known independently
(`ASCRT_ONE_F` must be exactly 1.0); if it is not, every ULP figure is measured against a broken reference.

Process exit codes are not the verdict for Arm A: the probe compiles each name separately and the failure
list, not the status, is the readout.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was compiled or
preprocessed, no macro expanded by a toolchain, no value printed or compared, no die contacted. The 60-name
enumeration, the two diffs and the existence of `asc_fp8.h` are file reads over the installed CANN
9.0.0-beta.2 tree performed under the phase-1 sanctioned read-only exception; they establish what the
headers contain textually and nothing about what a compiler resolves or what any constant's value is.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that the eight names fail to resolve — a name defined
through another macro, through a `constexpr`, or in a header outside the three enumerated would be missed
by the grep predicate, and `math_constants.h:19`'s `constexpr int ASCRT_NAN_F_VALUE` shows that pattern is
in use. **8 is an upper bound on the absences and 30 a lower bound on the omissions**, and Arms A and B
are what would replace both with compiler-derived numbers.

It establishes **nothing about any constant's value**. Only names were enumerated. Whether the nine
resolving mathematical constants, or the 21 special values, hold correctly-rounded values is Arm C and is
entirely open — `ASCRT_PIO4_F`'s nine-digit literal is noted in §3 as worth checking and is not claimed to
be wrong.

It does not establish that the near-twins are substitutes. §2 pairs six of the eight with defined names on
the strength of what they denote; whether the values match bit-for-bit is Arm D and is unrun. Recommending
a substitution before that arm would be exactly the guess this entry criticises.

It does not establish that the mismatch is a reference error rather than version skew. One toolkit pin was
read; a pin defining `ASCRT_LOG2E_F` would reframe it entirely, and that check against the other installed
CANN trees was not performed.

**The naming-convention account in §3 is not evidence.** That the eight absent names follow another
vendor's convention is a plausible explanation of the table's provenance and is not an observation about
how it was produced.

It says nothing about fp8 beyond the existence of a header with no `ASCRT_*` macros: whether fp8 constants
exist under another prefix, and whether the format is usable without them, is Arm E and is open.

BOARD is `family-claimed(unverified)`: a preprocessor constant is not board-dependent, upstream's file names
no board token this book recognises, and no board was contacted.
