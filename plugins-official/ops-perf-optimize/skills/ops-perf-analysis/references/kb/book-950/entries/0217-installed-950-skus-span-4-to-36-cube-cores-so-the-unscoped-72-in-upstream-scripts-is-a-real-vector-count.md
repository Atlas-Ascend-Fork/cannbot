```
ID:        0217-installed-950-skus-span-4-to-36-cube-cores-so-the-unscoped-72-in-upstream-scripts-is-a-real-vector-count
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   corroborated — upstream publishes two 950 SKU rows (28/56 and 32/64); the installed CANN
           9.0.0-beta.2 ini set independently carries five configurations including 36/72. The two
           origins agree where they overlap and the ini set is strictly wider. Both trace to vendor
           ini (0204); no core was counted on a device.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:130-134 — "| DAV_3510 (PCIE) |
           Ascend950PR_957b | 28 | 56 | 1.65 GHz | 112 MB | 112 GB |" / "| DAV_3510 (Server) |
           Ascend950PR_9589 | 32 | 64 | 1.65 GHz | 128 MB | 128 GB |", under the heading
           "**同一 NpuArch 内，核数、频率、L2、Memory 等参数可能随子型号不同而变化。**"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — the 32 `NpuArch=3510` files carry
           (cube_core_cnt, vector_core_cnt) ∈ {(4,8), (8,16), (28,56), (32,64), (36,72)};
           36/72 appears in Ascend950DT_9591/9592/9595/9596/95A1/95A2 and Ascend950PR_9599.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -h '^vector_core_cnt=' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend950*.ini | sort -u
OVERTURN:  `GetCoreNumAiv()` on a real 950 part returning a value outside {8,16,56,64,72} — the
           enumerated set is then not the fleet, and any tiling keyed to its bounds is unscoped.
```

# 0217 · Installed 950 SKUs span 4 to 36 cube cores, so the unscoped 72 in upstream scripts is a real Vector count

## 1 · Claim
Upstream asserts that core counts vary by sub-model within one NpuArch and publishes two DAV_3510
examples: 28 CubeCore / 56 VectorCore and 32 / 64. The installed CANN 9.0.0-beta.2 platform-config
set carries five distinct DAV_3510 configurations — (4,8), (8,16), (28,56), (32,64), (36,72) — and
the 36/72 configuration appears in seven files, six 950DT and one 950PR. Not established here: no
device was contacted and `GetCoreNumAiv()` was never called.

The consequence for the harvest: `72` is a legitimate DAV_3510 `vector_core_cnt`, not an error.

## 2 · The wrong branch this removes
Contradiction **C-007** records five unscoped `coreNum` defaults across
`ascendc-perf-optimize/references/tiling/` — `64` in six scripts, `72` in the scan and reduction
scripts, `32` as `aicore_num` in conv, and `8`/`24` in worked examples — none of them chip-scoped. An
agent auditing that subtree against upstream's published SKU table sees 28/56 and 32/64, does not see
72, and concludes the scan and reduction scripts are wrong. It then "fixes" them to 64 and has
introduced a bug on every 36-core part in this install.

That is the branch this entry removes, and it is a specific hazard of harvesting: a truth source that
publishes *examples* invites a reader to treat the example set as the domain. Upstream is explicit
that it is not — it declines to publish ranges precisely so that no one does this (0204) — but the
declination is a sentence and the table is a table, and tables transmit better.

The second branch is the one C-007 is actually about and this entry does not repair: `72` being real
does not make an unscoped `72` correct. A script default of 72 is wrong on the 28-core parts, which
are the majority of the set. The fix is `GetCoreNumAiv()` (0207), not a better literal.

## 3 · Ground / Source
`npu-hardware-params.md:122-136`, the 子型号变化参数 block in full — the framing matters as much as
the rows:

> > **同一 NpuArch 内，核数、频率、L2、Memory 等参数可能随子型号不同而变化。**
> >
> > `platform_config/*.ini` 涵盖多种配置（含工程样片、仿真配置），ini 文件是发现硬件参数的必要不充分
> > 条件，因此**不在此处枚举"参数范围"**。算子代码**必须通过 `PlatformAscendC` 接口运行时获取**。
> >
> > 作为参考，以下为有 archXX 特化开发路径的架构典型量产 SKU 示例（数据来源：对应 ini 文件）：
> >
> > | 架构 | 示例型号 | CubeCore | VectorCore | 频率 | L2 | Memory |
> > | DAV_3510 (PCIE) | Ascend950PR_957b | 28 | 56 | 1.65 GHz | 112 MB | 112 GB |
> > | DAV_3510 (Server) | Ascend950PR_9589 | 32 | 64 | 1.65 GHz | 128 MB | 128 GB |
> >
> > > 注：DAV_2201 / DAV_3510 中 CubeCore : VectorCore = 1 : 2。

Read the second paragraph against the third: upstream refuses to enumerate a range, then publishes
two rows from the same ini set as 示例. The rows carry exactly the epistemic status the range would
have carried. The refusal is well placed and incomplete, and this entry exists in the gap.

Second origin — the installed toolkit, read under the phase-1 read-only exception. Grouping all 32
`NpuArch=3510` files by (cube, vector):

```
(4,  8)   Ascend950PR_950z
(8,  16)  Ascend950DT_950x, Ascend950DT_950y
(28, 56)  Ascend950DT_9571..9578, Ascend950PR_9579, _957b, _957c, _957d
(32, 64)  Ascend950DT_9581..9588, Ascend950PR_9589, _958b
(36, 72)  Ascend950DT_9591, _9592, _9595, _9596, _95A1, _95A2, Ascend950PR_9599
```

Upstream's two rows are reproduced exactly (`957b` → 28/56, `9589` → 32/64), which is a genuine
cross-check of the second origin against the first at their point of overlap. The other three
configurations are not in upstream's table.

Two qualifications belong here rather than in §7, because they bound what the ini set proves. By
0204's own convention, some of these files may be engineering samples, simulation configurations, or
planned SKUs — the (4,8) and (8,16) rows, with L2 at 16 MB and 32 MB against 112-128 MB for the
rest, look like small configurations rather than production parts, and nothing in the ini format says
which. And the set is this toolkit's set: a later CANN may add rows, so the observed maximum of 36 is
a floor on the fleet, never a ceiling.

Every configuration satisfies `vector = 2 × cube` (0216).

## 4 · Procedure
Runnable later on `950PR`; each distinct SKU needs its own run, and BOARD is narrowed at promotion to
the SKUs actually contacted.

Arm A — report the pair and the resolved file:

```cpp
auto plat = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
std::printf("aic=%u aiv=%u soc=%s\n", plat.GetCoreNumAic(), plat.GetCoreNumAiv(),
            /* resolved SoC string */);
```

The resolved SoC string is not decoration: this entry is a claim about which file corresponds to
which part, so a reading without its filename attributes nothing (0204 §4 Step 3).

Arm B — the census arm, which is the one that tests this entry's actual claim. Run Arm A on every
distinct 950 SKU the fleet exposes and collect the observed set of `aiv` values. Compare against
{8, 16, 56, 64, 72}. Two outcomes are informative and neither is a failure: an observed value outside
the set widens the domain and corrects this entry; an ini configuration never observed is consistent
with 0204's claim that the set contains non-production entries.

Arm C — the occupancy arm, which distinguishes a reported count from a usable one. On each part,
launch a trivially parallel pure-Vector kernel at `SetBlockDim(aiv)` and at `SetBlockDim(aiv/2)`,
same shape, same die, same session, and record wall time. Half width should cost roughly double. A
part reporting 72 that does not scale past 64 would mean the count is nominal, which no file read can
detect.

Device selection is explicit throughout: the operator names the device index, the probe prints it
back with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run
(shared machine, ≤4 dies), and no die is substituted for another. Arm C's paired runs must occur on
one named die in one session, or the ratio carries no attribution.

## 5 · Checker — acceptance declared before the run
Verdict variable `observed_aiv_set`, a set rather than a scalar — a single-part run cannot address a
claim about variation, and reducing it to one boolean would let one confirming part stand for the
fleet.

Pass is declared now as: `observed_aiv_set ⊆ {8, 16, 56, 64, 72}` AND `|observed_aiv_set| ≥ 2`. The
second clause is the operative one. A run on a single SKU is reported as `NOT ESTABLISHED — one
configuration observed`, never as a pass, because this entry's content is that the value varies, and
one sample is compatible with it being constant.

Failure is named now so it cannot be reinterpreted: any observed `aiv` outside the set overturns the
enumeration and the entry is corrected in place with the new value and its part, logged.

`cores_are_live` from Arm C is a separate verdict per part: pass iff the half-width run takes between
1.7× and 2.3× the full-width run. A part failing this has its `aiv` recorded as nominal, and its
value is excluded from `observed_aiv_set` rather than silently kept.

The blinding test, declared before the run: run Arm C with `SetBlockDim` pinned to 1. Wall time must
rise by roughly `aiv`×. If it does not, block dimension is not controlling parallelism in that kernel
and every Arm C verdict is void. Without this the checker only reads "two numbers differed", which is
the known blind species.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The core-count groupings in
§3 come from reading installed ini files under the sanctioned phase-1 read-only exception; a file
read cannot call `GetCoreNumAiv()`, cannot tell a production SKU from an engineering configuration,
and cannot show that a reported core executes.

## 7 · Scope limits — what this entry does NOT establish
No device was contacted. The entry does not establish that any of the five configurations corresponds
to a real part — 0204 records upstream's own convention that some shipped ini files do not — nor that
the enumerated set bounds the fleet: it is one toolkit (`9.0.0-beta.2`), one host directory
(`aarch64-linux`), one machine, and a later CANN may add configurations. It does not establish that
`GetCoreNumAiv()` returns `vector_core_cnt`, nor that all reported cores are schedulable. It does
**not** validate the unscoped `72` in upstream's scan and reduction scripts: it establishes that 72 is
a real value for some DAV_3510 configurations, which makes the literal defensible on those parts and
still wrong on the 28-core majority — the defect C-007 records is the absence of scoping, and this
entry does not repair it. Nothing transfers to the other book (RULES.md Art. 1); the Ascend910B2 row in
upstream's SKU table and the DAV_2201 half of its ratio note are carried as quotation only. Finally,
the entry says nothing about frequency, L2 or memory variation beyond noting that the same block
varies them too; those are separate claims and 0218 carries L2.
