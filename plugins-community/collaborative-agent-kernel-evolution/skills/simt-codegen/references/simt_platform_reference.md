# SIMT Platform Reference — Ascend 950PR

> Deep reference for hardware details, API mapping, and memory layout.
> Not on the main reading path — see `SKILL.md` § Reading Path for the entry point.
> For model-specific code patterns, see the self-contained `pass_details_model_{A|B|C}.md` files.

---

## Simt:: Namespace API Mapping

Both `asc_*` (Model A) and `Simt::*` (Model B/C) namespaces lower to the same ISA ops.

| Feature | Model A (`asc_*`) | Model B/C (`Simt::`) |
|---|---|---|
| Thread index | `threadIdx.x` | `Simt::GetThreadIdx<0>()` |
| Block index | `blockIdx.x` | `Simt::GetBlockIdx()` |
| Block size | `blockDim.x` | `Simt::GetThreadNum<0>()` |
| Grid size | `gridDim.x` | `Simt::GetBlockNum()` |
| Warp size | `warpSize` | `Simt::GetWarpSize()` |
| Warp reduce | `asc_reduce_add(val)` | `Simt::WarpReduceAddSync<T>(val)` |
| Shuffle | `asc_shfl(v, src, w)` | `Simt::WarpShflSync(v, src, w)` |
| Shuffle down | `asc_shfl_down(v, d)` | `Simt::WarpShflDownSync(v, d, 32)` |
| Shuffle up | `asc_shfl_up(v, d)` | `Simt::WarpShflUpSync(v, d, 32)` |
| Shuffle xor | `asc_shfl_xor(v, m)` | `Simt::WarpShflXorSync(v, m, 32)` |
| Ballot | `asc_ballot(pred)` | `Simt::WarpBallotSync(pred)` |
| All | `asc_all(pred)` | `Simt::WarpAllSync(pred)` |
| Any | `asc_any(pred)` | `Simt::WarpAnySync(pred)` |
| Active mask | `asc_activemask()` | `Simt::WarpActiveMask()` |
| Atomic add | `asc_atomic_add(addr, v)` | `Simt::AtomicAdd<T>(addr, v)` |
| Atomic CAS | `asc_atomic_cas(addr, cmp, v)` | `Simt::AtomicCas<T>(addr, cmp, v)` |
| Barrier | `asc_syncthreads()` | `asc_syncthreads()` (same) |
| Fence | `asc_threadfence()` | `asc_threadfence()` (same) |
| Dispatch | `asc_vf_call<fn>(dim3(T), ...)` | `Simt::VF_CALL<fn>(Simt::Dim3{T,1,1}, ...)` |
| Launch bound | `__launch_bounds__(T)` | `LAUNCH_BOUND(T)` |
| Core pin | not needed — [puresimt infers AIV](simt_build_and_compile.md#kernel-task-type) | `KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY)` |
| TU guard | `#if defined(ASCENDC_CPU_DEBUG)` | `#ifndef __CCE_AICORE__` |

No CUDA-style mask argument on vote/shuffle (whole-warp implicit). The file compiles twice (host + device pass); guard host code with `#ifndef __CCE_AICORE__`.

---

## FP<->Int Cast Intrinsics — `__cvt_*<ROUND>` (Ascend950PR verified)

Per-thread type conversion. Each cast = exactly 1 ISA op (F2I, I2F, or F2F).

```cpp
int32_t v = __cvt_int32_t<ROUND::R>(x[i]);  // float->int, nearest-even, saturation forced
float f = __cvt_float<ROUND::R>(v);           // int->float, nearest-even
```

**ROUND modes** (from `__clang_dpp_types.h`):

| Mode | Meaning | C equivalent |
|---|---|---|
| `ROUND::R` | Nearest-even (default) | `nearbyint()` with FE_TONEAREST |
| `ROUND::A` | Nearest, ties-away | `std::round()` |
| `ROUND::F` | Floor | `floor()` |
| `ROUND::C` | Ceiling | `ceil()` |
| `ROUND::Z` | Truncate (toward zero) | `trunc()` / C-style `(int)f` |

**Critical semantics** (all verified T1-sim):
- **Saturation is always forced** (`RS_ENABLE`) — fp->int NEVER wraps on overflow. `2147483648.0f -> INT32_MAX`, not undefined
- **NaN -> 0** (always, not UB/garbage)
- `__cvt_uint32_t` return type is `int` — cast result to `uint32_t` explicitly to avoid sign confusion at values > 2^31
- f32->f32 (`__cvt_float(float)`) quantizes per mode; NaN -> `0x7FFFFFFF`; -0 -> +0

**API family**:
- `__cvt_int32_t<ROUND>(float)`, `__cvt_uint32_t<ROUND>(float)`, `__cvt_int64_t<ROUND>(float)`, `__cvt_uint64_t<ROUND>(float)`
- `__cvt_float<ROUND>(int32/uint32/int64/uint64)`, `__cvt_float<ROUND>(float)` (quantize)

---

## Bit Manipulation Builtins (Ascend950PR verified)

Per-thread integer bit operations. **Critical: not all are single ISA ops**.

| Builtin | ISA Cost | Notes |
|---|---|---|
| `__brev(u32)` | 1 op (BREV) | Bit reverse |
| `__popc(u32)` | 1 op (POPC) | Population count |
| `__clz(int)` | 1 op + zero-guard (CLZ+ISETP) | Count leading zeros; `__clz(0)` = 32 |
| `__ffs(int)` | **~6 ops** (POPC-based expansion) | Find first set (1-based); `__ffs(0)` = 0. **NOT single instruction** |
| `__mulhi(int, int)` | 1 op (IMUL) | High 32 bits of 32x32 multiply |
| `__umulhi(u32, u32)` | 1 op (IMUL) | Unsigned high 32 bits |
| `__mul_i32toi64(int, int)` | 1 op (IMUL) | Full 64-bit product from 32x32 |
| `__umul64hi(u64, u64)` | **~12 ops** | High 64 bits — software expansion |
| `__mul64hi(s64, s64)` | **~21 ops** | Signed high 64 — software expansion |
| `__byte_perm(x, y, sel)` | 1 op (PRMT) | CUDA-compatible byte permutation |
| `__sad(x, y, z)` | software | z + |wrap32(x-y)| — wraps in 32-bit THEN abs |
| `__mul24(x, y)` | IMUL + 3xSHFI | **NOT** a hardware 24-bit multiply |

**64-bit variants**: `__brev(u64)` = 2xBREV; `__popc(u64)` = 2xPOPC+IADD; `__clz(ll)` and `__ffs(ll)` are **divergent software** — they emit `BRANCH+DVG` which diverges the warp. Prefer 32-bit variants and budget divergence cost if 64-bit is unavoidable.

---

## ISA Cost Model (Ascend950PR measured, T1-sim)

Dependent-chain issue cadence:

| ISA Op | Latency (cycles) | Notes |
|---|---|---|
| SIMT_IADD_I | 3 | Integer add |
| SIMT_FADD | 3 | FP32 add |
| SIMT_FMUL | 4 | FP32 multiply |
| SIMT_FFMA | 7 | FP32 fused multiply-add |
| SIMT_IMAD_I | 7 | Integer multiply-add |
| SIMT_REDUX | 16 | Native warp reduce (vs butterfly 5x17=85) |
| SIMT_SHFL | 17 | Warp shuffle (all variants) |
| SIMT_LDG (dep) | ~57/iter issue, RTT ~173 | Global memory load (cold, RANGE) |
| SIMT_STG (dep) | RTT ~255 | Global memory store |
| ATOMIC_GM (dep) | RTT ~16.9k | Serializes under contention |
| F2I / I2F / F2F | 1 op each | Cast — ROUND+sat are immediates |
| BREV32/POPC32/PRMT/MULHI | 1 op each | Bit ops — single instruction |
| FFS32 | ~6 ops | Software expansion (POPC-based) |
| Vote (All/Any/Ballot) | ~16-17 (est.) | Same class as REDUX/SHFL |

**ILP**: 8 independent FADD chains -> issue interval drops to 1-2 cy/op (vs 3 cy dependent). Structure loops for independent computation chains.

**Whole-program at small N (<=4096)**: All entries measure ~419 cycles flat — launch overhead dominates. Don't micro-optimize; fuse kernels instead.

**Atomic contention**: All-lane atomic (bug) = 24x wall time + 32x overcount vs leader-only. Per-thread atomics on shared counters are catastrophic.

**Body is GM-latency-bound**: LDG/STG RTT >> compute cost. Coalesce accesses + launch enough warps to overlap RTT. Compute is ~2% of body time for elementwise ops.

---

## UB Memory Layout (SIMT)

On A5 (Ascend 950), the 256KB Unified Buffer is partitioned when running SIMT:

```
┌──────────────────────────────┐
│  Static UB                   │
├──────────────────────────────┤
│  Dynamic UB                  │
├──────────────────────────────┤
│  Reserved (8KB for ASC)      │
├──────────────────────────────┤
│  DataCache                   │  ← SIMT threads access this
│  (max 128KB, min 32KB)       │
└──────────────────────────────┘
```

- **DataCache** is the only portion SIMT threads can read/write (via `__ubuf__` pointers)
- **Max 128KB** — SIMT gets at most half the 256KB UB
- **Min 32KB** — DataCache below 32KB produces a runtime error
- The SIMD (Vector) path uses the full 248KB UB budget (256KB − 8KB reserved)

---

## Thread Hierarchy

```
<<<blocks_per_grid, [threads_per_block,] dyn_ubuf_size, stream>>>

blocks_per_grid    → maps to AI Cores (56 on Ascend 950PR)
threads_per_block  → threads within one block (Model A only; Model B uses dim3 in asc_vf_call)
                     Must be multiple of 32, max 2048

Warp = 32 consecutive threads (LaneId = threadIdx.x % 32)
Block = all threads sharing one AI Core (up to 2048)
Grid = all blocks across all AI Cores
```

---

## Header Reference

| Header | Provides | When to include |
|---|---|---|
| `simt_api/common_functions.h` | `asc_vf_call`, `__simt_vf__` | Always (Model B/C) |
| `simt_api/asc_simt.h` | `blockIdx`, `threadIdx`, warp builtins | Always (Model A) |
| `simt_api/device_sync_functions.h` | `asc_syncthreads`, `asc_threadfence` | Block barriers or memory ordering |
| `simt_api/math_functions.h` | `sinf`, `expf`, `sqrtf`, etc. | Transcendental math in VF |
| `simt_api/device_functions.h` | `__float2int_rn`, `asc_ldca/ldcg/stcg/stwt` | Type casting, cache-hinted load/store |
| `simt_api/device_atomic_functions.h` | `asc_atomic_add/sub/max/min/and/or/xor/cas/inc/dec/exch` — **32/64-bit dtypes only**; the 16-bit overloads are in `asc_fp16.h`/`asc_bf16.h` below, not here ([coverage](simt_multi_dtype_guide.md#atomic-dtypes)) | Atomics on UB or GM |
| `simt_api/device_warp_functions.h` | `asc_shfl_*`, `asc_reduce_*`, `asc_all/any/ballot/activemask` | Cross-thread communication |
| `simt_api/vector_functions.h` | `make_float2/3/4`, `make_int2/3/4` | Vector type construction |
| `simt_api/asc_fp16.h` | half/half2 support for ALL above APIs | Any API uses `half`/`half2` |
| `simt_api/asc_bf16.h` | bfloat16 support for ALL above APIs | Any API uses `bfloat16_t`/`bfloat16x2_t` |

---

## A950 Hardware-Verified APIs (runtime confirmed, Jun 2026)

| API | Verified in | Operator |
|---|---|---|
| `asc_shfl_down(var, delta)` | TopK warp reduction | TopKCustom |
| `asc_shfl_xor(var, laneMask)` | Bitonic sort compare-swap | SortSim |
| `asc_shfl(var, srcLane, width)` | Stream compaction lane broadcast | NonZeroSIMT |
| `asc_ballot(pred)` | Stream compaction warp vote | NonZeroSIMT |
| `__popc(mask)` | Stream compaction popcount | NonZeroSIMT |
| `__ffs(mask)` | Stream compaction first-set-bit | NonZeroSIMT |
| `asc_atomic_add(&gm, float)` | Scatter-add accumulation | ScatterAdd |
| `asc_syncthreads()` | Cross-warp barrier | TopK, SortSim |
| `blockIdx.x/threadIdx.x/blockDim.x` | All operators | All |
| `asc_vf_call<>` with `dim3()` | All Model B operators | All |

**Documented with cycle counts from T1-sim ISA probes** (see `simt_warp_ops.md`): `asc_reduce_add` (16 cy REDUX, used in ReduceSum operator example), `asc_reduce_max`, `asc_reduce_min`, `asc_all`, `asc_any`, `asc_activemask`, `asc_shfl_up`
