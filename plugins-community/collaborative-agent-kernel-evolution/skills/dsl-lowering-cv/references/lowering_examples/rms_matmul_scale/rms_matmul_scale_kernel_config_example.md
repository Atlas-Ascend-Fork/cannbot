### Example Input DSL (kernel config)
```python
L1_M, L1_N = 128, 256
K_TILE = 1024
DTYPE_X = tl.half
DTYPE_MM = tl.float32
DTYPE_OUT = tl.half

layout_x = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
layout_w = tl.make_layout(tl.make_shape(K, O), tl.make_stride(O, 1))
layout_mm = tl.make_layout(tl.make_shape(M, O), tl.make_stride(O, 1))
layout_out = tl.make_layout(tl.make_shape(M, O), tl.make_stride(O, 1))

matmul_done_id = 0
```

### Example Output (AscendC + Catlass config)
```cpp
#include <cmath>
#include "kernel_operator.h"
#include "lib/matmul_intf.h"
#include "catlass/arch/arch.hpp"
#include "catlass/arch/resource.hpp"
#include "catlass/catlass.hpp"
#include "catlass/gemm/block/block_mmad.hpp"
#include "catlass/gemm/dispatch_policy.hpp"
#include "catlass/gemm/gemm_type.hpp"
#include "catlass/gemm_coord.hpp"
#include "catlass/layout/layout.hpp"
#include "catlass/matrix_coord.hpp"
using namespace Catlass;

using ArchTag = Arch::AtlasA2;
using LayoutA = layout::RowMajor;
using LayoutB = layout::RowMajor;
using LayoutC = layout::RowMajor;
using LayoutD = layout::RowMajor;

using ElementA = half;
using ElementB = half;
using ElementMM = float;
using ElementD = half;

using MmadDispatchPolicy = Gemm::MmadAtlasA2Pingpong<true>;
using L1Shape = GemmShape<128, 256, 256>;
using L0Shape = GemmShape<128, 256, 64>;

using AType = Gemm::GemmType<ElementA, LayoutA>;
using BType = Gemm::GemmType<ElementB, LayoutB>;
using CType = Gemm::GemmType<ElementMM, LayoutC>;
using BlockMmad = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, AType, BType, CType>;

constexpr uint32_t MATMUL_READY = 0;
constexpr uint32_t REDUCE_TILE_K = 1024;
```

### Notes

- **No BlockScheduler**: When DSL does not use `tl.make_scheduler(...)`, do NOT create a `BlockScheduler`. Use manual loop scheduling instead.
- **Additional constants**: Vector-specific constants like `REDUCE_TILE_K` (K-axis UB tile size) are defined here.
- **Element type naming**: When the intermediate and output types differ, use descriptive names like `ElementMM` (matmul accumulation) vs `ElementD` (final output).
- **No DType for input types that match**: `ElementA = half` and `ElementB = half` correspond to `DTYPE_X = tl.half`.
