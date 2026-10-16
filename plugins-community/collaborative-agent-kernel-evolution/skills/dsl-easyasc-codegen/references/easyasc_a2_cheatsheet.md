# easyasc.a2 cheatsheet

A2 (Ascend 910B) DSL surface. Use for kernels that will be **compiled to AscendC and run on the host machine**.

> Parallel surface to `easyasc.a5`, not a compatibility layer. Different instruction families. Pick by target device.

## Imports

```python
from easyasc.a2 import *
```

This pulls in: `@kernel`, `@func`, `@vf`, `@auto_sync`, `Tensor`, `GMTensor`, `DBuff`, `TBuff`, `Var`, `Reg`, `RegList`, `MaskReg`, `OpExec`, `DT`, `Position`, plus a2-specific cube + vec stub functions and high-level shortcuts (`matmul`, `CeilDiv`, `Min`, `Max`, `GetCubeIdx`, `GetCubeNum`, `GetVecIdx`, `GetVecNum`, etc.).

## The five-line kernel skeleton

```python
@kernel()
def my_kernel(x: GMTensor, y: GMTensor, z: GMTensor, M: Var, N: Var, K: Var):
    l1x = Tensor(DT.half, [M, K], Position.L1)   # on-chip declarations
    l1y = Tensor(DT.half, [K, N], Position.L1)
    l0c = Tensor(DT.float, [M, N], Position.L0C)

    l1x <<= x[:, :]                              # GM -> L1
    l1y <<= y[:, :]
    matmul(l0c, l1x, l1y, m=M, n=N, k=K, is_init=True)
    z[:, :] <<= l0c                              # L0C -> GM
    return z
```

Argument order rule: **all GMTensor (input then output) come before all Var**. OpExec validates this.

## Data types

`DT.half`, `DT.float`, `DT.bfloat16`, `DT.int8`, `DT.uint8`, `DT.int32`, `DT.int16`. Element sizes drive `C0` and stride math:

| dtype | bytes | C0 |
|---|---|---|
| int8/uint8 | 1 | 32 |
| half/bfloat16 | 2 | 16 |
| float/int32 | 4 | 8 |

## Storage positions

- `Position.L1` — main on-chip cube buffer
- `Position.L0A` / `Position.L0B` — cube operand panes (NZ packed)
- `Position.L0C` — cube accumulator (fixed C0=16, dtype-agnostic)
- `Position.UB` — vec workspace (the only place vec ops are legal)

`<<=` chooses the right move instruction by inspecting source + dest positions:

```
l1 <<= gm[:, :]      # GM->L1 (cube path)
ub <<= gm_or_l1[...] # ->UB
gm[...] <<= l0c      # L0C->GM
gm[...] <<= ub       # UB->GM (vec writeback)
```

## Buffers (DBuff / TBuff) — pipelining

```python
l1q = DBuff(DT.half, [M, K], Position.L1)   # 2-slot ring
cnt = Var(0)
for ...:
    l1q[cnt] <<= q[...]                      # writes slot (cnt % 2)
    matmul(l0c[cnt], l1q[cnt], ...)
    cnt += 1
```

Slot lineage drives auto-sync handshake. Use `DBuff` for double-buffer; `TBuff` for triple.

## Cube primitives (a2)

- `matmul(dst_l0c, l1a, l1b, m=, n=, k=, is_init=True/False)` — high-level shortcut
- `gm_to_l1_nd2nz`, `set_constant_to_l1`, `l1_to_l0`, `mmad`, `l0c_to_gm_nz2nd`, `l0c_to_l1`, `l0c_to_ub` — lower-level
- A2 cube path is the C220 family (`device_type` startswith `b`); A5 cube is C310 (950)
- L1/L0A/L0B use NZ layout: `[block_n, aligned_m, C0]`

## Vec primitives (a2 — UB-only)

Available top-level math (all consume vec mask on dst writeback):

```
add  sub  mul  div  vmax  vmin  vand  vor  muladddst
adds subs muls vmaxs vmins   # *_scalar variants
exp  log  abs  ln  sqrt  rsqrt  rec  brcb  cast
cadd cmax cmin cgadd cgmax cgmin cpadd   # group reductions
dup  compare  compare_scalar  select  gather  scatter
```

Data movement on vec side (a2 exports the **pad** subset): `gm_to_ub_pad`, `ub_to_gm_pad`, `ub_to_ub`.

Mask conventions:
- binary/unary/`dup`: masked lanes preserve old `dst` value
- `cadd/cpadd/cgadd`: masked source treated as `0`
- `cmax/cgmax`: masked source treated as `-inf`
- `cmin/cgmin`: masked source treated as `+inf`
- `compare/select/gather/scatter`: ignore vec mask (currently)

## Control flow rewrites

These Python forms are **rewritten by the parser** inside `@kernel`/`@func`/`@vf`:

- `for i in range(begin, end[, step]):` → `start_loop`/`end_loop` IR (NOT a Python loop)
- `if/elif/else` → `with If(...): / with Elif(...): / with Else():`
- `and`/`or`/`not` → bitwise forms
- `break`/`continue` inside DSL `range` → `break_()`/`continue_()`
- `unroll(...)` is authoring-time unroll (`break`/`continue` not allowed inside)

For conditions whose evaluation itself emits IR (e.g. `GetSubBlockIdx() == 0`), `elif` is supported and evaluation is correctly deferred.

## Synchronization

```python
with auto_sync():
    for ... :          # parser inserts intra-side handshakes for supported pipe pairs
        ...
```

Cross-side ownership (cube↔vec) still needs explicit `bind_cv_mutex` / `bind_vc_mutex` on a `GMTensor`.

Pipe families:
- cube side: MTE2, MTE1, M, FIX
- vec side:  MTE2, V, MTE3

## Common pitfalls

- **Argument ordering**: all `GMTensor` first (inputs then outputs), all `Var` last. Mixing fails OpExec validation.
- **Shape ambiguity**: when two `Var`s carry the same int value at runtime, OpExec can't infer which dim binds where — pass `shape_bindings={tensor_idx: [scalar_idx_per_dim]}` to `OpExec.__call__`.
- **Vec ops on non-UB tensors**: rejected. Move to UB first.
- **`Tensor.T` only legal on L1**.
- **micro `@vf` only takes UB tensors + scalars** as inputs.
- **Tail handling**: write tile loops with `Min(begin + TILE, total)` and don't assume divisibility.
- **UB Tensor 维度必须是编译时常数**：`Tensor(DT.float, [1, TILE_L], Position.UB)` 中
  `TILE_L` 必须是 Python 字面量或模块级常数，不能是 `Var` 或从 `make_inputs()` 的
  shape 推导的值。若运行时 `row_len` 可能超过 `TILE_L`，必须用内循环分块（见下方
  "UB Tiling 模板"）。违反此规则会导致 smoke PASS 但 evaluation 精度失败
  （特定 shape 超界时出现 `pattern=algorithm_error`）。
- **Tensor 下标必须是 slice**：`x_ub[0:1, :]` 合法；`x_ub[var_idx, :]` / `x_ub[0, :]`
  非法（parse 阶段报 `TypeError: dimN index must be slice, got int/Var`）。
  需要"按某维度随机访问 UB"时，在 `make_inputs()` 中预展开成逐元素形式。

## Reference: examples in this skill

- `examples_a2/matmul.py` — cube-only batched QK matmul (good DBuff/CeilDiv/GetCubeIdx pattern)
- `examples_a2/sort_rows.py` — vec-only row sort
- `examples_a2/flash_attention.py` — full cube↔vec fused flash attention

## UB Tiling 模板（支持任意 row_len）

当算子需要在空间维度（row_len）上分块处理时，使用此模板。
`TILE_L` 必须是编译时常数，满足 `buffers × TILE_L × sizeof(T) ≤ UB 总容量`。

```python
from easyasc.a2 import *

TILE_L = 128   # ← 编译时常数；根据 UB 预算和 dtype 调整


@kernel()
def kernel(
    x_gm:  GMTensor,   # [total_rows, row_len]  float32  — 输入
    y_gm:  GMTensor,   # [total_rows, row_len]  float32  — 输出
    total_rows: Var,
    row_len:    Var,
):
    # 多核行切分
    rows_per_core = CeilDiv(total_rows, GetVecNum())
    row_start = Var(rows_per_core * GetVecIdx())
    row_end   = Min(row_start + rows_per_core, total_rows)

    # UB buffer — 大小固定为 TILE_L（编译时常数）
    x_ub = Tensor(DT.float, [1, TILE_L], Position.UB)
    y_ub = Tensor(DT.float, [1, TILE_L], Position.UB)

    # 行内 tile 循环：支持任意 row_len（含 row_len > TILE_L 的情况）
    n_tiles = CeilDiv(row_len, TILE_L)

    for r in range(row_start, row_end):
        for t in range(0, n_tiles):
            l_start = Var(t * TILE_L)
            l_end   = Min(l_start + TILE_L, row_len)  # 尾块自动处理
            with auto_sync():
                x_ub <<= x_gm[r:r + 1, l_start:l_end]

                # ---- 在此处插入计算逻辑（操作 x_ub → y_ub）----
                # 示例：y = x * scale + shift（逐元素）
                # muls(y_ub, x_ub, scale_scalar)
                # adds(y_ub, y_ub, shift_scalar)

                y_gm[r:r + 1, l_start:l_end] <<= y_ub

    return y_gm


def make_inputs():
    # ⚠️ 务必覆盖 api_description.md 中最大的 row_len 值（而非只用 shape_info 的小 shape）
    B, C, L = 4, 768, 128   # 示例：请替换为实际最大 shape
    x = torch.randn(B * C, L, dtype=torch.float32)
    y = torch.zeros_like(x)
    return (x, y, B * C, L)


def reference(*inputs):
    x, y_out, total_rows, row_len = inputs
    # 返回与 kernel 输出对应的 PyTorch 参考值
    return x  # 示例：identity（请替换为实际计算）
```
