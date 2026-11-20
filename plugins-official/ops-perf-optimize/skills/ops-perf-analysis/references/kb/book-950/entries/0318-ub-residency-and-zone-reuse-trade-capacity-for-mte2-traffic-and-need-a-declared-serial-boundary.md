```
ID:        0318-ub-residency-and-zone-reuse-trade-capacity-for-mte2-traffic-and-need-a-declared-serial-boundary
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:18-21 —
           "| **常驻复用** | 跨整个 Process 或多层循环 | 循环外搬入，循环内只读/读写 | weight、
           gamma、scale 小参数 | | **分时复用** | 单次 Process 内多阶段串行 | 前一阶段结束，后一
           阶段覆盖 | RmsNorm→RoPE、SoftMax→后处理 |"
SOURCE:    same file:145 — "UB 临时 buffer 总量从 `sum(stage_buffers)` 降为
           `max(concurrent_buffers)`" ; :296-300 — "1. **常驻 buffer 压缩主数据 tile 空间** ...
           2. **TBuf/VECCALC 不受队列同步保护**：需要手动使用 PipeBarrier 或明确阶段边界保证一致性。
           3. **分时复用需严格串行边界**：各阶段必须具备严格的串行边界，错误判断生命周期会导致后续
           阶段覆盖仍在使用的数据。" ; :309 — "6. **后续阶段重叠流水时需重算 zone**：若后续优化把
           串行阶段改造成重叠流水，原有 zone reuse 方案可能失效。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured operator on a named 950 board in which making a loop-invariant parameter
           UB-resident does not reduce MTE2 bytes moved — the repeated fetches would then not be
           happening, and the technique's premise would be false for that shape.
```

# 0318 · UB residency and zone reuse trade capacity for MTE2 traffic and need a declared serial boundary

## 1 · Claim
Upstream asserts two distinct on-chip reuse strategies with different lifetimes and different
failure modes. **Residency** (`常驻复用`): a small loop-invariant parameter — weight, gamma, scale —
is fetched into UB once at `Process` entry and read from UB for the operator's whole life, so the
per-tile MTE2 fetch of it disappears; upstream states the saving as a factor of `N`, the tile or
loop count. **Zone reuse** (`分时复用`): within one `Process`, serial stages share one TBuf carved
into zones, a later stage overwriting an earlier stage's dead data, so total temporary UB falls from
`sum(stage_buffers)` to `max(concurrent_buffers)`; upstream states the reduction as 30–60 %.
Upstream asserts three constraints. Resident buffers permanently shrink the space available to the
main data tile and its double buffering. `TBuf`/`VECCALC` allocations are **not** protected by queue
synchronisation, so a manual `PipeBarrier` or an explicit stage boundary is required. Zone reuse
requires strictly serial stage boundaries, and mis-judging a lifetime lets a later stage overwrite
live data. Upstream asserts a fourth, which is the one an optimiser will hit later: if a subsequent
change overlaps the previously serial stages into a pipeline, the zone plan may be invalidated. Not
established here.

## 2 · The wrong branch this removes
Both techniques look like pure wins and neither is.

Residency's cost is a permanent reduction of the tile budget. An agent that makes `weight`, `gamma`
and `scale` all resident has not moved 3 small buffers off the critical path, it has removed their
combined size from every tile computation for the rest of the kernel — and under double buffering
that removal is doubled in effect, because the tile budget is halved to begin with (`950:0018`).
The failure surfaces as `InitBuffer` refusing, or as a tile so small that per-tile fixed cost
becomes the bottleneck (`950:0017`). Upstream's own checklist item is the arithmetic:
`常驻 buffer 大小 + 主 tile + 双缓冲 ≤ UB 容量`.

Zone reuse's cost is a correctness obligation with no compiler support. Queue-managed tensors
(`TQue`) carry their own producer/consumer synchronisation; `TBuf`/`VECCALC` does not, and upstream
says so directly. So an agent that carves a TBuf into zones has taken on the job the queue was
doing, and the failure mode is a silent overwrite of live data — not a fault, not a hang, a wrong
number. The signature upstream gives is `分时复用数据被覆盖 | 阶段边界判断错误`.

The fourth constraint is the one that costs later rather than now, and it is worth an agent's
attention because it inverts the usual advice. Zone reuse is *only* valid while the stages are
serial. The next optimisation an agent reaches for on a memory-bound operator is overlapping those
stages — and doing so silently invalidates the zone plan that the previous optimisation installed.
Two individually correct optimisations compose into a wrong kernel. Upstream states this and it is
the reason the entry carries the constraint rather than the recipe.

## 3 · Ground / Source
The two strategies, `common/ub_resident_design.md:16-21`:

```
### 2.1 常驻复用 vs 分时复用

| 策略类型 | 数据生命周期 | 复用方式 | 典型场景 |
| **常驻复用** | 跨整个 Process 或多层循环 | 循环外搬入，循环内只读/读写 | weight、gamma、scale 小参数 |
| **分时复用** | 单次 Process 内多阶段串行 | 前一阶段结束，后一阶段覆盖 | RmsNorm→RoPE、SoftMax→后处理 |
```

The benefit table, `:7-12`, which is where the two numbers come from:

```
| 指标 | naive | optimized | 收益 |
| 参数搬运次数 | 每 tile/loop 1 次 | Process 生命周期仅 1 次 | 搬运次数降低 N 倍（N=tile/loop 数） |
| 临时 buffer 总量 | `sum(stage_buffers)` | `max(concurrent_buffers)` | UB 占用降低 30-60% |
| Vector 单 Repeat 周期 | 多拍（bank 冲突，因芯片而异） | 1-2 拍（无冲突） | 计算速度提升数倍 |
| 代码复杂度 | 低 | 中（需生命周期管理） | 常驻 buffer + 分区 offset |
```

Row 1 is a *definition* rather than a measurement — if a parameter is fetched once instead of `N`
times, the count falls by `N` by construction. Rows 2 and 3 are unscoped ranges with no case, no
shape, no dtype and no board; `30-60%` and `数倍` are the class this book records as
measured-unscoped at best. None of the four rows carries a board or a tool.

The zone mechanism, `:143-145`:

```
分时复用：单块 TBuf 按阶段划分为多个 zone。前一阶段（如 RmsNorm）使用 zone0/1/2 计算完成后数据
失效，后一阶段（如 RoPE）直接复用同一物理空间的 zone0/1/2，无需额外分配 buffer。UB 临时 buffer
总量从 `sum(stage_buffers)` 降为 `max(concurrent_buffers)`。
```

with the worked offsets at `:247-261`: zones at `0`, `rows * headSize` and `rows * headSize * 2`,
re-aliased by name in the second stage.

The four constraints, `:296-309`, quoted in the header. Note the exact wording of the second:
`TBuf/VECCALC 不受队列同步保护` — this is a statement about the *allocation kind*, not about the
tensor, and it is the load-bearing sentence in the whole file for correctness. `950:0053` records,
from the other shelf, that buffer-reuse safety on the queue path rests on a TQue FIFO order no
document guarantees; the two together say that neither path has a written guarantee, from opposite
directions.

The self-check list, `:337-342`, is unusually good for this shelf — four of its six items can
actually fail (the UB budget inequality, the serial-boundary check, the DataBlock placement check
and the naive-comparison check), which is the property `950:0002`'s neighbourhood records most
upstream checklists lack.

The FP32 accumulator constraint, `:318` and `:341` — `累加器精度不足 | FP16 累加溢出 | 常驻累加器
使用 FP32 精度` — is a residency-specific consequence: a resident accumulator lives for the whole
`Process`, so it accumulates over the whole problem, and the dtype that was adequate per tile may
not be.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — residency's claimed saving, measured as bytes. One operator with a loop-invariant `gamma`,
built twice: fetched per tile, and fetched once at `Process` entry. Primary readout is **MTE2 bytes
moved**, not time — the claim is that `N−1` fetches stop happening, and byte count says so directly.
Secondary: kernel time, MTE2 segment, and the largest tile each build can allocate. That last one is
the cost side and must be reported with the benefit; a residency win quoted without the tile
shrinkage is half a result.

Arm 2 — the tile-budget trade, swept. Vary the resident buffer's size from 0 to the point where
`InitBuffer` refuses, recording at each point the maximum tile and the kernel time. The curve has a
maximum somewhere, and *where* is the number upstream's checklist inequality cannot supply.

Arm 3 — zone reuse's total, and its correctness. Build a two-stage operator (upstream's
RmsNorm→RoPE shape) three ways: independent buffers; zoned with an explicit `PipeBarrier` at the
stage boundary; zoned with the barrier removed. Record total UB requested for each, and compare all
three elementwise against a CPU reference. The third build is expected to be wrong, and its being
wrong is what makes the second build's correctness meaningful.

Arm 4 — the composition trap, retained whatever it shows. Take the zoned build and overlap the two
stages (issue stage 2's first tile while stage 1's last is still live). Upstream predicts the zone
plan is invalidated. If the output stays correct, the stages were not sharing what the zone map says
they share, and the entry is corrected in place.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median. Device
selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind
only on three idle samples; re-sample after; discard if the die moved. Refuses to assume: that a
free die stays free; that a die may be substituted; that UB capacity is a literal — it is queried
(`950:0207`, `950:0209`) and echoed beside every budget figure, because both arms are inequalities
against it; that a `PipeBarrier` present in the source is present in the binary (Arm 3's builds are
disassembled and diffed, since a null result between arms 3b and 3c is unattributable otherwise).

## 5 · Checker — acceptance declared before the run
Verdict `byte_drop` = (per-tile-fetch MTE2 bytes − resident MTE2 bytes) / per-tile bytes, with the
floor. Declared before the run: pass is `byte_drop` positive and consistent with the parameter's
size times `N−1`. The OVERTURN fires iff `byte_drop` is inside the floor.

Verdict `tile_cost` = (max tile without residency − max tile with) in bytes, reported
unconditionally and with no pass condition. It exists so that no downstream recommendation can quote
`byte_drop` without it.

Verdict `ub_total_drop` = (independent-buffer UB − zoned UB) / independent UB, against upstream's
30–60 %.

Verdict `zone_correct` = true iff build 3b matches the reference and build 3c does not.

The exit code is not the verdict. Three guards. First, every build is compared elementwise against a
CPU reference over the whole output, not a sampled tile: an overwritten zone corrupts a region, and
region-shaped errors survive spot checks. Second — the input that makes this checker go red — build
3c (zoned, barrier removed) is the planted positive: it **must** fail the precision comparison. If
3c passes, the two stages are not actually sharing the zone, `zone_correct` is meaningless, and
Arm 3's green on 3b establishes nothing. A correctness study whose only outcome is "all builds
passed" cannot distinguish a safe design from an inert experiment. Third, no byte figure is reported
without the echoed UB capacity and the floor.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `30-60%`, the `N 倍` and
the `数倍` are upstream's unscoped figures; no operator was built, no byte was counted, and no zone
was overwritten.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Two of upstream's three benefit figures are unscoped ranges with
no shape, dtype, board or tool (`30-60%`, `数倍`) and the third is true by construction (`N 倍`), so
this entry carries a mechanism and a set of constraints, not a magnitude — a consuming skill must
not attach a percentage to it. It does not establish the *cost* side either: the tile-budget
reduction is stated as an inequality to satisfy, never as a measured curve, and §4 Arm 2 exists
because the optimum is unknown. The `TBuf/VECCALC 不受队列同步保护` statement is upstream's
assertion about an allocation kind and is not verified against any header or any build here.
Upstream's file is chip-mixed: its bank material is scoped (`0314`–`0316`) but its residency and
zone material names no architecture at all, and the family it sits under (`公共优化能力`) has no
適用架構 marking, so the routing into this book rests on the mechanism vocabulary and on the file's
own DAV_3510 rows — recorded as a routing judgement, not a certainty. BOARD is
`family-claimed(unverified)`. Nothing transfers to the other book (RULES.md Art. 1).
