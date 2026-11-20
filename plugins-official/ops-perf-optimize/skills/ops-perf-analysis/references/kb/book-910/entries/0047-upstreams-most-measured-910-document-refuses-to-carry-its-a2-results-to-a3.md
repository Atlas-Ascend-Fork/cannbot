```
ID:        0047-upstreams-most-measured-910-document-refuses-to-carry-its-a2-results-to-a3
LABEL:     boundary
LEVEL:     L7 (verification)
STRATUM:   harvested — drafted from one upstream origin; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:5 — "本文档基于 **A2 大规模数据** 实战验证；A3、A5 等架构的硬件细节差异需另行验证后再套用"; ibid:7-8 — "不要把本文的 A2 二分搜索/直方图方案当作 A5 TopK 的默认实现"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  the A2 findings in that document are shown to hold unchanged on a named Ascend910_93 (A3) part — which would make the refusal unnecessary, though not wrong to have made.
```

# 0047 · Upstream's most-measured 910 document refuses to carry its A2 results to A3

## 1 · Claim
Upstream asserts that its A2 sort/selection optimisation document is validated on A2 large-scale
data only, and that hardware detail differences on A3 and A5 must be verified separately before its
content is applied there. Upstream repeats the fence for a specific case: its A2 binary-search and
histogram schemes must not be taken as the default A5 TopK implementation. Not established here —
and this entry claims the refusal, not the findings.

## 2 · The wrong branch this removes
A2 and A3 share an NpuArch (0001), an `__NPU_ARCH__` value (0001), and a SocVersion enum (0002).
Every identifier an agent can query returns the same answer on both. The natural conclusion — the
only one the machine supports — is that they are the same target, and that a result measured on one
holds on the other.

Upstream's own most-measured 910 document says otherwise, in its first substantive line, and
declines to extend. That is worth an entry by itself, because it is the single upstream statement
that tells a consuming agent the identifier collapse is not merely an inconvenience: the parts
differ enough that a team who measured on one would not vouch for the other.

The wrong branch removed is therefore not a coding error but a *scoping* one: taking any of
0041–0046, or any A2-marked upstream material, as established for Ascend910_93. This book's BOARD
fields already refuse that, and this entry records that upstream independently refuses it too.

The mirror-image error is equally available and equally wrong: concluding from this refusal that A2
and A3 are known to differ. They are not. Upstream says the differences "需另行验证" — need
separate verification — which is a statement about what has not been checked, not about what has
been found.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md`, lines 5-8, verbatim in full:

"> **当前覆盖范围**：本文档基于 **A2 大规模数据** 实战验证；A3、A5 等架构的硬件细节差异需另行
验证后再套用。覆盖算子族包括选择类（TopK / KthValue / Median / Quantile）、排序类（Sort / ArgSort
/ ArgMax / Min）、分桶统计类（Histogram / BinCount / Unique）、过滤输出类（Where / NonZero /
MaskedSelect）。"

"> Ascend 950 / DAV_3510 TopK 已有独立的多模板性能复现方案，必须改读
> [TopK 模板使用指南](templates/usage_guide.md)。不要把本文的 A2 二分搜索/直方图方案当作 A5 TopK
> 的默认实现。"

What makes this the strongest 910 evidence in the sources surveyed for this book, and why it earns
an entry rather than a footnote:
- it is the only document in scope that declares a *verification scope* for itself and then honours
  it, rather than stating results and leaving the reader to guess;
- it carries a measured ladder including regressions (0049), which is the mark of a record kept
  rather than a case made;
- it names its own architecture-specific limits in a dedicated table (§6.1, feeding 0041–0046,
  0048) rather than mixing them into prose;
- and its 適用架構 marking in `ops/ascendc-performance-best-practices/SKILL.md:34` is
  "DAV_2201 / DAV_3510", i.e. the skill's index claims wider applicability than the document itself
  does. The document is more conservative than its own index. That asymmetry is worth noting: an
  agent routed by the index table would arrive believing the content is dual-architecture, and only
  reading line 5 corrects it.

The other anti-extrapolation fence in the repo, for contrast and not as corroboration (same repo,
one origin, and it concerns the 950 family):
`ascendc-perf-optimize/references/tiling/sort/topk_host_tiling.md:193` — "这些数值是性能策略，
不是架构能力边界". That statement is another agent's domain; it is cited here only to record that
the discipline appears twice upstream and both times in sort material.

## 4 · Procedure
Proposed, runnable later; not run. Testing a refusal to extend means testing whether the extension
would in fact have held — which needs both parts and is the most expensive procedure in this block.

1. Two physically different parts are required: one Atlas A2 (Ascend910B1–B4 or 910B2C) and one
   Atlas A3 (Ascend910_93). Name both dies, record `npu-smi info -t board` for each, check occupancy
   before and after on each, and refuse to substitute — substituting a die here destroys the
   experiment, since the parts ARE the variable.
2. Run the arms of 0041 (barrier cost), 0042 (TBuf/TQue overlap), 0044 (int16 saturation), 0045
   (ReduceSum dtypes) and 0046 (half exactness) on both parts, unchanged, same binary where the
   toolchain allows one binary for both.
3. Record every result twice, per part, and never merge them.
4. If only one part is available, this procedure does not run. Record that, rather than running
   half of it — a single-part result is what the entry exists to warn against.

## 5 · Checker — acceptance declared before the run
Verdict: per sub-claim, the pair `(result_A2, result_A3)` and a boolean `agrees`.
This entry's claim — that upstream was right to refuse — is not decided by `agrees` at all, and
saying so before the run is the point. If every sub-claim agrees, the refusal was *unnecessary in
these five cases* and remains correct as a matter of discipline; §1's OVERTURN is written that way
deliberately. If any disagrees, the refusal was load-bearing and the corresponding entry's BOARD
must narrow.
The one outcome that would be a genuine error is a run on one part reported as covering both. §5
declares in advance that no merged verdict may be issued, and that a single-part run yields
NOT ATTEMPTED for every sub-claim rather than a partial pass.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. This entry does not establish that A2 and A3 differ in any
respect — upstream declines to extend, which is not a finding of difference (see §2). It does not
establish what those differences would be if they exist; this book's STANDING_QUESTIONS carries the
open question of what separates A3 from A2 at all. It does not validate the A2 findings themselves;
those are 0041–0046 and 0048–0050, each harvested and unmeasured. It says nothing about whether
other A2-marked upstream material carries the same self-imposed limit — most of it does not, which
makes that material weaker, not stronger.
