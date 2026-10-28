### Example Input DSL (host part)
```python
def host_main(Q: torch.Tensor, K: torch.Tensor, V: torch.Tensor, O: torch.Tensor):
    M, D = Q.shape
    N, D = K.shape
    Bk = 256  # KV block size
    scale = 1.0 / math.sqrt(D)

    # 5 workspace segments:
    workspace_score = torch.empty(M * Bk, dtype=torch.float32, device=Q.device)
    workspace_prob = torch.empty(M * Bk, dtype=torch.float16, device=Q.device)
    workspace_out = torch.empty(M * D, dtype=torch.float32, device=Q.device)
    workspace_max = torch.full((M,), float('-inf'), dtype=torch.float32, device=Q.device)
    workspace_sum = torch.zeros(M, dtype=torch.float32, device=Q.device)
    O.zero_()
    core_num = tl.get_core_num()

    flash_attn_basic_kernel[core_num](
        Q, K, V, O,
        workspace_score, workspace_prob, workspace_out, workspace_max, workspace_sum,
        M, N, D, Bk, scale
    )
```

### Example Output (host tiling + op definition)
```cpp
// op_host/flash_attn_basic_custom_tiling.h
#include "register/tilingdata_base.h"
namespace optiling {
BEGIN_TILING_DATA_DEF(FlashAttnBasicCustomTilingData)
  TILING_DATA_FIELD_DEF(uint32_t, M);
  TILING_DATA_FIELD_DEF(uint32_t, N);
  TILING_DATA_FIELD_DEF(uint32_t, D);
  TILING_DATA_FIELD_DEF(uint32_t, Bk);
  TILING_DATA_FIELD_DEF(float, scale);
END_TILING_DATA_DEF;
REGISTER_TILING_DATA_CLASS(FlashAttnBasicCustom, FlashAttnBasicCustomTilingData)
}

// op_host/flash_attn_basic_custom.cpp
// Workspace layout (5 segments):
//   1) ws_score:  M × Bk × sizeof(float)    — attention score (fp32)
//   2) ws_prob:   M × Bk × sizeof(half)     — softmax probability (fp16, input to BMM2)
//   3) ws_out:    M × D  × sizeof(float)    — partial output from BMM2 (fp32)
//   4) ws_max:    M × sizeof(float)          — per-row running max
//   5) ws_sum:    M × sizeof(float)          — per-row running sum
#include "flash_attn_basic_custom_tiling.h"
#include "register/op_def_registry.h"
#include "tiling/platform/platform_ascendc.h"
namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
  FlashAttnBasicCustomTilingData tiling;
  const gert::StorageShape* q_shape = context->GetInputShape(0);
  const gert::StorageShape* k_shape = context->GetInputShape(1);
  const gert::RuntimeAttrs* attrs = context->GetAttrs();

  uint32_t M = q_shape->GetStorageShape().GetDim(0);
  uint32_t D = q_shape->GetStorageShape().GetDim(1);
  uint32_t N = k_shape->GetStorageShape().GetDim(0);
  uint32_t Bk = 256;
  float scale = 1.0f / sqrtf(static_cast<float>(D));

  if (attrs != nullptr) {
    const uint32_t* bk_attr = attrs->GetAttrPointer<uint32_t>(0);
    if (bk_attr != nullptr) Bk = *bk_attr;
    const float* scale_attr = attrs->GetAttrPointer<float>(1);
    if (scale_attr != nullptr) scale = *scale_attr;
  }

  auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
  uint32_t aicCoreNum = ascendcPlatform.GetCoreNumAic();
  uint32_t aivCoreNum = ascendcPlatform.GetCoreNumAiv();
  context->SetBlockDim(ascendcPlatform.CalcTschBlockDim(aivCoreNum, aicCoreNum, aivCoreNum));

  tiling.set_M(M);
  tiling.set_N(N);
  tiling.set_D(D);
  tiling.set_Bk(Bk);
  tiling.set_scale(scale);
  tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
  context->GetRawTilingData()->SetDataSize(tiling.GetDataSize());

  uint32_t sysWorkspaceSize = ascendcPlatform.GetLibApiWorkSpaceSize();
  size_t wsScoreBytes = (size_t)M * (size_t)Bk * sizeof(float);
  size_t wsProbBytes  = (size_t)M * (size_t)Bk * sizeof(uint16_t);
  size_t wsOutBytes   = (size_t)M * (size_t)D  * sizeof(float);
  size_t wsMaxBytes   = (size_t)M * sizeof(float);
  size_t wsSumBytes   = (size_t)M * sizeof(float);
  size_t *currentWorkspace = context->GetWorkspaceSizes(1);
  currentWorkspace[0] = wsScoreBytes + wsProbBytes + wsOutBytes + wsMaxBytes + wsSumBytes + sysWorkspaceSize;
  return ge::GRAPH_SUCCESS;
}
}
```

### Notes

- **5-segment workspace**: The most complex workspace layout — each segment serves a different stage of the iterative KV-block pipeline.
- **Bk (KV block size)**: Determines the "tile" along the N dimension per KV iteration. Typically 256.
- **scale attribute**: `1/sqrt(D)`, can be passed as attribute or computed in tiling.
- **ws_max / ws_sum initialized on host**: max to `-inf`, sum to `0`. O tensor initialized to zero. The kernel reads/writes these running statistics across KV iterations.
