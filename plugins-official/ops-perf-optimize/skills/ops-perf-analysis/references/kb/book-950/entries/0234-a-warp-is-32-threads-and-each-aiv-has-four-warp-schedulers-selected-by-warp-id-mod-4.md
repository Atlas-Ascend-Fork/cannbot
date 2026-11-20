```
ID:        0234-a-warp-is-32-threads-and-each-aiv-has-four-warp-schedulers-selected-by-warp-id-mod-4
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (ops/npu-arch, restated in ascendc-simt-api-reference,
           same repo). Upstream ITSELF marks the scheduler count as a public-or-experience value
           with no ini field behind it (0206 row 9). No device was contacted.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/simt-arch-guide.md:33-39 — "- 内部按 **32 线程** 分组形成 warp /
           - Warp 是硬件调度的最小单位 / - 每个 AIV 核包含 4 个 Warp Scheduler，调度器编号为
           `warp_id % 4` / - 同一时刻一个 AIV 核只执行一个线程块任务 / - 线程块内多个 Warp 被依次调度执行"
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:174 — "| 9 | Warp Scheduler 每 AIV 4 个 |
           Guide §5 SIMT vs SIMD | 公开资料 / 经验值 |"   # upstream's own unverified marker
SOURCE:    ops/ascendc-simt-api-reference/references/overview.md:3 — "每32个线程组成一个Warp，
           Warp内每个线程称为Lane（编号0~31）。"   # same repo — ONE origin (RULES.md Art. 3).
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a thread-count sweep on 950PR in which throughput steps at a granularity other than 32,
           or in which a block of 4 warps does not run measurably concurrently while 5 warps do
           show serialisation — either breaks the 32-lane warp or the four-scheduler count.
```

# 0234 · A warp is 32 threads and each AIV has four warp schedulers selected by `warp_id % 4`

## 1 · Claim
Upstream asserts that SIMT threads are grouped by hardware into warps of **32**, that the warp is the
smallest unit of hardware scheduling, that each AIV core contains **4** warp schedulers with the
scheduler chosen as `warp_id % 4`, that an AIV executes only one thread-block task at a time, and
that the warps within a block are dispatched in sequence. Upstream calls each thread within a warp a
Lane, numbered 0-31. Not established here: no device was contacted and nothing was timed.

Upstream itself marks the scheduler count as unverified: `npu-hardware-params.md:174` lists
"Warp Scheduler 每 AIV 4 个" as row 9 of its 公开资料/经验值 table (0206), meaning no field in the
installed INI supplies it. The warp width of 32 carries no such marker but has no ini field either.

## 2 · The wrong branch this removes
The warp width is the alignment quantum of the whole SIMT model, and it propagates upward into
tiling. Upstream's own core-split rule requires the per-core element count to be warp-aligned (0240);
an agent that does not know the number cannot satisfy the rule, and an agent that guesses 64 — the
fp32 VL lane count on this part (0219) — aligns to the wrong quantity entirely. Those two
numbers describe different machines: 64 is how many fp32 elements one *SIMD vector register* holds,
32 is how many *SIMT threads* the scheduler dispatches together. They are adjacent in the material
and unrelated in the hardware.

The consequence of a wrong warp width is not a fault. A per-core count of 48 elements occupies two
warps and leaves half the second idle; the kernel is correct and runs at three-quarters efficiency,
with a profile that shows full occupancy on the warps that ran.

The four-scheduler figure has a different consumer. It bounds how much warp-level parallelism a
single AIV can actually overlap, which is what makes "more threads hide memory latency" true up to a
point and false past it. An agent that reads only "2048 threads maximum, use more to hide latency"
(0232) has no model for where the returns stop; `4 schedulers × 32 lanes` is the shape of that model.
Since upstream flags the 4 as unverified, the honest posture is that the *shape* is known and the
*number* is not.

`warp_id % 4` matters for a third reason: it makes scheduler assignment deterministic and
non-configurable. There is no affinity knob to get wrong, which is worth knowing before someone looks
for one.

## 3 · Ground / Source
`npu-arch/references/simt-arch-guide.md:31-39`, the Warp 调度 block, and `:43-63`, the mechanism
section, which restates it and adds the execution semantics:

> ### Warp 调度
> - 内部按 **32 线程** 分组形成 warp
> - Warp 是硬件调度的最小单位
> - 每个 AIV 核包含 4 个 Warp Scheduler，调度器编号为 `warp_id % 4`
> - 同一时刻一个 AIV 核只执行一个线程块任务
> - 线程块内多个 Warp 被依次调度执行
>
> ## Warp 调度机制
> ### 基本概念
> - 每 **32 个线程** 组成一个 Warp
> - Warp 是硬件调度的最小单位
> - Warp 内每个线程称为 Lane，编号 0~31
> ### 硬件调度
> - 每个 AIV 核包含 **4 个 Warp Scheduler**，调度器编号为 `warp_id % 4`
> - 同一时刻一个 AIV 核只执行一个线程块任务
> - 线程块内多个 Warp 被依次调度到 AI Core 执行

The three-level hierarchy at `:13-17` places the warp: block count is a tiling-side `SetBlockDim`,
thread count is a kernel-side `constexpr` (0232), and the warp is 硬件自动分组 — nobody sets it. That
is why there is no API for it and why it can only be observed indirectly.

`npu-arch-guide.md:305` lists the scheduler among the SIMT-only hardware with the unverified footnote
attached: "**SIMT 独有硬件**（DAV_3510 新增）：Warp Scheduler（每 AIV 4 个）[¹](#unverified) /
SIMT Register File / SIMT DCache（最大 128KB，复用 UB 作 Cacheline，128B 粒度）[¹]", and
`npu-hardware-params.md:174` is the row that footnote points at. Upstream is being explicit that this
number came from public material or engineering experience rather than from a configuration field —
which is exactly the disclosure 0206 exists to preserve, and it is why this entry does not reach for a
second origin: there is none to reach for. A `grep` over the installed CANN 9.0.0-beta.2 ini set for
warp- or scheduler-related fields returned nothing, consistent with upstream's own statement and
establishing nothing.

`ascendc-simt-api-reference/references/overview.md:3` states the warp width from the API side:
"SIMT API基于AI Core硬件能力，通过 `AscendC::Simt::VF_CALL` 启动SIMT VF子任务。每32个线程组成一个Warp，
Warp内每个线程称为Lane（编号0~31）。" Same repo — one origin (RULES.md Art. 3).

Note the asymmetry within upstream's own marking: the warp width of 32 is stated in three places and
marked unverified in none, while the scheduler count of 4 is stated in the same sentences and marked
unverified. Either the 32 has a source upstream did not name, or the marking is incomplete. Nothing
here resolves that, and §4 tests them separately for that reason.

The one downstream consumer of the warp width found in this scope is
`ascendc-simt-tiling-design/references/guide.md:20` — "单核最少处理元素数需要对 warp (即 32) 进行对齐"
(0240). So the number is load-bearing in tiling, not merely descriptive.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion.
**Correction 2026-08-24 (found by the 950-remainder miner, applied by the controller):** an earlier
form of this section said neither quantity has an accessor. The warp width DOES have one —
`GetWarpSize()` is declared at `kernel_simt_common_intf.h:28` in the installed toolkit, and
`warpSize` appears as a default argument to four shuffle primitives. What stands: no ini field
behind it, and never measured — the accessor's return value is itself an upstream claim until Arm A
runs, so the staircase below remains the establishing procedure, with `GetWarpSize()` read at the
start as one more recorded input. The scheduler count still has no accessor; both arms of Arm D
remain indirect.

Arm A — the warp width, by a thread-count staircase. Build one trivial SIMT VF (each thread writes
one element, no divergence, no memory reuse) and launch it at thread counts 1, 2, 4, 8, 16, 32, 33,
64, 65, 96, 97 on a single block, taking the minimum `aiv_time` over 50 repetitions at each. Under a
32-lane warp, wall time should be flat from 1 to 32 and step at 33, 65, 97 — the signature of a
granularity, not of a slope. The step positions are the readout; the absolute times are not.

Because `LAUNCH_BOUND` must match the launch count (0232), each point is a separate build. The build
md5s are recorded and confirmed distinct, or the sweep is void.

Arm B — the scheduler count, by an occupancy staircase. Launch at 32, 64, 96, 128, 160 threads
(1 to 5 warps) on a single block with a workload whose per-thread cost is dominated by a long
dependent chain, so that concurrency shows up as flat wall time rather than as bandwidth. Under four
schedulers, 1-4 warps should cost about the same and 5 warps should cost about twice one warp. The
knee position is the readout.

Arm C — the discriminating control for Arm B, and the arm that makes it attributable. Repeat Arm B
with a memory-bound body instead of a compute-bound one. If the knee moves, Arm B was measuring
bandwidth saturation rather than scheduler count, and its number means nothing. A knee that stays at
4 across both bodies is the result.

Arm D — `warp_id % 4`, if any observable exposes scheduler identity. Absent an accessor, the
falsifiable form is negative: launch four warps and check that no permutation of block assignment
changes throughput, which is what a fixed modulo mapping predicts and an affinity-configurable
scheduler would not.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All points of one staircase run on one named
die in one session — a staircase assembled from runs on different dies carries no attribution at all.

## 5 · Checker — acceptance declared before the run
Two verdict variables, kept apart because upstream's confidence in the two numbers differs and the
entry should not let one carry the other.

`warp_lanes` (Arm A) — the smallest thread count at which wall time first steps up, minus one. Pass
iff it equals 32. Declared now: a value of 64 does not pass and specifically indicates the confusion
named in §2, since 64 is the fp32 VL lane count on this part (0219); the entry would be corrected in
place and the collision logged.

`scheduler_count` (Arm B, gated by Arm C) — the number of warps that run before the first knee. Pass
iff it equals 4 **and** Arm C's knee is at the same position. If the two bodies knee at different
points, the verdict is `NOT ESTABLISHED — knee is workload-dependent`, never a pass. That gate is the
whole design of this checker: a single staircase showing a knee at 4 is compatible with four
schedulers, with four outstanding memory requests, and with several other fours.

The positive fixture, declared before the run: run Arm A with the VF body made deliberately divergent
so that every thread takes a different branch (0235). The staircase must *disappear* — wall time
should rise smoothly with thread count rather than in steps of 32. If the steps survive, the harness
is measuring launch overhead rather than warp granularity, and every `warp_lanes` value it produced
is void. Without this, the checker only reads "the curve had steps", which is the known blind
species.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no
thread was launched, and nothing was timed. The ini search reported in §3 found no warp- or
scheduler-related field; a search that finds nothing establishes nothing about the hardware, and it
is recorded only because it agrees with upstream's own statement that no such field exists.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish the warp width or the scheduler count — it records
that upstream states them and that upstream marks one of the two as having no configuration field
behind it. There is **no second origin**: all three quoted files are one repo, and the installed
toolkit supplies nothing here, unlike the buffer constants (0209-0216) where it does. It does not
establish that "one thread-block task at a time per AIV" holds, nor what happens to a block whose
thread count is not a multiple of 32 — upstream states neither, and the partial-warp question is the
one a tiling routine most needs answered (0240). It says nothing about divergence cost, which is
0235 on separate upstream evidence. It says nothing about how warps interact with the DCache
reservation (0237) or with per-thread register allocation (0236), both of which are per-thread
properties whose aggregate is per-warp and neither of which is derived here. `warp_id % 4` is quoted
and not tested beyond the negative form in §4 Arm D. Nothing transfers to the other book (RULES.md Art. 1):
upstream states SIMT hardware does not exist on architectures before DAV_3510, so there is no
corresponding claim to make there.
