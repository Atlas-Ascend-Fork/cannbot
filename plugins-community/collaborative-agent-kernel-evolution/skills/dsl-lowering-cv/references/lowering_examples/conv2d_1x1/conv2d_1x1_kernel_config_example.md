### Example Input DSL (kernel config)
```python
L1_M, L1_N = 128, 256
DTYPE_C = tl.half  # Fixpipe: output fp16 directly

layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
layout_b = tl.make_layout(tl.make_shape(K, N), tl.make_stride(N, 1))
layout_d = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
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
#include "catlass/gemm_coord.hpp"
#include "catlass/matrix_coord.hpp"
using namespace Catlass;

using ArchTag = Arch::AtlasA2;
using LayoutA = layout::RowMajor;
using LayoutB = layout::RowMajor;
using LayoutD = layout::RowMajor;
using ElementA = half;
using ElementB = half;
// Fixpipe: ElementC = half (Cube outputs fp16 directly, no fp32 accumulator exposed)
using ElementC = half;

constexpr bool enableUnitFlag = true;
using MmadDispatchPolicy = Gemm::MmadAtlasA2Pingpong<enableUnitFlag>;

using L1Shape = GemmShape<128, 256, 256>;
using L0Shape = GemmShape<128, 256, 64>;
using AType = Gemm::GemmType<ElementA, LayoutA>;
using BType = Gemm::GemmType<ElementB, LayoutB>;
using CType = Gemm::GemmType<ElementC, LayoutD>;

using BlockMmad = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, AType, BType, CType>;
```

### Notes

- **Fixpipe pattern**: `ElementC = half` means Cube Fixpipe hardware casts fp32→fp16 automatically. No separate Vector scope needed.
- **Identical to standard matmul Fixpipe**: Since 1x1 conv is pure matmul after reshape, the kernel config is the same as any matmul Fixpipe pattern.
- **No ElementD**: In Fixpipe, Cube writes directly to the output tensor (D), so there's no separate D type — C IS the output.
