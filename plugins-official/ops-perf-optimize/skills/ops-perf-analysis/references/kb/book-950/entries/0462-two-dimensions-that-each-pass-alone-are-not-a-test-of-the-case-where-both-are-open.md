```
ID:        0462-two-dimensions-that-each-pass-alone-are-not-a-test-of-the-case-where-both-are-open
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/subfamilies.md:122-127 —
           "- **mPad > 16 + 多 s2 块组合**:GQA 维度首次打开(`mPad > 16` 即 `mEff > 16`)时,必须额外
           验证三类用例: / - (a) 单 s2 块 + mPad > 16 / - (b) 多 s2 块 + mPad = 16 /
           - (c) 两者同时打开 / 实测教训:(a)(b) PASS 不等价于 (c) PASS;(c) 路径在 P·V GEMM 上易出现
           精度漂移,需单独验证。"
SOURCE:    same shelf, design.md:386 — "- [ ] **清单 8(m 对齐维 > 单 fractal + 多 s2 块组合)**:
           GQA 维度首次打开时跑 3 类用例(单 s2+m 对齐 > fractal / 多 s2+m 对齐 = fractal / 两者同开);
           见 subfamilies §3.1" ; :472-487 — the one-dimension-at-a-time opening order and
           "**禁止**:多维度同时打开,精度回归出错时无法定位维度。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a GQA build on a named 950 board at which cases (a) and (b) pass and case (c) also passes,
           across the full shape sweep including the largest `mPad` and `s2N` the tiling admits — the
           conjunction would then carry no failure mode on this implementation and the third case
           would be redundant. Equally: a (c) failure whose error is confined to rows above the first
           fractal, or to KV blocks after the first, would identify which of the two dimensions
           carries the defect and would narrow this entry from a conjunction to a single cause.
```

# 0462 · Two dimensions that each pass alone are not a test of the case where both are open

## 1 · Claim
Upstream asserts that when the GQA dimension is first opened in a FlashAttention implementation —
specifically when the aligned `m` dimension exceeds one fractal, `mPad > 16` — three cases must be
verified and not two: (a) a single KV block with `mPad > 16`; (b) multiple KV blocks with
`mPad = 16`; and (c) both at once. Upstream asserts, as a lesson from practice, that (a) and (b)
passing is not equivalent to (c) passing, and that the (c) path is prone to precision drift in the
`P·V` GEMM specifically and needs verifying on its own. Upstream asserts separately a general opening
discipline for the same operator — one feature dimension at a time, a full precision regression after
each — and forbids opening several at once because a failure then cannot be localised. Not established
here.

## 2 · The wrong branch this removes
Without this entry a competent agent does exactly the right thing and stops one case short. The
general discipline is to open one dimension at a time and regress after each: open `mPad > 16`,
regress, green; open multi-block `s2`, regress, green. Both dimensions are now "verified", the test
matrix has two ticks, and the combination has never run. This is not laziness — it is the
one-dimension-at-a-time rule applied faithfully, and the rule as stated does not say to come back and
test the product.

The two statements are in tension and both are upstream's. `design.md:487` forbids opening several
dimensions at once. `subfamilies.md:122-127` requires a case with two open at once. They reconcile
only if the rule is read as "open one at a time *and then also test the conjunction*", which is a
reading neither passage states. An agent that has internalised the first rule has a positive reason to
skip case (c). Registered as `C-950fin-007`.

The normal checks do not catch it because the check *is* the thing that is incomplete. A precision
regression is a set of cases; the cases are chosen by the dimensions opened; the conjunction is not a
dimension. And upstream names the failure as *drift*, not as a wrong answer — so even if (c) runs at a
loose tolerance it can pass, and the tolerance for attention is set by the softmax's own error budget,
which is not tight.

## 3 · Ground / Source
The requirement, `references/flashattention/subfamilies.md:122-127`:

```
- **mPad > 16 + 多 s2 块组合**:GQA 维度首次打开(`mPad > 16` 即 `mEff > 16`)时,必须额外验证三类用例:
  - (a) 单 s2 块 + mPad > 16
  - (b) 多 s2 块 + mPad = 16
  - (c) 两者同时打开

  实测教训:(a)(b) PASS 不等价于 (c) PASS;(c) 路径在 P·V GEMM 上易出现精度漂移,需单独验证。
```

`实测教训` — a lesson learned from measurement. This is one of the few sentences in the FA family that
claims a measurement happened, and it reports the *shape* of a result without the result: no case, no
error magnitude, no `mPad`, no `s2N`, no dtype, no board, no tolerance. What survives is the structural
claim, and the structural claim is the useful part: a conjunction of two independently-verified
dimensions is a third thing.

The number 16 is the fractal height, and upstream writes it as a bare literal in a family whose own
memory-division section forbids bare numbers in formulas (`design.md:208`). The design shelf's
restatement at `:386` avoids it — `m 对齐维 > 单 fractal` — naming the quantity instead of its value.
So the same requirement is stated once with the constant and once with the concept, in two files.
Recorded as `Q-950fin-11`: whether 16 is the fractal height for every dtype on this family, or the
fp16 value written into a dtype-independent rule.

The general discipline this sits against, `design.md:472-487`:

```
### §6.4 维度打开纪律

回答:**新算子开发时各特性维度按什么顺序打开?**

逐维度打开,每打开一维跑一次全场景精度回归。典型顺序:

MVP(单核 + 单 qHead 单 kvHead + fp16 + non-causal + 对齐 shape + 小 D)
  → 非对齐 / GQA / bf16
  → causal
  → 多核
  → 三级流水
  → D 维度扩展(逐档:小 D → 中 D → 用户上限)

**禁止**:多维度同时打开,精度回归出错时无法定位维度。

**强制门禁**:用户需求中 D 上限较大时,MVP 之后必须在多核 + 流水线维度通过后立即打开"D = 用户上限"的精度回归,不允许"只测小 D 就交付大 D"。
```

Two things here are worth carrying beyond §2's tension. First, the mandatory gate — `不允许"只测小 D
就交付大 D"` — is a second instance of the same epistemic rule in the same section: a dimension that
was not tested at its extreme is not delivered at its extreme. It is stated for `D` and not for
`mPad`, `s2N` or `Sk`, and upstream gives no reason for the asymmetry. Second, the opening order puts
`多核` after `causal` and before `三级流水`, so the pipeline depth — which is where three of the four
slot semantics of `0453` acquire their values — is opened last, on top of everything else, and its own
conjunctions are never enumerated.

This book already carries the general form of this claim from an unrelated family (`0395`: a passing
small aligned shape establishes nothing about the tail). This entry is its second instance in the
corpus, arrived at independently by a different upstream author in a different shelf, and the two
differ in a way worth stating: `0395` is about extrapolating from a small case to a large one, and this
one is about extrapolating from two verified axes to their product. The second is harder to see,
because both axes really were verified.

Two files, one repository: one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample afterwards and
discard the case if the die moved. All comparisons against an FP64 reference at the atol declared per
`overview.md §4.4`, never at the kernel's own precision (`0396`).

**Arm 1 — the 2×2, not the two cases.** One GQA build, four cells:
`mPad ∈ {16, > 16}` × `s2N ∈ {1, > 1}`. Report max and mean absolute error per cell, ≥20 repetitions
each, plus the disagreeing-run fraction. The claim is that the fourth cell differs from what the other
three predict, so all four are needed and the interesting number is
`err(c) − max(err(a), err(b))`, not any cell's pass/fail.

**Arm 2 — the localisation, which is what upstream's mechanism asserts.** For the (c) cell, dump the
`P·V` result before the rescale and the final output separately, and report per-row and per-KV-block
error. Upstream names the `P·V` GEMM specifically; this arm is where that is confirmed or moved. If
the error is already present in `Q·K^T` or appears only after the online rescale, the mechanism is not
what upstream says even if the cell fails.

**Arm 3 — the ladder past the stated boundary.** Extend `mPad ∈ {16, 32, 64, 128}` × `s2N ∈ {1, 2, 3,
8}` and report the error surface. Upstream states the requirement at the *first* opening of the
dimension and implies nothing about how the drift scales. A surface that grows with both axes is a
different finding from a step at the boundary, and neither is currently known.

**Arm 4 — the fractal constant.** Repeat the (c) cell at fp16 and bf16 and record the `mPad` at which
the behaviour changes in each. If it is 16 for both, the bare literal is dtype-independent here; if it
differs, `Q-950fin-11` is answered and the literal is an fp16 value in a dtype-independent rule.
Retained because it may not bite — a null result is the answer to the question.

Refuses to assume: that a green cell is a green cell on one run (every cell is repeated and the
disagreeing fraction is reported, since drift may be schedule-dependent); that the atol used for the
regression is tight enough to see drift (arm 1 reports raw error, and the atol is applied afterwards
by the checker, not by the harness); that 16 is the fractal height (arm 4 derives it); that the
disagreement is in the output (arm 2 dumps intermediates); that a free die stays free, or that a die
may be substituted.

## 5 · Checker — acceptance declared before the run
Verdict `conjunction_excess = err(c) − max(err(a), err(b))`, declared before the run, with the
repetition spread on each term. Acceptance for the entry: `conjunction_excess` exceeds the spread —
the fourth cell is worse than either axis alone predicts. The OVERTURN fires iff
`conjunction_excess ≤ spread` across the whole of arm 3's surface including its far corner.

Verdict `drift_stage` from arm 2 ∈ {`mm1`, `mm2`, `post_rescale`, `none`}. Upstream's claim is `mm2`.
Any other value is recorded as a correction to the mechanism, with the entry's structural claim
untouched — the two are separable and this checker keeps them separate on purpose.

Verdict `fractal_boundary(dtype)` from arm 4, per dtype.

The exit code is not the verdict, and here that is the entry's whole subject: the failure mode is
drift, which passes any check whose tolerance is loose, and the three-case rule exists because the
suite that would catch it is the thing being designed. Guards: (1) the checker computes raw error and
applies the tolerance itself, and fails red if any cell was reported as a pass/fail without its raw
error — a suite that reports only verdicts cannot show a conjunction excess, which is the blind-checker
species; (2) **the input that makes this checker go red**: cell (a) and cell (b), which must both agree
within atol — if either fails, the conjunction excess is not attributable to the conjunction and the
run establishes nothing, so the checker refuses a verdict rather than reporting (c) as the culprit;
(3) no cell is reported without its `mPad`, `s2N`, dtype, repetition count, raw error, atol, CANN pin
and variance spread.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The three-case requirement, the
`实测教训` sentence, the `P·V` attribution, the two checklist restatements, the opening order and the
mandatory large-`D` gate are file reads performed at drafting time. The observation that the two
statements pull in opposite directions, and the observation that the same requirement is written once
with the constant 16 and once with the concept "one fractal", are readings of upstream's own lines,
not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that case (c) fails: upstream reports a
lesson from measurement and supplies no case, no error magnitude, no shape, no dtype, no tolerance and
no board. It does not establish that the `P·V` GEMM is where the drift arises. It does not establish
16 as the fractal height for any dtype (`Q-950fin-11`). It does not establish that (a) and (b) are the
right two singletons — upstream chose them and gives no argument that another pair would not do. It
does not resolve `C-950fin-007`, whether the one-dimension-at-a-time rule and the three-case
requirement are consistent as written. It says nothing about conjunctions of any other pair of
dimensions, which upstream never enumerates, nor about the pipeline-depth dimension the opening order
places last. It is a claim about a *verification procedure*, not about the operator's behaviour: even
if (c) never failed, the reasoning "two axes verified implies their product verified" would remain
invalid, and that reasoning is what this entry is for. No board token appears in any quoted passage, so
BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing
here is established for any 910-family board.
