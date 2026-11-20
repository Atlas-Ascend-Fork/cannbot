```
ID:        0210-bt-on-dav-3510-is-4-kb-not-the-1-kb-a-neighbour-skill-states
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 950PR 2026-08-24, §5 PASS branch: bt_bytes = 4096 (Arm B largest
           success 4096 B, smallest fail 4160 B, 64 B granularity; refusal, not wrap). Both §5
           guards closed: Arm B confirms 4096 independently of the bt==fb value collision, and
           the install boundary moves by exactly a 2048 B offset. Readouts in §6.
BOARD:     950PR (narrowed at promotion per §4; 950DT remains ini-enumerated only, see §7)
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:111 — "| BT | `bt_size` | 4 KB (4096) |"
           (§2.5 DAV_3510); :151 速查表 row "BT | — | — | 1 KB | 1 KB | **4 KB**"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` (`innerversion=V100R001C10SPC001B214`) —
           all 32 `NpuArch=3510` files in `aarch64-linux/data/platform_config/` carry
           `bt_size=4096`; `Ascend950PR_9589.ini` additionally `fb0_size=4096`, `fb1_size=2048`.
INDEX:     950PR (SoC Ascend950PR_9579), AIC 28, CANN 9.1.0
           ts 20260730_231653901, driver 25.7.rc1, 2026-08-24; untimed correctness runs
           (curFreq at the 100 MHz idle floor), card idle before/after every case, no co-tenant.
           Re-derive interface: GetCoreMemSize(BT) and GetCoreMemSize(FB) printed separately in
           one probe → 4096 / 4096, SoC string alongside (harvest/RUNS_20260824.md).
           Re-derive ini: enumerate bt_size over every NpuArch=3510 file in
           <toolkit>/x86_64-linux/data/platform_config → 36/36 carry 4096.
           Re-derive boundary: upstream blaze matmul_custom example + matmul_basic.md §2.2 bias
           recipe, single core / single block (baseM=16, baseN=n, baseK=K=16, bf16 in/out,
           hand-filled tiling), bias[j]=j fp32, golden = A·B + bias, per-column threshold 32;
           case matrix {n=512, 1024, 1040} at offset 0 and {n=512, 528} at offset 2048.
           Re-derive software tier: ASC_BT_SIZE per __NPU_ARCH__ in
           asc/include/utils/base/sys_constants.h.
OVERTURN:  on this part and pin: `GetCoreMemSize(BT)` returning anything other than 4096; a
           single install with end beyond 4096 B succeeding with every column correct; an install
           with end at or below 4096 B being refused or producing wrong columns under this §4's
           geometry; or the offset guard failing to move the boundary by exactly the offset. On
           other parts (950DT included) a diverging result narrows scope, it does not overturn.
```

# 0210 · BT on DAV_3510 is 4 KB, not the 1 KB a neighbour skill states

## 1 · Claim
Upstream asserts that the DAV_3510 BT (bias table / FixPipe bias buffer) is 4 KB (4096 B), read
from the ini field `bt_size`, and that this is a fourfold increase over the previous generation. The
installed CANN 9.0.0-beta.2 platform-config set carries `bt_size=4096` in all 32 of its
`NpuArch=3510` files. A different upstream skill states 1 KB for the same chip.

**As run 2026-08-24 on 950PR (the claim is UPHELD):** `GetCoreMemSize(BT)` returns 4096 (FB
queried separately in the same probe, also 4096 — the collision §3 warned about, which is why
the verdict is Arm B's, not Arm A's); the usable single-install boundary is **4096 B exactly**
(4096 granted with every output column bit-exact, 4160 refused); and the bound 9.1.0 ini set
carries `bt_size=4096` in 36 of 36 NpuArch=3510 files. Readouts in §6.

This is contradiction **C-002** in `harvest/CONTRADICTIONS.md` — now resolved for the measured
part: BT is 4 KB on 950PR; `metrics_reference.md`'s 1 KB (line 123, pointer corrected in C-002) is measured-wrong there. Before the
run the disagreement was one-sided but undecided — a second document is not a run.

## 2 · The wrong branch this removes
BT sizes the FixPipe bias table, so it caps how many output channels a Cube tile can carry bias for
in one pass. An agent holding 1 KB splits N four times more finely than it needs to: every split
costs a FixPipe reconfiguration and an extra L0C drain, and the kernel is correct throughout. There
is no error and no obviously wrong number in the profile — just more, smaller Cube tiles than the
hardware requires.

The reverse — believing 4 KB where 1 KB is true — would fault or truncate bias, which is loud. So
the asymmetry matters: the *conservative* reading is the silent one, and an agent that resolves a
1-vs-4 disagreement by taking the smaller value has chosen the failure mode nothing will report.

## 3 · Ground / Source
`npu-hardware-params.md:103-114` (§2.5, DAV_3510) lists `| BT | bt_size | 4 KB (4096) |`, and the
cross-architecture quick table at `:142-154` puts it in context:

> | 特征 | DAV_1001 | DAV_2002 | DAV_2201 | DAV_3002 | DAV_3510 |
> | BT | — | — | 1 KB | 1 KB | **4 KB** |

`SKILL.md:42-44` repeats it as one of three headline buffer deltas. The same document, `:118`,
defines the neighbouring FB fields and their accessor:

> **FB（Fix Buffer）**：FixPipe 量化 scale 存储区。INI 字段 `fb0_size` / `fb1_size` / `fb2_size` /
> `fb3_size`；`GetCoreMemSize(FB)` 返回 `fb0_size`。

The contradicting statement is `ascendc-performance-analysis/references/metrics_reference.md:117`,
which gives 950 BT = **1 KB**. Neither document cites the other. npu-arch declares itself the 真源
and declares reverse self-reference by a downstream skill a risk
(`npu-arch-guide.md:74`) — but a declaration of authority is not evidence, and Art. 7 forbids
resolving this by deciding which author is more plausible.

What does move it is the second origin. In this machine's installed toolkit, `Ascend950PR_9589.ini`
carries verbatim:

```
[AICoreSpec]
fb0_size=4096
fb1_size=2048
fb2_size=0
fb3_size=0
bt_size=4096
```

and the same `bt_size=4096` appears in every one of the 32 `NpuArch=3510` files, invariant across
all core counts (4/8/28/32/36) and all L2 sizes present. No 3510 ini in this install carries
`bt_size=1024`.

Note the value collision worth guarding against: `fb0_size` is also 4096, and `GetCoreMemSize(FB)`
returns `fb0_size` while `GetCoreMemSize(BT)` returns `bt_size`. On DAV_3510 those two happen to be
equal, so a probe that queried the wrong enumerator would get the right number for the wrong reason
— and would then be wrong on any part where they diverge. §4 guards this explicitly.

## 4 · Procedure
Runnable later on `950PR`; `950DT` requires its own run and this entry's BOARD is narrowed at
promotion to whichever ran.

Arm A — query both enumerators in one probe and print them separately:

```cpp
auto plat = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
uint64_t btSize = 0, fbSize = 0;
plat.GetCoreMemSize(platform_ascendc::CoreMemType::BT, btSize);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::FB, fbSize);
std::printf("bt=%llu fb=%llu soc=%s\n", (unsigned long long)btSize,
            (unsigned long long)fbSize, /* resolved SoC string */);
```

Printing both is not decoration: it is the only way to show the BT reading was not an FB reading.
The resolved SoC string is printed so the value can be matched against the ini the runtime actually
chose (0204 §4 Step 3).

Arm B — the boundary, which is what establishes usable capacity rather than a reported number. Build
a Cube kernel that installs a bias table of `n` fp32 entries through FixPipe and increase `n` until
the build or the launch refuses. Record the largest `n` that succeeds and the smallest that fails.
At 4 bytes per entry, 1 KB is 256 entries and 4 KB is 1024, so the two hypotheses are separated by a
factor of four and the bisection cannot land ambiguously between them.

Arm C — the discriminating negative. Install a bias table of exactly 1024 entries (4 KB). Under
npu-arch's claim this succeeds; under `metrics_reference.md`'s claim it must fail. This is the arm
that makes C-002 decidable in one observation, and it is run *before* Arm B's full bisection so a
clear answer is available even if the bisection is cut short.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another at any point.

**As-run instantiation notes (2026-08-24, recorded before the promoting run):**
1. Fleet has no 950DT; BOARD narrows to 950PR at promotion, as this §4 already provides.
2. Mechanism, instantiated for this pin (CANN 9.1.0, in-toolkit tensor_api): the table is
   installed by `CopyL12BT` (L1→BT; destination statically pinned to `Location::BIAS`,
   `impl/tensor_api/arch/cube/l1_to_bt/copy.h:53-55`) and consumed by the 5-arg `Mmad`
   overload — hardware C-matrix init from the bias table (`cmatrixSource`; the BT byte address
   is encoded per-mmad into the destination operand's high 32 bits,
   `mmad_impl/instruction.h`). FixPipe performs only the L0C→GM writeback. This §4's phrase
   "installs ... through FixPipe" is instantiated as "installs into BT through the Cube bias
   path"; what is under test — BT capacity — is unchanged.
3. Vehicle: upstream's own blaze `matmul_custom` example plus the bias recipe of
   `matmul_basic.md` §2.2, single core / single block with hand-filled tiling (baseM=16,
   baseN=n, baseK=16, K=16), so the whole table is ONE `CopyL12BT` install of n fp32 entries;
   upstream's SWAT tiling engine formulates 256-wide basic blocks and is bypassed. As shipped
   the example does not compile on this pin (`FixpipeParams` fails `IsCopyQuantParamV`; ledger
   row 2026-08-24); the writeback uses explicit `M_FIX` events + 3-arg `Copy`, and mmad unit
   flags are disabled to match the pin's default-off handshake.
4. Arm C observable STRENGTHENED against silent truncation: bias[j] = j (fp32), golden =
   A·B + bias, per-column verdict with threshold |err| > 32 (bf16 rounding ≤ ~8 at |value|≈1000;
   a wrapped or garbage bias shifts a column by ≥ 256). "Succeeds" = all n columns within
   threshold; "fails" = launch/sync refusal OR wrong columns. The first wrong column, if any,
   localises the capacity: 256 ⇒ 1 KB, 512 ⇒ 2 KB, none at 1024 entries ⇒ ≥ 4 KB.
   Verifier's poison fixture: golden computed WITHOUT bias must FAIL verification.
5. Arm B granularity: 16-entry (64 B) steps — n must be a multiple of 16 for the cube geometry;
   the competing hypotheses are 4× apart, so 64 B steps are decisive. Instrument reach: the
   single-install geometry tops out at 2048 entries (8192 B, L0B/L0C bound) — a boundary above
   that is recorded as "≥ 8192 B, beyond this instrument", not as a value. §5's
   boundary-must-move guard is instantiated as: repeat the bisection with the install at BT
   byte offset 2048; the largest surviving n must drop by exactly 512 entries.

## 5 · Checker — acceptance declared before the run
Verdict variable `bt_bytes`, taken from Arm B's largest success — not from Arm A. Arm A can only
show the API agrees with the ini, and the two documents on the 4 KB side already agree, so Arm A
cannot discriminate between the hypotheses; only a boundary can.

Pass is declared now as `bt_bytes == 4096`. The alternative is declared now too, so it cannot be
reinterpreted afterwards: `bt_bytes == 1024` overturns this entry, vindicates
`metrics_reference.md:117`, and demotes the npu-arch/ini pair to two documents carrying one error.
Any third value corrects the entry in place and is logged.

Two named guards, because this checker has two ways to be blind. First, Arm A is red — not green —
if `bt == fb`, *unless* Arm B independently confirms 4096; equal values are the case where a
mis-enumerated query is indistinguishable from a correct one. Second, the bisection must be shown to
move: rerun Arm B with the bias table deliberately double-buffered, and the boundary must halve. If
the boundary does not move, the bisection is not measuring BT allocation at all and every reading
from it is void. That is the positive fixture — the checker must be seen going red on an input whose
answer is known — not a formality.

Process exit code is not the verdict: a probe that faults because the oversized table *was* accepted
exits non-zero for the opposite of the reason a failure would.

## 6 · Evidence
Run 2026-08-24, 950PR, CANN 9.1.0 ts 20260730_231653901, driver 25.7.rc1;
card idle (no processes, NPU-Util 0 %) before and after every case; untimed correctness runs.

**Arm A (interface, run earlier the same day, ledger):** `bt=4096 fb=4096 soc=Ascend950PR_9579`,
both enumerators in one probe, printed separately. Per §5 this alone is RED (bt == fb); it turns
green only through Arm B below.

**Arm C (the discriminating observation):** one `CopyL12BT` install of 1024 fp32 entries
(4096 B), consumed by mmad across all 1024 output columns:

```
geometry: M=16 K=16 N=1024 ... bt_install_bytes=4096 bt_byte_offset=0
[verify] shape=(16,1024)  max_abs_err=0.0000  wrong_cols(|err|>32)=0/1024   [PASS]
```

Under npu-arch's 4 KB claim this had to succeed; under `metrics_reference.md`'s 1 KB claim (line 123; C-002
carries the pointer correction from :117) it had to fail. It succeeded **bit-exactly** — every band 0.0000, including columns 256–1023, which
a 1 KB (or 2 KB) table cannot serve unwrapped.

**Poison fixture (checker bleeds):** same run with golden computed WITHOUT bias:
`wrong_cols=992/1024`, first wrong column 32 (bias[j]=j puts columns 0–31 below the 32.0
threshold — the arithmetic the fixture predicts), band maxima 255.8 / 511.9 / 1024.3. FAIL as
required.

**Arm B (boundary, 64 B granularity, with the §5 move-guard):**

| install | BT byte offset | span ends at | result |
|---|---|---|---|
| 512 entries (2048 B) | 0 | 2048 | granted, 0/512 wrong (bit-exact) |
| 1024 entries (4096 B) | 0 | 4096 | granted, 0/1024 wrong (bit-exact) |
| 1040 entries (4160 B) | 0 | 4160 | **REFUSED**, stream sync error 507015 |
| 512 entries (2048 B) | 2048 | 4096 | granted, 0/512 wrong (bit-exact) |
| 528 entries (2112 B) | 2048 | 4160 | **REFUSED**, stream sync error 507015 |

`bt_bytes` = largest success = **4096**; smallest fail 4160. The boundary sits at install-END =
4096 B regardless of offset — the offset guard moved the largest surviving install by exactly
the offset (1024 → 512 entries), so the instrument measures BT allocation, not something else.
Failure mode is an explicit runtime refusal (507015), not silent wrap; the upper probe (2048
entries = 8192 B at offset 0) was refused with the same code. Consumption at offset 2048 works —
the mmad bias addressing honours the offset (bias entries land on the correct columns).

**INI arm, bound pin:** all 36 `NpuArch=3510` files in `x86_64-linux/data/platform_config`
carry `bt_size=4096` — the 27 `Ascend950DT_*`, 9 `Ascend950PR_*`, and 2 `Ascend350_*` files
alike (the count is per-file enumeration; an earlier `Ascend950*`-glob count of 34 is the same
data with narrower scope, self-reported in the ledger). §3's CANN 9.0.0-beta.2 enumeration
(32 files, aarch64) stands as harvested.

**Software-constant tier (a fourth tier, found during this run):**
`asc/include/utils/base/sys_constants.h` gates `ASC_BT_SIZE` per `__NPU_ARCH__`:
0 for 1001/2002, **1 KB for 2201/3002/3003/3113**, **4 KB for 3510**. The same table carries
`ASC_UB_SIZE = 248*1024` exact for 3510 and `192*1024 − 256` for 2201 — the vendor's own
compile-time constants mirror the per-family API behaviour measured in 0209 and (on the other
book's board) 0003/0004.

**Vehicle compatibility note:** upstream's blaze `matmul_custom` example does not compile as
shipped against this pin's tensor_api (`FixpipeParams` fails `IsCopyQuantParamV`); the writeback
was replaced by explicit M→FIX events + 3-arg `Copy` (ledger row 2026-08-24). This affects the
vehicle, not the quantity under test.

## 7 · Scope limits — what this entry does NOT establish
One die of one 950PR SKU (Ascend950PR_9579) under one pin (CANN 9.1.0 ts 20260730_231653901,
driver 25.7.rc1). **950DT**: ini-enumerated only (27 files, all 4096), nothing run — the ini
invariance makes divergence unlikely but the boundary there is not measured. The boundary is for
a SINGLE install: multi-install accumulation, fragmentation, and whether concurrent ping-pong
halves interact were not probed (upstream's own double-buffer recipe splits the 4 KB in half).
Granularity is 64 B — a boundary offset inside (4096, 4160) finer than 64 B is not excluded, and
alignment constraints below 64 B were not probed. Error 507015 is the observed refusal code; its
official semantics are not established, and whether refusal happens at the copy or at launch
validation is not separated. Consumption ran through the mmad bias path (`cmatrixSource`); a
FixPipe-side bias application, if this pin has one, was not exercised. The classic-API
`TPosition::C2`/`InitBuffer` route was not used — this entry says nothing about TPipe-level BT
budgeting. `fb1/fb2/fb3` consumers remain unestablished; FB was queried only to guard the value
collision. The compile-time `ASC_BT_SIZE` table was read on this machine's x86_64 toolkit; its
2201-family rows must be re-derived on a 2201 machine's toolkit before any use in the other book
(RULES.md Art. 1 — nothing here establishes BT on any 910 board; the 1 KB quick-table entries for
2201/3002 are upstream text plus a software constant, still not a measurement on those parts).
