```
ID:        0055-the-atlas-a2-peak-bandwidth-and-vector-throughput-figures-are-quoted-without-a-derivation
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   harvested — two upstream figures used as denominators in theoretical-time formulas, with no derivation or measurement conditions; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ops-profiling/SKILL.md:243 — "Atlas A2: GM 峰值带宽约 1.8 TB/s = 1.8e12 Byte/s"; ibid:252 — "Atlas A2: float32 Vector 峰值算力约 11.06 TOPS"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a bandwidth or throughput sweep on a named Atlas A2 board reaches a sustained figure materially above either quoted peak, or falls so far below it that the peak is useless as a denominator.
```

# 0055 · The Atlas A2 peak bandwidth and Vector throughput figures are quoted without a derivation

## 1 · Claim
Upstream asserts that Atlas A2 has a GM peak bandwidth of about 1.8 TB/s and a float32 Vector peak
throughput of about 11.06 TOPS. Upstream uses both as denominators in theoretical-time formulas:
transfer time = bytes / bandwidth, compute time = elements / throughput, with the ratio of actual
to theoretical driving a bound diagnosis. Upstream gives no derivation, no measurement conditions
and no source for either figure. Not established here.

## 2 · The wrong branch this removes
These two numbers sit at the bottom of a diagnostic method. The whole "is this pipe at its limit?"
question — which decides whether to optimise a pipe or hide it behind another — reduces to
comparing measured time against `bytes / 1.8e12` or `elements / 11.06e12`. If a denominator is
wrong by 30 %, every attainment figure derived from it is wrong by 30 %, and a pipe at 75 % of true
peak can be reported as at 100 % and abandoned.

The specific hazard is asymmetric. An over-stated peak makes everything look inefficient, which
wastes effort but is recoverable. An under-stated peak makes a pipe look saturated when it is not,
and the agent stops optimising something that had room — an error that leaves no trace at all.

What an agent should do instead is what upstream's own better documents do for capacities (0011):
measure the achievable figure on the part in hand and use that as the denominator, treating the
quoted peak as an upper bound on the bound. The 1.8 TB/s figure in particular is a *peak*, and
0024/0025 record that achieved bandwidth depends strongly on alignment and transfer size — so the
gap between peak and achievable is not noise, it is the subject of two other entries.

## 3 · Ground / Source
`ops/ops-profiling/SKILL.md` §"理论性能计算", line 243: "Atlas A2: GM 峰值带宽约 1.8 TB/s =
1.8e12 Byte/s", and line 252: "Atlas A2: float32 Vector 峰值算力约 11.06 TOPS". Both introduced by
约 ("approximately") and neither sourced.

The same figures without the chip name, in a worked example —
`ops/ascendc-performance-analysis/references/metrics_reference.md` §5.1, lines 233-236:
"**示例**：float 4096×4096 矩阵，GM 峰值带宽 1.8TB/s / 数据量 = 4096 × 4096 × 4 = 64 MB /
理论耗时 = 64 MB / 1.8 TB/s = 35.6 μs", and §5.2 lines 250-252: "**示例**：32K 个 float 元素的
单指令 Vector 计算，理论峰值算力 11.06 TOPS / 理论耗时 = 32K / 11.06 TOPS = 0.003 μs".

Arithmetic checked here: 64 MB (67 108 864 B) / 1.8e12 = 37.3 µs, against upstream's stated
35.6 µs. Using 64 × 10⁶ B gives 35.6 µs exactly — so upstream computed with a decimal megabyte
while writing "64 MB" for a binary quantity. A 4.7 % discrepancy inside a worked example. Minor,
but it is the kind of slip that says the example was not re-derived.

The caveats upstream does attach, §5.1 lines 239-242: "- MTE2/MTE3 同时工作时共享带宽：总耗时 =
(MTE2 数据量 + MTE3 数据量) / GM 带宽 - 小数据块搬运时实际带宽远低于理论峰值（≥16KB 时才接近峰值）
- 不同芯片理论带宽不同". The second is exactly 0025's territory and means the denominator is not
reachable at small sizes.

**Provenance grade.** `ops/npu-arch/references/npu-hardware-params.md` §4 lists bandwidth figures
for the 950 family under the tier "公开资料 / 经验值" — public material or engineering experience,
upstream's weakest evidence class, explicitly not derivable from installed INIs (0012). No
equivalent A2 row exists there. So the best available guess at these figures' provenance is that
they belong to that same weakest tier, and even that is an inference this entry does not assert.

Note the entry merges the two figures because they share one wrong branch — a wrong denominator in
a theoretical-attainment calculation — and would otherwise be two entries with identical §2.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; record the part; occupancy before and after; no substitution.
2. Bandwidth arm: the size and alignment grid of 0024 §4 and 0025 §4, run once and shared by all
   three entries. Report the maximum sustained GB/s achieved anywhere on the grid, using all cores,
   512 B-aligned, at the largest transfer size — that is the closest thing to an achievable peak.
3. Throughput arm: a dense fp32 Vector kernel with no memory pressure (data resident in UB, many
   arithmetic ops per element), sweeping arithmetic intensity upward until throughput plateaus.
   Report the plateau in TOPS. Report the instruction mix, since 11.06 TOPS presumably assumes one
   specific operation and the figure is not portable across the instruction set.
4. Report BOTH the achieved figure and its ratio to the quoted peak. The ratio is what a consuming
   agent needs in order to know how much to trust the quoted denominator.
5. Five repeats each, first discarded.

## 5 · Checker — acceptance declared before the run
Verdict variables `bw_max_achieved` and `tops_max_achieved`.
PASS (the quoted peaks are upper bounds and roughly right) iff `bw_max_achieved` lies in
[0.6, 1.0] × 1.8 TB/s and `tops_max_achieved` in [0.6, 1.0] × 11.06 TOPS.
Exceeding the quoted peak overturns the figure outright and is the clean red input.
Falling below 0.6 does NOT overturn — a peak is not required to be achievable — but it does mean
the figure is unusable as a diagnostic denominator, and the entry is corrected to record the
achievable figure alongside the quoted one. That distinction is declared now, because "we measured
0.5 × peak" could otherwise be narrated either as confirming the peak or as refuting it.
Control: `bw_max_achieved` at 64 KB transfers must exceed that at 256 B transfers by a wide margin
(0025). Without it, the arm is not resolving bandwidth and is VOID.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "Atlas A2" is a product line spanning five parts; GM
bandwidth and core count both vary by sub-model (0009, and npu-arch's own §"子型号变化参数"), so a
single family-wide figure is questionable on its face. **No derivation, source, tool or condition
is given for either number**, and this entry does not supply one. It does not establish the
instruction mix behind 11.06 TOPS, nor whether it refers to per-core or whole-chip throughput —
which is a factor-of-48 ambiguity and the single largest unknown here. It does not establish
figures for fp16, bf16 or int8 Vector throughput, or for Cube throughput (0038 gives only a ratio).
It says nothing about Atlas A3.
