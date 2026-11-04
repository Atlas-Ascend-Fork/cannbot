# Multi-Dtype Support Guide for SIMT Kernels

## Overview

SIMT kernels on Ascend 950 use C++ templates to support multiple data types from a single
source file. This is simpler than the SIMD path's `DTYPE_X1` macro + `if constexpr` approach —
SIMT uses raw pointers and free functions, so `template <typename T>` works directly.

**Default behavior**: Always generate templated kernels. The only exceptions are operators
with fixed output types (see [When NOT to Templatize](#when-not-to-templatize)).

**Target dtypes — the data axis**: `float` (float32), `half` (float16), `bfloat16_t`
(bfloat16). Add `int32_t` for operators that move or select data without arithmetic
on it (gather, scatter, transpose, concat); it costs one more instantiation and no
widening helpers, since none of the 32-bit-only API constraints below apply to it.

**The second axis — index dtypes.** Gather/scatter-family operators have a *second,
independent* dtype axis: the index tensor, `{int32_t, int64_t}`. It is not a variation
of the data axis and does not collapse into it. Template it separately:

```cpp
template <typename T, typename IndexT>
```

Total instantiations are the **cross-product**, not the max: 4 data dtypes × 2 index
dtypes = 8. The verified `operator_examples/axis_gather_example/` emits exactly that —
`nm -C gather.o | grep -c 'simt_'` returns 8, from
`{float, half, bfloat16_t, int32_t} × {int32_t, int64_t}`.

Two consequences worth stating plainly:

- **Do not hardcode the index type.** A kernel written against `int32_t* index` alone
  silently rejects int64 callers — and `torch.gather` / `index_select` /
  `scatter_add` default to int64 indices in PyTorch. It compiles; it fails at
  dispatch or, worse, reinterprets.
- **Do not use an unsigned index type** for any gather/scatter whose contract allows
  negative indices (np.take, ONNX Gather, `torch.index_select` all do). `uint32_t`
  makes `-1` unrepresentable, so the wrap-then-guard step becomes impossible to write
  correctly. Read the index as signed, wrap by `+= axisSize`, *then* bounds-check.

The host-side `dtypeCode` / `indexDtypeCode` pair in the tiling struct selects the
instantiation. On the OpDef side these two axes must appear as the full cross-product
in the `.DataType()` lists — see `SKILL.md` rule 10 and
`msopgen_adaptation.md` Step 2a. The kernel-side count and the OpDef-side count must
agree, or a registered combination has no kernel behind it.

---

## Template Pattern

### Model A (pure SIMT)

```cpp
#include "simt_api/asc_simt.h"
#include "simt_api/asc_fp16.h"     // always include — lightweight
#include "simt_api/asc_bf16.h"     // always include — lightweight

template <typename T, typename IndexT>          // IndexT: int32_t or int64_t
__global__ __launch_bounds__(256) void my_kernel(
    T* input, IndexT* index, T* output,
    uint32_t totalElements, uint32_t axisSize)  // axisSize bounds the guard
{
    uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= totalElements) return;

    // Read signed, wrap negatives, THEN bounds-check. This order is required by
    // np.take / ONNX Gather / index_select semantics.
    int64_t iv = static_cast<int64_t>(index[idx]);
    if (iv < 0) iv += static_cast<int64_t>(axisSize);
    if (iv < 0 || iv >= static_cast<int64_t>(axisSize)) {
        output[idx] = static_cast<T>(0);         // guard: no OOB read
        return;
    }
    output[idx] = input[iv];
}
```

### Model B (SIMT VF)

```cpp
template <typename T, typename IndexT>          // IndexT: int32_t or int64_t
__simt_vf__ __launch_bounds__(256) inline void my_vf(
    __gm__ const T* input, __gm__ const IndexT* index, __gm__ T* output,
    uint32_t totalElements, uint32_t axisSize)
{
    uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= totalElements) return;

    int64_t iv = static_cast<int64_t>(index[idx]);
    if (iv < 0) iv += static_cast<int64_t>(axisSize);
    if (iv < 0 || iv >= static_cast<int64_t>(axisSize)) {
        output[idx] = static_cast<T>(0);
        return;
    }
    output[idx] = input[iv];
}
```

Dispatch instantiates the cross-product. Emit `asc_vf_call<...>` only where both
types are concrete — a macro inside each `dtypeCode` case, never wrapped in another
template (see `SKILL.md` error table: `template<auto>` NTTP cannot be re-wrapped):

```cpp
#define DISPATCH(T)                                                         \
    if (td.indexDtypeCode == 0)                                             \
        asc_vf_call<my_vf<T, int32_t>>(dim3(td.threadsPerBlock), ...);      \
    else                                                                    \
        asc_vf_call<my_vf<T, int64_t>>(dim3(td.threadsPerBlock), ...);

switch (td.dtypeCode) {
    case 0: { DISPATCH(float);       break; }
    case 1: { DISPATCH(half);        break; }
    case 2: { DISPATCH(bfloat16_t);  break; }
    case 3: { DISPATCH(int32_t);     break; }
}
#undef DISPATCH
```

### Model C (hybrid SIMT+SIMD)

The `__simt_vf__` follows the same template pattern as Model B. The `__simd_vf__`
uses Micro API which accepts `half` operands directly (`Maxs`, `Adds`, `Muls`).

---

## SIMT API Dtype Constraints

Several SIMT intrinsics only accept 32-bit types. When `T` is `half` or `bfloat16_t`,
widen before the intrinsic and narrow after.

| API | Supported types | half / bfloat16 workaround |
|---|---|---|
| `asc_shfl_down` | `float`, `uint32_t` | Widen to float before shuffle, narrow after |
| `asc_shfl_xor` | `float`, `uint32_t` | Same as above |
| `asc_shfl_up` | `float`, `uint32_t` | Same as above |
| `asc_reduce_add` | `float`, `uint32_t` | Widen to float, reduce, narrow back |
| `asc_reduce_max` | `float`, `uint32_t` | Same as above |
| `asc_reduce_min` | `float`, `uint32_t` | Same as above |
| `asc_atomic_add` | **Not 32-bit-only.** Coverage is per-header and per-memspace — [Atomic add — dtype coverage](#atomic-dtypes) | None needed for availability: `half`/`bf16` have native overloads. Widen only when you need >16-bit accumulation precision |
| `asc_atomic_max` / `asc_atomic_min` | `int32_t`, `uint32_t` | For float: bitcast to `uint32_t` with sign-flip; for half/bf16: widen to float first |
| `asc_ballot` | `uint32_t` (result) | No dtype dependency — works with any data type |
| `__popc` | `uint32_t` | No dtype dependency |
| `laneid` / `lanemask_lt` | `uint32_t` | No dtype dependency |

---

## Widening Helper Patterns

Use these template wrappers to make warp operations dtype-agnostic.

> **Qualifier: `__simt_callee__`, not `__device__`.**
> A helper that calls a warp intrinsic must be marked `__simt_callee__`
> (`__attribute__((cce_simt_callable))`). `__device__` is **not** defined in
> either compiler dialect — it yields `error: unknown type name '__device__'`
> under both `-cce-enable-puresimt` and the default mode.
> An unqualified or `__aicore__`-qualified helper fails differently:
> `simt_callee function can only be called by simt_vf/simt_callee function`.
> `__simt_callee__` functions may only be called from a `__simt_vf__` or another
> `__simt_callee__`. Verified on CANN 9.1.0-beta.3 / `dav-3510`.

### Warp shuffle

```cpp
template <typename T>
__simt_callee__ inline T warp_shfl_down(T val, uint32_t delta) {
    float wide = static_cast<float>(val);
    wide = asc_shfl_down(wide, delta);
    return static_cast<T>(wide);
}

template <>
__simt_callee__ inline float warp_shfl_down<float>(float val, uint32_t delta) {
    return asc_shfl_down(val, delta);
}
```

### Warp reduce (sum)

```cpp
template <typename T>
__simt_callee__ inline T warp_reduce_sum(T val) {
    float wide = static_cast<float>(val);
    wide = asc_reduce_add(wide);   // native REDUX, broadcasts to all 32 lanes
    return static_cast<T>(wide);
}

template <>
__simt_callee__ inline float warp_reduce_sum<float>(float val) {
    return asc_reduce_add(val);
}
```

### Warp reduce (max)

```cpp
template <typename T>
__simt_callee__ inline T warp_reduce_max(T val) {
    float wide = static_cast<float>(val);
    wide = asc_reduce_max(wide);
    return static_cast<T>(wide);
}

template <>
__simt_callee__ inline float warp_reduce_max<float>(float val) {
    return asc_reduce_max(val);
}
```

<a id="atomic-dtypes"></a>
### Atomic add — dtype coverage

**This is the canonical statement of `asc_atomic_add` coverage.** Every other file in this skill
links here instead of restating the matrix. Change it here and the links follow; the previous
arrangement wrote the matrix out in five files and three of them contradicted each other.

| dtype | `__gm__` | `__ubuf__` | declared in |
|---|---|---|---|
| `int32_t`, `uint32_t`, `float` | yes | yes | `device_atomic_functions.h` |
| `int64_t`, `uint64_t` | yes | **no** | `device_atomic_functions.h` |
| `half`, `half2` | yes | yes | `simt_api/asc_fp16.h` |
| `bfloat16_t`, `bfloat16x2_t` | yes | yes | `simt_api/asc_bf16.h` |

Coverage is per-header and per-memspace, not uniform, and the header split is what earlier
revisions got wrong. Evidence level differs by row: `int32_t` is probe-verified and scalar `half`
is device-verified; the rest are header-declared, so treat them as declared rather than measured.

Two consequences to carry into kernel design. The absent `__ubuf__` 64-bit row constrains the
histogram pattern in [`simt_advanced_patterns.md`](simt_advanced_patterns.md) §1.12. And the
scalar 16-bit return value is not a fetch-add — see the trap below, which decides whether you may
use these as a cursor.

Other atomic ops do **not** share this matrix: `asc_atomic_max`/`min` are `int32_t`/`uint32_t`
only, and 16-bit min/max/compare-exchange has no native form at all — that is what the word-CAS
pattern further down is still for.
<!-- claim: atomic-add-dtypes · also in: ../ARCHITECTURE.md · find with: grep -rn "claim: atomic-add-dtypes" skills/simt-codegen · edit all sites together -->

> ⚠️ **Correction (2026-08-05). 16-bit atomics are native. Earlier revisions of this skill said
> they did not exist — that was wrong, and it sent operators down a word-CAS detour they never
> needed.** The overloads are real, and they are a hardware `atomicAdd`, not a library CAS loop:
>
> | Overload | Declared in | Impl |
> |---|---|---|
> | `asc_atomic_add(__gm__ half*, half)` | `simt_api/asc_fp16.h:295` | `asc_fp16_impl.h:858` → `atomicAdd` |
> | `asc_atomic_add(__ubuf__ half*, half)` | `asc_fp16.h:291` | `asc_fp16_impl.h:809` |
> | `asc_atomic_add(__gm__ half2*, half2)` | `asc_fp16.h:297` | `asc_fp16_impl.h:864` |
> | `asc_atomic_add(__gm__ bfloat16_t*, bfloat16_t)` | `simt_api/asc_bf16.h:303` | `asc_bf16_impl.h:884` |
> | + `__ubuf__` and `bfloat16x2_t` variants | `asc_bf16.h:301` | `asc_bf16_impl.h:835,890` |
>
> **Why we got it wrong:** they are *not* in `device_atomic_functions.h`, which is the only
> atomics header this skill used to point at. They live in the **dtype** headers. Include
> `simt_api/asc_fp16.h` (or `asc_bf16.h`) and the overload resolves.
>
> Device-verified: a 65536-element `int8`→`half[256]` histogram doing one native
> `asc_atomic_add(__gm__ half*, half)` per element is bit-exact against `np.bincount` and
> byte-identical across 3 runs at 1, 8, and 56 blocks. Its racy `+=` control loses 24–35% of
> updates, so contention was genuinely present. Compile gate on the pair above: `simt_=2`,
> `Kernel_Type=2`, zero `-Wunsequenced` diagnostics.

**One real trap in the scalar overload — the return value is not a fetch-add.** The vendor
implementation re-reads the location *after* the atomic, non-atomically:

```cpp
inline half asc_atomic_add(__gm__ half *address, half val) {
    atomicAdd(address, val);
    return *address;      // ← separate, non-atomic load; another thread may have added by now
}
```

So the scalar `half`/`bfloat16_t` overloads are safe when you **ignore the return value**
(accumulation: histogram, scatter-add, segment-sum) and **unsafe as a cursor/allocator**, where
you need the pre-add value to claim a unique slot. The `half2`/`bfloat16x2_t` overloads return
`atomicAdd`'s own result and do not have this defect. For a 16-bit cursor, use an `int32_t`
counter instead — see `simt_advanced_patterns.md` §1.13.

For `half` / `bfloat16_t`, in order of preference:

1. **Native 16-bit atomic** (above). Include the dtype header. This is the default now.
2. **Keep the accumulator wide.** Accumulate in `float`/`int32_t`, convert at I/O. Still the
   right call when precision matters — 16-bit accumulation over many hits loses mantissa.
3. **fp32 scratch** (below, "Non-Associative Accumulation"). Costs an extra output and 2×
   memory, needs a grid-wide barrier before the narrowing pass — `asc_syncthreads` is
   block-scoped and **not** sufficient.
4. **Word-CAS** (this section). Retained because it is correct and portable, and because it is
   the only route for a 16-bit *read-modify-write other than add* (min, max, compare-exchange
   on a packed pair). It is no longer the answer for plain accumulation.

Word-CAS is a CAS-loop on the aligned 32-bit word containing the 16-bit element:

> ⚠️ **DANGEROUS OLD PATTERN — DO NOT USE:**
> `asc_atomic_add(reinterpret_cast<__gm__ float*>(half_ptr), wide_val)` performs a
> **4-byte atomic on a 2-byte slot**, corrupting the adjacent element in memory. This
> was the root cause of scatter round 3 failure F5. Never cast `half*`/`bfloat16_t*`
> to `float*` near an `asc_atomic_*` call.

> ⚠️ **The CAS return value must land in a DIFFERENT variable than the one the loop
> condition compares.** Writing `while ((expected = asc_atomic_cas(p, expected, desired))
> != expected)` assigns and reads `expected` in one expression: the comparison is `x != x`,
> always false, so the body runs **exactly once** and a losing CAS is silently discarded —
> a lost update. It is also unsequenced modify-and-read (UB in C++17); bisheng diagnoses it
> as `warning: unsequenced modification and access to 'expected'`. **Treat that warning as
> fatal.** Measured on device (56 blocks × 256 threads, duplicate indices): the one-variable
> form loses **19198 of 24576** accumulated mass — worse than using no atomic at all, because
> a thread that loses the race deposits nothing instead of clobbering. At 1 block it degrades
> to 0.024% mean relative error and **passes** a `mean_rel < 1e-2` gate, so an aggregate
> metric on low-contention data will not catch it. See `Verifying an atomic` below.

```cpp
// Word-CAS: atomically update a half/bfloat16 element within its containing uint32 word.
// Works for any 16-bit type and any atomic op (add, min, max).
template <typename T>
__simt_callee__ inline void atomic_add_half(__gm__ T* addr, T val) {
    // 16-bit types only. Without this, the primary atomic_add_generic template below
    // routes any unlisted T here and the memcpy overreads sizeof(T) from a 2-byte source.
    static_assert(sizeof(T) == 2, "atomic_add_half is for 16-bit types only "
                                  "(half, bfloat16_t); use asc_atomic_add for 4/8-byte types");

    // Align to the containing 32-bit word
    uintptr_t byte_addr = reinterpret_cast<uintptr_t>(addr);
    __gm__ uint32_t* word_ptr = reinterpret_cast<__gm__ uint32_t*>(byte_addr & ~3ULL);
    uint32_t shift = (byte_addr & 2U) ? 16U : 0U;  // which half of the word
    uint32_t mask  = 0xFFFFU << shift;

    // `assumed` is what we believe the word holds. The non-atomic read is safe: it is only
    // a hint, and the CAS revalidates it. No volatile or fence is needed inside the loop.
    uint32_t assumed = *word_ptr;
    for (;;) {
        // Extract the 16-bit element, compute in float, pack back
        uint16_t old_bits = static_cast<uint16_t>((assumed >> shift) & 0xFFFFU);
        T old_val;
        __builtin_memcpy(&old_val, &old_bits, sizeof(T));
        T new_val = static_cast<T>(static_cast<float>(old_val) + static_cast<float>(val));
        uint16_t new_bits;
        __builtin_memcpy(&new_bits, &new_val, sizeof(T));
        uint32_t new_word = (assumed & ~mask) | (static_cast<uint32_t>(new_bits) << shift);

        // Separate variable for the return — this is what makes the retry work.
        uint32_t seen = asc_atomic_cas(word_ptr, assumed, new_word);
        if (seen == assumed) return;   // won: our value is in memory
        assumed = seen;                // lost: recompute against what is actually there
    }
    // No ABA hazard: new_word is a pure function of the observed word, so if the word
    // returns to a previously-seen value, recomputing from it is still correct.
}

// Primary template = the 16-bit path. Every type WITHOUT an explicit specialization below
// lands here, so the static_assert in atomic_add_half is what stops int64_t/uint64_t from
// silently taking a 16-bit CAS. Add a specialization per native-atomic dtype you need
// (asc_atomic_add covers int32/uint32/float/int64/uint64 per the header — see the table above).
template <typename T>
__simt_callee__ inline void atomic_add_generic(__gm__ T* addr, T val) {
    atomic_add_half(addr, val);  // half/bf16 path
}

template <>
__simt_callee__ inline void atomic_add_generic<float>(__gm__ float* addr, float val) {
    asc_atomic_add(addr, val);
}

template <>
__simt_callee__ inline void atomic_add_generic<int32_t>(__gm__ int32_t* addr, int32_t val) {
    asc_atomic_add(addr, val);
}
```

The same word-CAS pattern works for `atomic_min`/`atomic_max` on half/bf16 — replace the `+` with the appropriate comparison in the CAS loop body.

<a id="verifying-an-atomic"></a>
### Verifying an atomic (mandatory before you trust one)

A broken atomic produces plausible output, not garbage, so ordinary tolerance checks miss it.
Three cheap gates, in order of value:

1. **Run identical input 3× and compare the outputs bitwise — if the atomic is an accumulator.**
   A correct atomic *accumulation* over a commutative op with an exactly-representable result is
   deterministic for a fixed input and grid; run-to-run variation means lost or duplicated
   updates. This is the only detector that fires at *every* contention level — the broken loop
   above stays non-deterministic even at 1 block, where every error-magnitude gate passes it.

   **Do not apply this gate to a cursor.** When the atomic hands out slots (stream compaction,
   dynamic work queues) the output *order* legitimately varies run to run, and demanding
   bitwise reproducibility makes a correct kernel look broken. For a cursor, compare **sorted**
   outputs, assert the count exactly, assert no poison hole below the cursor, and assert nothing
   was written past it. For *float* accumulation, expect variation from summation order and
   compare against a tolerance derived from accumulation depth, not bitwise. Worked example and
   the measured intermittency in
   [`simt_advanced_patterns.md`](simt_advanced_patterns.md) §1.13.
   <!-- claim: atomic-3x-bitwise-rule · also in: simt_advanced_patterns.md · find with: grep -rn "claim: atomic-3x-bitwise-rule" skills/simt-codegen · edit all sites together -->
2. **Force contention.** Random indices over a large output barely collide. Point ~1/8 of your
   indices at a single hot bin, and check **per-element** against an independently-computed
   golden (`np.add.at`, not `torch.index_add_` — a different implementation of the same
   semantics, so the reference cannot share a bug with the kernel).
3. **Poison the output** to `0xFF` before launch and copy the poison H2D, so an element that
   was never written cannot read as a pass.

Compile with `-Wunsequenced` and treat it as an error. It catches the one-variable CAS bug at
compile time, for free.

> **Preferred approach**: When the operator uses atomics for accumulation (ScatterAdd,
> Histogram), keep the accumulator as `float` or `int32_t` and only convert I/O types.
> This avoids the CAS overhead entirely. See also "Non-associative accumulation" below.

---

## Non-Associative Accumulation — fp32 Scratch Pattern

Half and bfloat16 addition is **non-associative**: `(a + b) + c ≠ a + (b + c)` due to
per-step rounding. Parallel atomic accumulation rounds in a different order than sequential
CPU accumulation. At near-zero-sum cells, the relative error can exceed tolerance even though
the absolute error is tiny.

**Affected patterns:**
- `scatter_add` on fp16/bf16 with duplicate indices
- `segment_sum`, `segment_mean` on fp16/bf16
- `reduce_sum`/`reduce_mean` with per-warp atomics on fp16/bf16
- histogram with fractional weights on fp16/bf16

**Rule:** For half/bf16 reductions where accumulation order affects the result, accumulate
in **fp32 scratch** and narrow to half/bf16 once at the end. Do not per-step round in the
atomic.

```cpp
// Instead of: asc_atomic_add((__gm__ half*)output + idx, half_val);
// Use:        asc_atomic_add((__gm__ float*)fp32_scratch + idx, float(half_val));
//             ... after all threads complete ...
//             output[idx] = static_cast<half>(fp32_scratch[idx]);  // narrow once
```

The fp32 scratch buffer is registered as an **extra op output** (not workspace — error 334).
If a scratch tensor already exists (e.g., the `win` buffer from the 2-launch winner pattern),
reuse it as the fp32 accumulator to avoid adding another OpDef output.

**Status:** Confirmed on HW — fp32-accumulate fixed scatter round 3 cases 4 & 18
(fp16 `add` order-rounding), bringing scatter to 20/20.

---

## Sizeof-Dependent Constants

These constants change with `T`. Use `sizeof(T)` — never hardcode.

| Constant | Formula | float (4B) | half (2B) | int8 (1B) |
|---|---|---|---|---|
| UB 2D tile padding (elements) | `4 / sizeof(T)` | 1 | 2 | 4 |
| DataCopy alignment (elements) | `32 / sizeof(T)` | 8 | 16 | 32 |
| Coalescing width (elements) | `128 / sizeof(T)` | 32 | 64 | 128 |

```cpp
template <typename T>
struct DtypeTraits {
    static constexpr uint32_t TILE_PAD    = 4 / sizeof(T);
    static constexpr uint32_t ALIGN_ELEMS = 32 / sizeof(T);
    static constexpr uint32_t COALESCE_W  = 128 / sizeof(T);
};
```

For 2D transpose UB tiles:
```cpp
template <typename T>
constexpr uint32_t TILE_DIM = 32;
// Inner dimension padded to avoid bank conflicts
__ubuf__ T tile[TILE_DIM][TILE_DIM + DtypeTraits<T>::TILE_PAD];
```

---

## Template Instantiation

### Model A — Explicit instantiation

At the bottom of the `.asc` file, instantiate for each target dtype:

```cpp
template __global__ void my_kernel<float>(float*, int32_t*, float*, uint32_t);
template __global__ void my_kernel<half>(half*, int32_t*, half*, uint32_t);
template __global__ void my_kernel<bfloat16_t>(bfloat16_t*, int32_t*, bfloat16_t*, uint32_t);
```

### Model B/C — Dispatch via tiling dtype field

The entry function dispatches based on a dtype field passed through tiling data:

```cpp
__global__ __aicore__ void my_entry(__gm__ uint8_t* x, __gm__ uint8_t* idx,
                                     __gm__ uint8_t* y, __gm__ uint8_t* tiling_gm)
{
    // ... read tiling data ...
    uint32_t dtype_code = tilingData->dtypeCode;  // 0=float, 1=half, 2=bfloat16

    if (dtype_code == 0) {
        asc_vf_call(my_vf<float>,
            (__gm__ float*)x, (__gm__ int32_t*)idx, (__gm__ float*)y, total);
    } else if (dtype_code == 1) {
        asc_vf_call(my_vf<half>,
            (__gm__ half*)x, (__gm__ int32_t*)idx, (__gm__ half*)y, total);
    } else {
        asc_vf_call(my_vf<bfloat16_t>,
            (__gm__ bfloat16_t*)x, (__gm__ int32_t*)idx, (__gm__ bfloat16_t*)y, total);
    }
}
```

The tiling host code sets `dtypeCode` based on the input tensor's actual dtype at runtime.

---

## op_host Type Registration

Register all supported dtypes in the host-side operator definition:

```cpp
// In op_host/{op_name}_custom.cpp
ge::graphStatus InferShape(...) { /* ... */ }
ge::graphStatus InferDataType(...) {
    // Output dtype matches input dtype
    auto dt = op.GetInputDescByName("x")->GetDataType();
    op.GetOutputDescByName("y")->SetDataType(dt);
    return ge::GRAPH_SUCCESS;
}

// In the .AddInputDesc / .AddOutputDesc calls:
this->AddInputDesc("x")
    .AddType({ge::DT_FLOAT, ge::DT_FLOAT16, ge::DT_BF16});
this->AddOutputDesc("y")
    .AddType({ge::DT_FLOAT, ge::DT_FLOAT16, ge::DT_BF16});
```

---

## Includes

Include both fp16 and bf16 headers unconditionally — they are lightweight and avoid
conditional-include complexity:

```cpp
#include "simt_api/asc_simt.h"
#include "simt_api/asc_fp16.h"
#include "simt_api/asc_bf16.h"
```

If the operator also uses warp/sync/atomic APIs, add those includes as usual per §0.5
of the parent SKILL.md.

---

<a id="when-not-to-templatize"></a>
## When NOT to Templatize

| Case | Reason | What to do |
|---|---|---|
| **Index-only output** (NonZero, Sort indices) | Output is always `int32_t` | Templatize the input type `T` but keep output as `int32_t` |
| **Histogram / BinCount** | Output is always integer counts | Input type may vary; output stays `int32_t` |
| **Fixed accumulator** (ScatterAdd internal sum) | Accumulation precision requires float | Keep accumulator as `float`; templatize I/O only |
| **Single-dtype operator** | Op only makes sense for one dtype (e.g., int8 quantization) | Skip template, use concrete type |
