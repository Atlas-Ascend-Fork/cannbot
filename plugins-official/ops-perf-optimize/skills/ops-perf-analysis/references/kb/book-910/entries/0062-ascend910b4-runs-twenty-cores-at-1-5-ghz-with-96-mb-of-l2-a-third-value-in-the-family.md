```
ID:        0062-ascend910b4-runs-twenty-cores-at-1-5-ghz-with-96-mb-of-l2-a-third-value-in-the-family
LABEL:     boundary
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     910B4
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:93 — "**同架构其他子型号的核数、频率、L2、Memory 等存在差异**（如 910B4 核数 20@1.5GHz / L2 96MB / Memory 32GB）"; ibid:76 — "具体 SKU 可能裁剪（如 Ascend910B3 / Ascend910B4 均为 20 核）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a named Ascend910B4 part reports 24 Cube cores, 1.8 GHz, or an L2 capacity other than 96 MB.
```

# 0062 · Ascend910B4 runs twenty cores at 1.5 GHz with 96 MB of L2 — a third value in the family

## 1 · Claim
Upstream asserts that Ascend910B4 has 20 cores at 1.5 GHz, 96 MB of L2 and 32 GB of memory, and
that Ascend910B3 and Ascend910B4 both carry 20 cores. Upstream asserts that core count, frequency,
L2 and memory all differ across sub-models of one architecture. This makes **96 MB a third L2
figure** for the DAV_2201 family in upstream's own text, alongside 192 MB and 32 MB. Not
established here.

## 2 · The wrong branch this removes
0009 established that core counts differ inside DAV_2201 (24/48 versus 20/40). This entry closes
the harder question behind it: **how far the variation goes**. Three axes move together — cores,
clock, and cache — and they move by different factors. 910B4 against 910B2 is 0.83× the cores,
0.83× the clock and 0.5× the L2. A cost model calibrated on one and applied to the other is wrong
by different amounts in its compute term and its residency term, so a single scaling factor cannot
repair it.

The specific wrong branch: an agent that reads 0009, correctly concludes "query the core count at
runtime", and stops there. Querying cores alone leaves the clock and the L2 hardcoded — and per
0011's corrected §7 an L2 accessor exists, so there is no excuse for the third. A part with 83 % of
the cores and 50 % of the L2 will hold half as much working set resident while running only slightly
slower per core, which changes the tiling decision, not merely its scale.

The second branch is scoping this entry's own BOARD field. `910B4` is an accepted token in
`form/CONVENTIONS.md`, and this is the first entry in the book to use a board token other than
910B2 or 910_93 — because it is the first source that states a value **for a single named part**.
That is what BOARD is for, and it is worth noticing how rare it is: 60 of this book's 65 entries
cannot name a board because their sources do not.

## 3 · Ground / Source
`ops/npu-arch/references/npu-arch-guide.md:93`, the note under the 算力与系统规格 table, verbatim:
"> **注意**：以上为选定子型号的典型值（真源：`platform_config/*.ini`）。**同架构其他子型号的核数、
频率、L2、Memory 等存在差异**（如 910B4 核数 20@1.5GHz / L2 96MB / Memory 32GB），详见
`npu-hardware-params.md` 典型SKU示例。"

Line 76, the same file's standing caveat on its own table: "> 表内为**规格典型值**（族系规格），
具体 SKU 可能裁剪（如 Ascend910B3 / Ascend910B4 均为 20 核），vNPU 切分后单实例可见值更低。
**算子运行时必须通过下方接口获取实际值**，硬编码典型值会越界或浪费。"

Note the **vNPU** clause: partitioning makes the per-instance visible values lower still, so the
per-part figures are themselves an upper bound on what a kernel will see. No source in scope
quantifies vNPU partitioning, and this entry does not.

**Why this is the third L2 value.** Collected across upstream:
- 192 MB, Ascend910B2 — `npu-hardware-params.md:132`, `npu-arch/SKILL.md:52`, and
  `npu-arch-guide.md:182` (three files, one origin), carried by 0007.
- 32 MB, "910B1/B2" — `ascendc-performance-analysis/references/metrics_reference.md:122`, carried by
  0007 as `harvest/CONTRADICTIONS.md` C-001.
- **96 MB, Ascend910B4** — this entry.

The third figure does not resolve C-001 and is not a fourth position in that dispute: it is a
*different part*, so 96 MB and 192 MB can both be right. What it does is remove the assumption that
one number can stand for the family, which was implicit in the way C-001 was posed — as though the
question were "which of two numbers is the 910 L2". Filed as
`harvest/contradictions-910.md` **C-910-010**, which records the widening rather than a conflict.

The pointer at the end of line 93 ("详见 `npu-hardware-params.md` 典型SKU示例") does **not**
resolve: that file's SKU table (`:130-134`) lists only Ascend910B2 for DAV_2201 and contains no
910B4 row. A dangling cross-reference inside the declared truth source, of the same kind the
claim-card `ascendc-tiling-design--001` records for a FlashAttention parameter.

The file's standing, line 74: "> ⚠️ **核心原则**：本节作为 NPU 架构知识在 skills 仓中的上游真源，
下游 skill 应消费本节数据，**反向自引用即视为风险**。"

**Harvest note.** This file — `npu-arch/references/npu-arch-guide.md`, 431 lines — was not read in
the first pass of this book's harvest, which worked from `npu-arch/SKILL.md` and
`npu-hardware-params.md` only. It was reached by a coverage sweep for uncited 910-marked files at
the end of the harvest. Entries 0060–0065 and the correction note in 0011 §7 all come from that
sweep. Recorded because the miss is instructive: two files of a five-file skill are not the skill.

## 4 · Procedure
Proposed, runnable later; not run.

1. This procedure needs an Ascend910B4 part specifically. Name the die, record
   `npu-smi info -t board -i <n>`, check occupancy before and after, and refuse to substitute —
   substituting here substitutes the subject of the claim.
2. One host-side pass printing, on one line: `GetCoreNumAic()`, `GetCoreNumAiv()`,
   `GetCoreMemSize(L2)`, `GetCurNpuArch()`, and the board string. The L2 accessor exists
   (`npu-arch-guide.md:208`; see 0011 §7's correction).
3. Clock: read `cube_freq` from the matching `platform_config/*.ini` (`grep -R`, read-only) — no
   runtime accessor for frequency is named in any source in scope, so record that gap rather than
   inventing a measurement.
4. Memory: `aclrtGetDeviceInfo` or `npu-smi` for total HBM.
5. If no 910B4 is available, this entry cannot be verified and that is recorded as NOT ATTEMPTED.
   Do not verify it on a 910B2 and report the family.

## 5 · Checker — acceptance declared before the run
Verdict tuple `(aic, aiv, l2_bytes, freq_mhz, mem_bytes)` tagged with the board string.
PASS iff the board string identifies a 910B4 AND `aic == 20` AND `l2_bytes` is within 5 % of
96 MiB AND `freq_mhz` is within 5 % of 1500.
Each element is reported separately and a partial match is a partial verdict — if the cores match
and the L2 does not, the entry is corrected on the L2 alone, because these are three independent
values that upstream happened to state in one parenthesis.
The board string is a gate, not a field: if it does not identify a 910B4, no verdict is issued at
all, whatever the numbers say. That is the check that stops a convenient reading on a nearby part
from being recorded as this entry's evidence — the failure this entry's §2 exists to warn about.
`aiv == 2 × aic` is checked as a corollary of 0008 and reported, but is not part of this entry's
pass condition.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. BOARD names 910B4 because that is the part upstream's sentence
is about — **not** a part this book ran on. The figures come from a parenthetical example inside a
caveat, which is thinner ground than a table row, and the pointer to the fuller table does not
resolve (§3). This entry does not establish whether "20 核" means 20 Cube cores or 20 total —
`npu-arch-guide.md:76` says "20 核" and its own table column is "CubeCore 核数", so 20 Cube / 40
Vector is the reading taken, and it is a reading. It does not establish figures for 910B1, 910B2C or
Ascend910_93, still unstated anywhere in scope (Q-910-07). It does not quantify vNPU partitioning.
It does not resolve C-001.
