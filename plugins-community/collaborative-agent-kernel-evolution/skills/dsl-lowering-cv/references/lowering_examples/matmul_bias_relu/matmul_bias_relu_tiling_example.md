### Example Input DSL (host part)
```python
def host_main(A: torch.Tensor, B: torch.Tensor, bias: torch.Tensor, D: torch.Tensor):
    M, K = A.shape
    K, N = B.shape

    workspace = torch.empty(M*N, dtype=torch.float32, device=A.device)
    core_num = tl.get_core_num()

    matmul_bias_relu_kernel[core_num](
        A, B, bias, D, workspace,
        M, N, K
    )
```

### Example Output (host tiling + op definition)
```cpp
// op_host/matmul_bias_relu_custom_tiling.h
#include "register/tilingdata_base.h"
namespace optiling {
BEGIN_TILING_DATA_DEF(MatmulBiasReluCustomTilingData)
  TILING_DATA_FIELD_DEF(uint32_t, M);
  TILING_DATA_FIELD_DEF(uint32_t, N);
  TILING_DATA_FIELD_DEF(uint32_t, K);
END_TILING_DATA_DEF;
REGISTER_TILING_DATA_CLASS(MatmulBiasReluCustom, MatmulBiasReluCustomTilingData)
}

// op_host/matmul_bias_relu_custom.cpp
#include "matmul_bias_relu_custom_tiling.h"
#include "register/op_def_registry.h"
#include "tiling/platform/platform_ascendc.h"
namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
  MatmulBiasReluCustomTilingData tiling;
  const gert::StorageShape* a_shape = context->GetInputShape(0);
  const gert::StorageShape* b_shape = context->GetInputShape(1);

  uint32_t M = a_shape->GetStorageShape().GetDim(0);
  uint32_t K = a_shape->GetStorageShape().GetDim(1);
  uint32_t N = b_shape->GetStorageShape().GetDim(1);

  auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
  uint32_t aicCoreNum = ascendcPlatform.GetCoreNumAic();
  uint32_t aivCoreNum = ascendcPlatform.GetCoreNumAiv();
  context->SetBlockDim(ascendcPlatform.CalcTschBlockDim(aivCoreNum, aicCoreNum, aivCoreNum));

  tiling.set_M(M);
  tiling.set_N(N);
  tiling.set_K(K);
  tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
  context->GetRawTilingData()->SetDataSize(tiling.GetDataSize());

  uint32_t sysWorkspaceSize = ascendcPlatform.GetLibApiWorkSpaceSize();
  size_t requiredWorkspaceBytes = (size_t)M * (size_t)N * sizeof(float);
  size_t *currentWorkspace = context->GetWorkspaceSizes(1);
  currentWorkspace[0] = requiredWorkspaceBytes + sysWorkspaceSize;
  return ge::GRAPH_SUCCESS;
}
}
```

### Notes

- **Same structure as matmul_gelu/matmul_add**: Standard M×N fp32 workspace, no attributes.
- **bias tensor**: bias is a 1D tensor of shape [N], passed as a separate input but does not affect tiling or workspace computation.
