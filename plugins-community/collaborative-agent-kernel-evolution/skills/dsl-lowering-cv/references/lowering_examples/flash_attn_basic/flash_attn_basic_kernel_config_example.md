### Example Input DSL (kernel config)
```python
L1_M = 128
DTYPE_SCORE = tl.float32
DTYPE_PROB = tl.half
DTYPE_OUT = tl.float32
DTYPE_FINAL = tl.half

layout_q = tl.make_layout(tl.make_shape(M, D), tl.make_stride(D, 1))
layout_k = tl.make_layout(tl.make_shape(N, D), tl.make_stride(D, 1))  # K stored as (N, D)
layout_v = tl.make_layout(tl.make_shape(N, D), tl.make_stride(D, 1))
layout_score = tl.make_layout(tl.make_shape(M, Bk), tl.make_stride(Bk, 1))
layout_prob = tl.make_layout(tl.make_shape(M, Bk), tl.make_stride(Bk, 1))
layout_out = tl.make_layout(tl.make_shape(M, D), tl.make_stride(D, 1))
layout_o = tl.make_layout(tl.make_shape(M, D), tl.make_stride(D, 1))

score_ready_id = 0
prob_ready_id = 1
out_ready_id = 2
update_done_id = 3
```

### Example Output (AscendC + Catlass config)
```cpp
#include <cmath>
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
using namespace Catlass;

using ArchTag = Arch::AtlasA2;

// BMM1: Q(M,D) @ K_b^T(D,Bk) → Score(M,Bk) fp32
// K is stored row-major (N,D), and we take a (Bk,D) slice; the matmul transposes it
using ElementQ = half;
using ElementK = half;
using ElementScore = float;
using LayoutQ = layout::RowMajor;     // Q: (M, D), stride (D, 1)
using LayoutKT = layout::ColumnMajor; // K_b: stored (Bk, D), used as K^T → ColumnMajor
using LayoutScore = layout::RowMajor;

// BMM2: Prob(M,Bk) @ V_b(Bk,D) → OutPartial(M,D) fp32
using ElementProb = half;
using ElementV = half;
using ElementOut = float;
using LayoutProb = layout::RowMajor;
using LayoutV = layout::RowMajor;
using LayoutOut = layout::RowMajor;

using MmadDispatchPolicy = Gemm::MmadAtlasA2Pingpong<true>;

// BMM1 shapes: L1_M × Bk × D (Bk and D are full dimensions, no tiling along K/N within one BMM call)
// Using L1Shape with M=128, N=Bk (runtime), K=D (runtime) — but Catlass needs compile-time L1Shape
// For simplicity, use L1Shape matching the max tile: L1_M=128, L1_N=256, L1_K=256
using L1Shape = GemmShape<128, 256, 256>;
using L0Shape = GemmShape<128, 256, 64>;

using QType = Gemm::GemmType<ElementQ, LayoutQ>;
using KTType = Gemm::GemmType<ElementK, LayoutKT>;
using ScoreType = Gemm::GemmType<ElementScore, LayoutScore>;
using BlockMmad1 = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, QType, KTType, ScoreType>;

using ProbType = Gemm::GemmType<ElementProb, LayoutProb>;
using VType = Gemm::GemmType<ElementV, LayoutV>;
using OutType = Gemm::GemmType<ElementOut, LayoutOut>;
using BlockMmad2 = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, ProbType, VType, OutType>;

// 4 cross-core events per KV-block iteration
constexpr uint32_t SCORE_READY = 0;
constexpr uint32_t PROB_READY = 1;
constexpr uint32_t OUT_READY = 2;
constexpr uint32_t UPDATE_DONE = 3;
```

### Notes

- **ColumnMajor for K^T**: K is stored as (N, D) row-major. When used as K^T in Q @ K^T, it appears as (D, Bk). Using `layout::ColumnMajor` tells BlockMmad that the B matrix has transposed storage. Construct `LayoutKT(D, Bk)` — ColumnMajor takes (rows, cols) of the **logical** matrix.
- **Dual BlockMmad**: BMM1 (Q×K^T→Score) and BMM2 (Prob×V→Out) have different element/layout types.
- **4 events**: Each KV block iteration uses all 4 events for the Cube↔Vector↔Cube↔Vector pipeline.
- **No BlockScheduler**: Per-block_m scheduling with KV-block inner loop.
- **`<cmath>` include**: Needed for `expf()` and `sqrtf()` in online softmax.
