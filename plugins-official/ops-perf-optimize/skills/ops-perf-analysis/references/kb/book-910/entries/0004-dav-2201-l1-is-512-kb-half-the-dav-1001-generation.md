```
ID:        0004-dav-2201-l1-is-512-kb-half-the-dav-1001-generation
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 910B2 2026-08-24. The §5 checker's declared FAIL branch fired
           (`l1_bytes` = 524032, not 524288) and the claim is CORRECTED IN PLACE per that branch:
           the API under-reports the ini by 256 B, the same delta 0003 measured on UB. See §6.
           STRENGTHENED same day, later run: the §7-named enforcement-boundary arm CLOSED —
           InitBuffer at TPosition::A1 grants 524288 and refuses 524320, so the three-tier
           structure (API = ini−256, enforcement = ini) holds on this family's L1 as on its UB.
BOARD:     910B2
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:81 — "| L1 | `l1_size` | 512 KB (524288) |" (§2.3 DAV_2201)
SOURCE:    verification machine, CANN `Version=9.1.0` `timestamp=20260730_231653901`
           (aarch64-linux): `platform_config/Ascend910B{1,2,2C,3}.ini` all carry `l1_size=524288`.
INDEX:     910B2, NPU 0, bus 0000:C1:00.0, AIC 24, rated 1800 MHz (untimed correctness run;
           curFreq 800 MHz idle), HBM 65536 MB/die, CANN 9.1.0 ts 20260730_231653901,
           driver 25.5.1, 2026-08-24.
           Re-derive API tier: the SAME single-pass probe as 0003 (GetCoreMemSize over UB, L1,
           L0A, L0B, L0C, BT plus GetCurNpuArch in one process) — L1 returns 524032, arch 2201.
           Re-derive ini tier: grep -h '^l1_size=' <toolkit>/aarch64-linux/data/platform_config/Ascend910B*.ini
           Re-derive enforcement tier: single-source `--cce-aicore-lang --cce-aicore-arch=
           dav-c220-cube` kernel (cube variant of the 0003 probe) that InitBuffers one
           TBuf<TPosition::A1> of N bytes after an optional reserve, GM→A1 head/tail-block
           copies, verdict at stream sync; direct probes at 524032/524288/524320 plus a
           reserve-65536 arm whose boundary must sit at exactly 524288−65536.
OVERTURN:  on a full 910B2 under this pin: `GetCoreMemSize(L1)` returning anything other than
           524032, the resolved ini carrying anything other than 524288, a single A1 InitBuffer
           beyond 524288 being granted with clean sync, or one at or below 524288 being
           persistently refused (a transient refusal reproduced by re-probe is required — see
           §6). On another part or pin, a diverging triple narrows scope instead of overturning.
```

# 0004 · DAV_2201 L1 is 512 KB — half the DAV_1001 generation

## 1 · Claim
**As corrected 2026-08-24 by the §4 run:** on Ascend910B2 under CANN 9.1.0, the ini `l1_size` is
524288 (512 KB) in every 2201 platform_config file enumerated, and `GetCoreMemSize(CoreMemType::L1)`
returns **524032** = 524288 − 256. The API under-reports the ini by exactly 256 B — the same
delta this book measured on UB (0003), so the −256 is per-family API behaviour, not a UB
peculiarity. The generational half of the claim stands as upstream states it (DAV_1001 carried
1 MB; the measured 2201 part reports the 512 KB tier, not 1 MB — the §5 red value 1048576 did
not appear).

**Third tier, closed by the later same-day run (the arm §7 had named OPEN):** the runtime's
single-`InitBuffer` enforcement boundary at `TPosition::A1` is **524288 exactly** — the ini
value, not the API value (524288 granted, 524320 refused with 507015; the reserve-shift
blinding lands at exactly 524288 − 65536). The full three-tier structure of 0003's UB result
holds on L1: ini 524288, API = ini − 256, enforcement = ini. Upstream's "tile by the API
return" stays safe on this family — the API is the conservative tier.

As harvested, this entry carried upstream's single-number claim: `l1_size` 524288 and the API
returns it. The run split ini from API.

## 2 · The wrong branch this removes
A Cube tiling agent carries an L1 budget forward from Ascend910-era code or documentation and
plans a `kL1` / A-full-load / B-full-load residency that needs more than 512 KB. Unlike the UB
case (0003), the error direction here is *generational regression* — the newer part has LESS L1 —
so an agent's instinct that a later chip is bigger points the wrong way. The failure appears as
an L1 over-budget at tiling time or, worse, as a silently-degraded schedule if the tiling code
clamps instead of failing.

## 3 · Ground / Source
`ops/npu-arch/references/npu-hardware-params.md` §2.3, line 81: `| L1 | \`l1_size\` | 512 KB
(524288) |`.

The generational comparison is stated in the same file's §3 差异速查 table, line 148:
```
| L1 | 1 MB | 1 MB | 512 KB | 1 MB | 512 KB |
```
across the columns DAV_1001 / DAV_2002 / DAV_2201 / DAV_3002 / DAV_3510. So DAV_2201 and DAV_3510
share 512 KB, and all three earlier generations have 1 MB.

Restated in the same repo (one origin):
`ops/ascendc-performance-analysis/references/metrics_reference.md:118` — "| **L1 Buffer** | 512 KB
| 512 KB | 512 KB | 1 MB |" for 910B1/B2, 910B3, 950, 310P3.

No conflicting version was found for DAV_2201 L1 in the sources surveyed for this book. That is
itself worth stating: the absence of a conflict is not evidence of correctness — both statements
above are the same origin.

## 4 · Procedure
Proposed, runnable later; not run.

Identical in shape to 0003 §4, substituting `CoreMemType::L1`. Name the die; record occupancy
before and after; refuse to substitute a die. Print arch and size on one line. Cross-read
`l1_size` from `platform_config/*.ini` with `grep -R` (read-only, no execution).

Because 0004 and 0003 are one runtime query apart, the honest procedure queries UB, L1, L0A, L0B,
L0C and BT in one pass and records all six — a second visit to the same die to fetch one more
constant is waste, and splitting them invites the two readings to be taken under different
conditions and then compared as if they were not.

**As run, 2026-08-24:** exactly that single-pass probe ran once (all six CoreMemTypes plus L2,
HBM, FB, core counts, GetCurNpuArch, in one process after `aclrtSetDevice(0)`); this entry takes
its L1 reading from the same run 0003 took its UB reading from. Arch and size printed by one
process on adjacent lines (as-run note, same as 0003 §6).

## 5 · Checker — acceptance declared before the run
Verdict variable `l1_bytes`.
PASS iff `l1_bytes == 524288` and the same line reports NpuArch 2201.
FAIL iff any other value, including 1048576 (the DAV_1001 figure) — which is the specific input
that makes this checker go red, and the specific value an agent carrying old knowledge would
expect. Unwritten out-parameter (sentinel 0) is INCONCLUSIVE, not PASS.
Exit code is not the verdict.

## 6 · Evidence
Run 2026-08-24, 910B2 NPU 0 (bus 0000:C1:00.0), CANN 9.1.0 ts 20260730_231653901, driver 25.5.1,
AICore 0% on all 8 dies. Identity block in INDEX.

**Interface arm:** `GetCoreMemSize(L1) = 524032`, `GetCurNpuArch() = 2201`, one process.
Against §5: `l1_bytes == 524288` is FALSE → the declared FAIL branch ("any other value …
corrected in place") fired. The declared red value 1048576 (DAV_1001) also did not appear —
the generational-regression half survives. The checker bleeds on its declared red input by
construction (feed 1048576: comparison fails). The probe's unwritten-out-parameter sentinel was
−1 rather than §5's 0; the parameter WAS written, so INCONCLUSIVE did not arise.

**INI arm:** `Ascend910B1/B2/B2C/B3.ini` all carry `l1_size=524288` on this installation.
API ≠ ini by −256; per 0003 §4's rule, the disagreement is the finding and outranks both.

**Enforcement arm (added 2026-08-24, the arm §7 had named OPEN; die 0, AICore 0 % on all
8 dies pre and post):** cube-side probe (`--cce-aicore-arch=dav-c220-cube`, first use of the
cube token on this pin — accepted), one `TBuf<TPosition::A1>` of N bytes, GM→A1 head and
tail-block copies, verdict at stream sync. Direct probes:

```
GRANTED n=524032 reserve=0     GRANTED n=524288 reserve=0     REFUSED n=524320 reserve=0 sync=507015
```

Blinding, declared before the run: with 65536 B reserved first, the boundary bracket is
458752/458784 — 458752 + 65536 = **524288 exactly**, corroborating the direct probes
arithmetically. Recorded honestly: the reserve-0 bisection converged to 520160/520192, but its
"refused" endpoint re-probed GRANTED — one transient refusal mid-bisection steered it low; the
verdict rests on the direct probes and the blinding arithmetic, both of which agree, not on
the bisection. Evidence tier: allocation-layer grant/refuse with reserve-shift blinding — no
byte round-trip back to GM ran (L1 has no direct read-back path in this probe), unlike 0003's
UB sentinels. Refusal code observed: 507015 (the code the 950 book's BT/L0/L1 overflows
produce), where UB overflows on both boards produce 507035 — an observation, not established
semantics.

## 7 · Scope limits — what this entry does NOT establish
The run covers ONE part (910B2, NPU 0, bus 0000:C1:00.0) under ONE pin (CANN 9.1.0
ts 20260730_231653901). No other 2201 part is established (ini invariance enumerated only).
The enforcement-boundary arm (closed in §6) is ALLOCATION-tier evidence: a single
`TBuf<TPosition::A1>` grant boundary with reserve-shift blinding, no byte round-trip — it does
not establish that every byte of the granted range holds data (0003's UB arm did round-trip;
L1 lacked a read-back path in this probe), nor which tier the Matmul HIGH-LEVEL API holds a
plan to after its own staging — that remains a separate question. One transient refusal
occurred during the reserve-0 bisection (re-probe granted); its cause is not established, and
the OVERTURN clause now requires persistence for refusal-based readings. The −256 delta's
mechanism is not established (same open question as 0003 §7; RE-DERIVED on this machine same
day: the aarch64 toolkit's `asc/include/utils/base/sys_constants.h` carries the vendor's own
compile-time table with `ASC_UB_SIZE = 192*1024 - 256` and `ASC_L1_SIZE = 512*1024 - 256` in
the 2201 rows — a vendor-side witness that the −256 is intentional; what the 256 B is FOR stays
open. Enumeration lesson kept: the toolkit ships two same-named files and the impl-side one
carries no table — a first-hit find reported a false absence before the full enumeration). It does not establish whether L1 is partitioned between A
and B by a fixed rule, or whether the 512 KB is shared between the CubeCore and its two
VectorCores.
