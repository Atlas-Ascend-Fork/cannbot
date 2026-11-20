```
ID:        0060-crosscorewaitflag-on-mte2-inflates-the-ratio-and-a-0.1-gap-declares-it-polluted
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/bound_diagnosis.md:68 — "MC² 通算融合算子中，`CrossCoreWaitFlag` 通常挂在 AIC 的 MTE2 流水线上等待 AIV 通信完成。这会导致 profiling 中 `aic_mte2_ratio` **含通信等待空转**，而非真实访存瓶颈"
           ops/ascendc-perf-optimize/references/comm-compute/bound_diagnosis.md:76 — "若 ratio_full - ratio_pure > 0.1（或 ratio_pure / ratio_full < 0.8） → mte2_polluted = true"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured MC² case on a named 950 board where the full and compute-only builds show the
           same `aic_mte2_ratio` within run spread while communication demonstrably waits — the
           wait would then not be charged to MTE2, and the pollution test would be measuring
           something else.
```

# 0060 · CrossCoreWaitFlag on MTE2 inflates the ratio, and a 0.1 gap declares it polluted

## 1 · Claim
Upstream asserts that in MC² fused operators the `CrossCoreWaitFlag` by which AIC waits for AIV's
communication is usually attached to AIC's MTE2 pipeline, so the profiled `aic_mte2_ratio` includes
idle waiting rather than real memory pressure; that the isolation test's compute-only build
(communication commented out) is naturally free of that wait, so comparing the two gives a
pollution test — `ratio_full − ratio_pure > 0.1`, or equivalently `ratio_pure / ratio_full < 0.8`,
sets `mte2_polluted = true`; and that when polluted, single-core bound diagnosis must not route to
the memory page, because memory optimisation does nothing for communication idling, and must instead
route to the communication-masking strategies. Not established here.

## 2 · The wrong branch this removes
This is the wrong branch the whole single-core routing tree would otherwise take, and it is the one
case in this skill where a ratio is declared untrustworthy by construction rather than by threshold.
The tree (0005) routes a high MTE2 ratio to `memory.md`, whose techniques all reduce or reorganise
transfers. On an MC² operator the number is high because a core is waiting for another card, so
every technique on that page is inapplicable — and worse, they are not inert: merging copies and
changing tiling on a communication-bound operator moves the split that the balancing analysis is
about to compute.

The pollution test is also the cheapest thing in the MC² chain: the compute-only build already
exists for R (0059), so the check is one extra column from data already captured. An agent that
skips it has no way to know whether the ratio it is reading means anything.

## 3 · Ground / Source
`bound_diagnosis.md:64-92`, the MC² 场景 MTE2 污染判定 section. The mechanism is quoted in SOURCE; the
test is stated as three steps at `:70-79`:

> 隔离测试 Step 2（纯计算，通信已注释）的 profiling 数据天然排除了通信等待。通过对比完整算子与纯
> 计算的 MTE2 ratio，可判定是否被污染：
> Step 1 — 取完整算子 profiling 的 aic_mte2_ratio（含通信等待）
> Step 2 — 取隔离测试 Step 2（纯计算）profiling 的 aic_mte2_ratio（无通信等待）
> Step 3 — 判定：若 ratio_full - ratio_pure > 0.1（或 ratio_pure / ratio_full < 0.8）
>          → mte2_polluted = true，MTE2 ratio 被通信等待污染；否则 → mte2_polluted = false

Routing consequence, `:81-84`: 核内 Bound 诊断**不应**路由到 `single-core-pipeline/memory.md`
（访存优化策略对通信等待空转无效）, and should instead route to `comm-compute/`'s masking strategies
(local_matmul, pipeline_balancing) 通过消除/减少通信等待来降低 MTE2 占比. Output fields, `:86-92`:
`mte2_polluted`, `mte2_ratio_full`, `mte2_ratio_pure`.

The single-core half carries the same rule from the other side: `index.md:13-18` makes it Step 0 of
bound routing, before any lane comparison — 若算子为 MC² 通算融合（存在 CrossCoreWaitFlag 挂在 MTE2
流水线上），须先用隔离测试判定 MTE2 ratio 是否被通信等待污染 — with the two-way branch on
`mte2_polluted`; and `memory.md:11` repeats the warning at the top of the page the routing would
otherwise reach, ending 若 `mte2_polluted = true`，本文档策略无效.

Two details a consumer must not lose. The two stated forms of the test are not equivalent: a
difference of 0.1 and a ratio of 0.8 coincide only at `ratio_full = 0.5`; below that the difference
test is stricter, above it the ratio test is. Neither is given precedence. And the ratio named here
is `aic_mte2_ratio` — the AIC side — while the single-core routing tree and its severity ladders are
stated over `aiv_*` ratios (0015, 0016); the two families are not the same measurement.

## 4 · Procedure
Later phase, needs one card per rank. Capture per 0057, isolation per 0059.
1. Device selection per 0057: explicit device list, board token per rank from the driver, occupancy
   recorded before and after.
2. From the isolation campaign of 0059, extract `aic_mte2_ratio` for the full build and the
   compute-only build, per rank, at three problem sizes chosen so that `ratio_full` lies below,
   near and above 0.5 — that is where the two forms of the test disagree.
3. Independently establish whether communication is in fact waiting, without using the MTE2 ratio:
   from the trace, measure the AIC idle interval bracketed by `CrossCoreWaitFlag`, or vary the
   communication volume at fixed compute and observe whether `ratio_full` tracks it.
4. Compute both forms of the test at every size and record where they disagree.

## 5 · Checker — acceptance declared before the run
Verdict variables `gap = ratio_full − ratio_pure`, `frac = ratio_pure / ratio_full`,
`polluted_gap`, `polluted_frac` (the two tests' verdicts), and `wait_observed` from the independent
measurement in step 3. Acceptance of the test as a detector: `polluted_gap` agrees with
`wait_observed` at every size. The disagreement between the two forms is reported as its own result —
if they differ at any size, the replacement must pick one and say which.

Exit code is not the verdict. Both ratios are published per rank; a rank whose compute-only build
shows a *higher* MTE2 ratio than the full build (negative gap) is reported rather than clamped,
since that would indicate the isolation edit changed the memory behaviour of the compute phase, which
is 0059's closure problem showing up here.

Red input: a non-MC² single-card operator run through the same test. Its gap must be near zero. If
the test declares an operator with no cross-core wait to be polluted, it is measuring build
differences rather than communication wait, and no MC² verdict from it is admissible.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. The 0.1 and 0.8 thresholds have no derivation, no board and no case identity, and
the two forms are not equivalent. It does not establish that `CrossCoreWaitFlag` sits on the MTE2
pipeline — that is asserted, and it may differ by pattern (0064's Pattern A and B synchronise in
opposite directions) or by CANN version. It says nothing about pollution of other ratios by the same
wait, nor about the AIV side, where `BarrierAll` waiting must land somewhere too. No board token is
established.
