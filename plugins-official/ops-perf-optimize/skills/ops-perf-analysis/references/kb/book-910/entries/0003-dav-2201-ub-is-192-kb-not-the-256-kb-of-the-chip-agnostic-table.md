```
ID:        0003-dav-2201-ub-is-192-kb-not-the-256-kb-of-the-chip-agnostic-table
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 910B2 2026-08-24. The §5 checker's declared FAIL branch fired
           (`ub_bytes` = 196352, not 196608) and the claim is CORRECTED IN PLACE per that branch:
           the ini value and the API return are 256 B apart on this family. See §6.
BOARD:     910B2
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:83 — "| UB | `ub_size` | 192 KB (196608) |" (§2.3 DAV_2201)
SOURCE:    verification machine, CANN `Version=9.1.0` `timestamp=20260730_231653901`
           (aarch64-linux): `platform_config/Ascend910B{1,2,2C,3}.ini` all carry `ub_size=196608`.
INDEX:     910B2, NPU 0, bus 0000:C1:00.0, AIC 24, rated 1800 MHz (untimed correctness runs;
           curFreq 800 MHz idle), HBM 65536 MB/die, CANN 9.1.0 ts 20260730_231653901,
           driver 25.5.1, 2026-08-24.
           Re-derive API tier: host probe calling GetCoreMemSize(CoreMemType::UB) and
           GetCurNpuArch() in one process after aclrtSetDevice(0) — returns 196352, arch 2201.
           Re-derive ini tier: grep -h '^ub_size=' <toolkit>/aarch64-linux/data/platform_config/Ascend910B*.ini
           Re-derive enforcement tier: single-source `--cce-aicore-lang --cce-aicore-arch=dav-c220-vec`
           kernel (build line in book-910/CALIBRATION.md) that InitBuffers one TBuf<VECCALC> of N bytes,
           sentinels at first and last words DataCopied back to GM; bisect N at 32 B granularity.
OVERTURN:  on a full 910B2 under this pin: `GetCoreMemSize(UB)` returning anything other than
           196352, the same §4 probe granting more than 196608 or refusing 196608 or less, or a
           sentinel round-trip failing at the granted boundary. On another part or pin, a
           diverging triple narrows scope instead of overturning.
```

# 0003 · DAV_2201 UB is 192 KB, not the 256 KB of the chip-agnostic table

## 1 · Claim
**As corrected 2026-08-24 by the §4 run (the original claim is below):** on Ascend910B2 under
CANN 9.1.0, "UB is 192 KB" resolves into THREE readings, and upstream's asserted identity between
the ini field and the API return is FALSE on this family:

- ini `ub_size` = **196608** (192 KB), in every 2201 platform_config file enumerated;
- `GetCoreMemSize(CoreMemType::UB)` returns **196352** = 196608 − 256 — the API under-reports the
  ini by exactly 256 B (the same −256 appears on this family's L1, see 0004);
- the runtime's single-`InitBuffer` enforcement boundary is **196608 exactly** (granted with the
  last word writable; 196640 refused, error 507035) — the ini value, not the API value.

Upstream's operational rule (运行时始终以该接口返回值分块) therefore remains SAFE on this family —
the API is the conservative tier, 256 B below what the runtime enforces — but its stated ground
(ini ≡ API return) is wrong here. The chip-agnostic 256 KB figure matches none of the three
readings and stays dead.

As harvested, this entry carried upstream's single-number claim: DAV_2201 `ub_size` is 196608 and
the API returns it. The run split that into the three tiers above.

## 2 · The wrong branch this removes
An agent sizing a Vector tile from the chip-agnostic 256 KB figure over-commits UB by a third on
every DAV_2201 part. The failure is not a clean allocation error: `InitBuffer` budgets computed on
host from a hardcoded constant simply produce a tiling that the kernel cannot honour, and the
symptom surfaces as a launch failure or corrupted output far from the constant that caused it.
The normal checks do not catch this because a host-side tiling function has no reason to consult
the device — the wrong number is arithmetically consistent with itself all the way down.
See 0011 for the rule that removes the class, not just this instance.

## 3 · Ground / Source
Primary, `ops/npu-arch/references/npu-hardware-params.md` §2.3 (DAV_2201 — Ascend910B /
Ascend910_93 系列), line 83:

```
| UB | `ub_size` | 192 KB (196608) |
```

The same file, line 116, states the interpretation and the standing rule:
"> **关于 UB 容量**：表内值为 INI `ub_size` 字段，即 `GetCoreMemSize(CoreMemType::UB, ...)`
返回的用户可用容量。**运行时始终以该接口返回值分块**，禁止硬编码。"

Restated elsewhere in the SAME repo — one origin, not corroboration (RULES.md Art. 3):
- `ops/npu-arch/SKILL.md:43` — "| UB | 192 KB | 248 KB |" (DAV_2201 vs DAV_3510)
- `ops/ascendc-performance-analysis/references/metrics_reference.md:117` — "| **UB** | 192 KB |
  192 KB | 248 KB | 256 KB |" across columns 910B1/B2, 910B3, 950, 310P3
- `ops/ascendc-tiling-design/SKILL.md:46` — "UB 容量限制（DAV_2201: 192KB, DAV_3510: 248KB）"
- `ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:25` — "以 Ascend
  910B 为例：UB (192KB) = 48 bank × 4KB = 16 bank group × 3 bank/group"
- `ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:310` — "| UB 容量 | 192KB
  per AIV | TQue×2 + 3×TBuf = 172KB 可行 |"
- `ops/ascendc-performance-best-practices/reference/elementwise/double_buffer_design.md:80` —
  "Available UB = 192KB (Ascend 910B3)"

**Conflicting version**, recorded at `harvest/CONTRADICTIONS.md` C-003:
`ops/ascendc-code-review/references/ascendc-perf.md:578` gives a chip-agnostic "典型容量" of UB
256 KB, and line 611 of that file hardcodes `UB_SIZE(256KB)` as a crash threshold. That figure
matches neither DAV_2201 (192 KB) nor DAV_3510 (248 KB). C-003 is cited, not re-filed.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die explicitly; record occupancy before and after; refuse to substitute another die.
2. Host-side tiling function on a DAV_2201 part (name it: Ascend910B2 if available, else record
   which part was used and treat the result as scoped to that part only):
   ```cpp
   auto p = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
   uint64_t ubSize = 0;
   p.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSize);
   printf("ub_size=%llu npuarch=%d\n", (unsigned long long)ubSize, (int)p.GetCurNpuArch());
   ```
3. Print the arch alongside the size in the same line, so the reading cannot be attributed to the
   wrong family after the fact.
4. Independently, `grep -Rn "ub_size" "$ASCEND_HOME_PATH"/*/data/platform_config/` (read-only,
   permitted in the no-card phase) and record the INI value for the matching SoC. If the INI and
   the API disagree, that disagreement is the finding and outranks both.

**As run, 2026-08-24 (instantiation notes, recorded before promotion):** steps 1–4 ran as
written (step 2 via `PlatformAscendCManager::GetInstance()` after `aclrtSetDevice(0)` — same
accessor, no tiling context on a bare probe). Because step 4's arms DID disagree (API −256 vs
ini), a third arm was added before promotion to decide which tier the runtime enforces: a
single-source AIV kernel InitBuffering one `TBuf<VECCALC>` of N bytes with first/last-word
sentinels DataCopied back to GM, N bisected at 32 B granularity between a granted and a refused
anchor, one process per attempt, plus a blinding pass with 65536 B reserved first whose boundary
had to move by exactly 65536 (it did). Readouts in §6.

## 5 · Checker — acceptance declared before the run
Verdict variable `ub_bytes`, the value written by `GetCoreMemSize`.
PASS iff `ub_bytes == 196608` AND the same line reports NpuArch 2201.
FAIL iff `ub_bytes == 262144` (the chip-agnostic 256 KB) or any other value — either way the
number and the arch are recorded and the claim is corrected in place, not re-argued.
Exit code is not the verdict; `GetCoreMemSize` can return a status without writing the out
parameter, so the checker treats an unwritten `ub_bytes` (sentinel 0) as INCONCLUSIVE rather than
as a failed comparison. That sentinel is what stops this from being a checker that reads only the
line it expects: the "no value at all" case has its own verdict.

## 6 · Evidence
Run 2026-08-24, 910B2 NPU 0 (bus 0000:C1:00.0), CANN 9.1.0 ts 20260730_231653901, driver 25.5.1,
AICore 0% on all 8 dies before and after. Identity block in INDEX.

**Interface arm (§4 steps 2–3):** `GetCoreMemSize(UB) = 196352`, `GetCurNpuArch() = 2201`, same
process (as-run note: printed on adjacent lines of one probe rather than one line; the property —
one process, one resolved platform — holds. The probe's unwritten-out-parameter sentinel was −1,
not §5's 0; the parameter WAS written, so the INCONCLUSIVE case did not arise).
Against §5: `ub_bytes == 196608` is FALSE → the declared FAIL branch ("any other value — the
number and the arch are recorded and the claim is corrected in place") fired. The declared red
input 262144 trivially fails the same comparison — the checker bleeds.

**INI arm (§4 step 4):** `Ascend910B1/B2/B2C/B3.ini` all carry `ub_size=196608` on this
installation. API ≠ ini by −256: per §4 step 4's own rule, "that disagreement is the finding and
outranks both."

**Enforcement arm (added before this run, recorded in §4 as-run notes) — verbatim probe lines:**
```
GRANTED n=196608 reserve=0 sentinels ok
REFUSED n=196640 reserve=0 sync=507035
```
Blinding, declared and run before the verdict was read: with 65536 B reserved first,
```
GRANTED n=131072 reserve=65536 sentinels ok
REFUSED n=131104 reserve=65536 sync=507035
```
boundary moved 196608 → 131072, exactly 65536 — the bisection measures allocation.

## 7 · Scope limits — what this entry does NOT establish
The run covers ONE part (910B2, NPU 0, bus 0000:C1:00.0) under ONE pin (CANN 9.1.0
ts 20260730_231653901, driver 25.5.1). It does NOT establish the triple for 910B1, 910B4,
Ascend910B2C, Ascend910_93, or any other 2201 part — the ini INVARIANCE across those files was
enumerated, the API and the boundary were measured on one part only. The −256 delta's mechanism
is NOT established: whether it is a deliberate reservation, a rounding artifact, or a defect of
this platform-library build is unknown, and whether it appears on other pins is untested
(2026-08-24, later run: the installed toolkit's own compile-time constants —
`asc/include/utils/base/sys_constants.h`, re-derived on this machine — bake `192*1024 - 256`
and `512*1024 - 256` into the 2201 UB/L1 rows, a vendor-side witness that the −256 is
intentional; the mechanism question above stays open). The
boundary is for a single `TBuf` in one TPipe; multi-queue layouts, and how much of the 196608 is
*usable* after framework reservations (0035 records a documented 8 KB one), are not established —
note the boundary result says InitBuffer itself reserves nothing here. Nothing about DAV_3510
transfers to or from this entry (RULES.md Art. 1).
