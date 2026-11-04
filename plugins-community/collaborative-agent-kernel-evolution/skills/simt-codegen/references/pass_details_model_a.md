# Pass Details — Model A (Pure SIMT)

## Compilation

Device object (`-c`) — this is what a codegen pass produces:

```bash
A=$ASCEND_HOME_PATH/$(uname -m)-linux
bisheng --asc-aicore-lang --npu-arch=dav-3510 -cce-enable-puresimt \
  --cce-aicore-only -std=c++17 -O2 \
  -I"$A/include" -I"$A/asc/include" -I"$A/asc/impl" -I. \
  -c my_op.asc -o my_op.o

# Artifact gate — exit 0 alone proves nothing. Same two assertions as SKILL.md:
nm -C my_op.o | grep -c 'simt_'      # must be > 0 -- puresimt emits a `..._simt_entry` clone,
                                     #   so this works for Model A despite no __simt_vf__
nm    my_op.o | grep -c 'Kernel_Type'  # must be >= 1
```

<!-- claim: asc-include-root · also in: pass_details_model_c.md · find with: grep -rn "claim: asc-include-root" skills/simt-codegen · edit all sites together -->
> The three `-I` paths are **belt-and-braces, not load-bearing**: `--asc-aicore-lang` puts
> the ASC tree on the search path itself, and clang silently ignores `-I` dirs that do not
> exist. The build succeeds either way — verified identical 6232 B object from both the
> correct root and the old `compiler/tikcpp` one. Fixed anyway so the recipe does not teach
> a wrong path. If a vendor header is missing, the cause is the front end (`-x cce` vs
> `--asc-aicore-lang`), never a missing `-I` — see `SKILL.md` "A missing vendor header".


`--cce-aicore-only` **is** required on Model A `-c` compiles. Measured on
`operator_examples/gather_1d/gath_1d.asc`: without it, exit 0 and a 42184 B
host-only object (`T main`, `T gather_1d(std::vector<float>&, ...)`, no
`Kernel_Type`); with it, 3864 B carrying
`.AIV_Kernel_Type__Z16gather_1d_customPfPiS_m` plus 5 `.ParamInfo_*`.
It does **not** conflict with `-cce-enable-puresimt`.

The conflict is **link-time only**. When you link a host+device executable
(the `main()` harness in the skeleton below), drop `--cce-aicore-only` — with it
the link fails `bisheng: error: cannot specify -o when generating multiple
output files`.

See `simt_build_and_compile.md` for the full flag rationale and the error table.

## Compilable Skeleton

Copy this, fill in the compute body:

```cpp
// === Model A Skeleton — pure SIMT ===
#include "acl/acl.h"
#include "simt_api/asc_simt.h"
// Add as needed: simt_api/device_warp_functions.h, device_sync_functions.h,
// device_atomic_functions.h, math_functions.h, asc_fp16.h, asc_bf16.h

template <typename T>
__global__ __launch_bounds__(256) void {op_name}_kernel(
    T* input, T* output, uint32_t totalElements)
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
extern "C" void launch_{op_name}(void* input, void* output,
    uint32_t totalElements, uint32_t dtypeCode,
    uint32_t blocks, uint32_t threads, uint32_t ubuf, void* stream)
{
    switch (dtypeCode) {
        case 0: {op_name}_kernel<float><<<blocks, threads, ubuf, (aclrtStream)stream>>>(
                    (float*)input, (float*)output, totalElements); break;
        case 1: {op_name}_kernel<half><<<blocks, threads, ubuf, (aclrtStream)stream>>>(
                    (half*)input, (half*)output, totalElements); break;
        case 2: {op_name}_kernel<bfloat16_t><<<blocks, threads, ubuf, (aclrtStream)stream>>>(
                    (bfloat16_t*)input, (bfloat16_t*)output, totalElements); break;
    }
}
```

<!-- shared: dtype_api_warning -->
**Multi-dtype API restrictions**: Not all SIMT APIs support `half`/`bfloat16_t`. If your compute body uses any of these, widen to `float` before the call and narrow after:

| API | Supported types | half/bf16 workaround |
|---|---|---|
| `asc_atomic_add` | `float`, `int32_t`, `uint32_t`, `int64_t`, `uint64_t` | Widen accumulator to `float`, use `asc_atomic_add(__gm__ float*, float)` |
| `asc_shfl_down/up/xor` | `float`, `uint32_t` | Widen to float before shuffle, narrow after |
| `asc_reduce_add` | `float`, `uint32_t` | Widen to float, reduce, narrow back |

For full workaround patterns (including CAS loop for half atomics), see [`simt_multi_dtype_guide.md`](simt_multi_dtype_guide.md).

## Required Reading

**In-repo, verified on A950** — read these:
- `references/operator_examples/gather_1d/gath_1d.asc` + `gather_1d_guide.md` — annotated Gather1D (Model A pure SIMT)
- `references/simt_build_and_compile.md` — the build recipe and the three msopgen-only requirements
- For histogram (UB atomics) and stream compaction (ballot+popc) patterns → `references/simt_operator_patterns.md`

**Optional — SDK examples, only if the devkit is present.** These paths resolve
only when `asc-devkit` has been vendored into `skills/cake-docs-search/`; it is
**not** part of this repo and is absent in the default environment. Check with
`ls skills/cake-docs-search/asc-devkit/` first, and skip this block if it is
missing — do not report the absence as an error, and do not stall waiting for it.

- `asc-devkit/examples/00_introduction/01_add/simt_add/add.asc` — simplest pure SIMT kernel (element-wise add)
- `asc-devkit/examples/00_introduction/04_simple_operator/pure_simt_gather/gather.asc` — pure SIMT gather with dynamic grid sizing via `GetCoreNumAiv()`

---

### Pass 1 — `kernel_pass`

Emit the `__global__` kernel function. This replaces `vf_pass` + `entry_pass` from Model B.

**1.1 Include Selection**

| Condition | Include |
|---|---|
| Always (Model A) | `#include "acl/acl.h"` |
| Always (Model A) | `#include "simt_api/asc_simt.h"` |
| Dynamic grid sizing | `#include "tiling/platform/platform_ascendc.h"` |
| Using warp functions | `#include "simt_api/device_warp_functions.h"` |
| Using sync/fence | `#include "simt_api/device_sync_functions.h"` |
| Using atomics | `#include "simt_api/device_atomic_functions.h"` |
| Using math functions | `#include "simt_api/math_functions.h"` |
| Using `half`/`half2` | `#include "simt_api/asc_fp16.h"` |
| Using `bfloat16_t` | `#include "simt_api/asc_bf16.h"` |
| Cache hints (`asc_ldcg`/`asc_ldca`/`asc_stcg`) | `#include "simt_api/device_functions.h"` |
| Debug printf | `#include "asc_printf.h"` |
| CPU debug mode | `#include "tikicpulib.h"` (guarded by `#if defined(ASCENDC_CPU_DEBUG)`) |

Note: `kernel_operator.h` is NOT used for Model A (no `asc_vf_call`). `simt_api/asc_simt.h` IS required (provides `blockIdx`, `threadIdx`, `blockDim`, `gridDim`, `warpSize`, `laneid()`, `lanemask_*()`, `__popc()`).

**1.2 Kernel Function Signature**

```cpp
__global__ __launch_bounds__(MAX_THREADS) void KERNEL_NAME(
    TYPE* arg1, TYPE* arg2, ..., uint64_t scalar_arg)
```

Rules:
- `__global__` annotation is mandatory
- `__launch_bounds__(N)` with max threads (typically 256–2048)
- Plain `T*` pointers — `__gm__` qualifier is not required (but won't cause errors)
- Struct pointer args are allowed (e.g., `EdgePixel*`, `Bucket*`)
- `__ubuf__` arrays can be declared inside the kernel body

**1.3 Available APIs in Model A `__global__` Kernels**

All SIMT APIs are verified working in Model A (SDK examples: `histogram.asc`, `sobel_warp_shfl.asc`, `insert_hash_table.asc`, `matrix_transpose.asc`, `data_cache_hint.asc`):

- **Thread indexing**: `blockIdx.x/y/z`, `threadIdx.x/y/z`, `blockDim.x/y/z`, `gridDim.x/y/z`, `warpSize`
- **Warp**: `asc_shfl_down`, `asc_shfl_up`, `asc_shfl`, `asc_shfl_xor`, `asc_reduce_add/max/min`, `asc_ballot`, `asc_all`, `asc_any`, `asc_activemask`
- **Lane utilities**: `laneid()`, `lanemask_lt()`, `lanemask_eq()`, `__popc()`
- **Sync**: `asc_syncthreads()` (block barrier), `asc_threadfence()` (memory ordering)
- **Atomics**: `asc_atomic_add`, `asc_atomic_cas`, `asc_atomic_sub`, `asc_atomic_max`, `asc_atomic_min`, etc. on `__ubuf__` or GM
- **UB memory**: `__ubuf__` arrays, `extern __ubuf__ char dynamicBuf[]` for dynamic UB
- **Cache hints**: `asc_ldcg()`, `asc_ldca()`, `asc_stcg()`
- **Other**: `#pragma unroll`, `volatile` pointer casting, `dim3(x,y,z)` for 2D/3D grids

<!-- shared: pattern_ref_table -->
**§1.6+ SIMT Pattern & ISA References (all models)**

The following pattern references apply to **all SIMT models (A, B, C)**. Model A uses `asc_*` free functions; Model B/C can also use `Simt::*` namespace equivalents.

| Topic | File | Key contents |
|---|---|---|
| Warp ops | [`references/simt_warp_ops.md`](simt_warp_ops.md) | §1.6 Butterfly reduction, §1.14 native `asc_reduce_add`, §1.20 REDUX (16cy), §1.21 shuffle edge-lanes, §1.22 vote/ballot |
| Memory & UB | [`references/simt_memory_ops.md`](simt_memory_ops.md) | §1.7 GM scratch, §1.17 2D grid. Cache hints, bank conflicts, dynamic UB, `__ldg`/`__stg` → [`memory_optimization_guide.md`](memory_optimization_guide.md) |
| Advanced patterns | [`references/simt_advanced_patterns.md`](simt_advanced_patterns.md) | §1.8 iterative algorithm, §1.9 axis-parallel, §1.10 stream compaction, §1.11 atomic CAS, §1.12 histogram, §1.15 printf |
| ISA intrinsics | [`references/simt_platform_reference.md`](simt_platform_reference.md) | `Simt::` namespace APIs, `__cvt_*` casts, bit builtins, ISA cost model |

**1.4 Template Support**

For multi-dtype operators:
```cpp
template <typename type_data, typename type_idx>
__global__ __launch_bounds__(2048) void KERNEL_NAME(
    type_data* input, type_idx* index, type_data* output,
    uint32_t width, uint32_t total_length)
```

**Reference**: `simt_add/add.asc`, `pure_simt_gather/gather.asc`

> **Multi-dtype**: For widening helpers (warp shuffle/reduce on half/bfloat16), explicit instantiation pattern, and sizeof-dependent constants, read [`simt_multi_dtype_guide.md`](simt_multi_dtype_guide.md).

⚠️ **After completing Pass 1**: Append to `codegen_reasoning.md` (format in SKILL.md §Codegen Reasoning Log: References used / What was adapted vs. derived / Key decisions).

<!-- NOTE: ACL lifecycle is shared across models A/B/C, but grid sizing and launch syntax are model-specific. Do NOT copy verbatim from another model's host_pass. -->
### Pass 2 — `host_pass` (ACL Runtime + Launch)

Emit the host function following the ACL lifecycle.

**2.1 ACL Lifecycle**

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

    // ── Kernel launch (4-arg for Model A) ──
    uint32_t dyn_ubuf_size = 0;
    KERNEL_NAME<<<num_blocks, THREAD_COUNT, dyn_ubuf_size, stream>>>(
        (TYPE*)input_device, (TYPE*)output_device, total_elements);

    // ── Synchronize ──
    aclrtSynchronizeStream(stream);

    // ── Copy output D2H ──
    aclrtMemcpy(output_host, output_size_bytes, output_device, output_size_bytes, ACL_MEMCPY_DEVICE_TO_HOST);

    // ── Cleanup ──
    aclrtFree(input_device);
    aclrtFree(output_device);
    aclrtFreeHost(output_host);
    aclrtDestroyStream(stream);
    aclrtResetDevice(device_id);
    aclFinalize();
}
```

**2.2 Launch Syntax (Model A)**

Model A uses 4-arg launch: `kernel<<<blocks, threads, ubuf, stream>>>(args)`

| Arg | Meaning |
|---|---|
| `blocks` | Number of blocks (grid size) |
| `threads` | Threads per block |
| `ubuf` | Dynamic UB size in bytes (0 for most Model A kernels) |
| `stream` | ACL stream |

**2.3 CPU Debug Mode**

```cpp
#if defined(ASCENDC_CPU_DEBUG)
    #include "tikicpulib.h"
    AscendC::SetKernelMode(AscendC::KernelMode::AIV_MODE);
    ICPU_RUN_KF(KERNEL_NAME, num_blocks, input_device, output_device, total);
#else
    KERNEL_NAME<<<num_blocks, THREAD_COUNT, dyn_ubuf_size, stream>>>(input_device, output_device, total);
#endif
```

**Memory lifecycle rules**:
- Every `aclrtMalloc` must have a matching `aclrtFree`
- Every `aclrtMallocHost` must have a matching `aclrtFreeHost`
- `aclrtSynchronizeStream` is mandatory between kernel launch and D2H copy
- Use `aclrtMemset(ptr, size, 0, size)` to zero-initialize device memory (e.g., atomic counters)
- Error check: `aclGetRecentErrMsg()` after sync to detect kernel failures

---

<!-- shared: main_pass_template -->
### Pass 3 — `main_pass` (Test Harness + Verification)

Emit `main()` with test data generation, golden computation, kernel invocation, and verification.

**3.1 Test Data Generation**

Generate deterministic test data matching input shapes from `op_desc.json`:
```cpp
std::vector<float> input(input_size);
for (uint32_t i = 0; i < input_size; i++) {
    input[i] = i * 1.2f;
}
```

**3.2 Golden Computation**

CPU reference matching `functional.py` semantics:
```cpp
std::vector<float> golden(output_size);
for (uint32_t i = 0; i < output_size; i++) {
    golden[i] = /* reproduce functional.py logic */;
}
```

**3.3 Kernel Invocation**

Call the host function from Pass 2.

**3.4 Verification**

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
