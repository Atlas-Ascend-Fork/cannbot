```
ID:        0421-one-conversion-family-spells-its-architecture-four-ways-and-a-fifth-spelling-names-a-chip-that-exists-nowhere
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/conversion/transpose_vconv_021.md:81 —
           "- 总字节量 `totalVolumeActual * eleLenInBytes >= 70000`（`SMALL_SHAPE_BYTES_THRES_HOLD_DAV_5102_021`)，" ;
           transpose_small_shape.md:53 — "> 注:`transpose_tiling.cpp:52` 另有一个
           `SMALL_SHAPE_BYTES_THRES_HOLD_DAV_5102_021 = 70000`,"
SOURCE:    same shelf, SKILL.md:41 — "| Conversion 数据转换类 | Transpose, Concat, Split | DAV_3510 |" ;
           conversion/guide.md:3 — "(AscendC / arch35 / dav-3510)" ; conversion/guide.md:67 —
           "仅 `__NPU_ARCH__==3510` 可用" ; conversion/templates/dav3510/ (directory name) ;
           conversion/transpose_n_last.md:258 — "在 ascend950 上"
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read (no device):
           grep -rn 'DAV_5102' upstream/skills-dev-main/ops/ascendc-performance-best-practices/
           ls -d upstream/skills-dev-main/ops/ascendc-performance-best-practices/reference/*/templates/dav*
OVERTURN:  a statement anywhere in upstream's repository, or in the installed CANN toolchain, defining
           `DAV_5102` as an architecture, a SoC, or an abbreviation of `DAV_3510` — the constant's name
           would then be a declared token rather than an undefined one, and this entry's fifth spelling
           would collapse into the other four.
```

# 0421 · One conversion family spells its architecture four ways, and a fifth spelling names a chip that exists nowhere

## 1 · Claim
Upstream asserts, across one operator family's twelve documents and its directory layout, four
different spellings for one architecture: `DAV_3510` in the shelf's front-page family table,
`dav-3510` and `arch35` in the family guide's own scope line, the numeric `3510` as the value of
`__NPU_ARCH__` in every compile gate, and the directory component `dav3510` in every template path.
Upstream additionally names a board in the family's only two measured tables — `ascend950` — which is
not any of the four and is not a board token this project recognises. And upstream names a fifth
token in a constant that gates a real routing decision: `SMALL_SHAPE_BYTES_THRES_HOLD_DAV_5102_021`,
carrying the value 70000, cited in two files. `DAV_5102` appears nowhere else in the shelf, is defined
nowhere, and is not `DAV_3510` with its digits in any recognisable order. Not established here.

## 2 · The wrong branch this removes
This book has already measured that names are a routing channel — filenames get read, directory
components get matched, and an agent that sees `dav3510` in one family and `dav310` in four others
concludes the two target different parts. `0346` records that exact hazard for the sibling families and
its overturn condition is a definition of `dav310` that upstream never supplies. This entry is the
other half of the same problem in the same shelf: the family that uses the *unambiguous* spelling in
its paths uses four other spellings in its prose, so a consumer normalising on any one of them will
fail to match the others.

The consequential one is `DAV_5102`. It sits in a constant name whose value, 70000 bytes, is one of the
four gates admitting the 021 VCONV strategy, and a reader trying to establish whether that gate applies
to their part has a token to look up and nothing to look it up in. Two readings are available and the
documents do not distinguish them: a transposition of `3510`'s digits carried through into a shipped
identifier, or a genuine other architecture whose threshold was reused here. Under the first the gate is
this architecture's; under the second it is another part's constant applied to this one, which is the
species `0316` records for bank-conflict recipes and `0329` for a dual-arch marking that fences itself
to the other family in its first paragraph. Registered as `C-950td-026`.

## 3 · Ground / Source
The five spellings, each at its site.

Front-page family table, `ascendc-performance-best-practices/SKILL.md:41`:

```
| Conversion 数据转换类 | Transpose, Concat, Split | DAV_3510 | ✅ [Transpose融合设计](reference/conversion/transpose_fusion_design.md) · ✅ [性能优化指南](reference/conversion/guide.md) |
```

Family guide's scope line, `conversion/guide.md:3`, carrying two more in one parenthesis:

```
本目录为 Transpose 算子(AscendC / arch35 / dav-3510)提供**按 tiling 策略组织的调优参考**
```

Compile gate, `conversion/guide.md:67`:

```
GATHER 策略受编译宏 `TRANSPOSE_ENABLE_GATHER`(默认 0)保护,需 Reg 寄存器模型,仅 `__NPU_ARCH__==3510` 可用。关闭时 host 不产出该策略,相应 shape 由 NDDMA 家族覆盖。
```

Directory component, from the tree itself — `conversion/templates/dav3510/`, ten `.template` files.
Kernel source paths inside the documents use yet another form, `arch35/` (e.g.
`transpose_n_last.md:5`, `arch35/transpose_n_last.h`), so the *document* and the *template directory*
disagree about the same code's location.

Board name, `conversion/transpose_n_last.md:258` and `transpose_small_shape.md:286`:

```
以 batch_to_space 算子（perm=[2,3,0,4,1,5]，6D）为例，在 ascend950 上：
```

`ascend950` is a family, not one of this project's board tokens (`950PR`, `950DT`), and it is the only
place in the family where a *part* rather than an *architecture* is named. It appears exactly twice,
attached to the family's only two measured tables (`0419`, `0420`).

The fifth token, `conversion/transpose_vconv_021.md:81`:

```
- 总字节量 `totalVolumeActual * eleLenInBytes >= 70000`（`SMALL_SHAPE_BYTES_THRES_HOLD_DAV_5102_021`），
```

and the note that flags it as a distinct constant, `conversion/transpose_small_shape.md:53`:

```
> 注:`transpose_tiling.cpp:52` 另有一个 `SMALL_SHAPE_BYTES_THRES_HOLD_DAV_5102_021 = 70000`,
```

`grep -rn DAV_5102` over the whole shelf returns exactly those two lines. The token is never expanded,
never mapped, and never compared to `DAV_3510`. This book's chip-identifier entries give the shape of
what a real mapping looks like — `0201` (three identifiers that must not be substituted for one
another), `0202` (`archXX` is the first two digits of a DAV number and names a directory, not a
capability), `0203` (`__DAV_C310__` is a build macro and must not be read as a numeric architecture
value) — and `DAV_5102` fits none of those patterns. Under `0202`'s rule its first two digits would
name `arch51`, which no upstream document mentions.

The directory split across the shelf, re-derived at drafting time:

```
dav3510/ : conversion, sort
dav310/  : conv, gather, reduce, scan
```

`0346` already carries the `dav310` half of this and its overturn condition; what this entry adds is
that the *other* half is not uniformly better — `conversion` uses the unambiguous directory name and
four other spellings in its text, so an agent normalising on the directory name still cannot match
`SKILL.md`'s `DAV_3510` or the guide's `arch35`. Nothing in the family states that the five refer to
one thing, and nothing states that `ascend950` is a part of the architecture the other four name.

One further naming defect in the same family, recorded because it has the same consequence and a
cheaper fix: `conversion/transpose_tiling_data.md` links its nine strategies to
`kernel/arch35/*.h` and `templates/transpose_<strategy>.md`. Neither path exists — the directory holds
no `kernel/`, and the strategy documents sit at `conversion/*.md` with the templates at
`templates/dav3510/*.template`. That file appears to have been written against a different layout than
the one it ships in. Registered as `C-950td-027`.

## 4 · Procedure
Proposed, and most of it needs **no device**: this is a naming question, answerable by reading the
installed toolchain and upstream's own tree. Only the last arm needs a board.

**Arm 1 — device-free. Does `DAV_5102` exist anywhere?** `grep -Rn 'DAV_5102\|5102'` over (a) the whole
upstream repository, not just this shelf, and (b) the installed CANN toolchain at
`/usr/local/Ascend/cann-9.0.0-beta.2/`, including `platform_config/*.ini` where architecture
identifiers are declared and where `0204`/`0205` record how this project reads them. Report every hit
with its file and line, or report the absence. An `.ini` naming `5102` would settle the second reading
of §2 immediately.

**Arm 2 — device-free. Does the 70000 gate differ from the 4000000 one in kind?**
`transpose_small_shape.md:47` gives `SMALL_SHAPE_BYTES_THRES_HOLD = 4000000` for the general small-shape
route and `:53` flags the `DAV_5102` constant as a *different* threshold used by the 021 path. Evaluate
both gates over a shape sweep and report the region where they disagree — the set of shapes admitted by
one and refused by the other is the practical footprint of the unresolved token, and it may be empty.

**Arm 3 — device-free. Which spelling does the toolchain actually accept?** Compile a trivial kernel
with `--npu-arch=dav-3510` (the form `scan/templates/usage_guide.md:217` gives) and with each other
spelling in turn, and record which the compiler accepts. This is what tells a consumer which of the
five is a *build* token and which are prose.

**Arm 4 — on-card, and only if arm 1 finds `5102` defined as a different architecture.** Run the 021
VCONV strategy at a shape just above and just below 70000 bytes on a named 950 board and record whether
the gate's position is defensible there — i.e. whether the strategy is actually faster above it.
Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; re-sample after; discard if the die moved. Variance floor from 30
in-process and 5 fresh-process runs.

Refuses to assume: that `DAV_5102` is a typo (arm 1 is what tests it, and treating it as one before
looking is the error this entry exists to prevent); that the installed toolkit at run time is the pin
read at drafting time (`readlink -f` re-derives it); that `ascend950` denotes 950PR or 950DT; that the
five spellings denote one architecture; that a free die stays free; that a die may be substituted.

## 5 · Checker — acceptance declared before the run
Verdict `dav5102_defined` from arm 1 ∈ {`absent`, `defined_as_alias`, `defined_as_other_arch`}.
Declared before the run: this entry is **supported** iff `dav5102_defined == absent` across both the
upstream repository and the installed toolchain — the token gates a real routing decision and is
defined nowhere. The OVERTURN fires on either non-absent value, and the two have opposite consequences:
`defined_as_alias` reduces the finding to a style note, while `defined_as_other_arch` **escalates** it
to a foreign constant applied to this architecture, which is a stronger claim than this entry makes and
would require rewriting §1 rather than retiring it.

Verdict `gate_disagreement_region` from arm 2 = the set of shapes admitted by one threshold and refused
by the other, reported as a region rather than a count. An empty region means the token's practical
footprint is nil and the finding is documentation-only.

Verdict `accepted_spelling` from arm 3 = the subset of the five that the compiler accepts as a build
flag.

The exit code is not the verdict, and for arms 1–3 there is barely a process to exit: these are greps
and compiles, and their failure mode is looking in too few places. Three guards. First, **the input
that makes this checker go red**: arm 1's grep set includes `DAV_3510`, which **must** be found in both
the upstream repository and the installed toolchain. If the search returns nothing for a token known to
exist, the search is scoped wrongly — wrong root, wrong follow-symlink flag — and the `absent` verdict
for `DAV_5102` is worthless. This project has that failure on record: `grep -r` does not follow
symlinked directories in these trees and `grep -R` does, and the toolchain's `lib`, `impl` and
`interface` are all symlinks. Every search in this entry uses `-R` and reports the root it ran from.
Second, arm 3 reports the compiler's own diagnostic text for each rejected spelling, not just the exit
status — a flag rejected for being unknown and a flag rejected for a downstream reason are different
answers. Third, no verdict is reported without the toolkit pin from `readlink -f`; a naming question
answered against an unnamed toolkit version is not answered.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The five spellings, the two
`DAV_5102` occurrences, the directory split and the broken link targets in `transpose_tiling_data.md`
are file reads and greps of upstream's own tree performed at drafting time, re-derivable by the two
commands in INDEX. No compilation was attempted and no architecture identifier was resolved against the
installed toolchain.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that `DAV_5102` is undefined *anywhere*
— it establishes that it appears twice in this shelf and nowhere else in it, and §4 arm 1 is what
extends the search to the repository and the toolchain. It does not establish that the five spellings
denote one architecture, nor that they denote more than one; it records that upstream never says. It
does not establish that `ascend950` is 950PR or 950DT, and this book does not treat it as a board token
(CONVENTIONS lists the accepted spellings). It does not establish the 70000 or 4000000 thresholds, or
that the 021 gate is correctly placed — arm 4 is conditional and unrun. It does not resolve `0346`'s
`dav310` question, which has its own overturn condition and is a different family's problem; this entry
only observes that the `dav3510` half is not uniformly cleaner. It does not establish that
`transpose_tiling_data.md`'s broken links (`C-950td-027`) cost anything. It supplies no mapping table
of its own and deliberately does not guess one — `0201` records that these identifiers must not be
substituted for one another, and inventing an expansion for `DAV_5102` would be exactly that
substitution. BOARD is `family-claimed(unverified)`. Nothing here is established for any 910-family
board, and no fact about any non-950 architecture enters this book (RULES.md Art. 1).
