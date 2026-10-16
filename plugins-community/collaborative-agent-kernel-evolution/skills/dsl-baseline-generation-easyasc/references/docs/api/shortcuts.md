# Shortcuts

This page documents the public shortcut-style helpers shared conceptually across `easyasc.a2` and `easyasc.a5`.

These helpers are higher-level convenience entry points rather than low-level instruction primitives.

## 1. Matmul Shortcut

### `matmul(dst, l1a, l1b, splitn=None, splitk=None, m=None, n=None, k=None, is_init=True)`

- Purpose: Emit the standard matmul path used by most repository kernels, including optional split-N or split-K staging.
- Parameters:
  - `dst`: `Tensor` in `L0C`
  - `l1a`, `l1b`: input `Tensor` objects in `L1`
  - `splitn`: optional split size for N-tiling
  - `splitk`: optional split size for K-tiling
  - `m`, `n`, `k`: optional explicit logical dimensions
  - `is_init`: whether the destination accumulation starts from zero
- Restrictions:
  - only valid inside an active kernel
  - `dst` must be `Position.L0C`
  - `l1a` and `l1b` must be `Position.L1`
  - `splitn` and `splitk` cannot both be set
  - the active kernel must have the framework-managed `_l0a`, `_l0b`, `_l0acnt`, and `_l0bcnt` buffers
- Example:

```python
matmul(l0c, l1x, l1y, m=M, n=N, k=K, is_init=True)
```

## 2. VecOP Convenience Builders

### `maximum(a, b)`

- Purpose: Build a `VecOP` representing elementwise max between a tensor and another tensor or scalar.
- Parameters:
  - `a`, `b`: one tensor plus either another tensor or a scalar/`Var`
- Restrictions:
  - at least one operand must be a `Tensor`
  - the returned object must be consumed by `<<=`
- Example:

```python
dst <<= maximum(src, 0.0)
```

### `minimum(a, b)`

- Purpose: Build a `VecOP` representing elementwise min between a tensor and another tensor or scalar.
- Parameters:
  - `a`, `b`: one tensor plus either another tensor or a scalar/`Var`
- Restrictions:
  - at least one operand must be a `Tensor`
  - the returned object must be consumed by `<<=`
- Example:

```python
dst <<= minimum(src1, src2)
```
