```
ID:        0352-the-reg-compute-interface-compiles-for-four-npu-arch-values-and-the-truth-source-lists-one
LABEL:     boundary
LEVEL:     L8 (toolchain & build)
STRATUM:   corroborated — two independent origins: upstream's self-declared chip truth source, whose
           product table enumerates the DAV numbers it recognises, and the INSTALLED CANN
           9.0.0-beta.2 headers on this machine, whose reg-compute entry point is gated on four
           `__NPU_ARCH__` values. Nothing was compiled; no build was routed.
BOARD:     family-claimed(unverified)
           # a preprocessor gate names architecture numbers, not boards. 3510 is the only one of the
           # four that upstream maps to a 950 part, and no board was contacted.
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:13-21 — the 产品映射表, declared the single
           truth source for the chip list, with rows for DAV_1001 / DAV_2002 / DAV_2201 / DAV_3002 /
           DAV_3510 and no row for 5102, 3003 or 3113.
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:34-35
           — "`$ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/` /
           `AscendC::Reg::*` interfaces and support types that are valid call targets inside VF
           functions." — the whitelist names this directory as the authoritative VF-safe root and
           says nothing about any architecture gate on it.
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, aarch64 —
           `include/ascendc/basic_api/interface/reg_compute/kernel_reg_compute_intf.h:26-27`:
             `#if defined(__NPU_ARCH__) && ((__NPU_ARCH__ == 3510) || (__NPU_ARCH__ == 5102) ||`
             `    (__NPU_ARCH__ == 3003) || ((__NPU_ARCH__ == 3113))) || defined(__ASC_NPU_HOST__)`
           guarding every one of the twenty-one `#include`s that constitute the reg-compute surface
           (`:34-53`), closed at `:54`.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read on this machine:
           grep -n "__NPU_ARCH__" $ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/kernel_reg_compute_intf.h
OVERTURN:  a build for a target whose `__NPU_ARCH__` is one of 5102, 3003 or 3113 in which the
           reg-compute surface is NOT available — i.e. the gate is not doing what its text says; or,
           in the other direction, an upstream document that maps any of those three to a chip, which
           would close the gap rather than kill the claim.
```

# 0352 · The reg-compute interface compiles for four `__NPU_ARCH__` values, and the truth source lists one of them

## 1 · Claim
Upstream asserts that `regbase` is a 950-era programming model and, in its declared chip truth source,
enumerates the DAV numbers it recognises: 1001, 2002, 2201, 3002, 3510. Upstream's Regbase whitelist
asserts that `basic_api/interface/reg_compute/` is the authoritative VF-safe call surface, and states
no architecture condition on it. Not established here: nothing was compiled.

Read in the installed CANN 9.0.0-beta.2 toolkit, an independent origin: the single header that
aggregates that surface, `kernel_reg_compute_intf.h`, wraps all twenty-one of its includes in one
preprocessor conditional that admits `__NPU_ARCH__` equal to **3510, 5102, 3003 or 3113**, or the
host-side macro `__ASC_NPU_HOST__`. Three of those four numbers have no row in upstream's product
table.

The inference, stated separately: the register-compute programming model this book routes by
vocabulary is enabled by the toolchain for more than one architecture, and this book can say nothing
about the other three, because no origin in scope maps them to any part. What the gate establishes is
that "regbase implies 3510" is an assumption the toolkit does not make.

## 2 · The wrong branch this removes
Two branches, in opposite directions.

The first is a book-keeping branch that reaches this book's own foundations. `form/CONVENTIONS.md`
routes by mechanism: "`regbase` and `SIMT` are 950-era PROGRAMMING MODELS, not chips — a passage using
that vocabulary lands in book-950 by mechanism even if no chip is named." That rule is a good rule and
this entry does not disturb it, because a routing convention is a filing decision and not a claim
about hardware. What the gate removes is the *next* step an agent takes without thinking: reading
"this file uses `Reg::*`, therefore this fact is a 950 fact". It is not. It is a fact about a
programming model whose header admits four architecture numbers, and 950 membership has to come from
somewhere else — a board token, an ini, a measurement. An entry that silently converts regbase
vocabulary into 950 scope has widened its scope past its evidence, which is the thing Art. 2 exists
to stop.

The second is a build branch with a concrete failure. An agent generating a kernel that calls
`Reg::*` and building it for a target that sets none of the four values gets *nothing from this
header* — no declarations, no error naming the architecture, just unresolved names at the call site.
The diagnostic will say `no member named 'LoadAlign' in namespace 'AscendC::Reg'`, which reads as a
misspelling or a missing include, and an agent will go looking for a header it already included. The
architecture gate is invisible in the message. 0208 records the same shape one layer down — an
unchecked `GetCurNpuArch()` return silently selecting a fallback — and this is the compile-time
version of it: the guard is real, the guard is silent, and the symptom names something else.

The related trap that this entry does **not** claim and that §4 must separate: `__ASC_NPU_HOST__` is
a fourth way in, and it is not an architecture at all. A host-side translation unit gets the whole
reg-compute surface declared regardless of `__NPU_ARCH__`. Whether those declarations are usable
there, or merely present for tiling-side type checking, is not established by reading the guard.

## 3 · Ground / Source
The gate, in full, from `kernel_reg_compute_intf.h:26-54`:

> ```cpp
> #if defined(__NPU_ARCH__) && ((__NPU_ARCH__ == 3510) || (__NPU_ARCH__ == 5102) || (__NPU_ARCH__ == 3003) || \
>     ((__NPU_ARCH__ == 3113))) || defined(__ASC_NPU_HOST__)
>
> #if defined(ASCENDC_CPU_DEBUG) && ASCENDC_CPU_DEBUG == 1
> #include "stub_def.h"
> #endif
>
> #include "kernel_reg_compute_utils.h"
> #include "kernel_reg_compute_maskreg_intf.h"
> …
> #include "kernel_reg_compute_histograms_intf.h"
> #endif
> ```

Three readings worth separating.

The **operator precedence** is not a typo but is worth stating, because it changes what the gate
means: `A && (B) || C` binds as `(A && B) || C`. So `__ASC_NPU_HOST__` alone suffices; it is not
conjoined with `defined(__NPU_ARCH__)`. A host build with no architecture macro at all gets the full
surface.

The **redundant parenthesis** around `((__NPU_ARCH__ == 3113))` is cosmetic and is recorded only
because it is the kind of trace that suggests the list grew by edit rather than by generation — which
bears on whether the list is complete, not on what it currently admits.

The **three unmapped numbers**. `npu-hardware-params.md:13-21` is upstream's 产品映射表 and declares
itself the single truth source for the chip list; its rows are DAV_1001, DAV_2002, DAV_2201, DAV_3002,
DAV_3510. 5102, 3003 and 3113 appear in no row. This is the same species as `C-950arch-001`, where
three installed ini files carry `NpuArch=3505` against a table that has no 3505 row and an upstream
rule that maps it to `arch35` anyway — and it is a *different instance*, because that one was found in
`platform_config/*.ini` and this one is in a compile guard. 0205 carries the ini instance; it is cited
here, not re-entered. Under upstream's own two-digit rule (`archXX` = first two digits of the DAV
number, `npu-arch-guide.md:36-43`), 5102 → arch51, 3003 → arch30, 3113 → arch31 — three architecture
families, none of them arch35, all admitted to the same header.

What no origin in scope supplies: any mapping from 5102, 3003 or 3113 to a part, a generation, or a
release. This entry deliberately does not guess. Note in particular that 2201 — the value upstream
maps to the *other* book's family — is **not** in this gate, so the gate is not simply "every
architecture the toolkit knows".

The whitelist's silence is the other half of the ground. `regbase_api_whitelist.md:34-35` names the
directory as the primary verification source and adds a rule at `:112` — "If the task needs an API
that is not listed here, verify the SDK header family first" — with no hint that the header family
may evaluate to empty. 0245 establishes that the absence rule is the correct procedure; this entry
records the case the procedure does not cover, which is an API that is present in the file and absent
from the translation unit.

`SPLIT_CORE_VEC`, which gates a different SIMT-side body under a partly overlapping condition, is a
separate mechanism and is claimed by 0373, not here.

## 4 · Procedure
Runnable later; Arms A and B need no device.

Arm A — what the gate is worth, by preprocessing only. For each of `__NPU_ARCH__` ∈ {3510, 5102,
3003, 3113, 2201, unset} and separately for `__ASC_NPU_HOST__`, run the compiler's preprocessor over a
one-line file that includes `kernel_reg_compute_intf.h`, and record whether `AscendC::Reg::LoadAlign`
appears in the output. Six preprocessor runs, no code generation, no device. The readout is a table:
architecture value → surface present or absent. This is the cheapest arm in this block and it settles
the guard's literal behaviour.

Arm B — the diagnostic, which is what an agent actually meets. With `__NPU_ARCH__` set to a value not
in the list, compile a translation unit that calls `Reg::LoadAlign` and record the verbatim error
text. §2 predicts a "no member named" message that never mentions the architecture. Recording the
exact string is the deliverable: it is what turns a mystifying build failure into a one-line lookup,
and it is what the delivered skill should carry.

Arm C — the real target's value. On a 950 board, build a trivial kernel with the project's normal
toolchain and print `__NPU_ARCH__` from a `#pragma message` or a `static_assert` that deliberately
fails, and confirm it is 3510. Upstream states this (`0201`, `0203`); it has not been observed here,
and every claim in this block that says "a 3510 build" rests on it.

Arm D — host-side reachability, the reading §2 explicitly refuses to assume. Compile a host-side
tiling translation unit with `__ASC_NPU_HOST__` defined and `__NPU_ARCH__` unset, and record whether
`Reg::LoadAlign` is merely declared or actually callable — i.e. whether taking its address or
instantiating it links. "Declared but not defined" and "usable" are different facts and the guard
distinguishes neither.

Device selection, for Arm C only: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked first (shared machine, ≤4
dies), and no die is substituted.

## 5 · Checker — acceptance declared before the run
`gate_admits` (Arm A) — the set of `__NPU_ARCH__` values for which the surface is present. Pass iff it
equals exactly {3510, 5102, 3003, 3113} plus the `__ASC_NPU_HOST__` case. A *larger* set means some
other header re-includes the surface unguarded, which would make the gate decorative and is the
interesting failure. A *smaller* set means a nested guard inside one of the twenty-one includes
overrides it, which changes where the boundary actually lives.

`unmapped_values_remain_unmapped` — this is not a run. It is a documentation search across the sources
in scope, declared here so it is not quietly skipped: pass iff 5102, 3003 and 3113 are absent from
every upstream file. A hit anywhere closes the gap and demotes this entry from a boundary to a
footnote, which is a good outcome and must be looked for rather than waited for.

`diagnostic_names_architecture` (Arm B) — true iff the compiler's message contains `__NPU_ARCH__`, an
architecture number, or the word `arch`. Predicted **false**. This checker is deliberately built to go
red on the outcome the entry expects, so that a green result is informative: if the toolchain does
name the architecture, the whole §2 branch about a silent guard disappears and the delivered skill needs no
warning at all.

The positive fixture, declared before the run: Arm A must include one run with the guard deliberately
satisfied (`__NPU_ARCH__=3510`) that **must** show `LoadAlign` present. If it does not, the
preprocessor invocation is wrong — a missing include path, a wrong root — and every "absent" result in
the table is an artefact of the harness rather than of the guard. Without that arm the checker reads
only "the symbol was missing in five configurations", which is exactly the shape that a broken include
path also produces, and is the known blind species.

Process exit codes are not the verdict for Arm B: a compile failure is the expected outcome there and
the message body, not the status, is the readout.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No preprocessor was run, no
translation unit compiled, no board contacted, and no `__NPU_ARCH__` value observed on any real target.
The gate text quoted in §3 is a file read on the installed CANN 9.0.0-beta.2 tree under the phase-1
read-only exception.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or preprocessed. The entry does not establish that the guard behaves as its text
reads — a nested condition inside any of the twenty-one included headers could narrow the effective
set, and several of them were not opened. It does not establish that 3510 is what a real 950 build
sets; that is upstream's assertion (0201, 0203) and Arm C is what would confirm it.

It establishes **nothing whatever about 5102, 3003 or 3113**. No origin in scope maps them to a part,
a generation, or a release, and this entry deliberately does not infer one from the digits — upstream's
own `npu-arch-guide.md` warns "不可按数值推断". Anything a later reader wants to know about those three
is unestablished, including whether they are chips at all.

It does not establish that the reg-compute surface is *unavailable* elsewhere. Only one header was
read; another header may declare the same names under different conditions, and `Reg::DataCopy` (0351)
is a live example of a symbol whose declaration and definition sit in different files with different
visibility.

It says nothing about the `__ASC_NPU_HOST__` path beyond that it opens the guard: whether those
declarations link, and whether host-side instantiation is supported at all, is Arm D and is open.

It says nothing about the SIMT surface, which is gated separately and differently
(`kernel_simt_intf.h` admits 3510 and 5102 only) — that gate belongs to 0373 and is not claimed here.

BOARD is `family-claimed(unverified)`: a preprocessor value is not a board token, and no board was
contacted.
