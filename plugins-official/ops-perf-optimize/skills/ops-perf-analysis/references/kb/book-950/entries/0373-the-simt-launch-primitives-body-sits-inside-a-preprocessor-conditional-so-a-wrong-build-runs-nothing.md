```
ID:        0373-the-simt-launch-primitives-body-sits-inside-a-preprocessor-conditional-so-a-wrong-build-runs-nothing
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   corroborated — two independent origins: upstream's SIMT programming guide, which documents
           `VF_CALL` as the launch primitive and states no condition on it, and the INSTALLED CANN
           9.0.0-beta.2 headers on this machine, in which the primitive's entire body sits inside a
           preprocessor conditional. Nothing was compiled and no VF was launched.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-programming-best-practices/references/vf-call.md:5-11 — "## 调用语法 /
           ```cpp / AscendC::Simt::VF_CALL<VFFunction>(AscendC::Simt::Dim3(thread_num), args...); / ```
           / - `VFFunction`：要启动的 SIMT VF 函数（带模板参数） / - `Dim3(thread_num)`：启动线程数，
           必须是编译期常量 / - `args...`：传递给 VF 函数的参数" — no build condition is stated anywhere
           in the file.
SOURCE:    ops/ascendc-simt-programming-best-practices/SKILL.md:36-37 — the 核心编程范式速查 shows
           "`AscendC::Simt::VF_CALL<OpSimt<T>>(AscendC::Simt::Dim3(512), count, (__gm__ T*)x,
           (__gm__ T*)y);`" as the canonical launch, again unconditioned.
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, aarch64 —
           `asc/include/interface/simt_api/cpp/kernel_simt_utils.h:18-33`:
             `namespace AscendC { namespace Simt {`
             `using Dim3 = cce::dim3;`
             `template <auto funcPtr, typename... Args>`
             `__aicore__ inline void VF_CALL(Dim3 threadNums, Args &&...args)`
             `{`
             `#if (defined(__NPU_ARCH__) && __NPU_ARCH__ == 5102) || defined(SPLIT_CORE_VEC) || defined(ASCENDC_CPU_DEBUG)`
             `    cce::async_invoke<funcPtr>(threadNums, args...);`
             `#endif`
             `}`
           The function body is empty unless one of the three conditions holds.
SOURCE:    same toolkit — `asc/impl/utils/sys_macros.h:61-63`:
           `#if (defined(__DAV_VEC__) && (__NPU_ARCH__ == 2201 || __NPU_ARCH__ == 3510))` /
           `#define SPLIT_CORE_VEC` / `#endif` — so on a 3510 target `SPLIT_CORE_VEC` is defined only
           when `__DAV_VEC__` is also defined, i.e. for the vector-core half of a split-core build.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read on this machine:
           grep -n -A4 "inline void VF_CALL" $ASCEND_HOME_PATH/asc/include/interface/simt_api/cpp/kernel_simt_utils.h
           grep -n -B1 -A2 "define SPLIT_CORE_VEC" $ASCEND_HOME_PATH/asc/impl/utils/sys_macros.h
OVERTURN:  a 3510 build in which `VF_CALL` launches the VF with none of `__NPU_ARCH__ == 5102`,
           `SPLIT_CORE_VEC` or `ASCENDC_CPU_DEBUG` defined — some other mechanism would then be
           dispatching the VF and the empty body would be dead code rather than a live silent no-op.
           Equally overturning: a build in which the omitted launch produces a diagnostic.
```

# 0373 · The SIMT launch primitive's body sits inside a preprocessor conditional, so a wrong build runs nothing

## 1 · Claim
Upstream asserts that a SIMT vector function is launched by
`AscendC::Simt::VF_CALL<VFFunction>(AscendC::Simt::Dim3(thread_num), args...)`, that the thread count must
be a compile-time constant, and that the remaining arguments are forwarded. Upstream states this in a
reference file and again in its skill's canonical pattern block, and states **no build condition** on the
call in either place. Not established here: nothing was compiled.

Read in the installed CANN 9.0.0-beta.2 headers, an independent origin, by file read: `VF_CALL` is defined
in `kernel_simt_utils.h` with its **entire body inside a preprocessor conditional** admitting
`__NPU_ARCH__ == 5102`, or a defined `SPLIT_CORE_VEC`, or a defined `ASCENDC_CPU_DEBUG`. When none holds,
the function compiles to an empty body. `SPLIT_CORE_VEC` is defined in `sys_macros.h` only when
`__DAV_VEC__` is defined together with `__NPU_ARCH__` being 2201 or 3510.

The inference, stated separately from the two readings above: on a 3510 target that is not a
`__DAV_VEC__` build and not a CPU-debug build, a `VF_CALL` written exactly as upstream documents it
compiles, links, runs, and launches nothing. Not established here — that inference is what §4 Arm A exists
to test, and it is a reading of a preprocessor conditional, not an observation of a build.

## 2 · The wrong branch this removes
Every other failure in this block announces itself. This one does not, and the reason is structural: the
silence is *inside the function that was supposed to do the work*.

Consider the sequence an agent actually follows. It writes the VF, marks it `__simt_vf__`, gives it a
`LAUNCH_BOUND`, writes the grid-stride loop, and calls `VF_CALL` with `Dim3(512)`. Everything compiles —
`VF_CALL` is declared, its signature matches, its template argument resolves. Everything links: an empty
function links fine. It runs: an empty function runs fast. And the output buffer contains whatever it
contained before the kernel — zeros, if the framework zeroed it, or the input, or garbage.

Now the diagnosis. The agent's hypothesis space is: my index arithmetic is wrong; my grid-stride loop
never executes; my pointer cast is wrong; my tiling gave me zero elements. All four are plausible, all
four are checkable, and all four are wrong. The one hypothesis that is correct — *the launch primitive is
a no-op in this build configuration* — is not reachable from the source, because the source is correct.
It is reachable only by opening a vendor header and reading a preprocessor conditional, which is not
where anyone looks when their arithmetic seems off.

The failure is worse than an unresolved symbol in exactly the way a silent wrong answer is always worse
than a loud one: an unresolved `VF_CALL` would name the problem in one line.

**Why a build might miss the condition.** `SPLIT_CORE_VEC` is not defined by the SIMT headers. It is
defined in `sys_macros.h` under `__DAV_VEC__`, which is a *split-core build* selector — the vector-core
half of a build that compiles cube and vector sides separately (`sys_macros.h:57-63` defines
`SPLIT_CORE_CUBE` symmetrically under `__DAV_CUBE__`). So whether `VF_CALL` has a body depends on which
core-side compilation unit is being produced, and that is a build-system decision several layers away
from the kernel author. A mixed-core (`MIX`) build sets neither macro — `sys_macros.h:72-78` selects
`g_coreType = AscendC::MIX` in exactly that case — and on such a build `VF_CALL` is empty.

**The two-header trap.** There are two spellings of the same launch primitive in this toolkit, and they
carry the same conditional but live in different headers with different companions.
`simt_api/common_functions.h:24-38` defines `asc_vf_call` — lowercase, taking `dim3` — and, crucially,
**defines `SPLIT_CORE_VEC` itself** at `:24-26` before using it. `simt_api/cpp/kernel_simt_utils.h`
defines `VF_CALL` — the spelling upstream documents — and does **not** define `SPLIT_CORE_VEC`; it relies
on whatever defined it earlier. So the same conditional is self-satisfying in one header and
inherited in the other, and which one a translation unit gets depends on its include order. An agent that
includes `simt_api/asc_simt.h` and one that includes `kernel_operator.h` plus the SIMT interface may not
get the same answer, and nothing in either header says so.

**What this entry does not claim.** It does not claim that ordinary 950 SIMT builds are broken. The
conditional plainly exists to make `VF_CALL` a no-op on the core side that must not launch it, which is a
sensible design. The claim is that the *documentation states no condition*, the *failure is silent*, and
the condition depends on a macro no upstream document mentions.

## 3 · Ground / Source
Upstream's two statements are quoted in SOURCE. Neither `vf-call.md` (50 lines, read in full) nor
`SKILL.md` (73 lines, read in full) contains the tokens `SPLIT_CORE_VEC`, `__DAV_VEC__`, `__NPU_ARCH__`,
or any statement about which build configurations support `VF_CALL`. The only condition either states is
on the *argument*: "`Dim3(thread_num)`：启动线程数，必须是编译期常量" (0232 carries the compile-time-constant
claim and the 2048 cap; not re-entered here).

The header, `kernel_simt_utils.h:18-33`, in full:

> ```cpp
> namespace AscendC {
> namespace Simt {
> using Dim3 = cce::dim3;
> template <auto funcPtr, typename... Args>
> __aicore__ inline void VF_CALL(Dim3 threadNums, Args &&...args)
> {
> #if (defined(__NPU_ARCH__) && __NPU_ARCH__ == 5102) || defined(SPLIT_CORE_VEC) || defined(ASCENDC_CPU_DEBUG)
>     cce::async_invoke<funcPtr>(threadNums, args...);
> #endif
> }
> }  // namespace Simt
> }  // namespace AscendC
> ```

Note the arch value that appears literally: **5102**, not 3510. The one architecture number written into
the condition is not the one this book's family carries, and 3510 reaches the body only through
`SPLIT_CORE_VEC`. 0352 records that the reg-compute interface admits 3510, 5102, 3003 and 3113 and that
upstream's product table lists none of the last three; this is the same unexplained value appearing in a
second gate, and this entry does not infer what it is.

The macro's definition, `sys_macros.h:57-63`:

> ```cpp
> #if (defined(__DAV_CUBE__) && (__NPU_ARCH__ == 2201 || __NPU_ARCH__ == 3510))
> #define SPLIT_CORE_CUBE
> #endif
>
> #if (defined(__DAV_VEC__) && (__NPU_ARCH__ == 2201 || __NPU_ARCH__ == 3510))
> #define SPLIT_CORE_VEC
> #endif
> ```

and its consequence for core type, `:72-78`: `SPLIT_CORE_CUBE` → `g_coreType = AIC`; `SPLIT_CORE_VEC` →
`AIV`; neither → `MIX`. So "`VF_CALL` has a body" and "this translation unit is the AIV side of a
split-core build" are the same condition on a 3510 target.

The sibling spelling, `simt_api/common_functions.h:19-38`:

> ```cpp
> #ifndef SPLIT_CORE_VEC
> #if (defined(__DAV_VEC__) && (__NPU_ARCH__ == 2201 || __NPU_ARCH__ == 3510))
> #define SPLIT_CORE_VEC
> #endif
> #endif
> #if (__NPU_ARCH__ == 3510) || (__NPU_ARCH__ == 5102)
> #ifndef __NPU_COMPILER_INTERNAL_PURE_SIMT__
> using dim3 = cce::dim3;
> template <auto funcPtr, typename... Args>
> __aicore__ inline void asc_vf_call(dim3 threadNums, Args &&...args)
> {
> #if (defined(__NPU_ARCH__) && __NPU_ARCH__ == 5102) || defined(SPLIT_CORE_VEC) || defined(ASCENDC_CPU_DEBUG)
>     cce::async_invoke<funcPtr>(threadNums, args...);
> #endif
> }
> #endif
> #endif
> ```

Two differences from the `VF_CALL` version matter. This one is at namespace scope, not inside
`AscendC::Simt`. And it re-derives `SPLIT_CORE_VEC` before testing it, so it is self-contained where
`VF_CALL` is not. The vendor's own SIMT `printf` documentation uses this spelling — `debug-api.md:138`'s
example comment reads "// asc\_vf\_call调用时dim3参数：dim3(8, 2, 8)" — so the vendor documentation and
the upstream skill document different spellings of the same primitive. That is 0375's claim; here it
matters only because the two spellings differ in whether they guarantee their own condition.

`kernel_simt_intf.h:30-41` gates the whole SIMT interface on `(__NPU_ARCH__ == 3510) || (__NPU_ARCH__ ==
5102)` and includes `kernel_simt_common_intf.h` (which includes `kernel_simt_utils.h`) but does **not**
include `simt_api/common_functions.h`. So a translation unit reaching `VF_CALL` through
`kernel_simt_intf.h` gets the inherited-condition version, and whether `SPLIT_CORE_VEC` is defined by then
depends on `sys_macros.h` having been reached with `__DAV_VEC__` set.

## 4 · Procedure
Arms A and B are preprocessor and compile work and need no device. Arm C needs one.

Arm A — the conditional, evaluated. For each configuration in the cross product {`__NPU_ARCH__` = 3510,
5102, unset} × {`__DAV_VEC__` defined, undefined} × {`ASCENDC_CPU_DEBUG` defined, undefined}, run the
compiler's preprocessor over a translation unit that includes the project's normal SIMT prologue and calls
`VF_CALL`, and record whether `cce::async_invoke` survives into the output. Twelve preprocessor runs, no
code generation, no device. The readout is the table of which configurations have a body.

Arm B — the include-order question. Repeat the 3510 / no-`__DAV_VEC__` / no-debug configuration twice:
once including `simt_api/asc_simt.h` first, once including `kernel_operator.h` first. If the two differ,
include order decides whether the launch happens, and that is a fact no document states and no reviewer
can see.

Arm C — the silent no-op, observed. On a 950 board, build one trivial SIMT operator (`y[i] = x[i] + 1`)
twice: in a configuration Arm A shows has a body, and in one Arm A shows does not. Poison the output
buffer before each run. Record: exit status, any diagnostic, and whether the poison survives. §2 predicts
a clean exit, no diagnostic, and intact poison in the second. **The poison is the whole experiment** —
without it, "the output was wrong" cannot be distinguished from "the output was never written".

Arm D — the diagnostic search. For the empty-body configuration, capture the full build log at maximum
verbosity and search for any mention of the SIMT VF, `async_invoke`, or an empty function body. Predicted:
nothing. If a warning exists, the entire trap is a documentation problem rather than a silent one, and
the delivered skill should point at the warning.

Arm E — the two spellings, compared. In the empty-body configuration, call `asc_vf_call` instead of
`VF_CALL` and repeat Arm C. Since `common_functions.h` re-derives `SPLIT_CORE_VEC` itself, the two may
differ — and if they do, an agent can be told "use this spelling and the condition cannot be missed",
which is an actionable result rather than a warning.

Device selection, for Arms C and E: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and both configurations run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`body_present_config_set` (Arm A) — the set of the twelve configurations in which `async_invoke` survives
preprocessing. Pass iff it equals exactly {5102 (any), `__DAV_VEC__` with 3510 or 2201,
`ASCENDC_CPU_DEBUG` (any)}. A larger set means something else defines `SPLIT_CORE_VEC` and the gate is
narrower in text than in effect; a smaller set means a nested condition overrides it.

`include_order_matters` (Arm B) — true iff the two include orders differ in Arm A's predicate for the
same configuration. Reported, not gated. Both answers are useful and neither is upstream's claim.

`launch_is_silent` (Arm C) — true iff the empty-body build exits zero, emits no diagnostic, **and** leaves
the poison intact. Three clauses, all required. A build that exits zero with a *changed* buffer is a
different and less alarming finding, and one merged "it did not work" verdict would erase which.

`log_warns` (Arm D) — true iff any build line names the VF, `async_invoke`, or an empty body. Predicted
**false**; a true result removes the trap and is the better outcome.

`spellings_differ` (Arm E) — true iff `asc_vf_call` launches where `VF_CALL` does not. Reported.

The positive fixture, declared before the run: Arm C's **body-present** build must overwrite the poison
and produce correct output. If it does not, the harness never launches the VF in any configuration, and
"the poison survived" in the other build is a statement about the harness, not about the conditional.
A second fixture for Arm A: one configuration must be run with the conditional's text deliberately
altered to `#if 1`, and `async_invoke` must then survive in every configuration; if it does not, the
preprocessor invocation is not reaching the header at all and every "absent" cell in the table is an
artefact of a wrong include path. Without both, the checker reads only "the symbol was missing and the
buffer was unchanged", which is exactly what a broken build harness also produces — the known blind
species.

Process exit codes are not the verdict for any arm: every configuration in this entry exits zero, which
is the entry's subject.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No preprocessor was run, no
translation unit compiled, no VF launched, no buffer poisoned, no die contacted. The header text and the
macro definition quoted in §3 are file reads over the installed CANN 9.0.0-beta.2 tree performed under the
phase-1 sanctioned read-only exception; they establish what the headers say and nothing about what a
compiler emits or a device executes.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled, preprocessed, or run. The entry does not establish that any real 950 build lands in
the empty-body configuration, that a VF is ever silently not launched, or that no diagnostic is emitted —
Arms A through E are all open. The inference in §1's third paragraph is a reading of a preprocessor
conditional, and a conditional's text is not a build.

It does not establish what a normal 950 SIMT build sets. Whether `__DAV_VEC__` is defined in the standard
toolchain invocation for a SIMT kernel is exactly the question that decides whether this trap is common or
unreachable, and nothing in this harvest answers it — no build was attempted and no toolchain invocation
was inspected.

It does not establish what `5102` is. That value is written literally into the conditional and into
`kernel_simt_intf.h`'s gate, it is not in upstream's product table (0352), and this entry deliberately
does not infer a chip from it — upstream's own `npu-arch-guide.md` warns 不可按数值推断.

It does not establish that the conditional is a defect. It is very plausibly deliberate: a launch
primitive that must be a no-op on the core side that does not launch. The claim is about documentation
silence and failure silence, not about the design.

It does not establish anything about `cce::async_invoke`, `cce::dim3`, or what a launch actually does —
those live below this header and were not read.

It says nothing about the *other* half of the pair: whether a VF that is never launched leaves a
recognisable trace in a profile, which is what a performance-oriented agent would notice first and which
no arm here measures.

BOARD is `family-claimed(unverified)`: the conditional names architecture values, not boards; the toolkit
ships 950 inis but a header is not a board, and no board was contacted.
