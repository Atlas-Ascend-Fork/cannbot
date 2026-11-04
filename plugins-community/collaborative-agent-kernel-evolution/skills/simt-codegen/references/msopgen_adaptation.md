# msopgen Project Adaptation for SIMT Operators

> How to adapt the msopgen-generated AscendC project structure for SIMT operators.
> SIMT operators use the same project layout as Vector/CV operators — the lowering
> skill replaces the kernel skeleton and adapts the host tiling.

---

## Step 0: Generate the Project

```bash
msopgen gen \
  -i output/{op_name}/{op_name}_project.json \
  -c "ai_core-ascend950pr" \
  -lan cpp \
  -out {OpNameCustom}
```

This produces:

```
{OpNameCustom}/
├── CMakeLists.txt              # top-level build (keep as-is)
├── CMakePresets.json            # ASCEND_COMPUTE_UNIT: "ascend950" (keep as-is)
├── build.sh                    # builds .run package (keep as-is)
├── op_host/
│   ├── CMakeLists.txt          # (keep as-is)
│   ├── {op_name}_custom.cpp    # ← ADAPT: tiling for SIMT grid/block config
│   └── ...
├── op_kernel/
│   ├── CMakeLists.txt          # (keep as-is)
│   ├── {op_name}_custom.cpp    # ← REPLACE: swap skeleton with SIMT kernel
│   └── {op_name}_custom_tiling.h  # ← ADAPT: SIMT tiling data structure
└── framework/                  # (keep as-is)
```

---

## Step 1: Adapt Tiling Data Structure

### msopgen generates (Vector pattern):

```cpp
// op_kernel/{op_name}_custom_tiling.h
struct {OpName}CustomTilingData {
    uint32_t size;
};
```

### SIMT adaptation (Model B):

```cpp
struct {OpName}CustomTilingData {
    uint32_t totalElements;     // total work items (e.g., index_total_length)
    uint32_t blocksPerGrid;     // number of thread blocks
    uint32_t threadsPerBlock;   // threads per block (multiple of 32, ≤ 2048)
    uint32_t dynUBufSize;       // 0 for Model A/B, > 0 for Model C
    // operator-specific params:
    uint32_t inShape0;          // e.g., input rows
    uint32_t inShape1;          // e.g., input cols
};
```

---

## Step 2: Adapt Host Tiling Function

### msopgen generates:

```cpp
// op_host/{op_name}_custom.cpp
static ge::graphStatus TilingFunc(gert::TilingContext* context) {
    auto* tiling = context->GetTilingData<TilingData>();
    const auto* shape = context->GetInputShape(0);
    int32_t data_sz = 1;
    for (int i = 0; i < shape->GetStorageShape().GetDimNum(); i++)
        data_sz *= shape->GetStorageShape().GetDim(i);
    tiling->size = data_sz;
    context->SetBlockDim(8);
    // ...
}
```

### SIMT adaptation (Model B):

```cpp
static ge::graphStatus TilingFunc(gert::TilingContext* context) {
    auto* tiling = context->GetTilingData<TilingData>();

    // Read input shapes
    const auto* inputShape = context->GetInputShape(0);
    const auto* indexShape = context->GetInputShape(1);
    tiling->inShape0 = inputShape->GetStorageShape().GetDim(0);
    tiling->inShape1 = inputShape->GetStorageShape().GetDim(1);

    // Calculate total work items
    tiling->totalElements = 1;
    for (int i = 0; i < indexShape->GetStorageShape().GetDimNum(); i++)
        tiling->totalElements *= indexShape->GetStorageShape().GetDim(i);

    // SIMT grid/block config
    tiling->threadsPerBlock = 256;  // default: 8 warps
    tiling->blocksPerGrid =
        (tiling->totalElements + tiling->threadsPerBlock - 1) / tiling->threadsPerBlock;
    tiling->dynUBufSize = 0;  // Model B: no UB allocation

    // SetBlockDim = blocksPerGrid for SIMT
    context->SetBlockDim(tiling->blocksPerGrid);

    size_t* workspace = context->GetWorkspaceSizes(1);
    workspace[0] = 0;
    return ge::GRAPH_SUCCESS;
}
```

### For Model C, additionally:

```cpp
    // Model C: calculate dynUBufSize
    uint32_t elementsPerBlock = tiling->totalElements / tiling->blocksPerGrid;
    tiling->dynUBufSize = elementsPerBlock * sizeof(float) * 2;  // 2 UB buffers
    // Constraint: total UB ≤ 128KB (SIMT DataCache limit)
```

---

## Step 2b: The tiling contract (multi-field TilingFunc — attrs, dtype dispatch, shape)

**RULE: every field the kernel reads from
`<Op>CustomTilingData` MUST be assigned in `TilingFunc`.** A field the host leaves unset arrives
as **0** on-device → `dim3(0)` invalid grid, `innerSize = 0` div-by-zero, or the wrong dtype
branch. This is the root cause of **AICORE error 507035**. The gather example above is the
*minimal* case (one shape, no attrs, fixed dtype); most Level-2/3 ops (scatter, arg_max, cummin,
segment-sum) need the fuller pattern below.

Derive each field from the op's real inputs — never hardcode:

| Field | Source |
|---|---|
| `totalElements` / `totalUpdates` | product of the driving tensor's shape (e.g. `numel(indices)`) |
| `dataShape[i]` | `GetInputShape(0)->GetStorageShape().GetDim(i)` (flatten trailing dims into an inner-size slot if the kernel indexes `dim*inner + col`) |
| `dataStrides[i]` | row-major running product of `dataShape` |
| `<attr>` (dim, reduce, k, …) | `context->GetAttrs()->GetAttrPointer<int64_t>(<index>)` — index matches OpDef `this->Attr(...)` order; guard the null pointer |
| `dtypeCode` | map `context->GetInputDesc(0)->GetDataType()` (`ge::DT_FLOAT→0`, `DT_FLOAT16→1`, `DT_BF16→2`, `DT_INT32→3`, `DT_INT64→4`) — **NOT `GetInputDataType`, which does not exist on `TilingContext`** |
| `indicesDtype` | `context->GetInputDesc(1)->GetDataType() == ge::DT_INT64 ? 1 : 0` |
| `threadsPerBlock` | 256 (warp-aligned) |
| `numBlocks` | `ceil(totalElements / threadsPerBlock)`, min 1 — **and** `context->SetBlockDim(numBlocks)` |

```cpp
static uint32_t DataDtypeCode(ge::DataType dt) {
  switch (dt) {
    case ge::DT_FLOAT: return 0;  case ge::DT_FLOAT16: return 1;
    case ge::DT_BF16:  return 2;  case ge::DT_INT32:   return 3;
    case ge::DT_INT64: return 4;  default:             return 0;
  }
}

static ge::graphStatus TilingFunc(gert::TilingContext* context) {
  auto* tiling = context->GetTilingData<OpCustomTilingData>();
  const gert::Shape& dataShape = context->GetInputShape(0)->GetStorageShape();
  const gert::Shape& idxShape  = context->GetInputShape(1)->GetStorageShape();
  const uint32_t dataRank = dataShape.GetDimNum();
  tiling->dataRank = dataRank;

  // attrs — index matches this->Attr(...) declaration order in the OpDef
  int64_t dim = 0, reduce = 0;
  const gert::RuntimeAttrs* attrs = context->GetAttrs();
  if (attrs != nullptr) {
    const int64_t* p0 = attrs->GetAttrPointer<int64_t>(0);
    const int64_t* p1 = attrs->GetAttrPointer<int64_t>(1);
    if (p0) dim = *p0;  if (p1) reduce = *p1;
  }
  if (dim < 0) dim += static_cast<int64_t>(dataRank);
  tiling->dim = static_cast<uint32_t>(dim);
  tiling->reduceMode = static_cast<uint32_t>(reduce);

  for (uint32_t i = 0; i < 8; i++)
    tiling->dataShape[i] = (i < dataRank) ? (uint32_t)dataShape.GetDim(i) : 0;
  uint32_t innerSize = 1;
  for (uint32_t i = 1; i < dataRank; i++) innerSize *= (uint32_t)dataShape.GetDim(i);
  tiling->dataShape[1] = innerSize;  // kernel: out = idx*innerSize + col

  uint32_t totalUpdates = 1;
  for (uint32_t i = 0; i < idxShape.GetDimNum(); i++) totalUpdates *= (uint32_t)idxShape.GetDim(i);
  tiling->totalUpdates = totalUpdates;

  tiling->dtypeCode    = DataDtypeCode(context->GetInputDesc(0)->GetDataType());  // NOT GetInputDataType (absent on TilingContext)
  tiling->indicesDtype = (context->GetInputDesc(1)->GetDataType() == ge::DT_INT64) ? 1u : 0u;

  const uint32_t threadsPerBlock = 256;
  uint32_t numBlocks = (totalUpdates + threadsPerBlock - 1) / threadsPerBlock;
  if (numBlocks == 0) numBlocks = 1;
  tiling->threadsPerBlock = threadsPerBlock;
  tiling->numBlocks = numBlocks;

  context->SetBlockDim(numBlocks);
  size_t* ws = context->GetWorkspaceSizes(1);
  ws[0] = 0;  // SIMT: no OPP workspace (error 334)
  return ge::GRAPH_SUCCESS;
}
```

**Verify before finishing:** diff the field set the kernel reads out of `<Op>CustomTilingData`
against the field set `TilingFunc` assigns. Any field in the first set and not the second arrives
as 0 on-device. Do NOT leave a field at a hardcoded constant or `0` with a
"compile-only"/"populated at runtime" comment; that is a stub, and it will surface as a wrong
result rather than a build failure.

---

## Step 2c: Array-valued (ListInt) attributes — e.g. transpose `perm`, `axes`, `dims`

Scalar attrs (`Int`/`Bool`: softmax `dim`, top_k `k`/`largest`) are easy — declare `this->Attr("k").Int()`
and read `GetAttrPointer<int64_t>(idx)`. **Array attrs (`ListInt`) are where codegen tends to stub**
(transpose dropped `perm` and copied InferShape). Do NOT stub them and do NOT store them as raw device
pointers in the tiling struct (`uint64_t perm_ptr` set to 0 is the classic crash). Wire them end-to-end:

**1. OpDef (op_host) — declare it, matching the op_desc `attributes_meta`:**
```cpp
this->Attr("perm").ListInt();     // index order here = the GetAttrs() index later
```
(`attr-not-declared` fires if an op_desc attr is missing here.)

**2. InferShape — actually use it (no trivial copy):**
```cpp
// GetListInt returns const TypedContinuousVector<int64_t>*; call GetData() directly.
// Do NOT assign to a ContinuousVector* — it inherits that PRIVATELY (inaccessible-base).
const gert::TypedContinuousVector<int64_t>* permVec = context->GetAttrs()->GetListInt(0);
const int64_t* perm = permVec->GetData();
size_t n = x_shape->GetDimNum();
y_shape->SetDimNum(n);
for (size_t i = 0; i < n; i++) y_shape->SetDim(i, x_shape->GetDim(perm[i]));  // output dim i = input dim perm[i]
```
(`infershape-trivial-copy` fires if a shape-permuting attr is present but InferShape only copies.)

**3. Tiling — store the array INLINE (fixed max-8), never a device pointer:**
```cpp
struct OpCustomTilingData { ...; uint32_t perm[8]; uint32_t outputShape[8]; uint32_t inputStrides[8]; };
```
TilingFunc reads the ListInt and fills the inline arrays (+ row-major strides):
```cpp
const gert::TypedContinuousVector<int64_t>* pv = context->GetAttrs()->GetListInt(0);
const int64_t* perm = pv->GetData();
for (uint32_t i = 0; i < ndim; i++) {
  tiling->perm[i]        = (uint32_t)perm[i];
  tiling->outputShape[i] = (uint32_t)inShape.GetDim(perm[i]);
  tiling->inputStrides[i]= inStrides[i];
}
```

**4. Kernel — read array metadata from the IMMUTABLE tiling buffer in GM.**
`GET_TILING_DATA(td, tiling)` yields a *local* struct copy; `td.perm` is not a `__gm__` pointer, so it
can't be passed to `asc_vf_call`. **⚠️ Do NOT copy the arrays into mutable `__gm__` global arrays** —
that pattern is RACY: the entry writes the globals and the VF reads them with **no fence/barrier**, so a
cold launch reads stale/zero values (round_2 A5 bugs **E2/E6**: gather flaky, transpose all-zero /
crash 507035 — and scatter's *scalar* globals raced too). Instead reinterpret the tiling `GM_ADDR`
(the serialized tiling struct is immutable — written once by the host) and pass its array members:
```cpp
GET_TILING_DATA(td, tiling);                    // scalars: td.ndim, td.totalBlocks, ...
__gm__ const OpCustomTilingData* tg =
    reinterpret_cast<__gm__ const OpCustomTilingData*>(tiling);
asc_vf_call<vf<T>>(dim3(td.totalBlocks), (__gm__ const T*)x, (__gm__ T*)y,
                   tg->inputStrides, tg->outputShape, tg->perm, td.ndim, td.totalElements);
```
Bounds-guard any attr-derived index (`if (perm[d] < ndim)`) before using it to index a local array — an
out-of-range value is an out-of-bounds stack write → device error 507035.
> **A5-verification pending:** this immutable-GM-read replaces the racy `__gm__`-globals pattern; the
> transpose canary (deterministic all-zero → correct) is the confirmation. Treat a mutable `__gm__`
> global array, or a scalar-global write in the entry, as the anti-pattern this replaces.

**5. Wrapper (`<op>.cpp`) — correct include + pass the IntArrayRef.**
Include **`pytorch_npu_helper.hpp`** (NOT `OpAdapter.h`/`NPUNativeFunctions.h` — those leave
`EXEC_NPU_CMD`/`aclnn<Op>Custom` undeclared and the pybind build fails). Take `at::IntArrayRef perm`,
permute the output shape, and forward perm to the generated aclnn API:
```cpp
#include "pytorch_npu_helper.hpp"
...
EXEC_NPU_CMD(aclnnTransposeCustom, x, perm, y);   // perm is the ListInt attr
```

---

## Wrapper Rules

### ⚠️ Enum / mode attr — single source of truth (SKILL.md rule related: H2)

Any op with a mode/attr enum (reduce modes, activation types, padding modes) shared between
the wrapper and the kernel must define the encoding **once**. Two independently-authored
mappings will diverge — and the divergence is invisible to local tests when both sides agree
internally (scatter round 3 F2: wrapper had amax=3/amin=4, kernel had amax=4/amin=3).

**Rule:** Define mode encodings as `constexpr` or `enum` in the **tiling header**
(`{op_name}_custom_tiling.h`). The wrapper, kernel, and any benchsite plugin must all
`#include` or reference this single definition. Never hand-author the same mapping in two
places.

```cpp
// op_kernel/{op_name}_custom_tiling.h
enum ReduceMode : uint32_t {
    REDUCE_NONE = 0, REDUCE_ADD = 1, REDUCE_MUL = 2, REDUCE_AMIN = 3, REDUCE_AMAX = 4
};
// Both wrapper and kernel #include this header → one source of truth.
```

### ⚠️ EXEC_NPU_CMD / ACLNN_CMD lvalue binding (SKILL.md rule related: H6)

`EXEC_NPU_CMD` and `ACLNN_CMD` macros take every argument by non-const lvalue reference
(`ConvertTypes(Ts&...)`). Passing literals (`(int64_t)100`), temporaries, or cast
expressions **fails to compile**.

**Rule:** Every scalar argument to `EXEC_NPU_CMD`/`ACLNN_CMD` must be a **named lvalue
variable**. Never pass literals or temporaries. Bind to a named local first:

```cpp
// WRONG — compile error (rvalue reference):
EXEC_NPU_CMD(aclnnScatterCustom, x, idx, upd, y, (int64_t)dim, (int64_t)reduce, (int64_t)0);

// CORRECT — named lvalues:
int64_t dim_val = dim;
int64_t reduce_val = reduce_code;
int64_t phase = 0;
EXEC_NPU_CMD(aclnnScatterCustom, x, idx, upd, y, dim_val, reduce_val, phase);
```

---

## Adding a Scratch Tensor as Extra Op Output (H7)

When the kernel needs cross-launch state (e.g., the `win` buffer for the 2-launch winner
pattern, or an fp32 accumulator for half/bf16 reductions), register it as an **extra op
output** — NOT workspace (workspace triggers error 334 on A5).

### 1. OpDef — register the scratch output

```cpp
// In the OpDef class body, after the real output:
this->Output("y")          // real output
    .ParamType(REQUIRED)
    .DataType({DT_FLOAT16, DT_FLOAT, ...})
    .Format({FORMAT_ND, ...});
this->Output("scratch")    // scratch buffer for cross-launch state
    .ParamType(REQUIRED)
    .DataType({DT_INT32, ...})   // match the scratch dtype (e.g., int32 for winner IDs)
    .Format({FORMAT_ND, ...});
```

### 2. InferShape — set scratch shape

```cpp
// In InferShapeAndType:
auto data_shape = op.GetInputDescByName("x")->GetShape();
op.GetOutputDescByName("scratch")->SetShape(ge::Shape(data_shape));  // same shape as output
```

### 3. TilingFunc — no special handling needed

The scratch tensor's device pointer is passed through the kernel's GM parameter list like
any other tensor. No additional tiling fields needed for the scratch itself (the kernel
already knows its shape from the output shape fields).

### 4. Wrapper — allocate and pass scratch

```cpp
auto scratch = at::zeros(y.sizes(), y.options().dtype(at::kInt));
EXEC_NPU_CMD(aclnnOpCustom, x, idx, upd, y, scratch, dim_val, reduce_val, phase);
```

> ⚠️ **Stub regeneration required.** Any OpDef I/O change (adding/removing an Output)
> makes the pre-generated `op_api/aclnn_{op}.{h,cpp}` stubs stale. The bundle must ship
> regenerated stubs from `build_out/autogen/`. See hardening spec H11.

---

## Step 3: Replace Kernel Code

### msopgen generates (Vector skeleton):

```cpp
// op_kernel/{op_name}_custom.cpp
#include "kernel_operator.h"
#include "{op_name}_custom_tiling.h"

extern "C" __global__ __aicore__ void {op_name}_custom(
    GM_ADDR input, GM_ADDR index, GM_ADDR output,
    GM_ADDR workspace, GM_ADDR tiling)
{
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);  // MANDATORY: else ld.lld "auto derivate failed"
    REGISTER_TILING_DEFAULT({OpName}CustomTilingData);
    GET_TILING_DATA(tilingData, tiling);
    // TODO: user kernel impl
}
```

### SIMT replacement (Model B):

```cpp
// op_kernel/{op_name}_custom.cpp
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
#include "{op_name}_custom_tiling.h"

// ── VF function (before entry) ──
__simt_vf__ __launch_bounds__(256) inline void simt_{op_name}(
    __gm__ float* input,
    __gm__ uint32_t* index,
    __gm__ float* output,
    uint32_t in_shape0,
    uint32_t in_shape1,
    uint32_t totalElements)
{
    uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= totalElements) return;
    // ... per-thread compute ...
}

// ── Entry function ──
// Uses __aicore__ to integrate with msopgen's tiling registration.
// Reads tiling data, then dispatches to __simt_vf__ via asc_vf_call.
extern "C" __global__ __aicore__ void {op_name}_custom(
    GM_ADDR input, GM_ADDR index, GM_ADDR output,
    GM_ADDR workspace, GM_ADDR tiling)
{
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);  // MANDATORY: else ld.lld "auto derivate failed"
    REGISTER_TILING_DEFAULT({OpName}CustomTilingData);
    GET_TILING_DATA(tilingData, tiling);

    asc_vf_call<simt_{op_name}>(
        dim3(tilingData.threadsPerBlock),
        (__gm__ float*)input,
        (__gm__ uint32_t*)index,
        (__gm__ float*)output,
        tilingData.inShape0,
        tilingData.inShape1,
        tilingData.totalElements);
}
```

### Key adaptation: `__aicore__` entry bridges tiling → SIMT

The msopgen project uses `__aicore__` entry points with `GM_ADDR` parameters and tiling data. The SIMT VF function is called from inside this entry via `asc_vf_call`. This bridges the two worlds:

- **msopgen side**: `__aicore__` + `REGISTER_TILING` + `GET_TILING_DATA` — standard operator registration
- **SIMT side**: `asc_vf_call<VF>(dim3(N), ...)` — SIMT thread dispatch

The standalone experiments used `__global__ __vector__` entries with hardcoded params. In the msopgen project, the entry is `__global__ __aicore__` and reads params from tiling data instead.

---

## Verified Answers (tested on A950, CANN 9.1.0-beta.1, 2026-06-10)

Test project: Gather1D Model B, generated via msopgen and built with `source build.sh`. The
equivalent kernel source is in `operator_examples/gather_1d/`.

### `.cpp` extension works for SIMT

**Confirmed**: `npu_op_kernel_sources` compiles SIMT features (`__simt_vf__`, `asc_vf_call`, `blockIdx`/`threadIdx`) from `.cpp` files. No need to rename to `.asc`. The msopgen-generated `.cpp` file is used directly.

### `__aicore__` entry works with `asc_vf_call`

**Confirmed**: `extern "C" __global__ __aicore__ void` entry dispatches SIMT threads via `asc_vf_call<VF>(dim3(N), ...)` without issue. The `REGISTER_TILING_DEFAULT` + `GET_TILING_DATA` macros work inside `__aicore__` context, and the tiling data is correctly passed to the VF function.

This means the msopgen skeleton requires **no structural changes** — just inject the VF function before the entry and replace the TODO with `asc_vf_call`.

### `ascend950` SoC resolves natively

**Bonus finding**: The `opc` tool (called by `npu_op_kernel_sources`) resolves `ascend950` to the correct hardware target without the manual `Ascend950PR_9579` patching needed by standalone builds. The `ASCEND_COMPUTE_UNIT: "ascend950"` in `CMakePresets.json` and `AddConfig("ascend950")` in OpDef are sufficient.

---

## Summary: What Changes vs What Stays

| Component | Action |
|---|---|
| `CMakeLists.txt` (top-level) | Keep as-is |
| `CMakePresets.json` | Keep as-is (`ascend950`) |
| `build.sh` | Keep as-is |
| `op_kernel/{op_name}_custom_tiling.h` | **Adapt**: add grid/block fields |
| `op_kernel/{op_name}_custom.cpp` | **Replace**: SIMT VF + entry with tiling bridge |
| `op_host/{op_name}_custom.cpp` | **Adapt**: compute grid/block config in TilingFunc |
| `op_host/` registration (OpDef) | Keep as-is (`AddConfig("ascend950")`) |
| `framework/` | Keep as-is |
