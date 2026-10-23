# Interpolate and pad — resampling, padding, and repetition

## Scope

Shape-changing tensor transforms: `interpolate`/upsample/downsample (nearest,
bilinear, bicubic, area; `align_corners` both ways), `pad` (constant,
reflect, replicate, circular), `repeat` / `repeat_interleave`, and tile
expansions. Two sub-families with opposite concerns: interpolate is
compute-class (sampling coordinates and weight arithmetic decide correctness
and speed), pad/repeat are memory-class (contiguous copies with almost no
math). Do not cross their techniques: no sampling tricks in a pad copy, no
copy tricks in a resampler. Data-dependent index movement is
[indexing.md](indexing.md); layout permutation without shape change is
[layout-transform.md](layout-transform.md).

## Writing essentials — interpolate

- Dispatch on the host by `(mode, align_corners, ratio)` into specialized
  kernels; a single generic kernel handling every mode pays full coordinate
  decode on every path and is the fallback only. The specializations worth
  writing as separate kernels: integer-ratio upsample, integer-ratio
  downsample, and the general path per mode.
- Integer-ratio resamples are copies, not gathers. 2× nearest upsample
  replicates each pixel block with a reshape-broadcast
  (`[a, b, c] → [a, a, b, b, c, c]` via `reshape(BLOCK, 1)` expansion);
  0.5× downsample is a strided load (step 2); bilinear with
  `align_corners=False` at exactly 0.5× degenerates to a 2×2 average pool —
  one contiguous load of `2 * BLOCK_W` elements, `reshape(BLOCK_W, 2)`, then
  sum, never discrete `x0 = 2*w, x1 = x0+1` strided loads.
- Reproduce the reference's coordinate mapping exactly:
  `align_corners=False`: `src = scale * (dst + 0.5) - 0.5` with
  `scale = src_size / dst_size` in float; `align_corners=True`:
  `src = dst * (src_size - 1) / (dst_size - 1)`. Compute `scale` once on the
  host (fp32) and pass it in — the kernel then does only multiply/add. When
  verification fails only on low-precision `align_corners=True` shapes,
  suspect the scale division itself: the reference's device division and a
  host fp32 division can differ in the last unit — compute the scale by the
  same division path the reference uses.
- `tl.cast` to int truncates toward zero, it does not floor. Where
  `src < 0` (first row/column of `align_corners=False` upsampling), correct
  the index (`y0 = tl.where(src_y < y0_f, y0 - 1, y0)`) before computing the
  interpolation fraction. Clamp neighbor indices to `[0, size - 1]` the way
  the reference does — its boundary cases may adjust both neighbors and
  recompute weights, not just clip addresses.
- Bicubic: the reference kernel is Keys' bicubic with `A = -0.75` — not
  Catmull-Rom — with the piecewise weight selected by nested `tl.where`
  (`tl.where(t < 1.0, w1, tl.where(t < 2.0, w2, 0.0))`; `if` does not work on
  vector data). After boundary clamping, the 4×4 neighborhood reuses pixels,
  so weights no longer sum to one: accumulate the used-weight sum alongside
  the value and divide at the end. Where the reference accumulates the 16
  terms in scalar order (typical for `align_corners=True`), accumulate
  term-by-term in the same order — vectorizing the sum changes the
  association and fails bit-sensitive verification.
- Nearest rounding follows the reference's path split: with an output `size`
  given, the source index is integer arithmetic
  (`h_out * H_in // H_out`); with a `scale_factor`, it is the cast of the
  float mapping. Do not share one formula for both.
- Vector loads need compile-time-constant widths: `tl.arange(0, W)` with a
  runtime `W` becomes a dynamic-shape load that degrades to scalar access.
  Pad row widths up to a power of two (`MAX_IN_W = next_power_of_2(W_in)`,
  capped by the on-chip memory budget) passed as `tl.constexpr`, and mask the
  tail.
- Scattered vector loads (one vector whose lanes index across different
  rows/channels) are not a usable fast path on this backend: for
  coordinate-heavy modes the working structure is a block-strided outer loop
  (`for block_start in range(pid * BLOCK, total, num_programs * BLOCK)`)
  with per-pixel scalar coordinate math inside — regular vector loads/stores
  at the block level, scalar math at the pixel level.
- Upsampling reuses input rows across output rows: block vertically (a small
  output-row group loading its shared input rows once) rather than one load
  per output row. Horizontal coordinates are identical for every output row —
  precompute the `x0`/`x1`/`lambda` tables on the host once and pass them as
  tensors; recomputing the cast/floor/where chain per tile per row is wasted
  work.
- Keep the loop-carried variables type-stable: a variable that starts scalar
  and is assigned a vector inside a loop is a compile error
  (`Loop-carried variable ... initial type ... but re-assigned to ...`) — use
  fresh names for vector temporaries. `@triton.jit` forbids nested function
  definitions (inline the helper) and `float()` on loop variables (they are
  already scalars). No `break` — fixed ranges with masks (repair guide §18).
- `forward()` computes shapes, dispatches, and does the host-side
  precomputation; every pixel-level computation lives in a kernel. Grid is
  `min(total_rows, core_count)` with the core count read once from device
  properties, never a hardcoded constant.

## Writing essentials — pad and repeat

- Constant pad splits into fill + copy: `output.fill_(value)` (or an
  equivalent fill kernel), then a copy kernel that moves only the valid
  interior with plain vector loads/stores and no per-element `if in_bounds`
  branch. Non-constant modes (reflect/replicate/circular) are row-wise
  boundary mappings: `in = out - pad_low`, negative → `-in`, past-the-end →
  `2 * (dim - 1) - in` (reflect), clamp (replicate), modulo (circular) — and
  do the comparisons in fp32 (`in.to(tl.float32) < 0`), since integer
  compares degrade on this backend.
- Compress dimensions on the host before launching: squeeze leading size-1
  dimensions (adjusting the pad specification to match) and specialize by
  resulting rank and mode; the fully general N-D pad kernel is the fallback
  only.
- Distribute work by output elements, not input: memory-bound transforms
  have a bigger output than input (or reordered); each program owns a
  contiguous output range, balanced so program block counts differ by at most
  one (`blocks_per_core`, first `remainder` programs take one extra).
  `torch.repeat` (whole-tensor repetition per dimension) and
  `repeat_interleave` (each element repeated along one dimension) are
  different operators with different structures — identify which one the
  reference is before writing.
- Multi-dimension `torch.repeat` processes one dimension per kernel, from the
  lowest dimension up, as an outer×inner contiguous copy: each program loads
  a contiguous inner segment once and stores its `r` copies back-to-back
  (`r` a `tl.constexpr`, so the copy loop unrolls at compile time); the
  copies land consecutively in the output. A single flattened kernel walking
  all dimensions at once, or a slice path storing copies far apart (strided
  writes), is the structure to avoid.
- Never apply `//` or `%` to a vector produced by `tl.arange`: integer vector
  division compiles to a scalar loop, one division per lane. Do the division
  on scalar loop/block indices (`outer = block_idx // num_inner_blocks`,
  `local = block_idx - outer * num_inner_blocks`) and keep the vector
  arithmetic pure add/multiply, or use a reshape-broadcast instead of the
  division. `repeat_interleave`'s `in = out // repeats` mapping follows the
  same rule (scalar indices or a precomputed lookup; variable repeat counts
  go through a prefix-sum table built once).
- Convert `tl.program_id` and `tl.arange` results to `tl.int32` for
  addressing, keep the input `.contiguous()` on the host, and choose blocks
  as powers of two sized near the actual extent — very large fixed blocks
  (tens of thousands of elements) can fail compilation; treat the on-chip
  memory budget as the ceiling.

## Common mistakes and fixes

```python
# Wrong: one generic kernel for every interpolate mode
if mode == 0: ... elif mode == 1: ...   # runtime dispatch inside
# Right: host routes (mode, align_corners, ratio) to specialized kernels

# Wrong: gather for an exact 2x nearest upsample
out = tl.load(x_ptr + (h // 2) * W + w // 2)
# Right: reshape-broadcast replication of each pixel pair (contiguous)

# Wrong: four discrete loads for a 2x2 pool
a = tl.load(p + 2*w); b = tl.load(p + 2*w + 1); ...
# Right: one contiguous load of 2*BLOCK, reshape (BLOCK, 2), tl.sum

# Wrong: truncating cast used as floor for negative source coords
y0 = tl.cast(src_y, tl.int32)                  # src_y < 0 truncates to 0
# Right: y0 = tl.where(src_y < y0_f, y0 - 1, y0) after the cast

# Wrong: Catmull-Rom weights for a Keys' bicubic reference
# Right: A = -0.75 Keys' kernel, tl.where piecewise, w_sum normalization

# Wrong: runtime-width vector load
row = tl.load(x_ptr + tl.arange(0, W))         # W runtime → scalar loop
# Right: MAX_IN_W: tl.constexpr = next_pow2(W); masked load

# Wrong: pad constant via per-element branch
v = tl.where(in_bounds, x, fill_value)         # branch per element
# Right: fill the whole output first; copy kernel moves the valid interior

# Wrong: integer coordinate compare directly
tl.where(coord < 0, -coord, coord)
# Right: compare in fp32 — .to(tl.float32) < 0 — then map

# Wrong: vector division for repeat mapping
src = tl.load(x_ptr + offs // r)               # vector // → scalar loop
# Right: scalar block indices decomposed, or reshape-broadcast expansion

# Wrong: repeat copies stored strided
for i in range(r): tl.store(out + i * stride_far + offs, v)
# Right: consecutive copies — out_base + i * inner_size + offs, r constexpr

# Wrong: scalar promoted to vector across a loop
w = 0.0
for k in range(4): w = w + wx[k] * val         # w becomes a vector
# Right: fresh names for vector temporaries; initialize with the right type
```

## Recommended patterns

Bilinear row resample with host-precomputed horizontal coordinates:

```python
@triton.jit
def bilinear_row_kernel(x_ptr, y_ptr, x0_ptr, x1_ptr, lam_ptr,
                        H_in, W_in, W_out, scale_h,
                        BLOCK_W: tl.constexpr, MAX_IN_W: tl.constexpr):
    plane = tl.program_id(0).to(tl.int32)         # one output (n, c) plane
    h = tl.program_id(1).to(tl.int32)             # one output row
    src_y = (h.to(tl.float32) + 0.5) * scale_h - 0.5
    y0 = tl.cast(src_y, tl.int32)
    y0 = tl.where(src_y < y0.to(tl.float32), y0 - 1, y0)   # floor fix
    y0 = tl.maximum(tl.minimum(y0, H_in - 1), 0)
    y1 = tl.minimum(y0 + 1, H_in - 1)
    wy = src_y - y0.to(tl.float32)
    w = tl.arange(0, BLOCK_W)
    m = w < W_out
    x0 = tl.load(x0_ptr + w, mask=m, other=0).to(tl.int32)   # host tables
    x1 = tl.load(x1_ptr + w, mask=m, other=0).to(tl.int32)
    lam = tl.load(lam_ptr + w, mask=m, other=0.0)
    p00 = tl.load(x_ptr + row(y0) + x0, mask=m, other=0.0).to(tl.float32)
    # ... three more corner loads (y1 row, x1 column); bilinear blend in
    # fp32; store. row(y) = (plane * H_in + y) * W_in.
```

(The host builds `x0`/`x1`/`lam` once per `(W_in, W_out)` and caches them;
vertical blocking loads the shared input rows per output-row group.)

Repeat as an outer×inner contiguous copy, one dimension at a time:

```python
@triton.jit
def repeat_kernel(x_ptr, y_ptr, inner_size,
                  R: tl.constexpr, BLOCK: tl.constexpr):
    outer = tl.program_id(0).to(tl.int32)
    blk = tl.program_id(1).to(tl.int32)
    offs = (blk * BLOCK + tl.arange(0, BLOCK)).to(tl.int32)
    m = offs < inner_size
    v = tl.load(x_ptr + outer * inner_size + offs, mask=m, other=0.0)
    for rep in range(R):                          # constexpr, unrolled
        base = outer * inner_size * R + rep * inner_size
        tl.store(y_ptr + base + offs, v, mask=m)
```

Broadcast shape errors from reshape-broadcast expansions, negative static
offsets in boundary mappings, and int32/int64 address arithmetic: see repair
guide `triton-npu-repair-guide/references/repair-experience.md` §17, §13,
§14.
