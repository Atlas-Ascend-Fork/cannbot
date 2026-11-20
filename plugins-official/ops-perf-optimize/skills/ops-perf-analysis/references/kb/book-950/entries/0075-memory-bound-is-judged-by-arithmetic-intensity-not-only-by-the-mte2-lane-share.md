```
ID:        0075-memory-bound-is-judged-by-arithmetic-intensity-not-only-by-the-mte2-lane-share
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/memory.md:5-9 — "## 判定条件 - MTE2 利用率高（AIC 带宽接近理论峰值） - Vector/Cube 单元存在等待数据的空闲气泡 - 计算密度低（Ops/Byte 低于硬件能力）"
           ops/ascendc-perf-optimize/references/single-core-pipeline/memory.md:34-38 — "## Tiling 修正建议 - 调整 UB tile 大小以提升 L2 命中率 - 优化数据搬移粒度与对齐参数 - 调整多核切分以减少单核数据量"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a kernel on a named 950 board whose arithmetic intensity is well above the machine's
           balance point — so it cannot be bandwidth-limited — and which nevertheless satisfies the
           MTE2-share arm of the routing tree and responds to a memory technique: the three
           conditions would then not be co-extensive, and the page's entry test would admit
           kernels its strategies cannot help.
```

# 0075 · Memory bound is judged by arithmetic intensity, not only by the MTE2 lane share

## 1 · Claim
Upstream asserts three joint conditions for the memory-bound diagnosis: MTE2 utilisation high with
AIC bandwidth near its theoretical peak; Vector or Cube units showing idle bubbles while waiting for
data; and *computational density low* — Ops per Byte below the hardware's capability. Upstream
asserts three tiling corrections for that state: size the UB tile to improve the L2 hit rate, tune the
transfer granularity and alignment parameters, and adjust the multi-core split to reduce the per-core
data volume. Not established here; nothing was measured, and no value of Ops/Byte, peak bandwidth or
"hardware capability" is given anywhere in this scope.

## 2 · The wrong branch this removes
The routing tree (0005) reaches this page on a lane-share condition alone — MTE2 utilisation high with
bandwidth as the dominant limit — and a lane share is a statement about *time*, not about *work*. Two
kernels with the same MTE2 share can be in opposite regimes: one moving a large volume with little
arithmetic (genuinely bandwidth-limited, where every technique on this page applies), and one moving a
small volume badly — unaligned, fragmented, or repeatedly (where the fix is the copy's shape, not its
size, and reducing the per-core data volume does nothing). The third condition is what separates them,
and it is the only bound predicate in the whole diagnosis layer that is not a lane ratio.

The wrong branch this removes is therefore a mis-selection *within* the page: an agent routed here by
lane share alone will reach for the tiling corrections — smaller tiles, fewer bytes per core — when
the operator's arithmetic intensity says bandwidth was never the constraint, and the right cards are
the alignment and fusion ones (0040, 0020, 0044). The second-order cost is that shrinking the tile to
"reduce per-core data" multiplies the tile count, which is 0017's scalar-bound failure arriving from a
memory-page recommendation.

## 3 · Ground / Source
`memory.md:5-9`, the whole judgement block, quoted in SOURCE. The three conditions are stated as a
list with no connective — whether they are conjunctive or alternative is not said, which matters
because the routing tree at `index.md:22` uses only the first, and `index.md:42` restates the arm as
`MTE2/AIC 带宽为主导瓶颈`.

`memory.md:11`, the MC² veto that precedes every other condition on this page: `CrossCoreWaitFlag`
on the MTE2 pipeline makes the ratio include communication idling, so the isolation test of 0060 must
clear it first — 若 `mte2_polluted = true`，本文档策略无效. That is the one condition on this page with
a numeric test behind it, and it is a test of the *instrument*, not of the operator.

`memory.md:13-16`, the simulation reading points: overlap of the MTE2 timeline with the compute
timeline, and identification of large transfer windows and mergeable sequences of small ones.

`memory.md:20-32`, the feature-to-card routing table — nine rows mapping a diagnosed feature to the
cards this book carries as 0040 (mem-01), 0020/0027 (vec-01/vec-05), 0029 (vec-06), 0042 (mem-02),
0043 (mem-03), 0045 (mem-05), 0049 (mem-07), 0044 (mem-04), 0048 (mem-06).

`memory.md:34-38`, the tiling corrections, quoted in SOURCE. Note what each presupposes and does not
state: the L2 hit-rate advice presupposes an L2 capacity (unestablished — the register's C-002 row
records a disagreement about a related capacity, and no 950 L2 size is established in this book); the
granularity and alignment advice presupposes an alignment constant, which upstream itself refuses to
unify (0041); and the multi-core advice presupposes a core count (unestablished for either board
token). So all three corrections are stated over quantities this scope never supplies.

Nowhere in this scope is a peak bandwidth figure, a machine balance point (Ops/Byte at which
bandwidth and compute cross), or a method for computing an operator's arithmetic intensity from
msprof output. The third judgement condition is therefore not evaluable from the instruments the
same skill defines (0010's metric table), which is why this entry's §4 has to construct the
measurement rather than cite one.

## 4 · Procedure
Later phase, needs a card. Board token from the driver readout; device selection per 0010, with
occupancy recorded before and after and no assumption that the die is idle or which 950 board it is.

1. Establish the machine balance point empirically rather than from a datasheet: build a
   parameterised kernel that performs `k` fused multiply-adds per loaded element, sweep `k` over
   powers of two from 1 to 256 at a fixed large working set, and record `aiv_time` and the achieved
   bytes/second and Ops/second at each `k`. The knee — where achieved bandwidth stops rising and
   achieved Ops/s starts rising — is the balance point in Ops/Byte for this dtype and access pattern.
2. Build a labelled case set of eight kernels: four with arithmetic intensity well below the measured
   balance point (genuinely bandwidth-limited) and four well above it, arranged so that two of the
   latter still show a high MTE2 lane share by moving their (small) data badly — unaligned, in many
   short copies.
3. For every kernel, record: `aiv_mte2_ratio`, the achieved bytes/second against the measured peak,
   the Vector/Cube idle fraction, and the computed Ops/Byte.
4. Apply two treatments to every kernel, in randomised build order, five repetitions each, median and
   spread: (V) a volume treatment from this page's tiling corrections — reduce the per-core data
   volume and re-tile; (S) a shape treatment — the alignment and contiguity card (0040) plus copy
   merging (0043), leaving the volume unchanged.

## 5 · Checker — acceptance declared before the run
Verdict variables, declared before any run: `balance_point` (Ops/Byte, from step 1, with the sweep
published); `intensity(c)` per kernel; and `dV(c)`, `dS(c)` — the gain from each treatment as a
fraction of baseline `aiv_time`, each compared against that kernel's spread.

Acceptance of the third condition as a discriminator: for every kernel with `intensity(c)` below
`balance_point`, `dV(c) > dS(c)`; and for every kernel above it, `dS(c) > dV(c)` — including the two
high-intensity kernels that nevertheless show a high MTE2 share, which are the cases the lane-share
arm alone would route wrongly. Acceptance of the page's own entry test: the three judgement conditions
hold together on the low-intensity kernels and not on the high-intensity ones.

The process exit code is not the verdict: every kernel builds and runs in both arms. The verdict is
the printed table of `(kernel, intensity, mte2_ratio, dV, dS, spread)`, published whole — including
the kernels where the two treatments tie, which are retained and named rather than dropped.

This checker can go red, and the input that does it is named in advance: the two high-intensity,
high-MTE2-share kernels. If `dV > dS` on those, arithmetic intensity does not discriminate and this
entry is corrected in place. And if step 1's sweep shows no knee at all, `balance_point` is
undetermined, the whole table is reported as `balance_point_unresolved`, and no claim about the third
condition follows — a checker that read only the lane share would have reported a clean result from
the same data, which is the failure species this design avoids.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. No value is established for peak bandwidth, for the balance point,
for L2 capacity or for any core count — so all three of the page's tiling corrections rest on
quantities this book does not have, and the third judgement condition is not evaluable from the
metric set the same skill defines. It does not establish whether the three conditions are conjunctive
or alternative; upstream states them as an unconnected list. It says nothing about the AIC/Cube side
beyond quoting the page's mention of it, nothing about MC² operators (whose MTE2 ratio must first
clear 0060's pollution test), and nothing about which of the nine cards this page routes to is right
for a given feature — each of those is its own entry.
