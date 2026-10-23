# Softmax and normalization — row statistics then apply

## Scope

Operators that compute per-row (or per-group) statistics and then apply a
transform with them: `softmax` and `log_softmax`, `LayerNorm`, `RMSNorm`,
`GroupNorm` and fused variants (skip-add + norm, norm + activation,
norm + quantize epilogue), plus their backward kernels. The reduction
mechanics (fp32 accumulators, identity-matched `other=`, split merges) live in
[reduction.md](reduction.md); this card adds the statistics-then-apply
structure and its numerics.

## Writing essentials

- Structure every normalization as reduce-then-apply with the statistics held
  in registers. Two legal shapes, chosen by data ownership:
  - One fused kernel, when all statistics for an output row/group are readable
    by a single program: a first loop accumulates `sum`/`sq_sum` (or
    max/sum-exp), a second loop applies the transform. No intermediate tensor
    touches memory. This is the default for forward LayerNorm/RMSNorm/softmax.
  - Two kernels (reduce, then apply), when statistics must merge across
    programs — the backward case, where `grad_input` needs global sums and
    per-channel `grad_weight`/`grad_bias` reduce over a different grain than
    per-(row) statistics. The reduce kernel writes fp32 partial buffers
    (`tl.atomic_add` per tile), the apply kernel reads the merged sums.
  Do not force one shape onto the other case: a split forward norm pays an
  extra launch for nothing, and a fused multi-grain backward cannot see the
  global sums it needs.
- Accumulate statistics in fp32 (`tl.full([1], 0.0, tl.float32)` scalars or an
  fp32 vector accumulator — never a 0-d `tl.full((), ...)`, which some
  positions reject); formulas like `var = (sq - sum * sum / N) / N` are
  sensitive to accumulator precision. Clamp variance non-negative before the
  reciprocal (`var = tl.maximum(var, 0.0)`), keep `eps` fp32, and use
  `tl.rsqrt(var + eps)` — it maps to a hardware instruction.
- Softmax numerics: never `exp` an unshifted row. Either two passes (max, then
  sum of `exp(x - max)`) or the online single pass carrying `(m, l)`:
  `l = l * exp(m_old - m_new) + sum(exp(x - m_new))`; final outputs are
  `exp(x - m) / l`, and log-softmax is `x - (m + log l)`.
- Load per-channel weight/bias by scalar index when a block lies within one
  channel (`ch = d_start // D` on the scalar loop variable), never by
  vectorized channel arithmetic (`offsets // D` then a gathered load) — integer
  vector division scalarizes badly on Ascend. If the block spans channels,
  restructure so it does not, or load the affine weights per channel in an
  outer loop.
- Size `BLOCK` against the on-chip memory ceiling and the row extent: a whole
  row fits in one tile only while `n_cols * dtype_bytes` stays under it;
  otherwise loop both passes over `BLOCK_N` chunks. Use
  `triton.next_power_of_2(...)` for the block and mask every access — the
  padded lanes between the real extent and the power of two must be masked
  out (`other=` matching the statistic's identity).
- Grid: one program per row/group for small row counts; otherwise a 1D
  interleaved loop (`for gid in range(pid, total_groups, num_programs)`) with
  the grid clamped to the core count, so per-group statistics still live in
  registers across the loop.
- Make static lengths `tl.constexpr` — block sizes and group geometry
  (`channels_per_group`, `elems_per_group`): they are invariant per launch and
  the compiler specializes on them.
- Use `tl.cdiv` inside kernels and `triton.cdiv` (or plain integer math) on
  the host; calling `triton.cdiv` inside `@triton.jit` is a compile error.
- Avoid `tl.reshape` inside kernels; prefer flat 1D indexing with explicit
  base offsets. Reshape has known correctness and constexpr-shape limitations
  on Ascend toolchains.
- Softmax over a non-innermost dimension: make the reduction dimension
  contiguous (host-side transpose/`.contiguous()`) and reduce along the inner
  axis, rather than walking strided memory inside the kernel.
- Fuse adjacent pointwise work into the apply pass: residual add before the
  statistics (`x = x + residual`, then normalize, optionally storing the
  updated residual), and activation or quantization after the affine multiply —
  one kernel, no intermediate round trips.
- Backward gradients (for reference): softmax `dx = p * (dy - sum(dy * p))`,
  log-softmax `dx = dy - p * sum(dy)`, both computed in fp32 with `p` recomputed
  or reloaded; keep `grad_weight`/`grad_bias` accumulating in fp32 and cast to
  the output dtype only at the final return.

## Common mistakes and fixes

```python
# Wrong: statistics accumulated in the input dtype
acc = tl.zeros([BLOCK], dtype=tl.float16)
acc += x * x
# Right: fp32 accumulator, upcast each load, cast once at the store

# Wrong: exp without the row max
p = tl.exp(x) / tl.sum(tl.exp(x))
# Right: m = tl.max(x); p = tl.exp(x - m) / tl.sum(tl.exp(x - m))

# Wrong: negative variance reaching the sqrt
rstd = tl.rsqrt(var + eps)              # var can be slightly negative
# Right: var = tl.maximum(var, 0.0); rstd = tl.rsqrt(var + eps)

# Wrong: vectorized channel index for affine weights
ch = offsets // D
w = tl.load(w_ptr + ch)                 # int vector division scalarizes
# Right: scalar index per block — ch = d_start // D; tl.load(w_ptr + base + ch)

# Wrong: two kernels for a plain forward row norm
stats_kernel[grid](...); apply_kernel[grid](...)
# Right: one kernel, statistics pass then apply pass, stats in registers

# Wrong: backward grad_input computed in the reduce kernel
# Right: reduce writes fp32 partials; apply reads merged sums, then writes
#        grad_input

# Wrong: atomics into uninitialized or low-precision buffers
gw = torch.zeros(C, dtype=torch.float16)
tl.atomic_add(gw_ptr + c, s2 * inv_std)
# Right: fp32 zeros buffer; .to(out_dtype) once at the end

# Wrong: cdiv from the wrong namespace
n = triton.cdiv(K, BLOCK)               # inside @triton.jit
# Right: tl.cdiv in-kernel; triton.cdiv only on the host

# Wrong: reshape to broadcast statistics across a tile
x2 = tl.reshape(x, (BLOCK, 1))
# Right: index flat, expand explicitly (p[:, None]) where broadcasting is needed

# Wrong: power-of-two block without masking the padded extent
offs = tl.arange(0, BLOCK_N)            # BLOCK_N = next_power_of_2(S) > S
tl.load(p + offs)                       # reads past the row
# Right: tl.load(p + offs, mask=offs < S, other=identity)
```

## Recommended patterns

Fused forward RMSNorm skeleton (statistics in registers, apply pass fused with
the affine multiply):

```python
@triton.jit
def rmsnorm_kernel(x_ptr, w_ptr, y_ptr, n_cols, eps,
                   BLOCK: tl.constexpr, OUT_DTYPE: tl.constexpr):
    row = tl.program_id(0)
    base = row * n_cols
    acc = tl.zeros([BLOCK], dtype=tl.float32)
    for c in range(0, n_cols, BLOCK):
        offs = c + tl.arange(0, BLOCK)
        x = tl.load(x_ptr + base + offs, mask=offs < n_cols, other=0.0)
        xf = x.to(tl.float32)
        acc += xf * xf
    rrms = tl.rsqrt(tl.sum(acc) / n_cols + eps)
    for c in range(0, n_cols, BLOCK):
        offs = c + tl.arange(0, BLOCK)
        m = offs < n_cols
        x = tl.load(x_ptr + base + offs, mask=m, other=0.0).to(tl.float32)
        w = tl.load(w_ptr + offs, mask=m, other=1.0).to(tl.float32)
        tl.store(y_ptr + base + offs, (x * rrms * w).to(OUT_DTYPE), mask=m)
```

Online softmax (single statistics pass, second pass writes):

```python
m_i = tl.full([1], float("-inf"), tl.float32)
l_i = tl.zeros([1], tl.float32)
for c in range(0, n_cols, BLOCK):
    offs = c + tl.arange(0, BLOCK)
    x = tl.load(row_ptr + offs, mask=offs < n_cols,
                other=float("-inf")).to(tl.float32)
    m_new = tl.maximum(m_i, tl.max(x))
    l_i = l_i * tl.exp(m_i - m_new) + tl.sum(tl.exp(x - m_new))
    m_i = m_new
# apply pass: y = exp(x - m_i) / l_i   (log-softmax: x - (m_i + log(l_i)))
```

Division-by-constant 1-ULP mismatches in the statistics (`/ n_cols`, `/ S`)
and UB overflow from oversized blocks: see repair guide
`triton-npu-repair-guide/references/repair-experience.md` §11 and §16.
