```
ID:        0455-an-mx-format-scale-is-quantised-along-the-mmad-reduction-axis-so-v-scale-runs-along-sk-and-not-its-innermost-d
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/overview.md:157-176 —
           "### §3.5 I5 — MX 类格式 scale 轴对齐不变量 / MX 类(mxfp8 / mxfp4 / mxfp6 等)块量化格式的
           scale **必须沿被消费 matmul 的 reduction (K-mmad) 轴量化**。 / **根源**:硬件 Tensor Core
           对 MX 类格式的硬约束—— "data must be consecutive over the reduction dimension"。" ·
           "| V | P·V | S_k | **S_k**(不是 BSND innermost 的 D)|" ·
           "**值得警惕的反直觉**:V 在 BSND `[B, Sk, Hkv, D]` 布局下 D 是 innermost 连续维度。按"沿
           连续维度量化"的直觉会得到"V scale 沿 D",但这与 PV Mmad 的 K-mmad = S_k 不兼容。**业界标准
           把 V scale 沿 S_k 量化**。" · "**违反后果**:Mmad ScaleB 轴错位 → 输出 NaN / inf(Mmad
           直接产出非数,不是数值漂移)。"
SOURCE:    same file:176 — "> 本不变量根源在 Mmad 硬件约束,所有用 MX 类格式做 MatMul 的算子(不限
           attention)都受其约束。当前暂放本文件,理想归属是独立的 MatMul methodology(暂未建)。"
           ; same shelf, subfamilies.md:315 — "- scale 张量内存连续轴是否对齐 K-mmad?(I5 校核;
           **典型踩坑**:V scale 错放在 D 上,不兼容 PV Mmad)"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an mxfp8 P·V Mmad on a named 950 board, with V's scale quantised along D, that produces
           finite values agreeing with an FP32 reference — the axis rule would then not be a hardware
           constraint on this part, whatever it is on other vendors' Tensor Cores, and the "直接产出
           非数" claim would be false here. Equally: the same build producing NaN/inf on the first
           Mmad, while the S_k-quantised build agrees, is the observation this entry predicts.
```

# 0455 · An MX-format scale is quantised along the Mmad reduction axis, so V's scale runs along S_k and not its innermost D

## 1 · Claim
Upstream asserts that for MX block-quantised formats (mxfp8, mxfp4, mxfp6), the scale tensor must be
quantised along the reduction axis of the matmul that consumes it — the `K-mmad` axis — and gives the
root cause as a hardware Tensor Core constraint that the data be consecutive over the reduction
dimension. Upstream asserts the resulting axis assignment for attention: Q and K are consumed by
`Q·K^T` whose reduction axis is `D`, so their scales run along `D`; `P` and `V` are consumed by `P·V`
whose reduction axis is `S_k`, so both scales run along `S_k`. Upstream asserts that V's case is
counter-intuitive, because under the BSND layout `[B, Sk, Hkv, D]` the innermost contiguous dimension
of V is `D`, so the instinct "quantise along the contiguous dimension" gives the wrong axis. Upstream
asserts the failure mode is not drift: a misaligned `ScaleB` axis makes the Mmad emit NaN or inf
directly. Upstream asserts the invariant is not attention-specific — it binds every operator using MX
formats for matmul — and states that its placement in the attention file is provisional. Not
established here.

## 2 · The wrong branch this removes
Without this entry an agent laying out an mxfp8 attention kernel reasons from memory layout, which is
almost always the right instinct: block-quantised scales describe groups of contiguous elements, so
the scale axis follows the contiguous axis. For Q, K and P this reasoning happens to give the right
answer. For V it gives the wrong one, and V is the only tensor in the operator whose contiguous axis
and whose consuming reduction axis differ. So the instinct is confirmed three times and fails once,
which is worse than failing always.

The normal checks do not catch it early. The scale layout is a host-side decision; the kernel compiles;
the tiling is unchanged; a shape check passes because the scale tensor has the same element count
either way (`S_k/32 × …` versus `D/32 × …` differ in shape but both are "a scale tensor"). The failure
appears at the first `P·V` Mmad, and it appears as NaN — which, in an operator that also contains a
softmax, an exponential and a rescale, is the single most over-determined symptom available. An agent
debugging NaN in FlashAttention will look at the softmax max-subtraction, the `exp` overflow, the
zero-length row, the padding rows, and the accumulator dtype, all of which are real NaN sources in
this operator, before it looks at a scale tensor's axis.

The second wrong branch is scoping. Because the rule is written inside `overview.md §3` as one of the
attention family's invariants, an agent building a plain mxfp8 matmul will not read it — and upstream
says in the same paragraph that the constraint binds that operator too. The rule's *location* is the
trap for everyone outside attention.

## 3 · Ground / Source
The invariant, `references/flashattention/overview.md:157-174`:

```
### §3.5 I5 — MX 类格式 scale 轴对齐不变量

MX 类(mxfp8 / mxfp4 / mxfp6 等)块量化格式的 scale **必须沿被消费 matmul 的 reduction (K-mmad) 轴量化**。

**根源**:硬件 Tensor Core 对 MX 类格式的硬约束—— "data must be consecutive over the reduction dimension"。块量化的 scale 描述 reduction 沿线的 32 元素一组,必须与 Mmad 的 K-mmad 方向严格对齐。业界标准(Blackwell Tensor Core / NVIDIA cuDNN MXFP8 attention)一致遵守此约束。

**attention 中的推论**:

| 张量 | 被消费 matmul | K-mmad 轴 | scale 量化轴 |
|------|------------|---------|-----------|
| Q | Q·K^T | D | D |
| K | Q·K^T | D | D |
| P(kernel 内构造)| P·V | S_k | S_k |
| V | P·V | S_k | **S_k**(不是 BSND innermost 的 D)|

**值得警惕的反直觉**:V 在 BSND `[B, Sk, Hkv, D]` 布局下 D 是 innermost 连续维度。按"沿连续维度量化"的直觉会得到"V scale 沿 D",但这与 PV Mmad 的 K-mmad = S_k 不兼容。**业界标准把 V scale 沿 S_k 量化**。

**违反后果**:Mmad ScaleB 轴错位 → 输出 NaN / inf(Mmad 直接产出非数,不是数值漂移)。
```

Three things in that passage need separating, because they are of three different evidential kinds and
upstream states them in one block.

**A hardware constraint**, quoted in English inside a Chinese document: `"data must be consecutive
over the reduction dimension"`. Upstream does not say whose sentence this is. It is presented as the
root cause and it is the only part of the invariant that could be a property of the Ascend part.

**An industry-standard appeal**: `业界标准(Blackwell Tensor Core / NVIDIA cuDNN MXFP8 attention)
一致遵守此约束`. This names another vendor's hardware and another vendor's library as the evidence
that the rule holds. Under RULES.md Art. 2 that is not evidence about a 950 board at all — it is a
statement that a different Tensor Core behaves this way. The invariant may well be true here; the
citation offered for it is about elsewhere. This is the entry's sharpest scope limit and §7 carries it.

**A group size**: `块量化的 scale 描述 reduction 沿线的 32 元素一组` — 32 elements per scale, stated
once, with no derivation and no dtype dependence, in a family that is otherwise disciplined about
never writing bare numbers (`design.md:208`, `**禁止**直接写数字`). Recorded as `Q-950fin-03`.

The self-disclosed misfiling, `:176`:

```
> 本不变量根源在 Mmad 硬件约束,所有用 MX 类格式做 MatMul 的算子(不限 attention)都受其约束。当前暂放本文件,理想归属是独立的 MatMul methodology(暂未建)。
```

A constraint that binds all MX matmul, parked in the attention methodology because the matmul
methodology does not exist. The shelf's own matmul family (`0469`) is scoped to mxfp8 + eltwise fusion
and does not carry this rule, so the one document in the repository that would most obviously need it
is the one that does not have it. Registered as `C-950fin-004` — not a disagreement between two
statements, but a rule and its stated home in different places, disclosed by upstream itself.

The quantised subfamily restates the trap as a check item, `subfamilies.md:315`: `- scale 张量内存
连续轴是否对齐 K-mmad?(I5 校核;**典型踩坑**:V scale 错放在 D 上,不兼容 PV Mmad)`, and
`:252` makes it a pre-review checklist line requiring V's axis to be *declared explicitly*:
`V scale 沿 S_k 还是沿 D 已显式声明?` — an obligation to write the answer down, which is upstream's
usual shape for a decision people get wrong silently. `:253` adds a second, separable obligation from
the same family: the L1 head-offset formula for the data carrier and for the scale carrier must be
derived independently, because their coefficients may differ.

`subfamilies.md:195` records where this material came from: `本骨架在首个量化 FA 算子(GQA × mxfp8
推理,A5 平台)落地过程中形成` — the first quantised FA operator, on the A5 platform. That is one of
only four places the FA family names a platform at all, and it scopes the *provenance* of the skeleton
rather than any measurement.

All passages are in one repository: one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. mxfp8 is
stated by the shelf's own matmul template to be Ascend950-only hardware support
(`references/matmul/matmul-fusion-design-template.md:30`), so this procedure has no 910 counterpart
and none is proposed.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

**Arm 1 — the isolated Mmad, which is where the claim actually lives.** Not a FlashAttention kernel: a
single mxfp8 `P·V`-shaped Mmad, `[m, S_k] × [S_k, D]`, with the B-side scale built two ways — along
`S_k` (upstream's rule) and along `D` (the trap) — and everything else identical, including the same
scale *values* permuted. Record the output tile, the count of non-finite elements, and elementwise
agreement against an FP32 reference. Isolating the Mmad is the point: in a full attention kernel NaN
has at least five other sources (§2), and this arm has one.

**Arm 2 — the group size.** Sweep the scale group along the reduction axis at 16, 32 and 64 elements,
`S_k`-aligned, and record which are accepted, which fault at load, and which produce finite correct
output. Upstream states 32 with no derivation; this arm turns a bare literal into a measured
acceptance set or shows the literal is the only value the API takes.

**Arm 3 — the four-tensor assignment in situ.** A minimal quantised GQA kernel, with each of Q, K, P
and V's scale axis independently switchable. Run the four single-flips against the all-correct build.
Prediction from §3: flipping Q or K breaks `Q·K^T`, flipping P or V breaks `P·V`, and each flip's
non-finite output appears at the corresponding Mmad. Retained even where it is expected to bite,
because *which* Mmad produces the first non-finite value is the evidence that the mechanism is the
axis and not the softmax.

**Arm 4 — the non-attention scope, retained because it may not bite.** The same isolated Mmad as arm 1
in a plain mxfp8 matmul harness with no attention structure at all. If arm 1 and arm 4 agree, the rule
is confirmed as non-attention-specific, which is what `:176` asserts and what `C-950fin-004` records
as unhomed. If they disagree, `:176` is wrong and the rule is narrower than upstream says.

Refuses to assume: that a free die stays free, or that a die may be substituted; that NaN in a
FlashAttention output implicates the scale axis (arm 1 exists so that it can); that a scale layout the
host builds is the layout the kernel loads (each arm echoes the scale tensor's shape and strides as
seen on the device); that 32 is the group size (arm 2 derives it); that another vendor's Tensor Core
constraint holds here (the whole procedure exists because it might not); that a finite output is a
correct one — every arm carries its elementwise comparison.

## 5 · Checker — acceptance declared before the run
Verdict `nonfinite_fraction(axis)` for `axis ∈ {S_k, D}` from arm 1, declared before the run.
Acceptance for the entry: `nonfinite_fraction(D) > 0` and `nonfinite_fraction(S_k) == 0` and the
`S_k` build agrees elementwise within the declared atol. The OVERTURN fires iff
`nonfinite_fraction(D) == 0` **and** the D build agrees within atol — the axis would then not be
load-bearing on this part.

Verdict `first_nonfinite_stage` from arm 3 ∈ {`mm1`, `mm2`, `softmax`, `none`}, read from a per-stage
dump rather than from the final output. Declared now: a flip of V's axis whose first non-finite value
appears in `mm1` would mean the harness is not isolating what it thinks it is, and the arm is reported
`untestable`.

Verdict `accepted_group_sizes` from arm 2, as a set.

The exit code is not the verdict: an Mmad that emits inf exits 0, and a comparison that computes
relative error against a reference containing zeros can score `inf` as "large error" rather than as
"not a number". Guards: (1) non-finite elements are counted separately from the error metric, and the
checker fails red if any arm reports an error metric without its non-finite count; (2) **the input
that makes this checker go red**: arm 1's `S_k` build with the scale values deliberately replaced by
ones, which must reproduce the unscaled reference exactly — if it does not, the harness's scale path
is broken and the `D`-axis result is an artifact of that, not of the axis; (3) no point is reported
without its scale shape, its strides as echoed from the device, its group size, its CANN pin and its
atol.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The invariant, the four-row
axis table, the counter-intuition note, the consequence line, the industry-standard appeal, the
32-element group size, the self-disclosed misfiling and the two quantised-subfamily checklist items
are file reads performed at drafting time. The separation of the passage into a hardware constraint, a
statement about another vendor's hardware, and an underived constant is a reading of upstream's own
lines, not an observation of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the constraint holds on any Ascend
part: upstream's stated evidence for it is a quoted English sentence with no attribution plus the
behaviour of Blackwell Tensor Cores and NVIDIA cuDNN, which under RULES.md Art. 2 establishes nothing about
950PR or 950DT. It does not establish that a misaligned axis produces NaN rather than wrong finite
values. It does not establish 32 as the block size, nor that the size is dtype-independent across
mxfp8/mxfp4/mxfp6 — upstream names three formats and one number. It does not establish that the rule
binds non-attention matmul, which upstream asserts at `:176` and no document in the repository acts
on; `C-950fin-004` records that gap and §4 arm 4 is the procedure that would close it. It does not
cover `int8` or FP8 non-MX quantisation, which `subfamilies.md:16` lists in the same subfamily and
which have no block scale at all. It does not cover the L1 head-offset coefficient separation
(`subfamilies.md:253`), named here and not carried. No board token appears in the invariant; the
platform named nearby (`subfamilies.md:195`, `A5`) scopes the skeleton's provenance and not a
measurement, and `A5` names a family rather than a board, so BOARD is `family-claimed(unverified)`.
§4 names 950PR/950DT only as where our run would happen. Nothing here is established for any
910-family board.
