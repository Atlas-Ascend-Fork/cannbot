```
ID:        0376-two-vf-calls-in-one-kernel-serialise-within-a-block-and-do-not-synchronise-across-cores
LABEL:     boundary
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (ops/ascendc-simt-programming-best-practices). Upstream
           states the guarantee and its limit and names no mechanism and no symptom. Nothing was
           compiled and no VF was launched.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-programming-best-practices/references/multi-core-sync.md:27-33 — "## 多个
           VF_CALL 之间的同步 / 1. 同一个 kernel 内多个 `Simt::VF_CALL` 之间**仅能保证 block 内 VF 串行**
           / 2. **不能保证全核同步** / 3. 如果 `Simt::VF_CALL` 之间需要全核同步： / - 在同步的位置加上
           `SyncAll()` / - tiling 设置 `context->SetScheduleMode(1)`"
SOURCE:    same file:3-13 — "## 多核之间交换数据 / 如果需要多核之间交换数据，需要使用 **workspace**：/
           1. **tiling 侧**：申请 workspace 大小 / 2. **kernel 侧**：直接使用 workspace 指针 /
           ### 防止时序问题 / - kernel 处需要调用 `SyncAll()` 接口 / - tiling 需要设置
           `context->SetScheduleMode(1)`"
SOURCE:    same file:15-25 — the paired snippet: "// Tiling 侧 / context->SetScheduleMode(1);  // 同步模式
           / size_t workspaceSize = ...;   // 计算所需 workspace 大小 / context->SetWorkspaceSize(
           workspaceSize); / // Kernel 侧 / __gm__ float* ws = (__gm__ float*)workspace; / // ... 使用
           workspace 交换数据 ... / AscendC::SyncAll();  // 全核同步"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 SIMT kernel in which two consecutive `VF_CALL`s ARE observed to be globally ordered
           without `SyncAll()` — i.e. every core's first VF provably completes before any core's second
           VF begins, over enough repetitions to exclude coincidence. Separately: a kernel in which
           the second VF of a block starts before the first completes, which would break the weaker
           guarantee too.
```

# 0376 · Two `VF_CALL`s in one kernel serialise within a block and do not synchronise across cores

## 1 · Claim
Upstream asserts a two-part ordering statement about consecutive SIMT launches: between multiple
`Simt::VF_CALL`s inside one kernel, **only** serialisation within a block is guaranteed, and all-core
synchronisation is **not** guaranteed. Upstream asserts the remedy: where all-core synchronisation is
needed between `VF_CALL`s, call `SyncAll()` at that point **and** set `context->SetScheduleMode(1)` in
tiling. Upstream asserts the same pair as the general prerequisite for exchanging data between cores
through workspace, and ships them as one snippet — the schedule mode on the host side, the barrier on the
kernel side. Not established here: nothing was compiled, no VF was launched, and upstream names no
mechanism and no symptom for either half.

## 2 · The wrong branch this removes
The intuition a SIMT programmer arrives with is that consecutive launches are a sequence. In the CUDA
model the guide's vocabulary borrows from, two kernel launches on one stream are ordered device-wide;
here, two `VF_CALL`s in one kernel body are ordered only within a block. Reading the second as the first
is the error, and the code that expresses it is the most natural code there is:

```
VF_CALL<Phase1>(Dim3(512), ws, in);   // every thread writes its partial into workspace
VF_CALL<Phase2>(Dim3(512), ws, out);  // every thread reads all partials
```

Phase 2 on core 0 may run while core 7 is still in phase 1. Core 0 reads a workspace slot that has not
been written and gets whatever was there — usually zero, because workspace is often zeroed, which is the
worst possible value for a reduction because it is *plausible*. The result is a slightly-wrong sum with no
error, no fault, and no reproducibility: the set of slots that were late changes every run.

Three properties make this specific failure hard to attribute.

**It scales in the wrong direction.** At one core there is no cross-core ordering to violate, so every
single-core test passes. At small core counts and small workloads the timing skew is smaller than the
launch overhead and it usually passes. It appears at production core counts and production shapes — after
the operator has been signed off.

**The correct-looking fix is on the wrong side.** An agent that suspects a race and adds a barrier
*inside* the VF body (`asc_syncthreads`, if it finds it — 0375 §2) has added an intra-block barrier to fix
a cross-block problem. It changes the timing, the failure rate drops, and the fix is recorded.

**The remedy is two-sided and the halves live in different files.** `SyncAll()` is kernel-side;
`SetScheduleMode(1)` is host-side, in the tiling function. An agent editing the kernel adds the barrier
and not the schedule mode. Upstream does not say what happens then — whether `SyncAll()` without
`SetScheduleMode(1)` blocks forever, returns immediately, or works. All three are plausible and they need
opposite responses, and this is the single most useful thing §4 could establish.

The `SetScheduleMode(1)` half also carries an unstated cost. Upstream's own comment calls it 同步模式 —
synchronous mode — which by its name constrains how the scheduler may overlap blocks across cores. If it
serialises block dispatch, then every operator that needs one cross-core barrier pays a scheduling penalty
across its whole execution, and the tiling routine has no basis on which to weigh that. No source in scope
prices it.

## 3 · Ground / Source
The ordering statement, `multi-core-sync.md:27-33`, in full:

> ## 多个 VF_CALL 之间的同步
>
> 1. 同一个 kernel 内多个 `Simt::VF_CALL` 之间**仅能保证 block 内 VF 串行**
> 2. **不能保证全核同步**
> 3. 如果 `Simt::VF_CALL` 之间需要全核同步：
>    - 在同步的位置加上 `SyncAll()`
>    - tiling 设置 `context->SetScheduleMode(1)`

Three numbered lines and the whole content of the file's second half. Point 1 is a positive guarantee —
block-internal serialisation — and it is worth noting that it is *asserted*, not derived: nothing says
whether it comes from the hardware, the compiler, or `cce::async_invoke`'s contract. Point 2 is the
negative. Point 3 is the remedy, and it is a conjunction.

The workspace prerequisite, `:3-13`, quoted in SOURCE, states the same pair for a different purpose
(exchanging data between cores at all, not specifically between launches), and the snippet at `:15-25`
shows them together with the schedule mode commented 同步模式.

`SetScheduleMode` appears in this harvest's scope only here. No document read during this harvest defines
it, enumerates its modes, states what mode 0 is, or says what it costs. `SyncAll()` is declared in the
installed toolkit at `include/ascendc/basic_api/interface/kernel_operator_block_sync_intf.h:76-84` with
two forms — one taking a `GlobalTensor<int32_t>` GM workspace and a `LocalTensor<int32_t>` UB workspace
plus further arguments, and a no-argument form declared twice under different conditions. That the
workspace-taking overload exists is worth recording: a barrier that needs its own workspace is a different
resource proposition from one that does not, and upstream's snippet uses the no-argument form while its
surrounding text is entirely about workspace.

`SyncAll` is **not** in `simt_api/device_sync_functions.h`, the header this same file names at `:35-39`;
that file declares `asc_syncthreads`, `asc_threadfence` and `asc_threadfence_block`. 0375 carries that
mismatch and the substitution hazard it creates; it is cited here because the remedy in point 3 cannot be
compiled from the include this file supplies.

What upstream does not supply: any statement of what happens when the two halves are separated; any
symptom for the unsynchronised case; any statement of whether point 1's block-internal serialisation
survives when the two VFs have different `Dim3` arguments; and any cost for 同步模式.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on `950PR`. Every arm needs multiple cores by construction, so none of them is a
single-core test.

Arm A — the negative guarantee, provoked. Build a two-phase SIMT kernel: phase 1 writes a per-core
sentinel into workspace, phase 2 reads every core's slot and counts how many are still unwritten. Launch
both phases with consecutive `VF_CALL`s and **no** `SyncAll()`. Run 500 times at the highest available
core count. Record the distribution of unwritten-slot counts. §2 predicts a non-zero count on some runs.
Reporting the *distribution* rather than a pass/fail is deliberate: a race that appears in 2 runs of 500
is the one that ships.

Arm B — the positive guarantee, point 1. Same kernel, but phase 2 reads only its **own block's** slot.
Run 500 times. Upstream asserts this is safe. A single unwritten own-slot observation breaks the weaker
guarantee and is a much more serious finding than Arm A's.

Arm C — the remedy, and its two halves separated. Four builds: neither `SyncAll` nor `SetScheduleMode(1)`;
`SyncAll` only; `SetScheduleMode(1)` only; both. Run Arm A's protocol on each. Record correctness **and**
whether any build hangs. This is the arm the entry exists for: upstream states the conjunction and never
says what one half alone does, and "hangs" is a live outcome that must be timed rather than waited on.

Arm D — the cost of 同步模式. For the both-halves build and a no-barrier build that is *already correct*
by construction (each core touching only its own data), compare durations at three core counts. The ratio
is the price of `SetScheduleMode(1)` plus the barrier; a second pair with `SetScheduleMode(1)` alone
separates the scheduling cost from the barrier cost. Without that separation the number attributes nothing
— a two-point comparison of two different builds carries no attribution.

Arm E — the block-serialisation guarantee under differing launch shapes. Repeat Arm B with the two
`VF_CALL`s given different `Dim3` arguments (512 then 256). Upstream's point 1 says nothing about whether
the guarantee depends on the shapes matching, and a generated kernel may well vary them.

Device selection is explicit: the operator names every device index used, the harness prints them back
with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and all builds of one comparison run on one named die in one session. Arms A and C
include builds that may hang: a watchdog timeout and die release are declared before the run, and an
un-timed arm is not permitted on a shared machine.

## 5 · Checker — acceptance declared before the run
`crosscore_unordered` (Arm A) — the number of runs out of 500 with at least one unwritten slot, and the
maximum unwritten count seen. Two numbers, reported together: a rare failure and a large failure are
different risks and one of them alone misrepresents the hazard.

`block_serialisation_holds` (Arm B) — true iff no own-slot read is ever unwritten in 500 runs. Pass
condition **true**. A false result overturns upstream's positive guarantee and is the entry's most
consequential possible outcome.

`half_remedy_outcome` (Arm C) — for each of the four builds, a triple: failure rate, hang (yes/no), and
mean duration. Reported as a 4-row table, never collapsed. The two single-half rows are the whole point,
and any summary that reports only "the full remedy worked" discards them.

`schedule_mode_cost` (Arm D) — two ratios per core count: (both halves / neither) and
(`SetScheduleMode(1)` only / neither). Both required. The first alone confounds the barrier with the
scheduling mode, which is the attribution error this book records as a named species.

`serialisation_survives_shape_change` (Arm E) — true iff Arm B's result holds with mismatched `Dim3`.
Reported.

The positive fixture, declared before the run: **Arm A's no-barrier build must fail at least once.** If it
does not, the workload has no cross-core race in it — the phases may be too short, or the scheduler may
happen to serialise — and every clean result in Arms B, C and E is a statement about the probe rather than
about ordering. A synchronisation experiment whose unsynchronised arm passes has measured nothing. A
second fixture: the sentinel check must be shown able to report a failure, by running phase 2 alone
against an unwritten workspace, which must report every slot unwritten. Without both, the checker reads
only "the slots looked written", which is the known blind species.

Process exit codes are not the verdict for any arm: every failure mode here exits zero, and a watchdog
kill is an informative outcome rather than an error.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no VF
launched, no workspace written or read, no barrier called, no die contacted. The quoted passages are
re-verified file reads of the upstream tree performed during this harvest; the `SyncAll` declaration noted
in §3 is a file read of the installed CANN 9.0.0-beta.2 headers under the phase-1 read-only exception.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that consecutive `VF_CALL`s are unordered across
cores, that they are ordered within a block, or that `SyncAll()` plus `SetScheduleMode(1)` fixes it — Arms
A through E are all open, and upstream states all three with **no mechanism and no symptom**.

**It establishes nothing about `SetScheduleMode`.** The function is named once in this harvest's entire
scope, with one argument value and a two-character comment. What mode 0 is, what other modes exist, what
the mode changes in the scheduler, and what it costs are all unknown here. Arm D would price one
configuration; it would not document the interface.

It does not establish what half a remedy does. Whether `SyncAll()` without `SetScheduleMode(1)` hangs,
returns immediately, or works is the question a kernel-editing agent will meet first, and no source in
scope answers it.

It does not establish that the remedy is compilable as documented. The same upstream file names
`simt_api/device_sync_functions.h` as its header, and that header does not declare `SyncAll` (0375). So
point 3 as written may not compile from the include this file supplies, and that is 0375's claim, not
established here.

It does not establish anything about `asc_syncthreads` as an alternative: 0375 records that it is an
intra-block primitive by naming and neighbourhood, which is reasoning about names, not semantics.

It says nothing about ordering *within* a single `VF_CALL` — thread-level and warp-level ordering inside
one launch is a different mechanism, and the fourteen warp-level primitives the toolkit declares (0375 §3)
appear in no upstream document in scope.

BOARD is `family-claimed(unverified)`: the file names no board token this book recognises and no board was
contacted.
