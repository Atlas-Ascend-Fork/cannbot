```
ID:        0471-three-different-quantities-are-aligned-in-this-fusion-and-only-the-effective-length-may-reach-a-copy-or-a-compute-call
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/matmul/patterns.md:90-93 —
           "**ODD-N 对齐**：UB 侧 Fixpipe 的 row stride 必须对齐到 32B（即 8 个 float）。 /
           若 `curN` 非 8 倍数（如 N=1/4/15/33），须将 UB 视图的 N 向上对齐到 8 的倍数
           （`curNUbAlign`）， / Fixpipe 每行仅填充 `curN` 列，尾部对齐列保持未触碰， /
           Epilogue 通过 `DataCopyPad` 按 `rowBytes = curN × sizeof(float)` 仅写出有效列。" ·
           :171 — "| K 对齐 | mxfp8 场景 | Host 侧 padding K 到 64 倍数（mxfp8 Cube 硬件要求） |"
SOURCE:    same family, matmul-fusion-design-template.md:123-127 —
           "**参数使用规则**： / | 参数位置 | 用有效长度 | 用对齐长度 | /
           | DataCopyPad blockLen / 计算 API count | ✓ | ✗ | /
           | UB 数据偏移 / Buffer 大小 | ✗ | ✓ |" ; :389 — "| S4 | `ALIGN_ELEM = 32/sizeof(float)` |
           dtype 改变后对齐错误 | 改为 `sizeof(DataType)` |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an mxfp8 + eltwise fusion on a named 950 board with the UB view's N left at `curN` for a
           non-multiple-of-8 `curN`, whose output matches an FP64 reference across the sweep — the
           32-byte row-stride requirement would then not bind, and the `curNUbAlign` rounding would be
           unnecessary. Equally: a `DataCopyPad` given `rowBytes = curNUbAlign × sizeof(float)` whose
           output is nevertheless correct would show the tail alignment columns are not garbage, which
           upstream's "保持未触碰" says they are.
```

# 0471 · Three different quantities are aligned in this fusion, and only the effective length may reach a copy or a compute call

## 1 · Claim
Upstream asserts three separate alignment obligations in the mxfp8 matmul + eltwise fusion pattern, on
three different axes and at three different stages. On N: the UB-side Fixpipe row stride must be
32-byte aligned, i.e. 8 floats, so when `curN` is not a multiple of 8 the UB view's N is rounded up to
`curNUbAlign`; Fixpipe fills only `curN` columns of each row and leaves the tail alignment columns
untouched; and the epilogue writes out only the valid columns via `DataCopyPad` with
`rowBytes = curN × sizeof(float)`. On K: the host pads K to a multiple of 64, stated as an mxfp8 Cube
hardware requirement. And across every API call, upstream asserts a two-row rule: `DataCopyPad`'s
`blockLen` and a compute API's `count` take the **effective** length, while UB data offsets and buffer
sizes take the **aligned** length. Upstream asserts that the alignment element count itself is
dtype-dependent, flagging `ALIGN_ELEM = 32/sizeof(float)` as a sample value to be rewritten as
`sizeof(DataType)` when the dtype changes. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent picks one number per dimension and uses it everywhere. That instinct is
correct for a contiguous, aligned tile and it is what makes the fusion's tail cases fail: this pattern
has, for one tile, a computed extent (`curN`), a UB view extent (`curNUbAlign`), and a GM row stride
(`N`), and each of the three appears in a different call. Using the aligned extent as a copy length
writes the untouched tail columns — which upstream says Fixpipe never filled — into GM. Using the
effective extent as a buffer offset makes every row after the first start one alignment gap early, so
the tile is sheared.

The normal checks do not catch it because both errors are invisible at aligned shapes. `curN = 32` has
`curNUbAlign = 32` and the two numbers are the same. Upstream names the shapes that separate them —
`N=1/4/15/33` — and they are the shapes a benchmark does not contain.

The second wrong branch is treating the alignment constant as a constant. `ALIGN_ELEM = 32/sizeof(float)`
is 8 for float and 16 for half; the `[SAMPLE]` register (`0474`) flags exactly this line as a
dtype-migration hazard. An agent that changes the epilogue's dtype and leaves `ALIGN_ELEM` at 8 aligns
a half-typed buffer to 16 bytes rather than 32, and the row stride requirement is a *byte* requirement.

The third wrong branch is K. `Host 侧 padding K 到 64 倍数` is a host obligation for a *hardware*
requirement, so nothing in the kernel checks it: an unpadded K reaches the Cube, and upstream does not
say what happens then.

## 3 · Ground / Source
The N obligation, `references/matmul/patterns.md:90-93`:

```
**ODD-N 对齐**：UB 侧 Fixpipe 的 row stride 必须对齐到 32B（即 8 个 float）。
若 `curN` 非 8 倍数（如 N=1/4/15/33），须将 UB 视图的 N 向上对齐到 8 的倍数（`curNUbAlign`），
Fixpipe 每行仅填充 `curN` 列，尾部对齐列保持未触碰，
Epilogue 通过 `DataCopyPad` 按 `rowBytes = curN × sizeof(float)` 仅写出有效列。
```

`保持未触碰` — kept untouched — is the load-bearing phrase and the one that makes this a trap rather
than a bookkeeping note. The tail columns are not zero-filled and not defined; they hold whatever the
buffer held. So a copy that includes them does not merely write redundant data, it writes the previous
tile's residue into the caller's output. Upstream states this once and never repeats it.

The parenthetical `（即 8 个 float）` fixes the element count at the float dtype, and the UB layout
diagram at `:79` computes it as `curNUbAlign = AlignUp(curN, 8)` — with a literal 8, in a family whose
own `[SAMPLE]` register says the 8 is dtype-derived. So the diagram and the register disagree about
whether 8 is a constant. Recorded as `C-950fin-015`.

The K obligation, `:171`, in the branch-coverage table:

```
| K 对齐 | mxfp8 场景 | Host 侧 padding K 到 64 倍数（mxfp8 Cube 硬件要求） |
```

restated at `matmul-fusion-design-template.md:269` as `Host 侧 padding（mxfp 场景 K 到 64 倍数）` —
note `mxfp` there against `mxfp8` here, so the template states it for the format family and the
patterns file for one member. 64 is a bare literal with no derivation; against `0455`'s MX block
quantisation group of 32 elements along the reduction axis, 64 is two blocks, which is suggestive and
is not stated anywhere. Recorded as `Q-950fin-21`.

The cross-cutting parameter rule, `matmul-fusion-design-template.md:123-127`:

```
**参数使用规则**：
| 参数位置 | 用有效长度 | 用对齐长度 |
|---------|-----------|-----------|
| DataCopyPad blockLen / 计算 API count | ✓ | ✗ |
| UB 数据偏移 / Buffer 大小 | ✗ | ✓ |
```

Two rows, four cells, and it is the most compressed statement of the whole entry: what a call *does*
takes the effective length, what a call *addresses* takes the aligned length. This is the rule that
generalises the N obligation, and the family states it in the template rather than in the tiling
document, so an agent reading only `patterns.md` gets the instance and not the rule.

The dtype dependence, `:389`:

```
| S4 | `ALIGN_ELEM = 32/sizeof(float)` | dtype 改变后对齐错误 | 改为 `sizeof(DataType)` |
```

and `:211`, where `ALIGN_ELEM` is used: `l1NAlign = CeilDiv(baseN, ALIGN_ELEM) × ALIGN_ELEM // N 对齐
到 32B`. So the same alignment appears as `AlignUp(curN, 8)` in one file and as
`CeilDiv(baseN, ALIGN_ELEM) × ALIGN_ELEM` in the other, over two different quantities (`curN` versus
`baseN` — a per-tile extent and a tiling base block). Whether they must agree, upstream does not say.

Two files, one repository: one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. mxfp8 is
stated Ascend950-only (`matmul-fusion-design-template.md:30`), so there is no 910 counterpart.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

**Arm 1 — the four cells of the parameter rule.** One mxfp8 + Div fusion with two switches: the copy
length (`curN` or `curNUbAlign`) and the UB row offset (`curN` or `curNUbAlign`). Four builds, run at
`curN ∈ {1, 4, 8, 15, 32, 33}`. Before each run, fill the whole UB output region with a sentinel and
the whole GM output with a second sentinel. Report per cell: elementwise agreement, and whether any
sentinel byte from the UB fill reached GM. The claim is that only one of the four cells is correct at
non-multiples of 8 and that all four agree at multiples of 8.

**Arm 2 — the untouched tail.** With the correct build, read back the UB tile after Fixpipe and report
the contents of columns `curN` to `curNUbAlign - 1`. Upstream says untouched; this arm says what
"untouched" contains — the previous tile's residue, the initial sentinel, or zeros. That distinction
decides whether the over-long copy in arm 1 is a correctness bug or merely wasteful, and upstream never
says which.

**Arm 3 — the K padding.** Run the fusion with K a multiple of 64 and with K padded only to 32 and to
16. Record fault, wrong values or correct output at each. `mxfp8 Cube 硬件要求` predicts a hardware
refusal at unpadded K; a correct result would mean the padding is a software convention.

**Arm 4 — the dtype-dependent alignment, retained because it may not bite.** Build the epilogue with
`DataType = half` and `ALIGN_ELEM` left at `32/sizeof(float)` (8), then corrected to
`32/sizeof(DataType)` (16). If both are correct, `C-950fin-015` is a documentation inconsistency with
no consequence at this dtype; if only the corrected one is, the `[SAMPLE]` register's S4 row is a real
defect trap and `0474`'s subject is confirmed by instance.

Refuses to assume: that a free die stays free, or that a die may be substituted; that `curNUbAlign` is
what the host computed (echoed from the device alongside `ALIGN_ELEM` and `rowBytes`); that a correct
output means no residue reached GM (arm 1's second sentinel exists for that); that the tail columns
are zero (arm 2 reads them); that the mxfp8 path accepts unpadded K without saying so (arm 3 tries);
that one `curN` characterises the sweep — `curN = 1` and `curN = 33` are both in it because they
stress opposite ends of the same rounding.

## 5 · Checker — acceptance declared before the run
Verdict `cell_outcome(copy_len, offset)` from arm 1, one of {`correct`, `residue_leaked`, `sheared`,
`fault`}, declared before the run for all four cells at each `curN`. Acceptance:
(`curN`, `curNUbAlign`) is the only `correct` cell at non-multiples of 8, and all four are `correct`
at multiples of 8. The OVERTURN's first half fires iff (`curN`, `curN`) is `correct` at every swept
`curN`.

Verdict `tail_contents` from arm 2 ∈ {`residue`, `sentinel`, `zeros`}. The OVERTURN's second half
fires iff `zeros` — the tail would then be harmless and the over-long copy would not be a correctness
defect.

Verdict `k_pad_required` from arm 3 ∈ {`64`, `32`, `16`, `none`}: the coarsest padding that still
produces a correct result.

Verdict `align_elem_matters(dtype)` from arm 4, boolean.

The exit code is not the verdict: the sheared cell produces plausible numbers and the residue cell
produces a correct-looking tile with wrong tail columns, and both exit 0. Guards: (1) the checker
compares the **entire** GM output including the columns beyond `curN` of each row against the second
sentinel, and fails red if that region was excluded — a comparison scoped to the valid columns cannot
see a residue leak; (2) **the input that makes this checker go red**: `curN = 8`, where
`curNUbAlign == curN` and all four cells must be byte-identical — if they differ there, the switches
change more than they claim and the whole table is an artifact; (3) no cell is reported without its
`curN`, echoed `curNUbAlign`, echoed `ALIGN_ELEM`, echoed `rowBytes`, K, atol and CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The N obligation with its four
clauses, the K padding row in both files, the two-row parameter rule and the S4 sample row are file
reads performed at drafting time. The observations that the same alignment is written as a literal 8
in one place and as a dtype-derived `ALIGN_ELEM` in another, that the two spellings apply to two
different quantities (`curN` and `baseN`), and that 64 is two of the 32-element MX blocks `0455`
records, are readings and arithmetic over upstream's own lines, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish the 32-byte row-stride requirement —
upstream asserts it with no header, no ISA reference and no board. It does not establish what the
untouched tail columns contain, which upstream never says and which decides how severe the over-long
copy is. It does not establish that K must be a multiple of 64, nor why 64 (`Q-950fin-21`). It does not
resolve whether `AlignUp(curN, 8)` and `CeilDiv(baseN, ALIGN_ELEM) × ALIGN_ELEM` must agree
(`C-950fin-015`), nor whether the two apply to the same tile. It does not establish the parameter rule
as complete — two rows cover four call sites and the family has more. It covers the mxfp8 + eltwise
fusion pattern only (`0469`); nothing here transfers to general matmul or to any other family's
alignment rules. It says nothing about the M dimension, which has a separate and differently-motivated
rounding (`0470`). No board token appears in any quoted passage, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
