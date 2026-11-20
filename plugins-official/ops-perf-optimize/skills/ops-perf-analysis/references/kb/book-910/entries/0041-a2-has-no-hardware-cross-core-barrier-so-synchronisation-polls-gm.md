```
ID:        0041-a2-has-no-hardware-cross-core-barrier-so-synchronisation-polls-gm
LABEL:     knowledge
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin, a document declaring itself A2-verified; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:253 — "## 5. 跨核同步（A2 无硬件 barrier）"; ibid:311 — "| Cross-core sync | 无硬件 barrier | GM 轮询实现 |"; ibid:146 — "FullBarrier()  // ~200μs GM 轮询，DMA 同时完成"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a hardware cross-core barrier primitive is shown to exist and work on a named Atlas A2 board, or a GM-polling FullBarrier is measured at a cost far from the ~200 µs quoted.
```

# 0041 · A2 has no hardware cross-core barrier, so synchronisation polls GM

## 1 · Claim
Upstream asserts that Atlas A2 has no hardware cross-core barrier and that global synchronisation
is implemented by polling GM: every core writes a cookie to a GM flag slot, and core 0 spins
reading each slot until all match, with a broadcast variant in the reverse direction. Upstream
quotes a FullBarrier at about 200 µs. Not established here.

## 2 · The wrong branch this removes
Multi-pass algorithms over data larger than UB — histogram levels, binary-search steps, any
two-phase reduction — need a global sync per pass, and an agent designing one prices it as
negligible because on most parallel machines a barrier is cheap. At ~200 µs it is not: a 16-step
binary search spends 3.2 ms in barriers alone, which can exceed the compute. The design consequence
is concrete and upstream states it — prefer algorithms with fewer synchronisation points, and move
less data per barrier (upstream's example: 1 count per step instead of a 256-bin histogram).

The second branch is the one an agent cannot recover from cheaply: choosing a multi-level histogram
(4–6 barriers) over a 16-step binary search looks right on barrier count and is wrong on total time,
because the histogram's scalar tail costs more than eleven extra barriers. Barrier count alone is
not the objective; upstream's own ladder (0049) shows the binary search winning despite more
barriers.

The third: a barrier that costs 200 µs is long enough to hide a DMA behind, which upstream exploits
(line 141: "在 FullBarrier（GM 轮询）期间，其他管道空闲。可在 barrier 前发起 DMA prefetch"). An
agent that treats the barrier as an atomic blocking call leaves that free prefetch unused.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md` §5, heading at line 253:
"## 5. 跨核同步（A2 无硬件 barrier）", with the implementation at lines 255-263, verbatim:
```
// FullBarrier: 所有 core → core 0
每个 core: 写 cookie 到 GM flags[step][bid]
Core 0:    for each core: while (GM[step][c] != cookie) { DMA read + poll }

// BroadcastBarrier: core 0 → 所有 core
Core 0:    写 cookie 到 GM flags[step][C]
其他 core: while (GM[step][C] != cookie) { DMA read + poll }
```
The A2 hardware summary, line 311: `| Cross-core sync | 无硬件 barrier | GM 轮询实现 |`.
The cost, line 146, inside the barrier-overlap pattern:
`FullBarrier()                              // ~200μs GM 轮询，DMA 同时完成`.
The optimisation guidance, lines 265-268: "- 减少 barrier 次数（二分搜索 16 步 vs 多级直方图 4-6
步）- 每步 barrier 只传 1 个 count（vs 256-bin 直方图）- Workspace layout 复用".

**This document's scope, and why it is the best 910 evidence in the repo.** Line 5: "> **当前覆盖
范围**：本文档基于 **A2 大规模数据** 实战验证；A3、A5 等架构的硬件细节差异需另行验证后再套用。"
It declares itself A2-verified and explicitly refuses to extend to A3 — a refusal this book treats
as a finding in its own right (0047). Its 适用架构 marking in
`ops/ascendc-performance-best-practices/SKILL.md:34` is "DAV_2201 / DAV_3510".

**A different upstream statement, apparently in tension**:
`ops/ascendc-performance-analysis/references/metrics_reference.md` §8.2, headed "核间同步（Atlas
A2/A3）" at line 438, describes three cross-core synchronisation modes and the
`CrossCoreSetFlag`/`CrossCoreWaitFlag` API with a flagId counter limited to 15 settings (line 448).
So A2 does have *some* cross-core flag mechanism. Whether "无硬件 barrier" means no *global*
barrier primitive (compatible with per-flag signalling existing) or something stronger is not
determined by either text. Filed as `harvest/contradictions-910.md` **C-910-009** and named in this
book's STANDING_QUESTIONS as Q-910-13; resolved by §4 arm 4 below, never by preferring either author
(RULES.md Art. 7).

Both statements are the same repo: one origin (STRATA S2).

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; refuse substitution. Record `GetCoreNumAiv()` rather
   than assuming it (0009, 0011).
2. Cost arm: a kernel doing nothing but `N` FullBarriers, `N` swept over 1, 10, 100, with all cores
   participating. Time per barrier is the slope, not the intercept — taking a single-barrier
   measurement would fold in launch overhead (0055, ~20 µs on A2, which is 10 % of the quoted
   barrier cost and not negligible).
3. Core-count arm: barrier cost at 2, 8, 24, 48 cores. GM polling by one core over `C` slots should
   scale with `C`; a flat cost would indicate something other than serial polling.
4. Capability arm: attempt `CrossCoreSetFlag`/`CrossCoreWaitFlag` in mode 0 (documented as
   all-AIC or all-AIV synchronisation) and time an equivalent global sync. This is the arm that
   addresses the tension in §3 — if mode 0 gives a working global barrier at lower cost, "无硬件
   barrier" is wrong or means something narrower, and that is the finding.
5. Five repeats each, first discarded.

## 5 · Checker — acceptance declared before the run
Verdict variable `barrier_us`, the slope of total time against barrier count at full core count.
PASS iff `barrier_us` lies in [100, 400] — a factor-of-two window around the quoted 200 µs,
declared now, wide because upstream's figure carries no conditions at all.
`barrier_scaling`: reported with no declared expectation; a slope in core count supports the serial
polling model and a flat response contradicts it, and the entry is corrected either way.
`crosscore_us` from arm 4: if a hardware flag path achieves a global sync at less than half
`barrier_us`, §1 is corrected — the claim becomes "the GM-polling barrier is what this
implementation used", which is much weaker than "A2 has no hardware barrier", and the difference
matters to every consuming agent.
The intercept from arm 2 must be reported alongside the slope and must be consistent with the
launch overhead of 0055. If it is not, the timing method is suspect and the slope is not trusted —
that consistency check is what stops this from being a measurement that confirms only itself.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched by this book. BOARD is `family-claimed(unverified)`: the
source says "A2", which is a product line spanning Ascend910B1–B4 and 910B2C, not a board — and
`form/CONVENTIONS.md` has no token for a product line. Upstream's own A2 result therefore does not
name a board either. This entry does not resolve the tension with the `CrossCore*` API (§3). The
~200 µs figure carries no core count, no board, no tool and no repeat count, so it is a magnitude,
not a number to model with. It does not establish anything for A3 (Ascend910_93) — the source
explicitly declines to, and 0047 records that refusal.
