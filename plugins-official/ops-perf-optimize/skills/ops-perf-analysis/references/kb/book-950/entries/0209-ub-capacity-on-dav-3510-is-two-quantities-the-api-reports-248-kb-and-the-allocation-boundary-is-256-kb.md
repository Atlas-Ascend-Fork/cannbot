```
ID:        0209-ub-capacity-on-dav-3510-is-two-quantities-the-api-reports-248-kb-and-the-allocation-boundary-is-256-kb
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 950PR 2026-08-24 (Arm A interface, Arm B boundary with its declared
           blinding arm, Arm C anchor re-computation). The §5 verdict landed OUTSIDE all three
           pre-declared values and the entry is CORRECTED IN PLACE per §5's correction clause:
           the single number 248 KB splits into TWO quantities — API-reported 253952 and
           runtime-enforced 262144. See §6.
BOARD:     950PR
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:110 — "| UB | `ub_size` | 248 KB (253952) |"
           (§2.5 DAV_3510); :150 §3 速查表 "UB | 256 KB | 256 KB | 192 KB | 248 KB | **248 KB**"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003` —
           `aarch64-linux/data/platform_config/Ascend950{PR,DT}_*.ini`: all 32 files with
           `NpuArch=3510` carry `ub_size=253952`. No 3510 ini carries 196608 or 262144.
SOURCE:    verification machine, CANN `Version=9.1.0` `timestamp=20260730_231653901`
           (x86_64-linux): all 34 `Ascend950*.ini` carry `ub_size=253952`; none carry 196608
           or 262144. Same invariance, second toolkit.
INDEX:     Ascend950PR (soc string `Ascend950PR_9579`), AIC 28, rated 1650 MHz
           (untimed correctness runs; curFreq at deep idle 100 MHz pre and post), HBM 131072 MB,
           CANN 9.1.0 ts 20260730_231653901, driver 25.7.rc1, 2026-08-24.
           Re-derive Arm A: host probe calling GetCoreMemSize(CoreMemType::UB) after
           aclrtSetDevice(0), printing aclrtGetSocName() in the same process — returns 253952.
           Re-derive Arm B: single-source `-xasc --npu-arch=dav-3510` kernel (build line in
           book-950/CALIBRATION.md) that InitBuffers one TBuf<VECCALC> of N bytes, writes sentinel words
           at [0] and [N/4-1], DataCopies both blocks to GM; host bisects N at 32 B granularity
           between a granted anchor (131072) and a refused anchor (327680), one process per probe.
           Re-derive ini side: grep -h '^ub_size=' <toolkit>/*/data/platform_config/Ascend950*.ini | sort -u
OVERTURN:  on a full (non-vNPU, uncut) 950PR under this pin: `GetCoreMemSize(UB)` returning
           anything other than 253952, OR the same §4 Arm B probe granting more than 262144,
           refusing 262144 or less, or a sentinel round-trip failing at the granted boundary.
           On any OTHER pin or part, a diverging pair does not overturn this entry — it narrows
           its scope and gets its own run record.
```

# 0209 · UB on DAV_3510 is 248 KB, and no installed 950 ini carries 192 or 256

## 1 · Claim
**As corrected 2026-08-24 by the §4 run (the original single-number claim is below):** on
Ascend950PR under CANN 9.1.0, "UB capacity" is TWO quantities, 8192 B apart, and neither may be
used for the other's job:

- `GetCoreMemSize(CoreMemType::UB)` returns **253952 (248 KB)** — exactly the `ub_size` every
  installed 3510 ini carries, in both enumerated toolkits. Upstream's asserted identity between
  the ini field and the API return is TRUE. This is the number a tiling must budget against.
- The runtime's **enforcement boundary** for a single `InitBuffer` allocation is **262144
  (256 KB)**: 262144 is granted and its last word is writable and readable back; 262176 is
  refused (error 507035). The API value is therefore NOT the allocation-enforcement bound —
  a kernel can be granted 8 KB more than the API reports, and nothing at launch or sync stops it.

The 8192 delta means the "256 KB" family of upstream documents (C-003's 典型容量 table,
`conv_tiling.py:245`, the SIMT branch's 256 KB base in C-005) describes the enforcement/physical
tier, and the SIMT branch's own "256 KB − 8 KB − …" arithmetic names the same 8 KB this run
measured. The 192 KB documents gained no support from any arm (§6, Arm C).

As harvested, this entry claimed the single number 248 KB. The run did not overturn that number —
it split it. B3 ("950 UB 192 vs 248 KB") is CLOSED for 950PR: 192 KB is dead, and 248-vs-256 was
never a disagreement, it was two tiers.

## 2 · The wrong branch this removes
UB capacity is the denominator of essentially every Vector tiling decision, so a wrong value is not
a local error. Two directions, both live in the material an agent will read.

Too small (192 KB): every tile is undersized. Nothing crashes, nothing is incorrect, and the
operator simply leaves 22 % of the buffer unused for the life of the kernel. There is no symptom in
a profile — occupancy looks fine, the pipeline looks balanced, the kernel is just slower than it
needs to be. This is the direction upstream's own reduction budgets take (§3), and the numbers
downstream of them — `rGroupCnt=61`, `workspaceBytes=7808` — are reproducible self-checks calibrated
at 192 KB, so they will look self-consistent and be wrong together.

Too large (256 KB): allocation overruns. On a full part this may be caught at `InitBuffer`; inside a
vNPU slice, where the visible value is lower still (0207), it may not be caught at all.

The wrong branch this specifically removes is subtler than either: an agent that finds 192, 248 and
256 in three upstream files and picks the *conservative* one, reasoning that under-allocating is
safe. That reasoning is correct about safety and wrong about the fact, and it converts a resolvable
disagreement into a permanent 22 % tax.

## 3 · Ground / Source
Upstream's DAV_3510 row, `npu-hardware-params.md:103-114`:

> ### 2.5 DAV_3510 — Ascend950DT / Ascend950PR 系列
> | 参数 | INI 字段 | 值 |
> | NpuArch | `NpuArch` | 3510 |
> | L1 | `l1_size` | 512 KB (524288) |
> | L0C | `l0_c_size` | 256 KB (262144) |
> | **UB** | **`ub_size`** | **248 KB (253952)** |
> | BT | `bt_size` | 4 KB (4096) |

and its own note at `:116`:

> **关于 UB 容量**：表内值为 INI `ub_size` 字段，即 `GetCoreMemSize(CoreMemType::UB, ...)` 返回的
> 用户可用容量。**运行时始终以该接口返回值分块**，禁止硬编码。

Read that note carefully: upstream is asserting an *identity* between an ini field and an API return
value. That identity is the load-bearing half and it is exactly what a file read cannot check. §4
exists for it.

Second origin — the installed toolkit, read under the phase-1 read-only exception. All 32 files
matching `Ascend950{PR,DT}_*.ini` with `NpuArch=3510` carry `ub_size=253952`, across every core
count present (4, 8, 28, 32, 36 cube cores) and every L2 size present (16, 32, 96, 112, 128 MB). The
value does not vary with SKU. Verbatim from `Ascend950PR_9589.ini`:

```
[AICoreSpec]
...
ub_size=253952
```

The contradicting documents, all upstream, all recorded in `harvest/CONTRADICTIONS.md`:

- **C-003** — `ascendc-code-review/references/ascendc-perf.md:578` gives a chip-agnostic 典型容量 of
  UB **256 KB**, and `:611` hard-codes `UB_SIZE(256KB)` as a crash threshold. 256 KB matches no
  architecture in npu-arch's own §3 table except DAV_1001 and DAV_2002, neither of which is a 950.
- **C-004** — inside `ascendc-perf-optimize` itself:
  `references/single-core-pipeline/vec.md:102` says 248 KB for 950, while
  `references/tiling/reduction/fallback/example/euclidean_norm/experience.md:5` says
  "平台：Ascend 950 / arch35（dav-3510）…UB≈**192KB**" — and does so under a banner claiming
  "数据全部 msprof 上板实测". That is the most dangerous of the three: a wrong constant carried
  under a measurement claim.
- **C-006** — four values as script defaults in one subtree: `262144` (`conv_tiling.py:245`),
  `248 * 1024` (six scripts), `192 * 1024` (`scan_tiling.py:103`), and the only chip-scoped one,
  `topk_host_tiling.md:209`, "240 KiB usable of 248 KiB physical, DAV_3510".
- **C-005** — the SIMT branch computes a usable budget from a **256 KB** base
  (`ascendc-simt-tiling-design/SKILL.md:41`, `npu-arch/references/simt-arch-guide.md:119`), which is
  a fourth value for the same chip and is carried separately as 0238.

So the split is: one origin (npu-arch) plus the installed ini set say 248 KB; four upstream
documents say 192, 240-of-248, 256, or 256-as-a-SIMT-base. The `topk_host_tiling.md:209` figure is
not a fourth contradiction — 240 KiB *usable* of 248 KiB *physical* is a statement about a software
reservation, and it is the only one of the four that names its chip and distinguishes the two
quantities. It is compatible with this entry.

## 4 · Procedure
Runnable later on `950PR` and, separately, on `950DT` — a run on one does not establish the other,
and this entry's BOARD line will be narrowed at promotion to whichever actually ran.

Arm A — the interface, on a full part. Host/tiling side:

```cpp
#include "utils/tiling/platform/platform_ascendc.h"
auto plat = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
uint64_t ubSize = 0;
plat.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSize);
std::printf("ub_size_api=%llu resolved_soc=%s\n",
            (unsigned long long)ubSize, /* the SoC string the runtime resolved */);
```

The probe prints the resolved SoC string alongside the value, because Arm A's whole purpose is to
compare against *the ini the runtime chose*, and choosing the wrong file would produce a mismatch
with no hardware disagreement behind it (0204 §4 Step 3).

Arm B — the boundary, which is what actually establishes usable capacity. Allocate a single UB
tensor of `N` bytes and bisect `N` upward until `InitBuffer` or the kernel launch refuses. Record
the largest `N` that succeeds and the smallest that fails. This is the arm that distinguishes
"248 KB is in the ini" from "248 KB is available to me", and it is also the arm that would surface a
reservation like `topk_host_tiling.md`'s 240 KiB. Bisection granularity is declared now: 32 B, the
UB block size the same ini reports (`ubblock_size=32`, see 0219's neighbourhood).

Arm C — the 192 KB hypothesis, tested rather than dismissed. Run the `euclidean_norm` reproducible
self-check cited in C-004 (`rGroupCnt=61`, `workspaceBytes=7808` at `tiling-flow.md:201`) on the same
part, and record whether its budget is consistent with the Arm B boundary. If those figures only
reproduce under a 192 KB budget, that is evidence the 192 KB document is describing something real —
a reservation, a different toolkit, or a different part — and this entry gains a scope limit rather
than a confirmation.

Device selection: operator names the device index; the probe prints it back with
`compiler/version.info`; occupancy is checked before the run (shared machine, ≤4 dies); no die is
substituted for another; the part is confirmed to be un-partitioned before Arm A is treated as a
family reading.

**As run, 2026-08-24 (instantiation notes, recorded before promotion):** Arm A used
`PlatformAscendCManager::GetInstance()` after `aclrtSetDevice(0)` instead of a tiling-context
`GetPlatformInfo()` — same accessor, same resolved platform; the resolved soc string was printed
by the same process as required. Arm B allocated the probe buffer as one `TBuf<TPosition::VECCALC>`
and proved the grant real by writing sentinels at the first and last words and copying both 32 B
blocks back to GM (a grant whose tail cannot round-trip is scored VOID, not GRANTED); each probe
size ran as its own process so a refusal could not poison the next attempt. The §5 blinding used
a second 65536 B `InitBuffer` allocated FIRST in the same TPipe (the vNPU / `SetLocalMemorySize`
routes named in §5 do not exist on this installation); the boundary was required to move by
exactly 65536, and did. Arm C ran the shipped `reduction_tiling.py` blob directly (host python,
no device), which is what "the reproducible self-check" resolves to in the shipped tree.

## 5 · Checker — acceptance declared before the run
Verdict variable `ub_bytes`, taken from Arm B's largest success — **not** from Arm A. This is
deliberate and is the entry's main methodological point: Arm A can only show that the API agrees with
the ini, and the two documents already agree, so Arm A cannot discriminate between the hypotheses.
Only a boundary can.

Pass is declared now as: `ub_bytes == 253952`. Two named alternatives are declared *before* the run
so neither can be reinterpreted afterwards — `ub_bytes == 245760` (240 KiB) confirms a software
reservation and this entry is corrected in place to distinguish physical from usable;
`ub_bytes == 196608` (192 KB) overturns this entry, vindicates C-004's `euclidean_norm` figure, and
demotes the ini-plus-npu-arch pair to "two documents copying one error".

The checker must be able to go red and the input that does it is stated: run Arm B against a
deliberately under-allocated context (a vNPU slice, or `SetLocalMemorySize` reduced by 64 KB). The
boundary must move by the amount reserved. If it does not move, the bisection is not measuring
allocation at all — every green from it is void, and that is the blinding test, not a formality.

`ub_api_bytes` from Arm A is recorded separately and has no pass condition; its only role is to
detect a resolved-ini mismatch. Process exit code is not the verdict for any arm: a probe that
faults *because* the allocation succeeded is the interesting case, and exiting non-zero there would
read as failure.

## 6 · Evidence
Run 2026-08-24, Ascend950PR (soc `Ascend950PR_9579`), CANN 9.1.0
ts 20260730_231653901, driver 25.7.rc1. Identity block in INDEX.

**Arm A (interface):** `GetCoreMemSize(UB) = 253952 bytes`, printed by the same process as
`aclrtGetSocName() = Ascend950PR_9579`. The resolved ini (`Ascend950PR_9579.ini`, 9.1.0 set)
carries `ub_size=253952` — no resolved-ini mismatch. Recorded with no pass condition, per §5.

**Arm B (boundary, the verdict arm) — verbatim probe lines:**
```
GRANTED n=262144 reserve=0 sentinels ok
REFUSED n=262176 reserve=0 sync=507035
```
`ub_bytes = 262144`. Against §5's declared outcomes: not 253952 (pass), not 245760 (reservation),
not 196608 (overturn) — the result lies OUTSIDE the declared set, 8192 ABOVE the API value, and
the §5 correction clause ("distinguish physical from usable, reservation size logged") is applied
with the sign inverted from what §5 anticipated: the API value is the reduced tier, the boundary
is the full tier, delta 8192.

**Blinding arm (declared in §5, run before the verdict was read):** with 65536 B reserved first,
```
GRANTED n=196608 reserve=65536 sentinels ok
REFUSED n=196640 reserve=65536 sync=507035
```
boundary moved 262144 → 196608, exactly 65536. The bisection measures allocation; greens are live.

**Follow-up, same day, same part and pin:** a full-byte round-trip probe (GM pattern → the whole
allocation → GM, host comparing every byte) confirms `FULL-ROUNDTRIP n=253952` and
`FULL-ROUNDTRIP n=262144 every byte ok`, with `REFUSED n=262176 sync=507035`. The boundary grant
is backed byte-for-byte, not just at the sentinel words.

**Arm C (the 192 KB hypothesis):** the C-004 anchor (`tiling-flow.md:201`: templateType=1,
`rGroupCnt=61`, `usedCoreNum=61`, `workspaceBytes=7808`) does NOT reproduce from the shipped
`reduction_tiling.py` at `[64000,32]` axes=[0], coreNum=72, at ANY of ub∈{196608, 253952}
× dtype∈{fp32, fp16}: the script emits `template=ARA-Recompute, used_core_num=1,
workspace_size=73728` (= its line-384 formula `core_num*256*4`) in all four runs, byte-identical
across the two budgets, and emits no `templateType` or `rGroupCnt` field at all. The anchor's
workspace formula (61×32×4) is not the script's. Verdict: the anchor cannot vindicate 192 KB —
its figures are not a function of `ub_size` in the shipped script, and it does not reproduce from
the artifact it ships beside (version skew inside one subtree; measured for THIS blob only —
an earlier script version may have produced it, which this run cannot see).

## 7 · Scope limits — what this entry does NOT establish
The run covers ONE part (soc `Ascend950PR_9579`), ONE pin (CANN 9.1.0
ts 20260730_231653901, driver 25.7.rc1, `-xasc` build), un-partitioned. Nothing here covers
950DT (BOARD was narrowed at promotion accordingly), any other 950PR SKU, a vNPU slice, or any
other toolkit's runtime behaviour — the ini INVARIANCE was enumerated in two toolkits, the
BOUNDARY was measured in one. The boundary is for a SINGLE `TBuf` allocation in one TPipe; the
run does not establish what a multi-queue layout can sum to, whether the extra 8 KB is SAFE to
use (something else — sync/event storage, the SIMT branch's documented 8 KB reserve — may live
there and be silently corrupted; the full-byte round-trip proves every byte is backed and
readable, not freedom from side effects on whatever else uses that region), or whether the enforcement is hardware or the 9.1.0 runtime's software check. It
does not adjudicate `topk_host_tiling.md`'s 240 KiB usable figure (a further software reservation
below the API tier — untested). Arm C establishes only that the anchor does not reproduce from
the SHIPPED script blob; it says nothing about where the anchor's figures came from. The
identification of the measured 8192 with the SIMT documents' "− 8 KB" was recorded here as an
arithmetic match, NOT a mechanism identification. **2026-08-25 annotation**: the vendor's own
code now names the mechanism — `GetRuntimeUBSize()` (9.1.0,
`asc/include/basic_api/kernel_operator_sys_var_intf.h`) on 3510 under `SPLIT_CORE_VEC` returns
`get_shmem_sz() − RESERVED_UB_SIZE` with `RESERVED_UB_SIZE = 8*1024` by default and `2*1024`
under `__ASC_DISABLE_VF_STACK_RESERVED__` — a VF-STACK reservation. Code-witnessed, still not
behaviourally isolated: whether the ini's baked 253952 and this runtime subtraction are one
mechanism or two subtractions with one rationale is untested; a discriminating arm exists
(build with the disable macro and read `GetRuntimeUBSize()` — 260096 would show the reserve is
a software report, not a grant change; the measured 262144 enforcement already shows the
PHYSICAL grant ignores it). Nothing transfers to the other book
(RULES.md Art. 1): the DAV_2201 column quoted inside upstream's §3 table is upstream's text, and the
910-family behaviour of the same API pair is that book's business.
