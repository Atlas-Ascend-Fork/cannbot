# Fundamentals — rules for every Triton-Ascend kernel

## Scope

Every rule in this card applies to all operator categories. Read it before any
category card; category cards assume it and do not repeat it. Hardware
constants below are stated as capacity ceilings to respect, never as numbers
to hardcode — read device properties at runtime instead.

## Writing essentials

### Kernel structure

Use the five-step structure as the default skeleton: program offset, optional
intra-program loop, index construction, boundary mask, load → compute → store.

```python
@triton.jit
def kernel(in_ptr, out_ptr, numel, BLOCK: tl.constexpr):
    xoffset = tl.program_id(0) * BLOCK          # 1. program offset
    for xsub in range(0, BLOCK, SUB):           # 2. intra-program loop (optional)
        x_index = xoffset + xsub + tl.arange(0, SUB)  # 3. index construction
        xmask = x_index < numel                 # 4. boundary mask
        x = tl.load(in_ptr + x_index, mask=xmask, other=0.0)  # 5. load/compute/store
        tl.store(out_ptr + x_index, x * 2.0, mask=xmask)
```

### Control-flow legality

- `return`, `break`, and `continue` are not supported inside `@triton.jit`;
  use masks and exact loop bounds instead.
- Avoid `while`; use a bounded `for` with a mask. Avoid
  `tl.static_range` over a large trip count (full unroll blows up IR).
- No lambda expressions and no Python slicing or direct tensor indexing on
  tiles; use tile-level operations (`tl.where`, `tl.sum`,
  `tl.extract_slice`, `tl.insert_slice`).
- Use `tl.where` to select values, never to select memory offsets.

### dtype and precision

- Accumulate in `tl.float32` for any arithmetic reduction over fp16/bf16 data
  (`sum`, `mean`, `prod`, dot accumulators). `max`/`min` reductions do not
  need upcasting. Cast back to the storage dtype only at the final store.
- Cast with `.to(tl.float32)`, not dtype constructors like `tl.float16(x)`.
- Numeric stability defaults: subtract the row maximum before `exp`; clamp
  variance to non-negative before `sqrt` or reciprocal-sqrt; make special
  constants (infinity, eps) explicitly float32 where dtype inference sees
  them (`tl.full(..., tl.float32)`).
- Division: Triton-Ascend lowers scalar and vector division through different
  paths than torch in some cases. When bit-exact agreement with a torch
  reference that divides by a constant matters, multiply by the precomputed
  reciprocal constant instead. Avoid `BLOCK == 1`, which can recompile the
  lane as a scalar path.
- Index arithmetic: keep pointer offsets in one integer width. Pass strides
  and indices as int32 from the host; do not feed int64 index tensors into
  kernels.

### constexpr discipline

- Values invariant to the data (block sizes, flags, dtype selectors) belong in
  the kernel signature as `X: tl.constexpr` so the compiler specializes them.
- `tl.constexpr` exists only in kernel signatures, never on the host side.
- With `triton.autotune`, config keys must be declared `tl.constexpr`
  parameters and must not be passed at the launch call; the tuner supplies
  them.
- Do not pass CUDA-only launch parameters (`num_warps`, `num_stages`,
  `num_ctas`); they are meaningless on Ascend. Tune block sizes and grid
  extents instead.

### Grid legality and large shapes

- The grid is a tuple, at most 3 dimensions, each dimension at most 65535.
  A block holds fewer than 65536 elements.
- Prefer 1D grids; they map to the core array directly.
- When `cdiv(numel, BLOCK)` exceeds the grid limit — or to keep the grid near
  the core count — use a persistent interleaved loop over blocks
  (`for i in range(pid, num_blocks, num_programs)`), or split one logical
  axis across two grid dimensions.

### Device properties

- Never hardcode core counts. Read them once in `__init__` and cache:
  `driver.active.utils.get_device_properties(device)["num_vectorcore"]` for
  vector-oriented work, `["num_aicore"]` for matrix-oriented work.
- Never query device properties in `forward`; it is per-call host overhead.

```python
import torch_npu
import triton.runtime.driver as driver

class ModelNew(torch.nn.Module):
    def __init__(self):
        super().__init__()
        props = driver.active.utils.get_device_properties(
            torch_npu.npu.current_device()
        )
        self.vec_cores = props["num_vectorcore"]
```

### Masks and addressing

- Every `tl.load`/`tl.store` carries a `mask` (or a block pointer with
  `boundary_check`). Choose `other=` as the identity of the consuming
  reduction: `0.0` for sums/products-of-additions, `-inf` for max, `+inf`
  for min — a wrong `other=` silently corrupts masked-lane reductions.
- A mask protects lanes, not addresses: the backend may still evaluate the
  full offset expression of masked-out lanes. Keep every offset inside the
  backing allocation by construction — no negative offsets, no
  constant-shifted offsets that can leave the valid range.
- Keep offset expressions affine (`base + idx * stride`); clamps and selects
  inside address expressions degrade lowering.

### Memory layout and alignment

- Access memory contiguously. On the host, make inputs `.contiguous()` or
  address through explicit strides; never assume contiguity you did not
  check.
- Data transfers move in 256-byte units; design block extents so rows fill
  them. Matrix-multiply-class tiles want row widths that are multiples of
  512 bytes (256 fp16/bf16 or 128 fp32 elements).
- For regular 2D tiles, prefer `tl.make_block_ptr` with `boundary_check` over
  hand-built index math.

### On-chip memory budget

- The unified buffer is a capacity ceiling on the order of 100–200 KB per
  core depending on the part. Every concurrently live tile — operands,
  accumulators, named intermediates, and compiler-inserted multi-buffering —
  counts against it; the compiler rejects the kernel with a `ub overflow`
  error when the sum exceeds it.
- Derive block extents from the live-tile sum, not from a single tensor's
  size. Splitting one axis into an inner loop is the standard way to shrink
  the live set.

## Common mistakes and fixes

```python
# Wrong: early exit / unsupported control flow
if done: break                  # → masks + exact loop bounds
while i < n: ...                # → bounded `for` + mask

# Wrong: Python-style access on tiles
val = tile[k]                   # → tile-level ops, or reload from the pointer
part = tile[a:b]                # → tl.extract_slice / recomputed loads

# Wrong: constructor cast
y = tl.float16(x)               # → y = x.to(tl.float16)

# Wrong: offsets that leave the valid range
t = tl.load(p + (offs - HALF) * stride, mask=m)   # → shift the base pointer,
                                                  #   or load segments separately

# Wrong: relying on the mask to guard addresses
t = tl.load(p + offs, mask=offs < n)  # mask is required but not sufficient:
                                      # keep offs inside the allocation too

# Wrong: int64 indices from the host
pos = cache_position            # int64 tensor → pos.to(torch.int32) first

# Wrong: grid as an int, or beyond the limit
kernel[n_blocks,](...)          # → tuple grid; persistent loop when huge

# Wrong: querying per forward / hardcoding cores
core = get_device_properties(...)["num_vectorcore"]  # in forward → __init__
grid = (20,)                    # hardcoded → cached device property

# Wrong: low-precision accumulation
acc += tl.dot(a, b)             # acc in fp16 → fp32 accumulator, cast at store

# Wrong: unstable numerics
e = tl.exp(x)                   # → subtract the row max first
r = tl.sqrt(var)                # → tl.maximum(var, 0.0) first

# Wrong: autotune / launch hygiene
kernel[grid](..., BLOCK=128)    # BLOCK is an autotune key → don't pass it
kernel[grid](..., num_warps=4)  # CUDA-only → remove
```

## Recommended patterns

Persistent interleaved loop for large or core-count-capped work:

```python
@triton.jit
def persistent_kernel(in_ptr, out_ptr, numel,
                      NUM_PROGRAMS: tl.constexpr, BLOCK: tl.constexpr):
    pid = tl.program_id(0)
    num_blocks = tl.cdiv(numel, BLOCK)
    for block_idx in range(pid, num_blocks, NUM_PROGRAMS):
        offs = block_idx * BLOCK + tl.arange(0, BLOCK)
        mask = offs < numel
        x = tl.load(in_ptr + offs, mask=mask, other=0.0)
        tl.store(out_ptr + offs, x * 2.0, mask=mask)
```

Host wrapper responsibilities (and nothing else): allocate outputs, ensure
contiguity, read device properties once, compute the grid, launch, return.

## Known failure-signature pointers

When a run fails, route through `triton-npu-repair-guide` and its
`repair-experience.md`; entries relevant to this card: §1 `tl.math` vs
libdevice, §2 `allow_tf32`, §3 fp32 infinity literals, §4 single-tile UB
overflow, §5 0d block_type, §6 while-loop lowering, §11 1-ULP division
mismatch, §12 masked loads with out-of-range offsets, §13 negative static
offsets, §14 int32/int64 mixing, §15 scalar extraction from tiles, §16
multi-tile UB overflow, §17 broadcast shape incompatibility, §18
break/continue/return.

Performance tuning beyond these legality rules (tile-size search, scheduling,
precision ablations) is an optimize-phase decision, not part of writing the
first implementation.
