```
ID:        0461-a-gqa-output-row-is-written-back-one-row-at-a-time-because-bsnd-makes-the-block-rows-non-contiguous
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/subfamilies.md:120 —
           "- **GQA 输出 BSND 写回必须逐行 DataCopy**:Q / Out BSND layout `[B, Sq, Hq, D]` 中同 qHead
           内相邻 Sq 行间隔 `Hq × D`,**Bq 行不连续**。若用批量 `DataCopy(GM, UB, curBq × D)` 会破坏邻
           qHead 输出。正确做法:按 (g, i) 二维循环,每行单独
           `DataCopyPad(outGm[gOff + i × qRowStride], outUb[(g × Bq + i) × D_align], {1, D, ...})`"
SOURCE:    same file:135 — "- [ ] **清单 7(输出写回 BSND)**:按 (g, i) 二维循环逐行 `DataCopyPad`,
           不做批量 `DataCopy(GM, UB, curBq × D)`" ; same shelf, design.md:385 — "- [ ] **清单 7
           (GQA 输出 BSND 写回)**:输出按 (g, i) 二维循环逐行 `DataCopyPad`,不做批量
           `DataCopy(GM, UB, curBq × D)`(Bq 行不连续);见 subfamilies §3.1"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a GQA build on a named 950 board whose batched `DataCopy(GM, UB, curBq × D)` write-back
           leaves the neighbouring query heads' output intact and agrees elementwise with the FP64
           reference — the BSND stride would then not be what upstream states, or the batched call
           would honour it, and the row-by-row obligation would be unnecessary. Equally: a per-row
           `DataCopyPad` write-back that is measurably slower than the batched form by more than the
           variance floor gives the obligation a cost, which upstream states nowhere.
```

# 0461 · A GQA output row is written back one row at a time, because BSND makes the block rows non-contiguous

## 1 · Claim
Upstream asserts that under the BSND layout `[B, Sq, Hq, D]` used for a GQA operator's query and
output tensors, two sequence positions of the same query head are `Hq × D` elements apart, so the `Bq`
rows a task produces are not contiguous in the output. Upstream asserts that a batched
`DataCopy(GM, UB, curBq × D)` write-back therefore damages the neighbouring query heads' output.
Upstream asserts the correct form: a two-level loop over `(g, i)` writing each row separately with
`DataCopyPad(outGm[gOff + i × qRowStride], outUb[(g × Bq + i) × D_align], {1, D, ...})`. Upstream
states this as a pre-review checklist item in two files. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent writes back the block it computed. The block is `[mEff, D]` in UB, it is
contiguous there, the output tile is `[curBq, D]` per query head, and one `DataCopy` of `curBq × D`
elements is the obvious call — it is one instruction instead of `curBq`, it is what every contiguous
write-back in the corpus looks like, and its length is arithmetically right.

The trap is that the length is right and the destination stride is not. BSND interleaves the query
heads at the innermost-but-one position, so consecutive `Sq` rows of one head are separated by the
whole head dimension of every other head. A flat copy of `curBq × D` elements starting at one head's
offset writes straight through its neighbours. The output is not merely wrong — it is wrong *in a
different query head than the one being computed*, so a per-head comparison of the head under test
passes while the damage appears in a head that some other task will overwrite later, or not.

The normal checks do not catch it in the shape an MVP uses. At `Hq = 1` there are no neighbours to
damage, and the flat copy is correct. At `curBq = 1` there is one row and the two forms are identical.
So the defect requires `Hq > 1` **and** `curBq > 1` together, which is the same conjunction structure
this family records at `0462` for a different pair of dimensions and which a dimension-at-a-time
opening order (`design.md:476-485`) will not produce until both are open.

The second wrong branch is choosing `DataCopy` over `DataCopyPad` for the per-row call. Upstream
specifies `DataCopyPad` with an explicit `{1, D, ...}` parameter block: the row is `D` elements, the UB
source is indexed at `D_align` stride, and the destination is at `qRowStride`. A per-row `DataCopy`
would still write `D_align` elements from a `D_align`-strided source, padding included, and the pad
columns would land in the next row's memory.

## 3 · Ground / Source
The rule with its layout arithmetic, `references/flashattention/subfamilies.md:120`:

```
- **GQA 输出 BSND 写回必须逐行 DataCopy**:Q / Out BSND layout `[B, Sq, Hq, D]` 中同 qHead 内相邻 Sq 行间隔 `Hq × D`,**Bq 行不连续**。若用批量 `DataCopy(GM, UB, curBq × D)` 会破坏邻 qHead 输出。正确做法:按 (g, i) 二维循环,每行单独 `DataCopyPad(outGm[gOff + i × qRowStride], outUb[(g × Bq + i) × D_align], {1, D, ...})`
```

Three quantities appear in one expression and they are three different strides, which is why this is a
trap and not an arithmetic note. The destination advances by `qRowStride`, the GM row pitch. The source
advances by `D_align`, the UB row pitch, which differs from `D` whenever the head dimension is not a
multiple of the block. And the copy length is `D`, the true row width. An implementation that uses one
number for all three is correct only when `D == D_align == qRowStride / 1`, which is the aligned
single-head case.

The source index `(g × Bq + i)` is the Bq-major row order that `0452` records — so this write-back is
the third of the three reasons upstream gives for that ordering, and the two entries are two halves of
one design decision. Reversing the row order would make this loop's source index `(i × curG + g)`,
which is a valid loop and a different memory access pattern.

The rule appears again as a checklist item in the same file (`:135`) and in the design shelf
(`design.md:385`), where the parenthetical `(Bq 行不连续)` carries the reason inline. Three locations,
one repository: one origin (RULES.md Art. 3).

What upstream does not state anywhere is the cost. `curBq` separate `DataCopyPad` calls replace one
`DataCopy`, and MTE3 instruction issue is not free; the family's own PipeBarrier discipline (`0464`)
is built around exactly this kind of per-instruction overhead. Upstream gives no measurement, no ratio
and no note that a cost exists. Recorded as `Q-950fin-10`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first: 30 in-process and 5 fresh-process runs of the
per-row build, IQR over median, beside every timing point.

**Arm 1 — the damage, localised.** One GQA kernel with the write-back switchable. Initialise the whole
output tensor to a per-element sentinel derived from its `(b, s, h, d)` index, so that any byte written
by the wrong task is identifiable by where it *came from*. Run one task computing one query head, with
the batched write-back, at `Hq ∈ {1, 2, 8}` × `curBq ∈ {1, 2, 16}`. Report, per cell: agreement for the
head under test, and the count of sentinel bytes destroyed in **other** heads. Upstream predicts damage
exactly when `Hq > 1` and `curBq > 1`.

**Arm 2 — the three strides.** The per-row build with each of the three quantities independently
mis-set — copy length `D_align` instead of `D`; source stride `D` instead of `D_align`; destination
stride `D` instead of `qRowStride` — at a shape with `D` not a multiple of the alignment block. Report
which rows and which columns disagree in each case. This turns "use these three numbers" into three
separable observations, and the column-versus-row pattern of the disagreement identifies which stride
was wrong, which is the diagnostic an implementer actually needs.

**Arm 3 — the cost, which upstream never states.** Per-row versus batched write-back, both correct
(batched run at `Hq = 1` where it is legal), across `curBq ∈ {1, 2, 8, 32, 64}`. Report MTE3 time and
total `aiv_time` for each. This gives `Q-950fin-10` its first number and says what the obligation costs
at the largest `curBq` the tiling permits.

**Arm 4 — the row order coupling, retained because it may not bite.** The per-row build with the UB row
order set `Sq`-major (`row(i, g) = i × curG + g`) and the source index adjusted to match, so the
write-back is still correct. If the two orders measure the same, the Bq-major convention's third
stated reason is not a performance reason and `0452`'s three reasons reduce to two; if `Sq`-major is
slower, the coupling is real and measurable.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a correct head
under test implies a correct tensor (arm 1's sentinel exists because it does not); that `D_align`
equals `D` (every arm echoes both); that `qRowStride` is what the host computed (echoed from the
device); that one `curBq` characterises the cost; that a fast write-back is a correct one.

## 5 · Checker — acceptance declared before the run
Verdict `neighbour_damage(Hq, curBq)` from arm 1: the count of destroyed sentinel bytes outside the
head under test, declared before the run. Acceptance for the rule: `neighbour_damage > 0` exactly on
the cells with `Hq > 1 and curBq > 1`, and `== 0` elsewhere. The OVERTURN fires iff
`neighbour_damage == 0` on every cell — the batched copy would then honour the layout and the
obligation would be unnecessary.

Verdict `stride_signature(mis-set)` from arm 2 ∈ {`trailing_columns`, `row_shift`, `head_bleed`,
`none`}, one per mis-set stride, declared as three distinct predictions before the run rather than read
off afterwards.

Verdict `perrow_cost(curBq) = t_perrow / t_batched` from arm 3, with its floor.

The exit code is not the verdict: the batched build exits 0 and produces a correct answer *for the head
it computed*, which is what a naive per-tile comparison checks. Guards: (1) the checker compares the
**entire** output tensor against the sentinel-plus-reference image, and fails red if any region was
excluded from the comparison — a comparison scoped to the tile under test is the blind-checker species
and would pass the defect this entry is about; (2) **the input that makes this checker go red**: arm 1
at `Hq = 1`, where the batched copy is legal and must produce zero damage — if damage is reported
there, the sentinel or the indexing is wrong and every other cell is an artifact; (3) no cell is
reported without `Hq`, `curBq`, `D`, the echoed `D_align` and `qRowStride`, the CANN pin and the atol.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The layout arithmetic, the
prohibition on the batched call, the per-row `DataCopyPad` form and its three indices, and the two
checklist restatements are file reads performed at drafting time. The observation that the expression
carries three distinct strides, and the observation that the defect needs `Hq > 1` and `curBq > 1`
together, are readings of upstream's own line, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the batched copy damages
neighbours on this hardware, only that upstream states the layout stride and the consequence. It does
not establish the cost of the per-row form, which upstream never mentions (`Q-950fin-10`). It does not
cover the input side: `Q`'s Nd2Nz read from the same BSND layout is asserted at `subfamilies.md:117`
to be `自然连续` under the Bq-major order, and that claim is not tested here. It does not cover other
layouts — `overview.md:19` says BNSD and SBHD need their own stride derivations declared at design
time, and nothing here transfers to them. It does not establish `DataCopyPad` as required over a
strided `DataCopy`, only that upstream specifies it. It says nothing about the MLA or split-KV-reduce
output paths, whose task structures differ. No board token appears in any quoted passage, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
