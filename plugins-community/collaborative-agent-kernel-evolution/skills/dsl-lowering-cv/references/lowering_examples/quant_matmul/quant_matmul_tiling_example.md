### Key Differences from Standard fp16 MatMul

- **int8 inputs**: A=[M,K] int8, B=[K,N] int8
- **int32 workspace**: Accumulation uses int32, but workspace is **NOT** M×N — use double-buffered L1-sized slots
- **Double-buffered workspace**: `L1_M * L1_N * aicCoreNum * WORKSPACE_STAGES * sizeof(int32_t)` — typically ~26 MB vs 200+ MB for full M×N
- **InferDataType hardcoded**: Output is always fp16 regardless of int8 input — must use `DT_FLOAT16`, NOT `GetInputDataType(0)`

### Example Input DSL (host part)
```python
def host_main(A: torch.Tensor, B: torch.Tensor, Scale: torch.Tensor,
              PerTokenScale: torch.Tensor, Y: torch.Tensor):
    M, K = A.shape
    N, K = B.shape  # B is [N, K], NOT [K, N]

    # Small double-buffered workspace (NOT M*N)
    # Layout: L1_M * core_num * WORKSPACE_STAGES rows x L1_N cols (int32)
    WORKSPACE_STAGES = 2
    L1_M, L1_N = 128, 256
    core_num = tl.get_core_num()
    workspace = torch.empty(L1_M * L1_N * core_num * WORKSPACE_STAGES, dtype=torch.int32, device=A.device)

    quant_matmul_kernel[core_num](A, B, Scale, PerTokenScale, Y, workspace, M, N, K)
```

### Example Output (host tiling + op definition)
```cpp
// op_host/quant_matmul_custom_tiling.h
#include "register/tilingdata_base.h"
namespace optiling {
BEGIN_TILING_DATA_DEF(QuantMatmulCustomTilingData)
  TILING_DATA_FIELD_DEF(uint32_t, M);
  TILING_DATA_FIELD_DEF(uint32_t, N);
  TILING_DATA_FIELD_DEF(uint32_t, K);
END_TILING_DATA_DEF;
REGISTER_TILING_DATA_CLASS(QuantMatmulCustom, QuantMatmulCustomTilingData)
}

// op_host/quant_matmul_custom.cpp
#include "quant_matmul_custom_tiling.h"
#include "register/op_def_registry.h"
#include "tiling/platform/platform_ascendc.h"
namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
  QuantMatmulCustomTilingData tiling;

  // A: [M, K] int8, B: [K, N] int8
  const gert::StorageShape* a_shape = context->GetInputShape(0);
  const gert::StorageShape* b_shape = context->GetInputShape(1);

  uint32_t M = a_shape->GetStorageShape().GetDim(0);
  uint32_t K = a_shape->GetStorageShape().GetDim(1);
  uint32_t N = b_shape->GetStorageShape().GetDim(1);  // B is [K, N]

  auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
  uint32_t aicCoreNum = ascendcPlatform.GetCoreNumAic();
  uint32_t aivCoreNum = ascendcPlatform.GetCoreNumAiv();
  // CalcTschBlockDim: for CV fusion (both cube+vector used), sliceNum = aivCoreNum
  context->SetBlockDim(ascendcPlatform.CalcTschBlockDim(aivCoreNum, aicCoreNum, aivCoreNum));

  tiling.set_M(M);
  tiling.set_N(N);
  tiling.set_K(K);
  tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
  context->GetRawTilingData()->SetDataSize(tiling.GetDataSize());

  // Workspace: double-buffered slots for Cube->Vector pipelining
  // Layout: L1_M * aicCoreNum * WORKSPACE_STAGES rows x L1_N cols (int32)
  // Total: 128 * 256 * aicCoreNum * 2 * 4 bytes (typically ~26 MB for 100 cores)
  // Compare: M * N * 4 bytes would be ~200+ MB for large shapes
  constexpr size_t L1_M = 128;
  constexpr size_t L1_N = 256;
  constexpr size_t WORKSPACE_STAGES = 2;
  uint32_t sysWorkspaceSize = ascendcPlatform.GetLibApiWorkSpaceSize();
  size_t requiredWorkspaceBytes = L1_M * L1_N * aicCoreNum * WORKSPACE_STAGES * sizeof(int32_t);
  size_t *currentWorkspace = context->GetWorkspaceSizes(1);
  currentWorkspace[0] = requiredWorkspaceBytes + sysWorkspaceSize;

  return ge::GRAPH_SUCCESS;
}
}

// InferDataType: hardcode DT_FLOAT16 (do NOT use GetInputDataType which returns int8)
namespace ge {
static ge::graphStatus InferDataType(gert::InferDataTypeContext *context)
{
    context->SetOutputDataType(0, ge::DT_FLOAT16);
    return ge::GRAPH_SUCCESS;
}
}
```

### Notes

- **Double-buffered workspace**: Instead of allocating `M * N * sizeof(int32_t)` (which can be 200+ MB for large shapes like M=4096, N=12288), use `L1_M * L1_N * aicCoreNum * WORKSPACE_STAGES * sizeof(int32_t)`. This is possible because Cube and Vector process tiles sequentially — each core only needs 2 slots (double buffer) of L1_M × L1_N.
- **N = b_shape->GetDim(1)**: When B is stored as [K, N], N is the second dimension. When B is stored as [N, K] (transposed weight), use `GetDim(0)` instead.
- **sizeof(int32_t)**: int8 matmul accumulates into int32 workspace. Using `sizeof(int8)` would allocate 4x too little memory.
- **InferDataType hardcoded**: For mixed-type operators (int8 input → fp16 output), `GetInputDataType(0)` returns `DT_INT8` which is wrong for the output. Must hardcode `DT_FLOAT16`.
