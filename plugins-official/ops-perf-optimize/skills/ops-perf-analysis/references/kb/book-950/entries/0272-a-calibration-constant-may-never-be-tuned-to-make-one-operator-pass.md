```
ID:        0272-a-calibration-constant-may-never-be-tuned-to-make-one-operator-pass
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (ops/ascendc-performance-evaluation). The rule is a
           process discipline, so what a run would establish is whether the mechanism enforcing it
           exists; nothing was executed here.
BOARD:     950PR
SOURCE:    ops/ascendc-performance-evaluation/SKILL.md:31 — "把上板实测（TTK / profiling 的 Task
           Duration）与引擎输出的理论时延对照；若实测与理论对不上，只调白名单旋钮
           （`perf_testcase.TUNING_WHITELIST`）并记 `tuning_reason`，禁止改引擎标定常量。"
SOURCE:    ops/ascendc-performance-evaluation/SKILL.md:20,48 — "**共享标定引擎**（不要按算子重写）…
           它掌管全部建模…由 Ascend950 微基准标定，带回归测试（`tests/offline/test_overlap_model.py`）"
           … "标定哲学（绝不为让某个算子通过而调常量）、`measured_cycles` 口径、`core_split_units`
           tiling 模型都写在 `tests/calibration/README.md` 和 `references/perf_case_schema.md`——
           动任何标定常量前先读它们。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a calibration constant in `hardware/ascend950pr.json` or
           `vector_instruction_types.json` whose committed history shows it changed to close a gap
           on one operator, with no accompanying bench re-run — the discipline is then aspirational.
```

# 0272 · A calibration constant may never be tuned to make one operator pass

## 1 · Claim
Upstream asserts a separation of powers in its performance-evaluation skill: a shared calibration
engine owns all modelling and is calibrated by on-board microbenchmarks, and per-operator flow
definitions own only the description of the operator. Upstream asserts the operative rule for
theory-versus-measurement disagreement: when the two do not match, only whitelisted knobs
(`perf_testcase.TUNING_WHITELIST`) may be adjusted, a `tuning_reason` must be recorded, and changing
the engine's calibration constants is **forbidden**. Upstream states the philosophy in one clause —
绝不为让某个算子通过而调常量, never tune a constant to make some operator pass — and requires that
`tests/calibration/README.md` and `references/perf_case_schema.md` be read before any calibration
constant is touched. Not established here: nothing was executed and no history was audited.

## 2 · The wrong branch this removes
This is the discipline that decides whether a performance model stays a model or becomes a curve fit,
and the wrong branch is the *helpful* one.

An agent is asked to make a roofline match a measurement. The gap is 18 %. Two edits are available:
adjust the operator's flow description, which is what the whitelist permits, or nudge
`hbm_sustained_read_bytes_per_s` down by 18 %, which closes it exactly. The second is faster, produces
a clean pass, and is untraceable in the output — the report shows theory and measurement agreeing.
It also destroys the model for every other operator, silently, because a shared constant was fitted to
one case. The next operator's gap is now 18 % in the other direction, and the natural response is
another nudge.

Upstream's own hardware model carries the countermeasure written as a note rather than as a rule:
`hbm_sustained_note` says the variant peak "is this HBM-sustained value; **it is NOT too low**" — a
sentence that exists because someone was about to raise it. And `l2_source` records the reversal
where a constant *was* changed on documentary grounds ("曾据'112MB'误改 112") and then falsified by a
pure-write measurement and reverted (0270 §3). So the discipline has already been tested once in this
material, and the record of it surviving is in the file.

The subtler wrong branch is the one the whitelist itself invites. A whitelisted knob with a recorded
`tuning_reason` is permitted, so an agent can reach a fit legitimately — by turning
`target_efficiency` down until the numbers agree. That is allowed and it is still a fit; the difference
is that the `tuning_reason` field makes it *visible*. The rule's value is not that it prevents fitting
but that it forces fitting to leave a trace, and an agent that writes "tuning_reason: to match
measurement" has complied with the letter and left exactly the evidence a reviewer needs.

Third: the rule has no stated enforcement. Nothing in the quoted text says a check rejects an
unwhitelisted edit. If the only mechanism is the sentence, then it is a rule that lives where it is
written and not where the edit happens — and the repair is placement, not exhortation.

## 3 · Ground / Source
`SKILL.md:25-31`, the workflow's last step, quoted with its neighbours so the rule's position in the
loop is visible:

> ## 工作流（推荐：flow + 模版）
> …
> 4. 跑 `python3 scripts/perf.py --op <op> --cases <op>_cases.json --show-case`（表格会显示路由到的模版），
>    再跑 `python3 tests/offline/test_design_conformance.py` 确认解释出的 flow 与设计一致。
> 5. 把上板实测（TTK / profiling 的 Task Duration）与引擎输出的理论时延对照；若实测与理论对不上，
>    只调白名单旋钮（`perf_testcase.TUNING_WHITELIST`）并记 `tuning_reason`，禁止改引擎标定常量。

The rule is step 5 of 5 — the last thing before the work is called done, which is where the temptation
is highest. That placement is deliberate and worth imitating.

The architecture the rule protects, `SKILL.md:18-23`:

> 两层，严格分离：
> - **共享标定引擎**（不要按算子重写）：`scripts/evaluate_a5_vector_roofline.py` + 两个参考 JSON。
>   它掌管全部建模——指令 issue/cycle、overlap、带宽、tiling 修正——由 Ascend950 微基准标定，带回归测试
>   （`tests/offline/test_overlap_model.py`）。
> - **计算流定义**（`references/examples/<op>_flow.json`）：算子 = 一组**模版**…它是唯一真源，也是符合性
>   金标准；对照真实设计文档评审。

Two clauses do the work. 不要按算子重写 — the engine is not rewritten per operator, so there is exactly
one place a constant can be wrong and exactly one place it can be fixed. And 带回归测试 — the engine
carries regression tests, which is what makes an unauthorised change detectable in principle.

`SKILL.md:48` names where the philosophy is written and makes reading it a precondition:

> 标定哲学（绝不为让某个算子通过而调常量）、`measured_cycles` 口径、`core_split_units` tiling 模型都写在
> `tests/calibration/README.md` 和 `references/perf_case_schema.md`——动任何标定常量前先读它们。

and the same line records what backs the constants: "单指令吞吐 + 超越函数 overlap 由 skill 内仪器
`tests/calibration/instruments/regbase-microbench/` 标定（源码 + 入库板上原始数据作溯源）；GM 带宽由
`tests/onboard/kernels/membw` 标定" — instrument source and raw board data committed as provenance
(0266, 0270). A constant with a committed instrument behind it is a constant an edit can be checked
against; that is the structural reason the prohibition is enforceable at all.

The gate that exists, `tests/calibration/check_calibration.py`, is described at `:48` as binding the
JSON constants to the in-skill on-board benches with a gate. Whether it fails on a constant that
drifted from its bench is exactly the question §4 asks — the file was not executed here, and a gate
that reads only the lines it expects would pass a fitted constant.

One thing this scope does **not** contain: the two documents the rule points at.
`tests/calibration/README.md` exists in the tree and was not mined for this entry, and
`references/perf_case_schema.md` (164 lines) carries the knob-by-knob reference including, by
upstream's own account, the `TUNING_WHITELIST` semantics. So the rule is harvested from the pointer,
not from the target, and §7 records that.

## 4 · Procedure
Runnable later; the decisive arms need no device and should run first. This is a claim about a
mechanism, so the procedure attacks the mechanism rather than the numbers.

Arm A — does the gate exist and can it fail. Run `tests/calibration/check_calibration.py` as shipped
and record the result. Then perturb one calibration constant in a scratch copy — say
`l2_residency_knee_bytes` by 10 % — and re-run. The gate must fail, and its diagnostic must name the
constant. A gate that passes a perturbed constant is not a gate, and everything downstream of it is
unguarded.

Arm B — the whitelist's extent, a file read. Enumerate `perf_testcase.TUNING_WHITELIST` and classify
each entry: does turning it change the *operator description* (legitimate) or the *model* (a fit by
another route)? `target_efficiency` and `dependency="dependent"` are the two to look at hardest —
upstream's own note at `SKILL.md:64` says "两者不要叠加", which is an admission that they overlap and
can be double-counted.

Arm C — the history audit, which is what the OVERTURN clause names. Over the committed history of
`references/hardware/ascend950pr.json` and `references/vector_instruction_types.json`, for every
change to a calibration constant, check whether a corresponding bench re-run or provenance update
accompanied it. Upstream's own `l2_source` note documents one change-and-revert cycle, so at least one
instance exists and can be used to validate the audit method before trusting its other findings.

Arm D — the consequence arm, on the board, which prices the prohibition rather than restating it.
Take one operator whose theory and measurement disagree, close the gap two ways — once by a whitelisted
flow adjustment with a recorded reason, once by editing a shared constant in a scratch copy — then
re-run the *other* eight operators' cases under both edits. The constant edit should degrade the others;
the flow adjustment should not touch them. That contrast is the argument in §2 made measurable, and it
is the only thing here that would convince someone the rule earns its cost.

Device selection for Arm D is explicit: the operator names the device index, the harness prints it back
with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All operators of one comparison run on one
named die in one session.

## 5 · Checker — acceptance declared before the run
Verdict variable `gate_can_fail` (Arm A) — pass iff the shipped `check_calibration.py` passes as
shipped **and** fails on the perturbed constant **and** its diagnostic names the perturbed field. All
three clauses, in one predicate. The second clause is the one that matters: a gate observed only in its
passing state has not been shown to be a gate, and this is the known blind species — a check pinned to
"the constants must come up clean" cannot discover a constant that drifted with its bench.

`whitelist_is_description_only` (Arm B) — reported as a classification, not a boolean. Any knob that
alters the model rather than the operator description is named. A non-empty list is not a failure; it is
the honest boundary of the discipline, and it is what the delivered skill would have to disclose.

`unaccompanied_constant_changes` (Arm C) — the count of calibration-constant edits with no bench re-run
or provenance update. Declared now: a count of zero is *not* automatically a pass. It is a pass only if
the audit method was first shown to detect the known instance — upstream's documented 112-MB
change-and-revert. An audit that finds nothing without having been shown able to find something has
established nothing, and saying so before the run is the only way to keep a clean result honest.

`cross_operator_damage` (Arm D) — the maximum change in predicted-versus-measured ratio across the
other operators, under each of the two edits. No pass threshold; the comparison is the result. A
constant edit that damages nothing would be the interesting outcome and would weaken §2's argument
rather than this entry's claim.

Process exit codes are not the verdict anywhere: in Arm A a non-zero exit is the expected outcome for
the perturbed run, and treating it as failure would invert the whole check.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. `check_calibration.py` was not
executed, no constant was perturbed, no history was audited, and no operator was run. §3 is a read of
`SKILL.md`; the calibration provenance and the one documented change-and-revert quoted there are
upstream's own records of upstream's own work.

## 7 · Scope limits — what this entry does NOT establish
Nothing was executed. The entry does not establish that the discipline is enforced: whether
`check_calibration.py` can fail is Arm A and is open, and the rule as quoted names no mechanism —
§2's third branch records that a rule with no enforcement lives only where it is written. It does not
establish that the discipline has been *followed*; Arm C is the audit and it has not run, and the one
change-and-revert upstream documents is evidence the rule was honoured once, not a history.

Two source gaps are load-bearing here and are disclosed rather than papered over. The rule was
harvested from `SKILL.md`, which *points at* `tests/calibration/README.md` and
`references/perf_case_schema.md` for the calibration philosophy, the `measured_cycles` 口径 and the
`core_split_units` model — **those two files were not mined for this entry**, so the whitelist's actual
contents and the philosophy's actual wording are cited at one remove. And `TUNING_WHITELIST` lives in
`scripts/perf_testcase.py`, which was likewise not read; Arm B exists because its extent is the
difference between a discipline and a formality.

It says nothing about whether the constants are *correct* — that is 0266 and 0270, and a perfectly
enforced discipline protecting wrong constants would pass every check here. BOARD is `950PR` because
the engine is calibrated on 950PR parts and the skill is scoped to Ascend950 pure-Vector; the
discipline itself is board-independent, but the constants it protects are not, and nothing here covers
**950DT**. Finally, this entry is a `procedure` and its subject is a process rule: a run can establish
that a gate fires, and cannot establish that a team will read the file before editing.
