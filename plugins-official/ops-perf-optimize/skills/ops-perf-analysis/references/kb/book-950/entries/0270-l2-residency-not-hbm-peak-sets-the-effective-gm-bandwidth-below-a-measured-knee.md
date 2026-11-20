```
ID:        0270-l2-residency-not-hbm-peak-sets-the-effective-gm-bandwidth-below-a-measured-knee
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   verified — §4 Arms A, B, D and fixture 2 run on 950PR 2026-08-25 with upstream's own `membw` instrument
           (ported single-source); §5's PASS brackets NOT met on either half — `knee_bytes[read]` and `[write]`
           onset in (112 MB, 120 MB], below the declared (128, 160]; `knee_bytes[copy]` onset in (32, 48] MB per
           tensor, below the declared [56, 64] — while `plateau_bw` sub/super-knee = 3.99/1.60 (read) and
           4.45/1.54 (write) TB/s, ≥ 2× ✓, and fixture 2 (L2 hint DISABLE) collapses the sub-knee plateau to
           the HBM rate ✓ (the knee IS L2 residency). Corrected in place: the residency knee sits BELOW the
           128 MiB L2 size, not above it. Arm C and fixture 1 not run (§6). Previously harvested.
BOARD:     950PR (measured 2026-08-25, the 9579 SKU: ini l2_size=134217728); 950DT unverified
           # upstream's sweeps name 950PR_9589 and 950PR_9579 specifically; 950DT is not covered.
SOURCE:    ops/ascendc-performance-evaluation/references/hardware/ascend950pr.json,
           `common.gm_bandwidth_measured` — "source": "membw-bench (pure DataCopyPad GM<->UB,
           64 cores, fp32, min over 50 reps) on 950PR_9589, 2026-06-08"; `hbm_sustained_read` /
           `_write` 1.5e12; `l2_read_bandwidth_bytes_per_s` 4.5e12; `l2_write_...` 4.95e12;
           `l2_residency_knee_bytes` 134217728; `fixed_overhead_us_host` 6.5
SOURCE:    same file, `common.gm_bandwidth_l2_aware` — "2026-06-11 ascend950-root-10012 <<<>>>
           mem_copy sweep (tests/calibration/bench_results/membw_copy_sweep.csv)"; curve
           [[134217728, 2.84e12], [268435456, 1.45e12]]; `l2_reread_bandwidth_bytes_per_s` 3.0e12
SOURCE:    ops/ascendc-performance-evaluation/SKILL.md:65 — "**GM 带宽**：`chip_peak`（默认上限
           roofline）；`l2_aware`（标定的 L2 驻留 copy 曲线，用于 norm 这类 1读1写 流式算子）；
           `gm_rw_contention`（读写共享 HBM，α≈0.3）。`gm_reread_bytes` 走 L2、与 HBM 流重叠。"
INDEX:     means=upstream `tests/onboard/kernels/membw/membw.asc` ported to one `-xasc` source (+ `-DL2OFF` variant
           applying `SetL2CacheHint(CACHE_MODE_DISABLE)` to both tensors), 56 blocks, `aclrtEvent` over 20–100
           launches × 5 batches (min and median)
           conditions=CANN 9.1.0, 950PR (Ascend950PR_9579.ini: l2_size=134217728), device idle,
           npu-smi curFreq reading 100 MHz throughout (the AI Core clock; MTE traffic ran at 4 TB/s regardless)
           readouts (TB/s, min time): read 8/16/32/64/96/112 MB = 1.39/2.26/2.92/3.65/3.77/3.99, 120/128/136/144/
           160/192/256/512 = 2.98/2.78/2.71/2.05/2.04/1.81/1.62/1.60; write 96/112/120/512 = 4.45/4.32/3.38/1.54;
           copy per tensor 16/32/48/56/64/96/256 = 6.89/5.38/2.95/3.55/2.50/1.61/1.45; L2-off read 16/64/128/512 =
           1.24/1.56/1.59/1.61; launch floor ≈ 4.0 µs (1–4 MB); 28/56/64 blocks at 64 MB read = 2.06/3.60/2.79
           time=2026-08-25
OVERTURN:  a 950PR DataCopyPad sweep whose effective bandwidth shows no knee near the L2 capacity,
           or a sub-knee working set sustaining only the HBM rate — either kills the residency model.
```

# 0270 · L2 residency, not HBM peak, sets the effective GM bandwidth below a measured knee

## 1 · Claim
Measured on 950PR (the 9579 SKU, 128 MiB L2) with upstream's own bandwidth instrument: a single streaming
read sustains **3.65–3.99 TB/s** while its working set is 64–112 MB and **1.60 TB/s** once it is 256 MB or
more; the fall begins between **112 and 120 MB** — below the L2 size — and is gradual (2.98 at 120, 2.78 at
128, 2.05 at 144, 1.81 at 192 MB). Write behaves the same way (4.45 TB/s plateau, onset in the same
bracket, 1.54 TB/s beyond). A copy (one read tensor and one write tensor live) begins to fall between
**32 and 48 MB per tensor** and reaches its HBM rate (1.45 TB/s counting both directions) by 128 MB per
tensor. Disabling the L2 hint on both tensors removes the sub-knee plateau entirely (16 MB read: 1.24
instead of 2.26 TB/s; 64 MB: 1.56 instead of 3.65) — the plateau is L2 residency, as upstream says.
Upstream's brackets are wrong on the low side: the single-stream knee is not in (128, 160] MB and the
copy knee is not in [56, 64] MB per tensor; both sit below, because a working set close to the L2 size
already misses. Below ≈ 8 MB the launch floor (≈ 4.0 µs per launch here, not 6.5) dominates and no
bandwidth model applies.

Inference, stated separately: the two-tensor knee at ≈ 40 MB per tensor (≈ 80 MB live) against the
single-stream ≈ 116 MB says the residency threshold is a property of total live bytes plus a margin the
replacement policy eats, not of "L2 capacity ÷ tensors" — the second is what a tiling routine would need
and it is the wrong shape by ~30 %.

## 2 · The wrong branch this removes
The published chip figure is 1.4-1.6 TB/s (0224, and upstream marks it a public-or-experience value).
An agent building a memory roofline uses it, and is wrong by up to 3× in the regime where most
Vector operators live — because a norm, a softmax or an elementwise chain over a few tens of megabytes
is *inside* L2, and it will be served at 2.8-4.5 TB/s.

The direction matters. A denominator that is 3× too small makes the predicted latency 3× too large, so
a well-written kernel reports 30 % of "peak" and the team concludes the memory path is broken. They
then spend the budget on copy restructuring that cannot help, because the kernel was already at the
real ceiling. This is 0206 §2's failure mode — an unverifiable rate producing an unreachable target —
except here the correct rate exists, in a file, measured, and the wrong one is the more prominent
number.

The inverse branch is subtler and is the one upstream's own note guards against. An agent that
discovers the L2 rate and applies it to a large streaming operator predicts a latency the HBM cannot
deliver. Upstream's `hbm_sustained_note` says exactly this — the variant `gm_bandwidth_bytes_per_s`
"is this HBM-sustained value; it is NOT too low" — a sentence written to stop someone raising the
constant to make a large-shape model fit.

The third branch is the copy asymmetry, and it is easy to get wrong even knowing about L2. The
single-stream knee is at the L2 capacity; the *per-tensor* knee for a copy is at half of it, because a
read tensor and a write tensor both occupy L2. An agent that takes 128 MB as "the L2 threshold" and
applies it per tensor in a copy overestimates residency by 2× and predicts L2 rates for a working set
that has already spilled.

## 3 · Ground / Source
`references/hardware/ascend950pr.json`, `common.gm_bandwidth_measured`, with its provenance string
intact — this is the best-documented measurement in this scope and the provenance is the point:

```json
"gm_bandwidth_measured": {
  "source": "membw-bench (pure DataCopyPad GM<->UB, 64 cores, fp32, min over 50 reps) on 950PR_9589, 2026-06-08. See tests/onboard/kernels/membw/",
  "hbm_sustained_read_bytes_per_s": 1500000000000,
  "hbm_sustained_write_bytes_per_s": 1500000000000,
  "hbm_sustained_note": "working set >> L2 (>=256MB): read 1.51, write 1.50 TB/s. The variant peak gm_bandwidth_bytes_per_s (1.4-1.6e12) is this HBM-sustained value; it is NOT too low.",
  "l2_assisted_peak_read_bytes_per_s": 3260000000000,
  "l2_assisted_peak_write_bytes_per_s": 3040000000000,
  "l2_assisted_peak_copy_bytes_per_s": 3670000000000,
  "l2_read_bandwidth_bytes_per_s": 4500000000000,
  "l2_write_bandwidth_bytes_per_s": 4950000000000,
  "l2_residency_knee_bytes": 134217728,
  "fixed_overhead_us_host": 6.5,
  "fixed_overhead_note": "host wall-time floor (<8MB are launch/sync bound, not BW bound)"
}
```

The instrument (`tests/onboard/kernels/membw/`), the part (950PR_9589), the date, the core count, the
dtype and the statistic (min over 50 reps) are all named. `l2_capacity_note` on the same object records
the sweep that located the knee and — unusually — records a correction the authors made and reverted:

> L2 容量模型地基(membw 单流扫描 2026-06-29, 读写对称证实 9589 L2=128MiB): 单流访问量 ≤128MB → L2 裸带宽
> (read ~4.5 / write ~4.95 TB/s, 数据驻 L2 不刷 HBM); 160MB 拐点(read 2.05 / write 1.77)、溢出退 HBM(~1.6)。
> 模型: eff_bw = L2_read/L2_write if 单流访问量 ≤ l2_residency_knee else HBM。copy 等多份并存时有效容量 =
> 128MB/同时份数。

and the same note under `memory_capacity_bytes.l2_source` records the reversal explicitly:

> 9589 L2 = 128MiB (134217728). 上板实测(kernels/membw --mode write, 2026-06-29 ascend950-root-10012):
> 纯写 ≤128MB 满速 ~4.95-4.98 TB/s(L2 速)、160MB 骤降 1.77、≥192MB HBM 1.57 → 写有效 L2 驻留拐点在
> (128,160]MB,9589 L2≥128MB。注:957b variant 记 112MiB,可能是不同 SKU；**曾据'112MB'误改 112,被纯写实测
> 证伪、已回退**。copy(R+W 两份)per-tensor 拐点 ~56-64MB 是占两份所致,与 128MB 单流容量不矛盾。

A recorded wrong turn, its falsifier, and its reversal. That is the evidence culture worth preserving
from this skill, and it is why the knee value carries more weight than the bandwidth headline. Note
also that it reconciles the 957b variant's 112 MiB L2 (which the installed ini confirms — 0218) as a
different SKU rather than as an error, without claiming to have tested it.

The `l2_aware` curve, `common.gm_bandwidth_l2_aware`:

```json
"source": "2026-06-11 ascend950-root-10012 <<<>>> mem_copy sweep (tests/calibration/bench_results/membw_copy_sweep.csv). copy_bw=combined(read+write)有效带宽 vs HBM流量工作集；已含读写争用。",
"note": "curve: 工作集(HBM-streamed bytes)→ 有效 copy 带宽。≤128MB 驻 L2(~2.84TB/s)，≥256MB 落 HBM(~1.45TB/s，取快侧以保证理论是有效下界)，中间线性插值。重复 copy_in 的张量(gm_reread_bytes)按 L2 读、与 HBM 流重叠，不计入。",
"l2_reread_bandwidth_bytes_per_s": 3000000000000.0,
"curve_combined_bytes_to_copy_bps": [[134217728, 2840000000000.0], [268435456, 1450000000000.0]]
```

"取快侧以保证理论是有效下界" — the fast side is chosen deliberately so the model stays a valid lower
bound (0264). A modelling choice with its reason attached.

`SKILL.md:65` names the three selectable bandwidth models and when each applies: `chip_peak` as the
default ceiling roofline, `l2_aware` for one-read-one-write streaming operators like norms, and
`gm_rw_contention` for read-write HBM sharing with α ≈ 0.3 (0271). So the model is not one number and
the *choice* is a documented knob rather than an assumption.

Two figures worth carrying separately. `fixed_overhead_us_host: 6.5` with the note that working sets
under 8 MB are launch- and sync-bound rather than bandwidth-bound — so below 8 MB none of this applies.
And `bandwidth_rampup`: `hbm_rampup_loss_bytes: 838860`, `hbm_rampup_bandwidth_bytes_per_s: 8e11`, with
the note that HBM needs ~1 µs to ramp, transfers under ~0.8 MB run at ~0.8 TB/s, and larger transfers
pay an equivalent +0.8 MB before the steady rate applies.

## 4 · Procedure
Runnable later on `950PR`. Upstream ships the instrument, so the procedure re-derives its sweep
independently rather than inventing one — and then attacks the two places the model is most likely to
be wrong.

Arm A — the single-stream knee. Build and run `tests/onboard/kernels/membw` from source on a named
950PR die, sweeping the working set across the knee: 32, 64, 96, 112, 128, 144, 160, 192, 256, 512 MB,
in `--mode read` and `--mode write` separately. Minimum over 50 repetitions, 64 cores, fp32 — matching
upstream's stated protocol so the comparison is like-for-like. Record effective bandwidth per point.
The **knee position** is the readout; the plateau values are secondary.

Arm B — the copy knee, which tests the halving claim. Repeat Arm A in copy mode (read + write) and
locate the per-tensor knee. Under upstream's reasoning it sits near 56-64 MB, not 128. This arm is what
distinguishes "L2 has a capacity" from "the residency threshold depends on how many tensors are live",
and the second is the claim a tiling routine needs.

Arm C — the model-selection arm, which prices the wrong branch in §2 rather than confirming the right
one. Take one norm-shaped operator (one read, one write) at a sub-knee shape and at a super-knee shape,
and compare measured Task Duration against the roofline computed under each of the three bandwidth
models (`chip_peak`, `l2_aware`, `gm_rw_contention`). Record which model is a bound and which is
violated at each shape. A model that is a bound at both shapes is the only acceptable outcome for the
default.

Arm D — the ramp-up and the host floor, which bound where the whole model applies. Sweep below 8 MB
(0.25, 0.5, 0.8, 2, 4, 8 MB) and record where measured time stops tracking bytes/bandwidth and starts
tracking a constant. Upstream predicts a ~0.8 MB ramp effect and a 6.5 µs host floor; both are
statements about the *inapplicability* of the bandwidth model, and a model whose boundary is unknown
will be applied outside it.

Device selection is explicit: the operator names the device index and the SKU (this claim is
SKU-specific — 9589 has 128 MiB L2 and 957b has 112 MiB, 0218), the harness prints both back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All points of one sweep run on one named die
in one session — a bandwidth curve assembled across dies attributes nothing, and L2 is shared across
cores so a co-tenant would move the knee.

**As run (2026-08-25, job l2_0270 on the 950 machine):** upstream's `membw.asc` was built as one `-xasc`
source (its own `<<<>>>` launch, `aclrtEvent` timing, TQue double-buffer, `DataCopyPad`, 16384-element
tiles) with two changes recorded here: the timed batch is repeated five times (min and median reported)
and a `-DL2OFF` build applies `SetL2CacheHint(CACHE_MODE_DISABLE)` to both GlobalTensors (fixture 2).
Blocks = 56 (this part's AIV count; upstream's default 64 exceeds it and measured lower — 2.79 vs 3.60
TB/s at 64 MB, recorded). Arm A: read and write at 8…512 MB, 100 launches per batch below 96 MB and 20
above (upstream: min over 50). Arm B: copy at 8…256 MB per tensor. Arm D: 1–8 MB read. Fixture 2 at 16 /
64 / 128 / 512 MB, read and copy. NOT run: Arm C (the three-model roofline comparison on a norm-shaped
operator — no such operator is built in this project) and fixture 1 (an L2-contending co-tenant: one die
in the fleet; the "pre-dirtied working set" alternative was not attempted). A 3× copy-512 MB warm-up
preceded the sweep; `npu-smi` reported the AI Core clock at 100 MHz before, after warm-up and after —
the MTE path moved 4 TB/s regardless, so that reading does not describe this kernel's clock domain.

## 5 · Checker — acceptance declared before the run
Verdict variable `knee_bytes`, one per mode (read, write, copy) from Arms A and B — never aggregated,
because the copy knee being at half the single-stream knee is the substantive claim and an average
would erase it.

Pass is declared now as: `knee_bytes[read]` and `knee_bytes[write]` in (128 MB, 160 MB] — upstream's own
bracket, stated as a bracket because its sweep did not resolve it more finely — **and**
`knee_bytes[copy]` in [56 MB, 64 MB]. Both halves in the same predicate.

`plateau_bw[mode, side]` — the effective bandwidth below and above each knee. Pass requires the
sub-knee plateau to exceed the super-knee plateau by at least 2×; the absolute values are reported
with run variance and are not gated, because upstream's figures are its own measurement on a specific
part and reproducing them to ±10 % is a stronger claim than this entry needs.

`model_is_bound[model, shape]` (Arm C) — declared FALSE-on-any-hit per model: false as soon as measured
Task Duration falls below the model's prediction at any shape. A bandwidth model that is exceeded is
not a bound, and the default model must not be exceeded anywhere.

The positive fixture, declared before the run: run Arm A with a co-tenant kernel deliberately streaming
a large working set on another die sharing the same L2 domain, if the topology allows, or failing that
with the sweep's own working set pre-dirtied. `knee_bytes` **must** move downward. If the knee does not
move when L2 is contended, the sweep is not measuring L2 residency at all — it is measuring something
that happens to change at 128 MB — and every knee value it produced is void. A second fixture: run the
sweep with `SetL2CacheHint(CACHE_MODE_DISABLE)` on the copied tensors; the sub-knee plateau must
collapse to the HBM rate. Without these, the checker only reads "bandwidth dropped somewhere around
128 MB", which is the known blind species — a working set crossing L2 capacity and a working set
crossing some other threshold look identical in one curve.

Process exit code is not the verdict for any arm.

## 6 · Evidence
RUN 2026-08-25, 950PR, device idle before and after. TB/s = bytes moved (read + write
for copy) ÷ per-launch time; min and median over 5 batches.

**Arm A — read, 56 blocks:**

| MB | launches per batch | µs min | µs med | TB/s (min time) | TB/s (median) |
|---|---|---|---|---|---|
| 8 | 100 | 6.0 | 6.1 | 1.39 | 1.38 |
| 16 | 100 | 7.4 | 7.5 | 2.26 | 2.22 |
| 32 | 100 | 11.5 | 11.6 | 2.92 | 2.90 |
| 64 | 100 | 18.4 | 18.5 | 3.65 | 3.64 |
| 96 | 20 | 26.7 | 26.9 | 3.77 | 3.75 |
| 112 | 20 | 29.4 | 29.5 | 3.99 | 3.98 |
| 120 | 20 | 42.2 | 42.6 | 2.98 | 2.96 |
| 128 | 20 | 48.2 | 48.4 | 2.78 | 2.77 |
| 136 | 20 | 52.5 | 52.7 | 2.71 | 2.71 |
| 144 | 20 | 73.5 | 74.0 | 2.05 | 2.04 |
| 160 | 20 | 82.1 | 82.5 | 2.04 | 2.03 |
| 192 | 20 | 111.3 | 111.4 | 1.81 | 1.81 |
| 256 | 20 | 165.6 | 165.9 | 1.62 | 1.62 |
| 512 | 20 | 335.7 | 335.9 | 1.60 | 1.60 |

**Arm A — write:**

| MB | launches | µs min | µs med | TB/s min | TB/s med |
|---|---|---|---|---|---|
| 8 | 100 | 2.9 | 2.9 | 2.89 | 2.88 |
| 16 | 100 | 4.7 | 4.7 | 3.60 | 3.57 |
| 32 | 100 | 8.1 | 8.2 | 4.12 | 4.08 |
| 64 | 100 | 15.2 | 15.3 | 4.41 | 4.38 |
| 96 | 20 | 22.6 | 22.7 | 4.45 | 4.43 |
| 112 | 20 | 27.2 | 27.2 | 4.32 | 4.31 |
| 120 | 20 | 37.2 | 37.7 | 3.38 | 3.34 |
| 128 | 20 | 43.5 | 43.5 | 3.09 | 3.08 |
| 136 | 20 | 51.8 | 52.3 | 2.75 | 2.73 |
| 144 | 20 | 59.9 | 60.1 | 2.52 | 2.51 |
| 160 | 20 | 76.3 | 76.4 | 2.20 | 2.19 |
| 192 | 20 | 108.4 | 108.8 | 1.86 | 1.85 |
| 256 | 20 | 173.0 | 173.1 | 1.55 | 1.55 |
| 512 | 20 | 348.6 | 348.9 | 1.54 | 1.54 |

`knee_bytes[read]`, `[write]`: last plateau point 112 MB (3.99 / 4.32), first fallen point 120 MB (2.98 /
3.38) → onset in (112, 120] MB — **outside the declared (128, 160]**. `plateau_bw`: 3.99 → 1.60 (2.5×) and
4.45 → 1.54 (2.9×), ≥ 2× ✓.

**Arm B — copy (MB per tensor, two tensors live):**

| MB per tensor | launches | µs min | µs med | TB/s min | TB/s med |
|---|---|---|---|---|---|
| 8 | 100 | 3.0 | 3.0 | 5.69 | 5.65 |
| 16 | 100 | 4.9 | 4.9 | 6.89 | 6.88 |
| 32 | 100 | 12.5 | 12.5 | 5.38 | 5.35 |
| 48 | 100 | 34.1 | 34.2 | 2.95 | 2.95 |
| 56 | 100 | 33.1 | 33.2 | 3.55 | 3.54 |
| 60 | 100 | 52.9 | 53.0 | 2.38 | 2.38 |
| 64 | 100 | 53.6 | 53.7 | 2.50 | 2.50 |
| 68 | 100 | 54.3 | 54.3 | 2.63 | 2.62 |
| 72 | 100 | 67.1 | 67.2 | 2.25 | 2.25 |
| 80 | 100 | 81.1 | 81.2 | 2.07 | 2.07 |
| 96 | 20 | 124.8 | 125.2 | 1.61 | 1.61 |
| 128 | 20 | 180.1 | 180.5 | 1.49 | 1.49 |
| 256 | 20 | 371.6 | 371.9 | 1.45 | 1.44 |

`knee_bytes[copy]`: last plateau point 32 MB (5.38), first fallen 48 MB (2.95) → onset in (32, 48] MB per
tensor — **outside the declared [56, 64]**; the 48–68 MB stretch is non-monotone (2.95, 3.55, 2.38, 2.50,
2.63), i.e. partially resident.

**Arm D — ramp / launch floor (read):**

| MB | launches | µs min | µs med | TB/s min | TB/s med |
|---|---|---|---|---|---|
| 1 | 200 | 4.0 | 4.0 | 0.26 | 0.26 |
| 2 | 200 | 4.7 | 4.8 | 0.45 | 0.44 |
| 4 | 200 | 4.7 | 4.7 | 0.89 | 0.88 |
| 8 | 200 | 6.1 | 6.2 | 1.39 | 1.36 |

Time is ≈ 4.0–4.7 µs from 1 MB to 4 MB and 6.1 µs at 8 MB: a launch floor near 4.0 µs (upstream: 6.5 µs),
below which bandwidth is not the variable.

**Fixture 2 — `SetL2CacheHint(CACHE_MODE_DISABLE)` on both tensors (TB/s, min time):**

| mode | MB | L2 disabled | L2 enabled (same point) |
|---|---|---|---|
| read | 16 | 1.24 | 2.26 |
| copy | 16 | 1.31 | 6.89 |
| read | 64 | 1.55 | 3.65 |
| copy | 64 | 1.40 | 2.50 |
| read | 128 | 1.59 | 2.78 |
| copy | 128 | 1.45 | 1.49 |
| read | 512 | 1.61 | 1.60 |
| copy | 512 | 1.50 | — |

The sub-knee plateau collapses to the super-knee rate (read 16 MB: 2.26 → 1.24; 64 MB: 3.65 → 1.56) while
the 512 MB points are unchanged (1.60 vs 1.61) — the knee measures L2 residency. Fixture 1 not run.

**Blocks sensitivity (read 64 MB):**

| blocks | TB/s |
|---|---|
| 28 | 2.06 |
| 56 | 3.60 |
| 64 | 2.79 |

## 7 · Scope limits — what this entry does NOT establish
One SKU (950PR_9579, 128 MiB L2); the 112 MiB (957b) and 16 MiB (`Ascend950PR_950z.ini`) SKUs are not
measured and their knees will differ. One instrument shape (upstream's membw: 56 blocks, 16384-element
tiles, TQue depth 2, fp32); a different tile or block count moves the plateaus (64 blocks: 2.79 vs 3.60
TB/s at 64 MB). Arm C — which bandwidth model is a bound at sub- and super-knee shapes — is not run, so
the default-model recommendation in §2 is priced only by the plateau ratio. Fixture 1 (contended L2) not
run; fixture 2 carries the residency attribution alone. The "knee" is reported as an onset bracket
(last plateau point, first fallen point); a fitted midpoint would land 10–20 MB higher, inside upstream's
bracket for the single stream — the disagreement with upstream is about where residency STARTS to fail,
which is what a tiling routine needs. The AI Core clock reading (100 MHz) did not describe this kernel;
absolute figures are per-launch event times on an idle device. 950DT untouched.
