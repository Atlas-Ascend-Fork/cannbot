### Example Input DSL (kernel config)
```python
L1_M, L1_N, L1_K = 128, 256, 256
DTYPE_C, DTYPE_D = tl.float32, tl.half
layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
layout_b = tl.make_layout(tl.make_shape(K, N), tl.make_stride(N, 1))
layout_c = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
layout_d = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
scheduler = tl.make_scheduler(problem_shape=tl.make_shape(M, N, K),
                              tile_shape=tl.make_shape(L1_M, L1_N),
                              swizzle_offset=3, swizzle_direction=0)
matmul_ready_id = 0
```

### Example Output (AscendC + Catlass config)
```cpp
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
#include "catlass/gemm_coord.hpp"
#include "catlass/matrix_coord.hpp"
using namespace Catlass;

using ArchTag = Arch::AtlasA2;
using LayoutA = layout::RowMajor;
using LayoutB = layout::RowMajor;
using LayoutC = layout::RowMajor;
using LayoutD = layout::RowMajor;
using ElementA = half;
using ElementB = half;
using ElementC = float;
using ElementD = half;

// ===== Mmad DispatchPolicy =====
// For standard fp16 matmul with element-wise epilogue (GELU, SiLU, ReLU, etc.),
// use the simple MmadAtlasA2Pingpong policy. No explicit stage parameters needed.
constexpr bool enableUnitFlag = true;
using MmadDispatchPolicy = Gemm::MmadAtlasA2Pingpong<enableUnitFlag>;

using L1Shape = GemmShape<128, 256, 256>;
using L0Shape = GemmShape<128, 256, 64>;
using AType = Gemm::GemmType<ElementA, LayoutA>;
using BType = Gemm::GemmType<ElementB, LayoutB>;
using CType = Gemm::GemmType<ElementC, LayoutC>;
using DType = Gemm::GemmType<ElementD, LayoutD>;

using BlockMmad = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, AType, BType, CType>;
using BlockScheduler = Gemm::Block::GemmIdentityBlockSwizzle<3, 0>;

constexpr uint32_t matmulReady = 0;
```

### Notes

- **ArchTag**: Use `Arch::AtlasA2` for Atlas A2 series NPUs.
- **Layout types**: `layout::RowMajor` for row-major (stride K,1), `layout::ColMajor` for column-major.
- **Element types**: Match DSL dtypes — `tl.half` → `half`, `tl.float32` → `float`.
- **L1Shape**: Matches DSL `L1_M, L1_N`. L1_K defaults to 256 for fp16 standard matmul.
- **L0Shape**: Usually `GemmShape<L1_M, L1_N, 64>` (L0_K = 64 is hardware-determined for fp16; 128 for int8).
- **BlockScheduler**: Only needed if DSL uses `tl.make_scheduler(...)`. Otherwise use simple manual scheduling.
- **Cross-core event IDs**: Map DSL `matmul_ready_id = 0` → `constexpr uint32_t matmulReady = 0`.

### DispatchPolicy Selection

For standard fp16 matmul, `MmadAtlasA2Pingpong<enableUnitFlag>` is sufficient:
- `enableUnitFlag = true`: Enable MTE unit flag for element-wise epilogue patterns (GELU, SiLU, ReLU, etc.)
- The Pingpong policy uses hardware-default L1/L0 stage counts (L1=2 ping-pong, L0A/L0B=2, L0C=1)

For more advanced use cases (quant matmul, grouped matmul), see the `quant_matmul` kernel config example which uses `MmadAtlasA2PreloadAsyncWithCallback` with explicit stage parameters.

### Catlass Epilogue and Kernel Type Composition (Reference)

The original catlass `27_matmul_gelu` example uses the following Epilogue and Kernel-level type hierarchy. While the lowered AscendC code implements the Vector epilogue manually (using AscendC primitives), this hierarchy documents the operator's structure:

```cpp
// Epilogue DispatchPolicy: element-wise activation with no additional source tensor
using EpilogueDispatchPolicy = Epilogue::EpilogueAtlasA2ElemWiseNoSource;

// Element-wise GELU tile operation
// computeLength = (L1_M / subBlockNum) * L1_N = (128 / 2) * 256 = 16384 elements
constexpr uint32_t computeLength = 16384;  // 64 * 256 = 16384 (in bytes: 64 * 128 * 2B = 16384B)
using TileElemWiseEpilogue = Epilogue::Tile::TileElemWiseGelu<ArchTag, CType, computeLength>;

// Tile copy helpers (2D GM↔UB data movement)
using EpilogueTileCopy = Epilogue::Tile::TileCopy<ArchTag, CType, DType>;

// Block-level epilogue composition
using BlockEpilogue = Epilogue::Block::BlockEpilogue<
    EpilogueDispatchPolicy, CType, DType, TileElemWiseEpilogue, EpilogueTileCopy>;

// Kernel-level type composition (wraps BlockMmad + BlockEpilogue + BlockScheduler)
using MatmulKernel = Gemm::Kernel::MatmulActivation<BlockMmad, BlockEpilogue, BlockScheduler>;
```

### Epilogue DispatchPolicy Types (Reference)

| EpilogueDispatchPolicy | When to Use |
|---|---|
| `EpilogueAtlasA2ElemWiseNoSource` | Element-wise activation (GELU, SiLU, ReLU) — no extra input tensor |
| `EpilogueAtlasA2ElemWiseOneSource` | Element-wise with one extra source (matmul_add, matmul_bias) |
| `EpilogueAtlasA2PerTokenDequant<ubStages>` | Per-token dequantization epilogue (int8 quant matmul) |
| `EpilogueAtlasA2Gemm` | Standard GEMM epilogue (alpha·A·B + beta·C) |
| `EpilogueAtlasA2Gemv` | GEMV epilogue |

### Kernel-Level Types (Reference)

| Kernel Type | When to Use |
|---|---|
| `Gemm::Kernel::MatmulActivation<Mmad, Epilogue, Scheduler>` | Matmul + element-wise activation (GELU, SiLU, ReLU) |
| `Gemm::Kernel::QuantMatmulMultiStageWorkspace<Mmad, Epilogue, Scheduler, workspaceStages>` | Quant matmul with multi-stage workspace pipelining |
