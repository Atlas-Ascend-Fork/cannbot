# SIMT Performance Characteristics — Ascend 950PR Reference

> Consolidated profiling data from three verified A950 hardware runs.
> Use this reference when selecting models, sizing grids, and interpreting msprof output.
> Source: three profiled runs on Ascend 950PR (gather Model B, gather pure-SIMT, gather+adds Model C), CANN 9.1.0-beta.3.

---

## Summary: Three Models Compared

| Metric | Model A (Pure SIMT) | Model B (SIMT VF) | Model C (SIMT+SIMD) |
|---|---|---|---|
| **Operator** | 2D gather (1023 cols) | 2D gather (128 cols) | 1D gather + adds |
| **Task duration** | 389.8 us | 72.1 us | 6.9 us |
| **Output size** | 48 MB | 6 MB | 32 KB |
| **us per MB output** | 8.1 | 12.0 | 213.4 (latency-bound) |
| **Effective write BW** | 123.1 GB/s | 83.2 GB/s | 4.6 GB/s |
| **SIMT VF ratio** | 99.9% | 99.4% | 90.0% |
| **SIMD VF ratio** | 0% | 0% | 0.6% |
| **Scalar ratio** | 0.2% | 0.5% | 5.8% |
| **MTE3 ratio** | 0% | 0% | 3.7% |
| **Blocks** | 56 | 48 | 8 |
| **Threads/block** | 220 | 256 | 1024 |
| **Total threads** | 12,320 | 12,288 | 8,192 |

**Caution**: Direct throughput comparison across models is misleading because the operators have different output sizes and access patterns. The "us per MB output" metric normalizes, but even that is affected by the specific operator and data layout.

---

## Pipe Utilization by Model

### Model A — Pure SIMT

```
SIMT VF:  ████████████████████████████████████████████████████ 99.9%
Scalar:   ░ 0.2%
MTE2/3:   · 0%
```

Highest SIMT utilization of all models. Minimal scalar overhead because the wider inner loop (1023 columns) amortizes per-row setup. No DMA engine usage — all memory access is per-thread scalar load/store.

### Model B — SIMT VF

```
SIMT VF:  ███████████████████████████████████████████████████ 99.4%
Scalar:   ░ 0.5%
MTE2/3:   · 0%
```

Slightly higher scalar overhead than Model A due to `asc_vf_call` dispatch overhead. Still overwhelmingly compute-bound. No DMA — direct GM writes per thread.

### Model C — SIMT + SIMD

```
SIMT VF:  ████████████████████████████████████████████████ 90.0%
SIMD VF:  · 0.6%
Scalar:   ███ 5.8%
MTE3:     ██ 3.7%
```

Lower SIMT ratio due to multi-stage kernel setup (UB allocation, sync flag ops, address calculations). The SIMD stage (Adds) is trivially fast at 0.6%. MTE3 (DataCopy) is 3.7% — bulk DMA for output.

---

## Key Performance Insights

### 1. SIMD Compute Is Essentially Free

From Model C profiling: the `__simd_vf__` Adds consumed only **0.6% of cycles** for a full vector-width addition across 1024 elements. This means:

- If an operator has ANY vectorizable arithmetic, offload it to `__simd_vf__` (Model C)
- Doing `output[i] = input[idx] + 1.0` per-thread in SIMT wastes the vector pipe
- The cost of Model C's extra complexity (UB staging, sync, DataCopy) is paid back as soon as the arithmetic is non-trivial

**Rule of thumb**: If the operator does more than just copy/permute data (i.e., any arithmetic), consider Model C.

### 2. MTE2 "Low Bandwidth" Warning Is a False Positive

msprof always flags: **"MTE2 bandwidth utilization lower than 80% when active"**

This is expected and benign for all SIMT kernels. SIMT threads do per-element scalar memory access through the vector pipeline, NOT through the MTE2 DMA engine. MTE2 is barely active because the data movement path is fundamentally different from traditional AscendC operators.

**Action**: Ignore this warning for SIMT operators.

### 3. MTE3 Wait Ratio Is the Sync Barrier Working

In Model C, `aiv_mte3_wait_ratio` averages **91.2%**. This is NOT a performance problem — it's the `SetFlag`/`WaitFlag` synchronization between the V pipe (SIMD) and MTE3 (DataCopy) working correctly. MTE3 must wait for SIMD to finish writing UB before it can copy to GM.

**If MTE3 wait ratio is near 0**: Something is wrong — the sync may be missing.

### 4. Block Load Imbalance Matters

Model A showed a **1.21x imbalance** between slowest and fastest blocks (389.3 us vs 322.4 us). The task duration is gated by the slowest block, so ~17% of the fastest block's time is wasted.

Causes:
- Uneven work distribution when `total_elements % blocks_per_grid != 0`
- Last block processes fewer threads but still occupies a full core
- Index patterns that cause different L2 cache hit rates per block

Mitigation:
- Use dynamic block count: `blocks = GetCoreNumAiv()` (56 on 950PR)
- If possible, pad total_elements to a multiple of blocks × threads
- For gather with known locality, sort indices to improve cache behavior

### 5. L2 Cache Behavior Varies by Access Pattern

| Model | Avg Read Hit Rate | Avg Write Hit Rate | Why |
|---|---|---|---|
| A (wide rows) | 27.5% | 97.4% | Large row width (4KB) strains L2 per fetch |
| B (narrow rows) | 73.0% | 97.5% | Smaller row width (512B) fits L2 better |
| C (1D random) | 53.8% | 81.3% | Small dataset but random access |

**Write hit rate** is consistently excellent (~97%) because output writes are sequential.

**Read hit rate** depends on:
- Input data size relative to L2 capacity
- Row width (larger rows = more L2 pressure per random access)
- Index locality (sorted indices → higher hit rates)

**For the generator**: Read cache behavior is an operator property, not something the generated code can control directly. But choosing grid size to maximize per-block data reuse can help.

---

## Thread and Block Limits

| Parameter | Model A | Model B/C | Notes |
|---|---|---|---|
| Max threads/block | 2048 | 1024 (typical) | `__launch_bounds__` / `dim3()` |
| Min threads/block | 1 | 1 | But should be multiple of 32 |
| Typical threads/block | 220–2048 | 256–1024 | |
| Max blocks | 65535 | core_count | Model B typically tied to physical cores |
| AIV cores (950PR) | 56 | 56 | `GetCoreNumAiv()` at runtime |
| Warp size | 32 | 32 | Fixed |

### Thread count must be a multiple of 32

Non-multiple thread counts create a partial warp. While this works functionally (excess threads hit bounds check and return), warp-level operations (`asc_shfl_*`, `asc_reduce_*`) may produce unexpected results for the partial warp.

### Grid sizing defaults

| Scenario | Blocks | Threads/block |
|---|---|---|
| Model B default | 56 | 256 |
| Model B large workload | 56 | 1024 |
| Model A default | 56 (dynamic) | ceil(total/56), capped at 2048 |
| Model C (UB bridge) | 8 | 1024 |

Model C uses fewer blocks with more threads because thread count = UB buffer elements. 1024 threads × 4 bytes = 4KB per buffer — manageable within 128KB DataCache.

---

## Memory Bandwidth Summary

| Metric | Model A | Model B | Model C | Unit |
|---|---|---|---|---|
| Main mem read BW | 1.7 | 6.3 | 19.1 | GB/s |
| Main mem write BW | 71.4 | 55.6 | 0.66 | GB/s |
| UB read BW | 170.5 | 222.8 | 43.9 | GB/s |
| UB write BW | 151.5 | 124.4 | 40.2 | GB/s |

**Model A's low main mem read BW** (1.7 GB/s) reflects excellent L2 cache absorption — the deterministic index pattern gives near-sequential reads despite being a "random" gather.

**Model C's low UB BW** reflects the small per-block dataset (4KB) — not enough data to saturate UB bandwidth. The absolute bandwidth numbers are data-volume-dependent, not a model property.

---

## Performance Optimization Checklist

When profiling a SIMT operator:

1. **Check SIMT VF ratio** — should be > 85%. If lower, look for excessive scalar overhead (complex setup, too many conditionals in VF)
2. **Check block time variance** — if max/min > 1.3x, consider dynamic block sizing or work redistribution
3. **Ignore MTE2 warning** — always fires for SIMT, always benign
4. **Check MTE3 wait** (Model C) — should be high (~90%). Near 0 = missing sync
5. **Check L2 read hit rate** — low hit rate on gather means index patterns aren't cache-friendly. Consider:
   - UB pre-staging if input fits in 8KB (VF-readable UB limit, see `memory_optimization_guide.md` §6)
   - Sorting indices if operator semantics allow it
   - Narrower data types (half instead of float) to reduce per-access footprint
6. **Consider Model C** if SIMD VF ratio is 0% but the operator has vectorizable arithmetic — you're leaving free compute on the table

---

## Per-Model Performance Profile

### When Model A is fastest
- Very wide rows (large inner dimension) → amortizes per-row overhead
- No cross-thread communication needed
- Template specialization for multiple dtypes

### When Model B is fastest
- Standard gather/scatter with moderate row width
- Needs warp functions (reduction, shuffle)
- Direct GM output is acceptable

### When Model C is fastest
- Small total dataset per block (fits 128KB UB)
- Mix of irregular access + regular arithmetic
- Contiguous output (DataCopy is more efficient than per-thread writes for contiguous data)

---

## Extended Performance Data (Jun 2026 Experiments)

### Expanded Summary Table

| Metric | SIMT VF (2D) | 1D SIMT Custom | 1D SIMD Custom | 1D SIMT 1M | 1D SIMD 1M | TopK serial | TopK warp-red | CumSum SIMT | SortSim bitonic | ScatterAdd atomic |
|---|---|---|---|---|---|---|---|---|---|---|
| Task Duration (us) | 72.125 | 11.791 | 49.627 | 132.517 | 1913.009 | 211.0 | 38.0 | 16.0 | — | — |
| Vec/SIMT VF ratio | 99.4% | 73.2% | 0.0% | 89.0% | 0.0% | 98.8% | 91.6% | 84.9% | 96.2% | 84.1% |
| Scalar ratio | 0.5% | 9.8% | 90.7% | 8.3% | 99.5% | 0.4% | 3.0% | 5.5% | — | 6.2% |
| ICache miss rate | ~0% | 23.5% | 1.1% | 0.4% | 0.015% | 9.8% | 12.1% | 23.5% | 0% | — |
| L2 read hit rate | ~73% | 85.1% | 87.5% | 98.3% | 98.3% | 6.5% | 12.0% | 14.3% | — | — |
| Main mem read BW (GB/s) | 6.3 | 0.21 | 0.041 | 1.41 | 0.075 | 0.009 | 0.052 | 0.019 | — | — |
| Main mem write BW (GB/s) | 55.6 | 0.006 | 0.001 | 0.042 | 0.0008 | 0.007 | 0.010 | 0.032 | — | — |
| Effective write BW (GB/s) | 83.2 | 4.1 | 0.97 | 31.7 | 2.09 | 0.002 | 0.010 | 250 | — | — |
| UB read BW (GB/s) | — | — | — | — | — | — | — | — | 6.6 | — |
| Index count | 12,288 | 12,288 | 12,288 | 1,048,576 | 1,048,576 | 7,680×K | 7,680×K | 1,048,576 | — | — |

**SortSim notes**: Bitonic sort using `__ubuf__` shared memory + `asc_shfl_xor`. 96.2% vec ratio is excellent — `asc_shfl_xor` compare-swap phases stay on the vector pipe. 0% ICache miss because the bitonic loop body is compact and hot. UB read BW 6.6 GB/s with zero bank conflicts (verified A950).

**ScatterAdd notes**: Per-thread `asc_atomic_add` pattern. 84.1% vec ratio with 6.2% scalar overhead from atomic coordination. The scalar overhead is inherent to `asc_atomic_add` — each atomic involves scalar-side address resolution before the vector-side RMW.

---

## Per-Thread Work Granularity

The 1D vs 2D gather experiments isolate the effect of per-thread work:

| | 2D Gather (reference) | 1D Gather (custom) |
|---|---|---|
| Per-thread work | 128 float copies (512 bytes) | 1 float copy (4 bytes) |
| Vec pipe ratio | 99.4% | 73.2% |
| Scalar ratio | 0.5% | 9.8% |
| ICache miss rate | ~0% | 23.5% |
| Unaccounted (stalls) | ~0% | ~17% |

**Root cause**: SIMT thread dispatch, bounds-check branches, and address calculation have a fixed per-thread cost. With 128 iterations per thread, this overhead is negligible. With 1 iteration, it becomes ~27% of wall time.

**Thresholds**:
- **≥128 bytes/thread**: overhead negligible (<1%)
- **≥32 bytes/thread**: overhead acceptable (<5%)
- **<16 bytes/thread**: >25% wasted on dispatch/scalar/icache

**Diagnostic**: ICache miss rate > 10% signals too little compute per thread. The fix is more work per thread, not larger code.

---

## SIMT vs SIMD Scaling

The traditional SIMD `GetValue`/`SetValue` gather is 4.2–14.4× slower than SIMT, and the gap **widens with scale**:

| Scale | SIMT duration | SIMD duration | SIMT advantage |
|---|---|---|---|
| 12K indices | 11.791 us | 49.627 us | **4.2×** |
| 1M indices | 132.517 us | 1,913.009 us | **14.4×** |

**Root cause of divergence**:
1. **SIMT amortizes fixed overhead**: ICache miss drops 23.5% → 0.4% at scale. Per-element cost drops 7.6× (0.96 → 0.126 ns/elem).
2. **SIMD's scalar bottleneck is absolute**: `GetValue`/`SetValue` processes one element per cycle per core. Scalar ratio actually increases at scale (90.7% → 99.5%).

**Implications**:
- Benchmark with ≥100K elements for representative SIMT throughput
- Small-scale tests understate SIMT advantage by ~7.6×
- Never use `GetValue`/`SetValue` loops for gather/scatter — they serialize on the scalar pipe

---

## Warp-Reduction Performance

The TopK experiment compares serial-merge (thread 0 scans 256 GM entries) vs warp-reduction (`asc_shfl_down` butterfly + 8 warp results):

| Config (4×8192) | Warp-reduction (us) | Serial-merge (us) | Speedup |
|---|---|---|---|
| K=1 | 16.0 | 33.5 | **2.1×** |
| K=10 | 38.0 | 210.7 | **5.5×** |
| K=100 | 245.4 | 1,973.0 | **8.0×** |

**Batch scaling is free**: 1→56 rows at same duration (each row on a separate core).

**K scaling**: Per-iteration cost is ~2.5 us (warp-reduction) vs ~20 us (serial-merge). Speedup grows with K because the merge phase dominated serial-merge runtime.

**Pipe utilization** (warp-reduction): 91.6% vec, 3.0% scalar (from `asc_shfl_down` lane coordination), 12.1% ICache miss.

---

## CumSum Performance

Per-column cumulative sum (256×4096 = 1M elements, 16 blocks):

| Metric | Value |
|---|---|
| Task Duration | 16.0 us |
| Vec ratio | 84.9% |
| Scalar ratio | 5.5% |
| ICache miss rate | 23.5% |
| L2 read hit rate | 14.3% |
| L2 write hit rate | 66.7% |

**Column-strided access kills L2**: stride = `inner_size` (4096) between consecutive reads per thread, so each access jumps 16 KB. Both read and write hit rates are low compared to gather patterns.

**ICache miss matches 1D Gather (23.5%)**: both are small kernels where cold icache dominates the first wave. This is a per-core fixed cost that amortizes at scale.

**Implication**: For axis-0 operations on row-major data with large `inner_size`, consider transpose-scan-transpose to improve cache behavior.
