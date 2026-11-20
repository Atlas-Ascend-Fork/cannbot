```
ID:        0105-parameter-space-analysis-is-four-serial-gated-stages-and-skipping-one-voids-the-candidate-set
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/parameter-analysis.md:3,7-16 —
           "候选枚举的前置步骤。不完成本分析则候选解集无效。" and
           "四个阶段串行执行，不可跳过或合并" with the gate column
           "清单非空 / 每参数有分类 / ≥1 个算法命中 / 每算法有生成规则"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured comparison on a named 950 board where a candidate set built without the
           §1-§2 parameter census reaches the same or better best-case time than one built with
           it, over the same search budget — that would make the prerequisite optional rather
           than voiding.
```

# 0105 · Parameter-space analysis is four serial gated stages, and skipping one voids the candidate set

## 1 · Claim
Upstream asserts that candidate enumeration has a mandatory prerequisite analysis of four stages
executed serially, which may be neither skipped nor merged, and that without it the candidate
solution set is void (`不完成本分析则候选解集无效`). The four stages and their gates, as upstream
states them: §1 determine the full set of tiling parameters the kernel actually receives — gate:
the list is non-empty; §2 classify each parameter and trace the provenance of each constraint —
gate: every parameter has a classification; §3 decide which algorithms are enabled for the current
shape/dtype by walking the family's `tiling-flow.md` decision tree — gate: at least one algorithm
hits; §4 construct the candidate solution space for each hit algorithm — gate: every algorithm has
a generation rule. Upstream further asserts the product is written to
`{工作目录}/参数空间分析.md`. Not established here.

## 2 · The wrong branch this removes
The wrong branch is the natural one: an agent asked to tune tiling starts enumerating values for
the parameters it can see in the tiling struct. Two things go wrong and neither is caught. First,
the parameter set is wrong — upstream's §1 explicitly separates fields that reach the kernel from
fields used only host-side, and the latter are not tuning dimensions; enumerating them wastes the
whole search budget on axes that cannot change the kernel. Second, the *gates* are what make the
stages more than a checklist: `≥1 个算法命中` fails loudly when a shape falls outside every
algorithm's entry condition, and an agent without that gate silently proceeds with the fallback
and reports a tuned result for a regime nobody modelled. Compare `harvest/CONTRADICTIONS.md`
C-950tiling rows in this block and the matmul MTE2 gate gap at 0107, where the interval
[70 %, 85 %) is routed by no arm at all — exactly the state §3's gate exists to surface.

## 3 · Ground / Source
`ops/ascendc-perf-optimize/references/tiling/parameter-analysis.md:1-18`, in full:

```
# 参数空间与算法使能分析

> 候选枚举的前置步骤。不完成本分析则候选解集无效。

---

## 执行顺序

四个阶段串行执行，不可跳过或合并：

| 阶段 | 目标 | 门禁 |
|------|------|------|
| §1 | 确定 kernel 实际接收的 tiling 参数全集 | 清单非空 |
| §2 | 参数类型分类，约束来源追溯 | 每参数有分类 |
| §3 | 判定当前 shape/dtype 下可用的算法 | ≥1 个算法命中 |
| §4 | 构建各命中算法的候选解空间 | 每算法有生成规则 |

产出写入 `{工作目录}/参数空间分析.md`。
```

§1's method, `:22-28`: read the demo code, find the host→kernel tiling structure, list every
field; separate fields passed to the kernel from fields used only on the host and exclude the
latter as non-tuning; then analyse how the kernel uses each field and extract the implicit
constraints (branch conditions, range checks).

§3's method, `:57-61`: load the family's `tiling-flow.md` decision tree and check each algorithm's
gate conditions, and for each hit extract its parameter delta against the default baseline —
extra constraints, fixed constants, tunable parameters added or removed. Output shape:
`算法 → 命中/未命中（原因） + 可调参数 + 特殊约束`.

Note on the gates as written: three of the four are satisfiable by construction and cannot go red
in practice — a parameter census is non-empty whenever the struct has a field, every parameter has
*a* classification once you assign one, and every algorithm has *a* generation rule once you write
one. Only §3's `≥1 个算法命中` can fail on real input. This is the same species as the
cannot-fail checklists elsewhere in this skill, and it is recorded here rather than adjudicated:
the gates are quoted as upstream states them, and the observation that three are vacuous is this
book's, not upstream's.

§2's provenance rule is the substantive content of this procedure and carries its own entry, 0104;
§4's candidate-range rule carries 0106.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The claim
is a procedure claim, so what is measured is the outcome of following it versus not.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; export `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Paired search, one operator family per pair, three families (matmul, reduction, scatter — chosen
because the first has the most parameters, the second has upstream's own worked self-check, the
third has upstream's only board-named measurement). For each family pick two shapes.
Arm WITH: run §1-§4 as written, producing the parameter census, the classification table, the
enabled-algorithm list with reasons, and the per-algorithm generation rule; enumerate candidates
from that.
Arm WITHOUT: enumerate over every field in the tiling struct, uniform ranges, same total candidate
budget (equal number of built-and-run points, fixed in advance).
Build every point with one compiler pin; md5 each binary so two candidates that should differ are
shown to differ; run under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5
discarded, per-case timing with no representative sampling.

Refuses to assume: that a free die stays free; that a die may be substituted; that the two arms
may share a build cache (each arm rebuilds from clean); that equal candidate *counts* means equal
wall-clock cost — both are recorded separately.

## 5 · Checker — acceptance declared before the run
Verdict variable `prereq_gain` = (best `aic_time` in arm WITHOUT − best `aic_time` in arm WITH) /
best in arm WITHOUT, one value per (family, shape) pair, six values. Declared before the run: the
"void without it" claim survives in its strong form iff every pair has `prereq_gain > 0` and at
least one pair exceeds 0.10; it survives in a weak form (useful, not voiding) if the median is
positive but any pair is negative; it is falsified iff the median is ≤ 0. A pair in which arm
WITHOUT fails to produce any correct-result candidate is recorded as arm WITH winning by
default, and that fact is stated rather than folded into a ratio.

The exit code is not the verdict, and a search harness that crashes mid-arm exits non-zero while
having produced a valid partial best — so the verdict is computed from the recorded per-candidate
table, and the checker goes red if either arm's table has fewer rows than the declared budget.
The failure species this guards against: an arm WITHOUT whose candidates were mostly rejected at
build time would show a flattering best-of while having explored almost nothing, so the checker
also reports built-and-ran counts per arm and refuses a verdict when they differ by more than 10 %.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no search was run. The entry does not establish that the four stages are
the right four, that serial execution is necessary (upstream asserts it; no ablation exists), or
that the analysis is worth its cost — the procedure above is designed to answer that and has not
been run. It does not establish that the three vacuous gates are harmless. No chip is named in
`parameter-analysis.md`, so BOARD is `family-claimed(unverified)` and the chip is unstated; §4
names 950PR/950DT because that is where our future run would happen, not because upstream measured
anywhere. Nothing here is established for any 910-family board.
