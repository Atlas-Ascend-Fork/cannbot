# SIMT Memory Operations Reference

> **Applies to**: All SIMT models (A, B, C) — these patterns are model-agnostic.
> **Back to**: [`../SKILL.md`](../SKILL.md)
> For cache hints, UB bank conflicts, dynamic UB, and `__ldg`/`__stg` intrinsics → see [`memory_optimization_guide.md`](memory_optimization_guide.md).

---

**1.7 Cross-Thread Communication via GM Scratch**

When the baseline specifies `asc_syncthreads()` + GM scratch (cross-warp merge, iterative algorithms), emit the barrier + shared-read pattern.

```cpp
#include "simt_api/device_sync_functions.h"

// Inside __simt_vf__ function:
// scratch_vals and scratch_idxs are __gm__ pointers to pre-allocated GM memory

// Each warp lane 0 writes its result to GM scratch
uint32_t warpId = threadIdx.x / 32;
if (threadIdx.x % 32 == 0) {
    scratch_vals[warpId] = local_max;
    scratch_idxs[warpId] = local_max_idx;
}

// Block barrier — all threads wait for all warp results to be visible
asc_syncthreads();

// Thread 0 scans all warp results
if (threadIdx.x == 0) {
    float best_val = scratch_vals[0];
    uint32_t best_idx = scratch_idxs[0];
    uint32_t num_warps = blockDim.x / 32;
    for (uint32_t w = 1; w < num_warps; w++) {
        if (scratch_vals[w] > best_val) {
            best_val = scratch_vals[w];
            best_idx = scratch_idxs[w];
        }
    }
    output[ki] = best_val;
}

asc_syncthreads();  // before next iteration
```

**CRITICAL**: Scratch memory must be a regular GM tensor (`aclrtMalloc`'d buffer or reserved tail of an input tensor). **Do NOT use the OPP workspace buffer** — it causes BIU error 334 on SIMT writes (see Pass 2 warning).

---

**1.17 2D Grid Configuration**

For operators that naturally map to 2D data (matrix transpose, image processing, 2D convolution).

Source: SDK example `matrix_transpose.asc` lines 197-198.

```cpp
// Host side — 2D grid and blocks
dim3 blocks(width / TILE_DIM, height / TILE_DIM, 1);
dim3 threads(TILE_DIM, TILE_DIM, 1);  // e.g., dim3(32, 32, 1)
kernel<<<blocks, threads, 0, stream>>>(output, input, width, height);

// Inside kernel — 2D thread indexing
int x = blockIdx.x * TILE_DIM + threadIdx.x;
int y = blockIdx.y * TILE_DIM + threadIdx.y;
```

Available built-ins: `blockIdx.x/y/z`, `threadIdx.x/y/z`, `blockDim.x/y/z`, `gridDim.x/y/z`
