### Example Input DSL (host part)
```python
def host_main(fmap, weight, bias, output):
    batch, Cin, H, W = fmap.shape
    Cout, _, kH, kW = weight.shape
    sH, sW = 1, 1
    pH, pW = 1, 1
    core_num = tl.get_core_num()
    conv2d_bias_kernel[core_num](
        fmap, weight, bias, output,
        batch, Cin, H, W, Cout, kH, kW, sH, sW, pH, pW
    )
```

### Example Output (host tiling + op definition)
```cpp
// op_host/conv2d_bias_custom_tiling.h
#include "register/tilingdata_base.h"
namespace optiling {
BEGIN_TILING_DATA_DEF(Conv2dBiasCustomTilingData)
  // Input spatial dimensions
  TILING_DATA_FIELD_DEF(uint32_t, batch);
  TILING_DATA_FIELD_DEF(uint32_t, Cin);
  TILING_DATA_FIELD_DEF(uint32_t, H);
  TILING_DATA_FIELD_DEF(uint32_t, W);
  // Output channels
  TILING_DATA_FIELD_DEF(uint32_t, Cout);
  // Kernel parameters
  TILING_DATA_FIELD_DEF(uint32_t, kH);
  TILING_DATA_FIELD_DEF(uint32_t, kW);
  TILING_DATA_FIELD_DEF(uint32_t, strideH);
  TILING_DATA_FIELD_DEF(uint32_t, strideW);
  TILING_DATA_FIELD_DEF(uint32_t, padH);
  TILING_DATA_FIELD_DEF(uint32_t, padW);
  // Derived dimensions
  TILING_DATA_FIELD_DEF(uint32_t, Ho);
  TILING_DATA_FIELD_DEF(uint32_t, Wo);
  TILING_DATA_FIELD_DEF(uint32_t, Cin1);
  TILING_DATA_FIELD_DEF(uint32_t, Cout1);
END_TILING_DATA_DEF;
REGISTER_TILING_DATA_CLASS(Conv2dBiasCustom, Conv2dBiasCustomTilingData)
}

// op_host/conv2d_bias_custom.cpp
#include "conv2d_bias_custom_tiling.h"
#include "register/op_def_registry.h"
#include "tiling/platform/platform_ascendc.h"
namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
  Conv2dBiasCustomTilingData tiling;
  const gert::StorageShape* x_shape = context->GetInputShape(0);  // fmap: (N, Cin, H, W)
  const gert::StorageShape* w_shape = context->GetInputShape(1);  // weight: (Cout, Cin, kH, kW)

  uint32_t batch = x_shape->GetStorageShape().GetDim(0);
  uint32_t Cin = x_shape->GetStorageShape().GetDim(1);
  uint32_t H = x_shape->GetStorageShape().GetDim(2);
  uint32_t W = x_shape->GetStorageShape().GetDim(3);
  uint32_t Cout = w_shape->GetStorageShape().GetDim(0);
  uint32_t kH = w_shape->GetStorageShape().GetDim(2);
  uint32_t kW = w_shape->GetStorageShape().GetDim(3);

  // Conv attributes (from op definition or hardcoded)
  uint32_t strideH = 1, strideW = 1;
  uint32_t padH = 1, padW = 1;

  // Derived dimensions
  uint32_t Ho = (H + 2 * padH - kH) / strideH + 1;
  uint32_t Wo = (W + 2 * padW - kW) / strideW + 1;
  constexpr uint32_t C0 = 16;
  uint32_t Cin1 = (Cin + C0 - 1) / C0;
  uint32_t Cout1 = (Cout + C0 - 1) / C0;

  auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
  uint32_t aicCoreNum = ascendcPlatform.GetCoreNumAic();
  // ConvBias: AIC-only (Cube handles conv + bias via Fixpipe)
  context->SetBlockDim(aicCoreNum);

  tiling.set_batch(batch);
  tiling.set_Cin(Cin);
  tiling.set_H(H);
  tiling.set_W(W);
  tiling.set_Cout(Cout);
  tiling.set_kH(kH);
  tiling.set_kW(kW);
  tiling.set_strideH(strideH);
  tiling.set_strideW(strideW);
  tiling.set_padH(padH);
  tiling.set_padW(padW);
  tiling.set_Ho(Ho);
  tiling.set_Wo(Wo);
  tiling.set_Cin1(Cin1);
  tiling.set_Cout1(Cout1);

  tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
  context->GetRawTilingData()->SetDataSize(tiling.GetDataSize());

  // ConvBias Fixpipe: no intermediate workspace needed
  // Only system workspace for Catlass internal use
  uint32_t sysWorkspaceSize = ascendcPlatform.GetLibApiWorkSpaceSize();
  size_t *currentWorkspace = context->GetWorkspaceSizes(1);
  currentWorkspace[0] = sysWorkspaceSize;
  return ge::GRAPH_SUCCESS;
}
}
```

### Notes

- **Conv-specific tiling**: Unlike matmul (M, N, K), conv tiling carries spatial dimensions (H, W, Ho, Wo), kernel params (kH, kW, stride, pad), and channel alignment (Cin1, Cout1, C0=16).
- **ConvBias = AIC-only**: `SetBlockDim(aicCoreNum)` — no AIV cores needed since bias is handled in Cube.
- **No intermediate workspace**: ConvBias uses Fixpipe to write output directly (unlike matmul+activation which needs fp32 workspace).
- **Input format**: Host must provide fmap in NC1HWC0 format and weight in FracZ format. If inputs are NCHW, host must convert before kernel launch.
