# Shared Scalar Helper Functions

This page documents the public scalar-oriented helpers shared conceptually across `easyasc.a2` and `easyasc.a5`.

These helpers build or query scalar `Var` values that are commonly used for:

- tiling math
- worker scheduling
- alignment
- scalar arithmetic on loop bounds and shape values

## 1. Scheduling and Worker Query Helpers

### `CeilDiv(a, b, name="")`

- Purpose: Create a `Var` equal to ceil-division of `a / b`.
- Parameters:
  - `a`, `b`: `Var` or `int`
  - `name`: optional output variable name
- Restrictions:
  - only `Var` and `int` are accepted
- Example:

```python
tiles = CeilDiv(M, 128)
```

### `GetCubeNum(name="")`

- Purpose: Return the number of available cube workers as a `Var`.
- Parameters:
  - `name`: optional output variable name
- Restrictions:
  - intended for kernel-side scheduling logic
- Example:

```python
num_cube = GetCubeNum()
```

### `GetCubeIdx(name="")`

- Purpose: Return the current cube worker index as a `Var`.
- Parameters:
  - `name`: optional output variable name
- Restrictions:
  - intended for kernel-side scheduling logic
- Example:

```python
cube_idx = GetCubeIdx()
```

### `GetVecNum(name="")`

- Purpose: Return the number of available vec workers as a `Var`.
- Parameters:
  - `name`: optional output variable name
- Restrictions:
  - intended for vec-side ownership logic
- Example:

```python
num_vec = GetVecNum()
```

### `GetVecIdx(name="")`

- Purpose: Return the current vec worker index as a `Var`.
- Parameters:
  - `name`: optional output variable name
- Restrictions:
  - intended for vec-side ownership logic
- Example:

```python
vec_idx = GetVecIdx()
```

### `GetSubBlockIdx(name="")`

- Purpose: Return the current subblock index as a `Var`.
- Parameters:
  - `name`: optional output variable name
- Restrictions:
  - commonly used for tail-safe vec writeback partitioning
- Example:

```python
sb = GetSubBlockIdx()
```

## 2. Scalar Math and Alignment

### `scalar_sqrt(a, name="")`

- Purpose: Create a scalar `Var` equal to `sqrt(a)`.
- Parameters:
  - `a`: `Var` or `float`
  - `name`: optional output name
- Restrictions:
  - `Var` input must be float-typed
- Example:

```python
inv_scale = scalar_sqrt(scale)
```

### `Align8(a, name="")`

- Purpose: Round an integer scalar up to the next multiple of 8.
- Parameters:
  - `a`: `Var` or `int`
  - `name`: optional output name
- Restrictions:
  - `Var` input must be int-typed
- Example:

```python
aligned = Align8(K)
```

### `Align16(a, name="")`

- Purpose: Round an integer scalar up to the next multiple of 16.
- Parameters:
  - `a`: `Var` or `int`
  - `name`: optional output name
- Restrictions:
  - `Var` input must be int-typed
- Example:

```python
aligned = Align16(K)
```

### `Align32(a, name="")`

- Purpose: Round an integer scalar up to the next multiple of 32.
- Parameters:
  - `a`: `Var` or `int`
  - `name`: optional output name
- Restrictions:
  - `Var` input must be int-typed
- Example:

```python
aligned = Align32(K)
```

### `Align64(a, name="")`

- Purpose: Round an integer scalar up to the next multiple of 64.
- Parameters:
  - `a`: `Var` or `int`
  - `name`: optional output name
- Restrictions:
  - `Var` input must be int-typed
- Example:

```python
aligned = Align64(K)
```

### `Align128(a, name="")`

- Purpose: Round an integer scalar up to the next multiple of 128.
- Parameters:
  - `a`: `Var` or `int`
  - `name`: optional output name
- Restrictions:
  - `Var` input must be int-typed
- Example:

```python
aligned = Align128(N)
```

### `Align256(a, name="")`

- Purpose: Round an integer scalar up to the next multiple of 256.
- Parameters:
  - `a`: `Var` or `int`
  - `name`: optional output name
- Restrictions:
  - `Var` input must be int-typed
- Example:

```python
aligned = Align256(M)
```

## 3. Scalar Arithmetic Builders

### `var_mul(a, b, name="")`

- Purpose: Build a scalar `Var` for multiplication.
- Parameters:
  - `a`, `b`: `Var`, `int`, or `float`
  - `name`: optional output name
- Restrictions:
  - accepted types are only `Var`, `int`, and `float`
  - result dtype is inferred from the operands
- Example:

```python
numel = var_mul(M, K)
```

### `var_add(a, b, name="")`

- Purpose: Build a scalar `Var` for addition.
- Parameters:
  - `a`, `b`: `Var`, `int`, or `float`
  - `name`: optional output name
- Restrictions:
  - accepted types are only `Var`, `int`, and `float`
- Example:

```python
end = var_add(start, block)
```

### `var_sub(a, b, name="")`

- Purpose: Build a scalar `Var` for subtraction.
- Parameters:
  - `a`, `b`: `Var`, `int`, or `float`
  - `name`: optional output name
- Restrictions:
  - accepted types are only `Var`, `int`, and `float`
- Example:

```python
remaining = var_sub(N, n0)
```

### `var_div(a, b, name="")`

- Purpose: Build a scalar `Var` for division.
- Parameters:
  - `a`, `b`: `Var`, `int`, or `float`
  - `name`: optional output name
- Restrictions:
  - accepted types are only `Var`, `int`, and `float`
- Example:

```python
ratio = var_div(total, parts)
```

### `var_mod(a, b, name="")`

- Purpose: Build a scalar `Var` for modulo.
- Parameters:
  - `a`, `b`: `Var` or `int`
  - `name`: optional output name
- Restrictions:
  - only integer-like operands are supported
- Example:

```python
slot = var_mod(cnt, 2)
```

### `Min(a, b, name="")`

- Purpose: Build a scalar `Var` representing the minimum of two values.
- Parameters:
  - `a`, `b`: `Var`, `int`, or `float`
  - `name`: optional output name
- Restrictions:
  - accepted types are only `Var`, `int`, and `float`
- Example:

```python
valid_m = Min(BLK, m2 - m)
```

### `Max(a, b, name="")`

- Purpose: Build a scalar `Var` representing the maximum of two values.
- Parameters:
  - `a`, `b`: `Var`, `int`, or `float`
  - `name`: optional output name
- Restrictions:
  - accepted types are only `Var`, `int`, and `float`
- Example:

```python
row_max = Max(prev_max, curr_max)
```
