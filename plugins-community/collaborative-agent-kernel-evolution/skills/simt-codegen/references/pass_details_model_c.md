# Pass Details — Model C (Hybrid SIMT+SIMD)

## Why the hybrid is the only option for an aicore primitive

Both halves are needed because neither dialect can do the job alone, and the compiler enforces this
from both sides (device-verified 2026-08-11 on Ascend950PR_9599 / CANN 9.1.0-beta.3 / `dav-c310-vec`):

| you want | what happens |
|---|---|
| an aicore API (`Sort32`, `DataCopy`, `LocalTensor`) inside a `__simt_vf__` | rejected — a VF may only call `__simt_callee__`; fires at `GlobalTensor`'s `__aicore__` constructor (`basic_api/kernel_tensor.h:237`) |
| the same API in a Model A puresimt kernel | `kernel_operator.h` will not parse — `unknown type name '__simd_callee__'` |
| drop `-cce-enable-puresimt` to regain the API | the `__global__` kernel now *requires* `__aicore__`, so you are in Model C |
| an aicore API in the `__aicore__` half, results handed to a VF | **works** — this is Model C |

So a VF reaches no aicore primitive, but the aicore half of the same kernel reaches all of them, in
one launch with no new OpDef plumbing. Do not route an operator away from SIMT because it needs a
vector primitive.

### Sorting specifically

Write `Concat` → `Sort<T, true>` → `Extract`. That is what the vendor's `KernelVbsMergeSort` uses
(`ops_math/ascendc/sort_with_index/arch35/merge_sort_simd.h:55-59`), it sizes its own tmp buffer via
`GetSortLen<T>()`, and it measured 71.9 µs against 74.7 µs for a hand-rolled `Sort32` + 4-way
`MrgSort` tree on identical data (2M fp32, 1024 chunks, 48 blocks), both bit-exact against
`std::sort`. `Sort32` accepts float and half only — int32/int64 keys do not survive an fp32 mantissa
above 2^24, so those dtypes need a scalar or radix path instead.

The composition is worth ~4%. What decides performance inside a Model C leaf is the algorithm
(selection vs full sort) and the SIMT granularity, neither of which the model choice fixes.

## Compilation

Device object (`-c`) — no `-cce-enable-puresimt` on Model C, the aicore/SIMD
half needs the normal front end:

```bash
A=$ASCEND_HOME_PATH/$(uname -m)-linux
bisheng --asc-aicore-lang --npu-arch=dav-3510 --cce-aicore-only \
  -std=c++17 -O2 -D__NPU_TILING__ \
  -I"$A/include" -I"$A/asc/include" -I"$A/asc/impl" -I. \
  -c my_op.asc -o my_op.o

# Artifact gate — a Model C object must carry BOTH halves:
nm -C my_op.o | grep -c 'simt_'        # must be > 0  (the __simt_vf__ stage)
nm my_op.o    | grep -c 'Kernel_Type'  # must be > 0  (the aicore entry)
```

<!-- claim: asc-include-root · also in: pass_details_model_a.md · find with: grep -rn "claim: asc-include-root" skills/simt-codegen · edit all sites together -->
> The three `-I` paths are **belt-and-braces, not load-bearing**: `--asc-aicore-lang` puts
> the ASC tree on the search path itself, and clang silently ignores `-I` dirs that do not
> exist. The build succeeds either way — verified identical 6232 B object from both the
> correct root and the old `compiler/tikcpp` one. Fixed anyway so the recipe does not teach
> a wrong path. If a vendor header is missing, the cause is the front end (`-x cce` vs
> `--asc-aicore-lang`), never a missing `-I` — see `SKILL.md` "A missing vendor header".


Both counts matter here in a way they don't for A or B: a Model C kernel that
compiles to `simt_*` symbols with no `Kernel_Type`, or vice versa, has lost one
of the two halves and is not the hybrid you asked for.

`--cce-aicore-only` selects the device half of the translation unit. Without it
the compile still exits 0 and emits a host-only object with **zero** device
code — a silent failure. Drop it only when linking a host+device executable,
where it fails `cannot specify -o when generating multiple output files`.

`-D__NPU_TILING__` selects the device overload of the msopgen-generated tiling
copier; `-I.` is load-bearing for the kernel's own `*_tiling.h`.

See `simt_build_and_compile.md` for the full flag rationale and the error table.

## Compilable Skeleton

Copy this, fill in the compute bodies:

```cpp
// === Model C Skeleton — Hybrid SIMT+SIMD ===
#include "acl/acl.h"
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
// Add as needed: simt_api/device_warp_functions.h, asc_fp16.h, asc_bf16.h

using namespace AscendC;

// Pass 1: SIMT gather — writes to __ubuf__
template <typename T>
__simt_vf__ __launch_bounds__(256) inline void simt_{op_name}(
    __gm__ T* input, __gm__ int32_t* index,
    __ubuf__ T* gather_out, uint32_t per_block_count)
{
    uint32_t tid = threadIdx.x;
    if (tid >= per_block_count) return;
    // TODO: gather logic — write to gather_out[tid]
    gather_out[tid] = input[index[blockIdx.x * per_block_count + tid]];
}

// Pass 2: SIMD compute on UB data (elementwise only)
template <typename T>
__simd_vf__ inline void simd_{op_name}(
    __ubuf__ T* input_buf, __ubuf__ T* output_buf, uint32_t count)
{
    LocalTensor<T> src, dst;
    src.SetAddr(input_buf); dst.SetAddr(output_buf);
    // TODO: elementwise compute — Adds, Muls, Maxs, Abs, etc.
    Adds(dst, src, static_cast<T>(0), count);
}

// Pass 3: Entry — orchestrate VFs + DataCopy
//
// NOT `template <typename T> extern "C" __global__ ...` — that is ill-formed C++
// (`error: expected unqualified-id`): a function cannot be both a template and
// have C language linkage. The entry is non-templated; dispatch on `dtypeCode`
// inside it and let the VF templates be instantiated per case.
extern "C" __global__ __aicore__ void {op_name}_custom(
    GM_ADDR input, GM_ADDR index, GM_ADDR output,
    GM_ADDR workspace, GM_ADDR tiling)
{
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);  // MANDATORY: else ld.lld "auto derivate failed"
    REGISTER_TILING_DEFAULT({OpName}CustomTilingData);
    GET_TILING_DATA(td, tiling);

    LocalMemAllocator<Hardware::UB> ubAlloc;
    LocalTensor<T> ubGather = ubAlloc.Alloc<T>(td.perBlockCount);
    LocalTensor<T> ubResult = ubAlloc.Alloc<T>(td.perBlockCount);

    asc_vf_call<simt_{op_name}<T>>(dim3(td.threadsPerBlock),
        (__gm__ T*)input, (__gm__ int32_t*)index,
        (__ubuf__ T*)ubGather.GetPhyAddr(), td.perBlockCount);

    asc_vf_call<simd_{op_name}<T>>(
        (__ubuf__ T*)ubGather.GetPhyAddr(),
        (__ubuf__ T*)ubResult.GetPhyAddr(), td.perBlockCount);

    SetFlag<V_MTE3>(0);
    WaitFlag<V_MTE3>(0);
    DataCopy(GlobalTensor<T>().SetGlobalBuffer((__gm__ T*)output + blockIdx.x * td.perBlockCount),
             ubResult, td.perBlockCount);
}

// Multi-dtype dispatch — ONLY if tiling header defines dtypeCode.
// For single-dtype operators (check op_desc.json), omit the switch
// and instantiate the template directly with the concrete type.
```

**Multi-dtype dispatch for Model C**: Template the `__simt_vf__` and `__simd_vf__` functions on `<typename T>`. In the entry function, use a `dtypeCode` switch to select the correct instantiation (same pattern as Model B skeleton). Always include both `asc_fp16.h` and `asc_bf16.h` for multi-dtype kernels. For warp operations on half/bfloat16, widen to float before the intrinsic, narrow after — see [`simt_multi_dtype_guide.md`](simt_multi_dtype_guide.md) for helpers.

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
- `references/operator_examples/gather_and_adds/gather_and_adds.asc` — two-VF pattern: `__simt_vf__` (gather GM→UB) + `__simd_vf__` (compute on UB) + DataCopy out
- `references/operator_examples/gather_and_adds/gather_and_adds_guide.md` — annotated guide for the two-VF pattern (structural template for all Model C operators)
- `references/simt_build_and_compile.md` — the build recipe. Note that a Model C kernel driving the cube unit needs a `KERNEL_TYPE_MIX_AIC_*` task type, not `KERNEL_TYPE_AIV_ONLY`
- For Model C variant with entry-function reductions (when `__simd_vf__` cannot compile ReduceMax/ReduceSum) → `references/simt_operator_patterns.md` §Masked Reduction

**Optional — SDK examples, only if the devkit is present.** This path resolves
only when `asc-devkit` has been vendored into `skills/cake-docs-search/`; it is
**not** part of this repo and is absent in the default environment. Check with
`ls skills/cake-docs-search/asc-devkit/` first, and skip it if missing — do not
report the absence as an error, and do not stall waiting for it.

- `asc-devkit/examples/04_best_practices/14_simt_and_simd_floor_mod/floor_mod.asc` — full KernelOp class variant with hybrid SIMT+SIMD

---

Model C uses two VF functions: a `__simt_vf__` for irregular access (writes to `__ubuf__`) and a `__simd_vf__` for vectorizable compute on UB data (Micro API). Output is written via `DataCopy` (MTE3 DMA), not per-thread GM writes.

**MicroAPI scope in `__simd_vf__`**: MicroAPI provides elementwise vector ops (LoadAlign, StoreAlign, Maxs, Adds, Muls, Abs, Min, Max) but NOT reductions (ReduceMax, ReduceSum) or complex operations (Exp, Duplicate). Reductions must go in the `__aicore__` entry function using AscendC high-level APIs.

**Decision rule**:
- Fused compute is purely elementwise → standard Model C with `__simd_vf__` (Pass 2 = `simd_vf_pass`)
- Fused compute contains any reduction → Model C variant, skip `__simd_vf__`, do reductions in entry (Pass 2 = `entry_reduction_pass`)

**Reference**: `references/operator_examples/gather_and_adds/gather_and_adds_guide.md` (standard Model C). For the variant with entry-function reductions → see `references/simt_operator_patterns.md` §Masked Reduction.

<!-- shared: pattern_ref_table -->
**§1.6+ SIMT Pattern & ISA References (all models)**

The following pattern references apply to **all SIMT models (A, B, C)**. Model C's `__simt_vf__` pass uses `Simt::*` or `asc_*` APIs.

| Topic | File | Key contents |
|---|---|---|
| Warp ops | [`references/simt_warp_ops.md`](simt_warp_ops.md) | §1.6 Butterfly reduction, §1.14 native `asc_reduce_add`, §1.20 REDUX (16cy), §1.21 shuffle edge-lanes, §1.22 vote/ballot |
| Memory & UB | [`references/simt_memory_ops.md`](simt_memory_ops.md) | §1.7 GM scratch, §1.17 2D grid. Cache hints, bank conflicts, dynamic UB, `__ldg`/`__stg` → [`memory_optimization_guide.md`](memory_optimization_guide.md) |
| Advanced patterns | [`references/simt_advanced_patterns.md`](simt_advanced_patterns.md) | §1.8 iterative algorithm, §1.9 axis-parallel, §1.10 stream compaction, §1.11 atomic CAS, §1.12 histogram, §1.15 printf |
| ISA intrinsics | [`references/simt_platform_reference.md`](simt_platform_reference.md) | `Simt::` namespace APIs, `__cvt_*` casts, bit builtins, ISA cost model |

### Pass 1 — `simt_vf_pass`

Emit the `__simt_vf__` function that performs irregular access (gather, scatter) and writes results to `__ubuf__`.

Key differences from Model B `vf_pass`:
- Output pointer is `__ubuf__ T*` (not `__gm__ T*`)
- Index with `threadIdx.x` for UB writes (UB is per-block private), not global `idx`
- Bounds check against per-block output length, not global total

⚠️ **After completing Pass 1**: Append to `codegen_reasoning.md` (format in SKILL.md §Codegen Reasoning Log: References used / What was adapted vs. derived / Key decisions).

### Pass 2 — `simd_vf_pass`

Emit the `__simd_vf__` function that operates on `__ubuf__` data using Micro API (LoadAlign, StoreAlign, Adds, Muls, etc.).

Key rules:
- No `dim3` in `asc_vf_call` for `__simd_vf__` — SIMD has no thread dispatch
- All buffer args are `__ubuf__ T*`
- Uses `one_repeat_size` and `repeat_times` for Micro API iteration

⚠️ **After completing Pass 2**: Append to `codegen_reasoning.md` (format in SKILL.md §Codegen Reasoning Log: References used / What was adapted vs. derived / Key decisions).

### Pass 2 variant — `entry_reduction_pass` (Model C with reductions)

When the fused compute contains reductions (ReduceMax, ReduceSum, mean, norm), skip `__simd_vf__` entirely. Instead, emit the reduction chain directly in the `__aicore__` entry function using AscendC high-level APIs.

Pattern (proven in MaskedSoftmax):
```cpp
// Phase 1: SIMT (irregular access) — same as standard Model C
asc_vf_call<simt_phase>(dim3(threads), gm_ptrs..., ubuf_output, ...);

// Phase 2: AscendC reductions directly in entry (NOT via __simd_vf__)
AscendC::ReduceMax(ubMaxScalar, ubInput, ubWorkspace, count);
float maxVal = ubMaxScalar.GetValue(0);
AscendC::Adds(ubOutput, ubInput, -maxVal, count);    // subtract max
AscendC::Exp(ubOutput, ubOutput, count);               // exp
AscendC::ReduceSum(ubSumScalar, ubOutput, ubWorkspace, count);
float sum = ubSumScalar.GetValue(0);
AscendC::Muls(ubOutput, ubOutput, 1.0f / sum, count); // normalize
```

Key differences from standard `simd_vf_pass`:
- No `__simd_vf__` function emitted
- Reductions run on the vector pipe via AscendC high-level APIs
- `ReduceMax`/`ReduceSum` need a workspace buffer (`ubAllocator.Alloc<T>(alignedCount)`)
- Scalar results extracted via `GetValue(0)`
- Entry function `entry_pass` merges Phase 2 + Phase 3 (DataCopy) into one

⚠️ **After completing Pass 2 variant**: Append to `codegen_reasoning.md` (format in SKILL.md §Codegen Reasoning Log: References used / What was adapted vs. derived / Key decisions).

### Pass 3 — `entry_pass`

Emit the entry function that orchestrates the two-VF pipeline:
1. `asc_vf_call<simt_vf>(dim3(THREADS), ...)` — SIMT gather to UB
2. `asc_vf_call<simd_vf>(...)` — SIMD compute on UB (no dim3)
3. `SetFlag<V_MTE3>(0)` + `WaitFlag<V_MTE3>(0)` — pipe barrier
4. `DataCopy(gm_tensor, ub_tensor, count)` — DMA write UB → GM

UB buffers are allocated via `LocalMemAllocator` in the entry function. `dynUBufSize > 0` in the launch.
<!-- claim: lma-vf-read-prohibition · also in: memory_optimization_guide.md · find with: grep -rn "claim: lma-vf-read-prohibition" skills/simt-codegen · edit all sites together -->

<!-- NOTE: ACL lifecycle is shared across models A/B/C, but grid sizing and launch syntax are model-specific. Do NOT copy verbatim from another model's host_pass. -->
### Pass 4 — `host_pass` (ACL Runtime + Launch)

Emit the host function following the ACL lifecycle.

**4.1 ACL Lifecycle**

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

    // ── Grid sizing (Model C: block count from tiling, NOT total_elements/threads) ──
    // Each block processes perBlockCount elements via UB staging.
    // Use tiling data or GetCoreNumAiv() — do NOT use (total_elements + threads - 1) / threads.
    uint32_t num_blocks = td.blocksPerGrid;  // from tiling; or GetCoreNumAiv() if runtime

    // ── Kernel launch (3-arg for Model C, dynUBufSize > 0) ──
    uint32_t dyn_ubuf_size = /* calculated from LocalMemAllocator usage */;
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

**4.2 Launch Syntax (Model C)**

Model C uses 3-arg launch: `entry<<<blocks, ubuf, stream>>>(args)` — same as Model B, but `dyn_ubuf_size > 0` because `LocalMemAllocator` is used in the entry function.

**4.3 CPU Debug Mode**

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
- Use `aclrtMemset(ptr, size, 0, size)` to zero-initialize device memory
- Error check: `aclGetRecentErrMsg()` after sync to detect kernel failures

---

<!-- NOTE: ACL lifecycle is shared across models A/B/C, but grid sizing and launch syntax are model-specific. -->
### Pass 5 — `main_pass` (Test Harness + Verification)

Emit `main()` with test data generation, golden computation, kernel invocation, and verification.

**5.1 Test Data Generation**

Generate deterministic test data matching input shapes from `op_desc.json`:
```cpp
std::vector<float> input(input_size);
for (uint32_t i = 0; i < input_size; i++) {
    input[i] = i * 1.2f;
}
```

**5.2 Golden Computation**

CPU reference matching `functional.py` semantics:
```cpp
std::vector<float> golden(output_size);
for (uint32_t i = 0; i < output_size; i++) {
    golden[i] = /* reproduce functional.py logic */;
}
```

**5.3 Kernel Invocation**

Call the host function from Pass 4.

**5.4 Verification**

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
