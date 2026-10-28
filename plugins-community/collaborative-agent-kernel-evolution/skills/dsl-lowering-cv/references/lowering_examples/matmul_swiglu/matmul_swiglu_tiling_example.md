### Example Input DSL (host part)
```python
def host_main(A: torch.Tensor, B: torch.Tensor, D: torch.Tensor):
    M, K = A.shape
    K, TWO_N = B.shape
    N = TWO_N // 2

    workspace = torch.empty(M * TWO_N, dtype=torch.float32, device=A.device)
    core_num = tl.get_core_num()

    matmul_swiglu_kernel[core_num](
        A, B, D, workspace,
        M, N, K
    )
```

### Example Output (host tiling + op definition)
```cpp
// op_host/matmul_swiglu_custom_tiling.h
#include "register/tilingdata_base.h"
namespace optiling {
BEGIN_TILING_DATA_DEF(MatmulSwigluCustomTilingData)
  TILING_DATA_FIELD_DEF(uint32_t, M);
  TILING_DATA_FIELD_DEF(uint32_t, N);
  TILING_DATA_FIELD_DEF(uint32_t, K);
END_TILING_DATA_DEF;
REGISTER_TILING_DATA_CLASS(MatmulSwigluCustom, MatmulSwigluCustomTilingData)
}

// op_host/matmul_swiglu_custom.cpp
#include "matmul_swiglu_custom_tiling.h"
#include "register/op_def_registry.h"
#include "tiling/platform/platform_ascendc.h"
namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
  MatmulSwigluCustomTilingData tiling;
  const gert::StorageShape* a_shape = context->GetInputShape(0);
  const gert::StorageShape* b_shape = context->GetInputShape(1);

  uint32_t M = a_shape->GetStorageShape().GetDim(0);
  uint32_t K = a_shape->GetStorageShape().GetDim(1);
  uint32_t TWO_N = b_shape->GetStorageShape().GetDim(1);
  uint32_t N = TWO_N / 2;

  auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
  uint32_t aicCoreNum = ascendcPlatform.GetCoreNumAic();
  uint32_t aivCoreNum = ascendcPlatform.GetCoreNumAiv();
  context->SetBlockDim(ascendcPlatform.CalcTschBlockDim(aivCoreNum, aicCoreNum, aivCoreNum));

  tiling.set_M(M);
  tiling.set_N(N);
  tiling.set_K(K);
  tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
  context->GetRawTilingData()->SetDataSize(tiling.GetDataSize());

  // Workspace: M × 2N × sizeof(float) — full-width matmul accumulation
  uint32_t sysWorkspaceSize = ascendcPlatform.GetLibApiWorkSpaceSize();
  size_t requiredWorkspaceBytes = (size_t)M * (size_t)TWO_N * sizeof(float);
  size_t *currentWorkspace = context->GetWorkspaceSizes(1);
  currentWorkspace[0] = requiredWorkspaceBytes + sysWorkspaceSize;
  return ge::GRAPH_SUCCESS;
}
}
```

### Notes

- **TWO_N vs N**: The matmul output is M×2N (full-width), but the final output D is M×N (half-width). Tiling stores N (half-width) in the tiling struct.
- **Workspace = M×2N×fp32**: The workspace holds the full-width matmul result. The Vector epilogue splits it into left/right halves and computes SwiGLU.
