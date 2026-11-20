```
ID:        0054-a-full-core-launch-on-atlas-a2-costs-about-twenty-microseconds
LABEL:     knowledge
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin. 2026-08-25: §4 RAN on 910B2 and §5's own control ("launch_us(1) must be
           lower than launch_us(full), or the run is VOID") did not pass — the launch cost is FLAT in block dim
           (event-timed 13.5–14.2 µs at 1, 8, 24, 40 and 48 blocks; device Task Duration 1.1–1.5 µs) — so by §5's
           letter the run is VOID and no verdict is issued. The control presupposed the scaling it was meant to
           test; readouts in §6, corrected control proposed in §4 as-run. No promotion.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ops-profiling/references/optimization_quickref.md:102-106 — "| 平台 | 满核头开销 | 说明 | / | Atlas A2 | ~20-21 us | 包含核启动 + TLB + 初始化 |" and "如果 Task Duration 中头开销占比 >30%，说明数据量太小或核数太多"
INDEX:     none — nothing measured to a §5 verdict; see SOURCE. (2026-08-25 readouts, 910B2, in §6: empty kernel
           event-timed 13.5–14.2 µs median at every block dim 1..48; msprof Task Duration 1.47 / 1.12 µs at 1 / 48
           blocks; an fp16 x+1 kernel at 48 cores is launch-bound (13.8–14.7 µs) up to 1 MB, 16.1 µs at 4 MB, 25.2 µs
           at 16 MB.)
OVERTURN:  an empty-kernel launch at full block dim on a named Atlas A2 board measures materially outside 20–21 µs — in particular if it scales with block dim rather than being a fixed full-core cost.
```

# 0054 · A full-core launch on Atlas A2 costs about twenty microseconds

## 1 · Claim
Upstream asserts that on Atlas A2 the full-core launch overhead is about 20–21 µs, comprising
kernel launch, TLB and initialisation, and that a head overhead exceeding 30 % of Task Duration
means the data volume is too small or the core count too high. Upstream prescribes reducing the
core count for small data: fewer cores means less head overhead. Not established here.

## 2 · The wrong branch this removes
Maximum parallelism is the default instinct: use every core. For a small operator that is exactly
wrong, and the reason is a fixed cost that does not appear anywhere in a data-volume model. At
20 µs, an operator whose useful work is 30 µs spends 40 % of its time launching, and the fix — use
fewer cores — is counter-intuitive enough that an agent will not reach it unaided.

The second branch is diagnostic and is why the 30 % rule matters more than the 20 µs figure. A
small operator that is "slower than the model" invites tiling changes, buffer tuning, instruction
selection — all of which act on the 60 % and none on the 40 %. Knowing to compute the head fraction
first redirects the whole investigation.

This is also the number that makes 0041's barrier cost interpretable. A ~200 µs GM-polling barrier
is ten launches' worth of overhead; without a launch figure to compare against, "200 µs" has no
scale.

## 3 · Ground / Source
`ops/ops-profiling/references/optimization_quickref.md` §4 Scalar Bound, lines 102-106, verbatim:
```
| 平台 | 满核头开销 | 说明 |
|------|----------|------|
| Atlas A2 | ~20-21 us | 包含核启动 + TLB + 初始化 |
```
"如果 Task Duration 中头开销占比 >30%，说明数据量太小或核数太多。"

The remedies in the same section, lines 95-98: "| 1 | **缩小 TilingData** | 减少不必要字段，
TilingData 越大搬运越慢 | | 2 | **减少核数** | 数据量小时，少核 = 少头开销 | | 3 | **TPipe 外置** |
避免 TPipe 在对象内创建和初始化 | | 4 | **移出不变量** | 循环不变的计算移到 Host 侧 |".

Note the table has a 平台 column with exactly one row. So upstream structured the statement to be
per-platform and then filled in only A2 — which means the figure is scoped (good) and that no
comparison to any other part is available (a limit).

This is one of very few explicitly A2-scoped numbers in the sources surveyed for this book. It
carries no tool, no repeat count, no board sub-model, and no core count beyond "满核" — and "full
core" is itself ambiguous given that the core count differs across DAV_2201 parts (0009): 48 AIV on
910B1/B2, 40 on 910B3. If the overhead scales with core count, "满核" names two different numbers.

`optimization_quickref.md` carries no provenance line (0053 §3), so the figure's origin is unknown.

Adjacent A2-scoped figures from the same skill, carried by 0055:
`ops/ops-profiling/SKILL.md:243` (GM peak bandwidth ~1.8 TB/s) and `:252` (fp32 Vector peak
~11.06 TOPS).

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; record the part and its core count via `GetCoreNumAiv()` (0011); occupancy before
   and after; no substitution.
2. Empty-kernel arm: a kernel that does nothing, launched at block dim swept over 1, 8, 24, 40, 48
   (clamped to the part's count). Task Duration per launch, 20 launches, first 10 discarded as
   warm-up, mean and spread of the last 10. `msprof op --warm-up=10`.
3. The block-dim sweep is the substance of the experiment, not a refinement. "满核头开销" implies a
   fixed cost at full occupancy; whether it is fixed or proportional to block dim is not stated and
   changes the advice entirely — if proportional, "reduce the core count" is quantitatively
   predictable, and if fixed, it is not.
4. Head-fraction arm: a real elementwise kernel at data volumes spanning 1 KB to 16 MB, reporting
   head overhead as a fraction of Task Duration, to locate where the 30 % rule fires.
5. Report absolute microseconds, not only ratios.

**As run (2026-08-25, the 910 machine, die 0, job launch910):** steps 2–5 as written with `aclrtEvent`
pairs around each launch (host-visible dispatch-to-completion; 20 launches, last 10 kept, three interleaved
passes) and msprof `Task Duration` at block dim 1 and 48 (the device-side view); `GetCoreNumAiv()` = 48 from
the 0009 run. Step 4 with an fp16 `x + 1` kernel (DataCopy in, `Adds`, DataCopy out, 16 KB tiles) at 48
cores from 1 KB to 16 MB and at 1 core from 1 KB to 1 MB. **§5's control cannot pass on this part**: it
requires the 1-block launch to be measurably cheaper than the 48-block launch, and the two are equal within
noise (medians 13.6–16.8 vs 13.9–14.2 µs) — the very "fixed overhead" reading `launch_scaling` was written to
detect. By §5's letter the run is VOID; the readouts stand in §6 for a re-run under a corrected control
(proposed: a kernel with a known device-side busy loop of ~10 µs must read ~10 µs above the empty kernel —
a control that tests the timing method, not the hypothesis).

## 5 · Checker — acceptance declared before the run
Verdict variable `launch_us(block_dim)`.
PASS iff `launch_us` at full block dim lies in [15, 30] µs — a window declared now, wider than the
quoted 20–21 because that figure carries no conditions at all.
`launch_scaling`: reported with no declared expectation. A flat `launch_us` across block dim
supports "fixed full-core overhead"; a rising one means the term is misnamed and the entry is
corrected. This is the more informative verdict of the two and is stated as such before the run so
that a single full-core measurement cannot be presented as the whole result.
Control: `launch_us(1)` must be lower than `launch_us(full)`, or the measurement is not resolving
launch cost at all and the run is VOID.
Cross-check against 0041: the barrier procedure's timing intercept must be consistent with
`launch_us` measured here. Two independent estimates of the same quantity disagreeing is a finding
about the method, and stating the cross-check now is what makes it one rather than an oversight.
Exit code is not the verdict.

## 6 · Evidence
§4 RAN 2026-08-25 on 910B2 (die 0, idle before and after) but NOT YET RUN to a verdict — §5's control failed
by construction (see §4 as-run). Readouts, recorded for the re-run:

**Empty kernel, `aclrtEvent` around each launch (µs; 20 launches, last 10 kept; three interleaved passes):**

| block dim | min | median | mean | max |
|---|---|---|---|---|
| 1 | 13.34 | 13.88 | 14.62 | 22.90 |
| 8 | 13.80 | 21.96 | 21.78 | 28.44 |
| 24 | 4.00 | 13.70 | 11.67 | 16.02 |
| 40 | 8.48 | 13.88 | 13.39 | 14.90 |
| 48 | 13.44 | 13.94 | 13.92 | 14.50 |
| 1 | 13.18 | 13.56 | 13.59 | 14.20 |
| 8 | 12.26 | 13.52 | 13.56 | 15.38 |
| 24 | 4.18 | 13.58 | 11.31 | 15.46 |
| 40 | 4.66 | 13.84 | 11.25 | 15.92 |
| 48 | 4.00 | 14.20 | 10.91 | 15.54 |
| 1 | 16.48 | 16.80 | 16.87 | 17.66 |
| 8 | 10.00 | 14.16 | 13.85 | 16.72 |
| 24 | 4.40 | 13.90 | 11.03 | 19.50 |
| 40 | 4.38 | 13.66 | 12.67 | 18.08 |
| 48 | 4.42 | 14.16 | 12.44 | 16.24 |

**Empty kernel under msprof (device-side, 20 launches):** block dim 1 — Task Duration min 0.90 / med 1.47 /
max 2.38 µs, aiv_time med 0.93 µs; block dim 48 — Task Duration 1.12 / 1.12 / 10.28 µs, aiv_time 0.06 µs.
The ≈ 14 µs is host-side dispatch and completion, not device execution.

**Head-fraction arm, fp16 `x + 1`, `aclrtEvent` (µs):**

| bytes | block dim | elems per core | min | median | max |
|---|---|---|---|---|---|
| 1 KB | 48 | 16 | 4.70 | 14.64 | 16.40 |
| 4 KB | 48 | 48 | 4.88 | 13.84 | 14.32 |
| 16 KB | 48 | 176 | 13.72 | 14.22 | 14.84 |
| 64 KB | 48 | 688 | 13.88 | 14.66 | 15.24 |
| 256 KB | 48 | 2736 | 13.36 | 13.82 | 14.54 |
| 1024 KB | 48 | 10928 | 13.86 | 14.06 | 14.32 |
| 4096 KB | 48 | 43696 | 14.34 | 16.10 | 18.20 |
| 16384 KB | 48 | 174768 | 18.50 | 25.24 | 26.72 |
| 1 KB | 1 | 512 | 14.20 | 14.42 | 15.10 |
| 16 KB | 1 | 8192 | 13.48 | 14.56 | 15.40 |
| 256 KB | 1 | 131072 | 10.36 | 22.38 | 32.52 |
| 1024 KB | 1 | 524288 | 28.42 | 29.96 | 31.78 |

At 48 cores the kernel is launch-bound (13.8–14.7 µs) up to 1 MB; 4 MB adds ≈ 2 µs, 16 MB ≈ 11 µs — the
"head is 30 %" line sits near 16 MB for this kernel at this clock (800 MHz).

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "Atlas A2" is a product line spanning five parts, not a
board, and "满核" names a different core count on different members of it (§3, 0009). No tool,
repeat count or measurement protocol is given by upstream, and `optimization_quickref.md` has no
provenance line. This entry does not establish the breakdown between launch, TLB and initialisation
— upstream names three components and measures their sum. It does not establish anything for Atlas
A3 (Ascend910_93), which upstream's own per-platform table leaves blank. It does not establish that
the 30 % rule identifies a real decision boundary; that is an unscoped threshold of the 0053 class.
