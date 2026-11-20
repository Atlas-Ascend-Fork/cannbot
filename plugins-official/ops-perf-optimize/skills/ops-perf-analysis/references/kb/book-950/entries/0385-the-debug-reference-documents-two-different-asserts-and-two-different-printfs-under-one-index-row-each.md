```
ID:        0385-the-debug-reference-documents-two-different-asserts-and-two-different-printfs-under-one-index-row-each
LABEL:     trap
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (ops/ascendc-simt-api-reference). The file's index table and
           its detail sections describe different interfaces under the same names. Nothing was
           compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-api-reference/references/debug-api.md:7-15 — the header and index: "头文件:
           `#include \"simt_api/asc_simt.h\"` / SIMT VF函数内使用的调试接口。 / | 函数 | 功能 | 原型 |
           详情 | / | `printf` | 格式化输出(仅VF内) | `void printf(const __gm__ char* fmt, ...)` |
           `debug/printf-176.md` | / | `assert` | 运行时断言检查 | `void assert(bool condition)` |
           `debug/assert-177.md` | / | `__trap` | 立即终止当前线程执行 | `void __trap()` |
           `debug/__trap.md` |"
SOURCE:    same file:24,129,228,347,464 — the five detail sections actually present: `assert-177`,
           `assert-179`, `printf-176`, `printf-178`, `__trap` — i.e. FIVE sections under THREE index
           rows.
SOURCE:    same file:98,102,152,159 — the two asserts differ in every stated respect: `assert-177` is
           "该接口当前仅支持融合编译场景" with header "utils/debug/asc\\_assert.h"; `assert-179` is
           "该接口实现AI CPU算子Kernel调试场景下的assert断言功能" with header "aicpu\\_api.h" and, at
           `:195`, "该接口仅支持通过<<<...\\>\\>\\>调用，并在异构编译场景使用".
SOURCE:    same file:277-279 vs :202 — the two printfs differ in signature and address space:
           SIMT is "template <class... Args> __attribute__((always_inline)) inline __simt_callee__
           void printf(const __gm__ char* fmt, Args&&... args)"; AI CPU is
           "void printf(const char* fmt, ...)" called as `AscendC::printf`, with `:243` "该接口不支持
           打印除换行符之外的其他转义字符" and `:244` a 1 MB per-core Dump ceiling.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an upstream revision that splits the index into per-interface rows, or that scopes each row to
           its execution unit — the conflation would then be closed at the layer an agent reads. A
           compile does not overturn this entry: which interface a given call resolves to is a fact
           about a build, and the defect is that one table describes two.
```

# 0385 · The debug reference documents two different asserts and two different printfs under one index row each

## 1 · Claim
Upstream asserts a three-row index for the SIMT debug interfaces — `printf`, `assert`, `__trap` — under a
single stated header, `simt_api/asc_simt.h`, and a single stated scope, "debug interfaces used inside a
SIMT VF function". Upstream then supplies **five** detail sections under those three rows: two for
`assert` and two for `printf`. Upstream asserts that the two asserts differ in execution unit (SIMT VF
versus AI CPU operator kernel), in header (`utils/debug/asc_assert.h` versus `aicpu_api.h`), in build
scope (fusion compilation only versus heterogeneous compilation invoked through `<<<...>>>`) and in
message format. Upstream asserts that the two printfs differ in signature (a variadic template over
`__gm__ char*` versus a C variadic over plain `char*`), in namespace (unqualified in-VF versus
`AscendC::printf`), and in constraints (a 2 MB GM FIFO versus a 1 MB per-core Dump ceiling and no escape
characters but newline). Not established here: nothing was compiled.

Upstream's index gives each pair one row, one prototype and one 详情 pointer, and the prototypes it gives
match neither detail section exactly.

## 2 · The wrong branch this removes
An index table is a routing artifact. Its job is to answer "what do I call and where does it live" in one
glance, and this one answers with a merged description of two interfaces that share only a name.

**The prototype in the index is a third variant.** The row says `void assert(bool condition)` — a function
taking a bool. `assert-177`'s own 函数原型 section says `assert(expr)`, a macro. Those are not the same
thing and the difference is operationally live: a macro can stringise its argument for the failure message
(which is exactly what 0384's dispute is about), a function cannot; a macro evaluates its argument in the
caller's context, a function's argument is evaluated at the call. Likewise the `printf` row says
`void printf(const __gm__ char* fmt, ...)` — a C variadic — where `printf-176` declares a variadic
*template*. An agent that reasons from the index's prototypes about argument handling reasons about
interfaces that do not exist.

**The header line is scoped to the wrong thing.** `:7` states one header for the whole page:
`simt_api/asc_simt.h`. The detail sections state `utils/debug/asc_assert.h` for the SIMT assert and
`__trap`, `utils/debug/asc_printf.h` for the SIMT printf, and `aicpu_api.h` for both AI CPU siblings. So
the page's own header line matches none of the five sections. This is the same species 0375 records for
the SIMT programming guide — a header attributed at the wrong granularity — reached independently in a
different skill.

**The build-scope constraints do not survive the merge, and they are the expensive part.** `assert-177`
carries 该接口当前仅支持融合编译场景 — fusion compilation only. `assert-179` carries 仅支持通过 `<<<...>>>`
调用，并在异构编译场景使用, plus an explicit bisheng linking recipe
(`--cce-aicpu-laicpu_api`, `--cce-aicpu-L`) that a CMake build is said to handle automatically. Those are
mutually exclusive build configurations. An agent that reads the merged row, picks up `assert`, and builds
in the wrong configuration gets a link failure or a silently absent assertion depending on which way it
missed — and the index gave it no reason to check.

**The AI CPU sections do not belong to the SIMT surface at all.** `:9` scopes the page to "SIMT VF函数内
使用的调试接口"; `assert-179` and `printf-178` are AI CPU operator-kernel interfaces. AI CPU is a
different execution unit from the AI Core the SIMT model runs on. So an agent searching this page for a
SIMT capability may find and adopt an AI CPU interface — plausible, documented, on the same page, under
the same index row — and discover the mismatch at link time if it is lucky and at run time if it is not.

**And the constraint an agent most needs is only on one side.** `printf-178`'s 1 MB per-core Dump ceiling
comes with the explicit consequence 超出则不会打印 — beyond it, nothing is printed. `printf-176`'s 2 MB
FIFO comes with no such statement (0383 §7 records that applying the AI CPU consequence to the SIMT FIFO
is reasoning by analogy). Merging the two rows invites exactly that transfer, in either direction: an
agent may carry the silent-truncation warning to the SIMT interface where it is unverified, or carry the
resizability (`simt_printf_fifo_size`) to the AI CPU one where it is not stated to apply.

## 3 · Ground / Source
The index and its scope, `debug-api.md:5-17`:

> # 调试接口
>
> 头文件: `#include "simt_api/asc_simt.h"`
>
> SIMT VF函数内使用的调试接口。
>
> | 函数 | 功能 | 原型 | 详情 |
> |------|------|------|------|
> | `printf` | 格式化输出(仅VF内) | `void printf(const __gm__ char* fmt, ...)` | `debug/printf-176.md` |
> | `assert` | 运行时断言检查 | `void assert(bool condition)` | `debug/assert-177.md` |
> | `__trap` | 立即终止当前线程执行 | `void __trap()` | `debug/__trap.md` |
>
> **注意**: printf/assert仅用于调试，生产环境应去除。SIMT VF外使用 `AscendC::Simt::printf` 或 `PRINTF`。

The 详情 column points at `printf-176` and `assert-177` — the SIMT ones — so the index is *aware* of the
numbering and simply does not mention that 178 and 179 exist. The note at `:17` adds a third and fourth
spelling (`AscendC::Simt::printf`, `PRINTF`) for use outside a VF, which are the two the installed header
declares (0383 §3).

The five sections and their distinguishing statements are quoted in SOURCE. Two further differences worth
recording:

`assert-179`'s message format, `:36-42`, is a *third* format, different from both of 0384's:

> ```
> int assertFlag = 10;
> // 断言条件
> assert(assertFlag == 12);
> ```
> …
> ```
> [ASSERT]` assertFlag == 12 ' at /home/.../test.cpp:36
> ```

`[ASSERT]` followed immediately by a backtick, spaces inside the quotes, `at` instead of a colon, and the
condition printed **unnegated** — and here the asserted condition is genuinely false (`10 == 12`), so
unlike 0384's first example this one is self-consistent. Three message formats for two interfaces in one
file.

`printf-178`'s constraints, `:243-251`:

> -   该接口不支持打印除换行符之外的其他转义字符。
> -   该接口使用Dump功能，所有使用Dump功能的接口在每个核上Dump的数据总量不可超过1M。请开发者自行控制待打印的
>     内容数据量，超出则不会打印。
> -   使用该接口时，若采用bisheng命令行编译，开发者需要手动链接相关的静态库；而使用CMake编译时，框架会自动
>     处理链接问题，无需开发者额外关注。

with the command line at `:248`:

> ```
> $bisheng -O2 foo.aicpu --cce-aicpu-L${INSTALL_DIR}/lib64/device/lib64 --cce-aicpu-laicpu_api -I${INSTALL_DIR}/include/ascendc/aicpu_api -c -o foo.aicpu.o
> ```

`.aicpu` source extension, an AI CPU library, an AI CPU include root — this section is unambiguously about
a different execution unit, and it sits on a page whose scope line says SIMT VF.

Recorded as `C-950rem-007`. All five sections are one file in `upstream/skills-dev-main` — one origin (RULES.md
Art. 3). The file appears to be a machine-assembled concatenation of vendor documentation topics (each
section retains its `<a name="ZH-CN_TOPIC_...">` anchors and HTML support tables), which explains the
mechanism: the index was written against a topic list and the topics were concatenated without the index
being regenerated. That is an account of how, not evidence of what, and §7 marks it.

## 4 · Procedure
Most of this is documentation work; two arms need a build.

Arm A — which interface a bare call resolves to. In a SIMT VF, with the page's stated header
`simt_api/asc_simt.h` included and nothing else, call `assert(v == 0)` and `printf("%d\n", v)`. Record
whether each resolves and, from the disassembly or the emitted symbol, which of the two documented
interfaces it is. This is the question the merged index makes unanswerable from the page.

Arm B — the build-scope constraints. Build the SIMT assert in a fusion-compilation configuration and in a
non-fusion one; build the AI CPU assert with and without the stated `--cce-aicpu-*` flags. Record for each
whether it compiles, links, and fires. The predicted failure modes differ — a link error for the AI CPU
one, a silently absent assertion for the SIMT one out of fusion scope — and knowing which is which is the
deliverable.

Arm C — the prototype question. Determine from `utils/debug/asc_assert.h` whether the SIMT `assert` is a
macro or a function, and from `utils/debug/asc_printf.h` whether `printf` is a template or a C variadic.
File read, no device; it settles whether the index's prototypes describe anything real.

Arm D — the third message format. Fire the AI CPU assert and record its verbatim output, then fire the SIMT
assert (0384 Arm A) and compare. Three documented formats, two interfaces: the arm establishes how many
formats actually exist.

Arm E — the page's own consistency, as a check that can be re-run. Write a script that extracts every
index row and every detail section from a concatenated reference page and reports rows without sections,
sections without rows, and prototype mismatches between the two. Run it over this file and over the
sibling `overview.md` and `macro-api.md`. A defect that a script finds is a defect that stays found; one
that a reader found once returns with the next regeneration.

Device selection, for Arms A, B and D: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session. A fired assertion fails
the run by design; a non-zero exit is expected.

## 5 · Checker — acceptance declared before the run
`bare_call_resolves_to` (Arm A) — per symbol, three-valued: the SIMT interface, the AI CPU interface, or
unresolved. Reported. Unresolved is a live and informative outcome: it would mean the page's stated header
is insufficient for either, which is 0375's species again.

`scope_failure_mode` (Arm B) — per interface per configuration, four-valued: compiles and fires, compiles
and silently does nothing, fails to link, fails to compile. Reported as a 2×2 table, never summarised. The
"compiles and silently does nothing" cell is the one with no detector and the reason the arm exists.

`index_prototype_is_real` (Arm C) — two booleans: does a function `assert(bool)` exist; does a C-variadic
`printf(const __gm__ char*, ...)` exist. Predicted **false** for both.

`distinct_message_formats` (Arm D) — the count of distinct verbatim formats observed, against three
documented. Reported with the formats themselves.

`index_section_mismatches` (Arm E) — three integers: rows without sections, sections without rows,
prototype mismatches. Reported per file.

The positive fixture, declared before the run: Arm E's script must be given a **synthetic page** in which
one row has no section, one section has no row, and one prototype disagrees — and must find all three. A
script validated only against this file would report three numbers with no evidence it could have reported
different ones; a checker whose only fixture is the document it was written for is the known blind species,
and it is the species this book has recorded against its own instruments. And Arm A must include a control
call to a symbol that certainly resolves from `simt_api/asc_simt.h` (`asc_vf_call`, per 0373 §3); if it
does not, the include is wrong and every "unresolved" result in the arm is an artefact.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was compiled,
no symbol resolved, no assertion fired, no script written, no die contacted. The quoted passages and the
section census are re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish which interface a bare call reaches, whether
either build-scope constraint bites, or whether the index's prototypes correspond to anything — Arms A
through E are all open.

**The concatenation account in §3 is an explanation, not evidence.** That the page looks machine-assembled
from vendor topics (retained anchors, HTML support tables, topic numbering in the section headings) is a
plausible account of how the index came to describe five sections in three rows. Nothing observed
establishes it, and the repair it implies — regenerate the index from the sections — is a recommendation
rather than a finding.

It does not establish anything about the AI CPU execution unit. Two of the five sections describe AI CPU
interfaces; this book's scope is the 950 AI Core surface, and those sections are recorded here only because
they share a page and an index row with SIMT interfaces. Their constraints — the 1 MB Dump ceiling, the
escape-character restriction, the bisheng linking recipe — are upstream's assertions about a unit this
harvest did not examine and must not be carried onto the SIMT interfaces.

It does not resolve the assert message-format question, which is 0384's and which this entry extends only
by observing that a **third** format exists in the AI CPU section — self-consistent there, unlike 0384's
first example.

It does not establish that `simt_api/asc_simt.h` is the wrong header for the page, only that it matches
none of the five sections' own 需要包含的头文件 statements. Whether it transitively includes them is Arm A
and is open — the same question 0375 leaves open for its two headers.

It says nothing about `__trap`, the third index row, which has exactly one section and whose own defect is
a different one (0386).

BOARD is `family-claimed(unverified)`: upstream's per-section 产品支持情况 tables name "Ascend 950PR/Ascend
950DT", which is upstream reproducing a vendor support matrix rather than a measurement, and no board was
contacted.
