```
ID:        0053-the-bottleneck-thresholds-are-stated-without-an-architecture-or-a-derivation
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   harvested — a set of decision-gating thresholds whose scope, era and derivation upstream does not state; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:189-194 — ">80% | 该单元是明确瓶颈"; ops/ops-profiling/references/optimization_quickref.md:9-14 — "`aiv_vec_ratio` 是最高占比，且 >50%", "50-65%: 轻度", "65-80%: 中度", ">80%: 深度"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired study on a named DAV_2201 board shows the optimisation yields upstream associates with each band do not separate at those boundaries — e.g. a unit at 45 % responding to optimisation as strongly as one at 85 %.
```

# 0053 · The bottleneck thresholds are stated without an architecture or a derivation

## 1 · Claim
Upstream asserts a utilisation ladder for identifying a bottleneck unit: above 80 % the unit is a
clear bottleneck and optimising it yields most; 50–80 % a significant contributor; 10–50 % minor;
below 10 % essentially idle. Upstream asserts a parallel severity ladder for VEC bound at 50–65 %
(mild), 65–80 % (moderate) and above 80 % (deep, near the theoretical limit). Upstream asserts
multi-unit patterns: one unit above 70 % with others below 20 % is a clear bottleneck; several
units at 30–50 % indicates pipeline bubbles; SCALAR above 30 % indicates scalar control overhead.
**No architecture, no board, no derivation and no measurement is given for any of these numbers.**
Not established here.

## 2 · The wrong branch this removes
The wrong branch is treating these as measurements. They are the most quotable numbers in the
upstream repo — round, memorable, in tables headed 判定 — and an agent will lift them into a
diagnosis routine as gates. Nothing marks them as anything but facts.

Three things about them are worth an entry:

First, their bands overlap and their arms are not exclusive. The utilisation ladder says 50–80 % is
a "significant contributor" while the VEC ladder splits the same range into mild and moderate. A
unit at 70 % is simultaneously a significant contributor, moderate, and — under the multi-unit rule
— a clear bottleneck if others are below 20 %. Which fires is a matter of which table the agent
opened.

Second, they gate an action, not a description. "Above 80 % → optimise this unit" is a resource
allocation decision, and if the boundary is wrong the effort goes to the wrong pipe. That is
expensive in a way that a wrong descriptive fact is not.

Third — and this is what makes them boundary rather than knowledge — a closely related upstream
document calls its own version of these numbers 经验判定线, empirical judgement lines. The candour
exists somewhere in the repo; it does not travel with the numbers.

An agent should use these as priors for where to look, and must not report a unit as "the
bottleneck" on the strength of a threshold this book cannot source.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §4.1 单单元利用率解读, lines
189-194, verbatim in full:
```
| 利用率 | 解读 |
| **>80%** | 该单元是明确瓶颈，优化此单元收益最大 |
| **50–80%** | 显著贡献者，优化有收益 |
| **10–50%** | 次要贡献者 |
| **<10%** | 基本空闲 |
```
§4.2 多单元模式诊断, lines 198-206, gives seven patterns including "一个单元 >70%，其余 <20% |
清晰瓶颈", "多个单元 30–50% | 流水线气泡", "SCALAR >30% | 标量控制开销大".

`ops/ops-profiling/references/optimization_quickref.md` §1 VEC Bound, lines 9-14:
"**判定**: `aiv_vec_ratio` 是最高占比，且 >50%" then "- 50-65%: 轻度，DoubleBuffer + UB 融合有较大
收益 - 65-80%: 中度，需减少 Cast 或融合指令 - >80%: 深度，VEC 本身接近理论极限，优化空间有限".
§4 Scalar Bound, line 87: "**判定**: `ai*_scalar_ratio` >30%". §5, line 112: "**判定**:
PipeUtilization.csv 各核 `ai*_time(us)` 差异 >10%". §6, line 138: "**判定**:
ResourceConflictRatio.csv 中 `aiv_vec_total_cflt_ratio` >5%".

Neither document states an architecture for any of these. `optimization_quickref.md` has no
provenance line at all — its sibling `csv_fields_reference.md` has one (0051), which makes the
absence here a difference in discipline within one skill rather than a house style.

The expected-yield column is the strongest claim and the least supported:
`optimization_quickref.md` lines 20-25 attach numbers to techniques — UB fusion 20–50 %, reducing
Cast 10–30 %, fused instructions 5–15 %, low-latency reduction 10–20 %, AIC:AIV = 1:2 30–40 %,
counter mode 5–10 % — with no case, no shape and no board behind any of them.

**The candour that exists elsewhere**: the deep-dive survey records
`ascendc-perf-optimize/references/single-core-pipeline/metrics.md:63` calling its severity ladder
经验判定线. That file is in another agent's domain and the quote was NOT re-verified for this book;
it is flagged here as a pointer, not asserted.

Same repo throughout: one origin.

## 4 · Procedure
Proposed, runnable later; not run. Testing a threshold means testing whether it separates outcomes,
not whether the number appears.

1. Name the die; record the part; occupancy before and after; no substitution.
2. Build a family of kernels whose `aiv_vec_ratio` spans 20 % to 95 % in roughly 5-point steps, by
   varying arithmetic intensity at fixed data volume. Measure the ratio for each rather than
   assuming it.
3. To each, apply one fixed optimisation from upstream's own list — UB fusion is the largest
   claimed and the easiest to apply uniformly — and measure the speed-up.
4. Plot speed-up against baseline ratio. Upstream's ladder predicts a step: large gains below 80 %,
   small gains above ("VEC 本身接近理论极限，优化空间有限").
5. Five repeats per point, first discarded, arms interleaved.

## 5 · Checker — acceptance declared before the run
Verdict variable `yield(ratio)`: the speed-up as a function of baseline utilisation.
PASS (the 80 % boundary upheld) iff mean `yield` below 80 % exceeds mean `yield` above 80 % by more
than three times the pooled repeat-to-repeat spread.
The declared negative, and the more likely outcome: a smooth `yield` curve with no step anywhere.
That does NOT mean the numbers are useless — it means they are not boundaries, and the entry is
corrected to say the ladder is a continuum, which is a materially different instruction to a
consuming agent than "optimise above 80 %".
A second declared negative: a step at some ratio OTHER than 80 %. Reported as the measured
boundary, with the entry corrected to it. Fitting the step location rather than testing only the
quoted value is what stops this from confirming what it went looking for.
The 50 %, 65 %, 30 % and 10 % boundaries are NOT tested by this procedure and no verdict is issued
for them — stated now so a run on the 80 % boundary is not later reported as validating the ladder.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. **No architecture, board, era, case or derivation is stated by
upstream for any threshold in this entry**, and this entry does not supply one — its claim is that
the numbers are asserted, not that they are right. It does not establish the expected-yield
percentages of §3, which are weaker still. It does not resolve the overlap between the two ladders
(§2). It does not establish whether the thresholds were ever measured on any part; the 经验判定线
pointer in §3 is second-hand and unverified. Every downstream use of these numbers must carry this
entry's stratum, per RULES.md Art. 10 — stated as upstream practice, unverified, never in measured
voice.
