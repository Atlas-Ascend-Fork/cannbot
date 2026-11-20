```
ID:        0271-read-and-write-contend-on-hbm-so-a-fully-overlapped-pipe-model-overpredicts-a-copy
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (ops/ascendc-performance-evaluation). Upstream reports
           its own dated on-board measurement with the case identity attached; an upstream
           measurement is upstream text (RULES.md Art. 3) and is not our readout. Nothing was run here.
BOARD:     950PR
           # the sweep names 950PR parts; upstream's hardware model has no 950DT variant.
SOURCE:    ops/ascendc-performance-evaluation/references/hardware/ascend950pr.json,
           `common.gm_bandwidth_measured` — "rw_contention_alpha": 0.3, "rw_contention_note":
           "read and write contend on HBM: copy(32MB each way)=18.28us vs max(read,write)=14.19us
           => combined GM time ~= max(mte2,mte3) + 0.3*min(mte2,mte3). max_pipe (mte2||mte3 fully
           overlapped) over-optimistic for read+write streaming; this drives the softmax
           under-prediction, not a low peak BW."
SOURCE:    ops/ascendc-performance-evaluation/SKILL.md:65 — "**GM 带宽**：`chip_peak`（默认上限
           roofline）；`l2_aware`（标定的 L2 驻留 copy 曲线，用于 norm 这类 1读1写 流式算子）；
           `gm_rw_contention`（读写共享 HBM，α≈0.3）。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950PR copy benchmark in which measured GM time equals `max(mte2, mte3)` within run
           variance for a read-plus-write stream well above L2 — the contention term would then be
           zero and `max_pipe` is not over-optimistic.
```

# 0271 · Read and write contend on HBM, so a fully-overlapped pipe model overpredicts a copy

## 1 · Claim
Upstream asserts that GM reads and writes contend for HBM rather than overlapping freely, and models the
combined GM time as `max(mte2, mte3) + α × min(mte2, mte3)` with α ≈ 0.3. Upstream asserts the measurement
behind it: a copy of 32 MB each way took 18.28 µs against `max(read, write)` of 14.19 µs on 950PR.
Upstream asserts the modelling consequence — the default `max_pipe` overlap assumption, which treats MTE2
and MTE3 as fully parallel, is **over-optimistic** for read-plus-write streaming — and names the observed
symptom it explains: an under-prediction on softmax, attributed to this rather than to a low peak
bandwidth figure. Upstream exposes the correction as a selectable model, `gm_rw_contention`. Not
established here: nothing was run.

## 2 · The wrong branch this removes
`theoretical = max(mte2, vector, mte3)` (0264) is the roofline an agent will remember, and its MTE2/MTE3
half assumes the two directions are free of each other. For a copy-shaped operator — one read, one write,
which is most elementwise and norm kernels — that assumption predicts the operator costs no more than its
larger direction. Upstream's own measurement says it costs about 29 % more.

The consequence is a systematic, one-directional model error. The prediction is always too fast, so every
measured operator looks slower than theory, and the natural reading is that the kernel is at fault. A team
chases a 20-30 % gap that the model created. Upstream's note says exactly this happened —
"this drives the softmax under-prediction, **not** a low peak BW" — a sentence written to stop someone
lowering the bandwidth constant to close the gap.

That is the second wrong branch and it is the expensive one, because it is a *fix* that makes things
worse. Faced with theory-below-measurement, the obvious repair is to reduce the peak bandwidth until the
model fits. That closes the gap on copy-shaped operators and opens one on read-only and write-only
operators, which were never affected by contention. The calibration discipline (0272) forbids exactly
this class of edit, and this entry is a worked example of why: the residual had structure, and the
structure was a missing term, not a wrong constant.

The third branch is over-application. α applies to HBM contention, so it belongs where the traffic
actually reaches HBM. Below the L2 residency knee (0270) the working set is served from L2 and the
contention term is not obviously the same — upstream's own `l2_aware` curve is described as
"已含读写争用", contention *already included*, so applying `gm_rw_contention` on top of `l2_aware` would
double-count. Two of the three bandwidth models in `SKILL.md:65` account for contention, in different
ways, and nothing states that they are mutually exclusive.

## 3 · Ground / Source
`references/hardware/ascend950pr.json`, `common.gm_bandwidth_measured`, the contention fields verbatim:

```json
"rw_contention_alpha": 0.3,
"rw_contention_note": "read and write contend on HBM: copy(32MB each way)=18.28us vs max(read,write)=14.19us => combined GM time ~= max(mte2,mte3) + 0.3*min(mte2,mte3). max_pipe (mte2||mte3 fully overlapped) over-optimistic for read+write streaming; this drives the softmax under-prediction, not a low peak BW."
```

The note carries the whole derivation: the case (32 MB each way), both readings (18.28 µs measured,
14.19 µs as `max`), the resulting model, and the symptom it explains. Working the arithmetic back: if
read and write each take ≈14.19 µs, then `max + α × min` = 14.19 × (1 + α) = 18.28 gives α = 0.288 ≈ 0.3.
So the constant is one measurement rounded, and its provenance is legible — which is more than most
constants in this material offer, and is also a warning: **α is a single data point at one size**.

The enclosing object supplies the measurement's identity, quoted in 0270 §3: `"source": "membw-bench
(pure DataCopyPad GM<->UB, 64 cores, fp32, min over 50 reps) on 950PR_9589, 2026-06-08"`. Instrument,
part, date, core count, dtype, statistic — the best-documented measurement in this scope, and still
upstream's (RULES.md Art. 3).

The model selection, `SKILL.md:65`:

> - **GM 带宽**：`chip_peak`（默认上限 roofline）；`l2_aware`（标定的 L2 驻留 copy 曲线，用于 norm 这类
>   1读1写 流式算子）；`gm_rw_contention`（读写共享 HBM，α≈0.3）。`gm_reread_bytes` 走 L2、与 HBM 流重叠。

Three models, one of which is the default ceiling and two of which correct it in overlapping ways. The
`l2_aware` object's own note (0270 §3) says its curve is "copy_bw=combined(read+write)有效带宽 …
**已含读写争用**" — contention already included. So `l2_aware` and `gm_rw_contention` both account for the
same physical effect by different routes, and upstream does not say whether they compose. That ambiguity
is recorded here rather than resolved.

The overlap assumption this corrects, `SKILL.md:63`:

> **Roofline**：`theoretical = max(mte2, vector, mte3)`，在 `overlap_model="max_pipe"`（稳态 overlap；
> `serial` 则相加）下…

`max_pipe` and `serial` are the two extremes — full overlap and none. The contention model is the middle
term neither offers, and it is expressed as a *bandwidth* model rather than as an overlap model, which is
a structural oddity: `α × min(mte2, mte3)` is a statement about pipe overlap and is selected through the
GM-bandwidth knob.

Note what α is **not** claimed to be. It is not derived from a hardware property, it has no ini field
(0224 records that no bandwidth field exists at all), and upstream gives it as ≈0.3 rather than as a
measured constant with an interval. One case, one size, one part, one date.

## 4 · Procedure
Runnable later on `950PR`. Upstream ships the instrument (`tests/onboard/kernels/membw`), so this
re-derives its result independently and then attacks the two things the single data point cannot support.

Arm A — reproduce the case. Run pure read, pure write, and copy at 32 MB each way on a named 950PR die,
64 cores, fp32, minimum over 50 repetitions — upstream's stated protocol, so the comparison is
like-for-like. Working set well above L2 (0218, 0270) so contention is on HBM rather than masked by
residency. Compute α = (measured_copy − max(read, write)) / min(read, write).

Arm B — is α a constant, which is the question one data point cannot answer. Sweep the transfer size
across 4, 8, 16, 32, 64, 128, 256 MB each way and compute α at every point. Upstream's model treats α as
size-independent; if it drifts, the correction is a curve and the single constant is a fit at one size.
This is the arm that matters most, because a roofline applies α everywhere.

Arm C — the asymmetric case, which the model's `max`/`min` form makes a prediction about and which
upstream never tested. Sweep the read:write ratio — 1:1, 2:1, 4:1, 8:1 — at constant total bytes. The
model predicts the penalty scales with the *smaller* direction, so it should vanish as the ratio grows.
If it does not, the `α × min` form is wrong even where α's value is right.

Arm D — the composition question §2's third branch raises. Run one norm-shaped operator below the L2 knee
and above it, and compare measured time against three predictions: `l2_aware` alone, `gm_rw_contention`
alone, and both composed. Upstream states that `l2_aware` already includes contention; if composing them
double-counts, that is a modelling defect an agent selecting knobs would hit immediately.

Arm E — the roofline consequence, end to end. Take the softmax case upstream names and compare measured
Task Duration against `theoretical` under `max_pipe` alone and under `max_pipe + gm_rw_contention`. The
claim is that the correction removes a named under-prediction; this is the arm that checks it does.

Device selection is explicit: the operator names the device index **and the SKU** (α is a per-part
measurement and 0218 records L2 varying across SKUs), the harness prints both back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. HBM is shared across cores, so sole-tenancy of the die is
confirmed and recorded before Arm A rather than assumed — a co-tenant streaming would depress every
reading and inflate α.

## 5 · Checker — acceptance declared before the run
Verdict variable `alpha_measured`, from Arm A. Pass iff it lands in [0.24, 0.36] — ±20 % around 0.3, a
band deliberately wider than the ±10 % used elsewhere in this block, because upstream states the value as
≈0.3 rather than as a measured constant and a tighter band would assert a precision the source does not
claim.

`alpha_is_size_stable` (Arm B) — pass iff α across the seven sizes stays inside that same band. This is
the operative verdict and it is separated deliberately: `alpha_measured` passing at 32 MB only reproduces
upstream's single point, and reproducing one point cannot establish a constant. A drift outside the band
means the correction is a curve, the entry is corrected in place, and the roofline needs a table rather
than a scalar.

`alpha_scales_with_min` (Arm C) — pass iff the measured penalty tracks `α × min(mte2, mte3)` across the
read:write sweep, within the same band. A penalty that persists at 8:1 falsifies the model's form
independently of its constant.

`compose_double_counts` (Arm D) — reported: whether `l2_aware + gm_rw_contention` over-predicts relative
to either alone. No pass threshold; upstream does not say whether they compose, and either answer is a
finding about the knobs.

The positive fixture, declared before the run: Arm A must include a **pure read** and a **pure write**
arm, for which α is undefined and the copy model must not fire. If the harness reports a non-zero
contention penalty for a single-direction stream, it is attributing something else to contention — most
likely a size effect or residency — and every α it produced is void. A second fixture: run the 32 MB copy
with the working set reduced below the L2 knee. α must change, because the traffic is no longer on HBM; if
it does not, Arm A was never measuring HBM contention. Without both, the checker reads only "the copy was
slower than the max", which is the known blind species — many things make a copy slower than its larger
half.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no bytes were
moved, and `membw-bench` was not reproduced. The 18.28 µs and 14.19 µs figures, the α of 0.3, and the
softmax attribution are all upstream's own reported readouts read out of a JSON file; under RULES.md Art. 3 an
upstream measurement enters this book as upstream text. The α ≈ 0.288 back-derivation in §3 is arithmetic
over upstream's two stated timings, performed here to show the constant's origin, and is not an
observation.

## 7 · Scope limits — what this entry does NOT establish
Nothing was run. The entry does not establish α, its size-stability, or the model's `max + α × min` form —
Arms A-C are all open. The most important limit is that **α rests on a single reported data point**: one
transfer size (32 MB each way), one part (950PR_9589), one date, one direction ratio (1:1). Upstream states
it as ≈0.3 and offers no interval, no size sweep and no asymmetric case, so treating it as a constant is an
extrapolation from one measurement — which is exactly what Arms B and C test. There is **no second
origin**: all of it is one upstream skill, and no ini field expresses HBM contention (0224). It does not
establish the softmax attribution: upstream names the symptom this term explains, and no operator was run
here to confirm the correction removes it (Arm E). It does not resolve whether `gm_rw_contention` and
`l2_aware` compose or double-count — upstream states that `l2_aware` already includes contention and never
says the two are exclusive (Arm D). It says nothing about the regime below the L2 knee, where the traffic
is not on HBM and the term's applicability is unstated, nor below ~8 MB where the operator is launch-bound
(0270). BOARD is `950PR` and more narrowly 950PR_9589; **nothing here covers 950DT**, which upstream's
hardware model has no variant for. Finally, this is a *bandwidth-model* knob expressing a *pipe-overlap*
effect, which is a structural oddity noted in §3 and not resolved: an agent reasoning about overlap will
look in `overlap_model` and find only `max_pipe` and `serial`.
