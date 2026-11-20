```
ID:        0347-the-matmul-family-names-no-chip-in-any-of-its-seven-files-and-inherits-its-architecture-from-one-table-cell
LABEL:     boundary
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled.
           The absence reported below is a file read of upstream's own tree.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/SKILL.md:30 — "| MatMul 矩阵乘类 | MatMul,
           BatchMatMul, MatMul_MXFP4, MatMul_A16W16 | DAV_3510 | ✅ [性能优化指南](reference/matmul/guide.md) |"
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/ — seven markdown files
           (guide, pingpong, mte2_preload, swat, streamk, fullload, scale_coalescing); a search for
           `950`, `3510`, `arch35`, `A5`, `Atlas`, `DAV_`, `910`, `A2` across all seven returns
           nothing. Measured figures appear at mte2_preload_design.md:7,263-267,
           fullload_design.md:7,319 and scale_coalescing_design.md:257-259 with dtype, shape and
           core count and **no board**.
SOURCE:    harvest/claims/ascendc-performance-best-practices--001-matmul-mte2-preload-is-measured-but-its-family-is-marked-dav-3510.md
           — the wave-1 harvest card that first recorded this routing question and declined to
           resolve it into book-910.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -rniE '950|3510|arch35|A5|Atlas|DAV_|910|A2' <shelf>/reference/matmul/*.md
OVERTURN:  any chip, architecture or board name appearing in a scoping position inside the matmul
           family's own files — the family would then carry its own attribution and this entry's
           subject would not exist.
```

# 0347 · The matmul family names no chip in any of its seven files and inherits its architecture from one table cell

## 1 · Claim
Upstream asserts, in one cell of its operator-family index, that the MatMul family targets
`DAV_3510`. Upstream asserts nothing else about this family's architecture anywhere: its seven
markdown files contain no chip name, no architecture token and no board name of any kind — a search
for `950`,
`3510`, `arch35`, `A5`, `Atlas`, `DAV_`, `910` and `A2` across all seven returns nothing. Three of
the files carry measured before/after timings — the MTE2 Preload seven-column table
(`0304`), the A-Full-Load MXFP4 result (`0311`), and the scale-coalescing result (`0312`) — each
with a dtype, a shape and in one case a core count, and none with a part. So every entry this book
draws from that family (`0301`–`0313`) carries `BOARD: family-claimed(unverified)`, and the whole
architecture attribution for thirteen entries rests on one cell of one table in a file none of the
seven links to for that purpose. Not established here beyond the file read reported in §3.

## 2 · The wrong branch this removes
The wrong branch is invisible and is this book's own. Thirteen entries were written into book-950 on
the strength of a routing decision; if the cell is wrong, thirteen entries are in the wrong book,
and RULES.md Art. 1 exists precisely to prevent facts from one board family being attributed to another.
This entry is where that risk is stated rather than absorbed.

For a consuming agent the branch is more ordinary and more likely. It reads
`mte2_preload_design.md`, finds `BF16 M=1024, K=4096, N=2048` measured at `66.0μs → 63.3μs`, and
carries the number. Nothing in the file says which machine produced it. The figure is precise to
three decimal places across seven pipe segments and is attributable to no part at all — so it
cannot be compared against a re-measurement, cannot be scaled to a different core count, and cannot
be excluded on the grounds that the reader's part differs. Precision without attribution reads as
authority.

The second branch is the routing one and it has already been walked once, correctly. The wave-1
harvest card recorded that a book-910 brief named these numbers as a target while the family's
`適用架構` column said `DAV_3510`, and declined to write them into book-910 — `写入 book-910 会把
一个真实测量挂到错误的书上`. That card is the record of a rule beating an instruction, and this
entry inherits its conclusion together with its uncertainty (`0304` §1 supersedes the card and keeps
it in place).

The third is the general form, and it is the one worth transmitting: **an architecture attribution
that lives only in an index cell is a routing statement, not a scope statement.** `0319` shows the
cell disagreeing with the document's own constants; `0329` shows the document refusing the cell
outright. Here the document says nothing at all, which is the quietest of the three and the hardest
to notice — there is no contradiction to spot, only an absence.

## 3 · Ground / Source
The cell, `SKILL.md:30`:

```
| MatMul 矩阵乘类 | MatMul, BatchMatMul, MatMul_MXFP4, MatMul_A16W16 | DAV_3510 |
✅ [性能优化指南](reference/matmul/guide.md) |
```

The family, read: `guide.md`, `pingpong_design.md`, `mte2_preload_design.md`, `swat_design.md`,
`streamk_design.md`, `fullload_design.md`, `scale_coalescing_design.md` — 2011 lines. A
case-insensitive search for `950`, `3510`, `arch35`, `A5`, `Atlas`, `DAV_`, `910` and `A2` across all
seven returns **zero lines**. The nearest thing to an architecture statement is generic —
`昇腾 AI 处理器` (`swat_design.md:5`, `streamk_design.md:5`) and `昇腾 AI Core 的 MTE2 发射单元`
(`scale_coalescing_design.md:9`).

What the measured passages do carry, for contrast — this is the shape of a measurement that is
scoped in every dimension except the one that matters most:

```
mte2_preload_design.md:261 — 以 `M=1024, K=4096, N=2048`、BF16、`baseM=baseN=256,
  baseK=128/sizeof(BF16)=64, kL1=512/sizeof(BF16)=256, kL1TileNum=16, PINGPONG_NUM=2` 为例
fullload_design.md:273     — `[128, 4096, 81920]` MXFP4, aicNum=32
scale_coalescing_design.md:257 — MTE2 段时间（`[128, 8192, 4096]`）| 34.4 μs | 31.27 μs | −9%
```

Shape, dtype, every tiling field, and for one of them a core count — and no board, no CANN version,
no tool, no repeat count and no variance. `aicNum=32` is the closest the family comes to naming
hardware, and it is a launch parameter, not a part: `950:0217` records installed 950 SKUs with 4, 8,
28, 32 and 36 cube cores, so 32 is consistent with a 950 and identifies nothing.

Other families in this same shelf do state their scope in their own text. `scatter_design.md:12`:
`适用：**DAV_3510（A5 / Ascend950）**`; `sort/templates/usage_guide.md:5`:
`本文用于后续重新实现或优化 Ascend 950 / DAV_3510 TopK`; `simt/optimization-guide.md:5`:
`本文面向 Ascend 950（DAV_3510）上的 Ascend C SIMT 算子`. So the shelf's convention is that a family
document declares its own architecture, and the matmul family is the one that does not.

The consequence for this block, stated for the record rather than hidden in a footnote: entries
`0301`–`0313` all carry `BOARD: family-claimed(unverified)`, and each one's §7 says the same thing —
if the index cell is wrong, those entries are booked in the wrong book. This entry is the single
place that risk is named, so that it can be checked once rather than re-argued thirteen times.

The wave-1 card that first raised it,
`harvest/claims/ascendc-performance-best-practices--001-...`, reached the same conclusion from the
other direction and left the 950-side decision to a later agent. `0304` takes that decision and
retains the card (RULES.md Art. 9).

Nothing here is measured.

## 4 · Procedure
This is an absence claim about seven files plus a routing claim about one table cell. The reading
arms need no device; the arm that would actually settle the attribution needs a board and belongs to
the entries whose numbers it would confirm.

Arm 1 — `[no-card]`, **run** (§3): the eight-token search across the family's seven files, plus the
same search across the other twelve families to establish that self-declaration is this shelf's
convention. Result: matmul returns nothing; scatter, sort and simt declare themselves.

Arm 2 — `[no-card]`, **partly done**. The shelf's own `evals/evals.json` was read and it makes the
picture worse rather than better. Eval id 2 is titled `MatMul 族在 DAV_3510 上的优化`, its prompt
asks `在 DAV_3510 架构上适用的优化指南是什么`, and its config declares
`"ascend_platforms": ["A2"]`. So the one artefact outside the index that attributes this family to an
architecture attributes it to **two, in the same object** — DAV_3510 in the title and prompt, A2 in
the platform tag. `950:0004` records the identical defect in the sibling skill (an `A2` platform tag
over an A5-only card library), which makes this the second instance of one species rather than an
isolated slip, and means an eval's platform field is not usable as evidence of anything here.
Remaining and **not run**: the rest of the repository — plugin manifests, sibling-skill
cross-references. Owed in `harvest/standing/950-bp.md`.

Arm 3 — the attribution itself, which only a run settles and which this entry does not own. Any of
`0304`, `0311` or `0312`'s §4 reproduces a measured figure on a **named** board; whichever runs first
supplies the family's first real attribution, and if the reproduced figures land far from upstream's
on a 950 part, the index cell becomes the suspect rather than the measurement. That is the honest
route: the cell is confirmed or impeached by the numbers underneath it, not by more reading.

Refuses to assume: that the absence is an oversight rather than a deliberate generality (upstream may
intend these techniques as architecture-independent, in which case the index cell is the error and
not the files); that a generic phrase (`昇腾 AI 处理器`) scopes anything; that `aicNum=32` names a
part.

## 5 · Checker — acceptance declared before the run
Verdict `tokens_found` = the set of architecture tokens located in the matmul family's own files.
Declared before the search: the entry is **supported** iff it is empty. The OVERTURN fires on any
token in a scoping position — a token inside a code identifier or an unrelated number does not
count, and that distinction is why the search output is read rather than counted.

Verdict `convention` = the number of the shelf's thirteen families whose own documents declare an
architecture. This is what turns "matmul says nothing" from an observation into a deviation.

Verdict `external_attribution` from Arm 2 — any statement of this family's architecture outside the
index cell.

The checker must be able to go red, and the fixture is a positive control: the same eight-token
search is run first against `reference/scatter/`, where `适用：**DAV_3510（A5 / Ascend950）**` at
`scatter_design.md:12` **must** be found. If the search cannot find a declaration that exists, its
empty result on matmul establishes nothing and `tokens_found` is void. An absence claim from an
unvalidated search is the cheapest possible blind result, and one control command excludes it.

There is no exit code to be the verdict; the deliverable is the token inventory.

## 6 · Evidence
NOT YET RUN as a device procedure — nothing was compiled, nothing was timed, and no board was
contacted. Nothing in this file is a measurement.

Arm 1 was performed as a file read under the phase-1 read-only exception, on 2026-08-24, against the
seven files (2011 lines) of `reference/matmul/`: the eight-token search returns zero lines, and the
same search against `reference/scatter/`, `reference/sort/templates/` and `reference/simt/` returns
their declarations. Arm 2 was partly performed: `evals/evals.json` eval id 2 carries `DAV_3510` in
its title and prompt and `"ascend_platforms": ["A2"]` in its config. A search establishes what
strings are present in a tree on one day. It cannot establish which part produced upstream's
timings, whether the index cell is correct, or whether the techniques are architecture-independent.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry establishes an absence in seven files as read on
2026-08-24 — it does **not** establish that the `DAV_3510` cell is wrong, nor that it is right, and
it deliberately does not resolve the routing: only a reproduction on a named board can
(§4 Arm 3, owned by `0304`/`0311`/`0312`). It does not establish that the absence is an oversight;
the techniques may be intended as architecture-independent, which would make the index cell the
defect instead, and nothing here distinguishes the two. The wider-repository search (Arm 2) is only
partly done — `evals/evals.json` was read and contradicts itself (DAV_3510 in the title and prompt,
`A2` in the platform tag), and plugin manifests and sibling-skill cross-references were not searched,
so a statement of this family's architecture may exist somewhere unread. That eval contradiction is
recorded and is used as evidence in neither direction. `aicNum=32` is a
launch parameter and is not treated as identifying a part. The thirteen entries drawn from this
family (`0301`–`0313`) inherit this uncertainty, and each says so in its own §7; this entry is
their shared record, not their resolution. BOARD is `family-claimed(unverified)` — the only honest
token when the evidence names no board, per `form/CONVENTIONS.md`. Nothing transfers to the other
book (RULES.md Art. 1), and the wave-1 card that considered writing this family's measurement into
book-910 is retained as the record of why it did not.
