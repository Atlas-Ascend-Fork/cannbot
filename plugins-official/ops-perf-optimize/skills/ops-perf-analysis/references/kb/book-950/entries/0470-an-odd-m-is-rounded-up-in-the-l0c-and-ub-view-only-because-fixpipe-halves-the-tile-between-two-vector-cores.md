```
ID:        0470-an-odd-m-is-rounded-up-in-the-l0c-and-ub-view-only-because-fixpipe-halves-the-tile-between-two-vector-cores
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/matmul/patterns.md:86-88 —
           "**ODD-M 处理**：当 M 为奇数时，Fixpipe DUAL_DST_SPLIT_M 要求 M 为偶数才能等分给双 AIV。 /
           须将 L0C/UB 视图的 M 向上取偶（`curMPad`），MMAD 仍用原始 `curM`。 /
           Epilogue 的 SubBlockIdx 偏移逻辑仅访问有效行，padding 行不会被写出到 GM。"
SOURCE:    same file:95-99 — "**SPLIT_M 偏移**：Epilogue 计算 GM 偏移时须追加： /
           ```cpp / offset += AscendC::GetSubBlockIdx() * halfM * N; / ``` / 其中
           `halfM = CeilDiv(curM, 2)`。" ; :77-78 — "布局为 ND [curMPad, curNUbAlign]，其中： /
           curMPad  = (curM + 1) & ~1        ODD-M 向上取偶"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an mxfp8 + eltwise fusion on a named 950 board with an odd `curM` whose L0C/UB view is
           sized `curM` rather than `curMPad`, and whose output nevertheless matches an FP64
           reference across the shape sweep — `DUAL_DST_SPLIT_M` would then not require an even M,
           and the rounding would be unnecessary. Equally: a build where `MMAD` is given `curMPad`
           instead of `curM` and the padding row's garbage reaches GM is the second failure this
           entry predicts, and it is a different defect from the first.
```

# 0470 · An odd M is rounded up in the L0C and UB view only, because Fixpipe halves the tile between two vector cores

## 1 · Claim
Upstream asserts that in the mxfp8 matmul + eltwise fusion pattern, the L0C-to-UB path is a fixed
`Fixpipe` with the `DUAL_DST_SPLIT_M` trait, which splits the tile's M dimension equally between two
vector cores and therefore requires M to be even. Upstream asserts the consequence: when `curM` is
odd, the **view** of the tile in L0C and UB is rounded up to the next even value,
`curMPad = (curM + 1) & ~1`, while `MMAD` continues to be issued with the original `curM`. Upstream
asserts that the epilogue's `SubBlockIdx` offset logic touches only valid rows, so the padding row is
never written out to GM. Upstream asserts the offset each vector core must add:
`offset += AscendC::GetSubBlockIdx() * halfM * N` with `halfM = CeilDiv(curM, 2)`. Not established
here.

## 2 · The wrong branch this removes
Without this entry an agent handling an odd M does the thing that is right everywhere else: pad the
computation. Round `M` up, compute the extra row, discard it on write-back. That is how tail blocks
are handled across this entire corpus, and it is wrong here in a specific way — the padding is a
property of the **view**, not of the computation. `MMAD` is issued with `curM`, so the extra row is
never computed; only the descriptor that Fixpipe and the epilogue read is even. An agent that pads the
`MMAD` instead computes a row of the product that does not exist, from L0A/L0B contents that were never
initialised for it.

The normal checks do not catch either error reliably. Under-sizing the view (leaving it `curM`) puts
`DUAL_DST_SPLIT_M` in an unsupported configuration whose behaviour upstream does not state — it may
fault, or it may split unevenly and give the second vector core one row too few. Over-sizing the `MMAD`
produces a garbage row that upstream says the epilogue does not write out, so the output is correct and
the defect is silent until some other change makes the epilogue's row bound wrong. Both are invisible
at even `M`, which is what a benchmark uses.

The second wrong branch is in the offset. `halfM = CeilDiv(curM, 2)` is computed from `curM`, the
**odd** value, not from `curMPad`. At `curM = 15`, `halfM = 8`: sub-block 0 handles rows 0–7 and
sub-block 1 starts at row 8 and has 7 real rows. An agent that derives the offset from `curMPad` (16)
gets `halfM = 8` as well and is right by accident; an agent that derives it from `curM / 2` (7) puts
sub-block 1 at row 7 and overlaps a row. So the correct formula, the accidental one and the wrong one
are all within one character of each other, and only one shape distinguishes them.

## 3 · Ground / Source
The rule, `references/matmul/patterns.md:86-88`:

```
**ODD-M 处理**：当 M 为奇数时，Fixpipe DUAL_DST_SPLIT_M 要求 M 为偶数才能等分给双 AIV。
须将 L0C/UB 视图的 M 向上取偶（`curMPad`），MMAD 仍用原始 `curM`。
Epilogue 的 SubBlockIdx 偏移逻辑仅访问有效行，padding 行不会被写出到 GM。
```

The three sentences are three separate obligations on three different components — the view, the
`MMAD`, and the epilogue — and they are stated as one paragraph. That is the entry's reason: a reader
who takes the paragraph as "handle odd M by padding" has one obligation and needs three.

The rounding expression, `:77-78`, inside the UB layout diagram:

```
布局为 ND [curMPad, curNUbAlign]，其中：
  curMPad  = (curM + 1) & ~1        ODD-M 向上取偶
```

`(curM + 1) & ~1` is round-up-to-even by bit masking, correct for non-negative integers and identical
in effect to `CeilDiv(curM, 2) * 2`. It is written as a bit operation in a document that otherwise
writes `CeilDiv` and `AlignUp`, which is a small inconsistency worth noting only because the same
document computes the *related* quantity `halfM` with `CeilDiv` twenty lines later. Two spellings of
one idea in one file.

The offset, `:95-99`:

```
**SPLIT_M 偏移**：Epilogue 计算 GM 偏移时须追加：
offset += AscendC::GetSubBlockIdx() * halfM * N;
其中 `halfM = CeilDiv(curM, 2)`。
```

Note `* N`, not `* curN`: the stride between GM rows is the **full** output width, not the tile's
width, which is correct for a row-major output and is the one place this family writes the global
shape into an offset. Note also that `halfM` uses `curM`, as §2 discusses.

What upstream does not state: whether `DUAL_DST_SPLIT_M` faults on an odd view or silently
mis-splits, what the padding row of the UB buffer contains, whether the second sub-block's row count
is `curM - halfM` (7 at `curM = 15`) or `halfM` with a bound check, and whether `taskRation`
(`GetTaskRation()`, stated `=2` at `template:212`) can ever be other than 2 — the whole `SPLIT_M`
arrangement assumes exactly two vector cores per cube core. This book's architecture entry `0216`
records that DAV_3510 pairs one cube core with exactly two vector cores, which is consistent, and that
entry is from a different shelf. Recorded as `Q-950fin-20`.

Two locations in one file; with the design template's restatements, two files in one repository — one
origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The pattern is
mxfp8, which `matmul-fusion-design-template.md:30` states is Ascend950-only hardware support, so this
procedure has no 910 counterpart and none is proposed.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

**Arm 1 — the three obligations, separated.** One mxfp8 + Div fusion with three independent switches:
view sized `curM` or `curMPad`; `MMAD` issued with `curM` or `curMPad`; epilogue row bound `curM` or
`curMPad`. Run all eight combinations at `curM ∈ {15, 16, 17, 31, 32}`. Report per combination: fault
or not, elementwise agreement, and the contents of GM row `curM` (which must be untouched). The
correct combination is one of the eight; the entry's claim is that the other seven are distinguishable.

**Arm 2 — the offset formula.** The correct build with `halfM` computed three ways —
`CeilDiv(curM, 2)`, `curM / 2`, `curMPad / 2` — at odd `curM`. Report which GM rows each sub-block
wrote, by writing the sub-block index into a scratch tensor rather than by inferring it from the
output. Prediction: the first and third agree, the second overlaps one row. This is the arm that
separates "right" from "right by accident".

**Arm 3 — the unsupported view.** With the view left at odd `curM`, record what `DUAL_DST_SPLIT_M`
does: fault, uneven split, or correct. Upstream states the requirement and not the consequence, so this
arm's outcome is new information whichever way it falls.

**Arm 4 — `taskRation`, retained because it may not bite.** Echo `AscendC::GetTaskRation()` on this
board and confirm it is 2, and check whether the `matmulArea` formula (`0472`) and the offset formula
both degrade correctly if it were 3. If the value is fixed at 2 on every 950 SKU, `Q-950fin-20` is
closed and the parameter is a constant with a getter.

Refuses to assume: that a free die stays free, or that a die may be substituted; that `curMPad` and
`halfM` are what the host computed (both echoed from the device); that a correct output means the
padding row was untouched (arm 1 reads GM row `curM` explicitly); that `GetTaskRation()` returns 2
(arm 4 queries it); that a build that does not fault is a build that split evenly (arm 2 records which
sub-block wrote which row).

## 5 · Checker — acceptance declared before the run
Verdict `combination_outcome(view, mmad, bound)` from arm 1, one of {`correct`, `fault`,
`wrong_values`, `padding_leaked`}, declared before the run for all eight cells. Acceptance for the
entry: exactly the cell (`curMPad`, `curM`, `curM`) is `correct`. The OVERTURN's first half fires iff
the cell (`curM`, `curM`, `curM`) is also `correct` at every odd `curM` — the even-view requirement
would then not exist.

Verdict `subblock_rows(halfM_formula)` from arm 2: the row set each sub-block wrote, per formula.
Acceptance: `CeilDiv(curM, 2)` partitions the rows with no overlap and no gap.

Verdict `odd_view_behaviour` from arm 3 ∈ {`fault`, `uneven`, `correct`}.

The exit code is not the verdict: the over-sized-`MMAD` cell is expected to exit 0 with a *correct*
output, because upstream says the padding row is not written out — so the checker must look where the
output is not. Guards: (1) GM row `curM` is pre-filled with a sentinel before every run and compared
byte-exactly afterwards; a run that did not read it back is reported `untestable`, never `correct` —
a comparison scoped to the valid rows cannot see a padding leak, which is the blind-checker species
this book records repeatedly; (2) **the input that makes this checker go red**: every combination at
even `curM`, where all eight must be `correct` and identical — if they differ there, the switches
change more than they claim to and the odd-`curM` table is an artifact; (3) no cell is reported without
its `curM`, echoed `curMPad`, echoed `halfM`, echoed `GetTaskRation()`, atol and CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The three-sentence rule, the
`(curM + 1) & ~1` expression, the UB layout line, and the offset formula with its `CeilDiv(curM, 2)`
are file reads performed at drafting time. The observations that the paragraph carries three
obligations on three components, that `halfM` is derived from the odd value, and that
`CeilDiv(curM, 2)` and `curMPad / 2` agree while `curM / 2` does not, are readings and arithmetic over
upstream's own lines, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that `DUAL_DST_SPLIT_M` requires an even
M — upstream asserts it and cites no header, no ISA reference and no board. It does not establish what
an odd view does, which upstream never states. It does not establish that the padding row is never
written to GM, only that upstream says the epilogue's offset logic touches valid rows. It does not
establish that `GetTaskRation()` is 2 on any board (`Q-950fin-20`); the corroborating statement about
the cube/vector pairing (`0216`) comes from a different shelf and is a different claim about hardware
topology, not about this API's return value. It covers the mxfp8 + eltwise fusion pattern only
(`0469`) and nothing here transfers to general matmul, whose L0C-to-UB path is not this fixed Fixpipe.
It says nothing about the N dimension, which has its own alignment obligation (`0471`), nor about the
UB budget those two padded extents feed (`0472`). No board token appears in any quoted passage, so
BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing
here is established for any 910-family board.
