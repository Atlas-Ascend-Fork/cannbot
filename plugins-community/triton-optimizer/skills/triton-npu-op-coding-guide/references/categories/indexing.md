# Indexing — gather, scatter, and index-mapped access

## Scope

Operators whose data movement is driven by an index tensor:
`index_select`, `torch.gather`, `Tensor[index]`, `take`, embedding lookups
(`y[i] = weight[index[i]]`), `index_put_` / `scatter` / `scatter_add`
(index-write, with `accumulate` semantics), `embedding_dense_backward`
(index-accumulate), token permutation/unpermutation, and MoE dispatch
(grouped gather/scatter by expert). Comparison-based reordering is a different
pattern — [sort-select.md](sort-select.md); the surrounding GEMMs are
[matmul.md](matmul.md).

## Writing essentials

- Specialize the dimension at compile time: normalize `dim` on the host and
  launch one kernel instance per `DIM = 0/1/2/3`, passing `DIM`/`NDIM` as
  `tl.constexpr`. Never decode coordinates at runtime
  (`for j in range(NDIM)` over loaded shapes, or `if dim == X` on a runtime
  value) — that inserts scalar division/modulo per element and blocks the
  hardware gather path. Python `if` on a `tl.constexpr` is legal (compile-time
  branch); on a runtime value it is not.
- Align the parallel axis with the contiguous one. The index tensors decide
  *where* data moves, but the memory traffic itself should run along the
  trailing/embedding/hidden dimension (`E`/`D`) in vector blocks:
  - read class (gather/index/embedding forward): parallelize over
    `outer × index_len`, each program moving one or more whole rows;
  - write class with a wide contiguous extent (`E ≥ ~128`): index-parallel
    with a vector `tl.atomic_add` along `E`;
  - write class with a short extent or heavy index duplication:
    extent-parallel, serially scanning the index dimension per program;
  - `accumulate=False` with unique indices: output-position-parallel with
    plain vector stores.
- Load and store by vectors along the contiguous extent, and load the index
  tensor itself vectorized (`tl.load(index_ptr + offs, mask=...).to(tl.int32)`)
  — a scalar index load per element, or a scalar atomic inside a
  `for e in range(BLOCK_E)` loop, forfeits the vector unit. Never split a
  loaded index tile back into scalars (`tile[j]`, `tl.get_element`) to index
  with — re-load the scalars you need straight from `index_ptr` (repair
  guide §15).
- Index dtype discipline: convert index values to `tl.int32` as soon as they
  are loaded; compute final flat offsets that can exceed int32 range
  (`base + batch_off * stride`) in `tl.int64`. Avoid scalar `.to(tl.int64)`
  casts and `%` on int64 vectors — use `idx - (idx // M) * M` when a modulus
  is unavoidable (see repair guide §14).
- Prefer the row-preload gather path when the gathered dimension is the last
  dimension and its extent fits the on-chip memory capacity (a device
  property; order of tens of thousands of fp32 elements): load the whole
  source row into registers once, then `tl.gather(row, idx)` per output
  position. Direct-indirect addressing (`x_ptr + idx * stride` per element) is
  the fallback when the row does not fit — chunk it (`BLOCK` + `BLOCK_SUB`)
  rather than forcing an oversized preload that spills. For a non-last-dim
  gather of manageable extent, consider moving that dimension to the end on
  the host first (`movedim(dim, -1).contiguous()`), gathering, and moving
  back — but only when the estimated gather benefit exceeds roughly twice the
  copy cost; an unconditional transpose can cost more than it saves.
- Base loop bounds on the output/index shape, never the input shape:
  `M = index.shape[:dim].prod()` — the output's extent is what the index
  defines; input-derived bounds miss or over-read work.
- Scatter semantics: `accumulate=True` uses `tl.atomic_add` into a
  host-zero-initialized output; fp16/bf16 accumulation goes through an fp32
  workspace buffer cast back at the end — atomics straight into a low-precision
  output lose precision. `accumulate=False` with duplicate indices needs
  deterministic last-write-wins (a single program writing that output segment
  serially, or a two-phase scheme) — otherwise the result is nondeterministic.
  Boundary handling (`index < 0`, `index >= dim_size`) masks the access
  (out-of-range reads return 0, out-of-range writes are dropped).
- Keep optional-argument and exception logic out of the hot loop: pass every
  optional tensor as a valid dummy tensor (a `None` pointer breaks the JIT
  signature), and handle exclusion positions (`padding_idx` rows) with a
  separate lightweight zeroing kernel after the main scatter — a per-element
  `if idx != padding_idx` in the loop breaks vectorization.
- Random index orders scatter and gather into scattered accesses. When the
  index distribution is arbitrary, sorting the work by target index first
  (host `argsort` + reindexed sources, or a grouped/binned layout) restores
  locality: adjacent programs then touch adjacent memory, and MoE-style
  dispatch groups each expert's token segment into a contiguous range
  (sort by expert id, segment starts via `searchsorted`, one program per
  expert slot) so writes to a group stop contending entirely. Token
  permute/unpermute are the row-sized building blocks
  (`dst[i] = src[indices[i]]` and its inverse).
- Embedding backward is a three-stage shape, not one kernel: a frequency
  kernel (index-parallel atomic counting of each output row's occurrences),
  the main scatter-add kernel (vector atomic along `D`, reading `1/freq` from
  the counted table when `scale_grad_by_freq`), and a padding-zero kernel.
  A single kernel with nested scalar loops over tokens × dims explodes the
  atomic count and risks device timeouts.
- Size the grid from the actual tile count with an in-kernel stride loop
  (`for b in range(pid, total, num_programs)`), keep the 1D grid under its
  hard launch limit (use a 2D grid or larger blocks otherwise), and derive
  blocks from the actual extents — a fixed large block walking a small
  dimension in a long single-program loop risks device timeouts, and an
  oversized fixed row preload spills.
- If autotuning an operator that mutates its output or accumulates in place,
  re-initialize the buffer per candidate config (or key the search on the
  target dimension `K`/`E`/`D` only) — otherwise later configs accumulate onto
  earlier results and both correctness and timing readings are wrong.
- Migrating GPU/CUDA Triton sources: strip `num_warps`, `num_stages`,
  `cache_modifier`, `evict_last` and other GPU-only launch options; drop
  fp64/unsigned index dtypes; apply the int32-index and fp32-accumulation
  rules above. Do not fake a transpose by swapping strides inside block
  pointer shape/order arguments to present a transposed layout as a natural
  one — pass the tensor's true strides, or transpose explicitly on the host.

## Common mistakes and fixes

```python
# Wrong: runtime dim dispatch inside the kernel
if dim == 0: off = i * stride0
# Right: host launches a DIM=0-specialized instance; DIM: tl.constexpr

# Wrong: scalar atomic per element of the contiguous extent
for e in range(BLOCK_E):
    tl.atomic_add(out_ptr + idx * E + e, val[e])
# Right: tl.atomic_add(out_ptr + idx * E + offs_e, val, mask=offs_e < E)

# Wrong: scalarizing a loaded index tile
idx_tile = tl.load(index_ptr + offs)
for j in range(BLOCK): target = idx_tile[j]        # tile scalar indexing
# Right: tl.load(index_ptr + j) per scalar needed, or keep the whole
#        vector operation vectorized (repair guide §15)

# Wrong: atomics into an fp16 output
tl.atomic_add(w_ptr + idx * D + d, g)              # w is fp16
# Right: fp32 workspace, accumulate, cast back once at the end

# Wrong: loop bounds from the input shape
M = x.shape[:dim].prod()
# Right: M = index.shape[:dim].prod()              # output defines the work

# Wrong: optional tensor passed as None
kernel[grid](x, w, grad is not None and grad or None)
# Right: pass a valid dummy tensor (zeros) and a HAS_GRAD: tl.constexpr flag

# Wrong: exclusion handled in the hot loop
if idx != padding_idx: tl.atomic_add(...)
# Right: separate zeroing kernel over the padding row after the main pass

# Wrong: duplicate-index overwrite left to scheduling order
tl.store(out_ptr + idx, val)                       # accumulate=False, dup idx
# Right: last-write-wins — one program owns the segment (or two-phase)

# Wrong: unmasked computed gather addresses
x = tl.load(x_ptr + idx * T + t_offs)              # idx may exceed the table
# Right: mask = in_range & (t_offs < T); load(..., mask=mask, other=0.0)

# Wrong: int64 vector arithmetic in the addressing path
off = (i64_idx % M) * stride
# Right: idx32 = i64_idx.to(tl.int32); int64 only for overflow-sized flat bases

# Wrong: 1D grid unfolded beyond the launch limit
grid = (outer * index_len * tiles,)
# Right: 2D grid, or clamp to cores with the in-kernel stride loop

# Wrong: preloading a row larger than on-chip capacity
row = tl.load(x_ptr + base + tl.arange(0, ROW))    # ROW beyond the ceiling
# Right: chunk the row into BLOCK + BLOCK_SUB passes

# Wrong: unconditional host transpose before gathering
x = x.movedim(dim, -1).contiguous()
# Right: transpose only when estimated gather benefit > 2x the copy cost
```

## Recommended patterns

Row gather (embedding lookup / index_select along dim 0), one program per
output row, base addresses precomputed:

```python
@triton.jit
def row_gather_kernel(x_ptr, index_ptr, y_ptr, n_rows, D,
                      BLOCK_D: tl.constexpr, OUT_DTYPE: tl.constexpr):
    row = tl.program_id(0)
    src = tl.load(index_ptr + row).to(tl.int32)      # scalar index, from memory
    base = src.to(tl.int64) * D                        # widen before the multiply
    out = y_ptr + row.to(tl.int64) * D
    for d in range(0, D, BLOCK_D):
        offs = d + tl.arange(0, BLOCK_D)
        m = offs < D
        v = tl.load(x_ptr + base + offs, mask=m, other=0.0)
        tl.store(out + offs, v.to(OUT_DTYPE), mask=m)
```

Vector-atomic scatter-add along the contiguous extent:

```python
@triton.jit
def scatter_add_kernel(src_ptr, index_ptr, dst_ptr, N, D,
                       BLOCK_D: tl.constexpr):
    row = tl.program_id(0)                            # one source row per program
    dst32 = tl.load(index_ptr + row).to(tl.int32)
    src = src_ptr + row.to(tl.int64) * D
    dst = dst_ptr + dst32.to(tl.int64) * D            # dst is a zeroed fp32 buffer
    for d in range(0, D, BLOCK_D):
        offs = d + tl.arange(0, BLOCK_D)
        m = offs < D
        v = tl.load(src + offs, mask=m, other=0.0).to(tl.float32)
        tl.atomic_add(dst + offs, v, mask=m)
```

Host: `dst = torch.zeros(..., dtype=torch.float32)`; cast to the output dtype
in a final elementwise pass when the reference output is low-precision.

Out-of-bounds computed gather offsets, int32/int64 mixing, tile
scalar-extraction, and unsupported `break`/`continue`/`return`: see repair
guide `triton-npu-repair-guide/references/repair-experience.md` §12, §14,
§15, §18.
