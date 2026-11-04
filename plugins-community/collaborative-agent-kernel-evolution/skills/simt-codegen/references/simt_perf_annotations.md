# SIMT Performance Optimization Annotations

> **Applies to**: All SIMT models (A, B, C). These hints guide `simt-codegen` toward efficient code generation. They are advisory — the codegen pass decides exact implementation.
> **Back to**: [`../SKILL.md`](../SKILL.md)

---

### Memory Coalescing

Consecutive `threadIdx.x` values must access consecutive memory addresses for optimal bandwidth.

```python
# GOOD — coalesced: thread i reads address base + i
# SIMT_VF_BODY:
#   idx = blockIdx.x * blockDim.x + threadIdx.x
#   output[idx] = input[idx]

# BAD — strided: thread i reads address base + i * stride
# SIMT_VF_BODY:
#   col = threadIdx.x
#   output[col * height + row] = input[col * height + row]  # column-major stride
```

**When to annotate**: If the access pattern is inherently strided (column access on row-major data, transpose), add:
```python
# SIMT_PERF: non_coalesced_access=true, suggest_ub_tiling=true
```
This tells the lowering stage to consider a `__ubuf__` tiled approach (load coalesced -> transpose in UB -> write coalesced).

### Cache Hint Annotations

Annotate data access patterns so the lowering stage can insert `asc_ldca/ldcg/stcg`:

```python
# SIMT_PERF: cache_hint=streaming        # input read once -> asc_ldcg()
# SIMT_PERF: cache_hint=cached           # lookup table / reused data -> asc_ldca()
# SIMT_PERF: cache_hint=store_streaming   # output written once -> asc_stcg()
```

| Data pattern | Annotation | Lowering uses |
|---|---|---|
| Lookup table, embedding weights, sin/cos table | `cache_hint=cached` | `asc_ldca()` |
| Input data read exactly once per kernel | `cache_hint=streaming` | `asc_ldcg()` |
| Output data written once, no read-back | `cache_hint=store_streaming` | `asc_stcg()` |
| Uncertain or mixed access | (omit annotation) | Plain load/store |

### `__launch_bounds__` Tuning

Default is `__launch_bounds__(256)`. Annotate when the operator characteristics suggest a different value:

```python
# SIMT_THREADS: 128   # register-heavy math (trig, complex FP) — more registers/thread
# SIMT_THREADS: 256   # default — good general purpose
# SIMT_THREADS: 512   # memory-bandwidth-bound — more threads hide latency
# SIMT_THREADS: 1024  # maximum parallelism, simple kernels (element-wise)
```

| Thread count | Best for | Tradeoff |
|---|---|---|
| 128 | Register-heavy math (trig, complex FP) | More registers/thread, fewer concurrent threads |
| 256 | Default — good general purpose | Balanced |
| 512-1024 | Memory-bandwidth-bound ops | More threads hide memory latency |
| 2048 | Maximum parallelism, trivially simple kernels | Minimum registers/thread |

### UB Bank Conflict Avoidance

When annotating patterns that use `__ubuf__` 2D arrays for inter-thread data sharing (transpose, histogram merge, tiled reductions):

```python
# SIMT_PERF: ubuf_2d_padding=true   # add +1 padding to inner dimension
```

This tells the lowering stage to declare `__ubuf__ float tile[32][32+1]` instead of `__ubuf__ float tile[32][32]`, eliminating bank conflicts when rows are read by different threads than wrote them.

### Atomic Contention Reduction

For patterns that need global atomics (stream compaction, histogram, scatter-add), annotate to prefer per-warp aggregation:

```python
# SIMT_PERF: atomic_strategy=per_warp   # ballot+popc -> 1 atomic per warp (up to 32x fewer)
# SIMT_PERF: atomic_strategy=per_thread  # simple per-thread atomic (OK for low contention)
```

**Measured contention cost** (Ascend950PR T1-sim): All-lane atomic (the bug) = **24x wall time** + **32x overcount** vs leader-only. Atomic GM RTT = ~16.9k cycles, serializing under contention. Always use `per_warp` unless contention is provably near-zero.

### ISA Cost-Aware Annotations (from Ascend950PR probes)

When the op pattern allows a choice, annotate the cheaper path based on measured ISA costs:

```python
# SIMT_PERF: reduce_method=native_redux    # 16 cy (single REDUX instruction)
# SIMT_PERF: reduce_method=butterfly_shfl  # 85 cy (5 x 17 cy SHFL steps) — only when argmax needed
```

**Key cost facts for annotation decisions** (from `ascend950pr_isa_probes/`):
- Native warp reduce (`asc_reduce_add`) = 16 cy vs butterfly = 85 cy -> **5.3x faster**, and result broadcasts to ALL lanes
- `__ffs` = ~6 ops (POPC-based expansion) — avoid in hot loops; prefer `__popc` + bit tricks
- 64-bit `__clz`/`__ffs` diverge the warp — prefer 32-bit variants
- Body is GM-latency-bound: `LDG RTT ~173 cy`, `STG RTT ~255 cy`, `FADD = 3 cy` -> compute is ~2% of body time

### ILP (Instruction-Level Parallelism) Annotations

When the per-thread body has independent computation chains, annotate for manual unrolling:

```python
# SIMT_PERF: ilp_factor=4   # unroll loop body 4x for independent compute chains
```

**Measured effect** (Ascend950PR): 8 independent FADD chains -> issue interval drops from 3 cy/op to 1-2 cy/op (1.5-3x throughput). Only benefits compute-bound kernels — most SIMT kernels are GM-latency-bound and won't see a difference.

### Load/Store Width Annotations

For bandwidth-bound ops, wider loads amortize instruction overhead per byte:

```python
# SIMT_PERF: load_width=b128   # use int4 (128-bit) loads — halves instruction count per byte
# SIMT_PERF: load_width=b32    # default — 1 LDG/STG per element
```

**Warning: B128 hazard**: `int4` types lower to 2 LDG + 2 STG ops per element (not 1). Still halves instruction count per byte vs B32 for contiguous data. Only beneficial for contiguous, aligned, bandwidth-bound access patterns.

### Small-N Kernel Fusion Annotation

All Ascend950PR probes measure ~419 cycles flat at N <= 4096 — launch overhead dominates. For small-N operators:

```python
# SIMT_PERF: small_n_fusion=true   # N <= 10^3: launch overhead dominates, consider kernel fusion
```

This tells the lowering stage (or future optimizer) that micro-optimizing this kernel body is pointless — the win is in eliminating the launch by fusing with adjacent kernels.
