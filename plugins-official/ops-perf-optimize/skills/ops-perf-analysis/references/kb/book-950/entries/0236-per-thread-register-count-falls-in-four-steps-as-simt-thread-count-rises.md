```
ID:        0236-per-thread-register-count-falls-in-four-steps-as-simt-thread-count-rises
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (ops/npu-arch); the SIMT register file it partitions is
           itself marked by upstream as a public-or-experience value with no ini field (0206 row 1).
           Nothing was compiled and no register pressure was observed.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/simt-arch-guide.md:259-268 — "`__launch_bounds__(N)` 限定每个 VF
           Block 使用的最大线程数，线程数直接影响每线程可用寄存器数：| 线程数范围 | 每线程可用寄存器数 |
           | 1025~2048 | 16 | | 513~1024 | 32 | | 257~512 | 64 | | 1~256 | 127 |"
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:166 — "| 1 | SIMT Register File 128KB |
           Guide §5 SIMT vs SIMD | 公开资料 / 经验值 |"   # upstream's own unverified marker
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a SIMT kernel whose per-thread live-variable count sits between two rungs and shows no
           spill at the higher thread count — or a measured spill onset at a thread count other
           than 256, 512 or 1024.
```

# 0236 · Per-thread register count falls in four steps as SIMT thread count rises

## 1 · Claim
Upstream asserts that `__launch_bounds__(N)` bounds the maximum threads per VF block and that the
thread count directly determines how many registers each thread may use, in four discrete bands:
1-256 threads → 127 registers, 257-512 → 64, 513-1024 → 32, 1025-2048 → 16. Upstream asserts that
variables exceeding the register budget spill to stack and that this costs performance. Not
established here: nothing was compiled and no spill was observed.

## 2 · The wrong branch this removes
This is the mechanism that makes 0232's pairing rule matter, and without it the two rules look like
bookkeeping. The bands are steep — a step from 1024 to 1025 threads halves the per-thread budget from
32 registers to 16 — and the boundaries sit exactly at the round numbers a person picks. An agent
tuning thread count upward "to hide memory latency", which is upstream's own advice for copy-bound
operators (0232 §3), crosses a boundary and the kernel's inner loop starts spilling. Wall time may go
*up* while occupancy goes up, and nothing reports that registers were the cause.

The specific silent failure is the `LAUNCH_BOUND`/`Dim3` mismatch: the register allocator budgets
from `LAUNCH_BOUND(N)` and the hardware launches `Dim3(M)` threads. Declaring 512 and launching 1024
means threads allocated 64 registers each are running where 32 are available. Upstream forbids the
mismatch (0232) but does not say it is enforced, so this entry supplies the reason the rule exists
rather than restating it.

The second branch is inverted and just as costly. An agent that keeps the 1024 default for a
register-heavy compute kernel is at 32 registers per thread; dropping to 512 threads doubles the
budget to 64 and may remove the spill entirely at half the parallelism. Upstream's own complexity
table (§3) recommends exactly that for ND runtime loops, dropping as far as 256 threads for
`uint32_t` indices and 128 for `uint64_t`. An agent that treats thread count as "more is better"
cannot find that trade, because the losing side of it is invisible.

Note what the bands imply about the register file: 256 × 127 ≈ 512 × 64 ≈ 1024 × 32 ≈ 2048 × 16 ≈
32768 registers in total. If registers are 4 bytes, that is 128 KB — which is exactly the SIMT
Register File size upstream states elsewhere and marks as unverified (0206 row 1). The arithmetic
closing is a consistency check on upstream's own numbers, not independent evidence, and it is stated
here as such.

## 3 · Ground / Source
`simt-arch-guide.md:257-285`, the `LAUNCH_BOUND` section, quoted whole because the table and the
usage rule are one unit:

> ## LAUNCH_BOUND 与寄存器数量
> ### 寄存器数量映射
> `__launch_bounds__(N)` 限定每个 VF Block 使用的最大线程数，线程数直接影响每线程可用寄存器数：
>
> | 线程数范围 | 每线程可用寄存器数 |
> |-----------|-----------------|
> | 1025~2048 | 16 |
> | 513~1024 | 32 |
> | 257~512 | 64 |
> | 1~256 | 127 |
>
> ### 使用原则
> - 寄存器用于存储线程局部变量
> - 超出寄存器容量则栈溢出，影响性能
> - 建议 `__launch_bounds__(N)` 的 N 与实际启动线程数一致
> - `LAUNCH_BOUND(N)` 和 `Simt::Dim3(N)` 必须使用同一个编译期常量

and the tuning table at `:293-303`, which is the part that turns the bands into advice:

> ### 寄存器压力与线程数调优
> 寄存器压力随 VF 复杂度增加而增大：
>
> | VF 复杂度 | uint32_t 索引线程数 | uint64_t 索引线程数 |
> | 极低（NONE/1D） | 1024 | 512 |
> | 中低（2D） | 1024 | 512 |
> | 中等（3D） | 1024 | 512 |
> | 较高（4D） | 1024 | 512 |
> | 最高（ND运行时循环） | 256 | 128 |

Two things are worth reading off that table rather than past it. First, the `uint64_t` column is
uniformly half the `uint32_t` column — index width alone costs a full band, which is a concrete reason
to prefer 32-bit indices in a SIMT VF and is stated nowhere else in this scope. Second, four of the
five complexity rows give the same answer; only the ND-runtime-loop row moves. So the guidance is
effectively binary — 1024 unless you have a runtime-shaped loop — and an agent that reads it as a
graded scale is over-reading it.

The register file this partitions, `npu-arch-guide.md:303`: "| 寄存器组织 | 128 KB 寄存器堆，按线程
并发数切分 [¹](#unverified) | 多条 VL=256 B 矢量寄存器 |", with the footnote pointing at
`npu-hardware-params.md:166`, row 1 of the 公开资料/经验值 table. Upstream is explicit that no
installed INI field supplies it. A `grep` over the installed CANN 9.0.0-beta.2 ini set for
register-file fields returned nothing, consistent with that statement and establishing nothing.

`simt-arch-guide.md:85-89` states the stack consequence from the memory-space side: "每个线程独享一组
寄存器 / 寄存器数量受线程数影响 / 超出寄存器容量的变量会栈溢出". Both files are `ops/npu-arch/` — one
origin (RULES.md Art. 3).

Upstream gives no accessor for the current per-thread register count and no diagnostic for spill. That
absence is what makes §4 indirect.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion. There is no
API for register count, so every arm infers it from an observable, and each is designed so nothing
else could produce the signal.

Arm A — the band boundaries, by a spill staircase. Build a SIMT VF whose body holds exactly `k` live
scalar variables across a long dependent chain, with `k` a compile-time parameter, and no memory
traffic beyond one load and one store. For fixed `k`, sweep `LAUNCH_BOUND`/`Dim3` (matched, per 0232)
over 256, 257, 512, 513, 1024, 1025, 2048, taking minimum `aiv_time` over 50 repetitions at each.
Under the table, a `k` of 20 should run flat up to 1024 and jump at 1025; a `k` of 40 should jump at
513; a `k` of 100 should jump at 257. The **positions** of the jumps are the readout, not the times.

Each point is a separate build because `LAUNCH_BOUND` is compile-time; build md5s are recorded and
confirmed distinct, or the sweep is void.

Arm B — the budget, by a live-variable staircase. Fix the thread count at 1024 and sweep `k` upward
from 8, looking for the `k` at which wall time first departs from linear. Under the table that
departure is at `k` ≈ 32. Repeat at 512 threads, expecting ≈ 64. Two thread counts, because a single
one cannot distinguish "the budget is 32" from "this kernel gets slower past 32 variables for some
other reason".

Arm C — the disassembly arm, which is the only direct evidence available and needs no device. For each
Arm B point, disassemble the kernel and count stack load/store instructions in the inner loop. Spill
onset in the instruction stream is unambiguous where a timing knee is not. This arm should run first:
it is cheap, it is decisive about *whether* spill occurs, and it makes Arm B's knees attributable.

Arm D — the mismatch arm, which tests §2's silent failure. Build `LAUNCH_BOUND(512)` with `Dim3(1024)`
and compare output bits and `aiv_time` against a matched `LAUNCH_BOUND(1024)`/`Dim3(1024)` build at
identical shape, on the same die in the same session. Correct-but-slower is the predicted outcome and
would confirm the mechanism; differing bits would be a more serious and different finding.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All points of one staircase run on one named
die in one session.

## 5 · Checker — acceptance declared before the run
Two verdict variables, kept apart, plus a gate.

`band_edges` (Arm A) — the set of thread counts at which wall time steps up, across the three `k`
values. Pass iff it equals {257, 513, 1025} with each edge appearing for the predicted `k`. An edge
at a thread count not in that set corrects the table in place and is logged with its `k`.

`budget[N]` (Arm B) — the live-variable count at which spill begins, per thread count. Pass iff
`budget[1024] ∈ [30, 34]` and `budget[512] ∈ [60, 68]`. Bands rather than exact values, because the
compiler reserves some registers for its own use and the observable is the *user-visible* budget, not
the architectural one — a measured 30 against a stated 32 is agreement, not a miss, and saying so now
prevents it being read either way afterwards.

The gate: both verdicts are `NOT ESTABLISHED` unless Arm C's disassembly shows stack traffic appearing
at the same points. A timing knee without corresponding spill instructions is measuring something
else, and this entry's claim is specifically about registers. That gate is the design of the checker,
not a formality — Arm A and Arm B are both indirect, and a knee has many ordinary causes.

The positive fixture, declared before the run: run Arm B with `k` forced to 8 at every thread count.
No spill instruction may appear in any disassembly and no knee may appear in any timing. If spill
appears at `k` = 8, the counter is matching instructions that are not spills and every `budget` value
it produced is void. Without this the checker only reads "stack traffic was found", which is the known
blind species.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
disassembly was inspected, and no thread was launched. The register-file arithmetic in §2 (four bands
multiplying to ≈32768 registers ≈ 128 KB) is arithmetic over two upstream figures performed here; it
checks upstream against itself and is not an observation.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish the band table or the register-file size — both are
upstream assertions, and upstream marks the 128 KB file as a public-or-experience value with no ini
field behind it (0206). There is **no second origin**: both quoted files are `ops/npu-arch/`, and the
installed toolkit supplies nothing here, unlike the buffer constants (0209-0216). It does not
establish that the bands are hardware partitions rather than a compiler policy; a toolchain could
implement the same schedule and a later toolchain could change it, and nothing in this scope
distinguishes those. It does not establish that spill is the *only* cost of crossing a band, nor that
127 registers are actually reachable at 256 threads — the compiler's own reservations are unaccounted
for, which is why §5 uses bands. It says nothing about vector registers: `RegTensor` and VL (0219)
belong to the SIMD-Regbase side, are a different resource, and are not partitioned by thread count.
It says nothing about the warp granularity of 32 (0234) interacting with the band edges at 256/512/
1024, all of which are multiples of 32 — whether the edges are warp-derived is not addressed.
Upstream's complexity table is quoted as guidance and no part of it is tested. Nothing transfers to
the other book (RULES.md Art. 1): SIMT hardware does not exist before DAV_3510 per upstream.
