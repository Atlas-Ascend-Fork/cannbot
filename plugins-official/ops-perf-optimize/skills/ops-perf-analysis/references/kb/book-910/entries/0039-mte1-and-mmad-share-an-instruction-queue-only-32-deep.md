```
ID:        0039-mte1-and-mmad-share-an-instruction-queue-only-32-deep
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — drafted from one upstream origin; nothing measured, and no architecture is stated
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:33 — "MTE1 和 MMAD 指令队列深度仅 32，容易满导致流水断流"; ibid:410 — "| MTE1/MMAD 队列 | 深度仅 32，容易满 | 使用 Load3D 替代 Load2D |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an instruction-count sweep on a named DAV_2201 board shows no stall onset near 32 outstanding MTE1 or MMAD instructions.
```

# 0039 · MTE1 and MMAD share an instruction queue only 32 deep

## 1 · Claim
Upstream asserts that the MTE1 and MMAD instruction queues have a depth of only 32, that they fill
easily, and that a full queue breaks the pipeline. Upstream prescribes replacing `Load2D` with
`Load3D` as the remedy, and separately flags "MTE1 队列满" as a profiling signal with the same fix.
No architecture is stated. Not established here.

## 2 · The wrong branch this removes
A Cube tiling that issues many small L1→L0 loads — fine-grained `Load2D` over a narrow K, or a
deeply split `stepK` — generates a long stream of MTE1 instructions. Each is cheap; the queue is
the constraint, not the bandwidth. Once it fills, the Scalar unit blocks on issue, and the stall
propagates backwards into everything that unit was also dispatching. The observable is an inflated
SCALAR or FLOWCTRL time, which points at control overhead rather than at the load granularity that
caused it.

The wrong branch is therefore not "issuing too much data" but "issuing too many instructions", and
those two have opposite fixes. An agent optimising for data volume makes tiles smaller, which makes
this worse. Nothing in a data-volume model contains a term for instruction count.

The remedy upstream names — `Load3D` for `Load2D` — works by folding many loads into one
instruction, which is only available where the access pattern suits it. Where it does not, the
alternative is coarser tiling, and that trades against L0 capacity (0005).

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §1.2 搬运单元, in the
搬运注意事项 list at line 33: "- MTE1 和 MMAD 指令队列深度仅 32，容易满导致流水断流".
§7 硬件约束速查表, line 410: `| MTE1/MMAD 队列 | 深度仅 32，容易满 | 使用 Load3D 替代 Load2D |`.
§4.3 特殊指标, line 215: `| MTE1 队列满 | L1→L0 指令队列深度 32 已满，考虑使用 Load3D |`.

Three statements, one file, one repo: one origin stated three times. Note that §1.2 says "MTE1 和
MMAD 指令队列" (plural queues, one depth) while §7 writes "MTE1/MMAD 队列" (ambiguous) and §4.3
attributes the depth to the "L1→L0 指令队列" alone. Whether there is one shared 32-deep queue or two
32-deep queues is not determined by the text, and the two readings differ in what a fix should
target. Recorded here rather than resolved.

Context for the path, same file line 26: "| **MTE1** | Move To Engine 1 | L1 → L0A/L0B, L1 → BT
Buffer | Cube 数据加载 |".

No architecture is stated, in a document with per-chip columns elsewhere. No source in scope gives
a queue depth for any other Ascend generation, so there is no comparison available.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Sweep the number of outstanding MTE1 instructions rather than the data volume: a Cube kernel
   with fixed total K, tiled into `n` L1→L0 loads with `n` swept over 8, 16, 24, 28, 32, 36, 48,
   64. Total bytes moved is held constant across the sweep — only the instruction count varies.
   That constancy is the design of the experiment and must be asserted by computing bytes per arm
   and confirming equality.
3. Per `n`: `aic_mte1_ratio`, `ai*_mte1_wait_ratio`, `aic_scalar_ratio`, FLOWCTRL time, and total
   task duration. Five repeats, first discarded.
4. The claim predicts a knee near `n = 32` in the wait ratio, not in the transfer time. Report both
   so the two can be distinguished.

## 5 · Checker — acceptance declared before the run
Verdict variable `queue_knee`: the smallest `n` at which `ai*_mte1_wait_ratio` exceeds its median
over `n ∈ {8, 16}` by more than three times that baseline's spread.
PASS iff `queue_knee` lies in [28, 40].
Gate, checked first: total bytes moved must be equal across all arms to within 0.1 %. If it is not,
the sweep varies two things and no verdict is issued — this is the check that keeps the experiment
from measuring transfer size and reporting it as queue depth.
Red inputs: no knee anywhere (INCONCLUSIVE if the wait counter is flat at all `n`, which is
distinguished by confirming the counter is non-zero somewhere; overturning if it rises smoothly
with `n` and shows no threshold), or a knee near 16 or 64, either of which would put the depth
elsewhere and correct the entry.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; **no architecture stated by the source**. This entry does not
resolve whether MTE1 and MMAD share one queue or have two of the same depth (§3) — a distinction
that matters for the fix and that §4 as written does not separate, since it sweeps MTE1 only. It
does not establish the cost of a full queue, only that stalling occurs. It does not establish that
`Load3D` helps, nor by how much; that is upstream's prescription and would need its own paired
arm. It says nothing about the Vector-side queues, whose depths no source in scope gives.
