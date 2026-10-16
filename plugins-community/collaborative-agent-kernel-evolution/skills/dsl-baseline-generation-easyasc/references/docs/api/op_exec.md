# OpExec

This page documents the public runtime-entry helper shared conceptually across `easyasc.a2` and `easyasc.a5`.

`shape_bindings` is part of the `OpExec(...)` call-time API. It is used only on the Python runtime side, before the kernel body runs. Its job is to tell `OpExec` which runtime scalar should be reused as the symbolic shape variable for each input/output tensor dimension when plain value-based matching would be ambiguous.

## 1. `OpExec`

### `OpExec(op_func, out_dir="", cann_path=None, custom_op_path=None, profile=False, gen_only=False, simulator=False, skip_compile=False, trace=None)`

- Purpose: Bind runtime inputs to a kernel, then run it through either the simulator path or the generation path.
- Parameters:
  - `op_func`: a kernel wrapper created by `@kernel`
  - `out_dir`: output directory prefix used by generation mode
  - `cann_path`: optional toolchain path override
  - `custom_op_path`: optional custom-op template path
  - `profile`: enable profile-oriented generation behavior
  - `gen_only`: emit artifacts without running the generated path
  - `simulator`: enable simulator execution through `KernelBase.run_sim()`; current accepted truthy spellings such as `True`, `"v2"`, and `"legacy"` all route to the current V2 runtime under `easyasc/simulator_v2/`
  - `skip_compile`: skip `b.sh` in generation mode
  - `trace`: simulator trace output path
- Runtime call:

```python
OpExec(...)(*tensor_args, *scalar_args, shape_bindings=...)
```

- Restrictions:
  - `op_func` must be a `KernelBase` instance
  - runtime call order is strict: all `torch.Tensor` inputs first, then scalar `int`/`float` values
  - `trace` is only valid when `simulator=True`
  - repeated scalar values may require explicit `shape_bindings`
- Return value:
  - returns `torch.Tensor` outputs in simulator mode
  - returns generated-path outputs according to the normal `OpExec` runtime contract in generation mode
- Example:

```python
z_out = OpExec(my_kernel, simulator=True)(
    x,
    y,
    z,
    M,
    N,
    K,
    shape_bindings={0: [0, 2], 1: [1, 2], 2: [0, 1]},
)
```

## 2. `shape_bindings`

### Purpose

`shape_bindings` controls how `OpExec` reconstructs symbolic `GMTensor` shapes from runtime `torch.Tensor` shapes and runtime scalar arguments.

When you call:

```python
OpExec(my_kernel)(x, y, z, M, N, K, shape_bindings=...)
```

`OpExec` must build kernel-side objects like:

```python
GMTensor(dtype, [M, K])
GMTensor(dtype, [N, K])
GMTensor(dtype, [M, N])
```

However, at runtime it only sees concrete values such as:

```python
x.shape == (5, 5)
y.shape == (9, 5)
z.shape == (5, 9)
M == 5
N == 9
K == 5
```

In that situation, a tensor dimension with value `5` could mean either `M` or `K`. `shape_bindings` disambiguates that mapping.

### Type

```python
shape_bindings: Dict[int, Sequence[Optional[int]]]
```

### Index meaning

- Dictionary key: tensor argument index, counted only among `torch.Tensor` arguments.
- Sequence element: scalar argument index, counted only among scalar arguments (`int` / `float`) that come after all tensors.
- `None`: do not force this tensor dimension to a specific scalar; let `OpExec` infer it automatically.

For:

```python
OpExec(my_kernel)(x, y, z, M, N, K, shape_bindings=...)
```

the indices are:

- tensor `0` -> `x`
- tensor `1` -> `y`
- tensor `2` -> `z`
- scalar `0` -> `M`
- scalar `1` -> `N`
- scalar `2` -> `K`

So:

```python
shape_bindings = {
    0: [0, 2],  # x.shape == [M, K]
    1: [1, 2],  # y.shape == [N, K]
    2: [0, 1],  # z.shape == [M, N]
}
```

means:

- bind `x.shape[0]` to scalar `M`
- bind `x.shape[1]` to scalar `K`
- bind `y.shape[0]` to scalar `N`
- bind `y.shape[1]` to scalar `K`
- bind `z.shape[0]` to scalar `M`
- bind `z.shape[1]` to scalar `N`

### Exact runtime behavior

For each tensor dimension, `OpExec` applies the following rules.

#### Case 1: explicit binding is provided

If `shape_bindings[tensor_idx][dim_idx]` is an integer `scalar_idx`, `OpExec`:

1. checks that `scalar_idx` is in range
2. reads that runtime scalar
3. checks that `scalar_value == tensor.shape[dim_idx]`
4. if they match, uses that scalar `Var` in the constructed `GMTensor` shape
5. if they do not match, raises an error

Example:

```python
x.shape == (5, 7)
M == 5
K == 3

shape_bindings = {
    0: [0, 2],  # tries to bind x.shape[1] to K
}
```

This fails because `x.shape[1] == 7`, but `K == 3`.

#### Case 2: no explicit binding and no scalar matches

If no scalar has the same runtime value as the tensor dimension, `OpExec` keeps that dimension as a plain integer literal.

Example:

```python
x.shape == (32, 48)
M == 32
K == 64
```

Then `x.shape[1] == 48` matches no scalar, so the constructed shape becomes effectively:

```python
[M, 48]
```

#### Case 3: no explicit binding and exactly one scalar matches

If exactly one scalar has the same runtime value as the tensor dimension, `OpExec` binds that dimension to the matching scalar automatically.

Example:

```python
x.shape == (32, 64)
M == 32
K == 64
```

Then `x` is inferred as:

```python
[M, K]
```

No `shape_bindings` entry is needed.

#### Case 4: no explicit binding and multiple scalars match

If more than one scalar has the same runtime value as the tensor dimension, `OpExec` refuses to guess and raises an ambiguity error.

Example:

```python
x.shape == (5, 5)
y.shape == (9, 5)
z.shape == (5, 9)
M == 5
N == 9
K == 5
```

Here every dimension whose value is `5` is ambiguous because both `M` and `K` equal `5`. In this situation you must bind the ambiguous dimensions explicitly.

### Why it exists

The kernel body usually uses symbolic scalar variables such as `M`, `N`, and `K` in:

- tensor declarations
- loop bounds
- tile math
- tail handling
- address calculations

`OpExec` therefore tries to reuse runtime scalar `Var` objects when building `GMTensor` shapes. That preserves the symbolic relationship between tensor dimensions and scalar parameters. `shape_bindings` exists because runtime value equality alone is sometimes not enough to recover that relationship.

### When you need it

Use `shape_bindings` when both of the following are true:

1. one or more kernel scalar arguments represent tensor dimensions
2. two or more of those scalar arguments have the same runtime value, so a tensor dimension could match multiple scalars

Typical case:

```python
M = 128
N = 256
K = 128
```

Now a dimension value of `128` could mean either `M` or `K`.

### When you do not need it

You usually do not need `shape_bindings` when:

- every tensor dimension matches at most one scalar value
- a dimension matches no scalar at all and can stay as a literal integer
- the kernel has no scalar shape arguments

Example without ambiguity:

```python
M = 64
N = 128
K = 256
x.shape == (64, 256)
y.shape == (128, 256)
z.shape == (64, 128)
```

Each dimension value matches a unique scalar, so `OpExec` can infer the symbolic mapping automatically.

### Partial bindings are allowed

You do not need to bind every tensor dimension. You only need to bind the dimensions that would otherwise be ambiguous.

Example:

```python
shape_bindings = {
    0: [0, 2],      # fully bind x
    2: [0, None],   # bind z.shape[0], infer z.shape[1]
}
```

This is valid as long as each unbound dimension is still unambiguous at runtime.

### Validation rules

`OpExec` validates `shape_bindings` strictly.

- `shape_bindings` must be a `dict`
- each value must be a `list` or `tuple`
- binding rank must equal the rank of the corresponding tensor
- each element must be `int` or `None`
- explicit scalar indices must be in range
- explicit bindings must match the actual runtime tensor dimension value

### Common error cases

#### Ambiguity error

If a dimension matches multiple scalar values and you did not bind it explicitly, `OpExec` raises:

```python
ValueError: Ambiguous scalar match for tensor #... dim #...
```

This means the runtime cannot decide which scalar variable should own that dimension.

#### Mismatch error

If you explicitly bind a dimension to the wrong scalar index, `OpExec` raises:

```python
ValueError: shape_bindings[...][...] mismatches tensor dim value
```

This means your declared symbolic binding disagrees with the actual runtime shape.

### Full example

Kernel signature:

```python
@kernel()
def my_kernel(x: GMTensor, y: GMTensor, z: GMTensor, m: Var, n: Var, k: Var):
    return z
```

Runtime call:

```python
m = 5
n = 9
k = 5

x = torch.randn((m, k), dtype=torch.float16)
y = torch.randn((n, k), dtype=torch.float16)
z = torch.randn((m, n), dtype=torch.float16)

out = OpExec(my_kernel, simulator=True)(
    x,
    y,
    z,
    m,
    n,
    k,
    shape_bindings={
        0: [0, 2],
        1: [1, 2],
        2: [0, 1],
    },
)
```

Without `shape_bindings`, the dimensions whose value is `5` would be ambiguous.

### Practical rule of thumb

If your kernel takes explicit scalar shape arguments such as `M`, `N`, `K`, `B`, `H`, or `S`, and two of them might be equal at runtime, add `shape_bindings` at the `OpExec(...)` call site. It is cheap, explicit, and prevents shape inference from depending on accidental runtime uniqueness.
