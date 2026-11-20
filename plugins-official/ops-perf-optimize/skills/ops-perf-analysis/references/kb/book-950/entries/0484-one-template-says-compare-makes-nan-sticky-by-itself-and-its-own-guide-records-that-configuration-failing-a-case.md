```
ID:        0484-one-template-says-compare-makes-nan-sticky-by-itself-and-its-own-guide-records-that-configuration-failing-a-case
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scan/templates/cum_streaming_scan.md:31 —
           "| **NaN 传播** | `Compare` 对 NaN 返回 false → NaN 被取用并向后传播，对齐 torch |" ;
           :29-30 — "`gtMask=(x>curMin)`；`curMin=Select(curMin, x, gtMask)`…" · "用 `GT`（而非 `GE`）
           → `x<=curMin` 时更新索引为当前 r。Cummax 用 `LT`" ; :38 — "`Compare<CMPMODE::GT>` + 两个
           `Select`"
SOURCE:    same shelf, templates/usage_guide.md:236-239 — "- NaN 必须显式粘滞：只写 `Compare` 不够。
           cann-bench 的 `value_range=["nan","nan"]` 生成的是 / **NaN 与实数混合**的输入；若只用 `GT`
           判 `x > curMin`，因 `(实数 > NaN) = false` 会把 NaN "恢复"成实数。 / 正解是再加一路
           `Compare<NE>(x, x)` 判 NaN，与 `LE` 的结果 `Or` 成一个掩码：`(le | nan) ? x : curMin`。 /
           （实测：只用 `GT` 时 20 用例中 case 14 精度失败。）" ; templates/cum_tile_resident_scan.md:103-108
           — "`takeB = (x <= curMin) || isNaN(x)`" with "用 `Or` 把两个掩码合成一个，替掉嵌套 `Select`" ;
           templates/usage_guide.md:14 — "流式扫描（含 argmin/argmax）。**仅作参考实现，勿用于性能路径**"
           and :204 — "TPipe pipe; ScanOps::CumStreamingScan<TX, TP> op;" inside `CUMMIN_ENTRY`
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a Cummin on a named 950 board built with `Compare<GT>` alone, over an input mixing NaN and
           real values, whose output matches `torch.cummin` elementwise including NaN placement — the
           explicit `NE` path would then be unnecessary and the streaming template's claim right.
           Equally: the same build failing on that input, at the case upstream names, confirms the
           guide and makes the template's table row a defect rather than a difference of emphasis.
```

# 0484 · One template says Compare makes NaN sticky by itself, and its own guide records that configuration failing a case

## 1 · Claim
Upstream asserts, in the streaming scan template's technique table, that NaN propagation is automatic:
`Compare` returns false for NaN, so a NaN is taken and propagates forward, aligned with torch. Upstream
asserts that template's comparison is `Compare<CMPMODE::GT>` and nothing else — `GT` for min, `LT` for
max — with two `Select`s driven by that one mask. Upstream asserts, in the integration guide for the
same template set, the opposite: `Compare` alone is not enough, because with `GT` only, `(real > NaN)`
is false and a NaN is "restored" to a real value; the correct form adds a second comparison
`Compare<NE>(x, x)` and `Or`s it with the `LE` result into one mask. Upstream asserts a measurement
for that: with `GT` only, case 14 of a 20-case suite fails on precision. Upstream's other template
implements the guide's form — `takeB = (x <= curMin) || isNaN(x)`, two masks combined with `Or`.
Upstream asserts the streaming template is a reference implementation not for the performance path,
and its own entry macro instantiates that template four times. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent building a Cummin reads the streaming template — the one the entry macro
uses — and takes NaN handling as solved. The reasoning in that table row is seductive and half right:
`Compare` does return false for NaN, so a NaN operand never wins a comparison, so once `curMin` is NaN
nothing displaces it. That is the *sticky* half. The half it misses is *becoming* NaN: with
`gtMask = (x > curMin)` and `Select(curMin, x, gtMask)`, an incoming NaN `x` also fails the comparison
and is therefore **not** taken, so the NaN never enters the running state at all. The mask that makes
NaN sticky once present is the same mask that keeps it out.

The normal checks do not catch it because a NaN input is not a normal input. A precision regression
built from ordinary distributions never produces one; upstream's suite produces it only under a
deliberate `value_range=["nan","nan"]` generator, and even then only one case of twenty fails. So the
defect is reachable by exactly one configuration of one test generator, and it is silent everywhere
else.

The second wrong branch is trusting the template roster. `usage_guide.md:14` marks the streaming
template `仅作参考实现，勿用于性能路径` — reference implementation only, do not use on a performance
path — and `usage_guide.md:204`, inside the `CUMMIN_ENTRY` macro that the same document presents as the
entry-point pattern, instantiates `ScanOps::CumStreamingScan<TX, TP>` for all four dtypes. So the
document that forbids the template ships the macro that uses it. **This book already records the same
species one shelf over**: `0136` records the analysis shelf's reference script emitting the one
template its own flow document forbids on a performance path. This is the second, independent-in-
artifact instance in one repository.

## 3 · Ground / Source
The streaming template's claim, `templates/cum_streaming_scan.md:31`:

```
| **NaN 传播** | `Compare` 对 NaN 返回 false → NaN 被取用并向后传播，对齐 torch |
```

and the comparison it uses, `:29-30`:

```
| **Compare + Select 两路同 mask** | `gtMask=(x>curMin)`；`curMin=Select(curMin, x, gtMask)`、`curIdx=Select(curIdx, r, gtMask)`。同一 mask 保证值与索引一致 |
| **并列语义（对齐 torch）** | torch.cummin/cummax 为 **last occurrence**：并列时取更晚位置。用 `GT`（而非 `GE`）→ `x<=curMin` 时更新索引为当前 r。Cummax 用 `LT` |
```

`GT` appears at `:29`, `:30`, `:38` and `:43`. No `NE`. No `Or`. No `isNaN`.

The guide's contradiction, `templates/usage_guide.md:236-239`:

```
- NaN 必须显式粘滞：只写 `Compare` 不够。cann-bench 的 `value_range=["nan","nan"]` 生成的是
  **NaN 与实数混合**的输入；若只用 `GT` 判 `x > curMin`，因 `(实数 > NaN) = false` 会把 NaN "恢复"成实数。
  正解是再加一路 `Compare<NE>(x, x)` 判 NaN，与 `LE` 的结果 `Or` 成一个掩码：`(le | nan) ? x : curMin`。
  （实测：只用 `GT` 时 20 用例中 case 14 精度失败。）
```

Note the mechanism the guide gives is the *reverse* of §2's reading: it says `(real > NaN) = false`
restores a NaN to a real value — i.e. once `curMin` is NaN, a subsequent real `x` fails `x > curMin`
and… under `Select(curMin, x, gtMask)` that means `curMin` is *kept*, which would be sticky. The guide's
sentence and the template's `Select` argument order cannot both be as printed and produce the guide's
symptom. One of the two is describing a different `Select` convention — and `usage_guide.md:219`
states the convention explicitly: `Select(dst, src0, src1, mask)` → mask true takes `src0`. Under that
convention `Select(curMin, x, gtMask)` keeps `curMin` when the mask is true, so `gtMask = (x > curMin)`
true means *keep the old minimum*, which is correct for a min. Then a NaN `x` gives a false mask and is
**taken** — the template's claim — while a real `x` after a NaN `curMin` also gives a false mask and is
also taken, which is the guide's symptom. **Both are consequences of the same one-mask design, and the
template states only the first.** Registered as `C-950fin-026`.

The third file implements the guide, `templates/cum_tile_resident_scan.md:103-108`:

```
`takeB = (x <= curMin) || isNaN(x)`：

- `<=` 而不是 `<`，实现 torch 的「并列取更晚下标」
- `curMin` 一旦是 NaN，后续实数 `x` 的 `(x <= NaN)` 为 false 且自身非 NaN → 不更新,
  于是 NaN **粘滞传播**，与 `torch.cummin` 一致
- 用 `Or` 把两个掩码合成一个，替掉嵌套 `Select`，值和索引各省一条 `Select`
```

Two masks, `Or`ed. And its stated reason for stickiness is the *correct* one: the real `x` fails
`x <= NaN` **and** is not itself NaN, so neither term of the `Or` fires. That is the argument the
streaming template's one-mask form cannot make.

The tie semantics also diverge: the streaming template uses `GT` (`:30`) and the guide's monoid uses
`LE` (`usage_guide.md:235`, `故用 LE（vB <= vA 时取靠后的 B）`). `GT` and `LE` are complements, so the
two forms select opposite branches and the `Select` argument order must differ between them; neither
document says so.

`0139` already carries "the comparison type follows the chosen scan algorithm and NaN must be made
sticky by hand" from the analysis shelf. This entry is that claim's counter-statement, found in this
shelf, plus the measurement (`case 14`) that `0139` does not have — so `0139` is cited and this entry
adds the disagreement and its case identity rather than re-entering the rule.

One repository, one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

**Arm 1 — the two mask forms, on NaN-mixed input.** One Cummin with the mask switchable: (a)
`Compare<GT>` alone, per the streaming template; (b) `LE | NE(x,x)` `Or`ed, per the guide and the
tile-resident template. Inputs: a NaN-real mixture at several NaN densities (1 in 1000, 1 in 10, 1 in
2), plus all-real and all-NaN as controls, at fp16, bf16 and fp32. Compare elementwise against
`torch.cummin` for **both values and indices** — the indices are where the tie semantics diverge and a
value-only comparison would miss it.

**Arm 2 — the two directions of the mechanism.** For build (a), report separately: how often a NaN in
the input fails to enter the running state, and how often a NaN already in the running state is
displaced by a real value. §3 shows these are two consequences of one design and that the two
documents each describe only one. This arm says which actually occurs.

**Arm 3 — the cost of correctness.** Time (a) against (b) on all-real input at the shapes the shelf
names. The guide's form costs one extra `Compare` and one `Or` per step; the tile-resident template
claims the `Or` *saves* a `Select` on each of the value and index paths, so the correct form may be
cheaper rather than dearer. That would make the streaming template's simplification a loss on both
axes, which is a result worth having.

**Arm 4 — the entry macro, retained because it may not bite.** Build the `CUMMIN_ENTRY` macro exactly
as `usage_guide.md:201-210` prints it and run the whole 20-case suite. If it passes, the "reference
only" marking is about performance and not correctness, and the roster's warning and the macro
coexist; if case 14 fails, the shipped entry point ships the defect its own guide documents.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a value
comparison covers an index defect (arm 1 compares both); that NaN density is irrelevant (arm 1 sweeps
it); that `Select`'s argument order is as either document implies (each build echoes its mask and its
`Select` operand order, since §3 shows the two documents cannot both be describing the same
convention); that the correct form is slower (arm 3 measures rather than assumes).

## 5 · Checker — acceptance declared before the run
Verdict `matches_torch(build, density, dtype)` from arm 1, split into `values_match` and
`indices_match`, declared before the run. Acceptance for the guide: build (a) fails at some NaN
density and build (b) passes at all of them. The OVERTURN fires iff build (a) passes at every density
including 1-in-2 — `Compare` alone would then make NaN sticky and the streaming template's row would
be right.

Verdict `nan_lost_rate` and `nan_displaced_rate` from arm 2, reported separately.

Verdict `correct_form_cost = t(b) / t(a)` from arm 3 on all-real input, with its floor.

Verdict `macro_suite_result` from arm 4: the failing case ids, if any.

The exit code is not the verdict: a NaN handled wrongly produces a finite number, which is a plausible
value and passes any check with a tolerance. Guards: (1) the comparison is elementwise against a
reference and **NaN positions are compared as positions**, not by arithmetic — `NaN != NaN` makes a
naive difference metric report agreement or disagreement arbitrarily, so the checker fails red if any
comparison used a subtraction on a NaN-containing pair; (2) **the input that makes this checker go
red**: the all-real control, where both builds must agree with torch exactly — if either fails there,
the harness's reference or its tie semantics are wrong and every NaN result is an artifact; (3) no
point is reported without its NaN density, dtype, shape, the echoed mask expression, the echoed
`Select` operand order and the CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The streaming template's table
row and its `GT`-only comparison, the guide's contradicting paragraph with its `case 14` result, the
tile-resident template's two-mask form, the `Select` convention line, the tie-semantics divergence,
the roster's "reference only" marking and the entry macro's four instantiations are file reads
performed at drafting time, each re-verified against its file. The analysis in §3 — that the guide's
stated mechanism and the template's `Select` argument order cannot both be as printed, and that under
the document's own stated `Select` convention both symptoms follow from the one-mask design — is a
reading of three of upstream's own lines, not an observation of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish which document is right about NaN —
Art. 7 forbids choosing by plausibility, and §4 arm 1 is the procedure. It does not establish that
case 14 fails, only that upstream reports it failing with `GT` alone; no shape, dtype, board or
repetition count accompanies that report. It does not resolve `C-950fin-026`, whether the guide's
stated mechanism or the template's is the one that occurs (arm 2). It does not establish the tie
semantics: `GT` and `LE` are complements and the two documents pair them with `Select` calls whose
operand order is not stated in either. It does not re-enter `0139`, which carries the make-NaN-sticky
rule from the analysis shelf and is cited here. It does not establish that the streaming template is
slow, which is the roster's stated reason for forbidding it and is a different claim from this
entry's. It does not cover Cumsum or Cumprod, which have no comparison and no NaN mask at all
(`cum_streaming_scan.md:44`). No board token appears in any cited file, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
