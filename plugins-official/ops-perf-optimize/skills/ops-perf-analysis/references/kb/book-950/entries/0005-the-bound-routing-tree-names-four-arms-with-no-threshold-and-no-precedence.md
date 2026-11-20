```
ID:        0005-the-bound-routing-tree-names-four-arms-with-no-threshold-and-no-precedence
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/index.md:20-27 — "├─ scalar耗时占比高 或者 计算量小 → Scalar Bound / 小 case → scalar.md ├─ MTE2/访存单元利用率高 + 带宽为主要限制 → 访存 Bound → memory.md ├─ Vector 单元利用率高 + 向量指令为主要限制 → Vec Bound → vec.md └─ 各单元利用率均不高 → 算**重叠因子**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a labelled case set on a named 950 board in which every case's bound class, assigned
           by an independent expert reading the trace, is recovered by the tree's four arms with
           no case matching two arms and none matching zero — that would show the predicates are
           in practice exclusive and exhaustive, and this entry's complaint is empty.
```

# 0005 · The bound routing tree names four arms with no threshold and no precedence

## 1 · Claim
Upstream asserts a four-arm routing tree from profiling data to a diagnosis page: scalar-heavy
or tiny compute → scalar; MTE2/memory-unit utilisation high with bandwidth dominant → memory;
Vector-unit utilisation high with vector instructions dominant → vec; all units low → compute
the overlap factor and go to no-bound. The arms are stated qualitatively — 占比高, 利用率高,
主要限制, 均不高 — with no numeric cut, no ordering, and no rule for a case that satisfies two
arms. Not established here; nothing was measured and no case set exists.

## 2 · The wrong branch this removes
A harness agent given four qualitative arms will pick the arm whose lane has the largest ratio
and report a bound. That is not the same decision the tree describes, and it is confidently
wrong in the case the skill's own worked example contains: MTE2 0.513, VEC 0.483, SCALAR 0.480
(metrics.md:51-55). Ranked, MTE2 wins and the agent routes to `memory.md`, whose entire
strategy set is about moving fewer bytes. Upstream's reading of the same numbers is that none
of the lanes dominates, so the operator is not memory bound at all but badly ordered, and the
right page is `no-bound.md`. One number decides between them and it appears exactly once in the
skill (see 0006). Without a stated threshold and a precedence rule, two agents reading the same
CSV route to two different strategy sets and both believe they followed the tree.

## 3 · Ground / Source
`references/single-core-pipeline/index.md:20-27`, the Step 1 block, verbatim:

> Step 1 — 初步判定：
>   ├─  scalar耗时占比高 或者 计算量小 → Scalar Bound / 小 case → scalar.md
>   ├─ MTE2/访存单元利用率高 + 带宽为主要限制 → 访存 Bound → memory.md
>   ├─ Vector 单元利用率高 + 向量指令为主要限制 → Vec Bound → vec.md
>   └─ 各单元利用率均不高 → 算**重叠因子**（算法见 metrics.md §2.1）：
>        Σ(各泳道耗时) / aiv_time，与理想上界 Σ/max 比。
>        达成率低（如 51%）= 流水并行不足 → 无 Bound → no-bound.md

The routing table at `:39-44` repeats the four arms with equally qualitative conditions
(`scalar占比最高或者计算量极小或 shape 很小`, `MTE2/AIC 带宽为主导瓶颈`, `Vector 指令为主导
瓶颈`, `无明显瓶颈`). The diagnosis pages restate their own entry conditions in the same voice:
`vec.md:11-13`, `memory.md:7-9`, `scalar.md:7-10`, `no-bound.md:7-12`. The only numeric cut
anywhere on this path is `metrics.md:57`'s "没有单一泳道超过 0.52" — inside a worked example,
not in the tree. Step 2 (`:28-29`) tells the reader to confirm the verdict against the
simulation timeline and 排除误判（如访存等计算 vs 计算等访存）, which is where the missing
precedence is meant to be recovered by a human.

The same species appears once more in my scope and is recorded with it: the MC² bound router at
`comm-compute/index.md:126-128` routes on `计算耗时 >> 通信耗时` with no value for `>>`, while
`bound_diagnosis.md:11-17` gives numeric R bands for the same decision (entry 0058).

## 4 · Procedure
Later phase, needs a card. Named board: 950PR (or 950DT — whichever the driver reports; the
board token is written from the readout, and a run on one says nothing about the other).

1. Device selection: require `ASCEND_RT_VISIBLE_DEVICES` to be set explicitly; refuse to run
   otherwise. Read the SoC name from the driver and record it verbatim. The procedure refuses
   to assume the die is idle, and re-reads occupancy after the run — a die that became busy
   mid-sweep invalidates the ratios, not just the timings.
2. Build a labelled case set of at least 24 kernels spanning: pure elementwise (vec-heavy),
   large streaming copy (mte2-heavy), tiny-shape broadcast with tens of thousands of tiles
   (scalar-heavy), and fused multi-stage operators with all lanes near 0.5 (the no-bound shape).
   Each case is labelled *before* profiling by a reader who sees only the kernel source.
3. Capture per case with msprof per entry 0010: `aiv_time`, `aiv_vec_ratio`, `aiv_mte2_ratio`,
   `aiv_scalar_ratio`, `aiv_mte3_ratio`, plus the overlap factor from `PipeUtilization.csv`.
4. Evaluate the four arms mechanically on each case, using a candidate threshold set — sweep
   the single-lane cut t over 0.40…0.70 in steps of 0.02 — and record, for each t: how many
   cases match no arm, how many match more than one, and how many arms' matches agree with the
   source-only label.

## 5 · Checker — acceptance declared before the run
Verdict variables, declared before any sweep is run: `ambiguous(t)` = number of cases matching
≥2 arms; `unrouted(t)` = number matching 0 arms; `agree(t)` = number whose single match equals
the pre-registered label. Acceptance for the *tree as written*: there exists t with
`ambiguous(t) = 0` and `unrouted(t) = 0` and `agree(t) = N`. Anything less is recorded as the
tree's real behaviour, not smoothed.

The exit code is not the verdict — the sweep completes successfully whatever it finds. The
verdict is the printed triple per t, and the whole curve is published, including the t that
flatters the tree least.

This checker can go red, and the input that does it is already known: the metrics.md worked
example, entered as a case with its published ratios. At t = 0.45 it matches three arms at
once; at t = 0.52 it matches none, which is upstream's own reading. A checker that reported
only "a routing decision was produced" would pass on both, which is the failure species this
design avoids: the counts are of ambiguity and silence, not of success.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no case set exists yet. This entry does not establish that
the four bound classes are the right classes, nor that a numeric threshold exists that makes
them exclusive — it is possible that no single-lane cut does, and that the honest repair is a
two-stage predicate (lane maximum *and* overlap factor) rather than a number. It does not
transfer to the MC² path, whose bound classes are defined on a different ratio (R = T_compute /
T_comm) and diagnosed by isolation test, not by lane ratios. It says nothing about AIC-side
(Cube) bounds: every ratio named here is an `aiv_*` ratio, and the Cube lane is absent from the
tree entirely.
