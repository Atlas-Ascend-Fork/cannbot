```
ID:        0024-on-ascend-910b-32-b-aligned-gm-access-is-quoted-at-70-percent-of-512-b-bandwidth-with-no-shape-given
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   verified — §4 run on 910B2 2026-08-25 via §5: `ratio(size)` = bw(32-B offset)/bw(512-B offset) =
           0.72 at 256 B, 0.72 at 1 KB (inside the declared [0.60, 0.80] window), but 0.98 / 0.97 /
           0.97 / 1.00 at 4 / 16 / 64 / 128 KB (outside it); `ratio_spread` = 0.28 > 0.15 → per §5 the
           entry is CORRECTED to "no single ratio exists": the 70 % holds for transfers ≤ 1 KB and vanishes
           from 4 KB up. Control: bw(512-B aligned, 64 KB) / bw(512-B aligned, 256 B) = 2.3 ✓. §6.
BOARD:     910B2 (measured 2026-08-25); other 910 parts unverified
SOURCE:    ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:212-215 — "// 实测带宽对比（GM→UB，Ascend 910B）：// 按最优粒度（512B）对齐: ~100% 带宽效率 // 256B 对齐: ~90% 带宽效率 // 32B 对齐:  ~70% 带宽效率（最差情况）"
INDEX:     means=6 × 6 grid, GM offset {32, 64, 128, 256, 512, 1024} B × transfer {256 B … 128 KB}, `DataCopyPad`
           GM→UB, 48 cores, `aclrtEvent` min of 5 launches
           conditions=CANN 9.1.0, 910B2 die 0, curFreq 800 MHz, 32 MB region per core
           readouts: ratio(32 B / 512 B) = 0.72, 0.72, 0.98, 0.97, 0.97, 1.00 for 256 B … 128 KB;
           a 64-B offset costs the same as 32 B, a 128-B offset costs nothing at 256 B and 11 % at 1 KB
           time=2026-08-25
OVERTURN:  a GM→UB alignment sweep on a named DAV_2201 board returns a 32 B-aligned bandwidth outside roughly 60–80 % of the 512 B-aligned figure — or returns a ratio that depends so strongly on transfer size that a single ratio is not a meaningful quantity.
```

# 0024 · On "Ascend 910B", 32 B-aligned GM access is quoted at 70 % of 512 B bandwidth — with no shape given

## 1 · Claim
Measured on 910B2 (48 cores, GM→UB): a GM start offset of 32 B delivers **0.72×** the bandwidth of a
512-B-aligned start for 256-B transfers and **0.72×** for 1-KB transfers — upstream's "about 70 %" —
but **0.98× / 0.97× / 0.97× / 1.00×** for 4 / 16 / 64 / 128 KB transfers. There is no single
ratio: the alignment penalty is a per-transfer cost that matters while the transfer is short and is
amortised away by 4 KB. A 64-B offset behaves exactly like 32 B; a 128-B offset costs nothing at 256 B
and 11 % at 1 KB; 256 B and above behave like 512 B. Upstream's figure is reproduced pointwise at the
shapes where it applies and is the wrong shape of claim — the correction §5 declared for a
`ratio_spread` above 0.15 (measured 0.28).

## 2 · The wrong branch this removes
Two branches, and the second is the reason this entry is `boundary` rather than `knowledge`.

The first: an agent that aligns only to the 32 B correctness requirement (0021) and believes its
data movement is done, leaving up to 30 % of GM bandwidth unused on every transfer. That is the
branch the upstream number is written to remove, and it removes it.

The second: an agent that takes 70 % as a *number* and puts it in a cost model. It cannot be used
that way. "Bandwidth efficiency" without a transfer size is not a defined quantity on this
machine — the same document states, four sections earlier, that transfers below 256 B are
dominated by setup cost and transfers above 4096 B use the bus well (0025), and
`metrics_reference.md:150` adds that peak bandwidth needs ≥ 16 KB. So the 70 % figure is a ratio
between two unspecified points on a curve that upstream itself says is strongly size-dependent.
Two agents could both honour this entry and build cost models that disagree by a factor of two.

Recording it as a boundary — a real, useful direction with an unusable magnitude — is what keeps
both branches closed at once.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md`,
lines 208-215, verbatim in full:
```cpp
// === Variant F: GM 按设备最优粒度对齐带宽优化 ===
// 以下数据为 Ascend 910B 实测结果，不同设备的最优对齐粒度可能不同。
uint32_t offset = AlignUp(rawOffset, 512);  // 910B 上 512B 为最优粒度
DataCopy(ubTensor, gmTensor[offset], dataSize);
// 实测带宽对比（GM→UB，Ascend 910B）：
// 按最优粒度（512B）对齐: ~100% 带宽效率
// 256B 对齐: ~90% 带宽效率
// 32B 对齐:  ~70% 带宽效率（最差情况）
```
The headline figure, line 17: "| 对齐访问带宽 | 未按最优粒度对齐: ~70% | 按设备最优粒度对齐 |
带宽提升最高 30%（Ascend 910B 实测） |". And line 7: "以 Ascend 910B 实测为例，32B 对齐的带宽约为
512B 对齐的 70%，不同设备的最优对齐值需实测确认。"

**Upstream's own scoping caveat**, line 45, which is better than most of this repo manages and is
quoted in full because it is the honest half: "以下阈值基于 Ascend 910B 实测经验，不同设备的 DMA
控制器、总线宽度和缓存行大小不同，具体数值需参考对应硬件手册或实测确认。"

**What "Ascend 910B" names.** It is a SocVersion, not a board. Per
`ops/npu-arch/references/npu-hardware-params.md:17-18` it spans Ascend910B1, B2, B3, B4, 910B2C
and Ascend910_93 — six parts, across two product lines (Atlas A2 and A3), with at least one known
material difference between them (core counts, 0009). BOARD is therefore
`family-claimed(unverified)` and NOT `910B2`, even though a chip-shaped string appears in the
source. The form checker accepts any listed token, so this distinction is enforced here and not
by the tool.

Same-repo restatement of the direction with a different number:
`ops/ascendc-performance-analysis/references/metrics_reference.md:409` — "| GM 对齐 | 非 512B 对齐
带宽降 30% | Tiling 保证内轴对齐 |". A 30 % drop and a 70 % retention are the same statement,
which is a consistency check, not corroboration (one origin).

## 4 · Procedure
Proposed, runnable later; not run. This is the procedure that would turn an unusable ratio into a
usable curve, which is a different and larger deliverable than reproducing the quoted number.

1. Name the die; record which part it is (`npu-smi info -t board`), because "910B" spans six and
   the result is only ever about the one used; occupancy before and after; no substitution.
2. Two-dimensional sweep, one binary, both axes runtime arguments so no build differs:
   - alignment of the GM offset: 32, 64, 128, 256, 512, 1024 B
   - transfer size: 256 B, 1 KB, 4 KB, 16 KB, 64 KB, 256 KB
3. Per cell: bytes moved / `aiv_mte2_time` from PipeUtilization.csv, five repeats, first discarded
   as warm-up, median and spread reported.
4. Report the full 6×6 grid, not a single ratio. If the ratio at 32 B versus 512 B varies across
   the size axis by more than the spread, then no single number exists and that is the finding —
   it is the OVERTURN condition's second clause and the more likely outcome.
5. Fix dtype and direction (GM→UB) to match upstream's stated scope, and note that MTE3 (UB→GM) is
   a separate experiment not run here.

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

0024-specific: the grid is offsets {32, 64, 128, 256, 512, 1024} B × transfers {256 B, 1, 4, 16, 64, 128 KB}, 48 cores (one core's ratio at 256 B / 1 KB is the same shape by the 0025 ladder); `aiv_mte2_time` replaced by the event time as above.

## 5 · Checker — acceptance declared before the run
Verdict variable `ratio(size) = bw(32 B, size) / bw(512 B, size)`, one value per transfer size.
PASS (upstream's figure reproduced) iff `ratio(size)` lies in [0.60, 0.80] for every size in the
sweep. The window is declared now, at ±10 points around 70 %, which is generous for a figure quoted
with a tilde.
The second and more informative verdict, `ratio_spread` = max − min of `ratio(size)` across sizes.
If `ratio_spread` exceeds 0.15, the entry is corrected to say that no single ratio exists, EVEN IF
every individual value fell inside the window — a claim can be reproduced pointwise and still be
the wrong shape of claim, and this checker is built to notice that.
Control that lets it go red: `bw(512 B, 64 KB)` must exceed `bw(512 B, 256 B)` by a wide margin,
confirming the instrument resolves bandwidth differences at all. If it does not, the grid is VOID.
Exit code is not the verdict.

## 6 · Evidence
RUN 2026-08-25, 910B2 die 0, 48 cores, read; GB/s from the min of 5 launches:

| transfer B \ GM offset | 32 B | 64 B | 128 B | 256 B | 512 B | 1024 B | ratio 32 B / 512 B |
|---|---|---|---|---|---|---|---|
| 256 | 487 | 489 | 689 | 671 | 673 | 673 | 0.72 |
| 1024 | 1089 | 1085 | 1344 | 1494 | 1517 | 1520 | 0.72 |
| 4096 | 1496 | 1509 | 1519 | 1516 | 1528 | 1526 | 0.98 |
| 16384 | 1486 | 1511 | 1516 | 1528 | 1526 | 1529 | 0.97 |
| 65536 | 1482 | 1531 | 1478 | 1528 | 1530 | 1526 | 0.97 |
| 131072 | 1531 | 1504 | 1532 | 1533 | 1529 | 1527 | 1.00 |

`ratio(size)` inside [0.60, 0.80] at 256 B and 1 KB only; `ratio_spread` = 0.28 > 0.15 → "no single ratio
exists" (declared correction). Control: bw(512 B offset, 64 KB) = 1530 vs bw(512 B offset, 256 B) = 673 →
2.3× — the grid resolves bandwidth. Note the 128-B column: at 256 B it equals the aligned columns (689 vs
671–673), at 1 KB it sits between (1344 vs 1088 / 1517) — a 128-B granularity in the MTE2 path that
upstream's 32-vs-512 framing cannot express.

## 7 · Scope limits — what this entry does NOT establish
910B2 only, GM→UB only (MTE3 not measured), one clock state (800 MHz), 48 cores streaming HBM-resident
regions; offsets below 32 B (a 16-B or 8-B start) and dtype effects were not swept; the per-transfer
alignment cost is inferred from the ratio curve, not timed in isolation. Nothing transfers to the 950
book (RULES.md Art. 1).
