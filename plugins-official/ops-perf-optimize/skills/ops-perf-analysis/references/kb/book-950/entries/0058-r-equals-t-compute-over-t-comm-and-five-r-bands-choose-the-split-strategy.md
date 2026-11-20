```
ID:        0058-r-equals-t-compute-over-t-comm-and-five-r-bands-choose-the-split-strategy
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/bound_diagnosis.md:11-17 — "| R ≈ 1 (0.9~1.1) | 完美平衡 | … | 等分切分即最优 | | 1.1 < R ≤ 2 | 计算 bound | … | 用通信掩盖计算，增大 tileCnt | | R > 2 | 强计算 bound | … | 增大 tileCnt 收益极小，倾向少切分；须搜索确认 | | R < 1 | 通信 bound | … | 用计算掩盖通信，增大 tileCnt | | R < 0.5 | 强通信 bound | … | 从短块出发搜索，最大化 tileCnt |"
           ops/ascendc-perf-optimize/references/comm-compute/bound_diagnosis.md:3 — "不同数据量下通信和计算耗时比值 R 差异巨大（实测 R 从 0.3 到 9.8）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board set in which the best split for cases at R = 1.5
           and R = 3 is the same shape of split — the 1.1/2 boundary would then separate nothing —
           or in which a case at R = 0.95 behaves like the R < 1 row rather than the R ≈ 1 row,
           which the table's overlapping conditions cannot decide.
```

# 0058 · R = T_compute / T_comm, and five R bands choose the split strategy

## 1 · Claim
Upstream asserts that the ratio R = β/α = T_compute / T_comm, obtained from an isolation test at
`tileCnt=1`, classifies an MC² operator into one of five bands with different split strategies:
R ≈ 1 (0.9–1.1) perfectly balanced, equal split optimal; 1.1 < R ≤ 2 compute bound, hide compute
behind communication and raise tileCnt; R > 2 strongly compute bound, raising tileCnt gains little
so prefer fewer splits, confirm by search; R < 1 communication bound, hide communication behind
compute and raise tileCnt; R < 0.5 strongly communication bound, search from the short block and
maximise tileCnt. Upstream asserts the balancing ratio ρ = max(R, 1/R), the long-to-short block size
ratio, and reports having measured R between 0.3 and 9.8. Not established here.

## 2 · The wrong branch this removes
Without R, an agent optimising an MC² operator has no way to know which phase to protect, and the
two mistakes are symmetric and expensive: splitting finely to hide communication that was never the
bottleneck (paying the inflation of 0070 for nothing), or splitting coarsely when communication
dominates and leaving most of it unmasked. R is one number from two builds and it decides the
direction of the entire search.

What the table cannot do is decide its own boundaries. Two of the five rows overlap: R = 0.95
satisfies both "R ≈ 1 (0.9~1.1)" and "R < 1", and R = 0.4 satisfies both "R < 1" and "R < 0.5"; the
table states no precedence. An agent implementing it literally as an ordered if-chain gets a
different answer depending on the order it happens to write the rows in, and both orders look
faithful to the document. This is the same defect species as the single-core routing tree (0005),
in a table that otherwise carries numbers.

## 3 · Ground / Source
`bound_diagnosis.md:1-19`. The preamble states the purpose and the measured range quoted in SOURCE,
and the reason the classification comes first: 需首先通过 α/β 分解精确判定 Bound 类型，以确定长短块
配平策略和搜索方向. The five-row table is quoted in SOURCE. `:19` adds 配平比 ρ = max(R, 1/R)，即
长块与短块的 M 大小之比 — a definition this book flags, because the search's P4 rule uses ρ in a way
that contradicts the strategy diagrams (0065, 0066).

α and β, `:40-46`: `α = T_comm / M` (μs per row of communication), `β = T_compute / M` (μs per row of
compute), `R = β / α = T_compute / T_comm`. The output block, `:52-60`, names the fields a diagnosis
must emit: `bound_type` ∈ {balanced, compute, strong_compute, comm, strong_comm}, R, α, β, T_comm,
T_compute, ρ.

The same routing decision appears a second time in this directory, in qualitative form:
`comm-compute/index.md:126-128` routes on 计算耗时 >> 通信耗时 / 通信耗时 >> 计算耗时 / 通信 ≈ 计算
with no value for `>>`. So the chain contains a numeric version and a qualitative version of one
decision, in two files, with no cross-reference. Recorded as C-950core-012, together with the
band-overlap defect as C-950core-013.

The strategy consequences of each band are elaborated in `pipeline_balancing.md:86-154` (short-block
placement, 0063) and `:432-446` (the R-value configuration table, 0073), and the inflation
asymmetry in `expansion_analysis.md:30-36` (0070).

## 4 · Procedure
Later phase, needs cards on all ranks; capture per 0057, isolation per 0059.
1. Device selection per 0057: explicit device list, one rank per device, board token per rank from
   the driver, occupancy recorded before and after.
2. Choose one MC² operator and vary the problem size so that R sweeps the reported range 0.3 to 9.8,
   in at least eight steps, with R measured — not predicted — at each step by isolation test.
3. At every step, run the full split search of 0069 and measure the top candidates, so the *best
   measured* split shape is known independently of the band the table would assign.
4. Include at least two problem sizes engineered to land in the overlap regions, R ≈ 0.95 and
   R ≈ 0.45, and record which strategy actually wins there.

## 5 · Checker — acceptance declared before the run
Verdict variables, declared before the sweep: `band_agrees(step)` = whether the best measured split
shape matches the strategy the band prescribes (equal split / raise tileCnt / fewer splits /
maximise tileCnt); `boundary_sharp(b)` for each boundary b ∈ {1.1, 2, 1, 0.5} = whether the best
shape changes across b and not within the neighbouring bands; and `overlap_decided` = whether the two
overlapping regions have a single winning strategy.

Acceptance of the table: `band_agrees` for every step and `boundary_sharp` for every boundary. The
overlap regions cannot be judged against the table — no prescription exists — so `overlap_decided`
is reported as new information, and if the winner there differs from both candidate rows, that is
recorded rather than assigned to the nearer row.

Exit code is not the verdict. Every step publishes its measured R, the full candidate ranking and the
spread, so a boundary that is smooth rather than sharp is visible as a gradient instead of being
reported as agreement.

Red input: two adjacent steps inside one band. Their best split shapes must agree; if the best shape
changes *within* a band as much as it does across a boundary, the bands are not carrying the
structure attributed to them and no boundary claim survives.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. The four boundary values have no derivation anywhere upstream, no board, no
operator family, and the 0.3–9.8 range is quoted without case identity. The overlapping conditions
are not resolved here, by design (Art. 7). R is defined from two isolation builds, so everything in
this entry inherits 0059's open question about whether commenting out one process leaves the other's
cost unchanged. Nothing here covers operators with more than two phases, or with communication on
both sides of the computation.
