# Layout transform — permutation, transpose, and block-indexed copies

## Scope

Operators that only change the data layout: `permute`/`transpose` (2D,
batched, swapping adjacent dimensions, flipping/reversing), reshapes that
force a contiguous copy, and paged or block-table scatter-copies (for
example writing KV tokens into a paged cache through precomputed metadata).
Consume-a-transpose-inside-a-GEMM is different — [matmul.md](matmul.md) covers
stride-fed transposes; shape-changing resample/pad/repeat is
[interpolate-pad.md](interpolate-pad.md); data-dependent index movement is
[indexing.md](indexing.md). Here the reordering itself is the operator.

## Writing essentials

- Short-circuit views before launching anything: an identity permutation, or
  one that only moves size-1 dimensions, is `x.view(out_shape)` — no output
  allocation, no kernel. Every real launch should be behind these checks.
  Beyond that, the core data movement lives in `@triton.jit` kernels —
  calling `torch.permute`/`x.t()`/`.contiguous()` in `forward()` to do the
  work is the failure this category exists to avoid.
- Merge still-contiguous dimensions on the host to lower the effective rank
  before specializing: `[A, B, M, N] → [A, B, N, M]` becomes
  `view(A*B, M, N)` and a batch transpose; the kernel then handles the
  smallest rank that expresses the permutation.
- Specialize by permutation pattern, with a generic fallback in the last
  branch only: dedicated kernels for 2D transpose, batch transpose,
  swap-adjacent-dims, and reverse; a 1D gather/scatter kernel for
  unrecognized permutations, written correctness-first. One generic scalar
  gather serving every input is the anti-pattern. Route degenerate shapes
  down (a batch size of 1 goes to the plain 2D kernel).
- A specialized kernel is tile-based or it is not specialized: regular 2D
  tile loads from the input layout and tile stores to the output layout
  (store the transposed tile, with the output's own strides), both tile
  dimensions masked at the extent. Element-wise `//`/`%` index decode or
  `tl.where` chains inside a "specialized" kernel forfeit the point. Pass
  input and output stride sets separately — they differ by construction
  here.
- Clamp the grid to the core count and walk extra tiles with an in-kernel
  strided loop (`for t in range(pid, num_tiles, num_programs)`), expressed as
  a fixed-trip `for` — `while` loops are not supported (repair guide §6, §18).
- Paged/block-table copies are layout transforms with indirection: the work
  item is (chunk, head); each program scalar-loads its chunk metadata (source
  start, destination block, offset, length), then moves the chunk as
  `[CHUNK, D]` 2D masked tiles so the head/inner dimension stays one
  contiguous vector access per row. Multiple tensors sharing the layout
  (K and V) share one kernel and the same tile arithmetic. Choose the tile
  width against the actual chunk lengths as a power-of-two `tl.constexpr` —
  a wide fixed tile wastes lanes on short chunks; a narrow one multiplies
  passes over long ones. Never unroll a per-token address loop with
  `tl.static_range` — each unrolled copy of the address arithmetic bloats
  the code and pressures registers; the tiled form replaces the loop
  instead of unrolling it.
- Size every concurrent tile against the on-chip memory budget and mask the
  tails; computed scatter addresses (block ids, offsets) are masked like any
  computed address so an out-of-range lane cannot read past the buffer.

## Common mistakes and fixes

```python
# Wrong: the operator implemented as a torch layout call
return x.permute(0, 2, 1).contiguous()
# Right: view short-circuit where legal; otherwise a specialized kernel

# Wrong: one generic scalar gather serving every permutation
out = tl.load(x_ptr + decode(offs, shape, perm))   # per-element div/mod
# Right: pattern-specialized tile kernels; generic gather only as fallback

# Wrong: launching a kernel for a view-only permutation
y = torch.empty_like(x); kernel[grid](x, y)        # perm moves only size-1 dims
# Right: return x.view(out_shape)

# Wrong: full-rank kernel for a mergeable permutation
#        [A,B,M,N] -> [A,B,N,M] handled at rank 4
# Right: host merges to view(A*B, M, N); batch-transpose kernel at rank 3

# Wrong: element decode inside a "specialized" kernel
addr = base + (offs // N) * s0 + (offs % N) * s1
# Right: offs_m[:, None] * s_m + offs_n[None, :] * s_n as a 2D tile

# Wrong: one stride set for input and output
kernel[grid](x, y, x.stride(0), x.stride(1))
# Right: pass x's strides for loads and y's strides for stores

# Wrong: while-loop stride over work items
while idx < num_items: ...; idx += num_programs
# Right: for idx in range(pid, num_items, num_programs)   (repair §6/§18)

# Wrong: unrolled per-token scatter loop
for t in tl.static_range(8):
    tl.store(dst + block + t + off, tl.load(src + t + off))
# Right: [CHUNK, D] masked 2D tile per chunk — tile, don't unroll

# Wrong: per-token scalar copy of a contiguous head dimension
for t in range(chunk_len):
    v = tl.load(src + t * stride + tl.arange(0, D))   # D-wide vector per token
# Right: one [CHUNK, D] tile covering many tokens per load/store pair

# Wrong: unclamped grid over tiles
grid = (num_tiles,)
# Right: grid = (min(num_tiles, cores),) + in-kernel strided loop

# Wrong: unmasked computed scatter address
tl.store(dst + dst_block * s_blk + offs)
# Right: mask = offs < chunk_len; store(..., mask=mask)
```

## Recommended patterns

2D transpose tile kernel (batched transpose adds one program axis and its
stride):

```python
@triton.jit
def transpose_2d_kernel(x_ptr, y_ptr, M, N,
                        sxm, sxn, sym, syn,
                        BLOCK_M: tl.constexpr, BLOCK_N: tl.constexpr):
    pid = tl.program_id(0)
    num_pid_n = tl.cdiv(N, BLOCK_N)
    num_tiles = tl.cdiv(M, BLOCK_M) * num_pid_n
    for t in range(pid, num_tiles, tl.num_programs(0)):
        pid_m = t // num_pid_n                      # scalar division only
        pid_n = t - pid_m * num_pid_n
        offs_m = pid_m * BLOCK_M + tl.arange(0, BLOCK_M)
        offs_n = pid_n * BLOCK_N + tl.arange(0, BLOCK_N)
        mm = offs_m < M
        nn = offs_n < N
        tile = tl.load(x_ptr + offs_m[:, None] * sxm + offs_n[None, :] * sxn,
                       mask=mm[:, None] & nn[None, :], other=0.0)
        tl.store(y_ptr + offs_n[:, None] * sym + offs_m[None, :] * syn,
                 tl.trans(tile), mask=nn[:, None] & mm[None, :])
```

Paged scatter-copy tile kernel (metadata-driven, chunk × head-dim tiles):

```python
@triton.jit
def paged_copy_kernel(src_ptr, dst_ptr, meta_ptr, num_items, num_heads,
                      D, s_src_tok, s_src_head,
                      s_dst_blk, s_dst_head, s_dst_tok,
                      CHUNK: tl.constexpr, BLOCK_D: tl.constexpr):
    pid = tl.program_id(0)
    for idx in range(pid, num_items, tl.num_programs(0)):
        item = idx // num_heads                     # scalar division only
        head = idx - item * num_heads
        row = meta_ptr + item * 4
        src0 = tl.load(row + 0); blk = tl.load(row + 1)
        dst0 = tl.load(row + 2); length = tl.load(row + 3)
        for c in range(0, length, CHUNK):           # fixed-trip, masked tail
            tok = tl.arange(0, CHUNK)
            dd = tl.arange(0, BLOCK_D)
            m = (c + tok) < length
            v = tl.load(src_ptr + (src0 + c + tok)[:, None] * s_src_tok
                        + head * s_src_head + dd[None, :],
                        mask=m[:, None] & (dd < D)[None, :], other=0.0)
            tl.store(dst_ptr + blk * s_dst_blk + head * s_dst_head
                     + (dst0 + c + tok)[:, None] * s_dst_tok + dd[None, :],
                     v, mask=m[:, None] & (dd < D)[None, :])
```

Out-of-bounds computed addresses, int32/int64 offset arithmetic, and
oversized tile sets against the on-chip budget: see repair guide
`triton-npu-repair-guide/references/repair-experience.md` §12, §14, §16.
