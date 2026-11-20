```
ID:        0387-a-kernel-that-includes-the-system-assert-header-collides-with-the-simt-assert-macro
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (ops/ascendc-simt-api-reference). Upstream states the
           collision and names no symptom; the statement sits in the AI CPU section's constraint list,
           not the SIMT one. Nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-api-reference/references/debug-api.md:196 — "-   kernel开发不要包含系统的
           assert.h，会导致宏定义冲突。"
SOURCE:    same file:195,197 — the two constraints it sits between, both AI-CPU-scoped: "-   该接口仅支持
           通过<<<...\\>\\>\\>调用，并在[异构编译](编译与运行.md)场景使用。" and "-   assert接口调用形式与
           C语言一致，不需要使用AscendC命名空间。"
SOURCE:    same file:68,165 — both `assert` sections give the prototype as the macro form "assert(expr)",
           not as a function; `:102` and `:159` give the two headers, "utils/debug/asc\\_assert.h" for
           the SIMT one and "aicpu\\_api.h" for the AI CPU one.
SOURCE:    same file:14 — the index row nevertheless states the prototype as a FUNCTION:
           "| `assert` | 运行时断言检查 | `void assert(bool condition)` | `debug/assert-177.md` |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 kernel translation unit that includes both `<assert.h>` and the AscendC assert header
           and compiles cleanly with the AscendC assert still firing — the collision would then not
           occur, or would be resolved silently in favour of one of the two, which is the outcome with
           no diagnostic and the one worth knowing about.
```

# 0387 · A kernel that includes the system assert header collides with the SIMT assert macro

## 1 · Claim
Upstream asserts a build rule: kernel development must not include the system `assert.h`, because doing so
causes a macro-definition conflict. Upstream asserts, in the adjacent line, that the assert interface is
called in the same form as C's and needs no `AscendC` namespace qualification. Upstream gives the
prototype for both of its assert sections as the macro form `assert(expr)`, while its index table states a
function signature `void assert(bool condition)`. Not established here: nothing was compiled, upstream
names **no symptom** for the collision, and the statement appears in the constraint list of the AI CPU
section rather than the SIMT one.

## 2 · The wrong branch this removes
The rule is easy to obey once known and nearly impossible to derive, because the two things that make it
necessary are the two things that make it invisible.

**It is called `assert` and used like C's.** `:197` says so explicitly: 调用形式与C语言一致，不需要使用
AscendC命名空间 — same call form as C, no namespace needed. So the interface is *designed* to look like
the standard one. An agent that writes `assert(x > 0)` and gets an unresolved name does the C thing:
`#include <assert.h>`. That single line is the violation, and it is the most reflexive repair in the
language.

**`assert.h` arrives without being asked for.** It is included transitively by many standard and
third-party headers. So a translation unit can violate the rule without containing the include at all,
which means the rule cannot be enforced by reading the file an agent wrote — only by preprocessing the
whole translation unit. A rule that a source-level review cannot check is a rule that will be violated.

**The symptom is unstated, and the plausible symptoms differ sharply.** 宏定义冲突 — macro-definition
conflict — is what the C preprocessor produces when a macro is redefined incompatibly, and the standard
`assert.h` is explicitly permitted to redefine `assert` on every inclusion depending on `NDEBUG`. Three
outcomes are consistent with the phrase and they need opposite responses:

- a redefinition **warning or error**, which is loud and costs one cycle;
- the system macro **wins silently**, in which case `assert(x)` in device code expands to the host
  implementation — which calls `__assert_fail` or similar and will not link, or worse, links against
  something that does nothing on device. The assertion is then present in the source and absent from the
  binary: the check an agent added to catch a fault is not there, and its silence is read as evidence the
  fault does not occur;
- the AscendC macro **wins silently**, in which case any host-side code in the same translation unit that
  expected C semantics gets device semantics.

The second is the one that produces false confidence, and it is exactly the shape this book records
elsewhere: an instrument that cannot go red, trusted because it did not.

**And `NDEBUG` compounds it.** The standard `assert` is defined to expand to nothing when `NDEBUG` is
defined — which release builds routinely define. If the system macro wins, every assertion in the kernel
silently vanishes in the build configuration where a fault is most likely to matter, and nothing in
upstream's rule mentions `NDEBUG` at all.

**The rule is filed in the wrong place.** `:196` sits between two constraints that are unambiguously AI
CPU (`<<<...>>>` invocation, heterogeneous compilation) in the `assert-179` section. The SIMT section
(`assert-177`) has its own constraint list — one line: 该接口当前仅支持融合编译场景 — and does not mention
`assert.h`. So the rule an agent building a *SIMT* kernel most needs is stated only in the section for a
different execution unit, on a page whose index merges the two (0385). Whether the rule applies to the
SIMT macro at all is therefore not established by its own placement, and §4 Arm A is what would say.

## 3 · Ground / Source
The rule and its neighbours, `debug-api.md:194-197`, the `assert-179` constraint list in full:

> ## 约束说明<a name="section43265506459"></a>
>
> -   该接口仅支持通过<<<...\>\>\>调用，并在[异构编译](编译与运行.md)场景使用。
> -   kernel开发不要包含系统的assert.h，会导致宏定义冲突。
> -   assert接口调用形式与C语言一致，不需要使用AscendC命名空间。

The first and third bullets bracket the second, and the first is AI CPU only. The third is the one that
makes the second necessary: an interface deliberately spelled like C's, in a language where the C one is a
macro.

The SIMT section's constraint list, `:96-98`, for contrast:

> ## 约束说明<a name="section43265506459"></a>
>
> 该接口当前仅支持融合编译场景。

One line, no mention of `assert.h`.

The prototype question, which is what makes the collision possible at all. Both detail sections give
`assert(expr)` — `:66-69` and `:162-166`:

> ## 函数原型
>
> ```
> assert(expr)
> ```

A parenthesised expression with no return type and no parameter type is how documentation writes a macro.
The index at `:14` gives `void assert(bool condition)` — a function. A function named `assert` would not
collide with a macro named `assert` in the preprocessor sense; it would be *replaced* by it, which is
worse and quieter. So the index's prototype and the collision warning are inconsistent, and the detail
sections' macro form is the one that makes the warning coherent. 0385 carries the index-versus-section
prototype mismatch; this entry uses it only to establish that the interface is a macro.

The headers, `:102` and `:159`: `utils/debug/asc_assert.h` for the SIMT assert (and for `__trap`, 0386),
`aicpu_api.h` for the AI CPU one. Both exist in the installed toolkit at the stated paths — a file-read
observation recorded in 0383 §SOURCE for `asc_printf.h`'s sibling and confirmed here for `asc_assert.h`.
Nothing in either header was read for a macro definition; that is Arm D.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Every arm is a compile; no device is needed except for the firing check.

Arm A — scope. Determine whether the rule applies to the SIMT assert at all: compile a SIMT kernel
including `utils/debug/asc_assert.h` and `<assert.h>` in both orders, and record diagnostics. If there is
no collision, the rule is AI-CPU-specific and its placement is correct; if there is, the rule is
misfiled and belongs in the SIMT section too. This is the arm the entry exists for, because the placement
makes the question live.

Arm B — the symptom, per order. Four builds: AscendC header first then `<assert.h>`; the reverse; with
`NDEBUG` defined; without. For each, record the diagnostic (if any) and **which macro is in effect** —
determined by `#pragma message` on the expansion of `assert(0)` rather than by reading the source. The
which-wins fact is the deliverable; the diagnostic is secondary.

Arm C — the silent-vanish case. For whichever configuration leaves the system macro in effect with
`NDEBUG` defined, build a kernel with a deliberately false assertion, run it, and confirm whether it fires.
§2 predicts it does not. An assertion present in source and absent in the binary, with no diagnostic, is
the outcome that justifies the rule and it must be observed rather than assumed.

Arm D — the definitions, read. Locate the `assert` macro definition in
`$ASCEND_HOME_PATH/asc/include/utils/debug/asc_assert.h` and record whether it is guarded (`#ifndef
assert`, `#undef assert`), whether it respects `NDEBUG`, and whether it stringises its argument or its
negation — the last also bears on 0384. File read, no device, and it may predict Arms A through C before
they run.

Arm E — transitive inclusion, which is what makes the rule unenforceable by review. Preprocess a realistic
kernel translation unit (project prologue plus `kernel_operator.h` plus the SIMT interface) and record
whether `assert.h` is reached without being written. If it is, the rule as stated is already violated by
the standard include set and the finding is much larger than a coding guideline.

Device selection, for Arm C only: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and both builds run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`simt_collision_occurs` (Arm A) — true iff including `<assert.h>` with the SIMT assert header produces a
diagnostic or changes which macro is in effect. Reported, not gated: the rule's placement makes both
answers findings, and a false result means the rule is correctly scoped to AI CPU and should not be
generalised.

`effective_macro` (Arm B) — per configuration, which definition `assert(0)` expands to. Four values, one
per build, reported as a table. Never summarised into "there was a conflict": the whole content is *which*
one wins, and in which order, and under `NDEBUG`.

`assertion_vanishes` (Arm C) — true iff a deliberately false assertion does not fire. Pass condition
**false**; a true result is the silent failure the rule exists to prevent and is the entry's most
consequential possible observation.

`macro_is_guarded` (Arm D) — three fields from the header: guard present, `NDEBUG` respected, argument
stringised or negated. Reported.

`assert_h_reached_transitively` (Arm E) — true iff `assert.h` appears in the preprocessed include tree of a
realistic kernel TU without being written by the author. Reported.

The positive fixture, declared before the run: Arm C must include a control build in a configuration where
the AscendC macro is known (from Arm B) to be in effect, whose deliberately false assertion **must** fire.
If it does not, the assertion never fires in any configuration — plausibly because the build is not in
fusion scope (`assert-177`'s stated constraint), or because the launch is a silent no-op (0373) — and
"the assertion vanished" in the test configuration is a statement about the harness, not about the macro
collision. A checker that can only observe an absent assertion cannot distinguish a suppressed macro from
a kernel that never ran, and that is the known blind species in its purest form here. A second fixture for
Arm B: one build must be shown to produce a *known* diagnostic (redefine an unrelated macro incompatibly)
so that "no diagnostic" is distinguishable from "diagnostics are being swallowed".

Process exit codes are not the verdict for any arm: Arm C's informative outcome is a process that exits
zero having skipped a check.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was compiled or
preprocessed, no macro expansion inspected, no assertion fired, no header definition read, no die
contacted. The quoted passages are re-verified file reads of the upstream tree performed during this
harvest; that `utils/debug/asc_assert.h` exists at the documented path in the installed CANN 9.0.0-beta.2
tree is a file read under the phase-1 read-only exception and establishes only that the file is there.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that a collision occurs, what its symptom is, which
macro wins, or whether an assertion can silently vanish — Arms A through E are all open, and upstream
states the rule with **no symptom at all**.

**It does not establish that the rule applies to the SIMT assert.** The statement sits in the AI CPU
section's constraint list, between two constraints that are unambiguously AI-CPU-scoped, and the SIMT
section's own constraint list does not mention `assert.h`. Whether the SIMT macro collides is Arm A and is
open; treating an AI CPU constraint as a SIMT one would be exactly the scope error this book's form exists
to prevent, and it is recorded here rather than resolved.

**The `NDEBUG` argument in §2 is reasoning about the C standard, not about this toolkit.** That the
standard `assert` expands to nothing under `NDEBUG` is a property of C; whether the AscendC macro respects
`NDEBUG`, whether it guards against redefinition, and whether release builds define it here are all
unread. Arm D is a file read that would answer the first two cheaply and has not been done.

It does not establish whether the interface is a macro or a function. The two detail sections say
`assert(expr)`; the index says `void assert(bool condition)`; 0385 carries that mismatch. The collision
warning is only coherent under the macro reading, which is why §3 prefers it — that is an argument from
coherence, not an observation.

It says nothing about `__trap`, which ships in the same header (0386), nor about whether including
`<assert.h>` affects it.

It says nothing about the AI CPU interface's other constraints — the `<<<...>>>` invocation form, the
heterogeneous-compilation requirement, and the bisheng linking recipe — which belong to an execution unit
this harvest did not examine (0385 §7).

BOARD is `family-claimed(unverified)`: preprocessor behaviour is not board-dependent, and no board was
contacted.
