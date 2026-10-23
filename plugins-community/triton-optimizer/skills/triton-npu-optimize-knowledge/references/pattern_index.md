# Triton Optimization Pattern Index

Use this generated stage tree as the execution-navigation view for pattern triage.

Pattern card content is served read-only from the cannbot-knowledge repository (provisioned at `.cannbot/dependencies/triton-optimizer/cannbot-knowledge/`); each entry's Source names its KB card path. Card names here use the contract's kebab-case IDs; KB files use the snake_case equivalent.

Scan stages in order: structural -> kernel -> refinement -> autotune. Within a stage, inspect High patterns before Normal patterns when their applicability domain matches.

Stage order overrides priority: a later-stage High pattern never precedes an earlier-stage Normal pattern. Stage describes change granularity and recommended scan order, not implementation difficulty or guaranteed speedup.

## 1. Structural: Coarse-Grained Optimization

### High

#### `classic-matmul`

- Priority: high
- Trigger: the kernel computes an `M x N` output tile with a regular reduction over `K`
- Summary: Rewrite a manual matmul or K-reduction hot loop into a regular tiled `tl.dot`-based matmul so the kernel structure matches what Ascend Triton lowers well.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/classic_matmul.md`

#### `engine-aware-grid-wave-scheduling`

- Priority: high
- Trigger: A multidimensional grid contains programs with different recurrence lengths, memory locality, or Cube/Vector work.
- Summary: Map logical work already contained in one device launch into program order, a compact live-task domain, physical waves, persistent stride loops, or a bounded serialized axis. Keep work and tile math fixed for the first comparison, and retain a mapping only when its scheduling, decoder, compiler-allocation, or DMA-concurrency effect is separately measured.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/engine_aware_grid_wave_scheduling.md`

#### `fusion-placement-and-materialization`

- Priority: high
- Trigger: A measured public call contains multiple Triton kernels, framework operations, allocations, copies, casts, or materialized intermediates.
- Summary: Combine operations when they can share computation or avoid writing an intermediate tensor. Keep separate kernels when that permits a faster schedule. Distinguish computational fusion from launch coalescing and compiler-internal fusion, and choose the boundary from legality, schedule compatibility, and measured total-operation behavior—not from kernel count or compiler precedent alone.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/fusion_placement_and_materialization.md`

#### `grid-flatten-and-ub-buffering`

- Priority: high
- Trigger: The logical grid is much larger than the physical AICore or VectorCore count.
- Summary: Flatten logical work items onto physical cores and batch small row-wise memory transfers into wider UB stores to reduce launch overhead and improve per-core work density.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/grid_flatten_and_ub_buffering.md`

#### `host-launch-coalescing`

- Priority: high
- Trigger: A host loop launches the same kernel once per batch item, head, bucket, or ragged segment.
- Summary: Replace repeated Python or wrapper launches of the same small kernel across independent logical segments with one device grid whose programs decode segment identity. The mechanism is fewer host/kernel launches and a larger submitted work set, paid for by device metadata loads, identity decode, and control.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/host_launch_coalescing.md`

#### `indirect-access-densification`

- Priority: high
- Trigger: The hot loop computes `dense(op(gathered_rows))`: each program resolves per-element or per-tile indices and issues random-row loads before a regular dot/reduction.
- Summary: When a kernel's hot path feeds indirect/random-row loads into regular dense arithmetic, split the work into two phases: one streaming pass that materializes the referenced rows into a contiguous buffer (with any dtype conversion folded in), then a dense tiled compute (classic-matmul) over that buffer. Adding a materialization round trip can beat indirect loads when the index distribution has spread.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/indirect_access_densification.md`

#### `native-int8-dot-int32-acc-default`

- Priority: high
- Trigger: The operator contracts `int8 x int8 -> (dequantized) fp16/bf16` semantics (npu_quant_matmul family): `relu`-free plain GEMM with dequant scales applied after the integer reduction.
- Summary: In an int8-by-int8 quantized GEMM (per-channel scale, optional bias / pertoken / offset), make the native int8 `tl.dot` with an **int32 accumulator** the default structure for every exact tile, and respond to UB overflow at wide tiles by **demoting the tile geometry** (e.g. 128x128 -> 64x128 with a doubled grid) instead of reverting the operand path to fp16-widened dot. The int32-to-fp32 conversion happens once in the epilogue.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/native_int8_dot_int32_acc_default.md`

#### `repeated-reference-dedup-exact-compensation`

- Priority: high
- Trigger: A buffer of indices/pointers selects elements with replacement, and the duplicate rate is measurable and material (e.g. expected duplicates >= 2x per selected element).
- Summary: When an index/pointer buffer selects the same underlying element multiple times and the downstream semantics are multiset (each occurrence counts), compute each distinct element once and restore the multiplicities with an exact algebraic compensation instead of recomputing redundant work.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/repeated_reference_dedup_exact_compensation.md`

### Normal

#### `a5-force-simt-only-discrete-access`

- Priority: normal
- Trigger: Target hardware is confirmed as A5 by user statement, profile metadata, runtime/compile logs, runtime device query, or environment/CANN target settings.
- Summary: Launch discrete-access-ub-staging Triton kernels on A5 with `force_simt_only=True`, then retune `num_warps` and grid decomposition. This profile-gated launch-mode experiment targets kernels whose hot path is primarily scalar/index-driven memory access.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/a5_force_simt_only_discrete_access.md`

#### `common-input-projection-packing`

- Priority: normal
- Trigger: Two or more dense projections consume the same input rows, use the same reduction extent and compatible operand/accumulator dtypes, and differ mainly in their output-channel ranges.
- Summary: Group compatible sibling affine projections that consume the same input as either one wider contraction or co-scheduled contractions that reuse each loaded input tile. Both forms share input traversal and launch setup while preserving independent parameter values, output semantics, and downstream ownership.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/common_input_projection_packing.md`

#### `cross-program-recompute-materialization`

- Priority: normal
- Trigger: An expensive producer is invariant across a consumer-only program or tile axis, so distinct consumer programs repeat the same logical work.
- Summary: Compute an expensive value once at a supported kernel boundary, write it to GM, and let consumer programs load it instead of recomputing it. This trades an extra GM write/read, allocation, and synchronization for deleted computation.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/cross_program_recompute_materialization.md`

#### `dense-substitution-fine-grained-sparse-attention`

- Priority: normal
- Trigger: Sparsity is per-position and effectively random, given as `indices[b, h, s, topK]` with no block structure. Start by testing a selected fraction such as `topK / S_kv >= 1/8`, then remeasure the crossover across `S_q`, `D`, dtype, and loader form; do not treat `topK * 8 >= S_kv` as a portable dispatch rule.
- Summary: When an attention operator selects KV positions by per-row arbitrary indices (topK sparseIndices, DSA/MLA style) and the selected fraction `topK / S_kv` is not tiny, replace gather-based sparse compute with a dense pass over the full `S_kv` plus a scattered boolean mask. Dense runs entirely on contiguous loads feeding `tl.dot` at cube rate. A gather whose rows are masked or non-contiguous can incur many small indirect row loads or an extra workspace GM round trip. A mask-free, row-contiguous gather can avoid much of that cost, so measure that in-place fix before paying the dense FLOP multiplier.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/dense_substitution_fine_grained_sparse_attention.md`

#### `invariant-preprocessing-cache`

- Priority: normal
- Trigger: Repeated calls consume the same weight, lookup table, layout descriptor, or other read-only source and rebuild the same padded, packed, transposed, quantized, or indexed representation.
- Summary: Reuse pure preprocessing results across public operator invocations under explicit contracts for cache identity, invalidation, ownership, bounded storage, and cold-versus-warm cost.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/invariant_preprocessing_cache.md`

#### `shape-regime-specialized-dispatch`

- Priority: normal
- Trigger: Per-shape review shows stable benefit in one regime and regression in another.
- Summary: Use a small host-side shape discriminator to select a specialized kernel for a proven shape regime while retaining a generic fallback for all other inputs. Dispatch selects an implementation for one invocation; it does not change test-case execution order.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/shape_regime_specialized_dispatch.md`

## 2. Kernel: Algorithm, Dataflow, And Storage

### High

#### `algebraic-optimization`

- Priority: high
- Trigger: The hot path repeats full traversal/reduction work or executes a linear contraction chain whose current parenthesization materializes a disproportionately large intermediate.
- Summary: Apply mathematical identities and semantics-preserving rewrites to reduce redundant memory passes, full data scans, contraction work, intermediates, or live ranges before micro-tuning loads. Covers floating-point identities, matrix-chain evaluation trees, operator-defined equivalences, and algebraic merge rules.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/algebraic_optimization.md`

#### `ascend-redundant-loop-work-deletion`

- Priority: high
- Trigger: A tiled loop visits a padded, maximum, or otherwise larger extent than useful work requires.
- Summary: Replace a full-range tiled loop plus an inner usefulness guard with a loop bounded by the proven useful extent. If the remaining useful tiles contain a fully valid region, a separate mask-free loop is a second, higher-risk candidate whose profitability depends on tile size, recurrence-body complexity, and Ascend lowering.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/ascend_redundant_loop_work_deletion.md`

#### `attention-work-deletion`

- Priority: high
- Trigger: A measured Attention call either materializes internal score or probability tensors between QK, masking or softmax, and value aggregation, or already runs an online recurrence over key tiles.
- Summary: Delete Attention work at two independent levels: after structural grouping is selected, replace an internal materialized score-to-softmax-to-value chain with a tile-owned online recurrence; in any online recurrence, prune invisible key tiles and semantic-mask work.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/attention_work_deletion.md`

#### `axis-split-partial-state-combine`

- Priority: high
- Trigger: A reduction-shaped kernel (dot over K, softmax, top-K, sum) has grid = f(non-reduction dims) that cannot fill the device even after tile resizing.
- Summary: When a reduction kernel's parallelism is capped by its non-reduction grid (the launch cannot fill the cores), split the REDUCTION axis across programs. Each program emits a partial reduction state (accumulator plus auxiliary state such as max/denominator/count), and a light combine kernel merges partial states according to the reduction algebra.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/axis_split_partial_state_combine.md`

#### `ragged-padded-grid-whole-tile-elision`

- Priority: high
- Trigger: A launch uses global padded or maximum extents for one or more axes while individual segments have smaller runtime extents.
- Summary: Return before tile-local work when authoritative segment metadata proves that an entire program tile lies outside the segment's valid rectangle. Keep the ordinary masked body for partial edge tiles. Treat entry elision and compact live-task submission as separate experiments.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/ragged_padded_grid_whole_tile_elision.md`

### Normal

#### `a5-simt-sliding-window-tuning`

- Priority: normal
- Trigger: Kernel matches the pattern signature above.
- Summary: Tuning methodology for kernels that map **each output point** to a **fixed-size input window** over an **affine N-D layout** (e.g. NCDHW/NCHW), then **reduce** (sum, max, etc.) under **A5 `force_simt_only=True`**. Teaches how to **derive** dispatch, inner paths, and launch params from **structural features** — not from a specific op name. Pool-style ops are one common instance; the same signals apply to any op matching the pattern signature below.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/a5_simt_sliding_window_tuning.md`

#### `accumulator-layout-alignment`

- Priority: normal
- Trigger: `tl.store` writes a transposed logical tensor and profiling or code inspection suggests the write degraded into scalar element stores.
- Summary: Align accumulator shapes with output memory layout to avoid store-time transposes that degrade into scalar element writes on Ascend NPU.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/accumulator_layout_alignment.md`

#### `amortized-neutral-padding-layout`

- Priority: normal
- Trigger: One irregular logical tensor feeds several consumer tiles that repeatedly pay boundary masks, short transfers, pointer clamping, or fill/select work.
- Summary: Introduce an internal tensor with tile-aligned physical extents and consumer-specific neutral values when one padding/preparation cost is amortized across repeated consumers. Keep logical extents as separate metadata so padding changes storage and lowering, not public semantics.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/amortized_neutral_padding_layout.md`

#### `attention-intermediate-vector-work-reduction`

- Priority: normal
- Trigger: A first Cube operation such as QK produces a tile consumed by Vector scale, mask, normalization, or recurrence work before a second Cube operation such as PV can start.
- Summary: Shorten the serialized Cube producer -> Vector transformation -> Cube consumer path in a mixed attention kernel by removing, sharing, or reshaping intermediate Vector work between the two Cube operations. Treat every rewrite as a measured candidate because fewer source operations do not guarantee a shorter lowered path.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/attention_intermediate_vector_work_reduction.md`

#### `block-pointer-dimensionality`

- Priority: normal
- Trigger: Source semantics and physical strides define a rectangular tile with predictable offsets and contiguous or regularly strided axes.
- Summary: Use `tl.make_block_ptr` as a compiler-facing representation candidate when source semantics define a regular multidimensional tile but IR suggests that manual pointer expressions lower into unexpectedly scalarized, fragmented, strided, or transpose-heavy memory operations. Treat the rewrite as a heuristic experiment: confirm that it improves emitted transfer shape or address generation, then retain it only when correctness and benchmark evidence support it.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/block_pointer_dimensionality.md`

#### `coupled-tile-legality-ablation`

- Priority: normal
- Trigger: A larger tile would reduce repeated loop work, but the compiler rejects it during UB planning or lowering.
- Summary: When a valuable large tile fails UB planning, inspect the extra temporaries created by calculations on the large tile. Move an equivalent invariant calculation to a smaller input tile when that can reduce the size or lifetime of temporary values; use a paired compile and correctness experiment to determine whether this unlocks the large tile.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/coupled_tile_legality_ablation.md`

#### `cube-vector-intermediate-tile-orientation`

- Priority: normal
- Trigger: A mixed Cube/Vector kernel materializes a rectangular Cube-produced tile that Vector transforms before a later Cube consumer.
- Summary: Choose the orientation of Cube-produced rectangular intermediates that cross L0C-to-GM so Vector consumes a regular row-major tile along the fused scan axis, deferring any remaining transpose to the consumer Cube dots. The two orientations hold the same values; only fixpipe layout and Vector access order change.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/cube_vector_intermediate_tile_orientation.md`

#### `discrete-access-ub-staging`

- Priority: normal
- Trigger: The central bottleneck is discrete memory access that semantically looks like `out = x[idx]`.
- Summary: Stage a contiguous range into the Unified Buffer first, then use on-chip indexing (`tl.gather` or equivalent) to select target values, rather than loading directly from global memory through discrete indices. For fixed-channel AoS layouts, apply the same principle with channel-first SoA buffers to enable contiguous loads.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/discrete_access_ub_staging.md`

#### `effective-extent-tiling`

- Priority: normal
- Trigger: A **`BLOCK_*`** tile is much larger than the **valid extent** protected by a mask, so the kernel does visibly more padded lane work than useful work.
- Summary: Choose tile widths from the live logical extent on each axis instead of a legacy maximum or blanket power-of-two rule, so masked lanes do not dominate loop trip counts, transfer work, or vector-path work.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/effective_extent_tiling.md`

#### `exponential-base-convention-ablation`

- Priority: normal
- Trigger: Profile or IR evidence shows the special-function and associated scale/conversion chain on the measured critical path.
- Summary: Ablate complete natural-base (`exp`/`log`) and base-2 (`exp2`/`log2`) implementations of exponential normalization as coherent conventions. Keep scaling, recurrence formulas, saved state, backward reconstruction, and all fast and boundary paths in the same convention.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/exponential_base_convention_ablation.md`

#### `gqa-kv-shared-row-batching`

- Priority: normal
- Trigger: Attention inputs are already split-head (`[B, S, N_q, D]` and `[B, S_kv, N_kv, D]`), `N_q % N_kv == 0`, group size `G = N_q / N_kv > 1`.
- Summary: Batch independent query-row computations that share one KV head into the same program so each read-only K or V tile is loaded once while every row retains independent scores, normalization state, accumulator, and output ownership. In attention this can be decode row folding or a small query-head group inside separately materialized QK/PV stages.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/gqa_kv_shared_row_batching.md`

#### `implicit-transpose-elimination`

- Priority: normal
- Trigger: You implement GEMM / Linear-like kernels where one operand is stored as `[N, K]` but the math needs `[K, N]` (e.g. `y = x @ w.T`).
- Summary: Eliminate implicit transpose-style access on Ascend NPU by ensuring operands are in the physical layout the kernel needs, avoiding compiler-injected layout transforms.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/implicit_transpose_elimination.md`

#### `layout-materialization-elision`

- Priority: normal
- Trigger: The current implementation creates an intermediate tensor with `permute(...).contiguous()`, `transpose(...).contiguous()`, `movedim(...).contiguous()`, `clone()`, `copy_()`, or a Triton helper that exists only to produce a different physical layout.
- Summary: Avoid allocating and filling a temporary tensor only to change layout, such as after `permute`, `transpose`, or `movedim`, when the next step immediately consumes it. Have the producer write the needed layout directly or have the consumer use explicit strides, offsets, or block-pointer metadata.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/layout_materialization_elision.md`

#### `logical-layout-tiling`

- Priority: normal
- Trigger: The kernel is mostly data movement, not dense arithmetic or reduction.
- Summary: Replace scalar-heavy 1D linear-index traversal with layout-aware multidimensional tiles when the logical operation is an affine data movement.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/logical_layout_tiling.md`

#### `loop-invariant-hoisting`

- Priority: normal
- Trigger: The kernel has a hot inner loop (often a K loop in GEMM-like kernels).
- Summary: Apply **Loop-Invariant Code Motion (LICM)** to Triton kernels: move computations that do **not** depend on the loop induction variable out of the loop, so each iteration performs only the minimal work that truly varies.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/loop_invariant_hoisting.md`

#### `packed-key-argmax-single-reduction`

- Priority: normal
- Trigger: The hot loop extracts (extremum, first-index) **over a whole tile**: `tl.max` / `tl.argmax` / `tl.min(tl.where(v == mv, pos, N))` on an [M, N] or [K, N] tile, per tile or per extraction round.
- Summary: Any reduction that must emit an **extremum together with the position of its first occurrence** (argmax/argmin, top-k extraction rounds, cummin/cummax-style scans, pooling-with-indices) normally costs two reductions per extraction — one for the value, one for the index — or a slow tuple reduce. Instead, encode value and position into a **single order-preserving integer key** so that one `tl.max` yields both: the monotonic value bits occupy the high field, the inverted position occupies the low field, so key order equals value order and ties resolve to the smallest index for free, matching torch semantics.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/packed_key_argmax_single_reduction.md`

#### `padded-row-col-copy`

- Priority: normal
- Trigger: The operator is **constant pad**, **slice + pad**, or another **per-axis bounds** elementwise map (not gather).
- Summary: Rewrite flat 1D copy kernels over `numel(out)` into row–column tiled form to reduce scalar overhead from per-element coordinate reconstruction on the last dimension.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/padded_row_col_copy.md`

#### `program-multiple-rows`

- Priority: normal
- Trigger: The kernel is **naturally row-wise**: each output row depends mainly on one row of input (e.g. row-wise LogSumExp, row norms, row softmax statistics).
- Summary: Amortize per-program fixed costs and improve vector-friendly batching for **row-reduction or row-wise fused kernels** by mapping **multiple rows** to one Triton `program_id` via `BLOCK_M > 1`, instead of one row per program.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/program_multiple_rows.md`

#### `shift-2d-mask-to-1d-index-stream`

- Priority: normal
- Trigger: A shift relation is structurally "take previous element" or "take previous position in chunk", including cross-chunk lane-0 handling.
- Summary: When a hot shift or predecessor path is expressed as a 2D mask-and-reduce construction, rewrite it to a direct 1D index stream (`base + arange - 1`) with only boundary masking. This removes unnecessary 2D intermediates and keeps the shift path closer to one-dimensional vector loads and elementwise math on Ascend NPU; do not stop at replacing the reduce with an on-chip `tl.gather` if the final lane formula can be simplified further.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/shift_2d_mask_to_1d_index_stream.md`

#### `simt-clip-window-closed-reduction`

- Priority: normal
- Trigger: **SIMT active** (`force_simt_only=True` or documented SIMT round).
- Summary: **Inner-loop structural repair** for **fixed-window reductions** over **affine layouts** on **SIMT paths**: compute each output window's **clipped input bounds once**, use a **closed-form window volume** as normalizer (e.g. mean divisor), and iterate **absolute coordinates inside the clip** instead of scanning the full `KERNEL_*` cube with per-tap validity masks and runtime counting.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/simt_clip_window_closed_reduction.md`

#### `slice-coalesce`

- Priority: normal
- Trigger: Scatter or gather style data movement dominates, and batching work in UB could replace many random global accesses with fewer contiguous transfers.
- Summary: When indexed movement is dominated by small scattered transfers, use `extract_slice` or `insert_slice` to batch the side that can become contiguous. This can reduce global-memory transactions, but the final read/write direction still determines whether the transfer is actually coalesced.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/slice_coalesce.md`

#### `slice-intermediate`

- Priority: normal
- Trigger: Intermediate tensors, rather than just inputs or outputs, are the main source of UB pressure.
- Summary: When the kernel computation creates intermediate tensors that, combined with inputs and outputs, would exceed the Unified Buffer (UB) capacity (in attention mechanisms, batch normalization, etc), divide computation into several steps, and use `extract_slice` and `insert_slice` to read/write into UB.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/slice_intermediate.md`

#### `sliding-window-inner-w-slab-gather`

- Priority: normal
- Trigger: The kernel is a **fixed `KERNEL_W` window reduction** (mean, max, etc., **values only**) along **W** on a **contiguous** NCHW (or 5D) tensor, with **`kw`** in a **`tl.constexpr`** loop and **`BLOCK_OW`** output columns per program.
- Summary: For **fixed-window reductions** along the **innermost contiguous spatial dimension** (NCHW-style: often **W**), load one **slab** of length **`W_SLAB_LEN = STRIDE_W * (BLOCK_OW - 1) + KERNEL_W`** at **`w_abs_min = ow_pid * BLOCK_OW * STRIDE_W - PAD_W`**, then **`tl.gather(slab, STRIDE_W * arange(BLOCK_OW) + kw)`** per **`kw`** instead of many **`start_w + kw`** masked loads. Higher rank differs only in outer loops over remaining spatial axes. **Adoption gate:** hot path must show **`W_SLAB_LEN` load + gather**.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/sliding_window_inner_w_slab_gather.md`

#### `stencil-resize-gm-to-ub-staging`

- Priority: normal
- Trigger: Kernel is memory-bound; input read count scales with `(output pixels × stencil footprint)`.
- Summary: For 2D sampling kernels (resize, gather-stencil, pooling-like windows) whose hot path reads **multiple overlapping input samples per output point**, the core memory strategy is: **stage one contiguous input slab from global memory (GM) into on-chip buffer (UB) per program**, flatten it, then serve stencil reads via **UB-resident gather** and vector math. Secondary wins — often larger than tuning gather itself — are **eliminating UB internal densify copies**, **aligning slab row stride with gather indexing at allocation time**, **tightening slab bounds to the true input window**, and **enlarging the output tile to cut program count**. Prefer **2D output tiling** `(BLOCK_H, BLOCK_W)` over flattening the output plane onto a single 1D program axis.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/stencil_resize_gm_to_ub_staging.md`

#### `strided-layout-reduction`

- Priority: normal
- Trigger: The operator reduces exactly one logical axis.
- Summary: Avoid implementing a non-last-dimension single-axis reduction by first doing `movedim(...).contiguous()` or an equivalent layout materialization. For contiguous row-major input, compute `[outer, reduce, inner]` from the original shape and reduce directly from the original layout with a strided/tiled kernel.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/strided_layout_reduction.md`

#### `tiling`

- Priority: normal
- Trigger: Block sizes, live intermediates, or multi-tensor loads risk UB overflow or poor locality.
- Summary: Reduce per-program working-set size through hierarchical or sub-block tiling, keeping live data within UB capacity.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/tiling.md`

## 3. Refinement: Lowering, Boundaries, And Ablations

### High

#### `mask-only-affine-addressing`

- Priority: high
- Trigger: A pointer expression wraps otherwise affine offsets in `tl.minimum` / `tl.maximum` against `M - 1`, `N - 1`, or `K - 1` while the same `tl.load` or `tl.store` already carries a boundary `mask`, so the clamp protects nothing the predicate does not.
- Summary: Delete per-lane index clamps from pointer expressions whose load or store already carries a boundary mask, keeping raw affine offsets in the address and letting the predicate do the protecting. A clamp such as `tl.minimum(offs, N - 1)` makes the address data-dependent, so the compiler can no longer prove the tile is a contiguous slice and lowers it to an indirect/gather load whose cost scales with lane count instead of bytes moved. The rewrite is bit-exact and unconditional: valid lanes keep identical addresses, and `mask=0` lanes are never dereferenced.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/mask_only_affine_addressing.md`

#### `scalar-latency-trap-removal`

- Priority: high
- Trigger: Runtime values that are shape constants are passed as normal arguments instead of `tl.constexpr`.
- Summary: Remove scalarizing constructs that block vector hardware utilization on Ascend NPU, including unnecessary scalar control flow, loop-carried pointer recurrences, modulo addressing, narrow masks, and int64 arithmetic on vector paths.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/scalar_latency_trap_removal.md`

### Normal

#### `ascend-cv-compile-option-ablation`

- Priority: normal
- Trigger: The target is Ascend A5 and the Triton kernel uses `enable_dynamic_cv_pipeline`, mixed Cube/Vector work, or generated `ssbuffer` regions.
- Summary: The Ascend A5 Triton compilation path exposes controls that change Cube/Vector pipelining, HFusion vectorization, multi-buffer depth, and UB block planning. Treat these A5-only controls as version-qualified, independently ablatable scheduling transformations whose benefit depends on generated dataflow and on-chip resource pressure, rather than as universally beneficial performance flags.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/ascend_cv_compile_option_ablation.md`

#### `compile-hint`

- Priority: normal
- Trigger: The hot kernel is already structurally good, but lowering still appears conservative.
- Summary: Use compiler hints to communicate layout facts the compiler cannot safely infer from pointer math alone.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/compile_hint.md`

#### `diagonal-block-traversal`

- Priority: normal
- Trigger: Large tiled matrix-style work shows poor locality or bank-conflict-like behavior even though the basic tiling is already reasonable.
- Summary: This pattern changes which program owns each output tile within one existing launch. It may improve cache locality when neighboring programs repeatedly touch the same regions, but the cause and benefit are target-dependent; compare it with the existing traversal and do not treat it as a host launch-count change.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/diagonal_block_traversal.md`

#### `dot-operand-precision-ablation`

- Priority: normal
- Trigger: A `tl.dot` or equivalent Cube operation consumes matched FP32 operands or explicitly upcasts lower-precision source values before the dot.
- Summary: Ablate matched lower-precision `tl.dot` operands independently from accumulator, recurrence or epilogue, and output precision. Treat the lower-precision path as a measured, contract-gated candidate with a validated fallback, never as a default rewrite.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/dot_operand_precision_ablation.md`

#### `exact-tile-no-boundary-fast-path`

- Priority: normal
- Trigger: A dominant benchmark shape is exactly tile-divisible, such as `M % BLOCK_M == 0` and `N % BLOCK_N == 0`.
- Summary: Split exact-tile hot paths from generic masked kernels when dispatch-time shape guards can prove there are no tail tiles, so Ascend lowering can avoid boundary-only masks, padding values, block-pointer `boundary_check`, and related control branches.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/exact_tile_no_boundary_fast_path.md`

#### `fp16-hilo-compensated-mma`

- Priority: normal
- Trigger: A structural reduction rewrite (split-K/axis split, densify, head batching, online-softmax regrouping) changed the summation order, and the correctness gate now fails MERE/matched_ratio while max-abs error is only about 1 ulp. The reference computes softmax/PV in fp32, but the optimized kernel wants to stay on fp16/bf16 Cube dots. Naive bf16/fp16 probability quantization can pass an old vendor golden yet fail the pure-fp32 reference after regrouping.
- Summary: Approximate fp32 operands with rounded fp16 high and residual parts, then combine two or three native fp16 `tl.dot`s into an fp32 accumulator. This can keep a larger tile on the fp16 MMA path, but the residual is rounded and the result is valid only for a tested value range and accuracy contract.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/fp16_hilo_compensated_mma.md`

#### `merge-adjacent-stores`

- Priority: normal
- Trigger: Multiple stores target adjacent addresses but are emitted as separate small `tl.store` operations.
- Summary: Combine separate small `tl.store` operations into one wider store when the destination addresses form a continuous interval, so the NPU emits a single vector-friendly DMA write instead of multiple tiny transactions.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/merge_adjacent_stores.md`

#### `overlap-tail-load-mask-free`

- Priority: normal
- Trigger: Idempotent row/segment reductions where `BLOCK < extent <= 2 * BLOCK` and `extent % BLOCK != 0`, so the straightforward kernel masks its final tile. For larger extents, keep all full middle tiles and overlap only the final partial tile.
- Summary: When a **row- or segment-wise idempotent reduction** (max, min, argmax, argmin, any, all) has `BLOCK < extent <= 2 * BLOCK` with `extent % BLOCK != 0`, cover it with two **unmasked** loads — a main tile `[0, BLOCK)` and an overlapping tail tile `[extent-BLOCK, extent)` — instead of one masked tail tile. For larger extents, keep the full middle tiles and overlap only the final partial tile. Overlapped elements participate twice, which is harmless because idempotent reductions tolerate duplicates and position-aware tie-breaking (`smaller pos wins`) preserves the true first occurrence. This removes the masked-load lowering (conditional whole-tile fill plus copy on Ascend) from the hot path.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/overlap_tail_load_mask_free.md`

#### `parallel`

- Priority: normal
- Trigger: Two independent vector-side computations happen in sequence and can be split across vector cores.
- Summary: Use `tl.parallel` to run tasks in the two vector cores of an aicore at the same time.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/parallel.md`

#### `reorder-load`

- Priority: normal
- Trigger: A hot kernel has multiple semantically independent loads whose placement can change without changing addresses, masks, or values.
- Summary: Test alternative source placements for independent loads as compiler scheduling hypotheses. Emitted transfer order and coordination, together with measured latency, decide whether a candidate helps.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/reorder_load.md`

#### `schedule-coupled-tile-transplant`

- Priority: normal
- Trigger: A vendor library, compiler-generated kernel, or another proven implementation exposes a promising tile for the same logical contraction or reduction.
- Summary: A tile size from an optimized reference is only one candidate. Treat it as part of a set of coupled schedule components: transfer its reduction width, buffering, traversal, physical mapping, accumulator split, and epilogue as separate experiments; an M/N/K tuple alone is not a portable tuning rule.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/schedule_coupled_tile_transplant.md`

#### `software-pipeline`

- Priority: normal
- Trigger: A hot tiled loop has independent next-tile transfer and enough work that overlap may matter.
- Summary: Inspect compiler-generated buffering and transfer-compute coordination in regular tiled loops. Treat manual carry or textual prefetch as a scheduling ablation, and retain it only when generated scheduling evidence and benchmarks attribute a real improvement.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/software_pipeline.md`

#### `vec-cmp`

- Priority: normal
- Trigger: Explicit `i64` or `i32` comparisons appear on the hot path outside the compiler's normal fast load/store mask cases.
- Summary: Rewrite explicit integer compare-heavy logic into a form that is more vector-friendly on Ascend NPU, especially when scalarized compares are blocking fast masking or selection.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/vec_cmp.md`

## 4. Autotune: Final Parameter Search

Run bounded parameter search only after the earlier stages have been scanned and explicit structural candidates have been evaluated.

### High

#### `autotune`

- Priority: high
- Trigger: The kernel structure already looks semantically correct, and the likely headroom is in `BLOCK_*` selection, split shape, or Ascend-specific compile options such as `multibuffer`.
- Summary: Use Triton-Ascend autotune as the default way to search split sizes, tile sizes, and selected compile options when the kernel structure is already reasonable and the main open question is parameter choice.
- Source: cannbot-knowledge `knowledge/ops/triton/optimizations/patterns/autotune.md`
