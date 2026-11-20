```
ID:        0489-the-vgather-stride-penalty-scales-with-the-power-of-two-in-the-byte-stride-and-the-bank-conflict-counter-stays-at-zero
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 950PR 2026-08-25 (msprof `aiv_total_time`, five launches per point,
           `aiv_vec_bank_cflt_ratio` beside every point), via §5's declared tiers: outcome **`neither`**
           (half alone reads `16-only`, float alone reads `pow2-only`; the predicate that fits both is
           the 2-adic part of the byte stride × lane count), `counter_registers` = false at every
           severe point, positive fixtures severe (5.37× half at 64 B, 5.98× float at 128 B), negative
           fixtures none (S = 33 both widths), linearity 1.003 / 0.864, `offset_relief` 32 B =
           relieved (0.500) / 256 B = none (1.000), `time_period` = 4 rows = 128 B. §6 has the tables.
           Previously harvested (drafted from the bring-up fixture, §5 declared before this sweep).
BOARD:     950PR (measured 2026-08-25); 950DT unverified
SOURCE:    ops/ascendc-performance-best-practices/reference/scan/templates/cum_lane_parallel_scan.md:82-83
           — "段长 `S` 同时就是 lane 间的 UB 地址步长。**步长取 2 的幂时 VLC 条 lane 的 gather 全撞在
           同一批 bank 上**，实测 `R=4096` bf16（S=32）比错位版本慢 5.5 倍（160 µs → 887 µs）。"
SOURCE:    same shelf, guide.md:187 — "**取 2 的幂会撞 bank，实测慢 5.5 倍**" ; guide.md:270 — "段长即
           lane 间步长，**取 2 的幂撞 bank 慢 5.5 倍**"   # same repo — ONE origin (RULES.md Art. 3)
SOURCE:    same shelf, common/ub_resident_design.md:79-83 (via 950:0317) — the bank conflict is to be
           confirmed by "msProf 资源冲突占比" — the counter this entry's §5 reads beside every time.
INDEX:     means=regbase `Reg::DataCopyGather` over VLC lanes (128 half / 64 float), element-index
           register from a host table, 32 gathers × 1024 iterations, exact per-lane min==max==mirror;
           msprof `--aic-metrics=ResourceConflictRatio`, `ai_core_metrics` rows (5 per point)
           conditions=CANN 9.1.0, `-xasc --npu-arch=dav-3510`, 950PR, steps 32,
           iters 1024, controls = odd multiples of sizeof(C); floors 5 % (max spread 1.6 % / 1.8 %)
           readouts: half control 236.96 µs; 16·odd 319.0 (1.35×), 32·odd 636.9 (2.69×), 64·odd
           1272.6 (5.37×), 128·k 2544.0 (10.74×) — float control 212.88 µs; 16·odd 242.4 (1.14×),
           32·odd 320.0 (1.50×), 64·odd 636.8 (2.99×), 128·k 1272.5 (5.98×); `bank_cflt` max
           0.00063 everywhere; pair +32 B 0.500 / +256 B 1.000; k-sweep period 4.
           time=2026-08-25
OVERTURN:  a repeat of §4 on a named 950 board in which two strides with the same 2-adic part at the
           same lane count differ in penalty by more than the floor (64 B against 192, 320 or 448 B;
           32 B against 96 or 160 B), or in which a multiple of 128 B pays less than a 64·odd stride,
           or in which an odd-multiple stride leaves the floor — any of these kills the four-class
           law in §1; or one in which `aiv_vec_bank_cflt_ratio` rises by ≥ 5 percentage points at the
           severe strides — that kills the counter half of the title and hands the verdict back to
           0483's §5 as written.
```

# 0489 · The vgather stride penalty scales with the power of two in the byte stride, and the bank-conflict counter stays at zero

## 1 · Claim
Measured on 950PR: the penalty a lane-parallel `DataCopyGather` pays for its inter-lane byte stride is
a function of **the largest power of two dividing the stride** and of the lane count, and of nothing
else in the stride. At 128 half lanes: strides 16·odd pay 1.35×, 32·odd 2.69×, 64·odd 5.37×, and every
multiple of 128 pays 10.74×, against the odd-stride floor; at 64 float lanes the same classes pay
1.14×, 1.50×, 2.99× and 5.98×. Neither of upstream's two predicates describes this: "a power of two"
fails because 192, 320 and 448 B pay exactly what 64 B pays; "a multiple of 16 bytes" is the right
trigger but names one tier where there are four, and its smallest tier is 1.14× at 64 lanes. The
declared §5 outcome is `neither`. Upstream's 5.5× is the 64-B tier at 128 lanes, reproduced at 5.37×
with upstream's own fixture (bf16-width elements, S = 32). The msprof bank-conflict counter
`aiv_vec_bank_cflt_ratio` read between 0.0001 and 0.0006 at every point, slow or fast.

Inference, stated separately: the times equal 19.9 µs × (lanes whose addresses are congruent modulo
128 B) at this iteration count, down to a floor of ~237 µs (half) / ~213 µs (float) — consistent with
a 128-byte address alias period on which congruent lanes serialise; 0314's quoted 32-B-row-over-16-
banks mapping would give a 512-byte period and is not what was measured. Which physical structure the
128-byte period is (16 banks × 8 B, or finer) is not established here (§7).

## 2 · The wrong branch this removes
Without this entry an agent that has read 0483 knows the two predicates disagree and has no way to
pick; an agent that has read 0317 reaches for the conflict counter to pick; and if the counter does
not see the phenomenon, that agent concludes "no bank conflict here" and leaves a 6× penalty in the
kernel. The normal checks do not catch it because every stride is correct — this is a pure time
effect — and because the counter-based protocol is upstream's own recommendation, so following it
looks like diligence. The wrong branch is therefore double: implementing the wrong predicate (over-
or under-perturbing `S`), and trusting a counter to arbitrate a phenomenon it may not measure. If §5's
`counter_registers` comes back false while `penalty` is large, 0317's protocol has a named hole on
this part and this entry is where it is written down.

## 3 · Ground / Source
The upstream passages are quoted in full in 950:0483 §3 and are not repeated. What this entry adds is
the instrument choice, which is the whole ground: upstream's template performs the gather with
`AscendC::Reg::DataCopyGather(xReg, vp, (RegTensor<G>&)gIdx, full)` over `VLC = 256 / sizeof(C)`
lanes with an element-index register (`cum_lane_parallel_scan.template:184-203`), so the sweep uses
exactly that primitive, that lane count and that index form — a SIMT per-thread gather is a different
access path and is run beside it only as a second instrument, never as the verdict's instrument.

Assumptions and how each is checked: (a) the gather reads the addresses the index register names —
checked by an exact per-lane sum against a host mirror, with the per-iteration MIN and MAX of the
sums both required to equal the mirror so every iteration of every lane is covered; (b) the compiler
does not hoist the repeated gathers — each iteration rotates its start index so no two consecutive
iterations issue the same sequence, and the time scales linearly with the iteration count (checked
at 64/256/1024); (c) `VLC` is not assumed — `GetVecLen()` is echoed from the device and `VLC` is
derived from it; (d) the counter columns exist and are read for every point — the run refuses a
point without them.

## 4 · Procedure
Runnable on `950PR` (and separately on `950DT`, not available in this phase). One 950PR, bus
the bound 950PR card, on the 950 machine; occupancy sampled before and after every job (`npu-smi info`),
no die substitution. Build: `bisheng -xasc --npu-arch=dav-3510 -O2 -std=c++17` against the installed
CANN 9.1.0, `-lascendcl -lruntime`; direct launch through `<<<>>>`.

Instrument (regbase, upstream's primitive): a `__VEC_SCOPE__` kernel that loads a host-built
element-index table into a `RegTensor<I>` (`int16_t` for half, `int32_t` for float — the width
upstream's `GatherIdxBySize` pairs with the data width), then for `iters = 1024` iterations performs
`steps = 32` gathers `DataCopyGather(x, vp, (RegTensor<G>&)gIdx, full)` with `Adds(gIdx, gIdx, 1)`
between them, accumulating with `Add`, rotating the start index by `iters mod steps`, and folding the
iteration sum into running `Min` and `Max` registers; the two are stored and compared on the host
against the mirror sum, lane by lane. The payload is a period-7 table of small integers so every sum
is exact in both widths. Index table for lane `l`: `l·S` (plain stride) or `(l>>1)·S + (l&1)·P`
(pair mode, Arm 3).

Arm 1 — stride set, per element width, `steps = 32`, `iters = 1024`:
- half (VLC 128): byte strides 32/64/128/256 (S = 16/32/64/128), 48/80/112/144 (S = 24/40/56/72),
  odd multiples of 2: 34/66/130 (S = 17/33/65), controls 18/40/72/100 (S = 9/20/36/50);
- float (VLC 64): 32/64/128/256 (S = 8/16/32/64), 48/80/112/144 (S = 12/20/28/36), odd multiples of
  4: 20/28/36/44 (S = 5/7/9/11), controls 24/40/72/100/132 (S = 6/10/18/25/33).
Arm 1′ — the 0314 Arm A′ row sweep, half: byte stride 32·k for k = 1..17, 24, 32.
Arm 3 — pairs, base stride 512 B: pair offset none / 256 B / 32 B, both widths.
Arm 2 — `steps = S` for S = 4, 5 (half) and 8, 9, 10 (float) at 8192 / 4096 iterations: the cost of
the remedy's padded length at strides the rule leaves alone.

Readout, every point: `msprof --ai-core=on --aic-mode=task-based --aic-metrics=ResourceConflictRatio`
around one process that launches the kernel 5 times; from `ai_core_op_summary.db` /
`ai_core_metrics`, all five rows: `aiv_total_time` (min, median, max) and `aiv_vec_bank_cflt_ratio`
(max), plus `aiv_vec_resc_cflt_ratio` for the record. The host also prints S, sizeof(C), byte stride,
echoed `GetVecLen()`, derived VLC, span, padded length VLC·S, iters, steps.

Refuses to assume: that slow means conflicted (the counter is read at every point and reported beside
the time — and if it stays flat, that is the finding, not a reason to drop it); that the SIMT form
measures the same thing (it is reported separately and never decides); that a host-timed number is a
device time (host timings from the bring-up are calibration only; §5 reads `aiv_total_time`); that
`VLC` is 64 or 128 by convention (echoed); that the padded-length cost is separable from the stride
cost by a single timing (Arm 2 holds the stride class fixed and varies only the step count).

**Bring-up disclosure (before §5 was written, 2026-08-25):** the fixture points S = 32 / 33 at both
widths and a host-timed float stride set were run to check the instrument; the fixture reproduced
upstream's ratio (5.34× half, 5.96× float) and `aiv_vec_bank_cflt_ratio` stayed below 0.1 % on every
row. The margins in §5 were chosen knowing those six device-time points and the host-timed float set;
no half-width device-time sweep, no Arm 1′ curve and no Arm 3 device times existed when §5 was
declared. Two instrument defects were found and fixed at bring-up (an fp16 result decoder that could
only decode the seven payload values; an iteration-count-1 anomaly under diagnosis) — both in
harvest/RUNS_20260824.md.

**As run (2026-08-25, geo2 h / geo2 f with the verification run):** exactly the arms above, one
msprof invocation per point wrapping one process that launches the kernel five times (five
`ai_core_metrics` rows per point; median/min/max reported). Deviations from the text above, all
recorded before the tiers were read: (i) the Arm 1 and Arm 1′ half sets overlap at 32/64/128/256 B and
were run twice — both medians reported, the lower used, differences ≤ 0.4 µs; (ii) float gained two
saturation points (512 B, 1024 B) and lacked the 192/320/448-B non-power-of-two multiples of 64 that
decided P-pow2 in half — float's P-pow2 reading is therefore weaker than half's and the combined
outcome rests on both widths as §5 requires; (iii) the linearity guard (6) was run at half only, as
declared; (iv) Arm 2's per-iteration time is ≈ 277 ns (half, S = 4/5) and ≈ 243 ns (float, S =
8/9/10) regardless of S, and the odd-stride floor at 32 steps is ≈ 232 ns per iteration — so the floor
is dominated by per-iteration work, not by the gathers, and this instrument bounds the per-gather cost
from above only (separation arm queued, geo3 c); (v) the SIMT form ran beside at six half strides and
is reported in §6, never classified.

## 5 · Checker — acceptance declared before the run
Floor first: `floor` = the larger of 5 % and the largest (max − min)/median of `aiv_total_time` over
the control points' five launches. `control` = median `aiv_total_time` over the odd-multiple strides
(34/66/130 B half; 20/28/36/44 B float), per width.

`penalty(stride)` = median `aiv_total_time` / `control`, per width. Tiers, declared now:
`severe` ≥ 4.0; `moderate` ∈ [1.3, 4.0); `mild` ∈ (1 + floor, 1.3); `none` ≤ 1 + floor.

The two upstream predicates, decided from Arm 1 and named both ways:
- **P-pow2 holds** iff every power-of-two stride ≥ 64 B is `severe` or `moderate` in both widths, and
  no stride that is not a power of two is above `moderate`.
- **P-16 holds** iff every multiple of 16 B in the set is at least `moderate` in both widths.
Outcomes: `pow2-only`, `16-only`, `both`, `neither` — each is a legitimate result and none is
preferred. A `mild` tier at 48/80/112/144 with `severe` at 128/256 is `pow2-only` with a disclosed
second-order effect, and is reported as exactly that, not as "16-byte rule confirmed".

`counter_registers` = true iff max `aiv_vec_bank_cflt_ratio` at any `severe` point exceeds the
control's by ≥ 5 percentage points. Declared both ways: true hands the arbitration back to 0483's §5
(counter-based) and this entry's title is wrong; false means the counter does not see this phenomenon
on this part and 0317's protocol carries a named hole.

`offset_relief(P_B)` (Arm 3, base 512 B): median(pair offset P_B) / median(no offset). `relieved`
iff ≤ 0.6; `none` iff within floor of 1.0; anything between is reported as `partial` with the number.

`time_period` (Arm 1′): the smallest k > 0 such that `penalty(32·(k+j))` equals `penalty(32·j)`
within floor for every j with both points in the set; named outcomes 4, 8, 16 (the ini bank count),
`none`. This is 0314's `bank_period` measured by time rather than by its counter, and is reported to
0314 as such — it does not fire 0314's §5, which is counter-defined.

Guards. (1) Positive fixture: S = 32 half (64 B) and S = 32 float (128 B) must both be `severe`
(the bring-up saw 5.34× and 5.96×); if either is not, the sweep does not reproduce the phenomenon
and every tier in it is void. (2) Negative fixture: S = 33 at both widths must be `none`; if it is
not, the control is contaminated and the run is void. (3) Correctness: a point whose per-lane
min/max/mirror check fails is discarded and named — a stride that reads out of its window would
produce a beautiful curve made of the wrong addresses. (4) Completeness: a point without all five
counter rows is not classified. (5) The exit code is not the verdict. (6) Linearity: at S = 32 and
33, half, device time at 256 iterations must be within 15 % of one quarter of the 1024-iteration
time, else the compiler is not issuing the gathers the source names and the penalty is
unattributable.

## 6 · Evidence
RUN 2026-08-25, 950PR (Ascend950PR, CANN 9.1.0, `bisheng -xasc --npu-arch=dav-3510
-O2`), device idle before and after (npu-smi: 0 % util, no other process, HBM baseline ≈ 5.4 GB).
Every point: correctness green (per-lane min == max == mirror), `GetVecLen()` echoed 256, five
`ai_core_metrics` rows.

**Half (VLC = 128), steps 32, iters 1024.** Control = median over 18/34/66/130 B = **236.96 µs**;
max spread over the control launches 1.6 %; floor 5 %.

| byte stride | S | 2-adic part | lanes per 128-B residue | `aiv_total_time` med (min–max) µs | penalty | tier | `bank_cflt` max | `resc_cflt` max |
|---|---|---|---|---|---|---|---|---|
| 18 | 9 | 2^1 | 2 | 236.9 (236.8–240.2) | 1.00× | none | 0.00034 | 0.564 |
| 32 | 16 | 2^5 | 32 | 636.9 (636.8–640.2) | 2.69× | moderate | 0.00060 | 0.209 |
| 34 | 17 | 2^1 | 2 | 237.0 (236.8–240.0) | 1.00× | none | 0.00034 | 0.564 |
| 40 | 20 | 2^3 | 8 | 237.0 (236.8–240.2) | 1.00× | none | 0.00034 | 0.564 |
| 48 | 24 | 2^4 | 16 | 319.0 (319.0–322.1) | 1.35× | moderate | 0.00057 | 0.418 |
| 64 | 32 | 2^6 | 64 | 1272.6 (1272.5–1276.0) | 5.37× | severe | 0.00062 | 0.104 |
| 66 | 33 | 2^1 | 2 | 236.9 (236.8–240.2) | 1.00× | none | 0.00034 | 0.564 |
| 72 | 36 | 2^3 | 8 | 236.9 (236.8–240.3) | 1.00× | none | 0.00034 | 0.564 |
| 80 | 40 | 2^4 | 16 | 319.0 (318.9–322.1) | 1.35× | moderate | 0.00057 | 0.418 |
| 96 | 48 | 2^5 | 32 | 636.9 (636.8–640.2) | 2.69× | moderate | 0.00060 | 0.209 |
| 100 | 50 | 2^2 | 4 | 237.0 (236.8–240.7) | 1.00× | none | 0.00034 | 0.564 |
| 112 | 56 | 2^4 | 16 | 319.0 (319.0–322.4) | 1.35× | moderate | 0.00057 | 0.418 |
| 128 | 64 | 2^7 | 128 | 2544.0 (2544.0–2547.5) | 10.74× | severe | 0.00063 | 0.052 |
| 130 | 65 | 2^1 | 2 | 237.0 (236.9–240.6) | 1.00× | none | 0.00034 | 0.564 |
| 144 | 72 | 2^4 | 16 | 319.0 (319.0–322.4) | 1.35× | moderate | 0.00057 | 0.418 |
| 160 | 80 | 2^5 | 32 | 636.8 (636.8–640.1) | 2.69× | moderate | 0.00060 | 0.209 |
| 192 | 96 | 2^6 | 64 | 1272.6 (1272.5–1276.4) | 5.37× | severe | 0.00062 | 0.104 |
| 224 | 112 | 2^5 | 32 | 636.9 (636.9–640.4) | 2.69× | moderate | 0.00060 | 0.209 |
| 256 | 128 | 2^8 | 128 | 2544.0 (2543.9–2547.8) | 10.74× | severe | 0.00063 | 0.052 |
| 288 | 144 | 2^5 | 32 | 636.8 (636.7–641.1) | 2.69× | moderate | 0.00060 | 0.209 |
| 320 | 160 | 2^6 | 64 | 1272.8 (1272.7–1276.8) | 5.37× | severe | 0.00062 | 0.104 |
| 352 | 176 | 2^5 | 32 | 636.9 (636.9–641.2) | 2.69× | moderate | 0.00060 | 0.209 |
| 384 | 192 | 2^7 | 128 | 2544.1 (2544.0–2548.4) | 10.74× | severe | 0.00063 | 0.052 |
| 416 | 208 | 2^5 | 32 | 637.0 (636.9–641.5) | 2.69× | moderate | 0.00060 | 0.209 |
| 448 | 224 | 2^6 | 64 | 1272.8 (1272.8–1277.0) | 5.37× | severe | 0.00062 | 0.104 |
| 480 | 240 | 2^5 | 32 | 637.0 (636.9–641.8) | 2.69× | moderate | 0.00060 | 0.209 |
| 512 | 256 | 2^9 | 128 | 2544.1 (2544.0–2548.3) | 10.74× | severe | 0.00063 | 0.052 |
| 544 | 272 | 2^5 | 32 | 637.0 (637.0–641.8) | 2.69× | moderate | 0.00060 | 0.209 |
| 768 | 384 | 2^8 | 128 | 2544.2 (2544.1–2549.6) | 10.74× | severe | 0.00063 | 0.052 |
| 1024 | 512 | 2^10 | 128 | 2544.6 (2544.4–2550.2) | 10.74× | severe | 0.00063 | 0.052 |

Arm 1′ read as k = stride/32: penalties 2.69 (k odd) / 5.37 (k ≡ 2 mod 4) / 10.74 (k ≡ 0 mod 4) for
every k in 1..17, 24, 32 → **`time_period` = 4**. Half alone: P-16 true (every multiple of 16 ≥
1.35× — above the 1.3 tier boundary by 0.05, with launch spread ≤ 1 %), P-pow2 false (192, 320, 448 B
severe) → `16-only`.

**Float (VLC = 64), steps 32, iters 1024.** Control = median over 20/28/36/44/100/132 B = **212.88 µs**;
max spread 1.8 %; floor 5 %.

| byte stride | S | 2-adic part | lanes per 128-B residue | `aiv_total_time` med (min–max) µs | penalty | tier | `bank_cflt` max | `resc_cflt` max |
|---|---|---|---|---|---|---|---|---|
| 20 | 5 | 2^2 | 2 | 212.8 (212.8–216.2) | 1.00× | none | 0.00013 | 0.630 |
| 24 | 6 | 2^3 | 4 | 212.8 (212.8–215.8) | 1.00× | none | 0.00013 | 0.630 |
| 28 | 7 | 2^2 | 2 | 212.9 (212.8–216.0) | 1.00× | none | 0.00013 | 0.630 |
| 32 | 8 | 2^5 | 16 | 320.0 (319.8–323.6) | 1.50× | moderate | 0.00054 | 0.419 |
| 36 | 9 | 2^2 | 2 | 212.8 (212.8–216.6) | 1.00× | none | 0.00013 | 0.630 |
| 40 | 10 | 2^3 | 4 | 212.9 (212.8–216.0) | 1.00× | none | 0.00013 | 0.630 |
| 44 | 11 | 2^2 | 2 | 212.9 (212.8–216.0) | 1.00× | none | 0.00013 | 0.630 |
| 48 | 12 | 2^4 | 8 | 242.4 (242.4–245.6) | 1.14× | mild | 0.00031 | 0.553 |
| 64 | 16 | 2^6 | 32 | 636.8 (636.8–640.2) | 2.99× | moderate | 0.00057 | 0.210 |
| 72 | 18 | 2^3 | 4 | 212.8 (212.8–215.8) | 1.00× | none | 0.00013 | 0.630 |
| 80 | 20 | 2^4 | 8 | 242.4 (242.4–246.1) | 1.14× | mild | 0.00031 | 0.553 |
| 100 | 25 | 2^2 | 2 | 212.9 (212.9–216.4) | 1.00× | none | 0.00013 | 0.630 |
| 112 | 28 | 2^4 | 8 | 242.4 (242.4–246.0) | 1.14× | mild | 0.00031 | 0.553 |
| 128 | 32 | 2^7 | 64 | 1272.5 (1272.4–1276.0) | 5.98× | severe | 0.00059 | 0.105 |
| 132 | 33 | 2^2 | 2 | 212.9 (212.8–216.4) | 1.00× | none | 0.00013 | 0.630 |
| 144 | 36 | 2^4 | 8 | 242.5 (242.4–246.3) | 1.14× | mild | 0.00031 | 0.553 |
| 256 | 64 | 2^8 | 64 | 1272.6 (1272.5–1275.7) | 5.98× | severe | 0.00059 | 0.105 |
| 512 | 128 | 2^9 | 64 | 1272.6 (1272.6–1276.5) | 5.98× | severe | 0.00059 | 0.105 |
| 1024 | 256 | 2^10 | 64 | 1272.9 (1272.8–1277.4) | 5.98× | severe | 0.00059 | 0.105 |

Float alone: P-pow2 true, P-16 false (48/80/112/144 B are `mild`) → `pow2-only`. **Both widths, as §5
requires: `neither`.** The one description that fits all 49 classified points: penalty tier =
2-adic part of the stride (capped at 128 B) × lane count / 128, and the medians are 19.9 µs per lane
in that class (16 → 319, 32 → 637, 64 → 1272, 128 → 2544 µs; the 8-lane class sits at the floor in
half and at 242 µs in float).

`counter_registers` = **false**: max `aiv_vec_bank_cflt_ratio` at any severe point 0.00063 against a
control maximum 0.00034 (half) / 0.00013 (float) — a rise of 0.03 percentage points where §5 demanded
5. `aiv_vec_resc_cflt_ratio` falls as time rises (0.630 → 0.052) with a constant numerator, the
fixed-overhead artifact already recorded for 0314's classic-vector run.

**Guards.** Positive fixtures: 64 B half severe (5.37×), 128 B float severe (5.98×). Negative
fixtures: 66 B half 1.00×, 132 B float 1.00× — none. Linearity (half): S = 32, 256 iters 318.9 µs vs
1272.6/4 = 318.2 → 1.003; S = 33, 51.2 µs vs 236.9/4 = 59.2 → 0.864 (within 0.85–1.15; the shortfall is
the fixed per-launch cost). Completeness: 5 rows at every point. Correctness: green at every point.

**Arm 3 (base stride 512 B, pairs).** Half: no offset 2543.8 µs; +256 B 2543.8 (ratio 1.000, `none`);
+32 B 1272.7 (0.500, `relieved`). Float: 1272.6 / 1272.5 (1.000, `none`) / 636.9 (0.500, `relieved`).
A 256-B offset is ≡ 0 modulo the 128-B period and moves no lane off its class; a 32-B offset splits
every class in two.

**Arm 2 (steps = S, the remedy's padded length at small strides).** Half S = 4 → 5 at 8192 iters:
2269.2 → 2269.3 µs (277.0 ns per iteration, unchanged); float S = 8 → 9 → 10 at 4096 iters: 995.9 →
997.5 → 999.0 µs (243.1 → 243.9 ns). At these strides an extra step costs nothing measurable per
iteration in this instrument; see §4 (iv) for why absolute per-gather cost is not separable here.

**SIMT-VF form beside (128 threads, never deciding), half:** 66 B 1469.8 µs (control), 48 B 1.02×,
80 B 1.02×, 64 B 1.18×, 128 B 1.75×, 256 B 1.75×; both counters exactly 0 at every SIMT point. Same
ordering as the regbase form, one sixth of the top penalty.

**Post-verdict discriminators (geo3, 2026-08-25, same instrument and readout; run AFTER the tiers
above were read, so reported and not adjudicated — no §5 variable is defined on them).**
- Pair offsets at base 512 B, half: +8 B 1272.7 µs, +16 B 1272.9, +32 B 1272.6, +64 B 1272.6 (all
  0.500 of no-offset), +128 B 2543.9, +256 B 2544.2 (1.000). Float: +8/16/32/64 B 636.8–636.9 (0.500);
  +128/+256 B 1272.4–1272.5 (1.000). The class a lane pays for is its address modulo 128 B at a
  granularity of 8 B or finer; an offset of 64 B relieves as fully as 8 B.
- Odd multiples of 8 B, half (24/56/88/120 B): 236.93–236.99 µs — the floor; 16 B: 318.9 (the 16-lane
  class); 8 B: 236.9 (floor); 4 B: 215.0 — below the floor. Float: 8 B 212.85 (floor), 16 B 242.4 (the
  8-lane class), 24/56/88/120 B 212.84–212.89 (floor).
- Steps/iteration split at constant 32 768 gathers, half: 66 B (8 steps × 4096) 988.6 µs, (32 × 1024)
  236.95, (128 × 256) 162.4 — the floor is per-iteration work and the per-gather cost at an odd stride
  is below 162.4/32768 = 5.0 ns; 64 B under the same three splits 1272.41 / 1272.42 / 1272.25 — the
  penalty is per-gather and independent of the split: 38.8 ns per gather at 64 congruent lanes,
  77.6 ns at 128, 19.4 ns at 32, 9.7 ns at 16 → **0.607 ns per congruent lane per gather, linear through
  zero**. Inference, conditional: at the part's rated 1650 MHz that is one cycle per congruent lane;
  the clock was not sampled during these runs (§7).
- Float 512 B and 1024 B: 1272.6 / 1272.7 — saturated at 64 lanes, as in the main table.

Bring-up (host-timed and six msprof points, 2026-08-25 earlier the same day) is in
harvest/RUNS_20260824.md and agrees with every device number above to within 2 %.

## 7 · Scope limits — what this entry does NOT establish
One board (950PR), one CANN pin (9.1.0), one primitive (`DataCopyGather`; `DataCopyScatter` untested),
one lane count per width (the full VLC — a masked, shorter gather is untested), one step count (32)
and iteration count (1024, plus the linearity points). 950DT untouched. The SIMT form is reported, not
classified, and its 0/0 counters say only that SIMT UB loads do not feed these two ratios. **The
mechanism is not named**: a 128-byte alias period with penalty linear in congruent lanes is what was
measured; whether that is 16 banks × 8-B interleave, a finer structure, or a gather-unit address
coalescer is not established — the vendor's own bank-conflict counter did not move, so calling it a
"bank conflict" is upstream's word, retained in the title only as the counter's name. The absolute
per-gather cost at the floor is bounded from above only (§4 iv, < 5 ns); the per-congruent-lane cost
(0.607 ns) is a slope, and its reading as "one cycle" assumes the 1650 MHz rating — `curFreq` was not
sampled during the sweep; the 47 processes' floors agree within 0.1 % (236.8–237.0 µs), which shows a
stable clock, not its value. Upstream's absolute 160 µs → 887 µs is not
reproduced as a number, only as a ratio, and upstream's `R = 511` 15 % counter-example is not
reproduced (Arm 2 measured the padded-length cost at small strides, not upstream's shape). The
`mild`/`moderate` boundary at 1.3 sat 0.05 above the half 16·odd tier and 0.16 above the float one;
the tiers are the declared instrument, the four-class 2-adic law is the finding.
