# CARD · ascendc-simt-api-reference 001 — the special-value macro tables are the one part of the reference that matches the headers

**BOOK: 950 — held as a card, and kept deliberately as a POSITIVE result. The 21 special-value macro names
match the installed headers exactly; the mathematical-constants table does not (8 absent, 30 omitted,
`950:0388`, `C-950rem-010`). A card that records what was checked and came back clean is what makes the
adjacent defect attributable.**

## What was checked (re-verified 2026-08-24, and re-derived against the toolkit)
`ascendc-simt-api-reference/references/macro-api.md:9-43` — three tables of seven macros each:

> ## bfloat16 特殊值 (asc_bf16.h)
> | ASCRT_INF_BF16 | 正无穷大 | / | ASCRT_MAX_NORMAL_BF16 | 最大表示值 | / | ASCRT_MIN_DENORM_BF16 | 最小表示值 |
> | ASCRT_NAN_BF16 | NaN | / | ASCRT_NEG_ZERO_BF16 | 负零 | / | ASCRT_ONE_BF16 | 1.0 | / | ASCRT_ZERO_BF16 | 正零 |

and the same seven roles for `half` (`asc_fp16.h`) and `float` (`math_constants.h`).

Installed toolkit — CANN `Version=9.0.0-beta.2`, `innerversion=V100R001C10SPC001B214`,
`timestamp=20260328_213255003`, aarch64. `asc/include/simt_api/asc_bf16.h` defines exactly 7 `ASCRT_*`
macros; `asc_fp16.h` exactly 7; `math_constants.h` 46, of which the 7 float special values are among them.
**All 21 documented names are present, spelled identically, with matching roles.** Two representative
definitions:

> `#define ASCRT_INF_BF16 __ushort_as_bfloat16((unsigned short)0x7F80U)`
> `#define ASCRT_INF_F            __builtin_inff()`

Note the two families use different value forms — the narrow types are bit patterns passed through a
conversion helper, the float ones are builtins or literals — which is consistent and is not a defect.

## Why this is recorded rather than dropped
Three reasons, and the first is the one that matters for the book's method.

**A negative result makes an adjacent positive one attributable.** `950:0388` reports that the same file's
数学常数 table names eight constants that exist nowhere and omits thirty that do. On its own that reads as
"the reference is unreliable". With this card beside it the finding is sharper and more useful: the
special-value tables were evidently produced against these headers and the mathematical-constants table was
not. That is a statement about *which* part of the document to trust, which is what a consuming agent
actually needs, and it is only available because the clean half was checked and written down.

**It is the enumeration's own control.** The grep predicate used for both halves is `#define ASCRT_<name>`
at line start over the three named headers. If that predicate were broken — wrong path, wrong pattern, a
symlink not followed — it would report absences everywhere. It reports 21/21 present in one table and 9/17
in another, from the same run over the same files. So the 21 matches are the positive fixture for the
30 omissions, in the sense RULES.md Art. 5 requires of a checker: an instrument that only ever reports "absent"
has not been shown able to report "present".

**It bounds the defect.** Whatever went wrong with the mathematical-constants table did not affect the
special values, so the failure is localised to one table rather than to the document's provenance as a
whole.

## Why this is a card and not an entry
There is no claim to overturn. "These 21 names exist" is a file read that agrees with a file read; it has
no wrong branch (`§2` would be empty), no procedure beyond the grep already run, and no scope it extends.
Entering it would be trivia, which the template forbids: "If you cannot name the wrong branch, the entry is
trivia and does not enter the book."

The one thing that *would* make it entry-worthy is a **value** check rather than a name check — whether
`ASCRT_MAX_NORMAL_FP16` really is the largest normal half, whether `ASCRT_MIN_DENORM_BF16` is 0x0001 as the
header shows and whether that is the smallest denormal. That is `950:0388` Arm C and it is unrun; if any
value is wrong, this card becomes an entry about a constant that lies.

## Known blind spot in the check
The predicate misses a macro defined through another macro or as a `constexpr`. `math_constants.h:19` uses
exactly that form — `constexpr int ASCRT_NAN_F_VALUE = 0x7fffffffU;` feeding `ASCRT_NAN_F` at `:24` — so the
count of 60 total is a lower bound and the 21/21 match is a name-presence result, not proof that no
special-value macro was missed in either direction.

## What was NOT checked
- **Values.** No macro was expanded, evaluated or compared against a reference. This is names only.
- **`asc_fp8.h`.** It ships and defines **zero** `ASCRT_*` macros, while the reference's scope line
  (`macro-api.md:7`) declares coverage of three float formats. Whether fp8 has constants under another
  prefix is open (`950:0388` §7).
- The other `simt_api/` headers — `math_functions.h`, `vector_functions.h`, `device_functions.h`,
  `device_atomic_functions.h`, `device_warp_functions.h` — none of which this reference documents at all,
  and one of which (`device_warp_functions.h`) corresponds to the fourteen undocumented warp-level
  primitives recorded at `Q-950rem-09`.

## Guessed level
L5 (compute & numerics).

## Evidence class
For upstream's tables: bare — a name and a Chinese gloss, no values, no scope. For this card's own check:
a file read under the phase-1 sanctioned read-only exception, re-derivable by
`grep -hoP '#define \KASCRT_\w+' $ASCEND_HOME_PATH/asc/include/simt_api/{math_constants.h,asc_bf16.h,asc_fp16.h} | sort -u`.

## OVERTURN sketch
A toolkit pin in which any of the 21 names is absent — which would make the special-value tables
version-coupled like the mathematical-constants one, and would remove this card's role as the clean control
for `950:0388`.

## Disposition
Card kept as a recorded clean check. **It is cited by `950:0388` §1 and §3 as the half that matched**, and
it should travel with that entry in any merge: separated from it, the entry reads as a general indictment of
the reference, and the useful finding is that exactly one of its four tables is wrong.
