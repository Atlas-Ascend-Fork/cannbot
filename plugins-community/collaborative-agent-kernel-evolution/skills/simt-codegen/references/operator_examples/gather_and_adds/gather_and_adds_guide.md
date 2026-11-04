# Gather+Adds — Model C (SIMT+SIMD Hybrid) Annotated Lowering Guide

> **Model**: C — SIMT+SIMD Hybrid (`__simt_vf__` + `__simd_vf__` + DataCopy)
> **Verified on**: Ascend 950PR, CANN 9.0.0-beta.2, `--npu-arch=dav-3510`
> **Source**: [`gather_and_adds.asc`](gather_and_adds.asc) (correctness PASSED, profiled)
> **Operator**: `output[i] = input[index[i]] + 1.0` — irregular gather + regular arithmetic

---

## Three-Stage Execution Pattern

This is the canonical pattern for operators that mix irregular memory access with regular compute:

```
Stage 1 (SIMT):  GM ──[scatter/gather]──→ UB     (per-thread, irregular)
Stage 2 (SIMD):  UB ──[vector compute]──→ UB     (full-width, regular)
Stage 3 (MTE3):  UB ──[DataCopy/DMA]────→ GM     (bulk transfer)
```

UB (Unified Buffer) is the bridge — SIMT deposits data there, SIMD operates on it, MTE3 drains it to GM.

---

## File Structure (4-pass mapping)

| Pass | Lines | What it emits |
|---|---|---|
| `vf_pass` | 34–59, 61–79 | `__simt_vf__` gather + `__simd_vf__` adds (two VF functions) |
| `entry_pass` | 81–112 | `__global__ __vector__` entry orchestrating all three stages |
| `host_pass` | 114–170 | Host function with ACL lifecycle + 3-arg `<<<>>>` launch |
| `main_pass` | 210–232 | `main()` with test data + golden + verification |

---

## Pass 1 — `vf_pass`: Two VF Functions

### Stage 1: SIMT Gather (irregular GM→UB)

```cpp
__simt_vf__ __launch_bounds__(THREAD_COUNT) inline void simt_gather(
    __gm__ float* input,            // source data in global memory
    __gm__ uint32_t* index,         // index array in global memory
    __ubuf__ float* gather_output,  // ← __ubuf__: output goes to UB, not GM
    uint32_t input_total_length,
    uint32_t index_total_length,
    uint32_t output_total_length)
{
    if (threadIdx.x >= output_total_length) {
        return;
    }

    uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= index_total_length) {
        return;
    }

    uint32_t gather_idx = index[idx];
    if (gather_idx >= input_total_length) {
        return;
    }

    gather_output[threadIdx.x] = input[gather_idx];  // ← threadIdx.x, NOT idx
}
```

#### Critical: UB addressing uses `threadIdx.x`, not global `idx`

```cpp
// ✅ CORRECT — UB is per-block private, so offset is block-local
gather_output[threadIdx.x] = input[gather_idx];

// ❌ WRONG — would write beyond UB buffer bounds, causing corruption
gather_output[blockIdx.x * blockDim.x + threadIdx.x] = input[gather_idx];
```

UB is **per-block private memory**. Each block has its own 128KB (max) of UB. When SIMT threads write to `__ubuf__`, the index must be relative to the block (0 to `blockDim.x - 1`), not a global thread ID.

### Stage 2: SIMD Adds (regular UB→UB)

```cpp
__simd_vf__ inline void simd_adds(
    __ubuf__ float* output,     // ← all __ubuf__: operates entirely on UB
    __ubuf__ float* input,
    uint32_t count,
    uint32_t one_repeat_size,
    uint16_t repeat_times)
{
    AscendC::MicroAPI::RegTensor<float> src_reg0;
    AscendC::MicroAPI::RegTensor<float> dst_reg0;
    AscendC::MicroAPI::MaskReg mask_reg;

    for (uint16_t i = 0; i < repeat_times; i++) {
        mask_reg = AscendC::MicroAPI::UpdateMask<float>(count);
        AscendC::MicroAPI::LoadAlign(src_reg0, input + i * one_repeat_size);
        AscendC::MicroAPI::Adds(dst_reg0, src_reg0, ADDS_ADDEND, mask_reg);
        AscendC::MicroAPI::StoreAlign(output + i * one_repeat_size, dst_reg0, mask_reg);
    }
}
```

#### Key differences from `__simt_vf__`

| Aspect | `__simt_vf__` (gather) | `__simd_vf__` (adds) |
|---|---|---|
| Annotation | `__simt_vf__ __launch_bounds__(N) inline` | `__simd_vf__ inline` |
| Dispatch | `asc_vf_call<F>(dim3(N), args...)` | `asc_vf_call<F>(args...)` — **no `dim3`** |
| Execution | N threads, per-thread scalar ops | Single invocation, full vector width |
| Memory | `__gm__` reads + `__ubuf__` writes | `__ubuf__` only (on-chip) |
| APIs | Scalar ops, warp functions | Micro API (`LoadAlign`, `Adds`, `StoreAlign`) |

The **presence or absence of `dim3()` as the first arg** to `asc_vf_call` determines SIMT vs SIMD dispatch.

---

## Pass 2 — `entry_pass`: Three-Stage Orchestrator

```cpp
__global__ __vector__ void gather_and_adds_kernel(
    __gm__ float* input,
    __gm__ uint32_t* index,
    __gm__ float* output,
    uint32_t input_total_length,
    uint32_t index_total_length)
{
    AscendC::LocalMemAllocator<AscendC::Hardware::UB> ub_allocator;

    // ── Stage 1: SIMT gather (GM → UB) ──
    uint32_t index_total_length_per_block = index_total_length / AscendC::GetBlockNum();
    AscendC::LocalTensor<float> gather_output =
        ub_allocator.Alloc<float>(index_total_length_per_block);

    asc_vf_call<simt_gather>(dim3(THREAD_COUNT),   // ← dim3 = SIMT dispatch
        input, index,
        (__ubuf__ float*)gather_output.GetPhyAddr(),
        input_total_length, index_total_length, index_total_length_per_block);

    // ── Stage 2: SIMD adds (UB → UB) ──
    AscendC::LocalTensor<float> adds_output =
        ub_allocator.Alloc<float>(index_total_length_per_block);
    constexpr uint32_t one_repeat_size = AscendC::GetVecLen() / sizeof(float);
    uint16_t repeat_times =
        (index_total_length_per_block + one_repeat_size - 1) / one_repeat_size;

    asc_vf_call<simd_adds>(                        // ← no dim3 = SIMD dispatch
        (__ubuf__ float*)adds_output.GetPhyAddr(),
        (__ubuf__ float*)gather_output.GetPhyAddr(),
        index_total_length_per_block, one_repeat_size, repeat_times);

    // ── Stage 3: DMA copy out (UB → GM) ──
    AscendC::SetFlag<AscendC::HardEvent::V_MTE3>(0);   // sync: V pipe done
    AscendC::WaitFlag<AscendC::HardEvent::V_MTE3>(0);   // wait before MTE3

    AscendC::GlobalTensor<float> output_global_tensor;
    output_global_tensor.SetGlobalBuffer(
        output + index_total_length_per_block * AscendC::GetBlockIdx());
    AscendC::DataCopy(output_global_tensor, adds_output, index_total_length_per_block);
}
```

### Key rules for the entry function (Model C)

| Rule | Detail |
|---|---|
| **UB allocation** | `LocalMemAllocator<Hardware::UB>` — allocates on-chip buffers |
| **`GetPhyAddr()`** | Extracts `__ubuf__` raw pointer from `LocalTensor` for `asc_vf_call` |
| **SIMT dispatch** | `asc_vf_call<F>(dim3(N), ...)` — has `dim3` |
| **SIMD dispatch** | `asc_vf_call<F>(...)` — NO `dim3` |
| **No explicit sync between stages** | `asc_vf_call` returns only after completion — sequential calls are ordered |
| **SetFlag/WaitFlag before DataCopy** | Required sync between V pipe (SIMD) and MTE3 (DMA) |
| **DataCopy for output** | SIMT threads CANNOT write from UB to GM — must use MTE3 DMA |
| **Per-block output offset** | `output + per_block_count * GetBlockIdx()` — each block writes its own slice |

### Why SetFlag/WaitFlag is needed

```
V pipe (SIMD adds) ──writes──→ UB ──reads──→ MTE3 (DataCopy)
                                    ↑
                          SetFlag/WaitFlag ensures
                          V is done before MTE3 starts
```

Without this sync, MTE3 may read from UB before SIMD has finished writing — producing a data race. Profiling shows MTE3 wait ratio ~91%, which is this barrier working correctly.

Between `asc_vf_call` invocations (SIMT→SIMD), no sync is needed — `asc_vf_call` is synchronous.

---

## Pass 3 — `host_pass`: ACL Lifecycle + Launch

```cpp
std::vector<float> gather_and_adds(std::vector<float>& input,
                                   std::vector<uint32_t>& index)
{
    constexpr uint32_t numBlocks = 8;
    // ... ACL init, malloc, H2D copy (same pattern as Model B) ...

#if defined(ASCENDC_CPU_DEBUG)
    AscendC::SetKernelMode(KernelMode::AIV_MODE);
    ICPU_RUN_KF(gather_and_adds_kernel, numBlocks,
                input_device, index_device, output_device,
                input_total_length, index_total_length);
#else
    constexpr uint32_t dynUBufSize = 2048;  // ← non-zero: UB is allocated in kernel
    gather_and_adds_kernel<<<numBlocks, dynUBufSize, stream>>>(
        input_device, index_device, output_device,
        input_total_length, index_total_length);
#endif
    // ... sync, D2H copy, cleanup ...
}
```

### `dynUBufSize` is critical for Model C

| Scenario | `dynUBufSize` | Why |
|---|---|---|
| Model A/B (no UB alloc) | `0` | No `LocalMemAllocator` in kernel |
| **Model C (UB alloc)** | **`> 0`** | `LocalMemAllocator<UB>` needs reserved space |

**Calculation**: `dynUBufSize >= sum of all Alloc sizes * sizeof(type)`

In this example: 2 buffers × 1024 floats × 4 bytes = 8192 bytes needed. The actual `dynUBufSize = 2048` works because the allocator manages the static UB budget, and `dynUBufSize` only reserves *additional* dynamic space. Setting it to 0 when UB is used will silently corrupt memory.

### Grid sizing for Model C

Model C typically uses **fewer, larger blocks** than Model B:
- 8 blocks × 1024 threads = 8192 total threads
- Each block processes `index_total_length / numBlocks` = 1024 elements
- Thread count and UB buffer size must be coordinated: 1024 threads → 1024-element UB buffer

---

## Pass 4 — `main_pass`: Test Harness

```cpp
int32_t main(int32_t argc, char* argv[])
{
    constexpr uint32_t input_total_length = 100000;
    // ... generate input, index ...

    // Golden: gather + add
    std::vector<float> golden(index_total_length);
    for (uint32_t i = 0; i < index_total_length; i++) {
        golden[i] = input[index[i]] + ADDS_ADDEND;  // matches three-stage pipeline
    }

    std::vector<float> output = gather_and_adds(input, index);
    return verify_result(output, golden);
}
```

---

## Differences from Model B — SIMT VF (torch_gather_20_20)

| Aspect | Model B (SIMT VF) | Model C (SIMT+SIMD, this guide) |
|---|---|---|
| VF functions | One: `__simt_vf__` | Two: `__simt_vf__` + `__simd_vf__` |
| SIMT output dest | `__gm__` (direct to GM) | `__ubuf__` (to UB) |
| UB addressing | N/A | `threadIdx.x` (block-local, NOT global idx) |
| SIMD stage | None | `__simd_vf__` with Micro API (LoadAlign/Adds/StoreAlign) |
| GM output | Per-thread writes | `DataCopy` DMA via MTE3 |
| Pipe sync | None needed | `SetFlag`/`WaitFlag` before DataCopy |
| `dynUBufSize` | 0 | > 0 (UB allocation in kernel) |
| UB allocator | Not used | `LocalMemAllocator<Hardware::UB>` |
| Typical grid | Many blocks, few threads | Few blocks, many threads (thread count = UB buffer elements) |

---

## When to Use Model C vs Model B

```
Does the operator have BOTH irregular access AND regular vectorizable compute?
├── YES → Model C — SIMT gathers to UB, SIMD computes, DataCopy out
│         Benefit: SIMD compute is ~0.6% of cycles (essentially free vs doing it in SIMT)
└── NO  → Model B — SIMT does everything, writes directly to GM
          Simpler, fewer sync concerns, no UB sizing constraints
```

From profiling: the SIMD Adds consumed only 0.6% of cycles for a full-width vector addition. Doing `output[i] = input[idx] + 1.0` per-thread in SIMT would waste vector pipe throughput.

---

## Performance (profiled on Ascend 950PR, CANN 9.0.0-beta.2)

| Metric | Value |
|---|---|
| Task duration | 6.919 us |
| SIMT VF ratio | ~90% |
| SIMD VF ratio | ~0.6% |
| Scalar ratio | ~5.8% |
| MTE3 ratio | ~3.7% |
| MTE3 wait ratio | ~91.2% (sync barrier, not a bug) |
| Blocks | 8 |
| Threads/block | 1024 |
| `dynUBufSize` | 2048 |
