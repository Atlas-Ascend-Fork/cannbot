# CV Lowering Error Correction Examples

## Table of Contents

| Section | Topic |
|---------|-------|
| [1](#1-missing-catlass-headers) | Missing Catlass Headers |
| [2](#2-undefined-blockmmad-type) | Undefined BlockMmad Type |
| [3](#3-crosscoresetflagwaitflag-template-arguments) | CrossCoreSetFlag/WaitFlag Template Arguments |
| [4](#4-ascend_is_aic--ascend_is_aiv-syntax) | ASCEND_IS_AIC / ASCEND_IS_AIV Syntax |
| [5](#5-layout-construction-mismatch) | Layout Construction Mismatch |
| [6](#6-gemmcoord-vs-matrixcoord-confusion) | GemmCoord vs MatrixCoord Confusion |
| [7](#7-getsubblocknum-vs-getsubblockidx) | GetSubBlockNum vs GetSubBlockIdx |
| [8](#8-workspace-size-mismatch) | Workspace Size Mismatch |
| [9](#9-missing-tiling-include-for-platformascendc) | Missing Tiling Include for PlatformAscendC |
| [10](#10-setblockdim-for-cv-operators-in-tilingfunc) | SetBlockDim for CV Operators in TilingFunc |
| [11](#11-undeclared-identifier-expf--logf--sqrtf-and-other-std-math-functions) | Undeclared Identifier 'expf' / 'logf' / 'sqrtf' |
| [12](#12-soc-target-hardcode-in-cmakepresetsjson-cann-83-historical-issue) | SoC Target Hardcode in CMakePresets.json |
| [13](#13-pytorch-npu-helper-acl-header-conflict-cann-83-historical-issue) | PyTorch NPU Helper ACL Header Conflict |
| [14](#14-workspace-double-allocation-cann-83-historical-issue) | Workspace Double Allocation |

## Common Compilation Errors

### 1. Missing Catlass Headers

**Error:**
```
fatal error: catlass/arch/arch.hpp: No such file or directory
```

**Fix:**
Ensure `ASCEND_HOME_PATH` is set and CMakeLists.txt includes:
```cmake
include_directories($ENV{ASCEND_HOME_PATH}/include)
```

### 2. Undefined BlockMmad Type

**Error:**
```
error: 'BlockMmad' was not declared in this scope
```

**Fix:**
Ensure all required `using` declarations are present in the kernel config section:
```cpp
using BlockMmad = Gemm::Block::BlockMmad<MmadDispatchPolicy, L1Shape, L0Shape, AType, BType, CType>;
```

### 3. CrossCoreSetFlag/WaitFlag Template Arguments

**Error:**
```
error: no matching function for call to 'CrossCoreSetFlag'
```

**Fix:**
Use the correct template arguments:
```cpp
// WRONG:
AscendC::CrossCoreSetFlag(matmulReady);

// CORRECT:
AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(matmulReady);
```

### 4. ASCEND_IS_AIC / ASCEND_IS_AIV Syntax

**Error:**
```
error: expected '(' before '{' token
```

**Fix:**
Use the macros without parentheses around the condition:
```cpp
// WRONG:
if (ASCEND_IS_AIC) { ... }

// CORRECT:
if ASCEND_IS_AIC { ... }
```

### 5. Layout Construction Mismatch

**Error:**
```
error: no matching constructor for 'LayoutA'
```

**Fix:**
Row-major layout takes (rows, cols):
```cpp
// For M×K matrix in row-major:
LayoutA layoutA(M, K);  // stride = (K, 1) implied
```

### 6. GemmCoord vs MatrixCoord Confusion

**Error:**
```
error: cannot convert 'GemmCoord' to 'MatrixCoord'
```

**Fix:**
- Use `GemmCoord{M, N, K}` for 3D problem/tile shapes
- Use `MatrixCoord{row, col}` for 2D offsets

### 7. GetSubBlockNum vs GetSubBlockIdx

**Error:**
Vector scope not partitioning work correctly.

**Fix:**
```cpp
// Total number of vector subcores
uint32_t numSub = AscendC::GetSubBlockNum();
// Current subcore index
uint32_t subcoreIdx = AscendC::GetSubBlockIdx();
// AICore index (shared between cube and vector)
uint32_t aicoreIdx = AscendC::GetBlockIdx() / numSub;
```

### 8. Workspace Size Mismatch

**Error:**
Runtime crash or incorrect results.

**Fix:**
Ensure workspace size in tiling matches what the kernel expects:
```cpp
// Tiling side:
size_t ws_bytes = (size_t)M * N * sizeof(float) + sysWorkspaceSize;
currentWorkspace[0] = ws_bytes;

// Kernel side (must match):
__gm__ float* ws_ptr = (__gm__ float*)workspace;
gm_mm.SetGlobalBuffer(ws_ptr);  // first M*N floats
gm_inv.SetGlobalBuffer(ws_ptr + (uint64_t)M * N);  // next M floats
```

### 9. Missing Tiling Include for PlatformAscendC

**Error:**
```
error: 'PlatformAscendC' is not a member of 'platform_ascendc'
```

**Fix:**
Add the platform include:
```cpp
#include "tiling/platform/platform_ascendc.h"
```

### 10. SetBlockDim for CV Operators in TilingFunc

**Background:**
In `TilingFunc(gert::TilingContext* context)`, there are two ways to set the block dim for CV fusion:

1. **Simple**: `SetBlockDim(aicCoreNum)` — works correctly on 910B2 where AIV cores are grouped in the same block as AIC cores (aivCoreNum = 4 × aicCoreNum, so block count = aicCoreNum covers both).
2. **Recommended (portable)**: `CalcTschBlockDim(aivCoreNum, aicCoreNum, aivCoreNum)` — explicitly computes the correct block dim per CANN spec, portable across hardware generations where AIC/AIV grouping may differ.

> **Note**: `PlatformAscendCManager::GetInstance()` is valid for **Kernel Launch** (no gert context). In `TilingFunc`, `PlatformAscendC(context->GetPlatformInfo())` is preferred as it uses the context's bound platform info.

**Recommended pattern in TilingFunc:**
```cpp
// Context-aware + CalcTschBlockDim (recommended for portability):
auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
uint32_t aicCoreNum = ascendcPlatform.GetCoreNumAic();
uint32_t aivCoreNum = ascendcPlatform.GetCoreNumAiv();
// CV fusion (both cube+vector), sliceNum = aivCoreNum:
context->SetBlockDim(ascendcPlatform.CalcTschBlockDim(aivCoreNum, aicCoreNum, aivCoreNum));

// Fixpipe (cube-only, no vector scope):
context->SetBlockDim(ascendcPlatform.CalcTschBlockDim(aicCoreNum, aicCoreNum, 0));
```

### 11. Undeclared Identifier 'expf' / 'logf' / 'sqrtf' (and other std:: math functions)

**Error:**
```
error: use of undeclared identifier 'expf'
error: use of undeclared identifier 'logf'
error: use of undeclared identifier 'sqrtf'
error: use of undeclared identifier 'std::exp'
```

**Cause:**
AscendC kernels cannot use `<cmath>` scalar math functions (`expf`, `logf`, `sqrtf`, `std::exp`, etc.). The AI Core does not support the C++ standard library at all.

For the complete list of prohibited `std::` functions and their AscendC replacements, see:
`skills/cake-code-review/api-best-references/api-restrictions.md` Section 1.1

**Fix — scalar emulation via vector API + GetValue(0):**
```cpp
// WRONG:
float e = expf(x);
float l = logf(x);

// CORRECT: use vector API on a small buffer, then read back scalar
// (requires a pre-allocated TBuf, e.g. pipe.InitBuffer(scalarBuf, 8 * sizeof(float)))
LocalTensor<float> tmp = scalarBuf.Get<float>();

Duplicate(tmp, x, 8);
PipeBarrier<PIPE_V>();
Exp(tmp, tmp, 8);
PipeBarrier<PIPE_V>();
float e = tmp.GetValue(0);  // scalar exp(x)

Duplicate(tmp, x, 8);
PipeBarrier<PIPE_V>();
Ln(tmp, tmp, 8);
PipeBarrier<PIPE_V>();
float l = tmp.GetValue(0);  // scalar log(x)
```

**Fix — batch vector operations (preferred for performance):**
```cpp
// If computing exp/log over a whole LocalTensor, use the vector API directly:
Exp(dstLocal, srcLocal, count);   // vectorized exp
Ln(dstLocal, srcLocal, count);    // vectorized log (natural)
Sqrt(dstLocal, srcLocal, count);  // vectorized sqrt
```

**Note:** `count` for these vector ops must meet minimum hardware constraints:
- `Cast (half↔float)`: ≥ 64 elements
- `DataCopy`: ≥ 32 bytes (≥ 16 fp16 or ≥ 8 fp32)
See `skills/cake-code-review/api-best-references/api-restrictions.md` for full constraints.

### 12. SoC Target Hardcode in CMakePresets.json (CANN 8.3 Historical Issue)

> ⚠️ **CANN 8.3 环境注意**：此问题在 CANN 8.3 中经常发生。CANN 8.5 的修复状态请开发者自行验证。

**Symptom:**
Build succeeds but kernel does not execute on the actual chip, or the op registers incorrectly for the wrong SoC type.

**Cause:**
`CMakePresets.json` or `build.sh` hardcodes SoC target as `ascend910` instead of `ascend910b`:
```json
// WRONG (CANN 8.3 template default):
"SOC_VERSION": "ascend910"

// CORRECT for Atlas 800T A2 / 910B2:
"SOC_VERSION": "ascend910b"
```

**Fix:**
```bash
# Check current SoC setting:
grep -r "SOC_VERSION\|soc_version\|ascend910" CMakePresets.json build.sh

# Update CMakePresets.json:
sed -i 's/"ascend910"/"ascend910b"/g' CMakePresets.json

# Or in build.sh:
cmake ... -DSOC_VERSION=ascend910b ...
```

**Verification:**
```bash
# After fix, confirm the .so name contains 910b:
ls output/op_kernel/*910b*.so
```

---

### 13. PyTorch NPU Helper ACL Header Conflict (CANN 8.3 Historical Issue)

> ⚠️ **CANN 8.3 环境注意**：此问题在 CANN 8.3 中因 `pytorch_npu_helper.hpp` 与 `acl_mdl.h` 头文件重复定义而触发。CANN 8.5 是否修复不确定，请开发者验证。

**Error (CANN 8.3):**
```
error: 'aclmdlRICaptureMode' redeclared as different kind of symbol
error: conflicts with a previous declaration of 'typedef ... aclOpExecutor'
```

**Cause:**
`#include "pytorch_npu_helper.hpp"` pulls in ACL headers that conflict with manually included `<acl/acl_mdl.h>` or similar ACL typedefs in the pybind wrapper.

**Fix (CANN 8.3):**
```cpp
// WRONG: manually including ACL header that conflicts
#include "pytorch_npu_helper.hpp"
#include <acl/acl_mdl.h>   // conflicts with pytorch_npu_helper

// CORRECT: rely on pytorch_npu_helper to transitively include ACL
// Remove manual ACL includes; pytorch_npu_helper handles them:
#include "pytorch_npu_helper.hpp"
// Do NOT manually add <acl/acl_mdl.h> or define aclOpExecutor/aclmdlRICaptureMode

// If specific ACL symbols are needed, use:
#include <acl/acl.h>   // high-level, conflict-safe
```

---

### 14. Workspace Double Allocation (CANN 8.3 Historical Issue)

> ⚠️ **CANN 8.3 环境注意**：此问题在 CANN 8.3 中被发现，CANN 8.5 是否解决不确定，请开发者自行验证。

**Symptom (CANN 8.3):**
Runtime crash or incorrect results when workspace is explicitly allocated in pybind wrapper AND also auto-allocated by the CANN framework via `GetWorkspaceSizes`.

**Cause:**
In CANN 8.3, manually allocating workspace in pybind (`npu_allocate_workspace(size)`) AND declaring workspace size in `TilingFunc` (via `context->SetWorkspaceSizes(...)`) causes the framework to allocate a second workspace region. The kernel receives the framework-allocated pointer (offset from base), not the manually allocated one → buffer aliasing or offset mismatch.

**Fix (CANN 8.3):**
Choose **one** allocation path:
```python
# Option A: Framework allocation (recommended for ops registered via OpDef)
# TilingFunc sets workspace size; pybind does NOT manually allocate
# pybind wrapper:
output = torch.empty(shape, dtype=dtype, device='npu')
result = torch.ops.custom.my_op(input, output)  # framework allocates workspace

# Option B: Manual allocation (for pybind-direct kernels without OpDef)
# Do NOT call context->SetWorkspaceSizes() in TilingFunc
# pybind wrapper manually allocates and passes as argument:
workspace = torch.empty(ws_size, dtype=torch.uint8, device='npu')
result = my_op_kernel(input, output, workspace)
```

