```
ID:        0327-a-timing-outlier-is-attributed-to-the-machine-by-comparing-two-cases-on-the-same-code-path
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing collected
BOARD:     950PR
SOURCE:    ops/ascendc-performance-best-practices/reference/scatter/precision_and_traps.md:117-134 —
           "## 7. 陷阱 4：性能读数会被同机负载污染 / 多进程共卡的 runner 会把两个评测进程压在同一张
           卡的两个 device 上，部分用例时延被拉高**一个数量级**。" · "**判别方法（比看总分可靠得多）**：
           **找同一条代码路径、同一量级规模的用例互相比对**。" · "| 用例（同为打包键路径） | 污染跑 |
           干净跑 | | 1.05M 元素 | 794.4us | **44.0us** | | 约 1M 元素 ×3 条 | 约 40us | 约 40us |" ·
           "- **代码缺陷会按 dtype / reduce / shape 结构分布，不会按用例序号整齐断开。**"
           · "结果里的 `device` 字段是 `npu:6,7` 而不是 `npu:0` 就要警惕。" ·
           "遇到异常低分**先看 runner，重跑一次再下结论**，别急着改代码。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a contaminated-looking readout on a named 950 board that survives a clean re-run on an
           exclusively-held die — the 18× would then be a property of the case rather than of the
           machine, and the discriminant would have produced a false positive.
```

# 0327 · A timing outlier is attributed to the machine by comparing two cases on the same code path

## 1 · Claim
Upstream asserts that a multi-process shared-card runner can place two evaluation processes on two
devices of one card, and that this inflates some cases' latency by an order of magnitude. Upstream
asserts a discriminant it calls more reliable than reading the total score: compare cases that take
the **same code path** at the **same order of magnitude of size**, and see whether they agree.
Upstream gives the readings — one 1.05 M-element case at 794.4 µs contaminated against 44.0 µs
clean, while three roughly 1 M-element cases on the same packed-key path sat at about 40 µs in both
runs. Upstream asserts two corroborating signatures: a code defect distributes along dtype, reduce
mode and shape structure and does not break cleanly at a case index, so "the first ten fine, the
last ten uniformly 10–15× slower, five different code paths collapsing at once" is a machine and not
a defect; and a `device` field reading `npu:6,7` rather than `npu:0` is a warning. Upstream asserts
the operational rule: on an abnormally low score, inspect the runner and re-run before concluding
anything about the code. Not established here.

## 2 · The wrong branch this removes
An 18× outlier on one case is the most actionable-looking signal a performance report produces. The
natural response is to open that case, find what is special about it, and optimise. Everything about
the case *is* special — it is the one that is slow — and the search will terminate in some
plausible-sounding difference, because a 1 M-element case always has several.

The cost is not only the wasted session. A "fix" derived from a contaminated reading gets shipped,
and it is a change made for a reason that does not exist. It will then be defended by the next
measurement, which will also be taken on whatever the machine was doing that day.

The discriminant works because it holds the two things that could explain a difference — code path
and size — and varies only the run. That is the same isolation discipline this book requires of any
attribution, applied to the environment instead of to the kernel. The reason it beats reading the
total score is that a total aggregates contaminated and clean cases together, so a contaminated run
looks like a mildly worse implementation rather than like a different machine.

The second wrong branch is the reverse: dismissing a real regression as contamination. Upstream's
shape signature is what prevents it — a defect tracks dtype, reduce mode or shape structure, so it
appears as a *pattern over the case attributes*, while contamination appears as a pattern over the
case *order*. Those are different axes and they are separable in the same table.

This entry is also the reason `0323`'s and `0331`'s timing arms carry a die-occupancy protocol:
this shelf met the failure, on the same board family, and wrote it down.

## 3 · Ground / Source
`scatter/precision_and_traps.md:117-134`, the whole trap:

```
## 7. 陷阱 4：性能读数会被同机负载污染

多进程共卡的 runner 会把两个评测进程压在同一张卡的两个 device 上，部分用例时延被拉高**一个数量级**。

**判别方法（比看总分可靠得多）**：**找同一条代码路径、同一量级规模的用例互相比对**。

| 用例（同为打包键路径） | 污染跑 | 干净跑 |
|---|---|---|
| 1.05M 元素 | 794.4us | **44.0us** |
| 约 1M 元素 ×3 条 | 约 40us | 约 40us |

一比就露馅。另外两条辅助判据：

- **代码缺陷会按 dtype / reduce / shape 结构分布，不会按用例序号整齐断开。**
  "前 10 条正常、后 10 条整齐慢 10~15 倍、五条不同代码路径同时塌" 一定是机器不是代码。
- 结果里的 `device` 字段是 `npu:6,7` 而不是 `npu:0` 就要警惕。

遇到异常低分**先看 runner，重跑一次再下结论**，别急着改代码。
```

Re-derived: `794.4 / 44.0 = 18.05×`. Upstream calls it `一个数量级`, which is consistent.

Read the table carefully — its force is in the second row, not the first. A single case at 794.4 µs
proves nothing; the same-path, same-scale controls sitting at ~40 µs in **both** runs are what
convert the outlier into an attribution. Without that row the table is a two-point comparison of two
runs and carries no attribution at all, which is exactly the failure mode this book records
elsewhere. Upstream built the control into the discriminant.

Note what the second row also establishes and upstream does not say: contamination is *per case*,
not per run. Three cases at 1 M elements were unaffected in the same contaminated run in which a
1.05 M-element case took 18× longer. So a run is not simply "dirty" — the interference is
intermittent within it, which is why sampling the die once before the session is insufficient
(`950`'s own die-occupancy record, memorised elsewhere in this project, reaches the same conclusion
from measurements this book does not carry).

The `npu:6,7` signature is a heuristic about one harness's device numbering and does not generalise
beyond it; recorded because it is cheap, not because it is sound.

Measured/inferred split at sentence level: **measured** — 794.4 µs, 44.0 µs, the ~40 µs controls.
**not measured** — that two processes on two devices of one card is the *cause* (upstream states the
mechanism and evidences the symptom); the "10~15 倍" and "五条路径同时塌" pattern, which is
described as a recognisable shape rather than reported as a reading.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The subject is a measurement
protocol, so §4 tests the protocol's discriminating power rather than any kernel.

Arm 1 — deliberate contamination. Run the scatter case set on an exclusively-held die, then re-run
it with a second process bound to a different die of the *same card*, then again with the second
process on a *different card*. Three conditions, one case set, everything else held. Record per-case
median time and the die-occupancy samples that preceded and followed each condition.

Arm 2 — the discriminant's sensitivity and specificity, which is the actual claim. From Arm 1's
tables, apply upstream's rule mechanically: for each case, find same-path same-magnitude siblings and
compute the ratio to their median. Verdict per case: `contaminated` if the ratio exceeds a threshold
declared before the run, `clean` otherwise. Score the discriminant against the known ground truth of
which condition each table came from.

Arm 3 — the false-positive direction, which upstream does not test. Introduce a *real* per-case
regression (a deliberately bad path choice for one dtype) on an exclusively-held die, and run the
same discriminant. It must **not** flag it as contamination — a defect that tracks dtype should
appear on all sizes of that dtype and therefore fail the same-path-sibling comparison in a different
way. This arm is what distinguishes a discriminant from a filter that calls every outlier a machine.

Arm 4 — the sampling question the second table row raises. Within one contaminated condition, run
the affected case 30 times and record the distribution. If contamination is intermittent within a
run, the distribution is bimodal, and that has a direct consequence for every timing arm in this
block: a median over 30 in-process runs may sit in either mode.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after each condition and
discard the condition if the die moved. The shared-machine budget (≤ 4 dies) is respected even in the
arm whose purpose is contention: the second process is bound explicitly, never left to the scheduler.
Refuses to assume: that "exclusively held" is achieved because it was requested — the control
condition's own occupancy samples are part of its record, and a control that was not clean is
discarded, not corrected; that one sample before a session characterises the session (Arm 4 exists
because it does not); that the harness's `device` field reports the physical die.

## 5 · Checker — acceptance declared before the run
Verdict `sibling_ratio[case]` = case median / median of its same-path same-magnitude siblings,
declared threshold `4×` — chosen before the run, well below upstream's observed 18× and well above
ordinary case-to-case spread, and stated now so it cannot be tuned to the answer.

Verdict `sensitivity` = fraction of same-card-contaminated cases flagged. Verdict `specificity` =
fraction of exclusively-held cases not flagged. Declared: the discriminant is **supported** iff
both exceed a declared 0.9. The OVERTURN fires iff `specificity` is low — a discriminant that flags
clean runs is worse than no discriminant, because it licenses dismissing real regressions.

Verdict `defect_not_flagged` = true iff Arm 3's real regression is not classified as contamination.
Verdict `bimodal` = true iff Arm 4's 30-run distribution has two separated modes.

The exit code is not the verdict. Three guards.

First — the input that makes this checker go red — Arm 1's exclusively-held condition is the
positive control and it **must** produce `sibling_ratio ≤ 4×` for every case. If the "clean"
condition already flags cases, the machine was never clean, the ground truth is wrong, and every
sensitivity and specificity figure in the run is void. A contamination study whose clean arm is
dirty confirms whatever it was looking for.

Second, Arm 3 is mandatory. Without it the discriminant has only been shown to detect contamination,
never shown to *not* detect something else, and that is the known blind species applied to a
diagnostic rather than to a checker.

Third, no per-case verdict is issued from a single run. Every median is over 30 in-process and 5
fresh-process runs, and Arm 4's result determines whether a median is even the right statistic —
if the distribution is bimodal, the report carries both modes and their weights, not a centre.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. 794.4 µs, 44.0 µs and the
~40 µs controls are upstream's readouts on Ascend950PR; this book has timed nothing, contaminated
nothing, and sampled no die.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or collected. Upstream reports one contaminated run and one clean run of one
case set; that establishes an occurrence, not a rate, not a threshold, and not the mechanism — the
"two processes on two devices of one card" story is stated and never instrumented. The 18× is one
case's figure and no envelope is given. The `10~15 倍` / `五条路径同时塌` pattern is described as a
recognisable shape and is not a reported reading. The `npu:6,7` signature belongs to one harness's
device numbering and generalises to nothing. Upstream's discriminant is never scored: no
false-positive rate is given, and §4 Arm 3 exists because a diagnostic that has only been tried on
true positives has not been shown to discriminate. Nothing here establishes how long a die stays
free after being sampled, which is the assumption every timing arm in this block rests on. BOARD is
`950PR`, the board the family's provenance note names; nothing is established for 950DT. Nothing
transfers to the other book (RULES.md Art. 1).
