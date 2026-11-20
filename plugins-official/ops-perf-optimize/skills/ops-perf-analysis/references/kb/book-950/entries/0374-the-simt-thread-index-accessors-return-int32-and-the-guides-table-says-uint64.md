```
ID:        0374-the-simt-thread-index-accessors-return-int32-and-the-guides-table-says-uint64
LABEL:     trap
LEVEL:     L1 (core & pipe assignment)
STRATUM:   corroborated — two independent origins: upstream's SIMT programming guide, whose API table
           states the return types, and the INSTALLED CANN 9.0.0-beta.2 headers on this machine, which
           declare them. Nothing was compiled and no index was computed on a device.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-programming-best-practices/references/index-calculation.md:5-10 — "## API 列表
           / | API | 返回类型 | 说明 | / | `AscendC::Simt::GetThreadIdx()` | uint64_t | 当前线程在核内的
           索引 (0 ~ threadNum-1) | / | `AscendC::Simt::GetThreadNum()` | uint64_t | 当前核的线程总数 | /
           | `AscendC::Simt::GetBlockIdx()` | uint64_t | 当前核的全局索引 (0 ~ blockNum-1) | /
           | `AscendC::Simt::GetBlockNum()` | uint64_t | 总核数 |"
SOURCE:    same file:14-19 — "// 线程在全局数据中的线性索引 / uint64_t globalIdx = GetBlockIdx() *
           GetThreadNum() + GetThreadIdx(); / // 步进 stride（所有核所有线程总数） / uint64_t stride =
           GetThreadNum() * GetBlockNum();"
SOURCE:    same file:34-38 — "## 头文件 / ```cpp / #include \"simt_api/common_functions.h\" / ```"
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, aarch64 —
           `asc/include/interface/simt_api/cpp/kernel_simt_common_intf.h:28-38`, inside
           `namespace AscendC { namespace Simt {`:
             `__aicore__ inline int32_t GetWarpSize();`
             `template <int32_t dim = 0> __aicore__ inline int32_t GetThreadNum();`
             `template <int32_t dim = 0> __aicore__ inline int32_t GetThreadIdx();`
             `__aicore__ inline int32_t GetBlockIdx();`
             `__aicore__ inline int32_t GetBlockNum();`
           All four return `int32_t`, not `uint64_t`; the two thread accessors are TEMPLATES over a
           `dim` index defaulting to 0; and a fifth accessor, `GetWarpSize()`, is declared beside them
           and appears in no upstream document in scope.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read on this machine:
           grep -n "GetThread\|GetBlock\|GetWarpSize" $ASCEND_HOME_PATH/asc/include/interface/simt_api/cpp/kernel_simt_common_intf.h
OVERTURN:  a toolkit pin in which the four accessors are declared `uint64_t` — the mismatch would then
           be version skew rather than a documentation error; or a compile in which the documented
           `uint64_t globalIdx = GetBlockIdx() * GetThreadNum() + GetThreadIdx();` is diagnosed, which
           would make the mismatch loud rather than silent.
```

# 0374 · The SIMT thread-index accessors return `int32`, and the guide's table says `uint64`

## 1 · Claim
Upstream asserts an API table for the four SIMT index accessors — `GetThreadIdx`, `GetThreadNum`,
`GetBlockIdx`, `GetBlockNum` — giving each a return type of `uint64_t`, and asserts the two derived
quantities in the same types: `uint64_t globalIdx = GetBlockIdx() * GetThreadNum() + GetThreadIdx();` and
`uint64_t stride = GetThreadNum() * GetBlockNum();`. Not established here: nothing was compiled.

Read in the installed CANN 9.0.0-beta.2 headers, an independent origin, by file read: all four are
declared `int32_t` inside `AscendC::Simt`. `GetThreadNum` and `GetThreadIdx` are additionally **function
templates** parameterised by an `int32_t dim` defaulting to 0, which upstream's table does not show. A
fifth accessor, `GetWarpSize()`, is declared immediately above them and returns `int32_t`.

The inference, stated separately: under the header's types, upstream's own global-index expression is
evaluated entirely in signed 32-bit arithmetic and only then converted to `uint64_t` by the initialisation.
Not established here — no expression was compiled and no overflow was produced.

## 2 · The wrong branch this removes
A type mismatch in a documentation table is usually harmless, because the compiler wins. Here the compiler
wins *quietly*, and what it wins is the arithmetic.

`uint64_t globalIdx = GetBlockIdx() * GetThreadNum() + GetThreadIdx();` — with `int32_t` accessors, the
multiplication and the addition happen in `int`, and the widening to `uint64_t` happens at the assignment,
after the damage. Two consequences follow and neither produces a diagnostic at default warning levels.

**Overflow.** `blockIdx × threadNum` is bounded by the machine's total thread count, which for the values
in this material (up to 2048 threads per core, 0232; tens of cores, 0217) stays far inside `int32`. So the
product is safe. The **stride loop is not necessarily the same question**: `i < count` compares an
`int`-derived value against a `uint64_t` count, and once `i` is `uint64_t` by the loop variable's
declaration the comparison is fine. The genuine exposure is the *element index*, not the thread index —
an agent that follows the documented pattern and then writes `x[globalIdx * elemsPerThread]` with
`elemsPerThread` an `int` has an `int` product indexing a buffer that may exceed 2³¹ elements. That is a
tensor of 2 G elements, which is 4 GB at fp16 — reachable.

**Signedness.** `int32_t` is signed. `GetThreadIdx()` is documented as ranging `0 ~ threadNum-1`, so a
negative value should never occur — but the *type* admits one, and `uint64_t globalIdx = <negative int>`
converts to an enormous positive value rather than trapping. Any path where an accessor could return a
sentinel (an uninitialised context, an error return) turns into an out-of-bounds index of about 2⁶⁴, and
the symptom is a fault at an address with no relationship to the tensor. 0208 records the analogous shape
one layer down: `GetCurNpuArch()` signals failure with a sentinel that an unchecked return silently
converts into a fallback.

**The template parameter is the larger omission.** `GetThreadIdx<dim>()` with `dim` defaulting to 0 means
the accessor is *per-dimension*: there is a thread index for dimension 0, 1 and 2. That matches
`Dim3`/`cce::dim3` being three-dimensional, and it matches the vendor's own SIMT example, which uses
`threadIdx.x`, `threadIdx.y`, `threadIdx.z` (`debug-api.md:141-143`) with a launch of `dim3(8, 2, 8)`.
Upstream's table shows a scalar accessor and its guide shows only one-dimensional launches
(`Dim3(512)`). So an agent working from the guide does not know that a 2-D or 3-D launch is expressible,
and — worse — an agent that *does* launch multi-dimensionally and calls the undecorated `GetThreadIdx()`
gets dimension 0 only, silently ignoring the other two. The loop then covers `threadNum.x` threads'
worth of work while `y × z` times as many threads execute it, and every element is computed
`y × z` times by different threads, racing on the same addresses.

That last consequence is the one worth carrying: the omission is not "a template parameter is
undocumented", it is "a multi-dimensional launch degenerates into a write race, silently".

## 3 · Ground / Source
Upstream's table, `index-calculation.md:5-10`, quoted in SOURCE, and the derived quantities at `:14-19`:

> ```cpp
> // 线程在全局数据中的线性索引
> uint64_t globalIdx = GetBlockIdx() * GetThreadNum() + GetThreadIdx();
>
> // 步进 stride（所有核所有线程总数）
> uint64_t stride = GetThreadNum() * GetBlockNum();
> ```

and the worked example at `:25-31`, which repeats the same types:

> ```cpp
> __simt_vf__ __aicore__ LAUNCH_BOUND(512) inline void OpSimt(uint64_t count, __gm__ float* x, __gm__ float* y) {
>     uint64_t idx = AscendC::Simt::GetBlockIdx() * AscendC::Simt::GetThreadNum() + AscendC::Simt::GetThreadIdx();
>     uint64_t step = AscendC::Simt::GetThreadNum() * AscendC::Simt::GetBlockNum();
>     for (uint64_t i = idx; i < count; i += step) {
>         y[i] = x[i] * 2.0f;
>     }
> }
> ```

The same expression appears a third time in the skill's canonical pattern block (`SKILL.md:40-41`) and a
fourth in `vf-call.md:21-24`, there wrapped in `static_cast<uint64_t>(...)` — which is the only place in
the skill that acknowledges the expression is not already `uint64_t`:

> ```cpp
>     for (uint64_t index = static_cast<uint64_t>(
>              AscendC::Simt::GetBlockIdx() * AscendC::Simt::GetThreadNum() + AscendC::Simt::GetThreadIdx());
>          index < count;
>          index += (AscendC::Simt::GetThreadNum() * AscendC::Simt::GetBlockNum())) {
> ```

Four statements of one expression across two files, one of them cast and three not. The cast is in the
`vf-call` example and absent from the `index-calculation` file whose entire subject is the arithmetic.
That is the shape this book keeps finding: the same quantity in several spellings, maintained separately.

The header, `kernel_simt_common_intf.h:18-43`, in full:

> ```cpp
> #include "simt_api/cpp/kernel_simt_utils.h"
> namespace AscendC {
> namespace Simt {
> enum class SatMode {
>     NO_SAT = 0,
>     SAT
> };
> __aicore__ inline int32_t GetWarpSize();
> template <int32_t dim = 0>
> __aicore__ inline int32_t GetThreadNum();
> template <int32_t dim = 0>
> __aicore__ inline int32_t GetThreadIdx();
> __aicore__ inline int32_t GetBlockIdx();
> __aicore__ inline int32_t GetBlockNum();
> }  // namespace Simt
> }  // namespace AscendC
> ```

Three facts beyond the return types. The thread accessors are templates and the block accessors are not —
so blocks are one-dimensional and threads are three-dimensional, an asymmetry no document states.
`GetWarpSize()` exists. And `SatMode` is declared here, a saturation-mode enum that appears in no upstream
document in scope.

**`GetWarpSize()` is a re-verification correction owed to an existing entry.** `Q-950arch-11`, recorded
against 0234, states of the 32-thread warp width and the four warp schedulers that "Neither has an
accessor and neither has an ini field". The first half is wrong: `GetWarpSize()` is declared in this
header, and `kernel_simt_warp_level_intf.h:18-51` additionally uses a bare identifier `warpSize` as a
default argument to `WarpShflSync`, `WarpShflUpSync`, `WarpShflDownSync` and `WarpShflXorSync`. 0234 is
outside this block's write partition and is **not** edited; the correction is recorded here, in
`harvest/standing/950-rem.md`, and in the final report. What remains true of `Q-950arch-11` is that the
warp width has no ini field and has never been measured — an accessor is a declaration, not a value.

The header-path claim is 0375's; this entry uses the header only for the types.

## 4 · Procedure
Arms A and B are compile-and-read and need no device.

Arm A — the types, confirmed by the compiler rather than by grep. Compile a translation unit containing
`static_assert(std::is_same_v<decltype(AscendC::Simt::GetThreadIdx()), int32_t>);` and the same for the
other three, plus `GetWarpSize`. Record which assertions hold. This is the arm that turns a file read into
a type fact.

Arm B — the documented expression, diagnosed. Compile upstream's uncast
`uint64_t globalIdx = GetBlockIdx() * GetThreadNum() + GetThreadIdx();` at `-Wall -Wextra
-Wsign-conversion -Wconversion` and record every diagnostic. Predicted at default levels: none. The list
of flags that *would* have caught it is the deliverable, because it is the one thing a project can act on
without changing any kernel.

Arm C — the overflow, produced. Build a SIMT kernel whose element index is
`globalIdx * elemsPerThread` with `elemsPerThread` an `int`, over a tensor of more than 2³¹ elements.
Poison the far end of the buffer. Record whether the far end is written, whether the kernel faults, and
where. This is the arm that shows whether the type mismatch is reachable or merely theoretical at the
shapes this hardware runs.

Arm D — the dimension omission, which §2 argues is the serious half. Launch with `Dim3(8, 2, 8)` — the
vendor's own documented example shape — and run two VF bodies: one calling the undecorated
`GetThreadIdx()`, one calling `GetThreadIdx<0>()`, `<1>()`, `<2>()` and combining them. Have each thread
atomically increment a per-element counter. Record the counter distribution. §2 predicts the first body
gives every element a count of 16 (the `y × z` product) and the second gives 1. That histogram is the
whole claim and it needs no timing.

Arm E — `GetWarpSize`, since it is now known to exist. Call it and record the value. This does not settle
`Q-950arch-11` — a returned constant is not a measured warp quantum, and 0234's staircase is still owed —
but it converts "no accessor" into a number and tells the next harvester what the toolchain believes.

Device selection, for Arms C, D and E: the operator names the device index, the harness prints it back
with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and all builds of one comparison run on one named die in one session. Arm C allocates
a multi-gigabyte tensor: the allocation is checked and released explicitly, and the arm is skipped rather
than retried if HBM is contended.

## 5 · Checker — acceptance declared before the run
`declared_types` (Arm A) — five booleans, one per accessor. Pass iff all five are `int32_t`. A `uint64_t`
anywhere is the OVERTURN's first clause.

`silent_at_default_warnings` (Arm B) — true iff no diagnostic appears at the project's normal flags.
Predicted **true**; a false result removes the trap and is the better outcome. Reported alongside
`caught_by_flags`, the list of flags that do produce a diagnostic — a separate variable, because "it is
silent" and "here is how to make it loud" are different deliverables and one boolean cannot carry both.

`far_end_written` (Arm C) — true iff the poisoned far end of the >2³¹-element tensor is overwritten
correctly. Pass condition **true** would mean no overflow occurred; a false result with a fault located
near the wraparound address is the positive finding.

`per_element_count_histogram` (Arm D) — the distribution of per-element write counts, for both bodies,
reported as a histogram and never as a mean. A mean of 16 and a mean of 1 would be visible, but a
*bimodal* distribution — some elements written 16 times and some not at all — is the outcome that
distinguishes a race from a clean overcount, and it is invisible in any summary statistic.

`warp_size_value` (Arm E) — the integer returned. Reported, explicitly **not** treated as establishing the
warp quantum.

The positive fixture, declared before the run: Arm D must include a control launch of `Dim3(512)` —
one-dimensional — for which **both** bodies must give every element a count of exactly 1. If they do not,
the atomic counter or the launch is wrong and the 3-D histograms mean nothing. And Arm C must include a
small-tensor control whose far end **is** written; if it is not, the poison check is broken independently
of any overflow. Without both, the checker reads only "some elements had odd counts", which is the known
blind species.

Process exit codes are not the verdict for any arm: Arm C expects a possible fault as the informative
outcome and Arm D expects a clean exit with wrong data.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was compiled,
no `static_assert` evaluated, no kernel launched, no counter incremented, no die contacted. The header
declarations quoted in §3 are file reads over the installed CANN 9.0.0-beta.2 tree performed under the
phase-1 sanctioned read-only exception.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that the type mismatch produces wrong results,
that the documented expression is silent at any warning level, or that a multi-dimensional launch races —
Arms A through E are all open, and the arithmetic argument in §2 is reasoning about declared types, not an
observation.

It does not establish that the mismatch is a documentation error rather than version skew. One toolkit pin
was read; a pin declaring `uint64_t` would reframe it entirely, and that check (repeating the grep against
`cann-8.5.0` and the other installed trees) was not performed.

It does not establish the semantics of the `dim` template parameter. That `GetThreadIdx<1>()` returns the
y-dimension index is an inference from `Dim3` being three-dimensional and from the vendor's
`threadIdx.x/.y/.z` example; the header declares a parameter and no meaning, and Arm D is what would
confirm the mapping.

It does not establish why the thread accessors are templated and the block accessors are not. That
asymmetry is read from the header and explained by no source.

**It does not settle `Q-950arch-11`.** `GetWarpSize()` existing corrects that question's "neither has an
accessor" clause — recorded here because 0234 is outside this block's write partition and was not edited —
but an accessor returning a constant is not a measurement of the warp quantum, and the thread-count
staircase 0234 owes is untouched.

It says nothing about `SatMode`, declared in the same header and mentioned by no upstream document in
scope, nor about the fourteen warp-level primitives declared in the neighbouring header (0375 §3).

BOARD is `family-claimed(unverified)`: a return type is not board-dependent, upstream's file names no
board token this book recognises, and no board was contacted.
