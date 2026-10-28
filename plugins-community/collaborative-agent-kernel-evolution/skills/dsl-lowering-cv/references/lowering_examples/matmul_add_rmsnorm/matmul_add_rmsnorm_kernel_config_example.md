### Example Input DSL (kernel config)
```python
L1_M, L1_N = 128, 256
K_TILE = 1024
DTYPE_C, DTYPE_D = tl.float32, tl.half

layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
layout_b = tl.make_layout(tl.make_shape(K, N), tl.make_stride(N, 1))
layout_c = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
layout_res = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
layout_y = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
layout_xadd = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))

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
using ElementRes = half;
using ElementGamma = half;
using ElementD = half;

using MmadDispatchPolicy = Gemm::MmadAtlasA2Pingpong<true>;
using L1Shape = GemmShape<128, 256, 256>;
using L0Shape = GemmShape<128, 256, 64>;

using AType = Gemm::GemmType<ElementA, LayoutA>;
using BType = Gemm::GemmType<ElementB, LayoutB>;
using CType = Gemm::GemmType<ElementMM, LayoutC>;
using BlockMmad = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, AType, BType, CType>;

constexpr uint32_t MATMUL_DONE = 0;
```

### Notes

- **No BlockScheduler**: Uses per-block_m manual scheduling (same as rms_matmul_scale).
- **Extra element types**: `ElementRes`, `ElementGamma` for the residual and gamma weight tensors (both fp16).
- **`<cmath>` include**: Needed for `sqrtf()` used in inv_rms computation.
- **ElementMM naming**: Using `ElementMM` (matmul accumulation type = float) to distinguish from `ElementD` (output type = half).
