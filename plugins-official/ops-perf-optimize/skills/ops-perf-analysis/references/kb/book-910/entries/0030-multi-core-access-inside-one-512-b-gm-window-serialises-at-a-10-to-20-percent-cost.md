```
ID:        0030-multi-core-access-inside-one-512-b-gm-window-serialises-at-a-10-to-20-percent-cost
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured, and no architecture is stated
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:407 — "| GM 同地址访问 | 512B 范围内多核串行化，性能降 10–20% | 错峰访问或改变切分方向 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a multi-core sweep on a named DAV_2201 board shows no timing difference between cores whose GM accesses share a 512 B window and cores whose accesses are spread across windows.
```

# 0030 · Multi-core access inside one 512 B GM window serialises at a 10–20 % cost

## 1 · Claim
Upstream asserts that when several cores access GM addresses falling within one 512 B range, the
accesses serialise and performance drops by 10–20 %, and that the remedies are staggering the
accesses in time or changing the split direction. Upstream separately asserts, as a diagnostic,
that large differences in per-core `mte2_time` indicate multiple cores reading the same address.
No architecture is stated. Not established here.

## 2 · The wrong branch this removes
The natural core split for a 2-D tensor is by the outer axis, giving each core a contiguous band of
rows. When the inner axis is narrow — a few elements, tens of bytes — consecutive cores' bands
start within the same 512 B window, and every core's first access collides. The split is correct,
balanced, and cache-friendly by every criterion an agent would apply, and it constructs the
collision.

The second wrong branch is diagnostic. The symptom is a spread in per-core times, which upstream's
own load-balance rule (§4.4, "最大值与最小值差距 >10% → 负载不均衡") tells the agent to read as
imbalance. The prescribed fix for imbalance is to rebalance the tiling — redistributing work
between cores — which does not move the addresses and does not help. Two upstream rules point at
the same observable and prescribe opposite actions; nothing upstream tells the agent which applies.
That is why this entry names the ambiguity rather than just the mechanism.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §7 硬件约束速查表, line 407:
```
| GM 同地址访问 | 512B 范围内多核串行化，性能降 10–20% | 错峰访问或改变切分方向 |
```
The diagnostic, `ops/ops-profiling/references/optimization_quickref.md:63`:
"| 4 | **避免同地址访问** | 多核读同一地址 | 检查各核 mte2_time 差异大 |".
The colliding rule, `metrics_reference.md` §4.4 核间负载均衡判断, lines 219-222: "通过 Profiling
数据中各核的耗时对比：- 最大值与最小值差距 >10% → 负载不均衡 - 需要调整 Tiling 策略，按基本块
总数均分" — carried separately by 0059.

An adjacent statement from npu-arch's §4 (公开资料与经验值 tier, so upstream's weakest evidence
grade), `ops/npu-arch/references/npu-hardware-params.md:172`: "| 7 | 多核同时访问 GM 同地址性能
优化 | Guide §4 MTE 数据搬运引擎 | 公开资料 / 经验值 |" — listed as a DAV_3510 *improvement*. If
the later architecture optimises this, the implication is that DAV_2201 does not, which weakly
supports the 910-side relevance of the claim. That is an inference from a table of改动, not
evidence, and is not carried into §1.

Same repo throughout: one origin. The 512 B window is the same granularity as 0020's alignment
optimum and 0028's L0A/GM figure; whether that is one mechanism or three coincidences is not
established anywhere in scope.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution. Record the core count from
   `GetCoreNumAiv()` rather than assuming it (0009, 0011).
2. One binary, two arms selected by a runtime argument, identical work per core:
   - Arm C (colliding): each core's GM base offset is `blockIdx * 32` bytes, so all cores start
     inside one 512 B window.
   - Arm S (spread): each core's base offset is `blockIdx * 4096` bytes, distinct windows.
   Both arms move the same total bytes and execute the same instruction sequence.
3. Per arm: total task duration, and the per-core `aiv_mte2_time` distribution — max, min, median.
   The claim is about both the aggregate cost and the per-core spread, and only the second
   distinguishes this from generic slowness.
4. Five repeats, first discarded, arms interleaved. Sweep core count over 2, 8, 24, 48 if the
   part allows, since serialisation cost should grow with the number of colliding cores and a
   flat response would be informative against the mechanism.

## 5 · Checker — acceptance declared before the run
Verdict variables `dur_C`, `dur_S`, and `spread_C`, `spread_S` (max − min of per-core mte2_time).
PASS iff `dur_C / dur_S` lies in [1.10, 1.25] at full core count — the 10–20 % window, declared
now, with a little slack at the top.
The second clause, which is what makes the verdict mechanistic rather than merely a slowdown:
`spread_C` must exceed `spread_S` by more than three times arm S's own repeat-to-repeat spread.
A duration difference without a per-core spread difference would mean something other than
serialisation is at work, and is recorded as such rather than credited to this claim.
The core-count sweep is the third check: if `dur_C / dur_S` is flat from 2 cores to 48, the
serialisation reading is wrong even if the ratio landed in the window at 48. A checker that took
only the full-core point would pass on that.
Red input: `dur_C / dur_S` below 1.02, which overturns.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; **no architecture is stated by the source**. This entry does
not establish whether the effect is on reads, writes, or both — upstream says 访问 without
distinguishing, and §4 as written uses reads only. It does not establish whether the 10–20 % figure
scales with the number of colliding cores or is a fixed penalty; §4 sweeps that but the claim does
not state it. It does not resolve the diagnostic ambiguity with the load-imbalance rule named in
§2 — that would need a case exhibiting one and not the other, which §4 does not construct. It says
nothing about whether the 512 B window here is the same mechanism as the 512 B alignment optimum of
0020.
