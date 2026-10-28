### Example Input DSL (kernel config)
```python
DTYPE_OUT = tl.half

conv_params = tl.make_conv_params(
    H=H, W=W, kH=kH, kW=kW,
    strideH=sH, strideW=sW,
    padH=pH, padW=pW,
    Cin=Cin, Cout=Cout,
    bias_ptr=bias
)

C0 = 16
Cin1 = tl.cdiv(Cin, C0)
Cout1 = tl.cdiv(Cout, C0)
layout_fmap = tl.make_ndc1hwc0_layout(batch, 1, Cin1, H * W, C0)
layout_weight = tl.make_fracz_layout(Cin1 * kH * kW, Cout1, C0)
layout_out = tl.make_ndc1hwc0_layout(batch, 1, Cout1, Ho * Wo, C0)
```

### Example Output (AscendC + Catlass config)
```cpp
#include "kernel_operator.h"
#include "catlass/arch/arch.hpp"
#include "catlass/arch/resource.hpp"
#include "catlass/catlass.hpp"
#include "catlass/conv/block/block_conv.hpp"
#include "catlass/conv/block/block_swizzle.hpp"
#include "catlass/conv/device/device_conv.hpp"
#include "catlass/conv/dispatch_policy.hpp"
#include "catlass/conv/kernel/conv3d_bias.hpp"
#include "catlass/conv_coord.hpp"
#include "catlass/gemm/gemm_type.hpp"
#include "catlass/layout/layout.hpp"
#include "catlass/status.hpp"
using namespace Catlass;

using ArchTag = Arch::AtlasA2;

// Data types
using ElementFmap = half;
using ElementFilter = half;
using ElementBias = half;
using ElementOut = half;

// Layouts (hardware-specific formats)
using LayoutFmap = layout::NDC1HWC0;          // Feature map: [N, D=1, Cin1, H*W, C0]
using LayoutFilter = layout::KDC1KHKWN1N0C0;  // Weight: FracZ [Kd*Cin1*kH*kW, Cout1, N0, C0]
using LayoutOut = layout::NDC1HWC0;            // Output: [N, D=1, Cout1, Ho*Wo, C0]
using LayoutBias = layout::VectorLayout;       // Bias: 1D [Cout]

// Dispatch policy: ConvAtlasA2Pingpong<L1A_stages, L1B_stages, L0A_stages, L0B_stages, L0C_stages, enableUnitFlag>
constexpr uint32_t l1AStages = 1;
constexpr uint32_t l1BStages = 1;
constexpr uint32_t l0AStages = 2;   // Pingpong for L0A (fmap after im2col)
constexpr uint32_t l0BStages = 2;   // Pingpong for L0B (weight)
constexpr uint32_t l0CStages = 1;
constexpr bool enableUnitFlag = true;
using DispatchPolicy = Conv::ConvAtlasA2Pingpong<l1AStages, l1BStages, l0AStages, l0BStages, l0CStages, enableUnitFlag>;

// GemmType wrappers for BlockConv
using FmapType = Gemm::GemmType<ElementFmap, LayoutFmap>;
using FilterType = Gemm::GemmType<ElementFilter, LayoutFilter>;
using BiasType = Gemm::GemmType<ElementBias, LayoutBias>;
using OutType = Gemm::GemmType<ElementOut, LayoutOut>;

// Tile shapes for Conv
// CoreTileShape: how many tiles per core in each dimension {nDim, dDim, c1Dim, hwDim}
using CoreTileShape = ConvCoreShape<2, 1, 2, 2>;  // dDim=1 for Conv2d (no depth)

// L1 tile shapes
using FmapL1TileShape = ConvFmapL1Shape<16, 1, 1>;     // mAL1=16 (HoWo tiles), Kd=1, Ci1=1
using FilterL1TileShape = ConvFilterL1Shape<1, 1, 16>;  // Kd=1, Ci1=1, nBL1=16 (Cout tiles)

// L0 tile shape (M, K, N granularity)
using L0TileShape = ConvL0Shape<16, 16, 16>;  // mL0=16, kL0=16, nL0=16

// BlockConv: the convolution equivalent of BlockMmad
using BlockConv = Conv::Block::BlockConv<
    DispatchPolicy, CoreTileShape,
    FmapL1TileShape, FilterL1TileShape, L0TileShape,
    FmapType, FilterType, OutType, BiasType>;

// Block scheduler: maps task IDs to output tile coordinates
// SwizzleOffset=3, SwizzleDirection=0 for cache-friendly tiling
using BlockScheduler = Conv::Block::Conv3dIdentityBlockSwizzle<3, 0>;

// ConvBias kernel: wraps BlockConv + scheduler, handles full conv+bias pipeline
using BlockEpilogue = void;  // No separate epilogue (bias handled inside BlockConv)
using ConvKernel = Conv::Kernel::ConvBias<BlockConv, BlockEpilogue, BlockScheduler>;
```

### Notes

- **BlockConv vs BlockMmad**: `BlockConv` replaces `BlockMmad` for convolution. It internally calls Load3Dv2 for im2col (in CopyL1ToL0A) — no manual Load3D needed.
- **ConvAtlasA2Pingpong**: More parameters than `MmadAtlasA2Pingpong` — separate stage counts for L1A, L1B, L0A, L0B, L0C.
- **Conv3dParams**: Conv2d uses Conv3d infrastructure with D=1, Kd=1.
- **CoreTileShape**: Controls how output is partitioned across cores. `dDim=1` for 2D convolution.
- **Layout formats**: `NDC1HWC0` is hardware-required for Load3D. `KDC1KHKWN1N0C0` is FracZ format for weights.
- **No cross-core events**: ConvBias is AIC-only, no Cube↔Vector sync needed.
- **Reference**: See `catlass-master/examples/24_conv_bias/conv_bias.cpp` for complete usage.
