```
ID:        0009-core-counts-differ-between-910b1-b2-and-910b3-inside-one-npu-arch
LABEL:     trap
LEVEL:     L1 (core & pipe assignment)
STRATUM:   corroborated — second origin = the installed CANN 9.1.0 platform-config set on the 910 machine
           (read-only): Ascend910B1/B2/B2C.ini carry cube_core_cnt=24 vector_core_cnt=48 and
           Ascend910B3/B4/B4-1.ini carry 20/40, all under NpuArch=2201 (§6, 2026-08-25). The §5 runtime
           verdict is INCONCLUSIVE by its own declared negative arm: one physical part in the fleet
           (Ascend910B2 → 24/48, the measured part). Not verified: the claim needs two parts.
BOARD:     910B2 (measured 2026-08-25: 24/48); 910B1, 910B3, 910B4 from the installed ini only
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:130-131 — "| 910B1/B2 | 24 | 48 | 1:2 | 分离模式 |", "| 910B3 | 20 | 40 | 1:2 | 分离模式 |"
INDEX:     none — nothing measured; see SOURCE. (Runtime readout on the ONE installed part, 2026-08-25:
           `aclrtGetSocName()` = Ascend910B2, `GetCurNpuArch()` = 2201, `GetCoreNumAic()` = 24,
           `GetCoreNumAiv()` = 48; ini census in §6. Not a verdict — §5 needs a second part.)
OVERTURN:  a runtime `GetCoreNumAic()` on a named 910B3 part returns 24, or on a named 910B2 part returns 20 — i.e. the counts do NOT differ by sub-model.
```

# 0009 · Core counts differ between 910B1/B2 and 910B3 inside one NpuArch

## 1 · Claim
Upstream asserts that Ascend910B1 and 910B2 carry 24 Cube cores and 48 Vector cores, while
Ascend910B3 carries 20 and 40 — a 17 % difference between parts that share NpuArch DAV_2201, the
same `__NPU_ARCH__` 2201, and the same SocVersion `ASCEND910B`. Upstream's truth source
independently states that core count is one of the parameters that varies by sub-model within one
NpuArch. Not established here.

## 2 · The wrong branch this removes
An agent hardcodes `coreNum = 24` (or 48) after reading npu-arch's SKU example table, which lists
only Ascend910B2. Every discriminator available to it — arch macro, NpuArch enum, SocVersion —
returns the same value on 910B3, so nothing in the build or the runtime tells it the number is
wrong. The kernel launches with a block dim 20 % above the available cores; the runtime clamps or
serialises, and the measured time is worse than the model predicted for a reason no profile field
names. This is the concrete cost of 0001 and 0002: the identifiers collapse, so the *only* honest
source of a core count is the runtime query (0011).

The second wrong branch is subtler and is why this entry is labelled `trap` rather than
`knowledge`: an agent that DOES query at runtime, but then compares a measurement taken on one
part against a model calibrated on another, has produced a two-point comparison of two different
machines and can attribute nothing from it.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §3.2 核数, lines 128-133 in
full:
```
| 芯片 | AIC (Cube核) | AIV (Vector核) | AIC:AIV | 工作模式 |
|------|-------------|---------------|---------|---------|
| 910B1/B2 | 24 | 48 | 1:2 | 分离模式 |
| 910B3 | 20 | 40 | 1:2 | 分离模式 |
| **950** | **32** | **64** | **1:2** | **分离模式** |
| 310P3 | 8 | 7 | ~1:1 | 耦合模式 |
```

Corroborating the *variability*, though not the specific numbers —
`ops/npu-arch/references/npu-hardware-params.md:124` (same repo, one origin):
"> **同一 NpuArch 内，核数、频率、L2、Memory 等参数可能随子型号不同而变化。**"
and line 126: "算子代码**必须通过 `PlatformAscendC` 接口运行时获取**."

npu-arch's SKU example table (line 132) lists only Ascend910B2 for DAV_2201, at 24/48 — consistent
with the metrics table's first row, and silent on 910B3.

**A third statement, in conflict with both**, filed as `harvest/contradictions-910.md` C-910-002:
`ops/ops-profiling/SKILL.md:215` — "| **Block Dim** | 等于可用核数（910B: 20~40 核） | 远小于可用
核数 | Block Dim = 1 |". The range 20–40 spans 910B3's pair exactly and excludes 910B1/B2's 24/48
on the upper end. So upstream carries three shapes of this fact: per-sub-model pairs, a
single-SKU example, and a range that contradicts the pairs.

**A board-token gap this entry exposes**: `form/CONVENTIONS.md` lists no accepted token for
Ascend910B3, though npu-arch's product map includes it in "Ascend910B1~B4" and two files scope
claims to it by name. BOARD here is therefore `family-claimed(unverified)`, which under-states what
the source says — the honest reading is in this section, not in the header. Recorded as a standing
question rather than fixed unilaterally, since CONVENTIONS is not this agent's file to edit.

## 4 · Procedure
Proposed, runnable later; not run.

1. This procedure requires TWO physically different parts and cannot be run on one. Name both dies
   explicitly, record `npu-smi info -t board` for each, check occupancy before and after on each,
   and refuse to substitute — substituting a die here destroys the entire experiment, because the
   claim is precisely that dies differ.
2. On each part, one pass printing `GetCoreNumAic()`, `GetCoreNumAiv()`, `GetCurNpuArch()`,
   `GetSocVersion()` and the board name from `npu-smi`.
3. Read-only INI arm: `grep -Rn "cube_core_cnt\|vector_core_cnt\|ai_core_cnt" \
   "$ASCEND_HOME_PATH"/*/data/platform_config/`, recording every 910B-family INI found and its
   counts, whether or not it matches an installed part.

**As run (2026-08-25, the 910 machine, one job):** step 2 on the only 910-family part in the fleet
(`npu-smi`: 910B2 ×8; die 0 bus 0000:C1:00.0 — the platform library, not the die, answers these
queries): `aclrtGetSocName()` = `Ascend910B2`, `GetSocVersion()` = 1, `GetCurNpuArch()` = 2201,
`GetCoreNum()` = 48, `GetCoreNumAic()` = 24, `GetCoreNumAiv()` = 48. Step 1's second part does not
exist here, so step 2 could not be repeated on a 910B3 and the §5 negative arm applies. Step 3 as
written, over `$TK/aarch64-linux/data/platform_config/` (the same seven files appear once more under
the `latest/*/data/platform_config` glob — one set, listed twice).

## 5 · Checker — acceptance declared before the run
Verdict: the pair `(aic_n, aiv_n)` per part, tagged with that part's board string.
The claim is upheld iff the two parts return different pairs while returning identical NpuArch and
SocVersion values. It is overturned iff the pairs are identical.
The declared negative arm: if only one part is available, the verdict is INCONCLUSIVE and must be
recorded as such — a single 24/48 reading is consistent with both the claim and its negation, and
scoring it as PASS is the failure this book exists to prevent.
Exit code is not the verdict; the board string comes from a different tool than the counts, and a
missing board string makes the reading unattributable and therefore INCONCLUSIVE rather than
passing on the counts alone.

## 6 · Evidence
§4's two-part comparison is NOT YET RUN to a verdict — the fleet holds one 910-family part — so the
§5 verdict is **INCONCLUSIVE** by its own declared negative arm (a single 24/48 reading is consistent
with the claim and with its negation). What WAS run on 2026-08-25 (the 910 machine, CANN 9.1.0) is the
one-part arm and the read-only ini arm, below; nothing in §1 is a measurement of two parts.

Runtime readout on the installed part (board string from `npu-smi`, counts from `platform_ascendc`):

| tool | value |
|---|---|
| `npu-smi info` | 910B2 (eight dies, all `910B2`) |
| `aclrtGetSocName()` | `Ascend910B2` |
| `GetSocVersion()` / `GetCurNpuArch()` | 1 / 2201 |
| `GetCoreNum()` / `GetCoreNumAic()` / `GetCoreNumAiv()` | 48 / 24 / 48 |

Read-only ini census (`platform_config/Ascend910B*.ini`, seven files):

| ini | NpuArch | ai_core_cnt | cube_core_cnt | vector_core_cnt |
|---|---|---|---|---|
| Ascend910B.ini | 1001 | 30 | — | 0 |
| Ascend910B1.ini | 2201 | 24 | 24 | 48 |
| Ascend910B2.ini | 2201 | 24 | 24 | 48 |
| Ascend910B2C.ini | 2201 | 24 | 24 | 48 |
| Ascend910B3.ini | 2201 | 20 | 20 | 40 |
| Ascend910B4.ini | 2201 | 20 | 20 | 40 |
| Ascend910B4-1.ini | 2201 | 20 | 20 | 40 |

The ini set states exactly upstream's split — 24/48 for B1/B2 and 20/40 for B3 — under one NpuArch,
and extends it: B2C sits with B1/B2, B4 and B4-1 with B3, and the NpuArch=1001 `Ascend910B.ini` is
a different generation (30 AI cores, no vector cores; cf. 910:0077 for the same file's L2). The
measured part matches its ini (24/48 = Ascend910B2.ini). What is NOT shown: that a 910B3 part
*returns* 20/40 at runtime — that is the half of the claim only a second part can supply.

## 7 · Scope limits — what this entry does NOT establish
One part measured (910B2 → 24/48); the runtime half of the claim for 910B3 (and B4, B4-1, B2C) rests
on the installed ini files, which are configuration the runtime reads, not a measurement of a die.
The fleet has no second 910-family SKU, so §5's PASS cannot be reached here and the entry stays
corroborated. Ascend910_93 and the 910C string (present in the toolkit, mapped to no ini — 910:0005's
lane) are not covered. The 1:2 AIC:AIV ratio holds in every 2201 ini and on the measured part; that
is seven files and one die, not a family law. Nothing transfers to the 950 book (RULES.md Art. 1).
