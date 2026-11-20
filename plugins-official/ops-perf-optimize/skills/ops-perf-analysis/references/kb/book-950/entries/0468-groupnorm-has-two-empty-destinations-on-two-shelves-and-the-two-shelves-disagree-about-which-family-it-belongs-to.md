```
ID:        0468-groupnorm-has-two-empty-destinations-on-two-shelves-and-the-two-shelves-disagree-about-which-family-it-belongs-to
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/SKILL.md:20 — "| NN 神经网络类（其它）| 神经网络专用，多种操作组合
           | GroupNorm 等非 attention | 📋 规划中 |"
SOURCE:    ops/ascendc-perf-optimize/references/tiling/index.md:24 — "| FA FlashAttention 类 |
           FlashAttention, GroupNorm | [fa/](fa/) |" ; same shelf,
           references/tiling/fa/fallback/index.md:3 — "> 当前为占位文档，内容待补充。" (both already
           carried at 950:0169, cited here rather than re-entered)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/overview.md:21-29 — the FA subfamily
           roster (FA / GQA, MHA, MLA, 稀疏 FA, 量化路径), which contains no normalisation operator
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read (no device):
           grep -n 'GroupNorm' -r upstream/skills-dev-main/ops/ascendc-tiling-design/ \
                                  upstream/skills-dev-main/ops/ascendc-perf-optimize/
OVERTURN:  a measured GroupNorm on a named 950 board whose tiling plan derived from the FA family's
           methodology (`0451`–`0466`) is at least as good as one derived from the reduction family's
           templates — the classification disagreement would then be immaterial, and routing
           GroupNorm to attention would be defensible rather than a mis-route. Equally: either
           destination acquiring content in a later revision resolves the trap by removing one of the
           two empty ends.
```

# 0468 · GroupNorm has two empty destinations on two shelves, and the two shelves disagree about which family it belongs to

## 1 · Claim
Upstream asserts, on the tiling-design shelf, that GroupNorm belongs to the "NN (other)" category,
explicitly described as non-attention (`GroupNorm 等非 attention`), and that this category is planned
with no content and no directory. Upstream asserts, on the perf-optimize shelf, that GroupNorm belongs
to the FlashAttention category, routed to a directory whose fallback document declares itself a
placeholder with content outstanding — a state this book already records at `950:0169`. So one
operator has two family assignments in one repository, the two assignments are mutually exclusive
(one says attention, the other says explicitly non-attention), and **both destinations are empty**.
Upstream's own FA subfamily roster on the tiling-design shelf lists five subfamilies, none of which is
a normalisation operator. Not established here; this entry records a routing state, an absence, and a
disagreement.

## 2 · The wrong branch this removes
Without this entry an agent asked to tile a GroupNorm follows whichever shelf it opened first. From
perf-optimize it lands in the FA directory and is told the modelling is not yet collected. From
tiling-design it lands on a `📋 规划中` row with no link at all. Both are dead ends, and the second
one at least says so immediately; the first costs a directory read and leaves the impression that
GroupNorm *is* an attention-class operator, which is the durable damage. An agent that has absorbed
that classification, and then finds the FA methodology fully documented on the other shelf
(`0451`–`0466`), will apply it: `__mix__` kernels, four-stage cube/vector interleave, online-softmax
state, `s2` forbidden from task dispatch. None of that describes a GroupNorm, which is a reduction over
groups followed by an affine transform and has no second matrix multiply at all.

The normal checks do not catch it because a routing table is not checked by anything. The route
resolves — the directory exists, the file exists — and the failure is that the document at the end of
it does not describe the operator that was routed there. `0169` already records the analysis shelf's
half of this and the reduction family that covers the operator one directory away; what this entry adds
is that the *other* shelf, the one that publishes the FA methodology, classifies the same operator as
explicitly not attention. So the shelf that would have supplied the wrong methodology is the shelf that
says the route is wrong.

The second wrong branch is inferring from "two shelves disagree" that one of them is right. Both
destinations are empty. The disagreement cannot be resolved by following either link, and it is not a
disagreement about a number that a run could settle — it is a taxonomy, and Art. 7 forbids adjudicating
it by which author seems more plausible. What §4 can settle is the *consequence*: whether a plan built
from the FA methodology is worse for GroupNorm than one built from the reduction family's.

## 3 · Ground / Source
The tiling-design shelf's assignment, `ops/ascendc-tiling-design/SKILL.md:20`:

```
| NN 神经网络类（其它）| 神经网络专用，多种操作组合 | GroupNorm 等非 attention | 📋 规划中 |
```

The row's example column does not merely list GroupNorm — it defines the category *by contrast with
attention*: `GroupNorm 等非 attention`, GroupNorm and other non-attention operators. So this shelf does
not passively put GroupNorm somewhere else; it puts it in a category whose defining property is not
being attention. There is no directory for this row (`0467`).

The perf-optimize shelf's assignment is carried at `950:0169` and is cited rather than re-entered
(plan Amendment 2): `references/tiling/index.md:24` routes `FlashAttention, GroupNorm` to `fa/`, and
`references/tiling/fa/fallback/index.md:3` declares that directory a placeholder,
`> 当前为占位文档，内容待补充。`, with the routing answer to give being `FA Tiling 建模暂未收录`.
`0169` also records that the same placeholder carries a one-line sketch of GroupNorm's multi-core
split (`Batch 切分 + Group 内归约`) — batch splitting plus within-group reduction, which is a
*reduction* description, in an attention directory.

The third leg is what the FA family itself covers, `references/flashattention/overview.md:21-29`: five
subfamilies — FA/GQA, MHA, MLA, sparse FA, quantised — selected by `Sq`, `Hq`, `Hkv`, whether the KV is
compressed, whether it is pure decode, whether it is sparse (`:191`). Every selection criterion is an
attention shape parameter. GroupNorm has none of them. So the FA methodology's own selection procedure
cannot classify the operator the other shelf routes into it, which is a stronger statement than "the
directory is empty": even if it were full, the entry procedure would reject the operator at step one.

Registered as `C-950fin-001`. Both shelves are in one repository, so this is a disagreement *inside*
one origin (RULES.md Art. 3) — which is why it is a contradiction row and not a corroboration, and why
neither side gains authority from the other's existence.

What no document in either shelf says is where GroupNorm's tiling knowledge actually lives. `0169`
identifies the reduction family one directory from the empty FA stub, whose applicability list names
LayerNorm and RMSNorm, operators with the same `mean → var → normalize` structure. That is an
inference from the operator's mathematics, not an upstream statement, and this entry does not upgrade
it: no document routes GroupNorm to reduction on either shelf. Recorded as `Q-950fin-17`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The
disagreement is a taxonomy and cannot be run; what §4 runs is its consequence.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first, reported beside every point.

**Arm 1 — the routing consequence.** Three GroupNorm kernels for one shape set
(`[N, C, H, W]` with `C` split into `G` groups, `G ∈ {1, 8, 32}`, `C/G` spanning small and large):
(a) planned from the reduction family's templates (`0121`–`0131`, `0401`–`0404`); (b) planned from the
FA family's methodology as far as it applies; (c) planned from neither, as a control by an
implementer given only the operator definition. Report `aiv_time`, correctness against an FP64
reference, and — separately — how far (b) could be carried before the methodology stopped applying.
That last is not a number and is reported as prose with the step at which it stopped.

**Arm 2 — the selection procedure, which is the cheapest arm.** Apply `overview.md §4.1`'s subfamily
selection to a GroupNorm requirement: `Sq`, `Hq`, `Hkv`, KV compression, decode-only, sparse. Record
which of the five subfamilies it selects. The prediction is that it selects none, because none of the
criteria has a value. This needs no device and no build, and it is the arm that shows the mis-route is
structural rather than merely inconvenient.

**Arm 3 — the sketch in the placeholder.** Build (d) from the one-line multi-core split the FA
placeholder itself gives for GroupNorm (`Batch 切分 + Group 内归约`, `0169`). Compare against (a).
Upstream's sketch is a reduction plan sitting in an attention directory; if (d) and (a) measure the
same, the placeholder's content was never attention-shaped and the routing table is the only thing that
put GroupNorm there.

**Arm 4 — retained because it may not bite.** Re-run arms 1–3 for LayerNorm, which both shelves route
to reduction unambiguously. If (a) and (b) differ for GroupNorm but a similar gap appears for LayerNorm
too, the gap is a property of the two methodologies rather than of the mis-route, and arm 1's result is
not attributable to the classification.

Refuses to assume: that a free die stays free, or that a die may be substituted; that "the FA
methodology does not apply" can be asserted without trying to apply it (arm 1(b) tries, and records
where it stops); that the reduction family is the right home (`Q-950fin-17` is open, and arm 1(c) is
the control that keeps both candidates honest); that a taxonomy disagreement has a measurable answer at
all — §5 declares what would and would not count.

## 5 · Checker — acceptance declared before the run
Verdict `subfamily_selected` from arm 2 ∈ {one of the five, `none`}. Acceptance for the structural half
of this entry: `none`. This is declared before the run and is the arm whose outcome is most nearly
certain — it is included because a claim that a procedure *cannot* classify an operator is worth
demonstrating rather than asserting, and because a selection that did land somewhere would be a
genuine surprise that changes the entry.

Verdict `plan_gap = (median t(b) − median t(a)) / median t(a)` from arm 1, with its floor, plus
`b_completable` boolean — whether a plan from the FA methodology could be completed at all. Declared
now: the OVERTURN fires iff `b_completable` is true and `plan_gap ≤ floor` — the FA route would then
cost nothing, and the classification disagreement would be immaterial in practice however untidy it is.

Verdict `sketch_matches_reduction` from arm 3: `true` iff (d) and (a) agree within the floor.

Verdict `gap_is_specific` from arm 4: `true` iff LayerNorm's equivalent gap is materially smaller than
GroupNorm's. A `false` here withdraws arm 1's attribution, and that is declared before the run rather
than after.

The exit code is not the verdict, and here the verdict is not primarily a runtime quantity: three of
the four arms produce classifications and prose. Guards: (1) arm 1(b)'s "where it stopped" must name a
specific step of `design.md §2`–`§7`, and the checker reports the arm `untestable` if it does not — a
narrative that says "it did not apply" without a step is not evidence; (2) **the input that makes this
checker go red**: arm 2 applied to a genuine GQA requirement, which must select `FA / GQA` — if the
selection procedure returns `none` for that too, the procedure was mis-applied and GroupNorm's `none`
carries no information; (3) no timing point is reported without its shape, `G`, `C/G`, floor, atol and
CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The tiling-design taxonomy row,
the FA subfamily roster with its selection criteria, and the perf-optimize routing and placeholder
lines (the latter two already carried at `950:0169`) are file reads performed at drafting time. The
observation that the FA family's own selection criteria are all attention shape parameters, and
therefore cannot classify a normalisation operator, is a reading of upstream's own list, not an
observation of a build or of any tool's behaviour.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or run. The entry does not establish which classification is right —
Art. 7 forbids resolving a source disagreement by preference, and §4 tests only the consequence of
following one of them. It does not establish that GroupNorm belongs to the reduction family; no
upstream document says so on either shelf, and `Q-950fin-17` records that as an inference from the
operator's mathematics rather than a harvested claim. It does not establish that either destination
will remain empty. It does not re-enter `950:0169`'s content, which is cited: the perf-optimize
placeholder's state, its four missing items and its GroupNorm sketch belong to that entry, and anything
this entry says about them is a citation, not a second establishment. It does not evaluate the
reduction family's fitness for GroupNorm, nor the FA methodology's — §4 proposes that and nothing here
anticipates it. No board token appears in any quoted passage, so BOARD is `family-claimed(unverified)`;
§4 names 950PR/950DT only as where our run would happen. Nothing here is established for any
910-family board.
