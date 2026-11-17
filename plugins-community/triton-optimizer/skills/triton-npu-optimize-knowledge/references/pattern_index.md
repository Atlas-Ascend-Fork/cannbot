# Triton Optimization Pattern Index

Use this generated stage tree as the execution-navigation view for pattern triage.

Scan stages in order: structural -> kernel -> refinement -> autotune. Within a stage, inspect High patterns before Normal patterns when their applicability domain matches.

Stage order overrides priority: a later-stage High pattern never precedes an earlier-stage Normal pattern. Stage describes change granularity and recommended scan order, not implementation difficulty or guaranteed speedup.

## 1. Structural: Coarse-Grained Optimization

### High

#### `dot-matmul-rewrite`

- Priority: high
- Use When: The kernel computes an `M x N` output tile through a regular reduction over `K` — semantically `sum_k A[..., k] * B[..., k]` — but the current implementation is a manual loop rather than a tiled `tl.dot` matmul, and profiling or IR suggests the hot loop spends too much effort on scalar address generation or repeated reduction structure.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/dot_matmul_rewrite.md`

#### `engine-aware-grid-scheduling`

- Priority: high
- Use When: The program-to-core mapping of a single launch looks wasteful. If a host loop calls the kernel once per segment, apply `host-launch-coalescing` first.

  One or more of these situations holds:

  - **Heterogeneous programs**: programs differ in loop length, memory region, or Cube/Vector mix, so which programs share a batch matters.
  - **Padded-grid no-ops**: a rectangular grid padded to the maximum submits many programs that only decode metadata and return early, because their tiles fall outside ragged segment lengths.
  - **Batch-boundary count**: the logical program count sits close to a program-batch boundary or leaves the last batch mostly idle.
  - **Thin programs**: per-program setup dominates, or a small independent grid axis could move inside the program.

  Profile or IR confirms the mapping matters: latency shifts when one program batch finishes and the next starts, or a Vector-heavy and a Cube-heavy kernel respond oppositely to the same axis order.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/engine_aware_grid_scheduling.md`

#### `gather-then-dense-compute`

- Priority: high
- Use When: Your kernel's hot loop resolves data-dependent row indices and loads scattered rows before a regular dot or reduction:

  ```python
  for k in range(num_steps):                 # every iteration re-gathers
      row_ptr = base + idx[k] * stride       # data-dependent pointer
      vals = tl.load(row_ptr + offs)         # one random row per lane
      acc = tl.dot(vals, w, acc)             # dense math on gathered rows
  ```

  Profiling shows the gather dominating the path: many small indirect row loads that the compiler cannot turn into block transfers. The selected rows are a small share of the source (topK rows, not the whole source), so gathering them once into one contiguous buffer is cheap to stream. And the indices are spread out — if many lanes hit the same address, even the densify pass would serialize on those hot spots.

  The rewrite gathers the selected rows once into a contiguous buffer, so the dense compute then runs on contiguous loads at full rate instead of scattered row loads.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/gather_then_dense_compute.md`

#### `grid-flatten-and-ub-buffering`

- Priority: high
- Use When: The launched grid is much larger than the physical AICore or VectorCore count, so many tiny programs each handle only one or a few small rows. Work is partitioned by batch or sequence buckets with visible load imbalance, or a batch/head grid axis leaves each program too thin to cover its own launch and setup. Gather-like code whose destination rows are continuous but still stored one row at a time, and gradient-accumulation code that repeatedly loads consecutive source rows one at a time, have the same shape:

  ```python
  pid = tl.program_id(0)               # grid >> physical core count
  x = tl.load(src + pid * ROW + offs)  # each program moves one small row
  tl.store(dst + pid * ROW + offs, x)
  ```

  Flattening the grid onto the physical cores turns thousands of tiny programs into one strided loop per core, and batching the row-wise transfers into wider UB stores cuts per-program setup and transaction count.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/grid_flatten_and_ub_buffering.md`

#### `host-launch-coalescing`

- Priority: high
- Use When: A Python or wrapper loop launches the same small kernel once per batch item, head, sequence bucket, or ragged segment. A typical example:

  ```python
  for segment in range(num_segments):
      kernel[(grid_for_segment,)](x + offsets[segment], out + offsets[segment])
  ```

  This is worth merging when each launch is so short that host dispatch and kernel-launch overhead is a visible share of total latency. It is possible when the segments are independent: their outputs can go to disjoint regions of one launch's output, and their per-segment metadata (lengths, offsets, strides) can be passed to the device as arrays.

  The merged form replaces the loop with one device launch whose programs decode their own segment identity, removing the repeated dispatch and launch overhead.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/host_launch_coalescing.md`

#### `int8-dot-int32-accumulator`

- Priority: high
- Use When: Your operator is an int8×int8 quantized GEMM with dequant scales applied after the integer reduction. The current kernel widens the int8 operands to fp16 or fp32 before `tl.dot` and accumulates in fp32. A typical example:

  ```python
  a = a_tile.to(tl.float16)   # int8 operands widened before the dot
  acc += tl.dot(a, b)         # acc is fp32
  ```

  With int8 inputs, every product and partial sum is computed without rounding, and you can prove the int32 accumulator cannot overflow for the largest supported K and value bounds.

  The native int8 dot with an int32 accumulator runs the faster integer MMAD path with half the operand footprint of the fp16-widened form.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/int8_dot_int32_accumulator.md`

#### `kernel-fusion-and-value-placement`

- Priority: high
- Use When: An ordered computation path runs as several kernels or framework operations, within one operator call or across cooperating wrappers. One or more of these shapes is present:

  - **Large intermediate round trip**: one launch writes a large intermediate tensor to memory and the next launch reads it back.
  - **Sibling or fan-out launches**: several launches reload the same inputs.
  - **Repeated dominant work**: multiple launches repeat the same dominant matmul, reduction, or expensive elementwise chain over the same tiles.
  - **Glue operations**: framework copies, casts, or allocations sit between otherwise related computations.

  A producer also constructs a data-dependent permutation or compacted destination map that a later consumer inverts, or rereads, to recover source rows. The producer already has both coordinates in registers, valid destinations have exclusive ownership, and a supported output or metadata channel can carry the derived map to the consumer.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/kernel_fusion_and_value_placement.md`

#### `repeated-gather-compute-once`

- Priority: high
- Use When: An index or pointer buffer selects elements with replacement: the same element is gathered several times, and downstream arithmetic counts each occurrence.

  ```python
  rows = index_row[i, :]            # values repeat, e.g. [3, 0, 3, 3, 1]
  vals = gathered[rows]             # loads len(index_row) elements
  out  = reduce(f(vals))            # every occurrence contributes
  ```

  Profiling shows loads and FLOPs tracking the index buffer length while the distinct element set is much smaller — each selected element referenced 2x or more on average. The downstream computation must accept an exact count-weight compensation per distinct element (softmax-family, linear sums, moments).

  Dedup to the distinct elements, compute each once, and restore the multiplicities exactly — count weights for sums, a `log(count)` shift for softmax.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/repeated_gather_compute_once.md`

### Normal

#### `common-input-projection-packing`

- Priority: normal
- Use When: Several linear projections consume the same input and reduce over the same dimension (K), differing mainly in their output channels — a generic shape, with Q/K/V-style siblings as the canonical instance:

  ```python
  Q = x @ W_q        # separate kernels, each re-reading the same x
  K = x @ W_k
  V = x @ W_v
  ```

  The same shape appears wherever sibling projections share one input — gated FFN gate/up pairs, Mamba `in_proj` branches, multi-head prediction heads — not only in attention. Profiling shows the sibling kernels repeating the same input loads, contraction-loop setup, and launch overhead. The parameters are immutable or cacheable long enough that packing them (transposition, concatenation) can be amortized outside the measured hot path, the outputs can stay disjoint (stride-aware views of one packed result or separate stores without cross-program communication), and the combined width still admits a legal, efficient tile/grid plan on the target.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/common_input_projection_packing.md`

#### `compute-once-share-via-gm`

- Priority: normal
- Use When: Several consumer programs (or launches) each recompute the same expensive value because it does not depend on the axis that distinguishes them — for example every program in a grid recomputes an input-wide statistics table that is identical for all of them — and profiling confirms the repeated computation is material, not just visible in source.

  The trade pays off only when reuse is high and the shared value is small: one GM write plus the consumer reads must cost less than the repeated production. A safe handoff for the shared value must exist — typically a separate kernel launch or an existing output slot. The baseline must be compute-bound, with enough MTE/GM headroom to absorb the added write/read traffic. Rule out cheaper alternatives first — deleting the duplicate work, LICM, algebraic simplification, or on-chip sharing through changed ownership (see the adoption order below).
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/compute_once_share_via_gm.md`

#### `dense-substitution-fine-grained-sparse-attention`

- Priority: normal
- Use When: An attention operator selects KV positions by per-row arbitrary indices (`indices[b, h, s, topK]`, no block structure), and profiling shows the sparse path dominated by gather traffic — many small random-row loads, or a separate gather pass that writes the selected K/V rows to memory and reads them back. The idea: when the selected fraction is not tiny, computing densely over the full `S_kv` at full cube rate plus a boolean mask can beat fewer but random reads. Start testing around `topK / S_kv >= 1/8`, then remeasure the crossover across `S_q`, `D`, dtype, and loader form; `topK * 8 >= S_kv` is not a portable dispatch rule.

  Two gates before substituting. First, the cheap loader repair has been tried and rejected: if rewriting the gather so each key row loads as one contiguous chunk without a data-dependent mask turns it into block transfers, fix the load form and stop there. Second, the dense-mask form must be legal: the `[B, H_kv, S_q, S_kv]` bool/int8 mask fits memory and can be built by one scatter kernel, and per-row indices are unique (a boolean mask cannot count a duplicated index twice).
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/dense_substitution_fine_grained_sparse_attention.md`

#### `force-simt-only-discrete-access-950`

- Priority: normal
- Use When: The Triton kernel runs on confirmed Ascend 950 hardware, and its hot path is discrete, index-driven memory access — gather/scatter-style loads, index arrays, or per-lane pointer arithmetic — with almost no arithmetic on the loaded values:

  ```python
  offs = row[:, None] * stride + idx[None, :]
  vals = tl.load(base + offs, mask=mask)
  ```

  Profiling shows `aiv_scalar_ratio` clearly above both `aiv_vec_ratio` and `cube_utilization` for this kernel's row in `op_summary_*.csv`. The generic flat-index-decode-to-layout-tiling repair has been ruled out or already tried, so the remaining scalar load is architectural rather than a fixable indexing structure.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/force_simt_only_discrete_access_950.md`

#### `invariant-preprocessing-cache`

- Priority: normal
- Use When: The operator is called many times with an input that does not change across calls — e.g. a weight, a lookup table, or a layout descriptor — and every call rebuilds the same padded, packed, transposed, quantized, or indexed version of it before launching the kernel. A typical example:

  ```python
  def forward(x, weight):
      packed = quantize(weight.t().contiguous())  # rebuilt on every call
      return kernel(x, packed)
  ```

  Profiling shows the preprocessing launches, allocations, or copies taking a visible share of per-call latency. The prepared value must be a pure function of the source and fixed transform options — never depending on runtime inputs, random state, or output storage — and the caller contract must give a way to tell when the source has changed. The same source must repeat often enough that cache hits pay for the misses.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/invariant_preprocessing_cache.md`

#### `shape-specialized-dispatch`

- Priority: normal
- Use When: You have a specialized rewrite that wins — on speed or on accuracy — only inside a proven shape range, while the generic kernel stays correct and competitive outside it. One of two situations:

  - **Performance split**: the same kernel wins consistently on one shape range and regresses on another, and profile, IR, or divisibility evidence explains why (tails, masks, padding, occupancy, tile fit).
  - **Numerics split**: an algebraic or precision rewrite that is exact in real-number arithmetic passes the accuracy contract only in a stable dtype and shape range, because reduction or rounding order changes.

  In both, the boundary follows a causal property (divisibility, tile fit, contraction cost, occupancy, or a validated numerical transition) — not the observed benchmark case list — and is cheap to check before launch.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/shape_specialized_dispatch.md`

## 2. Kernel: Algorithm, Dataflow, And Storage

### High

#### `algebraic-optimization`

- Priority: high
- Use When: The kernel's result is mathematically correct, but a semantics-preserving rewrite of the math could produce the same result with less work: repeated full passes over the same data that one fused pass could serve (e.g. computing mean and variance in two traversals), pairwise or broadcast expressions that factor into row/column terms (e.g. `exp(g_i - g_j)`), a contraction chain whose parenthesization materializes an oversized intermediate, or a loop-carried rescale dependency that a reformulation can break. Apply these rewrites before micro-tuning tile sizes, pipelines, or autotune grids.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/algebraic_optimization.md`

#### `arithmetic-intensity-balancing`

- Priority: high
- Use When: The hot loop is a `tl.dot`-style contraction or reduction over tiles loaded from GM, where each loaded operand tile is reused many times within the iteration (so arithmetic intensity grows with tile size), block sizes, heads-per-program, or grid mapping are still free parameters, and a profile or quick estimate shows per-tile compute and per-tile transfer within the same order of magnitude, so tile choice can actually move which resource is the bottleneck.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/arithmetic_intensity_balancing.md`

#### `attention-online-softmax-fusion`

- Priority: high
- Use When: One attention operator invocation runs as several separate kernels — a QK matmul, a softmax, and a value-aggregation (PV) matmul visible as distinct launches in the profile — and the score or probability tensors passed between them exist only to connect the stages. Fusing the stages into one kernel must be legal and worthwhile (that decision belongs to `kernel-fusion-and-value-placement`); this card supplies the attention-specific online-recurrence construction.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/attention_online_softmax_fusion.md`

#### `attention-visibility-mask-specialization`

- Priority: high
- Use When: An attention kernel already runs an online recurrence over key tiles, but loops over the full (padded or maximum) key length and rebuilds the visibility mask on every iteration:

  ```python
  for n0 in range(0, seq_len, BLOCK_N):   # every key tile, visible or not
      scores = tl.dot(q, tl.trans(load_k(n0)))
      scores = tl.where(visibility_mask(), scores, -inf)  # mask rebuilt every iteration
  ```

  Visibility policies (causal, window, prefix, ragged) have regular geometric structure, so tiles can be classified whole instead of masked element-wise: tiles entirely inside the visible region need no mask, tiles entirely outside can be skipped outright, and only tiles crossing the frontier keep the mask. The loop then runs only over the visible key tiles instead of the whole key sequence.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/attention_visibility_mask_specialization.md`

#### `ragged-tile-early-return`

- Priority: high
- Use When: The kernel processes ragged data: a batch of variable-length segments, such as the sequences in a varlen LLM batch. It launches a padded rectangular grid sized to the longest segment, so each segment spans multiple program tiles while its true length is smaller and known only at runtime. Tiles that fall completely outside their segment's valid rectangle still execute the tile body before a final all-false mask discards every lane:

  ```python
  offs = row_begin + tl.arange(0, BLOCK_ROWS)
  mask = offs < local_rows              # per-lane mask only, no whole-tile guard
  x = tl.load(ptr + offs, mask=mask)    # runs even when row_begin >= local_rows
  ```

  The per-segment lengths (metadata such as `cu_seqlens`) are available before tile data is accessed, so they can prove a whole tile invalid. Profiling shows kernel time tracking the padded grid area rather than the sum of live per-segment tiles.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/ragged_tile_early_return.md`

#### `reduction-axis-split-combine`

- Priority: high
- Use When: A reduction kernel (sum, softmax, top-K, dot over K) sizes its grid from the non-reduction dimensions only and cannot fill the device even after tile resizing: for example a per-row reduction over `[4, 1M]` launches 4 programs on a 32-core device, each looping over the long reduction axis while the other 28 cores idle.

  Two preconditions: the reduction admits cheap associative partial states — an fp32 partial sum, online-softmax state (accumulator, running max, running sum), or counts — that a light combine pass can merge, and each program after the split still has enough work that the partial-state write and combine cost pays off.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/reduction_axis_split_combine.md`

#### `redundant-loop-work-deletion`

- Priority: high
- Use When: A tiled loop iterates over a padded or maximum extent while the useful work is shorter, so useless trailing iterations still pay loop control, loads, recurrence, or pipeline work even though a guard suppresses their arithmetic:

  ```python
  for tile_start in range(0, total_extent, BLOCK):  # full/padded range
      if tile_start < useful_extent:                # guard only skips the work
          ...  # loads, compute, recurrence updates
  ```

  Runtime metadata or a loop-invariant predicate proves that the trailing tiles are all inactive. A partially valid final tile can retain its exact boundary predicate.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/redundant_loop_work_deletion.md`

### Normal

#### `amortized-neutral-padding-layout`

- Priority: normal
- Use When: One internal tensor's true length along a tiled axis is not tile-divisible (e.g. 100 valid elements while tiles are 128), and several consumer kernels or tiles read it repeatedly, with each consumer rebuilding the same boundary handling — tail masks, pointer clamping, short transfers, or fill/select work — on every read. The repeated boundary work outweighs a one-time preparation pass, every consumer has a neutral value that makes padded lanes harmless to its algebra (zero for dot/sum, the lower identity for max, the upper for min), and padding to a tile-aligned physical extent unlocks a materially better dot, reduction, vector-transfer, or block-pointer lowering on the target.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/amortized_neutral_padding_layout.md`

#### `attention-intermediate-vector-work-reduction`

- Priority: normal
- Use When: In a mixed attention kernel, a first Cube operation such as QK produces a tile that Vector scale, mask, normalization, or recurrence work must transform before a second Cube operation such as PV can start, and profiling shows the downstream Cube operation actually waiting on this intervening Vector phase — for example Vector-dominated engine ratios with an idle Cube — rather than the Vector work being hidden by overlap or dwarfed by transfer time. Code or IR shows duplicated or unnecessarily sequential Vector expressions whose result directly gates the downstream Cube consumer.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/attention_intermediate_vector_work_reduction.md`

#### `block-pointer-tiles`

- Priority: normal
- Use When: Your kernel accesses a logically regular rectangular tile — predictable offsets, contiguous or regularly strided axes — but expresses it as per-lane pointer arithmetic, and IR or profiling shows the access lowered into fragmented, scalarized, or non-coalesced transfers:

  ```python
  rows = m0 + tl.arange(0, BLOCK_M)[:, None]
  cols = n0 + tl.arange(0, BLOCK_N)[None, :]
  tile = tl.load(x + rows * stride_m + cols * stride_n, mask=...)   # tile load
  # or the same arithmetic on the store side:
  tl.store(out + rows * stride_m + cols * stride_n, acc, mask=...)
  # or a load followed by an explicit transpose for a dot operand:
  k_t = tl.trans(tl.load(k_ptrs, mask=k_mask))
  ```
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/block_pointer_tiles.md`

#### `cv-intermediate-tile-orientation`

- Priority: normal
- Use When: In a mixed Cube/Vector kernel (attention-style), a Cube dot produces a tile that Vector work transforms row by row (softmax-like scale/mask/exp) before a later Cube dot consumes it, and the producer dot emits the transpose of the Vector-natural orientation:

  ```python
  qkT = tl.dot(k, q.T)               # [64, 256]: scan axis (queries) is trailing
  pT = tl.exp2(qkT - lse[None, :])   # Vector walks the long trailing axis
  ```

  The same values are available in the Vector-natural orientation (`tl.dot(q, k.T)` → `[256, 64]`), and profiling or IR attributes cost to the Cube-to-Vector transfer (fixpipe) or to Vector walking the transposed tile.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/cv_intermediate_tile_orientation.md`

#### `discrete-access-ub-staging`

- Priority: normal
- Use When: The kernel's central bottleneck is discrete memory access that semantically looks like `out = x[idx]`: index-driven global loads dominate the hot path, and the gather source array is small or medium enough that staging a contiguous range into the on-chip buffer and selecting locally is more plausible than direct scattered reads.

  A second form: the hot loop reads fixed fields from interleaved records, e.g. coordinates stored as `[N, 3]` in memory order `x0 y0 z0 x1 y1 z1 ...`, so reading one field means stride-3 access. The input is reused enough that a one-time transpose to channel-first order (`x0 x1 ... y0 y1 ...`) on the wrapper side pays for itself.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/discrete_access_ub_staging.md`

#### `gqa-kv-shared-row-batching`

- Priority: normal
- Use When: Your operator is GQA/MQA attention: `N_q` query heads share `N_kv` KV heads with group size `G = N_q / N_kv > 1` (Q is `[B, S, N_q, D]`, K/V are `[B, S_kv, N_kv, D]`), and the kernel runs one program per query head (or per query position and query head). The `G` sibling programs in a KV-head group iterate the same `S_kv` range over the same K/V offsets, so each shared K/V tile is loaded `G` times. A typical shape:

  ```python
  head_kv = (pid % N_q) // G    # G sibling programs share this KV head
  k = tl.load(K + head_kv * skh + kv_offs[:, None] * sks + d_offs[None, :])
  ```

  Profile shows the re-reads are material: decode cases are HBM/L2-bound on K/V with traffic near `G` times the logical cache size, or a Vector-dominated profile shows `G` redundant consumer programs.

  Two forms apply, depending on the kernel's current structure:

  - **Decode fold**: decode or other small-`S` shapes, where query positions and the head group are small enough to fold into one online-softmax row tile that still fits.
  - **Separate-stage grouping**: QK, normalization, and PV are already separate stages, so a bounded head group can share a K or V tile inside the contraction stages without duplicating normalization state.

  Applying this pattern cuts shared K/V loads from `G` per KV head to one, at the cost of extra live accumulators and masks.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/gqa_kv_shared_row_batching.md`

#### `implicit-transpose-elimination`

- Priority: normal
- Use When: One of these situations — in all of them the physical layout does not match the access orientation, so the kernel pays a hidden transpose cost:

  - **Operand stored transposed**: a GEMM/Linear-like kernel where one operand is stored as `[N, K]` but the math needs `[K, N]` (e.g. `y = x @ w.T`), and the kernel emulates it with stride-swapped pointer math or `acc += tl.dot(a, tl.trans(tl.load(b_ptrs)).to(tl.float16))`.
  - **Transpose paid on the wrong side**: `A @ B` allows the logical transpose on either operand, and one operand's orientation is free (a block-pointer load) while the other is already on-chip (produced by an earlier operation) — but the current code transposes the loaded tile, paying a real conversion.
  - **Hot read perpendicular to storage**: a gate-like tensor is stored as `[B, T, HV]` (T contiguous) but the hot loop reads a time chunk for a fixed batch/head lane — every read strides across the contiguous axis, i.e. an implicit transpose per access.

  Profiling shows high scalar/control time or large `WAIT_FLAG_DEVI` time around the matmul path.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/implicit_transpose_elimination.md`

#### `intermediate-layout-copy-deletion`

- Priority: normal
- Use When: The current code creates an intermediate tensor purely to change the physical layout, and the next step immediately copies it into the final output or hands it to exactly one consumer. A typical example:

  ```python
  tmp = x.permute(0, 2, 1).contiguous()      # or transpose/movedim/clone/copy_
  out.copy_(tmp.reshape(out_shape))          # second full-size pass, layout only
  ```

  The layout change must be expressible as pure address math — axis reordering, singleton-axis insertion/removal, or another affine mapping that explicit strides, tile offsets, or `tl.make_block_ptr` can describe — and the target layout must be known at dispatch time. Profiling can confirm the extra pass is a material share of the call.

  The rewrite has the producer write the needed layout directly (or the consumer read via strides), deleting the intermediate entirely — roughly one full read plus one full write of it.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/intermediate_layout_copy_deletion.md`

#### `intermediate-ub-overflow`

- Priority: normal
- Use When: A kernel keeps several full-sized tensors live at once, typically in an accumulator-style update over a whole tile:

  ```python
  result = acc * alpha[:, None] + update  # acc, alpha, update, result all live
  ```

  The compiler reports that the live values do not fit in UB, or the kernel compiles only after shrinking the tile below the size the algorithm needs. The pressure comes from the intermediate values of the computation, not from any single input or output alone.

  Processing the tile in slices keeps only one slice's intermediates live at a time, so the same computation fits UB.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/intermediate_ub_overflow.md`

#### `l2-stripe-capacity-tile-widening`

- Priority: normal
- Use When: A tiled `tl.dot` GEMM or batched matmul reaches near-peak throughput on moderate sizes but collapses sharply once one operand's long axis (say N) grows past a threshold — a large-factor cliff, not a gradual slope. The tiling code is a standard 2-D GEMM grid whose `BLOCK_M` and `BLOCK_N` were tuned on small shapes and never revisited for the large-size regime:

  ```python
  # tuned on small shapes; N now huge
  grid = (triton.cdiv(M, BLOCK_M) * triton.cdiv(N, BLOCK_N) * BATCH,)
  ```

  The re-read accounting explains the cliff: each M-side panel is re-read `N / BLOCK_N` times and each N-side panel `M / BLOCK_M` times, so the slice of the N-side operand that one program batch touches per pass grows with N until it is comparable to or larger than L2.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/l2_stripe_capacity_tile_widening.md`

#### `large-tile-fit-enabling`

- Priority: normal
- Use When: A larger tile would reduce repeated loop work, but the compiler rejects it during UB planning / buffer allocation, and the source-level tensor sizes do not explain the failure. The hot loop performs an elementwise scale, cast, or mask on the large dot/reduction result:

  ```python
  qk = tl.dot(q, k)          # large [BLOCK_M, BLOCK_N] fp32 tile
  qk = qk * sm_scale         # a second large-tile operation lives here
  ```

  The loop-invariant operation can be moved onto a smaller input instead (e.g. pre-scale `q` once before the loop), which may reduce peak live UB enough for the large tile to compile. This is a compiler-resource hypothesis: moving the operation is not claimed to always reduce UB or improve performance. When it works, the rejected large tile compiles and its loop-work savings unlock.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/large_tile_fit_enabling.md`

#### `logical-layout-tiling`

- Priority: normal
- Use When: The kernel is mostly affine data movement — a copy, transpose, reshape, pad, crop, or slice — not dense arithmetic or a reduction. It is launched over a flat `n_elements` or `out.numel()` range, and each lane rebuilds its logical coordinates with division and remainder chains before computing load or store offsets:

  ```python
  offs = pid * BLOCK + tl.arange(0, BLOCK)
  c0 = offs // s0
  r0 = offs % s0
  c1 = r0 // s1
  ```

  The output-to-input mapping is affine: coordinates map through strides, axis reorder, fixed offsets, or padding bounds, with no data-dependent indirection. At least one logical dimension is contiguous or low-stride, so it can become a tile axis. Profiling shows high scalar and control overhead for what should be a cheap copy.

  Tiling to the logical layout removes the per-lane div/mod decoding, leaving base-plus-stride addressing.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/logical_layout_tiling.md`

#### `loop-invariant-hoisting`

- Priority: normal
- Use When: A hot tiled loop rebuilds addresses, masks, or window bounds, or reloads stable input tiles, without dependence on its induction variable. Profiling or IR shows that this repeated transfer, scalar, or control work is a large share of the loop's cost.

  A second case is a reduction that produces only a few values per row or block. A following step computes a scale or a reciprocal from those values, or converts them to another dtype, and broadcasts the result over a much larger element tile. The lowered code recomputes that small step inside the element loop even though its inputs do not change there.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/loop_invariant_hoisting.md`

#### `normalization-base-convention-ablation`

- Priority: normal
- Use When: The kernel normalizes with exponentials over a recurrence with saved state — online softmax, log-sum-exp, or similar — and profile or IR shows the exponential instructions plus the base-conversion multiply chain on the critical path. A typical example — `exp2` fed by scores carrying a `log2(e)` factor:

  ```python
  scores_2 = scores * scale * LOG2_E   # literal near 1.442695
  p = tl.exp2(scores_2 - m_new[:, None])
  ```

  The logarithm base must be a purely internal choice: nothing outside the kernel reads the saved normalization state expecting a particular base, and you must be able to find and switch every path that touches it — forward, backward, and the saved state. If you can only see one local `exp2` call and cannot account for the rest, do not apply this pattern yet.

  Switching the whole convention removes the base-conversion chain from the critical path and runs the normalization on the cheaper exponential path.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/normalization_base_convention_ablation.md`

#### `packed-key-argmax-single-reduction`

- Priority: normal
- Use When: The kernel reduces a whole tile and must return both an extremum value and the position of its first occurrence — argmax/argmin, top-k extraction rounds, or pooling-with-indices. The current implementation pays two reductions per extraction: one for the value and one for the index.

  ```python
  best_val = tl.max(work, axis=1)
  best_idx = tl.argmax(work, axis=1)   # second full reduction over the same tile
  ```

  The argmax/top-k extraction reduces a whole tile at once — or one round per top-k step. Ties must resolve to the first occurrence, matching `torch.argmax` / `torch.topk` semantics.

  Packing value and position into one integer key fuses the value and index reductions into a single `tl.max`, removing a full pass over the tile.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/packed_key_argmax_single_reduction.md`

#### `pad-copy-row-col-tiling`

- Priority: normal
- Use When: The kernel is a constant-pad, slice-then-pad, or similar elementwise copy. It indexes the output as one flat range over `numel(out)` and rebuilds every coordinate with div/mod arithmetic on each iteration. A typical example:

  ```python
  offsets = pid * BLOCK + tl.arange(0, BLOCK)
  d_last = offsets % out_dim_last          # repeated // and % recover coordinates
  rows = offsets // out_dim_last
  valid = (d_last >= pad_left) & (d_last < pad_left + in_dim_last) & (rows < out_rows)
  ```

  Profiling shows scalar or masked-load/compare cost out of proportion to copy bandwidth, concentrated at the last-dimension pad boundaries.

  The rewrite tiles the kernel as rows × columns: div/mod runs once per row lane instead of once per element, and the merged `valid` mask splits into `row_mask & col_mask`.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/pad_copy_row_col_tiling.md`

#### `program-multiple-rows`

- Priority: normal
- Use When: The kernel computes each output row mainly from one input row (row-wise LogSumExp, row norms, row softmax statistics). One Triton program currently handles exactly one row, and the inner loop only tiles the row length `N`:

  ```python
  pid = tl.program_id(0)           # one program per row
  row_ptr = x_ptr + pid * stride   # narrow (1, BLOCK_N) tiles
  ```

  Profiling or timeline views show many tiny programs relative to the row count `B`, high scalar/control overhead, or under-filled vector work per program. The pattern also applies when `N` fits a single tile (`BLOCK_N = next_power_of_2(N)`, no `N` loop); judge by the actual tile footprint and target measurements, not by `N` alone.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/program_multiple_rows.md`

#### `result-tile-layout-alignment`

- Priority: normal
- Use When: A kernel computes a result tile (typically a `tl.dot` or reduction accumulator) and stores it out, but the tile's axis order is the transpose of the output's contiguous memory layout — for example the tile is `(N, M)` while the output is a row-major `(M, N)` tensor. The store address therefore strides across memory instead of advancing contiguously, and profiling or IR inspection shows the store degraded into per-element scalar writes. The pattern applies when the tile's axis order is a free choice of the kernel — as it is for an accumulator — so you can carry the tile in the output's axis order from the start (swapping the reduction axis and mask broadcast directions accordingly) instead of paying a store-time transpose.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/result_tile_layout_alignment.md`

#### `scattered-transfer-batching`

- Priority: normal
- Use When: A kernel rearranges rows through an index array, and each index drives its own small scattered global load or store. These small scattered transfers are a large share of the kernel's global-memory cost. One or more of these situations apply:

  - **One side can become contiguous**: the reads, or the writes, could be made contiguous by staging a block of rows in UB.
  - **Source and output axes differ**: adjacent source rows lie along one logical axis while adjacent output rows lie along another, so handling one output row at a time leaves both sides scattered. A small tile spanning those axes fits in UB.
  - **The destination map is complete**: a producer already builds a complete destination map, and a later consumer rereads it to recover source rows before it can own contiguous output tiles. The producer has both coordinates at its existing store, so the inverse is derivable there.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/scattered_transfer_batching.md`

#### `shift-mask-reduce-to-load`

- Priority: normal
- Use When: The kernel shifts every lane one position (`out[i] = x[i-1]`), with lane 0 handled specially. The code builds this shift with a 2D mask-and-reduce instead of a direct shifted load:

  ```python
  shift_mask = offs_i == (offs_j + 1)
  shifted = tl.sum(tl.where(shift_mask, x[None, :], 0.0), axis=1)
  ```

  The mask-reduce builds an N×N boolean matrix to fetch each element's left neighbor — O(N²) work for what is one shifted load.

  IR shows `tt.broadcast` / `tt.reduce` work that serves only the shift path, and profiling shows overhead concentrated there.

  A 1D predecessor load replaces the quadratic mask-and-reduce with one shifted load.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/shift_mask_reduce_to_load.md`

#### `simt-window-divisor-formula`

- Priority: normal
- Use When: A pooling-style kernel — fixed K_D×K_H×K_W window per output, regular strides — running in SIMT launch mode divides each output by the number of valid window elements: near the borders the window is clipped and the divisor shrinks (avg-pool with `count_include_pad=False`). The inner loops scan the full window and build that divisor by counting valid elements one by one at runtime:

  ```python
  for kw in range(KERNEL_W):
      w = start_w + kw
      valid_w = (w >= 0) & (w < in_w)
      mask = valid_d & valid_h & valid_w
      acc += tl.load(x_ptr + off, mask=mask, other=0.0)
      count += tl.where(mask, 1, 0)   # divisor accumulated per window element
  ```

  The rewrite computes each output's clipped window bounds once, derives the divisor from a closed-form formula, and iterates only inside the clipped region — no per-element masks, no runtime counting.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/simt_window_divisor_formula.md`

#### `simt-window-reduction-tuning`

- Priority: normal
- Use When: Your kernel reduces a fixed-size input window for each output point, as in pooling-style ops over NCDHW/NCHW layouts. The window position is an affine function of the output coordinate, the kernel size is fixed at compile time, and the inner loop does discrete per-window-element loads rather than dense vector math. A typical example:

  ```python
  start = out_coord * STRIDE - PAD        # affine output→input map
  for tap in tl.static_range(KERNEL_D * KERNEL_H * KERNEL_W):
      acc += tl.load(x_ptr + base + start + tap, mask=in_bounds)
  ```

  The kernel runs on Ascend 950 with `force_simt_only=True`, so this scalar, index-heavy access is the intended lowering. This card is a tuning methodology rather than a single rewrite: it applies when you must choose dispatch, inner paths, and launch parameters across many shapes.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/simt_window_reduction_tuning.md`

#### `strided-layout-reduction`

- Priority: normal
- Use When: The operator reduces one non-last axis of a contiguous row-major tensor, such as `torch.sum(x, dim=1)` on `[B, M, N]`. The current implementation first writes a transposed copy to memory so the reduction can run on the last axis:

  ```python
  x = x.movedim(dim, -1).contiguous()   # or transpose/permute(...).contiguous()
  out = sum_lastdim_kernel(x.reshape(-1, x.shape[-1]))
  ```

  Profiling shows a `Transpose`, `Memcpy`, `DataCopy`, or `Contiguous` step before the reduction kernel. The copy takes time comparable to or larger than the reduction kernel itself. The suffix after the reduced axis is long enough that loads along `inner` stay reasonably coalesced.

  Reducing along the strided axis directly skips the transposed copy, so the kernel pays only for the reduction itself.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/strided_layout_reduction.md`

#### `tile-footprint-fitting`

- Priority: normal
- Use When: A kernel processes its data in one large flat block and keeps several tensor tiles or intermediates live at the same time, so the per-program working set approaches or exceeds UB capacity:

  ```python
  offsets = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)  # one large flat block
  a = tl.load(x + offsets, mask=mask)
  b = tl.load(y + offsets, mask=mask)
  c = tl.load(z + offsets, mask=mask)                    # several tiles live at once
  result = compute(a, b, c)                              # UB overflow risk here
  ```

  The compiler-reported UB allocation or a runtime failure confirms the overflow. Growing `BLOCK_SIZE` makes the failure or the pressure worse. The kernel's overall structure is otherwise reasonable — the problem is per-program memory footprint, not the need for a different kernel shape.

  Splitting the block into sub-blocks processed in sequence keeps only one sub-block live at a time, so the tile fits UB.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/tile_footprint_fitting.md`

#### `valid-length-tiling`

- Priority: normal
- Use When: A kernel rounds the tile width up to a fixed bucket — typically a power of two or a hard-coded upper limit — while a mask protects a much smaller valid length:

  ```python
  BLOCK_H = next_power_of_2(width)   # e.g. 128 lanes for 80 valid
  offs = tl.arange(0, BLOCK_H)
  x = tl.load(ptr + offs, mask=offs < width)
  ```

  Most lanes in each block then do padded work rather than useful work. Profiling shows LD/ST, scalar-loop, or transfer cost tracking the full tile width instead of the valid lane count. The oversized axis is a copy-like or indexed/masked access path that does not participate in `tl.dot`, cube alignment, or reduction-tree structure. The host already knows the shape and could choose a smaller tile or a different launch branch. Sizing the tile to the live valid length removes the padded-lane work instead of paying it on every iteration.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/live_length_tiling.md`

#### `window-2d-ub-staging`

- Priority: normal
- Use When: Your kernel samples a 2D input with overlapping windows — resize, gather-window, or pooling-like — so each output point reads several input samples, and the hot loop issues one dynamic-index global load per sample:

  ```python
  for tap in range(K):
      acc += w[tap] * tl.load(gm_ptr + row_off[tap] * in_w + col_off[tap])
  ```

  The rewrite stages one rectangular input block into UB per program and serves all window reads from it on-chip, turning many scattered global loads into one contiguous copy.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/window_2d_ub_staging.md`

#### `window-slab-gather`

- Priority: normal
- Use When: The kernel computes a fixed-window reduction (mean, max, or similar) along the innermost contiguous dimension of an NCHW-style tensor — pooling is the canonical case. Each program owns a block of adjacent output columns and loops over the window positions with one masked global load per step:

  ```python
  for kw in range(KERNEL_W):  # one narrow masked load per window position
      v = tl.load(x_ptr + base + (start_w + kw) * stride_w, mask=ow_mask, other=0.0)
      acc += v
  ```

  Adjacent output windows overlap, so the same input columns are reloaded from global memory once per window position. Because the input columns are regularly strided, one contiguous input range covers every window the program owns.

  The rewrite loads that whole range once and gathers each window position from it on-chip, so overlapping columns are loaded once instead of `KERNEL_W` times.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/window_slab_gather.md`

## 3. Refinement: Lowering, Boundaries, And Ablations

### High

#### `mask-only-affine-addressing`

- Priority: high
- Use When: A load or store clamps regular offsets with `tl.minimum` / `tl.maximum` against a dimension bound (`M - 1`, `N - 1`, `K - 1`), even though the same `tl.load` or `tl.store` already carries a boundary mask — the clamp protects nothing the mask does not. A typical example:

  ```python
  offs_c = tl.minimum(offs, N - 1)             # clamped index
  tile = tl.load(ptr + offs_c, mask=offs < N)  # mask already guards it
  ```

  The clamp is often recomputed inside a reduction loop on every iteration even though only the last iteration can be partial.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/mask_only_affine_addressing.md`

#### `scalar-latency-trap-removal`

- Priority: high
- Use When: Profiling shows high scalar/control overhead — a high `aiv_scalar_ratio`, or vector time that the arithmetic in the source cannot explain — and IR shows vector operations lowered as scalar loops. The hot path then contains scalarizing constructs such as: shape constants passed as runtime args instead of `tl.constexpr`, loop-carried pointer updates (`ptr += BLOCK_K`), modulo (`%`) tail guards, a `tl.where` selecting one special lane, `int64` index math that fits `int32`, `tl.cumsum`/`tl.associative_scan` scalar fallbacks, or boundary masks an earlier `boundary_check` already covers.

  Typical examples — the loop-carried pointer update and the modulo boundary guard:

  ```python
  for k in tl.range(0, K, BLOCK_K):
      ptr += BLOCK_K                          # loop-carried address dependency
      offs = (k + tl.arange(0, BLOCK)) % N    # modulo boundary guard
  ```
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/scalar_latency_trap_removal.md`

### Normal

#### `compile-hint-adding`

- Priority: normal
- Use When: The kernel structure is settled, but the generated code still carries defensive masks, padding, or narrow transfers for accesses you can prove are aligned or contiguous: for example the compiler pads a `tl.dot` operand on all sides even though only K needs it (M and N are already aligned), or keeps a load/store narrow and masked even though the pointer range is provably contiguous. Communicating the proven fact through a compiler hint lets the lowering drop that defensive code.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/compile_hint_adding.md`

#### `cv-compile-option-ablation-950`

- Priority: normal
- Use When: The target is Ascend 950, the kernel mixes Cube and Vector work — typically a repeated Cube→Vector→Cube or load/compute/store chain, as in attention-style kernels — and profiling suggests the two engines are waiting on each other: pipeline stalls, cross-core wait, or buffer-reuse pressure. The kernel's source-level structure is already settled, so the remaining headroom is in how the compiler pipelines and buffers the dataflow. Kernels on this compile path either set the `enable_dynamic_cv_pipeline` compile option or show `ssbuffer` regions in the generated IR.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/cv_compile_option_ablation_950.md`

#### `diagonal-block-traversal`

- Priority: normal
- Use When: A large tiled matrix-style kernel is tiled reasonably, but profiling shows poor cache locality: the programs running concurrently on the cores (a program batch) touch many distinct operand regions at once, so L2 reuse is lost. The grid spans many blocks along both M and N, so traversal order is a real lever. Reordering which program computes which tile lets programs that read the same data run at the same time, so shared data is fetched from memory once per program batch instead of many times.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/diagonal_block_traversal.md`

#### `dot-operand-precision-ablation`

- Priority: normal
- Use When: Your kernel feeds a `tl.dot` (or equivalent Cube operation) with matched FP32 operands, either because the operands are stored as FP32 or because lower-precision source tiles are upcast only to feed the dot:

  ```python
  left_dot = left.to(tl.float32)   # source tile is fp16/bf16
  right_dot = right.to(tl.float32)
  acc = tl.dot(left_dot, right_dot, acc=acc_fp32)
  ```

  The target supports a higher-throughput matched lower-precision operand pair with a higher-precision accumulator. The operator's accuracy contract permits a controlled operand-rounding experiment, and representative correctness cases are available. Tile geometry, grid, logical work, and surrounding arithmetic can stay fixed, so operand precision is independently attributable.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/dot_operand_precision_ablation.md`

#### `dual-vector-core-parallel`

- Priority: normal
- Use When: Two or more vector-side computations — type conversions, elementwise operations, or scaling steps — run one after another on the hot path and do not depend on each other's results. While each one runs, the second vector core of the AICore sits idle. This part of the kernel is limited by vector compute, not by memory movement.

  ```python
  scaled_a = a.to(tl.float16) * a_s   # depends only on a
  scaled_b = b.to(tl.float16) * b_s   # depends only on b
  acc = tl.dot(scaled_a, scaled_b, acc)
  ```

  Issuing the independent computations together lets both vector cores work at once, up to halving the region's time.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/dual_vector_core_parallel.md`

#### `exact-tile-no-boundary-fast-path`

- Priority: normal
- Use When: The kernel's dominant shapes are exactly divisible by the tile sizes — Python dispatch can prove it before launch with a cheap guard such as `M % BLOCK_M == 0 and N % BLOCK_N == 0` — yet the generated code or profiling still shows boundary checks, masks, or padding on that exact-tile hot path. A typical example — a mask that guards only block edges:

  ```python
  offs_m = pid_m * BLOCK_M + tl.arange(0, BLOCK_M)
  mask = offs_m < M            # boundary-only: always true when M % BLOCK_M == 0
  x = tl.load(ptr + offs_m, mask=mask, other=0.0)
  ```

  The same idea — do boundary work only where a boundary can actually exist — applies to three related situations:

  - **Dispatch-proven case**: the host can prove before launch that this call needs no boundary handling (e.g. a short attention call whose sequence fits one tile), so dispatch picks a specialized mask-free kernel while the generic one stays as fallback.
  - **Pre-padded input**: an upstream stage already padded the input to a tile-aligned physical length (the logical length is kept separately), so loads need no boundary mask at all.
  - **Tail-only loop**: only the final iteration of a contraction or recurrence loop can be partial, but a generic loop rebuilds the tail mask on every iteration — run the full iterations mask-free and peel out the tail.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/exact_tile_no_boundary_fast_path.md`

#### `hilo-split-matmul`

- Priority: normal
- Use When: One of two situations:

  - **fp32 dot hotspot**: a contraction that must keep fp32 accuracy is the hotspot, and it runs one fp32 `tl.dot` (`acc = tl.dot(p, v, acc)`) whose fp32 operands take so much UB that the tile is capped well below the size the fp16 path could use.
  - **Post-rewrite accuracy gap**: a structural rewrite (split-K, axis split, head batching, online-softmax regrouping) changed the summation order, and the accuracy gate now fails by about 1 ulp — the reference computes in fp32, but the kernel needs to stay on the fast fp16/bf16 dot path and naive low-precision rounding no longer passes.

  In both, typically only one operand needs the split because the other is already exactly representable in fp16/bf16.

  The split replaces one fp32 dot with two or three fp16 dots, so it pays only when the larger fp16 tile or the accuracy repair outweighs the extra dots.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/hilo_split_matmul.md`

#### `independent-load-placement`

- Priority: normal
- Use When: Your hot kernel issues several loads that do not depend on each other, and their source order could change without changing any address, mask, or value. The typical shape is a dominant tile load sitting next to small scale, weight, bias, or metadata loads:

  ```python
  x = tl.load(x_ptr + x_offsets)          # dominant tile load
  scale = tl.load(scale_ptr + s_offsets)  # small parameter loads
  weight = tl.load(weight_ptr + w_offsets)
  ```

  The profile shows memory latency, transfer coordination, or on-chip buffer pressure contributing materially to kernel latency. You can inspect the generated IR or device code and benchmark each placement candidate.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/independent_load_placement.md`

#### `merge-adjacent-stores`

- Priority: normal
- Use When: A copy-heavy or store-heavy kernel writes its output through several small `tl.store` operations whose destination addresses sit next to each other — typically one store per loop iteration, or a few stores to adjacent sub-ranges of one output block:

  ```python
  for i in range(K):
      tl.store(out + base + i * SUB, vals_i)  # K small adjacent stores
  ```

  Merging is safe when the written addresses form one continuous interval and the per-element masks agree, and worthwhile when profiling or code inspection shows the many small stores — not loads or compute — limiting throughput.

  The rewrite merges them into one wide store: many small DMA transactions become one vector-friendly write.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/merge_adjacent_stores.md`

#### `overlap-tail-load-mask-free`

- Priority: normal
- Use When: A row- or segment-wise idempotent reduction (max, min, argmax, argmin, any, all) runs on rows whose length is not a multiple of `BLOCK`, so the final tile is masked. A typical example:

  ```python
  cols = tl.arange(0, BLOCK)
  vals = tl.load(row_ptr + cols, mask=cols < n, other=float("-inf"))  # final tile
  row_max = tl.max(vals, axis=0)
  ```

  IR shows the masked tail load lowered to a conditional whole-tile fill plus copy on the hot path. For argmax/argmin, ties are already resolved by position (the smaller position wins), so visiting an element twice cannot change the result.

  The rewrite covers the tail with two overlapping unmasked tiles — `[0, BLOCK)` and `[length-BLOCK, length)` — so the masked load disappears from the hot path.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/overlap_tail_load_mask_free.md`

#### `software-pipeline`

- Priority: normal
- Use When: A hot regular tiled loop loads independent tiles and computes on them in load-then-compute order:

  ```python
  for _ in range(num_k_tiles):
      a = tl.load(a_ptr)
      acc = tl.dot(a, b, acc)
      a_ptr = tl.advance(a_ptr, (0, BLOCK_K))
  ```

  Profiling shows engine idle time or Task Wait around the loop, or generated IR lacks clear transfer-compute coordination. Each iteration has enough work that overlapping the next tile's transfer with current-tile compute could pay off. Compiler-reported usable UB leaves room for the extra buffers and live values an overlapped schedule needs.

  Pipelining the loop — prefetching the next tile while computing the current one — hides the transfer latency behind compute.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/software_pipeline.md`

#### `vec-cmp`

- Priority: normal
- Use When: Your kernel computes an explicit `i64` or `i32` comparison into a named boolean value, and that boolean feeds `tl.where`, a conditional assignment, or a precomputed `mask=` variable on the hot path:

  ```python
  mask = offsets < n_elements              # i64 compare, computed explicitly
  x = tl.load(x_ptr + offsets, mask=mask)  # or: tl.where(mask, a, b)
  ```

  The generated IR shows this integer compare lowered to scalar work. The compare is not written inline as the `mask=` argument of a `tl.load` or `tl.store`, where the compiler already applies its fast path.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/vec_cmp.md`

## 4. Autotune: Final Parameter Search

Run bounded parameter search only after the earlier stages have been scanned and explicit structural candidates have been evaluated.

### High

#### `autotune`

- Priority: high
- Use When: The kernel is correct and its structure is settled (earlier-stage rewrites applied or ruled out), and the remaining headroom is in parameter choice: exposed compile-time tile sizes, split shape, buffering, or supported launch options. For an established SIMT row-reduction path, that headroom can also lie in row-batch size and SIMT worker count while the feature-side computation and the reduction body stay fixed. The kernel may expose those choices as `tl.constexpr` parameters, or keep them fixed behind a persistent launch geometry that already covers every row.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/autotune.md`
