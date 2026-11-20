```
ID:        0142-topk-thresholds-are-performance-policy-not-architectural-capability-limits-and-may-not-be-extrapolated
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/sort/topk_host_tiling.md:193 —
           "这些数值是性能策略，不是架构能力边界。" ; sort/topk.md:84 — "这些门槛来自相邻 case A/B，
           不是架构能力边界。不要扩展到 fp16/fp32/bf16 的中轴场景" ; sort/topk.md:280-285 —
           "## 9. 禁止外推的边界" ; sort/index.md:33 — "阈值只能在相邻边界全量 A/B 后调整；
           不能从单个 case 外推。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured A/B on a named 950 board showing one of these thresholds sits at a hard
           capability boundary — a case just past it failing to build or to produce correct output
           rather than merely running slower — which would make the number a capability limit after
           all.
```

# 0142 · TopK thresholds are performance policy, not architectural capability limits, and may not be extrapolated

## 1 · Claim
Upstream asserts, four times and in three files, that the numeric thresholds in its TopK routing are
performance policy rather than statements about what the architecture can do. Specifically: the radix
tile search starting points (15360 / 10240 for single-block and single-core, non-64-bit and 64-bit;
7680 / 5120 for multi-core), decrementing by 256, `这些数值是性能策略，不是架构能力边界`; the
fallback-candidate gates (`dtype == int64`, `nonLast and D > 2048`, and the int32 compound
condition) `来自相邻 case A/B，不是架构能力边界`, with an explicit instruction not to extend them to
fp16/fp32/bf16 middle-axis cases because those shapes are faster in the common tiler; a four-item
list of situations where extrapolation is forbidden outright — a non-DAV_3510 platform, a different
UB size, a different high-level API version, unordered TopK, `k > 2048`, non-contiguous input, and
the Sort/ArgSort family; and a process rule that thresholds may be adjusted only after a full A/B at
the adjacent boundary and never extrapolated from one case. Not established here — and by upstream's
own framing, "not established" is the correct state for a threshold outside the cases it was
calibrated on.

## 2 · The wrong branch this removes
The wrong branch is treating a calibrated number as a fact about the machine. `D > 2048` looks like a
capability boundary — it is a power of two, it appears beside `TOPK_K_MAX = 2048`, and it gates a
routing decision. It is neither: it is where two implementations crossed over on the cases someone
measured. An agent that reads it as a capability will refuse `D = 4096` on a path that would have
worked, or will "fix" a gate by rounding it to a nicer number, or — the expensive one — will carry
it to another dtype. Upstream forbids exactly that carry in the same breath as it states the gate,
and gives the reason: for fp16/fp32/bf16 middle-axis shapes the common tiler is faster, so extending
the int32 gate to them would route them to the slower path.

The second wrong branch is subtler and is what makes this a `boundary` entry rather than a
`knowledge` one. A reference document full of precise numbers invites the reader to treat precision
as authority. This family's numbers are precise (15360, 10240, 7680, 5120, decrement 256, `3*k <= D`,
`4*k <= D`, `inner >= coreNum * 32`) and upstream's own position is that their authority is exactly
the set of cases they were A/B'd on and no wider. Recording that position as a claim — with its own
overturn condition — is the only way it survives into a derived artifact; a caveat in a preamble does
not transmit.

Third: the process rule. `阈值只能在相邻边界全量 A/B 后调整；不能从单个 case 外推` is a rule about
how to change a number, and it is the rule that the reduction family violated and then fixed on
board (0127, where a gate calibrated on one criterion mis-fired by 28 % and 10× until a second
threshold was added). The two families agree, from opposite directions: one states the discipline,
the other shows what its absence costs.

## 3 · Ground / Source
`sort/topk_host_tiling.md:191-193`:

```
具体 tile 搜索起点为：single block/single core 的非 64 位 15360、64 位 10240；multi-core 的非
64 位 7680、64 位 5120。Radix tile 以 256 递减，optimized 的最小步进同时受 k 和 32B 对齐约束。
这些数值是性能策略，不是架构能力边界。
```

`sort/topk.md:73-85`, the fallback-candidate gate with its fence attached:

```
### 3.2 Fallback candidate

以下任一条件成立即进入 fallback 候选区：

dtype == int64
or (nonLast and D > 2048)
or (dtype == int32 and nonLast and D >= 32 and rows >= 512
    and (k <= 32 or 4*k <= D))

这些门槛来自相邻 case A/B，不是架构能力边界。不要扩展到 fp16/fp32/bf16 的中轴场景；这些
代表 shape 在 common 中更快。`int64` 则必须提前截获，以避开不稳定的 common 64 位路径。
```

`sort/topk.md:280-285`, the forbidden-extrapolation list in full:

```
## 9. 禁止外推的边界

- 非 DAV_3510、不同 UB 或不同高阶 API 版本：先重新做能力检查和阈值 A/B。
- 无序 TopK、k>2048、非连续输入：不满足当前契约，不能静默套用。
- Sort/ArgSort 可复用 radix/merge 原理，但不能套用只保留 k 个 running candidates 的截断逻辑。
- `sort/fallback/` 是通用 M-way Sort 模型，不能替代本文的 A5 TopK 路由。
```

`sort/index.md:27-33`, the reproduction principles, of which the fourth is the process rule:

```
## 2. 复现原则

1. 保留 `small-axis -> fallback/transpose-fallback -> common` 的一级优先级。
2. 保留 common 内 `non-last mode 8 -> small merge -> single block -> fp32 merge -> single core -> optimized multi-core -> general radix -> SortAndTopK` 的优先级。
3. Host tiling 按复原规格与 Python 模型生成；TilingData、kernel 和 launch 必须整体核对，禁止只拷 kernel
   后重写简化 tiling。
4. 阈值只能在相邻边界全量 A/B 后调整；不能从单个 case 外推。
```

And the scope statement the whole family sits under, `sort/topk.md:3-6`:

```
> 适用范围：Ascend 950 / DAV_3510、连续 ND 输入、有序 TopK、输出 index 为 `int64`，
> `int8 / uint8 / int32 / int64 / fp16 / fp32 / bf16`，`1 <= k <= min(D, 2048)`。
> 本文固化 TopK 的已验证策略。它是 case 级多模板路由，
> 不是一套可由单一 RadixSort、MergeSort 或通用 Sort fallback 替代的算法。
```

Two things about that scope line. It names `Ascend 950 / DAV_3510` — an architecture and a family,
not a board, so 950PR and 950DT are covered indistinguishably and BOARD stays
`family-claimed(unverified)`. And it says `已验证策略` — verified — without stating where, when, on
what cases, or with what tool. The A/B data the fences refer to is not in this tree; the fences are
the only trace of it. That is the honest reading and it is why this entry is `harvested` and not
higher: a document saying "these numbers came from measurements" is not a measurement.

Under 0104's provenance rule every threshold quoted here traces to a literal, so all are software
经验值 and all are inside the range 0106's rule would enumerate. Upstream agrees, in its own words,
and adds a condition on *how* they may be re-enumerated: a full adjacent-boundary A/B, not a single
case.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The claim
is that these numbers are policy, not capability, so the procedure crosses them and records which
kind of failure appears — a slower run (policy) or a broken one (capability).

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs;
interquartile range over median.

Adjacent-boundary A/B, done as upstream's own rule prescribes rather than as a single-case probe.
For each of three thresholds — `D > 2048` in the fallback gate, `3*k <= D` in the transpose gate, and
the 15360 radix tile start — construct at least six cases straddling the boundary (three each side),
and at every case force both routes that the threshold selects between. One compiler pin; md5 per
binary; host echo of the tilingKey, the selected mode and the tile actually used; output compared
elementwise against a CPU reference, with value/index pairs both checked, since upstream's pair
invariant (`任何 compare、Gather、Sort、transpose、merge、尾块搬运都必须同时更新 value 和原始 axis
index`) is exactly what a forced route is likely to break. Record `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Capability arm — the one that decides this entry's label. For each crossed threshold, record whether
the forbidden side *fails* (build error, launch error, wrong result) or merely *loses*. A threshold
whose crossing only loses is policy; one whose crossing breaks is capability, and upstream's sentence
would be wrong for it.

Extrapolation arm: take the int32 fallback gate and apply it to fp16 and bf16 middle-axis shapes,
which upstream explicitly forbids, and measure both routes. This is the arm upstream predicts will
show the common tiler faster, and it is retained whether or not it bites.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` or
`ubSize` are literals (both queried per 0141, and `inner >= coreNum * 32` depends on the first); that
a forced route was taken (host echo of tilingKey required); that a result at one dtype transfers to
another — the extrapolation arm exists because upstream says it does not.

## 5 · Checker — acceptance declared before the run
Verdict variable `crossing_kind(threshold) ∈ {policy, capability, no-effect}`: `capability` if any
case on the forbidden side fails to build, fails to launch, or produces a wrong result; `policy` if
all such cases run correctly but slower by more than the variance floor; `no-effect` if the two
routes are within the variance floor across the whole straddle. Declared acceptance: upstream's
sentence is supported iff `crossing_kind = policy` for all three thresholds. The OVERTURN fires iff
any threshold returns `capability`. A `no-effect` verdict is a third outcome and is reported as one —
it would mean the threshold separates nothing on this board and the A/B that produced it does not
reproduce.

Verdict variable `extrapolation_cost` = forced-fallback median time / common-tiler median time on the
fp16/bf16 middle-axis cases; upstream's prohibition is supported iff it exceeds 1 + variance floor.

The exit code is not the verdict: a TopK that returns the wrong indices with the right values exits
0, and this family's whole pair invariant is about exactly that. The instrument is therefore an
elementwise comparison of *both* the values and the indices, and the checker fails red if only one
of the two was compared. Second guard: tilingKey identity — the two arms of every straddle must echo
different tilingKeys, and if the host overrode a forced route the comparison is void and the checker
goes red rather than reporting a `no-effect`.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The thresholds quoted are
upstream's constants, and the A/B data upstream says produced them is not present in this tree.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no threshold was crossed. The entry does not establish that any of these
numbers is correct, and by upstream's own fence it establishes nothing about them outside the cases
they were calibrated on — cases whose data is not in this tree. It does not establish that the
crossings are non-breaking; §4's capability arm exists because that is unknown, and a `capability`
verdict would overturn the entry. It does not establish that the common tiler is faster for
fp16/bf16 middle-axis shapes; upstream asserts it as the reason for the prohibition and gives no
numbers. `Ascend 950 / DAV_3510` names an architecture covering both 950PR and 950DT, so BOARD is
`family-claimed(unverified)` and no specific board is named; upstream's `已验证策略` carries no
location, date, case set or tool. §4 names 950PR/950DT because that is where our run would happen.
Nothing here is established for any 910-family board, and upstream's own first forbidden-extrapolation
bullet — a non-DAV_3510 platform requires a fresh capability check and threshold A/B — says as much.
