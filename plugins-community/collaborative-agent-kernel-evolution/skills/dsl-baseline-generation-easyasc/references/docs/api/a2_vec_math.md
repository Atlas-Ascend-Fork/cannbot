# A2 Vector Math

This page covers the UB vector math helpers exported directly by `easyasc.a2`.

Important scope note:

- these names are top-level functions in `a2`
- the same names in `a5` usually refer to micro register operations instead

## Mask behavior summary

Before reading individual APIs, keep this current simulator summary in mind:

- Binary / unary / unary-scalar / `dup`
  - consume the current vec mask at dst writeback
  - masked-off lanes keep the previous `dst` value
- Group reductions
  - `cadd`, `cgadd`, `cpadd`: masked-off source slots contribute `0`
  - `cmax`, `cgmax`: masked-off source slots behave like `-inf`
  - `cmin`, `cgmin`: masked-off source slots behave like `+inf`
  - when an entire active reduction domain is masked off, the corresponding `dst` slot is not overwritten
- `brcb`
  - currently ignores the current vec mask state
- Related control ops documented on the A2 vec control page
  - `compare`, `compare_scalar`, `select`, `gather`, and `scatter` currently ignore the current vec mask state

## 1. Shared Binary Vec Parameters

The following functions share the same parameter shape:

- `add`
- `sub`
- `mul`
- `div`
- `vmax`
- `vmin`
- `vand`
- `vor`
- `muladddst`

Shared parameters:

- `dst`: destination UB `Tensor`
- `src1`, `src2`: source UB `Tensor`
- `repeat`: optional repeat count; inferred from `dst` when omitted
- `*_blk_stride`: optional block strides
- `*_rep_stride`: optional repeat strides

Shared restrictions:

- `dst`, `src1`, and `src2` must all be `Tensor` in `Position.UB`
- all three dtypes must match
- every stride or repeat parameter must be `int` or `Var` when provided
- these ops consume the current vec mask at dst writeback; masked-off lanes keep the previous `dst` value

### `add(dst, src1, src2, ...)`

- Purpose: Elementwise vector add, `dst = src1 + src2`.
- Parameters: use the shared binary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`, `int`
- Example:

```python
add(dst, src1, src2)
```

### `sub(dst, src1, src2, ...)`

- Purpose: Elementwise vector subtract, `dst = src1 - src2`.
- Parameters: use the shared binary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`, `int`
- Example:

```python
sub(dst, src1, src2)
```

### `mul(dst, src1, src2, ...)`

- Purpose: Elementwise vector multiply, `dst = src1 * src2`.
- Parameters: use the shared binary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`, `int`
- Example:

```python
mul(dst, src1, src2)
```

### `div(dst, src1, src2, ...)`

- Purpose: Elementwise vector divide, `dst = src1 / src2`.
- Parameters: use the shared binary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`
- Example:

```python
div(dst, src1, src2)
```

### `vmax(dst, src1, src2, ...)`

- Purpose: Elementwise vector max between two tensors.
- Parameters: use the shared binary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`, `int`
- Example:

```python
vmax(dst, src1, src2)
```

### `vmin(dst, src1, src2, ...)`

- Purpose: Elementwise vector min between two tensors.
- Parameters: use the shared binary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`, `int`
- Example:

```python
vmin(dst, src1, src2)
```

### `vand(dst, src1, src2, ...)`

- Purpose: Elementwise bitwise and on vector tensors.
- Parameters: use the shared binary vec parameter set above.
- Restrictions:
  - supported dtypes: `int16_t`, `uint16_t`
  - for bitwise views of other 16-bit data, use explicit `reinterpret(...)` first
- Example:

```python
vand(dst, src1, src2)
```

### `vor(dst, src1, src2, ...)`

- Purpose: Elementwise bitwise or on vector tensors.
- Parameters: use the shared binary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`, `int`
  - if you need strict bit semantics for float/half data, consider explicit `reinterpret(...)`
- Example:

```python
vor(dst, src1, src2)
```

### `muladddst(dst, src1, src2, ...)`

- Purpose: Multiply `src1` and `src2`, then accumulate into `dst`.
- Parameters: use the shared binary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`, `int`
  - use it only when `dst` already contains the value you want to accumulate into
- Example:

```python
muladddst(dst, src1, src2)
```

## 2. Shared Unary Vec Parameters

The following functions share this parameter pattern:

- `exp`
- `ln`
- `abs`
- `rec`
- `sqrt`
- `rsqrt`
- `vnot`
- `relu`

Shared parameters:

- `dst`: destination UB `Tensor`
- `src`: source UB `Tensor`
- `repeat`: optional repeat count
- `dst_blk_stride`, `src_blk_stride`: optional block strides
- `dst_rep_stride`, `src_rep_stride`: optional repeat strides

Shared restrictions:

- `dst` and `src` must be UB tensors
- `dst.dtype` must equal `src.dtype`
- these ops consume the current vec mask at dst writeback; masked-off lanes keep the previous `dst` value

### `exp(dst, src, ...)`

- Purpose: Elementwise exponential.
- Parameters: use the shared unary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`
- Example:

```python
exp(dst, src)
```

### `ln(dst, src, ...)`

- Purpose: Elementwise natural logarithm.
- Parameters: use the shared unary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`
- Example:

```python
ln(dst, src)
```

### `abs(dst, src, ...)`

- Purpose: Elementwise absolute value.
- Parameters: use the shared unary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`
- Example:

```python
abs(dst, src)
```

### `rec(dst, src, ...)`

- Purpose: Elementwise reciprocal.
- Parameters: use the shared unary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`
- Example:

```python
rec(dst, src)
```

### `sqrt(dst, src, ...)`

- Purpose: Elementwise square root.
- Parameters: use the shared unary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`
- Example:

```python
sqrt(dst, src)
```

### `rsqrt(dst, src, ...)`

- Purpose: Elementwise reciprocal square root.
- Parameters: use the shared unary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`
- Example:

```python
rsqrt(dst, src)
```

### `vnot(dst, src, ...)`

- Purpose: Elementwise bitwise not.
- Parameters: use the shared unary vec parameter set above.
- Restrictions:
  - supported dtypes: `int16_t`, `uint16_t`
- Example:

```python
vnot(dst, src)
```

### `relu(dst, src, ...)`

- Purpose: Elementwise relu.
- Parameters: use the shared unary vec parameter set above.
- Restrictions:
  - supported dtypes: `float`, `half`
- Example:

```python
relu(dst, src)
```

## 3. Shared Unary-Scalar Vec Parameters

The following functions share this parameter pattern:

- `adds`
- `muls`
- `vmaxs`
- `vmins`
- `lrelu`
- `axpy`

Shared parameters:

- `dst`: destination UB `Tensor`
- `src`: source UB `Tensor`
- `val`: scalar `int`, `float`, or `Var`
- `repeat`: optional repeat count
- stride parameters: optional vec stride metadata

Shared restrictions:

- `dst` and `src` must be UB tensors
- `dst.dtype` must equal `src.dtype`
- scalar type must be compatible with the tensor dtype
- these ops consume the current vec mask at dst writeback; masked-off lanes keep the previous `dst` value

### `adds(dst, src, val, ...)`

- Purpose: Add a scalar to each element.
- Parameters: use the shared unary-scalar parameter set above.
- Restrictions:
  - supported dtypes follow vec unary-scalar support in the current backend
- Example:

```python
adds(dst, src, 1.0)
```

### `muls(dst, src, val, ...)`

- Purpose: Multiply each element by a scalar.
- Parameters: use the shared unary-scalar parameter set above.
- Restrictions:
  - supported dtypes follow vec unary-scalar support in the current backend
- Example:

```python
muls(dst, src, 2.0)
```

### `vmaxs(dst, src, val, ...)`

- Purpose: Clamp each element to at least a scalar threshold.
- Parameters: use the shared unary-scalar parameter set above.
- Restrictions:
  - supported dtypes follow vec unary-scalar support in the current backend
- Example:

```python
vmaxs(dst, src, 0.0)
```

### `vmins(dst, src, val, ...)`

- Purpose: Clamp each element to at most a scalar threshold.
- Parameters: use the shared unary-scalar parameter set above.
- Restrictions:
  - supported dtypes follow vec unary-scalar support in the current backend
- Example:

```python
vmins(dst, src, 1.0)
```

### `lrelu(dst, src, val, ...)`

- Purpose: Apply leaky relu with scalar slope `val`.
- Parameters: use the shared unary-scalar parameter set above.
- Restrictions:
  - supported dtypes follow vec unary-scalar support in the current backend
- Example:

```python
lrelu(dst, src, 0.1)
```

### `axpy(dst, src, val, ...)`

- Purpose: Apply the vec-side AXPY-style scalar fused op supported by the backend.
- Parameters: use the shared unary-scalar parameter set above.
- Restrictions:
  - scalar type must be compatible with tensor dtype
- Example:

```python
axpy(dst, src, 0.5)
```

## 4. Duplication and Broadcast Helpers

### `dup(dst, value, repeat=None, dst_blk_stride=None, dst_rep_stride=None)`

- Purpose: Duplicate a scalar value into a UB tensor.
- Parameters:
  - `dst`: destination UB `Tensor`
  - `value`: `int`, `float`, or `Var`
  - `repeat`: optional repeat count
  - `dst_blk_stride`, `dst_rep_stride`: optional stride metadata
- Restrictions:
  - `dst` must be `Position.UB`
  - supported dtypes: `float`, `half`, `int`, `uint32_t`
  - `dup()` consumes the current vec mask at dst writeback; masked-off lanes keep the previous `dst` value
- Example:

```python
dup(dst, 0.0)
```

### `brcb(dst, src, dst_blk_stride=None, dst_rep_stride=None, repeat=None)`

- Purpose: Apply the vec-side broadcast/repeat helper used by repository kernels.
- Parameters:
  - `dst`: destination UB `Tensor`
  - `src`: source UB `Tensor`
  - `dst_blk_stride`, `dst_rep_stride`, `repeat`: optional control parameters
- Restrictions:
  - `dst` and `src` must both be UB tensors
  - `dst.dtype` must equal `src.dtype`
  - `brcb()` currently ignores the current vec mask state
- Example:

```python
brcb(dst, src)
```

## 5. Group Reduction-Style Operators

The following functions all share this parameter pattern:

- `cmax`
- `cgmax`
- `cmin`
- `cgmin`
- `cadd`
- `cgadd`
- `cpadd`

Shared parameters:

- `dst`: destination UB `Tensor`
- `src`: source UB `Tensor`
- `repeat`: optional repeat count
- `dst_rep_stride`: destination repeat stride, explicit by design
- `src_blk_stride`, `src_rep_stride`: optional source stride metadata

Shared restrictions:

- `dst` and `src` must be UB tensors
- supported dtypes: `float`, `half`
- `dst_rep_stride` cannot be `None`
- the destination stride units differ between `vc`, `vcg`, and `vcp` families; the implementation prints a one-time reminder about those units
- these ops consume the current vec mask state from `set_mask()` / `reset_mask()`

Current simulator mask semantics for this family:

- `cadd`
  - masked-off source slots contribute `0`
  - if all active-prefix mask bits are `0`, the destination scalar is not overwritten
- `cgadd`
  - masked-off source slots contribute `0` inside each datablock
  - if one datablock mask is entirely `0`, that datablock's destination scalar is not overwritten
- `cpadd`
  - masked-off source slots contribute `0` before pairwise add
- `cmax`, `cgmax`
  - masked-off source slots behave like `-inf`
  - if the full active prefix is all-zero for `cmax`, its destination scalar is not overwritten
  - if one datablock mask is all-zero for `cgmax`, that datablock's destination scalar is not overwritten
- `cmin`, `cgmin`
  - masked-off source slots behave like `+inf`
  - if the full active prefix is all-zero for `cmin`, its destination scalar is not overwritten
  - if one datablock mask is all-zero for `cgmin`, that datablock's destination scalar is not overwritten

### `cmax(dst, src, ...)`

- Purpose: Group max reduction in the `vc` family.
- Parameters: use the shared group parameter set above.
- Restrictions:
  - destination stride units follow the `vc` family rule
- Example:

```python
cmax(dst, src, dst_rep_stride=1)
```

### `cgmax(dst, src, ...)`

- Purpose: Group max reduction in the `vcg` family.
- Parameters: use the shared group parameter set above.
- Restrictions:
  - destination stride units follow the `vcg` family rule
- Example:

```python
cgmax(dst, src, dst_rep_stride=1)
```

### `cmin(dst, src, ...)`

- Purpose: Group min reduction in the `vc` family.
- Parameters: use the shared group parameter set above.
- Restrictions:
  - destination stride units follow the `vc` family rule
- Example:

```python
cmin(dst, src, dst_rep_stride=1)
```

### `cgmin(dst, src, ...)`

- Purpose: Group min reduction in the `vcg` family.
- Parameters: use the shared group parameter set above.
- Restrictions:
  - destination stride units follow the `vcg` family rule
- Example:

```python
cgmin(dst, src, dst_rep_stride=1)
```

### `cadd(dst, src, ...)`

- Purpose: Group add reduction in the `vc` family.
- Parameters: use the shared group parameter set above.
- Restrictions:
  - destination stride units follow the `vc` family rule
- Example:

```python
cadd(dst, src, dst_rep_stride=1)
```

### `cgadd(dst, src, ...)`

- Purpose: Group add reduction in the `vcg` family.
- Parameters: use the shared group parameter set above.
- Restrictions:
  - destination stride units follow the `vcg` family rule
- Example:

```python
cgadd(dst, src, dst_rep_stride=1)
```

### `cpadd(dst, src, ...)`

- Purpose: Group packed add reduction in the `vcp` family.
- Parameters: use the shared group parameter set above.
- Restrictions:
  - destination stride units follow the `vcp` family rule
- Example:

```python
cpadd(dst, src, dst_rep_stride=1)
```
