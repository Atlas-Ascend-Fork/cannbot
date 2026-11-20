```
ID:        0220-low-precision-cube-dtypes-widen-the-mac-array-rather-than-adding-cores
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — ops/npu-arch derives the figures from `[DtypeMKN]`; the installed CANN
           9.0.0-beta.2 ini carries that section with the same K values. Both trace to vendor ini
           (0204); no MMAD was issued.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:125-145 — "不同于 FP16/BF16 使用
           `cube_m/n/k_size=16×16×16=4096`，FP8_E4M3FN 的 Cube MAC 阵列更大（INI `[DtypeMKN]` 段）：
           `DT_FLOAT8_E4M3FN = 16,32,16 → M×K×N = 16×32×16 = 8192`" … "MXFP4 按 INT4 的 MKN
           （`DT_INT4=16,64,16`）推导：16384 MAC/周期，2 倍于 FP8。" … "注：HiF8、MXFP8 在 INI 中无独立的
           DtypeMKN 条目，但算力等效于 E4M3FN。"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — `Ascend950PR_9589.ini` `[DtypeMKN]`:
           `Default=16,16,16` · `DT_FLOAT8_E4M3FN=16,32,16` · `DT_INT8=16,32,16` ·
           `DT_INT4=16,64,16` · `DT_INT2=16,128,16` · `DT_UINT1=16,256,16`
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           sed -n '/\[DtypeMKN\]/,/^\[/p' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend950PR_9589.ini
OVERTURN:  an fp8 matmul on 950PR whose measured MACs/cycle/core does not exceed the fp16 rate —
           the array does not widen with dtype and every low-precision TFLOPS figure is wrong.
```

# 0220 · Low-precision Cube dtypes widen the MAC array rather than adding cores

## 1 · Claim
Upstream asserts that the DAV_3510 Cube MAC array is not one fixed shape: the ini section
`[DtypeMKN]` overrides the K dimension per data type, so the per-cycle MAC count scales with
precision rather than staying at the 16×16×16 default (0214). Upstream derives 8192 MACs/cycle for
`DT_FLOAT8_E4M3FN` (16×32×16) and 16384 for `DT_INT4` (16×64×16), and asserts that HiF8 and MXFP8
have no ini row of their own but are equivalent in throughput to E4M3FN, while MXFP4 is derived from
the INT4 row. The installed CANN 9.0.0-beta.2 ini carries the same `[DtypeMKN]` values and extends
the pattern: `DT_INT2=16,128,16` (32768) and `DT_UINT1=16,256,16` (65536). Not established here: no
MMAD was issued and nothing was timed.

## 2 · The wrong branch this removes
An agent that has read `[AICoreSpec]`'s `cube_m_size=cube_n_size=cube_k_size=16` — the fields
upstream files under 跨架构一致参数 — has a single number, 4096, and applies it to every dtype. Two
consequences, opposite in sign.

For fp8 and int8, the roofline denominator is 2× too small, so a kernel at 90 % of the true peak
reports 180 % and the team stops optimising. For int4 it is 4× too small. Nothing about a
"we exceeded peak" reading forces a re-derivation; it reads as a measurement error and gets rounded
to "roughly at peak".

The second, subtler branch is the reason the entry is worded as "widen the array" rather than "fp8 is
faster". The speedup comes from a larger K per cycle, which means the *tiling* consequence is
specific: `baseK` steps in units of the dtype's K, so a tiling routine that steps K by 16 for every
dtype leaves three quarters of an int4 MMAD idle while looking perfectly correct. An agent that knows
only "fp8 is 2× faster" cannot derive that; an agent that knows the array is 16×32×16 can.

Third: the equivalences are *asserted*, not tabulated. HiF8, MXFP8 and MXFP4 have no rows. An agent
that greps `[DtypeMKN]` for `HIF8` finds nothing and must not conclude the format is unsupported —
upstream says it runs at E4M3FN's rate, and that assertion has no ini backing at all.

## 3 · Ground / Source
`npu-arch-guide.md:123-145`, the derivation section in full:

> #### FP8_E4M3FN 算力推导
> 不同于 FP16/BF16 使用 `cube_m/n/k_size=16×16×16=4096`，FP8_E4M3FN 的 Cube MAC 阵列更大
> （INI `[DtypeMKN]` 段）：
> ```
> DT_FLOAT8_E4M3FN = 16,32,16  →  M×K×N = 16×32×16 = 8192
> ```
> 代入公式：
> ```
> 950PR Server:  8192 × 32核 × 1650 MHz × 2(FMA) ÷ 10⁶ = 865 TFLOPS
> 950PR PCIE:    8192 × 28核 × 1650 MHz × 2(FMA) ÷ 10⁶ = 757 TFLOPS
> ```
> FP8 族系（含 HiF8、MXFP8）均视为 8192 MAC/周期。MXFP4 按 INT4 的 MKN（`DT_INT4=16,64,16`）推导：
> 16384 MAC/周期，2 倍于 FP8。
> ```
> 950PR Server:  16384 × 32核 × 1650 MHz × 2(FMA) ÷ 10⁶ = 1730 TFLOPS
> 950PR PCIE:    16384 × 28核 × 1650 MHz × 2(FMA) ÷ 10⁶ = 1514 TFLOPS
> ```
> > 注：HiF8、MXFP8 在 INI 中无独立的 DtypeMKN 条目，但算力等效于 E4M3FN。

The supported-format list at `:337-349` names what the array is being widened *for*: FP8 E5M2 / E4M3,
MXFP8 E5M2/E4M3 ("32 个 Data 共享 1 个 Scale"), MXFP4 E2M1/E1M2, HiF8, alongside the existing
FP16 / BF16 / HF32 / FP32 / S8. The C++ type names are at `:353-358`: `fp8_e5m2_t`,
`fp8_e4m3fn_t`, `hifloat8_t`, and `int4b_t` — with the parenthetical that `int4b_t` is for Vector and
weight storage and is **not** Cube MMAD supported, which is worth noticing because `DT_INT4` *is* a
`[DtypeMKN]` row. Same skill throughout, one origin (RULES.md Art. 3).

Second origin — the installed toolkit, read under the phase-1 read-only exception.
`Ascend950PR_9589.ini`:

```
[DtypeMKN]
Default=16,16,16
DT_FLOAT8_E4M3FN=16,32,16
DT_INT8=16,32,16
DT_UINT8=16,32,16
DT_INT4=16,64,16
DT_INT2=16,128,16
DT_UINT2=16,128,16
DT_UINT1=16,256,16
DT_FLOAT=16,8,16
DT_INT32=16,8,16
```

Upstream's two derivations reproduce exactly. Three things in this block upstream does not mention:
`DT_INT2` / `DT_UINT2` at 16×128×16 = 32768 and `DT_UINT1` at 16×256×16 = 65536, extending the
doubling ladder two rungs further; `DT_UINT8` sharing INT8's row; and the two rows that go the *other*
way, `DT_FLOAT` and `DT_INT32` at 16×8×16 = 2048, which are 0221.

The pattern across the whole section is a single rule — K scales inversely with element width, from
256 at 1 bit to 8 at 32 bits — with `Default` sitting at the 16-bit rung. Stating it as a rule is
inference; the rows are the data.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion.

Arm A — throughput per dtype, the measurement that matters. Build one single-core matmul harness and
instantiate it for fp16, fp8_e4m3fn, int8 and int4 at identical logical M/N/K. Choose shapes so
operands are L1-resident (0212) and the accumulator L0C-resident (0211), so neither MTE2 nor FixPipe
is the limiter and the Cube array is. Take the minimum `aic_time` over 50 repetitions and compute
achieved MACs/cycle = (M·N·K)/(aic_time × cube_freq), with `cube_freq` read from the resolved ini and
printed rather than assumed.

Arm B — the ratios, which is where the claim lives. Report each dtype's rate as a ratio to fp16 on the
same die in the same session. Expected: 1.0 (fp16), 2.0 (fp8, int8), 4.0 (int4). Absolute
MACs/cycle figures are reported too, but the ratio is the verdict variable — a two-point comparison
across dtypes on one build attributes to the dtype; two absolute numbers from two sessions attribute
to nothing.

Arm C — the K-step arm, which tests §2's tiling consequence rather than the headline. For int4, sweep
`baseK` over {16, 32, 64, 128} at fixed M and N and record achieved rate. If the array is 16×64×16, the
rate should plateau at `baseK` = 64 and a `baseK` of 16 should cost roughly 4×. This is the arm that
turns the claim into something a tiling routine can use.

Arm D — the unbacked equivalences, which have no ini row and therefore no second origin. Repeat Arm A
for `hifloat8_t` and for an MXFP8 format, and compare against the fp8_e4m3fn rate. Upstream asserts
equality; nothing in the ini supports it, so this arm is the only evidence that will ever exist for
those two formats.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All dtypes in one ratio comparison run on
one named die in one session.

## 5 · Checker — acceptance declared before the run
Verdict variable `mac_ratio[dtype]`, one per dtype, from Arm B — never an aggregate, because the
dtypes are independent claims and one passing must not cover another failing.

Pass is declared now as: `mac_ratio[fp8] ∈ [1.8, 2.2]`, `mac_ratio[int8] ∈ [1.8, 2.2]`,
`mac_ratio[int4] ∈ [3.6, 4.4]` — ±10 % bands, declared before any readout. A ratio **above** the band
does not pass: it means the array is wider than the ini reports and the entry is corrected upward,
which is a different result from confirmation and must not be recorded as one.

`mac_ratio[fp16] == 1.0` by construction is the normalisation, not a result, and is stated so it is
not mistaken for one.

The blinding test, declared before the run: rerun Arm A for fp8 with `baseK` pinned to 16 instead of
32. The achieved rate must fall to approximately the fp16 rate. If it does not, the harness is not
measuring array occupancy — it is measuring something that does not depend on K — and every ratio it
produced is void. Without this, the checker only reads "one number was about twice another", which is
the known blind species: many unrelated causes produce a factor of two.

Arm D's verdicts are separate and carry no pass band, because upstream's equivalence claim has no
numeric backing to test against; they are reported as ratios to fp8 with their run variance, and a
deviation corrects upstream's assertion rather than this entry's rows.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `[DtypeMKN]` rows in §3
are a read of installed files under the sanctioned phase-1 read-only exception; a configuration
section describes a shape the toolchain believes in and cannot observe a single MAC.

## 7 · Scope limits — what this entry does NOT establish
No device was contacted, no matmul was built, nothing was timed. The entry does not establish that any
dtype achieves its tabulated rate — the MAC counts are arithmetic over ini fields, exactly as 0214's
4096 is, and the TFLOPS figures upstream derives from them inherit that status (0222). It does not
establish the HiF8, MXFP8 or MXFP4 equivalences: those have no `[DtypeMKN]` row, so they rest on one
upstream assertion with no second origin, and §4 Arm D is the only thing that would settle them. It
does not establish that `DT_INT4`'s row is reachable from Cube MMAD at all — upstream's own type table
says `int4b_t` is for Vector and weight storage and is not Cube MMAD supported, which sits awkwardly
beside an `[DtypeMKN]` row for INT4 and is not resolved here. It says nothing about the `DT_INT2`,
`DT_UINT2` and `DT_UINT1` rows beyond recording them; no upstream document in this scope mentions
them and no format name is claimed for them. It says nothing about accuracy, about the MXFP
32-data-per-scale tiling constraint, or about whether operand bandwidth can sustain the wider array —
a wider K per cycle demands proportionally more L1→L0 traffic, and that limit is untested. The reading
is pinned to toolkit `9.0.0-beta.2`, host directory `aarch64-linux`, one machine. Nothing transfers to
the other book (RULES.md Art. 1).
