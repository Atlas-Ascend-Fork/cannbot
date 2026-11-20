```
ID:        0008-dav-2201-splits-cube-and-vector-into-separate-cores-at-one-to-two
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:86-87 — "| 核心类型 | `core_type_list` | `CubeCore,VectorCore` |", "| 核间关系 | — | CubeCore : VectorCore = 1 : 2 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a DAV_2201 part reports a `core_type_list` containing `AICore`, or a VectorCore-to-CubeCore count ratio other than 2:1.
```

# 0008 · DAV_2201 splits Cube and Vector into separate cores at one-to-two

## 1 · Claim
Upstream asserts that DAV_2201 declares `core_type_list = CubeCore,VectorCore` — two distinct core
types, with no combined `AICore` — and that the population ratio is one CubeCore to two
VectorCores. Upstream separately describes this as 分离模式 (separated mode), in which the Cube
core and Vector cores are deployed apart, each with its own Scalar unit, and each able to load
code independently. Not established here.

## 2 · The wrong branch this removes
An agent that learned the Ascend910 (DAV_1001) or Ascend310P model — where Cube functionality is
folded inside `AICore` and there is no separate CubeCore — writes a kernel and a block-dim
calculation that assume one core count. On DAV_2201 there are two, differing by 2×, and
`blockIdx` means a different thing on the AIC side than on the AIV side. The mistake surfaces as
half the cores idle or as a block dim that over-subscribes the Cube side by 2×. The normal checks
miss it because a single-core-type mental model produces code that runs — it simply runs on half
the machine, and a correctness test cannot see that.

## 3 · Ground / Source
`ops/npu-arch/references/npu-hardware-params.md` §2.3, lines 86-87:
```
| 核心类型 | `core_type_list` | `CubeCore,VectorCore` |
| 核间关系 | — | CubeCore : VectorCore = 1 : 2 |
```
Same file §3 差异速查, lines 146-147, places DAV_2201 against its neighbours:
```
| 核心类型 | AICore | AICore+VectorCore | CubeCore+VectorCore | AICore+VectorCore+CubeCore | CubeCore+VectorCore |
| Cube:Vec 比例 | N/A (无Vec) | 非 1:2 | 1:2 | N/A (单核) | 1:2 |
```
so DAV_1001 has no separate Vector core at all, and DAV_2002 has both types but explicitly NOT at
1:2 — the ratio is a DAV_2201/DAV_3510 property, not a general one.

Same repo (one origin), `ops/ascendc-performance-analysis/references/metrics_reference.md`
§3.2 核数 and §"工作模式说明", lines 130 and 137:
```
| 910B1/B2 | 24 | 48 | 1:2 | 分离模式 |
```
"- **分离模式**（Atlas A2/A3）：Cube 核和 Vector 核分离部署，各有独立 Scalar 单元，可独立加载代码"
— note this second statement is scoped to Atlas A2/A3, i.e. all of DAV_2201 per 0001.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Host-side, one pass:
   ```cpp
   auto p = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
   printf("aic=%u aiv=%u arch=%d\n", p.GetCoreNumAic(), p.GetCoreNumAiv(), (int)p.GetCurNpuArch());
   ```
3. Read-only INI cross-check: `grep -Rn "core_type_list\|cube_core_cnt\|vector_core_cnt" \
   "$ASCEND_HOME_PATH"/*/data/platform_config/` and record the SoC each match belongs to.
4. Behavioural arm for the "independent code load" half, which the counts do NOT establish: build
   one kernel with distinct AIC and AIV code paths of visibly different instruction-cache
   footprint, and record whether both sides launch. Absent this arm, only the ratio is tested.

## 5 · Checker — acceptance declared before the run
Verdict variables `aic_n`, `aiv_n`.
PASS iff `aiv_n == 2 * aic_n` and both are non-zero, with NpuArch 2201 on the same line.
Red inputs: `aiv_n == 0` (which is what a DAV_1001-style single-core-type part would give and is
therefore the discriminating negative), or any ratio other than exactly 2.
The ratio is checked, not the absolute counts — 0009 records that the absolute counts differ
between parts inside this same arch, so a checker pinned to 24/48 would go red on a correct 910B3
and would be measuring the wrong thing. Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. This entry does not establish the absolute core counts on any
part — see 0009, where upstream's own numbers differ across DAV_2201 members. It does not
establish that "each has its own Scalar unit" or "can load code independently"; those are
upstream's words about the mode, and the counts in §4 do not test them (§4 step 4 is what would).
It says nothing about whether the 1:2 ratio holds under a Mix (AIC+AIV) launch, nor about how
`blockIdx` is numbered across the two core types.
