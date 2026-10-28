### Key Differences from Standard fp16 MatMul

- **int8 element types**: `ElementA = int8_t`, `ElementB = int8_t`
- **int32 accumulation**: `ElementC = int32_t` (matmul output to workspace)
- **L1_K=512, L0_K=128**: int8 elements are 1 byte (not 2 bytes like fp16), so K dimensions double
- **DispatchPolicy**: `MmadAtlasA2Pingpong<false>` — NOT `PreloadAsyncWithCallback` (see note below)
- **Workspace double-buffering**: `WORKSPACE_STAGES = 2` with per-stage cross-core flags
- **Epilogue tile operations**: `TileRowBroadcastMul`, `TileBroadcastOneBlk`, `TileOneBlkColumnBroadcastMul` for vectorized dequant
- **2D copy helpers**: `CopyGm2Ub` / `CopyUb2Gm` for tile-based workspace↔output transfers
- **EPILOGUE_TILE_M = 32**: Sub-tile size for epilogue processing within L1_M × L1_N tiles

### Example Input DSL (kernel config)
```python
L1_M, L1_N, L1_K = 128, 256, 512  # int8: L1_K doubles from 256 to 512
DTYPE_A, DTYPE_B = tl.int8, tl.int8
DTYPE_C = tl.int32   # matmul accumulation
DTYPE_D = tl.half    # final output after dequant
layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))      # RowMajor
layout_b = tl.make_layout(tl.make_shape(K, N), tl.make_stride(N, 1))      # RowMajor (B stored as [K,N])
layout_c = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
layout_d = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
scheduler = tl.make_scheduler(problem_shape=tl.make_shape(M, N, K),
                              tile_shape=tl.make_shape(L1_M, L1_N),
                              swizzle_offset=3, swizzle_direction=0)
WORKSPACE_STAGES = 2
EPILOGUE_TILE_M = 32
```

### Example Output (AscendC + Catlass config)
```cpp
#ifndef K_MAX_SHAPE_DIM
#define K_MAX_SHAPE_DIM 0
#endif

#include "kernel_operator.h"
#include "lib/matmul_intf.h"
#include "catlass/arch/arch.hpp"
#include "catlass/catlass.hpp"
#include "catlass/gemm/block/block_mmad.hpp"
#include "catlass/gemm/block/block_swizzle.hpp"
#include "catlass/gemm/dispatch_policy.hpp"
#include "catlass/gemm/gemm_type.hpp"
#include "catlass/layout/layout.hpp"
#include "catlass/arch/resource.hpp"
#include "catlass/arch/cross_core_sync.hpp"
#include "catlass/epilogue/tile/copy_gm_to_ub.hpp"
#include "catlass/epilogue/tile/copy_ub_to_gm.hpp"
#include "catlass/epilogue/tile/tile_broadcast_mul.hpp"
#include "catlass/epilogue/tile/tile_broadcast_one_blk.hpp"
#include "catlass/gemm_coord.hpp"
#include "catlass/matrix_coord.hpp"
using namespace Catlass;

using ArchTag = Arch::AtlasA2;
using ElementA = int8_t;
using ElementB = int8_t;
using ElementC = int32_t;  // matmul accumulation type
using ElementD = half;     // final output type after dequant

using LayoutA = layout::RowMajor;
using LayoutB = layout::RowMajor;     // B is [K, N], stored as RowMajor(K, N)
using LayoutC = layout::RowMajor;
using LayoutD = layout::RowMajor;

// ===== Mmad DispatchPolicy =====
// Use Pingpong<false> for int8 quant matmul.
// ENABLE_UNIT_FLAG must be false for int8.
//
// Why NOT PreloadAsyncWithCallback:
//   PreloadAsyncWithCallback requires lambda callbacks (callbackBeforeFixpipe,
//   callbackAfterFixpipe) that capture [host] context. AscendC __aicore__ functions
//   cannot invoke [host] lambdas. The catlass reference avoids this via nested structs
//   with CATLASS_DEVICE operator()(), but manual kernel code cannot replicate this
//   pattern. Pingpong<false> provides correct behavior for int8 with no callback
//   requirement.
using MmadDispatchPolicy = Gemm::MmadAtlasA2Pingpong<false>;

// int8: L1_K=512, L0_K=128 (1 byte per element → double fp16 counts of 256/64)
using L1Shape = GemmShape<128, 256, 512>;
using L0Shape = GemmShape<128, 256, 128>;
using AType = Gemm::GemmType<ElementA, LayoutA>;
using BType = Gemm::GemmType<ElementB, LayoutB>;
using CType = Gemm::GemmType<ElementC, LayoutC>;
using DType = Gemm::GemmType<ElementD, LayoutD>;

using BlockMmad = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, AType, BType, CType>;
using BlockScheduler = Gemm::Block::GemmIdentityBlockSwizzle<3, 0>;

// ===== Workspace Double-Buffering =====
// AIC writes to slot[s] while AIV reads slot[s^1]. Each slot = L1_M * L1_N elements.
constexpr uint32_t WORKSPACE_STAGES = 2;

// Per-stage cross-core flag IDs:
//   flagAicStore[s]   = FLAG_AIC_STORE_BASE + s * 2
//   flagAivCompute[s] = FLAG_AIV_COMPUTE_BASE + s * 2
constexpr uint32_t FLAG_AIC_STORE_BASE = 0;
constexpr uint32_t FLAG_AIV_COMPUTE_BASE = 1;

// ===== Epilogue Tile Processing =====
// Process EPILOGUE_TILE_M rows at a time within each L1_M × L1_N tile
constexpr uint32_t EPILOGUE_TILE_M = 32;
using EpilogueTileShape = MatrixShape<EPILOGUE_TILE_M, L1Shape::N>;
using ComputeType = Gemm::GemmType<float, layout::RowMajor>;

// Scale: row-broadcast multiply — each row × shared Scale[N] vector
using TileRowBroadMul = Epilogue::Tile::TileRowBroadcastMul<ArchTag, ComputeType, EpilogueTileShape>;

// PerTokenScale: expand (M,1) → (M, eleNumPerBlk) via hardware Brcb scatter
using TileBrcbOneBlk = Epilogue::Tile::TileBroadcastOneBlk<ArchTag, ComputeType, EPILOGUE_TILE_M>;

// PerTokenScale: column-broadcast multiply over full tile
using TileColBroadMul = Epilogue::Tile::TileOneBlkColumnBroadcastMul<ArchTag, ComputeType, EpilogueTileShape>;
```

### DispatchPolicy Selection Guide

| DispatchPolicy | When to Use | Template Parameters |
|---|---|---|
| `MmadAtlasA2Pingpong<enableUnitFlag>` | Standard fp16 matmul OR int8 quant matmul (manual kernel) | `<bool>` |
| `MmadAtlasA2Preload<enableUnitFlag, enableShuffleK>` | Optimized fp16 matmul with preload | `<bool, bool>` |
| `MmadAtlasA2PreloadAsync<preload, l1, l0A, l0B, l0C, unitFlag, shuffleK>` | Grouped matmul with async preload | `<uint32_t × 5, bool × 2>` |
| `MmadAtlasA2PreloadAsyncWithCallback<...>` | Catlass device-level API only (requires nested struct callbacks — not usable in manual kernels) | `<uint32_t × 5, bool × 2>` |

**Selection rule for manual kernels**: Use `Pingpong<false>` for int8 quant matmul. Use `Pingpong<true>` for standard fp16 matmul. `PreloadAsyncWithCallback` is only viable in the Catlass device-level API where nested structs with `CATLASS_DEVICE operator()()` provide the callback mechanism.

### Notes

- **int8 L1/L0 K dimensions**: Hardware processes a fixed number of bytes per cycle. int8 = 1 byte, fp16 = 2 bytes. So int8 K dimensions are 2x larger: L1_K=512 (vs 256), L0_K=128 (vs 64).
- **RowMajor for B=[K,N]**: When B is stored as [K, N] in memory, use `layout::RowMajor` and construct `LayoutB(K, N)`. When B is stored as [N, K] (transposed weight), use `layout::ColumnMajor` and construct `LayoutB(K, N)`.
- **2D copy helpers required**: The optimized dequant epilogue uses `CopyGm2Ub`/`CopyUb2Gm` for 2D tile transfers (not row-by-row DataCopyPad). Include `copy_gm_to_ub.hpp` and `copy_ub_to_gm.hpp`.
- **Tile broadcast headers**: Include `tile_broadcast_mul.hpp` and `tile_broadcast_one_blk.hpp` for `TileRowBroadcastMul`, `TileBroadcastOneBlk`, and `TileOneBlkColumnBroadcastMul`.
- **ElementC = int32_t**: int8 × int8 matmul accumulates into int32. The dequant epilogue (KernelVector) converts int32 → float → fp16.
- **Per-stage flags vs single event**: Instead of a single `matmulReady` event ID, use per-stage flag arrays. This allows the Cube to start writing the next tile's workspace slot before Vector finishes with the current one.
- **EPILOGUE_TILE_M = 32**: Processing 32 rows at a time balances UB memory usage against DMA efficiency. The full L1_M (128) tile is split into L1_M/EPILOGUE_TILE_M sub-tiles.

### Catlass Epilogue Type Composition (Reference)

The original catlass example uses a full Epilogue type hierarchy for the device-level API. While the lowered AscendC code implements the Vector epilogue manually, understanding this hierarchy helps verify correctness:

```cpp
// Epilogue DispatchPolicy for per-token dequantization with UB double-buffering
constexpr uint32_t ubStages = 2;
using EpilogueDispatchPolicy = Epilogue::EpilogueAtlasA2PerTokenDequant<ubStages>;

// Epilogue tile types (for reference — lowered code implements these manually)
using ScaleType = Gemm::GemmType<float, layout::VectorLayout>;
using PerTokenScaleType = Gemm::GemmType<float, layout::VectorLayout>;

using EpilogueTileShape = MatrixShape<32, 256>;
using TileRowBroadcastMul = Epilogue::Tile::TileRowBroadcastMul<ArchTag, ComputeType, EpilogueTileShape>;
using TileBroadcastOneBlk = Epilogue::Tile::TileBroadcastOneBlk<ArchTag, ComputeType, EpilogueTileShape::ROW>;
using TileOneBlkColumnBroadcastMul = Epilogue::Tile::TileOneBlkColumnBroadcastMul<ArchTag, ComputeType, EpilogueTileShape>;
using TileCopy = Epilogue::Tile::TileCopy<ArchTag, CType, ScaleType, PerTokenScaleType, DType>;
using TileScheduler = Epilogue::Tile::EpilogueHorizontalTileSwizzle;

using BlockEpilogue = Epilogue::Block::BlockEpilogue<
    EpilogueDispatchPolicy, CType, ScaleType, PerTokenScaleType, DType,
    TileRowBroadcastMul, TileBroadcastOneBlk, TileOneBlkColumnBroadcastMul, TileCopy, TileScheduler>;

// Kernel-level type (wraps BlockMmad + BlockEpilogue + BlockScheduler + workspaceStages)
using MatmulKernel = Gemm::Kernel::QuantMatmulMultiStageWorkspace<
    BlockMmad, BlockEpilogue, BlockScheduler, WORKSPACE_STAGES>;
```
