```
ID:        0204-an-ini-file-is-necessary-but-not-sufficient-evidence-that-a-chip-exists
LABEL:     boundary
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin states the convention; the convention is a rule about
           evidence, and no attempt was made here to find a shipped ini with no silicon behind it.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:5 — "**数据可信度约定**：本文档中「INI 字段」
           /「实测」均指从 ini 读取到的静态配置值。**ini 文件是发现硬件参数的必要不充分条件** —
           并非每个 ini 都对应真实量产芯片，部分配置可能来自工程样片、仿真平台或规划中的 SKU。"
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:126 — "`platform_config/*.ini` 涵盖多种配置
           （含工程样片、仿真配置），ini 文件是发现硬件参数的必要不充分条件，因此**不在此处枚举
           "参数范围"**。算子代码**必须通过 `PlatformAscendC` 接口运行时获取**。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `platform_config/*.ini` whose fields are shown to disagree with what
           `GetCoreMemSize`/`GetCoreNumAiv` return on the physical part it names — that would make
           the ini not merely insufficient but actively misleading, a stronger claim than upstream's.
```

# 0204 · An ini file is necessary but not sufficient evidence that a chip exists

## 1 · Claim
Upstream asserts a confidence convention over its own data: every number it labels "INI 字段" or
"实测" is a *static configuration value read from an ini*, and an ini's presence is a **necessary
but not sufficient** condition for a hardware parameter to be real — because the shipped
`platform_config/` set also contains engineering samples, simulation configurations, and planned
SKUs. Upstream draws the operative consequence itself: it declines to publish parameter *ranges*
from the ini set, and requires operator code to obtain values from `PlatformAscendC` at runtime.
Not established here.

## 2 · The wrong branch this removes
This is the entry that licenses every other constant in this block, so the wrong branch is large.
Without it an agent treats the ini directory as a device census: it counts the files, reads
"there are 32 DAV_3510 SKUs", derives a min/max core count, and ships a tiling heuristic keyed to
that range. Two failures follow and neither is visible from inside. First, a config for a part that
was never fabricated widens the range downward or upward for free — the heuristic is then tuned for
a chip nobody has. Second, and worse, the ini census *under*-counts in the other direction: a SKU
introduced by a later toolkit is absent, so "the maximum is 36 cube cores" is true of this install
and false of the fleet. No compile fails, no test fails; the operator is merely mis-tiled on the
part that was not in the directory.

The convention also disciplines our own bookkeeping. An entry in this book that says "corroborated
by the installed ini" is claiming a *second document*, not a second measurement, and this entry is
where that distinction is written down.

## 3 · Ground / Source
`ops/npu-arch/references/npu-hardware-params.md:3-5`, the document's own header block, in full:

> > **数据源**：`${ASCEND_HOME_PATH}/<arch>/data/platform_config/*.ini`（arch 如 `aarch64-linux`、
> > `x86_64-linux`、`arm64-linux`），参数值以运行时 `PlatformAscendC` 接口返回为准。
> >
> > **数据可信度约定**：本文档中「INI 字段」/「实测」均指从 ini 读取到的静态配置值。**ini 文件是
> > 发现硬件参数的必要不充分条件** — 并非每个 ini 都对应真实量产芯片，部分配置可能来自工程样片、
> > 仿真平台或规划中的 SKU。文档聚焦架构级常量（§1、§2）和关键差异速查（§3），变化参数仅以典型
> > 量产 SKU 举例。

And the consequence it draws, at `:124-126`:

> > **同一 NpuArch 内，核数、频率、L2、Memory 等参数可能随子型号不同而变化。**
> > `platform_config/*.ini` 涵盖多种配置（含工程样片、仿真配置），ini 文件是发现硬件参数的必要
> > 不充分条件，因此**不在此处枚举"参数范围"**。算子代码**必须通过 `PlatformAscendC` 接口运行时
> > 获取**。

Two observations about this passage matter more than the rule itself.

First, upstream is redefining a word: it declares that when it writes 实测 ("measured"), it means
"read from an ini". That is an honest disclosure and it is also a warning — a downstream reader who
sees 实测 in an npu-arch table and reads it in the ordinary sense has been told, once, in a header
block, that it does not mean that. This is the only such disclosure in the repo (the 2026-08-24
structural survey found no other skill stating a confidence convention), so nothing repairs the
misreading downstream.

Second, upstream's discipline is asymmetric in a way it does not remark on: it refuses to publish
ranges (§ "子型号变化参数") but does publish specific SKU rows from the same ini set as examples,
including `Ascend950PR_957b` and `Ascend950PR_9589`. The example rows carry exactly the same
epistemic status as the range it declined to state. The refusal is well-placed; it is just not
complete.

## 4 · Procedure
Runnable later on `950PR` and `950DT`. The claim is about the relation between a file and a part,
so the procedure must contact both.

Step 1 — read the ini for the part under test and record every field an operator consumes:
`ub_size`, `l1_size`, `l0_a_size`, `l0_b_size`, `l0_c_size`, `bt_size`, `l2_size`,
`cube_core_cnt`, `vector_core_cnt`, `cube_freq`, `sparsity`, `core_type_list`. Record the toolkit
pin (`compiler/version.info`) with them; the pin is part of the datum.

Step 2 — on the physical board, obtain the same quantities through the sanctioned runtime path and
through nothing else:

```cpp
auto plat = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
uint64_t ub, l1, l0a, l0b, l0c, l2, bt;
plat.GetCoreMemSize(platform_ascendc::CoreMemType::UB,   ub);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L1,   l1);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_A, l0a);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_B, l0b);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_C, l0c);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L2,   l2);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::BT,   bt);
uint32_t aic = plat.GetCoreNumAic(), aiv = plat.GetCoreNumAiv();
```

Step 3 — record which ini file the runtime actually resolved to. This is the step the procedure
refuses to skip and refuses to infer: the board's reported SoC string is printed and matched
against the filename, because a mismatch here would explain a field mismatch in Step 2 without any
hardware disagreement at all. The device index is named by the maintainer, printed back, and its
occupancy is checked before the run (shared machine).

Step 4 — the *sufficiency* arm, which is the one that tests upstream's actual claim rather than its
corollary: for every ini in the directory that this install cannot resolve to a present device,
record it as unresolvable. Upstream's claim predicts this set is non-empty on a typical machine.

## 5 · Checker — acceptance declared before the run
Two verdict variables, deliberately separate, because they can disagree and the disagreement is the
information.

`ini_matches_runtime` — true iff every field in Step 1 equals its Step 2 counterpart for the
resolved ini. Any single mismatch sets it false and the mismatching field is named; the process exit
code is not the verdict, since the probe can fail to link for reasons unrelated to agreement.

`ini_set_is_a_census` — true iff Step 4's unresolvable set is empty. Upstream's claim predicts
FALSE. So this checker's pass condition is *the negative*, which is what makes it a positive fixture
rather than a confirmation ritual: it must find at least one ini with no device behind it. If it
finds none, that is a real result — it means this install's ini set happens to be a census, and the
entry's §7 gains a line rather than the checker gaining a green tick.

The blindness case is stated: if Step 4 marks a file "unresolvable" merely because resolution was
not attempted (no device of that family present at all), the count is meaningless. So Step 4 runs
only for families the machine has at least one member of, and files outside those families are
reported as *not tested*, never as unresolvable.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `platform_config`
directory of the installed `cann-9.0.0-beta.2` was read during harvest to source other entries in
this block; a directory read is not a run, and it cannot address the sufficiency question this
entry raises, because deciding whether a shipped ini has silicon behind it requires the silicon.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that any particular ini in this install lacks a
real part behind it — it records that upstream says some do, and supplies the procedure that would
find them. It does not establish that `PlatformAscendC` returns the ini's value; §4 Step 2 exists
because that is assumed everywhere upstream and demonstrated nowhere. It does not cover ini files
for the other book's architectures (RULES.md Art. 1). It says nothing about *which* of the three
categories upstream names — engineering sample, simulation config, planned SKU — any given file
belongs to; the ini format carries no such field, so that classification is not recoverable from
the data source at all, and any entry claiming it would be inventing. Finally, this entry does not
license the reverse inference: an ini's *absence* is not evidence a part does not exist, since the
set ships with the toolkit and a later toolkit may add rows.
