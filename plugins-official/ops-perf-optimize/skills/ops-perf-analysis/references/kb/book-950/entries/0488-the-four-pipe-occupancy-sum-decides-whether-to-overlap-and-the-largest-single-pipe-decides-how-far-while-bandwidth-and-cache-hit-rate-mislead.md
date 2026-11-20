```
ID:        0488-the-four-pipe-occupancy-sum-decides-whether-to-overlap-and-the-largest-single-pipe-decides-how-far-while-bandwidth-and-cache-hit-rate-mislead
LABEL:     procedure
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scan/templates/cum_tile_resident_scan.md:30-34
           — "**判据只有一句：`PipeUtilization` 里 `vec% + scalar% + mte2% + mte3%` 加起来 /
           ≈100% 就是完全串行、必须上双缓冲；>130% 才算真重叠。** / 这比逐条算理论耗时快得多，也不会
           被 L2 命中率的差异误导（小足迹用例能吃到 L2， / 实测能到 2.1~2.7 TB/s，用 GB/s 判断会误判成
           "已达带宽上限"）。"
SOURCE:    same file:47-49 — "**先用「占比之和」决定要不要做，再用「最长单项」决定能做到哪**，
           理想重叠下的耗时 ≈ 总耗时 × 最长那条占比。" ; same shelf,
           templates/usage_guide.md:129-131 — the same criterion restated ; :144-146 —
           the same two-step method restated ; templates/cum_lane_parallel_scan.md — the same shelf's
           use of `ResourceConflictRatio` to exclude a bank conflict (`bank_cflt` 仅 0.1%,
           usage_guide.md:87)
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a kernel on a named 950 board whose four-pipe occupancy sum is above 130% and which still
           gains materially from adding ping-pong double buffering — the "already overlapped" reading
           of the sum would then be wrong. Equally: a kernel whose sum is near 100% and which gains
           nothing from double buffering would falsify the "completely serial" reading. And the second
           step is falsified by any kernel whose time after ideal overlap falls materially below
           `总耗时 × 最长那条占比`.
```

# 0488 · The four-pipe occupancy sum decides whether to overlap, and the largest single pipe decides how far, while bandwidth and cache hit rate mislead

## 1 · Claim
Upstream asserts a two-step diagnostic built from one profiler view. Step one: sum the four pipe
occupancy ratios — vector, scalar, MTE2, MTE3 — from `PipeUtilization`; a sum near 100% means the
pipes are completely serial and double buffering is required, and a sum above 130% is real overlap.
Step two: the largest single occupancy bounds what overlap can achieve, with the predicted ideal time
being `总耗时 × 最长那条占比`. Upstream asserts this is faster than computing theoretical per-stage
times, and that it avoids being misled by L2 cache hit rate — because a small-footprint case served
from L2 reaches a measured 2.1-2.7 TB/s, and judging by GB/s would misread that as already at the
bandwidth ceiling. Upstream states the criterion in three places across two files. Not established
here.

## 2 · The wrong branch this removes
Without this entry an agent diagnosing a memory-bound-looking kernel reaches for bandwidth. GB/s is
the standard instrument, it has a known ceiling, and "we are at 80% of peak bandwidth" is the standard
conclusion. Upstream's point is that the denominator is wrong when the working set fits in L2: the
achieved figure is against DRAM bandwidth while the traffic is being served from cache, so the ratio
is meaningless and the conclusion — "bandwidth-bound, nothing more to do" — is exactly backwards for a
kernel that is in fact completely serial and would gain 25-31% from double buffering.

The normal checks do not catch it because the bandwidth number is *correct*. Nothing is measured
wrongly; the metric simply does not answer the question asked of it. This book records the same
species at `0127` from another family and at `0317` — a bank conflict is confirmed by the conflict
counter and never inferred from vector time — and this is the third instance. What makes this one
worth its own entry is that upstream supplies the *replacement* instrument and its two thresholds,
rather than only naming the trap.

The second wrong branch is applying step one and stopping. A sum near 100% says double buffering will
help; it says nothing about how much. Upstream's own six-case table (`0481`) has two cases at 101-102%
that gained 0.3% and 2% — both correctly diagnosed as serial by step one, and both bounded by step two
at an MTE3 share of 74-80%. An agent that applies only step one spends effort on those two cases and
concludes the technique does not work.

The third wrong branch is reading the two thresholds as measurements. 100% and 130% are stated with no
derivation and no case behind either. 100% is arithmetic — four occupancies summing to the whole means
nothing ran concurrently — but 130% is a judgement about what counts as "real" overlap, and the shelf's
own table has post-change sums of 132%, 155%, 168%, 170%, 170% and 173%, so the threshold sits just
below the lowest observed value. Recorded as `Q-950fin-32`.

## 3 · Ground / Source
The criterion and the trap it replaces, `templates/cum_tile_resident_scan.md:30-34`:

```
**判据只有一句：`PipeUtilization` 里 `vec% + scalar% + mte2% + mte3%` 加起来
≈100% 就是完全串行、必须上双缓冲；>130% 才算真重叠。**

这比逐条算理论耗时快得多，也不会被 L2 命中率的差异误导（小足迹用例能吃到 L2，
实测能到 2.1~2.7 TB/s，用 GB/s 判断会误判成"已达带宽上限"）。
```

Two properties make this a usable instrument rather than advice. It names the **profiler view**
(`PipeUtilization`) and the **four fields**, so it is reproducible without knowing what the author
meant. And it states what it is better *than* — per-stage theoretical timing, and GB/s — so a reader
knows which conclusion it is meant to override.

The second step, `:47-49`:

```
后两个几乎没动——它们加完双缓冲后 `mte3` 单项就占到 74%/80%，是**纯写带宽受限**
（int64 索引占总写量的 4/5）。所以：**先用「占比之和」决定要不要做，
再用「最长单项」决定能做到哪**，理想重叠下的耗时 ≈ 总耗时 × 最长那条占比。
```

`理想重叠下的耗时 ≈ 总耗时 × 最长那条占比` is the entry's most useful sentence: a **predicted floor**
computable from one profile before any code changes. At 80% MTE3, the best achievable is 80% of
current time; at 25% across four pipes, it is 25%. That is falsifiable — any result below the predicted
floor kills it — and no other performance rule in this corpus makes a numeric prediction of that kind.

Restated at `templates/usage_guide.md:129-131` (`四个 ratio 加起来 ≈100% 就是完全串行，必须上
ping-pong；加到 130% 以上才算真重叠。这比逐条算理论耗时快得多，也不会被 L2 命中率误导。`) and the
two-step form again at `:144-146`. Three statements, two files, one repository — one origin (RULES.md
Art. 3), and the repetition is evidence the author thought it was the section's most transferable
claim rather than evidence it is right.

The `2.1~2.7 TB/s` figure is the only L2-served bandwidth number in the shelf. It carries no board, no
case and no method, and this book's architecture block holds no L2 bandwidth for any 950 board to check
it against — the same gap `Q-950fin-27` records for the `~1.2 TB/s` MTE3 figure in the same file. Two
absolute bandwidth figures in one document, neither scoped. Recorded together as `Q-950fin-27`.

The shelf practises the same discipline once more, on a different instrument: at `usage_guide.md:87`
it excludes a bank conflict as the cause of a 1.6× anomaly by naming the metric and its value
(`ResourceConflictRatio`, `bank_cflt` 仅 0.1%) before concluding (`0486`). So the family has a
consistent method — name the counter, state its value, then conclude — and it is the method `0317`
demands.

What the criterion does not cover: the sum is over four pipes on the **vector** core. A mixed
AIC/AIV kernel has cube-side pipes too (`0464`'s PipeBarrier material is about exactly that), and this
shelf's operators are vector-only, so the four-field sum is complete here and is not a general rule.
Upstream does not say so.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first, beside every point.

**Arm 1 — step one as a predictor.** Across the six shapes upstream's table names plus six chosen to
span the range, measure the four-pipe occupancy sum **before** any change, then add ping-pong double
buffering and measure the gain. Plot gain against the pre-change sum. Upstream's criterion predicts a
threshold near 100%: cases near 100% gain, cases already above 130% do not. This is the arm that turns
a rule of thumb into a curve, and it either finds the threshold upstream states or finds another.

**Arm 2 — step two as a floor.** For every case, compute `总耗时 × 最长那条占比` from the pre-change
profile and compare against the post-change time. Report the residual `(t_after − predicted) /
t_before`. Upstream's prediction is that the residual is non-negative; a negative residual anywhere
falsifies the floor, and its size is how conservative the rule is.

**Arm 3 — the trap the criterion replaces.** For the same twelve cases, record achieved GB/s and L2
hit rate alongside the occupancy sum, and identify every case where the bandwidth reading would have
said "at the ceiling" while the occupancy sum said "serial". Upstream asserts such cases exist and
names their mechanism (small footprint served from L2); this arm counts them and reports the L2 hit
rate at which the divergence begins.

**Arm 4 — the two thresholds, retained because they may not be thresholds.** From arm 1's curve, report
the sums at which the gain first becomes material and at which it vanishes, and compare against 100%
and 130% (`Q-950fin-32`). A curve with no knee would mean the thresholds are conventions rather than
boundaries, which is a finding about the instrument, not about the technique.

Refuses to assume: that a free die stays free, or that a die may be substituted; that `PipeUtilization`
reports what its field names suggest (`0317`'s species — every field is named in the report and its
definition recorded); that the four fields are the complete set for a kernel type (§3 records they are
for vector-only operators and this shelf's are); that occupancy and time move together (both are
reported); that a gain is a gain without its floor.

## 5 · Checker — acceptance declared before the run
Verdict `gain(case)` and `presum(case)` from arm 1, declared before the run. Acceptance for step one:
`gain` is material — declared now as >10% — for every case with `presum < 110%`, and immaterial for
every case with `presum > 130%`. Either half failing is a finding about the criterion.

Verdict `floor_residual(case) = (t_after − presum_max × t_before) / t_before` from arm 2. Acceptance
for step two: `floor_residual ≥ −floor` for every case. A materially negative residual is the
OVERTURN's third condition — the predicted floor would then be breachable and the rule would be
unsafe rather than merely conservative.

Verdict `bandwidth_misleads(case)` from arm 3, boolean, with the L2 hit rate at each.

Verdict `knee_positions` from arm 4, or `none`.

The exit code is not the verdict: this entry is a diagnostic method, and every build in every arm is
correct. Guards: (1) every occupancy figure is reported with the profiler's field name and the tool
version, and a figure reported without them is `untestable` — a sum over four fields whose definitions
are unknown is not a measurement, which is exactly the discipline the shelf itself practises when it
excludes bank conflict by naming `bank_cflt`; (2) **the input that makes this checker go red**: a
deliberately serialised kernel — one with an unconditional `PipeBarrier<PIPE_ALL>` between every stage
— whose occupancy sum must come out at or near 100% and which must gain from double buffering. If its
sum is not near 100%, the four fields do not measure what this entry assumes and every point in arm 1
is an artifact; (3) no point is reported without its shape, dtype, tool version, field names, floor and
CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The criterion with its two
thresholds, the L2 bandwidth figure, the two-step method, its restatements in the second file, and the
shelf's use of `ResourceConflictRatio` are file reads performed at drafting time, each re-verified
against its file. The observation that 130% sits just below the lowest post-change sum in upstream's
own six-row table (132%) is arithmetic over that table, not a measurement. The observation that the
four-field sum is complete for vector-only operators and not for mixed kernels is a reading of the
field list against this shelf's operator set, not an observation of any profile.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the occupancy sum predicts the
double-buffering gain, only that upstream states it and repeats it three times. It does not establish
100% or 130% as thresholds (`Q-950fin-32`); 100% is arithmetic and 130% is a judgement with no case
behind it. It does not establish the `理想重叠下的耗时 ≈ 总耗时 × 最长那条占比` floor, which is the
entry's most useful claim and its most falsifiable one. It does not establish the `2.1~2.7 TB/s`
L2-served figure or that GB/s misleads on any 950 board (`Q-950fin-27`). It does not establish what
`PipeUtilization`'s four fields measure — the field definitions are not in this shelf and this book
has not read the profiler's documentation. It does not extend to mixed AIC/AIV kernels, where the
cube-side pipes are outside the four-field sum and upstream does not say so. It does not cover
`ResourceConflictRatio` beyond noting the shelf's use of it (`0317` carries that). No board token
appears in either file, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where
our run would happen. Nothing here is established for any 910-family board.
