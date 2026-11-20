```
ID:        0221-fp32-and-int32-halve-the-cube-mac-array-and-npu-arch-never-states-it
LABEL:     boundary
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — ONE origin only: the installed CANN 9.0.0-beta.2 `[DtypeMKN]` section. No
           upstream document in this scope states these two rows, so there is nothing to
           corroborate against — the absence is the finding. Nothing was timed.
BOARD:     950PR, 950DT
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2`, `innerversion=V100R001C10SPC001B214` —
           `aarch64-linux/data/platform_config/Ascend950PR_9589.ini` `[DtypeMKN]`:
           `DT_FLOAT=16,8,16` and `DT_INT32=16,8,16`, against `Default=16,16,16`.
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:123-145 — upstream's `[DtypeMKN]` derivation
           section, which enumerates the rows that *widen* the array (FP8, INT4) and states no row
           that narrows it; `ops/npu-arch/references/npu-hardware-params.md` lists no FP32 Cube
           throughput at all.  # quoted as the ABSENCE, not as support.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -n 'DT_FLOAT=\|DT_INT32=\|^Default=' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend950PR_9589.ini
OVERTURN:  an fp32 matmul on 950PR achieving more than 2048 MACs/cycle/core — the `DT_FLOAT` row
           then does not describe the Cube array, and the whole per-dtype reading of `[DtypeMKN]`
           (0220) needs re-examining with it.
```

# 0221 · FP32 and INT32 halve the Cube MAC array, and npu-arch never states it

## 1 · Claim
The installed CANN 9.0.0-beta.2 platform config carries `[DtypeMKN]` rows `DT_FLOAT=16,8,16` and
`DT_INT32=16,8,16` for DAV_3510 — M×K×N = 2048, half the `Default=16,16,16` value of 4096.
Upstream asserts the *opposite* direction of this same mechanism for low-precision types (0220),
and asserts nothing at all about fp32 or int32 Cube throughput: no npu-arch table has an FP32 Cube
算力 row, and the derivation section enumerates only the rows that widen the array. Not established here: no MMAD
was issued, nothing was timed, and this claim has exactly one origin.

## 2 · The wrong branch this removes
Upstream's Cube 算力 table (`npu-arch-guide.md:82-91`) has rows for BF16/FP16, for FP8/HiF8/MXFP8, and
for MXFP4. It has no FP32 row. An agent needing an fp32 matmul roofline finds nothing, falls back to
the one number it does have — 4096 MACs/cycle from `[AICoreSpec]` (0214) — and builds a denominator
that is 2× too large. Every fp32 Cube kernel then reports roughly 50 % of peak no matter how well it
is written, and the team spends its budget looking for a factor of two that does not exist.

This is the failure mode 0206 §2 predicts in the abstract, arriving concretely: an unverifiable-or-
absent *rate* produces an unreachable ceiling, and nothing distinguishes "the kernel is slow" from
"the denominator was wrong". Here it is worse than an unverifiable figure, because the figure is not
merely unverified — it is absent, and the fallback is silently wrong in the direction that looks like
a kernel defect.

The second branch is an algorithm-selection one. If fp32 Cube runs at half rate while fp16 runs at
full and fp8 at double (0220), then the cost of staying in fp32 for a Cube-bound operator is 2×
against fp16 and 4× against fp8 — which changes whether a mixed-precision rewrite is worth doing. An
agent that believes all dtypes share one array cannot price that decision at all.

Note the symmetry that makes the ini row credible on its face: K runs 256 → 128 → 64 → 32 → 16 → 8 as
element width runs 1 → 2 → 4 → 8 → 16 → 32 bits, one clean ladder with `Default` at the 16-bit rung.
`DT_FLOAT` and `DT_INT32` sit exactly where a 32-bit type should. That is a pattern argument, not
evidence, and it is stated here as such.

## 3 · Ground / Source
**The only origin.** `Ascend950PR_9589.ini`, `[DtypeMKN]` in full, read under the phase-1 read-only
exception:

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

The two rows of interest are the last two, and they are the only rows in the section whose K is
*below* the default. Applying upstream's own formula (`npu-arch-guide.md:100`,
`TFLOPS = M×K×N × 核数 × cube_freq(MHz) × 2 ÷ 10⁶`) to `DT_FLOAT` on the two SKUs upstream tabulates:

```
950PR Server (32 cores, 1650 MHz):  2048 × 32 × 1650 × 2 ÷ 10⁶ = 216.3 TFLOPS
950PR PCIE   (28 cores, 1650 MHz):  2048 × 28 × 1650 × 2 ÷ 10⁶ = 189.2 TFLOPS
```

against upstream's published 432 T and 378 T for BF16/FP16. Those two numbers are this entry's
arithmetic, not upstream's — upstream publishes no fp32 Cube figure — and they inherit whatever
status the formula and the ini row have, which is: unmeasured (0222).

**The absence, quoted as such.** `npu-arch-guide.md:82-91`, the 算力与系统规格 table, has rows
`Cube 算力 BF16/FP16`, `Cube 算力 FP8/HiF8/MXFP8`, `Cube 算力 MXFP4`, and `Vector 算力 FP16`. There is
no FP32 row. The derivation section at `:123-145` walks through FP8 and MXFP4 and stops; it does not
mention `DT_FLOAT` or `DT_INT32`, and it introduces `[DtypeMKN]` only as the place where the array
gets *larger* ("FP8_E4M3FN 的 Cube MAC 阵列更大"). `npu-hardware-params.md` lists FP32 nowhere except
as a Cube MMAD supported *format* (`npu-arch-guide.md:343`, "FP16 / BF16 / HF32 / FP32 / S8 | 通用类型").

So upstream supports fp32 on Cube, tabulates no rate for it, and describes the mechanism that would
give the rate in a section that only looks in one direction. That is a gap in the declared 真源
(0204), not a contradiction with it — nothing upstream says is falsified by these rows.

This is filed as `C-950arch-005` in `harvest/contradictions-950-arch.md` as a coverage gap rather
than a numeric conflict.

One caution about the second origin that this entry does not have. Every other constants entry in this
block (0209-0216, 0219, 0220) rests on npu-arch *and* the ini agreeing. This one rests on the ini
alone. A transcription or generation error in the vendor's ini would be invisible here, and there is
no third party either to confirm or to contradict. That is why the stratum is `harvested` and why §4
is the only thing that will move it.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion. This claim
has no second document, so the run is not a tie-breaker — it is the first real evidence.

Arm A — fp32 Cube throughput, absolute. Build a single-core fp32 matmul with operands L1-resident
(0212) and accumulator L0C-resident (0211) so the array is the limiter, run at a shape where head and
tail are under 1 % of total, take the minimum `aic_time` over 50 repetitions, and compute achieved
MACs/cycle = (M·N·K)/(aic_time × cube_freq). `cube_freq` is read from the resolved ini and printed,
not assumed.

Arm B — the ratio to fp16, which is the verdict. Run the identical harness at fp16 on the same die in
the same session at the same logical shape and report fp32/fp16. Expected 0.5. Two absolute numbers
from two sessions would attribute to nothing; the ratio on one die attributes to the dtype.

Arm C — int32, the row's twin. Repeat Arms A and B for int32 against int8. Expected fp32-like
behaviour: int32 at 2048, int8 at 8192, ratio 0.25. If `DT_FLOAT` behaves as tabulated but `DT_INT32`
does not, the ini rows are not uniformly meaningful and 0220's reading of the section weakens with it.

Arm D — the K-step arm, which distinguishes "the array is 16×8×16" from "fp32 is slow for some other
reason". Sweep `baseK` over {8, 16, 32, 64} for fp32 at fixed M and N. If the array's K is 8, the rate
plateaus at `baseK` = 8 and larger steps buy nothing; if fp32 slowness comes from operand bandwidth or
accumulator pressure instead, the curve will not plateau there. This arm is what makes the claim
attributable rather than merely observed.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All dtype comparisons run on one named die
in one session.

## 5 · Checker — acceptance declared before the run
Verdict variable `fp32_over_fp16` from Arm B. Pass is declared now as the band [0.45, 0.55] — ±10 %
around 0.5.

Two outcomes are named now so neither can be reinterpreted after the fact. A ratio near 1.0 means the
`DT_FLOAT` row does not describe the Cube array, this entry is overturned, and 0220's per-dtype
reading of `[DtypeMKN]` must be re-examined with it — the rows would then be something other than
array shapes. A ratio well below 0.45 means fp32 is limited by something beyond the array, and Arm D
is what says which.

`int32_over_int8` from Arm C is a separate verdict with band [0.225, 0.275]; it is not merged with the
fp32 verdict, because the entry's content is that *both* rows read the same way and one of them
failing is a finding rather than noise.

The blinding test, declared before the run: rerun Arm A with `baseK` pinned to 4 — below the row's K.
Achieved MACs/cycle must fall by roughly half. If it does not, the harness is not sensitive to K at
all and every rate it produced is void. Without this, the checker only reads "fp32 was slower than
fp16", which is the known blind species: fp32 being slower has many ordinary causes, and none of them
is the claim.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `[DtypeMKN]` rows in §3
are a read of one installed file under the sanctioned phase-1 read-only exception; the two TFLOPS
figures computed there are arithmetic over that row and upstream's formula, performed here, and are
not observations. Nothing was compiled, no device was contacted, and no MAC was counted.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, and this entry has **one** origin — unlike every other constants entry in this
block, it has no second document either agreeing or disagreeing, so an error in the vendor's ini
generation would be undetectable from here. It does not establish that the `DT_FLOAT` row governs Cube
MMAD rather than some other unit or some tiling default; that `[DtypeMKN]` rows describe the physical
array at all is upstream's reading (0220), adopted here and untested. It does not establish the two
TFLOPS figures in §3 as achievable: they are arithmetic over an unmeasured MAC count times an
unmeasured frequency, which is exactly the status 0222 records for every figure of that shape. It does
not establish that upstream's omission is an error — a truth source may legitimately decline to
publish a rate it has not confirmed, and 0206 records that upstream marks such figures rather than
inventing them; what is recorded here is that the omission leaves a user with no fp32 number and a
tempting wrong one. It says nothing about HF32, which upstream lists as a supported Cube format with
no `[DtypeMKN]` row of its own and which is therefore in the same position as HiF8 (0220 §7). The
reading is pinned to toolkit `9.0.0-beta.2`, host directory `aarch64-linux`, one machine, one ini
file. Nothing transfers to the other book (RULES.md Art. 1).
