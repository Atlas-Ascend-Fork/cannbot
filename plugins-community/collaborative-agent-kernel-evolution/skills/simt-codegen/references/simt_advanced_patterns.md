# SIMT Advanced Patterns Reference

> **Applies to**: All SIMT models (A, B, C) — these patterns are model-agnostic.
> **Back to**: [`../SKILL.md`](../SKILL.md)

---

**1.8 Iterative Algorithm Pattern**

For iterative algorithms (topk K iterations, k-th value search), combine warp reduction (1.6) + GM scratch (1.7) in a loop inside the VF function. Each iteration:
1. All threads scan their chunk -> local max
2. Warp butterfly reduction -> warp max
3. Cross-warp merge via scratch + syncthreads -> global max
4. Thread 0 writes result + masks found element
5. syncthreads before next iteration

The iteration count (K) is passed as a scalar parameter to the VF function.

---

**1.9 Independent Axis-Parallel Pattern**

The simplest SIMT pattern — no sync, no warp functions, no UB. Each thread handles one independent lane (column, batch element) with a sequential loop.

```cpp
// Inside __simt_vf__ function:
uint32_t col = blockIdx.x * blockDim.x + threadIdx.x;
if (col >= total_cols) return;
float acc = 0.0f;
for (uint32_t i = 0; i < scan_len; i++) {
    acc += input[i * inner_size + col];
    output[i * inner_size + col] = acc;
}
```

No additional includes needed beyond the base set. `dynUBufSize = 0`.

---

**1.10 Stream Compaction Pattern (ballot + popc + compact write)**

> **IMPORTANT — Routing caveat**: NonZero, Where, and masked select on contiguous tensors
> should **NOT** use this SIMT pattern. Their input is a linear scan — native AscendC with
> DMA + vectorized compare + prefix-sum is ~58x faster. SIMT scalar GM loads (173 cy each)
> cannot compete with MTE2 bulk DMA for contiguous reads. The conditional in NonZero/Where
> is a trivially maskable vector compare, not true control-flow divergence — the vector pipe handles
> it natively with `Compare()` → mask → compact.
> Reserve this pattern for **irregular-input** operators (sparse filtering, graph traversal).
> Measured on Ascend 950PR, CANN 9.1.0-beta.3 (NonZero SIMT probe).

For operators that produce data-dependent output sizes **with irregular/random input access**, use the ballot+popc pattern for warp-coalesced compact output. This uses 1 atomic per warp instead of 1 per qualifying thread (up to 32x fewer atomics).

Source: SDK example `sobel_warp_shfl.asc` lines 83-108.

```cpp
#include "simt_api/device_warp_functions.h"
#include "simt_api/device_atomic_functions.h"

// Inside __simt_vf__ or __global__ kernel:
// After computing a per-thread condition...

// Step 1: Warp votes on condition
uint32_t vote_mask = asc_ballot(condition);
if (vote_mask == 0) return;  // early warp exit — no qualifying threads

// Step 2: Lane 0 atomically reserves output slots for the whole warp
uint32_t warp_base = 0;
if (laneid() == 0) {
    warp_base = asc_atomic_add(global_counter, static_cast<uint32_t>(__popc(vote_mask)));
}

// Step 3: Broadcast reserved base to all lanes
warp_base = asc_shfl(warp_base, 0, warpSize);

// Step 4: Each qualifying thread writes to its compact position
if (vote_mask & lanemask_eq()) {
    uint32_t local_offset = __popc(vote_mask & lanemask_lt());
    output[warp_base + local_offset] = my_value;
}
```

Key APIs: `asc_ballot()`, `__popc()`, `laneid()`, `lanemask_lt()`, `lanemask_eq()`, `asc_shfl()` (broadcast), `asc_atomic_add()`

> 🚨 **Combining this with a grid-stride loop silently loses half your output.** The block above is
> the *one-shot* form: one element per thread, `return` on a dead warp. But the grid-stride loop
> that rule 8 mandates for data-driven sizes makes the obvious transliteration wrong, because
> `asc_ballot` must be reached by **every lane of the warp**, and `continue` diverges before it:
>
> ```cpp
> // ❌ WRONG — `continue` skips the ballot for non-qualifying lanes, so the mask
> //    describes only the survivors while lanemask_lt() still counts all lanes below.
> for (uint32_t i = tid; i < n; i += stride) {
>     bool q = pred(in[i]);
>     if (!q) continue;                 // ← divergence BEFORE the ballot
>     uint32_t mask = asc_ballot(1);    // ← mask is now wrong for every lane
>     ...
> }
> ```
>
> Device-measured on `Ascend950PR_9599`, against a numpy golden:
>
> | n | n%32 | `continue` form | golden | holes | writes past cursor |
> |---|---|---|---|---|---|
> | 65536 | 0 | **16432** | 32627 | 0 | 0 |
> | 65535 | 31 | **16432** | 32626 | 0 | 0 |
> | 1000 | 8 | **203** | 507 | 0 | 0 |
> | 33 | 1 | **0** | 14 | 0 | 0 |
>
> Roughly half the survivors vanish — and **every structural check still passes**: the output
> prefix is gap-free, nothing is written past the cursor, and the count is self-consistent with
> what was written. Only an independent element-wise golden catches it. At `n=33` the kernel
> emits nothing at all and still reports success.
>
> ```cpp
> // ✅ CORRECT — every lane reaches the ballot; out-of-range lanes vote 0.
> for (uint32_t base = 0; base < n; base += stride) {
>     uint32_t i = base + tid;
>     bool q = (i < n) && pred(in[i]);   // no branch around the ballot
>     uint32_t mask = asc_ballot(static_cast<int32_t>(q));
>     if (mask != 0) {
>         uint32_t warp_base = 0;
>         if (laneid() == 0) warp_base = asc_atomic_add(counter, __popc(mask));
>         warp_base = asc_shfl(warp_base, 0, warpSize);
>         if (q) out[warp_base + __popc(mask & lanemask_lt())] = in[i];
>     }
> }
> ```
>
> The `return` on `vote_mask == 0` in the one-shot block is **safe**, including at partial tail
> warps — verified exact at `n%32 ∈ {0, 31, 8, 1}`. Inactive lanes contribute no bits and
> `lanemask_lt()` stays consistent. The hazard is specifically *conditional divergence on the path
> to the ballot*, which is what a stride loop introduces.
>
> Note also that `__popc(mask & lanemask_lt())` **is** a warp-level exclusive prefix sum. If you
> need intra-warp order stability, this pattern already gives it to you for free.

**Host side**: `global_counter` must be a device-allocated `uint32_t`, zeroed with `aclrtMemset` before kernel launch. After kernel, copy `global_counter` back to host to know the output size.

---

**1.11 Atomic CAS Pattern (lock-free insert with memory ordering)**

For operators requiring lock-free insertion or scatter with conflict detection (hash tables, dedup, scatter with unique detection).

Source: SDK example `insert_hash_table.asc` lines 99-141.

```cpp
#include "simt_api/device_atomic_functions.h"
#include "simt_api/device_sync_functions.h"  // for asc_threadfence

// Inside __global__ kernel (Model A) or __simt_vf__ (Model B):

// CAS loop: try to claim a slot
uint32_t old = asc_atomic_cas(&slot->flag, EMPTY_FLAG, WRITE_FLAG);
if (old == EMPTY_FLAG) {
    // Won the slot — write data
    slot->key = my_key;
    asc_threadfence();  // ensure data write visible before state update
    slot->state = READY;
}

// Spin-wait for another thread's write to complete (if needed):
while (*reinterpret_cast<volatile uint32_t*>(&slot->state) != READY) {}

// Warp-cooperative value write (one warp per insertion):
is_insert_succ = asc_shfl(is_insert_succ, 0, warpSize);  // broadcast from lane 0
if (is_insert_succ) {
    for (uint32_t j = laneid(); j < value_dim; j += warpSize) {
        bucket->value[j] = values[idx * value_dim + j];  // warp-parallel copy
    }
    asc_threadfence();
    if (laneid() == 0) {
        bucket->flag = HOLD_FLAG;  // release
    }
}
```

Key APIs: `asc_atomic_cas()`, `asc_threadfence()`, `asc_shfl()`, `volatile` pointer casting

---

**1.12 Histogram Pattern (per-warp private UB + atomic + cross-warp merge)**

Two-kernel approach for histogram/binning operators. Avoids global atomic contention by using per-warp private `__ubuf__` arrays with `asc_atomic_add` on UB, then merging across warps.

Source: SDK example `histogram.asc` lines 103-154.

```cpp
// Kernel 1: accumulate per-block partial histogram
__global__ void accumulate_histogram(uint32_t* partial_histogram,
    const uint32_t* input_words, uint32_t word_count)
{
    __ubuf__ uint32_t s_hist[WARP_COUNT * BIN_COUNT];

    // A __ubuf__-qualified POINTER may not carry an initialiser: `__ubuf__ T* p = expr;`
    // fails with `error: initialization is not supported for __shared__ variables`, because
    // __ubuf__ is a __shared__-class attribute and the dialect forbids initialising one.
    // It applies to a pointer that merely points *into* UB, not just to UB arrays.
    // Split the declaration from the assignment:
    __ubuf__ uint32_t* warp_hist;
    warp_hist = s_hist + (threadIdx.x >> 5) * BIN_COUNT;

    // Zero init (cooperative across all threads)
    for (uint32_t i = 0; i < (WARP_COUNT * BIN_COUNT) / THREADS_PER_BLOCK; i++) {
        s_hist[threadIdx.x + i * THREADS_PER_BLOCK] = 0;
    }
    asc_syncthreads();

    // Grid-stride loop: per-warp atomic add to __ubuf__ histogram
    for (uint32_t tid = blockIdx.x * blockDim.x + threadIdx.x;
         tid < word_count; tid += blockDim.x * gridDim.x) {
        uint32_t bin = compute_bin(input_words[tid]);
        asc_atomic_add(warp_hist + bin, 1U);
    }
    asc_syncthreads();

    // Merge across warps: each thread handles one bin
    for (uint32_t bin = threadIdx.x; bin < BIN_COUNT; bin += THREADS_PER_BLOCK) {
        uint32_t sum = 0;
        for (uint32_t w = 0; w < WARP_COUNT; w++) {
            sum += s_hist[bin + w * BIN_COUNT];
        }
        partial_histogram[blockIdx.x * BIN_COUNT + bin] = sum;
    }
}

// Kernel 2: merge partial histograms from all blocks (parallel tree reduction in __ubuf__)
```

Key APIs: `asc_atomic_add()` on `__ubuf__`, `asc_syncthreads()`, `gridDim.x`
**Note**: Uses Model A (`__global__` + 4-arg launch). Two sequential kernel launches on host side.

> **The `warp_hist` pointer is optional — indexing `s_hist[base + bin]` is simpler and compiles
> identically.** Device-verified on CANN 9.1.0-beta.3 / `dav-3510`, same source three ways:
>
> | form | result |
> |---|---|
> | `__ubuf__ uint32_t* w = s_hist + off;` | **no object** — `initialization is not supported for __shared__ variables` |
> | `__ubuf__ uint32_t* w; w = s_hist + off;` | 12512 B, `simt_`=1, `Kernel_Type`=1 |
> | `uint32_t base = off;` then `s_hist[base + bin]` | 12184 B, `simt_`=1, `Kernel_Type`=1 |
>
> The zero-init loop above also assumes `THREADS_PER_BLOCK` divides `WARP_COUNT * BIN_COUNT`
> exactly. It does at 8×256/256, but if you retune either constant, switch to the guarded
> `for (uint32_t i = threadIdx.x; i < WARP_COUNT * BIN_COUNT; i += THREADS_PER_BLOCK)` form or
> the tail bins keep whatever UB held before.

---

**1.15 Debug Printf**

For kernel debugging during development. Guard with thread ID check to avoid flooding output.

Source: SDK example `printf.asc`.

```cpp
#include "asc_printf.h"

// Inside kernel — guard to limit output volume
if (threadIdx.x < 3) {
    printf("[SIMT] tid=%u val=%f\n", idx, val);
}
```

**Note**: Include is `"asc_printf.h"` (NOT `"simt_api/asc_printf.h"`).

---

## §1.13 Atomic accumulate to GM (scatter-add / segment-sum / bincount)

`out[indices[i]] += updates[i]`, where several `i` may target the same slot. This is the pattern
the other sections here do *not* cover — §1.10 atomics a single counter, §1.12 atomics integer
histogram bins in `__ubuf__`.

**Choosing the accumulator dtype is the whole problem**, and the failure mode of getting it wrong
is a plausible-looking number, not a crash. Every dtype you are likely to want has a native atomic
— but availability is split across **two different headers**, and that split is what earlier
revisions of this skill got wrong. The matrix lives in
[`simt_multi_dtype_guide.md` §Atomic add — dtype coverage](simt_multi_dtype_guide.md#atomic-dtypes);
check it before assuming you need a CAS loop.

Two caveats matter specifically for this pattern: the **scalar** 16-bit overloads' return value is
a non-atomic re-read, so use them where you ignore the result (accumulation) and not as a cursor;
and 16-bit accumulation over many hits loses mantissa, so widen to `float` when precision demands
it rather than when the atomic is missing.

```cpp
// float / int32 accumulate — grid-stride so any index count fits a bounded grid
for (uint32_t i = blockIdx.x * blockDim.x + threadIdx.x; i < n; i += gridDim.x * blockDim.x) {
    int64_t slot = static_cast<int64_t>(indices[i]);
    if (slot < 0) slot += outLen;                 // negative-index wrap, if your semantics allow
    if (slot < 0 || slot >= outLen) continue;     // OOB guard before any write
    asc_atomic_add(&out[slot], updates[i]);
}
```

> ⚠️ **Never `asc_atomic_add(reinterpret_cast<__gm__ float*>(half_ptr), v)`.** That is a 4-byte
> atomic on a 2-byte slot; it corrupts the neighbouring element. It has already cost one benchsite
> run.

**Contention**: GM atomic RTT is ~16.9k cycles and serializes. When many lanes in a warp hit the
same slot, dedup first — `asc_ballot` + `__popc` to elect one lane per distinct slot per warp,
reducing traffic up to 32×. Worth it only when duplication is actually high; profile first.

**Verification is not optional.** A dropped atomic update leaves output that passes loose
tolerance checks. Force a hot bin rather than trusting random indices, and check per-element
against an independent golden (`np.add.at` / `np.bincount`). Assert the **exact** conservation law
your operator has — `sum(bins) == N` for a histogram — because a mean-relative-error gate hides
this entire bug class.

**The 3×-bit-identical rule applies to accumulation, not to every atomic.** Requiring
bit-identical output across three runs of the same input is right when the atomic is an
*accumulator over a commutative op with an integer or exactly-representable result*. It is
**wrong** when the atomic is a *cursor* handing out slots (stream compaction, dynamic work
queues): there the output *order* legitimately varies run to run, and demanding reproducibility
makes a correct kernel look broken. Measured: a verified-correct compaction kernel reported
non-identical output across runs, and the non-reproducibility was itself intermittent — the same
binary at `blocks=1` flipped between reproducible and not. For a cursor, compare **sorted**
outputs, assert the count exactly, assert no poison hole below the cursor, and assert nothing was
written past it. For float accumulation, expect run-to-run variation from summation order and
compare with a tolerance derived from the accumulation depth, not bitwise.

Full rationale in [`simt_multi_dtype_guide.md` §Verifying an atomic](simt_multi_dtype_guide.md#verifying-an-atomic).
<!-- claim: atomic-3x-bitwise-rule · also in: simt_multi_dtype_guide.md · find with: grep -rn "claim: atomic-3x-bitwise-rule" skills/simt-codegen · edit all sites together -->

---

> **ISA verification data**: [`ascend950pr_isa_probes/simt.atomic.rmw.md`](ascend950pr_isa_probes/simt.atomic.rmw.md)
