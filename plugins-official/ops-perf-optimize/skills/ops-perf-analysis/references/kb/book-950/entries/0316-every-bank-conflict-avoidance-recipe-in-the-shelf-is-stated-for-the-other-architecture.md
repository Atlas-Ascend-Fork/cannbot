```
ID:        0316-every-bank-conflict-avoidance-recipe-in-the-shelf-is-stated-for-the-other-architecture
LABEL:     boundary
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:96 —
           "**规避**：确保 src 和 dst 的起始地址不在同一 bank。对于 220x，通常给中间 buffer 增加
           padding 使地址错开至少一个 bank。" ; :130-137 — "**规避（220x 官方推荐）**：
           pipe.InitBuffer(inQueueX, 1, 4096 * sizeof(float) + 256); pipe.InitBuffer(inQueueY, 1,
           64 * 1024 - (4096 * sizeof(float) + 256)); pipe.InitBuffer(outQueueZ, 1, 4096 *
           sizeof(float));" ; :108 — "**规避**：改为 `blk_stride = 1`（连续读），通过
           `dst_gap/src_gap` 控制跨 Repeat 的地址增量。"
SOURCE:    ops/ascendc-performance-best-practices/reference/simt/optimization-guide.md:233 —
           "不要固定使用末维 `+1` 等单一 padding 规则。应根据 Ascend UB bank/sub-bank 映射分析
           stride，再选择 padding、奇数 stride 或分块布局，并用 `ResourceConflictRatio.csv` 中的
           bank conflict 指标验证。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured 950 run in which the 220x recipe verbatim — 256 B padding after the first
           buffer, second buffer sized to reach a 64 KB boundary — removes a bank conflict that a
           DAV_3510-derived padding does not, at the same shape. The recipes would then transfer
           after all, and this entry's caution would be the wrong call.
```

# 0316 · Every bank-conflict avoidance recipe in the shelf is stated for the other architecture

## 1 · Claim
Upstream asserts three avoidance techniques for UB bank conflicts — insert 256 B of padding so
adjacent buffers start in different banks; size a buffer so the next one lands past a bank-group
boundary; rewrite a Vector call from `blk_stride = 16` (or 8) to `blk_stride = 1` and carry the
inter-repeat increment in `dst_gap`/`src_gap` — and states each of them, with its worked constants,
for NPU 220x. The one worked `InitBuffer` triple is labelled `220x 官方推荐`. Upstream states no
DAV_3510 padding constant, no DAV_3510 buffer sizing, and no DAV_3510 stride rewrite anywhere in the
file. Separately, in the shelf's SIMT guide, upstream asserts the general form of the rule and warns
against exactly the transfer this file invites: do not apply a fixed padding recipe, analyse the
target's bank/sub-bank mapping and validate with the `ResourceConflictRatio.csv` bank-conflict
metric. Not established here.

## 2 · The wrong branch this removes
The document reads as a bank-conflict manual. An agent that has just learned DAV_3510's geometry
(`0314`) and DAV_3510's conflict rules (`0315`) reaches §2.2.5 for the fix and finds three, all with
numbers, none of them for its part. The numbers are the wrong ones, and each is wrong for a
different reason:

- **256 B padding.** On 220x that is two 128-row banks' worth of offset — it moves the following
  buffer by 8 rows, `8 mod 16 ≠ 0`, so it breaks group aliasing. On DAV_3510 a bank is 16 KB
  (`0314`); 256 B does not move the buffer out of its bank at all, let alone its group. The quantum
  that breaks group aliasing on DAV_3510 is a function of a 16 KB bank and 8 groups, not of 4 KB
  and 16.
- **`64 * 1024 - (4096 * sizeof(float) + 256)`.** The `64 * 1024` is a 220x sixteen-bank boundary
  (`16 × 4 KB`). On DAV_3510, sixteen banks is 256 KB — the whole buffer — so the expression is not
  merely mis-tuned, it is meaningless.
- **`blk_stride = 1`.** This one is generation-independent in *form*: contiguous DataBlocks land in
  consecutive banks on either part. But upstream's justification is arithmetic on 16 groups
  (`bank 差 = 16，16 % 16 = 0`), and on DAV_3510 the aliasing strides are multiples of 8. So the
  recipe survives the transfer and its *derivation* does not, which means an agent cannot tell from
  the text which of the three is safe to carry.

The second wrong branch is the opposite over-correction: treating the whole section as inapplicable
and skipping bank conflicts on DAV_3510 entirely. The *phenomenon* is stated for both parts
(`0315`); only the constants are 220x's.

The entry's operational content is therefore a rule, not a number: **on DAV_3510, derive the padding
from the measured geometry and confirm it with the conflict counter — never port a constant.** That
is what the SIMT guide already says in general terms, and this entry is where the two halves meet.

## 3 · Ground / Source
The three recipes, `common/ub_resident_design.md:89-137`.

Scenario 1, read-write, `:89-96`:

```
**场景 1：读写冲突 —— src 与 dst 落在同一 bank**

// 假设 x 起始地址在 bank0，y 起始地址也在 bank0（地址差为 bank size 的整数倍）
Add(dst, src, src2, ...);  // src 读 bank0，dst 写 bank0，读写冲突

**规避**：确保 src 和 dst 的起始地址不在同一 bank。对于 220x，通常给中间 buffer 增加 padding 使
地址错开至少一个 bank。
```

Scenario 2, write-write, `:98-108`, with the stride rewrite:

```
// 220x 上 blk_stride=16：8 个 DataBlock 全部落入同一 bank group，8 拍完成
Adds(dst, src, scalar, MASK, 1, {1, 16, 1, 16});

// 220x 上 blk_stride=8：block0 和 block2 落入同一 bank group，4 拍完成
Adds(dst, src, scalar, MASK, 1, {1, 8, 1, 8});

**规避**：改为 `blk_stride = 1`（连续读），通过 `dst_gap/src_gap` 控制跨 Repeat 的地址增量。
```

Scenario 4, the full worked triple, `:119-137`:

```
**场景 4：连续分配多个 buffer，地址周期性重叠**

// 220x 原始实现：x/y/z 连续分配，起始地址差为 0x4000（16KB）
// x: bank0, y: bank0（地址差 16KB = 4×bank size），z: bank0
pipe.InitBuffer(inQueueX, 1, 4096 * sizeof(float));
pipe.InitBuffer(inQueueY, 1, 4096 * sizeof(float));
pipe.InitBuffer(outQueueZ, 1, 4096 * sizeof(float));

**规避（220x 官方推荐）**：
// x 多申请 256B，避免一个 Repeat 内 x 和 y 同时读同一 bank group
// y 多申请空间，确保 z 不会和 x/y 落入同一个 bank
pipe.InitBuffer(inQueueX, 1, 4096 * sizeof(float) + 256);
pipe.InitBuffer(inQueueY, 1, 64 * 1024 - (4096 * sizeof(float) + 256));
pipe.InitBuffer(outQueueZ, 1, 4096 * sizeof(float));
```

Re-derived on 220x's geometry: `4096 × 4 = 16384 B = 16 KB = 4 × 4 KB banks`, so consecutive
buffers start 4 banks apart and `4 × 4 = 16 ≡ 0 (mod 16)` puts all three in group 0 ✓ — the aliasing
upstream describes. On DAV_3510's geometry (`0314`: 16 KB banks, 8 groups) the same three buffers
start **1 bank** apart, `1 mod 8 ≠ 0`, and there is no group aliasing to break. The recipe solves a
problem the target part does not have, and the "fix" perturbs a layout that was already clean.

The generalised form of the rule, from the shelf's SIMT guide, `simt/optimization-guide.md:233`:

```
不要固定使用末维 `+1` 等单一 padding 规则。应根据 Ascend UB bank/sub-bank 映射分析 stride，再选择
padding、奇数 stride 或分块布局，并用 `ResourceConflictRatio.csv` 中的 bank conflict 指标验证。
```

Two files in one repo are one origin (RULES.md Art. 3), so the SIMT guide does not corroborate the
resident-buffer file; it is quoted because it is the same repository's own instruction *not* to do
what its neighbour's worked example invites.

The verification instrument is named in three places — `:81` (`msProf 资源冲突占比分析`), `:317`
(`使用 msProf 采集资源冲突占比确认`), and the SIMT guide's `ResourceConflictRatio.csv` — and
`950:0052`'s neighbourhood records that these ratios exist only on device. So the shelf's own
prescribed check cannot be run in a simulator, which is worth carrying into any skill that repeats
the advice.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The entry's claim is
negative — that the constants do not transfer — so the procedure must be able to show a transfer if
one exists, not merely fail to find one.

Baseline: the exact three-buffer `Add` case upstream describes, built on DAV_3510 with the
*unpadded* allocation. Record conflict ratio and cycles per repeat. If the baseline is already
clean, that is itself the finding — the 220x pathology does not reproduce, which is what §3's
arithmetic predicts — and the remaining arms measure whether the "fixes" make it worse.

Arm A — the ported recipe, verbatim: `+256` on the first buffer and
`64 * 1024 - (4096 * sizeof(float) + 256)` on the second. Record the same two quantities.

Arm B — a DAV_3510-derived padding. Compute, from the geometry `0314` establishes, the smallest
offset that moves the second buffer into a different bank group, and apply that instead. Record.

Arm C — a swept padding, so neither A nor B is privileged: pad the first buffer by
`0, 256 B, 1 KB, 4 KB, 8 KB, 16 KB, 32 KB` and plot conflict ratio against padding. The minimum of
that curve is the answer, and A and B are two points on it. This is the arm that makes the study
honest — it can show the 256 B point winning, which would fire the OVERTURN.

Arm D — the stride rewrite, which §2 argues survives the port. Build
`Adds(..., {1, 16, 1, 16})`, `{1, 8, 1, 8}` and `{1, 1, 1, 1}` on DAV_3510 and record cycles per
repeat for each. Upstream's 220x arithmetic predicts 8 beats and 4 beats for the first two; the
DAV_3510 group count of 8 predicts the severe stride is a multiple of 8, so `{1, 8, 1, 8}` should be
the *worst* case here, not the milder one. If that inversion is observed, it is the cleanest single
demonstration that the constants are generation-specific.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, beside
every point. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard if the die moved. Refuses to assume: that a free die stays free; that a die
may be substituted; that the padding request became the address — every arm echoes the resolved UB
base address of all three tensors, and an arm whose addresses did not move as requested is discarded
rather than interpreted; that `ResourceConflictRatio` isolates UB bank conflicts (cycles per repeat
is carried alongside as the wall-clock check, per `0315` §5).

## 5 · Checker — acceptance declared before the run
Verdict `pad_opt` = the padding value at which Arm C's conflict ratio is minimised, with the floor.
Declared before the run: this entry is **supported** iff `pad_opt` is the DAV_3510-derived value
from Arm B and **not** 256 B. The OVERTURN fires iff `pad_opt == 256 B` outside the floor — the
recipe would then transfer, whatever the arithmetic says, and the entry is corrected in place.

Verdict `baseline_clean` = true iff the unpadded baseline's conflict ratio is within the floor of a
known-clean control (all three buffers in different groups by construction). `baseline_clean == true`
is the predicted outcome and is *not* a pass by itself — it means Arms A–C are measuring
perturbations of a clean layout, and the report must say so rather than presenting a flat curve as
a resolved question.

Verdict `stride_inversion` = true iff Arm D's `{1, 8, 1, 8}` is the worst of the three on DAV_3510.

The exit code is not the verdict. Three guards. First, all arms are compared elementwise against a
CPU reference: padding changes offsets, and an off-by-one in a hand-placed buffer produces a fast
wrong answer. Second — the input that makes this checker go red — Arm C includes a padding value
chosen to *create* aliasing on DAV_3510 (a multiple of `8 × 16 KB`), which **must** show the worst
conflict ratio in the sweep. If the deliberately-aliased point reads clean, the instrument is not
measuring bank conflicts at all and every point on the curve is void. That planted positive is
mandatory: a padding study whose only outcome is "no conflicts anywhere" cannot distinguish a clean
part from a blind counter. Third, no point is reported without its floor and its echoed addresses.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 220x arithmetic in §3
(`16 KB = 4 banks`, `4 × 4 ≡ 0 mod 16`) and the DAV_3510 counter-arithmetic (`16 KB = 1 bank`,
`1 mod 8 ≠ 0`) are both performed here on paper from stated geometries; no buffer was allocated and
no conflict ratio was read.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the 220x recipes fail on
DAV_3510 — it establishes that they are stated for 220x, that their derivations use 220x's bank and
group counts, and that the arithmetic does not carry. Whether they nonetheless help is §4's
question, and §5 declares the outcome under which this entry is wrong. It supplies **no** DAV_3510
padding constant: Arm B's value is computed from `0314`'s geometry, which is itself unmeasured, so
this entry hands a consuming skill a method and not a number, deliberately. It does not establish
the cost of a conflict on DAV_3510 (`0315` §7: upstream gives a direction, not a figure). It says
nothing about bank conflicts arising from MTE traffic, SIMT thread loads or VF `LoadAlign` — the
whole section is written about Vector repeats. The 220x quotes and their arithmetic are upstream's
text, carried for contrast only; no fact from them enters this book (RULES.md Art. 1). BOARD is
`family-claimed(unverified)`: the source's DAV_3510 column is headed "Atlas 350"
(`C-950bp-011`) and no board token is named.
