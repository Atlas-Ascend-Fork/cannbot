```
ID:        0398-a-softmax-denominator-is-at-least-one-so-the-eps-usually-added-to-it-is-unnecessary
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), which states the claim
           twice in one file, once as a technique note and once as a named misconception. Nothing was
           compiled and no denominator was evaluated.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/numerical_stable/knowledge.md:32-46 —
           "### T1: Max-Shift + LogSumExp / **解决问题**: `log(Σexp(x))` 或 `Softmax = exp(x)/Σexp(x)`
           上溢 / **数学原理**: / ``` / log(Σexp(xᵢ)) = m + log(Σexp(xᵢ - m)),  其中 m = max(x) / ``` /
           **为什么有效**: / - 右侧 `exp(xᵢ - m) ∈ (0, 1]`（至少一项 = 1） / - 避免 exp 参数过大 /
           - Softmax 分母 ≥ 1，**不需要 eps**（常见误区） / **必要代价**: 两遍归约（或 online 单遍维护
           running-max/sum）"
SOURCE:    same file:69-71 — "### ❌ 误区 1: Softmax 分母需要 eps / **错误**: `y = exp(x-m) /
           (sum(exp(x-m)) + eps)` / **正确**: 分母已 ≥ 1（含 exp(0)=1），无需 eps"
SOURCE:    same file:48-66 — the backward halves that share the max-shift's state: "LogSoftmax
           Backward: / Forward: y = x - m - log(sum(exp(x-m))) / Backward: grad_x = grad_y - exp(y) *
           sum(grad_y)"; "Softmax Backward: / Forward: y = exp(x-m) / sum(exp(x-m)) / Backward: grad_x =
           y * (grad_y - sum(grad_y * y))"; "**稳定实现关键**: / - **复用 forward 输出** … / - **sum 使用
           fp32 累加器**（T3） … / - **避免重复计算**"
SOURCE:    same file:74-79 — the two neighbouring misconceptions that scope the eps rule: "❌ 误区 2:
           RMSNorm 需要 Welford … **正确**: 只计算 `E[x²]`，无相消风险，单遍 fp32 即可" and "❌ 误区 3:
           Elementwise 需要 fp32 累加器 … **正确**: 无归约，仅需 T5 值域保护"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a max-shifted softmax on a 950 board whose denominator evaluates to less than 1, or to
           exactly 0 — reachable if the maximum's own `exp(x−m)` term is not exactly 1 (a rounding or
           flush-to-zero effect in the exp implementation), or if a masked softmax excludes the maximising
           element after the shift. Either makes the eps a real guard rather than a misconception.
```

# 0398 · A softmax denominator is at least one, so the eps usually added to it is unnecessary

## 1 · Claim
Upstream asserts the max-shift identity `log(Σexp(xᵢ)) = m + log(Σexp(xᵢ − m))` with `m = max(x)`, and
asserts why it works: after the shift every term `exp(xᵢ − m)` lies in (0, 1] with **at least one term
equal to 1**, so the exponential's argument is never large. Upstream asserts the consequence for softmax:
the denominator is therefore ≥ 1, and **no eps is needed** — and names adding one as a 常见误区, a common
misconception. Upstream restates it as a numbered misconception with the wrong and right forms written out.
Upstream asserts the necessary cost of the technique: two reduction passes, or an online single pass
maintaining a running max and sum. Upstream asserts the backward formulations for LogSoftmax and Softmax,
and three implementation keys: reuse the forward output rather than recomputing, use an fp32 accumulator
for the sums, and precompute the sum before broadcasting. Not established here: nothing was compiled and no
denominator was evaluated.

## 2 · The wrong branch this removes
Adding an eps to a denominator is a habit, and habits are not applied selectively.

**Where the habit comes from.** Every normalisation an agent has written needs one: `1/sqrt(var)` becomes
`rsqrt(var + eps)`, `x/||x||` becomes `x / max(||x||, eps)`, and upstream's own T2 says so
(`knowledge.md:69-84`). LayerNorm's eps is a documented attribute. So "divide → add eps" is reinforced by
the neighbouring technique in the same document, and softmax is a division by a sum. The agent adds it
without deciding to.

**What it costs.** Not correctness in the crash sense — the result stays finite. It costs *accuracy*, in a
specific and unhelpful direction: every output is scaled by `S/(S+ε)`, so the softmax no longer sums to 1.
For a one-hot-ish distribution where S ≈ 1 and ε = 1e-5, the error is about 1e-5 on every element — five
decimal digits, which is inside fp16's ~3 (0397) and *outside* fp32's ~7. So the eps introduces a
systematic bias that is invisible at fp16 and measurable at fp32, and it survives every algorithm fix
because it is not in the algorithm. That is exactly the "stable systematic bias" and "small but stubborn
mismatches that survive algorithm fixes" signature `api_misuse.md:112-114` records (0396 §1), reached from
a different cause.

It also costs an instruction and a constant in the hot loop, and it costs the reviewer's attention: an eps
in the code implies a hazard, so the next reader looks for the underflow case that is not there.

**Why the guarantee holds, and where it is thin.** The denominator is `Σ exp(xᵢ − m)`. The maximising
element contributes `exp(0) = 1` exactly, so the sum is ≥ 1 by construction — no bound on the input, no
assumption about the distribution. That is a much stronger guarantee than the eps habit is designed for,
and it is why upstream can call the eps a misconception rather than a conservatism.

The thin spots are two, and upstream names neither. First, the guarantee depends on `exp(0)` evaluating to
exactly 1 in the implementation actually used — a Taylor-path exp with a reduced expansion level would not
necessarily return exactly 1 at 0, and 0035 records that `ExpandLevel` zero buys speed by leaving the
Taylor path. Second, it depends on the maximising element being *in the sum*: a masked softmax (attention
with a causal or padding mask) that computes `m` over the unmasked set and sums over the same set is fine,
but one that takes `m` before masking and sums after can exclude the element contributing the 1 — and then
the denominator can be arbitrarily small, or zero if every element is masked. Upstream's rule is stated
without either qualification, and the masked case is the one every attention kernel meets.

**The cost sentence is the part that gets dropped.** 必要代价: 两遍归约 — the necessary cost is two reduction
passes (max, then sum), or an online single pass maintaining a running max and sum. An agent that adopts
the max-shift without adopting the second pass has a shift computed from a stale or partial maximum, which
breaks the ≥ 1 guarantee in the same way masking does. The technique and its cost are one item, and only
the technique is memorable.

**The two neighbouring misconceptions scope it.** 误区 2 says RMSNorm needs no Welford because `E[x²]` has
no cancellation risk; 误区 3 says elementwise operators need no fp32 accumulator because they have no
reduction. Read together with 误区 1, the three say: apply each stabilisation to the mechanism that
requires it, not to every operator that looks numerically delicate. That is the same discipline 0397 §2
records for the accumulator rule, stated as three worked negatives.

## 3 · Ground / Source
T1, `knowledge.md:32-46`:

> ### T1: Max-Shift + LogSumExp
>
> **解决问题**: `log(Σexp(x))` 或 `Softmax = exp(x)/Σexp(x)` 上溢
>
> **数学原理**:
> ```
> log(Σexp(xᵢ)) = m + log(Σexp(xᵢ - m)),  其中 m = max(x)
> ```
>
> **为什么有效**:
> - 右侧 `exp(xᵢ - m) ∈ (0, 1]`（至少一项 = 1）
> - 避免 exp 参数过大
> - Softmax 分母 ≥ 1，**不需要 eps**（常见误区）
>
> **必要代价**: 两遍归约（或 online 单遍维护 running-max/sum）

and the restatement, `:69-71`:

> ### ❌ 误区 1: Softmax 分母需要 eps
> **错误**: `y = exp(x-m) / (sum(exp(x-m)) + eps)`
> **正确**: 分母已 ≥ 1（含 exp(0)=1），无需 eps

Stated twice, once with its derivation and once with the wrong code written out. The parenthetical
含 exp(0)=1 is the whole argument and it is the sentence this entry rests on.

The backward halves, `:48-66`, quoted in SOURCE, and their three implementation keys. Note the first key —
复用 forward 输出 — is a *residency* claim as much as a numerical one: it requires `y` (or `exp(y)`) to
survive from forward to backward, which in a fused kernel is a buffer decision (0356's promotion rule) and
in a separate backward kernel is an extra tensor. The numerical technique and the memory plan are coupled
and upstream states only the numerical half.

The second key — sum 使用 fp32 累加器 — is 0397's T3 applied to `sum(grad_y)` and `sum(grad_y * y)`, so the
backward pass carries the accumulator requirement even when the forward was fp16 throughout.

The neighbouring misconceptions, `:74-79`, quoted in SOURCE.

The technique-combination rules, `:150-163`, place T1 in context and are recorded because they make the eps
rule's scope explicit: "T1 几乎必带 T3: log 域归约涉及求和 → fp32 累加器"; "T2 几乎必带 T3: 归一化需要求和/
范数 → fp32 累加器"; and the decision tree routes a formula containing log/exp/softmax/logsumexp to the
logdomain scenario (T1+T3, possibly +T5) and one containing a normalisation denominator to the normdenom
scenario (T2+T3, possibly +T4). So softmax is *logdomain*, not *normdenom* — and T2, the eps-protection
technique, belongs to normdenom. The eps habit is literally the application of the wrong branch of the
file's own decision tree.

What upstream does not supply: any statement about masked softmax; any statement about whether `exp(0)`
returns exactly 1 in the available implementations; any eps value for the cases where one *is* needed
(T2 gives ranges per dtype at `:80-84`, and T2 is a different technique); and any measurement of the bias an
unnecessary eps introduces.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3). The wider `numerical_stable/`
family was sampled rather than mined in this block (0397 §7).

## 4 · Procedure
Runnable later on `950PR`. The claim is an inequality with a named mechanism, so the procedure evaluates the
denominator directly.

Arm A — the guarantee, evaluated. Compute `Σ exp(xᵢ − m)` for a swept input set — uniform, one-hot-like
(one large element), all-equal, all-negative, and extreme-range — and record the **minimum denominator
observed** across every case. The claim predicts ≥ 1 always, with equality approached when one element
dominates. A value below 1 anywhere is the OVERTURN.

Arm B — the `exp(0)` question §2 raises. Evaluate the available exponential paths at exactly 0 and record
whether each returns exactly 1.0. Include the reduced-expansion path (0035's `ExpandLevel` zero) if it is
reachable. If any path returns 1 − δ, the guarantee becomes `≥ 1 − δ` and the eps rule needs a caveat.
This is a small arm and it is the one that could most cheaply falsify the mechanism.

Arm C — the masked case, which upstream does not cover. Build a masked softmax two ways: `m` computed over
the unmasked set, and `m` computed before masking. Sweep the mask density to fully-masked. Record the
denominator in each. Under §2 the second can lose the contributing 1; the fully-masked row is where a
zero denominator would appear, and whether that is reachable decides whether an attention kernel needs a
guard the general rule says it does not.

Arm D — the cost of an unnecessary eps. Build the softmax with and without `+ eps` at eps ∈ {1e-5, 1e-7},
compare against an fp64 reference, and record the max deviation of the output's sum from 1.0. §2 predicts a
systematic bias of about ε/S. Recording it makes the misconception's cost a number rather than an
argument, and 0396's metric rule applies: report absolute and relative error together, not a mean.

Arm E — the necessary cost. Build the two-pass form and the online single-pass running-max/sum form, compare
outputs against fp64 and durations against each other at three sequence lengths. Upstream calls the two-pass
form 必要代价 and offers the online form as an alternative without pricing either.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`min_denominator` (Arm A) — the smallest denominator observed, per input class. Pass iff ≥ 1.0 in every
class. Reported per class and never as a global minimum alone: a violation in one class is the finding and
a global figure would name the class only by accident.

`exp_zero_is_exact` (Arm B) — per exponential path, true iff `exp(0)` returns exactly 1.0. Pass condition
**true** for the default path. A false anywhere is reported with the path named, because the rule's
mechanism is that specific term.

`masked_min_denominator` (Arm C) — the smallest denominator per mask density, for both mask orderings.
Reported as a table. The fully-masked row is reported explicitly even if it is degenerate — a zero
denominator that nobody wrote down is how an attention kernel produces NaN in production.

`eps_bias` (Arm D) — the mean **signed** deviation of the output sum from 1.0, per eps value. Signed, not
absolute: the claim is a systematic bias in one direction and an absolute figure cannot show direction.
Reported beside the max absolute error, per 0396's metric rule.

`two_pass_cost` (Arm E) — duration ratio between the online and two-pass forms, per sequence length, with
both accuracy figures beside them. Never a duration alone: an online form that is faster and less accurate
is not a win and one number would say it was.

The positive fixture, declared before the run: Arm A must include an input for which the denominator is
**provably** greater than 1 by a known amount — n identical elements give exactly n — and the measured value
must equal n. If it does not, the evaluation harness is wrong and every minimum in the arm is an artefact.
And Arm D must include a **zero-eps control** whose output sums to 1.0 within fp64 rounding; if it does not,
the deviation being attributed to eps is present without eps and the arm attributes nothing. Without both,
the checker reads only "the denominator was at least one and the sums looked close", which is the known
blind species — a null result from an instrument never shown able to produce a non-null one.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no exponential
evaluated, no denominator computed, no bias measured, no die contacted. The quoted passages are re-verified
file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that the denominator is ≥ 1 on this hardware,
that `exp(0)` returns exactly 1 in any available implementation, or that an unnecessary eps costs anything —
Arms A through E are all open.

**The guarantee is stated for the unmasked case only.** Upstream's rule has no qualification and §2
identifies two ways it can fail — a masked softmax whose maximum is computed outside the summed set, and an
exponential path where `exp(0)` is not exactly 1. Neither is upstream's claim; both are derived here from
upstream's own stated mechanism (含 exp(0)=1) and from 0035's record that a reduced expansion level leaves
the Taylor path. Arms B and C are what would establish them. **An attention kernel must not take this
entry's rule as covering its masked path.**

It does not establish the necessary cost. 两遍归约 is stated and the online alternative is named; neither is
priced, and Arm E is what would.

It does not establish anything about the backward formulations beyond quoting them. The three
implementation keys couple a numerical technique to a residency decision (reusing the forward output) that
this entry does not evaluate, and 0356's promotion rule is the place that trade would be judged.

It says nothing about eps values for the cases where one **is** required — that is T2, a different
technique, whose per-dtype ranges (`:80-84`) are unharvested — nor about the relationship between this rule
and any framework-supplied softmax eps attribute, which no source in scope mentions.

**The `numerical_stable/` family was sampled, not mined.** This entry and 0397 take three items from
`knowledge.md`; the file's other techniques, its combination rules beyond the two quoted, and the 390-line
`patterns.md` beside it are unharvested, and what they contain is unknown to this book.

BOARD is `family-claimed(unverified)`: the identity is mathematics, its realisation depends on the
exponential implementation, and no board was contacted.
