# SIMT Operator Patterns — Baseline DSL Templates

> **Applies to**: All SIMT models (A, B, C). Each pattern shows the per-thread compute pseudo-code that `simt-codegen` lowers into compilable AscendC.
> **Back to**: [`../SKILL.md`](../SKILL.md)

---

### Irregular Indexing — `torch.gather` vs `index_select` (COMMON, SILENT BUG)

These look alike but index DIFFERENTLY. A wrong choice **compiles and runs, with wrong values** — no
static check catches it, so match the reference exactly:

- **`torch.gather(x, dim, index)`** — `index` shape **== output shape**; **one index per output
  element**: `out[c0,…,c_{n-1}] = x[…, index[c0…c_{n-1}] at position dim, …]`. Read **`index[idx]`**
  (idx = linear output position).
- **`torch.index_select(x, dim, index)`** — `index` is **1-D** (length = output size along dim); **one
  index per slice**: read `index[coord_along_dim]`.

⚠️ Reading a per-row index for gather (`index[idx / innerSize]`) silently implements **index_select**
— this was the original gather bug (only element 0 matched).

**General N-D gather (any dim, per-element index) — coord decomposition.**
Needs `outputShape[ndim]`, `inputStrides[ndim]`, `dim` in tiling (inline arrays → `__gm__` globals;
see `msopgen_adaptation.md` Step 2c):
```python
# SIMT_VF_BODY:
#   idx = blockIdx.x*blockDim.x + threadIdx.x
#   if idx >= totalElements: return
#   rem = idx                                  # decompose idx -> output coords (== index shape)
#   for d in range(ndim-1, -1, -1): coords[d] = rem % outputShape[d]; rem //= outputShape[d]
#   iv = index[idx]                            # PER-ELEMENT index (not index[row])
#   off = 0
#   for d in range(ndim): off += (iv if d == dim else coords[d]) * inputStrides[d]
#   output[idx] = input[off]
```
The 1-D `output[i] = input[index[i]]` form is only the dim=0/inner=1 special case. **The same
coord-decomposition drives transpose (perm-substituted coords) and general-dim scatter** — prefer it
over hardcoded `row/col` math, which only handles one fixed dim.

**Validated: gather round_2 flaky ~2–4/10 → 20/20, 58.50/100 on benchsite.**
**Validated: transpose round_2 all-zero/crash → 20/20, 53.23/100 on benchsite.**

Both ops hit the same two extra bugs beyond scatter:
- **X1**: mutable `__gm__` globals for per-launch metadata → cross-core race (stale/zero shape arrays).
  Fix: pass immutable `__gm__ const TilingData*` to VF (SKILL.md rule 12).
- **X2**: `dim3(totalBlocks)` passed as thread count → 507035 crash at scale.
  Fix: `dim3(threadsPerBlock)`, grid via `SetBlockDim(numBlocks)` with cap (SKILL.md rule 11).

**Scatter (write-mirror of gather).**
⚠️ **Output-ownership (SKILL.md rule 13):** `out` = a full copy of `data` with updates applied at the
scattered positions, so **every un-scattered output element must equal `data`**. The kernel MUST write
every output position — the wrapper hands an uninitialized (`empty`) buffer. **Do NOT put `data.clone()`
or `torch.zeros_like()` in the wrapper** (strict wrapper rule).

**How to achieve full output coverage** (pick one):
- **Two-launch kernel** (recommended for scatter): Launch 1 = grid-stride memcpy (`output[i] = data[i]`
  for all `i`), Launch 2 = scatter VF. Stream ordering guarantees Launch 1 completes before Launch 2.
  Use a `phase` tiling attr to dispatch from one OpDef. Avoids the cross-core VF hazard (rule 7) because
  each launch is a separate stream-ordered kernel.
- **Fused per-position select** (when the output domain is enumerable): iterate the *output* domain, not
  the updates domain — `out[i] = is_target(i) ? compute(i) : data[i]`. Works for `masked_fill`, `where`.
- `scatter_add`/segment-sum: base = **zeros** via kernel-side grid-stride zero-fill (Launch 1), then
  atomic scatter (Launch 2). Or fuse: `out[i] = 0` for all `i` then atomic-add in a single VF
  (safe with `SetBlockDim(1)` or when zero-fill and scatter ranges are partitioned across cores).

**Why NOT an in-kernel copy VF:** `asc_vf_call` is per-core synchronous only (rule 7). With
`SetBlockDim > 1`, a copy VF on core A and the scatter VF on core B have **no cross-core ordering** —
the copy can land after the scatter, reverting ~15% of cells nondeterministically. `SyncAll<true>()`
does NOT fix this (verified on A5). The two-launch pattern avoids this because stream ordering
serializes the launches.

The sparse-write part — the index picks the OUTPUT offset:
```python
# SIMT_VF_BODY (tiling: indicesShape[ndim], dataStrides[ndim], dataShape[ndim], dim):
#   tid = blockIdx.x*blockDim.x + threadIdx.x
#   if tid >= totalUpdates: return
#   rem = tid                                    # decompose over the INDEX/UPDATES shape
#   for d in range(ndim-1,-1,-1): coords[d] = rem % indicesShape[d]; rem //= indicesShape[d]
#   iv = index[tid]
#   if iv < 0: iv += dataShape[dim]
#   if iv < 0 or iv >= dataShape[dim]: return    # bounds-guard → no OOB write / device crash
#   off = 0
#   for d in range(ndim): off += (iv if d==dim else coords[d]) * dataStrides[d]
#   output[off] = updates[tid]                   # SPARSE write only; base (out=data) established separately
```
⚠️ **NEVER hardcode `dim==0` when the op declares a `dim`/`axis` attr.** A `scatter_idx*inner_size+col`
addressing only works for dim=0 and does an out-of-bounds write for dim≠0 → device error 507035
(round_2 scatter crashed on the dim=1 cases). Read `dim` from tiling and use the general offset above.

**Validated: scatter 1/20 → 18/20 on benchsite.** Use `operator_examples/torch_gather_20_20/` as the Model B structural template; adapt the multi-launch phase dispatch and atomic reduce logic from the pattern above.

| # | Failure | Fix | General lesson |
|---|---|---|---|
| F1 | OpDef dtype lists were diagonal (5 entries) — 9 cases rejected EZ1001 | Full 10-combo cross-product (5 data × 2 index dtypes) | OpDef `.DataType()` = positional tuples, not sets. Mixed-type ops need the cross-product. |
| F2 | Wrapper and kernel had swapped amax/amin enum values | Single encoding table in tiling header | One source of truth for mode enums. |
| F3 | In-kernel copy VF had cross-core race (~15% cells reverted) | Two-launch kernel: Launch 1 = memcpy, Launch 2 = scatter (stream ordering serializes). Wrapper `data.clone()` was a prior workaround, now banned (strict wrapper rule, SKILL.md rule 13). | `asc_vf_call` is per-core sync only. No cross-core VF barrier. SyncAll does NOT work. |
| F4 | `numBlocks` reached ~10^5 → vector-core crash 507035 | Cap `numBlocks` at 32768 + grid-stride in every VF | Data-driven element counts need grid-stride + cap. |
| F5 | `else { out = update_val; }` fallbacks for unimplemented reduce modes | CAS loops for multiply; word-CAS for half/bf16 atomics — **the half/bf16 half of this fix was unnecessary**, see note below | No silent wrong-answer fallbacks. Implement or drop the registration. |
| F7 | Dup-index `reduce=none` left arbitrary winner (10 cases) | 2-launch winner scheme: `atomic_max(&win, tid+1)` then apply | Deterministic cross-core ordering needs two stream-ordered launches + scratch tensor. |
| F9 | Local proxy computed golden on NPU (nondeterministic reference) | CPU fp64 golden | Eval golden = CPU fp64, never the device under test. |
| F11 | Stale aclnn stub (1-output) vs updated OpDef (2-output) → 0/20 | Regenerate stub from build_out | On any OpDef I/O change, regenerate the aclnn stub. |

Cases 4 & 18 (fp16 `add` order-rounding) fixed with fp32-accumulate + final narrow → **20/20**.

> **Note on F5 (2026-08-05).** The word-CAS half of that fix was built on a false premise: it was
> written because this skill said `asc_atomic_add` had no 16-bit overloads. It does — they live in
> `asc_fp16.h`/`asc_bf16.h`, not `device_atomic_functions.h`. The F5 row is left as the historical
> record of what shipped, not as a recommendation. For new work, use the native overload
> ([dtype coverage](simt_multi_dtype_guide.md#atomic-dtypes)); word-CAS is now only for 16-bit
> min/max/compare-exchange, which still have no native form. The CAS-loop *rule* the row teaches
> (no silent wrong-answer fallbacks) is unaffected.

### Deterministic Cross-Core Ordering (2-Launch Winner)

When multiple SIMT threads across cores write to the same output cell and the result must
be deterministic (specific winner, not arbitrary), a single parallel pass leaves a
nondeterministic winner. Since SIMT has no cross-core barrier (SKILL.md rule 7), the
solution is **two stream-ordered kernel launches** with a scratch tensor:

**Launch 1 — Resolve:** Determine the winner per output cell. Each thread writes its candidacy:
```python
# SIMT_VF_BODY (phase == 0, tiling: totalUpdates, indexShape, dataStrides, dim):
#   for tid in grid_stride(totalUpdates):
#       out_idx = compute_output_offset(tid, indices, dim, indexShape, dataStrides)
#       asc_atomic_max(&scratch[out_idx], tid + 1)   # highest-tid wins; +1 so 0 = "no writer"
```

**Launch 2 — Apply:** Iterate the **output domain** (not source elements), write the winner's value:
```python
# SIMT_VF_BODY (phase == 1, tiling: totalOutputElements):
#   for p in grid_stride(totalOutputElements):
#       winner = scratch[p]
#       if winner > 0:
#           output[p] = source[winner - 1]
```

**Key design rule:** Launch 2 iterates output cells → needs only 3 GM pointers
`(scratch, source, output)` → stays within `asc_vf_call`'s limit. Iterating the source
domain would also need `indices` → 4 pointers → violates the limit.

**Infrastructure:**
- Scratch tensor registered as **extra op output** (not workspace → error 334). See
  `msopgen_adaptation.md` "Adding a Scratch Tensor as Extra Op Output."
- Phase controlled by an integer attr value. Wrapper issues two `EXEC_NPU_CMD` calls
  with different phase values — stream ordering serializes them.
- For half/bf16 `reduce=add`: use fp32 scratch as accumulator (see
  `simt_multi_dtype_guide.md` "Non-Associative Accumulation").

**Affected op families:** scatter (`reduce=none` with dup indices), unique (first-occurrence),
sort_by_key (stable ordering), argsort, segment reductions with deterministic accumulation,
any "compact + dedup" with a defined tie-break.

### Element-wise with Predicate (ReLU, Threshold)

```python
# Pattern: output[i] = input[i] if condition else alt
# SIMT_VF_BODY:
#   idx = blockIdx.x * blockDim.x + threadIdx.x
#   if idx >= total_length: return
#   val = input[idx]
#   output[idx] = (val > threshold) ? val : 0
```

### Cross-Thread Communication with GM Scratch

For operators requiring inter-thread data exchange (topk, histogram, dedup), use `asc_syncthreads()` with GM scratch buffers. Verified working on A950.

```python
# Pattern: all threads write partial results, thread 0 merges
# SIMT_VF_BODY:
#   scratch[threadIdx.x] = my_value
#   asc_syncthreads()
#   if threadIdx.x == 0:
#       for t in range(THREAD_COUNT):
#           result = merge(result, scratch[t])
#   asc_syncthreads()  # before next iteration
```

**Scratch buffer rules**:
- Must be a regular GM tensor (aclrtMalloc'd) or reserved tail of an input tensor
- **NEVER use OPP workspace buffer** — causes BIU error 334 (see Restrictions)
- UB (`__ubuf__`) is per-block private — use threadIdx.x for UB indexing, not global idx
- Annotate: `SIMT_INCLUDE: simt_api/device_sync_functions.h`

### Independent Axis-Parallel Operation (CumSum, Prefix Scan)

For operators where each output element depends only on elements along one axis, map one thread per independent lane.

```python
# Pattern: per-column cumulative sum (axis=0 on row-major data)
# SIMT_VF_BODY:
#   col = blockIdx.x * blockDim.x + threadIdx.x
#   if col >= total_cols: return
#   acc = 0
#   for i in range(scan_len):
#       acc += input[i * inner_size + col]
#       output[i * inner_size + col] = acc
```

**Key characteristics**:
- No warp functions, no sync, no UB needed (`dynUBufSize = 0`)
- Sequential dependency is within the thread's own loop, not between threads
- Column-strided memory access on row-major data has poor L2 hit rate (~14.3%) — for large `inner_size`, consider transpose-scan-transpose

### Iterative SIMT Algorithm (TopK, K-th Value)

For operators that repeat a find-and-remove cycle K times, annotate the VF body with an iteration loop combining: per-thread scan -> warp reduction -> cross-warp merge -> mask found element -> repeat.

**Key characteristics**:
- Requires both `SIMT_INCLUDE: simt_api/device_warp_functions.h` and `SIMT_INCLUDE: simt_api/device_sync_functions.h`
- Batch dimension maps to blocks naturally — no tiling needed when batch <= 56 (core count)
- K scaling is linear; warp reduction makes each iteration ~8x cheaper than serial merge

**Round_6 supersession (9.458x on A5):** The iterative find-and-remove approach above is the baseline. Two additional algorithms, both A14-safe (self-contained VFs, no device helper calls), provide large improvements on under-parallelized cases:

1. **Cooperative disjoint-band selection** (round_4, 6.549x): for under-parallelized large-k cases (`numSlices < 2048 && S <= 32768 && k*S > 1e6`), assign tpg threads per slice with disjoint output-rank bands. Band-start cursor via inline 4-bit MSD radix rank-select (histogram overlays the candidate buffer, stays under the 507035 private-array ceiling). Handles k=2000 successfully (c12 26.1x, c17 12.4x, zero regressions). `tpg=1` outside the gate reproduces the baseline exactly.

2. **Two-launch GM-scratch scan-partition** (round_5, 9.458x): for tiny-numSlices huge-S cases (`numSlices < 64 && S > 32768 && S*k > 1e6`), split S into P = sqrt(S/k) chunks over two stream-ordered launches. Phase A: P blocks parallel-reduce chunk-local top-k global indices into an int64 scratch output tensor (not OPP workspace — avoids error 334). Phase B: one worker/slice merges the P*k candidates. c1 79.4x, c14 20.6x, zero regressions.

See `simt_perf_tuning_rules.md` reusable levers for algorithmic details.

> Implementation details (butterfly loop, scratch layout, masking) are in the pass details files and lowering examples.

### Reduction (ReduceSum, ReduceMean, ArgMax)

For operators that reduce along one axis, map one block per row with grid-stride over the batch dimension.

```python
# Pattern: row-wise reduction with grid-stride + warp REDUX
# SIMT_VF_BODY:
#   for row in grid_stride(blockIdx.x, batchSize, gridDim.x):
#       if tid == 0: output[row] = 0.0
#       asc_syncthreads()
#       partial = 0
#       for col in stride_loop(tid, dim, blockDim.x):
#           partial += input[row * dim + col]
#       warp_sum = asc_reduce_add(partial)
#       if lane == 0: asc_atomic_add(output[row], warp_sum)
#       asc_syncthreads()
```

**Key characteristics**:
- `asc_reduce_add` is a single REDUX instruction (~16 cycles for 32 lanes) — no shuffle chain needed
- Grid-stride over rows: `blocks_per_grid = GetCoreNumAiv()`, NOT `batchSize`. Each block loops over its assigned rows. Avoids over-subscription penalty at batch >> core_count (2.4× degradation observed without grid-stride)
- In-kernel zero-init per row (thread 0 + barrier) — no host pre-initialization needed
- One `asc_atomic_add` per warp (8 atomics for 256 threads) — low contention
- `SIMT_INCLUDE: simt_api/device_warp_functions.h` + `simt_api/device_atomic_functions.h` + `simt_api/device_sync_functions.h`

**Both barriers are load-bearing — do not drop either:**
- The barrier **after zero-init** stops a warp's `asc_atomic_add` from landing before thread 0's zeroing store, which would erase that contribution.
- The barrier **at the end of the row body** stops a fast warp from starting the next row and zeroing it while a slow warp is still accumulating into it. This one only bites once `batchSize > gridDim.x` — i.e. only when the grid-stride loop actually takes a second trip. It is invisible at one row per block.

**`asc_reduce_add` is a warp collective** — every thread in the warp must reach it. Never place it inside a divergent branch. The `if (lane == 0)` guard goes *after* the reduce, never around it; likewise the column loop must be uniform across the warp, so use a stride loop rather than an early `return` on `col >= dim`.

`asc_reduce_add` supports `float` and `uint32_t`. For `half`/`bfloat16_t`, widen to float and narrow back — see `simt_multi_dtype_guide.md`.

**Variants**: swap to `asc_reduce_max` + `asc_atomic_max` with identity `-FLT_MAX` for ReduceMax; for ReduceMean, sum as above and scale by `1/dim` in the warp leader before the atomic.

> Use `operator_examples/torch_gather_20_20/` as the Model B structural template; adapt the warp reduction + atomic accumulation pattern above.

### Masked Reduction — Model C variant (MaskedSoftmax, MaskedMean)

For operators that fuse an irregular/predicated read with a **reduction**. This is
the **Q4 "NO"** branch: standard Model C (`__simt_vf__` → `__simd_vf__`) does not
apply, because **`__simd_vf__` cannot compile `ReduceMax`/`ReduceSum`** (MicroAPI
has elementwise ops only — no reductions, no `Exp`, no `Duplicate`).

The reductions move **out** of a VF and **into** the `__aicore__` entry function,
where the full AscendC high-level API is available:

```
__simt_vf__   irregular / predicated read      → __ubuf__
     ↓        (stays on-chip — no HBM round-trip)
__aicore__ entry, AscendC APIs: ReduceMax → Adds(-max) → Exp → ReduceSum → Muls(1/sum)
     ↓
DataCopy (MTE3) → GM
```

```python
# Pattern: masked softmax, one block per row
# SIMT_MODEL: simt_vf (Model C variant — no __simd_vf__)
# SIMT_VF_BODY (phase 1, writes __ubuf__ float* ub_masked):
#   tid = threadIdx.x
#   if tid >= seqLen: return
#   off = blockIdx.x * seqLen
#   ub_masked[tid] = NEG_INF if mask[off + tid] == 0 else input[off + tid]
#
# ENTRY_BODY (phase 2, AscendC on UB — NOT in a VF):
#   ReduceMax(ubMax, ubMasked, ubReduce, seqLen); rowMax = ubMax.GetValue(0)
#   if rowMax <= NEG_INF + 1: Duplicate(ubExp, 0.0, seqLen); goto writeout   # all-masked row
#   Adds(ubExp, ubMasked, -rowMax, seqLen)      # numerical stability
#   Exp (ubExp, ubExp, seqLen)
#   ReduceSum(ubSum, ubExp, ubReduce, seqLen); rowSum = ubSum.GetValue(0)
#   Muls(ubExp, ubExp, (rowSum > 0 ? 1/rowSum : 0), seqLen)
# writeout:
#   SetFlag<V_MTE3>(0); WaitFlag<V_MTE3>(0); DataCopy(gmOut + off, ubExp, alignedSeqLen)
```

**Key characteristics**:
- **The fusion win is the `__ubuf__` handoff.** Pass `ubTensor.GetPhyAddr()` cast to `__ubuf__ T*` as a VF argument — a VF *can* take a `__ubuf__` pointer. The masked intermediate never round-trips through HBM, saving `2 × seqLen × sizeof(T)` bytes per row.
- **`-inf` sentinel must be `-FLT_MAX` (`-3.402823466e+38f`), not a true infinity** — a real `-inf` propagates `NaN` through `exp(x - max)` when a whole row is masked.
- **Guard the all-masked row twice**: once on `rowMax` (before the `exp`) and once on `rowSum > 0` (before the reciprocal). Either alone leaves a `0/0` path, and a mask can be all-zero per row independently of the tensor.
- **Alignment asymmetry — keep it.** Reductions and elementwise ops take the *logical* `seqLen`; `DataCopy` moves `alignedSeqLen = ceil(seqLen/8)*8`. Passing `alignedSeqLen` to `ReduceMax` folds in uninitialized tail elements.
- **`SetFlag`/`WaitFlag<HardEvent::V_MTE3>` before `DataCopy`** — without it the DMA can read UB before the vector pipe retires its writes. Same class as the V_MTE2 WAR hazard: silent wrong answers, invisible at small sizes.
- **Reduction workspace** for `ReduceMax`/`ReduceSum` must be `alignedSeqLen` elements, not 8. Undersizing corrupts the reduction.
- `threadsPerBlock` must cover `seqLen` (phase 1 is one thread per column with an early return, no stride loop). For `seqLen > 1024`, rewrite phase 1 as a strided loop.
- `SIMT_INCLUDE: kernel_operator.h` + `simt_api/asc_simt.h`

> Use `operator_examples/gather_and_adds/` as the Model C structural template; replace its `__simd_vf__` stage with the entry-function reduction sequence above.

### Stream Compaction (Masked Select with Irregular Input)

> **IMPORTANT — Routing caveat**: NonZero, Where, and masked select on contiguous tensors
> should **NOT** use SIMT stream compaction. Their input access is regular (linear scan),
> so native AscendC with DMA + vectorized compare + prefix-sum is ~58x faster.
> SIMT scalar GM loads (173 cy each) cannot compete with MTE2 bulk DMA for contiguous reads.
> Reserve this pattern for operators with **truly irregular input access** — e.g., sparse
> filtering where the input indices themselves are data-dependent, or graph traversal
> where neighbors are discovered at runtime.
> The 58x gap is structural: native AscendC uses MTE2 bulk DMA while SIMT uses scalar GM loads (173 cy each).

For operators that output a variable-length dense subset of qualifying elements **and** have irregular/random input access. Uses warp-level ballot+popc for efficient atomic reservation.

```python
# Pattern: output qualifying elements from irregular access (sparse filter)
# SIMT_MODEL: pure_simt
# SIMT_VF_BODY:
#   idx = blockIdx.x * blockDim.x + threadIdx.x
#   if idx >= total_length: return
#   qualifies = (input[idx] != 0)
#   mask = asc_ballot(qualifies)
#   if mask == 0: return                           # warp early exit
#   warp_base = 0
#   if laneid() == 0: warp_base = asc_atomic_add(counter, __popc(mask))
#   warp_base = asc_shfl(warp_base, 0, warpSize)  # broadcast
#   if mask & lanemask_eq():
#     offset = __popc(mask & lanemask_lt())
#     output[warp_base + offset] = idx
# SIMT_PERF: atomic_strategy=per_warp
# SIMT_INCLUDE: simt_api/device_warp_functions.h
# SIMT_INCLUDE: simt_api/device_atomic_functions.h
```

**Key characteristics**:
- 1 global atomic per warp instead of per qualifying thread (up to 32x fewer atomics)
- Output size is data-dependent — counter must be `aclrtMemset` to zero before launch
- Use `operator_examples/gather_1d/` as the Model A structural template; adapt the ballot+popc compaction pattern above.

**When to use SIMT vs SIMD for data-dependent output**:

| Input access | Output decision | Example | Best approach |
|---|---|---|---|
| Contiguous (linear scan) | Per-element mask (0 or 1) | NonZero, Where, ReLU mask | SIMD two-pass (DMA + vector compare + prefix-sum) |
| Random/irregular | Per-element mask | Sparse filter, graph neighbor select | SIMT stream compaction |
| Random/irregular | Variable per-element | Sparse matmul, tree traversal | SIMT stream compaction |

### Histogram / Binning (Histogram, BinCount)

For operators that count occurrences per bin. Uses per-warp `__ubuf__` sub-arrays + two-kernel approach.

```python
# Pattern: histogram with per-warp UB atomics
# SIMT_MODEL: pure_simt (SDK two-kernel) or simt_vf (validated single-kernel)
# SIMT_KERNEL: name=histogram_kernel, two_pass=true
# SIMT_VF_BODY:
#   // Kernel 1: per-warp __ubuf__ histogram
#   warp_hist = __ubuf__[warp_id * BIN_COUNT]
#   for pos in grid_stride_loop(total):
#     bin = compute_bin(input[pos])
#     asc_atomic_add(warp_hist + bin, 1)
#   asc_syncthreads()
#   // merge across warps -> partial_histogram[blockIdx.x]
#   // Kernel 2: merge partial histograms across blocks
# SIMT_PERF: atomic_strategy=per_warp
# SIMT_INCLUDE: simt_api/device_atomic_functions.h
# SIMT_INCLUDE: simt_api/device_sync_functions.h
```

**Key characteristics**:
- Two kernels: accumulate per-block, then merge across blocks
- `__ubuf__` sizing: `WARP_COUNT x BIN_COUNT x sizeof(uint32_t)` must fit in 8KB (VF-readable UB limit). For 256 bins × 6 warps × 4B = 6KB — fits.
- Use `operator_examples/gather_1d/` (Model A) or `operator_examples/torch_gather_20_20/` (Model B) as the structural template; adapt the per-warp UB atomic pattern above.

### Matrix Transpose / Data Reorganization

For operators that change data layout. Uses `__ubuf__` tiled approach for coalesced reads AND writes.

> ⚠️ **The grid is 1-D. Do not index tiles with `blockIdx.y`.** The grid comes from the host's
> `SetBlockDim(numBlocks)`, which takes a scalar, so a Model B launch gives
> `gridDim = (numBlocks, 1, 1)` and **`blockIdx.y` is uniformly 0** — measured:
> `<<<56, 0, stream>>>` → `gridDim = (56,1,1)`. A kernel that addresses tile rows by
> `blockIdx.y` computes only the first row of tiles and silently leaves the rest at whatever
> the output buffer held. That is a wrong answer, not a compile error, and a zeroed output
> buffer will make it look plausible. Flatten the tile grid into `blockIdx.x` and decompose
> in-kernel, as below. (2-D *threads* are a separate matter and do work — `dim3(32,32,1)`
> gives `blockDim.x=32 blockDim.y=32`.)

```python
# Pattern: 2D transpose via __ubuf__ tile
# SIMT_MODEL: pure_simt
# SIMT_GRID: blocks_per_grid=ceil(width/32)*ceil(height/32) (1-D, via host SetBlockDim),
#            threads_per_block=dim3(32, 32, 1)
# SIMT_VF_BODY:
#   tilesX = (width + 31) / 32
#   tileX  = blockIdx.x % tilesX          # decompose the flattened tile index --
#   tileY  = blockIdx.x / tilesX          # blockIdx.y is always 0, never use it
#   xIndex = tileX * 32 + threadIdx.x
#   yIndex = tileY * 32 + threadIdx.y
#   if (xIndex < width && yIndex < height)                         # bounds-guard both axes
#       tile[threadIdx.y][threadIdx.x] = input[xIndex + width * yIndex]  # coalesced load
#   asc_syncthreads()
#   xIndex' = tileY * 32 + threadIdx.x
#   yIndex' = tileX * 32 + threadIdx.y
#   if (xIndex' < height && yIndex' < width)
#       output[xIndex' + height * yIndex'] = tile[threadIdx.x][threadIdx.y]  # coalesced store
# SIMT_PERF: ubuf_2d_padding=true, non_coalesced_access=false
# SIMT_INCLUDE: simt_api/device_sync_functions.h
```

**Key characteristics**:
- **1-D grid** (`SetBlockDim(tilesX * tilesY)`) with 2-D threads `dim3(32, 32, 1)`
  <!-- claim: model-b-grid-is-1d · also in: ../SKILL.md · find with: grep -rn "claim: model-b-grid-is-1d" skills/simt-codegen · edit all sites together -->
- `__ubuf__ float tile[32][33]` — +1 padding for bank conflict avoidance
- Use `operator_examples/torch_gather_20_20/` as the Model B structural template; adapt the UB-tiled 2D grid transpose pattern above. See also `memory_optimization_guide.md` §7 for UB-bitcast dodge constraints.
