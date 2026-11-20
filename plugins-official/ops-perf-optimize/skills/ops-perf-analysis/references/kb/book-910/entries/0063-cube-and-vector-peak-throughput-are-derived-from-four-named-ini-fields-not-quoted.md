```
ID:        0063-cube-and-vector-peak-throughput-are-derived-from-four-named-ini-fields-not-quoted
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     910B2
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:118 — "Ascend910B2:   4096 × 24 × 1800 × 2 ÷ 10⁶ = 353.89 TFLOPS"; ibid:161 — "**910B2**：128 × 48 × 1800 × 2 ÷ 10⁶ = **22 TFLOPS**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a dense Cube or Vector kernel on a named Ascend910B2 part sustains throughput above the derived figure, or the INI fields the derivation reads hold values other than those quoted.
```

# 0063 · Cube and Vector peak throughput are derived from four named INI fields, not quoted

## 1 · Claim
Upstream asserts a derivation rather than a number. For Cube: `M×K×N × ai_core_cnt × cube_freq ×
2 ÷ 10⁶`, with each factor traced to an INI field — `cube_m_size=cube_k_size=cube_n_size=16` giving
4096, `[SoCInfo] ai_core_cnt`, `[AICoreSpec] cube_freq`, and ×2 because one MAC is a multiply and
an add. For Ascend910B2 that yields 4096 × 24 × 1800 × 2 ÷ 10⁶ = **353.89 TFLOPS** BF16/FP16. For
Vector: `vec_calc_size × vector_core_cnt × vec_freq × 2 ÷ 10⁶`, with `[AICoreSpec] vec_calc_size`
= 128 and `[SoCInfo] vector_core_cnt` = 48, yielding 128 × 48 × 1800 × 2 ÷ 10⁶ = **22 TFLOPS** FP16.
Upstream asserts that 910B2's INI has no independent `vec_freq` and that `cube_freq` is used for
both. Not established here.

## 2 · The wrong branch this removes
0055 records two peak figures quoted with no derivation, and says an agent cannot know how much to
trust a denominator it cannot reconstruct. This entry is the answer to that complaint for the two
compute figures: the derivation is published, every factor names an INI field, and the arithmetic
can be re-run against the installed toolkit on any part.

That changes what an agent should do. Rather than carrying "910B2 is 353 TFLOPS" — which is wrong
on 910B4 (0062: 20 cores at 1.5 GHz, so 4096 × 20 × 1500 × 2 ÷ 10⁶ = 245.8 TFLOPS, arithmetic
performed here) — it carries the formula and reads the two varying factors at runtime. The formula
is portable across the family; the number is not, and the family varies (0009, 0062).

The wrong branch this closes is therefore quoting the number. The one it opens, and which §7 keeps
open, is trusting the formula's *hidden* assumptions: that every Cube cycle issues a full MAC array,
that the Vector unit sustains 128 lanes, and that the clock is the one in the INI rather than a
throttled one.

Note also what the Vector figure reveals about 0055. ops-profiling quotes "float32 Vector 峰值算力约
11.06 TOPS" for Atlas A2. This derivation gives **22 TFLOPS at FP16**, and 22/2 = 11 — so the two are
consistent under a reading in which FP32 Vector runs at half the FP16 rate. **Neither document says
so.** The reconciliation is arithmetic performed here, it is plausible, and it is not established;
0055 §7 named the per-core-versus-whole-chip ambiguity as its largest unknown, and this derivation
settles that half (48 cores are inside the formula, so it is whole-chip) while leaving the dtype
half open.

## 3 · Ground / Source
`ops/npu-arch/references/npu-arch-guide.md` §"Cube 算力公式推导", lines 105-118. The factor table:
```
| M × K × N (Cube MAC 阵列) | 16×16×16 = **4096** | INI `cube_m_size=cube_k_size=cube_n_size=16` |
| AICore 核数 | 24(910B2) / 28(PCIE) / 32(Server) | INI `[SoCInfo] ai_core_cnt` |
| cube_freq | 1800(910B2) / 1650(950PR) MHz | INI `[AICoreSpec] cube_freq` |
| ×2 | FMA 计为 2 次浮点运算 | 1 次 MAC = 1 乘 + 1 加 |
| ÷10⁶ | MAC/s → TFLOPS | TFLOPS = 10¹² FLOPS = 10⁶ × 10⁶ MAC×2 |
```
and the worked line 118: "Ascend910B2:   4096 × 24 × 1800 × 2 ÷ 10⁶ = 353.89 TFLOPS".

The Vector derivation, lines 155-161, factor table then worked example:
```
| vec_calc_size | 128 | ... | INI `[AICoreSpec] vec_calc_size` |
| vector_core_cnt | 48 | ... | INI `[SoCInfo] vector_core_cnt` |
| 频率 (MHz) | 1800 | ... | 910B2: `cube_freq`（INI 无独立 `vec_freq`）；950PR: `[VectorCoreSpec] vec_freq` |
```
"**910B2**：128 × 48 × 1800 × 2 ÷ 10⁶ = **22 TFLOPS**"

Arithmetic re-derived here rather than pasted: 4096 × 24 × 1800 × 2 = 3.5389e11 MAC-FLOPS·MHz →
353.89 TFLOPS ✓. 128 × 48 × 1800 × 2 = 2.2118e7, ÷10⁶ → 22.1 TFLOPS ✓. Both check.

The summary table those derivations feed, line 88-91: "| Cube 算力 BF16/FP16 | 353T | 378T | 432T |"
and "| Vector 算力 FP16 | 22T | 47T [¹](#unverified) | 54T [¹](#unverified) |". **Note the
provenance marks**: the two 950 Vector figures carry an explicit `[¹](#unverified)` footnote and the
910B2 figure does not — upstream marks exactly which of its own numbers are unverified, at
per-cell granularity. That is the best provenance discipline found anywhere in this harvest.

A limit stated in the same section, line 123: "Vector 不支持 bfloat16，故 BF16 总算力即 Cube 算力"
— carried by 0065.

The FP8 heading at line 150 sits above the *Vector* derivation table, which appears to be a
formatting slip in upstream (the formula and factors under it are `vec_calc_size`-based and are
labelled Vector in the worked lines). Recorded, not relied on.

## 4 · Procedure
Proposed, runnable later; not run.

1. INI arm, read-only, no card, and the one that matches the claim: `grep -R` over
   `"$ASCEND_HOME_PATH"/*/data/platform_config/` for `cube_m_size`, `cube_k_size`, `cube_n_size`,
   `ai_core_cnt`, `cube_freq`, `vec_calc_size`, `vector_core_cnt`, `vec_freq`. Record every value
   against its SoC name. Re-run the two formulas from the values found; do not paste the result.
2. Runtime arm: `GetCoreNumAic()` / `GetCoreNumAiv()` on a named die (occupancy before and after,
   no substitution) and compare against the INI's counts — 0012's necessary-not-sufficient rule
   applies, and a divergence here is more interesting than either formula.
3. Achievability arm: a dense Cube kernel (large M, N, K, FP16, all cores, L1-resident operands) and
   a dense Vector kernel (UB-resident, high arithmetic intensity, FP16), each swept upward until
   throughput plateaus. Report the plateau in TFLOPS and its ratio to the derived peak.
4. Repeat the Vector arm at FP32 — this is what tests the 11.06 reconciliation of §2, and no
   source states it.
5. Five repeats each, first discarded.

## 5 · Checker — acceptance declared before the run
`formula_reproduces`: PASS iff the INI values found in arm 1, put through the published formulas,
give 353.89 and 22.1 for the 910B2 SoC to within 0.1 %. This arm tests the *derivation*, which is
the claim, and needs no device — a mismatch here means upstream's arithmetic or its field
attribution is wrong, which is a stronger finding than any timing result.
`cube_attainment`, `vec_attainment`: achieved ÷ derived peak. No pass threshold is declared, because
a peak is not required to be achievable and this book will not score a real machine against a
number nobody measured. The ratios are the deliverable.
`fp32_ratio` from arm 4: PASS for §2's reconciliation iff FP32 Vector throughput is within 10 % of
half the FP16 figure. This verdict is labelled as testing **this book's inference**, not upstream's
assertion — a failure corrects §2 and leaves §1 standing, and a success is not credited to upstream.
An attainment above 1.0 overturns the derived peak outright and is the clean red input.
Control: the dense Cube arm must exceed the dense Vector arm by roughly the 353/22 ratio; if it does
not, one of the two kernels is not compute-bound and its attainment figure is void.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. BOARD names 910B2 because that is the part the worked examples
are about — not a part this book ran on. The derived figures are **peaks from a formula**, not
achievable throughput, and 0055 §2 records why the gap matters. This entry does not establish the
formula's hidden assumptions: that a full MAC array issues every cycle, that 128 Vector lanes
sustain, or that the INI clock is the operating clock under load. It does not establish the FP32
Vector rate — §2's 22/2 = 11 reconciliation with ops-profiling is arithmetic performed here and is
explicitly unestablished. It does not establish figures for any other DAV_2201 part; the formula
ports, the numbers do not (0062). It says nothing about int8, FP8 or sparse Cube throughput.
