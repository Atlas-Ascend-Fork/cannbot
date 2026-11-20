```
ID:        0212-l1-on-dav-3510-is-512-kb-and-did-not-grow-with-l0c
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 950PR 2026-08-24, §5 PASS branch: l1_bytes = 524288 (two-tenant
           total 524288 granted BIT-EXACT, 589824 refused; single-tenant end slid at 64 B
           granularity: 524032/524224/524288 granted clean, 524352 refused — ceiling is the ini
           value exactly, NO reservation found). Arm A control green (l0a=65536); blinding
           green (int8 doubles elements at unmoved byte ends). Readouts in §6.
BOARD:     950PR (narrowed at promotion per §4; 950DT remains ini-enumerated only, see §7)
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:108 — "| L1 | `l1_size` | 512 KB (524288) |"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — all 32 `NpuArch=3510` files in
           `aarch64-linux/data/platform_config/` carry `l1_size=524288`.
INDEX:     950PR (SoC Ascend950PR_9579), AIC 28, CANN 9.1.0
           ts 20260730_231653901, driver 25.7.rc1, 2026-08-24; untimed correctness runs, card
           idle before/after every case.
           Re-derive interface: GetCoreMemSize(L1)=524288 with L0A control 65536 and L0C 262144
           in one process, SoC printed (harvest/RUNS_20260824.md interface table).
           Re-derive boundary: mm_probe (0210's vehicle evolved: explicit A/B L1 byte offsets,
           bias off), bf16 K=256 baseK=16, A tenant 8192 B at 0; B tenant's END positioned by
           B_L1_OFF at 64 B granularity (footprint 507904/516096 B); double tenant A 262144 B
           (M=64, K=2048) + B adjacent; verdict = refusal OR wrong output columns
           (magnitude-aware threshold; wrap fixtures shown red).
           Re-derive ini: grep -h '^l1_size=' over NpuArch=3510 platform_config files.
OVERTURN:  on this part and pin: `GetCoreMemSize(L1)` returning anything but 524288; any
           resident layout whose highest occupied byte exceeds 524288 succeeding with every
           column correct; or one ending at or below 524288 (tenants non-overlapping) being
           refused or wrong under this §4's geometry. On other parts a diverging result
           narrows scope, it does not overturn.
```

# 0212 · L1 on DAV_3510 is 512 KB and did not grow with L0C

## 1 · Claim
Upstream asserts that the DAV_3510 L1 buffer — the Cube input cache where left and right matrix
operands reside — is 512 KB (524288 B), read from the ini field `l1_size`. The installed CANN
9.0.0-beta.2 platform-config set carries `l1_size=524288` in all 32 of its `NpuArch=3510` files.

**As run 2026-08-24 on 950PR (the claim is UPHELD, and sharpened):** `GetCoreMemSize(L1)`
returns 524288 exactly (with the L0A control green in the same probe); the enforced address
ceiling is **524288 to 64 B granularity** (resident ends 524032/524224/524288 granted with
clean output, 524352 refused); a two-tenant layout totalling exactly 524288 runs BIT-EXACT and
589824 is refused — so on this part the whole ini value is usable by operands and the
reservation §4 anticipated does not exist at this granularity. The chip-agnostic 1 MB (C-003)
is measured-wrong on 950PR. Readouts in §6.

## 2 · The wrong branch this removes
The wrong branch here is inherited from its neighbour. L0C doubled on DAV_3510 (0211) and upstream
presents the buffer changes as a set — L0C up, UB up, BT up. An agent that reads the delta table and
generalises "the buffers grew" gives L1 a proportional increase it did not get, and sizes an
A-FullLoad or B-FullLoad residency decision against 1 MB. That decision does not fail at compile
time: the tiling routine emits a plan, the plan overflows L1, and the operator either falls back at
runtime or thrashes MTE2 refilling operands it believed were resident.

The failure is hard to attribute afterwards because the symptom is an MTE2-bound profile, and an
MTE2-bound profile has a dozen ordinary causes. Nothing points back at the residency premise.

The second branch is the mirror image and matters for Cube tiling specifically: L1 is the buffer
that did *not* change, so it is the one place where a template carried forward from an earlier part
is right for the right reason. An agent that "modernises" every constant on a 950 port will change
this one too, and be wrong by introducing a change rather than by omitting one.

## 3 · Ground / Source
`npu-hardware-params.md:103-114` (§2.5, DAV_3510) gives `| L1 | l1_size | 512 KB (524288) |`. The
cross-architecture quick table at `:148` puts the invariance on the record:

> | 特征 | DAV_1001 | DAV_2002 | DAV_2201 | DAV_3002 | DAV_3510 |
> | L1 | 1 MB | 1 MB | 512 KB | 1 MB | 512 KB |

`npu-arch-guide.md:175-186`, the per-core Buffer table, lists L1 without the bold-face emphasis it
gives L0C, UB and BT — a formatting choice that carries the claim: `| **L1** | 512 KB | 512 KB |
Cube 输入缓存 |`. `npu-arch-guide.md:257` states its role: `| **L1 Buffer** | Cube 输入缓存 |
矩阵乘左/右矩阵驻留 |`. Both files are `ops/npu-arch/` and are therefore one origin (RULES.md Art. 3).

Second origin — the installed toolkit, read under the phase-1 read-only exception. From
`Ascend950PR_9589.ini`:

```
[AICoreSpec]
l0_c_size=262144
l1_size=524288
```

`l1_size=524288` holds in all 32 `NpuArch=3510` files — every 950PR and 950DT variant present, at 4,
8, 28, 32 and 36 cube cores, and across every L2 size in the set. No 3510 ini in this install carries
1048576.

**An upstream document does contradict this value.** Contradiction **C-003** in
`harvest/CONTRADICTIONS.md` records `ascendc-code-review/references/ascendc-perf.md:578` publishing a
chip-agnostic 典型容量 table with UB **256 KB**, L1 **1 MB**, L0C **256 KB**. Its L1 figure is 1 MB
against the 512 KB stated here — a factor of two, on the one buffer whose content is that it did *not*
change. So L1 is a three-way claim: npu-arch and all 32 installed 950 ini files say 524288, and a
chip-agnostic table in a third skill says 1048576.

That table names no architecture, and npu-arch's §3 quick table shows 1 MB is the correct L1 for
DAV_1001, DAV_2002 and DAV_3002 while 512 KB is correct for DAV_2201 and DAV_3510 — so the likeliest
reading is that the agnostic figures were written from a different family and carry no 950 scope at all.
That is a reading, not a finding: Art. 7 forbids resolving a contradiction by deciding which author is
more plausible, and §4 Arm B is what settles it. What makes it operational rather than academic is that
`ascendc-code-review` uses these figures as review thresholds — the same table hard-codes its UB value at
`:611` as a crash threshold — so a reviewer applying it to a 950 kernel would pass an L1 residency plan
that overflows by 2×.

The two origins agreeing here are not independent in the strong sense (both are vendor ini data, 0204),
so `corroborated` raises the priority of running §4 and raises nothing else — and it raises it more than
for a constant with no C-row, because a third document actively disagrees.

One thing the two origins do not jointly establish: `npu-arch-guide.md:184-188` is explicit that the
tabulated buffer figures are 族系典型值 and that `GetCoreMemSize` is authoritative at runtime. The
identity between `l1_size` and that return value is asserted by upstream and untested here. Nor does
either origin say how much of L1 a *user* may occupy — MTE1 staging, and on DAV_3510 the new UB→L1
path (0225), both consume it, and neither source apportions it.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion.

Arm A — report the value with an in-probe control:

```cpp
auto plat = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
uint64_t l1 = 0, l0a = 0, l0c = 0;
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L1,   l1);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_A, l0a);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_C, l0c);
std::printf("l1=%llu l0a=%llu l0c=%llu soc=%s\n", (unsigned long long)l1,
            (unsigned long long)l0a, (unsigned long long)l0c, /* resolved SoC string */);
```

L0A is the control: it is 64 KB on every architecture upstream lists (0213), so if all three come
back wrong together the fault is the probe or the resolved platform info, not L1. The resolved SoC
string is printed so the reading can be matched against the ini the runtime actually chose
(0204 §4 Step 3).

Arm B — the boundary, which is what establishes usable residency rather than a reported number.
Build a matmul kernel and sweep the L1-resident operand footprint upward — `baseK × baseM ×
sizeof(T)` for an A-resident plan, at fixed `baseN` so only the L1 tenant varies — until host tiling
rejects the plan or the launch fails. Record the largest accepted footprint and the smallest
rejected. Under this entry the boundary sits at or below 524288; under a 1 MB L1 it sits near
1048576, and the two are a clean factor of two apart, so the sweep cannot land ambiguously between
them. A boundary *below* 524288 is the informative outcome: it locates the reservation neither origin
reports.

Arm C — the double-tenant arm, which is the one that tests what a tiling routine actually needs.
Repeat Arm B with both A and B operands resident simultaneously. The accepted total must be
approximately the same byte figure, not twice it. If the two-tenant total exceeds the one-tenant
total, L1 is not the binding constraint in Arm B and Arm B's number is attributable to something
else.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another.

**As-run instantiation notes (2026-08-24, recorded before the verdict was read):**
1. Fleet has no 950DT; BOARD narrows to 950PR at promotion, as provided.
2. Arm A is satisfied by the same-day all-CoreMemType probe (one process, SoC printed):
   l1=524288, l0a=65536 (the control, green), l0c=262144, soc=Ascend950PR_9579
   (harvest/RUNS_20260824.md interface table).
3. Arm B instantiated: there is no host tiling engine in the vehicle (hand-filled tiling —
   upstream's SWAT formulates 256-wide blocks and is bypassed), so "host tiling rejects" becomes
   "the device/runtime refuses (stream-sync error) OR the output columns go wrong against
   golden = A·B" — the same output-carried verdict 0210 used, which also catches silent
   wrap/overlap that a rejection-only observable cannot see. Vehicle: mm_probe (0210's vehicle
   evolved: explicit A/B L1 byte offsets, bias path OFF, dtype switch). The swept tenant is B
   (K=256, baseK=16, footprint = 512·N bytes, N in 16-entry steps ⇒ 8 KiB granularity), the
   fixed tenant A is 8 KiB; a 64 B-granular slide of B's END (fixed 516096 B footprint, offsets
   7936/8128/8192/8256 ⇒ ends 524032/524224/524288/524352) localises the address ceiling below
   the 8 KiB step, including the −256-style reservation hypothesis the 2201 family raised.
4. Arm C instantiated: A = 256 KiB (M=64, K=2048) at offset 0, B adjacent at 262144; accepted
   TOTAL (A+B end) compared against Arm B's single-tenant figure — 524288-exact expected to
   pass, 589824 expected to fail if L1 is the binding constraint.
5. §5 blinding instantiated: int8 build at the SAME byte ends (int8 K=512 vs bf16 K=256, same
   N, same offsets) — element count doubles, byte boundary must not move; the int8 lane carries
   its own poison case (golden shifted by 7) so the checker's red is shown on both dtypes.

## 5 · Checker — acceptance declared before the run
Verdict variable `l1_bytes`, taken from Arm B's largest accepted footprint — not from Arm A. Arm A
can only show the API agrees with the ini, and both origins here are ini-derived, so Arm A cannot
discriminate; only a boundary can.

Pass is declared now as `l1_bytes == 524288`. Two alternatives are named now so neither can be
reinterpreted afterwards: `l1_bytes == 1048576` overturns this entry and means npu-arch and the
whole 950 ini set carry a common error; any value strictly between 0 and 524288 does *not* overturn
it but corrects it in place to distinguish physical capacity from user-available residency, with the
reservation size logged.

Arm A is red if `l0a != 65536` regardless of what `l1` reads — the control failing voids the reading
it exists to protect.

The blinding test, declared before the run: rerun Arm B with the operand dtype changed from fp16 to
int8. The accepted `baseK × baseM` element count must double while the byte figure stays put. If the
element count does not move, the sweep is not bounded by L1 bytes at all and every value it produced
is void. That is the input that makes this checker go red on a known answer — without it, it reads
only "the sweep stopped somewhere", which is the known blind species.

Process exit codes are not the verdict for any arm: a launch that faults because an oversized plan
was *accepted* exits non-zero for the opposite of the reason a rejection would.

## 6 · Evidence
Run 2026-08-24, 950PR, CANN 9.1.0 ts 20260730_231653901, driver 25.7.rc1; card
idle before/after every case; untimed correctness runs.

**Arm A (interface, same-day one-process probe, ledger):** l1=524288, l0a=65536 (control green),
l0c=262144, soc=Ascend950PR_9579.

**Arm B (single-tenant boundary; A fixed at 8192 B; verdict = refusal OR wrong columns):**

| B tenant footprint | B ends at byte | result |
|---|---|---|
| 262144 @8192 | 270336 | granted, output clean (max err 0.002 ≈ bf16 rounding) |
| 516096 @8192 | 524288 | granted, clean |
| 507904 @16128 / @16320 / @16384 | 524032 / 524224 / 524288 | granted, clean — 64 B slide |
| 507904 @16448 | **524352** | **REFUSED**, stream-sync error 507015 |
| 524288 @8192 | 532480 | **REFUSED**, 507015 |

The enforced ceiling is **524288 exactly** (64 B granularity): every end at or below it passes,
the first end 64 B above it is refused. No reservation below the ini value — the correction
branch §5 held ready ("a boundary below 524288 locates the reservation") did not fire.

**Arm C (double tenant):** A = 262144 B (M=64, K=2048) at 0 + B = 262144 B adjacent — total
exactly 524288 — granted with **bit-exact** output; B grown to 327680 (total 589824) refused.
The two-tenant total equals the single-tenant ceiling, not twice it: L1 bytes are the binding
constraint, as §4 Arm C requires.

**Blinding (§5, declared before the run):** int8 at the SAME byte ends (K=512 int8 vs K=256
bf16, same N=1008, same offsets — element count doubled): end 524288 granted exact, end 532480
refused. The byte boundary did not move.

**Checker bleeds:** int8 poison (golden shifted by 7) FAILED 64/64 as required; the bf16 lane's
wrap fixtures (L0-lane far cases) FAIL under the magnitude-aware verifier (the first, fixed-
threshold verifier was voided and rewritten before any §5 reading — self-report in
harvest/RUNS_20260824.md). An accidental fixture confirmed sensitivity: two slide cases from a
first, flawed geometry overlapped the tenants by 256 B and 64 B — the verifier flagged
1008/1008 and 993/1008 columns wrong at small error magnitudes (~2–7), exactly the subtle-
corruption regime a rejection-only observable cannot see; those two cases were discarded as
ceiling readings and the geometry corrected (non-overlapping offsets) before the verdict run.

**Refusal code:** 507015, the same code BT (0210) and L0A/L0B (0213) overflows produce —
consistent with a generic bounds refusal; official semantics not established.

## 7 · Scope limits — what this entry does NOT establish
One die of one 950PR SKU under one pin; 950DT is ini-enumerated only, nothing run. The "no
reservation" finding is at 64 B granularity for the layouts run (two ND/ZN-formatted matmul
tenants, MTE2-filled, single L1 pass): it does not establish that every framework path leaves
the full 524288 usable — bias staging (0210's recipe parks fp32 bias at the L1 end), the
DAV_3510 UB→L1 path (0225), and multi-buffer pipelines each occupy L1 by their own conventions;
what died is only the idea of a HARDWARE/runtime reservation below the ini value. The negative
claim in the slug ("did not grow with L0C") remains an observation about two independent
constants, not a causal statement, and cross-family comparison columns stay upstream's framing
(RULES.md Art. 1). Nothing about L1 bandwidth, the adjacent `l1_to_l0_a_rate` / `l1_to_ub_rate`
fields, or Cube/Vector sharing of L1 under mixed launches. Above-boundary behaviour was probed
at refusal points only in this lane (no far/wrap case was run against L1 — the wrap-vs-refusal
crossover characterised on L0A/L0B in 0213 §6 is not established for L1). Error 507015's
official semantics are not established.
