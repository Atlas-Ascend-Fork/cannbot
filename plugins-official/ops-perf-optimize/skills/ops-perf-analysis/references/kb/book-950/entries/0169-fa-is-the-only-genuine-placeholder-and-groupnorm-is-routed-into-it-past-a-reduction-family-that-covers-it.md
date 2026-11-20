```
ID:        0169-fa-is-the-only-genuine-placeholder-and-groupnorm-is-routed-into-it-past-a-reduction-family-that-covers-it
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/fa/fallback/index.md:3,7,11,18 —
           "> 当前为占位文档，内容待补充。" · "FlashAttention, GroupNorm" · "多核切分策略
           （FlashAttention: Batch × Head / GroupNorm: Batch 切分 + Group 内归约）" ·
           "> 当前返回：「FA Tiling 建模暂未收录。」" ; tiling/index.md:24 —
           "| FA FlashAttention 类 | FlashAttention, GroupNorm | [fa/](fa/) |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured GroupNorm on a named 950 board where a plan derived from the reduction family's
           templates is no better than one derived without any tiling reference — the mis-route
           would then cost nothing, and re-homing GroupNorm would be cosmetic.
```

# 0169 · FA is the only genuine placeholder, and GroupNorm is routed into it past a reduction family that covers it

## 1 · Claim
Upstream asserts that the FA family's fallback is a placeholder with content outstanding, listing four
missing items and stating the routing answer to give: `FA Tiling 建模暂未收录`. Upstream asserts that
the FA family covers two operators, FlashAttention and GroupNorm, both in the top-level routing table
and in the placeholder's own applicable-operators list. Upstream asserts, within the placeholder's
missing-content list, a one-line sketch of what GroupNorm's multi-core split would be —
`Batch 切分 + Group 内归约`, batch splitting plus within-group reduction. The reduction family, one
directory away, carries five templates plus two interleaved templates plus a cross-core reduction-axis
branch, and its own applicability list names LayerNorm and RMSNorm — operators whose R-axis structure
`mean → var → normalize` upstream describes there in detail. Not established here; this entry records
a routing state and an absence.

## 2 · The wrong branch this removes
Three of the four `占位` labels in this subtree are wrong (0152, 0156, 0163). This one is right: the
`fa/` directory contains two files totalling 35 lines, no `tiling-flow.md`, no `tiling-fields.md`, no
script. Recording that matters as much as recording the three mislabels, because an agent that learns
"the `占位` labels are unreliable" will go looking behind this one too and find nothing. The four
labels are not one defect; they are three false negatives and one true one, and only reading each
directory distinguishes them.

The routing consequence is the costly half. GroupNorm's computation along its reduction axis is a
normalisation — mean, variance, normalise — which is exactly the shape the reduction family's
`tiling-flow.md` describes for LayerNorm, including the buffer-count correction (0130) and the Welford
recommendation under Recompute. Routing GroupNorm to `fa/` sends it to a refusal string, past a
family whose derivation procedure covers it. An agent following the router gets
`FA Tiling 建模暂未收录` for an operator the reference set can in fact model.

The placeholder's own GroupNorm line is the evidence that this was noticed and filed in the wrong
place: `GroupNorm: Batch 切分 + Group 内归约` is a reduction-family sentence — split the outer axis
across cores, reduce within the group — written inside an FA placeholder. Whoever wrote it knew the
shape of the answer; the routing table sent the operator to a directory that has none.

The third wrong branch is inventing content for the absence. FlashAttention genuinely has no tiling
model here, and the honest consuming behaviour is the refusal, not a plan assembled from the matmul
and reduction families because FA "is" a matmul-softmax-matmul chain. This entry records the absence
as an absence.

## 3 · Ground / Source
`fa/fallback/index.md`, in full — the entire file is 18 lines:

```
# FA FlashAttention 类 — 兜底算法

> 当前为占位文档，内容待补充。

## 适用算子

FlashAttention, GroupNorm

## 待补充内容

- 多核切分策略（FlashAttention: Batch × Head / GroupNorm: Batch 切分 + Group 内归约）
- 单核切分策略
- Buffer 规划
- 分支覆盖

---

> 当前返回：「FA Tiling 建模暂未收录。」
```

`fa/index.md`, in full — 17 lines, a routing table with one row pointing at the placeholder:

```
# FA 族 Tiling 算法路由

> FA 族（FlashAttention, GroupNorm）Tiling 算法入口。默认使用 fallback 兜底算法。

## 1. 已注册算法

| 优先级 | 算法 | 选择条件 | 目录 |
|--------|------|---------|------|
| 0（兜底） | 官方参考 | 无条件（回退保障） | [fallback/](fallback/) |

## 2. 贡献新算法

在 `fa/` 下创建新目录，在此文件的路由表中注册。
```

The directory holds these two files and nothing else — no `tiling-flow.md`, no `tiling-fields.md`, no
`script/`. Every other family in this domain has at least one of the three.

The routing that sends GroupNorm here, `tiling/index.md:24`:

```
| FA FlashAttention 类 | FlashAttention, GroupNorm | [fa/](fa/) |
```

and the registry row, `tiling/index.md:77`:

```
| FA | [fa/](fa/) | [fallback/](fa/fallback/)（占位） | — | — |
```

This is the one `占位` label in the registry that is accurate.

What sits next door, `reduction/fallback/index.md:10-16`:

```
| 算子类型 | 沿 R 轴的典型计算 | 模板选型注意点 |
|---------|-----------------|--------------|
| ReduceSum / ReduceMax | 单次归约 | 标准 UB 预算；Sum 可选二分累加 |
| Softmax | max → exp → sum → div | 多遍流水，Recompute 需重读原数据 |
| LayerNorm / RMSNorm | mean → var → normalize | 两个关联统计量，分载时用 Welford |
| ArgMax / ArgMin | 归约 + 索引跟踪 | 启用 with_index 增强 |
| EuclideanNorm | square → sum → sqrt | 单次可交换归约；**多轴交错布局**走交错连续载入模板 |
```

and the derivation procedure that would apply, `reduction/fallback/tiling-flow.md:350` (quoted in
0130 §3): `| LayerNorm | mean, var, normalize | 两个关联统计量 → Recompute 时启用 Welford |`, with the
three-step agent procedure at `:353`:
`先确定算子数学流程 → 数清 UB 内同时存在的 buffer 份数 → 代入对应模板的预算公式`.

GroupNorm differs from LayerNorm in which axes the statistics are taken over — per group of channels
rather than per sample — which changes the collapse (0121) but not the template language. Whether it
collapses cleanly to `(A1, R, A0)` is the question a re-homing would have to answer, and no document
in this tree asks it.

Registered as C-950tiling-036 (GroupNorm routed to a stub past a family whose procedure covers its
computation shape). The four `占位` labels are now: C-950tiling-026 elewise (wrong),
C-950tiling-027 broadcast (wrong), C-950tiling-028 conversion (registry wrong, family index right),
and this one — accurate.

## 4 · Procedure
Two arms. The first needs no device and is permitted in this phase; it has not been run.

Arm 1 — collapse feasibility for GroupNorm, no device, no execution. For six GroupNorm shapes spanning
`num_groups ∈ {1, 4, 32, C}` and both channel-first and channel-last layouts, apply the reduction
family's Step-0 collapse (`reduction/fallback/tiling-flow.md:26-38`) by hand and record whether each
produces a single `(A1, R, A0)` triple, an interleaved layout requiring the pre-gate (0125), or
neither. Then, for the ones that collapse, apply 0130's buffer-count procedure to derive a UB budget
and record the resulting template selection. The deliverable is a yes/no on whether GroupNorm is
expressible in the reduction family's language — which is what re-homing would require and what no
document currently states.

Arm 2 — the cost of the mis-route, on a named 950 board (950PR or 950DT); never run in this phase.
Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Take two GroupNorm shapes that arm 1 finds expressible. Build three kernels with one compiler pin: the
plan derived from the reduction family's templates; the plan derived from the placeholder's one-line
sketch alone (`Batch 切分 + Group 内归约`, with tile sizes chosen by an agent with no further
guidance); and a naive single-tile-per-core plan representing what an agent produces after the refusal
string. md5 each; host echo of the collapsed triple, the template and the derived tile fields; output
compared against an fp64 reference within the operator's declared tolerance; `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped.

For FlashAttention there is no arm. The absence is genuine, nothing in this tree models it, and no
procedure here can establish what upstream does not contain.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ub_size` or
`core_num` are literals (queried, 0141); that GroupNorm collapses to a single R — arm 1 is what tests
that, and an interleaved result would route it to the pre-gate rather than to the five templates; that
the reduction family's Welford recommendation applies to GroupNorm's grouped statistics.

## 5 · Checker — acceptance declared before the run
Verdict variable `groupnorm_expressible`, 0 to 6, from arm 1: the number of shapes that collapse into
a form the reduction family's decision tree can route. Declared before the run: the mis-route is
substantive iff `groupnorm_expressible ≥ 4`. If it is 0, GroupNorm genuinely needs its own model and
its placement in `fa/` — while still a stub — is not a mis-route but an honest gap, and this entry is
corrected in place.

Verdict `misroute_cost` = refusal-plan median `aiv_time` / reduction-derived median from arm 2,
reported with the variance floor. The OVERTURN fires iff `misroute_cost ≤ 1 + variance_floor` on both
shapes — the reduction family's templates would then buy nothing for GroupNorm.

The exit code is not the verdict. Arm 1's instrument is the six-row collapse table and the checker
fails red if it has fewer than six rows, since silently skipping a shape whose collapse could not be
determined would inflate `groupnorm_expressible`. Arm 2's guards: the elementwise numeric comparison
on all three arms — a normalisation with a wrong reduction extent produces plausible values and exits
0 — and the host echo of the collapsed triple, since a plan that collapsed differently than intended
is not the plan under test.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Arm 1 needs no device and has
not been run either.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, and no collapse was attempted. The entry does not establish that GroupNorm is
expressible in the reduction family's template language — arm 1 exists because that is unknown, and a
zero result would mean this is an honest gap rather than a mis-route. It does not establish the cost
of the mis-route. It establishes nothing whatever about FlashAttention: upstream has no model for it
here, this book invents none, and the four missing items the placeholder lists remain missing. It does
not establish that the reduction family's Welford recommendation or its `(A1, R, A0)` collapse
transfer to grouped statistics. It does not propose a re-homing — that is a change to the routing
table, which is upstream's artifact and outside what a harvested entry may assert. No chip is named
anywhere in the FA family — the whole family is 35 lines — so BOARD is `family-claimed(unverified)`
and the chip is unstated; §4 arm 2 names 950PR/950DT because that is where our run would happen.
Nothing here is established for any 910-family board.
