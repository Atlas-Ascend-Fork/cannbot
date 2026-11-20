```
ID:        0077-l2-on-the-measured-910b2-is-192-mb-by-knee-ini-and-interface-and-the-32-mb-figure-is-the-previous-generations
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — born from 0007's §5 overturn mechanism 2026-08-24: the surviving number
           becomes its own entry, BOARD naming the part actually run. Three arms agree; readouts
           in §6.
BOARD:     910B2
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:132 — "| DAV_2201 | Ascend910B2 | 24 |
           48 | 1.8 GHz | 192 MB | 64 GB |" (the statement the run upheld)
SOURCE:    verification machine, CANN `Version=9.1.0` `timestamp=20260730_231653901`
           (aarch64-linux): `platform_config/Ascend910B{1,2,2C,3}.ini` carry `l2_size=201326592`;
           `Ascend910B4.ini` 100663296, `Ascend910B4-1.ini` 176160768; `Ascend910B.ini`
           (`NpuArch=1001`, previous generation) carries `l2_size=33554432` — the 32 MB.
INDEX:     910B2, NPU 0, bus 0000:C1:00.0, AIC 24, rated 1800 MHz (hit-rate metric; curFreq
           800 MHz idle pre and post), HBM 65536 MB/die, CANN 9.1.0 ts 20260730_231653901,
           driver 25.5.1, 2026-08-24.
           Re-derive interface: GetCoreMemSize(CoreMemType::L2) with GetCurNpuArch() in one
           process → 201326592, arch 2201.
           Re-derive ini: grep -h '^l2_size=' <toolkit>/aarch64-linux/data/platform_config/Ascend910B*.ini
           Re-derive knee: single-source dav-c220-vec kernel, 4 passes of 64 KB-chunk streaming
           reads over an S-byte GM buffer, S ∈ {8..256} MB, profiled with
           --ai-core=on --aic-mode=task-based --aic-metrics=L2Cache; warm-pass hit rate =
           (aiv_r0+aiv_r1 read_cache_hit) / (3·S/128).
OVERTURN:  on this part and pin: a repeat of the §4 sweep whose 100 %-hit plateau ends at or
           below 128 MB or extends to 224 MB or beyond, GetCoreMemSize(L2) returning anything
           other than 201326592, or a 2201 platform_config ini for this SKU carrying a different
           l2_size. On other SKUs (910B4's inis already differ) a diverging result narrows
           scope, it does not overturn.
```

# 0077 · L2 on the measured 910B2 is 192 MB — by knee, ini, and interface — and the 32 MB figure is the previous generation's

## 1 · Claim
On the measured Ascend910B2 under CANN 9.1.0, L2 capacity is 192 MB by all three arms run:
`GetCoreMemSize(L2)` returns 201326592; every 2201 ini for B1/B2/B2C/B3 carries
`l2_size=201326592`; and a behavioural streaming-reuse sweep holds a 100.00 % warm-pass hit rate
through 160 MB and collapses to 0.00 % by 256 MB — a knee inside 192 MB ± 25 % and decisively
outside 32 MB ± 25 %. The 32 MB that upstream's metrics table put in the 910B1/B2 column is the
PREVIOUS generation's value: it sits, verbatim, in the installed `Ascend910B.ini` with
`NpuArch=1001`.

## 2 · The wrong branch this removes
The branch 0007 §2 described, now with a verdict: an agent gating an L2-residency decision on the
32 MB figure declines cache-resident schedules for working sets that fit six times over. The
64 MB working set 0007 used as its example is comfortably resident — measured, not assumed: at
64 MB the warm-pass hit rate is 100.00 %. And the error's mechanism is now legible: the wrong
number is not noise, it is the previous generation's spec surviving in a later table — the exact
species an agent "cross-checking" two documents of the same vintage cannot catch.

## 3 · Ground / Source
Inherited from 0007 §3 (both upstream statements, their locations, and the provenance lead).
The lead is now confirmed by the installed ini set: 33554432 lives in the NpuArch=1001 file.
Registered contradiction C-001 — resolved for this part by this run.

## 4 · Procedure
As run 2026-08-24 (this entry is born from the run; 0007 §4 is the design it instantiated):
1. Die named: NPU 0, bus 0000:C1:00.0; full npu-smi table recorded before and after (all 8 dies
   AICore 0 %); no substitution.
2. INI arm: every `Ascend910B*.ini` l2_size enumerated (values in SOURCE).
3. Runtime arm: GetCoreMemSize(L2) + GetCurNpuArch in one process.
4. Behavioural arm: 4-pass streaming read (64 KB chunks, one AIV core) over S ∈
   {8, 16, 32, 64, 128, 160, 192, 224, 256} MB, 3 repeats per size, hit counts from the
   profiler's aiv_r0/r1_read_cache_hit columns (this msprof's equivalent of L2Cache.csv);
   warm-pass hit rate computed against 3·S/128 lines.

## 5 · Checker — inherited from 0007 §5, declared before that run
`l2_knee_bytes` within ±25 % of exactly one of {32 MB, 192 MB}: met (knee localised to
(160, 256) MB; 100 % plateau through 160 MB rules out every value below it, including 32 MB).
`l2_ini_bytes` reported separately: 201326592 for the measured SKU's file. The third-way red
case (knee at neither value) did not occur. Both extremes of the instrument shown in-band:
100.00 % at 8 MB, 0.00 % (5 absolute hits) at 256 MB.

## 6 · Evidence
Run 2026-08-24. Warm-pass hit rate (passes 2–4 of 4; 128 B lines; ≥2 repeats/size, verdict
region 3/3; three msprof runs produced no op-summary and are recorded in 0007 §6):

| S (MB) | warm-hit % (all repeats) | effective read bandwidth |
|---|---|---|
| 8 / 16 / 32 / 64 | 100.00 (counts = 3·S/128 exactly, +5) | 181–184 GB/s |
| 128 | 100.00 | 184 GB/s |
| 160 | 100.00 | 185 GB/s |
| 192 | 68.75 / 69.79 / 69.79 | 163 GB/s |
| 224 | 21.43 / 21.43 / 20.54 | 138 GB/s |
| 256 | 0.00 / 0.00 / 0.00 (5 hits absolute) | 129 GB/s |

Interface: `GetCoreMemSize(L2) = 201326592`, `GetCurNpuArch() = 2201`, one process.
INI: values in SOURCE; the 32 MB found only in the NpuArch=1001 file.
Auxiliary, not a verdict: the bandwidth column is single-AIV effective read bandwidth at
curFreq 800 MHz and is reported only because the knee is visible in it independently
(185 → 163 → 138 → 129 GB/s).

## 7 · Scope limits — what this entry does NOT establish
One die of one part, one pin. The knee is LOCALISED to (160 MB, 256 MB) by these sweep points,
not measured to the megabyte — 192 MB is carried by the agreement of three arms, not by the
sweep alone pinning 192.0. The gradual collapse shape (69 % → 21 % → 0 %) says the replacement
behaviour is not strict-LRU under cyclic streaming; this entry does not characterise the policy.
Capacity visible to one AIV core under streaming reads is what was measured; whether other
engines or all cores together see the same effective capacity is not separated by this method.
910B4 (ini 96 MB), 910B4-1 (ini 168 MB), 910B2C, 910B3, Ascend910_93: ini values enumerated
where present, nothing behavioural run — the family's L2 is per-SKU and each SKU needs its own
knee. Nothing about how the 1001 figure entered upstream's metrics table, and nothing about
DAV_3510 (RULES.md Art. 1).
