# easyasc.a5 DSL coverage & gaps

What the `easyasc.a5` micro surface **already exposes** (so you don't needlessly drop to raw
AscendC), and the **genuine gaps** where the DSL can't yet express a production pattern.

Derived by diffing the `easyasc.a5` export list (`easyasc/a5.py`) against the methodology mined
from arch35 production kernels. This is a snapshot of the DSL surface — re-derive if the package
changes.

> **Why this matters**: a survey of arch35 *C++* kernels will flag many techniques as "needs a
> primitive easyasc lacks" — but most of those primitives **do exist** in `easyasc.a5` under
> different names. Check this doc before concluding you must hand-write AscendC.

---

## 1. Already exported — use the DSL

These cover the bulk of the reg/micro methodology in `reg_vf_skeleton.md`,
`reg_micro_cookbook.md`, and `numerical_precision.md`. Do **not** drop to AscendC for them.

| Capability | easyasc.a5 names |
|---|---|
| Reg load/store | `ub_to_reg`, `reg_to_ub`, `ub_to_reg_continuous`, `reg_to_ub_continuous`, `*_single` |
| **Pack / unpack on load/store** (mixed precision) | `ub_to_reg_unpack`, `ub_to_reg_unpack4`, `reg_to_ub_pack4`, `ub_to_reg_upsample/downsample`, `reg_to_ub_downsample` |
| **Load/store distributions** | `LoadDist`, `LoadDistValue`, `StoreDist`, `StoreDistValue` |
| Gather / scatter / broadcast | `gather`, `ub_to_reg_gather`, `reg_to_ub_scatter`, `ub_to_reg_brcb`, `dup` |
| **Stream-compaction** | `gather_mask` (mask-driven compact) |
| **Cast with config** | `cast` + `CastConfig`, `RegLayout`, `RoundMode` (saturation/rounding parameterizable) |
| Elementwise / scalar | `add sub mul div vmax vmin vand vor vxor prelu`, `adds muls vmaxs vmins shiftls shiftrs axpy lrelu` |
| Transcendentals | `exp abs relu sqrt ln log log2 log10 neg vnot vcopy` |
| **In-register reductions** | `cadd cgadd cpadd cmax cgmax cmin cgmin` |
| Compare / select | `compare`, `select` |
| **Interleave / deinterleave** | `interleave`, `deinterleave` |
| Mask algebra (incl. XOR) | `mask_and mask_or mask_xor mask_not mask_mov mask_sel mask_pack mask_unpack mask_interleave mask_deinterleave`, `update_mask`, `move_mask_spr` |
| Index gen | `arange` |
| **Explicit pipe events** | `setflag`, `waitflag`, `bar_v/mte2/mte3/mte1/m/fix/all` |
| **Cross-core (cube↔vec) handshake** | `cube_ready vec_ready wait_cube wait_vec allcube_ready allvec_ready allcube_wait allvec_wait`, `CvMutex`, `VcMutex` |
| **Atomics** | `atomic_add`, `atomic_max`, `atomic_min` |
| Cube | `matmul`, `gm_to_l1_nd2nz`, `l1_to_l0`, `mmad`, `l0c_to_gm_nz2nd`, `l0c_to_l1`, `l0c_to_ub`, `set_constant_to_l1` |
| Misc | `reinterpret`, `split_workspace`, `reset_cache`, `clean_dcache` |

**Corrected misconceptions** (commonly mis-flagged as missing, but present): LoadDist/StoreDist,
pack/unpack, `CastConfig` rounding/saturation, interleave/deinterleave, `mask_xor`, `gather_mask`,
`setflag`/`waitflag`, cube↔vec handshake, atomics.

---

## 2. Genuine gaps (prioritized)

### P0 — `sort32` / `mergesort4` / `mergesort_2seq` not exported on a5 (near-miss)
The sort wrappers exist in `easyasc/stub_functions/vec/sort.py`, the parser handles them
(`easyasc/parser/asc_handlers/vec_sort.py` → `Sort32` / `MERGESORT4` / `Mergesort2Seq`), and
`easyasc.a2` re-exports them — but **`easyasc.a5` does not**. `sort.py` has no architecture guard
(it's a generic UB-float sort). arch35 sort kernels confirm the C310 hardware has the intrinsics.
- **Impact**: the entire sort/merge pattern family (`reg_micro_cookbook.md` Pattern B) is
  unreachable from a5 without hand-writing AscendC.
- **Action**: add the three names to the `easyasc.a5` import block, then validate `sort32` on the
  a5 simulator against a PyTorch reference. Low effort, high payoff.

### P0 — histogram / bucketing primitive absent
No `histogram` (or equivalent) anywhere in the package. arch35 uses a dedicated `Histograms`
instruction for radix-sort digit counting and index-repetition statistics.
- **Impact**: histogram / scatter-stat (`reg_micro_cookbook.md` Pattern D) and radix-sort must be
  emulated with compare+select+reduce loops — slow and verbose.
- **Action**: add a `histogram` micro stub + parser handler mapping to the HW instruction; or, if
  the HW instruction isn't exposed, document the compare+`cadd` emulation recipe as the supported
  fallback.

### P1 — `gather_mask` has no surviving-count readback
`gather_mask(dst, src, mask)` compacts but returns no count of surviving lanes. Compact-with-count
(needed for variable-size output / filtering) requires reading the count register. `move_mask_spr`
moves a mask SPR but its relationship to the compaction count is unverified.
- **Action**: verify whether the count is recoverable via `move_mask_spr` + popcount, or expose an
  explicit count out-param / SPR readback. Document the confirmed idiom.

### P1 — unaligned load/store family not exported
The authoritative headers define `LoadUnAlign`/`LoadUnAlignPre`/`StoreUnAlign`/`StoreUnAlignPost`
(with `UnalignReg` state), but `easyasc.a5` exports none of them — it relies on aligned load +
host-side padding. Production compaction/neighbor-window recipes use the unaligned family.
- **Action**: expose the unaligned load/store wrappers, or document the aligned-load+pad workaround
  as the supported substitute (and its limits).

### P2 — fused / niche primitives (perf-only or rare)
Defined in MicroAPI, no easyasc.a5 export, but **emulatable** with the primitive pair (correct,
just more instructions) — only worth adding for hot paths:
- `Truncate`, `MulsCast`, `AbsSub`, `ExpSub`, `MulDstAdd` — fused ops (emulate: `Sub`+`Abs`,
  `Sub`+`Exp`, `Mul`+`Add`, etc.).
- `ShiftLeft`/`ShiftRight` by **per-lane** amount (easyasc only has scalar-amount `shiftls`/`shiftrs`),
  widening `Mull`, carry `AddC`/`SubC`, `Unsqueeze`, `MaskGenWithRegTensor`, `CreateAddrReg`.

> The gap list above is now cross-checked against the **complete** MicroAPI surface enumerated in
> `arch35_micro_reference.md` §1 (from the authoritative `reg_compute/*_intf.h` headers), not a
> sample. §1F there lists the same gaps inline.

---

## 3. Out of micro-DSL scope (handled elsewhere, not gaps here)

These were flagged by the C++ survey but are **host-side / codegen** concerns, not the `@vf`
micro surface — they're handled (or not) by the op-host + `run_codegen` path, not by adding a
micro primitive:
- **Tiling-key generation / template dispatch** — host tiling + codegen.
- **Scalar promotion** (bf16 scalar → fp32 before fp32 compute) — author-side: convert the scalar
  explicitly in the kernel; not a missing primitive.
- **Multi-level reduce** — composable from `cadd`/`cgadd` + UB staging (see
  `numerical_precision.md` §7); not a single missing primitive.

---

## 4. Recommended next actions for the branch

1. **Wire `sort32`/`mergesort4`/`mergesort_2seq` into `easyasc.a5`** and add an a5 sort example +
   simulator validation. (P0, small)
2. **Decide histogram strategy**: native instruction stub vs documented emulation recipe. (P0)
3. **Pin down compact-with-count** (`gather_mask` + count). (P1)
4. Re-run this diff whenever `easyasc/a5.py` changes; keep §1 in sync so authors are never told to
   hand-write something the DSL already supports.
