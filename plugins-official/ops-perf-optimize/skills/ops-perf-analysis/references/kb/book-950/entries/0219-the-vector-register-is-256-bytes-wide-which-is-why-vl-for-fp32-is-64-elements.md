```
ID:        0219-the-vector-register-is-256-bytes-wide-which-is-why-vl-for-fp32-is-64-elements
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   verified — §4 run on 950PR 2026-08-25, via §5's declared predicate: device echo GetVecLen()=256;
           one full-mask store writes 64 fp32 / 128 half elements (2:1 in one run); zero words
           changed beyond the extent; UpdateMask-narrowed fixture wrote exactly 8. §6 has the
           readouts. Previously corroborated (three upstream skills + installed ini field, all
           documents).
BOARD:     950PR (measured 2026-08-25); 950DT family-claimed(unverified) — ini field only, no run
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:303 — "| 寄存器组织 | 128 KB 寄存器堆，按线程
           并发数切分 [¹] | 多条 VL=256 B 矢量寄存器 |"
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/vf-programming-rules.md:9 —
           "| `AscendC::Reg::RegTensor<T>` | 向量寄存器，VL=256B。b16→128 元素，b32→64 元素 |"
           # same repo as the line above — ONE origin (RULES.md Art. 3).
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214` — `Ascend950PR_9589.ini` `[AICoreSpec]`:
           `vector_reg_width=256`, `predicate_reg_width=32`, `wide_reg_width=768`, `vec_calc_size=128`.
INDEX:     vec_len_bytes=256 (device echo) · lanes fp32=64, half=128 (one full-mask store each,
           poison-counted, zero beyond-extent) · narrowed-mask fixture=8 · ini vector_reg_width=256
           (9.1.0, no unit). Run 2026-08-25, Ascend950PR.
OVERTURN:  `AscendC::GetVecLen()` returning anything but 256 on a 950 part at this pin, or a
           full-mask store of a `RegTensor<float>` writing other than 64 elements, measured with a
           poison counter that also reports the narrowed-mask fixture correctly.
```

# 0219 · The vector register is 256 bytes wide, which is why VL for fp32 is 64 elements

## 1 · Claim
Upstream asserts that a Regbase vector register is VL = 256 **bytes** wide, and that this yields 128
elements for 16-bit types and 64 for 32-bit types. The installed CANN 9.0.0-beta.2 platform config
carries a named `[AICoreSpec]` field `vector_reg_width=256` for every DAV_3510 SKU, alongside
`predicate_reg_width=32` and `wide_reg_width=768`. Not established here: `GetVecLen()` was never
called and no register was written.

This matters for the harvest bookkeeping as much as for the fact. The 2026-08-24 deep-dive placed
"256 B vector-register width (hence VL_FP32 = 64)" on its ESTABLISH FROM SCRATCH list — the set of
figures it judged to have no upstream authority at all. The installed ini has a field for it. The
item moves off that list and onto the ordinary verification queue.

## 2 · The wrong branch this removes
VL is the loop constant of every Regbase VF: the repeat count is `ceil(totalElems / (VL/sizeof(T)))`
and the per-iteration offset is `i * (VL/sizeof(T))`. Get it wrong and the loop either overruns the
buffer or leaves a tail unprocessed — and the second is the common one, because a too-small VL simply
does fewer elements per pass and the remainder is silently dropped if the mask is computed from the
same wrong constant.

The specific wrong branch this removes is a **unit** error, not an arithmetic one. 256 is a number
that is plausible as bits and as bytes, and both readings appear in this material: `vf-programming-rules.md:9`
says 256 B and derives 64 fp32 elements; `ascendc-performance-evaluation`'s hardware model labels the
same value `vector_reg_width_bits` (0273). Under the bits reading, VL_FP32 would be 8, not 64 — an
eightfold error in every loop bound, arriving through a field name rather than through a calculation.
Nothing type-checks a unit.

The second branch is the one vec-03 warns about directly: deriving the lane count from a *borrowed*
constant rather than from VL. `B32_DATA_NUM_PER_REPEAT` is also 64 on this part, so the wrong
derivation gives the right answer for fp32 and the wrong answer the moment the dtype changes (0252).

## 3 · Ground / Source
**Upstream**, three statements, all one origin (RULES.md Art. 3) but in three different skills — which
matters because it means a reader in any of them meets the figure:

`npu-arch/references/npu-arch-guide.md:295-306`, the SIMT-vs-SIMD capability table:

> | 维度 | SIMT | SIMD |
> | 寄存器类型 | 标量寄存器（per-Thread） | 矢量寄存器（per-VF） |
> | 寄存器组织 | 128 KB 寄存器堆，按线程并发数切分 [¹](#unverified) | 多条 VL=256 B 矢量寄存器 |

Note the asymmetry inside that one row: the SIMT side carries the `[¹]` unverified footnote (0206),
the SIMD side does not. Upstream is implicitly claiming the 256 B figure is better supported than the
128 KB one, and the installed ini turns out to bear that out.

`ascendc-regbase-best-practice/.../vf-programming-rules.md:5-9`, the core-types table, which is the
statement that derives the element counts:

> | 类型 | 说明 |
> | `AscendC::Reg::RegTensor<T>` | 向量寄存器，VL=256B。b16→128 元素，b32→64 元素 |
> | `AscendC::Reg::MaskReg` | 掩码寄存器 |
> | `__ubuf__ T*` | UB 地址指针，由 `localTensor.GetPhyAddr()` 获取 |

and the same file's `:43` states the consequence for masking: `UpdateMask` "内部自动递减 VL_T
（float:64，half:128）".

`ascendc-performance-evaluation/references/vector_instruction_types.json` carries
`"bytes_per_instruction": 256` at top level, with the unit spelled out in its own `units` block as
`"B/instruction"` — 256 bytes per vector instruction, consistent with a 256-byte register.

**Second origin — the installed toolkit**, read under the phase-1 read-only exception.
`Ascend950PR_9589.ini`, the tail of `[AICoreSpec]`:

```
[AICoreSpec]
...
ub_size=253952
ubblock_size=32
ubbank_size=4096
ubbank_num=16
ubsubbank_num=64
ubburst_in_one_block=32
ubbank_group_num=8
support_fixpipe=1
sparsity=0
l0a_layout_zN=1
vector_reg_width=256
predicate_reg_width=32
wide_reg_width=768
```

The ini gives no unit. That is the honest state of the second origin: it supplies a field and a
number, and the unit comes from upstream's prose and from the derived element counts, which only work
in bytes. The corroboration is of the *value*; the unit rests on the first origin's arithmetic.

Two adjacent fields are worth recording because they are the first hardware backing this book has for
neighbouring figures and both were on the deep-dive's establish-from-scratch list.
`predicate_reg_width=32` is consistent with a `MaskReg` holding 32 bits — enough for 128 b16 lanes at
one bit per... it is not, and that arithmetic does not close, which is stated here rather than
smoothed over: 128 b16 lanes would need 128 mask bits, so either the mask is per-32-bit-group or the
field means something else. Nothing here resolves it, and no entry is written on it.
`ubblock_size=32` is a 32-byte UB block granularity, adjacent to the "32 B DataCopy granularity" item
the deep-dive also listed as unestablished — but a UB block size and a DataCopy granularity are
different quantities, and equating them would be exactly the inference this book is built to refuse.
Recorded, not claimed.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion.

Arm A — the API, which is the value a kernel actually uses. Inside a `__simd_vf__`, evaluate
`AscendC::Reg::GetVecLen()` and store it:

```cpp
__simd_vf__ inline void VecLenProbeVf(__ubuf__ uint32_t* out)
{
    AscendC::Reg::RegTensor<uint32_t> r;
    AscendC::Reg::MaskReg m;
    uint32_t remaining = 1;
    m = AscendC::Reg::UpdateMask<uint32_t>(remaining);
    AscendC::Reg::Duplicate(r, static_cast<uint32_t>(AscendC::Reg::GetVecLen()));
    AscendC::Reg::StoreAlign(out, r, m);
}
```

The expected value is 256, in bytes. Recording it as a raw integer beside `sizeof(float)` is the
whole point: the readout must let a reader see 256/4 = 64 rather than be handed 64.

Arm B — the element count, which is what settles the unit and cannot be faked by a constant. Fill a
`RegTensor<float>` with a full mask, `StoreAlign` it to a UB region pre-poisoned with a sentinel, and
count how many 4-byte words changed. Under 256 bytes the answer is 64; under 256 bits it is 8. Repeat
for `half`, expecting 128 and 16 respectively. Two dtypes, because a single dtype cannot distinguish
"VL is 256 bytes" from "the lane count happens to be 64".

Arm C — the poison arm, which makes Arm B's count trustworthy. Pre-poison the *entire* destination
region, not just the expected extent, and report words changed **beyond** the expected 64. A non-zero
count there means the store wrote further than VL and the width is larger than claimed; that outcome
is as informative as the primary one and would be invisible to a probe that only checked the first 64
words.

Arm D — the ini cross-check. Print `vector_reg_width` from the resolved ini beside the Arm A value and
the resolved SoC string, so the two origins are compared on the same part rather than in the abstract
(0204 §4 Step 3).

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All arms run on one named die in one
session.

**As-run notes (2026-08-25, before the promoting evaluation of §6).** Arm A's readout comes from a
scalar GM store of `(float)GetVecLen()` at the end of a direct-launch `__vector__` kernel, not the
sketched single-lane `StoreAlign` — same quantity, simpler carrier; the raw value (256) is recorded
beside sizeof so the reader sees 256/4 = 64. Arms B/C run in one regbase `__VEC_SCOPE__` kernel:
one full-mask `Reg::DataCopy<StoreDist::DIST_NORM_B32/B16>` store into a poison region sized 2×
the expected extent (128 fp32 words / 256 halves), with words-changed counted over the WHOLE
region, so the beyond-extent count is measured rather than assumed. Arm D's ini figure
(`vector_reg_width=256`, no unit stated) is the survey readout from the same machine at the bound
9.1.0 pin, printed beside the resolved part (npu-smi: Ascend950PR,). The §5
positive fixture ran as declared: `UpdateMask<float>` with remaining=8 → exactly 8 words written,
offset 0. `950DT` was not contacted; BOARD narrows at promotion.

## 5 · Checker — acceptance declared before the run
Two verdict variables, kept apart because one is a reported number and the other is an observed
extent — and the entry's content is that they agree.

`vec_len_bytes` (Arm A) — pass iff it equals 256.

`lanes_observed` (Arm B) — pass iff it equals 64 for `float` **and** 128 for `half`. Both dtypes are
required in the same predicate: a checker that asserted only the fp32 count would go green under the
bits reading if some unrelated constant happened to be 64, which is the known blind species. The two
dtypes must move together by a factor of two, and that relation is checked explicitly rather than
inferred from two independent passes.

`overrun_words` (Arm C) — pass iff zero. A non-zero value overturns the width claim regardless of
what Arms A and B reported, and is reported with the observed extent rather than as a boolean.

The positive fixture, declared before the run: run Arm B with the mask deliberately narrowed to 8
elements via `UpdateMask` on a remaining count of 8. `lanes_observed` must then be 8, not 64. If the
counter still reports 64, it is measuring the buffer rather than the store, and every count it
produced is void. That is the input that makes this checker go red on a known answer.

Process exit code is not the verdict for any arm.

## 6 · Evidence
RUN 2026-08-25 — all four arms plus the declared positive fixture, one session, one die. 2026-08-25 direct-launch probes, Ascend950PR (npu-smi occupancy checked before/after; single one-block kernels), bound pin CANN 9.1.0 build 20260730_231653901, `-xasc --npu-arch=dav-3510`; probe sources and full logs with the verification run.

- **Arm A** — device-side echo: `GetVecLen()` = **256**, recorded raw beside sizeof so the reader
  performs the division: 256/4 = 64 (fp32), 256/2 = 128 (half). (Namespace note: the accessor
  resolves as `AscendC::GetVecLen()` from `basic_api/kernel_operator_sys_var_intf.h:76`, declared
  `constexpr`, returning `VECTOR_REG_WIDTH` = 256 — not under `Reg::` as this entry's OVERTURN line
  guessed; the quantity is the same.)
- **Arm B** — one full-mask `Reg::DataCopy<StoreDist::DIST_NORM_B32/B16>` store of one register:
  **64 fp32 elements** and **128 half elements** written, contiguous from offset 0 — the 2:1
  relation holds in one run, which is what separates "VL is 256 bytes" from "64 happens twice".
- **Arm C** — the destination poison regions were sized 2× the expected extent (128 fp32 words /
  256 halves) and counted over their WHOLE length: words changed beyond the expected extent = **0**
  in both dtypes.
- **Arm D** — installed ini on the same machine at the bound 9.1.0 pin: `vector_reg_width=256`
  (`[AICoreSpec]`, no unit stated), beside the resolved part (npu-smi: Ascend950PR).
- **Positive fixture, as declared** — `UpdateMask<float>` with remaining = 8: exactly **8** words
  written, from offset 0, the other 120 poison words untouched. The counter counts stores, not
  buffers.

§5's predicate evaluates PASS on every clause. The unit question is settled behaviourally: the
register is **256 BYTES** wide. Sibling readouts from the same session: 0247/0248 (operand
semantics), 0252 (lane-count rule), 0273 (the `_bits` suffix).

## 7 · Scope limits — what this entry does NOT establish
No device was contacted and no register was written. The entry does not establish that
`vector_reg_width=256` means bytes — the ini states no unit, and the byte reading comes from
upstream's derived element counts, which is an argument rather than an observation; 0273 records that
a third upstream file labels the same value as bits. It does not establish that `GetVecLen()` returns
this field, nor that the architectural register width equals the width a single instruction consumes,
though `bytes_per_instruction: 256` is consistent with their being equal. The two origins are both
documents from the same vendor pipeline (0204), so `corroborated` raises verification priority and
not trust. It says nothing about `predicate_reg_width=32` or `wide_reg_width=768`: §3 records that the
mask arithmetic does not obviously close, and no claim is made about either field. It says nothing
about `ubblock_size=32` as a DataCopy granularity — a UB block size and a copy granularity are
different quantities and are not equated here. The reading is pinned to toolkit `9.0.0-beta.2`, host
directory `aarch64-linux`, one machine. Nothing transfers to the other book (RULES.md Art. 1).
