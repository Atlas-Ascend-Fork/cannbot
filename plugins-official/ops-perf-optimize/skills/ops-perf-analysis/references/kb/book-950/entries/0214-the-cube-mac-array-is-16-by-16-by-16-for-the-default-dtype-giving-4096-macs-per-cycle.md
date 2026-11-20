```
ID:        0214-the-cube-mac-array-is-16-by-16-by-16-for-the-default-dtype-giving-4096-macs-per-cycle
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — ops/npu-arch and the installed CANN 9.0.0-beta.2 ini set independently
           carry `cube_m_size=cube_n_size=cube_k_size=16` and `[DtypeMKN] Default=16,16,16` for
           DAV_3510. Both trace to vendor ini (0204); no MAC was timed.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:37 — "| Cube MAC 阵列 | `cube_m_size /
           cube_k_size / cube_n_size` | 16×16×16 | 一个周期完成 4096 次 MAC |"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — `Ascend950PR_9589.ini` and all 32
           `NpuArch=3510` files: `cube_m_size=16`, `cube_n_size=16`, `cube_k_size=16`, and
           `[DtypeMKN] Default=16,16,16`.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -h '^cube_[mnk]_size=' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend950PR_9589.ini
OVERTURN:  a Cube throughput measurement on 950PR that exceeds 4096 MACs/cycle/core for fp16 or
           bf16 — the array is then larger than the ini reports and every TFLOPS figure derived
           from it (0222) is a floor, not a peak.
```

# 0214 · The Cube MAC array is 16×16×16 for the default dtype, giving 4096 MACs per cycle

## 1 · Claim
Upstream asserts that the Cube MAC array on DAV_3510 is M×K×N = 16×16×16, that this yields 4096
multiply-accumulates per cycle per core, and that the three dimensions are the ini fields
`cube_m_size`, `cube_k_size`, `cube_n_size`. Upstream files this among its cross-architecture
invariants. The installed CANN 9.0.0-beta.2 set carries all three as 16 in every `NpuArch=3510`
file, and additionally carries `[DtypeMKN] Default=16,16,16` — a per-dtype table whose default row
matches. Not established here: no Cube kernel was built and no throughput was timed.

## 2 · The wrong branch this removes
4096 MACs/cycle is the numerator of every Cube roofline, so a wrong value silently rescales every
"we are at 61 % of peak" statement a team makes. But the more damaging branch is the one the
`[DtypeMKN]` section creates: an agent that reads `cube_m_size=16, cube_n_size=16, cube_k_size=16`
from `[AICoreSpec]` and stops there concludes the array is 16³ *for every dtype*. It is not — the
same file's `[DtypeMKN]` block overrides K per dtype, and the overrides run from 8 to 256 (0220,
0221). A fp8 roofline built on 4096 understates peak by 2×; an fp32 roofline built on 4096
overstates it by 2×, and the fp32 case is the one that produces a team chasing an unreachable target.

So the rule this entry actually installs is: 16×16×16 is the **default row**, not the array. The
`[AICoreSpec]` triple and the `[DtypeMKN]` default agree, which is exactly what makes it easy to
mistake one for the other.

## 3 · Ground / Source
`npu-hardware-params.md:33-39`, §1 跨架构一致参数, third row:

> | Cube MAC 阵列 | `cube_m_size / cube_k_size / cube_n_size` | 16×16×16 | 一个周期完成 4096 次 MAC |
>
> > **注意**：即便以上参数通常一致，代码中仍应通过 `GetCoreMemSize` 获取，避免硬编码。

`npu-arch-guide.md:105-111` restates it as the first parameter of the TFLOPS derivation:

> | M × K × N (Cube MAC 阵列) | 16×16×16 = **4096** | INI `cube_m_size=cube_k_size=cube_n_size=16` |
> | ×2 | FMA 计为 2 次浮点运算 | 1 次 MAC = 1 乘 + 1 加 |

and the quick table at `:153` marks it present on all five architectures: `| Cube 16³ | ✓ | ✓ | ✓ |
✓ | ✓ |`. Same skill throughout — one origin (RULES.md Art. 3).

Crucially, the same guide qualifies the invariance three sections later, `:125-138`:

> 不同于 FP16/BF16 使用 `cube_m/n/k_size=16×16×16=4096`，FP8_E4M3FN 的 Cube MAC 阵列更大
> （INI `[DtypeMKN]` 段）：`DT_FLOAT8_E4M3FN = 16,32,16 → M×K×N = 16×32×16 = 8192`

So upstream itself scopes the 16³ figure to FP16/BF16 in one place while listing it as a
cross-architecture constant in another. Those are compatible — one is the default, one is a
per-dtype override — but only if a reader sees both, and they are 90 lines apart in different files.

Second origin — the installed toolkit, read under the phase-1 read-only exception.
`Ascend950PR_9589.ini`:

```
[AICoreSpec]
cube_freq=1650
cube_m_size=16
cube_n_size=16
cube_k_size=16
vec_calc_size=128

[DtypeMKN]
Default=16,16,16
DT_FLOAT8_E4M3FN=16,32,16
DT_INT8=16,32,16
DT_INT4=16,64,16
DT_FLOAT=16,8,16
DT_INT32=16,8,16
```

All three `[AICoreSpec]` fields equal 16 in every `NpuArch=3510` file. The `[DtypeMKN]` default row
independently equals `16,16,16`, which is the second origin's version of the same claim; the
non-default rows are 0220 and 0221.

`Ascend035.ini` (`NpuArch=3505`, 0205) carries `cube_m_size=1, cube_n_size=16, cube_k_size=16` —
outside upstream's verified set, and quoted because it shows the "cross-architecture invariant" is
scoped to the architectures upstream lists, not to everything shipping in the directory.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion. The claim
has a structural half (the array shape) and a rate half (4096 per cycle), and they need different
arms — conflating them is how a shape claim gets certified with a timing number.

Arm A — the shape, from the platform layer. Read the three dimensions through whatever
`PlatformAscendC` accessor exposes them (or, failing an accessor, from the resolved ini, recording
that as a file read rather than a query) and print them beside the resolved SoC string, so the
values can be matched to the file the runtime actually chose (0204 §4 Step 3).

Arm B — the rate, by microbenchmark. Build a single-core fp16 matmul with M, N, K chosen so the
operand tiles are L1-resident (0212) and the accumulator is L0C-resident (0211), so neither MTE2 nor
FixPipe is the limiter. Run at a shape large enough that head/tail is <1 % of the total, take the
minimum over 50 repetitions, and compute achieved MACs/cycle = (M·N·K) / (aic_time × cube_freq).
`cube_freq` is read from the resolved ini and printed, not assumed.

Arm C — the dtype arm, which is the one that tests §2's actual risk. Repeat Arm B for bf16, fp32 and
int8 at identical shapes, and record the ratio of each to fp16. Under the `[DtypeMKN]` table the
expected ratios are 1.0, 0.5 and 2.0. This arm establishes whether `[DtypeMKN]` describes the machine
or only the compiler's tiling choice — a distinction no file read can make.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. Arm B and Arm C must run on the same die
in the same session, or the ratio in Arm C carries no attribution at all.

## 5 · Checker — acceptance declared before the run
Two verdict variables, deliberately separate.

`mac_shape` — the triple from Arm A. Pass iff it equals (16, 16, 16). This is a structural check and
carries no timing.

`macs_per_cycle` — from Arm B. Pass iff it lands in [3686, 4096], i.e. within 10 % below the claimed
peak and never above it. The upper bound is the operative clause: a reading **above** 4096 does not
pass, it overturns the entry, because the array would then be larger than both origins report. That
asymmetry is declared now precisely so a pleasing over-performance cannot be read as success.

Arm C's ratios have their own declared band, ±10 % around (1.0, 0.5, 2.0), and a miss corrects 0220
or 0221 rather than this entry.

The blinding test, declared before the run: rerun Arm B with `baseK` halved. Achieved MACs/cycle must
stay put while wall time halves. If the achieved rate moves, Arm B is not measuring the array — it
is measuring some limiter that scales with K, and every number it produced is void. Without this,
the checker only reads "a number came out near 4096", which is the known blind species: it cannot
distinguish a real 4096 from a shape that happened to divide out that way.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The ini values in §3 are a
read of installed files under the sanctioned phase-1 read-only exception; a file read reports
configuration fields and cannot observe a single MAC.

## 7 · Scope limits — what this entry does NOT establish
No device was contacted, no matmul was built, and nothing was timed. The entry does not establish
that the hardware performs 4096 MACs per cycle — it establishes that two vendor-ini-derived origins
say the array is 16×16×16 and that upstream computes 4096 from it. The 4096 figure is arithmetic over
three fields, not an observation, and this distinction carries into every TFLOPS number derived from
it (0222). It does not establish the figure for any dtype other than the `[DtypeMKN]` default row;
fp8, int4, fp32 and int32 have their own rows and their own entries (0220, 0221), and the "cross-
architecture invariant" heading upstream files this under does not survive contact with that table.
It says nothing about sustained throughput, about whether one core can be fed fast enough to reach
the array's rate, or about `sparsity` (0215), which on earlier parts could double effective MACs and
on DAV_3510 cannot. Nothing transfers to the other book (RULES.md Art. 1); the ✓ marks in upstream's
five-column table are quoted as upstream's text. The reading is pinned to toolkit `9.0.0-beta.2`,
host directory `aarch64-linux`, one machine.
