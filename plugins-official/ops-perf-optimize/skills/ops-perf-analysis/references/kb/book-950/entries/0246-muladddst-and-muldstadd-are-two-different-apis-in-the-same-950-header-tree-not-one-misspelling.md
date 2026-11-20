```
ID:        0246-muladddst-and-muldstadd-are-two-different-apis-in-the-same-950-header-tree-not-one-misspelling
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   verified — §4 run on 950PR 2026-08-25, via §5's declared sub-verdicts: resolves_both PASS (both
           APIs ran on live data, 22 vs 38), dtype_partition_holds PASS (int32/int64 refusals with
           the verbatim SupportType diagnostic; MulAddDst int32 runs), different numbers on two
           operand sets. lowering_differs (Arm C) instrument-blocked — recorded in §6, does not
           gate existence per §5. Previously corroborated (headers + upstream, both documents).
BOARD:     950PR (measured 2026-08-25)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:76 —
           "| Binary reg compute | `Add`, `Sub`, `Mul`, `Div`†, `Max`, `Min`, `And`, `Or`, `Xor`,
           `MulAddDst`, `Mull` | Yes | `basic_api/interface/reg_compute/` |"  (`MulDstAdd` appears
           nowhere in this file)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-03-fused-instr.md:1,36,51
           — "# 技术卡片 vec-03：融合指令（MulDstAdd / VMULA 替 Mul+Add）" / "MulDstAdd(xR, wR, bR, m);"
           / "`MulDstAdd(dst, src1, src2, mask)` 语义 = `dst = dst*src1 + src2`"
           # the two files above are both `upstream/skills-dev-main` — ONE origin (RULES.md Art. 3).
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, 950-era (ships
           `dav_c310`/`npu_arch_3510` trees and `Ascend950{PR,DT}_*.ini`):
             `include/ascendc/basic_api/interface/reg_compute/kernel_reg_compute_vec_binary_intf.h:70-71`
               — `template <typename T = DefaultType, MaskMergeMode mode = MaskMergeMode::ZEROING, typename U>`
                 `__simd_callee__ inline void MulAddDst(U& dstReg, U& srcReg0, U& srcReg1, MaskReg& mask);`
             `include/ascendc/basic_api/interface/reg_compute/kernel_reg_compute_vec_fused_intf.h:39-40`
               — `template <typename T = DefaultType, MaskMergeMode mode = MaskMergeMode::ZEROING, typename U>`
                 `__simd_callee__ inline void MulDstAdd(U& dstReg, U& srcReg0, U& srcReg1, MaskReg& mask);`
INDEX:     both APIs ran: 22 vs 38 (3,5,7), 11 vs 17 (2,3,5) · MulAddDst int32 = 38 exact, int64
           compiles · MulDstAdd int32/int64 refused ("SupportType<int, half, float, __bf16>...not
           supported"). Run 2026-08-25. Declarations re-derivable by file read (9.1.0 paths:
           asc/include/basic_api/reg_compute/kernel_reg_compute_vec_{fused,binary}_intf.h).
OVERTURN:  a 950-era toolkit in which only one of the two names resolves — i.e. a compile of a VF
           calling `Reg::MulDstAdd` or `Reg::MulAddDst` that fails with "no member named" for a
           target where the other succeeds.
```

# 0246 · `MulAddDst` and `MulDstAdd` are two different APIs in the same 950 header tree, not one misspelling

## 1 · Claim
Upstream asserts, in one skill, that the VF-safe fused multiply-add is `MulAddDst`
(`regbase_api_whitelist.md:76`), and upstream asserts, in another skill, that it is `MulDstAdd`
(`vec-03-fused-instr.md`). The 2026-08-24 deep-dive recorded this as defect 4.10 and the phase-1
plan filed it as blocking question **B1**, a disagreement about spelling. It is not a disagreement.
The installed CANN 9.0.0-beta.2 toolkit on this machine declares **both** as distinct
`__simd_callee__ inline` function templates, in two different `reg_compute/` interface headers, with
different supported-dtype sets and different lowerings. Not established here: nothing was compiled,
no kernel ran, and no numerical result was produced.

The upstream defect is therefore not a typo but a **whitelist gap**: `MulDstAdd` appears nowhere in
`regbase_api_whitelist.md`, and that file's own rule instructs the reader to treat an absent API as
unavailable *until verified in the installed SDK headers*. Following that rule resolves B1.

## 2 · The wrong branch this removes
Without this entry, an agent that has read the whitelist meets `MulDstAdd` in vec-03 and applies the
whitelist's absence rule literally: not listed, therefore unavailable, therefore vec-03 is wrong.
It then "corrects" vec-03 by substituting `MulAddDst` — which compiles, because `MulAddDst` is real
— and silently changes the arithmetic, because the two APIs place `dst` in different positions of
the expression (0247). The result is a numerically wrong kernel produced by an agent that was
following the authoritative document.

The reverse branch is equally available: an agent that trusts vec-03 concludes the whitelist is
stale and stops consulting it, losing the one document that scopes which surface is callable inside
a VF at all (0250).

The third branch is the one a careful agent takes and is still wrong: treat the two as aliases and
pick either. They are not aliases. `MulAddDst` accepts nine dtype families including 64-bit integers;
`MulDstAdd` accepts three float types only. A generated kernel templated on `int32_t` compiles under
one name and fails under the other, and the failure appears as an inscrutable `static_assert` about
dtype support rather than as "you chose the wrong API".

## 3 · Ground / Source
**Upstream, side A** — `regbase_api_whitelist.md:76`, the VF-Function-Safe table's binary row:

> | Binary reg compute | `Add`, `Sub`, `Mul`, `Div`†, `Max`, `Min`, `And`, `Or`, `Xor`, `MulAddDst`, `Mull` | Yes | `basic_api/interface/reg_compute/` |

and the file's governing rule, stated in its opening paragraph:

> If an API is absent from the lists below, treat it as unavailable until you verify it in the
> installed SDK headers and update the design instead of guessing.

That sentence is the correct procedure and it is what §4 and this entry's second SOURCE execute.
`grep -n "MulDstAdd"` over that file returns nothing.

**Upstream, side B** — `vec-03-fused-instr.md`, which uses the other spelling uniformly: in its
title (`:1` "融合指令（MulDstAdd / VMULA 替 Mul+Add）"), in its worked code (`:36`
`MulDstAdd(xR, wR, bR, m);   // x = x*w + b（in-place）`), and in a precision red line built on it
(`:51`, quoted in full in 0247). Both files live under `upstream/skills-dev-main` and are therefore
**one origin** (RULES.md Art. 3) — the disagreement is intra-repo and could not be settled inside it.

**Second origin — the installed toolkit.** Read under the sanctioned phase-1 read-only exception; no
execution, no compilation. Toolkit identity, recorded because a 910-era toolkit would answer nothing
about 950: `compiler/version.info` gives `Version=9.0.0-beta.2`;
`ascend_all_cann_install.info` gives `innerversion=V100R001C10SPC001B214`, `arch=aarch64`. It is
950-era on three independent indications — it ships
`aarch64-linux/data/platform_config/Ascend950PR_*.ini` and `Ascend950DT_*.ini` (32 files,
`NpuArch=3510`), an `asc/impl/basic_api/reg_compute/dav_c310/` implementation tree, and an
`asc/impl/c_api/instr_impl/npu_arch_3510/` tree. `dav_c310` ≡ `__DAV_C310__` ≡ DAV_3510 ≡ arch35 by
0203.

Declaration 1 — `include/ascendc/basic_api/interface/reg_compute/kernel_reg_compute_vec_binary_intf.h`,
lines 67-74 verbatim:

```cpp
template <typename T = DefaultType, typename U>
__simd_callee__ inline void Mull(U& dstReg0, U& dstReg1, U& srcReg0, U& srcReg1, MaskReg& mask);

template <typename T = DefaultType, MaskMergeMode mode = MaskMergeMode::ZEROING, typename U>
__simd_callee__ inline void MulAddDst(U& dstReg, U& srcReg0, U& srcReg1, MaskReg& mask);
```

Declaration 2 — `include/ascendc/basic_api/interface/reg_compute/kernel_reg_compute_vec_fused_intf.h`,
lines 26-42 verbatim:

```cpp
namespace AscendC {
namespace Reg {
...
template <typename T = DefaultType, MaskMergeMode mode = MaskMergeMode::ZEROING, typename U>
__simd_callee__ inline void MulDstAdd(U& dstReg, U& srcReg0, U& srcReg1, MaskReg& mask);
} // namespace Reg
} // namespace AscendC
```

Both are in `namespace AscendC::Reg`, both are `__simd_callee__` (VF-safe), both take the identical
parameter list. The signatures are indistinguishable; the headers are not.

The implementations differ, and the difference is what makes them separate instructions rather than
duplicated declarations. `arm64-linux/asc/impl/basic_api/reg_compute/dav_c310/kernel_reg_compute_vec_binary_impl.h:1848-1881`:

```cpp
template <typename T = DefaultType, MaskMergeMode mode = MaskMergeMode::ZEROING, typename U>
__simd_callee__ inline void MulAddDstImpl(U& dstReg, U& srcReg0, U& srcReg1, MaskReg& mask)
{
    using ActualT = typename U::ActualT;
    static_assert(SupportType<ActualT, uint16_t, int16_t, uint32_t, int32_t, half, float, bfloat16_t,
                  int64_t, uint64_t>(), "current data type is not supported on current device!");
    static_assert(SupportEnum<mode, MaskMergeMode::ZEROING>(),
                  "current MulAddDst api only supported Mode ZEROING on current device!");
    if constexpr (sizeof(ActualT) == 8) {
        ... Mul(traitTwoDstTmpReg, srcReg0, srcReg1, mask);
            Add(dstReg, traitTwoDstTmpReg, dstReg, mask); ...
    } else {
        constexpr auto modeValue = GetMaskMergeMode<mode>();
        vmula(dstReg, srcReg0, srcReg1, mask, modeValue);
    }
}
```

and `.../dav_c310/kernel_reg_compute_vec_fused_impl.h:101-111`:

```cpp
__simd_callee__ inline void FusedMulDstAddImpl(U& dstReg, U& srcReg0, U& srcReg1, MaskReg& mask)
{
    using ActualT = typename U::ActualT;
    static_assert(SupportType<ActualT, half, float, bfloat16_t>(),
                  "current data type is not supported on current device!");
    static_assert(SupportEnum<mode, MaskMergeMode::ZEROING>(), "MulDstAdd only support Mode ZEROING");
    constexpr auto modeValue = GetMaskMergeMode<mode>();
    vmadd(dstReg, srcReg0, srcReg1, mask, modeValue);
}
```

Three differences, all from the declarations and `static_assert`s, none inferred:

| | `MulAddDst` | `MulDstAdd` |
|---|---|---|
| interface header | `kernel_reg_compute_vec_binary_intf.h` | `kernel_reg_compute_vec_fused_intf.h` |
| dtypes | u16, i16, u32, i32, half, float, bf16, i64, u64 | half, float, bf16 |
| lowers to | `vmula` (b64: `Mul` + `Add`) | `vmadd` |
| MaskMergeMode | ZEROING only | ZEROING only |

`kernel_reg_compute_vec_fused_intf_impl.h:64-73` additionally exposes `FusedMulDstAdd` as an exact
second name for `MulDstAdd` — both forward to `FusedMulDstAddImpl` with identical template
arguments. So the surface has three names for two instructions, which is worth knowing before
reading open-source kernels.

Corroborating within upstream (same origin, so it adds locatability rather than independence):
`ascendc-performance-evaluation/references/vector_instruction_types.json` carries `MulAddDst` and
`MulDstAdd` as **separate instruction rows** with exactly the dtype sets above, each citing its own
vendor documentation page (`.../复合计算/MulAddDst-39.md` and `.../复合计算/MulDstAdd.md`). That the
dtype partition was reproduced independently in a JSON authored for a different purpose is why the
distinction is treated here as structural rather than as a header quirk.

Filed as `C-950arch-002` in `harvest/contradictions-950-arch.md` — recorded as a whitelist
completeness defect, not as a spelling dispute.

## 4 · Procedure
Runnable later on a named 950 board (`950PR`). The header read has already settled *existence*; what
it cannot settle is whether both names resolve and lower as declared on a real target, so the
procedure is a compile plus a run, and the compile arm is the cheap decisive one.

Arm A — resolution, compile only, no device. Two translation units, each a minimal `__simd_vf__` that
calls one of the names on `float`:

```cpp
template <typename T>
__simd_vf__ inline void FmaVf(__ubuf__ T* dst, __ubuf__ T* a, __ubuf__ T* b, uint32_t n, uint16_t rpt)
{
    AscendC::Reg::RegTensor<T> dR, aR, bR;
    AscendC::Reg::MaskReg m;
    uint32_t remaining = n;
    for (uint16_t i = 0; i < rpt; ++i) {
        int32_t off = static_cast<int32_t>(i) * static_cast<int32_t>(AscendC::Reg::GetVecLen() / sizeof(T));
        m = AscendC::Reg::UpdateMask<T>(remaining);
        AscendC::Reg::LoadAlign(dR, dst + off);
        AscendC::Reg::LoadAlign(aR, a + off);
        AscendC::Reg::LoadAlign(bR, b + off);
        AscendC::Reg::MulAddDst(dR, aR, bR, m);      // TU2: MulDstAdd
        AscendC::Reg::StoreAlign(dst + off, dR, m);
    }
}
```

Both must compile for a 3510 target. Record the full diagnostic if either does not.

Arm B — the dtype partition, which is the falsifiable half of the table in §3. Instantiate each name
at `int32_t` and at `int64_t`. Under the `static_assert`s, `MulAddDst` compiles for both and
`MulDstAdd` fails for both with a "current data type is not supported" diagnostic. A build where
`MulDstAdd` accepts `int32_t` overturns the partition even if Arm A passed.

Arm C — the lowering, on the board. Emit assembly (or disassemble the compiled kernel) for the two
float instantiations and record which mnemonic appears: `vmula` for `MulAddDst`, `vmadd` for
`MulDstAdd`. This is the arm that shows they are different *instructions* rather than two names
compiled to the same thing. It requires no execution — a disassembly is a build artifact — which is
why it is preferred over a timing comparison.

Arm D — numerical distinctness, on the board, and this is the arm that connects to 0247. Run both on
identical inputs with `dst` pre-loaded to a value distinguishable from both sources, and compare
outputs bit-for-bit. Bit-identical output across the two APIs would mean they compute the same
function despite lowering differently, which would matter more than anything in §3.

Device selection is explicit for Arms C and D: the operator names the device index, the probe prints
it back with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run
(shared machine, ≤4 dies), and no die is substituted for another. Arms A and B need no device and run
first.

**As-run notes (2026-08-25, before the promoting evaluation of §6).** Arms A and B ran as compile
probes on the bound 9.1.0 pin plus device runs shared with 0247 (both APIs called on live data —
existence established by execution, which is stronger than the sketched compile-only form). One
spelling correction found on the way: on 9.1.0 the reg surface is namespace `AscendC::Reg::`
(`AscendC::RegTensor` is refused with a did-you-mean). Arm C could NOT be executed as sketched —
three instrument dead-ends, each self-reported before any verdict use: (i) whole-TU mnemonic
histograms compare library-header text, not the one differing call; (ii) `-save-temps` emits
`.asci` files that are PREPROCESSED SOURCE, not assembly (their diff shows only the C++ source
line and filename markers); (iii) the shipped `llvm-objdump` does not decode dav-c310 vector
instructions into mnemonics. Arm C is recorded as instrument-blocked, not as identical-lowering.

## 5 · Checker — acceptance declared before the run
Verdict variable `two_distinct_apis`, composed from four sub-verdicts that are recorded separately —
an aggregate boolean would let a passing Arm A stand in for the partition and the lowering, which are
the substantive claims.

`resolves_both` (Arm A) — pass iff both TUs compile. Either failing overturns this entry for that
name on that toolkit.

`dtype_partition_holds` (Arm B) — pass iff `MulAddDst` compiles at `int32_t` and `int64_t` AND
`MulDstAdd` fails at both with a diagnostic naming data-type support. A *silent* success for
`MulDstAdd` at `int32_t` is a fail, and so is a failure whose diagnostic names something else — the
checker matches diagnostic text, not exit status, because "it did not compile" and "it did not
compile for the stated reason" are different results.

`lowering_differs` (Arm C) — pass iff the two disassemblies contain different mnemonics. Identical
mnemonics is not a fail of the *existence* claim but demotes §3's table row and is logged.

`outputs_differ` (Arm D) — pass iff the two results differ bit-for-bit on the crafted input. This is
the positive fixture and the guard against the known blind species: a checker that only confirmed
"both compiled" would go green on a toolkit where the two names were aliases, which is exactly the
hypothesis under test. The input that makes it fire is stated now — `dst = 3.0, src0 = 5.0,
src1 = 7.0` yields 38.0 under `dst + src0*src1` and 22.0 under `dst*src0 + src1`; if the harness
reports these equal, the harness is broken and every verdict it issued is void.

Process exit codes are not the verdict anywhere in this checker: in Arm B a non-zero exit is the
expected outcome for one of the two builds.

## 6 · Evidence
RUN 2026-08-25 — Arms A, B and D; Arm C instrument-blocked (see §4 as-run notes). 2026-08-25, shared 950 machine, bound pin CANN 9.1.0 build 20260730_231653901, `-xasc --npu-arch=dav-3510`; compile probes host-side, run arms on Ascend950PR; probe sources and full logs with the verification run.

- **`resolves_both` (Arm A)** = PASS, exceeded: both names not only compile but RAN on live data —
  `MulDstAdd(3,5,7)` = 22.0, `MulAddDst(3,5,7)` = 38.0 (0247 §6 carries the full evaluation).
- **`dtype_partition_holds` (Arm B)** = PASS on the checker's own terms: `MulAddDst` at `int32_t`
  RUNS (returns 38 exact) and compiles at `int64_t`; `MulDstAdd` at `int32_t` AND `int64_t` fails
  with the diagnostic naming data-type support, verbatim: "static assertion failed due to
  requirement 'SupportType<int, half, float, __bf16>()': current data type is not supported on
  current device!" — from `dav_3510/kernel_reg_compute_vec_fused_impl.h:101`; the same diagnostic
  trace names the `vmadd` call at `:105`.
- **`lowering_differs` (Arm C)**: NOT ESTABLISHED BY DISASSEMBLY — the shipped `llvm-objdump`
  cannot decode dav-c310 vector instructions, and two earlier instruments were false (§4 as-run
  notes). What stands instead: the behavioural divergence (22 vs 38, two operand sets, plus the
  int32 partition) proves the two names reach DIFFERENT operations, and the compiler's own
  diagnostic places `vmadd` inside `MulDstAdd`'s impl. §3's vmula/vmadd table row keeps its
  header-read sourcing, now with a run-level corroboration of difference and no assembly-level
  confirmation of the specific mnemonics.
- **Arm D (different numbers)** = PASS: 22 ≠ 38 on identical inputs; 11 ≠ 17 on a second set.

The whitelist's escape hatch was right and its table was incomplete: both APIs exist, both are
VF-callable, and they are not interchangeable.

Specifically, on the header work that produced §3: **a header grep is a file read, not a run.** It
establishes that both symbols are declared in the installed toolkit's `reg_compute/` interface
headers, at the paths and with the signatures quoted, and that their implementations carry the
`static_assert` dtype sets and the `vmula` / `vmadd` calls quoted. It does not establish that either
name resolves for a real target (Arm A), that the dtype partition is enforced at instantiation
(Arm B), that the declared lowering is what the compiler emits (Arm C), or that the two produce
different numbers (Arm D). No compilation was attempted, no device was contacted, and nothing was
executed — the phase-1 sanction covers reading installed files and nothing else.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish operand semantics — which operand `dst`
plays in each expression — that is a separate claim carried by 0247, on separate evidence, and
deliberately not fused into this one: this entry is about *existence and distinctness*, and letting
one sentence carry both would be the measurement-and-inference-in-one-sentence species. It does not
establish behaviour on any board: the headers name none, the `dav_c310` tree is arch35 by 0203, and
no 950 part was contacted, so BOARD is `family-claimed(unverified)` and stays there until §4 runs.
It is pinned to exactly one toolkit — `9.0.0-beta.2`, `V100R001C10SPC001B214`, host directory
`arm64-linux`/`include/ascendc` on this machine — and a different CANN version may declare a
different surface; note that `ascendc-performance-evaluation`'s hardware model cites `cann-9.1.0` ini
paths, which were not available here. It does not establish that `MulDstAdd` is *absent* from every
upstream whitelist-like document, only from `regbase_api_whitelist.md`. It does not establish that
`Mula`, listed as a third fused name in upstream's instruction JSON, exists in these headers — a
`grep` for `Mula` over the installed `reg_compute/` interface headers returned nothing, which is an
absence and is recorded as such rather than as a finding. Finally, it makes no performance claim: the
two APIs' relative cost is untested, and vec-03's "−40 %" figure is explicitly an external,
disclaimed number and is not carried here.
