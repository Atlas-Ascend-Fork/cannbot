```
ID:        0472-one-ub-budget-is-written-as-elements-against-a-byte-capacity-and-the-twin-file-sizes-the-same-area-with-two-different-types
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/matmul/patterns.md:103-109 —
           "``` / UB 总用量 = matmulArea + stageNum × stageSize_ /
           matmulArea  = CeilDiv(baseM, taskRation) × baseNAlign  (SplitM 修正) /
           stageSize_  = min(剩余 UB / stageNum / sizeof(DataType) / baseNAlign × baseNAlign,
           matmulArea) / ``` / 必须满足 `UB 总用量 ≤ TOTAL_UB_SIZE`（不同芯片 UB 容量不同，
           见 [SAMPLE] S1）。"
SOURCE:    same family, matmul-fusion-design-template.md:218-231 —
           "lastUBBytes = UB_SIZE - matmulArea × sizeof(DataType)   // 剩余 UB 字节数 /
           usableElems = lastUBBytes / stageNum / sizeof(DataType)  // 每 stage 可用元素数 /
           stageSize_  = min(usableElems / l1NAlign × l1NAlign, matmulArea)  // 对齐后取 min" ·
           ":231 — **UB 容量自检**：`matmulArea × sizeof(float) + stageNum × stageSize_ ×
           sizeof(DataType) ≤ TOTAL_UB_SIZE`" · ":214 — matmulArea = l1MSplit × l1NAlign
           // matmul 结果占用 UB 元素数"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an mxfp8 + eltwise fusion on a named 950 board, with a non-float `DataType`, whose UB
           occupancy computed by the template's `lastUBBytes` line agrees with the occupancy computed
           by its own self-check line — the two `sizeof` choices would then be equivalent in practice
           and the discrepancy would be notational. Equally: a build sized by `patterns.md`'s
           element-count comparison that overruns UB at a shape where the template's byte comparison
           refuses is the observation this entry predicts.
```

# 0472 · One UB budget is written as elements against a byte capacity, and the twin file sizes the same area with two different types

## 1 · Claim
Upstream asserts, in the tiling document for the mxfp8 matmul + eltwise fusion, a UB budget
`UB 总用量 = matmulArea + stageNum × stageSize_` and requires it to satisfy
`UB 总用量 ≤ TOTAL_UB_SIZE`. Upstream asserts, in the design template of the same family, that
`matmulArea` is a count of **elements** (`matmul 结果占用 UB 元素数`), and states the same self-check
in bytes: `matmulArea × sizeof(float) + stageNum × stageSize_ × sizeof(DataType) ≤ TOTAL_UB_SIZE`.
Upstream asserts, two lines above that self-check, a residual computation
`lastUBBytes = UB_SIZE - matmulArea × sizeof(DataType)`, using `sizeof(DataType)` for the same area
the self-check sizes with `sizeof(float)`. Not established here; this entry records two arithmetic
inconsistencies inside one family's UB budget.

## 2 · The wrong branch this removes
Without this entry an agent implements whichever formula it reads. Both are presented as the UB
capacity check; both name `TOTAL_UB_SIZE`; neither flags the other. The tiling document's version
compares a **quantity in elements** against a **capacity in bytes**, so at `sizeof(DataType) = 4` it
under-reports occupancy by a factor of four, and at half precision by eight. A design that passes that
check can be four to eight times over capacity, and UB overrun in this corpus is documented as silent
(`0458`), so the failure is a corrupted neighbouring buffer rather than an allocation error.

The normal checks do not catch it because the check *is* the thing that is wrong. There is no second
opinion: `TOTAL_UB_SIZE` is a `[SAMPLE]` constant the implementer sets per chip (`0474`), the tiling
engine's outputs are opaque (`0469`), and the arithmetic is done on paper at design time. An agent that
computes it correctly and an agent that computes it as written both produce a number and a tick.

The second wrong branch is subtler and only bites when `DataType` is not float. The template's residual
line subtracts `matmulArea × sizeof(DataType)` from `UB_SIZE`, while its own self-check charges that
same area `matmulArea × sizeof(float)`. `matmulArea` is the Fixpipe output region, which the layout
diagram (`patterns.md:74-83`) and the buffer table (`:140`) both give as float — it is the matmul
accumulator's landing area. So the self-check is the one that matches the layout, and the residual line
under-subtracts whenever `sizeof(DataType) < 4`, leaving `stageSize_` too large by exactly the
difference. An agent that migrates the epilogue to half — which the `[SAMPLE]` register's S2 row
anticipates — inherits a `stageSize_` computed from a residual that is `matmulArea × 2` bytes too big.

## 3 · Ground / Source
The tiling document's budget, `references/matmul/patterns.md:103-109`:

```
UB 总用量 = matmulArea + stageNum × stageSize_
matmulArea  = CeilDiv(baseM, taskRation) × baseNAlign  (SplitM 修正)
stageSize_  = min(剩余 UB / stageNum / sizeof(DataType) / baseNAlign × baseNAlign, matmulArea)

必须满足 `UB 总用量 ≤ TOTAL_UB_SIZE`（不同芯片 UB 容量不同，见 [SAMPLE] S1）。
```

`matmulArea` here is `CeilDiv(baseM, taskRation) × baseNAlign` — a product of two extents, so a count
of elements, with no `sizeof` anywhere. `stageSize_`'s own expression divides by `sizeof(DataType)`,
so it too is a count of elements. Therefore `UB 总用量` is a count of elements, and
`TOTAL_UB_SIZE` is a capacity in bytes — the name says so, and the template uses it as bytes at `:219`
and `:231`. The comparison at `:109` is dimensionally unsound as written. Registered as
`C-950fin-016`.

The template's version, `matmul-fusion-design-template.md:209-231`:

```
l1NAlign   = CeilDiv(baseN, ALIGN_ELEM) × ALIGN_ELEM    // N 对齐到 32B
taskRation = AscendC::GetTaskRation()                    // SplitM 拆分比（=2）
l1MSplit   = CeilDiv(baseM, taskRation)                  // 每个 Vector 核分到的 M
matmulArea = l1MSplit × l1NAlign                        // matmul 结果占用 UB 元素数
```

```
lastUBBytes = UB_SIZE - matmulArea × sizeof(DataType)   // 剩余 UB 字节数
usableElems = lastUBBytes / stageNum / sizeof(DataType)  // 每 stage 可用元素数
stageSize_  = min(usableElems / l1NAlign × l1NAlign, matmulArea)  // 对齐后取 min
```

```
**UB 容量自检**：`matmulArea × sizeof(float) + stageNum × stageSize_ × sizeof(DataType) ≤ TOTAL_UB_SIZE`
```

The template's comment on `:214` states the unit explicitly — `matmul 结果占用 UB 元素数`, a count of
elements — which is what makes the tiling document's comparison checkable at all: without it, `UB
总用量` could have been read as bytes. And the template's own two lines disagree with each other about
what an element of that area weighs: `sizeof(DataType)` at `:219`, `sizeof(float)` at `:231`.
Registered as `C-950fin-017`.

Which one is right is decided by the layout, not by preference. `patterns.md:74-83` puts `cLocal_` —
the matmul result arriving from L0C via Fixpipe — at UB offset 0 with layout
`ND [curMPad, curNUbAlign]`, and the AIV buffer table at `:140` gives `UB_L0COut` a size of
`baseMPad × baseNUbAlign × sizeof(float)`. Both say float. So `:231` matches the layout and `:219`
does not, and Art. 7 still applies — the two are recorded, and the resolution is a run, not a reading.
§4 arm 1 is that run.

Two further quantities in these formulas have no stated source. `TOTAL_UB_SIZE` is a `[SAMPLE]` value
the implementer redefines per chip (`0474`, S1) — and this corpus records four different UB constants
across the neighbouring shelf's scripts with none chip-scoped (C-006), plus a shelf-level disagreement
about the capacity itself (C-003, C-004). `baseNAlign` appears in `patterns.md` and `l1NAlign` in the
template, computed from `baseN` and `ALIGN_ELEM`; whether they are the same quantity under two names,
upstream does not say, and `0471` records that `ALIGN_ELEM` is itself dtype-dependent.

Two files, one repository: one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

**Arm 1 — which `sizeof` the area actually takes.** One mxfp8 + Div fusion. Query UB at runtime
(`GetCoreMemSize(CoreMemType::UB)`), echo it, and echo the device-side addresses and extents of
`cLocal_`, `dLocal_` and `resultLocal_`. Compute the true occupancy of the Fixpipe output region from
the echoed addresses. Compare against `matmulArea × sizeof(float)` and against
`matmulArea × sizeof(DataType)` for `DataType ∈ {float, half}`. This is a direct read of which line is
right, and it resolves `C-950fin-017` without needing any of the budget arithmetic.

**Arm 2 — the element-versus-byte check.** Construct a tiling whose `UB 总用量` **in elements** is
below `TOTAL_UB_SIZE` and whose occupancy **in bytes** exceeds the queried UB capacity — which the
tiling document's check accepts and the template's rejects. Build it and run it. Report: whether it
faults, whether the output agrees, and whether the sentinel written into the region past the computed
budget survives. `0458` predicts a silent overrun; this arm is where `C-950fin-016` acquires a
consequence rather than a dimensional argument.

**Arm 3 — the residual line under a dtype migration.** Build with `DataType = half`, computing
`stageSize_` once with `lastUBBytes` as written (`sizeof(DataType)`) and once with `sizeof(float)`.
Echo both `stageSize_` values and the resulting total occupancy against the queried capacity. Report
which, if either, exceeds it. This is the failure §2 names and it needs no unusual shape — only a
dtype the sample was not written for.

**Arm 4 — the two alignment names, retained because it may not bite.** Echo `baseNAlign` (as used in
`patterns.md`) and `l1NAlign` (as computed in the template) from one build and compare. If they are
always equal, they are one quantity under two names and §3's note is documentation only; if they can
differ, the two budget formulas are not even about the same tile.

Refuses to assume: that a free die stays free, or that a die may be substituted; that `TOTAL_UB_SIZE`
is the hardware capacity (both are queried and echoed separately, and this corpus records four
incompatible values for the constant, C-006); that a build that does not fault is within capacity
(arm 2's sentinel decides that); that `matmulArea` is what the host computed (echoed from the device);
that `GetTaskRation()` is 2 (`0470`, echoed); that a correct output means the budget was right.

## 5 · Checker — acceptance declared before the run
Verdict `area_element_bytes` from arm 1: the measured bytes per element of the Fixpipe output region,
declared before the run to be compared against 4 and against `sizeof(DataType)`. Acceptance for §3's
reading: `area_element_bytes == 4` for every `DataType`. The OVERTURN fires iff it equals
`sizeof(DataType)` — the template's residual line would then be right and its own self-check wrong,
which is the same contradiction resolved the other way and is reported as such.

Verdict `element_check_overruns` from arm 2 ∈ {`silent_overrun`, `fault`, `fits_anyway`}.
`fits_anyway` would mean `TOTAL_UB_SIZE` as set in the sample is far below the real capacity and the
dimensional error is masked by a conservative constant — which is a finding about the constant, not an
absolution of the formula, and it is declared as a distinct outcome now rather than read as a pass.

Verdict `stagesize_delta(half)` from arm 3: the difference between the two computed `stageSize_`
values, and whether either total exceeds the queried capacity.

Verdict `align_names_agree` from arm 4, boolean.

The exit code is not the verdict: an over-budget build exits 0 and corrupts a neighbour (`0458`), which
is the entry's whole premise. Guards: (1) arm 2 pre-fills the region immediately past the computed
budget with a sentinel and compares it byte-exactly afterwards, and a run that did not read the
sentinel back is `untestable`, never `fits`; (2) **the input that makes this checker go red**: a
tiling comfortably inside capacity by both formulas, which must show an intact sentinel — if the
sentinel is destroyed there, the harness's notion of "past the budget" is wrong and arm 2's result is
an artifact; (3) no figure is reported without the queried UB capacity, the `TOTAL_UB_SIZE` constant in
force, `DataType`, echoed `matmulArea`, echoed `stageSize_`, `stageNum`, and the CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The two budget statements, the
element-count comment, the residual line, the self-check line, the UB layout diagram and the AIV buffer
table are file reads performed at drafting time. The dimensional analysis in §3 — that `matmulArea` and
`stageSize_` are both element counts, so their sum is an element count, compared at `:109` against a
byte capacity — is arithmetic over upstream's own expressions and their own unit comments, not an
observation of any build or allocation.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or allocated. The entry does not establish which of the two `sizeof`
choices is correct: §3 gives a reading based on the layout diagram and the buffer table, and Art. 7
forbids settling a source disagreement by which reading is more plausible — §4 arm 1 is the procedure
that would settle it. It does not establish that the element-versus-byte comparison ever causes an
overrun in practice; the `TOTAL_UB_SIZE` constant it compares against is itself a sample value with no
authority (`0474`, C-003, C-004, C-006), so a conservative setting could mask the error entirely. It
does not establish `TOTAL_UB_SIZE`, `baseNAlign`, `l1NAlign`, `baseM/baseN/baseK` or the tiling
engine's behaviour — all are delegated to SWAT (`0469`, `Q-950fin-19`). It does not resolve whether
`baseNAlign` and `l1NAlign` are one quantity. It covers the mxfp8 + eltwise fusion pattern only
(`0469`) and its statically-offset UB layout (`0473`); nothing here transfers to a `TPipe`-managed UB
or to any other family's budget. No board token appears in any quoted passage, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
