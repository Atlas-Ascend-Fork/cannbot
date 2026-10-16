# Var

This page documents `Var`, the scalar object used throughout the DSL for dimensions, loop counters, scalar arithmetic, and scalar IO between tensors and variables.

Although `Var` often looks like a normal Python scalar in user code, most of its operators are overloaded to build DSL instructions rather than perform plain host-side computation.

## 1. `Var`

### `Var(value=0, dtype=None, name="")`

- Purpose: represent a scalar value in kernel or micro code.
- Typical uses:
  - shape variables such as `M`, `N`, and `K`
  - counters such as `cnt`
  - loop-derived offsets
  - scalar arithmetic intermediates
  - scalar reads from UB or GM
- Constructor parameters:
  - `value`: `int`, `float`, another `Var`, or `None`
  - `dtype`: optional `DataTypeValue`
  - `name`: optional variable name

### Constructor inference rules

- If `dtype` is omitted:
  - `int` value -> `DT.int`
  - `float` value -> `DT.float`
  - `Var` value -> reuse the source `Var.dtype`
  - `None` -> leave dtype as `None`
- If `name=""` and `value` is not another `Var`, runtime creates a temporary name such as `_tmp_var_*`.
- If `value` is another `Var`:
  - the new object reuses the source variable's `idx`
  - the constructor copies the source variable's current `value`
  - this is alias-like behavior, not a deep independent clone
  - in practice, prefer arithmetic helpers or direct assignment over using `Var(existing_var)` as a copy API

### Instruction emission

- A fresh `Var(...)` created inside an active `@kernel` or `@vf` emits `create_var`.
- `Var(existing_var)` does not emit `create_var`.

Example:

```python
cnt = Var(0)
scale = Var(3.0, DT.float, "scale")
```

## 2. Stored State

A `Var` object mainly carries:

- `dtype`: scalar dtype, often `DT.int` or `DT.float`
- `name`: DSL symbol name
- `value`: optional concrete host-known value used for eager folding in simulator-friendly paths
- `idx`: internal identity used by the IR/runtime

Practical meaning:

- if `value` is known, many scalar operations compute `out.value` eagerly
- if `value` is unknown, the DSL still emits the symbolic instruction and defers evaluation

## 3. Arithmetic Operators

`Var` overloads scalar arithmetic and routes most operations to helpers in `easyasc.stub_functions.var_op`.

### `a * b`

- Calls `var_mul(a, b)`.
- Accepted operands:
  - `Var`
  - `int`
  - `float`
- Result dtype:
  - `DT.float` if either operand is float-like
  - otherwise `DT.int` if either operand is int-like
- Constant folding:
  - if both operand values are known, `out.value` is computed eagerly
- Emits:
  - `var_mul`

Example:

```python
rows_per_core = tile_m * GetCubeNum()
```

### `a + b`

- Calls `var_add(a, b)`.
- Accepted operands:
  - `Var`
  - `int`
  - `float`
- Result dtype:
  - float dominates int
- Constant folding:
  - eager when both values are known
- Emits:
  - `var_add`

Example:

```python
begin = tile_m_per_core * GetCubeIdx() + 4
```

### `a - b`

- Calls `var_sub(a, b)`.
- Accepted operands:
  - `Var`
  - `int`
  - `float`
- Result dtype:
  - float dominates int
- Constant folding:
  - eager when both values are known
- Emits:
  - `var_sub`

### `a / b` and `a // b`

- Both route to `var_div(a, b)`.
- Accepted operands:
  - `Var`
  - `int`
  - `float`
- Important restriction:
  - the two operands must resolve to the same dtype family
  - `int / float` or `float / int` is rejected unless you cast or construct matching types first
- Result behavior:
  - `DT.int` -> floor-style integer division
  - `DT.float` -> floating-point division
- Constant folding:
  - eager when both values are known and divisor is non-zero
- Emits:
  - `var_div`

Example:

```python
tile_m = M // 128
ratio = scale / coeff
```

### `a % b`

- Calls `var_mod(a, b)`.
- Accepted operands:
  - `Var`
  - `int`
- Restrictions:
  - both sides must be int-like
  - zero divisor raises when concrete values are known
- Result dtype:
  - always `DT.int`
- Constant folding:
  - eager when both values are known
- Emits:
  - `var_mod`

Example:

```python
slot = cnt % 2
```

### `a += b`

- `Var` implements `__iadd__`, but not general in-place `-=`, `*=`, `/=`, or `%=` overloads.
- Accepted operands:
  - `Var`
  - `int`
  - `float`
- Behavior:
  - keeps `self.dtype` unchanged
  - validates the rhs against `self.dtype` before emitting:
    - `DT.float` only accepts `float` or `Var(dtype=DT.float)`
    - integer-typed `Var` accepts Python `int`
    - integer-typed `Var` only accepts `Var` rhs when the rhs dtype matches exactly
  - emits `var_add` with `out=self`
- Important note:
  - this is still DSL-style scalar mutation, not plain Python host arithmetic

Example:

```python
cnt = Var(0)
cnt += 1
```

## 4. Assignment-Style Operators

### `var <<= other`

`Var.__ilshift__` supports three source categories.

#### `var <<= other_var`

- Purpose: scalar-to-scalar assignment.
- Restrictions:
  - source must be another `Var`
- Behavior:
  - emits `var_assign`
  - destination object is reused

Example:

```python
dst <<= src
```

#### `var <<= tensor`

- Equivalent to `var.GetValueFrom(tensor)`.
- Supported tensor sources:
  - `Tensor` at `Position.UB`
  - `GMTensor`
- Restrictions:
  - not supported inside `@vf`
  - destination `Var.dtype` must already be set
- Behavior:
  - emits `GetValueFrom`
  - simulator reads the first element of the flattened source view
  - that value is cast to `dst.dtype`

Example:

```python
scalar <<= ub[0:1, 0:1]
```

### `var >>= tensor`

- Equivalent to `var.SetValueTo(tensor)`.
- Supported destination:
  - `Tensor` at `Position.UB`
- Restrictions:
  - not supported inside `@vf`
  - destination must be a local UB tensor, not a `GMTensor`
  - source `Var.dtype` must already be set
- Behavior:
  - emits `SetValueTo`
  - simulator resolves the scalar value from the `Var`
  - writes that value into the first element of the flattened UB view
  - writeback uses the tensor dtype, so numeric conversion follows the tensor element type

Example:

```python
seed >>= ub
```

## 5. Explicit Scalar IO Methods

### `GetValueFrom(src)`

- Purpose: load a scalar from a tensor-like source into the `Var`.
- Parameters:
  - `src`: `Tensor` or `GMTensor`
- Restrictions:
  - not supported in `@vf`
  - destination `Var.dtype` must not be `None`
  - if `src` is `Tensor`, it must be at `Position.UB`
- Behavior:
  - emits `GetValueFrom`
  - in simulator:
    - reads `src_view[0]`
    - casts it to `dst.dtype`
    - stores the casted result as the current runtime value of the `Var`
- Practical meaning:
  - this is scalar extraction from the first element of the current source view, not a reduction over the whole tensor

Example:

```python
scalar = Var(0, DT.int)
scalar.GetValueFrom(ub)
```

GM example:

```python
scalar = Var(0, DT.int)
scalar.GetValueFrom(src_gm)
```

### `SetValueTo(dst_tensor)`

- Purpose: store the scalar value into a UB tensor view.
- Parameters:
  - `dst_tensor`: `Tensor`
- Restrictions:
  - not supported in `@vf`
  - destination tensor must be at `Position.UB`
  - `GMTensor` is not allowed
  - source `Var.dtype` must not be `None`
- Behavior:
  - emits `SetValueTo`
  - in simulator:
    - resolves the scalar runtime value
    - casts it using `Var.dtype`
    - writes the result into `dst_tensor` element `0`
- Practical meaning:
  - this is scalar-to-first-lane writeback, often used together with `GetValueFrom`

Example:

```python
seed = Var(3.75, DT.float)
seed.SetValueTo(ub)
```

## 6. Comparison Operators and `Expr`

Comparisons on `Var` do not produce Python `bool`. They produce `Expr` objects.

Supported operators:

- `==`
- `!=`
- `<`
- `<=`
- `>`
- `>=`

Example:

```python
cond = (cnt < limit)
```

### What `Expr` is

- `Expr` is a lightweight symbolic boolean-expression container.
- It stores the generated expression string, not a concrete Python truth value.

### Important restriction

- `Expr` cannot be used in normal Python boolean context.
- Calling `bool(expr)` raises:
  - `TypeError("Expr cannot be used in Python boolean context, use If/Elif/Else instead")`

This is why kernel control flow should use:

- `If(...)`, `Elif(...)`, `Else(...)`
- or native Python `if/elif/else` inside decorated functions, letting the framework rewrite the AST

### `Expr` logical combinators

- `expr_a & expr_b` -> logical `&&`
- `expr_a | expr_b` -> logical `||`
- `~expr` -> logical `!`

Example:

```python
cond = (cnt < end) & (tile_m != 0)
```

## 7. Value Folding vs Symbolic Execution

`Var` mixes two worlds:

- host-known scalar values in `value`
- symbolic IR instructions recorded into the active kernel or micro module

That means a `Var` operation can do both at once:

1. compute a concrete `out.value` immediately when inputs are known
2. still emit a DSL instruction such as `var_add` or `var_div`

This dual behavior is why `Var` is useful both for simulator execution and for symbolic code generation.

## 8. Usage Notes

- Give shape and loop-control variables explicit dtypes when clarity matters, especially for division and modulo.
- Prefer `DT.int` for counters, loop indices, and tile arithmetic.
- Prefer `DT.float` for scalar math that will later feed float computations.
- Use `GetValueFrom` / `SetValueTo` only when you really mean "first element of this view".
- Do not use `Var` comparisons as normal Python conditions outside the DSL rewriting flow.
