```
ID:        0138-scan-gates-and-segment-formulas-rest-on-vlc-and-vreg-which-are-never-defined-or-given-units
LABEL:     boundary
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scan/fallback/tiling-flow.md:85-86,109-111,
           57,145,296 — "R > 2*VLC → lane 并行顺序扫描" · "S = ceil(R / VLC)" ·
           "N 宽（alignN > VREG/4=16 元素 fp32）" · "guardC = 256 / cBytes  // 哨兵区 = 1 vreg" ·
           "窄 N 门控: alignN ≤ VREG/4" ; scan/fallback/script/scan_tiling.py:11 — "VL = 64  # 256B / 4B"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  finding VLC defined with a value anywhere in this skill, or a vector length query on a
           named 950 board returning a value inconsistent with the 64-element / 256-byte reading
           this entry records as the only consistent one.
```

# 0138 · Scan gates and segment formulas rest on VLC and VREG, which are never defined or given units

## 1 · Claim
Upstream asserts scan gates and segment-length formulas in terms of two symbols it never defines.
`VLC` appears in the algorithm-selection gate (`R > 2*VLC` picks lane-parallel scanning over
Kogge-Stone), in the segment-length formula (`S = ceil(R / VLC)`), in the buffer provisioning rule
(`数据区要按 VLC*S`), and in the justification for Kogge-Stone at small R (`那趟固定的 log2(VLC)`) —
with no value and no definition anywhere in the family. `VREG` appears in the un-indexed N-width
gate as `alignN > VREG/4=16 元素 fp32`, implying 64 in *elements*, and one vector register is
separately stated as 256 *bytes* (`guardC = 256 / cBytes // 哨兵区 = 1 vreg`). The family's
reference script defines a third name for what appears to be the same quantity: `VL = 64 # 256B /
4B`. Not established here; this entry records the absence and the one reading under which all four
statements are consistent.

## 2 · The wrong branch this removes
Every one of these symbols sits in a decision, not in a comment. `R > 2*VLC` chooses between two
algorithms; `S = ceil(R / VLC)` sets a UB address stride whose divisibility decides a 5.5× bank
conflict (0133); `alignN > VREG/4` chooses between one-way and two-way Sklansky. An agent that
substitutes a plausible number gets a plan whose algorithm choice, stride and template all rest on
a guess, and every resulting kernel is correct — so nothing objects.

The unit ambiguity in `VREG` is the specific trap. `VREG/4 = 16 元素 fp32` forces `VREG = 64`
counted in elements; `1 vreg = 256 bytes` is a byte statement. Both are true of the same register
at fp32, and they are consistent only if the reader supplies the fp32 assumption. A reader who met
`guardC = 256 / cBytes` first will read `VREG/4` as 64 *bytes*, i.e. 16 elements at fp32 —
numerically the same answer by coincidence — but 8 elements at fp16, where the elements reading
gives 16. So at fp16 the two readings of the same gate differ by 2×, and the gate is the
oneway/twoway boundary. The script's `n * 4 > 256 // 4` (0136) hardcodes fp32 and so cannot settle
it.

The correct handling is 0104's provenance rule plus 0141's query discipline: a vector length is a
chip specification field, so it must be queried and never guessed, and a plan that cannot query it
should say so rather than substitute.

## 3 · Ground / Source
`VLC`, all five appearances, `scan/fallback/tiling-flow.md`:

```
:85    R > 2*VLC → lane 并行顺序扫描（指令条数与 log2(R) 脱钩）
:86    否则      → 行内 Kogge-Stone（log2(R) 级，R 小时它那趟固定的 log2(VLC) 更划算）
:109   S = ceil(R / VLC)
:111   数据区要按 VLC*S（而非 R）备量，尾部补齐成幺元
:197   - `R <= 2 * guardC` → `gsS = 0`，走 Kogge-Stone（log2(R) 级，R 小时那趟固定的 log2(VLC) 更划算）
```

No definition, no value, no units, in this file or in `scan/fallback/index.md`,
`scan/fallback/tiling-fields.md`, `scan/index.md` or the script.

`VREG`, both appearances:

```
:57    ├─ N 宽（alignN > VREG/4=16 元素 fp32）
:296   窄 N 门控: alignN ≤ VREG/4；foldCount>1；fp16/bf16 foldCount≤4；foldLen≥256（向上取 2 的幂）
```

The byte statement, `:145`, inside the mode-5 pseudocode:

```
        cBytes = 4                          // 比较类型一律 4 字节（见 §3.2 ③）
        guardC = 256 / cBytes               // 哨兵区 = 1 vreg
```

and its instantiation, `:195`: `R > 2 * guardC`（guardC = 64 for fp32/int32）`.

The script's third name, `scan/fallback/script/scan_tiling.py:11`:

```python
VL = 64            # 256B / 4B
```

`VL` is also the alignment unit in the field table, `scan/fallback/tiling-fields.md:20`:
`向量宽 W = mBlk*nTileLen（目标 W_TARGET≈1024，按 VL=64 对齐）`, and in the alignment table,
`tiling-flow.md:319`: `| 向量宽 W / nTileLen | 按 `VL=64`（256B/4B）对齐 |`.

The single reading under which all of this is consistent, derived here rather than quoted: a vector
register is 256 bytes; `VL` and `VLC` are its length in elements of the relevant type — 64 at
4 bytes, 128 at 2 bytes; `VREG` is used as that same element count (64) at `:57`, so `VREG/4 = 16`
elements; and `guardC = 256/cBytes` is the same quantity computed from bytes. `VLC`'s trailing `C`
then means "of the comparison type", which matches its use beside `sizeof(C)` in the same formula
(0133) and beside `cBytes` in the parallel gate at `:195`. Under that reading `VLC = guardC`, and
upstream uses two names for one thing in two sections of one file. This is a reading, not a fact:
upstream never states it, and the entry records it as the hypothesis §4 would test.

The 256-byte vector register is on the list of quantities this project must establish from scratch —
a prior survey of this skill recorded that no upstream document supplies it, including the skill
that declares itself the hardware truth source. So `VLC` is undefined *and* the value it would take
under the consistent reading is itself unestablished.

Registered as C-950tiling-017 (VREG's two unit systems). `VLC`'s absence is recorded in
`harvest/standing/950-tiling.md` rather than as a contradiction row — nothing disagrees with it,
it simply is not there.

## 4 · Procedure
Two arms. The first needs no device and is permitted in this phase; it has not been run.

Arm 1 — read-only symbol search. `grep -Rn '\bVLC\b\|\bVREG\b\|GetVecLen\|VECTOR_REG' ` over
`upstream/skills-dev-main/` and, if a 950-era CANN toolkit is installed, over its include tree.
`-R` and not `-r`: these trees contain symlinked directories that `grep -r` will not follow, which
would produce a false absence. Read only; nothing compiled, nothing executed, no device contacted.
Record every hit with path, line and the value if any, plus the toolkit pin where applicable.

Arm 2 — runtime query and behavioural confirmation on a named 950 board (950PR or 950DT); never run
in this phase. Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at
20 s spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Query the vector length at runtime rather than assuming it — the `GetVecLen()/sizeof(dtype)` idiom
upstream's own technique library states as the rule (never a borrowed constant) — and print it with
the toolkit pin and board id for fp32, fp16 and bf16. Then confirm behaviourally: sweep `N` for an
un-indexed Cumsum across the predicted oneway/twoway boundary at fp32 (`N ∈ {8,12,16,20,32}`) and
at fp16 (`N ∈ {8,12,16,20,32}`), building both templates at every N where both are legal, and
record which the host selects. Under the elements reading the fp16 boundary sits at 16 elements;
under the bytes reading it sits at 8. One sweep separates them.

Refuses to assume: that a free die stays free; that a die may be substituted; that the queried
vector length equals `VLC` — the behavioural sweep is what connects the query to the gate; that the
fp32 result transfers to fp16, since the whole ambiguity is a dtype-dependent factor of two.

## 5 · Checker — acceptance declared before the run
Verdict variable `vlc_resolved ∈ {repo, toolkit, runtime, unresolved}` from arm 1 and the query.
Declared before the run: the OVERTURN fires if `vlc_resolved = repo` — a definition inside this
skills repo would mean §3's absence is a reading error of ours, and the entry is corrected in place.
Resolution from an installed toolkit or a runtime query is the expected outcome and adds a SOURCE
line with its pin, which is a different origin of authority.

Verdict variable `boundary_elements` from the behavioural sweep: the `alignN` at which the host
switches from oneway to twoway, per dtype. Declared acceptance for the elements reading: 16 at fp32
and 16 at fp16. For the bytes reading: 16 at fp32 and 8 at fp16. Any other pair supports neither and
is reported as measured.

The exit code is not the verdict: `grep` exits 1 on no match, which is the finding `unresolved`, not
a failure. The blind mode this checker must avoid is a sweep whose two arms are never both legal —
if only one template builds at every swept N, no switch point is observable and a "boundary at 16"
would be read off the host's refusals rather than off a comparison. The checker therefore requires
two distinct md5s and two distinct echoed template names at three or more consecutive N values per
dtype, and goes red otherwise rather than reporting a boundary.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Arm 1 needs no device and
has not been run either, so no grep output is recorded anywhere in this entry.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, and no symbol search was performed. The entry does not establish a value for
`VLC`, `VREG` or the vector register width — the 256-byte / 64-element reading in §3 is the only
reading consistent with all four statements, and it is a reading, not a measurement. It does not
establish that `VLC` and `guardC` are the same quantity. It does not establish the `foldCount ≤ 4`
and `foldLen ≥ 256` twoway gates that sit beside the `VREG/4` condition, which are separate
literals. It does not resolve `sizeof(C)`'s default, which 0133's bank rule also depends on. No
chip is named anywhere in the scan family, so BOARD is `family-claimed(unverified)`; §4 arm 2 names
950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.
