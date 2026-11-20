```
ID:        0386-trap-ends-the-thread-in-the-index-row-and-ends-the-operator-in-its-own-section
LABEL:     trap
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (ops/ascendc-simt-api-reference), whose index row and detail
           section state different scopes for the same primitive. Nothing was compiled and no trap was
           executed.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-api-reference/references/debug-api.md:15 — the index row: "| `__trap` |
           立即终止当前线程执行 | `void __trap()` | `debug/__trap.md` |" — immediately terminates
           execution of the CURRENT THREAD.
SOURCE:    same file:487 — the detail section's 功能说明: "在SIMT VF实现代码中调用此接口会中断算子的运行，
           适用于Kernel侧异常场景的调试。" — calling it interrupts the OPERATOR's run.
SOURCE:    same file:492 — the prototype: "__simt_callee__ inline void __trap()"; `:503` — "## 约束说明
           / 无"; `:509` — "使用该接口需要包含\"utils/debug/asc\\_assert.h\"头文件。"
SOURCE:    same file:517-525 — the worked example: "__simt_vf__ __launch_bounds__(1024) inline void
           SimtKernel(__gm__ bool* dst, __gm__ float* x) / { / int idx = threadIdx.x + blockIdx.x *
           blockDim.x; / if (isnan(x[idx])) { / __trap(); / } / dst[idx] = x[idx]; / }" — a
           per-thread predicate guarding the call, with no statement of what the surviving threads do.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  one run of the documented example with exactly one NaN in the input: if the non-NaN elements
           of `dst` are correctly written, `__trap` ended one thread; if none are, it ended the
           operator. One observation settles it.
```

# 0386 · `__trap` ends the thread in the index row and ends the operator in its own section

## 1 · Claim
Upstream asserts, in its index table, that `__trap` immediately terminates execution of the **current
thread**. Upstream asserts, in the detail section for the same primitive twenty-two lines from the end of
the same file, that calling it inside a SIMT VF interrupts the **operator's** run. Upstream asserts the
prototype `__simt_callee__ inline void __trap()`, states its constraints as 无 — none — and names
`utils/debug/asc_assert.h` as the required header. Upstream's worked example guards the call with a
per-thread predicate (`if (isnan(x[idx])) { __trap(); }`) and continues, after the guard, to a
per-thread store. Not established here: nothing was compiled and no trap was executed.

A thread-scoped termination and an operator-scoped termination are different primitives. One repo states
both, so reading further cannot settle it (RULES.md Art. 3).

## 2 · The wrong branch this removes
The two readings put `__trap` in two different categories of tool, and an agent picks a usage pattern from
the category rather than from the sentence.

**Under the thread reading**, `__trap` is a guard: the offending thread exits, the rest of the launch
completes, and the output is a valid tensor with holes where the guarded threads were. That makes it usable
in production-adjacent code — a NaN filter, a bounds guard — and it makes the example's trailing
`dst[idx] = x[idx];` meaningful, because most threads reach it.

**Under the operator reading**, `__trap` is an abort: the first thread to hit it takes the whole launch
down and the output is undefined. That makes it a debugging-only instrument, and the example becomes a
kernel that dies on the first NaN anywhere in the input — which is a reasonable debugging behaviour and a
catastrophic production one.

The example is written to be *consistent with both*, which is why it does not adjudicate. A per-thread
predicate followed by a per-thread store reads naturally under the thread interpretation and is equally
valid under the operator one (the store is simply never reached on any thread once the abort fires).

**The dangerous direction is specific.** An agent holding the thread reading writes `__trap` as a
production guard. If the operator reading is correct, one anomalous element in one tensor kills the
operator — and, worse, kills it *non-deterministically with respect to the data*, because whether any
element is NaN depends on upstream layers. The failure appears late, in a pipeline, on real data, having
passed every test built from clean inputs.

The reverse direction costs a capability rather than correctness: an agent holding the operator reading
never uses `__trap` outside debugging and writes a slower explicit-mask guard instead.

**Divergence makes the thread reading non-obvious even if it is correct.** 0235 records upstream asserting
that branch divergence serialises both arms within a warp. If threads of one warp are executed in
lockstep with predication, "terminate this thread" is not a hardware-natural operation — it is a mask
update, and the warp continues. So the thread reading implies a specific mechanism (predication off) with
a specific consequence: the trapped thread's lanes are simply inactive for the rest of the VF, and the
"termination" is scoped to a lane rather than to any schedulable entity. Whether the remaining lanes'
stores still happen is then the real question, and neither upstream sentence addresses it.

**And 约束说明: 无 is doing damage.** A primitive whose constraint section says "none", whose two scope
statements conflict, and whose header is the *assert* header rather than a trap-specific one, is a
primitive nobody wrote a specification for. The empty constraints section reads as a positive statement —
there is nothing to watch out for — and it is the section where the scope question should have been
resolved.

## 3 · Ground / Source
The index row, `debug-api.md:15`:

> | `__trap` | 立即终止当前线程执行 | `void __trap()` | `debug/__trap.md` |

立即终止当前线程执行 — immediately terminate the current thread's execution. 当前线程, current thread, is
unambiguous.

The detail section, `:485-487`:

> ## 功能说明<a name="section259105813316"></a>
>
> 在SIMT VF实现代码中调用此接口会中断算子的运行，适用于Kernel侧异常场景的调试。

中断算子的运行 — interrupt the operator's run. 算子, operator, is equally unambiguous and is a different
scope.

The rest of the section, `:490-512`, adds nothing that decides it:

> ## 函数原型
> ```
> __simt_callee__ inline void __trap()
> ```
> ## 参数说明
> 无
> ## 返回值说明
> 无
> ## 约束说明
> 无
> ## 需要包含的头文件
> 使用该接口需要包含"utils/debug/asc\_assert.h"头文件。

and the example, `:517-525`:

> ```
> __simt_vf__ __launch_bounds__(1024) inline void SimtKernel(__gm__ bool* dst, __gm__ float* x)
> {
>     int idx = threadIdx.x + blockIdx.x * blockDim.x;
>     if (isnan(x[idx])) {
>         __trap();
>     }
>     dst[idx] = x[idx];
> }
> ```

Note that the header is `utils/debug/asc_assert.h` — the same header as `assert` (0384, 0385). So `assert`
and `__trap` are shipped together, which is circumstantial support for the operator reading: `assert-177`
states at `:47` that a failed assertion 算子运行失败, the operator run fails. If `__trap` is the primitive
`assert` is built on, the operator reading follows. That is inference from a shared header and a related
statement, not evidence, and §7 marks it.

The name is the other circumstantial signal and it points the other way in the sense that matters:
`__trap` is the CUDA spelling, where `__trap()` requests a trap operation that aborts the *kernel*, not
the thread. This file uses CUDA-shaped spellings throughout (`threadIdx.x`, `blockDim.x`,
`__launch_bounds__`, `<<<...>>>` in the AI CPU sections, `asc_syncthreads` elsewhere in the toolkit, 0375),
so the borrowed name carries a borrowed expectation — and the borrowed expectation matches the *detail
section*, not the index row. Again inference from a naming convention, and again not evidence about this
implementation.

Recorded as `C-950rem-008`. Both statements are one file in `upstream/skills-dev-main` — one origin (RULES.md
Art. 3), and the disagreement is *within* one document, twenty-two lines from its end.

`__trap`'s 产品支持情况 table at `:468-476` is, uniquely among the five sections, **empty** — the heading
is present and no table follows. The other four sections each carry a row naming "Ascend 950PR/Ascend
950DT". So this is the one debug primitive on the page with no stated product support at all.

## 4 · Procedure
Runnable later on `950PR`. One run of the documented example decides the central question.

Arm A — the scope, observed. Build the documented example verbatim. Fill `x` with valid floats except for
**one** NaN at a known index, poison `dst` beforehand, and run. Read `dst` back. If every non-NaN element
holds its input, `__trap` ended one thread; if `dst` is entirely poison, it ended the operator; if some
region is written and some is not, it ended something in between — a warp, a block, a core — and *that*
boundary is the finding, because neither upstream statement predicts it.

Arm B — the boundary, located. Repeat Arm A with the NaN placed at index 0, at a warp boundary (index 32),
mid-warp (index 17) and at a block boundary, and record the extent of unwritten output each time. Under the
lane-predication mechanism §2 describes, the unwritten extent is one element; under a warp-scoped
mechanism it is 32; under an operator-scoped one it is everything. The extent as a function of position is
the measurement.

Arm C — divergence interaction. Repeat with 2, 8 and 32 NaNs inside one warp. If the unwritten extent grows
with the count under the thread reading, lanes are being masked independently as 0235's divergence account
predicts; if it jumps to the whole warp at the first NaN, the "thread" scope is really a warp scope.

Arm D — the exit status and the diagnostic. For each arm, record the process exit status, any runtime
error, and whether a profile shows the kernel as completed or aborted. An operator-scoped trap that exits
zero and produces partial output would be the worst combination and is a live outcome.

Arm E — the relationship to `assert`. Fire a failing `assert` (0384 Arm A) and a `__trap` in otherwise
identical kernels and compare the two outcomes on all of Arm D's axes. If they are identical, `assert` is
built on `__trap` and the operator reading is strongly supported; if they differ, they are separate
mechanisms and `assert`'s 算子运行失败 says nothing about `__trap`.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session. A trap may leave the
device in an unclean state: the harness declares a watchdog, releases the die, and re-verifies device
health between arms rather than assuming it.

## 5 · Checker — acceptance declared before the run
`unwritten_extent_elements` (Arm A, B) — the number of `dst` elements still holding poison, per NaN
position. This is the verdict variable and it is an integer rather than a boolean on purpose: 1 supports
the index row, the full tensor supports the detail section, 32 supports neither and is the most informative
outcome.

`extent_vs_nan_count` (Arm C) — the unwritten extent as a function of the NaN count within one warp.
Reported as a series, never as a single ratio.

`exit_status_and_diagnostic` (Arm D) — the process status, any runtime error text, and the profile's
completion state. Reported as three fields; a trap that aborts silently with a zero exit is the
combination that would make `__trap` undetectable from outside, and no single field would show it.

`assert_matches_trap` (Arm E) — true iff `assert` and `__trap` produce identical outcomes on all of Arm D's
axes. Reported, not gated: it is evidence about the mechanism, not about either statement's correctness.

The positive fixture, declared before the run: Arm A must include a control run with **no NaN in the
input**, in which every element of `dst` must be written. If the poison survives there, the kernel never
writes `dst` at all — a real possibility given 0373's silent-no-op launch conditional — and every
"unwritten extent" measured in the arm is a statement about the launch rather than about `__trap`. A second
fixture: the poison must be a value the input cannot produce, so that "written" and "unwritten" are
distinguishable; `dst` is `bool` in the documented example, which has few distinguishable values, so the
arm uses a wider destination type or a separate written-flag array. Without both, the checker reads only
"some output was missing", which cannot separate a trap from a launch failure — the known blind species.

Process exit codes are not the verdict: Arm D measures the exit status as data, and both a zero and a
non-zero exit are consistent with either reading until the output extent is read.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no trap
executed, no output read back, no die contacted. The two quoted statements are re-verified file reads of
the upstream tree performed during this harvest, as is the observation that this section's 产品支持情况
table is empty.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish `__trap`'s scope, and by Art. 7 it must not:
both statements are one origin and choosing between them by plausibility is the adjudication the law
forbids. Arm A settles it in one observation and has not been run.

**The two circumstantial arguments in §3 are not evidence.** That `__trap` ships in the *assert* header
and that `assert` is documented as failing the operator run is an argument from a shared header; that
`__trap` is the CUDA spelling for a kernel-aborting primitive is an argument from a borrowed name. Both
point at the operator reading, neither is an observation of this implementation, and Arm E is what would
turn the first into evidence.

It does not establish the mechanism. §2's lane-predication account — that under 0235's divergence
serialisation "terminate this thread" must be a mask update rather than a schedulable-entity exit — is
reasoning from a separately harvested claim about divergence, not a statement about `__trap`. Arms B and C
are what would locate the real boundary, and "warp" is a live third answer that neither upstream sentence
offers.

It does not establish what the surviving threads do. Under any non-operator reading there are surviving
threads and no source in scope says whether their stores complete, whether the launch reports success, or
whether the output is usable.

It does not establish product support. `__trap`'s own 产品支持情况 section is empty where the other four
sections on the page carry a row; this entry records that absence and does not fill it in from the
neighbours.

It says nothing about `__trap` outside a SIMT VF, about whether it is callable from a `__simt_callee__`
helper, or about its interaction with the print FIFO (0383) — a trap that discards buffered output would
lose the `printf` lines an agent added to find the fault, and nothing in scope addresses it.

BOARD is `family-claimed(unverified)`: this section carries no product-support table at all, and no board
was contacted.
