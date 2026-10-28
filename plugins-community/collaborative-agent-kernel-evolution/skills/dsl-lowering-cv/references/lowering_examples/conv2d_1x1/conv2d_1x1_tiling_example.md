### Example Input DSL (host part)
```python
def host_main(x: torch.Tensor, weight: torch.Tensor, D: torch.Tensor):
    N_batch, Cin, H, W = x.shape
    Cout = weight.shape[0]
    M = N_batch * H * W
    K = Cin
    N_out = Cout
    A = x.permute(0, 2, 3, 1).reshape(M, K).contiguous()
    B = weight.squeeze(-1).squeeze(-1).t().contiguous()
    core_num = tl.get_core_num()
    conv2d_1x1_kernel[core_num](A, B, D, M, N_out, K)
```

### Example Output (host tiling + op definition)
```cpp
// op_host/conv2d_1x1_custom_tiling.h
#include "register/tilingdata_base.h"
namespace optiling {
BEGIN_TILING_DATA_DEF(Conv2d1x1CustomTilingData)
  TILING_DATA_FIELD_DEF(uint32_t, M);
  TILING_DATA_FIELD_DEF(uint32_t, N);
  TILING_DATA_FIELD_DEF(uint32_t, K);
END_TILING_DATA_DEF;
REGISTER_TILING_DATA_CLASS(Conv2d1x1Custom, Conv2d1x1CustomTilingData)
}

// op_host/conv2d_1x1_custom.cpp
#include "conv2d_1x1_custom_tiling.h"
#include "register/op_def_registry.h"
#include "tiling/platform/platform_ascendc.h"
namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
  Conv2d1x1CustomTilingData tiling;
  // Input x is 4D: (N, Cin, H, W) — extract dims for matmul reshape
  const gert::StorageShape* x_shape = context->GetInputShape(0);  // fmap
  const gert::StorageShape* w_shape = context->GetInputShape(1);  // weight

  uint32_t N_batch = x_shape->GetStorageShape().GetDim(0);
  uint32_t Cin = x_shape->GetStorageShape().GetDim(1);
  uint32_t H = x_shape->GetStorageShape().GetDim(2);
  uint32_t W = x_shape->GetStorageShape().GetDim(3);
  uint32_t Cout = w_shape->GetStorageShape().GetDim(0);

  // 1x1 conv = matmul: M = N*H*W, K = Cin, N_out = Cout
  uint32_t M = N_batch * H * W;
  uint32_t K = Cin;
  uint32_t N_out = Cout;

  auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
  uint32_t aicCoreNum = ascendcPlatform.GetCoreNumAic();
  // Fixpipe: AIC-only, no AIV cores
  context->SetBlockDim(aicCoreNum);

  tiling.set_M(M);
  tiling.set_N(N_out);
  tiling.set_K(K);
  tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
  context->GetRawTilingData()->SetDataSize(tiling.GetDataSize());

  // Fixpipe: no workspace needed (Cube outputs directly to output tensor)
  uint32_t sysWorkspaceSize = ascendcPlatform.GetLibApiWorkSpaceSize();
  size_t *currentWorkspace = context->GetWorkspaceSizes(1);
  currentWorkspace[0] = sysWorkspaceSize;
  return ge::GRAPH_SUCCESS;
}
}
```

### Notes

- **1x1 conv = matmul**: M = batch * H * W, K = Cin, N = Cout. Host reshapes 4D input to 2D.
- **Fixpipe pattern**: AIC-only dispatch (no AIV), no workspace for intermediate fp32.
- **No bias in this example**: Weight is the only parameter besides input.
