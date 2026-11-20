```
ID:        0348-depthwise-convolution-is-scalar-sensitive-because-its-single-mmad-covers-a-small-k-and-standard-conv2d-is-not
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/conv/conv_common_perf_experience.md:30 —
           "标准 Conv2D 的单次 Mmad 的 kL0 较大（典型值 256+），Mmad 执行时间长，Scalar 开销占比低，
           对 Scalar 优化不敏感。" ; :36-38 — "1. **Weight 全载**：每组 weight 的 `[cout/groups,
           cin/groups, kh, kw]` 在 `SetupGroup` 阶段一次性加载到 L1 ... 消除了 `kAL1Iter`、
           `khAL1Iter`、`kwAL1Iter` 三个循环轴 2. **单组计算量小**：`cin/groups = 1`，通过 enlarge
           将多组拼接后 `kTotal = cinAligned × kh × kW`（典型值 144），单次 `kL0`（典型值 16-48）远
           小于标准 Conv2D（典型值 256+） 3. **N 维固定**：`coutOpt = 16`（enlarge 后），`nL0 = 16`"
SOURCE:    same file:54-58 — "由于单次 Mmad 的 kL0 很小（16-48），一次最内轴 k 循环的 Mmad 执行时间
           可能只有几微秒，非常容易被 Scalar 指令打断 ... - **干掉 TQue**：内循环中用静态构造或
           TBuf + 手动 flag 替代 TQue，消除 buffer 状态机轮转和 event ID 动态分配的 Scalar 开销"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured DepthwiseConv2D on a named 950 board where replacing the inner loop's `TQue`
           with a statically constructed tensor leaves scalar time and kernel time unchanged outside
           the run spread — the scalar sensitivity would then not follow from the small `kL0`, and
           the family's whole optimisation direction would need re-deriving.
```

# 0348 · Depthwise convolution is scalar-sensitive because its single Mmad covers a small K, and standard Conv2D is not

## 1 · Claim
Upstream asserts that convolution maps to a matrix multiply with M as the output spatial extent
(`Ho × Wo`), N as the output channel count, and K as `Cin × kH × kW`, and that the variants differ
mainly in K's composition and size — which then determines the loop-axis count, the work per Mmad,
and the share of time spent on scalar instructions. Upstream asserts that standard Conv2D has a
large per-Mmad `kL0` (typically 256+), long Mmad execution, a low scalar share, and is therefore
insensitive to scalar optimisation, with 8-plus loop axes. Upstream asserts three structural
properties of DepthwiseConv2D that follow from `groups = C`: each group's weight
`[cout/groups, cin/groups, kh, kw]` loads into L1 once in `SetupGroup` and is reused for the whole
group, removing the `kAL1Iter`, `khAL1Iter` and `kwAL1Iter` axes; `cin/groups = 1` makes the
per-group work small, so after enlarging, `kTotal = cinAligned × kh × kw` (typically 144) and a
single `kL0` is typically 16–48 against 256+; and N is fixed at `coutOpt = 16` after enlarge, so no N
split loop is needed — leaving four axes. Upstream asserts the consequence: with `kL0` at 16–48 the
innermost Mmad may run only a few microseconds and is easily interrupted by scalar instructions, so
depthwise must minimise scalar work by removing `TQue` from the inner loop in favour of static
construction or a `TBuf` with manual flags, copying frequently-read tiling fields into locals,
precomputing and caching the `Load3D` configuration registers, and eliminating unnecessary loop
levels. Not established here.

## 2 · The wrong branch this removes
The two convolutions look like one operator family with a parameter, and the shelf ships two
independent template sets for them (`0349`). An agent that carries standard Conv2D's optimisation
experience onto depthwise will target data movement and Cube utilisation — the right targets when a
single Mmad runs long — and will find the scalar pipe is what is actually costing it. The reverse
carry is equally available: applying depthwise's scalar-shedding work to standard Conv2D, where
upstream states directly it is not sensitive, spends effort on a pipe whose share is low.

The discriminator upstream supplies is a *derivable* number rather than a measurement: `kL0`. It is
computable from the operator's own shape before any profile exists — `Cin × kH × kW` for standard,
`cinAligned × kh × kw` after enlarge for depthwise — and the two regimes sit an order of magnitude
apart. That is why the entry carries the derivation and not only the advice: a routing rule that can
be evaluated at tiling time is worth more than one that needs a trace.

The second wrong branch is `TQue` itself, and it is uncomfortable. `TQue` is the framework's
correctness mechanism — it carries the producer/consumer synchronisation that `TBuf`/`VECCALC` does
not (`0318` §2, and `950:0053`). Removing it from an inner loop moves that obligation onto the
author's manual flags. Upstream states the *benefit* — no buffer state-machine rotation, no dynamic
event-id allocation — and does not restate the cost, so an agent reading this file alone learns half
of a trade. The cost is the same one `0335`'s static-`LocalTensor` technique carries and is stated
there: hand-computed offsets need an explicit non-overlap check.

The third is the enlarge itself. `coutOpt = 16` and `kTotal ≈ 144` are not natural properties of the
operator; they are consequences of packing multiple groups together to meet the Cube's K alignment
(`0349`). An agent that reads 16 and 144 as depthwise constants will not understand why they change
when the enlarge factor does.

## 3 · Ground / Source
The mapping and the K-composition argument, `conv/conv_common_perf_experience.md:5-11`:

```
卷积类算子的核心计算是：对每个输出位置，将一个局部感受野内的输入与卷积核做加权求和。在 NPU Cube
路径上，这被映射为矩阵乘法：

- **M 维**：输出空间维度（Ho × Wo），即每个输出点
- **N 维**：输出通道维度（Cout）
- **K 维**：输入通道 × 卷积核尺寸（Cin × kH × kW）

不同卷积变体的差异主要体现在 K 维的构成和规模上，进而影响循环轴数量、单次 Mmad 计算量、Scalar
开销占比。
```

The two loop nests, `:17-28` and `:42-50`. Standard Conv2D:

```
for groupOpt / for batch / for kAL1Iter / for khAL1Iter / for kwAL1Iter
  / for mAL1Iter / for mL0Iter / for nL0Iter / for kL0Iter
```

Depthwise:

```
for group / for batch / for mAL1Iter / for mL0Iter / for nL0Iter / for kL0Iter
```

Six levels against nine as written, and upstream labels them `4 层` and `8+ 层` — counting the
axes that vary rather than the `for` statements, since `nL0Iter` `通常只1次` and `group`/`batch` are
outer. The label and the code disagree on the count; the *difference* (three axes removed:
`kAL1Iter`, `khAL1Iter`, `kwAL1Iter`) is stated identically by both and is the load-bearing part.
Recorded in `harvest/standing/950-bp.md`.

The three depthwise properties, `:36-38`, quoted in the header. Re-derived where possible:
`kTotal = cinAligned × kh × kw`; at `cinAligned = 16` and a 3×3 kernel, `16 × 9 = 144` ✓ matching
upstream's typical value, which also identifies `cinAligned` as 16 — the Cube's K0 for fp16
(`0349`) — even though upstream never says so. `kL0 ∈ [16, 48]` against `kTotal = 144` gives 9, 3 or
`144/kL0` inner iterations; upstream's own loop comment says `kTotal/kL0 次，如 9 次` (`:49`),
consistent with `kL0 = 16`.

The sensitivity claim and its three remedies, `:52-58`:

```
### 1.3 Scalar 敏感性

由于单次 Mmad 的 kL0 很小（16-48），一次最内轴 k 循环的 Mmad 执行时间可能只有几微秒，非常容易被
Scalar 指令打断。标准 Conv2D 的单次 Mmad 时间长（kL0=256），Scalar 开销占比低；DepthwiseConv2D
必须通过以下手段最小化 Scalar 计算：

- **干掉 TQue**：内循环中用静态构造或 TBuf + 手动 flag 替代 TQue，消除 buffer 状态机轮转和
  event ID 动态分配的 Scalar 开销
- **减小全局变量访问**：将 tiling 中频繁访问的字段拷贝到局部变量，减少 GM Load 指令；Load3D
  配置寄存器预计算并缓存
- **固定循环轴**：消除不必要的循环层级，减少循环变量维护和地址计算
```

The routing table that summarises it, `conv/guide.md:51-55`, gives `scalar_minimization` the
condition `单次 Mmad 短（kL0 ≤ 48）` — the same 48 as the range's upper end, now used as a threshold.
So the family does state a numeric gate, in the index rather than in the analysis.

What upstream never supplies: a single timing. `几微秒` is the only duration in the section, applied
to an Mmad and not to any measured case, and there is no before/after for any of the three remedies.
`典型值` prefixes every number (256+, 144, 16-48, 16), marking them as representative rather than
measured.

The two families are served by two independent template sets — `conv2d_kernel.template` under
`__cube__`, `dwconv2d_kernel.template` under `__mix__(1,2)` — and `conv/guide.md:45` states
`两套模板互相独立；Host 按问题形态选一套落地`, which is the structural expression of the same split.

Nothing here is measured.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — the sensitivity claim, as a curve rather than a pair. Build one depthwise-shaped operator and
one standard-Conv2D-shaped operator and sweep `kL0` across `16, 32, 48, 64, 128, 256` by varying the
channel and kernel extents, recording per point: scalar pipe share, Mmad duration, and kernel time.
Upstream's claim predicts scalar share falling as `kL0` rises, with the two operators landing at
opposite ends of one curve rather than being two phenomena. If they fall on one curve, `kL0` is the
discriminator upstream says it is and the index's `kL0 ≤ 48` gate is locatable on it.

Arm 2 — the `TQue` removal, attributed. Three builds of the depthwise inner loop: `TQue`; static
construction; `TBuf` with manual flags. Record scalar instruction count (disassembly), scalar pipe
share, and kernel time. Upstream groups the two replacements; they have different correctness costs
and should be attributed separately.

Arm 3 — the other two remedies, separately. Tiling-field localisation alone, and `Load3D`
configuration precompute alone. Upstream lists three remedies and measures none; a consuming skill
that must pick one has no basis today.

Arm 4 — the correctness cost the source omits. Build the `TBuf` variant with a deliberately
overlapping manual offset and confirm it is caught. See §5.

Arm 5 — the standard-Conv2D negative arm, retained whatever it shows. Apply Arm 2's best variant to
the standard Conv2D operator, where upstream predicts little benefit. An arm that does not bite is
recorded as an arm that did not bite.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, with
`0327`'s same-path sibling check applied before any table is read. Device selection:
`npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three
idle samples; re-sample after; discard the case if the die moved. Refuses to assume: that a free die
stays free; that a die may be substituted; that `kL0` is what the host tiling says — it is echoed
from the kernel, since the whole curve is indexed by it; that `cinAligned` is 16 (it is echoed too,
because §3's `144` re-derivation depends on it and upstream never states it).

## 5 · Checker — acceptance declared before the run
Verdict `scalar_share(kL0)` = Arm 1's curve, with the floor at every point. Declared before the run:
upstream is **supported** iff the curve is monotonically decreasing in `kL0` and the two operators
lie on it rather than beside it. Two separate curves would mean `kL0` is not the discriminator and
something else distinguishes the variants — which would be a more interesting result and would
correct the entry in place.

Verdict `gate_location` = the `kL0` at which scalar share falls below a declared 20 % — chosen now,
before the run, and compared against the index's `kL0 ≤ 48`.

Verdict `tque_gain[variant]` for Arm 2's two replacements, each with the floor.
Verdict `remedy_gain[i]` for Arm 3's two, each with the floor.
Verdict `standard_null` = true iff Arm 5's gain is inside the floor.

The exit code is not the verdict. Three guards.

First, every build is compared elementwise against a CPU reference over the whole output. Removing
`TQue` transfers producer/consumer synchronisation to manual flags, and a missing flag produces a
race whose output is wrong intermittently — so each build is run repeatedly and compared every time,
not once.

Second — the input that makes this checker go red — Arm 4's deliberately overlapping `TBuf` offset
**must** fail the comparison. If it passes, the comparison is not covering the buffers the technique
touches and every green in Arm 2 is void for the class of defect the technique introduces. That
fixture is mandatory because the whole point of removing `TQue` is to remove a safety mechanism, and
a checker that cannot detect its absence has not tested the trade.

Third, `scalar_share` is reported alongside kernel time at every point, never instead of it. The
entry's subject is precisely a case where one pipe's share and the wall clock can move
independently, and reporting either alone reproduces the confound.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. `256+`, `144`, `16-48`, `16`
and `几微秒` are upstream's typical values, every one of them prefixed `典型值` or hedged; no
convolution was built, no Mmad was timed, and no scalar share was read. The `16 × 9 = 144`
re-derivation in §3 is arithmetic on paper.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. **Upstream supplies no timing at all** for this family — not for
either operator, not for any of the three remedies — so the entry carries a mechanism and a routing
argument with no magnitude, and a consuming skill must not attach a benefit figure to any of it.
Every number is marked `典型值`: 256+, 144, 16–48 and 16 are representative shapes, not measured
constants, and none carries a case. The scalar-sensitivity claim is an argument from Mmad duration,
not an observation of scalar share. The `kL0 ≤ 48` gate appears in the family index and is derived
nowhere. The three remedies are listed and never attributed individually. The correctness cost of
removing `TQue` is not stated by this file and is carried here from `0318`/`0335`, which are
different subjects. `cinAligned = 16` is this book's inference from the `144` arithmetic and the
fp16 K0, not upstream's statement. The loop-axis counts in the prose (`4 层`, `8+ 层`) disagree with
the code blocks beneath them. BOARD is `family-claimed(unverified)`: the Convolution family is marked
DAV_3510 in the shelf index (`0347`'s species) and no file in it names a chip. Nothing transfers to
the other book (RULES.md Art. 1).
