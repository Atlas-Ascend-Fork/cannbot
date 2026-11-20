```
ID:        0326-restricting-the-legal-input-domain-to-the-cases-in-hand-cost-the-hidden-set-and-the-correctness-gate
LABEL:     trap
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     950PR
SOURCE:    ops/ascendc-performance-best-practices/reference/scatter/scatter_design.md:182-187 —
           "### 一条方法论提醒 / 手上的公开用例**恰好全部满足"三张量非 dim 维相等"**，据此把一类合法
           输入直接 `TORCH_CHECK` 拒掉，结果隐藏用例 77/80、correctness 门禁整体判失败、掉 15 分。"
           · "**算子的合法输入域要按语义规范推（`desc.md` / `proto.yaml` / torch 文档），不能按手上
           的用例推。**"
SOURCE:    same file:149-150 — "**形状**：三张量 rank 相同且 ≤ 8；`indices.size(k) ≤
           min(data.size(k), updates.size(k))`。非 dim 维范围不等由⑥覆盖，**不要 `TORCH_CHECK`
           拒掉**（§8 方法论）。" ; :9 — "在 **Ascend950PR 上实测评测总分 72.46（20/20 通过）、
           Scatter 算子榜第 1 / 21 个提交**，隐藏集 80/80。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a case set in which the operator's semantic specification and the public case set agree
           on the input domain, so that inferring the domain from the cases gives the same answer —
           the practice would then be safe for that operator, and the rule would need a condition.
```

# 0326 · Restricting the legal input domain to the cases in hand cost the hidden set and the correctness gate

## 1 · Claim
Upstream asserts a mistake it made and the price. The public case set for its scatter operator
happened to satisfy "the three tensors' non-`dim` extents are equal" in every case; upstream
inferred that as a precondition and rejected the complement with `TORCH_CHECK`. The hidden case set
did not satisfy it. Upstream asserts the outcome: 77 of 80 hidden cases, the correctness gate failed
overall, 15 points lost. Upstream asserts the rule that follows — an operator's legal input domain
is derived from its semantic specification (`desc.md`, `proto.yaml`, the torch documentation), never
from the cases in hand — and encodes it as a constraint in the family's own scope section:
non-equal non-`dim` extents are covered by path ⑥ and must not be rejected. Not established here.

For scale: the same implementation, with the rejection removed, is reported at 80/80 on the hidden
set (`:9`). So the delta this one inference cost is 3 hidden cases and the entire correctness gate.

## 2 · The wrong branch this removes
The inference is not lazy, which is why it is worth an entry. It is a reasonable generalisation from
a complete sample: every available case satisfies the property, the property simplifies the
implementation substantially (it collapses per-dimension stride arithmetic into a three-segment
address form), and adding a `TORCH_CHECK` is the *responsible*-looking way to encode an assumption
— it fails loudly rather than silently.

That is exactly why it is dangerous. The check converts an unhandled case from a wrong answer into a
refusal, which feels like the safe direction. It is not, when the harness scores refusals as
failures and the unmet cases are a whole class rather than an edge. And a `TORCH_CHECK` is
*invisible* to every local signal: the public cases never trip it, so the local suite is green and
the local score rises.

The structural point, and the reason this sits in a book about NPU performance: a case set is a
sample of the input domain and is never its definition. Three sources define the domain — the
operator description, the proto, and the framework's own documented semantics — and all three are
available before any case is run. Upstream names all three.

The second wrong branch is the over-correction: accepting everything and handling nothing, so that
out-of-domain input produces a wrong answer instead of a refusal. Upstream's actual resolution is
neither — it *implemented* the general case as path ⑥ and routed to it, at the cost of a slower
path that most cases never take. The rule is "derive the domain from the specification, then cover
it", not "never check".

## 3 · Ground / Source
The methodology note, `scatter/scatter_design.md:182-187`, in full:

```
### 一条方法论提醒

手上的公开用例**恰好全部满足"三张量非 dim 维相等"**，据此把一类合法输入直接 `TORCH_CHECK` 拒掉，
结果隐藏用例 77/80、correctness 门禁整体判失败、掉 15 分。

**算子的合法输入域要按语义规范推（`desc.md` / `proto.yaml` / torch 文档），不能按手上的用例推。**
```

The rule as a shipped constraint, `:149-150`:

```
- **形状**：三张量 rank 相同且 ≤ 8；`indices.size(k) ≤ min(data.size(k), updates.size(k))`。
  非 dim 维范围不等由⑥覆盖，**不要 `TORCH_CHECK` 拒掉**（§8 方法论）。
```

The domain the specification actually gives, cited by upstream to torch:
`torch 只要求 index.size(k) ≤ self.size(k)` (`:48`). So the general case was documented, not
obscure — and the implementation's own path ⑥ exists to serve it, described at `:48` as
`三张量**非 dim 维范围不一致**` with `优先级最高，一票否决其余五条` (`:100`). The rejected class was
the one the routing table puts *first*.

The scoring context, `:8-9`:

```
> **来源与可信度**：提炼自 [cann-bench](https://gitcode.com/cann/cann-bench) `tasks/level2/scatter`
> 的一份 direct-launch 实现，在 **Ascend950PR 上实测评测总分 72.46（20/20 通过）、Scatter 算子榜
> 第 1 / 21 个提交**，隐藏集 80/80。
```

`80/80` with the general path; `77/80` and a failed gate with the rejection. Both figures come from
the same harness on the same board, which is what makes them comparable — unlike the two-environment
comparison in `0325`.

This is a *disclosure*, not a measurement of a rate: it records one occurrence, on one operator,
with one case set. The `15 分` is a property of that harness's scoring, not of the defect.

The same family supplies a second instance of the same species from the other direction — `0159`
records a fast-path predicate missing `extentsMatch`, where `公开用例往往一条通用路径都不触发 ⇒
**标准集满分也照样挂隐藏集**`. So this shelf has met the "public cases do not exercise the general
path" failure twice, once as an over-restriction and once as an over-admission, and both times the
local suite was green.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The claim is about a
*process*, so the procedure is a coverage audit, and its first half needs no device.

Arm 1 — the domain, derived rather than sampled. `[no-card]`, and **not run**: for the operator under
test, extract the legal input domain from each of the three sources upstream names (`desc.md`,
`proto.yaml`, framework documentation), record them separately, and record where they disagree. Two
sources disagreeing is itself a finding and is more likely than it sounds.

Arm 2 — the sample's coverage of that domain. Enumerate the public case set and mark, for each
degree of freedom in the derived domain, whether any case exercises the non-trivial value. The
output is a coverage table whose empty rows are exactly the places where an inference from cases
would be unsafe. This is the instrument the whole entry is about, and it also needs no device.

Arm 3 — the consequence, measured. Build two variants: one that rejects the uncovered class with
`TORCH_CHECK`, one that routes it to the general path. Run both against a case set constructed to
include the uncovered class. Record pass counts and, separately, the general path's cost on the
cases that could have taken a fast path — because the price of covering the domain is real and must
travel with the rule.

Device selection for Arm 3: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that the three specification sources agree (they are recorded
separately, and a merge is not performed); that the public case set is a sample of anything — Arm 2
treats it as an arbitrary list, which is what upstream's failure shows it to be.

## 5 · Checker — acceptance declared before the run
Verdict `domain_sources` = the three derived domains from Arm 1, with disagreements listed. No pass
condition; disagreement is a finding, not a failure.

Verdict `uncovered_dofs` = the set of degrees of freedom with no non-trivial public case, from
Arm 2. Declared before the run: `uncovered_dofs` non-empty is the **expected** outcome, and the
entry's advice applies exactly to that set. An empty `uncovered_dofs` fires the OVERTURN — the
public cases would then span the domain, inference from them would be safe for this operator, and
the rule would need a condition it currently does not have.

Verdict `reject_cost` = (general-path pass count − rejecting-path pass count) on the constructed
set, and `general_overhead` = the general path's time penalty on fast-path-eligible cases, with a
variance floor.

The exit code is not the verdict. Three guards.

First — the input that makes this checker go red, and it is Arm 2's own construction. The coverage
table is built by *executing* each public case and recording which branch it took, not by inspecting
the case metadata. A metadata-based table records what the author believes the cases cover; a
branch-execution table records what they actually exercise, and the two differ precisely when it
matters. If a branch is marked covered by metadata and never observed in execution, the metadata
table is void. This is the same lesson `0325` states for `.cpu()` versus a `stride` assertion:
reproduce the action, not the check you think is equivalent.

Second, Arm 3's constructed case set must contain at least one case that the rejecting build
*refuses*. If both builds pass everything, the constructed set does not reach the uncovered class
and `reject_cost` is meaningless.

Third, `general_overhead` is reported with `reject_cost`. A rule that says "cover the domain" and
hides its price will be reversed by the next person optimising for score.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. `77/80`, `80/80`, `72.46`,
`20/20` and the 15-point loss are upstream's readouts on Ascend950PR under a harness not present in
this tree; this book has enumerated no domain, executed no case, and built nothing.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled, and both device-free arms were left unrun. The entry records one
disclosed occurrence on one operator with one case set — it establishes neither a rate nor a
general property of case sets. The `15 分` is a property of one scoring harness and does not
transfer. The three specification sources upstream names (`desc.md`, `proto.yaml`, torch
documentation) are not present in this tree and were not read; whether they in fact agree on this
operator's domain is unknown here. Nothing establishes that the general path (⑥) is correct for the
whole derived domain — only that it exists and is routed to first. The entry does not establish
that `TORCH_CHECK` is the wrong tool; upstream's failure was in *what* it checked, and a check
derived from the specification would have been correct. The cost of covering the domain is nowhere
quantified by upstream. BOARD is `950PR`, the board the family's provenance note names; nothing is
established for 950DT. Nothing transfers to the other book (RULES.md Art. 1).
