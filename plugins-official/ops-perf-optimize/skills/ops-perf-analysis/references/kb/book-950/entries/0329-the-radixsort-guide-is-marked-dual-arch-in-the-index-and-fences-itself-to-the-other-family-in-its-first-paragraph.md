```
ID:        0329-the-radixsort-guide-is-marked-dual-arch-in-the-index-and-fences-itself-to-the-other-family-in-its-first-paragraph
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/SKILL.md:33 — "| RadixSort 基数排序类 | TopK,
           KthValue, Sort, ArgSort, ArgMax/Min | DAV_2201 / DAV_3510 | ✅ [性能优化指南](reference/sort/radix_sort.md) |"
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:5 — "> **当前覆盖范围**：
           本文档基于 **A2 大规模数据** 实战验证；A3、A5 等架构的硬件细节差异需另行验证后再套用。"
           ; :8 — "不要把本文的 A2 二分搜索/直方图方案当作 A5 TopK 的默认实现。"
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/templates/usage_guide.md:5-6 —
           "本文用于后续重新实现或优化 Ascend 950 / DAV_3510 TopK。A2 大规模稀疏选择仍参考
           [radix_sort.md](../radix_sort.md)，二者不可直接混用。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  the appearance, in `radix_sort.md`, of a technique explicitly validated on a DAV_3510
           part — the file would then genuinely be dual-architecture and the index cell would be
           correct, making this a reading error rather than a routing defect.
```

# 0329 · The RadixSort guide is marked dual-arch in the index and fences itself to the other family in its first paragraph

## 1 · Claim
Upstream asserts, in the shelf's operator-family index, that the RadixSort family applies to
`DAV_2201 / DAV_3510` and routes both to `reference/sort/radix_sort.md`. That file asserts, in its
own opening note, that it is validated on A2 large-scale data, that hardware differences on A3 and
A5 require separate verification before its content is applied, and — in the imperative — that its
binary-search and histogram schemes must not be taken as the default implementation for A5 TopK.
Upstream asserts, in a third file the index cell does not name, that
`reference/sort/templates/usage_guide.md` is the document for Ascend 950 / DAV_3510 TopK and that
the two must not be mixed. Not established here — this is a reading of three documents, and nothing
was measured.

So the 950 authority for this family is a file the index does not route to, and the file the index
does route to refuses the routing on its first screen.

## 2 · The wrong branch this removes
The shelf's own query flow is `算子名 → 映射到算子族 → 定位并完整读取 reference/<family>/`. An agent
asked to optimise a 950 TopK follows it, lands on the index cell, sees `DAV_2201 / DAV_3510`, opens
`radix_sort.md`, and — if it reads past the opening note — stops. If it does not read past the note,
it implements an A2 histogram/binary-search scheme on a 950 part and gets no signal that anything is
wrong, because the code compiles and the answers are right.

The failure is not that the guide is bad; it is validated, densely, on the family it names. The
failure is that a routing table cell is doing scope work it cannot do. This is the same species as
`0319`, where a `DAV_3510` cell routes to a document whose every capacity constant names a 910 part
— and the two together are the finding worth carrying: **in this shelf, the 適用架構 column routes
and does not scope.** An agent must read the target document's own attribution and prefer it,
including when the two disagree.

The second wrong branch is the over-correction: treating `radix_sort.md` as worthless for 950 work.
It is not — it is a well-attributed body of A2 knowledge, and the 950-side document explicitly
preserves the pointer to it for `A2 大规模稀疏选择`. What it is not is a 950 default.

The third is silent mixing. `二者不可直接混用` is stated once, in the file most 950 readers will
never open, and the two documents describe genuinely different implementations (a multi-level
histogram with a vectorised binary-search tail against a nine-template dispatch, `0330`). An agent
that has read both and takes the best of each has built something neither document validated.

## 3 · Ground / Source
The index cell, `SKILL.md:33`:

```
| RadixSort 基数排序类 | TopK, KthValue, Sort, ArgSort, ArgMax/Min | DAV_2201 / DAV_3510 |
✅ [性能优化指南](reference/sort/radix_sort.md) |
```

Every other family row in that table names exactly one document set and one architecture; this row
names two architectures and one document. `Scalar 编码与诊断` is the only other `DAV_2201 / DAV_3510`
row.

The routed file's own scope, `reference/sort/radix_sort.md:5-8`:

```
> **当前覆盖范围**：本文档基于 **A2 大规模数据** 实战验证；A3、A5 等架构的硬件细节差异需另行验证后
> 再套用。覆盖算子族包括选择类（TopK / KthValue / Median / Quantile）、排序类（Sort / ArgSort /
> ArgMax / Min）、分桶统计类（Histogram / BinCount / Unique）、过滤输出类（Where / NonZero /
> MaskedSelect）。
...
> 不要把本文的 A2 二分搜索/直方图方案当作 A5 TopK 的默认实现。
```

The A2 attribution is not incidental to the document — it runs through it. Section headings and
statements at `:97` (`**ARCH 关键限制（A2）**`), `:121`
(`TBuf 手动 double buffer（两个 TBuf + PipeBarrier 切换）在 A2 上**不工作**`), `:218`
(`### 4.2 A2 Adds(int16) 饱和问题`), `:253` (`## 5. 跨核同步（A2 无硬件 barrier）`) and `:298`
(`### 6.1 A2 硬件特性速查`) are all architecture-specific and all name the same architecture. None
of them names a 950 part. A `grep -n "950\|3510\|arch35"` over the file returns the two lines quoted
above and nothing else.

The 950 authority, `reference/sort/templates/usage_guide.md:1-6`:

```
# DAV_3510 TopK 模板使用指南

## 1. 模板定位

本文用于后续重新实现或优化 Ascend 950 / DAV_3510 TopK。A2 大规模稀疏选择仍参考
[radix_sort.md](../radix_sort.md)，二者不可直接混用。
```

The index cell does name that path — but as a *secondary* link on the RadixSort row's document
column? It does not: the row's only link is `radix_sort.md`. The 950 document is reachable only from
inside the A2 document's own header block (`radix_sort.md:8` links to it), which means the routing
path to the 950 material runs *through* the document the 950 reader is being told not to use.

Recorded as `C-950bp-007`. Note what kind of defect this is: not a numeric disagreement, and not
resolvable by any measurement. It is a routing statement that contradicts a scope statement, and
both are readable today.

The consequence for this book's own harvest is stated for the record: **`radix_sort.md` is not
mined into book-950 at all.** Its content is A2-attributed by its own author, and RULES.md Art. 1
forbids carrying it here. What it says about the *other* family is that family's business.

## 4 · Procedure
No device is required and none is proposed. This entry is a reading claim about three documents, and
the honest procedure is a re-read, not a run — declaring a device procedure here would be ceremony.

Arm 1 — `[no-card]`, and **run**: `grep -n` for every architecture token (`950`, `3510`, `arch35`,
`A5`, `Atlas`, `2201`, `A2`, `A3`, `910`) over `reference/sort/radix_sort.md` and over
`reference/sort/templates/usage_guide.md`, and record which tokens each file carries and where. The
result is in §3 and §6.

Arm 2 — `[no-card]`, **not run**: the same sweep over all thirteen family document sets in the
shelf, producing a table of `index cell architecture` against `document self-attribution`. This
entry and `0319` are two rows of that table found by hand; the table itself would say how general
the defect is, and it costs nothing but has not been produced. Owed in
`harvest/standing/950-bp.md`.

Arm 3 — the part that would need a card, stated so that a later agent does not mistake its absence
for an oversight. If anyone wishes to know whether the A2 binary-search and histogram schemes in
fact perform badly on a 950 part, that is a **separate claim** requiring its own entry, its own
BOARD line and its own §4: build the A2 scheme and the DAV_3510 template stack (`0330`) on the same
named 950 board, at shapes both admit, with a variance floor and `0327`'s contamination check, and
compare. This entry deliberately does not ask it, for a reason that is the entry's own subject:
upstream does **not** claim the A2 schemes perform badly on A5 — it claims their hardware
differences are unverified there (`需另行验证后再套用`). "Unverified" and "refuted" are different
states, and treating the first as the second is the same collapse the index cell makes in the other
direction. A device arm attached to *this* entry would therefore be measuring a claim nobody made.

Refuses to assume: that a document's placement in a family directory scopes it; that an index cell
is authored by whoever authored the document it points at; that `不可直接混用` is enforced anywhere
(it is a sentence, and nothing checks it).

## 5 · Checker — acceptance declared before the run
Verdict `routed_doc_attribution` = the set of architecture tokens `radix_sort.md` carries in a
scoping position. Declared before the sweep: the entry is **supported** iff that set contains A2
tokens and contains no DAV_3510 token in a *validating* position. The OVERTURN fires iff a technique
in that file is stated as validated on a 950 part.

Verdict `index_cell` = the architecture string in `SKILL.md:33`.
Verdict `950_doc_reachable_from_index` = true iff the shelf's index links the DAV_3510 TopK document
directly. Declared: `false` is the predicted result and is the defect.

The checker must be able to go red, and here is how. The sweep is run **first** against a control
document whose architecture attribution is not in dispute — `reference/scatter/scatter_design.md`,
which states `适用：DAV_3510（A5 / Ascend950）` at `:12` and matches its index cell. The sweep must
report that document as consistent. If the instrument reports the control as inconsistent, its
notion of "scoping position" is wrong and every verdict from it is void. That is a planted positive
the sweep has to find, and without it a grep for architecture tokens would flag every document that
mentions any chip for any reason — which is most of them.

There is no exit code to be the verdict; the deliverable is a table.

## 6 · Evidence
NOT YET RUN as a device procedure — no readout exists, and nothing in this file is a measurement.
Arm 1 was performed as a file read under the phase-1 read-only exception and its result is in §3:
`radix_sort.md` carries A2 attributions at `:5`, `:8`, `:97`, `:121`, `:218`, `:253` and `:298`, and
carries no 950 validation anywhere; `templates/usage_guide.md` carries the DAV_3510 attribution at
`:1` and `:5`. A grep is not a measurement, establishes nothing about any part, and cannot tell
whether either document's content is correct.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry establishes a contradiction between an index cell and a
document's own scope statement — it does **not** establish that the A2 techniques fail on 950,
which upstream never claims either; the claim on both sides is that they are unverified there, and
unverified is not refuted. It does not establish that `templates/usage_guide.md` is correct for 950,
only that it is the file claiming that scope (`0330`–`0333` carry its content, all at harvested
stratum). It does not establish how widespread the index-cell/document mismatch is: two instances
were found by hand (`0319` is the other), the shelf-wide sweep that would say was not run. Nothing
from `radix_sort.md` is carried into this book, so nothing here should be read as a judgement of its
A2 content, which belongs to the other book and is not this agent's to assess (RULES.md Art. 1). BOARD is
`family-claimed(unverified)`: the defect is in documentation routing and no board is implicated.
