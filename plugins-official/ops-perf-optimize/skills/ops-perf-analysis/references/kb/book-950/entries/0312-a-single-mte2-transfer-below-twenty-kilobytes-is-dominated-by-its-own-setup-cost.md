```
ID:        0312-a-single-mte2-transfer-below-twenty-kilobytes-is-dominated-by-its-own-setup-cost
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/scale_coalescing_design.md:9 —
           "> **20 KB 物理根因**：昇腾 AI Core 的 MTE2 发射单元对 "发起一次 GM→L1 搬运" 有固定头
           开销（地址建立、Burst 描述符、DMA 通道配置）。单次搬运量达到约 20 KB 左右时，头开销被
           数据时间摊薄到 < 5%；若单次低于 20 KB，头开销占比显著拉高，表现为 *cycles/byte* 远高于
           HBM 理论峰值。"
SOURCE:    same file:5 — "使 MTE2 的**带宽利用率**从典型的 50%–70% 拉回到 80%+ 的健康区间" ;
           :257-259 — "| MTE2 段时间（`[128, 8192, 4096]`）| 34.4 μs | 31.27 μs | **−9%** | |
           Task 总时间 | 39.53 μs | 36.76 μs | **−7%** | | MTE2 带宽利用率 | ~50–60% | ~80%+ |
           **+25 pp** |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a bandwidth-versus-transfer-size sweep on a named 950 board whose achieved GM→L1
           bandwidth shows no knee anywhere near 20 KB — either rising smoothly with no inflection,
           or inflecting at a materially different size. The constant would then be a policy value,
           not the physical threshold upstream calls it.
```

# 0312 · A single MTE2 transfer below twenty kilobytes is dominated by its own setup cost

## 1 · Claim
Upstream asserts a per-transfer threshold for GM→L1 movement: the MTE2 issue unit pays a fixed cost
per transfer — address setup, burst descriptor, DMA channel configuration — and at roughly 20 KB per
transfer that fixed cost amortises to under 5 % of the transfer, while below 20 KB it rises sharply
and shows as a cycles-per-byte far above the HBM peak. Upstream asserts a consequence it calls the
"false MTE2 bound": a matmul can show high MTE2 busy at only 50 %–70 % bandwidth utilisation, and
merging small transfers restores 80 %+. Upstream asserts a measurement for one such merge at
`[128, 8192, 4096]`: MTE2 segment 34.4 → 31.27 µs (−9 %), task 39.53 → 36.76 µs (−7 %), bandwidth
utilisation ~50–60 % → ~80 %+ (+25 pp). Not established here.

The threshold is load-bearing across this family: it is the entry gate for scale coalescing
(`0313`), one of the four admission conditions for Full-Load (`0311`, `对侧流式 Bytes ≥ 20 KB`), and
the reason a "false MTE2 bound" is routed to a different repair from a real one (`0304` §2).

## 2 · The wrong branch this removes
An agent sees MTE2 busy above 70 % and treats the operator as bandwidth-bound. It then reduces bytes
moved: bigger tiles, better reuse, Full-Load. If the transfers were small, none of that helps —
the pipe is busy paying setup, not moving data, and making each transfer *fewer* does nothing while
making each *larger* is the whole fix. Upstream separates the two cases numerically:
MTE2 busy > 85 % **and** bandwidth ≥ 85 % is a real bound; MTE2 busy > 60 % **with** bandwidth
< 70 % is the false one (`mte2_preload_design.md:286-287`). Bandwidth utilisation, not busy fraction,
is the discriminator, and an agent reading only busy cannot tell them apart.

The second wrong branch is the reverse and is invited by this very entry: applying merge logic to an
operator whose transfers are already large. Upstream states it — `检查是否 MTE2 总量本来就够大
（A/B 已 32 KB+）；合并只对 <20KB 的小块有效` — and the cost of getting it wrong is L1 spent on
buffers that buy nothing.

The third: treating 20 KB as a tunable. Upstream presents it as a physical amortisation point, so an
agent that "tunes" it downward to make a case qualify has not changed the machine, only the gate.
The correct move when a case sits below the knee and cannot be merged is to record it as not
applicable — which is what `0313`'s fallback ladder does.

## 3 · Ground / Source
The threshold and its stated cause, `scale_coalescing_design.md:9`:

```
> **20 KB 物理根因**：昇腾 AI Core 的 MTE2 发射单元对 "发起一次 GM→L1 搬运" 有固定头开销
（地址建立、Burst 描述符、DMA 通道配置）。单次搬运量达到约 20 KB 左右时，头开销被数据时间摊薄到
< 5%；若单次低于 20 KB，头开销占比显著拉高，表现为 *cycles/byte* 远高于 HBM 理论峰值。
```

The threshold applied as a search target, `:80-88`, which is the only place any numbers accompany
it:

```
1. **计算单次 scale 合并搬运量**：
   Bytes_scaleA = baseM × scaleKL1/32 × |dtype_scale|
   目标：`Bytes_scaleA ≥ 20 KB`（带宽拐点）。以 `baseM = 128, |dtype_scale| = 1 B` 为例：
   - `scaleKL1 = 512`（即 `SCALE_L1_BUFFER_NUM = 1`）：2 KB ✘
   - `scaleKL1 = 1024`（`=2`）：4 KB ✘
   - `scaleKL1 = 5120`（`=10`）：20 KB ✔（**最低门槛**）
   - `scaleKL1 = 8192`（`=16`）：32 KB ✔（**推荐**，兼容 K=8192 的整块覆盖）
   - `scaleKL1 = K`（"一次装完"）：理想值；L1 容得下时首选
```

Re-derived: `128 × 512/32 × 1 = 2048` ✓; `128 × 1024/32 = 4096` ✓; `128 × 5120/32 = 20480` ✓;
`128 × 8192/32 = 32768` ✓. The ladder is internally consistent.

The measured table, `:253-259`:

```
| 指标 | 优化前（SCALE_L1_BUFFER_NUM=2）| 优化后（SCALE_L1_BUFFER_NUM=16）| 变化 |
| 单次 scale MTE2 搬运量 | 1024 B | 8192–32768 B | +10× |
| scale MTE2 次数 | `2 × kL1Iter` | `2 × kL1Iter / 16` | ÷16 |
| MTE2 段时间（`[128, 8192, 4096]`）| 34.4 μs | 31.27 μs | **−9%** |
| Task 总时间 | 39.53 μs | 36.76 μs | **−7%** |
| MTE2 带宽利用率 | ~50–60% | ~80%+ | **+25 pp** |
```

Re-derived: `(34.4 − 31.27)/34.4 = 9.1 %` ✓; `(39.53 − 36.76)/39.53 = 7.0 %` ✓. But the first row
does **not** reconcile with §3.1's ladder: at `SCALE_L1_BUFFER_NUM = 2` the ladder gives 4096 B, not
1024 B, and `32768 / 4096 = 8×`, not the stated `+10×` (nor `32768/1024 = 32×`). So the table's
"before" cell disagrees with the file's own worked example for the same configuration. Recorded as
`C-950bp-005`; it does not affect the threshold claim, which is what this entry carries, and it does
affect any use of the `+10×` figure, which is therefore not carried.

The `20 KB` gate restated as a Full-Load admission condition, `fullload_design.md:266`, and as a
disqualifier, `scale_coalescing_design.md:222` — same repo, one origin (RULES.md Art. 3), quoted because
a reader arriving from either file meets the same number.

What upstream never supplies: any sweep. There is no bandwidth-versus-size curve anywhere in the
shelf; the knee is asserted with a mechanism and applied as a constant. The nearest thing in this
book's scope is the 910-attributed DMA efficiency table in
`reference/common/datacopy_optimization_design.md:47-53`, which puts its own bands at
`< 32 / 32–256 / 256–4096 / > 4096 / > 65536` bytes and explicitly scopes itself to Ascend 910B —
different chip, different numbers, and not carried here (RULES.md Art. 1).

Measurement/inference split at sentence level: **measured** — 34.4, 31.27, 39.53, 36.76 µs and the
bandwidth utilisation figures, on one unnamed part at one shape. **not measured** — the 20 KB knee
itself, the "< 5 % overhead" figure, and the four named components of the fixed cost.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The claim is a curve, so
the procedure measures a curve rather than a point.

Arm 1 — the knee. A standalone GM→L1 copy kernel, one transfer per iteration, transfer size swept
over `1, 2, 4, 8, 12, 16, 20, 24, 32, 48, 64, 128 KB` at fixed total bytes moved (so the *count*
falls as the size rises). Record achieved GB/s and cycles per byte at each point. The knee, if it
exists, is where cycles/byte flattens. Report the whole curve, not a threshold — a threshold is what
upstream already asserts, and a curve is what would let a downstream skill route a case that sits at
14 KB.

Arm 2 — the fixed cost, extracted rather than assumed. Fit the Arm 1 data to
`time = a + b × bytes` per transfer. `a` is the per-transfer overhead upstream describes and never
quantifies; `b⁻¹` is the achievable bandwidth. Upstream's "< 5 % at 20 KB" is then a checkable
statement: `a / (a + b × 20480) < 0.05`.

Arm 3 — reproduce the application. Two builds of the family's MXFP4 matmul at `[128, 8192, 4096]`
with `SCALE_L1_BUFFER_NUM ∈ {2, 16}`, collecting MTE2 segment time, task time and MTE2 bandwidth
utilisation (`msprof --aic-metrics=PipeUtilization`). Also echo the actual per-transfer scale byte
count from the kernel, which is what settles the `1024 B` versus `4096 B` disagreement in §3
without needing to interpret it.

Arm 4 — the false-bound discriminator, which is what the entry is used for. On one shape below the
knee and one above it, record MTE2 busy and MTE2 bandwidth utilisation together. Upstream's routing
rule requires the pair to separate the two regimes; if busy alone separates them just as well, the
two-number rule is unnecessary and the entry is simplified.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, beside
every point on the curve. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard if the die moved. Refuses to assume: that a free die stays free; that a die
may be substituted; that the L2 state is comparable between points — each size is run both
cold-L2 and warm-L2 and both are reported, because a residency effect would masquerade as a knee
(`950:0270` records that L2 residency, not HBM peak, sets effective GM bandwidth below a measured
knee, which is a different knee and must not be confused with this one).

## 5 · Checker — acceptance declared before the run
Verdict `knee_bytes` = the transfer size at which Arm 1's cycles-per-byte first comes within 5 % of
its asymptote. Declared before the run: pass is `knee_bytes ∈ [16 KB, 24 KB]`, i.e. upstream's
"约 20 KB" read with a ±20 % band, stated now so it cannot be widened afterwards. The OVERTURN fires
iff the curve has no identifiable asymptote-approach point, or `knee_bytes` falls outside that band.

Verdict `overhead_share_20k` = `a / (a + b × 20480)` from Arm 2. Upstream's "< 5 %" is a separate
pass condition and may fail while `knee_bytes` passes — the two are reported separately for exactly
that reason.

Verdict `bw_gain` = Arm 3's bandwidth utilisation delta, against upstream's +25 pp.
Verdict `scale_bytes_before` = Arm 3's echoed per-transfer scale byte count at
`SCALE_L1_BUFFER_NUM = 2`, which resolves `C-950bp-005` as a matter of fact.

The exit code is not the verdict. Three guards. First, Arm 1's kernel writes a checksum of what it
copied and the checksum is verified: a copy loop that is optimised into nothing produces a
magnificent bandwidth curve. Second — the input that makes this checker go red — Arm 1 is repeated
with the total bytes moved doubled at every size. Achieved GB/s **must** be unchanged at every point
(bandwidth is a rate) while total time **must** double. If GB/s moves, the measurement is
size-dependent in a way the model does not capture and the whole curve is void. That is a planted
positive the checker has to find, not a clean line it hopes to read. Third, every point carries its
floor and its L2 state; a knee visible only in the warm-L2 series is reported as an L2 effect, not
as an MTE2 issue cost.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. 20 KB, "< 5 %", 34.4, 31.27,
39.53, 36.76 µs and the 50–60 % → 80 %+ utilisation figures are upstream's; this book has copied no
bytes and read no counter.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Upstream supplies no bandwidth-versus-size sweep anywhere, so the
20 KB knee is an assertion with a mechanism story attached, not a measured curve; the "< 5 %"
amortisation figure has no derivation and the four named cost components (address setup, burst
descriptor, DMA channel configuration) are never separated or sized. The one measurement given is
for a single shape on an unnamed part with no repeat count, variance, tool or CANN pin. The table's
"before" cell (1024 B) contradicts the file's own worked ladder (4096 B) for the same configuration,
so the "+10×" figure is not carried by this entry at all. The threshold is stated for GM→L1 (MTE2)
and nothing here establishes it for UB↔GM or for MTE3. The `< 32 / 256 / 4096 / 65536` byte bands in
the shelf's `common/datacopy_optimization_design.md` are explicitly Ascend 910B-attributed and are
neither carried nor contradicted here (RULES.md Art. 1). BOARD is `family-claimed(unverified)`: no file in
this family names a chip (`0347`). Nothing transfers to the other book.
