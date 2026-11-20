```
ID:        0216-dav-3510-pairs-one-cubecore-with-exactly-two-vectorcores-and-splits-them-as-separate-core-types
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   corroborated — ops/npu-arch states the 1:2 ratio and the split core-type list; the
           installed CANN 9.0.0-beta.2 ini set independently carries
           `core_type_list=CubeCore,VectorCore` with `vector_core_cnt = 2 × cube_core_cnt` in all 32
           `NpuArch=3510` files. Both trace to vendor ini (0204); no core was launched.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:113-114 — "| 核心类型 | `core_type_list` |
           `CubeCore,VectorCore` |" / "| 核间关系 | — | CubeCore : VectorCore = 1 : 2 |"
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:167-171 — "**适用于 `CubeCore,VectorCore` 型
           架构**：每个 Cube Core 配 2 个 Vector Core（DAV_2201 / DAV_3510 已验证）… **实际值以
           `GetCoreNumAiv()` 为准**，部分 SKU 或 vNPU 实例可能裁剪。"  # same skill — ONE origin.
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — every `NpuArch=3510` ini:
           (cube_core_cnt, vector_core_cnt) ∈ {(4,8), (8,16), (28,56), (32,64), (36,72)};
           `core_type_list=CubeCore,VectorCore` in all 32.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -h '^\(cube\|vector\)_core_cnt=' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend950PR_9589.ini
OVERTURN:  a 950 part on which `GetCoreNumAiv() != 2 * GetCoreNumAic()`, or on which a pure-Vector
           kernel launched at `GetCoreNumAiv()` blocks leaves cores idle.
```

# 0216 · DAV_3510 pairs one CubeCore with exactly two VectorCores and splits them as separate core types

## 1 · Claim
Upstream asserts that DAV_3510 has a split core architecture — `core_type_list` is
`CubeCore,VectorCore`, with no combined `AICore` type — and that the ratio is one CubeCore to two
VectorCores. Upstream immediately qualifies it: the ratio describes the family specification, and
the actual count must come from `GetCoreNumAiv()` because a SKU or a vNPU instance may be cut. The
installed CANN 9.0.0-beta.2 set carries `core_type_list=CubeCore,VectorCore` in all 32
`NpuArch=3510` files, and `vector_core_cnt` is exactly twice `cube_core_cnt` in every one of them
across all five core-count configurations present. Not established here: no kernel was launched and
no accessor was called.

## 2 · The wrong branch this removes
The ratio decides which accessor a `SetBlockDim` call should read, and getting it wrong halves or
doubles the launch. A pure-Vector operator that calls `GetCoreNumAic()` launches on half the
available cores and is exactly 2× slower with a perfectly clean profile — every core it did launch
is fully utilised, so occupancy metrics look ideal. That is the failure mode with no signal.

The split-core-type half matters separately and is easy to miss. On architectures whose
`core_type_list` contains a combined `AICore`, one core does both jobs and there is a single core
count to reason about. On DAV_3510 there is not: a fused Cube+Vector operator must take *both*
counts and split each dimension against its own, which is precisely what upstream's routing table
says (`npu-arch-guide.md:212-216`). An agent carrying a single `coreNum` variable through a fused
kernel has already made the error, and it will not surface as a fault.

The upstream card libraries hardcode five different core counts across one subtree with none of them
chip-scoped (C-007). So the agent's wrong branch is the ambient practice in the material it reads,
which is why this entry names the accessor rather than the number.

## 3 · Ground / Source
`npu-hardware-params.md:103-114` (§2.5, DAV_3510), the last two rows:

> | 核心类型 | `core_type_list` | `CubeCore,VectorCore` |
> | 核间关系 | — | CubeCore : VectorCore = 1 : 2 |

The quick table at `:146-147` shows the architecture-level contrast that makes the split meaningful:

> | 核心类型 | AICore | AICore+VectorCore | CubeCore+VectorCore | AICore+VectorCore+CubeCore | CubeCore+VectorCore |
> | Cube:Vec 比例 | N/A (无Vec) | 非 1:2 | 1:2 | N/A (单核) | 1:2 |

`npu-arch-guide.md:165-171` states the rule with its scope and its caveat — this is the passage
worth keeping intact, because the caveat is the operative half:

> ### AIV (Vector) 核数
> **适用于 `CubeCore,VectorCore` 型架构**：每个 Cube Core 配 2 个 Vector Core（DAV_2201 / DAV_3510
> 已验证）。
> **不适用于**：`AICore,VectorCore` 型（DAV_2002，AICore 与 VectorCore 非 1:2）及单核集成型
> （DAV_3002 三合一、DAV_1001 无独立 Vec）。
> **实际值以 `GetCoreNumAiv()` 为准**，部分 SKU 或 vNPU 实例可能裁剪。

and the accessor routing at `:212-216`:

> | 算子使用的计算单元 | 核数接口 |
> | Vector（Add/Mul/Reduce 等） | `GetCoreNumAiv()` |
> | Cube（MatMul/Conv 等） | `GetCoreNumAic()` |
> | Cube + Vector（融合算子） | 两个都取，分别用于各自分块 |

All `ops/npu-arch/` — one origin (RULES.md Art. 3).

Second origin — the installed toolkit, read under the phase-1 read-only exception.
`Ascend950PR_9589.ini`:

```
[SoCInfo]
ai_core_cnt=32
cube_core_cnt=32
vector_core_cnt=64
core_type_list=CubeCore,VectorCore
```

Across all 32 `NpuArch=3510` files the (cube, vector) pairs are (4,8), (8,16), (28,56), (32,64),
(36,72) — five distinct configurations, ratio exactly 2 in every one. Note also that `ai_core_cnt`
equals `cube_core_cnt` in these files rather than naming a third kind of core; that is worth
recording because a reader who takes `ai_core_cnt` as "all the cores" gets the Cube count and a
pure-Vector kernel launched at half width.

The corroboration here is stronger than for a single constant: the ratio holds across five
independent configurations, so a transcription error would have to have been made five times
consistently. It is still two documents from one vendor pipeline, not a measurement.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion.

Arm A — the counts, from the runtime, both of them:

```cpp
auto plat = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
uint32_t aic = plat.GetCoreNumAic();
uint32_t aiv = plat.GetCoreNumAiv();
std::printf("aic=%u aiv=%u ratio=%.3f soc=%s\n", aic, aiv,
            aic ? (double)aiv / aic : -1.0, /* resolved SoC string */);
```

The resolved SoC string is printed so the pair can be matched against the ini the runtime actually
chose (0204 §4 Step 3). The ratio is computed in the probe rather than by hand so the readout carries
the claim directly.

Arm B — the occupancy arm, which is what establishes that the count is *usable* rather than merely
reported. Launch a trivially parallel pure-Vector kernel (elementwise add over a large contiguous
buffer) at `SetBlockDim(aiv)` and again at `SetBlockDim(aiv / 2)` and at `SetBlockDim(aiv * 2)`, same
shape, same die, same session. Record wall time for each. The half-width run should take
approximately twice as long; the double-width run should either be refused or take the same time as
the full-width run. This is what distinguishes "the API reports 64" from "64 cores execute".

Arm C — the fused arm, which tests §2's second branch. Launch a Cube+Vector operator with the Cube
dimension split against `aic` and the Vector dimension against `aiv`, then again with both split
against a single count, same shape and die. Record both times and both correctness results. The
single-count version is expected to be correct and slower, and demonstrating that is the point.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another — a multi-die sweep can make a per-die
occupancy claim false for every die at once, so all arms run on one named die in one session.

## 5 · Checker — acceptance declared before the run
Two verdict variables, kept apart because they can disagree and the disagreement is the information.

`aiv_over_aic` — from Arm A. Pass iff `aiv == 2 * aic` exactly. Not a tolerance: these are integer
counts and any inexactness is a real finding, not noise.

`cores_are_live` — from Arm B. Pass iff the half-width run takes between 1.7× and 2.3× the full-width
run's time, AND the double-width run does not beat the full-width run. The second clause is the one
that matters: if `SetBlockDim(aiv * 2)` is *faster*, then `aiv` under-reports the usable cores and
`aiv_over_aic` passing means nothing.

Arm A passing with Arm B unavailable is reported as `NOT ESTABLISHED — reported counts only`, never
as a pass. A run that only reads the accessors cannot distinguish a correct count from a count that
merely echoes the ini, and echoing the ini is what a hardcoded constant also does — the known blind
species.

The blinding test, declared before the run: run Arm B with `SetBlockDim` pinned to 1. The wall time
must rise by roughly `aiv`×. If it does not, the block dimension is not controlling parallelism in
this kernel and every timing Arm B produced is void.

Process exit code is not the verdict for any arm; a refused oversized launch exits non-zero and is an
expected outcome, not a failure.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The ini values in §3 are a
read of installed files under the sanctioned phase-1 read-only exception; configuration counts do not
establish that any core executes.

## 7 · Scope limits — what this entry does NOT establish
No device was contacted and no kernel was launched. The entry does not establish that
`GetCoreNumAiv()` returns `vector_core_cnt`, that all reported cores are schedulable, or that a vNPU
slice reports its own reduced count — upstream asserts the last and §4 does not test it. It does not
establish the ratio on any part outside this install's ini set, and upstream itself scopes the 1:2
rule to `CubeCore,VectorCore` architectures and warns that SKUs may be cut; a cut that removed
VectorCores asymmetrically would break the ratio without contradicting either origin. Nothing
transfers to the other book (RULES.md Art. 1) — the DAV_2201 half of upstream's 已验证 parenthesis and
every other-architecture column in the quoted tables are carried as quotation, not as fact, and this
book claims nothing about whether any 910-family part is 1:2. It says nothing about what the two
core types can do concurrently, about SSBuffer messaging between them (0227), or about whether the
ratio implies anything about achievable Vector throughput. The reading is pinned to toolkit
`9.0.0-beta.2`, host directory `aarch64-linux`, one machine.
