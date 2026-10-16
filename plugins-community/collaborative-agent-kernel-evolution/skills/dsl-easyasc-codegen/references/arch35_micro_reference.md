# arch35 MicroAPI reference (ground truth for easyasc a5)

The full A5 / C310 `MicroAPI` reg-compute surface, mapped to easyasc.a5. The C++ `MicroAPI` is
the hardware ground truth that easyasc a5 micro ops lower onto; use this to resolve the
**"same name ≠ same thing"** ambiguity called out in `easyasc_a5_cheatsheet.md`, and pair it
with `reg_micro_cookbook.md` (patterns) + `micro_perf_rules.md` (tuning).

> **Two sources, two stabilities:**
> - **§1 (the mapping)** is enumerated from the **authoritative API headers**
>   `…/asc/include/basic_api/reg_compute/kernel_reg_compute_*_intf.h` — the definition of the
>   MicroAPI surface, version-pinned and stable. Functions are `__simd_callee__ inline` in
>   `namespace AscendC::Reg`. This is the complete callable set, not a sample.
> - **§2 recipes / §3 pitfalls** are mined from **production kernel usage** across
>   `ops-nn-master / ops-transformer-master / ops-math-master`. Those file refs are paths only
>   (no line numbers — repos drift; `grep` the symbol to locate).
>
> **How to use**: find the easyasc op in §1 to learn its exact MicroAPI counterpart and the name
> divergence; consult §2/§3 for how it's used and what breaks. Name divergence is real and
> systematic — easyasc `vmax`→`Max`, `vand`→`And`, `shiftls`→`ShiftLefts`, `dup`→`Duplicate`.

---

## 1. Complete MicroAPI surface → easyasc.a5 mapping

`equiv` column: the `easyasc.a5` export that lowers to this primitive, `— (gap)` if easyasc has
no export for it, or `— (type)` for an enum/struct. Signatures are representative (overloads grouped).

### 1A. Data movement — `datacopy / addrreg / membar / copy`

| MicroAPI | signature (representative) | semantics | easyasc.a5 equiv |
|---|---|---|---|
| `LoadAlign` | `LoadAlign<T,LoadDist>(dstReg, __ubuf__ T* src[, AddrReg/postStride])` | aligned UB→reg load; `LoadDist` does broadcast/upsample/downsample/interleave/unpack/channel-split during load (+ dual-reg, post-update, AddrReg overloads) | `ub_to_reg` (+ `ub_to_reg_unpack`/`unpack4`/`upsample`/`downsample`/`brcb`/`continuous`/`single` for the dist variants) |
| `StoreAlign` | `StoreAlign<T,StoreDist>(__ubuf__ T* dst, srcReg, MaskReg)` | aligned reg→UB store w/ mask; `StoreDist` packs/interleaves/merges during store (+ dual-reg, post-update, AddrReg overloads) | `reg_to_ub` (+ `reg_to_ub_pack4`/`downsample`/`single`) |
| `Load` | `Load<T>(dstReg, __ubuf__ T* src)` | simplified unaligned load | `ub_to_reg` |
| `Store` | `Store<T>(__ubuf__ T* dst, srcReg[, count])` | simplified unaligned store | `reg_to_ub` |
| `LoadUnAlignPre` | `LoadUnAlignPre<T>(UnalignRegForLoad&, __ubuf__ T* src)` | seed the align-state reg for an unaligned load run | — (gap; easyasc uses aligned load + host pad) |
| `LoadUnAlign` | `LoadUnAlign<T,PostLiteral>(dstReg, UnalignRegForLoad&, __ubuf__ T*&, postStride)` | unaligned load using the pre-seeded align reg; auto-advances ptr | — (gap) |
| `StoreUnAlign` / `StoreUnAlignPost` | `StoreUnAlign<T,PostLiteral>(__ubuf__ T*&, srcReg, UnalignRegForStore&, postStride)` | unaligned store + finalize | — (gap) |
| `Gather` / `GatherB` | `Gather<…>(dstReg, __ubuf__ T* base, idxReg, MaskReg)` | indexed UB→reg load (indices are BYTE offsets; no bounds check) | `ub_to_reg_gather`, `gather` |
| `Scatter` | `Scatter<…>(__ubuf__ T* base, srcReg, idxReg, MaskReg)` | indexed reg→UB store | `reg_to_ub_scatter` |
| `CreateAddrReg` | `CreateAddrReg<T>(idx0, stride0[, …up to 4 dims])` | build a multi-dim indirect-address register (strides in BYTES) | — (gap; easyasc addresses via tensor slicing) |
| `LocalMemBar` | `LocalMemBar<MemType src, MemType dst>()` | local-memory barrier between VEC/SCALAR load/store phases | `bar_v` / `bar_mte2` / `bar_mte3` / `bar_all` |
| `Move` | `Move<T[,MaskMergeMode]>(dstReg, srcReg[, MaskReg])` | reg→reg copy (masked = conditional merge) | `vcopy` (masked → `select`) |

### 1B. Mask & compaction — `maskreg / gather_mask / pack`

| MicroAPI | signature (representative) | semantics | easyasc.a5 equiv |
|---|---|---|---|
| `And`/`Or`/`Not`/`Xor` (mask) | `And(MaskReg dst, a, b, pregAll)` etc. | bitwise ops on **mask registers** — incl. a genuine mask-level `Xor` | `mask_and` / `mask_or` / `mask_not` / `mask_xor` |
| `CreateMask` | `CreateMask<T,MaskPattern>()` | full/pattern mask (ALL, VL1…VL128, H, Q) | `CreateMask` |
| `UpdateMask` | `UpdateMask<T,RegTrait>(uint32 count)` | enable first `count` lanes (tail handling); `RegTraitNumTwo` for int64 | `update_mask` |
| `MaskGenWithRegTensor` | `MaskGenWithRegTensor<T,offset>(MaskReg dst, srcReg)` | derive a mask from a reg-tensor's bits | — (gap) |
| `Move`/`MoveMask` (mask) | `Move(MaskReg dst, src[, mask])` / `MoveMask<T>()` | copy / fetch a mask register | `mask_mov` / `move_mask_spr` |
| `Select` (mask) | `Select(MaskReg dst, a, b, mask)` | pick between two masks | `mask_sel` |
| `Pack`/`UnPack` (mask) | `Pack<HighLowPart>(MaskReg dst, src)` | narrow/widen mask width (LOWEST/HIGHEST half) | `mask_pack` / `mask_unpack` |
| `Interleave`/`DeInterleave` (mask) | `Interleave<T>(MaskReg d0,d1, s0,s1)` | interleave/de-interleave two masks | `mask_interleave` / `mask_deinterleave` |
| `Pack`/`UnPack` (tensor) | `Pack<DstT,SrcT,HighLowPart>(dstReg, srcReg)` | narrow/widen element width (e.g. int32-view↔uint16) | `reg_to_ub_pack4` / `ub_to_reg_unpack`,`ub_to_reg_unpack4` |
| `Gather` (reg) | `Gather<…>(dstReg, srcReg, idxReg)` | reg→reg lane gather by index | `gather` |
| `Squeeze` | `Squeeze<T,GatherMaskMode>(dstReg, srcReg, MaskReg)` | stream-compaction: pack mask-true lanes contiguously (optional STORE_REG) | `gather_mask` |
| `Unsqueeze` | `Unsqueeze<T>(dstReg, MaskReg)` | inverse scatter of compacted lanes | — (gap) |
| `GetSpr`/`ClearSpr` | `GetSpr<spr>()` / `ClearSpr<spr>()` | read/clear a special-purpose reg (e.g. the compaction AR counter) | — (gap; blocks compact-with-count) |

### 1C. Vector arithmetic — `vec_binary / vec_binary_scalar / vec_ternary_scalar / vec_cmpsel`

| MicroAPI | signature (representative) | semantics | easyasc.a5 equiv |
|---|---|---|---|
| `Add`/`Sub`/`Mul`/`Div` | `Add<T,MaskMergeMode>(dst, s0, s1, mask)` | element-wise vector arithmetic | `add` / `sub` / `mul` / `div` |
| `Max`/`Min` | `Max<T,mode>(dst, s0, s1, mask)` | element-wise max/min | `vmax` / `vmin` |
| `And`/`Or`/`Xor` (vec) | `And<T,mode>(dst, s0, s1, mask)` | element-wise bitwise on reg tensors | `vand` / `vor` / `vxor` |
| `Prelu` | `Prelu<T,mode>(dst, s0, s1, mask)` | parametric ReLU | `prelu` |
| `ShiftLeft`/`ShiftRight` | `ShiftLeft<T,U,mode>(dst, s0, s1, mask)` | shift by **per-lane** amount (s1) | — (gap; easyasc shift is scalar-amount only) |
| `Mull` | `Mull<T>(d0, d1, s0, s1, mask)` | widening multiply → two dst regs | — (gap) |
| `MulAddDst` | `MulAddDst<T,mode>(dst, s0, s1, mask)` | fused `dst += s0*s1` (vec×vec) | — (gap; ≠ axpy which is scalar×vec) |
| `Add`/`Sub` carry, `AddC`/`SubC` | `AddC<T>(carryOut, dst, s0, s1, carryIn, mask)` | add/sub with carry/borrow in-out | — (gap) <!-- codespell:ignore carryin --> |
| `Adds`/`Muls` | `Adds<T,U,mode>(dst, src, scalar, mask)` | vector ± / × broadcast scalar | `adds` / `muls` |
| `Maxs`/`Mins` | `Maxs<T,U,mode>(dst, src, scalar, mask)` | element-wise max/min vs scalar | `vmaxs` / `vmins` |
| `ShiftLefts`/`ShiftRights` | `ShiftLefts<T,U,mode>(dst, src, scalar, mask)` | shift by a **scalar** amount (direction in the name) | `shiftls` / `shiftrs` |
| `LeakyRelu` | `LeakyRelu<T,U,mode>(dst, src, scalar, mask)` | leaky ReLU | `lrelu` |
| `Axpy` | `Axpy<T,U,mode>(dst, src, scalar, mask)` | fused `dst += scalar*src` | `axpy` |
| `Compare` | `Compare<T,CMPMODE>(MaskReg dst, a, b, mask)` | element-wise cmp (EQ/NE/LT/LE/GT/GE) → mask | `compare` |
| `Compares` | `Compares<T,CMPMODE>(MaskReg dst, src, scalar, mask)` | cmp vs scalar → mask | — (gap; emulate with `dup`+`compare`) |
| `Select` | `Select<T>(dst, s0, s1, mask)` | `dst = mask ? s0 : s1` | `select` |

### 1D. Vector unary / convert / fused / reduce / arange / histograms

| MicroAPI | signature (representative) | semantics | easyasc.a5 equiv |
|---|---|---|---|
| `Abs`/`Exp`/`Ln`/`Log`/`Log2`/`Log10`/`Neg`/`Relu`/`Sqrt` | `Exp<T,mode>(dst, src, mask)` | element-wise unary math | `abs`/`exp`/`ln`/`log`/`log2`/`log10`/`neg`/`relu`/`sqrt` |
| `Not` (unary) | `Not<T,mode>(dst, src, mask)` | bitwise NOT on a reg tensor | `vnot` |
| `Cast` | `Cast<Dst,Src,CastTrait>(dst, src, mask)` | dtype convert; `CastTrait{RegLayout,SatMode,MaskMergeMode,RoundMode}` controls sat/rounding | `cast` (+ `CastConfig`/`RoundMode`) |
| `Truncate` | `Truncate<T,RoundMode,mode>(dst, src, mask)` | round in-place within same dtype (f32→f32 etc.) | — (gap) |
| `MulsCast` | `MulsCast<…,RegLayout>(dst, src, scalar, mask)` | fused multiply-by-scalar + cast | — (gap; perf fusion) |
| `AbsSub` | `AbsSub<T,mode>(dst, s0, s1, mask)` | `|s0 − s1|` | — (gap; emulate `Sub`+`Abs`) |
| `ExpSub` | `ExpSub<…,RegLayout,mode>(dst, s0, s1, mask)` | `exp(s0 − s1)` (softmax fusion) | — (gap; emulate `Sub`+`Exp`) |
| `MulDstAdd` | `MulDstAdd<T,mode>(dst, s0, s1, mask)` | `dst = dst*s0 + s1` | — (gap) |
| `Reduce` | `Reduce<ReduceType,…>(dst, src, mask)` | cross-reg reduction SUM/MAX/MIN → lane 0 | `cgadd`/`cgmax`/`cgmin` (in-group: `cadd`/`cmax`/`cmin`) |
| `ReduceDataBlock` | `ReduceDataBlock<ReduceType,…>(dst, src, mask)` | per-data-block reduction | — (gap) |
| `PairReduceElem` | `PairReduceElem<PairReduce,…>(dst, src, mask)` | pair-wise element reduction (SUM) | `cpadd` (closest) |
| `Arange` | `Arange<T,IndexOrder>(dst, scalar)` | fill `[start, start+1, …]` (inc/dec order) | `arange` |
| `Histograms` | `Histograms<…,HistogramsBinType,HistogramsType>(dst, src, mask)` | bucket counts into BIN0..7 (FREQUENCY/ACCUMULATE) | — (gap; **P0**, blocks radix-sort/repetition-stat) |

### 1E. Enums & types (selected)

| Type/Enum | Members / purpose | easyasc.a5 |
|---|---|---|
| `LoadDist` / `StoreDist` | layout transform during load/store: `DIST_NORM`, `DIST_BRC_*`, `DIST_US_*`/`DIST_DS_*` (up/down-sample), `DIST_DINTLV_*`, `DIST_UNPACK_*`/`DIST_UNPACK4_B8`, `DIST_PACK_*`, `DIST_INTLV_*`, `DIST_SPLT*CHN_*`, `DIST_FIRST_ELEMENT_*` | `LoadDist`/`StoreDist` (exported) |
| `PostLiteral` | `POST_MODE_NORMAL` / `POST_MODE_UPDATE` (auto-advance ptr) | implicit in `*_continuous` |
| `MaskMergeMode` | `ZEROING` (zero masked lanes, default) / `MERGING` (keep dst) | implicit per-op |
| `MaskPattern` | `ALL`, `VL1..VL128`, `H`, `Q` — mask shape | via `CreateMask` arg |
| `RoundMode` | `CAST_RINT`/`CAST_FLOOR`/`CAST_CEIL`/`CAST_ROUND`/`CAST_TRUNC`/`CAST_NONE`/… | `RoundMode` (exported) |
| `SatMode` | `SAT` / `NO_SAT` (saturate on cast) | in `CastConfig` |
| `CastTrait` | `{RegLayout, SatMode, MaskMergeMode, RoundMode}` | `CastConfig` |
| `HighLowPart` | `LOWEST` / `HIGHEST` (which half for pack/unpack) | arg of `mask_pack`/`unpack` |
| `RegTrait` | `RegTraitNumOne` (1 phys reg) / `RegTraitNumTwo` (2, for int64) | implicit by dtype |
| `AddrReg` / `MaskReg` / `RegTensor` | indirect-address reg / predicate reg / VREG-sized batch | `MaskReg`, `Reg`/`RegList` |
| `ReduceType` / `HistogramsBinType` / `HistogramsType` / `IndexOrder` | reduction kind / `BIN0..7` / `FREQUENCY`,`ACCUMULATE` / inc-dec | mostly internal |

### 1F. Genuine easyasc.a5 gaps surfaced by the full surface

No easyasc.a5 export lowers to these (cross-checked against `easyasc/a5.py`) — see
`dsl_coverage_and_gaps.md` for priority:
- **`Histograms`** (P0) — no histogram primitive; radix-sort & repetition-stat blocked.
- **unaligned load/store** (`LoadUnAlign*`, `StoreUnAlign*`) — easyasc relies on aligned load + host padding.
- **`Squeeze` count readback** (`GetSpr`/`ClearSpr`) — `gather_mask` compacts but the surviving-count SPR isn't exposed → compact-with-count is hard.
- **fused ops** (`MulAddDst`, `MulsCast`, `AbsSub`, `ExpSub`, `Truncate`) — perf fusions; emulate with the primitive pair (correct, just more instructions).
- **per-lane shift** (`ShiftLeft`/`ShiftRight` by reg), **widening mul** (`Mull`), **carry add/sub** (`AddC`/`SubC`), **`Unsqueeze`**, **`MaskGenWithRegTensor`**, **`CreateAddrReg`** — niche; no easyasc path today.

---

## 2. Canonical recipes (by op-family)

### sort_merge

**Sign-bit flip for sortable floating-point encoding**
When: Sorting floats ascending — IEEE-754 bit order != numeric order (negatives invert under int compare).
Steps: (1) ReinterpretCast value tensor to int32/int16. (2) `Adds`/`Xor` with 0x80000000 (fp32) or 0x8000 (fp16) to flip sign bit. (3) Sort (bitonic or radix) as integer. (4) After `Extract`, ReinterpretCast back to float and flip again to restore. Descending: skip flips.
Ref: ops-math-master/math/sort/op_kernel/arch35/sort_merge_big_batch.h ; merge_sort_simd.h

**4-way merge via MrgSort with validBitTail**
When: Merging 2-4 sorted blocks without O(n^2) re-sort.
Steps: (1) Load up to 4 blocks into UB slices, record counts. (2) Wrap pointers in `MrgSortSrcList` (fill unused slots with list 0, count 0). (3) `MrgSort` with `validBitTail = (1<<listCount)-1`. (4) Copy merged output to cache/GM; repeat until single block.
Ref: ops-math-master/math/sort/op_kernel/arch35/sort_merge_big_batch.h

**Sort struct packing/unpacking via Concat/Extract**
When: `AscendC::Sort` requires [32b-index, 32b-value] interleaved pairs.
Steps: (1) `ArithProgression` index array → `Concat(packed, values, idxTmp, rep)`. (2) `Sort(sorted, packed, idxTmp, sortTmp, rep)`. (3) `Extract(outVals, outIdx, sorted, rep)` to split struct. Keep `rep = CeilDiv(n, DEALING_SORT_NUM_ONCE)` consistent across all three.
Ref: ops-math-master/math/sort/op_kernel/arch35/sort_merge_big_batch.h

**Index array init via Arange + tile offset**
When: Generating original indices for sort-with-index where each block has a logical offset.
Steps: (1) `Arange(vci, 0)` → [0,1,...]. (2) Per block: `Adds(idx, vci, block_id*blockSize, mask)`. (3) Or `ArithProgression(.,base,1,count)` for LocalTensor.
Ref: ops-math-master/math/sort_with_index/op_kernel/arch35/merge_sort_simd.h ; sort_merge_big_batch.h

### histogram_scatter_stat

**Radix-sort histogram via DeInterleave + Histograms**
When: Extract 8-bit radix digit from 32-bit keys per pass; accumulate bin counts (0-255).
Steps: (1) `DataCopy` 32-bit keys. (2) `ShiftRights` by pass*8 to align digit to bits[0,7]. (3) `DeInterleave` uint32→2x uint16→4x uint8 (zero-init the second input each time). (4) `Histograms<.,.,BIN0/BIN1,FREQUENCY/ACCUMULATE>` on uint8. (5) exclusive-sum (`Sub`/`Add` tree) for scatter offsets.
Ref: ops-math-master/math/top_k_v2/op_kernel/arch35/top_k_radix_block_sort_b32.h ; indices_sort_utils.h

**Index-repetition histogram bucketing (sort vs no-sort decision)**
When: Measuring scatter/gather index redundancy via dual XOR-fold histogram + FNV-1a hash.
Steps: (1) Load 256 uint32 indices (4-block batches, DIST_NORM). (2) `ShiftRights` by lastDimShift. (3) XOR-fold 4 bytes→low byte via `ShiftRight`+`Xor` chain (8/16/24). (4) Pack 4 low-bytes→uint8 via nested `DeInterleave`. (5) `Histograms(BIN0)`+`Histograms(BIN1)` accumulate uint8→uint16. (6) FNV view: `Xor`(offset),`Muls`(FNV_PRIME), fold same. (7) `Max(BIN0,BIN1)`→`ReduceMax`; `Compare(>thr)`→`Select(1,0)`→`ReduceSum`. (8) maxScore = sqrt(...); threshold = rowLen/512.
Ref: ops-nn-master/index/scatter_nd_add/op_kernel/arch35/indices_sort_utils.h

**Offset computation via gather-based index multiplication**
When: Convert multi-dim indices to linear offsets by gathering per-dim strides.
Steps: (1) `Duplicate(out, 0)`. (2) Per dim: build `orderReg = Arange(i*vfLen)` then `Muls(rankSize)`; cast to index type if int64; `DataCopyGather(in, base, order, mask)`; `Muls(stride)`; `Add` into out; `Adds(order, +1)`. (3) `DataCopy` out to UB.
Ref: ops-nn-master/index/scatter_nd_add/op_kernel/arch35/scatter_nd_add_common.h

**Deterministic radix Sort for duplicate grouping**
When: scatter_nd_add must group duplicate indices for atomic aggregation.
Steps: (1) Use distinct key/secondary/value tensors (no aliasing). (2) key=shiftSortLocal, secondary=updatesOriginIdex, value=outOfst. (3) `static constexpr sortConfig{RADIX_SORT,false}`; align with `shiftOffset_ = UB_AGLIN_VALUE/sizeof(dtype)`.
Ref: ops-nn-master/index/scatter_nd_add/op_kernel/arch35/scatter_nd_add_common.h

### compact_filter_unique

**Stream-compaction via mask gather + AR counting**
When: Densely pack valid elements selected by predicate; output size varies (unique/filter).
Steps: (1) `ClearSpr<AR>()`. (2) Load input → reg. (3) Build predicate mask (`Compare`/`UpdateMask`). (4) `GatherMask<T,STORE_REG>(dst, src, mask)` to compact. (5) Store via `DataCopyUnAlign<T,POST_MODE_UPDATE>` (increments AR). (6) After loop, `GetSpr<AR>()` / sizeof(T) = count.
Ref: ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_helper.h

**Neighbor-window comparison for change/boundary detection**
When: Detect x[i] != x[i+1] in sorted/dedup sequences (unique_consecutive, unique-ID boundaries).
Steps: (1) Load current window → xPrev. (2) `DataCopyUnAlignPre` at next-element addr. (3) `DataCopyUnAlign` → xNext. (4) `Compare(NE)` → change mask. (5) For int64 mask: `MaskPack<LOWEST>`; for int8/16: `MaskUnPack` to split paths. (6) `GatherMask` the order/index register with the mask. Loop over windows; handle last element separately.
Ref: ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_helper.h ; scatter_nd_add_common.h

**Difference array for run-length / repetition counts**
When: Convert change-point positions to run lengths (positions [0,3,7] → lengths [3,4]); per-unique-ID counts.
Steps: (1) Load index sequence. (2) `Sub(post, pre)` on consecutive pairs (or `PostAdjDiff` helper supplying explicit firstValue). (3) Store diffs; last element needs special handling.
Ref: ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_helper.h ; scatter_nd_add_common.h

### gather_index_lut

**Indexed load from local memory (gather)**
When: Load non-contiguous UB elements via an index register.
Steps: (1) Prepare indices in RegTensor (`Arange`/compute); remember indices are BYTE offsets — `Muls(idx, sizeof(T))`. (2) `DataCopyGather(dst, base, idxReg, mask)`. (3) For unaligned addrs use `DataCopyUnAlignPre`→`DataCopyUnAlign`→`DataCopyUnAlignPost`.
Ref: ops-nn-master/index/gather_nd/op_kernel/arch35/gather_nd_mix.h

**Compare + conditional merge (bounds clamp)**
When: Compute per-lane condition and selectively patch a register (e.g. clamp OOB gather indices).
Steps: (1) `Compare(mask, src0, src1, pred)`. (2) Build compensating reg. (3) `Copy<T,MERGING>(dst, comp, mask)` or `Select` to choose original vs patched.
Ref: ops-nn-master/index/gather_nd/op_kernel/arch35/gather_nd_mix.h

### cast_reinterpret_bittrick

**bf16/fp16 <-> float Cast with UnPack/Pack sandwich**
When: Mixed-precision accumulate (Adam/momentum) — load narrow, compute in float, store narrow.
Steps: (1) `DataCopy` narrow data. (2) `UnPack` int16-view→int32. (3) `Cast(float, ., trait0{UNKNOWN sat/round})`. (4) compute in float. (5) `Cast(bf16, float, trait1{NO_SAT, CAST_RINT})`. (6) `Pack` int32-view→uint16. (7) `MaskPack` mask. (8) `DataCopy` store with packed mask.
Ref: ops-nn-master/optim/apply_adam_w/op_kernel/arch35/apply_adam_w_dag.h

**FP8/FP4 exponent extraction & manipulation**
When: float→FP8/FP4 with manual bias adjust (avoid full-precision divide).
Steps: (1) `Duplicate(mask, 0x7F800000)` exponent mask. (2) `And(exp, reg, mask)`. (3) `ShiftRights(exp, 23)`. (4) `Adds(exp, bias)`; `Maxs` clamp negatives to 0. (5) `Muls`/`Truncate` scale+round. (6) `ShiftLefts(exp, 23)` reconstruct. (7) `Compare`+`Select` to inject sentinels for zero/inf/denorm.
Ref: ops-nn-master/quant/swiglu_mx_quant/op_kernel/arch35/swiglu_mx_quant_last_last.h

**Masked conditional select for exception handling**
When: Inject safe replacements for NaN/Inf/zero during cast/quant.
Steps: (1) `CompareScalar` to identify zeros/negatives. (2) `MaskAnd`/`MaskOr` combine. (3) `Select(result, sentinel, computed, mask)`.
Ref: ops-nn-master/quant/swiglu_mx_quant/op_kernel/arch35/swiglu_mx_quant_last_last.h

### datamove_dist

**Load-compute-store pipeline with POST_MODE_UPDATE**
When: Streaming element-wise op with auto-advancing ptrs.
Steps: (1) `UpdateMask<T>(len)`. (2) `DataCopy<T,POST_MODE_UPDATE>(reg, src, oneRepeat)` (advances src). (3) vector ops with mask. (4) `DataCopy<T,POST_MODE_UPDATE>(dst, reg, oneRepeat, mask)`. (5) loop `repeatTimes = CeilDiv(len, oneRepeat)`, tail uses `UpdateMask(remaining)`.
Ref: ops-nn-master/optim/apply_adam_w/op_kernel/arch35/apply_adam_w_dag.h

**Gather-based strided indexing**
When: Non-contiguous reshapes (as_strided) by computed offsets.
Steps: (1) Pre-compute per-dim stride/size arrays. (2) In `__VEC_SCOPE__`: `Arange`+arithmetic → byte offsets. (3) `DataCopyGather(dst, base, idxReg, mask)`; StoreDist controls packing (DIST_PACK_B16 for uint8). (4) Add a barrier between index compute and gather to avoid stale reads.
Ref: ops-math-master/conversion/as_strided/op_kernel/arch35/as_strided_gather.h

**Reduction with partial masks (full + tail)**
When: Horizontal reduce over full vector then a partial-width tail.
Steps: (1) full `CreateMask<T>()`, tail `UpdateMask<T>(tail)`. (2) `ReduceSum` full. (3) `ReduceSum` tail into temp. (4) `Add` tail into result gated by tail mask. (5) extract scalar with `CreateMask(VL1)` / `GetValue(0)`.
Ref: ops-nn-master/quant/swiglu_mx_quant/op_kernel/arch35/swiglu_mx_quant_last_last.h
---

## 3. Pitfalls (constraints / hazards observed in arch35 code)

| Symptom | Cause | Fix | Ref |
|---|---|---|---|
| Sort/Concat/Extract corrupts data on unaligned/partial blocks | APIs process fixed chunks (32 DEALING_SORT_NUM_ONCE, 16 CONCAT_AGLIN); partial blocks read OOB | Pre-fill aligned region with `Duplicate(±INF/NAN, alignSize)`, then `DataCopyPad(..., actualElem, padParams.isPad=true)`. Use -INF pad ascending, +INF descending | ops-math-master/math/sort/op_kernel/arch35/sort_merge_big_batch.h |
| Extract emits indices misaligned/out-of-order | `rep` inconsistent across Concat/Sort/Extract, or wrong struct-size assumption | Keep `rep = CeilDiv(n, DEALING_SORT_NUM_ONCE)` identical everywhere; struct = 8B (4B idx+4B val); same buffer layout | ops-math-master/math/sort/op_kernel/arch35/sort_merge_big_batch.h |
| MrgSort with <4 lists gives wrong results or crashes | Requires exactly 4 list pointers + validBitTail | Fill unused slots with list 0, count 0; `validBitTail = (1<<listCount)-1` | ops-math-master/math/sort/op_kernel/arch35/sort_merge_big_batch.h |
| Float sort places ±0.0 / NaN/Inf at wrong positions after sign flip | +0.0→0x80000000, -0.0→0x00000000 sort differently | Detect via `CompareScalar(EQ, 0.0/0x7fffffff)` and conditionally `Xor`/`Not` to keep in correct bin | ops-math-master/math/sort/op_kernel/arch35/sort_radix_sort_more_core.h |
| Sort produces reversed/scrambled float output | Missing/inverted sign-bit flip; negatives compare as large signed ints | Ascending: ReinterpretCast→`Adds(0x80000000)` before AND after sort; descending: no flip | ops-math-master/math/sort_with_index/op_kernel/arch35/merge_sort_simd.h |
| Reinterpret bit-trick silently changes value | Used arithmetic `Cast` instead of `ReinterpretCast` | For sign-flip tricks use `LocalTensor.ReinterpretCast<int32_t>()` (zero-copy); reserve `MicroAPI::Cast` for value conversions | ops-math-master/math/sort_with_index/op_kernel/arch35/merge_sort_simd.h |
| Interleave/DeInterleave output transposed/garbled | Mismatched widths or uninitialized second input | Same-type pairs only (u16,u16)->(u32,u32); always `Duplicate(zeroVec,0,mask)` for the paired input | ops-math-master/math/sort/op_kernel/arch35/sort_radix_sort_more_core.h ; indices_sort_utils.h |
| Histogram binning wrong, esp. at block boundaries | DeInterleave needs zero-paired input; tail lanes not masked | `DeInterleave(input_u32, zeroU32)`; `UpdateMask<uint8_t>(n)` then `MaskPack` before Histograms | ops-math-master/math/top_k_v2/op_kernel/arch35/top_k_radix_block_sort_b32.h |
| Histogram overcounts tail lanes; threshold mispredicts | UpdateMask reused across tail iters; uninit lanes accumulated | Recompute `UpdateMask<uint32_t>(tailNum)` before each `Histograms`; never reuse prior-iter mask | ops-nn-master/index/scatter_nd_add/op_kernel/arch35/indices_sort_utils.h |
| ReduceSum/Max/Min result lost or stale; only lane 0 valid | Result lands in lane 0; if mask excludes lane 0 or dst not cleared, garbage | `Duplicate(dst,0,full)` before; ensure mask includes lane 0; extract `GetValue(0)` immediately; for uint16 ReduceMax `And` 0x0000FFFF to clear lane 1 | ops-math-master/math/sort/op_kernel/arch35/sort_radix_sort_more_core.h ; indices_sort_utils.h |
| GatherMask result wrong count / non-contiguous | AR not reset; wrong mask mode (CreateMask ALL vs UpdateMask) | `ClearSpr<AR>()` before; use `UpdateMask` for count-based masks; read AR immediately after GatherMask | ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_helper.h |
| GatherMask selects wrong positions | Arange order reg lacks per-iter offset, or stale Compare mask | Verify `Arange(i*VFLEN)` increments each iter; recompute Compare mask each iter | ops-nn-master/index/scatter_nd_add/op_kernel/arch35/scatter_nd_add_common.h |
| DataCopyGather OOB / garbage / negative-index wrap | Indices are BYTE offsets, not element; no bounds check; signed wrap | `Muls(idx, sizeof(T))`; pre-validate via `Compare(idx,0)`/`Compare(idx,limit)` + `Select` to clamp | ops-nn-master/index/gather_nd/op_kernel/arch35/gather_nd_mix.h ; as_strided_gather.h |
| Gather fetches stale data | No ordering between index compute and gather in same scope | Insert `PipeBarrier<PIPE_V>()` after index compute, before `DataCopyGather` | ops-math-master/conversion/as_strided/op_kernel/arch35/as_strided_gather.h |
| Unaligned DataCopy hangs / corrupts / wrong AR | Missing Pre/Post wrappers; base DataCopy needs block alignment | `DataCopyUnAlignPre(ureg, addr)` → loop `DataCopyUnAlign<T,POST_MODE_UPDATE>` → `DataCopyUnAlignPost(addr, ureg)` | ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_helper.h ; scatter_nd_add_common.h |
| Compaction output interleaved instead of densely packed | GatherMask result not flushed / UB stride mismatch | Immediately store via `DataCopyUnAlign<POST_MODE_UPDATE>` with 32B-aligned dstAddr and matching post stride | ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_helper.h |
| Mask ops fail / wrong lane count on int8 or int64 | Mask width mismatch: int8 has 4x lanes, int64 has 0.5x | int8: `MaskUnPack(LOWEST/HIGHEST)` into sub-masks per quarter; int64: `MaskPack(LOWEST)` to narrow before int32 GatherMask | ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_helper.h ; scatter_nd_add_common.h |
| Cast int64→uint8 yields 0 / truncation | MicroAPI width limit; needs 2-stage int64→int32→uint8 | `Compare(GE,0)` range check, `Cast<int32,U>` then `Cast<uint8,int32>`; remap negatives to U8_MAX via Select | ops-nn-master/index/scatter_nd_add/op_kernel/arch35/scatter_nd_add_common.h |
| Float→bf16/fp16 cast yields 0 / wrong value | Wrong RoundMode (CAST_NONE truncates) or missing UnPack/Pack sandwich | Load: trait0 {SatMode::UNKNOWN, RoundMode::UNKNOWN}; Store: trait1 {NO_SAT, CAST_RINT}; sandwich UnPack(in)/Pack(out) across size boundary | ops-nn-master/optim/apply_adam_w/op_kernel/arch35/apply_adam_w_dag.h |
| Pack/store corrupts data or writes wrong lanes | `MaskPack` skipped before Pack/DIST_PACK store; 16↔32b mask width mismatch | Always `MaskPack(maskOut, maskIn)` before any Pack; mask type must match source element width | ops-nn-master/optim/apply_adam_w/op_kernel/arch35/apply_adam_w_dag.h |
| LoadDist DIST_UNPACK_B32 wrong dtype/count | LoadDist mode must match dst RegTensor dtype; src must be 4B-aligned int32 | Use DIST_UNPACK_B32 only int32→int64 dst, source 4B aligned; or ReinterpretCast<int64> | ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_helper.h |
| DIST_DINTLV_B16 output interleaved opposite to expectation | DIST_DINTLV_B16 de-interleaves on load to two regs | Expect dst1/dst2 de-interleaved; call `Interleave` to restore original order if needed | ops-nn-master/quant/swiglu_mx_quant/op_kernel/arch35/swiglu_mx_quant_last_last.h |
| POST_MODE_UPDATE skips elements / reads past end | oneRepeat miscalc or buffer not multiple of oneRepeat*sizeof(T) | `oneRepeat = VL/sizeof(T)`; `repeatTimes = CeilDiv(len, oneRepeat)`; tail `UpdateMask(remaining)` | ops-nn-master/optim/apply_adam_w/op_kernel/arch35/apply_adam_w_dag.h |
| UpdateMask beyond active lanes corrupts data silently | totalLen > actual remaining; extra lanes still execute | Pass actual count; `repeat=(total+VL-1)/VL`, final mask `total%VL` | ops-nn-master/optim/apply_adam_w/op_kernel/arch35/apply_adam_w_dag.h |
| Mask ops produce garbage with mismatched mask dtype | `CreateMask<T>`/`UpdateMask<T>` T differs from RegTensor<T> | Use identical T across mask creation, ops, and DataCopy | ops-nn-master/quant/swiglu_mx_quant/op_kernel/arch35/swiglu_mx_quant_last_last.h |
| Compare result wrong width/signedness | `Compare<T,CMPMODE>` T mismatches input; int64 needs special variant | Match T exactly; use RegTraitNumTwo variant for int64 pairs; LT/GE/NE safe for all | ops-nn-master/index/gather_nd/op_kernel/arch35/gather_nd_mix.h |
| Masked Duplicate leaves stale unmasked lanes | Duplicate only writes masked lanes | `Duplicate(dst,0,ALL)` first, then masked Duplicate; or guarantee safe prior state | ops-nn-master/index/embedding_dense_grad_v2/op_kernel/v35/embedding_dense_grad_v2_regbase.h |
| CreateAddrReg stride wrong by a factor | Stride is in BYTES not elements | `stride_bytes = block_idx * element_count * sizeof(T)`; verify fits AddrReg width | ops-nn-master/index/gather_nd/op_kernel/arch35/gather_nd_mix.h |
| MrgSort (reg-level) garbled / partially sorted | elementLengths or value_bits mismatch input encoding | Inputs pre-sorted; `elementLengths[i]=actual count`; value_bits matches interleave (0b11/0b111/0b1111) | ops-nn-master/index/top_k_top_p_sample_v2/op_kernel/top_k_top_p_sample_v2_sort_cumsum.h |
| int64 count output corrupted / off by 2x | int64 needs double-width storage; byte count not scaled | Allocate with DOUBLE_OFFSET scaling; copy `copyLen * DOUBLE_OFFSET`; cast int32 intermediate→int64 after PostAdjDiff | ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_single_core_kernel.h |
| PostAdjDiff off-by-one / wrong first element | First diff needs explicit firstValue, not index[0] | `PostAdjDiff(dst, src, firstValue, count, position)` — supply firstValue manually | ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_helper.h |
| Neighbor-window cmp drops last / extra element | x[i] vs x[i+1] leaves last uncompared; off-by-one repeat | `totalNums = nums-1`; loop `CeilDiv(totalNums, VL)`; append final element if IS_TAIL | ops-nn-master/index/unique_consecutive/op_kernel/arch35/unique_consecutive_helper.h |
| Select / CompareScalar result inverted | GE returns true=all-bits-set; arg order or mask semantics confused | `Select(dst, trueVal, falseVal, mask)`: mask true→trueVal; test with known constants per arch | ops-math-master/conversion/as_strided/op_kernel/arch35/as_strided_gather.h |
| RegTensor passed where LocalTensor expected (or vice versa) | Different memory residency; APIs accept one type | Explicit reg cast `(RegTensor<U>&)reg`; `LocalTensor.GetPhyAddr()` for `__local_mem__ T*`; avoid blind ReinterpretCast | ops-math-master/conversion/as_strided/op_kernel/arch35/as_strided_gather.h |
| Sort no-op (output == input) | key/secondary/value aliased, or sortConfig not RADIX | Use distinct tensors; `sortConfig{RADIX_SORT,false}` | ops-nn-master/index/scatter_nd_add/op_kernel/arch35/scatter_nd_add_common.h |
---

## 4. Caveats

- **§1 is authoritative** (from the `reg_compute/*_intf.h` definition headers) — it is the
  complete callable surface, not a sample. Earlier "semantic guess" flags are now resolved:
  `mask_xor` IS a genuine mask-level `Xor` (in `maskreg_intf.h`); `shiftls`/`shiftrs` map cleanly
  to `ShiftLefts`/`ShiftRights` (direction is in the name); `Interleave`/`DeInterleave` and
  `Histograms` ARE defined MicroAPI (not "unknown").
- **§2/§3 are usage-mined** (sampled production kernels), so they show *common* patterns, not every
  possible use. Their file refs are paths only — `grep` the symbol to locate (repos drift).
- **Genuine easyasc.a5 gaps** are consolidated in §1F and prioritized in `dsl_coverage_and_gaps.md`
  — chiefly `Histograms`, unaligned load/store, and `Squeeze` count-readback.
- **Verify arg-order for `Select`/`Compares`** against the header before relying on it — masked-op
  argument conventions are easy to invert.

---

*§1 enumerated from `cann-<ver>/…/asc/include/basic_api/reg_compute/kernel_reg_compute_*_intf.h`
(authoritative API headers — re-enumerate if the CANN version changes). §2/§3 mined from
production arch35 kernels; treat their refs as a search index, not a frozen spec.*
