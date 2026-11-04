# Gather1D — Annotated SIMT Example Guide

> This is a companion to `gath_1d.md` (the uploaded example). It annotates the key patterns
> for use by `simt-codegen`.
>
> **Model**: Pure SIMT (Model A) — no `__simt_vf__`, no warp functions.
> For the preferred SIMT VF (Model B) pattern, see `simt_platform_reference.md` and
> the SDK example at `02_features/03_simt/simt_gather/gather.asc`.

---

## Kernel Pattern (gath_1d.md lines 23–33)

```cpp
__global__ void gather_1d_custom(float* input, int32_t* index, float* output, uint64_t index_total_length)
{
    int32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= index_total_length) {
        return;
    }
    output[idx] = input[index[idx]];
}
```

**Key patterns:**
1. `__global__ void` — marks device function (Model A, no `__simt_vf__`)
2. Plain `float*` / `int32_t*` — no `__gm__` needed in pure model
3. Thread ID: `blockIdx.x * blockDim.x + threadIdx.x` — standard formula
4. Bounds check BEFORE any memory access — prevents OOB
5. Irregular access: `input[index[idx]]` — this is why SIMT is chosen (SIMD cannot vectorize random lookups)

---

## Host ACL Lifecycle (gath_1d.md lines 35–103)

```
aclInit(nullptr)
  aclrtSetDevice(device_id)
  aclrtCreateStream(&stream)
    aclrtMallocHost(&output_host, size)        ← page-locked host output
    aclrtMalloc(&input_device, size, HUGE)     ← device GM for each tensor
    aclrtMalloc(&index_device, size, HUGE)
    aclrtMalloc(&output_device, size, HUGE)
    aclrtMemcpy(input_device, ..., HOST_TO_DEVICE)
    aclrtMemcpy(index_device, ..., HOST_TO_DEVICE)
      <<<>>> kernel launch
    aclrtSynchronizeStream(stream)             ← MUST wait before reading result
    aclrtMemcpy(output_host, ..., DEVICE_TO_HOST)
    aclrtFree(input_device)
    aclrtFree(index_device)
    aclrtFree(output_device)
    aclrtFreeHost(output_host)
  aclrtDestroyStream(stream)
  aclrtResetDevice(device_id)
aclFinalize()
```

**Rules:**
- Every `aclrtMalloc` must have a matching `aclrtFree`
- Every `aclrtMallocHost` must have a matching `aclrtFreeHost`
- `aclrtSynchronizeStream` is mandatory between launch and D2H copy
- Error check: `aclGetRecentErrMsg()` after sync to detect kernel failures

---

## Launch Configuration (gath_1d.md lines 72–78)

```cpp
uint32_t blocks_per_grid = 56;
uint32_t threads_per_block = 256;
uint32_t dyn_ubuf_size = 0;

gather_1d_custom<<<blocks_per_grid, threads_per_block, dyn_ubuf_size, stream>>>(
    input_device, index_device, output_device, index_total_length);
```

**This is Model A (4-arg launch)**:
- `blocks_per_grid = 56` — one block per AI Core (`GetCoreNumAiv()` on A950PR)
- `threads_per_block = 256` — 8 warps per block
- `dyn_ubuf_size = 0` — no dynamic UB allocation
- Total threads = 56 × 256 = 14,336
- Total coverage: must be ≥ `index_total_length` (here: 56 × 256 = 14,336 ✓)

**For dynamic grid sizing** (preferred), use `GetCoreNumAiv()` (SDK pattern):
```cpp
auto mgr = platform_ascendc::PlatformAscendCManager::GetInstance();
numBlocks = mgr->GetCoreNumAiv();
threadsPerBlock = (total + numBlocks - 1) / numBlocks;
if (threadsPerBlock > 2048) { threadsPerBlock = 2048; recalculate numBlocks; }
```

---

## Verification Pattern (gath_1d.md lines 105–154)

```cpp
// 1. Generate deterministic test data
std::vector<float> input(100000);
for (uint32_t i = 0; i < 100000; i++) input[i] = i * 1.2f;

// 2. Generate index with known pattern
std::vector<int32_t> index(12288);
for (uint32_t i = 0; i < 12288; i++) index[i] = (i * 97 + 13) % 100000;

// 3. Compute golden on CPU
std::vector<float> golden(12288);
for (uint32_t i = 0; i < 12288; i++) golden[i] = input[index[i]];

// 4. Run kernel and compare
std::vector<float> output = gather_1d(input, index);
return verify_result(output, golden);  // exact match (integer indices, no fp tolerance)
```

**Rules:**
- Golden must match functional.py semantics exactly
- For gather: output is exact copy — use `std::equal` (no tolerance)
- For float compute: may need tolerance comparison

---

## Model B Equivalent

For the SIMT VF version of the same operator (preferred for production), the structure becomes:

```cpp
#include "simt_api/common_functions.h"

__simt_vf__ __launch_bounds__(256) inline void simt_gather_1d(
    __gm__ float* input, __gm__ int32_t* index,
    __gm__ float* output, uint32_t total)
{
    uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= total) return;
    output[idx] = input[index[idx]];
}

// NOTE: SDK examples use __global__ __vector__; __global__ __aicore__ may also work
__global__ __vector__ void gather_kernel(
// __global__ __aicore__ void gather_kernel(
    __gm__ float* input, __gm__ int32_t* index,
    __gm__ float* output, uint32_t total)
{
    asc_vf_call<simt_gather_1d>(dim3(256), input, index, output, total);
}

// Launch: gather_kernel<<<num_blocks, 0, stream>>>(...)  ← 3-arg
```

Differences from the uploaded gath_1d.md:
- `__simt_vf__` + `__gm__` pointers on VF
- Separate entry function with `asc_vf_call`
- 3-arg launch instead of 4-arg
- Can add warp/sync functions inside VF if needed later
