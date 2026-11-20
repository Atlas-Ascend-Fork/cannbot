```
ID:        0378-a-simt-thread-computes-on-gm-directly-and-a-ub-buffer-is-for-intra-core-sharing-only
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (ops/ascendc-simt-programming-best-practices), stated across
           three of its own files. Upstream gives a three-row selection table with reasons and no
           numbers. Nothing was compiled and no transfer was timed.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-programming-best-practices/references/data-transfer.md:3-14 — "## 简单场景：
           直接在 GM 上计算 / SIMT 支持直接操作 GM 数据，通常不需要显式调用 DataCopyPad 等接口：" with the
           worked body "`y[i] = x[i] + 1.0f;  // 直接读写 GM`"
SOURCE:    same file:45-51 — "## 选择指南 / | 场景 | 方案 | 原因 | / | 逐元素操作，无依赖 | 直接 GM |
           避免不必要的 UB 搬运 | / | 需要核内线程间共享数据 | UB 中转 | 共享数据需在核内共享内存 | /
           | 多次访问同一数据 | UB 中转 | UB 访问延迟低于 GM |"
SOURCE:    ops/ascendc-simt-programming-best-practices/references/intra-core-shared.md:3-5 — "## 概述 /
           类似 CUDA 中的 shared_memory，SIMT 核内多线程之间交换数据需要使用 UB buffer。"
SOURCE:    ops/ascendc-simt-programming-best-practices/SKILL.md:54,56 — the SIMT/SIMD comparison table:
           "| **数据访问** | GM 直接读写（`__gm__ T*`） | DataCopyPad 搬到 UB/L0C |" and
           "| **核内共享** | UB buffer + `__ubuf__` 指针 | TQue 流水线 queue |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 SIMT kernel in which a direct `__gm__` element-wise access is slower than the same
           computation staged through UB at n = 1 access per element — the "avoid unnecessary UB
           movement" reason would then be inverted for the case the table sends to GM.
```

# 0378 · A SIMT thread computes on GM directly, and a UB buffer is for intra-core sharing only

## 1 · Claim
Upstream asserts that SIMT supports operating directly on GM data and that explicit staging interfaces
such as `DataCopyPad` are usually unnecessary, showing an element-wise body that reads and writes `__gm__`
pointers in the loop. Upstream asserts a three-row selection table: element-wise work with no dependence
goes direct to GM, because UB movement would be unnecessary; data shared between threads *within a core*
goes through UB, because shared data must live in the intra-core shared memory; and data accessed several
times goes through UB, because UB access latency is lower than GM. Upstream asserts the intra-core case by
analogy — the UB buffer is "like CUDA's shared_memory" — and contrasts the whole model against SIMD in its
skill table: SIMT reads and writes GM directly through `__gm__` pointers where SIMD copies to UB or L0C,
and SIMT shares within a core through a UB buffer and a `__ubuf__` pointer where SIMD uses a `TQue`
pipeline. Not established here: nothing was compiled, no transfer was timed, and upstream gives **no
figure** for any of its three reasons.

## 2 · The wrong branch this removes
The branch this removes is an experienced agent's competence transferring from the wrong model.

An agent that has written AscendC vector kernels knows that touching GM in the compute loop is the
cardinal error: the whole SIMD discipline is `CopyIn → Compute → CopyOut`, tiles are staged in UB, and a
GM access inside the arithmetic is a bug. Carrying that into SIMT produces a kernel that stages every tile
into UB, computes there, and copies back — reproducing the SIMD pipeline inside a programming model whose
selling point is that it does not need one. It works. It is more code, it consumes the UB budget that the
DCache reservation is already competing for (0237, 0377), and it forfeits the model's advantage on exactly
the workloads SIMT exists for: irregular access, per-thread branching, gather-shaped indexing (0243).

The mirror error is the one the table's second row guards. An agent that has internalised "SIMT touches GM
directly" writes an intra-core reduction with threads exchanging partials through GM. That is not merely
slow — it is **unsynchronised**, because the ordering guarantee between threads of one block is not the
same as the ordering between cores (0376), and nothing in the direct-GM idiom provides a barrier. The
result is a race whose failure rate depends on thread count, which is the presentation
`common_traps.md:145-159` records as masquerading as precision drift.

So the two rows are not two performance options. The first is a performance choice and the second is a
correctness requirement, and the table presents them in one column headed 方案 with reasons of equal
grammatical weight. An agent reading it as a performance table will treat the second row as advice.

The third row is where the table is weakest and most likely to be misapplied. "多次访问同一数据 → UB 中转"
has no *n*: two accesses, or ten? The staging itself costs a read and a write, so the crossover cannot be
at n = 2 unless UB access is more than twice as cheap, and no figure anywhere in this material supports
any particular threshold. An agent that stages on the second access has probably lost; an agent that never
stages has probably lost on a hot lookup table. The table gives a direction and the direction is not
actionable without the number.

**A fourth consideration upstream does not raise at all.** Direct GM access from a SIMT thread means the
memory system sees per-thread accesses rather than staged bursts. Whether those coalesce — and what
address pattern is required for them to — is the single most consequential question about the direct-GM
idiom, and no source in scope mentions coalescing, burst formation, or access-pattern requirements. 0165
records the analogous effect on the SIMD side (a transposed last axis collapses NDDMA burst to one
element); nothing establishes whether an equivalent cliff exists here.

## 3 · Ground / Source
The direct-GM idiom, `data-transfer.md:3-14`:

> ## 简单场景：直接在 GM 上计算
>
> SIMT 支持直接操作 GM 数据，通常不需要显式调用 DataCopyPad 等接口：
>
> ```cpp
> __simt_vf__ __aicore__ LAUNCH_BOUND(512) inline void OpSimt(
>     uint64_t count, __gm__ float* x, __gm__ float* y) {
>     for (uint64_t i = ...; i < count; i += step) {
>         y[i] = x[i] + 1.0f;  // 直接读写 GM
>     }
> }
> ```

通常 — "usually" — is the hedge, and the file's selection table is where the exceptions are meant to live.

The table, `:45-51`, quoted in SOURCE. Three rows, three reasons, no numbers, no shapes, and no
measurement anywhere in the file.

The intra-core case, `intra-core-shared.md:3-5`, and its mechanics at `:9-38`: `TBuf<QuePosition::VECCALC>`
declared in the kernel, `InitBuffer(sharedBuf_, 2048)`, a `LocalTensor<uint32_t>` obtained and its
`GetPhyAddr()` cast to `__ubuf__ uint32_t*`, that pointer passed into the VF as a parameter, and inside the
VF plain subscripting: `uint32_t val = sharedData[0];` and
`sharedData[Simt::GetThreadIdx()] = val * 2;`. So the shared buffer is addressed by thread index and the
VF sees it as an ordinary pointer — which is what makes the concurrency warning at `:43` necessary
(0379).

The model contrast, `SKILL.md:46-58`, is the clearest statement of the partition and is worth quoting for
the two rows this entry claims:

> | 维度 | SIMT | SIMD |
> |------|------|------|
> | **数据访问** | GM 直接读写（`__gm__ T*`） | DataCopyPad 搬到 UB/L0C |
> | **核内共享** | UB buffer + `__ubuf__` 指针 | TQue 流水线 queue |
> | **适用场景** | 逐元素、条件分支、不规则访问 | 规则向量、高吞吐归约 |

The last row is the design rationale and it is the reason the first two hold: SIMT is offered for
element-wise, branch-heavy and irregular-access work, which is precisely the class for which tile staging
buys least. 0243 carries the related claim from a different skill — a SIMT thread reads GM directly where
a SIMD VF must stage through UB — and `Q-950arch-23` records that upstream gives two qualitative lists and
**no crossover point** for when direct access wins. That open question is the same gap this table's third
row leaves, reached from a different document.

What upstream does not supply anywhere in these three files: a latency figure for UB or GM, a crossover
*n*, any statement about access coalescing, any statement about alignment requirements for a `__gm__`
subscript, and any statement of what a direct GM write from many threads to nearby addresses costs.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on `950PR`. The table's three rows need three different arms because they are three
different kinds of claim.

Arm A — row 1, the element-wise case. One SIMT operator (`y[i] = x[i] + 1.0f`) built twice: direct GM, and
staged through a UB tile with `TBuf` and explicit copies. Identical inputs, one die, one session, three
tensor sizes spanning L2-resident to well beyond it (0270's knee is the boundary that matters). Compare
durations. Upstream's reason — "避免不必要的 UB 搬运" — predicts direct wins; the *margin* is the readout.

Arm B — row 3, the crossover. Same operator generalised to read each element *n* times, sweeping *n* over
1, 2, 4, 8, 16. Both variants. The smallest *n* at which staged beats direct is the number the table
implies and does not give. This is the deliverable a tiling routine could actually use.

Arm C — row 2, which is a correctness arm and must not be run as a performance one. Build an intra-core
reduction three ways: partials exchanged through the `TBuf` UB buffer as upstream shows; partials exchanged
through GM with no barrier; partials exchanged through GM with whatever intra-block barrier exists
(`asc_syncthreads`, per 0375 — its identity is unestablished, so the arm records what it does rather than
assuming). Run each 500 times at four thread counts. Record failure rates. §2 predicts the second fails at
higher thread counts.

Arm D — coalescing, which no source mentions and which §2 argues is the missing axis. Repeat Arm A with
three access patterns at fixed element count: contiguous per thread, strided by the thread count
(grid-stride, as upstream's own loop produces), and shuffled. Record durations. A large spread means the
direct-GM idiom has an access-pattern cliff that upstream's "usually" does not warn about; a small spread
means the memory system is absorbing it and the idiom is as robust as the table implies.

Arm E — the UB budget interaction. For the staged variant, record the UB actually reserved and confirm it
against whatever `SetLocalMemorySize` accepted (0377). A staged SIMT kernel competes with the DCache
reservation (0237), and the table's second and third rows send work into a budget the same skill says must
leave at least 32 KB free.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session. Arm C's barrier-free
variant is a race, not a hang, but a watchdog is declared anyway.

## 5 · Checker — acceptance declared before the run
`direct_gm_faster` (Arm A) — duration ratio, staged over direct, per tensor size, never averaged. Pass iff
> 1.0 at every size. A ratio ≤ 1.0 at any size is the OVERTURN for that size class and is the finding.

`staging_crossover_n` (Arm B) — the smallest *n* at which staged wins, per tensor size. Reported, not
gated: upstream states a direction and no threshold, so there is nothing to pass against and the number is
the deliverable. Reported as "no crossover within the swept range" if none is found, rather than
extrapolated.

`gm_exchange_failure_rate` (Arm C) — failing runs out of 500, per exchange method, per thread count.
Reported as a table. Never merged with any duration: row 2 is a correctness claim and reporting it beside a
performance number is how it gets read as advice.

`pattern_spread` (Arm D) — the ratio between the slowest and fastest access pattern at fixed element count.
Reported.

`ub_reserved_bytes` (Arm E) — reported, with the DCache residual it leaves.

The positive fixture, declared before the run: **Arm C's barrier-free GM-exchange variant must fail at
least once** at the highest thread count. If it does not, the reduction has no intra-core race in it and
the UB variant's clean result says nothing about why UB is required — a correctness experiment whose
unsynchronised arm passes has measured nothing. And Arm A must include a control pair built from identical
source with the *same* method, whose durations must agree within run-to-run variance; if two identical
builds differ by more than the effect being measured, the timing harness cannot resolve the comparison and
every ratio in Arms A, B and D is void. Without both, the checker reads only "one build was faster and
nothing crashed", which is the known blind species.

Process exit codes are not the verdict for any arm: Arm C expects wrong values from processes that exit
zero.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no transfer
timed, no reduction raced, no UB reserved, no die contacted. The quoted passages are re-verified file reads
of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that direct GM access is faster, that UB access
has lower latency, or that intra-core sharing through GM is unsafe — Arms A through E are all open, and
upstream supplies **no figure for any of its three reasons**.

**It does not establish a crossover for the multiple-access row.** Upstream says "多次访问" and gives no
*n*; this entry does not manufacture one, and Arm B is what would produce it. `Q-950arch-23` records the
same gap reached from `0243`: two qualitative lists and no crossover point.

It says nothing about access coalescing, burst formation, or alignment requirements for a `__gm__`
subscript from a SIMT thread. No source in scope mentions any of them, and §2's argument that this is the
missing axis is reasoning from the SIMD analogue (0165), not from evidence about SIMT.

It does not establish the intra-core barrier. Row 2 requires threads of one core to exchange data safely,
and what primitive orders them is unestablished: `asc_syncthreads` exists in the toolkit (0375) and no
upstream document in scope names it, its semantics were not read, and the fourteen warp-level primitives
that neighbour it are undocumented anywhere in this material.

It does not establish the UB budget the staged path draws on. 0209, 0238, 0239 and `Q-950arch-04` record
that the usable UB figure is disputed across four documents and never measured, and 0377 records that the
reservation accessor is spelled two ways.

It says nothing about the SIMD half of the `SKILL.md` comparison table, which describes a different
programming model, nor about L0C, which that table mentions and which no SIMT document in scope discusses
again.

BOARD is `family-claimed(unverified)`: the files name no board token this book recognises and no board was
contacted.
