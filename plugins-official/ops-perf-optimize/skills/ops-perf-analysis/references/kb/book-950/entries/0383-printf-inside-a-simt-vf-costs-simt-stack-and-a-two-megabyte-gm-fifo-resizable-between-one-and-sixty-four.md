```
ID:        0383-printf-inside-a-simt-vf-costs-simt-stack-and-a-two-megabyte-gm-fifo-resizable-between-one-and-sixty-four
LABEL:     knowledge
LEVEL:     L7 (verification)
STRATUM:   corroborated — two independent origins: upstream's SIMT API reference, which reproduces the
           vendor's own documentation for the interface, and the INSTALLED CANN 9.0.0-beta.2 headers on
           this machine, which declare the two SIMT print entry points. Nothing was compiled and no
           output was captured.
BOARD:     family-claimed(unverified)
           # the reference's own 产品支持情况 table names "Ascend 950PR/Ascend 950DT" with a check mark;
           # that is upstream reproducing a vendor support matrix, not a board this harvest contacted.
SOURCE:    ops/ascendc-simt-api-reference/references/debug-api.md:298-300 — "-   printf在SIMT VF中调用，
           会占用SIMT栈空间，请合理控制调用printf次数，防止SIMT栈溢出。 / -   printf功能需要占用额外的
           Global Memory空间用于数据缓存，缓存空间大小默认为2MB。您可以通过acl.json中的
           \"simt\\_printf\\_fifo\\_size\"字段进行配置，配置范围最小为1MB，最大为64MB。当打印数据量较大时，
           建议增加缓存空间。 / -   在仿真环境下，使用printf接口会增加算子运行时间，通过在VF代码中判断
           线程ID，可以仅在部分线程中打印调试信息，减少重复内容的打印，更有利于调试。"
SOURCE:    same file:277-279 — the prototype: "template <class... Args> /
           __attribute__((always_inline)) inline __simt_callee__ void printf(const __gm__ char* fmt,
           Args&&... args)"
SOURCE:    same file:305-307 — "使用该接口需要包含\"utils/debug/asc\\_printf.h\"头文件。"
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, aarch64 —
           `asc/include/utils/debug/asc_printf.h` exists at the documented path, and
           `asc/include/interface/simt_api/cpp/kernel_simt_print_intf.h:14-29` declares, inside
           `namespace AscendC { namespace Simt {`, both `PRINTF` and `printf` as
           `template <class... Args> __aicore__ inline void …(const __gm__ char* fmt, Args&&... args)`,
           guarded by `#ifndef ASCENDC_CPU_DEBUG` and a `__CHECK_FEATURE_AT_PRECOMPILE` /
           `__NPU_DEVICE__` condition.
INDEX:     none — nothing measured; see SOURCE. The header's existence and the two declarations are
           re-derivable by file read:
           grep -n "printf\|PRINTF" $ASCEND_HOME_PATH/asc/include/interface/simt_api/cpp/kernel_simt_print_intf.h
OVERTURN:  a SIMT `printf` that continues to emit after more than 2 MB of formatted output on a default
           configuration — the FIFO would then not be the limit stated, or would not be a limit at all;
           or an `acl.json` `simt_printf_fifo_size` outside the stated 1–64 MB range being accepted.
```

# 0383 · `printf` inside a SIMT VF costs SIMT stack and a two-megabyte GM FIFO, resizable between one and sixty-four

## 1 · Claim
Upstream asserts three costs for calling `printf` inside a SIMT vector function. First, it consumes SIMT
**stack** space, so the number of calls must be controlled to avoid stack overflow. Second, it requires
**additional Global Memory** as a data buffer, defaulting to **2 MB**, configurable through the `acl.json`
field `simt_printf_fifo_size` with a minimum of 1 MB and a maximum of 64 MB, and upstream recommends
increasing it when the printed volume is large. Third, in a simulation environment `printf` increases the
operator's run time, and upstream's mitigation is to gate printing on a thread-ID test so only some
threads print. Upstream asserts the prototype as a variadic template marked `always_inline` and
`__simt_callee__`, taking a `__gm__ char*` format string, and names `utils/debug/asc_printf.h` as the
required header. Not established here: nothing was compiled and no output was captured.

Read in the installed CANN 9.0.0-beta.2 toolkit, an independent origin: the named header exists at the
documented path, and a `AscendC::Simt` namespace declares **two** print entry points, `printf` and
`PRINTF`, both variadic templates over a `__gm__ char*` format, both conditionally compiled.

## 2 · The wrong branch this removes
`printf` is the first instrument an agent reaches for, and in this model it is not free in the way the
name implies.

**The stack cost has no stated budget.** "请合理控制调用printf次数" — control the number of calls
reasonably — with no number. SIMT stack is per-thread and the thread count is a compile-time constant that
may be as high as 2048 (0232), so the aggregate is the per-call stack cost times the thread count times
the calls per thread, and none of the three is documented. An agent debugging a wrong element does the
natural thing — puts a `printf` inside the grid-stride loop — and at 512 threads over a large tensor that
is not a few calls, it is millions. Stack overflow is the stated failure and no source in scope says what
it looks like: a fault, a corrupted frame, or silently truncated output would all be consistent, and they
need different responses.

**The GM cost is the one that produces false conclusions.** 2 MB of FIFO at, say, 60 bytes per formatted
line is roughly 35 000 lines. Beyond that the buffer is full — and the `assert`-side documentation of the
same mechanism states the consequence plainly at `:299` for the AI CPU variant: 超出则不会打印, output
beyond the limit is simply not printed. So a debugging agent that adds a `printf` per element and looks at
the output sees the *first* 35 000 lines, concludes the failure is not in the region it printed, and moves
on. The evidence it is reasoning from is truncated and nothing says so at the point of use. That is the
worst possible failure mode for a debugging instrument: silent, and it biases the conclusion in a specific
direction (early elements look fine, late ones are unexamined).

**The simulation cost inverts a debugging strategy.** Printing more, to see more, makes the run slower —
and upstream's mitigation is to print from fewer threads. An agent chasing a race or a thread-divergence
bug that gates printing on `GetThreadIdx() == 0` has removed exactly the threads whose interleaving it was
trying to observe. The mitigation is right for reducing duplicate output and wrong for the class of bug
that made the agent print in the first place, and upstream does not distinguish the two cases.

**The two entry points and the two scopes.** The index table's note at `:17` says "SIMT VF外使用
`AscendC::Simt::printf` 或 `PRINTF`" — outside a SIMT VF, use those. Inside, the plain `printf` from
`asc_printf.h`. The installed header declares both `printf` and `PRINTF` inside `AscendC::Simt`, so the
qualified spelling exists; whether the unqualified in-VF `printf` is the same function reached by
argument-dependent lookup, or a different one, is not stated by either origin and is Arm E.

**And the cost is configured somewhere no kernel author looks.** `simt_printf_fifo_size` lives in
`acl.json` — a runtime configuration file, not a build flag and not a kernel source. So the fix for
truncated debug output is an edit to a file the operator author may not own, and an agent that does not
know the field exists has no way to reach it from the symptom.

## 3 · Ground / Source
The three constraints, `debug-api.md:298-300`, in full:

> -   printf在SIMT VF中调用，会占用SIMT栈空间，请合理控制调用printf次数，防止SIMT栈溢出。
> -   printf功能需要占用额外的Global Memory空间用于数据缓存，缓存空间大小默认为2MB。您可以通过acl.json中的
>     "simt\_printf\_fifo\_size"字段进行配置，配置范围最小为1MB，最大为64MB。当打印数据量较大时，建议增加
>     缓存空间。
> -   在仿真环境下，使用printf接口会增加算子运行时间，通过在VF代码中判断线程ID，可以仅在部分线程中打印调试
>     信息，减少重复内容的打印，更有利于调试。

Three numbers with units and a named configuration field — 2 MB default, 1 MB minimum, 64 MB maximum,
`acl.json` / `simt_printf_fifo_size`. That is the most precisely specified cost model in this entire
harvest block, and it is the reason this entry is `knowledge` rather than `trap`: the figures are stated,
scoped and actionable.

The prototype, `:277-279`:

> ```
> template <class... Args>
> __attribute__((always_inline)) inline __simt_callee__ void printf(const __gm__ char* fmt, Args&&... args)
> ```

`always_inline` is worth noting against the stack claim: an always-inlined variadic that materialises its
arguments into a per-thread frame is exactly how a per-call stack cost arises, and it means the cost
cannot be amortised by outlining.

The worked example, `:313-324`, shows the multi-dimensional thread built-ins and a launch shape:

> ```
> #include "kernel_operator.h"
> #include "simt_api/asc_simt.h"
> #include "utils/debug/asc_printf.h"
>
> // asc_vf_call调用时dim3参数：dim3(8, 2, 8)
> __simt_vf__ __launch_bounds__(128) inline void SimtCompute()
> {
>     int x = threadIdx.x;
>     int y = threadIdx.y;
>     int z = threadIdx.z;
>     printf("simt vf: d: (%d, %d, %d), f: %f, s: %s\n", x, y, z, 3.14f, "pass");
> }
> ```

and its output at `:326-338` — 128 lines, one per thread, ordered `(0,0,0)` through `(0,1,1)` and
truncated with `......`. That output is itself evidence for the volume argument in §2: one `printf` in one
VF at 128 threads is 128 lines, and 128 threads is the small end.

Three vocabulary observations, recorded because they bear on other entries and not claimed here:
`asc_vf_call` and `dim3` (lower-case) rather than `VF_CALL`/`Dim3` (0375); `__launch_bounds__(128)` rather
than `LAUNCH_BOUND(512)` as the SIMT programming guide writes it (0374 §3); `threadIdx.x/.y/.z` rather
than `Simt::GetThreadIdx()`. Three spellings differing between the two skills in one twelve-line example.

The AI CPU sibling, `printf-178` at `:369-380`, is a **different function** — `void printf(const char*
fmt, ...)` from `aicpu_api.h`, called as `AscendC::printf`, with its own constraints (`:243` 该接口不支持
打印除换行符之外的其他转义字符; `:244` a 1 MB per-core Dump total, 超出则不会打印; `:245` explicit
`--cce-aicpu-laicpu_api` linking under bisheng). It is documented under the same index row as the SIMT one
and is carried by 0385, not here.

The installed header, `kernel_simt_print_intf.h:14-29`, declares both `PRINTF` and `printf` in
`AscendC::Simt`, guarded by `#ifndef ASCENDC_CPU_DEBUG` and by
`#if !defined(__CHECK_FEATURE_AT_PRECOMPILE) || (defined(__CHECK_FEATURE_AT_PRECOMPILE) && defined(__NPU_DEVICE__))`.
So the qualified spellings are compiled out under CPU debug — which is the environment the third constraint
calls 仿真环境 — and what `printf` resolves to there is unestablished.

## 4 · Procedure
Runnable later on `950PR`. The three costs are three independent measurements.

Arm A — the FIFO limit and the truncation symptom. Build a SIMT kernel that prints a numbered line per
element over a tensor large enough to exceed 2 MB of formatted output at the default configuration.
Capture stdout and record the **highest line number that appears**. Then repeat with
`simt_printf_fifo_size` set to 1 MB, 4 MB and 64 MB. The claim predicts the reachable line count scales
with the configured size and that output stops silently. Recording *how* it stops — truncated mid-line,
dropped whole lines, or a warning — is the deliverable, because §2's whole argument is that the stop is
invisible.

Arm B — the configuration bounds. Set `simt_printf_fifo_size` to 512 KB and to 128 MB, outside the stated
range, and record whether each is rejected, clamped, or accepted. Acceptance of an out-of-range value is
the OVERTURN's second clause and would mean the stated range is advisory.

Arm C — the stack cost, which has no stated budget. Sweep the number of `printf` calls per thread from 1
to 64 at a fixed thread count, and separately sweep the thread count from 32 to 2048 at one call per
thread. Record the point at which the run fails and **what the failure looks like**. Two sweeps, because
the stated resource is per-thread and only the product tells whether the limit is per-thread or aggregate.

Arm D — the simulation cost and its mitigation's blind spot. Time one kernel three ways in the simulation
environment: no `printf`, `printf` from all threads, `printf` gated on `GetThreadIdx() == 0`. Record
durations and, for the third, whether any inter-thread ordering information survives. §2 claims the
mitigation removes the observations a divergence bug needs; the arm should record what the gated output can
and cannot show.

Arm E — the two entry points. Inside a VF, call unqualified `printf`, `AscendC::Simt::printf` and
`AscendC::Simt::PRINTF`, and record which compile and whether their output is identical. Then repeat
outside a VF. This settles the index note at `:17` and the header's two declarations, neither of which is
explained by either origin.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session. Arm C drives a resource to
exhaustion: a watchdog timeout and die release are declared before the run.

## 5 · Checker — acceptance declared before the run
`reachable_lines_by_fifo_size` (Arm A) — the highest line number observed, per configured FIFO size.
Pass iff the count increases monotonically with the size. A flat count means the FIFO is not the limit and
something else truncates.

`truncation_is_silent` (Arm A) — true iff no diagnostic accompanies the stop. Predicted **true**; a false
result removes the sharpest branch in §2 and is the better outcome.

`out_of_range_config` (Arm B) — per value, three-valued: rejected, clamped, accepted. Reported.

`printf_calls_before_failure` and `threads_before_failure` (Arm C) — two integers plus, for each, the
observed failure class (fault, truncated output, corrupted output, hang). Reported separately and never
multiplied together into a single "capacity": the whole question is whether the limit is per-thread or
aggregate, and one number cannot express both.

`sim_overhead_ratio` (Arm D) — duration ratios against the no-`printf` build, per variant.

`entry_point_matrix` (Arm E) — a 3×2 table (three spellings × inside/outside VF): compiles, and output
identical to the reference spelling.

The positive fixture, declared before the run: Arm A must include a run whose total output is comfortably
**under** the configured FIFO size, and every line must appear. If lines are missing there, the capture
path — not the FIFO — is losing output, and every truncation point measured in the arm is an artefact of
the harness. A second fixture for Arm C: a single `printf` from a single thread must succeed; if it does
not, the sweep's failure point measures a broken build rather than a stack limit. Without both, the checker
reads only "output stopped somewhere", which cannot distinguish a FIFO limit from a lost pipe — the known
blind species, and here it is especially easy to fall into because the expected result *is* missing output.

Process exit codes are not the verdict for any arm: Arm A expects a clean exit with incomplete output,
which is the entry's subject.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no line
printed, no FIFO configured, no stack exhausted, no die contacted. The header path and the two
declarations noted in §3 are file reads over the installed CANN 9.0.0-beta.2 tree performed under the
phase-1 sanctioned read-only exception; they establish that the interface exists and nothing about the
three costs.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish the 2 MB default, the 1–64 MB range, the stack
cost, the simulation overhead, or that truncation is silent — Arms A through E are all open. The
independent origin corroborates that the **interface exists at the documented header path**; it does not
corroborate a single one of the three cost figures, none of which appears in any header.

It does not establish a stack budget. Upstream says "control the number of calls reasonably" and gives no
per-call cost, no total, and no failure symptom. Arm C would produce the first number any source offers.

It does not establish what happens past the FIFO limit. The 超出则不会打印 statement quoted in §2 is from
the **AI CPU** sibling's constraint list at `:299`, describing that interface's 1 MB per-core Dump total —
a different function on a different execution unit. Applying it to the SIMT FIFO is §2's reasoning by
analogy and is flagged here as such; Arm A is what would establish the SIMT behaviour.

It does not establish the relationship between the unqualified in-VF `printf`, `AscendC::Simt::printf` and
`AscendC::Simt::PRINTF`. Three spellings, two origins, no explanation from either, and the header compiles
two of them out under `ASCENDC_CPU_DEBUG` — which is plausibly the 仿真环境 the third constraint names,
leaving what `printf` resolves to there entirely open.

It says nothing about the AI CPU `printf` (`printf-178`), which is a different function with different
constraints and different linking requirements, documented under the same index row — 0385 carries that.

It says nothing about format-specifier support for the SIMT variant. The AI CPU sibling explicitly states
it supports no escape character but the newline; whether the SIMT one shares that restriction is unstated,
and the worked example uses `%d`, `%f` and `%s` with a trailing `\n` only.

BOARD is `family-claimed(unverified)`: upstream's 产品支持情况 table names "Ascend 950PR/Ascend 950DT" with
a check mark, which is upstream reproducing a vendor support matrix rather than a measurement, and no board
was contacted.
