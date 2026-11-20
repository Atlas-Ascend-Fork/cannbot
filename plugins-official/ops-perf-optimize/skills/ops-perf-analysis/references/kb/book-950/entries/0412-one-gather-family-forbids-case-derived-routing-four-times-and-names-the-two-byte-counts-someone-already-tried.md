```
ID:        0412-one-gather-family-forbids-case-derived-routing-four-times-and-names-the-two-byte-counts-someone-already-tried
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/gather/guide.md:186 —
           "> **阈值规则**：禁止用 case ID、64 MiB/128 MiB 等固定输出大小或单个已知 shape 作为路由条件。
           优先从 SoC UB 容量、dtype/index 字节数、对齐、双缓冲布局、任务并行度和搬运成本推导候选；
           理论模型只负责筛选，最终用代表 case A/B 和完整用例集回归决定是否启用。"
SOURCE:    same shelf, templates/gather_elements_small_gd_tiled.md:31 —
           "不要使用 case ID、`G==7`、64 MiB/128 MiB 输出大小等作为通用路由条件。" ;
           templates/gather_elements_v2_last_dim.md:65 — "不要使用 case ID、64 MiB/128 MiB 等固定输出阈值。" ;
           templates/gather_elements_v2_scalar.md:89 — "不写 case ID、固定输出 MiB 阈值或单一 shape 特判。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a routing rule in this family expressed as a fixed output size or a single shape that is
           shown, on a named 950 board over a case set drawn independently of the one that produced it,
           to select the fastest available template at least as often as a rule derived from UB
           capacity, dtype widths and transfer cost. The prohibition would then be a style preference
           rather than a correctness rule, and the four statements would be over-stated.
```

# 0412 · One gather family forbids case-derived routing four times and names the two byte counts someone already tried

## 1 · Claim
Upstream asserts, four separate times across four files of one operator family, that a routing
predicate may not be a case ID, a fixed output size in bytes, or a single known shape. Three of the
four name the same two byte counts — 64 MiB and 128 MiB — and one additionally names a specific
gather-axis plane count, `G == 7`, taken from the family's own measured case. Upstream asserts the
replacement in positive form: derive candidates from SoC UB capacity, dtype and index byte widths,
alignment, double-buffer layout, task parallelism and transfer cost; use the theoretical model only to
screen; decide by A/B on representative cases plus a full-case-set regression. Not established here.

## 2 · The wrong branch this removes
The wrong branch is the one that works. A tuner has a case that is slow, finds a template that is fast
on it, and needs a predicate to select that template. The shape is right there; the output size is
right there; both are cheap to test and both are correct on every case anyone has run. The rule ships,
the benchmark improves, and the predicate is a lookup table with one row. `0046` already carries this
prohibition from the L2-bypass card, where upstream forbids routing by case ID or a fixed shape list;
what this family adds is the record of a specific attempt — nobody writes `64 MiB/128 MiB` into a
prohibition three times unless a rule shaped like that existed.

The second wrong branch is subtler and is why the rule needs its positive half. An agent told only
"don't use the shape" replaces `outputBytes > 64 MiB` with `outputElements * dtypeSize > 67108864` and
believes it has complied. It has not: the quantity is still a fixed output size, only spelled
differently. The test upstream actually states is about **provenance**, not syntax — a predicate is
admissible if it is derived from a machine property (UB capacity, dtype width, alignment quantum,
core count) or from a cost model over those, and inadmissible if its constant came from a case. That
is the same hard-versus-soft distinction `0104` makes for constants, applied to predicates: this family
is the place in the repository where it is stated most often and most explicitly.

## 3 · Ground / Source
Four statements, four files, one directory. The index page's, `reference/gather/guide.md:186`:

```
> **阈值规则**：禁止用 case ID、64 MiB/128 MiB 等固定输出大小或单个已知 shape 作为路由条件。优先从 SoC UB 容量、dtype/index 字节数、对齐、双缓冲布局、任务并行度和搬运成本推导候选；理论模型只负责筛选，最终用代表 case A/B 和完整用例集回归决定是否启用。
```

The small-GD mode's, which adds the plane count,
`templates/gather_elements_small_gd_tiled.md:31`:

```
不要使用 case ID、`G==7`、64 MiB/128 MiB 输出大小等作为通用路由条件。
```

The LastDim template's, attached directly to its cost model,
`templates/gather_elements_v2_last_dim.md:65`:

```
成本模型只用于筛选，不能替代代表 case A/B。不要使用 case ID、64 MiB/128 MiB 等固定输出阈值。
```

The Scalar template's, as item 4 of a numbered decision checklist,
`templates/gather_elements_v2_scalar.md:89`:

```
4. 不写 case ID、固定输出 MiB 阈值或单一 shape 特判。
```

`G == 7` is traceable. The family's one published measurement for the Scalar and small-GD paths is a
case with `Gx = Gi = 7` (`0410`), and both files carrying that measurement close by forbidding `7` as a
gate — `不构成 G==7 的通用阈值` (`gather_elements_small_gd_tiled.md:87`) and `不应把 7 或对应 shape
写成通用门槛` (`gather_elements_v2_scalar.md:91`). So the prohibition is attached to the exact number
its own evidence would tempt a reader to use, in the same paragraph as the evidence. That placement is
the mechanism: a rule stated where the temptation arises, not in a preface.

The positive half is the part that makes the rule executable, and it is stated once, in the index's
version. Six admissible sources — `SoC UB 容量、dtype/index 字节数、对齐、双缓冲布局、任务并行度和搬运
成本` — and a two-stage discipline: the model screens (`理论模型只负责筛选`), the measurement decides
(`最终用代表 case A/B 和完整用例集回归`). Every cost gate in this family is written to that shape and
says so in its own words: `模型不能准确覆盖 DMA 启动、stride 效率、核间并行和 bank conflict，只负责拒绝
显然不划算的候选；最终以 A/B 为准` (`gather_elements_small_gd_tiled.md:58`), and `该模型是路由门控，
不代替最终实测` (`gather_elements_v2_transpose.md:62`).

The `完整用例集回归` clause is the one an agent will drop and the one that matters most. Its reason is
stated at `gather_elements_v2_scalar.md:88`: `对候选路由运行完整用例集，按总体评分选择，避免只优化一个
case 后引入其他 shape 回退` — optimise one case, regress another. This family has that failure on
record: `0408`'s case4 was mis-routed because a fast number from one path was credited to another, and
`0410`'s counter-example is a path that is 23× wrong on a case nobody had A/B'd.

What the four statements do **not** supply is a test that a predicate can be run through. "Derived from
UB capacity" is checkable by a human reading the derivation and is not checkable mechanically, and
upstream offers no procedure for auditing an existing predicate. That gap is this entry's own §4
subject, and it is what separates a prohibition from a gate.

One tension worth recording rather than resolving. The family's own shipped router hardcodes four
constants — `kPostDimLimit = 32`, `kTransposeLen = 16`, `kInternalUbLimitBytes = 120000`,
`kCachelineElementsBytes = 512` (`0407`) — and none carries a derivation from the six admissible
sources. `120000` in particular is not a UB fraction, not a power of two, and not a round multiple of
any alignment quantum in the family. By the rule's own provenance test those four are as
case-derived as anything it forbids; by its letter they survive, because none of them is a case ID, an
output size in MiB, or a shape. Registered as `C-950td-016`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. A prohibition
is not directly measurable — what is measurable is whether obeying it produces better routing than
violating it, and that comparison needs two rule sets and a case set neither was fitted to.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs, 5 fresh-process runs.

**Case set construction, and it must come first.** Two disjoint sets. **Set A** (fitting): eight
`PER_ELEMENT` gathers spanning `dim == last` and `dim != last`, `gatherDim ∈ {2, 7, 64, 1024}`, two
dtypes. **Set B** (holdout): eight more drawn by a rule fixed *before* Set A is measured — for
instance, shapes from an operator inventory, or a stratified random draw over the same ranges with a
recorded seed — and **not looked at** until both rule sets are frozen. Without the holdout this arm
measures fitting, not routing, which is the failure the prohibition exists to prevent and which the
study would otherwise reproduce.

**Arm 1 — build the forbidden rule honestly.** On Set A only, measure every applicable template
(SIMT, Scalar, small-GD where buildable, LastDim, in-kernel transpose) and fit the best
case-derived predicate available: thresholds on output bytes and on `gatherDim`, tuned to select the
winner on every Set A case. Record it. This is the rule upstream forbids, built as well as it can be
built — a weak version would make the comparison meaningless.

**Arm 2 — build the permitted rule.** On Set A, fit a predicate using only the six admissible sources:
the runtime-queried UB (`0141`), dtype and index widths, the alignment quantum, the double-buffer
factor, the task count against the queried core count (`0207`), and the family's own transfer-cost
models (`0407`, `0411`). Same fitting data, different admissible inputs.

**Arm 3 — run both on Set B.** For each holdout case, record which template each rule selects and what
the measured best is. The metric is the **regret**: median `aiv_time` of the selected template divided
by median `aiv_time` of the best measured template, per case, with the floor.

**Arm 4 — audit the shipped router against its own rule.** Take the four constants of
`gather_elements_v2_route.template` and attempt, for each, a derivation from the six admissible
sources using the queried UB and core count. Report which of the four can be derived and which cannot.
This is `C-950td-016` and needs no device.

Refuses to assume: that a free die stays free; that a die may be substituted; that Set B was not
inspected (the draw rule and seed are recorded before Set A is measured, and the report states when
each set was first read); that a rule fitted on Set A generalises (that is the question); that `ub_size`
or `core_num` are literals; that a template named is a template run.

## 5 · Checker — acceptance declared before the run
Verdict `regret_A(rule)` and `regret_B(rule)` = median per-case regret of each rule on each set, with
the floor. Declared before the run: this entry is **supported** iff
`regret_B(forbidden) > regret_B(permitted) + floor` — the case-derived rule generalises worse on cases
it was not fitted to. The OVERTURN fires iff `regret_B(forbidden) ≤ regret_B(permitted)`: the forbidden
rule would then route at least as well on unseen cases, and the four prohibitions would be style rather
than correctness.

Verdict `overfit_gap(rule)` = `regret_B(rule) − regret_A(rule)`. Declared now, because it is the
quantity the prohibition is really about: the forbidden rule is predicted to have `regret_A ≈ 1` (it
was fitted to be perfect there) and a large gap; the permitted rule is predicted to have a worse
`regret_A` and a smaller gap. A forbidden rule with `regret_A ≈ 1` and `overfit_gap ≈ 0` would be the
most interesting possible result and is what the OVERTURN would look like in practice.

Verdict `derivable(k)` for each of the four router constants from arm 4, four booleans, reported
individually.

The exit code is not the verdict, and this study's characteristic failure is silent: a rule can be
"validated" by a case set it was fitted to, and the process exits 0 throughout. Three guards. First,
every measured template on every case is compared elementwise against a CPU reference; a regret
computed over a wrong answer is not a regret. Second, **the input that makes this checker go red**:
Set B includes two cases deliberately outside Set A's ranges (a `gatherDim` of 4096 and an output two
orders of magnitude larger than any in Set A). The forbidden rule **must** show elevated regret on at
least one of them; if it does not — if a rule fitted on eight cases is optimal on cases far outside
their range — then either the template ranking is insensitive to shape in this family, in which case
the whole study is uninformative and must be reported as such, or the harness is not actually applying
the rules. Either way the result is void, not a confirmation. That planted case is what keeps this from
being a study whose only outcome is "the rule we already believed is right". Third, no case is reported
without its floor, its per-template md5s and echoed names, and the timestamp at which its set was first
read.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The four prohibitions and their
placements are file reads performed at drafting time; the traceability of `G == 7` to the family's own
published case is a reading of two files that state the measurement and the prohibition in the same
paragraph, not an observation of how the number was arrived at. The observation that the shipped
router's four constants are not derivable from the six admissible sources is arithmetic and reading
performed here (`120000` against UB capacities this book records as unmeasured at `0209` and disputed
at `0131`), not a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that case-derived routing is worse — it
records that upstream forbids it four times in one family and states what to use instead, and §4 is
what would test it. It does not establish that a rule fitted to any particular case set generalises or
fails to. It does not supply a mechanical test for predicate admissibility; upstream gives a provenance
criterion a human can apply and no procedure for auditing an existing rule, and §2 records that gap
rather than filling it. It does not resolve `C-950td-016` — the shipped router's own four constants
appear to fail the rule's provenance test while satisfying its letter, and this entry records the
tension without adjudicating it. It does not establish `64 MiB`/`128 MiB`/`G == 7` as constants anyone
actually shipped; their appearance in a prohibition is evidence a rule of that shape existed, which is
weaker than a record of one. It does not extend the prohibition beyond this family, though `0046`
carries the same rule from a different one. No board token appears anywhere in the gather family, so
BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen.
Nothing here is established for any 910-family board.
