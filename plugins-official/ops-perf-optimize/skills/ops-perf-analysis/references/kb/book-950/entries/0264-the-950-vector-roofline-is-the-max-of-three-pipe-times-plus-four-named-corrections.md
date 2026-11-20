```
ID:        0264-the-950-vector-roofline-is-the-max-of-three-pipe-times-plus-four-named-corrections
LABEL:     procedure
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (ops/ascendc-performance-evaluation). Upstream reports
           its own on-board calibration for the correction terms; an upstream measurement enters
           this book at the harvested stratum (RULES.md Art. 3) and is not our readout.
BOARD:     950PR
           # upstream scopes the whole skill to Ascend950 / DAV_3510 pure-Vector kernels and names
           # 950PR variants (957b, 9589) as its hardware model; 950DT is not covered by it.
SOURCE:    ops/ascendc-performance-evaluation/SKILL.md:63 — "**Roofline**：`theoretical = max(mte2,
           vector, mte3)`，在 `overlap_model=\"max_pipe\"`（稳态 overlap；`serial` 则相加）下，再加标定
           修正——`fill_drain`（有限 tile 的流水填充/排空）、`core_balance`（核间尾块负载，用 flow 的
           `core_split_units`，**不是** UB 的 `tile_count`）、`launch_floor`（极小 shape 的设备下限，按
           `max` 施加、非叠加）。"
SOURCE:    ops/ascendc-performance-evaluation/SKILL.md:68 — "如果 tile 太少、达不到稳态，就给
           `tile_count`/`tiling` 让 fill/drain + 尾块均衡被建模；tile 稀少时不要把稳态 `max_pipe` 的
           bound 当作可达目标上报。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950PR pure-Vector kernel whose measured Task Duration falls below the model's
           `theoretical` at a shape where all four corrections were applied — a roofline that is not
           a lower bound is not a roofline.
```

# 0264 · The 950 Vector roofline is the max of three pipe times plus four named corrections

## 1 · Claim
Upstream asserts a theoretical-performance model for Ascend950 pure-Vector kernels: the base is
`theoretical = max(mte2_time, vector_time, mte3_time)` under a steady-state overlap assumption
(`overlap_model="max_pipe"`; the alternative `serial` sums the three instead), and four calibrated
corrections are applied on top — `fill_drain` for pipeline fill and drain at finite tile counts,
`core_balance` for the inter-core tail load, `launch_floor` for a device-imposed minimum at very small
shapes, and the GM-bandwidth model selection. Upstream asserts that `core_balance` is computed from
the flow's `core_split_units` and **not** from the UB-derived `tile_count`, and that `launch_floor` is
applied as a maximum rather than added. Upstream asserts explicitly that when tiles are few the
steady-state `max_pipe` bound must not be reported as an achievable target. Not established here:
nothing was run.

## 2 · The wrong branch this removes
`max(mte2, vector, mte3)` is the entire roofline an agent will remember, and it is the half that is
wrong on its own. The four corrections are not refinements — they are what makes the number a bound
rather than an aspiration, and three of the four only matter in exactly the regimes where operators
actually get written: small shapes, few tiles, uneven core splits.

Two concrete wrong branches. First, an agent computes `max_pipe` for a 4-tile kernel and reports the
gap between it and the measurement as an optimisation opportunity. There is no opportunity: with four
tiles the pipeline never reaches steady state, and upstream says so at `:68` in the imperative. The
team then spends its budget chasing a bound that assumed a condition its shape cannot satisfy.

Second, `core_balance`. An agent that has read the tiling side has `tile_count` to hand — it is the
UB-capacity-derived number, the one the flow already computed — and uses it for the tail-load
correction. Upstream marks this wrong in bold, and the reason is structural: `tile_count` counts UB
tiles within a core, `core_split_units` counts the units distributed *across* cores, and the tail
imbalance is a property of the second. Using the first gives a plausible number that models the wrong
tail, and nothing about the output looks wrong.

The `launch_floor` clause is a third, quieter trap: applied as `max(body, floor)` it is a floor;
applied additively it would inflate every shape, including the large ones where it is irrelevant.
Upstream states the mode — 按 `max` 施加、非叠加 — precisely because the additive reading is the
natural one.

The `max_pipe` versus `serial` choice is the fourth. `max_pipe` assumes the three pipes fully overlap;
upstream's own bandwidth notes record that read and write contend on HBM (0271), so full overlap is
not available for a read-plus-write streaming operator. Choosing `max_pipe` there is a modelling
assumption presented as arithmetic.

## 3 · Ground / Source
`ascendc-performance-evaluation/SKILL.md:61-68`, the 默认建模选择 block in full — this is the model:

> 默认建模选择（下面是要点；每个旋钮的完整参考见 `references/perf_case_schema.md`）：
>
> - **Roofline**：`theoretical = max(mte2, vector, mte3)`，在 `overlap_model="max_pipe"`（稳态
>   overlap；`serial` 则相加）下，再加标定修正——`fill_drain`（有限 tile 的流水填充/排空）、
>   `core_balance`（核间尾块负载，用 flow 的 `core_split_units`，**不是** UB 的 `tile_count`）、
>   `launch_floor`（极小 shape 的设备下限，按 `max` 施加、非叠加）。
> - **Vector 时间**：`issue_per_cycle = issue_slots / throughput_cycles`，先按执行单元、再按子管线聚合
>   ——一个单元的时间是 `max(发射口时间, 各子管线各自的 Σ)`，超越函数（`vector_transcendental`：
>   Exp/Log/Div/Sqrt/Reciprocal/Rsqrt）与 1 拍 ALU 重叠。它是吞吐下限（需要 ILP）；
>   `target_efficiency` / `dependency="dependent"` 覆盖低 ILP 的依赖链——两者不要叠加。
> - **GM 带宽**：`chip_peak`（默认上限 roofline）；`l2_aware`（标定的 L2 驻留 copy 曲线，用于 norm
>   这类 1读1写 流式算子）；`gm_rw_contention`（读写共享 HBM，α≈0.3）。`gm_reread_bytes` 走 L2、
>   与 HBM 流重叠。
> - **Tiling / 模版**：`tiling` 由 UB 容量推 `tile_count`；`flow_runtime` 把 case 路由到第一个 `select`
>   命中且 tiling UB 可行的模版。

and the scope declaration at `:10-14`:

> 当前范围：
> - 硬件：Ascend950 / DAV_3510，纯 VectorCore kernel。
> - 计算：RegBase 纯 vector 微指令流。
> - 不支持：Cube kernel、cube-vector 混合 kernel、`references/vector_instruction_types.json` 里没有的
>   隐式特殊数学模型。

Two things in this material are worth more than the formula.

First, `:31` states a calibration discipline that is the strongest evidence-culture statement in this
skill: "若实测与理论对不上，只调白名单旋钮（`perf_testcase.TUNING_WHITELIST`）并记 `tuning_reason`，
禁止改引擎标定常量" — when measurement and theory disagree, you may only turn whitelisted knobs and must
record why; changing the engine's calibration constants is forbidden. Carried separately as 0272.

Second, the two-layer architecture at `:20-23` separates a shared calibrated engine from per-operator
flow definitions, and asserts the engine "不要按算子重写" and is "由 Ascend950 微基准标定，带回归测试".
So the corrections are claimed to be *calibrated on hardware*, not guessed. Upstream's
`references/hardware/ascend950pr.json` carries the calibration provenance inline, e.g.
`min_launch_floor_source`: "950PR_9579 add tiny-shape sweep (TTK dyn_perf_us, 2026-06-10):
N=1024..1M, measured-minus-body intercept ≈1.5-1.77us, min measured 1.669us; 1.6 ≤ min so
max(body,1.6) stays a valid lower bound. Used as a FLOOR (max), not additive."

That is an upstream measurement with a date, a part, an instrument and a stated protocol — the best
provenance in this scope. It is still upstream text (RULES.md Art. 3), so it enters here at `harvested` and
is not our readout. Note that it also states the *reason* the floor is a max: 1.6 ≤ the minimum
measured, so `max(body, 1.6)` remains a valid lower bound. A model that added it would no longer be a
lower bound, which is why the mode is not a detail.

The overhead figures the base rests on, from the same JSON's `overheads`:
`kernel_startup_us: 1.5`, `kernel_completion_us: 0.5`, `mte_startup_us: 0.5`,
`mte_completion_us: 0.5`, with `base_time_formula` = `(mte_startup + mte_completion) * 2 +
(kernel_startup + kernel_completion)` and the disclosure "adopted from perf-eval-tools Ascend950
platform yaml; actual-mode short-kernel head/tail fixed cost, NOT a steady-state value".

## 4 · Procedure
Runnable later on `950PR`. The claim is that the model is a *lower bound*, so the procedure is a
theory-versus-measurement sweep designed to find a violation, not to confirm agreement.

Arm A — the bound property, across regimes. Take the operators upstream already supplies flows for
(add, cast, gelu, swiglu, rms_norm, layer_norm, softmax, reduce_sum, vchain) and for each sweep the
shape from tiny to large: N ∈ {1024, 4096, 16384, 65536, 262144, 1048576, 4194304}. For each case
compute `theoretical` with the engine as shipped, then measure Task Duration on the board with TTK or
msprof, minimum over 50 repetitions. Record the ratio measured/theoretical.

The verdict is directional: a ratio below 1.0 anywhere is a violated bound.

Arm B — the corrections, ablated one at a time. Re-run Arm A with each correction disabled in turn
(`fill_drain` off, `core_balance` off, `launch_floor` off, `overlap_model="serial"`), and record where
each correction is load-bearing. This is what distinguishes "the model is accurate" from "the model
happens to be accurate at the shapes we tried" — an unablated model that fits tells you nothing about
which of its five terms did the work.

Arm C — the `core_split_units` versus `tile_count` substitution, which tests §2's named trap. Compute
`core_balance` both ways on a case with a deliberately uneven core split (element count chosen so the
last core gets a small remainder), and record the two predictions against the measurement. Upstream
asserts one is right; this arm shows the size of the error the other makes.

Arm D — the `max_pipe` assumption, on a read-plus-write streaming operator. Compare `max_pipe` and
`serial` and the `gm_rw_contention` variant (0271) against the measurement for a norm-shaped case with
one read and one write of comparable size. Upstream's own bandwidth notes predict `max_pipe`
over-optimism here; this arm measures it.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All points of one sweep run on one named die
in one session — a theory-versus-measurement curve assembled across dies attributes nothing.

## 5 · Checker — acceptance declared before the run
Verdict variable `bound_holds`, declared FALSE-on-any-hit: it is false as soon as one case in Arm A
produces measured/theoretical < 1.0 outside run variance. This is the only pass/fail in the checker,
and it is deliberately asymmetric — a roofline may be loose and still correct, but a roofline that is
exceeded is not a roofline. Process exit code is not the verdict.

`accuracy_band` is reported, not gated: the distribution of measured/theoretical across Arm A, with
the shape and operator attached to the worst case in each direction. No accuracy threshold is declared,
because upstream does not claim one and inventing one here would let a tight fit read as validation of
the model's *structure*, which Arm B is what actually tests.

`correction_is_loadbearing[k]`, one per ablated correction from Arm B — the maximum change in
predicted latency across the sweep when correction `k` is disabled. A correction whose ablation moves
nothing anywhere is reported as inert, which is a finding about the model rather than a failure.

The positive fixture, declared before the run: run Arm A on a case whose measured latency is known to
be launch-dominated (N = 1024, well under the 0.8 MB HBM ramp threshold). With `launch_floor`
disabled, `bound_holds` **must** go false. If it does not, the harness is not comparing against the
model at all — most likely the floor is being applied somewhere the ablation did not reach — and every
`bound_holds = true` it reported is void. Without this, the checker only reads "no violation was
found", which is the known blind species: it cannot distinguish a sound bound from a comparison that
never fired.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No evaluator was executed, no
kernel was built, and no Task Duration was collected. The calibration figures quoted in §3 —
`min_launch_floor_us`, the head/tail overheads, and their provenance strings — are upstream's own
reported measurements read out of a JSON file; under RULES.md Art. 3 an upstream measurement is upstream
text, and none of it was reproduced here.

## 7 · Scope limits — what this entry does NOT establish
Nothing was run. The entry does not establish that the model is a bound, that any correction is
correctly calibrated, or that the engine's constants match the hardware — Arms A-D are all open. It
does not establish the correction terms' values: they are upstream's, with upstream's provenance, and
the `min_launch_floor` note is the only one in the set that states its own protocol. BOARD is `950PR`
because upstream scopes the skill to Ascend950 pure-Vector and models 950PR variants specifically;
**nothing here covers 950DT**, and upstream's hardware JSON has no 950DT variant at all. It covers
only pure-VectorCore kernels: upstream declares Cube and mixed Cube-Vector kernels out of scope, so
the model says nothing about them. It says nothing about the Vector-time sub-model (issue slots,
sub-pipeline aggregation, transcendental overlap) beyond quoting it — that is a separate claim and is
where the instruction table (0266) enters. It does not establish that `core_split_units` is the right
input for `core_balance`; upstream asserts it and Arm C measures the alternative. The provenance of
the hardware model itself is unverified in one respect worth naming: its `source_ini` fields cite
`Ascend/cann-9.1.0/...`, a toolkit not installed on this machine, so its variant rows could not be
checked against their own stated source.
