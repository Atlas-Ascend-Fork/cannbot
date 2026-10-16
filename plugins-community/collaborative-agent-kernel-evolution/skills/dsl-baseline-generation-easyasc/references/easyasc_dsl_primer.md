# easyasc DSL — 5-minute primer

This is the minimum-viable surface of the easyasc DSL needed to generate a Vector kernel for cake. For anything beyond, follow the entries in `easyasc_dsl_pointers.md`.

## What is easyasc?

A Python DSL that lets you write Ascend NPU kernels. The same Python file serves two purposes:

1. **Simulator mode** (`OpExec(kernel, simulator=True)`): runs in pure Python against torch tensors — used for correctness checks during DSL authoring.
2. **Codegen mode** (`OpExec(kernel, simulator=False, out_dir=...)`): emits AscendC `.cpp/.h` files and builds them via CMake — used by the next stage (`easyasc-codegen`).

In this skill we only produce the Python file and run mode (1). The cake workflow runs mode (2) in a separate stage.

## A2 vs A5 — pick A2 by default

easyasc has two authoring surfaces:

| Surface | Import | Vec compute style | Use when |
|---|---|---|---|
| **A2** | `from easyasc.a2 import *` | Direct UB-tensor functions: `add(dst, src1, src2)`, `exp(dst, src)`, `cadd(dst, src)`, ... | **Default for cake Vector path.** Compiles to `ascend910b`, matches CAKE's evaluation target. |
| A5 | `from easyasc.a5 import *` | Register-level via `@vf()` micro-functions: `prev_reg <<= src[off]`; `curr_reg <<= curr_reg + prev_reg` | Only if the operator needs A5-specific cube features (matmul / `Position.L1`/`L0C`), or if `op_desc.json` explicitly targets `ascend950`. |

A5's pure-vec path is significantly more verbose because every vec compute must live inside a `@vf()` micro-function operating on `Reg` objects. For the elementwise / reduction kernels cake generates, A2 is the right surface.

If the operator is a CV/matmul, **A2 also exposes cube primitives** (`DBuff`, `Position.L1`/`Position.L0C`, `matmul()`, `GetCubeNum()`/`GetCubeIdx()`). Reference: `references/output_example/qk_matmul_batched.py`. Only fall back to `from easyasc.a5 import *` for A5-only features (@vf register kernels, fp8 micro-cast, cumsum scan, L0A/L0B direct access) — A5 codegen defaults to ascend950 and is not validated on 910B2.

## Mandatory imports

```python
from easyasc.a2 import *   # default for cake Vector path
import torch               # for the simulator self-check at the bottom of the file
```

## Core objects

| Object | What it is | Where it lives |
|---|---|---|
| `@kernel()` | Decorator that turns a Python function into an Ascend kernel | wraps the kernel function |
| `GMTensor` | Type annotation for a global-memory tensor argument | kernel parameter type |
| `Var` | Type annotation for a scalar argument (shape dim, attribute) | kernel parameter type |
| `Tensor(dtype, [shape], Position.X)` | Allocates an on-chip buffer | inside the kernel body |
| `DT.float` / `DT.half` / `DT.bfloat16` | Element data type | passed to `Tensor(...)` |
| `Position.UB` | UB scratchpad — almost everything in Vector kernels | passed to `Tensor(...)` |

## Argument order — enforced

`input GMTensor* → output GMTensor* → Var*`. Mixing this order raises an OpExec error at runtime.

```python
@kernel()
def softmax_custom(
    x: GMTensor,         # input
    y: GMTensor,         # output
    M: Var, N: Var,      # scalars (shape dims)
):
    ...
```

## Naming — hard constraint in cake

The kernel function name MUST be exactly `{op_name}_custom`. This name flows through codegen as the AscendC op type name (`_to_camel("softmax_custom") == "SoftmaxCustom"`) and is what CAKE's pybind wrapper calls (`aclnnSoftmaxCustom`).

## Core partitioning (Vector)

Pick how to split work across vector cores using dynamic helpers — never hardcode a count.

```python
total_chunks = CeilDiv(M, chunk_size)          # total tiles
chunks_per_core = CeilDiv(total_chunks, GetVecNum())
chunk_begin = Var(chunks_per_core * GetVecIdx())
chunk_end   = Min(chunk_begin + chunks_per_core, total_chunks)

for chunk_idx in range(chunk_begin, chunk_end):
    ...
```

## Two ways to express vec compute (A2)

### Style A — function form (`fn(dst, src1, src2, ...)`)
The canonical A2 form. `dst` must be a UB Tensor; functions mutate `dst` in place.

```python
add(dst, src1, src2)        # dst = src1 + src2
mul(dst, src1, src2)
exp(dst, src)               # dst = exp(src)
sqrt(dst, src)
cadd(dst, src)              # group reduction sum (32 lanes per group → 1 lane)
vmax(dst, src1, src2)
```

Full list: see `references/docs/api/a2_vec_math.md` — covers `add` `sub` `mul` `div` `vmax` `vmin` `vand` `vor` `muladddst` `exp` `ln` `abs` `rec` `sqrt` `rsqrt` `vnot` `relu` `cadd` `cgadd` `cpadd` `cmax` `cmin` etc.

### Style B — `<<=` shorthand
For elementwise expressions involving `+ - * /` and the `maximum(...)` / `minimum(...)` builders, you can write:

```python
val_ub <<= val_ub * -1.0          # scalar mul
out_ub <<= maximum(in_ub, 0.0)    # elementwise max with scalar
out_ub <<= maximum(a_ub, b_ub)    # elementwise max with tensor
```

Both work; use whichever is clearer. Mixing inside the same kernel is fine.

## Data movement — `<<=` and `auto_sync`

The `<<=` operator schedules a move (or, with a VecOP on the right, a vec compute). ALL moves and compute MUST be inside a `with auto_sync():` block — it inserts the right pipeline barriers.

```python
ub_in  = Tensor(DT.float, [tile_rows, N], Position.UB)
ub_out = Tensor(DT.float, [tile_rows, N], Position.UB)

with auto_sync():
    ub_in <<= x[row0:row0+tile_rows, 0:N]   # GM → UB load
    relu(ub_out, ub_in)                     # vec compute (Style A)
    y[row0:row0+tile_rows, 0:N] <<= ub_out  # UB → GM store
```

## A complete minimal kernel (LeakyReLU)

```python
from easyasc.a2 import *
import torch


@kernel()
def leaky_relu_custom(
    x: GMTensor, y: GMTensor,
    N: Var, tile: Var, negative_slope: Var,
):
    ub_in    = Tensor(DT.float, [tile], Position.UB)
    ub_neg   = Tensor(DT.float, [tile], Position.UB)
    ub_pos   = Tensor(DT.float, [tile], Position.UB)
    ub_out   = Tensor(DT.float, [tile], Position.UB)

    total_tiles    = CeilDiv(N, tile)
    tiles_per_core = CeilDiv(total_tiles, GetVecNum())
    t_begin        = Var(tiles_per_core * GetVecIdx())
    t_end          = Min(t_begin + tiles_per_core, total_tiles)

    for ti in range(t_begin, t_end):
        with auto_sync():
            off   = Var(ti * tile)
            count = Min(tile, N - off)

            ub_in <<= x[off:off + count]
            # positive part: max(x, 0)
            ub_pos <<= maximum(ub_in[0:count], 0.0)
            # negative part: min(x, 0) * negative_slope
            ub_neg <<= minimum(ub_in[0:count], 0.0)
            ub_neg <<= ub_neg * negative_slope
            # combine: pos + neg
            add(ub_out, ub_pos, ub_neg)

            y[off:off + count] <<= ub_out[0:count]


if __name__ == "__main__":
    torch.manual_seed(0)
    N, tile = 4096, 256
    negative_slope = 0.01

    x = torch.randn(N, dtype=torch.float32)
    y = torch.zeros(N, dtype=torch.float32)

    y_kernel = OpExec(leaky_relu_custom, simulator=True)(x, y, N, tile, negative_slope)
    y_ref = torch.nn.functional.leaky_relu(x, negative_slope=negative_slope)
    torch.testing.assert_close(y_kernel, y_ref, rtol=1e-5, atol=1e-5)
    print(f"max_abs_diff={torch.abs(y_kernel - y_ref).max().item():.6e}")
```

> If any API name above does not match what `references/docs/api/a2_vec_math.md` documents (the doc is the source of truth), prefer the doc. The DSL has evolved and the primer is just a starting sketch. If `references/docs/` itself is stale relative to a newer upstream easyasc release, consult `${EASYASC_DSL_HOME}/doc/` as the final fallback.

## Reductions across tiles (online accumulation)

For reductions like `sum`, `max` over a dimension whose size doesn't fit in UB, accumulate into a small scratch buffer across tile loops:

```python
acc_ub = Tensor(DT.float, [acc_lanes], Position.UB)
acc_ub <<= 0.0   # init

for tile_i in range(...):
    with auto_sync():
        ub_chunk <<= x[..., tile_i*tile : (tile_i+1)*tile]
        # group reduce within the chunk
        cadd(tmp_ub, ub_chunk)
        # accumulate into the running total
        add(acc_ub, acc_ub, tmp_ub)
```

For online softmax (subtract running max, accumulate scaled exp sum), see `references/constraints/online-softmax-tail.md`.

## A2 idioms you MUST know before writing reductions / norms / fused ops

> **Background.** A real cake debugging session reproduced 5 separate
> known-pitfall failures because the sub-agent never opened these files. All
> four constraints live under `references/constraints/` (mirrored from
> ops-lab). Each is small (<300 lines). Read them, don't paraphrase them.

### Required reads for Reduction / NN-Normalization / Loss-Reduce

1. **`vec-reduction-a2.md`** — `cadd` / `cmax` are **group reductions**: one repeat folds 64 fp32 lanes (= 8 C0 blocks of 8 each) into **one scalar**. They are NOT whole-row reductions. The canonical pattern is:
   ```
   cadd(per_row_scalar [M, 1], src [M, 64])     # one repeat per row
   brcb(broadcast      [M, 8], per_row_scalar [M, 1], dst_blk_stride=1, dst_rep_stride=8)
   mul (wide_dst       [M, 64], wide_src [M, 64], broadcast [M, 8])    # C0-block broadcast
   ```
   The `[M, 8]` shape on the brcb output is mandatory — it's how the hardware does scalar-into-row broadcast for a subsequent `mul/sub/add` against a wide `[M, 64]` tile.

2. **`reduction.md`** — covers multi-pass row stats (two-pass softmax, three-pass tiled softmax, online-softmax MLA stats, absmax / quant). RMSNorm-style ops follow the "two-pass per-row" pattern: pass 1 accumulates `sum(x^2)`, pass 2 reloads and applies `rsqrt(...)` & scale.

3. **`autosync.md`** — `auto_sync()` is **same-side queueing only**. Important non-edges:
   - **V → MTE2** has no autosync edge. A vec write (e.g. `dup(ub, 0.0)`) is NOT ordered before a later `<<= gm[...]` reload in the same `with auto_sync()` block.
   - **Control-lane Var reads are not tracked at all.** `Var(0.0) <<= ub_sum` (`GetValueFrom`) executes on the control lane and the simulator may read `ub_sum` before the vec-lane `cadd` finishes — producing 0. Stay in the vec lane (use tensor ops + `brcb`) instead of extracting scalars to Vars whenever you can.
   - If you really need cross-pipe ordering, the simulator-supported barrier is `bar_all()`; per-pipe `bar_v()` is a no-op there.

4. **`tail-safety.md`** — keep **local buffers full tile-sized**; apply `valid_h`, `valid_m`, `valid_k` only at the GM read/write slices. `<<=` lowers to `gm_to_ub_pad`, which auto-zero-pads the cols beyond `valid_h` — exactly what you want so `cadd` over the full `TILE_H` still yields the correct row sum.

### Runtime `1/N` from an int Var (e.g. mean over last dim)

This is **not in upstream's `a2-device.md` §7** — it tells you to precompute on the host. Inside the kernel, the A2 workaround is:

```python
n_lanes = 64                                  # one cadd repeat width on fp32
h_tile  = Tensor(DT.float, [TILE_M, 1], Position.UB)
inv_h_t = Tensor(DT.float, [TILE_M, 1], Position.UB)

with auto_sync():
    dup(h_tile, H)        # fill h_tile with int Var H — fp32-cast happens on the write
    rec(inv_h_t, h_tile)  # inv_h_t = 1 / h_tile, element-wise

# later, after cadd(sum_s [M, 1], sq_tile [M, TILE_H]):
with auto_sync():
    mul(sum_s, sum_s, inv_h_t)   # mean = sum * (1/H) per row; full Var-parametric, NOT baked
```

Why **not** `var_div(1.0, H)`: easyasc's `var_div` requires both operands to share dtype, and shape-dim Vars are `Datatype.int`. The float literal `1.0` and `int_var` mismatch → `TypeError`. The dup+rec dance materialises the cast onto the vector unit, sidestepping the type check.

Why **not** `inv_N = 1.0 / N.value` baked at codegen-time: it folds the codegen-time int into the kernel and breaks any other shape at runtime.

Why **not** `Var(0.0); Var(0.0) <<= int_var; 1.0 / Var(0.0)`: works **at simulator level for a single trace**, but `GetValueFrom`-style Var assignments execute on the control lane and don't cross the vec-pipe boundary cleanly when followed by a vec consumer like `muls(...)`.

### Where the canonical examples live

- **NN-Norm / per-row reduce-then-scale** → `references/output_example/add_rms_norm.py` (replaces the deleted stale `layer_norm.py`; cadd group reduction + brcb broadcast + dup+rec for runtime `1/H`)
- **Pure elementwise / activation (two-branch combine, e.g. PReLU/ELU/Hardsigmoid)** → `references/output_example/leaky_relu.py` (2-D `[1, TILE_N]`, demonstrates `maximum + minimum*slope`, runtime Var scalar via `muls`)
- **Simplest elementwise / transcendental** → `output/ReLU/ReLU_dsl.py` or `output/Sigmoid/Sigmoid_dsl.py` in the repo
- **Per-row reduce → row stat (sum/mean/max/min)** → `references/output_example/sum_reduction_over_a_dimension.py` (cadd → brcb → broadcast-mul; chain after for L1/L2/abs variants)
- **Softmax (single op, 3-pass tiled)** → `references/output_example/softmax.py` (supports H multiples of 64)
- **Flash-attn / online-softmax stats** → `references/output_example/flash_attn_full.py`
- **CV / matmul** → `references/output_example/qk_matmul_batched.py`

## Things to NOT do

- Do not hardcode core count (`16`, `40`). Use `GetVecNum()`.
- Do not call Python `math.exp(...)` on a `Tensor` — use the DSL's `exp(dst, src)`.
- Do not put data movement outside `with auto_sync():`.
- Do not allocate `Position.L1` / `Position.L0C` for pure Vector kernels — those are cube-only.
- Do not attempt `OpExec(..., simulator=False)` from this skill — that is the next stage's job.
- Do not import from `easyasc.a5` unless the operator pattern actually requires the A5-specific @vf/Reg surface.
- Do not allocate UB tensors with 1-D shape — current easyasc requires `Tensor(DT.float, [M, N], Position.UB)` (length-2 shape). The in-skill `output_example/` is now all 2-D canonical (any stale 1-D files have been upgraded as of the 5-month example refresh).
- Do not extract a Var from a UB tensor via `Var(0.0) <<= ub_tensor` in the middle of a `with auto_sync()` block — the read happens on the control lane and is NOT ordered with the vec-lane writes that produced the value. Keep reductions+scaling in tensor ops (use `brcb` for scalar→row broadcast).
- Do not write `inv_N = 1.0 / N` directly — `var_div` rejects mixed int/float dtypes. Use the `dup(fp_tile, int_var) → rec(inv_tile, fp_tile)` idiom (see "Runtime 1/N from an int Var" above).

## Things to consult `easyasc_dsl_pointers.md` for

All references below are now local (under `references/` in this skill); see `easyasc_dsl_pointers.md` for the path table.

- Which exact API to use for a given primitive (→ `docs/09_api_reference.md` / `docs/api/a2_vec_math.md`)
- Online softmax / reduction-fused topology (→ `docs/07_kernel_patterns.md`, `constraints/online-softmax-tail.md`)
- Tail handling and shape-not-divisible cases (→ `constraints/tail-safety.md`)
- cadd group reduction + brcb scalar broadcast (→ `constraints/vec-reduction-a2.md`)
- auto_sync edges (V↔MTE only; control-lane Var reads not synced) (→ `constraints/autosync.md`)
- A2 vs A5 differences (→ `docs/02_programming_model.md`)
- CV / matmul (A2 cube path) example (→ `output_example/qk_matmul_batched.py`)
