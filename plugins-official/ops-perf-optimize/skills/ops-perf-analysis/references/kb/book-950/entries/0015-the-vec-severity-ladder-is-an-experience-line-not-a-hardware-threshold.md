```
ID:        0015-the-vec-severity-ladder-is-an-experience-line-not-a-hardware-threshold
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/vec.md:17-21 — "| VEC 占比 | 等级 | 优化方向 | | 50–65% | 轻度 | DoubleBuffer + UB 融合有较大收益 | | 65–80% | 中度 | 减少 Cast 或融合指令 | | >80% | 深度 | 微架构调优收益有限，须从算法层减计算量 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a case set on a named 950 board in which kernels above 80% `aiv_vec_ratio` respond to
           micro-architectural work (fusion, DB, instruction selection) as strongly as kernels
           in the 50–65% band — the ladder's top rung would then be false, and its advice
           ("go to the algorithm") actively costly.
```

# 0015 · The VEC severity ladder is an experience line, not a hardware threshold

## 1 · Claim
Upstream asserts a three-rung ladder on the VEC share of `aiv_time`: 50–65% is mild, where
DoubleBuffer and UB fusion pay well; 65–80% is moderate, where Cast reduction and instruction
fusion are indicated; above 80% is deep, where micro-architectural tuning has limited return and
the compute volume itself must be reduced at the algorithm level. Upstream asserts separately,
in the metrics page that governs all thresholds, that lines of this kind are 经验判定线 and that
near a line the measured `aiv_time` still decides. Not established here; nothing was measured.

## 2 · The wrong branch this removes
Two branches. Without the ladder, an agent that finds a VEC-dominated kernel applies whatever
technique it read last, and on a kernel at 90% vector share it will spend its budget on fusion
and buffer tricks whose ceiling is small — the ladder's real content is a *stopping rule* for
micro-optimisation. With the ladder taken as a threshold rather than a hint, the opposite
failure: an agent reports "vec ratio 0.79, moderate, apply Cast reduction" for a kernel with no
Casts at all, because the ladder's rungs name treatments and the agent treats the rung as a
prescription. The rung is a prior over which treatment is likely to pay; the diagnosis pages'
feature table (`vec.md:80-92`) is what actually selects the card.

## 3 · Ground / Source
`vec.md:15-21`, the whole block:

> **瓶颈严重程度分级**：
> | VEC 占比 | 等级 | 优化方向 |
> | 50–65% | 轻度 | DoubleBuffer + UB 融合有较大收益 |
> | 65–80% | 中度 | 减少 Cast 或融合指令 |
> | >80% | 深度 | 微架构调优收益有限，须从算法层减计算量 |

The band below 50% is unstated: a kernel at 45% vector share is on no rung, and the routing tree
(0005) would not have called it VEC bound either. The governing caveat is `metrics.md:63`
(entry 0009), which names 经验判定线 and requires `aiv_time` near a line. `vec.md:11-13` gives
the page's entry conditions in the same qualitative voice; `vec.md:87` adds a fourth line,
`aiv_vec_ratio` >90%, as the trigger for the LUT card (0035), and `vec-11:8` repeats it. So the
skill contains four cut points on one metric — 50, 65, 80, 90 — of which only the last two are
attached to a specific card.

The top rung's advice is also a measurement-plus-inference sentence of the species 0008 records:
"微架构调优收益有限" is an inference from the share, not an observation of a ceiling.

## 4 · Procedure
Later phase, needs a card. Board token from the driver readout.
1. Device selection per 0010; explicit visible-devices; occupancy recorded either side.
2. Assemble at least twelve VEC-dominated kernels spread across the ratio range 0.45–0.95, four
   per rung, drawn from at least three operator families (elementwise, activation, reduction) so
   that a rung is not represented by a single family.
3. Apply, to every kernel regardless of rung, the same two treatments in randomised order,
   rebuilt from a common source tree: (M) a micro-architectural treatment — UB fusion (0020)
   plus instruction fusion (0022); (A) an algorithm-level treatment — the LUT path (0035) where
   a transcendental is present, otherwise a reduction in redundant element work.
4. Record `aiv_time` before and after each treatment, five repetitions, median and spread, and
   the pre-treatment `aiv_vec_ratio`.

## 5 · Checker — acceptance declared before the run
Verdict variable `ladder_predicts`, declared before any run: for each rung, the mean gain of the
treatment the ladder prescribes must exceed the mean gain of the other treatment, with the
difference larger than the pooled spread. Specifically the top rung must show
`gain_A > gain_M` — that is the rung carrying the actionable advice, and it is the one this
check is built to be able to refute.

Exit code is not the verdict. Per-kernel gains are printed for both treatments including the
kernels where the prescribed treatment lost, which are retained and named.

Red input: a kernel above 80% whose vector work is a long chain of fusable pairs. If M wins
there, `ladder_predicts` is false for the top rung and the entry is corrected in place. A
checker that applied only the prescribed treatment per rung could never observe this, which is
why both treatments are applied to every kernel.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board; the ladder has no stated derivation, no operator family, no shape
and no board attached anywhere upstream. It does not establish the band below 50%, which
upstream leaves silent. It does not establish that `aiv_vec_ratio` is even comparable across
operator families — a share is a share of that kernel's own duration. It says nothing about
AIC/Cube-heavy operators, nothing about MC² operators whose ratios may be polluted (0060), and
nothing about what 微架构调优 includes beyond the two cards named in the rungs.
