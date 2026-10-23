# Convolution — standard, depthwise, transposed, and causal convolutions

## Scope

Convolution operators: standard `conv1d/2d/3d` (with groups), depthwise
(`groups == channels`), transposed convolutions, 1×1 convolutions, and the
small-kernel causal depthwise conv1d that precedes SSM blocks. The projection
GEMMs around a conv and the general GEMM contract are [matmul.md](matmul.md);
element-wise epilogues follow [elementwise.md](elementwise.md). This card owns
the conv-specific structure: tap decomposition, receptive-field access,
padding, group handling, and the transposed-conv equivalence.

## Writing essentials

- Weights are initialized by hand on the CPU, replicating
  `nn.Conv*.reset_parameters`: `torch.empty` + `uniform_` on CPU, then
  `.to(device)` — all weights first, then all biases, in that order. Never
  run `uniform_` on the NPU (its RNG sequence differs from the CPU's at the
  same seed, so the golden and the implementation would see different
  weights), and never instantiate an `nn.Conv*` module to obtain weights.
- `fan_in` differs by family and decides the bound
  (`bound = 1 / sqrt(fan_in)`, `uniform_(-bound, bound)`): standard
  `(C_in // groups) * Π(kernel_size)`; depthwise degenerates to
  `Π(kernel_size)`; transposed conv uses `out_channels * Π(kernel_size)` —
  the opposite side of its `(in_channels, out_channels, K_H, K_W)` weight.
  Writing the standard formula for a transposed conv shifts every weight.
- Dispatch on the host by `(kernel size, stride, groups, channels per
  group)` into specialized paths, each preparing its own data layout — one
  mega-kernel cannot hold a resident accumulator per path in on-chip memory.
  The recurring route set:
  - `K == 1`, stride 1, no padding, groups 1: the conv is exactly a GEMM —
    view the input as `(C_in, spatial)` and follow [matmul.md](matmul.md);
    no conv-specific kernel.
  - standard conv, stride 1: decompose the K taps into K shifted 1×1
    convolutions. Each tap's input columns are contiguous, so one
    `tl.make_block_ptr` load per tap feeds a `tl.dot` into a single
    accumulator — no im2col materialization. Dilation only shifts the tap
    start.
  - standard conv, stride > 1: sampled columns are strided, and strided
    loads mis-compile as dot operands. Materialize a contiguous im2col
    first (gather on the load side, contiguous on the store side), then
    GEMM with the reduction dim padded to a multiple of the Cube native
    width (16). The im2col reduction order must equal the weight flatten
    order (tap outer, channel inner).
  - depthwise (no cross-channel reduction): an element-wise vector path —
    never `tl.dot`, which wastes most of the matrix unit's minimum tile.
    Per-tap vector multiply-accumulate over `[BLOCK_C, BLOCK_W]` tiles,
    weights pre-laid-out tap-major so each tap's channel weights are one
    contiguous load.
- Stride-2 vectorized input loads are forbidden in every form (masked or
  not, block pointer or computed pointer) — this backend mis-compiles them.
  The safe structure is a host-side column-parity split: deinterleave the
  padded input into even/odd column planes; the parity of a sampled column
  depends only on the kernel column index (a compile-time constant), so the
  kernel selects the plane with an affine offset and reads stride-1 within
  it.
- Gate every path that pays host preprocessing (pre-padding, re-layout,
  deinterleave) on the case's arithmetic volume — the fixed launch overhead
  dominates small cases, which should fall back to a masked-load path with
  no preprocessing. After enlarging tiles, check the tile count still
  matches the core-count order; if blocking collapsed parallelism, fall
  back to smaller tiles.
- Padding is best paid on the host as pre-zero-fill (`torch.zeros` +
  interior `copy_`, or a dedicated pad kernel) so in-kernel offsets are
  always non-negative and every load is a plain affine access: block-pointer
  `boundary_check` on a negative offset zeroes the *whole block*, not the
  out-of-range elements, and fails exactly at the borders. Build the padded
  buffer for the maximum window coordinate and pad `K_dim` to the 16
  multiple there, once.
- Clamps never enter load address expressions — a clamped offset breaks the
  affine address analysis and the load scalarizes. Handle boundaries with
  host pre-padding; if a defensive clamp is unavoidable (keeping the
  address legal), the values still come from the mask, not the clamp.
- `tl.dot` operands come from `tl.make_block_ptr` (or a `tl.where`-
  materialized equivalent). Ptr-arith addresses, masked loads, clamped
  addresses, and the direct outputs of `reshape`/`trans`/`split` fed into
  `tl.dot` mis-compile or abort compilation. The block pointer's contiguous
  axis must genuinely have unit stride and `order` must match the real
  strides — a mismatch is silent wrong values that happen to look right at
  offset 0. No 3D batched `tl.dot`. No runtime predicate around a dot
  (`if valid: acc = tl.dot(...)`) — a compile-time `tl.constexpr` branch,
  or an unconditional dot with masked loads.
- In kernels without dots (pad, copy, re-layout), use plain pointer
  arithmetic and masked loads instead of block pointers: block pointers
  with an odd first-dimension base address read intermittently wrong data
  on this backend, and for these kernels the pointer-arith form costs
  nothing.
- Host-side rectangular slice copies, strided-view copies, and channel
  reorders fall onto a slow scalar copy path. Replace them with dedicated
  row-contiguous copy kernels (row-contiguous direction compiles to vector
  access; column-direction strided access scalarizes), and fuse multi-stage
  preprocessing into one kernel.
- Transposed conv is an equivalence, not a new algorithm: dilate the input
  with zeros, pad by `K - 1 - P`, and run a stride-1 standard conv against
  spatially *flipped* weights. The flip happens inside the Triton kernel
  (read at `KH - 1 - kh`), never as a host `torch.flip`. The output is
  allocated at the exact `out_channels` and written directly through a UB
  transpose (`tl.trans`) plus a block-pointer store whose `shape` carries
  the exact channel count — never a padded channel workspace trimmed by a
  host slice afterwards.
- Groups are decoded per output channel: `g = co // C_out_per_group`;
  input uses group-relative indices plus the group start, weights use
  global `co` with group-local `ci`. A unified GEMM across group boundaries
  computes wrong output channels. A block-pointer store only truncates at
  the total channel count, not at the group boundary: full tiles (block ==
  channels per group) may block-store; partial tiles use masked scalar
  stores without extra pointer clamping.
- Every kernel: 1D grid clamped to the core count (a device property) with
  an in-kernel stride loop, and no `while`. Choose the tile-decode order
  and the partition (contiguous tile ranges per program rather than
  strided interleave) by what adjacent programs should reuse — the
  output-channel block innermost makes neighbors share one input tile;
  innermost output-column blocks make neighbors share one weight tile.
- Device-side weight transforms (transpose, flip, pack, zero-pad to the
  16 multiple) run once and are cached per instance, keyed by the source
  weight identity (`data_ptr()` of a cached reference) or the full conv
  configuration — two configurations can share shapes with different
  weights, and a shape-only key serves one config's transformed weights to
  the other. Module-level caches leak across instances and produce
  run-order-dependent accuracy failures.
- Prefer a deterministic host heuristic for the main kernel's block sizes
  over `@triton.autotune` (its timing probes add run-to-run noise);
  autotune is acceptable only for kernels that run once per cache miss.
  Any split accumulation follows [reduction.md](reduction.md): output
  zero-initialized, every chunk `tl.atomic_add` (never a plain store for
  chunk 0 with atomics after — that races), bias added on one designated
  split only. Dots use `input_precision="ieee"` with fp32 accumulators;
  weight dtype aligns to the input dtype; a missing bias is a dummy tensor
  plus a `tl.constexpr` flag, never `None`.
- A kernel-size dimension of 1 is explicit coordinate arithmetic, never a
  `for k in range(1)` loop. Batch offsets use the per-batch plane volume
  (`n * C*D*H*W`), never `n * N*C*D*H*W`, which skips past the whole batch.

## Writing essentials — causal depthwise conv1d (SSM-style)

- Fixed small window (W of 2–8), depthwise over channels: keep the window
  in registers. Load the first W−1 elements (from zero padding at the
  sequence start, or from a carried conv state), then per time step load
  only the new element and shift — W−1 of the W loads per step disappear.
  W must be a `tl.constexpr` small enough for the whole window plus one
  BLOCK_D tile to stay in registers; larger windows fall back to
  re-loading the window per step.
- Choose the layout so the dimension iterated per token is the contiguous
  one (per-token processing wants all channels of one token in one
  contiguous load; short-sequence batched processing wants the same for the
  time axis), and hoist loop-invariant address components (base + offset +
  channel offsets) out of the time loop — only `+ t * stride` remains
  inside.
- Time tiling overlaps: adjacent time tiles share W−1 elements so the
  convolution window stays continuous across the boundary; only the first
  tile reads the carried state. Fuse the epilogue (bias register-resident,
  activation computed on the fp32 accumulator — a low-precision `exp`
  overflows for negative inputs) behind `tl.constexpr` switches so unused
  code compiles out.
- Variable-length batches with padding slots skip padded work items by
  folding one validity check (slot id from a metadata tensor) into every
  mask in the kernel — never an early `return`, which this backend's JIT
  does not support. Concurrent state updates write a separate buffer that
  the host copies back afterwards, so programs never race on the shared
  state. Manual unrolling of the tap loop into independent expressions
  trades block loads for scalar loads and raises register pressure — keep
  the loads vectorized.

## Common mistakes and fixes

```python
# Wrong: weights drawn from the NPU RNG (or an instantiated nn module)
w = torch.empty(shape, device="npu").uniform_(-b, b)
# Right: CPU empty + uniform_, then .to(device); weights then biases

# Wrong: transposed-conv bound from in_channels
fan_in = in_channels * KH * KW
# Right: fan_in = out_channels * KH * KW      # opposite face of the weight

# Wrong: host flip for the transposed-conv equivalence
w = torch.flip(w, dims=[2, 3])
# Right: read at KH - 1 - kh / KW - 1 - kw inside the kernel

# Wrong: depthwise conv through the matrix unit
acc = tl.dot(x_tile, w_tile)                  # no cross-channel reduction
# Right: per-tap vector multiply-accumulate over [BLOCK_C, BLOCK_W] tiles

# Wrong: while loop over the reduction
while k0 < K_DIM: ...; k0 += BLOCK_K
# Right: for k0 in range(0, K_DIM, BLOCK_K)   (repair §18)

# Wrong: trusting boundary_check with negative offsets
tl.advance(xp, (oh - P,))                     # border block reads all-zero
# Right: host pre-pads so every offset is >= 0

# Wrong: runtime predicate around the dot
if tile_valid: acc = tl.dot(a, b)
# Right: tl.constexpr branch, or unconditional dot with masked loads

# Wrong: strided (stride>1) input load straight into tl.dot
x = tl.load(x_ptr + (l * stride + k)[None, :] + c[:, None] * W)
# Right: materialize contiguous im2col, or host-reorder, then GEMM

# Wrong: stride-2 vectorized input load (any form)
x = tl.load(x_ptr + 2 * offs)                 # mis-compiles on this backend
# Right: host parity-plane split; stride-1 affine access inside each plane

# Wrong: clamp inside a load address
addr = x_ptr + tl.maximum(ih, 0) * W + iw
# Right: host pre-pad removes boundaries; masks zero values, not addresses

# Wrong: batch offset through the batch dimension too
base = x_ptr + n * N * C * D * H * W
# Right: base = x_ptr + n * (C * D * H * W)   # per-batch plane volume

# Wrong: chunk 0 stored, later chunks atomic
if k_split == 0: tl.store(out, acc)
else: tl.atomic_add(out, acc)                 # races chunk 0
# Right: zero-init output; all chunks atomic_add; bias on one split only

# Wrong: module-level weight-transform cache
_CONV_CACHE[k] = transform(w)                 # shape-only key, shared
# Right: per-instance cache keyed by weight data_ptr() or full conv key

# Wrong: slicing a loaded receptive-field tensor
rf = tl.load(rf_ptr, boundary_check=(0, 1))
v = rf[:, kh, kw]                             # unsupported tensor index: slice
# Right: one block_ptr load per (kh, kw) from global memory

# Wrong: reshape/split output fed directly to tl.dot
a = tl.split(reshape(pair, (R, J, 2)))
acc = tl.dot(a, b)                            # layout metadata ignored
# Right: a = tl.where(mask, a, 0) to materialize, or block_ptr loads

# Wrong: im2col reduction order different from the weight flatten order
# Right: both (kh * KW + kw) * C_in_pg + ci — tap outer, channel inner

# Wrong: single dot per tap when BLOCK_K < C_in
acc = tl.dot(w_k, x_k)                        # tail of C_in never reduced
# Right: for c0 in range(0, C_IN_PG, BLOCK_K): acc = tl.dot(w, x, acc)

# Wrong: padded channel workspace trimmed by a host slice
out = out_pad[:, :out_channels].contiguous()
# Right: allocate exact out_channels; block_ptr store masks the last tile
```

## Recommended patterns

Stride-1 standard conv as K shifted 1×1 dots (contiguous per-tap columns,
device-transposed weights so the reduction axis has unit stride):

```python
@triton.jit
def conv_tap_dot_kernel(x_pad_ptr, w_t_ptr, b_ptr, y_ptr, ...strides...,
                        C_OUT_PG: tl.constexpr, C_IN_PG: tl.constexpr,
                        L_OUT: tl.constexpr, K: tl.constexpr,
                        BLOCK_M: tl.constexpr, BLOCK_N: tl.constexpr,
                        BLOCK_K: tl.constexpr):
    pid = tl.program_id(0)
    for t in range(pid, TOTAL_TILES, NUM_PROG):
        n, g, m0, l0 = decode(t)                  # scalar decode, host-folded
        acc = tl.zeros((BLOCK_M, BLOCK_N), tl.float32)
        for k in tl.static_range(K):              # taps, compile-time unrolled
            for c0 in range(0, C_IN_PG, BLOCK_K): # full reduction coverage
                x = tl.make_block_ptr(x_pad_ptr + x_base(n, g),
                                      shape=(C_IN_PG, L_OUT),
                                      strides=(L_PAD, 1),
                                      offsets=(c0, l0 + k),
                                      block_shape=(BLOCK_K, BLOCK_N),
                                      order=(1, 0))
                w = tl.make_block_ptr(w_t_ptr + g * W_GRP + k * C_IN_PG,
                                      shape=(C_OUT_PG, C_IN_PG),
                                      strides=(K * C_IN_PG, 1),
                                      offsets=(m0, c0),
                                      block_shape=(BLOCK_M, BLOCK_K),
                                      order=(1, 0))
                acc = tl.dot(w, x, acc, input_precision="ieee")
        acc = acc + tl.load(b_ptr + g * C_OUT_PG + m0 + offs_m,
                            mask=offs_m < C_OUT_PG, other=0.0)[None, :]
        tl.store(y_ptrs_exact(n, g, m0, l0), acc.to(OUT_DTYPE),
                 mask=(offs_m < C_OUT_PG)[:, None] & (offs_n < L_OUT)[None, :])
```

(The host pre-pads `x` once so `offsets=(c0, l0 + k)` never goes negative;
`x_base`/`y_ptrs_exact` are host-folded index math with int64 flat bases.)

Causal depthwise conv1d, register window, one new load per token:

```python
@triton.jit
def causal_conv1d_kernel(x_ptr, w_ptr, b_ptr, y_ptr, T, D,
                         HAS_BIAS: tl.constexpr, ACT: tl.constexpr,
                         BLOCK_D: tl.constexpr, OUT_DTYPE: tl.constexpr):
    # x, y: [N, T, D], D contiguous; W = 4 specialized; window in registers
    pid = tl.program_id(0)                        # task = (batch, d-tile)
    for task in range(pid, TOTAL_TASKS, NUM_PROG):
        n = task // NUM_DTILES                    # scalar division only
        d = (task - n * NUM_DTILES) * BLOCK_D + tl.arange(0, BLOCK_D)
        m = d < D
        base = x_ptr + n.to(tl.int64) * T * D + d # invariant: hoisted (LICM)
        c0 = tl.load(base, mask=m, other=0.0).to(tl.float32)
        c1 = tl.load(base + D, mask=m, other=0.0).to(tl.float32)
        c2 = tl.load(base + 2 * D, mask=m, other=0.0).to(tl.float32)
        w0 = tl.load(w_ptr + 0 * D + d, mask=m, other=0.0).to(tl.float32)
        # ... w1, w2, w3 likewise; bias loaded once before the loop
        for t in range(T):                        # one new element per token
            c3 = tl.load(base + (t + 3) * D, mask=m, other=0.0).to(tl.float32)
            acc = c0 * w0 + c1 * w1 + c2 * w2 + c3 * w3     # fp32 FMA
            if HAS_BIAS:                          # constexpr switch
                acc = acc + bias
            if ACT:
                acc = acc / (1 + tl.exp(-acc))    # fp32 activation
            tl.store(y_ptr + n.to(tl.int64) * T * D + t * D + d,
                     acc.to(OUT_DTYPE), mask=m)
            c0 = c1; c1 = c2; c2 = c3            # register shift
```

(Padded work items fold `slot != pad_id` into `m` — no early `return`.)

Negative static offsets, int32/int64 flat bases, receptive-field tiles past
the on-chip budget, and unsupported `while`/`return`: see repair guide
`triton-npu-repair-guide/references/repair-experience.md` §13, §14, §16,
§18.
