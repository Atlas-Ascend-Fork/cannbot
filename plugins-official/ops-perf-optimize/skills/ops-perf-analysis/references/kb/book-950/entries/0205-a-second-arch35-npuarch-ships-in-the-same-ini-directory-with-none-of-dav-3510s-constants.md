```
ID:        0205-a-second-arch35-npuarch-ships-in-the-same-ini-directory-with-none-of-dav-3510s-constants
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — two contacts on two different propositions, neither of them a run: the
           upstream product map (what it lists) and one read of the installed toolkit's ini
           directory (what ships there). This is NOT corroboration — the two origins do not assert
           the same thing, they supply the two halves of a gap. Nothing was queried on a device.
BOARD:     family-claimed(unverified)
           # the claim is about the arch35 NAMESPACE, not about a 950 part; DAV_3505 names no
           # board token this book recognises, which is itself the finding.
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:13-21 — the 产品映射表 in full; its
           rows are DAV_1001, DAV_2002, DAV_2201 (×2), DAV_3002, DAV_3510 (×2). There is no
           DAV_3505 row, and no row whose 芯片型号 is Ascend035.
SOURCE:    installed toolkit, CANN `Version=9.0.0-beta.2`, `innerversion=V100R001C10SPC001B214`,
           `timestamp=20260328_213255003` — `aarch64-linux/data/platform_config/Ascend035.ini`,
           `Ascend035A.ini`, `Ascend035B.ini`, each carrying `NpuArch=3505`.
INDEX:     none — nothing measured; see SOURCE. The ini side is re-derivable by file read:
           grep -H '^NpuArch=' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend035*.ini
OVERTURN:  a later toolkit in which no `NpuArch=3505` ini ships, or an upstream revision of the
           产品映射表 that adds a DAV_3505 row — either closes the gap this entry names. Also
           overturned if `Ascend035` is shown to be excluded from the `archXX` rule by some
           mechanism upstream states elsewhere and this entry missed.
```

# 0205 · A second `arch35` NpuArch ships in the same ini directory with none of DAV_3510's constants

## 1 · Claim
Upstream asserts a complete product map (`npu-hardware-params.md` §0) that lists seven rows and
declares itself the single place to edit when the chip list changes. Upstream also asserts
(0202) that `archXX` is the first two digits of the DAV number. The installed CANN 9.0.0-beta.2
toolkit ships three ini files in the directory upstream declares as its own data source —
`Ascend035.ini`, `Ascend035A.ini`, `Ascend035B.ini` — carrying `NpuArch=3505`, which the archXX rule
maps to **arch35**, and which appears in no row of the map. Their constants match `DAV_3510`'s in
no field an operator depends on. Not established here: nothing was run on any part, and no device
of either architecture was contacted.

## 2 · The wrong branch this removes
An agent that has internalised "arch35 means 950" — which is exactly what the card libraries teach,
since `arch35`/`arch3510` are used interchangeably throughout them — treats an `arch35` label as a
950 scope. This entry supplies the counterexample from the machine's own toolkit: `arch35` is
already a two-member namespace here, and the second member has `ub_size=32768`, `l0_c_size=0`,
`l1_size=0`, `vector_core_cnt=0`, `core_type_list=AICore`, and a Cube MAC shape of 1×16×16. A tiling
routine that branched on `arch35` and assumed 248 KB of UB, a VectorCore, and a 16³ MAC array would
be wrong in every one of those on `Ascend035`.

The failure is silent in the specific way that matters: `NpuArch=3505` is not an error value, not a
reserved value, and not obviously a simulator — it is a well-formed entry in the vendor's own
platform directory with a full `AICoreintrinsicDtypeMap`. Nothing about reading it flags a problem.
The only defence is scoping on the four-digit value, never on the two-digit abbreviation.

## 3 · Ground / Source
Upstream's map, `npu-hardware-params.md:13-21`, quoted in full — note the header sentence at `:11`
that makes exhaustiveness a design claim, not an accident:

> **本表为 SKILL.md 与 `npu-arch-guide.md` 共用的真源，需要修改芯片清单时仅在此处更新。**
>
> | 产品系列 | SocVersion | NpuArch | __NPU_ARCH__ | 芯片型号 |
> |---------|-----------|---------|:---:|---------|
> | Atlas 训练系列 | ASCEND910 | DAV_1001 | 1001 | Ascend910 |
> | Atlas 推理系列 | ASCEND310P | DAV_2002 | 2002 | Ascend310P1, Ascend310P3, Ascend310P5, Ascend310P7 |
> | Atlas A2 训练/推理 | ASCEND910B | DAV_2201 | 2201 | Ascend910B1~B4, Ascend910B2C |
> | Atlas A3 训练/推理 | ASCEND910B | DAV_2201 | 2201 | Ascend910_93 |
> | Atlas 200I/500 A2 推理 | ASCEND310B | DAV_3002 | 3002 | Ascend310B1~B4 |
> | Atlas A5 训练 | ASCEND950 | DAV_3510 | 3510 | Ascend950DT (Decode) |
> | Atlas A5 推理 | ASCEND950 | DAV_3510 | 3510 | Ascend950PR (Prefill) |

The installed toolkit's `Ascend035.ini`, verbatim head and the fields that matter:

```
[version]
SoC_version=Ascend035
Short_SoC_version=Ascend035
AIC_version=AIC-N-350
CCEC_AIC_version=dav-n350
NpuArch=3505

[SoCInfo]
ai_core_cnt=1
vector_core_cnt=0
l2_size=0
core_type_list=AICore

[AICoreSpec]
cube_freq=150
cube_m_size=1
cube_n_size=16
cube_k_size=16
vec_calc_size=4
l0_a_size=0
l0_b_size=0
l0_c_size=0
l1_size=0
ub_size=32768
```

`Ascend035A.ini` and `Ascend035B.ini` carry the same `NpuArch=3505` with `ub_size=131072` and
`262144` respectively — so the three files do not even agree with each other on UB.

Set against `DAV_3510` (0209-0216, from the same directory): `ub_size=253952`, `l1_size=524288`,
`l0_c_size=262144`, `bt_size=4096`, `core_type_list=CubeCore,VectorCore`, `cube_m/n/k=16/16/16`,
`cube_freq=1650`. The overlap is empty.

Two honest qualifications belong here rather than in §7, because they bear on how much the finding
proves. First, `AIC_version=AIC-N-350` and `CCEC_AIC_version=dav-n350` use an `N`/`n350` naming that
none of the 950 files use, so the two may be different product lines that merely collide in the
first two digits — which is precisely the collision 0202's OVERTURN predicted and does not weaken
the point. Second, by 0204's convention this ini may well be an engineering-sample or simulation
configuration with no silicon behind it; that does not matter for this claim, because the failure
mode is a *string* comparison on `arch35` in a build or routing rule, and the string is present in
the directory regardless of whether the part is.

This gap is filed as `C-950arch-001` in `harvest/contradictions-950-arch.md`.

## 4 · Procedure
Runnable later. The decisive arm needs no device; the confirming arm does.

Arm A — enumeration, no device. Over the pinned toolkit's platform-config directory, group every
ini by the first two digits of its `NpuArch` and print any group with more than one distinct value,
together with the fields that differ. This is 0202 §4 Step 1-2 and is shared deliberately: the two
entries make the same measurement carry two different claims, and neither should be re-run
separately.

Arm B — resolution, on a `950PR`. Confirm that a 950 part resolves to a `NpuArch=3510` ini and not
to a 3505 one, and that `GetCurNpuArch()` returns the four-digit value rather than anything
two-digit. The device index is named by the maintainer and printed back; occupancy is checked first
(shared machine); nothing is inferred from `PATH`.

Arm C — the routing arm, which is the one that tests the actual risk. Build the same kernel source
twice: once behind `#if __NPU_ARCH__ == 3510` and once behind whatever `arch35`-shaped selector the
operator repo's build system uses, and compare which implementation each selects for a `950PR`
target and for a hypothetical 3505 target. The procedure refuses to assume the two selectors are
equivalent; that equivalence is the thing under test.

## 5 · Checker — acceptance declared before the run
Verdict variable `arch35_is_ambiguous`. Declared before any readout: it is TRUE iff Arm A returns a
two-digit group `35` containing at least two distinct `NpuArch` values that differ in at least one
of `ub_size`, `l1_size`, `l0_c_size`, `core_type_list`, `cube_m_size`. The process exit code is not
the verdict.

The checker is a positive fixture by construction — it must FIND the collision, and a clean run is
a *failure to reproduce this entry*, which is a real outcome and would demote the entry rather than
confirm it. The stated blinding test: point Arm A at a directory containing only `Ascend950*.ini`;
it must then report `arch35_is_ambiguous = false`. If it reports true against that input, the
grouping logic is broken and every green result from it is void.

The known blind species is guarded explicitly: the enumeration counts the files it processed and
compares against the directory listing, because these trees contain symlinks and `grep -r` does not
follow symlinked directories while `grep -R` does — a silently short file list would produce a
confident "no collision".

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The ini contents in §3 are
a read of files on this machine's installed toolkit, performed under the phase-1 read-only
exception; a file read is not a run, establishes nothing about any physical part, and in particular
does not show that any `Ascend035` device exists or that any build system would route to it.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, no build was performed, no device was contacted. The entry does not establish
that `DAV_3505` denotes a real chip, that it is an Ascend NPU in any sense a 950 kernel author would
recognise, or that any operator repo actually routes it into an `arch35` directory — Arm C exists
because that last step is the whole risk and is currently unverified. It does not establish that
upstream's map is wrong; a map may legitimately omit non-product configurations, and upstream never
promises the map covers the ini set. What it establishes is narrower and sufficient: on this
install, the two-digit abbreviation does not identify a unique architecture, so it cannot carry a
scope. The finding is pinned to one toolkit version (`9.0.0-beta.2`) on one machine and to one
architecture directory (`aarch64-linux`); other toolkit versions and other host architectures were
not enumerated. It says nothing about `arch22` or any 910-family collision (RULES.md Art. 1) — that
question exists but belongs to the other book and must be established there independently.
