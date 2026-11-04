# SIMT Codegen Skill — Architecture Reference

> Purpose: Give a complete picture of the SIMT feature implementation for future optimization planning.
> Last updated: 2026-06-25

---

## 1. What This Skill Does

`simt-codegen` generates compilable AscendC code that runs SIMT (Single Instruction Multiple Thread) execution on Huawei Ascend 950PR/950DT (A5) hardware. It takes a functional PyTorch operator definition and lowers it directly to AscendC `.asc` or `.cpp` files through a multi-pass transformation pipeline.

**Input**: `{op_name}_functional.py` + `op_desc.json` (+ optional evo grid config)
**Output**: Compilable `.asc` file at `output/{op_name}/{op_name}Custom/op_kernel/{op_name}.asc`

---

## 2. Position in the CAKE2 Pipeline

```
Stage 0:  Environment detection (CANN / Local / Remote)
Stage 1:  op_desc.json generation
Stage 2:  Reference PyTorch implementation
Stage 3:  Functional PyTorch conversion
Stage 4:  Tiling pre-classification
Stage 5:  Operator type detection ─────────────────────────────────┐
              │                                                     │
              ├── Vector? → Stages 6-10 (Vector path)              │
              ├── CV?     → Stages 6-10 (CV path)                  │
              └── SIMT?   → Stage 6 (msopgen) ───► simt-codegen ──┘
                                                        │
                                                   Stage 9: Code review
                                                   Stage 10: Evaluation
```

### Routing into SIMT

Stage 5 inspects `functional.py` for SIMT-candidate patterns (gather, scatter, sort, topk, histogram, etc.) and applies two filter questions:

- **Q1**: Does the operator have irregular/data-dependent memory access or control flow? (NO → Vector path)
- **Q2**: Is the input access pattern contiguous? (YES → Vector path; SIMD+mask is faster for contiguous scans)

Only operators that pass both filters enter `simt-codegen`. The full Q1–Q6 decision tree lives in [`SKILL.md` §0.1 SIMT Model Selection](SKILL.md) and is the single source for model choice — this document does not restate it.

---

## 3. Hardware Target

| Property | Value |
|---|---|
| Target SoC | Ascend 950PR / 950DT (A5) |
| Compiler arch flag | `--npu-arch=dav-3510` |
| AI Vector cores | 56 (AIV) |
| Warp size | 32 threads |
| Max threads/block | 2048 |
| Unified Buffer (UB) | 256 KB total; SIMT gets max 128 KB (DataCache partition) |
| CANN version | 9.1.0-beta.1 |

### SIMT Block Parameters (from `arch.yaml`)

| Property | Value | Source |
|---|---|---|
| SIMT cores per AIV | 2 | PEM:1050 |
| Max warps | 64 | PEM:1057 |
| Threads per warp | 32 | PEM:1058 |
| Issue width | 4 (instrs/cycle) | PEM:1059 |
| Total SIMT registers | 131,072 | PEM:1053 |
| SIMT predicate regs | 32 | PEM:1054 |
| Divergence stack depth | 16 | PEM:1132 |
| DCache line size | 128 bytes | PEM:1162 |
| DCache ways | 4 | PEM:1164 |
| UB read latency (SIMT) | 7 cycles | PEM:774 idx7 |
| UB write latency (SIMT) | 3 cycles | PEM:776 idx7 |

**Codegen implications**: The 16-level divergence stack limits nested divergent branches — deeply nested `if/else` chains must be restructured. The 131K register file gives ~64 regs/thread at max occupancy (2048 threads) — heavy register usage reduces occupancy. The 128B DCache line means 32 consecutive `float` accesses coalesce into one line fetch.

**Authoritative source**: [`references/ascend950pr_isa_probes/arch.yaml`](references/ascend950pr_isa_probes/arch.yaml) — banked hardware parameters with oracle citations (T1-cfg verified).

### SIMD Vector ISA Dtype Constraints (from `isa_matrix.md`)

For **Model C** kernels that use `__simd_vf__` (Micro API) or AscendC reductions in the entry function, the underlying SIMD vector ISA dtype support is load-bearing:

| Op | u8 | s8 | u16 | s16 | f16 | bf16 | u32 | s32 | f32 | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| vadd/vsub | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all 9 dtypes |
| vmul | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **no 8-bit** |
| vdiv | — | — | ✗ | ✗ | ✓ | — | ✗ | ✗ | ✓ | **float-only** |
| vcadd (ReduceSum) | ✗ | ✗ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **no s8/u8 on 3510** |
| vcmax/vcmin | ✗ | ✗ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **no s8/u8 on 3510** |
| vmadd (FMA) | — | — | — | — | ✓ | ✓ | — | — | ✓ | f16/bf16/f32 only |

**Authoritative source**: [`references/ascend950pr_isa_probes/isa_matrix.md`](references/ascend950pr_isa_probes/isa_matrix.md) — full per-op dtype grid with `:line` citations.

SIMT kernels compiled with `dav-3510` **cannot run on 910B** hardware (ISA mismatch). The `ascend950` SoC identifier in msopgen projects resolves natively via `opc`.

---

## 4. Three Programming Models

### Model A — Pure SIMT (`pure_simt`)

CUDA-like model. Single `__global__` kernel function, 4-arg launch syntax.

```
__global__ kernel(T* input, T* output, ...) {
    idx = blockIdx.x * blockDim.x + threadIdx.x;
    // Full SIMT API: warp, sync, atomics, __ubuf__, cache hints
}

kernel<<<blocks, threads, ubuf, stream>>>(...)  // 4-arg launch
```

- **Includes**: `acl/acl.h` + `simt_api/asc_simt.h` (NOT `kernel_operator.h`)
- **Requires**: `-cce-enable-puresimt` compiler flag
- **Advantages**: Templates, struct args, simpler code, CUDA-portable
- **Limitations**: No Micro API (LoadAlign, DataCopy, etc.), no `LocalTensor`, no `Pipe`
- **Verified SDK examples**: `simt_add/add.asc`, `histogram.asc`, `sobel_warp_shfl.asc`, `insert_hash_table.asc`, `matrix_transpose.asc`, `data_cache_hint.asc`

### Model B — SIMT VF Bridge (`simt_vf`)

Officially supported model. Entry function dispatches SIMT threads via `asc_vf_call`.

```
__simt_vf__ inline void simt_kernel(__gm__ T* input, ...) {
    // per-thread compute — warp/sync/atomic available here
}

__global__ __aicore__ void entry(GM_ADDR ...) {
    asc_vf_call<simt_kernel>(dim3(THREADS), ...);
}

entry<<<blocks, ubuf, stream>>>(...)  // 3-arg launch
```

- **Includes**: `kernel_operator.h` + `simt_api/asc_simt.h`
- **Constraints**: VF must be a free function; `asc_vf_call` args: only raw pointers + primitives; `__gm__` on all VF pointer params
- **Advantages**: Integrates with msopgen (tiling macros, `REGISTER_TILING_DEFAULT`)
- **Alternative API**: `Simt::` namespace (`Simt::VF_CALL`, `Simt::GetThreadIdx<0>()`) — equivalent, verified on A950

### Model C — Hybrid SIMT+SIMD (`hybrid_simd`)

Extends Model B with two VF functions for operators that have BOTH irregular access AND regular vectorizable compute.

```
__simt_vf__ inline void simt_gather(..., __ubuf__ T* ub_out, ...) {
    ub_out[threadIdx.x] = input[index[idx]];  // irregular → UB
}

__simd_vf__ inline void simd_adds(__ubuf__ T* out, __ubuf__ T* in, ...) {
    // Micro API: LoadAlign, Adds, StoreAlign
}

__global__ __aicore__ void entry(...) {
    asc_vf_call<simt_gather>(dim3(THREADS), ...);     // SIMT → UB
    asc_vf_call<simd_adds>(...);                       // SIMD on UB (no dim3)
    SetFlag<V_MTE3>(0); WaitFlag<V_MTE3>(0);          // sync
    DataCopy(gm_tensor, ub_tensor, count);             // UB → GM
}
```

- **Variant**: When fused compute has reductions (ReduceMax, ReduceSum), skip `__simd_vf__` entirely and do reductions in the `__aicore__` entry using AscendC APIs
- **Constraints**: UB data must fit in 128 KB; requires `dynUBufSize > 0` in launch

---

## 5. Multi-Pass Code Generation

### Pass Structure by Model

| Pass | Model A | Model B | Model C |
|---|---|---|---|
| 0 | Analysis + model selection | Analysis + model selection | Analysis + model selection |
| 1 | `kernel_pass` — `__global__` kernel | `vf_pass` — `__simt_vf__` function | `simt_vf_pass` — `__simt_vf__` (→ UB) |
| 2 | `host_pass` — ACL + 4-arg launch | `entry_pass` — `__global__` + `asc_vf_call` | `simd_vf_pass` — `__simd_vf__` (Micro API) |
| 3 | `main_pass` — test + verify | `host_pass` — ACL + 3-arg launch | `entry_pass` — orchestrate VFs + DataCopy |
| 4 | — | `main_pass` — test + verify | `host_pass` — ACL + 3-arg launch |
| 5 | — | — | `main_pass` — test + verify |

### Pass 0 — Analysis

Reads `functional.py` + `op_desc.json`. Produces:
1. **SIMT model selection** (Q1–Q6 decision tree)
2. **Grid/block configuration** (defaults: 56 blocks, 256 threads/block)
3. **Dtype-dependent includes** (half → `asc_fp16.h`, warp → `device_warp_functions.h`, etc.)
4. **Operator pattern mapping** to a per-thread compute template
5. **Performance hints** (coalescing, cache hints, UB padding, atomic strategy)

### Kernel Logic Passes

Each pass: generate code → compile → **inspect the artifact** → on failure: reference
check + retry (up to 3×). Exit 0 is not the success predicate — a device compile without
`--cce-aicore-only` exits 0 with zero device code emitted. See `references/simt_build_and_compile.md` Quick Reference.

The kernel logic passes (Pass 1 for A/B, Pass 1+2 for C) must produce a `codegen_reasoning.md` log documenting the derivation chain — which rules and references were used and how the code was adapted (anti-cheating measure).

### Host + Main Passes

- **Host pass**: ACL lifecycle (`aclInit` → device alloc → H2D copy → launch → sync → D2H copy → cleanup)
- **Main pass**: Test harness with deterministic data generation, CPU golden computation, and tolerance-based verification

---

## 6. Operator Pattern Catalog

| Pattern | Example Operators | Key APIs | Model | Lowering Example |
|---|---|---|---|---|
| Irregular Indexing | Scatter, axis-gather | thread ID math | A/B | `gather_1d/` |
| Per-element Indexing | `torch.gather` / GatherElements | coord decomposition, `index[idx]` | B | `torch_gather_20_20/` (20/20) — **not** axis-gather |
| Elementwise + Predicate | ReLU, Threshold | thread ID + condition | B | `gather_1d/` |
| Fused Gather+Elementwise | GatherRelu, GatherAdd | SIMT→UB + SIMD Maxs/Adds | **C** | `gather_and_adds/` |
| Masked Reduction | MaskedSoftmax | SIMT mask→UB + ReduceMax/Exp/Sum | **C variant** | `simt_operator_patterns.md` §Masked Reduction |
| Warp Reduction | ReduceSum, TopK, Argmax | `asc_reduce_add` + `asc_atomic_add` merge | B | `simt_operator_patterns.md` §Reduction |
| Axis-Parallel | CumSum, Prefix Scan | no sync, no warp | B | `simt_operator_patterns.md` |
| Atomic Scatter | ScatterAdd | `asc_atomic_add`, CAS emulation, multi-launch | A/B | `simt_operator_patterns.md` |
| Histogram / Binning | Histogram, BinCount | per-warp `__ubuf__` atomics + merge | **A** | `simt_operator_patterns.md` |
| 2D Transpose | Transpose, Permute | `__ubuf__` 2D tile + bank padding | B | `simt_operator_patterns.md` |
| Stream Compaction | NonZero (non-contiguous) | `asc_ballot` + `__popc` + leader atomic | A/B | `simt_operator_patterns.md` |
| Lock-Free Insert | Hash tables, Dedup | `asc_atomic_cas` + `asc_threadfence` | A | (SDK: `insert_hash_table.asc`) |

---

## 7. SIMT ISA — Available Intrinsics

All intrinsics are model-agnostic (available in all three models, inside the appropriate context).

### Thread Indexing
`blockIdx.x/y/z`, `threadIdx.x/y/z`, `blockDim.x/y/z`, `gridDim.x/y/z`, `warpSize`

### Warp Operations
| API | Latency | Notes |
|---|---|---|
| `asc_reduce_add/max/min(val)` | 16 cy (REDUX) | Result broadcasts to ALL 32 lanes |
| `asc_shfl_down/up/xor(var, delta)` | 17 cy (SHFL) | Edge lanes keep own value |
| `asc_shfl(var, srcLane, width)` | 17 cy | Broadcast from specific lane |
| `asc_ballot(pred)` | ~16 cy | Returns uint32_t mask |
| `asc_all/any(pred)` | ~16 cy | Whole-warp vote |
| `asc_activemask()` | ~16 cy | Mask of active lanes |
| `laneid()`, `lanemask_lt/eq()`, `__popc()` | 1 op | Lane utilities |

### Synchronization
| API | Use |
|---|---|
| `asc_syncthreads()` | Block-wide barrier |
| `asc_threadfence()` | Memory ordering (store visible to other threads) |
| `asc_threadfence_block()` | Block-scope memory ordering |

### Atomics (11 operations, dtype coverage varies per operation)
`asc_atomic_add/sub/max/min/and/or/xor/cas/inc/dec/exch` on `__ubuf__` or GM.

Coverage is **per-operation, per-memspace, and per-header** — there is no single dtype set that
applies to all eleven. `asc_atomic_add` is the widest (9 dtypes); `asc_atomic_max`/`min` are
int32/uint32 only. Two structural facts worth knowing before you design around atomics:
`__ubuf__` has **no 64-bit** support, and **16-bit atomics exist but are declared in the dtype
headers** (`asc_fp16.h`, `asc_bf16.h`) rather than `device_atomic_functions.h` — looking only in
the latter is what made earlier revisions of this skill claim 16-bit was unsupported.

Full matrix, evidence level per row, and the scalar-return trap:
[`references/simt_multi_dtype_guide.md` §Atomic add — dtype coverage](references/simt_multi_dtype_guide.md#atomic-dtypes).
<!-- claim: atomic-add-dtypes · also in: references/simt_multi_dtype_guide.md · find with: grep -rn "claim: atomic-add-dtypes" skills/simt-codegen · edit all sites together -->
GM atomic RTT: ~16.9k cycles (serializes under contention). Use per-warp dedup (ballot+popc → 1 atomic/warp) to reduce contention 32×.

### Memory
| API | Use |
|---|---|
| `__ubuf__` arrays | On-chip SRAM (128 KB max for SIMT) |
| `extern __ubuf__ char dynamicBuf[]` | Dynamic UB allocation |
| `asc_ldca(&addr)` | Load cached (keep in L1) |
| `asc_ldcg(&addr)` | Load streaming (bypass L1) |
| `asc_stcg(&addr, val)` | Store streaming (bypass L1) |
| `__ldg/__stg` + width variants | B8-B128 load/store (B128 = 2 ops) |

### Compute
| Op | Latency | Notes |
|---|---|---|
| IADD/FADD | 3 cy | |
| FMUL | 4 cy | |
| FFMA/IMAD | 7 cy | |
| F2I / I2F / F2F | 1 op | `__cvt_*<ROUND>()`, saturation forced, NaN→0 |
| BREV/POPC/PRMT/MULHI | 1 op | |
| `__ffs` | ~6 ops | Software expansion (prefer `__popc` + bit tricks) |

**ILP effect**: 8 independent FADD chains → issue interval drops from 3 cy/op to 1-2 cy/op. Most SIMT kernels are GM-latency-bound (LDG RTT ~173 cy, STG RTT ~255 cy), so compute is ~2% of body time for elementwise ops.

---

## 8. Memory Architecture

### UB Layout (SIMT on A5)

```
┌──────────────────────────────────┐
│  Static UB                       │
├──────────────────────────────────┤
│  Dynamic UB                      │
├──────────────────────────────────┤
│  Reserved (8 KB)                 │
├──────────────────────────────────┤
│  DataCache (32-128 KB)           │  ← SIMT threads access this
└──────────────────────────────────┘
```

- SIMT threads can only access the DataCache partition (max 128 KB, min 32 KB)
- SIMD (Vector) path uses full 248 KB UB
- Each AI Core has its own UB — UB is per-block private

### Memory Optimization Techniques

| Technique | When | Effect |
|---|---|---|
| **Coalescing** | Always | Consecutive `threadIdx.x` → consecutive addresses; strided → UB tiled approach |
| **Cache hints** | Mixed access patterns | `asc_ldca` for reused data, `asc_ldcg` for streaming, `asc_stcg` for write-once |
| **UB bank padding** | 2D `__ubuf__` arrays | `tile[32][33]` instead of `tile[32][32]` — eliminates bank conflicts |
| **Grid-stride loop** | Data > grid size | Fixed grid, amortizes UB init cost |
| **UB pre-staging** | Small input (≤128 KB) with random access | GM→UB bulk copy before SIMT; ~22% speedup on gather |
| **Per-warp atomics** | Atomic contention | ballot+popc → 1 atomic/warp (32× fewer). All-lane atomic = 24× wall time |

### VF Per-Thread Stack Limit (DCache Stack)

**CRITICAL**: Local variables declared inside a `__simt_vf__` function are allocated on the **DCache stack**. The AIV DCache is 32 KB total (PEM:418, 4-way, 128B lines — see `arch.yaml`), shared across all threads in a block. Per-thread stack budget:

| Threads/block | Per-thread stack (approx) |
|---|---|
| 256 | ~128 bytes |
| 128 | ~256 bytes |
| 64 | ~512 bytes |

Exceeding the per-thread stack triggers **error 354**: `"DCache access address exceeds the maximum range of the DCache stack MEM"`. This crashes all AI Cores regardless of input size.

**Rule**: Keep VF local variables under **~100 bytes/thread** (leave headroom for compiler spills). Any per-thread state larger than a few scalars must use GM scratch.

**Large per-thread state pattern** — when a VF thread needs arrays (sort buffers, accumulators, histograms > 100B):

```cpp
// BAD — stack overflow at 256 threads:
__simt_vf__ void kernel(...) {
    float scores[256];    // 1024 bytes on DCache stack → error 354
    int32_t indices[256]; // 1024 bytes
}

// GOOD — use GM scratch (tensor tail or dedicated scratch tensor):
__simt_vf__ void kernel(__gm__ float* output, uint32_t scratchOffset, ...) {
    uint32_t idx = asc_blockIdx_x() * asc_blockDim_x() + asc_threadIdx_x();
    __gm__ float* myScores = output + scratchOffset + idx * maxK;
    __gm__ int32_t* myIndices = ...;
    // GM access is slower (~100ns vs ~1ns) but L2 caching covers O(K²) insertion sort
}
```

**Alternatives** (in order of preference):
1. **GM scratch (tensor tail)**: Host tiling reserves space after output tensor. Works for any size.
2. **Recompute instead of store**: If data can be re-derived (e.g., partial sums), recompute rather than caching in a local array.
3. **Reduce thread count**: Drop to 64 threads → 512B/thread. Trades parallelism for stack space; last resort.

`__ubuf__` is NOT viable for per-thread arrays: 8 KB shared across 256 threads = 32 bytes/thread.

### Workspace Buffer Restriction

**CRITICAL**: The OPP workspace buffer (4th `GM_ADDR` parameter) is **NOT SIMT-writable**. Any write causes `error code 334: BIU→VEC data error`. Use tensor tails or dedicated scratch tensors instead. Always set `workspace[0] = 0` in TilingFunc.

### SIMT Runtime Error Quick Reference

| Error | Message | Root Cause | Fix |
|---|---|---|---|
| 334 | BIU→VEC data error | Write to OPP workspace from SIMT | Use tensor tail or scratch tensor |
| 354 | DCache stack overflow | VF local variables exceed per-thread stack | Move large arrays to GM scratch |

---

## 9. Performance Profile (A950 Hardware Measurements)

### Model Comparison

| Metric | Model A | Model B | Model C |
|---|---|---|---|
| SIMT VF pipe ratio | 99.9% | 99.4% | 90.0% |
| SIMD VF ratio | 0% | 0% | 0.6% |
| Scalar ratio | 0.2% | 0.5% | 5.8% |
| Write BW (effective) | 123.1 GB/s | 83.2 GB/s | 4.6 GB/s (latency-bound) |

### Per-Thread Work Granularity

| Bytes/thread | Overhead | VF ratio |
|---|---|---|
| ≥128 | <1% | ~99% |
| ≥32 | <5% | ~95% |
| <16 | >25% | ~73% |

**Diagnostic**: ICache miss rate > 10% signals too little compute per thread. The fix is more work per thread (loop-in-thread), not more threads.

### SIMT vs SIMD Scaling

| Scale | SIMT | SIMD (GetValue/SetValue) | SIMT advantage |
|---|---|---|---|
| 12K indices | 11.8 µs | 49.6 µs | **4.2×** |
| 1M indices | 132.5 µs | 1,913.0 µs | **14.4×** |

Gap widens with scale because SIMT amortizes fixed overhead while SIMD's scalar bottleneck is absolute.

### Warp Reduction Speedup (TopK)

| K | Warp-reduction | Serial-merge | Speedup |
|---|---|---|---|
| 1 | 16.0 µs | 33.5 µs | 2.1× |
| 10 | 38.0 µs | 210.7 µs | 5.5× |
| 100 | 245.4 µs | 1,973.0 µs | 8.0× |

### Key Performance Insights

1. **SIMD compute is essentially free** — `__simd_vf__` Adds consumed only 0.6% of cycles. If the operator has any vectorizable arithmetic, offload to Model C.
2. **MTE2 "low bandwidth" warning is a false positive** for all SIMT kernels — ignore it.
3. **MTE3 wait ratio ~90% is correct** (Model C) — it's the V→MTE3 sync barrier working.
4. **Block load imbalance** — 1.21× max/min observed. Use `GetCoreNumAiv()` for dynamic block count.
5. **Small N (≤4096)** — All ops measure ~419 cycles flat; launch overhead dominates. Don't micro-optimize; fuse kernels instead.

---

## 10. msopgen Integration

SIMT operators use the same msopgen project layout as Vector/CV operators. The adaptation is:

| Component | Action |
|---|---|
| `CMakeLists.txt`, `CMakePresets.json`, `build.sh` | Keep as-is |
| `op_kernel/{op_name}_custom_tiling.h` | Add grid/block fields (totalElements, blocksPerGrid, threadsPerBlock, dynUBufSize) |
| `op_kernel/{op_name}_custom.cpp` | Replace skeleton with SIMT VF + entry via tiling bridge |
| `op_host/{op_name}_custom.cpp` | Compute grid/block config in TilingFunc; set `workspace[0] = 0` |

Key findings (verified on A950, 2026-06-10):
- `.cpp` extension works for SIMT features — no need to rename to `.asc`
- `__aicore__` entry works with `asc_vf_call` — supports `REGISTER_TILING_DEFAULT`
- `ascend950` SoC resolves natively via `opc` in msopgen projects

---

## 11. Verified Lowering Examples

All verified on A950 hardware with correctness PASSED:

| Example | Model | Pattern | Speedup vs baseline |
|---|---|---|---|
| Gather1D | A | Pure SIMT gather | — |
| Gather Hybrid | B | SIMT VF gather | — |
| CumSum | B | Axis-parallel (no sync) | — |
| TopK | B | Warp reduction + sync | 5.5–8× vs serial |
| Gather+Adds | C | SIMT→UB→SIMD→DMA | — |
| GatherRelu | B | Pure SIMT gather+ReLU | — |
| GatherReluHybrid | C | SIMT→UB→SIMD→DMA | 1.78× vs built-in |
| MaskedSoftmax | C variant | SIMT mask + entry reductions | 1.02× |
| Histogram | A | Per-warp UB atomics | 1.29× vs built-in |
| Stream Compaction | A | ballot+popc compact write | — |
| Transpose | B | UB tile + bank padding | 1.05× |
| ScatterAdd | A/B | Atomic dedup patterns | — |

---

## 12. Common Failure Modes

### Compile-Time

| Error | Cause | Fix |
|---|---|---|
| `Unsupported NPU architecture` | Wrong `--npu-arch` | Use `dav-3510` |
| `requires __aicore__ qualifier` | Model A without `-cce-enable-puresimt` | Add the flag |
| `asc_vf_call target not a function` | VF is a class member | Extract to free function |
| `asc_vf_call forward reference` | VF defined after entry | Move VF above entry |
| Launch arity mismatch | 3-arg vs 4-arg confusion | Model A: 4-arg; Model B/C: 3-arg |

### Runtime

| Symptom | Cause | Fix |
|---|---|---|
| `error 334: BIU→VEC data error` | SIMT write to OPP workspace | Use tensor tails; `workspace[0] = 0` |
| Block 0 correct, others garbage | UB indexed with global ID | Use `threadIdx.x` for `__ubuf__` |
| Stale/zeroed output (Model C) | Missing V→MTE3 sync | Add `SetFlag`/`WaitFlag` before DataCopy |
| Random garbage from UB | Missing MTE2→V sync | Add `asc_sync_notify`/`wait` after `asc_copy_gm2ub_align` |
| Illegal instruction on 910B | `dav-3510` binary on wrong hardware | A950 hardware required |

---

## 13. File Organization

```
skills/simt-codegen/
├── SKILL.md                                   # Main skill definition (all passes, rules, decision trees)
├── ARCHITECTURE.md                            # This file
└── references/
    ├── simt_platform_reference.md             # Simt:: API mapping, UB layout, thread hierarchy, HW-verified APIs, ISA intrinsics + cost model
    ├── simt_operator_patterns.md              # Per-thread compute templates for each pattern
    ├── simt_perf_annotations.md               # Advisory hints for code generation
    ├── simt_perf_reference.md                 # A950 profiling data, model comparison
    ├── simt_warp_ops.md                       # Warp reduction, shuffle, vote patterns
    ├── simt_memory_ops.md                     # GM scratch, 2D grid config (cache hints/UB/bank conflicts moved to memory_optimization_guide.md)
    ├── simt_advanced_patterns.md              # Iterative algorithm, stream compaction, CAS, histogram
    ├── simt_multi_dtype_guide.md              # Templated kernels, widening helpers, instantiation
    ├── simt_debug_patterns.md                 # Runtime failure diagnosis
    ├── memory_optimization_guide.md           # Coalescing, cache hints, UB bank conflicts, grid-stride, UB pre-staging
    ├── msopgen_adaptation.md                  # msopgen project adaptation for SIMT
    ├── pass_details_model_a.md                # Model A pass-by-pass instructions
    ├── pass_details_model_b.md                # Model B pass-by-pass instructions
    ├── pass_details_model_c.md                # Model C pass-by-pass instructions
    ├── ascend950pr_isa_probes/                 # T1-sim verified ISA behavior (9 probes) + hardware params
    │   ├── arch.yaml                          # Banked dav-3510 hardware params (T1-cfg verified)
    │   ├── isa_matrix.md                      # SIMD vector ISA dtype support grid (T2 verified)
    │   ├── simt.elementwise.binary.md
    │   ├── simt.reduce.warp-sum.md
    │   ├── simt.shuffle.md
    │   ├── simt.vote.md
    │   ├── simt.sync.md
    │   ├── simt.ldst.global.md
    │   ├── simt.cast.fp-int.md
    │   ├── simt.arith.bit.md
    │   └── simt.atomic.rmw.md
    └── operator_examples/                     # structural templates + variant disambiguation
        ├── torch_gather_20_20/    # Model B template (20/20 cannbench; torch.gather semantics)
        ├── axis_gather_example/   # axis-gather (np.take/tf.gather/ONNX Gather), compile-verified
        ├── gather_1d/             # Model A template (pure SIMT)
        └── gather_and_adds/       # Model C template (SIMT+SIMD hybrid)
```

---

## 14. Known Limitations & Open Questions

### Verified Limitations
- **No dynamic parallelism** — SIMT within SIMT is not supported
- **No inter-block communication** — blocks are independent; only intra-block sync (`asc_syncthreads`)
- **128 KB UB ceiling** — SIMT DataCache is at most half of 256 KB UB
- **OPP workspace is not SIMT-writable** — always error 334
- **`torch_npu` doesn't support A950** — must use standalone C++ test binaries
- **Warp functions in A5 simulator timeout** — biases cake-evo against warp variants (known gap, see memory `simt-evo-sim-gap.md`)

### Constraints
- `__simd_vf__` cannot compile reductions (ReduceMax, ReduceSum). Reductions must go in the `__aicore__` entry function.
- `asc_shfl_up`, `asc_reduce_add/max/min`, `asc_all`, `asc_any`, `asc_activemask` — documented with cycle counts from T1-sim ISA probes; `asc_reduce_add` is used in the ReduceSum operator example

### Optimization Opportunities (for future discussion)
- **Kernel fusion** for small-N operators (launch overhead dominates at N ≤ 4096)
- **cake-evo SIMT integration** — grid/block tuning (G-S1 through G-S5 variants)
- **Transpose-scan-transpose** for axis-0 ops on row-major data with large inner_size (L2 read hit rate drops to ~14% with column-strided access)
- **B128 wide loads** for contiguous bandwidth-bound operators
- **ILP tuning** — loop unrolling factor selection based on register pressure
- **Model C expansion** — more operators could benefit from SIMT→SIMD offload (SIMD compute is essentially free at 0.6% of cycles)
