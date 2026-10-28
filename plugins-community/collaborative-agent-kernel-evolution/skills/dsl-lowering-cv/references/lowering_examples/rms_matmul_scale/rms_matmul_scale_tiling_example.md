### Example Input DSL (host part)
```python
def host_main(x: torch.Tensor, weight: torch.Tensor, out: torch.Tensor, norm_eps: float = 1e-6):
    b, s, n, d = x.shape
    m = b * s
    k = n * d
    o = weight.shape[1]

    workspace_mm = torch.empty(m * o, dtype=torch.float32, device=x.device)
    workspace_inv = torch.empty(m, dtype=torch.float32, device=x.device)
    core_num = tl.get_core_num()

    rms_matmul_scale_kernel[core_num](
        x, weight, out,
        workspace_mm, workspace_inv,
        m, k, o, norm_eps,
    )
```

### Example Output (host tiling + op definition)
```cpp
// op_host/rms_matmul_scale_custom_tiling.h
#include "register/tilingdata_base.h"
namespace optiling {
BEGIN_TILING_DATA_DEF(RmsMatmulScaleCustomTilingData)
  TILING_DATA_FIELD_DEF(uint32_t, M);
  TILING_DATA_FIELD_DEF(uint32_t, N);
  TILING_DATA_FIELD_DEF(uint32_t, K);
  TILING_DATA_FIELD_DEF(float, eps);
END_TILING_DATA_DEF;
REGISTER_TILING_DATA_CLASS(RmsMatmulScaleCustom, RmsMatmulScaleCustomTilingData)
}

// op_host/rms_matmul_scale_custom.cpp
// Workspace layout:
//   1) matmul fp32 accumulation: [M, N]
//   2) per-row inv_rms fp32: [M]
#include "rms_matmul_scale_custom_tiling.h"
#include "register/op_def_registry.h"
#include "tiling/platform/platform_ascendc.h"
namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
  RmsMatmulScaleCustomTilingData tiling;
  const gert::StorageShape* x_shape = context->GetInputShape(0);
  const gert::StorageShape* w_shape = context->GetInputShape(1);
  const gert::RuntimeAttrs* attrs = context->GetAttrs();

  const auto& xs = x_shape->GetStorageShape();
  const auto& ws = w_shape->GetStorageShape();

  uint32_t b = static_cast<uint32_t>(xs.GetDim(0));
  uint32_t s = static_cast<uint32_t>(xs.GetDim(1));
  uint32_t n = static_cast<uint32_t>(xs.GetDim(2));
  uint32_t d = static_cast<uint32_t>(xs.GetDim(3));
  uint32_t M = b * s;
  uint32_t K = n * d;
  uint32_t N = static_cast<uint32_t>(ws.GetDim(1));

  float eps = 1e-6f;
  if (attrs != nullptr) {
    const float* eps_attr = attrs->GetAttrPointer<float>(0);
    if (eps_attr != nullptr) {
      eps = *eps_attr;
    }
  }

  auto ascendc_platform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
  uint32_t aic_core_num = ascendc_platform.GetCoreNumAic();
  uint32_t aiv_core_num = ascendc_platform.GetCoreNumAiv();
  // CalcTschBlockDim: for CV fusion (both cube+vector used), sliceNum = aiv_core_num
  context->SetBlockDim(ascendc_platform.CalcTschBlockDim(aiv_core_num, aic_core_num, aiv_core_num));

  tiling.set_M(M);
  tiling.set_N(N);
  tiling.set_K(K);
  tiling.set_eps(eps);
  tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
  context->GetRawTilingData()->SetDataSize(tiling.GetDataSize());

  uint32_t sys_workspace_size = ascendc_platform.GetLibApiWorkSpaceSize();
  size_t mm_workspace_bytes = static_cast<size_t>(M) * static_cast<size_t>(N) * sizeof(float);
  size_t inv_workspace_bytes = static_cast<size_t>(M) * sizeof(float);
  size_t* current_workspace = context->GetWorkspaceSizes(1);
  current_workspace[0] = mm_workspace_bytes + inv_workspace_bytes + sys_workspace_size;
  return ge::GRAPH_SUCCESS;
}
}
```

### Notes

- **Multiple workspace regions**: When DSL allocates multiple workspace tensors, combine them into a single workspace with offsets. Document the layout in comments.
- **Attribute handling**: Use `GetAttrPointer<T>(index)` to read operator attributes. Index corresponds to the order in project.json.
- **SetBlockDim**: For CV fusion operators (both cube+vector used), use `CalcTschBlockDim(aivCoreNum, aicCoreNum, aivCoreNum)` — `sliceNum = aivCoreNum` because data is sliced by the number of AIV (vector) cores. Do NOT call `SetBlockDim(aicCoreNum)` directly.
- **Shape derivation**: When inputs have higher dimensions (e.g., [B,S,N,D]), compute derived dimensions (M=B*S, K=N*D) in tiling.
