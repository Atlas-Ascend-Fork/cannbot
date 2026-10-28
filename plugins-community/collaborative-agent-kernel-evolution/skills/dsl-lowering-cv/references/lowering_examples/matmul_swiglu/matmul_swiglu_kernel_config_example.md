### Example Input DSL (kernel config)
```python
TWO_N = 2 * N
L1_M, L1_N = 128, 256
DTYPE_C, DTYPE_D = tl.float32, tl.half

layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
layout_b = tl.make_layout(tl.make_shape(K, TWO_N), tl.make_stride(TWO_N, 1))
layout_c = tl.make_layout(tl.make_shape(M, TWO_N), tl.make_stride(TWO_N, 1))
layout_d = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))

matmul_ready_id = 0
```

### Example Output (AscendC + Catlass config)
```cpp
#include "kernel_operator.h"
#include "lib/matmul_intf.h"
#include "catlass/arch/arch.hpp"
#include "catlass/catlass.hpp"
#include "catlass/gemm/block/block_mmad.hpp"
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

constexpr bool enableUnitFlag = true;
using MmadDispatchPolicy = Gemm::MmadAtlasA2Pingpong<enableUnitFlag>;

using L1Shape = GemmShape<128, 256, 256>;
using L0Shape = GemmShape<128, 256, 64>;
using AType = Gemm::GemmType<ElementA, LayoutA>;
using BType = Gemm::GemmType<ElementB, LayoutB>;
using CType = Gemm::GemmType<ElementC, LayoutC>;
using DType = Gemm::GemmType<ElementD, LayoutD>;

using BlockMmad = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, AType, BType, CType>;

constexpr uint32_t matmulReady = 0;
```

### Notes

- **LayoutB stride**: B is K×2N with stride (2N, 1), but the BlockMmad uses the full-width layout. The tile along N dimension covers L1_N columns of the 2N-wide matrix.
- **Same type aliases**: The Catlass types are identical to matmul_gelu — the SwiGLU specifics (split, gate) are entirely in the Vector epilogue.
