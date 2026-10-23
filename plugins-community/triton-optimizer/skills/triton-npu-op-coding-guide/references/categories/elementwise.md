# Elementwise — pointwise arithmetic, activations, and math functions

## Scope

Operators where each output element depends only on the input element(s) at the
same (possibly broadcast) position: arithmetic (`add`, `mul`, `div`, `sub`,
`pow`), activations (`relu`, `sigmoid`, `tanh`, `gelu`, `silu`, gated variants
such as SwiGLU/GEGLU), math functions (`exp`, `log`, `sqrt`, `sin`, `cos`,
`abs`), and their backward variants. If the source op takes a `dim=` reduction
argument or reads neighboring elements, it is not elementwise — route through
the index.

## Writing essentials

- Flatten to 1D and access contiguously. On the host make the input
  `.contiguous()` and launch a 1D grid over `cdiv(numel, BLOCK)`; in the kernel
  address with flat offsets only. Pure elementwise work gains nothing from 2D
  tiling — double masks and strided access add index overhead with no locality
  benefit. Stride-based in-kernel addressing is the fallback only when the host
  cannot make the input contiguous.
- Compute in fp32, store in the input dtype: load, `.to(tl.float32)`, apply the
  math, `.to(x.dtype)` at the store. Low-precision intermediates drift from the
  torch reference; make special constants (eps, infinity) explicitly fp32.
- Match the reference formula exactly, including its approximation mode. GELU
  has an exact-erf form and a tanh approximation; use the tanh form only when
  the reference does. Where the reference divides by a constant and bit-exact
  agreement matters, multiply by the precomputed reciprocal `tl.constexpr`
  instead of dividing.
- Clamp the grid to the vector core count: elementwise work runs on vector
  cores, so size the grid as `min(cdiv(numel, BLOCK), num_vectorcore)` read
  once in `__init__` — not a fixed full-core grid, which wastes scheduling on
  small tensors, and not more programs than there are cores for a grid-stride
  loop.
- Keep `BLOCK` a power of two, starting around 1024–2048 (autotune over
  `{256, 512, 1024, 2048, 4096}` keyed on `numel` if tuning is wanted later).
  Very small blocks underfill the vector unit; very large blocks hit the
  on-chip memory ceiling. Never use `BLOCK == 1` — the compiler may recompile
  the lane as a scalar path with different numerics.
- Reformulate exp-heavy math into a numerically stable form. Formulas like
  `tanh(ln(1 + e^x))` overflow for large positive `x` and underflow for large
  negative `x`; split into piecewise forms built on `exp(-|x|)`-style terms so
  every exponent stays bounded, and clamp where the reference clamps.
- Broadcast explicitly: expand with `p[:, None]` / `p[None, :]` before mixing a
  vector with a tile, and keep a broadcast operand in a register (load once)
  rather than reloading it per use.
- Fuse consecutive pointwise ops into one kernel — the fused chain does one
  load/store round trip instead of writing each intermediate to global memory.
  An activation that directly follows a matmul belongs in that matmul's
  epilogue, not in a second kernel.
- Use one uniform masked load/store path including the tail block; do not
  specialize full blocks versus tail blocks with separate code paths.
- int64 comparisons have no native vector-unit support and degenerate to scalar
  code. When comparing large integer values, cast both operands to fp32 first
  (only where the semantics allow the precision change).

## Common mistakes and fixes

```python
# Wrong: 2D tiling with double masks for a pure pointwise op
row = pid // ncols; col = pid % ncols
m = (row < M)[:, None] & (col < N)[None, :]
x = tl.load(p + row[:, None] * stride + col[None, :], mask=m)
# Right: flatten on the host, one flat offset vector, one mask
offs = pid * BLOCK + tl.arange(0, BLOCK)
x = tl.load(p + offs, mask=offs < numel, other=0.0)

# Wrong: fp16 math all the way through
y = tl.sigmoid(x)                    # x is fp16/bf16
# Right: compute in fp32, cast back at the store
y = tl.sigmoid(x.to(tl.float32)).to(x.dtype)

# Wrong: fixed full-core grid regardless of tensor size
grid = (self.vec_cores,)
# Right: no more programs than blocks, capped at the core count
grid = (min(triton.cdiv(numel, BLOCK), self.vec_cores),)

# Wrong: tanh-approximated GELU against an exact-erf reference
y = 0.5 * x * (1 + tl.math.tanh(...))
# Right: y = 0.5 * x * (1.0 + tl.math.erf(x * 0.7071067811865476)) — or the
# tanh form only when the reference itself uses approximate="tanh"

# Wrong: unstable exp for unbounded inputs
t = tl.exp(x); out = tl.log(1.0 + t)        # overflows for x > ~88 in fp32
# Right: piecewise stable form, e.g. tl.where(x > 0, x + log1p(exp(-x)), log1p(exp(x)))

# Wrong: bare 1D × 2D broadcast
w = p * tile                            # [BLOCK] × [BLOCK, D]
# Right: w = p[:, None] * tile           (see repair guide §17)

# Wrong: int64 compare in the kernel
sel = tl.where(idx_i64 > thr_i64, a, b)  # scalar fallback
# Right: cast to fp32 for the comparison when semantics allow

# Wrong: separate activation kernel after a matmul
out = torch.relu(matmul_out)            # extra full HBM round trip
# Right: apply the activation to the accumulator before its tl.store
```

## Recommended patterns

Grid-stride elementwise skeleton (also covers multi-input gated activations by
adding pointers):

```python
@triton.jit
def pointwise_kernel(x_ptr, y_ptr, numel,
                     OUT_DTYPE: tl.constexpr, BLOCK: tl.constexpr):
    pid = tl.program_id(0)
    num_progs = tl.num_programs(0)
    for start in range(pid * BLOCK, numel, num_progs * BLOCK):
        offs = start + tl.arange(0, BLOCK)
        mask = offs < numel
        x = tl.load(x_ptr + offs, mask=mask, other=0.0).to(tl.float32)
        y = compute_fn(x)                       # the operator's math, in fp32
        tl.store(y_ptr + offs, y.to(OUT_DTYPE), mask=mask)


def pointwise_op(x):                            # host wrapper
    x = x.contiguous()
    y = torch.empty_like(x)
    numel = x.numel()
    grid = (min(triton.cdiv(numel, BLOCK), VEC_CORES),)   # VEC_CORES cached in __init__
    pointwise_kernel[grid](x, y, numel, OUT_DTYPE=x.dtype, BLOCK=BLOCK)
    return y
```

Pass the output dtype as a `tl.constexpr` parameter rather than deriving it
from `x_ptr.dtype.element_ty` — see repair guide §14.

Broadcast shape errors and constant-division 1-ULP mismatches: see repair guide
`triton-npu-repair-guide/references/repair-experience.md` §11 and §17.
