# Pass Details — Model B (SIMT VF Bridge)

## Compilation

**Quick Start**: See [simt_build_and_compile.md](simt_build_and_compile.md#quick-reference) for ready-to-copy commands.

Model B kernels require:
- `--asc-aicore-lang` (front end — **not** `-x cce`, which cannot resolve the ASC headers)
- `--npu-arch=dav-3510`
- `--cce-aicore-only` on device-only (`-c`) compiles — omitting it silently emits a
  host-only object with zero VF instantiations. Never pass it when linking a `main()`.
- `-D__NPU_TILING__` for msopgen projects
- `-I.` so the kernel finds its own tiling header

```bash
# Syntax + codegen check
bisheng --asc-aicore-lang --npu-arch=dav-3510 --cce-aicore-only \
  -std=c++17 -O2 -D__NPU_TILING__ \
  -I"$A/include" -I"$A/asc/include" -I"$A/asc/impl" -I. \
  -c my_kernel.asc -o my_kernel.o

nm -C my_kernel.o | grep -c 'simt_'   # must be > 0; exit 0 alone proves nothing
```

For full recipes, the measured flag comparison, and the error table, see
[simt_build_and_compile.md](simt_build_and_compile.md).

## Compilable Skeleton

Copy this, fill in the compute body:

```cpp
// === Model B Skeleton — SIMT VF Bridge ===
#include "acl/acl.h"
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
// Add as needed: simt_api/device_warp_functions.h, device_sync_functions.h,
// device_atomic_functions.h, math_functions.h, asc_fp16.h, asc_bf16.h

template <typename T>
__simt_vf__ __launch_bounds__(256) inline void simt_{op_name}(
    __gm__ T* input, __gm__ T* output, uint32_t totalElements)
{
    // Grid-stride loop: handles data-driven element counts safely.
    // Host must cap: numBlocks = min(ceil(N / threadsPerBlock), 32768)
    for (uint32_t i = blockIdx.x * blockDim.x + threadIdx.x;
         i < totalElements;
         i += gridDim.x * blockDim.x) {
        // TODO: compute body — derive from operator semantics
        output[i] = input[i];
    }
    // NOTE: The `if (idx >= N) return;` one-element pattern is valid ONLY for
    // fixed-small-N (e.g., known at compile time to be < 32768 * 256). For any
    // data-driven element count, use this grid-stride loop. See SKILL.md rule 8.
}

// Multi-dtype dispatch — ONLY if tiling header defines dtypeCode.
// For single-dtype operators (check op_desc.json), omit the switch
// and instantiate the template directly with the concrete type.
extern "C" __global__ __aicore__ void {op_name}_custom(
    GM_ADDR input, GM_ADDR output, GM_ADDR workspace, GM_ADDR tiling)
{
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);  // MANDATORY: else ld.lld "auto derivate failed"
    REGISTER_TILING_DEFAULT({OpName}CustomTilingData);
    GET_TILING_DATA(td, tiling);

    switch (td.dtypeCode) {
        case 0: asc_vf_call<simt_{op_name}<float>>(dim3(td.threadsPerBlock),
                    (__gm__ float*)input, (__gm__ float*)output, td.totalElements); break;
        case 1: asc_vf_call<simt_{op_name}<half>>(dim3(td.threadsPerBlock),
                    (__gm__ half*)input, (__gm__ half*)output, td.totalElements); break;
        case 2: asc_vf_call<simt_{op_name}<bfloat16_t>>(dim3(td.threadsPerBlock),
                    (__gm__ bfloat16_t*)input, (__gm__ bfloat16_t*)output, td.totalElements); break;
    }
}
```

<!-- shared: dtype_api_warning -->
**Multi-dtype API restrictions**: Not all SIMT APIs support `half`/`bfloat16_t`. If your compute body uses any of these, widen to `float` before the call and narrow after:

| API | Supported types | half/bf16 workaround |
|---|---|---|
| `asc_atomic_add` | All of float/int32/uint32/int64/uint64/half/bf16, but split across headers and memspaces — [dtype coverage matrix](simt_multi_dtype_guide.md#atomic-dtypes) | None for `half`/`bf16`: include `asc_fp16.h`/`asc_bf16.h` and the native overload resolves. Widen to `float` only for >16-bit accumulation precision |
| `asc_shfl_down/up/xor` | `float`, `uint32_t` | Widen to float before shuffle, narrow after |
| `asc_reduce_add` | `float`, `uint32_t` | Widen to float, reduce, narrow back |

For full workaround patterns (including CAS loop for half atomics), see [`simt_multi_dtype_guide.md`](simt_multi_dtype_guide.md).

## Required Reading

**In-repo, verified on A950** — read these:
- `references/operator_examples/torch_gather_20_20/gather_20_20_guide.md` — torch.gather (Model B, 20/20 cannbench) — structural template for all Model B operators.
  Note this example is an **msopgen project kernel**, not a standalone `.asc`: it uses `GET_TILING_DATA` and therefore needs `-D__NPU_TILING__` plus a generated tiling header to compile. See `references/simt_build_and_compile.md` §2.
- `references/operator_examples/axis_gather_example/` — axis-gather (`np.take`/`tf.gather`/`torch.index_select`/ONNX `Gather`), compile-verified. Uses the `GET_TILING_DATA` fallback from `references/get_tiling_data_pattern.md`, so it type-checks standalone.
- `references/simt_build_and_compile.md` — the build recipe and the three msopgen-only requirements
- `references/simt_operator_patterns.md` §Reduction — cross-warp float reduction: `asc_reduce_add` (intra-warp) + `asc_atomic_add` by warp leaders (cross-warp merge), with the two barriers the grid-stride row loop requires
- For transpose (UB-bitcast tiling), CumSum (axis-parallel), SpMV (CSR sparse), UB pre-staging, and multi-launch scatter patterns → `references/simt_operator_patterns.md`

**Optional — SDK examples, only if the devkit is present.** These paths resolve
only when `asc-devkit` has been vendored into `skills/cake-docs-search/`; it is
**not** part of this repo and is absent in the default environment. Check with
`ls skills/cake-docs-search/asc-devkit/` first, and skip this block if it is
missing — do not report the absence as an error, and do not stall waiting for it.

- `asc-devkit/examples/02_features/03_simt/simt_gather/gather.asc` — canonical Model B gather: `__simt_vf__` VF + `__global__ __vector__` entry + `asc_vf_call` + 3-arg launch + host ACL lifecycle
- `asc-devkit/examples/04_best_practices/15_simt_gather_with_ub/gather_v1.asc` — Model B gather variant with 1024 threads
- `asc-devkit/examples/04_best_practices/15_simt_gather_with_ub/gather_v2.asc` — Model B with UB pre-staging optimization: `asc_copy_gm2ub_align` + pipe sync + `__ubuf__` pointers in VF

---

### Pass 1 — `vf_pass` (Core Compute)

Emit the `__simt_vf__` VF function that contains the per-thread compute logic.

**1.1 Include Selection**

Emit includes based on the dtype analysis from Pass 0:

| Condition | Include |
|---|---|
| Always (Model B/C) | `#include "acl/acl.h"` |
| Always (Model B/C) | `#include "kernel_operator.h"` |
| Always (Model B/C) | `#include "simt_api/asc_simt.h"` |
| Using `half`/`half2` | `#include "simt_api/asc_fp16.h"` |
| Using `bfloat16_t`/`bfloat16x2_t` | `#include "simt_api/asc_bf16.h"` |
| Using warp functions | `#include "simt_api/device_warp_functions.h"` |
| Using sync/fence | `#include "simt_api/device_sync_functions.h"` |
| Using math functions | `#include "simt_api/math_functions.h"` |
| Using atomics | `#include "simt_api/device_atomic_functions.h"` |
| CPU debug mode | `#include "tikicpulib.h"` (guarded by `#if defined(ASCENDC_CPU_DEBUG)`) |

> **Multi-dtype**: For templated VF signatures, dtype dispatch in entry function, and warp-op widening helpers, read [`simt_multi_dtype_guide.md`](simt_multi_dtype_guide.md). Always include both `asc_fp16.h` and `asc_bf16.h` for multi-dtype kernels.

**1.2 VF Function Signature**

```cpp
__simt_vf__ __launch_bounds__(THREAD_COUNT) inline void VF_NAME(
    __gm__ TYPE* arg1, __gm__ TYPE* arg2, ..., uint32_t scalar_arg)
```

Rules:
- `__simt_vf__` annotation is mandatory
- `__launch_bounds__(N)` where N is from Pass 0 thread count (must be multiple of 32, ≤ 2048)
- `inline` is required
- All pointer args must have `__gm__` qualifier
- VF function must be a **free function** (NOT a class member)
- Args: raw pointers (`__gm__ T*`), `__gm__ const TilingData*`, and primitives (`uint32_t`). No by-value structs or C arrays.

**⚠️ Array metadata in the VF — immutable tiling pointer, never `__gm__` globals:**
When the VF needs per-launch array metadata (shapes, strides, perm, etc.), pass the
**immutable tiling struct pointer** (`__gm__ const <Op>CustomTilingData*`) directly as a VF
argument. The VF reads `tg->outputShape[d]` etc. through it. **Never** copy tiling arrays
into mutable `__gm__` globals in the entry and read them from the VF — the entry write and
VF read have no cross-core ordering (SKILL.md rule 7), causing stale/zero metadata on cold
launch. This was the dominant failure for both gather (flaky wrong values) and transpose
(all-zero output / 507035 crash). See `simt_debug_patterns.md` §1 and §15.

```cpp
// ✅ CORRECT — immutable tiling pointer, no race:
__gm__ const GatherCustomTilingData* tg =
    reinterpret_cast<__gm__ const GatherCustomTilingData*>(tiling);
asc_vf_call<simt_gather<T>>(dim3(td.threadsPerBlock), x, index, y, tg);
// VF reads tg->outputShape[d], tg->inputStrides[d] directly — immutable during launch.

// ❌ WRONG — mutable __gm__ globals, racy:
// __gm__ uint32_t g_outShape[8];
// for (d = 0; d < ndim; d++) g_outShape[d] = td.outShape[d];  // entry writes
// asc_vf_call<simt_gather<T>>(..., g_outShape, ...);           // VF reads — RACE
```

**1.3 Thread ID Calculation**

Always start the VF body with:
```cpp
uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
```

**1.4 Bounds Check**

Always check bounds before any memory access:
```cpp
if (idx >= total_length) return;
```

**1.5 Compute Body**

Translate the per-thread compute pattern (determined in Pass 0) from `functional.py` semantics to C++ scalar operations.

**Available inside VF** (verified in `__simt_vf__`) **and inside Model A `__global__` kernels** (verified in SDK examples: `histogram.asc`, `sobel_warp_shfl.asc`, `insert_hash_table.asc`, `matrix_transpose.asc`):
- Warp: `asc_shfl_down`, `asc_shfl_up`, `asc_shfl_xor`, `asc_reduce_add`, `asc_reduce_max`, `asc_reduce_min`, `asc_all`, `asc_any`, `asc_ballot`, `asc_activemask`
- Sync: `asc_syncthreads()` (block barrier), `asc_threadfence()` (memory ordering)
- Atomics: `asc_atomic_add`, `asc_atomic_sub`, `asc_atomic_max`, `asc_atomic_min`, etc. on UB or GM

**Reference**: `simt_gather/gather.asc` (VF function definition)

**Example output**:
```cpp
#include "acl/acl.h"
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"

__simt_vf__ __launch_bounds__(256) inline void simt_gather_1d(
    __gm__ float* input, __gm__ int32_t* index,
    __gm__ float* output, uint32_t index_total_length)
{
    uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= index_total_length) return;
    output[idx] = input[index[idx]];
}
```

⚠️ **After completing Pass 1**: Append to `codegen_reasoning.md` (format in SKILL.md §Codegen Reasoning Log: References used / What was adapted vs. derived / Key decisions).

**1.6+ SIMT Pattern & ISA References (all models)**

The following pattern references apply to **ALL SIMT models (A, B, C)**. Read the relevant file when the operator requires that pattern:

| Topic | File | Key contents |
|---|---|---|
| Warp ops | [`references/simt_warp_ops.md`](simt_warp_ops.md) | §1.6 Butterfly reduction, §1.14 native `asc_reduce_add`, §1.20 REDUX (16cy), §1.21 shuffle edge-lanes, §1.22 vote/ballot |
| Memory & UB | [`references/simt_memory_ops.md`](simt_memory_ops.md) | §1.7 GM scratch, §1.17 2D grid. Cache hints, bank conflicts, dynamic UB, `__ldg`/`__stg` → [`memory_optimization_guide.md`](memory_optimization_guide.md) |
| Advanced patterns | [`references/simt_advanced_patterns.md`](simt_advanced_patterns.md) | §1.8 iterative algorithm, §1.9 axis-parallel, §1.10 stream compaction, §1.11 atomic CAS, §1.12 histogram, §1.15 printf |
| ISA intrinsics | [`references/simt_platform_reference.md`](simt_platform_reference.md) | `Simt::` namespace APIs, `__cvt_*` casts, bit builtins, ISA cost model |

---

### Pass 2 — `entry_pass` (Dispatcher)

Emit the entry function that dispatches SIMT threads via `asc_vf_call`.

> **Entry annotation**: Both `__global__ __aicore__` and `__global__ __vector__` work for SIMT entry (verified on A950, 2026-06-10). Use `__aicore__` for msopgen projects (supports `REGISTER_TILING_DEFAULT`); use `__vector__` for standalone `.asc` files.

> **⚠️ CRITICAL — Workspace Buffer Restriction**: The OPP workspace buffer (4th `GM_ADDR` parameter) is **NOT SIMT-writable**. Any SIMT write to workspace causes `error code = 334: BIU→VEC data error`. Do NOT pass the workspace pointer to a `__simt_vf__` function for writing. Use tensor tails or dedicated scratch tensors instead. Set `workspace[0] = 0` in TilingFunc.

**2.1 Entry Function Signature**

```cpp
// For msopgen projects: use __aicore__ (supports tiling macros)
__global__ __aicore__ void ENTRY_NAME(
    GM_ADDR arg1, GM_ADDR arg2, ..., GM_ADDR workspace, GM_ADDR tiling)

// For standalone .asc files: __vector__ also works
__global__ __vector__ void ENTRY_NAME(
    __gm__ TYPE* arg1, __gm__ TYPE* arg2, ..., uint32_t scalar_arg)
```

Rules:
- `__global__ __vector__` annotation (or `__global__ __aicore__` — verify which is correct on hardware)
- All pointer args must have `__gm__` qualifier (same as VF)

**2.2 Entry Function Body**

For Model B (SIMT VF):
```cpp
asc_vf_call<VF_NAME>(dim3(THREAD_COUNT), arg1, arg2, ..., scalar_arg);
```

> **⚠️ `dim3(...)` is threads-per-block, NOT the grid size.** `asc_vf_call`'s first
> argument is the number of threads **within one block** (must be ≤ 2048; default 256).
> The grid (number of blocks) is set separately on the host via `SetBlockDim(numBlocks)`.
> Passing `dim3(totalBlocks)` or `dim3(numBlocks)` creates an impossibly large thread
> count → immediate 507035 crash on any non-trivial input. This was the cause of
> transpose's crash on every real-scale case. See SKILL.md rule 11.

**2.3 Optional: UB Pre-staging Optimization (Model B only)**

When a small, randomly-accessed input fits in VF-readable UB (≤8KB), add data pre-staging inside the VF function. VF threads cooperatively load from GM to static `__ubuf__` arrays, barrier, then read from UB (~22% speedup for gather).

**VF UB addressing rule (A5-validated, see `memory_optimization_guide.md` §6)**: Only static `__ubuf__` arrays declared inside the `__simt_vf__` function body support VF reads. The hard limit is 8192 bytes total. `LocalMemAllocator`-allocated UB is VF-writable but NOT VF-readable (error 341).

```cpp
__simt_vf__ __launch_bounds__(256) inline void VF_NAME(
    __gm__ T* input, __gm__ uint32_t* index, __gm__ T* output, ...)
{
    __ubuf__ T input_buf[INPUT_SIZE];  // must be ≤ 8KB total

    // VF cooperative load: threads copy GM → UB in parallel
    for (uint32_t i = threadIdx.x; i < INPUT_SIZE; i += blockDim.x) {
        input_buf[i] = input[i];
    }
    asc_syncthreads();

    // Now read from UB (on-chip SRAM speed)
    uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    output[idx] = input_buf[index[idx]];
}
```

Pre-staging constraint: total `__ubuf__` in VF function must be ≤ 8KB (float: max 2048 elements; half: max 4096). If the input exceeds this, skip pre-staging and use direct `__gm__` access.

**Constraints**:
- VF function MUST be defined BEFORE entry function in the file (no forward references)
- `asc_vf_call` args must match VF function signature exactly

**Reference**: `simt_gather/gather.asc` (entry function)

**Example output**:
```cpp
__global__ __aicore__ void gather_kernel(
    GM_ADDR input, GM_ADDR index, GM_ADDR output,
    GM_ADDR workspace, GM_ADDR tiling)
{
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);  // MANDATORY: else ld.lld "auto derivate failed"
    REGISTER_TILING_DEFAULT(GatherCustomTilingData);
    GET_TILING_DATA(tilingData, tiling);

    asc_vf_call<simt_gather_1d>(dim3(tilingData.threadsPerBlock),
        (__gm__ float*)input, (__gm__ int32_t*)index,
        (__gm__ float*)output, tilingData.totalElements);
}
```

---

<!-- shared: host_pass_template -->
### Pass 3 — `host_pass` (ACL Runtime + Launch)

Emit the host function following the ACL lifecycle.

**3.1 ACL Lifecycle**

```cpp
void run_kernel(/* host input pointers, shapes */)
{
    // ── ACL Init ──
    aclInit(nullptr);
    int32_t device_id = 0;
    aclrtSetDevice(device_id);

    aclrtStream stream;
    aclrtCreateStream(&stream);

    // ── Allocate host output (page-locked) ──
    void* output_host = nullptr;
    aclrtMallocHost(&output_host, output_size_bytes);

    // ── Allocate device memory ──
    void* input_device = nullptr;
    aclrtMalloc(&input_device, input_size_bytes, ACL_MEM_MALLOC_HUGE_FIRST);
    // ... repeat for each input and output tensor

    // ── Copy inputs H2D ──
    aclrtMemcpy(input_device, input_size_bytes, input_host, input_size_bytes, ACL_MEMCPY_HOST_TO_DEVICE);
    // ... repeat for each input tensor

    // ── Grid sizing ──
    uint32_t num_blocks = (total_elements + THREAD_COUNT - 1) / THREAD_COUNT;

    // ── Kernel launch (3-arg for Model B/C) ──
    uint32_t dyn_ubuf_size = 0;
    ENTRY_KERNEL<<<num_blocks, dyn_ubuf_size, stream>>>(
        (TYPE*)input_device, (TYPE*)index_device, (TYPE*)output_device, total_elements);

    // ── Synchronize ──
    aclrtSynchronizeStream(stream);

    // ── Copy output D2H ──
    aclrtMemcpy(output_host, output_size_bytes, output_device, output_size_bytes, ACL_MEMCPY_DEVICE_TO_HOST);

    // ── Cleanup ──
    aclrtFree(input_device);
    aclrtFree(index_device);
    aclrtFree(output_device);
    aclrtFreeHost(output_host);
    aclrtDestroyStream(stream);
    aclrtResetDevice(device_id);
    aclFinalize();
}
```

**3.2 Grid Sizing**

Default (static):
```cpp
uint32_t num_blocks = (total_elements + THREAD_COUNT - 1) / THREAD_COUNT;
```

Dynamic (via platform query):
```cpp
auto mgr = platform_ascendc::PlatformAscendCManager::GetInstance();
uint32_t num_blocks = mgr->GetCoreNumAiv();
uint32_t threads_per_block = (total_elements + num_blocks - 1) / num_blocks;
if (threads_per_block > 2048) {
    threads_per_block = 2048;
    num_blocks = (total_elements + threads_per_block - 1) / threads_per_block;
}
```

**3.3 Launch Syntax**

| Model | Launch syntax | Args |
|---|---|---|
| B/C | `entry<<<blocks, ubuf, stream>>>(...)` | 3-arg: blocks, dyn_ubuf_size, stream |
| A | `kernel<<<blocks, threads, ubuf, stream>>>(...)` | 4-arg: blocks, threads_per_block, dyn_ubuf_size, stream |

**3.4 CPU Debug Mode**

Guard with `#if defined(ASCENDC_CPU_DEBUG)`:
```cpp
#if defined(ASCENDC_CPU_DEBUG)
    #include "tikicpulib.h"
    AscendC::SetKernelMode(AscendC::KernelMode::AIV_MODE);
    ICPU_RUN_KF(ENTRY_KERNEL, num_blocks, input_device, index_device, output_device, total);
#else
    ENTRY_KERNEL<<<num_blocks, dyn_ubuf_size, stream>>>(input_device, index_device, output_device, total);
#endif
```

**Memory lifecycle rules**:
- Every `aclrtMalloc` must have a matching `aclrtFree`
- Every `aclrtMallocHost` must have a matching `aclrtFreeHost`
- `aclrtSynchronizeStream` is mandatory between kernel launch and D2H copy
- Use `aclrtMemset(ptr, size, 0, size)` to zero-initialize device memory (e.g., atomic counters for stream compaction)
- Error check: `aclGetRecentErrMsg()` after sync to detect kernel failures

**Reference**: `simt_gather/gather.asc` (host function)

---

<!-- shared: main_pass_template -->
### Pass 4 — `main_pass` (Test Harness + Verification)

Emit `main()` with test data generation, golden computation, kernel invocation, and verification.

**4.1 Test Data Generation**

Generate deterministic test data matching input shapes from `op_desc.json`:
```cpp
// Input data — deterministic
std::vector<float> input(input_size);
for (uint32_t i = 0; i < input_size; i++) {
    input[i] = i * 1.2f;
}

// Index data — deterministic with known pattern
std::vector<int32_t> index(index_size);
for (uint32_t i = 0; i < index_size; i++) {
    index[i] = (i * 97 + 13) % input_size;  // pseudo-random but deterministic
}
```

**4.2 Golden Computation**

CPU reference matching `functional.py` semantics:
```cpp
// Golden output — exact match for gather (no FP tolerance)
std::vector<float> golden(index_size);
for (uint32_t i = 0; i < index_size; i++) {
    golden[i] = input[index[i]];
}
```

**4.3 Kernel Invocation**

Call the host function from Pass 3.

**4.4 Verification**

**Tolerance tiers** (select based on operator category):

| Category | Operators | Tolerance |
|---|---|---|
| Exact match | Gather, Scatter, Sort, Transpose, Histogram | `output[i] == golden[i]` |
| Relative (float32) | Softmax, Exp, CumSum, ScatterAdd (float) | `|out - gold| <= 1e-5 * |gold| + 1e-8` |
| Approximate (half) | Any half-precision operator | `|out - gold| <= 1e-3 * |gold| + 1e-4` |

```cpp
bool verify(const float* output, const float* golden, uint32_t count, bool exact = true) {
    for (uint32_t i = 0; i < count; i++) {
        if (exact) {
            if (output[i] != golden[i]) {
                printf("MISMATCH at [%u]: got %f, expected %f\n", i, output[i], golden[i]);
                return false;
            }
        } else {
            float diff = std::fabs(output[i] - golden[i]);
            if (diff > 1e-5f * std::fabs(golden[i]) + 1e-8f) {
                printf("MISMATCH at [%u]: got %f, expected %f (diff=%e)\n", i, output[i], golden[i], diff);
                return false;
            }
        }
    }
    return true;
}
```

**Reference**: `simt_gather/gather.asc` (main function and verification)
