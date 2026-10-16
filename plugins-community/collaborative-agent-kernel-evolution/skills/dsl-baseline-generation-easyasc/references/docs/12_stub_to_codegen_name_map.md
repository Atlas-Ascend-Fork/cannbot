# Stub to Codegen Name Map

This file is a quick lookup when you have a public helper name from `easyasc.a2` or `easyasc.a5` and want to find the emitted C++ helper, macro, or inline form in generated code.

Read this after [Code Generation and Runtime](06_codegen_and_runtime.md) if you need the full lowering flow.
This file does not explain semantics, legality, or simulator behavior.

## Scope

- "A2" means the `easyasc.a2` surface and the `device_type.startswith("b")` codegen path.
- "A5" means the `easyasc.a5` surface and the `device_type == "950"` codegen path.
- Generated names below come from `easyasc/parser/asc_handlers/`.
- Tables below describe names exported from the `easyasc.a2` and `easyasc.a5` top-level modules, not every helper file that happens to exist under `easyasc/stub_functions/`.
- Some helpers generate a view declaration or inline expression instead of a single runtime helper call.
- `sim_print` and `sim_dump_tensor` are simulator-only; they do not emit generated C++ statements.
- `easyasc.a5` imports `stub_functions.micro` after `stub_functions`, so several top-level names are intentionally shadowed by A5 micro helpers.

## One Important Difference First

The same top-level name does not always mean the same helper family on A2 and A5.

```python
from easyasc.a2 import add   # vec Tensor helper
from easyasc.a5 import add   # micro Reg helper
```

That means the generated names below should be read against the public import surface, not just the raw file name under `easyasc/stub_functions/`.

## Same Top-Level Name, Different Lowering Family

These names exist on both `easyasc.a2` and `easyasc.a5`, but they lower through different handler families.

| Top-level name(s) | `easyasc.a2` source | A2 generated symbol(s) | `easyasc.a5` source | A5 generated symbol(s) | Notes |
| --- | --- | --- | --- | --- | --- |
| `add`, `sub`, `mul`, `div`, `vmax`, `vmin`, `vand`, `vor` | `stub_functions.vec.binary` | `Add`, `Sub`, `Mul`, `Div`, `Max`, `Min`, `And`, `Or` | `stub_functions.micro.binary` | `MicroAPI::Add`, `MicroAPI::Sub`, `MicroAPI::Mul`, `MicroAPI::Div`, `MicroAPI::Max`, `MicroAPI::Min`, `MicroAPI::And`, `MicroAPI::Or` | A2 row is a vec Tensor op. A5 row is a micro Reg op. |
| `exp`, `ln`, `abs`, `relu`, `sqrt`, `vnot` | `stub_functions.vec.unary` | `Exp`, `Ln`, `Abs`, `Relu`, `Sqrt`, `Not` | `stub_functions.micro.unary` | `MicroAPI::Exp`, `MicroAPI::Ln`, `MicroAPI::Abs`, `MicroAPI::Relu`, `MicroAPI::Sqrt`, `MicroAPI::Not` | Same public names, different execution layer. |
| `adds`, `muls`, `vmaxs`, `vmins`, `lrelu`, `axpy` | `stub_functions.vec.unaryscalar` | `Adds`, `Muls`, `Maxs`, `Mins`, `LeakyRelu`, `Axpy` | `stub_functions.micro.unaryscalar` | `MicroAPI::Adds`, `MicroAPI::Muls`, `MicroAPI::Maxs`, `MicroAPI::Mins`, `MicroAPI::LeakyRelu`, `MicroAPI::Axpy` | A5 scalar ops work on Reg + MaskReg, not vec Tensor tiles. |
| `cast` | `stub_functions.vec.cast` | `Cast<dst, src, false>(..., RoundMode::...)` | `stub_functions.micro.cast` | `MicroAPI::Cast<dst, src, config>(...)` | A5 micro cast takes a `CastConfig` template argument. |
| `compare`, `select` | `stub_functions.vec.compare`, `stub_functions.vec.select` | `Compare`, `CompareScalar`, `Select` | `stub_functions.micro.compare` | `MicroAPI::Compare`, `MicroAPI::CompareScalar`, `MicroAPI::Select` | `easyasc.a5.select` comes from the micro compare module, not vec select. |
| `dup` | `stub_functions.vec.dupbrcb` | `Duplicate` | `stub_functions.micro.dup` | `MicroAPI::Duplicate` | Same name, different operand kinds. |
| `cadd`, `cgadd`, `cpadd`, `cmax`, `cgmax`, `cmin`, `cgmin` | `stub_functions.vec.group` | `WholeReduceSum`, `BlockReduceSum`, `PairReduceSum`, `WholeReduceMax`, `BlockReduceMax`, `WholeReduceMin`, `BlockReduceMin` | `stub_functions.micro.group` | `MicroAPI::ReduceSum`, `MicroAPI::ReduceSumWithDataBlock`, `MicroAPI::PairReduceSum`, `MicroAPI::ReduceMax`, `MicroAPI::ReduceMaxWithDataBlock`, `MicroAPI::ReduceMin`, `MicroAPI::ReduceMinWithDataBlock` | The public names match, but the reduction layer does not. |
| `gather` | `stub_functions.vec.gatherscatter` | `Gather` | `stub_functions.micro.datamove` | `MicroAPI::Gather` | A2 gather uses vec Tensor + offset. A5 gather uses Reg + index Reg. |

## Shared Top-Level Names

These helpers keep the same top-level meaning across A2 and A5.

### Scalar and Shape Helpers

| Helper | A2 generated form | A5 generated form | Notes |
| --- | --- | --- | --- |
| `GetCubeNum` | `GetBlockNum()` | `GetBlockNum()` | Scalar helper. |
| `GetCubeIdx` | `get_block_idx()` | `get_block_idx()` | Scalar helper. |
| `GetVecNum` | `GetBlockNum() * 2` | `GetBlockNum() * 2` | Current lowering assumes two vec sub-blocks per cube block. |
| `GetVecIdx` | `GetBlockIdx()` | `GetBlockIdx()` | Scalar helper. |
| `GetSubBlockIdx` | `get_subblockid()` | `get_subblockid()` | Scalar helper. |
| `CeilDiv` | `CeilDiv(...)` | `CeilDiv(...)` | Direct helper call. |
| `Min`, `Max` | `Min(...)`, `Max(...)` | `Min(...)`, `Max(...)` | Direct helper call. |
| `Align8`, `Align16`, `Align32`, `Align64`, `Align128`, `Align256` | `Align8B`, `Align16B`, `Align32B`, `Align64B`, `Align128B`, `Align256B` | same | The stub names map to byte-alignment helpers with `B` suffixes. |
| `scalar_sqrt` | `sqrt(...)` | `sqrt(...)` | Inline scalar expression. |
| `var_mul`, `var_add`, `var_sub`, `var_div`, `var_mod` | inline `*`, `+`, `-`, `/`, `%` expressions | same | Lowered as scalar expressions, not helper calls. |

### Cube and On-Chip Data Movement

| Helper | A2 generated symbol(s) | A5 generated symbol(s) | Notes |
| --- | --- | --- | --- |
| `gm_to_l1_nd2nz` | `GM2L1_ND2ZZ` for float `L1` destinations, otherwise `GM2L1_ND2NZ` | `GM2L1_ND2NZ` | The main family-specific cube datamove name difference. |
| `set_constant_to_l1` | `InitConstValue` | `InitConstValue` | Constant-fill helper. |
| `l1_to_l0` | float `L1`: `L0ZZ2ZZ`, `L0ZZ2NN`, `L0ZZ2NZ`, `L0ZZ2ZN`<br>non-float `L1`: `L0NZ2ZZ`, `L0NZ2NN`, `L0NZ2NZ`, `L0NZ2ZN` | `L0NZ2NZ` or `L0NZ2ZN` | On A2, dtype and transpose both affect the emitted name. On A5, the handler always uses the NZ-source family. |
| `mmad` | `MMAD` | `MMAD` | Shared cube compute helper. |
| `l0c_to_gm_nz2nd` | `L0C2GM_NZ2ND` | `L0C2GM_NZ2ND` | Shared writeback helper. |
| `l0c_to_l1` | `L0C2L1` | `L0C2L1` | Shared on-chip handoff helper. |
| `l0c_to_ub` | not exported by `easyasc.a2` | `L0C2UB_NZ2ND` | Available from `easyasc.a5` only. |

### Shared Vec and UB Helpers

| Helper | A2 generated symbol(s) | A5 generated symbol(s) | Notes |
| --- | --- | --- | --- |
| `gm_to_ub_pad`, `ub_to_gm_pad`, `ub_to_ub` | `GM2UBPAD`, `UB2GMPAD`, `UB2UB` | same | Shared vec datamove helpers. |

## A2-Only Top-Level Helpers

These names are exported from `easyasc.a2`, but not from `easyasc.a5`.

| A2-only helper(s) | A2 generated symbol(s) | Notes |
| --- | --- | --- |
| `rec`, `rsqrt` | `Reciprocal`, `Rsqrt` | Vec unary helpers that are not re-exported from `easyasc.a5`. |
| `brcb` | `Brcb` | Vec broadcast helper available only from the A2 top-level surface. |
| `scatter` | `Scatter` | A5 exports micro `reg_to_ub_scatter`, not top-level vec `scatter`. |
| `compare_scalar` | `CompareScalar` | Kept as a separate top-level helper on A2. |
| `muladddst` | `MulAddDst` | A2 top-level helper only. |
| `sort32`, `mergesort4`, `mergesort_2seq` | `Sort32`, `MERGESORT4`, `MERGESORT2SEQ` | Sort helpers are not re-exported from `easyasc.a5`. |
| `set_mask`, `reset_mask` | `SetVectorMask<half, MaskMode::NORMAL>`, `ResetMask` | Vec mask helpers exported only from `easyasc.a2`. |
| `set_cmpmask` | `SetCmpMask` | Compare-mask helper exported only from `easyasc.a2`. |

### Synchronization, Atomic, and Misc Helpers

| Helper | A2 generated form | A5 generated form | Notes |
| --- | --- | --- | --- |
| `bar_m`, `bar_v`, `bar_mte3`, `bar_mte2`, `bar_mte1`, `bar_fix`, `bar_all` | `PipeBarrier<PIPE_M/V/MTE3/MTE2/MTE1/FIX/ALL>()` | same | The public wrappers all lower through one `barrier` instruction. |
| `cube_ready`, `vec_ready`, `wait_cube`, `wait_vec`, `allcube_ready`, `allvec_ready`, `allcube_wait`, `allvec_wait` | `CUBE_READY`, `VEC_READY`, `WAIT_CUBE`, `WAIT_VEC`, `ALLCUBE_READY`, `ALLVEC_READY`, `ALLCUBE_WAIT`, `ALLVEC_WAIT` | same | Cross-core flag helpers. |
| `setflag`, `waitflag` | `set_flag`, `wait_flag` | same | Pipe event instructions, not `SEvent`/`DEvent` objects. |
| `atomic_add`, `atomic_max`, `atomic_min` | `SetAtomicAdd<float>()`, `SetAtomicMax<float>()`, `SetAtomicMin<float>()` | same | The context-manager exit emits `SetAtomicNone()`. |
| `reset_cache` | `pipe_ptr->Reset();` and `OccupyMMTE1Events();` | same | Parser lowering emits the raw helper calls; kernel header emission comments out only the auto-inserted prologue pair in generated `_cube.h` / `_vec.h`, while user-written `reset_cache` calls remain raw. |
| `clean_dcache` | `DataCacheCleanAndInvalid<...>` | same | Emits a templated cache-line helper. |
| `split_workspace` | `shiftAddr<dtype>(workspace, ...)` plus `SetGlobalBuffer(...)` | same | Generates a GM workspace view, not a single helper call. |
| `reinterpret` | `ReinterpretCast<dst_dtype>()` | same | Generates a local tensor view. |
| `kernel_print` | `printf(...)` | same | Generation-time debug print. |
| `kernel_dump_tensor` | `DumpTensor(...)` | same | Generation-time dump hook. |
| `inline` | literal inline C++ | same | No wrapper helper; the source is emitted directly. |
| `sim_print`, `sim_dump_tensor` | not exported by `easyasc.a2` | no generated code | Simulator-only helpers exported by `easyasc.a5`. |

## A5-Only Top-Level Helpers

These names exist only on the `easyasc.a5` top-level surface.

### Micro Register and Mask Families

| A5-only helper(s) | A5 generated symbol(s) | Notes |
| --- | --- | --- |
| `arange` | `MicroAPI::Arange` | A5-only micro helper. |
| `vxor`, `prelu` | `MicroAPI::Xor`, `MicroAPI::Prelu` | Extra micro binary helpers not exposed from `easyasc.a2`. |
| `log`, `log2`, `log10`, `neg`, `vcopy` | `MicroAPI::Log`, `MicroAPI::Log2`, `MicroAPI::Log10`, `MicroAPI::Neg`, `MicroAPI::Copy` | Extra micro unary helpers. |
| `shiftls`, `shiftrs` | `MicroAPI::ShiftLefts`, `MicroAPI::ShiftRights` | A5-only micro scalar helpers. |
| `deinterleave`, `interleave` | `MicroAPI::DeInterleave`, `MicroAPI::Interleave` | Register-lane rearrangement helpers. |
| `ub_to_l1_nd2nz`, `ub_to_l1_nz` | `UB2L1_ND2NZ`, `UB2L1_NZ` | Vec-to-L1 publish helpers exported only from `easyasc.a5`. |
| `ub_to_reg`, `reg_to_ub` | `MicroAPI::DataCopy<..., MicroAPI::DataCopyMode::DATA_BLOCK_COPY>` | The base A5 micro datacopy pair. |
| `ub_to_reg_continuous`, `reg_to_ub_continuous` | `MicroAPI::DataCopy<..., MicroAPI::LoadDist::...>` / `MicroAPI::DataCopy<..., MicroAPI::StoreDist::...>` | Distribution mode selects the exact emitted specialization. |
| `reg_to_ub_downsample`, `reg_to_ub_pack4`, `reg_to_ub_single`, `ub_to_reg_single`, `ub_to_reg_upsample`, `ub_to_reg_downsample`, `ub_to_reg_unpack`, `ub_to_reg_unpack4`, `ub_to_reg_brcb` | same `MicroAPI::DataCopy` family as above | These are convenience wrappers that pick `LoadDist` / `StoreDist` modes before the same codegen handler runs. |
| `ub_to_reg_gather`, `reg_to_ub_scatter`, `gather_mask` | `MicroAPI::DataCopyGather`, `MicroAPI::DataCopyScatter`, `MicroAPI::GatherMask` | A5-only micro datamove helpers. |
| `mask_not`, `mask_and`, `mask_or`, `mask_xor`, `mask_mov`, `mask_interleave`, `mask_deinterleave`, `mask_sel` | `MicroAPI::MaskNot`, `MaskAnd`, `MaskOr`, `MaskXor`, `MaskMov`, `MaskInterleave`, `MaskDeInterleave`, `MaskSel` | Mask-register operations. |
| `move_mask_spr`, `update_mask` | `MicroAPI::MoveMask`, `MicroAPI::UpdateMask` | Return values are assigned into `MaskReg` objects. |
| `mask_pack`, `mask_unpack` | `MicroAPI::MaskPack<...>`, `MicroAPI::MaskUnPack<...>` | Mode is encoded as a template argument. |
| `LoadDist`, `LoadDistValue`, `StoreDist`, `StoreDistValue` | no emitted code by themselves | These are configuration enums used by the A5 micro datamove wrappers. |

## Source Paths for Verification

Use these files when you want to confirm or extend the table:

- public surfaces: `easyasc/a2.py`, `easyasc/a5.py`
- handler registry: `easyasc/parser/asc_handlers/__init__.py`
- scalar helpers: `easyasc/parser/asc_handlers/math_ops.py`
- cube helpers: `easyasc/parser/asc_handlers/cube.py`
- vec helpers: `easyasc/parser/asc_handlers/vec_binary.py`, `vec_unary.py`, `vec_unary_scalar.py`, `vec_group.py`, `vec_dupbrcb.py`, `vec_gatherscatter.py`, `vec_datamove.py`, `vec_cast.py`, `vec_compare.py`, `vec_select.py`, `vec_sort.py`, `vec_mask.py`
- sync and misc: `easyasc/parser/asc_handlers/pipe_ops.py`, `atomic.py`, `misc.py`, `core.py`, `reinterpret.py`
- A5 micro helpers: `easyasc/parser/asc_handlers/vec_micro_ops.py`
