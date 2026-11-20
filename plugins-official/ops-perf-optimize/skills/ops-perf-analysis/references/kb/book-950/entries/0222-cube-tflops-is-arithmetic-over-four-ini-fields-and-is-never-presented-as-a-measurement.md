```
ID:        0222-cube-tflops-is-arithmetic-over-four-ini-fields-and-is-never-presented-as-a-measurement
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   corroborated — upstream states the formula and the inputs; the installed CANN
           9.0.0-beta.2 ini independently carries all four input fields with the values upstream
           uses. Both trace to vendor ini (0204). Nothing was timed — and the point of this entry
           is that upstream did not time it either.
BOARD:     950PR
           # upstream's worked derivations name 950PR Server and 950PR PCIE; no 950DT figure is given.
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:97-119 — "Cube BF16/FP16 理论峰值算力（TFLOPS）由
           以下公式计算：`TFLOPS = M × K × N × 核数 × cube_freq(MHz) × 2 ÷ 10⁶`" with the parameter
           table naming each source INI field, and the worked derivations
           "950PR Server:  4096 × 32 × 1650 × 2 ÷ 10⁶ = 432.54 TFLOPS".
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — `Ascend950PR_9589.ini`:
           `cube_m_size=cube_n_size=cube_k_size=16`, `ai_core_cnt=32`, `cube_freq=1650`;
           `Ascend950PR_957b.ini`: `ai_core_cnt=28`, `cube_freq=1650`.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -hE '^(cube_[mnk]_size|ai_core_cnt|cube_freq)=' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend950PR_9589.ini
OVERTURN:  a measured single-core Cube throughput on 950PR exceeding 4096 MACs/cycle for fp16 —
           the formula's M×K×N term would then understate the array and every figure derived from
           it is a floor rather than a peak.
```

# 0222 · Cube TFLOPS is arithmetic over four ini fields and is never presented as a measurement

## 1 · Claim
Upstream asserts a closed-form derivation for Cube peak throughput:
`TFLOPS = M × K × N × 核数 × cube_freq(MHz) × 2 ÷ 10⁶`, and names the source of each term — M×K×N from
the ini fields `cube_m_size`/`cube_k_size`/`cube_n_size`, 核数 from `[SoCInfo] ai_core_cnt`, the
frequency from `[AICoreSpec] cube_freq`, and the ×2 from counting one FMA as two floating-point
operations. Upstream shows the worked results: 432.54 TFLOPS for 950PR Server (32 cores) and 378.47 for
950PR PCIE (28 cores), both BF16/FP16. The installed CANN 9.0.0-beta.2 ini carries all four inputs with
exactly those values. Not established here — and the load-bearing observation is that it is not
established *by upstream* either: every published Cube TFLOPS figure in this material is the output of
this arithmetic, not the output of a run.

## 2 · The wrong branch this removes
These numbers are printed in a table headed 算力与系统规格, in bold, beside memory capacities and core
counts. They read as specifications. An agent building a roofline takes 432 T as the denominator and
reports "we are at 38 % of peak", and the sentence carries an implicit claim — that 432 was observed
somewhere — which nothing in this material supports.

Three consequences follow, in increasing order of damage.

The mild one: the figure is a *theoretical* ceiling assuming every cycle issues a full MAC array, so no
real operator reaches it and a team measuring 60 % may already be at the practical limit. Nothing in the
table says so; the word 理论峰值 appears in the derivation section and not in the table.

The structural one: because it is arithmetic, the figure inherits every uncertainty of its inputs. 核数
is `ai_core_cnt`, which 0207 records as a family-typical value that a cut SKU or a vNPU slice reduces —
so the "peak" is wrong on any part that is not the tabulated one, and wrong in the direction that makes
a kernel look worse. And M×K×N is the `[AICoreSpec]` triple, which is only the *default* dtype row:
fp8 doubles it and fp32 halves it (0220, 0221), so a single "Cube peak" figure is dtype-specific in a
way the formula makes visible and the table does not.

The one that actually costs money: an agent cannot tell this figure apart from a measured one, so it
cannot know that the right response to a disappointing ratio is sometimes to re-derive the denominator
rather than to optimise the kernel. That is 0206 §2's failure mode with a concrete formula attached —
and this entry's value is precisely that the formula is *given*, so the denominator is auditable.

## 3 · Ground / Source
`npu-arch-guide.md:95-119`, the derivation in full — this is one of the few places in this material where
a published number shows its work:

> #### Cube 算力公式推导
>
> Cube BF16/FP16 理论峰值算力（TFLOPS）由以下公式计算：
>
> ```
> TFLOPS = M × K × N × 核数 × cube_freq(MHz) × 2 ÷ 10⁶
> ```
>
> **参数含义**：
>
> | 参数 | 值 | 来源 |
> |------|:--:|------|
> | M × K × N (Cube MAC 阵列) | 16×16×16 = **4096** | INI `cube_m_size=cube_k_size=cube_n_size=16` |
> | AICore 核数 | 24(910B2) / 28(PCIE) / 32(Server) | INI `[SoCInfo] ai_core_cnt` |
> | cube_freq | 1800(910B2) / 1650(950PR) MHz | INI `[AICoreSpec] cube_freq` |
> | ×2 | FMA 计为 2 次浮点运算 | 1 次 MAC = 1 乘 + 1 加 |
> | ÷10⁶ | MAC/s → TFLOPS | TFLOPS = 10¹² FLOPS = 10⁶ × 10⁶ MAC×2 |
>
> **推导示例**：
>
> ```
> 950PR Server:  4096 × 32 × 1650 × 2 ÷ 10⁶ = 432.54 TFLOPS
> 950PR PCIE:    4096 × 28 × 1650 × 2 ÷ 10⁶ = 378.47 TFLOPS
> ```

Every term names an INI field or a definition. There is no measurement anywhere in the chain, and
upstream does not claim one — the word is 理论峰值, theoretical peak.

Verified as arithmetic here: 4096 × 32 × 1650 × 2 = 432,537,600, ÷10⁶ = 432.54. And
4096 × 28 × 1650 × 2 = 378,470,400 → 378.47. Both reproduce. That is a check of upstream's arithmetic,
not of the hardware, and it is worth doing because a derivation whose arithmetic does not close would be
a different kind of finding entirely.

Second origin — the installed toolkit, read under the phase-1 read-only exception. `Ascend950PR_9589.ini`
carries `cube_m_size=16`, `cube_n_size=16`, `cube_k_size=16`, `ai_core_cnt=32`, `cube_freq=1650`;
`Ascend950PR_957b.ini` carries `ai_core_cnt=28`, `cube_freq=1650`. So all four inputs are independently
present with the values upstream used, and the derivation can be re-run from this machine's files
without consulting upstream at all. That is what `corroborated` buys here: not that 432 T is achievable,
but that the *inputs* are what upstream says they are.

Where the figures appear without their derivation, `npu-arch-guide.md:82-91`:

> | 规格项 | Ascend910B2 (DAV_2201) | Ascend950PR PCIE (DAV_3510) | Ascend950PR Server (DAV_3510) |
> | Cube 算力 BF16/FP16 | 353T | 378T | 432T |
> | Cube 算力 FP8/HiF8/MXFP8 | — | 757T | 865T |
> | Cube 算力 MXFP4 | — | 1514T | 1730T |
> | Vector 算力 FP16 | 22T | 47T [¹](#unverified) | 54T [¹](#unverified) |

The asymmetry in that table is the whole point of this entry. The Vector rows carry `[¹]` — upstream's
unverified marker (0206) — and the Cube rows do not. Read literally, upstream is claiming the Cube
figures are better supported. They are not *measured*; they are derived from ini fields, which is a
different and stronger thing than the Vector figures' 公开资料/经验值 pedigree (0223) but is still not an
observation. The absence of a marker on a derived figure is the gap this entry fills.

Two scope notes upstream states and a reader will skip. `:121` — "上表中 Cube 算力为纯 Cube 单元算力，
不含 Vector Core 贡献…（但需注意 Vector 不支持 bfloat16，故 BF16 总算力即 Cube 算力）". And the fp8 /
MXFP4 rows are the same formula with a different M×K×N from `[DtypeMKN]` (0220), so they inherit
everything said here.

## 4 · Procedure
Runnable later on `950PR`. The claim is that a published number is arithmetic; the procedure establishes
what the arithmetic is worth by measuring the thing it predicts.

Arm A — re-derive from the resolved ini, no device. Read the four fields from the ini the runtime
actually resolves to and recompute the figure. This is the auditable step and it is what makes the
denominator traceable: an agent quoting 432 T on a part whose `ai_core_cnt` is 28 has quoted the wrong
row, and only re-deriving catches it. Print the resolved SoC string with the result (0204 §4 Step 3).

Arm B — the achieved fraction, single-core first. Build an fp16 matmul with operands L1-resident (0212)
and accumulator L0C-resident (0211) so the Cube array is the limiter, at a shape where head and tail are
under 1 % of total. Minimum `aic_time` over 50 repetitions. Compute achieved MACs/cycle/core =
(M·N·K)/(aic_time × cube_freq), with `cube_freq` read from the resolved ini and printed rather than
assumed. Single-core, because a multi-core figure convolves the array's rate with the memory system's
ability to feed it, and the formula is about the array.

Arm C — the scaling term, which is the part of the formula Arm B cannot test. Repeat Arm B at 1, 8, 16
and `ai_core_cnt` cores and record whether achieved throughput scales linearly. The formula multiplies
by 核数 with no efficiency term; a sub-linear curve means the published figure is unreachable for a
reason the formula cannot express, and locating where it departs is more useful than the peak itself.

Arm D — the vNPU / cut-SKU arm, which tests §2's structural consequence. Re-run Arm A and Arm B inside a
vNPU slice with fewer cores. `GetCoreNumAic()` should fall (0207, 0216) while `ai_core_cnt` in the ini
does not — so the *correctly* derived peak falls and the tabulated one does not. This arm demonstrates
that the published figure is not a property of the part.

Device selection is explicit: the operator names the device index and the SKU, the harness prints both
back with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run
(shared machine, ≤4 dies), and no die is substituted for another. All points of Arm C's scaling curve run
on one named die in one session — a scaling curve assembled across dies attributes nothing.

## 5 · Checker — acceptance declared before the run
Two verdict variables, kept apart because one checks upstream's arithmetic and the other checks the
hardware, and the entry's content is that these are different questions.

`formula_reproduces` (Arm A) — pass iff recomputing from the resolved ini's four fields yields the
figure upstream publishes for that SKU, to two decimal places. This is a check of upstream against
itself and needs no board; a failure here would be a transcription error in the truth source and is
worth finding cheaply.

`macs_per_cycle_per_core` (Arm B) — pass iff it lands in [3686, 4096], i.e. within 10 % below the
formula's M×K×N term and **never above it**. The upper bound is the operative clause and is declared now:
a reading above 4096 does not pass, it overturns the entry, because the array would then be larger than
the ini reports and every derived figure is a floor. Declaring the asymmetry in advance is what stops a
pleasing over-performance being read as success.

`core_scaling_efficiency` (Arm C) — achieved multi-core throughput divided by (single-core × cores).
Reported with the core count, **no pass threshold**: the formula asserts linearity and this variable
measures the gap, and inventing a threshold would let a convenient result read as confirmation of a term
the formula does not actually contain.

The positive fixture, declared before the run: rerun Arm B with `baseK` halved. Achieved MACs/cycle must
stay put while wall time halves. If the achieved rate moves, Arm B is not measuring the array — it is
measuring some limiter that scales with K — and every value it produced is void. Without this, the
checker only reads "a number came out near 4096", which is the known blind species: many shapes divide
out to a plausible figure.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No matmul was built and nothing
was timed. The two multiplications reproduced in §3 are arithmetic over upstream's own stated inputs,
performed here to confirm that upstream's arithmetic closes; confirming a multiplication is not
confirming a throughput. The ini fields are a file read under the sanctioned phase-1 read-only
exception.

## 7 · Scope limits — what this entry does NOT establish
Nothing was timed. The entry does not establish that any part achieves any fraction of the published
figures — Arms B and C are open. It establishes what the figures *are*: the output of a formula over
four ini fields, with no measurement anywhere in the chain, on either origin. It does not establish that
the formula is the right model: it contains no efficiency term, no term for operand supply, and no term
for the FixPipe drain, so a linear multiplication by 核数 is an assumption the formula makes and Arm C is
what tests it. BOARD is `950PR` because upstream's worked derivations name 950PR Server and PCIE; **no
950DT Cube figure is published anywhere in this scope**, and none is derived here. It covers the
BF16/FP16 default row only — the fp8, HiF8, MXFP8 and MXFP4 figures are the same formula with a
different M×K×N from `[DtypeMKN]` (0220), and HiF8/MXFP8/MXFP4 have no ini row at all, so those figures
rest on one upstream assertion each. It says nothing about Vector throughput, whose figures carry
upstream's own unverified marker and a dual-issue assumption (0223). It says nothing about whether the
ini's `ai_core_cnt` is the right core count for a Cube operator — upstream's own accessor routing says
`GetCoreNumAic()` is (0216) — nor about cut SKUs and vNPU slices, where the derived figure moves and the
published one does not (Arm D, open). Nothing transfers to the other book (RULES.md Art. 1): the 910B2 column
and the 353T figure in the quoted tables are upstream's text, carried as quotation.
