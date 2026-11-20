```
ID:        0072-local-matmul-must-outlast-the-first-communication-or-the-cube-stalls
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/local_matmul.md:62 — "通信后计算 + 计算 Bound 场景下，Local matmul 的耗时要掩盖住首块通信，否则无法保证 matmul 计算连续性。若 Local matmul 耗时不足，需调整 Local 数据量或通信粒度"
           ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:128 — "约束： 1. local_matmul ≥ comm[1]（保证首块通信完成，matmul 连续） 2. compute[k] ≥ comm[k+1]"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured case on a named 950 board, comm-then-compute and compute bound, in which a
           local matmul shorter than the first communication costs nothing measurable against one
           that covers it — the continuity requirement would then not bind, and the constraint could
           be dropped from the balancing model.
```

# 0072 · Local Matmul must outlast the first communication, or the cube stalls

## 1 · Claim
Upstream asserts that in the communication-then-computation, compute-bound case the local matmul must
take at least as long as the first block's communication — `local_matmul ≥ comm[1]` — because
otherwise the cube runs out of work before the first communicated block arrives and the matmul stream
is broken; and that if the local matmul is too short, either the local data volume or the
communication granularity must be adjusted. Upstream states the same constraint as the first of two in
the balancing strategy for that quadrant, the second being `compute[k] ≥ comm[k+1]`. Not established
here; nothing was measured.

## 2 · The wrong branch this removes
Local Matmul (0071) is introduced as a way to fill the fill-stage hole, which invites treating it as
free — any local work is better than idling. This constraint says the opposite for one specific
quadrant: local work that runs out early leaves the cube idle *again*, and a matmul stream that stops
and restarts pays the pipeline refill that 0070 names as the first cause of compute inflation. So the
local matmul is not just filler, it is the first term of a continuity chain, and its length is a
design parameter with a lower bound.

The wrong branch in the other direction is adjusting the wrong knob. Upstream names two remedies —
change the local data volume, or change the communication granularity — and the second is the one that
couples back into the split search: making the first communicated block smaller reduces `comm[1]`, and
that is a change to the split, which then has to be re-searched. An agent that only considers
enlarging the local share may not be able to (the local share is fixed at 1/rankNum of the data).

## 3 · Ground / Source
`local_matmul.md:58-66`, the constraints section. The continuity constraint is quoted in SOURCE; the
second constraint in that section is the independent-tiling-data requirement (0071).

`pipeline_balancing.md:114-130`, the Pattern A compute-bound quadrant, states it inside the strategy
with its reasoning:

> **计算 Bound**：计算要掩盖通信，并且 matmul 计算不能被通信中断。由于有 Local matmul 的存在，第一次
> 通信可以和 Local matmul 做掩盖。在第一块通算切分 matmul 计算时，一定要保证首块通信完成，因此
> **Local matmul 的耗时要掩盖住通信**，才能保证 matmul 的计算连续性。从配平角度，首块的 matmul 耗时
> （非 local 块，而是通算切分块）≥ 通信第二块的耗时。整体上第 N 块的计算耗时 ≥ 第 N+1 块的通信耗时。
> **短块在后（drain 端）**。

with the diagram pairing `Local matmul` against 通信块1 and the two-part constraint quoted in SOURCE.
`pipeline_balancing.md:116` states the general enabling fact once more — 不需要通信的 Local 数据可以
提前展开，在首次做通信时可以与 Local matmul 做掩盖.

The look-up table row, `pipeline_balancing.md:152`: 通信后计算 | 计算 Bound | 后（drain 端） |
local_matmul ≥ comm[1]; compute[N] ≥ comm[N+1].

Note that this constraint is stated for exactly one of the four quadrants. For Pattern A
communication-bound (`:132-140`) the corresponding requirement is different — communication issues
back-to-back and only the tail matmul must be minimised while keeping Mac utilisation — and for the
two Pattern B quadrants the local matmul is placed last, so no continuity constraint on the first
communication arises. A consumer must not generalise this bound across quadrants.

## 4 · Procedure
Later phase, needs one card per rank; capture per 0057, R per 0059, TilingData per 0062.
1. Device selection per 0057; board token per rank from the driver readout; occupancy either side.
2. One Pattern A operator at R ≈ 3 (compute bound, measured not assumed), with Local Matmul in the
   preemptive-independent mode.
3. Vary the local matmul's duration deliberately, holding the communicated split fixed: run it over a
   fraction f of the local rows, f ∈ {0.25, 0.5, 0.75, 1.0, and one value above 1.0 by including some
   recomputation}, so `local_matmul / comm[1]` sweeps from well below 1 to above 1. Measure `comm[1]`
   independently per 0059.
4. Measure T_total for each f per the ten-iteration protocol, and from the trace record the AIC idle
   interval between the end of the local matmul and the start of the first communicated block's
   computation.
5. Correctness: the f < 1 variants leave rows uncomputed by design, so the arithmetic result is not
   comparable — they are timing probes only, and must be labelled as such in the record so no one
   later reads them as a shippable configuration.

## 5 · Checker — acceptance declared before the run
Verdict variables `T_total(f)`, `idle_gap(f)` and `ratio(f) = local_matmul(f) / comm[1]`. Acceptance
of the constraint: `idle_gap` is materially positive for every f with `ratio < 1` and near zero for
`ratio ≥ 1`, and `T_total` improves as `ratio` approaches 1 and then flattens — a continuity
requirement predicts a knee at `ratio = 1`, not a monotone slope.

Exit code is not the verdict. The knee's position is reported with the spread of the neighbouring
points; if the curve has no knee within the sweep, the constraint is not observable at this operator's
scale and that is the finding.

Red input: `ratio` well above 1. Beyond the knee, extra local work must not keep improving T_total —
if it does, the local matmul is buying something other than continuity (for instance it is simply
faster per row than the communicated blocks), and the attribution fails.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. No board, operator, rank count or R value. The constraint is stated for one of the
four order-by-bound quadrants and this entry establishes nothing for the other three. It does not
quantify the cost of a broken matmul stream — the refill bubble it invokes is named in 0070 and
measured nowhere. The remedies (adjust local volume, adjust communication granularity) are named
without a rule for choosing between them, and the second re-enters the split search, so the
constraint and the search are coupled in a way neither document models.
