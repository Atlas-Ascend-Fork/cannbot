```
ID:        0346-four-dav-3510-families-keep-their-templates-in-a-directory-named-after-a-different-architecture
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled.
           The counts below are file reads of upstream's own tree.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/{conv,gather,reduce,scan}/templates/dav310/
           — four DAV_3510-marked families keep their device templates in a directory named
           `dav310`; e.g. conv/guide.md:42 — "| **Conv2D Cube** | groups=1，NCHW，必带 bias；runtime
           `Conv2DCase` | `__cube__` | [.template](templates/dav310/conv2d_kernel.template) | ... |"
SOURCE:    same shelf, reference/{conversion,sort}/templates/dav3510/ — two families of the same
           architecture use the unambiguous spelling; sort/templates/usage_guide.md:11 —
           "`dav3510/` 是 TopK 设备侧最佳版本快照，适用于 Ascend 950 / DAV_3510。"
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:16,19 — "| Atlas 推理系列 | ASCEND310P |
           DAV_2002 | 2002 | Ascend310P1, Ascend310P3, Ascend310P5, Ascend310P7 |" · "| Atlas
           200I/500 A2 推理 | ASCEND310B | DAV_3002 | 3002 | Ascend310B1~B4 |"
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           find <shelf>/reference -type d -name 'dav*' | sort
OVERTURN:  a statement anywhere in the upstream repository defining `dav310` as an abbreviation of
           `dav-3510` — the name would then be a declared shorthand rather than an undeclared
           collision, and the hazard would reduce to a style note.
```

# 0346 · Four DAV_3510 families keep their templates in a directory named after a different architecture

## 1 · Claim
Upstream asserts, in its operator-family index, that all six of the shelf's template-carrying
families — conv, gather, reduce, scan, conversion and sort — target `DAV_3510`, and upstream asserts
in two of their guides that the `dav3510/` directories hold Ascend 950 / DAV_3510 device snapshots.
Upstream's self-declared chip truth source asserts that `DAV_2002` is ASCEND310P and `DAV_3002` is
ASCEND310B — real inference architectures, neither of them a 950.

Against those assertions stands an absence and a mismatch, both readable today. Four of the six
families keep their device templates in a directory named `dav310`; the other two use `dav3510`. No
upstream document anywhere defines `dav310` or states it as an abbreviation. The name appears in 152
places across the shelf's markdown, including the shelf's own front-page family table and a
migration instruction that tells the consumer to preserve it. Not established here beyond the file
reads reported in §3 — nothing was compiled and no routing was observed.

## 2 · The wrong branch this removes
This book has a measured finding that filenames are a transmission channel: agents read `ls` output
and route on it (the harvest planason every entry here carries a
claim-shaped slug). A directory named for an architecture is exactly the kind of name that gets
routed on, and `dav310` is one digit from two real, different, non-950 architectures.

Three concrete branches follow.

An agent looking for 950 templates greps for `3510` or `dav3510` and finds conversion and sort. Four
of the six families are invisible to that search, and the natural conclusion — those families have
no device templates — is wrong. The conv family's entire kernel set lives under `dav310`.

An agent that *does* find `dav310` reads it as 310, concludes the templates target an inference
part, and declines to use them on a 950 — or, worse, tries to use them on a 310 part, where the
compiler will accept the source and the whole SIMT and Reg surface it depends on does not exist
(`950:0352`: the reg-compute interface is gated on four `__NPU_ARCH__` values, and neither 2002 nor
3002 is among them).

An agent extending the library creates a new family and has to choose a name. Two conventions are in
front of it, one of them ambiguous, and neither is documented. The defect reproduces.

The general form is the one worth carrying past this shelf: **a directory name that looks like a
scoping token but is defined nowhere is worse than no token**, because it is trusted. `0329` and
`0319` are the same species in the index-cell position; this is it in the filesystem.

## 3 · Ground / Source
The directory inventory, read from upstream's tree:

```
reference/conv/templates/dav310          reference/conversion/templates/dav3510
reference/gather/templates/dav310        reference/sort/templates/dav3510
reference/reduce/templates/dav310
reference/scan/templates/dav310
```

Four against two, all six families marked `DAV_3510` in `SKILL.md`'s 适用架构 column
(rows for Reduction, Scan, Gather, Conversion, Convolution and RadixSort — the last with the
qualification `0329` records). `grep -rn "dav310"` over the shelf's markdown returns 152 lines: the
name is not an internal artefact, it is written into guides, template tables and migration
instructions that a reader follows.

The two spellings appear in documents with the same purpose. `conv/guide.md:27-33` lays out its tree
with `dav310/` and lists six templates under it; `sort/templates/usage_guide.md:11` writes
`` `dav3510/` 是 TopK 设备侧最佳版本快照，适用于 Ascend 950 / DAV_3510 ``. The sort document states
its directory's meaning; no `dav310` document states its own.

What `310` denotes in upstream's own vocabulary, `npu-arch/references/npu-hardware-params.md:16,19`:

```
| Atlas 推理系列 | ASCEND310P | DAV_2002 | 2002 | Ascend310P1, Ascend310P3, Ascend310P5, Ascend310P7 |
| Atlas 200I/500 A2 推理 | ASCEND310B | DAV_3002 | 3002 | Ascend310B1~B4 |
```

So `310` is a product-line number (Ascend310P, Ascend310B) whose DAV numbers are 2002 and 3002 —
neither of which is `310` either. `DAV_310` is not a DAV number that exists in the table. The
collision is therefore not with a DAV value but with a *chip family name*, which is if anything
easier to misread: `dav310` parses naturally as "the DAV directory for 310".

The contents settle what these directories actually are. `reference/conv/templates/dav310/` holds
`conv2d_kernel.template` and `dwconv2d_kernel.template`, whose family guide describes an
`__mix__(1,2)` AIC+AIV kernel using `Reg::DataCopyGather` (`0349`) — a Reg/MicroAPI API that
`950:0352` records as gated on `__NPU_ARCH__ ∈ {3510, 5102, 3003, 3113}`. `reference/reduce/
templates/dav310/` holds `softmax_v2_*.template`, whose family sits under a `DAV_3510` index row.
The code is 950 code; only the directory says otherwise.

`grep -rn "dav310"` finds no definition, no expansion, and no note anywhere in the repository —
including in `docs/STANDARDS.md`, which governs skill structure. Recorded as `C-950bp-008`.

Two of the 152 references are worse than incidental, because they are in the shelf's front door and
in an instruction. `SKILL.md:35` routes the Reduction family's shared base class directly at
`reference/reduce/templates/dav310/softmax_v2_base.template` — so `dav310` appears in the top-level
operator-family table, the first thing an agent reads. And `SKILL.md:125` instructs the consumer to
carry the name outward:

```
1. 若为 `.template`，先按 `usage_guide.md` 转成 `.h`/`.cpp`；再将文件拷贝到项目的 `op_kernel/`
   目录（**保留 `dav310/` 等子目录结构**）
```

So the ambiguous name is not confined to this repository: the documented migration procedure plants
it in the consuming project's kernel tree, where a later reader has no shelf to check it against.
The `sort` family's conversion loop (`0330` §3) does the same for `dav3510`, structurally — it
preserves directory structure by design — so both conventions propagate, and a downstream project
following both guides ends up with two architecture directories for one architecture.

This is a documentation defect and needs no measurement to establish. What it *cannot* establish by
reading is whether any build system consumes the directory name: if a template-conversion script or
an include path keys off `dav310` versus `dav3510`, the two conventions are also a build hazard and
not only a reading one. `sort/templates/usage_guide.md:58-66` shows a conversion loop that walks
`$TEMPLATE` recursively and preserves structure, so at least there the name is carried into the
target project unchanged — which propagates the ambiguity into the consumer's tree.

Nothing here is measured.

## 4 · Procedure
No device is required and none is proposed; this is a reading claim and a device arm would be
ceremony. Two file-level arms and one build-level arm.

Arm 1 — `[no-card]`, **run** (§3): enumerate the architecture-named directories under the shelf's
`reference/`, count the markdown references to each spelling, and search the whole repository for
any definition of `dav310`. Result: four directories against two, 152 references, no definition.

Arm 2 — `[no-card]`, **not run**: extend the sweep to the whole `upstream/skills-dev-main` tree, not
just this shelf, and to any build scripts, CMake fragments or conversion tooling that mention either
spelling. The question Arm 1 cannot answer is whether anything *consumes* the name. Owed in
`harvest/standing/950-bp.md`.

Arm 3 — the only arm needing a compiler, and it is a small one: take one template from a `dav310`
directory and one from a `dav3510` directory, convert both per their families' usage guides, and
compile each with `--npu-arch` set to a 950 value and to a 310-family value. If the `dav310`
template fails on the 310 arch, the directory name is affirmatively misleading rather than merely
undefined — which is the difference between a style note and a trap. Expected to fail, on the
strength of `950:0352`'s gate, and expected is not established.

Refuses to assume: that a directory name has no consumers (Arm 2 exists because it may); that the
two spellings are the only ones (Arm 1's enumeration is by pattern `dav*`, not by the two known
names); that `docs/STANDARDS.md` governs directory naming at all — it was searched and says nothing,
which is itself the record.

## 5 · Checker — acceptance declared before the run
Verdict `dirs` = the enumerated architecture-named directories with their families. Verdict `refs` =
the reference count per spelling. Verdict `definition_found` = true iff any file in the repository
defines or expands `dav310`.

Declared before the sweep: the entry is **supported** iff `definition_found` is false while both
spellings appear in directories of families the index marks `DAV_3510`. The OVERTURN fires on
`definition_found == true`.

Verdict `consumers` from Arm 2 — the set of scripts or build files that read either name.
Verdict `arch_gate_fails` from Arm 3.

The checker must be able to go red, and the fixture is this: the definition search is run first for a
term that **is** defined in the repository — `DAV_3510` itself, which
`npu-hardware-params.md:20-21` maps to ASCEND950 — and it must be found. If the search cannot locate
a definition that exists, its negative result on `dav310` means nothing, and `definition_found` is
void. A "we searched and found nothing" verdict from an unvalidated search is the known blind
species in its cheapest form, and a positive control costs one command.

There is no exit code to be the verdict for Arms 1–2; the deliverable is the inventory.

## 6 · Evidence
NOT YET RUN as a build procedure — nothing was compiled, no template was converted, and no
`--npu-arch` was set. Nothing in this file is a measurement.

Arm 1 was performed as a file read under the phase-1 read-only exception. Its outputs are in §3: six
architecture-named template directories (`dav310` under conv, gather, reduce, scan; `dav3510` under
conversion, sort); 152 markdown references to `dav310` across the shelf; and no definition or
expansion of `dav310` anywhere in the repository. A directory listing establishes what names exist.
It cannot establish that any tool reads them, that any agent has ever mis-routed on one, or that the
templates behave differently from what their contents suggest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry establishes a naming inconsistency and the absence of a definition
in the repository as read on 2026-08-24 — it does **not** establish that anyone has been misled, and
the routing hazard in §2 is an argument from this book's own measured filename-channel finding, not
an observed incident. It does not establish that the `dav310` templates are 950 code by anything
stronger than their contents and their families' index rows; no template was compiled for any
architecture. It does not establish that the name has no consumers: the sweep covered this shelf's
markdown and directory tree, not build scripts, tooling, or the rest of the repository (Arm 2, not
run). It does not establish that `dav3510` is the intended convention — two families use it and
neither declares it normative. `docs/STANDARDS.md` was searched and is silent on directory naming,
which records an absence rather than a rule. The 310-family DAV numbers quoted from `npu-arch` are
upstream's text about other architectures and no fact from them is carried into this book
(RULES.md Art. 1). BOARD is `family-claimed(unverified)`: a directory name implicates no board.
