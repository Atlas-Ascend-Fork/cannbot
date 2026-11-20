```
ID:        0064-the-truth-source-and-a-downstream-skill-disagree-about-910-memory-bandwidth
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   verified — §4 run on 910B2 2026-08-25 via §5: `bw_sustained` = **1.537 TB/s** (read, 48 cores,
           128 KB transfers, 25 GB moved, min of 5) — below BOTH quoted peaks (1.6 and 1.8 TB/s), the declared
           "does not discriminate" branch: the claim (two figures, neither established) is UPHELD, and the
           sustained figure a denominator should use is now measured. Write 1.495, copy 1.258 TB/s
           (read + write bytes). Control bw(128 KB)/bw(256 B) = 2.3 ✓. §6.
BOARD:     910B2
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:91 — "| Memory 带宽 | 1.6 TB/s [¹](#unverified) | 1.4 TB/s [¹](#unverified) | 1.6 TB/s [¹](#unverified) |"; ops/ops-profiling/SKILL.md:243 — "Atlas A2: GM 峰值带宽约 1.8 TB/s = 1.8e12 Byte/s"
INDEX:     means=`DataCopyPad` streaming over 48 × 32 MB regions (1.5 GB per side), 128 KB transfers × 4000 per
           core, `aclrtEvent` min of 5 launches, three launches per mode
           conditions=CANN 9.1.0, 910B2 die 0, curFreq 800 MHz, device idle
           readouts: read 1537 / 1528 GB/s (min / median) · write 1495 / 1494 · copy 1258 / 1255
           (read+write bytes); core scaling read 1 / 8 / 24 / 48 cores = 229 / 771 / 1385 / 1533 GB/s;
           control 256-B transfers 672 GB/s
           time=2026-08-25
OVERTURN:  a streaming-bandwidth sweep on a named Ascend910B2 part sustains above 1.6 TB/s (killing the truth source's figure) or plateaus well below it (making both figures unusable as denominators).
```

# 0064 · The truth source and a downstream skill disagree about 910 memory bandwidth

## 1 · Claim
Upstream states two peaks for Ascend910B2 memory bandwidth — 1.6 TB/s in its truth source (footnoted
"unverified") and about 1.8 TB/s in a downstream profiling skill that uses it as a denominator.
Measured on 910B2: **sustained read 1.537 TB/s**, write 1.495 TB/s, copy 1.258 TB/s counting
both directions (48 AIV cores, 128 KB transfers, 25 GB moved per launch). The sustained figure lies below
both quoted peaks, which is §5's declared non-discriminating outcome: neither peak is falsified as a
peak, both are wrong as sustained denominators — a kernel moving 1.5 TB/s is at 98 % of what this part
sustains, not at 83 % or 94 %. Not established: which of the two is the correct *peak*; a sustained
measurement cannot say.

Inference, stated separately: read + write together deliver 1.257 TB/s of total traffic against
1.537 read-only and 1.495 write-only — the "MTE2 bytes + MTE3 bytes over one bandwidth" model
(`metrics_reference.md:240`) overestimates mixed throughput by ≈ 18 % here (`mixed_model_error`,
reported without threshold as §5 declared).

## 2 · The wrong branch this removes
0055 records that these peak figures are quoted without derivation and warns against modelling with
them. This entry adds the part that makes the warning concrete: **the two available numbers
disagree, and the one that is used in the formulas is the one the truth source does not endorse.**

An agent computing "is this pipe at its theoretical limit?" divides measured bytes by a bandwidth.
At 1.8 TB/s a kernel achieving 1.5 TB/s is at 83 % and looks like it has headroom; at 1.6 TB/s the
same kernel is at 94 % and looks saturated. Those two readings recommend opposite actions —
keep optimising the transfer, or stop and hide it behind compute.

The second and sharper point is a governance one, and it is why this is a `boundary` entry rather
than a number. `npu-arch-guide.md:74` states: "本节作为 NPU 架构知识在 skills 仓中的上游真源，下游
skill 应消费本节数据，**反向自引用即视为风险**." So upstream has a declared rule about which of its
own documents wins, ops-profiling's 1.8 TB/s violates it, and nothing mechanical enforces it. A
consuming agent that meets 1.8 TB/s in the profiling skill has no way to know it is reading a
downstream divergence from a source that marked its own figure unverified.

An agent should use neither as a denominator without measuring, and should prefer the truth
source's figure if forced to choose — while recording that the truth source disclaims it.

## 3 · Ground / Source
`ops/npu-arch/references/npu-arch-guide.md` §算力与系统规格, line 91, in the table whose columns are
Ascend910B2 (DAV_2201) / Ascend950PR PCIE / Ascend950PR Server:
```
| Memory 带宽 | 1.6 TB/s [¹](#unverified) | 1.4 TB/s [¹](#unverified) | 1.6 TB/s [¹](#unverified) |
```
Every cell carries the `[¹](#unverified)` mark. The same file's §"典型硬件参数与获取方式" preamble,
line 74: "> ⚠️ **核心原则**：本节作为 NPU 架构知识在 skills 仓中的上游真源，下游 skill 应消费本节
数据，**反向自引用即视为风险**。"

The provenance tier this figure sits in,
`ops/npu-arch/references/npu-hardware-params.md:178`: "| 13 | Memory 带宽 Server 1.6 TB/s / PCIE
1.4 TB/s | Guide §3 算力与系统规格 | 同上 |" — under §4's heading, "以下信息无法从当前安装的 INI
直接推导，数据来源于公开资料或工程经验积累". So bandwidth is in upstream's explicitly weakest
evidence class: public material or engineering experience, not derivable from an INI. Note that row
13 lists only the two 950 figures; the 910B2 value appears in the guide's table and not in this
provenance list.

The divergent figure, `ops/ops-profiling/SKILL.md:243`: "Atlas A2: GM 峰值带宽约 1.8 TB/s =
1.8e12 Byte/s", used at `:243-252` in the theoretical-time worked examples, and carried by 0055.

The third appearance, chip-unnamed,
`ops/ascendc-performance-analysis/references/metrics_reference.md:233`: "**示例**：float 4096×4096
矩阵，GM 峰值带宽 1.8TB/s" — with the arithmetic slip 0055 §3 records (the example computes with a
decimal megabyte while writing "64 MB").

Filed as `harvest/contradictions-910.md` **C-910-011**.

Two readings, neither established: 1.8 TB/s may be a different quantity (a different SKU, a
bidirectional figure, or a marketing peak) or it may be a downstream number that drifted. Nothing
in scope distinguishes them, and RULES.md Art. 7 forbids choosing by plausibility — including by the
plausibility argument "the truth source says it is the truth source", which is a self-declaration.

## 4 · Procedure
Proposed, runnable later; not run. This is the same grid as 0024/0025/0055 and should be one run.

1. Name the die; record `npu-smi info -t board -i <n>`, because bandwidth is a per-SKU parameter
   (0062); occupancy before and after; no substitution.
2. Streaming-read arm: all cores, 512 B-aligned, transfer size at the largest the sweep reaches
   (256 KB per core or more), total bytes ÷ elapsed, five repeats with the first discarded. Report
   sustained GB/s.
3. Read+write arm: upstream states MTE2 and MTE3 share GM bandwidth and that total time is
   `(MTE2 bytes + MTE3 bytes) / bandwidth` (`metrics_reference.md:240`). Measure a mixed stream to
   see whether the sum model holds, since a "bandwidth" that behaves differently read-only and mixed
   is not one number.
4. Report against BOTH quoted figures, as two ratios, never against one.
5. Read the INI for any bandwidth-shaped field and record whether one exists — upstream says the
   figure is *not* INI-derivable, and confirming that absence is worth doing once.

**As run (2026-08-25, the 910 machine, die 0 of eight 910B2, one job `bw910`; curFreq 800 MHz before,
after warm-up and after — the DVFS floor for the AI Core clock, which the MTE-bound kernel did not raise;
every verdict below is a ratio or a sustained figure measured under that one clock state):** one kernel,
`DataCopyPad` GM→UB (mode read), UB→GM (write) or both (copy) over a per-core 32 MB region (48 cores →
1.5 GB per side, far beyond the 192 MB L2), transfer start advancing by a 512-B-rounded step and
wrapping; transfer size and GM offset are runtime arguments so no build differs. Timing: `aclrtEvent`
around one launch (5 launches, min and median) plus per-core `GetSystemCycle()` deltas on their own
64-B GM lines; msprof's `aiv_mte2_time` was not collected — the event time over a kernel that does
nothing but MTE traffic is the same quantity at whole-kernel resolution. Bandwidth = bytes moved ÷
min time. A 3× warm-up (copy, 256 KB × 2000 × 48) preceded the sweeps.

0064-specific: step 5's ini read — `grep -i 'bandwidth|bw|hbm' Ascend910B2.ini` returned nothing (no bandwidth-shaped field), as upstream says.

## 5 · Checker — acceptance declared before the run
Verdict variable `bw_sustained`, the maximum sustained whole-chip GB/s.
The entry's claim (the two figures disagree and neither is established) is upheld while
`bw_sustained` fails to discriminate — which it will if it lands below both, the expected outcome
for a sustained figure against a peak.
It is resolved, and this entry restratified, iff `bw_sustained` exceeds 1.6 TB/s: that kills the
truth source's figure outright and leaves 1.8 TB/s standing. That is the clean red input and it is
declared now.
`bw_sustained` between the two is NOT a resolution and must not be reported as favouring the higher
figure — a sustained measurement sitting between two claimed peaks is consistent with both.
Declared in advance because this is the outcome most open to convenient narration.
`mixed_model_error` from arm 3: reported with no threshold; a large error means the single-bandwidth
model behind both figures is wrong, which would matter more than which number is right.
Control: `bw_sustained` at 256 KB transfers must far exceed that at 256 B transfers (0025), or the
harness is not measuring bandwidth and the run is VOID.
Exit code is not the verdict.

## 6 · Evidence
RUN 2026-08-25, 910B2 die 0 (idle before and after), curFreq 800 MHz throughout.

**Sustained, 48 cores, 128 KB transfers, 4000 per core, three launches each (GB/s, min time / median):**

| mode | bytes per launch | launch 1 | launch 2 | launch 3 |
|---|---|---|---|---|
| read | 25.2 GB | 1537.2 / 1529.3 | 1536.8 / 1528.0 | 1534.3 / 1518.9 |
| write | 25.2 GB | 1494.9 / 1494.8 | 1494.7 / 1494.5 | 1494.8 / 1493.9 |
| copy (read + write) | 50.3 GB | 1257.3 / 1255.2 | 1257.6 / 1256.2 | 1255.2 / 1254.8 |

`bw_sustained` = 1.537 TB/s < 1.6 TB/s → not a resolution between the two peaks (declared). Sum model
check: read-only 1.537 + write-only 1.495 would predict ≈ 1.5 TB/s of mixed traffic; measured 1.257 →
`mixed_model_error` ≈ −18 %.

**Core scaling (read, 128 KB):**

| cores | GB/s | GB/s per core |
|---|---|---|
| 1 | 229 | 228.5 |
| 8 | 771 | 96.3 |
| 24 | 1385 | 57.7 |
| 48 | 1533 | 31.9 |

**Control:** 256-B transfers 672 GB/s vs 128 KB 1534 GB/s (2.3×) — the harness measures bandwidth.
**Ini:** no bandwidth-shaped field in `Ascend910B2.ini` (step 5).

## 7 · Scope limits — what this entry does NOT establish
Which quoted figure is the true *peak* — a sustained measurement below both cannot say. One part, one
die, one access pattern (48 AIV cores each streaming its own 32 MB region with 128 KB `DataCopyPad`
transfers; the AIC side's MTE and a mixed AIC+AIV load were not driven), one clock state (800 MHz). The
copy figure interleaves read and write on each core with explicit MTE2↔MTE3 flags between them — a
different overlap schedule could reach a different mixed throughput; the −18 % is for this schedule.
Nothing transfers to the 950 book (RULES.md Art. 1).
