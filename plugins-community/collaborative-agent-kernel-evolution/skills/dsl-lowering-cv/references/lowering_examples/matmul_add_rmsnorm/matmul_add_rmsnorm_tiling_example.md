### Example Input DSL (host part)
```python
def host_main(A: torch.Tensor, B: torch.Tensor, residual: torch.Tensor,
              gamma: torch.Tensor, Y: torch.Tensor, X_add: torch.Tensor, norm_eps: float = 1e-6):
    M, K = A.shape
    K, N = B.shape

    workspace = torch.empty(M * N, dtype=torch.float32, device=A.device)
    core_num = tl.get_core_num()

    matmul_add_rmsnorm_kernel[core_num](
        A, B, residual, gamma, Y, X_add, workspace,
        M, N, K, norm_eps
    )
```

### Example Output (host tiling + op definition)
```cpp
// op_host/matmul_add_rmsnorm_custom_tiling.h
#include "register/tilingdata_base.h"
namespace optiling {
BEGIN_TILING_DATA_DEF(MatmulAddRmsnormCustomTilingData)
  TILING_DATA_FIELD_DEF(uint32_t, M);
  TILING_DATA_FIELD_DEF(uint32_t, N);
  TILING_DATA_FIELD_DEF(uint32_t, K);
  TILING_DATA_FIELD_DEF(float, eps);
END_TILING_DATA_DEF;
REGISTER_TILING_DATA_CLASS(MatmulAddRmsnormCustom, MatmulAddRmsnormCustomTilingData)
}

// op_host/matmul_add_rmsnorm_custom.cpp
#include "matmul_add_rmsnorm_custom_tiling.h"
#include "register/op_def_registry.h"
#include "tiling/platform/platform_ascendc.h"
namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
  MatmulAddRmsnormCustomTilingData tiling;
  const gert::StorageShape* a_shape = context->GetInputShape(0);
  const gert::StorageShape* b_shape = context->GetInputShape(1);
  const gert::RuntimeAttrs* attrs = context->GetAttrs();

  uint32_t M = a_shape->GetStorageShape().GetDim(0);
  uint32_t K = a_shape->GetStorageShape().GetDim(1);
  uint32_t N = b_shape->GetStorageShape().GetDim(1);

  float eps = 1e-6f;
  if (attrs != nullptr) {
    const float* eps_attr = attrs->GetAttrPointer<float>(0);
    if (eps_attr != nullptr) {
      eps = *eps_attr;
    }
  }

  auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
  uint32_t aicCoreNum = ascendcPlatform.GetCoreNumAic();
  uint32_t aivCoreNum = ascendcPlatform.GetCoreNumAiv();
  context->SetBlockDim(ascendcPlatform.CalcTschBlockDim(aivCoreNum, aicCoreNum, aivCoreNum));

  tiling.set_M(M);
  tiling.set_N(N);
  tiling.set_K(K);
  tiling.set_eps(eps);
  tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
  context->GetRawTilingData()->SetDataSize(tiling.GetDataSize());

  uint32_t sysWorkspaceSize = ascendcPlatform.GetLibApiWorkSpaceSize();
  size_t mmWorkspaceBytes = (size_t)M * (size_t)N * sizeof(float);
  size_t *currentWorkspace = context->GetWorkspaceSizes(1);
  currentWorkspace[0] = mmWorkspaceBytes + sysWorkspaceSize;
  return ge::GRAPH_SUCCESS;
}
}
```

### Notes

- **Attribute**: `eps` (epsilon for RmsNorm) is passed through the tiling struct, same pattern as rms_matmul_scale.
- **Single workspace**: Only the matmul accumulation workspace (M×N×fp32). Unlike rms_matmul_scale, no separate inv_rms workspace — the inv_rms is computed and used inline per row.
- **Dual output**: Y and X_add are both output tensors, but this only affects the entry function signature, not the workspace.
