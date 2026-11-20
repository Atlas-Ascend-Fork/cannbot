```
ID:        0464-the-pipebarrier-count-is-a-declared-contract-with-a-thirty-percent-redundancy-limit-and-a-fifty-percent-blocking-threshold
LABEL:     procedure
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/design.md:585-605 —
           "`PipeBarrier<PIPE_ALL>` 用于跨 pipe 整核 drain。设计阶段必须**显式列出**所有需要出现的
           位置(契约位置),禁止四处散布。" · "**冗余率验收**:在审查前列出"设计契约位置数"与
           "实现实际位置数",冗余率 `(实际 / 设计 - 1) < 30%`,达到 50% 视为性能阻塞项。" ·
           "**禁止**: / - 以"PIPE_ALL 是保险屏障,跟精度无关"为由四处散布。冗余 barrier 让 Cube 流水
           利用率系统性下降 / - 同核内跨 pipe 依赖用 PipeBarrier 替代专门的 HardEvent
           (应使用对应 `HardEvent::X_Y`) / - 同一 pipe 内的顺序操作之间散布 barrier(不需要)"
SOURCE:    same file:591-594 — "**FA 类的 PipeBarrier 来源**: / - 通用 Cube 同步约束(每次 Mmad 之后
           等)—— 属 Ascend C 通用 API 同步规则,见 `/ascendc-api-best-practices` / - 跨 pipe 边界
           (如 MTE2 → MTE1)无对应 HardEvent 时必须 PIPE_ALL 兜底 —— 通用规则 / - 平台特定治本配方
           (如某些平台的多 K-pass Mmad 隐式状态需要在循环起始 drain)—— 见 `/npu-arch` 平台差异表"
           ; :536 — "- [ ] PipeBarrier 冗余率(实际数量 / 设计契约数量 - 1)< 30%(见 §7.5)"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a FlashAttention build on a named 950 board whose redundancy ratio is raised from 0 to
           above 0.5 with no measurable change in cube pipeline utilisation or in kernel time beyond
           the variance floor — the two thresholds would then be arbitrary, and "冗余 barrier 让 Cube
           流水利用率系统性下降" would have no subject on this part. Equally: a build at exactly 30%
           whose utilisation is already degraded would show the threshold is set in the wrong place.
```

# 0464 · The PipeBarrier count is a declared contract with a 30% redundancy limit and a 50% blocking threshold

## 1 · Claim
Upstream asserts that `PipeBarrier<PIPE_ALL>` is a whole-core drain across pipes, and that a
FlashAttention design must enumerate every position where one is required — a contract list produced
at design time — rather than scattering them. Upstream asserts three sources for the required
positions: general Ascend C cube synchronisation rules such as after each Mmad; cross-pipe boundaries
such as MTE2 to MTE1 for which no hard event exists, where `PIPE_ALL` is the fallback; and
platform-specific remedies, the named example being an implicit multi-K-pass Mmad state on some
platforms requiring a drain at the start of the loop. Upstream asserts a numeric acceptance criterion:
the redundancy ratio `(actual positions / contracted positions) − 1` must be below 30%, and reaching
50% is treated as a performance-blocking item. Upstream asserts a mechanism for the cost — redundant
barriers systematically lower cube pipeline utilisation — and forbids three practices, of which one is
the rationalisation that `PIPE_ALL` is a harmless insurance barrier unrelated to precision. Not
established here.

## 2 · The wrong branch this removes
Without this entry an agent debugging a synchronisation defect adds a `PipeBarrier<PIPE_ALL>` and the
defect goes away. This is genuinely good debugging: a full drain is the strongest available ordering
guarantee, so it isolates whether the problem is ordering at all. The wrong branch is leaving it in,
and the rationalisation for leaving it in is the one upstream quotes — it cannot make the answer
wrong, so what is the harm. The harm is that it drains every pipe including the cube's, in an operator
whose whole design is a cube/vector pipeline, and it does so on a path that runs once per KV block.

The normal checks do not catch it because there is nothing to catch: the kernel is correct, faster
than the broken version it replaced, and slower than a version nobody built. Barrier redundancy has no
symptom. That is why upstream's answer is not a rule but an *accounting* — count what the design says
you need, count what the implementation has, and treat the ratio as an acceptance number.

The second wrong branch is the substitution one: using `PipeBarrier` where a specific `HardEvent::X_Y`
exists. Both order the two operations; the barrier also stops everything else. Upstream forbids it in
this section and again in the cross-core checklist (`0463`, `:535`), so it is stated twice in one
document, which is how this corpus marks a mistake people repeat.

## 3 · Ground / Source
The contract and the acceptance number, `references/flashattention/design.md:585-605`:

```
### §7.5 PipeBarrier 设计契约

回答:**算子内 `PipeBarrier<PIPE_ALL>` 应该出现在哪些位置?预计数量是多少?**

`PipeBarrier<PIPE_ALL>` 用于跨 pipe 整核 drain。设计阶段必须**显式列出**所有需要出现的位置(契约位置),禁止四处散布。

**FA 类的 PipeBarrier 来源**:
- 通用 Cube 同步约束(每次 Mmad 之后等)—— 属 Ascend C 通用 API 同步规则,见 `/ascendc-api-best-practices`
- 跨 pipe 边界(如 MTE2 → MTE1)无对应 HardEvent 时必须 PIPE_ALL 兜底 —— 通用规则
- 平台特定治本配方(如某些平台的多 K-pass Mmad 隐式状态需要在循环起始 drain)—— 见 `/npu-arch` 平台差异表

设计阶段应基于以上来源列出本算子的**契约位置清单**与预计数量。

**冗余率验收**:在审查前列出"设计契约位置数"与"实现实际位置数",冗余率 `(实际 / 设计 - 1) < 30%`,达到 50% 视为性能阻塞项。

**禁止**:
- 以"PIPE_ALL 是保险屏障,跟精度无关"为由四处散布。冗余 barrier 让 Cube 流水利用率系统性下降
- 同核内跨 pipe 依赖用 PipeBarrier 替代专门的 HardEvent(应使用对应 `HardEvent::X_Y`)
- 同一 pipe 内的顺序操作之间散布 barrier(不需要)
```

Two properties make this worth an entry rather than a checklist line, and one property makes it a
`procedure` rather than a `knowledge`.

The acceptance criterion is **declared before the review**, which is the discipline this book's own
form is built on (`form/ENTRY_TEMPLATE.md §5`). Upstream states the number, states when it is
computed, and states what the two counts are. It is the second instance in this corpus of an upstream
document naming an acceptance criterion instead of a benefit figure — the first is `0338` — and the
two are unrelated authors in different shelves.

The criterion is also **self-referential in a way that can be gamed**, and upstream does not close it.
The denominator is "the number of positions the design contracted", produced by the same team at the
same time as the implementation. Nothing prevents a design list written after the fact from containing
exactly the positions the implementation has, giving a redundancy ratio of zero by construction. This
is the "a marker the fix itself can satisfy is not a check" species; the accounting is only a check if
the contract list is written before the implementation, which upstream implies by putting it in the
design phase and never states as a requirement. Recorded as `Q-950fin-13`.

Neither 30% nor 50% is derived. No measurement, no shape, no board, no utilisation figure. The
mechanism sentence — `冗余 barrier 让 Cube 流水利用率系统性下降` — is a direction with no magnitude, so
the two thresholds are policy numbers in a document that elsewhere forbids bare numbers in formulas
(`:208`). Recorded as `C-950fin-010`.

The third source of contracted positions is the interesting one for this book: `平台特定治本配方
(如某些平台的多 K-pass Mmad 隐式状态需要在循环起始 drain)`. A platform-specific remedy, on `某些
平台` — some platforms, unnamed — deferring to a platform-difference table not quoted here. So the
contract list's size is architecture-dependent by upstream's own account, which means the redundancy
ratio is not comparable across boards, and the 30% figure is stated without saying which platform's
contract list it was calibrated against. Recorded as `Q-950fin-14`.

`:536` repeats the 30% figure as a cross-core checklist item, so it appears twice in one file. One
repository, one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first: 30 in-process and 5 fresh-process runs of the
zero-redundancy build, IQR over median, beside every point.

**Arm 1 — the cost curve, which is the number upstream does not give.** One GQA kernel with a
contracted barrier list of `N` positions, built at redundancy ratios `{0, 0.1, 0.2, 0.3, 0.5, 1.0}` by
inserting extra `PipeBarrier<PIPE_ALL>` calls at randomly chosen legal positions inside the loop body,
with the *same* choice reused across builds so the ratio is the only variable. Report per build:
`aic_time`, `aiv_time`, and cube pipeline utilisation from `PipeUtilization`. The thresholds 30% and
50% are upstream's; this arm is where the curve is, and whether anything happens at either.

**Arm 2 — the placement dependence.** At a fixed ratio of 0.3, three different placements: all extras
inside the innermost loop, all in the outer loop, all outside both. Report the same metrics. Upstream's
criterion counts *positions*, not executions, and a barrier in the innermost loop executes `s2N` times
more often than one outside it. If placement dominates the ratio, the criterion is measuring the wrong
quantity, which is a finding about the acceptance number itself.

**Arm 3 — the substitution.** One cross-pipe dependency implemented three ways: the specific
`HardEvent::X_Y`, `PipeBarrier<PIPE_ALL>`, and both. Report correctness and time for each. This gives
the second prohibition a cost, which upstream states as a direction only.

**Arm 4 — the platform-specific source, retained because it may not bite.** Remove the multi-K-pass
loop-start drain from the contract list and run at `D` large enough to force several K passes
(`0456`'s L0 K-axis blocking). If the build stays correct on this board, that contract position is not
required here, the contract list is one shorter, and every redundancy ratio computed against the
longer list was understated. If it breaks, the platform-specific source is real on 950 and
`Q-950fin-14` is partly answered.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a barrier's
*position count* predicts its *execution count* (arm 2 exists because it does not); that the contract
list is correct (arm 4 tests one of its entries); that utilisation and time move together (both are
reported); that removing a barrier that changes nothing is safe — every arm carries an elementwise
comparison against an FP64 reference and a ≥20-run disagreeing fraction, since a removed barrier's
failure may be intermittent.

## 5 · Checker — acceptance declared before the run
Verdict `utilisation_drop(r) = util(0) − util(r)` and `time_penalty(r) = (t(r) − t(0)) / t(0)`,
declared before the run with the variance floor on each. Acceptance for upstream's thresholds as
calibrated: `time_penalty(0.3) ≤ floor` and `time_penalty(0.5)` materially above it — declared now as
≥5% — so that 30% is a limit below which nothing measurable happens and 50% is where it does. Any
other shape of the curve is reported as a *recalibration*, not as a pass or a failure.

The OVERTURN fires iff `time_penalty(1.0) ≤ floor` and `utilisation_drop(1.0) ≤ floor` — doubling the
barrier count with no measurable effect would leave the mechanism without a subject on this part.

Verdict `placement_dominates` from arm 2: `true` iff the spread across the three placements at fixed
ratio exceeds `time_penalty(0.5) − time_penalty(0.3)`. A `true` here means the criterion counts the
wrong thing, and it is declared as a possible outcome before the run rather than discovered after.

Verdict `contract_position_required(multi_K_drain)` from arm 4 ∈ {`yes`, `no`, `intermittent`}.

The exit code is not the verdict: every build in arms 1 and 2 is correct, which is the entry's premise
— barrier redundancy has no correctness symptom. Guards: (1) every build echoes its **executed**
barrier count as well as its position count, instrumented by a counter, so that arm 2's finding is
measurable rather than inferred; a build reported without both counts is untestable; (2) **the input
that makes this checker go red**: the `r = 0` build compared against itself across two fresh
compilations — if the two differ by more than the floor, barrier count is not the dominant variable at
this scale and the whole curve is noise, and the checker refuses a verdict; (3) no point is reported
without its position count, executed count, utilisation metric name, floor, CANN pin and compiler
command.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The contract requirement, the
three sources, the redundancy formula, the 30% and 50% figures, the mechanism sentence and the three
prohibitions are file reads performed at drafting time. The observations that the denominator is
produced by the same team as the numerator, that neither threshold is derived, that the criterion
counts positions rather than executions, and that the contract list's size is architecture-dependent
by upstream's own account, are readings of upstream's own lines, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that redundant barriers cost anything
on any board: upstream states a direction with no magnitude, no shape, no tool and no board
(`C-950fin-010`). It does not establish 30% or 50% as the right thresholds, nor which platform's
contract list they were calibrated against (`Q-950fin-14`). It does not establish that the accounting
is a check rather than a marker the implementation can satisfy by construction (`Q-950fin-13`). It does
not establish the three sources as exhaustive, nor the multi-K-pass drain as required on 950 — upstream
says `某些平台` and names none. It does not cover `PipeBarrier` with a narrower pipe argument, only
`PIPE_ALL`. It says nothing about barrier requirements under the split-KV-reduce strategy, whose Cube
may be absent entirely (`0454`). No board token appears in any quoted passage, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
