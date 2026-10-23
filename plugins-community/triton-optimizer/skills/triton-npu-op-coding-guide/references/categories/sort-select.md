# Sort and select — reorder, top-K, and iterative selection

## Scope

Comparison-based reordering and selection operators: `sort`/`argsort`/`topk`
(and their `sorted`/`indices` outputs), selection-with-suppression loops such
as NMS, and "score then select top-K then emit ordered indices" composites.
Index-mapped reads/writes (gather/scatter/index_put) are a different pattern —
see [indexing.md](indexing.md); do not transplant its tricks here.

## Writing essentials

- All conditionals must be vector-form: Triton Ascend kernels have no
  `break`/`continue`/`return` and no Python `if` branches — express every
  choice as `tl.where(cond, a, b)` on scalars and tiles alike, and control
  `tl.load`/`tl.store` with `mask=`. Selection algorithms are inherently
  branchy; write them as fixed-trip-count loops whose iterations do masked
  work, not loops that exit early (see repair guide §18).
- Iterative selection (NMS-style "pick the best remaining element, then update
  the rest") follows the selection-sort idiom: per step, linear-scan for the
  best candidate updating `(best_idx, best_val)` with `tl.where`, guard every
  load/store that depends on `best_idx` with `found = best_idx != -1`
  (an unguarded address of `-1` reads out of bounds), record the result, then
  mark the chosen element as consumed by writing a sentinel into memory.
- Carry algorithm state in memory values, not scalar flags: mark
  selected/suppressed elements by overwriting their score with a sentinel in a
  host-allocated working copy — never mutate the caller's input tensor, and
  never accumulate a Python-style boolean across a loop. The working copy is
  also where `.to(torch.float32).contiguous()` happens, giving the kernel
  contiguous fp32 access.
- The reference's ordering semantics come from its sort step
  (`argsort(descending=True, stable=True)` typically); the iterative
  selection loop reproduces descending order implicitly — each step emits the
  highest remaining score — so do not collect-then-truncate, which breaks both
  the order and the `max_output_size` limit.
- Sequentially dependent selections run as `grid = (1,)`: one program, because
  each step depends on the previous one's suppression. Accept the
  serialization; do not parallelize a loop whose iterations write state the
  next iteration reads.
- TopK by value uses tile-wise partial sort + merge, never a full sort of the
  row and never a per-rank selection loop (`for rank in range(K)` scanning all
  N per rank is a scalar chain). Per tile: load with a `±inf` pad for the
  tail, `tl.sort` the tile, `tl.gather` the first K; merge across tiles
  through a temp workspace of fixed width `next_pow2(2 * K)` — write the
  running best and the chunk's top-K into it, reload, `tl.sort`, `tl.gather`
  the first K again.
- The merge must round-trip through memory. Splicing two K-wide register tiles
  with computed indices (`idx % K`) and `tl.where` is a forbidden pattern, and
  extracting one element from a sorted tile with
  `tl.sum(tl.where(arange == rank, vals, 0.0))` scalarizes — see repair
  guide §15. `tl.sort`/`tl.gather` widths are `tl.constexpr`; `K` and the
  workspace width must be powers of two or padded to them.
- Loop over the actual extent `for c in range(0, n_cols, TILE)` with a masked
  tail load — never iterate `next_pow2(n_cols)`, which sorts padding as data.
  `TILE = min(4096, next_pow2(n_cols))` is the usual starting point, and
  rows-per-program is derived from the on-chip memory budget
  (`budget // (TILE * element_size)`), not a fixed constant like 1/2/4.
- Pick the sort strategy by problem size at write time: small K with small N
  fits an in-tile sorting network (`tl.sort`); large K wants reduce-split or
  bucketing plus partial sorts. A full sorting network whose compare-exchange
  count grows with K is the wrong structure for large K, and no block-size
  tuning recovers it.
- `tl.cumsum` on Ascend compiles to a scalar chain. Any "count, then locate
  the K-th position" prefix-sum selection structure must be replaced — the
  standard replacement is sort-compaction: write each element's rank position
  if selected and a large sentinel (`LARGE`, chosen above any achievable rank,
  e.g. `1 << 21` for ranks below 2²¹) if not, then an ascending sort compacts
  the selected entries to the front, performing select + order in one library
  call. Do not attempt to rescue a prefix-sum selection loop by tuning its
  block sizes — it is a structure problem.
- `torch_npu.npu_sort_v2` (fed a 2D `[rows, N]` view — a 1D layout is
  unreliable) is the fast device-side sorted/top-K primitive where a host
  `torch_npu` compute call is permitted; it can serve twice: ascending sort to
  read the K-th value as a threshold, then the compaction sort above. It is
  not available in `convert`/`gen-operator`: their contract routes computation
  through the Triton kernel and forbids torch compute calls in `forward()`, so
  in those flows the in-kernel `tl.sort` paths above are the only legal
  option.
- Tie-breaking is part of the semantics: the reference's stable sort defines
  which equal element lands first, and the rank encoding in a sort-compaction
  or joint argmax carry must reproduce it (prefer the smaller index on ties
  when the reference is stable). Mismatched tie order fails verification even
  when the selected set is right.
- Index outputs: torch's `sort`/`topk` return int64 indices. Compute indices
  in int32 inside the kernel and `.to(tl.int64)` at the final store — the
  output tensor's dtype must match the reference exactly (see repair guide
  §14 for int32/int64 mixing discipline).
- Comparisons stay vectorized: pick candidates with tile-wide
  `tl.maximum`/`tl.where` reductions rather than scalar comparisons per
  element, which forfeit the vector unit.

## Common mistakes and fixes

```python
# Wrong: Python if in a kernel
if score > best_score: best_idx = i
# Right: best_idx = tl.where(score > best_score, i, best_idx)

# Wrong: boolean flag accumulated across a loop
keep = True
for j in range(n):
    keep = keep & (iou(j) < threshold)     # scalar chain, no early data flow
# Right: write sentinel values into the working score copy; state lives in memory

# Wrong: unguarded access keyed on "not found"
val = tl.load(data_ptr + best_idx)         # best_idx == -1 reads OOB
# Right: tl.load(data_ptr + best_idx, mask=found, other=0.0)

# Wrong: collect all passing elements, then truncate
keep_mask = scores > threshold; out = indices[keep_mask][:max_size]
# Right: iterate max_size selections of the best remaining candidate

# Wrong: per-rank selection loop for top-K
for rank in range(K):
    best = tl.max(tl.where(not_taken, x, -inf))   # O(N*K) scalar chain
# Right: tl.sort per tile + tl.gather the first K + workspace merge

# Wrong: in-register merge by computed indices
merged = tl.where(idx % K == 0, best, chunk_topk)   # splice trick
# Right: temp workspace [ROWS, next_pow2(2K)]: store, reload, sort, gather

# Wrong: scalar extraction from a sorted tile
kth = tl.sum(tl.where(tl.arange(0, B) == rank, sorted_vals, 0.0))
# Right: tl.gather(sorted_vals, rank) — see repair guide §15

# Wrong: iterating the padded extent
for c in range(0, next_pow2(n_cols), TILE):    # sorts pad values as data
# Right: for c in range(0, n_cols, TILE): with mask=(c + offs < n_cols)

# Wrong: cumsum to locate the K-th selected position
pos = tl.cumsum(selected)                       # scalarizes on Ascend
# Right: sort-compaction — rank positions + LARGE sentinel + ascending sort

# Wrong: int32 indices stored into an int64 output tensor
tl.store(out_idx_ptr + o, best_idx)
# Right: tl.store(out_idx_ptr + o, best_idx.to(tl.int64))

# Wrong: sentinel mutating the caller's tensor
tl.store(x_ptr + best_idx, sentinel)            # x is the input
# Right: host allocates a float32 contiguous working copy; kernel mutates that
```

## Recommended patterns

Iterative selection (NMS-style), single program, state in a working copy:

```python
@triton.jit
def select_kernel(vals_ptr, data_ptr, out_ptr, count_ptr,
                  n, max_output_size: tl.constexpr, threshold, sentinel):
    active = tl.program_id(0) == 0              # grid = (1,)
    count = 0
    for step in range(max_output_size):
        best_idx = -1
        best_val = threshold
        for i in range(n):
            v = tl.load(vals_ptr + i)
            better = (v > best_val) & active
            best_idx = tl.where(better, i, best_idx)
            best_val = tl.where(better, v, best_val)
        found = (best_idx != -1) & active
        tl.store(out_ptr + count, best_idx.to(tl.int64), mask=found)
        count = tl.where(found, count + 1, count)
        tl.store(vals_ptr + best_idx, sentinel, mask=found)   # consume
        # operator-specific suppression of other candidates here, writing
        # sentinels into vals_ptr (IoU checks for NMS; nothing for plain topk)
    tl.store(count_ptr, count, mask=active)
```

TopK tile-wise partial sort + workspace merge (per program, several rows):

```python
TILE = min(4096, next_pow2(n_cols))            # host
COMBINED = next_pow2(2 * K)
ROWS = max(1, min(ceil(n_rows / cores), UB_BUDGET // (TILE * elem_bytes)))

@triton.jit
def topk_kernel(x_ptr, out_ptr, ws_ptr, n_rows, n_cols, K,
                TILE: tl.constexpr, COMBINED: tl.constexpr,
                ROWS: tl.constexpr, PAD: tl.constexpr):
    rows = tl.program_id(0) * ROWS + tl.arange(0, ROWS)
    rmask = rows < n_rows
    cols = tl.arange(0, TILE)
    kidx = tl.arange(0, K)
    kg = tl.broadcast_to(kidx[None, :], (ROWS, K))   # gather index rank == src
    best = tl.full((ROWS, K), PAD, tl.float32)
    for c in range(0, n_cols, TILE):            # actual extent, not pow2
        m = rmask[:, None] & ((c + cols) < n_cols)[None, :]
        tile = tl.load(x_ptr + rows[:, None] * n_cols + (c + cols)[None, :],
                       mask=m, other=PAD)
        topk = tl.gather(tl.sort(tile, descending=True), kg, axis=1)
        # merge through the workspace: [best | chunk topk] -> sort -> first K
        tl.store(ws_ptr + rows[:, None] * COMBINED + tl.arange(0, COMBINED)[None, :],
                 PAD, mask=rmask[:, None])
        tl.store(ws_ptr + rows[:, None] * COMBINED + kidx[None, :], best,
                 mask=rmask[:, None])
        tl.store(ws_ptr + rows[:, None] * COMBINED + (K + kidx)[None, :], topk,
                 mask=rmask[:, None])
        merged = tl.load(ws_ptr + rows[:, None] * COMBINED
                         + tl.arange(0, COMBINED)[None, :],
                         mask=rmask[:, None], other=PAD)
        best = tl.gather(tl.sort(merged, descending=True), kg, axis=1)
    tl.store(out_ptr + rows[:, None] * K + kidx[None, :], best,
             mask=rmask[:, None])
```

Scalar-extraction from tiles, UB overflow from oversized sort tiles, and
int32/int64 index mixing: see repair guide
`triton-npu-repair-guide/references/repair-experience.md` §15, §16, §14.
