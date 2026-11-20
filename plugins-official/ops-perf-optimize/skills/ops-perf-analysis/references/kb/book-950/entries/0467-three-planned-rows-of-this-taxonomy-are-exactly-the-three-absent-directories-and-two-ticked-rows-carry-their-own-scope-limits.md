```
ID:        0467-three-planned-rows-of-this-taxonomy-are-exactly-the-three-absent-directories-and-two-ticked-rows-carry-their-own-scope-limits
LABEL:     boundary
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/SKILL.md:10-20 — the nine-row operator taxonomy, of which
           ":16 | Random 随机类 | 生成随机数,需种子管理 | RandomUniform, Dropout | 📋 规划中 |" ·
           ":18 | Convolution 卷积类 | 空间卷积，滑动窗口计算 | Conv2D, DepthwiseConv | 📋 规划中 |" ·
           ":20 | NN 神经网络类（其它）| 神经网络专用，多种操作组合 | GroupNorm 等非 attention | 📋 规划中 |"
           and the two qualified ticks ":15 ⚠️ [场景路由](references/conversion/patterns.md)（当前仅
           Transpose 部分支持）" · ":17 ✅ [场景路由](references/matmul/patterns.md)（mxfp8 + eltwise
           融合；其它 matmul 形态规划中）"
SOURCE:    same skill, the `references/` directory listing — six directories (broadcast, conversion,
           elewise, flashattention, matmul, reduction) against nine taxonomy rows
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read (no device):
           sed -n '10,20p' upstream/skills-dev-main/ops/ascendc-tiling-design/SKILL.md
           ls upstream/skills-dev-main/ops/ascendc-tiling-design/references/
OVERTURN:  a further `references/<family>/` directory appearing in this skill without its taxonomy row
           losing the 📋 marker, or a 📋 row acquiring content — the listing would then stop being a
           faithful index of coverage and an agent could no longer read coverage from `ls`. Equally:
           a consumer that routes correctly using only the taxonomy ticks, without reading the
           parenthetical qualifiers, would show the two qualified rows cost nothing.
```

# 0467 · Three planned rows of this taxonomy are exactly the three absent directories, and two ticked rows carry their own scope limits

## 1 · Claim
Upstream asserts a nine-category operator taxonomy for tiling design, with a status marker per row.
Upstream asserts that three categories — Random, Convolution, and "NN (other)" — are planned rather
than present, marking each `📋 规划中` with no linked document. The skill's `references/` directory
holds six subdirectories, and they are exactly the six rows that are not marked planned: the taxonomy
table and the directory listing carry the same information. Upstream further asserts, inside two of the
six present rows, that their coverage is narrower than their marker suggests: the Conversion row is
marked `⚠️` and says only Transpose is partly supported, and the MatMul row is marked `✅` and says its
scope is mxfp8 plus eltwise fusion with other matmul forms still planned. Not established here; this
entry records a coverage state and its transmission channel.

## 2 · The wrong branch this removes
Without this entry an agent routing an operator to a tiling methodology reads the status column. A
`✅` means covered, a `📋` means not; that is what the column is for. The wrong branch is taking the
`✅` on the MatMul row at face value: an agent with a plain fp16 matmul routes there, opens
`references/matmul/patterns.md`, and finds a document scoped in its second line to one fusion pattern —
whose multi-core answer (`K 轴在核内迭代,不参与核间切分`) is the opposite of what the general matmul
family elsewhere in this corpus does under StreamK (`0107`, `0309`). Both are correct in their own
scope, and the routing tick is what put the agent in the wrong one. This is `0469`'s subject and it
starts here, in the status column.

The second wrong branch is the mirror: reading the three `📋` rows as "no knowledge exists" and
inventing a methodology. Two of the three have coverage elsewhere in the corpus under other names —
Dropout is a filter operator with an implementation in the installed toolkit, and depthwise convolution
is carried at `0348`/`0349` from another shelf — so the absence is an absence *in this skill*, not in
the material.

## 3 · Ground / Source
The taxonomy's three planned rows, `ops/ascendc-tiling-design/SKILL.md:16`, `:18`, `:20`:

```
| Random 随机类 | 生成随机数，需种子管理 | RandomUniform, Dropout | 📋 规划中 |
| Convolution 卷积类 | 空间卷积，滑动窗口计算 | Conv2D, DepthwiseConv | 📋 规划中 |
| NN 神经网络类（其它）| 神经网络专用，多种操作组合 | GroupNorm 等非 attention | 📋 规划中 |
```

and the six that are not, at `:12-15`, `:17`, `:19`. Against them, `ls references/` gives:
`broadcast`, `conversion`, `elewise`, `flashattention`, `matmul`, `reduction` — six directories for six
non-planned rows, and no directory for any planned row. The correspondence is exact.

That exactness is the entry's reason. This corpus already records the opposite property on the
neighbouring shelf: `0152`, `0156` and `0163` each record a `占位` (placeholder) label sitting over a
directory that holds complete content, and `0169` records the one directory in that shelf that is a
genuine placeholder. So on `ascendc-perf-optimize`, `ls` is *not* an index of coverage and the labels
are unreliable in the direction of understatement; on `ascendc-tiling-design`, `ls` **is** an index of
coverage. An agent that has learned the first shelf's habit will over-trust `ls` here or under-trust
it there, and the two shelves must be treated differently. That is a filename-channel property, which
this project has measured as a real transmission mechanism (`form/CONVENTIONS.md`; plan Amendment §5).

The two qualified ticks, `:15` and `:17`:

```
| Conversion 数据转换类 | 改变布局/形状，合并/拆分张量 | Transpose, Concat, Split | ⚠️ [场景路由](references/conversion/patterns.md)（当前仅 Transpose 部分支持） |
| MatMul 矩阵乘类 | 矩阵乘法，高计算密度，用Cube单元 | MatMul, BatchMatMul | ✅ [场景路由](references/matmul/patterns.md)（mxfp8 + eltwise 融合；其它 matmul 形态规划中） |
```

These are the rows where the status column and the parenthetical disagree in *degree*. Conversion is
honest twice — the marker is `⚠️` and the text narrows it. MatMul is not: the marker is `✅`, the same
glyph as Reduction and FlashAttention, and only the parenthetical says that two of the three named
example operators (`MatMul, BatchMatMul`) are out of scope. So the status column alone over-reports
coverage for exactly one of the nine rows, and it is the row for the most commonly requested operator
in the table. Recorded as `C-950fin-014`.

One further asymmetry, stated for three rows and not for the others: Reduction, Elementwise, Broadcast
and FlashAttention carry `⚠️ 必须先读` on their routing document, a mandatory-first-read marker
(`:12`, `:13`, `:14`, `:19`). Conversion and MatMul do not. The four with the marker are the four whose
routing document is a `patterns.md`-style scene router or, for FA, an analysis document; upstream never
says what the marker's absence means for the other two.

One repository, one origin (RULES.md Art. 3). The `references/` listing and the SKILL.md table are two
artifacts of the same skill.

## 4 · Procedure
This entry is about a document's structure, so its verification is a document procedure, not a device
procedure. It is written to be run later and is not run here; it needs no board and no device, and it
must not be confused with a measurement.

**Arm 1 — the correspondence, mechanically.** A script that parses SKILL.md's taxonomy table, extracts
each row's status marker and its linked path, lists `references/`, and reports three sets: rows with a
marker but no directory, directories with no row, and rows whose linked path does not exist. Run it
against this skill and against `ascendc-perf-optimize` in the same invocation. The expected result is
empty sets for this skill and non-empty for the neighbour (`0152`, `0156`, `0163`, `0169`), which is
the contrast the entry claims.

**Arm 2 — the qualifier audit.** For each of the six present rows, compare the status glyph against the
scope actually stated in the first ten lines of the linked document. Report, per row, whether the
document narrows what the glyph promises. The prediction from §3 is that MatMul does and Conversion
does so consistently with its `⚠️`.

**Arm 3 — the consumer test, which is the only arm that could show the qualifier matters.** Give an
agent that has not read this entry a plain fp16 `BatchMatMul` requirement and this skill, and record
which document it opens and what tiling decision it produces. Repeat with the MatMul row's
parenthetical removed and then with the glyph changed to `⚠️`. This is a procedure over an agent, not
over a device; its outcome is a routing choice, not a number, and §5 declares how it is scored before
it is run.

**Arm 4 — re-derivation on a later revision, retained because it may not bite.** Re-run arm 1 against
a later revision of the upstream skill. If a directory ever appears without its row changing, the
OVERTURN's first half has fired and this entry is demoted; if not, the property held across a revision,
which is worth more than it held once.

Refuses to assume: that a marker means what the column header implies (arm 2 checks against the
documents); that this skill's convention generalises to any other skill (arm 1 runs both); that a
routing failure is attributable to the glyph without the counterfactual (arm 3 varies exactly one
thing); that a property observed at one revision is a property of the skill (arm 4).

## 5 · Checker — acceptance declared before the run
Verdict `index_faithful(skill)` from arm 1: `true` iff all three reported sets are empty. Declared
before the run: acceptance for this entry is `index_faithful(ascendc-tiling-design) == true` **and**
`index_faithful(ascendc-perf-optimize) == false`. Both halves are required — a checker that only
confirmed this skill's tidiness could not show that the tidiness is a property of *this* skill, which
is the claim a consumer needs.

Verdict `glyph_overreports(row)` from arm 2, boolean per row. Acceptance: `true` for MatMul and false
for the other five.

Verdict `misroutes` from arm 3 ∈ {`with_qualifier`, `without_qualifier`, `both`, `neither`}. Declared
now: the qualifier is shown to be load-bearing only if the result is `without_qualifier`. `both` means
the glyph dominates and the parenthetical is not read, which would strengthen `C-950fin-014` rather
than weaken it. `neither` means the routing is robust and the qualifier costs nothing — the OVERTURN's
second half.

The exit code is not the verdict: arm 1's script exits 0 whether the sets are empty or not, and arm 3's
outcome is a document choice. Guards: (1) the script fails red if it parsed fewer than nine taxonomy
rows or zero directories — a parser that silently matched nothing would report empty sets, which is the
blind-checker species this book records repeatedly, and the row count is the positive fixture it must
find; (2) **the input that makes this checker go red**: `ascendc-perf-optimize`, which must come back
`false` — if both skills report faithful, the script is not detecting mismatches at all; (3) every run
records the upstream revision it read, since arm 4's whole value is the comparison across revisions.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The nine taxonomy rows with
their markers, the two parenthetical qualifiers, the four mandatory-first-read markers and the
`references/` listing are file reads performed at drafting time; the six-directory listing and the nine
rows were counted directly rather than taken from any survey. The observation that the three planned
rows correspond exactly to the three absent directories is arithmetic over those two readings, not an
observation of any tool's behaviour.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or run, and nothing here is about hardware at all. The entry does not
establish that the correspondence will hold at any other revision of the upstream skill — it was read
once, at one revision, and arm 4 is the only thing that would make it a durable property. It does not
establish that the three planned categories lack knowledge anywhere; two of the three have material
elsewhere in this corpus under other shelves, and this entry records an absence *in this skill* only.
It does not establish that the qualified ticks cause misrouting; arm 3 is the procedure that would, and
its subject is an agent rather than a device. It does not evaluate the six present families' content —
Broadcast, Reduction, Conversion and Elementwise are carried elsewhere in this book from their own
documents, and FlashAttention is `0451`–`0466`. It does not say what the absent `⚠️ 必须先读` marker
means on the Conversion and MatMul rows. This entry has no board content of any kind; BOARD is
`family-claimed(unverified)` because the artifact it describes names no architecture, and no procedure
in §4 touches a device. Nothing here is established for any 910-family board, or for any 950 board.
