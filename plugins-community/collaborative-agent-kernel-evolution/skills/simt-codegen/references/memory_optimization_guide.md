# Memory Optimization Guide — SIMT on Ascend 950

> Derived from the CANN SDK examples `03_simt_api/03_best_practices/00_memory_optimizations/` (CANN 9.1.0-beta.3).
> Applies to both Model A and Model B SIMT kernels.
> **Ascend950PR data**: `ascend950pr_isa_probes/simt.ldst.global.md` — `__ldg`/`__stg` width variants (B8-B128, B128 = 2 ops), LDG RTT = 173 cy, STG RTT = 255 cy

---

## 1. Memory Coalescing

**Rule**: Consecutive `threadIdx.x` values must access consecutive memory addresses.

### Good: Coalesced Access

```cpp
// Thread 0 reads addr+0, thread 1 reads addr+1, ... thread 31 reads addr+31
float val = input[blockIdx.x * blockDim.x + threadIdx.x];
```

The hardware can merge 32 adjacent loads into a single memory transaction.

### Bad: Strided Access

```cpp
// Thread 0 reads addr+0, thread 1 reads addr+stride, ... thread 31 reads addr+31*stride
float val = input[threadIdx.x * stride + offset];
```

Each thread triggers a separate memory transaction. Bandwidth utilization drops by up to `stride×`.

### Per-Thread Load/Store Intrinsics — `__ldg`/`__stg` (Ascend950PR verified)

Explicit per-thread global memory access. These are an alternative to plain pointer dereference (`x[i]`) and to `asc_ldcg/ldca/stcg`.

```cpp
int32_t v = __ldg(&x[i]);        // explicit load from global memory
__stg(&z[i], v + 1);             // explicit store to global memory
```

**Width variants** (all verified errors=0):

| Type | Width | ISA Ops per element |
|---|---|---|
| `int8_t` / `uint8_t` | B8 | 1 LDG + 1 STG |
| `int16_t` | B16 | 1 LDG + 1 STG |
| `int32_t` / `float` | B32 | 1 LDG + 1 STG |
| `int64_t` | B64 | 1 LDG + 1 STG |
| `int4` (128-bit) | B128 | **2 LDG + 2 STG** |

**B128 hazard**: `int4` types lower to 2 ops each, not 1. Cost models must account for this (2x instruction count per element).

Plain `x[i]` dereference also lowers to `SIMT_LDG` — `__ldg` adds L2 cache hint control (`LD_L2CacheType`: FV, LV, PERS, PREF, NOTALLOC_*).

### Fix: UB-Tiled Approach (from `matrix_transpose.asc`)

When the algorithm requires non-coalesced access (e.g., column reads on row-major data):

1. Load coalesced into `__ubuf__` tile
2. `asc_syncthreads()`
3. Read from tile in the transposed order (no coalescing requirement for `__ubuf__`)
4. Write coalesced to output

See `simt_operator_patterns.md` Matrix Transpose section for the full pattern.

---

## 2. Cache Hints (from `data_cache_hint.asc`)

Ascend 950 supports three cache hint APIs that override the default caching policy:

| API | Behavior | Use When |
|---|---|---|
| `asc_ldca(&addr)` | Load cached — allocate in L1, keep on eviction | Data reused across iterations (lookup tables, embeddings, constants) |
| `asc_ldcg(&addr)` | Load streaming — bypass L1 cache | Data read exactly once per kernel (streaming input) |
| `asc_stcg(&addr, val)` | Store streaming — bypass L1, write directly to L2/GM | Data written once, not read back (final output) |

### When Cache Hints Matter

Cache hints are most impactful when the kernel has **mixed access patterns**:

```cpp
// Lookup table (reused by many threads) + streaming input (read once)
float weight = asc_ldca(&lookup_table[bin]);       // keep in L1
float data = asc_ldcg(&input[idx]);                // don't pollute L1
float result = data * weight;
asc_stcg(&output[idx], result);                    // write-through
```

Without hints, the streaming `input` data would evict the reused `lookup_table` from L1 cache, causing repeated cache misses on the table.

### When to Skip

- **All data is streaming** (pure element-wise ops): cache hints add instruction overhead with no benefit — the hardware's default policy is already optimal.
- **All data is reused** (small working set): same — everything fits in L1 anyway.
- **Uncertain**: omit hints and let the hardware decide. Profile before adding.

### Include

Cache hint functions are in `simt_api/device_functions.h` (also available via `simt_api/asc_simt.h`).

---

## 3. UB Bank Conflict Avoidance (from `matrix_transpose.asc`)

`__ubuf__` memory is banked — typically 32 banks, each 4 bytes wide. A **bank conflict** occurs when multiple threads in a warp access different addresses in the same bank simultaneously.

### The Problem

```cpp
__ubuf__ float tile[32][32];       // 32 columns = 32 banks

// Write: tile[threadIdx.y][threadIdx.x] — each thread in a warp hits a different bank ✓
// Read:  tile[threadIdx.x][threadIdx.y] — all 32 threads in a warp access bank (threadIdx.y) ✗
```

When reading the transposed tile, all threads access column `threadIdx.y` — the same bank — causing a 32-way bank conflict that serializes the access.

### The Fix: +1 Padding

```cpp
__ubuf__ float tile[32][32 + 1];   // 33 columns per row

// Write: tile[threadIdx.y][threadIdx.x] — still fine ✓
// Read:  tile[threadIdx.x][threadIdx.y] — thread i accesses address (i * 33 + threadIdx.y)
//        Since 33 and 32 are coprime, each thread hits a different bank ✓
```

### When to Apply

- `__ubuf__` 2D arrays where writes and reads use different indexing orders (e.g., write row-major, read column-major)
- NOT needed for 1D `__ubuf__` arrays or when reads and writes use the same order

### Cost

One extra `float` per row × 32 rows = 128 bytes overhead. Negligible compared to the 4–32× speedup from eliminating bank conflicts.

---

## 4. Dynamic UB Allocation (from `data_cache_hint.asc`)

Instead of statically sizing `__ubuf__` arrays, use dynamic allocation for flexibility:

```cpp
extern __ubuf__ char dynamicBuf[];    // declared globally

__global__ void kernel(float* input, float* output, uint64_t n) {
    float* ubuf_data = reinterpret_cast<float*>(dynamicBuf);
    // Use ubuf_data[0..N-1] as scratch space
}

// Host: launch with dynamic UB size
kernel<<<blocks, threads, UB_SIZE_BYTES, stream>>>(input, output, n);
```

**When to use:**
- UB size depends on runtime parameters (e.g., bin count, tile size)
- Multiple kernels need different UB sizes
- UB size exceeds what can be statically declared

**Limit:** The SDK example (`data_cache_hint.asc`) uses `UB_SIZE = 216 * 1024` (216KB), which exceeds the 128KB DataCache documentation. This suggests dynamic UB may draw from a larger pool than static `__ubuf__` declarations. Use 128KB as the conservative limit; test larger sizes on hardware.

> **Resolved 2026-08-11:** `216 * 1024 = 221184` is exactly this device's **total kernel shared
> memory budget**. Measured: 221184 B is the largest value accepted, and 222208 B is rejected at
> launch with `Invalid_Argument(EE1017) CheckAndGetTotalShareMemorySize failed`. So the SDK is
> sizing to the hardware budget, not to a separate "larger pool". Note that correctness fails
> *before* the budget does — a static `__ubuf__` array in a VF returns silently wrong data from
> ~192 KB with `sync_rc=0`. Keep 128 KB as the working limit for that reason, not because the
> budget is 128 KB. See §6.

**Warning (A5-validated)**: `extern __ubuf__ char dynamicBuf[]` has NOT been validated for VF reads on Ascend950PR. If VF threads need to read from dynamically allocated UB, use static `__ubuf__` arrays inside the `__simt_vf__` function instead (see §6 VF UB Addressing Rules).

---

## 5. Grid-Stride Loop (from `histogram.asc`)

When the data size exceeds the grid size, use a grid-stride loop instead of launching more blocks:

```cpp
for (uint32_t i = blockIdx.x * blockDim.x + threadIdx.x;
     i < total;
     i += blockDim.x * gridDim.x) {
    // process element i
}
```

**Advantages:**
- Fixed grid size regardless of data size
- Better for patterns that accumulate per-thread state (histogram, reduction)
- Reuses `__ubuf__` initialization across iterations (amortizes the zero-init cost)

**When to use:** Histogram, reduction, scan — any pattern where per-block state is accumulated across iterations. For simple element-wise ops, a grid-stride loop works but offers no advantage over sizing the grid to cover all elements.

---

## 6. UB Pre-Staging (from `gather_v2.asc`)

Bulk-copy hot input data from GM to UB *before* launching SIMT threads, so per-thread reads hit on-chip SRAM instead of HBM. Measured impact: ~22% speedup on gather (SDK: gather_v1 → gather_v2).

### VF UB Addressing Rules (A5-validated)

VF threads can access UB, but the rules depend on the allocation method:

| Allocator | VF Write → UB | VF Read ← UB | Size Limit | Use Case |
|-----------|:---:|:---:|:---:|---|
| `LocalMemAllocator` + `GetPhyAddr()` | yes | **contested** — 341 here, succeeded elsewhere (see note) | 128KB direct-launch / **8KB via msopgen** — see below | Model C hybrid: VF gathers to UB, SIMD reads |
| Static `__ubuf__` (in VF function) | yes | yes | **8192 bytes (8KB)** | Model B staging: VF cooperative load + VF read |

### Resolved 2026-08-11 — the two numbers measured two different things, on one machine

The earlier "two devices disagree by 27x" framing was wrong twice over. Both sets of numbers came
from the **same box** (`hostname=acde1f3b9e79`, `soc_name=Ascend950PR_9599`,
`res_limit_vector_core=72`, toolkit `9.1.0-beta.3` — compare
`/janet/950PR_constitution/evidence_simt_device_2026-08-06/machine_id.txt` with `hostname`), and
they were not measuring the same quantity. Three distinct limits, all re-measured on this device:

| quantity | limit | over the limit |
|---|---|---|
| UB a VF reads via a **pointer passed in** from the aicore half | **exactly `[0, 8192)`** | `507035 ACL_ERROR_RT_VECTOR_CORE_EXCEPTION` at runtime |
| a static `__ubuf__` array the **VF declares itself** | correct to **≥160 KB** | **silently wrong data** from ~192 KB, `sync_rc=0` |
| total kernel shared memory (all UB) | **221184 B** | `Invalid_Argument(EE1017) CheckAndGetTotalShareMemorySize failed` at launch |

So the 8 KB figure belongs **only** to the pointer-passed path, and the 221184 B figure is the total
UB budget — it was never a VF-readable ceiling. Attaching 8 KB to "static `__ubuf__` arrays declared
in a single `__simt_vf__`", as this section previously did, put the number on the wrong mechanism.

**The 8 KB window is exact and is a property of the address, not the buffer.** Holding one 64 KB
`TBuf` at UB `0x0` and sweeping a single-element VF read: index 2047 (byte 8188) returns correct
bits, index 2048 (byte 8192) faults. Ten further bisect modes separately ruled out total `TPipe`
footprint (64 KB with the read buffer first: passes), number of elements read, thread count (64 and
256 give the identical boundary) and pointer spelling (`GetPhyAddr()` cast and `&t(0)` yield the same
value). Actionable rule: **allocate VF-readable buffers first**; ordering alone decides whether the
kernel runs.

**"8192 B passes / 8200 B fails with error 341" does not reproduce.** Re-running the original probe
(`evidence_simt_device_2026-08-06/ub.asc`, static array inside the VF, write then read back with a
golden check, `dim3(64)`): 8192 B, 8200 B, 16 KB, 64 KB, 96 KB, 128 KB, 129 KB and 160 KB all pass
with zero mismatches. Whatever produced the 341 was not this ceiling.

⚠️ **The dangerous regime is the middle row, not the top one.** At 192 KB and at 221184 B the static
array returns `sync_rc=0` with plausible-looking wrong values (32 of 64 lanes mismatched) — no error
code, no fault. Only at 222208 B does the launch get rejected outright. Do not treat "it ran" as
"it was correct" anywhere near that budget; the original log recorded 221184 B as a PASS, and today
the same size produces corruption.

Measured 2026-08-11 on Ascend950PR_9599 / CANN 9.1.0-beta.3 / `dav-c310-vec`, ccec clang 15.0.5.

**Why previous hybrid kernels work**: All Model C hybrids (GatherReluHybrid, MaskedSoftmax) have VF threads *only writing* to `LocalMemAllocator`-allocated UB. The SIMD pipe reads from it. VF never reads from `LocalMemAllocator` UB in those kernels.

> ✅ **Resolved for the `TBuf`/`GetPhyAddr` path (2026-08-11): the constraint is an address window,
> not a prohibition.** A VF reads a `TBuf`-allocated buffer bit-exact through a raw
> `__ubuf__ T*` argument **if and only if the buffer sits below UB offset `0x2000`**. The same buffer
> at `0x2000` raises `507035 ACL_ERROR_RT_VECTOR_CORE_EXCEPTION` — a third failure signature,
> distinct from the 341 and EE1017 below. Ten bisect modes separately ruled out total `TPipe`
> footprint (64 KB with the read buffer allocated first: passes), element count (256 of 2048 at a
> high address: still faults), thread count (64 and 256 hit the identical boundary) and pointer
> spelling (`GetPhyAddr()` integer cast and `&t(0)` produce the same value). So the actionable rule
> is **allocate VF-readable buffers first**; ordering alone decides whether the kernel runs.
> Measured 2026-08-11 on Ascend950PR_9599 / CANN 9.1.0-beta.3 / `dav-c310-vec`. This is the
> `TPipe`/`TBuf` path specifically — the `LocalMemAllocator` rows below were not re-probed, so treat
> their status as unchanged.
>
> ⚠️ **The VF-read prohibition is contested, and it may be costing you an architecture.** On the
> 72-core part (`950PR_constitution` §5.0.1 P-C) a VF read from a `LocalMemAllocator` buffer
> **succeeded bit-exact** — `Alloc<float>(64)`, VF writes, `asc_syncthreads()`, VF sums all 64,
> every lane reads 64. Error 341 was not raised. If that holds on your part, the constraint is
> phantom, and workloads currently pushed into the Model C two-VF detour purely to avoid a VF read
> could stay in Model B. **Probe it before designing around it.** We keep the restriction as the
> documented default because it is what our device shows and the conservative choice is correct on
> both, but do not treat it as settled hardware behaviour.
> <!-- claim: lma-vf-read-prohibition · also in: pass_details_model_c.md · find with: grep -rn "claim: lma-vf-read-prohibition" skills/simt-codegen · edit all sites together -->

### When to Apply

```
Does VF need to READ from UB? (Model B staging)
├── YES → Is staged data per chunk ≤ 8KB?
│         ├── YES → Use static __ubuf__ in VF function + VF cooperative load
│         └── NO  → Cannot apply — exceeds VF-readable UB limit (8KB)
└── NO (VF only writes, SIMD reads — Model C hybrid)
      → Is total UB data per block ≤ 128KB?
          ├── YES → Use LocalMemAllocator + GetPhyAddr()
          └── NO  → Cannot apply — exceeds SIMT DataCache limit
```

Good candidates: lookup tables, small inputs with random access, many threads reading overlapping regions.
Poor candidates: large inputs (>128KB), sequential access, write-heavy operators.

### Model B Adaptation (A5-validated approach)

Declare `__ubuf__` arrays inside the VF function and use VF cooperative load (threads copy GM→UB in parallel). This is the only A5-validated pattern for VF reads from UB.

```cpp
__simt_vf__ __launch_bounds__(256) inline void simt_gather(
    __gm__ const float* input,
    __gm__ const int32_t* index, __gm__ float* output,   // signed: negative indices are legal
    uint32_t input_size, uint32_t total_length)
{
    __ubuf__ float input_buf[2048];  // 8KB max for VF-readable UB

    // VF cooperative load: threads copy GM → UB in parallel
    for (uint32_t i = threadIdx.x; i < input_size; i += blockDim.x) {
        input_buf[i] = input[i];
    }
    asc_syncthreads();  // ensure all threads see the loaded data

    uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= total_length) return;
    output[idx] = input_buf[index[idx]];  // UB read — on-chip SRAM speed
}

__global__ __vector__ void kernel_entry(
    __gm__ float* input, __gm__ uint32_t* index, __gm__ float* output,
    uint32_t input_size, uint32_t total_length)
{
    asc_vf_call<simt_gather>(dim3(256), input, index, output, input_size, total_length);
}
```

### Model C Adaptation

Model C uses `LocalMemAllocator` UB as a bridge (SIMT writes→UB→SIMD reads→GM). VF threads **write** to this UB, and the **SIMD pipe** reads from it. Do NOT attempt VF reads from `LocalMemAllocator` UB — error 341.

> ⚠️ **The VF-writable size is set by the launch's `dynUBufSize`, not by `InitBuffer`.**
> A 128 KB `InitBuffer` reserve does **not** grant 128 KB of VF-writable UB. Measured on
> `dav-3510`, holding reserve, rows written, rows reduced and grid fixed and varying
> only the launch argument:
>
> | rows written | `dynUBufSize=0` | `dynUBufSize=8192` |
> |---|---|---|
> | 4 | PASS | PASS |
> | 5 | **FAIL 507035** | PASS |
>
> With `dynUBufSize >= 8192` the identical kernel runs at 64 rows. The 128 KB figure is
> reachable **only via direct launch**, `kernel<<<blocks, dynUBufSize, stream>>>`.
>
> **The msopgen/aclnn delivery path has no `dynUBufSize` argument.** A Model C kernel
> shipped as a CANN custom op is therefore capped at an **8192-byte UB bridge**.
> Budgets of 10240 / 12288 / 14336 / 16384 / 65536 all fault with 507035 on that path.
> Size the bridge to 8 KB for anything delivered through msopgen, and treat the 128 KB
> number as direct-launch-only. Note also that a `dynUBufSize` above the 248 KB physical
> UB fails at launch with `ret 107000`.

For pre-staging a separate read-only input buffer in Model C, the VF function would need static `__ubuf__` arrays for VF reads (≤8KB) PLUS the `LocalMemAllocator` buffer for VF writes (up to 128KB). The two allocators coexist because they map to different UB address regions. Total UB budget across both: `8KB (VF-readable) + 128KB (write-only) ≤ total DataCache`.

### Sync Requirement (Mandatory)

`asc_copy_gm2ub_align` uses the MTE2 pipe; `asc_vf_call` uses the V pipe. Without explicit sync, SIMT threads may read stale UB data:

```cpp
if ASC_IS_AIV {
    asc_sync_notify(PIPE_MTE2, PIPE_V, EVENT_ID0);
    asc_sync_wait(PIPE_MTE2, PIPE_V, EVENT_ID0);
}
```

The `if ASC_IS_AIV` guard ensures sync only runs on AI Vector cores (SIMT only executes on AIV).

### dynUBufSize Rules

| Scenario | `dynUBufSize` |
|---|---|
| Model B + UB pre-staging | 0 (static `__ubuf__` array, not `LocalMemAllocator`) |
| Model C + UB pre-staging | > 0 (for `LocalMemAllocator` buffers, same as without pre-staging) |

### Size Constraints

`__ubuf__ T buf[N]` requires N to be a compile-time constant. The size limit depends on whether VF threads read from UB:

**VF-readable UB (static `__ubuf__` in VF function): `N * sizeof(T) ≤ 8KB`**

| Data type | Max elements in 8KB |
|---|---|
| `float` / `int32_t` (4B) | 2,048 |
| `half` / `bfloat16_t` (2B) | 4,096 |
| `int8_t` (1B) | 8,192 |

**VF-write-only / SIMD-readable UB (Model C hybrid via `LocalMemAllocator`): up to 128KB**

| Data type | Max elements in 128KB |
|---|---|
| `float` / `int32_t` (4B) | 32,768 |
| `half` / `bfloat16_t` (2B) | 65,536 |
| `int8_t` (1B) | 131,072 |

Each AI Core has its own UB (per-block private). UB arrays declared in `__simt_vf__` functions have a hard 8KB total limit across all arrays in that function.

---

## 7. Per-Element `__gm__` Access vs UB-Staged Tile + Compute + DMA-Back

Indexing `__gm__` per-element inside the hot loop incurs a full HBM round-trip per access
(LDG RTT ≈ 173 cy, STG RTT ≈ 255 cy). The alternative: copy the working set into UB once,
compute entirely on-chip, then DMA the result back.

**When staging wins**: compute-heavy ops; random-access patterns (gather-style reads); any op
that touches the same GM region more than once per output element.

**When staging is a wash**: pure coalesced element-wise copies where each element is read
exactly once — the DMA setup cost can exceed the cache benefit.

**Constraint**: VF-readable static `__ubuf__` is capped at 8 KB per VF function (§6 above).
For larger working sets, use the Model C `LocalMemAllocator` path (VF writes, SIMD reads,
up to 128 KB) or process in tiles that fit within 8 KB.

---

## 8. Per-Core Contiguous Slices + UB Double-Buffering vs Pure Grid-Stride

A pure grid-stride loop (§5) assigns elements to cores in round-robin order. For
bandwidth-bound ops, this means each core's DMA requests are scattered across HBM, and
the V pipe stalls waiting for each load.

**Alternative**: assign each core a contiguous slice of the output domain and ping-pong two
UB buffers so MTE2 (DMA) and V (compute) overlap:

```
while slices remain:
    DMA-load next slice into buf[ping]          // MTE2 pipe
    sync_notify(MTE2 → V)
    compute on buf[pong] (previous slice)       // V pipe
    DMA-store result from buf[pong]             // MTE2 pipe
    swap ping/pong
```

**When it helps**: large working sets per core; ops where DMA latency dominates; ops with
predictable, contiguous access patterns.

**When it does NOT help**: small inputs where double-buffer setup dominates; irregular access
patterns that prevent contiguous slice assignment; ops already limited by compute, not memory.

For the full set of builtin-parity optimization ideas (including algorithmic and launch-count
techniques), see `builtin_parity_optimizations.md`.

---

## 9. UB-Bitcast Dodge (Pure Data-Movement Ops)
<!-- claim: half-ub-tile-availability · also in: ../SKILL.md · find with: grep -rn "claim: half-ub-tile-availability" skills/simt-codegen · edit all sites together -->

For pure data-movement ops (no arithmetic touches the value), 4-byte dtypes can share one `float` UB tile via raw pointer bitcast, and int64 uses native int64 UB. This sidesteps the 507035 non-fp32/int64 UB fault while remaining bit-exact — NaN, inf, and denormals survive because no arithmetic is performed.

### Carrier/TILE Constraints

| Dtype width | Carrier | TILE | Declaration | Size |
|-------------|---------|------|-------------|------|
| 4-byte (float32, int32) | `float` | 32 | `__ubuf__ float tile[32][33]` | 4224 B |
| 8-byte (int64) | `int64_t` | 16 | `__ubuf__ int64_t tile[16][17]` | 2176 B |
| 2-byte (half, bf16) | N/A | N/A | Direct-GM only | 507035 on UB path |
| 1-byte (int8) | N/A | N/A | Direct-GM only | 507035 on UB path |

The +1 column padding eliminates UB bank conflicts (see section 3).

### VF Static-UB Ceiling

Recommended: `TILE=16` for int64 (`tile[16][17]` = 2176 B) and `TILE=32` for 4-byte types
(`tile[32][33]` = 4224 B). These are safe on every part measured so far.

The reason for the int64 recommendation is **contested**. On our device (56-core) int64
`tile[32][32]` = 8192 B faults at runtime with an empty plog and the error swallowed. On the
72-core part (`950PR_constitution` §5.0.1 P-D) the same tile **passes bit-exact**, and so does
`tile[32][33]` at 8448 B. Since the recommended sizes are well under both walls, keep them — but
if you are debugging an int64 UB fault, note that the 8192 B boundary may not be your cause.
<!-- claim: vf-readable-ub-ceiling · also in: ../SKILL.md · find with: grep -rn "claim: vf-readable-ub-ceiling" skills/simt-codegen · edit all sites together -->

### Shape Gate

UB-tiled data movement is a net win only on thin shapes (reduced-2D aspect ratio >= 8). On large square or near-square shapes, UB round-trip + `asc_syncthreads` + tile-cap serial grid-stride loses to direct 8x-unroll GM-to-GM streaming.

Gate the fast path by shape/perm/dtype at host tiling time, never by case index — case-index gating does not generalize on the benchsite.

### Scope

Pure data-movement only. Not usable for compute ops — any arithmetic on the value would produce incorrect results through the float carrier for non-float input types.

---
