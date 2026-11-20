```
ID:        0025-dma-transfers-below-256-b-are-dominated-by-setup-cost-on-ascend-910b
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   verified — §4 run on 910B2 2026-08-25; §5's PASS predicate NOT met and its red input NOT met, so
           the claim is CORRECTED IN PLACE (form/STRATA.md promotion note): `bw(4096)/bw(256)` = 4.43 (one
           core) / 2.26 (48 cores) ≥ 1.5 ✓; `bw(65536)/bw(4096)` = 1.009 / 1.000 — NOT > 1.1 ✗;
           `bw(65536)/bw(16384)` = 1.011 / 0.994 < 1.1 ✓; control `bw(16)/bw(65536)` = 0.014 ✓.
           The setup-cost regime is real but ends near 1 KB, not 256 B, and nothing is gained above 4 KB. §6.
BOARD:     910B2 (measured 2026-08-25); other 910 parts unverified
SOURCE:    ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:47-53 — "| < 32 bytes | 极低 | 对齐开销占主导 | ... | > 65536 bytes | 极佳 | 接近峰值吞吐 |", under the caveat at :45 "以下阈值基于 Ascend 910B 实测经验"
INDEX:     means=`DataCopyPad` GM→UB per core, transfer size 16 B … 128 KB at a 512-B-aligned offset, `aclrtEvent`
           min of 5 launches + per-core `GetSystemCycle()`; one core and 48 cores
           conditions=CANN 9.1.0, 910B2 die 0, curFreq 800 MHz throughout, 32 MB region per core (HBM-resident)
           readouts (GB/s, one core): 16 B 3.2 · 32 B 6.4 · 64 B 12.8 · 128 B 25.5 · 256 B 51.0 · 512 B 101.8 ·
           1 KB 202.3 · 4 KB 225.7 · 16 KB 225.2 · 64 KB 227.8 · 128 KB 218.6 — 5.0 ns per transfer up to 1 KB;
           48 cores: 16 B 46.7 … 256 B 673.5 · 512 B 1516 · ≥ 1 KB 1522–1534 (chip-saturated)
           time=2026-08-25
OVERTURN:  a transfer-size sweep on a named DAV_2201 board shows achieved bandwidth rising smoothly with size, with no band structure near 256 B or 4096 B.
```

# 0025 · DMA transfers below 256 B are dominated by setup cost on "Ascend 910B"

## 1 · Claim
Measured on 910B2: a GM→UB `DataCopyPad` costs a fixed **≈ 5.0 ns per transfer** on one core for every
size from 16 B to 1 KB — bandwidth per core is therefore proportional to size in that whole range (3.2
GB/s at 16 B, 51 GB/s at 256 B, 202 GB/s at 1 KB) — and saturates at **≈ 225 GB/s per core by 4 KB**,
with no further gain to 128 KB (227.8 at 64 KB, 218.6 at 128 KB). With 48 cores the chip saturates at
≈ 1.52–1.53 TB/s already at 512 B per transfer. Upstream's five bands are therefore right in direction
and wrong in their boundaries: there is no feature at 256 B (the per-transfer cost is the same fixed
5 ns from 16 B to 1 KB), the "good from 4 KB" band is where per-core saturation is reached, and the
"excellent above 64 KB, approaching peak" band does not exist — 64 KB delivers 1.01× of 4 KB on one core
and 1.00× on 48. Not established: the corresponding UB→GM (MTE3) ladder, which §4 excluded.

Inference, stated separately: a 5.0 ns issue cost is ≈ 4 cycles at the 800 MHz the core sat at; whether
it shrinks at the 1800 MHz rating (making the proportional regime end earlier in bytes) was not
measured — the ladder was run in one clock state.

## 2 · The wrong branch this removes
Over-tiling. An agent balancing UB occupancy, core count and tail handling has several reasons to
choose small tiles — they fit, they parallelise, they leave a smaller tail — and no local signal
that a tile below a few hundred bytes per transfer is being charged mostly for setup. The band
table gives the agent a floor to check its tiling against: if the per-transfer byte count lands
under 256 B, the tiling is paying a tax that no amount of compute optimisation recovers.

The band table also removes an over-correction. "Bigger transfers are better" pushed to its limit
produces one enormous tile, no double buffering, and no core parallelism. The table says the
returns flatten: 4096 B is already "good", and the step to 65536 B buys the last increment. An
agent that knows where the curve flattens can stop.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md`
§2.3 DMA 效率阈值, line 45 (the caveat) then lines 47-53 (the table), verbatim in full:

"以下阈值基于 Ascend 910B 实测经验，不同设备的 DMA 控制器、总线宽度和缓存行大小不同，具体数值需
参考对应硬件手册或实测确认。"
```
| 传输大小 | 效率 | 说明 |
| < 32 bytes | 极低 | 对齐开销占主导 |
| 32-256 bytes | 差 | DMA 设置成本显著 |
| 256-4096 bytes | 中等 | 大多数场景可接受 |
| > 4096 bytes | 好 | 总线带宽充分利用 |
| > 65536 bytes | 极佳 | 接近峰值吞吐 |
```
Restated as advice, line 247: "8. **DMA 效率阈值**：传输大小 < 256B 时 DMA 设置成本显著；> 4096B
时总线带宽充分利用。避免过度 tiling 导致每次 DMA 传输过小。具体阈值因设备 DMA 控制器特性而异，
需参考对应硬件手册。" And as a checklist item, line 349: "- [ ] 传输大小 > 256B（以 Ascend 910B
为例），避免大量小 DMA 传输，不同设备阈值可能不同".

**A different threshold for the same phenomenon**, same repo (one origin):
`ops/ascendc-performance-analysis/references/metrics_reference.md:408` — "| GM 搬运效率 | 单次
<16KB 带宽利用率低 | 使用 DataCopyParams 批量搬运 |", and line 150 — "| GM 搬运（最优） | **512B**
| ≥16KB 数据量时可达峰值带宽 |", and line 241 — "小数据块搬运时实际带宽远低于理论峰值（≥16KB 时才
接近峰值）". So one document places "approaching peak" above 65536 B and another places it at
16384 B — a 4× disagreement about where the curve flattens.

Filed as `harvest/contradictions-910.md` **C-910-007**. The two are compatible readings of one
curve at different tolerances ("接近峰值" is not a defined threshold), which is precisely why
**neither number may be used as a gate** — an agent choosing a tile size by one of them is choosing
by which document it opened. §5 below declares the discriminating clause in advance.

Note the word "实测经验" — measured *experience*, upstream's own hedge, weaker than the "实测" it
uses at line 212 (0024). Two evidence grades in one document, distinguished by one character.

## 4 · Procedure
Proposed, runnable later; not run. This procedure is the size axis of 0024's grid and should be
run as one experiment with it rather than twice.

1. Name the die; record the part; occupancy before and after; no substitution.
2. Transfer size swept over 16, 32, 64, 128, 256, 512, 1 K, 4 K, 16 K, 64 K, 256 K bytes with the
   GM offset held at 512 B alignment throughout, so alignment (0024's axis) is not confounded with
   size.
3. Per size: total bytes / `aiv_mte2_time`, five repeats, first discarded, median and spread.
   Report achieved GB/s absolutely as well as normalised, so the bands can be read against the
   1.8 TB/s peak that 0056 records upstream quoting.
4. Report the curve, and locate the two knees the claim predicts (near 256 B and near 4096 B) by
   fitting piecewise-constant efficiency levels — not by eye.

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

0025-specific: the size axis was run alone at a 512-B-aligned offset (0024's axis is the same job's grid); reps chosen so each launch moves ≈ 64 MB (one core) / ≈ 768 MB (48 cores), capped at 200 000 transfers.

## 5 · Checker — acceptance declared before the run
Verdict variables `bw(size)` and the derived `knee_low`, `knee_high`.
PASS iff `bw(4096) / bw(256)` exceeds 1.5, AND `bw(65536) / bw(4096)` exceeds 1.1, AND
`bw(65536) / bw(16384)` is below 1.1 — the last clause is what discriminates between the two
upstream thresholds, and it is declared now rather than chosen after the curve is seen.
Red input: a smooth curve with `bw(4096) / bw(256)` below 1.2, which would mean the bands describe
nothing and the entry is overturned.
The control that keeps this honest: `bw(16)` must be far below `bw(65536)`. If even the extreme
ends do not separate, the measurement is not resolving DMA efficiency and the run is VOID rather
than negative — a flat result from a blind instrument is not evidence of a flat curve.
Exit code is not the verdict.

## 6 · Evidence
RUN 2026-08-25, 910B2 die 0 (idle before and after), curFreq 800 MHz PRE / after warm-up / POST.

**One core, read (GM→UB), 512-B aligned:**

| transfer B | transfers | µs (min of 5) | GB/s (min time) | GB/s (median) | ns per transfer |
|---|---|---|---|---|---|
| 16 | 200000 | 1005.8 | 3.2 | 3.2 | 5.0 |
| 32 | 200000 | 1003.4 | 6.4 | 6.4 | 5.0 |
| 64 | 200000 | 1003.1 | 12.8 | 12.7 | 5.0 |
| 128 | 200000 | 1004.6 | 25.5 | 25.4 | 5.0 |
| 256 | 200000 | 1004.0 | 51.0 | 50.9 | 5.0 |
| 512 | 131072 | 659.5 | 101.8 | 101.5 | 5.0 |
| 1024 | 65536 | 331.8 | 202.3 | 194.1 | 5.1 |
| 4096 | 16384 | 297.3 | 225.7 | 214.4 | 18.1 |
| 16384 | 4096 | 298.0 | 225.2 | 219.7 | 72.7 |
| 65536 | 1024 | 294.6 | 227.8 | 225.3 | 287.7 |
| 131072 | 512 | 307.0 | 218.6 | 216.6 | 599.6 |

**48 cores, read:**

| transfer B | transfers per core | µs (min) | GB/s (min time) | GB/s (median) | ns per transfer per core |
|---|---|---|---|---|---|
| 16 | 100000 | 1644.5 | 46.7 | 46.6 | 16.4 |
| 32 | 100000 | 1607.1 | 95.6 | 95.4 | 16.1 |
| 64 | 100000 | 1608.7 | 191.0 | 189.0 | 16.1 |
| 128 | 100000 | 1608.6 | 381.9 | 379.9 | 16.1 |
| 256 | 65536 | 1195.6 | 673.5 | 672.2 | 18.2 |
| 512 | 32768 | 531.0 | 1516.5 | 1512.2 | 16.2 |
| 1024 | 16384 | 529.3 | 1521.6 | 1516.6 | 32.3 |
| 4096 | 4096 | 528.2 | 1524.6 | 1455.9 | 129.0 |
| 16384 | 1024 | 524.9 | 1534.3 | 1527.2 | 512.6 |
| 65536 | 256 | 528.1 | 1524.9 | 1488.5 | 2062.9 |
| 131072 | 200 | 822.0 | 1530.7 | 1507.6 | 4110.1 |

**§5 predicate (declared before the run):** `bw(4096)/bw(256)` = 4.43 (one core), 2.26 (48) — > 1.5 ✓;
`bw(65536)/bw(4096)` = 1.009 / 1.000 — the > 1.1 clause FAILS; `bw(65536)/bw(16384)` = 1.011 /
0.994 — < 1.1 ✓ (C-910-007: the 16 KB and 64 KB thresholds are one and the same on this part). Red
input (`bw(4096)/bw(256)` < 1.2) NOT met. Control: `bw(16)` is 72× below `bw(65536)` on one core — the
instrument resolves DMA efficiency. Outcome: neither PASS nor overturn → corrected in place (§1).

## 7 · Scope limits — what this entry does NOT establish
One part (910B2), one die, GM→UB only (`DataCopyPad`, the classic API's padded copy; the plain
`DataCopy` path with 32-B-multiple counts may have a different issue cost); one clock state (800 MHz, the
DVFS floor — the 5.0 ns issue cost is a wall-clock figure at that state); HBM-resident regions (each core
streams 32 MB; an L2-resident working set was not swept here — 910:0077 covers L2). The UB→GM ladder
(MTE3) is not measured. The per-core 225 GB/s saturation is one core's MTE2 limit under this access
pattern, not a chip parameter. Nothing transfers to the 950 book (RULES.md Art. 1).
