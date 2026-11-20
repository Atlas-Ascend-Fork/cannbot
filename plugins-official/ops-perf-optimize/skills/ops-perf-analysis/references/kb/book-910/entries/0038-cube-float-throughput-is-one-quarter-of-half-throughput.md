```
ID:        0038-cube-float-throughput-is-one-quarter-of-half-throughput
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured, and no architecture is stated
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:20 — "Cube float 算力仅为 half 算力的 1/4"; ibid:416 — "| Cube float 算力 | half 算力的 1/4 | — |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired Matmul on a named DAV_2201 board at identical shape shows an fp32-to-fp16 time ratio materially different from 4 — in particular a ratio near 2, which would indicate a different throughput relationship.
```

# 0038 · Cube float throughput is one quarter of half throughput

## 1 · Claim
Upstream asserts that the Cube unit's float (fp32) compute throughput is one quarter of its half
(fp16) throughput. Upstream states this twice: once as a key characteristic of the compute units
and once as a row in the hardware-constraint table. No architecture is stated for either. Not
established here.

## 2 · The wrong branch this removes
An agent asked to preserve precision reaches for fp32 accumulation or fp32 inputs, and prices the
change as a 2× memory cost — which is what the byte width suggests and what an intuition trained on
CPUs supplies. The Cube penalty is 4×, not 2×, so a precision decision that looked like a modest
trade is a large one. On a Cube-bound operator it is the dominant term.

The inverse branch is equally live and is why the entry is worth its number even where fp32 is
required: an agent that has measured an fp32 Matmul and finds it four times slower than expected
will look for a bug. There is none. Knowing the ratio turns an anomaly into a budget.

Note the claim is about *Cube* throughput specifically. Vector fp32 throughput is a different
quantity — upstream quotes an Atlas A2 figure of 11.06 TOPS for fp32 Vector (0056) — and the two
must not be merged into one "fp32 is slow" heuristic.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §1.1 计算单元, in the 关键特性
list at line 20: "- Cube float 算力仅为 half 算力的 1/4". Restated in §7 硬件约束速查表, line 416:
`| Cube float 算力 | half 算力的 1/4 | — |` — with an empty remedy column, as with 0018's DCache
row.

Context from the same section, line 13: "| **Cube** | 矩阵计算单元 | 执行矩阵乘法，以 fp16 为例
每次可完成 16×16 矩阵乘法 | L0A × L0B → L0C |" — the 16×16 shape is quoted for fp16 specifically,
which is consistent with a smaller effective shape at fp32 but does not state one.

The MAC array figure from the truth source,
`ops/npu-arch/references/npu-hardware-params.md:37`: "| Cube MAC 阵列 |
`cube_m_size / cube_k_size / cube_n_size` | 16×16×16 | 一个周期完成 4096 次 MAC |" — 4096 MACs per
cycle, dtype unstated. If that figure is the fp16 rate, the claim puts fp32 at 1024 MACs per cycle.
That arithmetic is performed here and is NOT an upstream claim; upstream never connects the two
statements, and the 4096 figure's dtype is exactly the missing piece.

**Both statements are the same file and the same repo**: one origin, twice. And neither carries an
architecture, in a document that elsewhere separates 910B1/B2, 910B3, 950 and 310P3 into columns.
So the ratio is asserted as if it were universal across a document that knows it is not universal
about anything else.

No source in scope gives an fp32 Cube figure for DAV_2201 in absolute terms, nor states whether
bf16 shares the fp16 rate — a question of immediate practical weight for training workloads, and
one this entry cannot answer.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Paired Matmul at identical M, N, K, identical tiling, identical core count, differing only in
   dtype: fp16 and fp32. Build both, md5 the binaries to confirm they differ, and record the
   tiling actually chosen for each — a framework that picks a different tiling for fp32 would make
   the comparison a comparison of two schedules rather than of two throughputs.
3. Shapes must be chosen Cube-bound, not memory-bound, or the ratio measures GM bandwidth (which is
   2× by byte width) rather than Cube throughput (claimed 4×). Verify by checking `aic_cube_ratio`
   exceeds 80 % in the fp16 arm before comparing; if it does not, enlarge K and repeat.
4. Add bf16 as a third arm. It is not in upstream's claim and that is precisely why it is worth
   measuring — the fp16-versus-bf16 result is not predicted by anything in scope.
5. Five repeats per arm, first discarded, arms interleaved.

## 5 · Checker — acceptance declared before the run
Verdict variable `cube_ratio = t_fp32 / t_fp16`, medians over four post-warm-up repeats.
Gate, run first: `aic_cube_ratio(fp16) > 0.8`. Without it the arms are not Cube-bound and no
verdict is issued — this is the check that stops the procedure from measuring bandwidth and calling
it throughput.
PASS iff `cube_ratio` lies in [3.4, 4.6].
The discriminating red input is a ratio near 2.0, which is what a purely byte-width explanation
predicts and what an agent would expect without this entry. Landing there would mean either the
claim is wrong or the gate failed, and the gate result tells which.
`bf16_ratio = t_bf16 / t_fp16` is reported with no declared expectation, labelled as unpredicted by
any source — reporting a number nobody claimed is how the gap in §3 gets closed.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. **No architecture is stated by the source**, in a document that
is otherwise per-chip — so this entry does not establish the ratio for DAV_2201 specifically, only
that upstream asserts it without scope. It does not establish absolute throughput at either dtype;
the 4096-MAC arithmetic in §3 is this book's, from a figure whose dtype upstream does not give. It
says nothing about bf16, int8, or the mixed-precision paths where inputs and accumulator differ —
which is how most real Matmuls run, and where the ratio may be neither 1 nor 4. It does not cover
Vector fp32 throughput, which is a different unit and a different claim (0056).
