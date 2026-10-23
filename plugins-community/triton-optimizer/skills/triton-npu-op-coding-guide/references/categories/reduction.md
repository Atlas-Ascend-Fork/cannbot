# Reduction — collapsing an axis to fewer outputs

## Scope

Operators that merge many input elements into fewer outputs along an axis:
`sum`, `mean`, `prod`, `max`, `min`, `argmax`/`argmin`, `logsumexp`, variance
and std as raw reductions, `cumsum` (prefix scan), and histogram/bincount-style
small-output-table reductions. Softmax, log-softmax, and normalization operators
are reductions wrapped in pointwise math — they live in
[softmax-norm.md](softmax-norm.md); read this card for their reduction core.
Cross-entropy is log-softmax consumed immediately — see the logsumexp pattern
below.

## Writing essentials

- One program per output row as the default layout: `grid = (M,)`, each program
  walks its row with a loop-carried accumulator and stores one result. No
  cross-program merge is needed in this layout. When M is small relative to the
  core count and the reduction axis is long, split the axis (below) instead of
  leaving cores idle.
- Carry the accumulator in fp32 and match its initializer — and the masked
  load's `other=` — to the reduction identity: `0.0` for sum/mean, `1.0` for
  prod, `-inf` for max/argmax, `+inf` for min. A `0.0` initializer for a max
  whose real values are all negative silently wins the reduction.
- Loop over the reduction axis in `BLOCK_K` chunks rather than loading the whole
  row at once: `acc += tl.load(row + k_offs, mask=..., other=0.0).to(tl.float32)`,
  then reduce the accumulator (`tl.sum(acc)`) once after the loop and cast to
  the output dtype at the final store. Count the accumulator when sizing
  `BLOCK_K` against the on-chip memory ceiling.
- Any `exp` inside a reduction (logsumexp, softmax's core) must subtract the row
  maximum first: `y = max + log(sum(exp(x - max)))`. Compute the max in a first
  pass over the row, then the sum in a second pass; keep everything fp32. With
  `other=-inf` on the masked load, padded lanes contribute `exp(-inf) = 0`
  naturally.
- Fused consumers beat materialized intermediates: cross-entropy is
  `logsumexp(row) - logit[label]` computed in one kernel (one scalar
  `tl.load(row + label)` for the ground-truth logit, label passed as int32);
  never write a softmax tensor to memory just to reduce it again.
- Joint reductions in one pass: carry `(running_max, running_idx)` together,
  updating both with `tl.where(block_max > running_max, ...)`; do not scan the
  row twice, once for `max` and once for `argmax`. First-index tie-breaking:
  take the smallest matching index within a block (`tl.sum(tl.where(is_max,
  k_offs, 0))` picks it when combined with an update-only-if-greater merge).
- Split-K for long reduction axes with few rows: `grid = (M, SPLIT)` with each
  program reducing a slice of the row. Two legal merge shapes:
  - atomic: `tl.atomic_add(y_ptr + row, partial)` into an output that the host
    zero-initialized (fp32);
  - two-phase: phase 1 writes `partial[row, split]` to an `[M, SPLIT]` fp32
    buffer, phase 2 (grid `(M,)`) loads the SPLIT partials and reduces them.
  Keep `SPLIT` within the AI-core count read at init — extra splits only
    contend. Do not split when the reduction axis is short; the added
    launch/merge cost outweighs the parallelism.
- Small-output-table reductions (histogram, bincount, scatter-sum into few
  bins): never reduce with global atomics onto the small table in a first
  implementation — every core contends on every bin. Use the dual-kernel shape:
  each program builds a local `[BINS]` table over its input slice (zeroed
  first, `BINS` a `tl.constexpr`, bin index computed in fp32 and clamped to
  `[0, BINS-1]`), stores `partial[program, :bins]`; a second kernel with one
  program per bin sums the partials. Within the local pass, prefer a
  match-matrix update (`matches = (bin_idx[:, None] == arange(BINS)[None, :])`,
  `local += tl.sum(matches, 0)`) — fully vectorized, no dynamic indexing — but
  its `BLOCK × BINS` matrix counts against the on-chip memory ceiling, so step
  down to per-element conditional increments when the table is wide.
- Prefix scans (`tl.cumsum`) compute within-tile prefixes only. A whole-row
  scan needs one program per row iterating blocks and carrying the running
  total across iterations (`carry += tl.sum(block)` after
  `store(cumsum(block) + carry)`), or an equivalent two-phase scan.

## Common mistakes and fixes

```python
# Wrong: low-precision accumulation
acc = tl.zeros([BLOCK_K], dtype=tl.float16)
acc += x                                # x is fp16/bf16
# Right: fp32 accumulator, upcast in the loop, cast back only at the store
acc = tl.zeros([BLOCK_K], dtype=tl.float32)
acc += x.to(tl.float32)

# Wrong: identity mismatch between accumulator and masked-load fill
acc = tl.full([1], float("-inf"), tl.float32)
x = tl.load(row + offs, mask=offs < K, other=0.0)   # for a SUM
# Right: other=0.0 pairs with a zeros() sum accumulator;
#        other=-inf pairs with a -inf max accumulator

# Wrong: exp without the max shift
sum_exp = tl.sum(tl.exp(x))
# Right: two passes — m = tl.max(x); sum_exp = tl.sum(tl.exp(x - m))

# Wrong: atomic merge into uninitialized memory
y = torch.empty(M, dtype=torch.float32)
tl.atomic_add(y_ptr + row, partial)
# Right: y = torch.zeros(...) — atomics accumulate onto an existing value

# Wrong: split-K sized without reference to the device
SPLIT = 64                               # more splits than cores
# Right: SPLIT = min(cap, ...) bounded by the cached AI-core count

# Wrong: histogram with global atomics from every program
tl.atomic_add(hist_ptr + bin_idx, 1)    # all cores hit the same bins
# Right: local per-program table + partial[program, bins] + reduce kernel

# Wrong: per-block cumsum with no carry across blocks
y = tl.cumsum(block)                     # each block restarts at 0
# Right: carry the running total across the row's block loop

# Wrong: two full scans for max and argmax
# Right: one pass carrying (value, index) together
```

## Recommended patterns

Row-reduction skeleton (per-program, loop-carried, identity-matched):

```python
@triton.jit
def row_reduce_kernel(x_ptr, y_ptr, M, K,
                      BLOCK_K: tl.constexpr, OUT_DTYPE: tl.constexpr):
    row = tl.program_id(0)
    x_row = x_ptr + row * K
    acc = tl.zeros([BLOCK_K], dtype=tl.float32)     # sum identity
    for k in range(0, K, BLOCK_K):
        offs = k + tl.arange(0, BLOCK_K)
        x = tl.load(x_row + offs, mask=offs < K, other=0.0)
        acc += x.to(tl.float32)
    tl.store(y_ptr + row, tl.sum(acc).to(OUT_DTYPE))
```

Split-K two-phase merge (phase 2 shown; phase 1 writes `partial[row, split]`):

```python
@triton.jit
def splitk_reduce_kernel(partial_ptr, y_ptr, M, SPLIT,
                         BLOCK_S: tl.constexpr, OUT_DTYPE: tl.constexpr):
    row = tl.program_id(0)
    offs = tl.arange(0, BLOCK_S)
    p = tl.load(partial_ptr + row * SPLIT + offs, mask=offs < SPLIT, other=0.0)
    tl.store(y_ptr + row, tl.sum(p).to(OUT_DTYPE))
```

Host: zero-initialize any atomic destination, allocate partials in fp32, pass
`BLOCK_S = triton.next_power_of_2(SPLIT)`.

Sizing `BLOCK_K` too large for the accumulator (UB overflow), or feeding int64
index scalars into the split arithmetic: see repair guide
`triton-npu-repair-guide/references/repair-experience.md` §14 and §16.
