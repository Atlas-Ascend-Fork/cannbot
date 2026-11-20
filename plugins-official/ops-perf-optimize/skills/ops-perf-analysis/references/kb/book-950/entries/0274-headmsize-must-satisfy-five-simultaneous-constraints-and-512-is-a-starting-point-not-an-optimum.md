```
ID:        0274-headmsize-must-satisfy-five-simultaneous-constraints-and-512-is-a-starting-point-not-an-optimum
LABEL:     boundary
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (ops/ascendc-mc2-best-practice). Upstream states the
           constraints and disclaims its own default; nothing was compiled and no tileCnt was swept.
BOARD:     family-claimed(unverified)
           # the pipeline-tuning material names no board token this book recognises; it is MC²
           # comm-compute material and no board was contacted.
SOURCE:    ops/ascendc-mc2-best-practice/references/shared/pipeline_tuning.md:119-130 — "## 4.
           headMSize 的约束 / 切换 `tileCnt` 时，`headMSize = M / tileCnt` 必须满足：" followed by the
           five-row 约束/说明/违反后果 table.
SOURCE:    same file:5 — "> 参考工程默认 `headMSize=512`（即 `tileCnt = M/512`）只是经验值，
           **不是最优值**。不同 M/K/dtype 组合下最优 `tileCnt` 不同，必须以 `msprof --ai-core=on
           --aic-mode=task-based` 实测为准。"
SOURCE:    same file:158 — "**切换 `tileCnt` 时必须重新调 `GetTilingData`**——`headMSize` 变了，
           所有 Blaze tiling 字段都会跟着变。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an MC² run in which a `headMSize` violating any one of the five constraints produces
           correct output at competitive latency — that row is then not a constraint. Each row is
           independently falsifiable and one counterexample suffices for that row.
```

# 0274 · `headMSize` must satisfy five simultaneous constraints, and 512 is a starting point, not an optimum

## 1 · Claim
Upstream asserts that in an MC² comm-compute operator the communication tile size
`headMSize = M / tileCnt` must simultaneously satisfy five constraints, each with a named consequence
for violating it: `headMSize > 0` (i.e. `tileCnt ≤ M`), else the tile is empty at run time;
`M % tileCnt == 0`, because the host-side `tileCnt = (m - tailMSize) / headMSize` does not currently
support a non-zero tail; `headMSize ≥ Blaze baseM` (typically 128 or 256), else `GetTilingData` errors
or fails to derive; `headMSize × kPerRank × sizeof(dtype)` must land in the UDMA-efficient range of
hundreds of KB to a few MB, else UDMA bandwidth utilisation drops and Put overhead is exposed; and
`bufferSize × headMSize × kPerRank × rankSize × sizeof(dtype) ≤ SHMEM_SPACE_SIZE` (default 1 GB), else
`aclshmem_align` fails. Upstream asserts that its reference project's `headMSize = 512` is an empirical
starting point and explicitly **not** an optimum. Not established here: nothing was compiled and no
`tileCnt` was swept.

## 2 · The wrong branch this removes
`headMSize = 512` appears in the reference project, so it will be copied. Upstream disclaims it in the
first line of the document, which is the right placement and is also the line a reader skims past on
the way to the code.

Copying it is wrong in two directions that upstream names. When M is large and K small, a smaller
`headMSize` (larger `tileCnt`) makes the communication granularity finer and exposes more stages to
overlap. When K is large, a single MMAD is already long enough that fewer, larger tiles reduce
communication count. So the default sits at one point of a two-sided trade and the reference shape
(`M=2048, K=8192, rankSize=4`, giving Put ≈ 1 MB) is what put it there.

The sharper failure is that the five constraints are **simultaneous** and pull against each other. Row 3
pushes `headMSize` up — it must be at least Blaze's `baseM`. Row 5 pushes it down — the SHMEM budget is
`bufferSize × headMSize × kPerRank × rankSize × sizeof(dtype)`, so at `bufferSize = 4` (upstream's
default) and a large rankSize the ceiling drops fast. Row 4 wants the product in a band, not above a
floor. An agent that tunes `tileCnt` for overlap alone will walk out of one of the others, and the
failure modes are not alike: row 2 is a silent correctness hazard (unsupported non-zero tail), row 3 is a
host-side derivation error, row 5 is an allocation failure. Only row 1 is loud and harmless.

The third branch is the one upstream states separately and is easy to miss because it is not in the
table: changing `tileCnt` is not a parameter edit. `headMSize` feeds `GetTilingData`, which re-derives
`baseM`, `baseN`, `baseK`, `stepK`, `usedCoreNum` and the rest of the Blaze tiling. An agent that
changes `tileCnt` and reuses the previous tiling struct is running a matmul tiling computed for a
different tile size — which will not obviously fail.

## 3 · Ground / Source
`pipeline_tuning.md:119-130`, the constraint table in full — it is the load-bearing artefact of this
entry and the consequence column is what makes it usable:

> ## 4. headMSize 的约束
>
> 切换 `tileCnt` 时，`headMSize = M / tileCnt` 必须满足：
>
> | 约束 | 说明 | 违反后果 |
> |------|------|---------|
> | `headMSize > 0` | `tileCnt ≤ M` | 编译期 OK，运行期 tile 为空 |
> | `M % tileCnt == 0` | 否则要显式处理 tail | host 侧 `tileCnt = (m - tailMSize) / headMSize` 当前不支持非零 tail |
> | `headMSize ≥ Blaze baseM`（典型 128/256） | Blaze `BlockMmad` 需要最小块 | `GetTilingData` 报错或推导失败 |
> | `headMSize × kPerRank × sizeof(dtype)` 落在 UDMA 高效区间 | 数百 KB ~ 数 MB | UDMA 带宽利用率下降，Put 开销暴露 |
> | `bufferSize × headMSize × kPerRank × rankSize × sizeof(dtype) ≤ SHMEM_SPACE_SIZE` | SHMEM 空间预算（默认 1 GB） | `aclshmem_align` 失败 |

Every row names what breaks and where — run time, host side, bandwidth, allocator. A constraint table
whose rows carry their consequence is directly actionable in a way that a list of inequalities is not,
and this is the shape worth carrying into the delivered skill.

The disclaimer, `:5`, placed as the document's opening blockquote:

> > 参考工程默认 `headMSize=512`（即 `tileCnt = M/512`）只是经验值，**不是最优值**。不同 M/K/dtype 组合下
> > 最优 `tileCnt` 不同，必须以 `msprof --ai-core=on --aic-mode=task-based` 实测为准。

and its expansion at `:131-136`, which gives the direction of the trade rather than a rule:

> **512 不是最优值**——参考工程固定 `headMSize=512` 只是为了在 `M=2048, K=8192, rankSize=4` 的典型 shape 下
> 取得一个合理起点（Put ≈ 1 MB，UDMA 带宽利用率高）。其他 shape/dtype 下最优值不同：
> - M 大、K 小时，`tileCnt` 增大（`headMSize` 减小）让通信粒度更细，掩盖级数更多；
> - K 大时，单次 MMAD 已足够长，`tileCnt` 可减小（`headMSize` 增大）减少通信次数。

Note that the reference shape is named — this is a scoped default, not a bare constant, and stating the
shape a default was tuned at is the honesty move worth imitating.

The re-tiling requirement, `:158`, stated outside the table:

> **切换 `tileCnt` 时必须重新调 `GetTilingData`**——`headMSize` 变了，所有 Blaze tiling 字段都会跟着变。

with the derivation map at `:141-148`: `headMSize` → Blaze `baseM` (≤ headMSize, aligned to 16/128);
`n` → `baseN`, `nTailTile`; `ka = k/rankSize` → `baseK`, `scaleKL1`, `stepK`; and `usedCoreNum` derived.

Two clarifications upstream supplies that pre-empt likely wrong inferences. `:87` separates `bufferSize`
from `tileCnt`: "`bufferSize` 独立于 `tileCnt`，默认 4。`tileCnt` 决定通信块总数，`bufferSize` 决定
SHMEM 中同时存在的 buffer 数。`bufferId = mLoopIdx & (bufferSize - 1)` 的位掩码约束作用于 `bufferSize`
（要求 `bufferSize` 为 2 的幂），不约束 `tileCnt`" — so the power-of-two requirement binds `bufferSize`,
not `tileCnt`, and `:198` explicitly denies that `tileCnt` must be a multiple of `bufferSize`. And
`:160-163` denies a plausible worry about `tileCnt=1`: `headMSize=m`, Blaze still derives a small
`baseM` and splits internally, so single-card MMAD performance does not degrade — only the
overlap does.

`:114` gives the selection criteria for a sweep, in priority order: total Task Duration (max across 4
cards) minimised first; then cube ratio near its theoretical ceiling, which upstream puts at 40-70 % for
MC² operators; then AIV and AIC times close together, meaning communication is hidden behind compute.

## 4 · Procedure
Runnable later on a named 950 board with at least 4 cards. This is a multi-card measurement, so the
device discipline is heavier than elsewhere in this block.

Arm A — the constraint rows, one violation per run. Starting from a valid configuration, produce one
variant per row that violates exactly that row and nothing else: `tileCnt > M`; an `M` and `tileCnt`
with non-zero remainder; a `headMSize` below Blaze's derived `baseM`; a `headMSize × kPerRank ×
sizeof(dtype)` well below the stated band (tens of KB) and well above it (tens of MB); and a
`bufferSize × headMSize × kPerRank × rankSize × sizeof(dtype)` exceeding `SHMEM_SPACE_SIZE`. For each,
record where it fails — host derivation, allocation, run time — or that it does not, and whether output
is correct. The third column is the payload: a constraint that neither errors nor corrupts is advice,
not a constraint.

Arm B — the `tileCnt` sweep, which is what the disclaimer demands. For a fixed shape, sweep `tileCnt`
over the divisors of M, **re-running `GetTilingData` at each point** per `:158`, and collect
`msprof --ai-core=on --aic-mode=task-based` per card. Report total Task Duration as the max across
cards, plus cube ratio and AIV/AIC times, per upstream's own criteria. The optimum's *position* is the
readout; upstream predicts it is not at 512 for shapes away from the reference.

Arm C — the re-tiling requirement, made observable. At one non-default `tileCnt`, run twice: once with
`GetTilingData` re-derived, once reusing the tiling struct from the default. Compare correctness and
latency. Upstream states the fields all change; this arm shows whether reusing them is wrong, slow, or
tolerated — three different answers with three different repairs.

Arm D — the shape dependence, which tests the trade's direction rather than the default's value. Repeat
Arm B at (large M, small K) and at (small M, large K). Upstream predicts the optimum moves toward larger
`tileCnt` in the first and smaller in the second. A sweep at one shape cannot test a claim about how the
optimum moves.

Device selection is explicit and stricter here because this is a multi-card operator: the operator names
every card in the group, the harness prints them back with `compiler/version.info` and each resolved SoC
string, occupancy is checked on all of them before the run (shared machine, ≤4 dies), and no card is
substituted for another between points of one sweep. Per upstream's capture protocol
(`ascendc-perf-optimize/references/comm-compute/index.md`), multi-rank capture takes ≥10 iterations,
discards the first 5 as warm-up, means the last 5, and takes the **max across ranks** — a mean across
ranks would hide the straggler that sets the operator's latency.

## 5 · Checker — acceptance declared before the run
Verdict variable `constraint_binds[row]`, one per row, five of them, **never aggregated**. Five
independent constraints behind one boolean is the shape that lets four enforced rows hide the one that is
silently tolerated, and the tolerated one — row 2, the non-zero tail — is the one with a correctness
consequence.

Per row, three declared outcomes, none reinterpretable afterwards: `enforced` (the violating run fails
at the stage upstream names, with a diagnostic naming it); `tolerated-degraded` (it runs, output is
correct, and Arm B's metrics show a cost); `tolerated-silent` (it runs, output is correct, no cost
detectable). A fourth outcome — runs, output **wrong** — is reported first regardless of which row
produced it, because that is the case where a stated constraint is the only guard.

`optimum_tileCnt[shape]` (Arm B) — the `tileCnt` minimising max-across-cards Task Duration. **No pass
threshold**: upstream claims only that the optimum is shape-dependent and not fixed at 512. What is
declared is what would falsify that — the optimum landing at `headMSize = 512` for **all three** shapes
in Arms B and D would mean the default is not merely a starting point, and upstream's disclaimer is
over-cautious. Saying that now prevents a convenient result reading either way.

`retiling_required` (Arm C) — pass iff the reused-tiling run is wrong or measurably slower. A reused
tiling that is correct and equally fast means `:158`'s 必须 is not binding at that point, which is worth
knowing before a sweep harness is built around re-deriving at every step.

The positive fixture, declared before the run: Arm A must include a *valid* configuration run alongside
the five violations, which must complete and produce correct output. If the valid run also fails, the
harness's MC² setup is broken and every `constraint_binds` verdict is void. A second fixture for Arm B:
include `tileCnt = 1`, where upstream states single-card MMAD performance should **not** degrade
(`:160-163`) — if it does degrade sharply, the sweep is measuring something other than communication
overlap and its optimum attributes nothing. Without both, the checker reads only "some configurations
were slower", which is the known blind species.

Process exit codes are not the verdict anywhere: in Arm A a non-zero exit is the expected outcome for
most of the six runs.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No MC² operator was built, no
`tileCnt` was swept, no `msprof` was collected, and no card was contacted. The reference shape and its
Put ≈ 1 MB figure quoted in §3 are upstream's own account of how its default was chosen.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that any of the five constraints binds, or what
happens on violation — Arm A is open for all five, and upstream supplies a consequence column that is an
assertion, not an observation. It does not establish the optimum `tileCnt` for any shape, nor the
direction of the trade upstream describes; Arms B and D are open. It does not establish the UDMA
efficient band: "数百 KB ~ 数 MB" is a range with no measurement behind it in this scope, and it is the
one row of the five whose violation has no crisp failure — which makes it the hardest to test and the
easiest to ignore. There is **no second origin**: all of it is one upstream skill, and the installed
toolkit says nothing about SHMEM, UDMA or Blaze tiling. BOARD is `family-claimed(unverified)`: the
pipeline-tuning material names no board token this book recognises, and no card was contacted — a result
on a 950PR group would establish 950PR only. It says nothing about `SHMEM_SPACE_SIZE` other than
upstream's stated 1 GB default, nor whether it is configurable. It says nothing about the Blaze tiling
fields the re-derivation produces — `baseM`, `baseN`, `baseK`, `stepK`, `usedCoreNum` — beyond that they
change; `stepK` in particular is the subject of contradiction **C-008**, where five upstream statements
disagree about its permitted values, and this entry does not touch that. Nothing transfers to the other
book (RULES.md Art. 1). Finally, upstream's own MC² hard data gate applies upstream of everything here: a
TilingData capture and a `tileCnt=1` isolation test are required before any balancing advice is given,
and this entry assumes rather than establishes that they were done.
