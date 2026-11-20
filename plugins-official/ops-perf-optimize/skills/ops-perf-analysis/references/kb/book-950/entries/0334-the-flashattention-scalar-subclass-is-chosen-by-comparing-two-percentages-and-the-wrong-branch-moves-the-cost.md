```
ID:        0334-the-flashattention-scalar-subclass-is-chosen-by-comparing-two-percentages-and-the-wrong-branch-moves-the-cost
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/flash_attention/guide.md:19-26 —
           "| `SCALAR%` | `SCALARLDST%` | 子类 | 加载策略 | | 任意 SCALAR_BOUND | 任意 | **通用前置**
           | **先**做 scalar_general_techniques 4 手段（跨子类、低风险），再按下方子类深化 | | ≥ 80% |
           < SCALAR% | **SCALAR** | scalar_precompute（S1–S5） | | 任意 | ≥ 95% **或** > SCALAR% |
           **SCALARLDST** | scalarldst_subbound（MR1–MR5） | | ≥ 95% | ≥ 95% | **MIXED** | 先
           MR1–MR5（对 SCALAR 无副作用），重采 trace 后重判 |" · "> 当 SCALARLDST 是真正主瓶颈时，
           禁止仅按 scalar_precompute 推进。S1/S2/S5 的"成员预计算"会把 SCALAR ALU 压力转嫁给
           SCALARLDST 访存通路，可能导致 case cycle 劣化。"
SOURCE:    ops/ascendc-performance-best-practices/SKILL.md:41 — "**SCALAR_BOUND 子类选择规则**：
           FIA（及其他 FA 变体）命中 SCALAR_BOUND 时，必须按 Step 3 报告的 `SCALAR%` 与
           `SCALARLDST%` 判定子类 ... `SCALAR% > SCALARLDST%` 走 SCALAR 子类；`SCALARLDST% ≥ 95%
           或 > SCALAR%` 走 SCALARLDST 子类；两者都 ≥ 95% 先做 MR1–MR5 再重判。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured FIA case on a named 950 board with `SCALARLDST% > SCALAR%` where the
           precompute techniques (S1/S2/S5) improve cycle time — the transfer of ALU pressure onto
           the load/store path would then not be net-negative there, and the routing rule's
           prohibition would be over-strict.
```

# 0334 · The FlashAttention scalar sub-class is chosen by comparing two percentages, and the wrong branch moves the cost instead of removing it

## 1 · Claim
Upstream asserts that a FlashAttention-family operator diagnosed as `SCALAR_BOUND` splits into
sub-classes decided by two profiled percentages, `SCALAR%` and `SCALARLDST%`, and that the choice
determines which optimisation set applies. Upstream asserts a mandatory generic prelude for every
sub-class — the four scalar-shedding techniques (`0335`) — described as cross-sub-class and
low-risk. Upstream asserts the SCALAR branch at `SCALAR% ≥ 80%` with `SCALARLDST% < SCALAR%`,
routing to precompute techniques S1–S5. Upstream asserts the SCALARLDST branch at
`SCALARLDST% ≥ 95%` **or** `SCALARLDST% > SCALAR%`, routing to load-shedding techniques MR1–MR5.
Upstream asserts a MIXED case at both ≥ 95 %, handled by running MR1–MR5 first (stated to have no
side effect on SCALAR) and re-profiling before deciding again. Upstream asserts the mechanism behind
the prohibition: when SCALARLDST is the real bottleneck, the precompute techniques S1, S2 and S5
convert ALU work into member reads, transferring pressure from the ALU onto the load/store path and
potentially degrading case cycle time. Not established here.

The shelf's index states the same rule with one difference: it gives the SCALAR branch as
`SCALAR% > SCALARLDST%` without the `≥ 80%` floor that the family guide adds.

## 2 · The wrong branch this removes
"Scalar-bound" reads as one condition and is two. The default response — precompute the arithmetic,
hoist invariants, replace division by shifts — attacks the ALU. If the bottleneck is the load/store
path, every one of those moves *adds* a member read where an ALU operation used to be, and upstream
states the result is possibly a slowdown. So the wrong branch here is not merely unproductive; it is
counterproductive, and it looks like progress the whole time because the SCALAR percentage does fall.

That is the entry's operational content: **the two percentages must be compared to each other, not
just to a threshold.** An agent that sees `SCALAR% = 85 %` and applies S1–S5 has satisfied the
`≥ 80%` floor and may still be on the wrong branch, because the rule's second clause is relative.
Upstream's SCALARLDST condition is a disjunction with a comparison in it (`≥ 95% 或 > SCALAR%`)
precisely so that a high absolute SCALAR does not license the SCALAR branch on its own.

The second wrong branch is skipping the prelude. The four generic techniques are asserted to apply
to every sub-class, and they address a different location entirely — kernel entry, `Init`, and
instruction-cache misses in the main loop — rather than the ALU or the load path. An agent that
routes straight to a sub-class skips the work with the largest reported effect in the family
(`0335`: eight cases out of SCALAR_BOUND) in favour of the work with the smallest (`0336`: −1.51 %).

The third is the MIXED handling, which is a small piece of method worth carrying. Upstream does not
attempt to decide MIXED cases; it runs the intervention asserted to have no side effect on the other
axis, then **re-measures and re-classifies**. Re-profiling after a change that moves the bottleneck
is the correct move and it is rarely the default one.

## 3 · Ground / Source
The routing table, `flash_attention/guide.md:17-26`:

```
## 子类选型规则（强制）

| `SCALAR%` | `SCALARLDST%` | 子类 | 加载策略 |
| 任意 SCALAR_BOUND | 任意 | **通用前置** | **先**做 scalar_general_techniques 4 手段（跨子类、
  低风险），再按下方子类深化 |
| ≥ 80% | < SCALAR% | **SCALAR** | scalar_precompute（S1–S5） |
| 任意 | ≥ 95% **或** > SCALAR% | **SCALARLDST** | scalarldst_subbound（MR1–MR5） |
| ≥ 95% | ≥ 95% | **MIXED** | 先 MR1–MR5（对 SCALAR 无副作用），重采 trace 后重判 |

> 当 SCALARLDST 是真正主瓶颈时，禁止仅按 scalar_precompute 推进。S1/S2/S5 的"成员预计算"会把
> SCALAR ALU 压力转嫁给 SCALARLDST 访存通路，可能导致 case cycle 劣化。
```

The prerequisite, `:7`:

```
> **使用前置**：先通过性能分析报告确认 `bound_type`、`SCALAR%`、`SCALARLDST%`、启动头开销或
> hot loop `GetValue` 模式，再用本表"子类判定"列选策略。
```

The two statements of the rule differ. The shelf index (`SKILL.md:41`) gives the SCALAR branch as
`SCALAR% > SCALARLDST%`; the family guide gives `≥ 80%` **and** `< SCALAR%`. A case at
`SCALAR% = 60 %`, `SCALARLDST% = 30 %` routes to SCALAR by the index and to no branch at all by the
guide. Same repository, one origin (RULES.md Art. 3), so this is a document disagreeing with itself; it
is recorded rather than resolved.

The table is also not a partition. `SCALAR% = 96 %`, `SCALARLDST% = 40 %` satisfies the SCALAR row
(≥ 80, and 40 < 96) and does not satisfy SCALARLDST or MIXED — fine. But `SCALAR% = 96 %`,
`SCALARLDST% = 96 %` satisfies SCALAR's row too (96 ≥ 80, but 96 < 96 is false — so no), while
`SCALAR% = 97 %`, `SCALARLDST% = 96 %` satisfies **both** SCALAR (97 ≥ 80, 96 < 97) and SCALARLDST
(96 ≥ 95), and MIXED (both ≥ 95). Three rows match one case, and the table states no precedence.
Upstream's prose resolves it in one direction (MIXED runs MR first) and the table does not.
Recorded in `harvest/standing/950-bp.md`; it is the same species `950:0005` records for the sibling
shelf's bound-routing tree — arms without precedence.

The mechanism is stated once and is the load-bearing sentence: S1/S2/S5's member precomputation
`会把 SCALAR ALU 压力转嫁给 SCALARLDST 访存通路`. `0336` §3 states the same trade from the other
side — `继续把 ALU 计算改成成员预计算可能只是在"少一次乘法"和"多一次成员 load"之间对冲`. That is a
*hypothesis about where the cost goes*, and the family reports no measurement of the transfer.

The percentages themselves come from "Step 3" of the sibling perf-optimize workflow, which this book
carries as `950:0001`. Their definitions, their denominators and the tool that produces them are not
restated here.

Nothing in this section is measured by this book.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The claim is a routing rule,
so the procedure measures whether the routing predicts the outcome.

Arm 1 — the routing's predictive value. Assemble a set of FIA cases spanning the
(`SCALAR%`, `SCALARLDST%`) plane, including cases in each of the four rows and at least two in the
overlap region §3 identifies. For every case, apply **both** interventions independently (S1–S5 and
MR1–MR5), and record the cycle change for each. The rule is supported iff the branch the table
selects is the branch that wins, case by case.

Arm 2 — the transfer mechanism, which is the half nobody has measured. On cases where S1–S5 is
applied, record `SCALAR%` and `SCALARLDST%` *before and after*. The stated mechanism predicts
SCALAR% falls and SCALARLDST% rises. If both fall, precomputation is not transferring pressure and
the prohibition rests on nothing; if SCALARLDST% rises and cycles still improve, the transfer is
real and the prohibition is over-strict — which is the OVERTURN.

Arm 3 — the prelude's independence. Apply the four generic techniques alone and re-profile. Upstream
asserts they are cross-sub-class; that predicts they change cycle time without changing which branch
the table selects. If applying them flips the classification, the prelude is not neutral and the
prescribed order (prelude, then classify) is wrong — it should be classify, prelude, re-classify.

Arm 4 — the MIXED assertion. On a case with both ≥ 95 %, apply MR1–MR5 and check the claim that it
has `对 SCALAR 无副作用`: record `SCALAR%` before and after.

Variance floor first, and it dominates: `0336` reports the SCALARLDST branch's whole effect at
−1.51 %, so a floor above about 1 % makes half this study unreportable. One build, 30 in-process
runs, 5 fresh-process runs, IQR over median, beside every figure, with `0327`'s same-path sibling
check applied before any table is read. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that `SCALAR%` and `SCALARLDST%` are measured against the same
denominator — both are echoed with their raw counters, because a rule built on comparing two ratios
is void if the ratios are not commensurable, and no upstream document states their definitions.

## 5 · Checker — acceptance declared before the run
Verdict `route_correct` = the fraction of Arm 1 cases where the table-selected intervention beats
the other, outside the floor. Declared before the run: the rule is **supported** iff
`route_correct ≥ 0.8` and no case shows the table-selected branch *degrading* cycles.

Verdict `transfer_observed` = true iff Arm 2 shows `SCALARLDST%` rising when S1–S5 is applied. The
OVERTURN fires iff `transfer_observed` is true **and** cycles nonetheless improve on
`SCALARLDST% > SCALAR%` cases.

Verdict `prelude_neutral` = true iff Arm 3 leaves the table's selection unchanged.
Verdict `mr_no_scalar_effect` = true iff Arm 4's `SCALAR%` is unchanged within the floor.
Verdict `overlap_cases` = the classification each overlap-region case receives from each of the two
upstream statements of the rule, reported side by side.

The exit code is not the verdict. Three guards. First, every intervention build is compared
elementwise against a reference: MR1's removal of a lazy-init guard and MR4's member localisation
are both refactors that can change behaviour, and `0336` §3 records upstream's own red line about
one of them (a modulus that must not become a bit-and). Second — the input that makes this checker
go red — Arm 1 includes at least one case that is **not** `SCALAR_BOUND` at all, where the table
should not be applied; the harness must classify it as out of scope rather than routing it. If a
non-scalar-bound case receives a branch, the classifier is reading a threshold it should never have
reached, and every routing verdict is suspect. Third, `route_correct` is never computed from cycle
time alone on cases whose `SCALAR%`/`SCALARLDST%` denominators differ between builds; those are
reported as incomparable.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 80 % and 95 % thresholds
are upstream's stated cuts; no case was profiled, no intervention applied, and the pressure-transfer
mechanism has never been observed by anyone whose report is in this tree.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The two thresholds (80 %, 95 %) carry no derivation and no
measurement anywhere in the family — they are policy cuts, and `950:0015`'s neighbourhood records
that this repository's severity ladders are experience lines rather than hardware thresholds. The
table is not a partition and states no precedence; the case at `SCALAR% = 97 %`,
`SCALARLDST% = 96 %` matches three rows. The shelf's index and the family guide state the SCALAR
condition differently (`> SCALARLDST%` against `≥ 80% ∧ < SCALAR%`), and this entry records the
disagreement without resolving it — same repo, one origin (RULES.md Art. 3). `SCALAR%` and `SCALARLDST%`
are never defined: no denominator, no counter, no tool version. The pressure-transfer mechanism that
justifies the prohibition is asserted twice and measured never. The claim that MR1–MR5 has no side
effect on SCALAR is asserted with no measurement. The whole rule is scoped to the FlashAttention
family and to FIA specifically (`已实测`); other variants are "参照通用方法论迁移", which is not
evidence. BOARD is `family-claimed(unverified)`: the family is marked DAV_3510 in the shelf index and
no file names a board. Nothing transfers to the other book (RULES.md Art. 1).
