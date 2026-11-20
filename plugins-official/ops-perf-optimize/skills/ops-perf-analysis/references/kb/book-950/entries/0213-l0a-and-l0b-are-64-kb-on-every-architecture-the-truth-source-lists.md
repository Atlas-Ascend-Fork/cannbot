```
ID:        0213-l0a-and-l0b-are-64-kb-on-every-architecture-the-truth-source-lists
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 950PR 2026-08-24, §5 PASS branch: l0a_bytes = 65536 AND
           l0b_bytes = 65536, each from its own decoupled sweep (65536 granted bit-exact /
           66048 refused, both buffers, both dtypes). Blinding green: int8 doubles the element
           count at an unmoved byte boundary. Arm C (cross-SKU) BLOCKED by fleet — scope note
           in §7. Readouts in §6.
BOARD:     950PR (narrowed at promotion per §4; 950DT remains ini-enumerated only, see §7)
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:33-39 — "## 1. 跨架构一致参数 … | L0A |
           `[AICoreSpec] l0_a_size` | 64 KB (65536) | … > **注意**：即便以上参数通常一致，代码中仍应
           通过 `GetCoreMemSize` 获取，避免硬编码。"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — all 32 `NpuArch=3510` files carry
           `l0_a_size=65536` and `l0_b_size=65536`.
INDEX:     950PR (SoC Ascend950PR_9579), AIC 28, CANN 9.1.0
           ts 20260730_231653901, driver 25.7.rc1, 2026-08-24; untimed correctness runs, card
           idle before/after every case.
           Re-derive interface: GetCoreMemSize(L0_A/L0_B/L0_C) one process → 65536/65536/262144
           (harvest/RUNS_20260824.md interface table; the l0c==l0a red-guard does not fire).
           Re-derive boundary: mm_probe (0210's vehicle evolved; upstream blaze matmul_custom +
           hand tiling), single L0 pass (baseK=K); A_L0 = 32·M bytes swept via M at K=16, N=16;
           B_L0 = 32·N via N at M=16, K=16; verdict carried by output vs golden = A·B
           (magnitude-aware threshold), poison and wrap fixtures shown red.
           Re-derive ini: grep -h '^l0_[ab]_size=' over NpuArch=3510 platform_config files.
OVERTURN:  on this part and pin: either enumerator returning anything but 65536; a single-pass
           operand install with end beyond 65536 B in either buffer succeeding with every
           column correct; or one at or below 65536 B failing under this §4's geometry. On
           other parts (950DT included) a diverging result narrows scope, it does not overturn.
```

# 0213 · L0A and L0B are 64 KB on every architecture the truth source lists

## 1 · Claim
Upstream asserts that L0A and L0B — the Cube unit's left and right operand buffers, the MTE1 landing
zone — are 64 KB (65536 B) each, and files them under 跨架构一致参数, parameters that hold across
*all* verified Ascend architectures rather than per-generation. Upstream attaches its own caveat in
the same breath: even for these, code should call `GetCoreMemSize` rather than hardcode. The
installed CANN 9.0.0-beta.2 set carries `l0_a_size=65536` and `l0_b_size=65536` in all 32
`NpuArch=3510` files.

**As run 2026-08-24 on 950PR (the claim is UPHELD for the measured part):** both enumerators
return 65536; both boundaries sit at 65536 B exactly (granted bit-exact at 65536, refused at
66048, in bf16 AND int8 — the dtype swap doubling elements without moving the byte boundary);
measured separately per buffer, found equal. The cross-architecture half of upstream's claim
remains out of reach (one SKU in the fleet — §7). Readouts in §6.

## 2 · The wrong branch this removes
The interesting wrong branch is not "the agent gets 64 KB wrong". It is that this is upstream's own
example of a cross-architecture invariant, and an invariant is exactly what an agent will hardcode.
Upstream anticipated that and forbade it in the adjacent sentence — which is the placement worth
imitating: the rule sits inside the table that tempts you, not in a preamble.

Concretely, `l0_a_size` together with `baseK` and dtype width sets the K-direction step of a Cube
tile. An agent that hardcodes 65536 is right today and has written a constant that no longer tracks
a cut SKU or a vNPU slice (0207); an agent that assumes L0A scales with L0C — which *did* change on
DAV_3510 (0211) — oversizes the operand step and the tiling is rejected or refills MTE1 more often
than it reports.

The second branch is asymmetry: L0A and L0B are separate fields and nothing guarantees they stay
equal on a future part. Code that reads one and uses it for both is correct on every architecture in
this install and carries an unstated assumption.

## 3 · Ground / Source
`npu-hardware-params.md:29-39`, §1 in full — this is the whole of upstream's cross-architecture
invariant set, which is worth seeing because it is only three rows:

> ## 1. 跨架构一致参数
> 以下参数在所有已验证的 Ascend NPU 架构上保持一致：
>
> | 参数 | INI 字段 | 值 | 说明 |
> |------|---------|:---:|------|
> | L0A | `[AICoreSpec] l0_a_size` | 64 KB (65536) | Cube 左矩阵操作数 |
> | L0B | `[AICoreSpec] l0_b_size` | 64 KB (65536) | Cube 右矩阵操作数 |
> | Cube MAC 阵列 | `cube_m_size / cube_k_size / cube_n_size` | 16×16×16 | 一个周期完成 4096 次 MAC |
>
> > **注意**：即便以上参数通常一致，代码中仍应通过 `GetCoreMemSize` 获取，避免硬编码。

Note the hedge upstream builds into its own heading: 所有**已验证的** architectures — verified ones,
not all architectures. Combined with 0205 (a `NpuArch=3505` ini ships in the same directory with
`l0_a_size=0`), that hedge is load-bearing rather than decorative: the invariant is over the set
upstream lists, and this install contains an ini outside that set which breaks it.

The quick table at `npu-arch-guide.md:154` restates it as `| L0A/B 64KB | ✓ | ✓ | ✓ | ✓ | ✓ |`, and
`:178-179` gives the per-core figures for 950PR. Same skill, one origin (RULES.md Art. 3).

Second origin — the installed toolkit, read under the phase-1 read-only exception. From
`Ascend950PR_9589.ini`:

```
[AICoreSpec]
l0_a_size=65536
l0_b_size=65536
l0_c_size=262144
```

Both fields equal 65536 in all 32 `NpuArch=3510` files, across every core count (4/8/28/32/36) and
every L2 size present. `Ascend035.ini` (`NpuArch=3505`, 0205) carries `l0_a_size=0` and
`l0_b_size=0` — outside upstream's verified set, and quoted here because it is the counterexample
that shows the invariant is scoped rather than universal.

No upstream document contradicts the 64 KB figure; L0A/L0B carry no C-row.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion.

Arm A — query both, separately, and never one for the other:

```cpp
auto plat = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
uint64_t l0a = 0, l0b = 0, l0c = 0;
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_A, l0a);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_B, l0b);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_C, l0c);
std::printf("l0a=%llu l0b=%llu l0c=%llu soc=%s\n", (unsigned long long)l0a,
            (unsigned long long)l0b, (unsigned long long)l0c, /* resolved SoC string */);
```

L0C is printed as a differential control: it is 256 KB on this architecture (0211), so a probe
returning 65536 for all three is reporting a default, not a reading. The resolved SoC string is
printed so the values can be matched against the ini the runtime actually chose (0204 §4 Step 3).

Arm B — the boundary, which establishes usable operand capacity rather than a reported number.
Sweep `baseM × baseK × sizeof(T)` upward at fixed `baseN` until host tiling rejects the plan, and
record the largest accepted and smallest rejected. Repeat with the B operand (`baseK × baseN`) at
fixed `baseM`. Two sweeps, not one: the point is to locate each buffer independently, because the
asymmetry branch in §2 is only visible if they are measured apart.

Arm C — the invariance arm, and the only one that touches upstream's actual claim. Upstream says
64 KB holds across architectures; this book may not inherit a cross-family conclusion (RULES.md Art. 1),
so within book-950 the strongest available check is across *SKUs*: run Arm A on a 28-core part and a
32-core part and, if available, a 36-core part, and require the same value. A family claim needs the
family's ends; a single 950PR reading establishes 950PR.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another.

**As-run instantiation notes (2026-08-24, recorded before the verdict was read):**
1. Fleet has no 950DT; BOARD narrows to 950PR at promotion. **Arm C is BLOCKED by the fleet**:
   one 950 configuration is installed (28-core 950PR_9579), so cross-SKU invariance cannot be
   run here — recorded as a scope narrowing, not skipped silently. §5's verdicts are Arm B's
   and are unaffected.
2. Arm A is satisfied by the same-day all-CoreMemType probe (one process, SoC printed):
   l0a=65536, l0b=65536, l0c=262144 — the l0c==l0a red-guard does not fire (factor of four
   apart, as 0211 requires) (harvest/RUNS_20260824.md interface table).
3. Arm B instantiated: "host tiling rejects" becomes "device/runtime refuses OR output columns
   go wrong against golden" (no host engine in the hand-tiled vehicle; the output-carried
   verdict also catches silent wrap). Two decoupled sweeps, single L0 pass (baseK = K, so the
   full 64 KiB is addressable without ping-pong halving): A_L0 = 32·M bytes grown via M at
   K=16, N=16 (B_L0 stays 512 B); B_L0 = 32·N bytes grown via N at M=16, K=16 (A_L0 stays
   512 B). Boundary bracketed at {65536 at, 66048 beyond, 131072 far}; 512 B granularity
   available if the bracket lands off the ini value.
4. §5 blinding instantiated: int8 build (cube granularity 32, so baseK=32) at the same byte
   arithmetic (A_L0 = 32·M, B_L0 = 32·N) — element count per buffer doubles at equal bytes;
   the bf16 lane carries a poison case (golden shifted by 64) showing the checker's red.

## 5 · Checker — acceptance declared before the run
Two verdict variables, never merged: `l0a_bytes` and `l0b_bytes`, each taken from its own Arm B
sweep. Merging them would make the asymmetry in §2 unobservable by construction, which is exactly
the failure this entry is about.

Pass is declared now as `l0a_bytes == 65536 && l0b_bytes == 65536`. A case where the two differ does
not fail the checker — it corrects the entry in place and is logged, because a real asymmetry is a
more valuable finding than a confirmation. Any value other than 65536 for either overturns the
corresponding half.

Arm A is red if `l0c == l0a` — on this architecture those must differ by a factor of four (0211),
and equality means the enumerators are not being distinguished. That clause is the guard against a
probe that returns the same default for every `CoreMemType` and reads as three agreeing successes.

The blinding test, declared before the run: rerun Arm B with the operand dtype changed from fp16 to
int8. The accepted element count must double while the byte boundary stays put. If the element count
does not move, the sweep is not bounded by L0A/L0B bytes and every value it produced is void. Without
this, the checker only reads "the sweep stopped somewhere" — the known blind species.

Process exit code is not the verdict for any arm.

## 6 · Evidence
Run 2026-08-24, 950PR, CANN 9.1.0 ts 20260730_231653901, driver 25.7.rc1; card
idle before/after every case; untimed correctness runs.

**Arm A (interface, same-day one-process probe, ledger):** l0a=65536, l0b=65536, l0c=262144,
soc=Ascend950PR_9579 — the l0c==l0a red-guard does not fire (factor of four, as 0211 requires).

**Arm B (two decoupled sweeps; verdict = refusal OR wrong output columns):**

| buffer | install (bytes) | dtype (elements) | result |
|---|---|---|---|
| L0A | 32768 | bf16 (16384) | granted, output bit-exact |
| L0A | 65536 | bf16 (32768) | granted, output bit-exact |
| L0A | 65536 | int8 (65536) | granted, output exact |
| L0A | 66048 | bf16 AND int8 | **REFUSED**, stream-sync error 507015 |
| L0A | 131072 | bf16 | granted, output CORRUPT (max err 6.4 ≫ rounding) — silent wrap |
| L0B | 32768 / 65536 | bf16 | granted, bit-exact |
| L0B | 65536 | int8 (65536 elements) | granted, exact |
| L0B | 66048 | bf16 AND int8 | **REFUSED**, 507015 |
| L0B | 131072 | bf16 | granted, output CORRUPT (max err 5.6) — silent wrap |

`l0a_bytes` = `l0b_bytes` = **65536** (largest success 65536, smallest fail 66048, 512 B-step
granularity available, 16-entry steps used). The declared asymmetry case did not occur — measured
separately, found equal.

**Blinding (§5, declared before the run):** int8 (cube granularity 32) doubles the element count
at the same byte arithmetic — the byte boundary did not move (65536 granted / 66048 refused in
both dtypes). The sweeps are bounded by bytes.

**Checker bleeds:** the poison case (golden shifted by 64) FAILED as required. Additionally, the
first verifier shipped with a fixed |err|>8 threshold transplanted from the bias lane and called
the 131072-B wrap cases PASS (max err 6.4 at values ≤16 — corruption under the threshold); it
was voided and rewritten magnitude-aware BEFORE any §5 reading (self-report in
harvest/RUNS_20260824.md), and the wrap cases were re-run as the fixed verifier's POSITIVE
fixtures: now FAIL 16/16 and 4096/4096.

**Enforcement is non-uniform above the boundary:** one step beyond (66048) is refused with
507015 — the same code BT (0210) and L1 (0212 lane) overflows produce, so it reads as a generic
bounds refusal — but 2× the capacity (131072) is GRANTED and wraps silently. A rejection-only
observable would mis-read the far case as "fits"; the output-carried verdict is what catches it.

## 7 · Scope limits — what this entry does NOT establish
One die of one 950PR SKU under one pin. **Arm C (cross-SKU invariance) is BLOCKED by the fleet**
— one 950 configuration installed — so upstream's cross-architecture claim stays unestablished:
within book-950 this run establishes 950PR_9579 and nothing about 950DT or other core counts
(their ini values are enumerated, all 65536, not run). Upstream's own heading hedges to 已验证的
architectures, and 0205 records an ini in the same install (`NpuArch=3505`, `l0_a_size=0`)
outside that set; "every architecture" in this slug means every architecture *the truth source
lists*. The boundary is for a SINGLE full-buffer install in a single L0 pass: ping-pong halves,
multi-slice accumulation, and MTE1 staging overhead were not separated. Above-boundary behaviour
is characterised only at two points (66048 refused; 131072 granted-and-wrapped) — the crossover
between refusal and silent wrap, and its mechanism, are not established; error 507015's official
semantics are likewise not established (observed here and on BT/L1 overflows). Wrap-corruption
magnitudes (6.4/5.6 at |values|≤16) are readouts of this geometry, not a model of the wrap.
Nothing about L0A/L0B bandwidth or the adjacent `l1_to_l0_[ab]_rate` fields. The asymmetry
question is settled only for this part and pin — the two buffers were measured separately and
found equal here, which does not license reading one for both elsewhere.
