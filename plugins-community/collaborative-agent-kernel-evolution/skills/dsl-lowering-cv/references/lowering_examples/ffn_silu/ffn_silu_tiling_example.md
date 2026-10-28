### Example Input DSL (host part)
```python
def host_main(X: torch.Tensor, W1: torch.Tensor, W2: torch.Tensor, Y: torch.Tensor):
    M, K = X.shape
    K, N1 = W1.shape
    N1, N2 = W2.shape

    # 3 workspace segments:
    workspace_mm1 = torch.empty(M * N1, dtype=torch.float32, device=X.device)
    workspace_act = torch.empty(M * N1, dtype=torch.float16, device=X.device)
    workspace_mm2 = torch.empty(M * N2, dtype=torch.float32, device=X.device)
    core_num = tl.get_core_num()

    ffn_silu_kernel[core_num](
        X, W1, W2, Y,
        workspace_mm1, workspace_act, workspace_mm2,
        M, N1, N2, K
    )
```

### Example Output (host tiling + op definition)
```cpp
// op_host/ffn_silu_custom_tiling.h
#include "register/tilingdata_base.h"
namespace optiling {
BEGIN_TILING_DATA_DEF(FfnSiluCustomTilingData)
  TILING_DATA_FIELD_DEF(uint32_t, M);
  TILING_DATA_FIELD_DEF(uint32_t, N1);
  TILING_DATA_FIELD_DEF(uint32_t, N2);
  TILING_DATA_FIELD_DEF(uint32_t, K);
END_TILING_DATA_DEF;
REGISTER_TILING_DATA_CLASS(FfnSiluCustom, FfnSiluCustomTilingData)
}

// op_host/ffn_silu_custom.cpp
// Workspace layout (3 segments):
//   1) ws_mm1:  M × N1 × sizeof(float)    — MM1 accumulation (fp32)
//   2) ws_act:  M × N1 × sizeof(half)     — SiLU activation output (fp16, Cube input for MM2)
//   3) ws_mm2:  M × N2 × sizeof(float)    — MM2 accumulation (fp32)
#include "ffn_silu_custom_tiling.h"
#include "register/op_def_registry.h"
#include "tiling/platform/platform_ascendc.h"
namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
  FfnSiluCustomTilingData tiling;
  const gert::StorageShape* x_shape = context->GetInputShape(0);
  const gert::StorageShape* w1_shape = context->GetInputShape(1);
  const gert::StorageShape* w2_shape = context->GetInputShape(2);

  uint32_t M = x_shape->GetStorageShape().GetDim(0);
  uint32_t K = x_shape->GetStorageShape().GetDim(1);
  uint32_t N1 = w1_shape->GetStorageShape().GetDim(1);
  uint32_t N2 = w2_shape->GetStorageShape().GetDim(1);

  auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
  uint32_t aicCoreNum = ascendcPlatform.GetCoreNumAic();
  uint32_t aivCoreNum = ascendcPlatform.GetCoreNumAiv();
  context->SetBlockDim(ascendcPlatform.CalcTschBlockDim(aivCoreNum, aicCoreNum, aivCoreNum));

  tiling.set_M(M);
  tiling.set_N1(N1);
  tiling.set_N2(N2);
  tiling.set_K(K);
  tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
  context->GetRawTilingData()->SetDataSize(tiling.GetDataSize());

  uint32_t sysWorkspaceSize = ascendcPlatform.GetLibApiWorkSpaceSize();
  size_t wsMm1Bytes = (size_t)M * (size_t)N1 * sizeof(float);
  size_t wsActBytes = (size_t)M * (size_t)N1 * sizeof(uint16_t);  // fp16
  size_t wsMm2Bytes = (size_t)M * (size_t)N2 * sizeof(float);
  size_t *currentWorkspace = context->GetWorkspaceSizes(1);
  currentWorkspace[0] = wsMm1Bytes + wsActBytes + wsMm2Bytes + sysWorkspaceSize;
  return ge::GRAPH_SUCCESS;
}
}
```

### Notes

- **4 tiling dimensions**: M, N1, N2, K — reflecting the two matmul stages with different width dimensions.
- **3-segment workspace**: Combined into a single allocation. The kernel partitions it via pointer arithmetic in Init.
- **Workspace layout documented in comments**: Critical for correctness — the Vector and second Cube stage must compute correct offsets.
