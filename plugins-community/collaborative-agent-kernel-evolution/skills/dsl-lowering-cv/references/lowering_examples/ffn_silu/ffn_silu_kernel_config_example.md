### Example Input DSL (kernel config)
```python
L1_M, L1_N = 128, 256
DTYPE_MM = tl.float32
DTYPE_ACT = tl.half
DTYPE_OUT = tl.half

layout_x = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
layout_w1 = tl.make_layout(tl.make_shape(K, N1), tl.make_stride(N1, 1))
layout_mm1 = tl.make_layout(tl.make_shape(M, N1), tl.make_stride(N1, 1))
layout_act = tl.make_layout(tl.make_shape(M, N1), tl.make_stride(N1, 1))
layout_w2 = tl.make_layout(tl.make_shape(N1, N2), tl.make_stride(N2, 1))
layout_mm2 = tl.make_layout(tl.make_shape(M, N2), tl.make_stride(N2, 1))
layout_y = tl.make_layout(tl.make_shape(M, N2), tl.make_stride(N2, 1))

mm1_done_id = 0
act_done_id = 1
mm2_done_id = 2
```

### Example Output (AscendC + Catlass config)
```cpp
#include "kernel_operator.h"
#include "lib/matmul_intf.h"
#include "catlass/arch/arch.hpp"
#include "catlass/arch/resource.hpp"
#include "catlass/arch/cross_core_sync.hpp"
#include "catlass/catlass.hpp"
#include "catlass/gemm/block/block_mmad.hpp"
#include "catlass/gemm/dispatch_policy.hpp"
#include "catlass/gemm/gemm_type.hpp"
#include "catlass/gemm_coord.hpp"
#include "catlass/layout/layout.hpp"
#include "catlass/matrix_coord.hpp"
#include "catlass/epilogue/tile/copy_gm_to_ub.hpp"
#include "catlass/epilogue/tile/copy_ub_to_gm.hpp"
using namespace Catlass;

using ArchTag = Arch::AtlasA2;
using LayoutA = layout::RowMajor;
using LayoutB = layout::RowMajor;
using LayoutC = layout::RowMajor;
using LayoutD = layout::RowMajor;

// Both matmuls share the same element types (fp16 input, fp32 accum)
using ElementInput = half;
using ElementWeight = half;
using ElementMM = float;    // matmul accumulation
using ElementAct = half;    // activation output (input to MM2)
using ElementOut = half;    // final output

using MmadDispatchPolicy = Gemm::MmadAtlasA2Pingpong<true>;
using L1Shape = GemmShape<128, 256, 256>;
using L0Shape = GemmShape<128, 256, 64>;

// MM1: X(M,K) @ W1(K,N1) → workspace_mm1(M,N1) fp32
using AType1 = Gemm::GemmType<ElementInput, LayoutA>;
using BType1 = Gemm::GemmType<ElementWeight, LayoutB>;
using CType1 = Gemm::GemmType<ElementMM, LayoutC>;
using BlockMmad1 = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, AType1, BType1, CType1>;

// MM2: workspace_act(M,N1) @ W2(N1,N2) → workspace_mm2(M,N2) fp32
using AType2 = Gemm::GemmType<ElementAct, LayoutA>;
using BType2 = Gemm::GemmType<ElementWeight, LayoutB>;
using CType2 = Gemm::GemmType<ElementMM, LayoutC>;
using BlockMmad2 = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, AType2, BType2, CType2>;

// 3 cross-core events for the 4-stage pipeline
constexpr uint32_t MM1_DONE = 0;
constexpr uint32_t ACT_DONE = 1;
constexpr uint32_t MM2_DONE = 2;
```

### Notes

- **Dual BlockMmad types**: `BlockMmad1` and `BlockMmad2` differ in AType because MM1 takes fp16 input (X) while MM2 takes fp16 activation output (workspace_act). Both produce fp32 accumulation.
- **3 cross-core events**: MM1_DONE (Cube→Vector after MM1), ACT_DONE (Vector→Cube after SiLU), MM2_DONE (Cube→Vector after MM2).
- **No BlockScheduler**: Per-block_m manual scheduling for both matmul stages.
- **Shared L1Shape/L0Shape**: Both matmuls use the same tile shape (can differ if needed).
