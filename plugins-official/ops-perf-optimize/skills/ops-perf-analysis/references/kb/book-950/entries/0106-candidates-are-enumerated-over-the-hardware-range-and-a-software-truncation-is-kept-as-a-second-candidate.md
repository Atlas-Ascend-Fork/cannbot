```
ID:        0106-candidates-are-enumerated-over-the-hardware-range-and-a-software-truncation-is-kept-as-a-second-candidate
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/parameter-analysis.md:69-71 —
           "1. 独立可调参数取其**硬件约束下的完整范围**，步长为硬件对齐粒度，不受软件截断值限制
            2. 派生参数按 §2 公式计算。若存在软件截断，同时保留截断值和硬件上限值作为候选维度
            3. 所有候选用硬件约束做最终校验，不满足则剔除"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board in which the best candidate is always at or
           inside the software truncation value for every parameter swept — that would make the
           beyond-truncation range dead search space rather than the reachable optimum this rule
           exists to reach.
```

# 0106 · Candidates are enumerated over the hardware range, and a software truncation is kept as a second candidate

## 1 · Claim
Upstream asserts three rules for constructing the candidate space of each enabled algorithm.
First, each independently tunable parameter is enumerated over its full range under hardware
constraints, at a step equal to the hardware alignment granularity, explicitly not limited by any
software truncation value. Second, derived parameters are computed from the §2 formulas, and where
a software truncation exists both the truncated value and the hardware upper bound are retained as
candidate dimensions. Third, every candidate is finally re-validated against the hardware
constraints and dropped if it does not satisfy them. Not established here.

## 2 · The wrong branch this removes
The wrong branch is enumerating between the bounds the existing code enforces. This feels safe and
is the default behaviour of every tuner that reads limits out of the implementation: the search
then cannot find anything the previous engineer had not already allowed, and reports the current
behaviour as the optimum. Rule 2 is the sharper one and the easiest to skip — when a parameter is
software-truncated, keeping *both* the truncated value and the hardware limit turns a silent
narrowing into an explicit two-point comparison, so the cost of the truncation becomes a number
rather than an assumption. Rule 3 is what makes rule 1 safe: enumerating past a software limit is
only sound if a hardware validation runs at the end, and an agent that adopts rule 1 without rule
3 will propose plans that cannot launch.

Concretely in this subtree: `stepK` is software-truncated at 4 by `STEPKA_THRESHOLD`
(`matmul/fallback/tiling-flow.md:35`) while the same family's text states a maximum of 8 at `:159`
and emits `step_k: 3` from `mc2/index.md:64` — see 0109. Under this rule the correct candidate
set for `stepK` is not `{1,2,4}` but `{1,2,4}` plus whatever the L1 inequality actually admits,
with the truncation kept as its own point so the comparison is visible.

## 3 · Ground / Source
`ops/ascendc-perf-optimize/references/tiling/parameter-analysis.md:63-73`, §4 in full:

```
## §4 候选解空间

对每个命中算法：

1. 独立可调参数取其**硬件约束下的完整范围**，步长为硬件对齐粒度，不受软件截断值限制
2. 派生参数按 §2 公式计算。若存在软件截断，同时保留截断值和硬件上限值作为候选维度
3. 所有候选用硬件约束做最终校验，不满足则剔除

输出：每算法的独立变量范围、硬件约束、派生公式、扩展维度、预计候选数。
```

The rule depends entirely on §2's provenance classification (0104) being correct: "software
truncation" is defined there as a limit whose assignment chain ends at a hardcoded literal, and
"hardware constraint" as one ending at a chip specification field. §2's output is required by
`:53` to include `被软件截断的参数列表（标注截断值和硬件上限）` — the truncation list is a named
artifact, not an implicit notion.

Upstream does not say what the alignment granularity is for any parameter, on any board. The
phrase `步长为硬件对齐粒度` is load-bearing for the size of the search space and is never given a
value in this file or anywhere else in the tiling subtree; the granularity constants a consumer
would need (32 B DataCopy block, 256 B repeat, 512 B L1 alignment as it appears in matmul's depth
refinement at `matmul/fallback/tiling-fields.md:186`) have no single authority here. That is a
gap in this rule as shipped, recorded in `harvest/standing/950-tiling.md`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; export `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Beyond-truncation sweep. Choose three software-truncated parameters from three families, each
identified by tracing to a literal per 0104: matmul `stepK` (truncated 4, and the text's own other
value 8), scan's borrow-R trigger (stated 4096 in one place and 16384 in another — 0130), sort's
merge ways `M` (0139). For each, enumerate the full range admitted by the hardware inequality at
alignment step, including every point beyond the truncation, and additionally include the
truncation value itself as a labelled candidate. For every point: build with one compiler pin,
md5 the binary, echo the parameters from the host, verify the output against the fp64 reference
within the operator's tolerance, and record `aic_time`/`aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 discarded, per case with no
representative sampling. Points that fail rule 3's hardware re-validation are recorded as dropped
with the inequality that dropped them, not silently omitted.

Refuses to assume: that a free die stays free; that a die may be substituted; that a parameter
value which builds is a value that was used (host echo required); that the hardware alignment
granularity is any particular number — it is swept as a candidate step of 16 B, 32 B, 64 B, 128 B,
256 B and 512 B, and which steps produce distinct legal points is itself recorded.

## 5 · Checker — acceptance declared before the run
Verdict variable `beyond_wins`, one per swept parameter: true iff the best correct-result
candidate strictly beyond the software truncation beats the best candidate at or inside it by more
than 5 % of the inside best. Declared acceptance: the rule is worth its search cost iff
`beyond_wins` is true for at least one of the three parameters. Declared falsification, i.e. the
OVERTURN condition: `beyond_wins` false for all three AND no beyond-truncation candidate within
2 % of the inside best — the beyond range is then dead space for these parameters and shapes, and
that null is reported as a null.

The exit code is not the verdict. The specific blind failure this checker must avoid: a
beyond-truncation candidate that was silently clamped back inside would run correctly and time
identically to the truncation point, producing `beyond_wins = false` from a sweep that never left
the allowed region. The host echo of the actual parameter value is therefore mandatory per point,
and any point whose echo differs from its request is recorded as `clamped` and excluded from both
sides of the comparison rather than counted as evidence. The checker also goes red if the count of
`clamped` points exceeds zero without being reported, and if the `msprof` row count is short.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no candidate was enumerated, built, or run. The entry does not establish
that any of the three named truncations is in fact soft — that classification is 0104's method
applied, and the method itself is unverified. It does not establish the hardware alignment
granularity for any parameter on any board; upstream never states one, and the procedure above
treats it as unknown. It does not establish that a larger candidate space finds a better plan
within a fixed search budget: rule 1 makes the space larger, and whether that helps or dilutes is
exactly what §4 would measure. No chip is named in `parameter-analysis.md`, so BOARD is
`family-claimed(unverified)` and the chip is unstated; §4's 950PR/950DT is where our run would
happen, not where upstream measured. Nothing here is established for any 910-family board.
