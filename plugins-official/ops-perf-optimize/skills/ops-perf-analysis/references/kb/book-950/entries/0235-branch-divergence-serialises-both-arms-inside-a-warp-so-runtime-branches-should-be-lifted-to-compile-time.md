```
ID:        0235-branch-divergence-serialises-both-arms-inside-a-warp-so-runtime-branches-should-be-lifted-to-compile-time
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (ops/npu-arch). Nothing was compiled and no divergence
           was timed; upstream states the mechanism and supplies no cost figure.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/simt-arch-guide.md:57-70 — "### SIMT 执行语义 / - Warp 内所有线程
           执行**相同指令**（SIMT 语义）/ - 分支发散（Branch Divergence）时串行执行各分支路径 /
           - 若 warp 内部分线程走 if 分支，部分走 else 分支 / - 硬件先执行 if 路径（else 线程等待），
           再执行 else 路径（if 线程等待）/ - 导致流水线气泡，降低有效利用率" and "### 分支发散优化 /
           - 减少同一 warp 内的分支分化 / - 将运行时分支提升到编译期（`if constexpr` / 模板参数）/
           - 同一 warp 内线程尽量走相同执行路径"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a SIMT kernel on a 950 board in which a fully divergent warp (32 distinct branch targets)
           costs no more than a uniform one at the same total work — the serialisation would then not
           occur, and the whole divergence-avoidance discipline is unnecessary.
```

# 0235 · Branch divergence serialises both arms inside a warp, so runtime branches should be lifted to compile time

## 1 · Claim
Upstream asserts SIMT execution semantics: all threads in a warp execute the **same instruction**, and
when threads within one warp take different branches the hardware executes the paths **serially** — the
`if` path first while the `else` threads wait, then the `else` path while the `if` threads wait —
producing pipeline bubbles and reducing effective utilisation. Upstream asserts three mitigations: reduce
branch divergence within a warp, lift runtime branches to compile time using `if constexpr` or template
parameters, and arrange for threads in one warp to follow the same execution path. Not established here:
nothing was compiled and no divergence was timed.

## 2 · The wrong branch this removes
SIMT looks like scalar programming — upstream describes it as 标量编程（线程视角）(0243 §3) — and the
whole point of that abstraction is that a thread can be written as if it were alone. `if (x[i] > 0)` is
the natural expression of a data-dependent condition and it compiles and it is correct.

What it costs is invisible in every ordinary way. A fully divergent warp runs both arms for all 32 lanes,
so a two-way branch costs up to 2× and an N-way switch up to N×, with correct output throughout. The
profile shows a slow SIMT kernel; occupancy looks fine, because the warps *are* resident and *are*
issuing — they are issuing instructions that half the lanes discard. There is no counter in this material
that reports divergence, so the cost is unattributable without knowing the mechanism.

The mitigation upstream names is the one an agent will not reach for on its own. Lifting a branch to
`if constexpr` or a template parameter means generating two kernels and selecting at launch — a
structural change to the operator, made for a reason that is invisible in the source. An agent that does
not know about divergence will never pay that cost, and the regbase side of the same architecture makes
the identical demand for a different reason: the SIMD VF hard constraints forbid runtime `if/else`
outright and require `if constexpr` (0254, constraint 6). So the two programming models converge on the
same rule from opposite directions — SIMD forbids it, SIMT permits it and charges for it — and an agent
that learns it in one place has it for both.

The subtler wrong branch is *where* divergence matters. It is a per-warp property, so a branch that
correlates with a thread index at 32-element granularity costs nothing — all lanes in each warp agree —
while the same branch on a data-dependent predicate costs the full serialisation. Upstream's third
mitigation ("同一 warp 内线程尽量走相同执行路径") is precisely about arranging that correlation, and it
is actionable only if the warp width is known to be 32 (0234). An agent that knows divergence is bad but
not that the quantum is 32 cannot sort its data to avoid it.

## 3 · Ground / Source
`simt-arch-guide.md:43-70`, the Warp 调度机制 section — the semantics and the mitigation, quoted together
because the mitigation is only intelligible given the mechanism:

> ## Warp 调度机制
>
> ### 基本概念
> - 每 **32 个线程** 组成一个 Warp
> - Warp 是硬件调度的最小单位
> - Warp 内每个线程称为 Lane，编号 0~31
>
> ### 硬件调度
> - 每个 AIV 核包含 **4 个 Warp Scheduler**，调度器编号为 `warp_id % 4`
> - 同一时刻一个 AIV 核只执行一个线程块任务
> - 线程块内多个 Warp 被依次调度到 AI Core 执行
>
> ### SIMT 执行语义
> - Warp 内所有线程执行**相同指令**（SIMT 语义）
> - 分支发散（Branch Divergence）时串行执行各分支路径
>   - 若 warp 内部分线程走 if 分支，部分走 else 分支
>   - 硬件先执行 if 路径（else 线程等待），再执行 else 路径（if 线程等待）
>   - 导致流水线气泡，降低有效利用率
>
> ### 分支发散优化
> - 减少同一 warp 内的分支分化
> - 将运行时分支提升到编译期（`if constexpr` / 模板参数）
> - 同一 warp 内线程尽量走相同执行路径

The mechanism is described in unusual operational detail for this material — which path runs first, that
the other threads *wait* rather than idle elsewhere, and that the result is 流水线气泡. That specificity
is what makes the claim falsifiable: it predicts a cost proportional to the number of distinct paths
taken, not merely "divergence is bad".

Upstream supplies **no cost figure**. There is no percentage, no benchmark, and no statement of how much
a two-way divergence costs relative to a uniform warp. So the mechanism is stated and its magnitude is
not, which is why §4's arms are about measuring the slope rather than confirming the sign.

The same guide's contrast table, `npu-arch-guide.md:297-301`, places divergence handling as the
architectural difference between the two models:

> | 维度 | SIMT | SIMD |
> | 控制逻辑 | Warp Scheduler 硬件分支调度 | 软件展开循环 |

硬件分支调度 — the hardware schedules the branch, which is what makes divergence a hardware cost rather
than a compiler one. On the SIMD side there is no divergence because there is no per-lane control flow;
the mask registers (0255) express selection instead, and the SIMD VF constraints forbid runtime branches
altogether (0254).

Note what upstream does *not* say and an agent may assume. It does not say divergence is limited to two
paths — the mechanism generalises to any number of distinct targets in a warp, up to 32. It does not say
whether a divergent branch whose arms are unequal in length costs the sum or the maximum (the description
implies the sum). And it does not say whether the mitigation via `if constexpr` is always available: a
branch on genuinely data-dependent values cannot be lifted to compile time at all, and for those the only
remedy is the third mitigation — arranging the data so warps are uniform.

All quoted material is `ops/npu-arch/` — one origin (RULES.md Art. 3). The warp width of 32 that the whole
claim rests on is 0234, which records that upstream marks the neighbouring scheduler count as a
public-or-experience value and supplies no ini field for either.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion. The claim is
about a cost slope, so the procedure varies divergence and holds total work constant — otherwise it
measures work, not divergence.

Arm A — the divergence staircase, total work held constant. Build one SIMT VF whose body executes exactly
one of N equal-cost arms selected by `threadIdx % N`, with N ∈ {1, 2, 4, 8, 16, 32}. Every lane does the
same amount of arithmetic in every configuration; only the number of distinct paths per warp changes.
Minimum `aiv_time` over 50 repetitions at each N. Under the stated mechanism, time should rise roughly
linearly in N. The **slope** is the readout and it is the figure upstream never supplies.

Arm B — the warp-alignment control, which is what makes Arm A attributable to divergence rather than to
the branch itself. Repeat Arm A with the selector changed from `threadIdx % N` to
`(threadIdx / 32) % N` — the same number of distinct arms across the kernel, but every warp uniform.
Under the mechanism, time should stay flat in N. If Arm B also rises, Arm A was measuring branch overhead
or instruction-cache pressure, and its slope attributes nothing.

Arm C — the compile-time lift, which measures the mitigation rather than the problem. Build the N=2 case
three ways: runtime `if/else`, `if constexpr` with two kernels selected at launch, and a branchless
select. Compare against the uniform baseline. This prices the remedy upstream recommends and would say
whether it recovers the full cost or part of it.

Arm D — the asymmetric-arms question §3 flags as unstated. Build a two-way divergent branch whose arms
differ 10× in cost, and compare against uniform warps running each arm alone. Sum versus maximum is
directly observable and upstream states neither.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. All points of one staircase run on one named die in one
session — a slope assembled across dies attributes nothing. Each N is a separate build if `LAUNCH_BOUND`
must match the launch count (0232); build md5s are recorded and confirmed distinct.

## 5 · Checker — acceptance declared before the run
Verdict variable `divergence_slope`, from Arm A: `aiv_time(N)` divided by `aiv_time(1)`, reported per N,
**gated by Arm B**.

Pass is declared now as: `divergence_slope(N)` increasing monotonically in N and reaching at least 1.5 at
N = 2, **and** Arm B's corresponding ratios staying within run variance of 1.0 across all N. Both clauses
in one predicate. Arm A rising with Arm B also rising is reported as `NOT ESTABLISHED — divergence not
isolated`, never as a pass: the entry's claim is that *intra-warp* divergence costs, and a curve that
rises for warp-uniform branches too is measuring something else.

A slope near 1.0 in Arm A with Arm B flat overturns the entry — the hardware would then not be
serialising — and that is the more valuable outcome, declared now so it cannot be reinterpreted as a
measurement failure.

`lift_recovery` (Arm C) — the fraction of the divergence cost recovered by the `if constexpr` build.
Reported with run variance, no pass threshold; upstream recommends the mitigation and quantifies nothing.

`asymmetric_cost` (Arm D) — whether the divergent time approaches the sum or the maximum of the two arms.
Reported; either answer is a fact upstream does not state.

The positive fixture, declared before the run: Arm A at N = 32 with the selector changed to a *constant*
must collapse to the N = 1 time. If it does not, the N-way body is not being selected at run time at all —
the compiler may have flattened it — and every slope figure is void. A second fixture: run Arm A with the
warp width assumed to be 64 instead of 32 in Arm B's selector (`(threadIdx / 64) % N`). If Arm B stays
flat under that selector too, the warp quantum is not 32 and 0234's premise, on which this entire
procedure rests, is wrong. Without these, the checker reads only "more branches were slower", which is the
known blind species: branch count and divergence are different things and a single curve cannot separate
them.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no branch
was diverged, and nothing was timed. Upstream supplies no cost figure for divergence anywhere in this
scope, so there is not even an upstream measurement to record as upstream text.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that divergence serialises, what it costs, or
that the recommended mitigations recover the cost — Arms A-D are all open, and upstream states the
mechanism with **no magnitude at all**, so there is no number here to be right or wrong about. There is
**no second origin**: all quoted material is one skill, and no ini field or header was consulted — a
control-flow behaviour is not the kind of fact a configuration file expresses. The whole claim rests on
the warp width being 32, which is 0234 and is itself unverified with no ini backing; §4's second fixture
exists because that premise, not this entry's mechanism, is the likelier thing to be wrong. It does not
establish the cost model for more than two paths, nor whether unequal arms cost the sum or the maximum —
upstream's description implies the sum and states neither (Arm D). It does not establish that
`if constexpr` lifting is available for any particular branch: a genuinely data-dependent predicate cannot
be lifted at all, and for those the only remedy is data arrangement, which this entry does not address
beyond quoting upstream's third bullet. It says nothing about the SIMD side, where runtime `if/else` is
forbidden outright (0254) for reasons that are not divergence, and nothing about mask-register selection
(0255), which is the SIMD answer to the same problem. Nothing transfers to the other book (RULES.md Art. 1):
upstream states SIMT hardware does not exist before DAV_3510.
