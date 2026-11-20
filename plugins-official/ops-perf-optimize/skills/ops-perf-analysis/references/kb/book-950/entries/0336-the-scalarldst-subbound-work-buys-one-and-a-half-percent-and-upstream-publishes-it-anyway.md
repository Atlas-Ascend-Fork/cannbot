```
ID:        0336-the-scalarldst-subbound-work-buys-one-and-a-half-percent-and-upstream-publishes-it-anyway
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/flash_attention/scalarldst_subbound_design.md:9-13
           — "| 指标 | Baseline | SCALARLDST 优化后 | 变化 | | 最长核 case cycle | 18353 | 18076 |
           -1.51% | | Cube 核 SCALARLDST busy | 81.30% | 81.14% | -0.16pp | | 头开销 cycles | 3205 |
           3102 | -3.21% |"
SOURCE:    same file:17 — "SCALARLDST 主导时，继续把 ALU 计算改成成员预计算可能只是在"少一次乘法"和
           "多一次成员 load"之间对冲。优化重点应转为减少 load/store 本身。" ; :101-105 —
           "风险红线： / - 不把 `stackSeqCount % (PRE_LAUNCH + 1U)` 改成位与，因为
           `PRE_LAUNCH + 1U == 3`。 / - 不改 TilingData 结构、host tiling 字段和事件同步链。 /
           - 删除 lazy-init 守卫前，必须保证所有调用路径已显式初始化 stride。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured FIA case on a named 950 board where the MR1–MR5 set moves the longest-core
           cycle count by more than the baseline arm's own repeat-to-repeat spread in either
           direction — a −1.51 % claim stands or falls entirely on that spread, which upstream never
           states.
```

# 0336 · The SCALARLDST sub-bound work buys one and a half percent, and upstream publishes it anyway

## 1 · Claim
Upstream asserts five load-shedding techniques for the SCALARLDST sub-class (`0334`) and reports
their combined effect on one case: longest-core cycles 18353 → 18076 (−1.51 %), Cube-core SCALARLDST
busy 81.30 % → 81.14 % (−0.16 pp), header-overhead cycles 3205 → 3102 (−3.21 %). Upstream asserts the
principle behind the set: when SCALARLDST dominates, converting ALU work into member precomputation
merely trades one multiply for one member load, so the target must be the loads themselves. The five
are MR1, removing a lazy-init guard from the hot loop by initialising explicitly at the entry above
it; MR2, capturing quasi-constant `*_Pow2_` / `*_Shift_` / `*_Mask_` members into function-local
`const` at the operator entry; MR3, replacing a small lookup table with a `switch` over constants;
MR4, aliasing workspace-base members into function-local `const`; MR5, reading loop-invariant members
once at entry. Upstream asserts three red lines: a modulus by `PRE_LAUNCH + 1U` must **not** become
a bit-and, because that value is 3; TilingData structure, host tiling fields and the event
synchronisation chain must not change; and the lazy-init guard may be removed only once every call
path is shown to initialise the stride explicitly. Not established here.

## 2 · The wrong branch this removes
This entry earns its slot for a reason that is not the technique. It is the smallest reported effect
in this shelf, it is reported with three decimal-place precision and no variance figure, and
upstream publishes it as a success. That combination is the thing a consuming agent must learn to
read.

`−1.51 %` on a single case, with no repeat count and no spread, is not distinguishable from zero by
anything in the document. `−0.16 pp` on a busy percentage is smaller still. A skill that repeats
these as achievements teaches an agent that 1.5 % is a result; the honest reading is that 1.5 % is a
number, and whether it is a result depends entirely on a figure upstream did not report. This is
the same discipline `0304` applies to a −4.1 % claim and `0311` to −7.5 %: the smaller the effect,
the more load the missing variance figure carries, and here it carries all of it.

The second wrong branch is the ordering one, and it is the useful half. Given a `SCALARLDST`-dominant
case, the natural move is still precomputation — it is what "scalar optimisation" means to most
agents. Upstream's opening sentence says why it cancels: a precomputed member is one fewer multiply
and one more load, and if loads are the bottleneck the trade is a wash or worse. So the sub-class
routing (`0334`) is not bureaucracy; it selects between two sets that push in opposite directions on
the same operator.

The third wrong branch is the strength-reduction reflex, and upstream's red line is the sharpest
single line in this family: `不把 stackSeqCount % (PRE_LAUNCH + 1U) 改成位与，因为 PRE_LAUNCH + 1U
== 3`. Replacing `% n` with `& (n−1)` is correct only when `n` is a power of two. An agent shedding
scalar cost will meet several moduli and this one looks identical to the others. The failure is
silent and produces wrong indices.

The fourth is MR1's own precondition. Removing a lazy-init guard from a hot loop is free only if
every caller already initialises; upstream states the obligation and it is a whole-program property
that a local diff cannot show.

## 3 · Ground / Source
The measurement, `scalarldst_subbound_design.md:7-13`:

```
已验证效果：

| 指标 | Baseline | SCALARLDST 优化后 | 变化 |
| 最长核 case cycle | 18353 | 18076 | -1.51% |
| Cube 核 SCALARLDST busy | 81.30% | 81.14% | -0.16pp |
| 头开销 cycles | 3205 | 3102 | -3.21% |
```

Re-derived: `(18353 − 18076)/18353 = 1.509 %` ✓; `81.30 − 81.14 = 0.16 pp` ✓;
`(3205 − 3102)/3205 = 3.214 %` ✓. Every figure is internally consistent. None carries a repeat
count, a variance, a board, a tool, a CANN pin or a case identity.

Note which metric moved most: header overhead, at −3.21 %, and its absolute change (103 cycles) is
37 % of the total change (277 cycles). So a third of a result attributed to hot-loop load shedding
sits in the launch header — which is where `0335`'s techniques operate. Whether the two overlap is
not stated and cannot be read off; it is recorded because a reader stacking both sets would
otherwise double-count.

The principle, `:17`:

```
SCALARLDST 主导时，继续把 ALU 计算改成成员预计算可能只是在"少一次乘法"和"多一次成员 load"之间
对冲。优化重点应转为减少 load/store 本身。
```

The four problem shapes and their directions, `:19-24`:

```
| 一次性初始化守卫留在热循环 | `if (!ready_) Update(...)` | 初始化前置，删除热循环守卫 |
| 准常量分支每轮读成员 | `if (pow2_) x >> shift_ else x / divisor_` | 入口捕获为局部 `const` 或模板化 |
| 查表替代 ALU 后增加 load | `maskTable_[len]` | 小集合改为 `switch` 常量 |
| 成员字段反复访问 | `this->coreWsBase_` / `this->blockSize_` | 函数局部 `const` 别名 |
```

The third row is a correction of an earlier optimisation: a lookup table was introduced to replace
ALU work, and on a load-bound path the table read is the cost. MR3 replaces it with a `switch` over
compile-time constants (`:72-89`, eight `case` labels producing 64-bit masks). That is a
mechanism-level statement about which resource a lookup table spends, and it generalises past this
operator.

The red lines, `:101-105`:

```
风险红线：

- 不把 `stackSeqCount % (PRE_LAUNCH + 1U)` 改成位与，因为 `PRE_LAUNCH + 1U == 3`。
- 不改 TilingData 结构、host tiling 字段和事件同步链。
- 删除 lazy-init 守卫前，必须保证所有调用路径已显式初始化 stride。
```

The stated risk of MR5, `:34` and `:99`: `防止过多局部变量造成寄存器 spill`, with the fallback
`回退部分局部化，保留收益最大的字段`. So the technique has a self-limiting point that upstream
names and never locates — the number of members that can be localised before spill costs more than
the loads saved is not given.

Measured/inferred split at sentence level: **measured** — the three before/after pairs, on one case.
**not measured** — that any individual technique among MR1–MR5 contributes (all five were applied
together, the same confound as `0335`); that the ALU-to-load transfer actually cancels (asserted,
never instrumented); where the spill point is.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. At this effect size the
procedure is mostly about the floor.

Variance floor **first and as the primary result**: build the baseline once, run it 30 times
in-process and 5 times fresh-process, and report the interquartile range over the median before any
comparison is attempted. If the floor exceeds 1.5 %, upstream's headline is unreportable on this
part and that is the finding — the run stops there and says so, rather than producing a number.

Arm 1 — reproduce, if the floor permits. Baseline and all-five-applied builds, recording
longest-core cycles, SCALARLDST busy and header cycles, against upstream's three pairs.

Arm 2 — per-technique attribution, which the source lacks. Six builds: baseline plus each of MR1–MR5
alone. Report each delta with the floor attached; techniques inside the floor are reported as
`unattributed`.

Arm 3 — the ALU/load trade, instrumented rather than argued. Take a precompute technique from the
S-set (`0334`) and apply it to this same case, recording `SCALAR%` and `SCALARLDST%` before and
after. Upstream's principle predicts SCALAR falls, SCALARLDST rises and cycles do not improve. This
is the only arm that tests the reason the two sub-classes exist.

Arm 4 — the spill point MR5 warns about. Localise members one at a time, past the point upstream
stopped, recording register pressure (from the compiler's resource report) and cycles at each step.
The turning point is a number nobody has.

Arm 5 — the red line, as a deliberate defect. Build with `% 3` replaced by `& 2` and confirm the
correctness comparison catches it. See §5.

`0327`'s same-path sibling check applied to every table. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved — at 1.5 % a co-tenant is not a nuisance, it is
the whole signal. Refuses to assume: that a free die stays free; that a die may be substituted; that
"longest-core cycle" is stable across runs (it is a max over cores, so it is the *most* variance-prone
statistic available, and its spread is reported separately from the mean-core spread); that the case
is known — upstream identifies none, so Arm 1 reproduces a method, not a case.

## 5 · Checker — acceptance declared before the run
Verdict `floor` = the baseline's IQR over median, reported first and unconditionally. Declared
before the run: if `floor ≥ 1.51 %`, every cycle comparison in this entry is reported as
`indistinguishable` and no pass or fail is issued. That is not a hedge; it is the acceptance
condition, declared now so that a −1.5 % reading cannot later be presented as a result against an
unstated spread.

Verdict `cycle_delta`, `busy_delta`, `header_delta` from Arm 1, each with the floor.
Verdict `mr_delta[i]` for `i = 1…5` from Arm 2, each labelled `attributed` or `unattributed`.
Verdict `trade_confirmed` = true iff Arm 3 shows SCALAR falling, SCALARLDST rising and cycles not
improving.
Verdict `spill_point` = the localisation count at which Arm 4's cycles turn.

The exit code is not the verdict. Three guards.

First — the input that makes this checker go red — Arm 5's `& 2` substitution is the planted
positive: the correctness comparison **must** fail on it. `stackSeqCount % 3` and
`stackSeqCount & 2` agree at `stackSeqCount ∈ {0, 1, 2}` and diverge from 3 onward, so a test whose
sequence counts stay below 3 will pass the broken build. If Arm 5 passes, the case does not exercise
the modulus at all, MR-set correctness has not been tested, and every green is void. The fixture is
chosen precisely because it is *nearly* right.

Second, MR1's precondition is checked as a whole-program property, not a diff: every call path
reaching the loop is enumerated and shown to initialise the stride, and a path that cannot be
enumerated is a blocker rather than a risk.

Third, no delta is reported without the floor, and `busy_delta` at 0.16 pp is reported as
`indistinguishable` unless the busy metric's own spread is measured and is smaller — a percentage
point of a busy ratio has its own variance and it is not the cycle floor.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. 18353, 18076, 81.30 %,
81.14 %, 3205 and 3102 are upstream's readouts on an unnamed part and an unidentified case; this book
has built nothing, timed nothing, and measured no variance — which is exactly the figure the entry
turns on.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The headline is a **single case** with no identity — no shape, no
dtype, no head configuration — no repeat count, no variance, no board, no tool and no CANN pin, so
`−1.51 %` is not distinguishable from zero by anything in the source, and this entry does not claim
it is a result. `−0.16 pp` is smaller still. No per-technique attribution exists: all five were
applied together. A third of the total cycle change sits in the header-overhead metric, which is
where `0335`'s separate technique set operates, and the overlap is not stated — so the two sets'
gains must not be added. The ALU-to-load cancellation that justifies the whole sub-class split is
asserted and never instrumented. MR5's spill point is named as a risk and never located.
`PRE_LAUNCH`, `stackSeqCount`, `maxKVStackLen`, `coreWsBase_` and `blockStackNum_` are named without
definitions. The techniques are validated on FIA only. BOARD is `family-claimed(unverified)`:
the family is marked DAV_3510 in the shelf index and no file names a board. Nothing transfers to the
other book (RULES.md Art. 1).
