```
ID:        0218-l2-on-dav-3510-varies-by-sku-from-16-mb-to-128-mb-and-is-the-one-buffer-shared-across-cores
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   corroborated — upstream publishes two 950 L2 figures (112 MB, 128 MB) and the installed
           CANN 9.0.0-beta.2 ini set independently carries five distinct `l2_size` values including
           both. Both trace to vendor ini (0204); no device was queried.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:130-134 — "| DAV_3510 (PCIE) |
           Ascend950PR_957b | 28 | 56 | 1.65 GHz | 112 MB | 112 GB |" / "| DAV_3510 (Server) |
           Ascend950PR_9589 | 32 | 64 | 1.65 GHz | 128 MB | 128 GB |", under
           "**同一 NpuArch 内，核数、频率、L2、Memory 等参数可能随子型号不同而变化。**"
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:182 — "| **L2** | 192 MB | **128 MB** (Server) /
           **112 MB** (PCIE) | 跨核共享缓存 |"   # same skill — ONE origin (RULES.md Art. 3).
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — across the 32 `NpuArch=3510` files,
           `l2_size` ∈ {16777216, 33554432, 100663296, 117440512, 134217728} = 16, 32, 96, 112,
           128 MB. `Ascend950PR_957b`=117440512, `Ascend950PR_9589`=134217728 — upstream's two rows
           reproduced exactly.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -h '^l2_size=' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend950*.ini | sort -u
OVERTURN:  `GetCoreMemSize(CoreMemType::L2, s)` on a 950 part returning a value outside
           {16, 32, 96, 112, 128} MB — the enumeration is then not the fleet, and any residency
           model keyed to its bounds is unscoped.
```

# 0218 · L2 on DAV_3510 varies by SKU from 16 MB to 128 MB, and is the one buffer shared across cores

## 1 · Claim
Upstream asserts that L2 is a cross-core shared cache whose capacity varies by sub-model within one
NpuArch, and publishes two DAV_3510 examples: 112 MB for `Ascend950PR_957b` (PCIE) and 128 MB for
`Ascend950PR_9589` (Server). The installed CANN 9.0.0-beta.2 platform-config set carries five distinct
`l2_size` values across its 32 `NpuArch=3510` files — 16, 32, 96, 112 and 128 MB — and reproduces
upstream's two rows exactly. Not established here: no device was contacted and `GetCoreMemSize` was
never called.

L2 is therefore unlike every other buffer in this block. UB, L1, L0A/B, L0C and BT are invariant across
all 32 files (0209-0213); L2 and the core counts (0217) are the two that move.

## 2 · The wrong branch this removes
L2 capacity is the residency knee: a working set that fits is served at L2 rates and one that does not
falls back to HBM, a 2-3× difference in effective bandwidth (0270). So an agent that treats L2 as a
constant has a tiling threshold that is right on one SKU and wrong on the rest.

The direction matters and both are silent. Assuming 128 MB on a 112 MB part means a tile sized to stay
resident spills, and the kernel runs at HBM rate while its model says L2 rate — the profile shows an
MTE2-bound kernel and the residency premise is invisible. Assuming 112 MB on a 128 MB part leaves 16 MB
of cache unused forever, with no signal at all.

The sharper branch is the one that looks like diligence. An agent that reads upstream's SKU table sees
two values, 112 and 128, and treats that as the range — so it writes a conservative model at 112. This
install contains SKUs at 16 MB and 32 MB, where 112 is wrong by 7×. That is 0204's failure exactly: a
truth source that publishes *examples* invites a reader to treat the example set as the domain, and
upstream declines to publish a range precisely so that no one does.

There is a fourth branch specific to L2 being **shared**. Every other capacity in this block is per-core;
L2 is not. So the residency budget an operator actually gets depends on what else is running on the
other cores of the same die, and on the shared machine this book's runs happen on, on what else is
running at all. A residency threshold derived from `l2_size` is a sole-tenant threshold, and nothing in
either origin says so.

## 3 · Ground / Source
`npu-arch-guide.md:173-186`, the per-core Buffer table — note that L2 is the row where the "per AI Core"
heading stops being true:

> ### Buffer 容量（每 AI Core）
>
> | Buffer | Ascend910B2 | Ascend950PR | 用途 |
> |--------|:---:|:---:|------|
> | **L0C** | 128 KB | **256 KB** | Cube 输出（Ascend950PR 翻倍） |
> | **UB** | 192 KB | **248 KB** | Vector 工作区，每 AIV 独立一份 |
> | **L2** | 192 MB | **128 MB** (Server) / **112 MB** (PCIE) | 跨核共享缓存 |
> | **BT** (biasSize) | 1 KB | **4 KB** | FixPipe Bias 表 |
>
> >  L1/L0A/L0B/L0C/UB/BT 通常在同代架构中一致，L2 和 Memory 可能因子型号而异。运行时一律以
> > `GetCoreMemSize` 为准。

跨核共享缓存 — shared across cores — and the note that L2 and Memory are the two that vary by sub-model
while the rest hold. Upstream separates the invariant buffers from the variable ones in one sentence,
which is the distinction this entry rests on.

The SKU rows, `npu-hardware-params.md:122-136`, under upstream's refusal to publish a range:

> > **同一 NpuArch 内，核数、频率、L2、Memory 等参数可能随子型号不同而变化。**
> > `platform_config/*.ini` 涵盖多种配置（含工程样片、仿真配置），ini 文件是发现硬件参数的必要不充分
> > 条件，因此**不在此处枚举"参数范围"**。
> >
> > | 架构 | 示例型号 | CubeCore | VectorCore | 频率 | L2 | Memory |
> > | DAV_3510 (PCIE) | Ascend950PR_957b | 28 | 56 | 1.65 GHz | 112 MB | 112 GB |
> > | DAV_3510 (Server) | Ascend950PR_9589 | 32 | 64 | 1.65 GHz | 128 MB | 128 GB |

Second origin — the installed toolkit, read under the phase-1 read-only exception. Grouping all 32
`NpuArch=3510` files by `l2_size`:

```
16777216  (16 MB)   Ascend950PR_950z                                   (4 cube / 8 vec)
33554432  (32 MB)   Ascend950DT_950x, _950y                            (8 / 16)
100663296 (96 MB)   Ascend950PR_957d                                   (28 / 56)
117440512 (112 MB)  Ascend950DT_9573, _9574, _9577, _9578,
                    Ascend950PR_957b, _957c, _958b, _9583, _9584,
                    _9587, _9588                                       (28 / 56 and 32 / 64)
134217728 (128 MB)  the remaining 17 files                             (28 / 56, 32 / 64, 36 / 72)
```

Upstream's two rows reproduce exactly — `957b` → 117440512, `9589` → 134217728 — which is a genuine
cross-check of the second origin against the first at their point of overlap. The other three values are
not in upstream's table, and the 16 MB and 32 MB configurations sit on the 4- and 8-cube-core parts that
0217 flags as plausibly non-production.

Note that L2 does **not** track core count: 112 MB and 128 MB both appear at 28/56 and at 32/64, and
96 MB appears at 28/56 alongside 112. So L2 cannot be inferred from the core count, which is the
inference an agent with two data points would reach for.

The downstream consumer that makes this operational is
`ascendc-performance-evaluation`'s hardware model (0270): its `l2_residency_knee_bytes` is 134217728,
pinned to `9589`, and its own note flags the 957b variant's 112 MiB as "可能是不同 SKU" and records a
change-and-revert where the constant was wrongly edited to 112 on documentary grounds and falsified by a
pure-write measurement. So the SKU spread has already caused one recorded error in upstream's own
calibration.

## 4 · Procedure
Runnable later on `950PR`; each distinct SKU needs its own run and BOARD is narrowed at promotion to the
SKUs actually contacted.

Arm A — the reported value, with its file. Call `GetCoreMemSize(CoreMemType::L2, l2)` and print it beside
the resolved SoC string, so the reading can be matched against the ini the runtime actually chose
(0204 §4 Step 3). Print `GetCoreMemSize(UB)` alongside as a control: UB is invariant across all 32 files,
so a probe returning wrong values for both is reporting a default rather than a reading.

Arm B — the residency knee, which is what establishes usable L2 rather than a reported number. Sweep a
single-stream working set across the reported capacity — 0.5×, 0.75×, 0.9×, 1.0×, 1.25×, 1.5×, 2× — and
record effective bandwidth at each point, minimum over 50 repetitions. The knee position is the readout.
This is 0270 §4 Arm A and the two entries share one run deliberately; what this entry adds is that the
sweep must be repeated **per SKU**, because the claim here is that the knee moves.

Arm C — the sharing arm, which no other entry covers and which §2's fourth branch names. Run Arm B's
sweep twice on the same part: once sole-tenant, once with a co-tenant kernel streaming a large working
set on other cores of the same die. The knee must move downward. If it does not, either L2 is partitioned
per core group or the co-tenant is not reaching L2, and both would change how a residency threshold
should be set.

Arm D — the enumeration, across SKUs. Run Arm A on every distinct 950 SKU the fleet exposes and compare
the observed set against {16, 32, 96, 112, 128} MB. A value outside it widens the domain and corrects
this entry; an ini configuration never observed is consistent with 0204's claim that the set contains
non-production entries.

Device selection is explicit: the operator names the device index **and the SKU**, the probe prints both
back with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run
(shared machine, ≤4 dies), and no die is substituted for another. Arm C's co-tenant is placed
deliberately and its placement recorded — an accidental co-tenant is exactly what Arm C is measuring, so
an unchecked shared machine would contaminate Arm B.

## 5 · Checker — acceptance declared before the run
Verdict variable `observed_l2_set`, a set rather than a scalar — a single-part run cannot address a claim
about variation, and one confirming SKU must not stand for the fleet.

Pass is declared now as: `observed_l2_set ⊆ {16, 32, 96, 112, 128} MB` **and** `|observed_l2_set| ≥ 2`.
The second clause is operative: a run on one SKU is reported as
`NOT ESTABLISHED — one configuration observed`, never as a pass, because this entry's content is that the
value varies and one sample is compatible with it being constant.

`knee_ratio[sku]` (Arm B) — the observed knee divided by the reported `l2_size`, per SKU. Pass iff it
lands in [0.9, 1.1] for every SKU measured. A knee consistently below 1.0 would mean part of L2 is
reserved or unreachable, which is a correction rather than a failure and would be logged with the
fraction.

`sharing_moves_knee` (Arm C) — pass iff the co-tenant sweep's knee is strictly below the sole-tenant
sweep's. A knee that does not move is reported with the co-tenant's measured bandwidth, because the
likeliest explanation is that the co-tenant never reached L2 and the arm did not fire.

The positive fixture, declared before the run: run Arm B with `SetL2CacheHint(CACHE_MODE_DISABLE)` on the
swept tensor. The sub-knee plateau **must** collapse to the HBM rate and the knee must disappear. If the
knee survives, the sweep is not measuring L2 residency — it is measuring something else that changes at
that working-set size — and every `knee_ratio` it produced is void. Without this the checker reads only
"bandwidth dropped somewhere", which is the known blind species: a working set crossing L2 capacity and
one crossing any other threshold look identical in a single curve.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `l2_size` groupings in §3
come from reading installed ini files under the sanctioned phase-1 read-only exception; a file read
cannot call `GetCoreMemSize`, cannot locate a residency knee, and cannot tell a production SKU from an
engineering configuration.

## 7 · Scope limits — what this entry does NOT establish
No device was contacted. The entry does not establish that any of the five values corresponds to a real
part — 0204 records upstream's own convention that some shipped ini files do not — nor that the
enumerated set bounds the fleet: it is one toolkit (`9.0.0-beta.2`), one host directory
(`aarch64-linux`), one machine, and a later CANN may add configurations. It does not establish that
`GetCoreMemSize(L2)` returns `l2_size`, nor that the full reported capacity is usable; Arm B's knee is
the only thing that would separate reported from usable, and upstream's own calibration data (0270)
already records one SKU where the documented figure and the measured knee were contested. It does not
establish anything about **sharing**: L2 is the one buffer in this block that is not per-core, every
figure here is implicitly sole-tenant, and neither origin says so — Arm C is the only arm that addresses
it and it is open. It says nothing about L2 bandwidth (0270), about `SetL2CacheHint` semantics, or about
how L2 is partitioned between Cube and Vector traffic. Nothing transfers to the other book (RULES.md Art. 1):
the 192 MB Ascend910B2 column in upstream's quoted table is carried as quotation only, and C-001 records
a separate 910-side disagreement about L2 that belongs there. Finally, the five-value enumeration is a
floor on the variation, not a range: upstream explicitly declines to publish a range from this ini set
and this entry does not publish one either — it reports what this install contains.
