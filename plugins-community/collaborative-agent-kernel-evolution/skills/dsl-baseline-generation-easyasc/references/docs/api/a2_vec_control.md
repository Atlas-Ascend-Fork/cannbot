# A2 Vec Control and Access Helpers

This page documents the non-math vector helpers exported by `easyasc.a2`.

Scope of this page:

- UB vector cast
- UB compare and select helpers
- vec mask state helpers
- UB gather and scatter helpers

All functions on this page are part of the `a2` surface only.

Notes:

- every tensor on this page is expected to live in `UB`
- several names such as `compare`, `select`, and `gather` also exist in `easyasc.a5`, but those are micro-register APIs and are documented separately

## 1. Vec Cast

### `cast(dst, src, repeat=None, dst_blk_stride=None, src_blk_stride=None, dst_rep_stride=None, src_rep_stride=None, round_mode=RoundMode.AWAY_FROM_ZERO)`

- Purpose: Perform UB vector cast between dtypes.
- Parameters:
  - `dst`: destination UB `Tensor`
  - `src`: source UB `Tensor`
  - `repeat`: optional repeat count
  - `dst_blk_stride`, `src_blk_stride`: block strides
  - `dst_rep_stride`, `src_rep_stride`: repeat strides
  - `round_mode`: vec cast rounding mode
- Restrictions:
  - exported by `a2`
  - `dst` and `src` must both be UB tensors
  - `round_mode` must be `RoundModeType`
  - when widening, the runtime forces `RoundMode.NONE`
- Current simulator notes:
  - cast ignores `dst_blk_stride` / `src_blk_stride`; only repeat strides matter
  - the cast-element count per repeat is determined by the wider of `src` / `dst` dtypes
  - the current vec mask is resolved on that cast-element domain
  - masked-off cast elements keep the previous `dst` value
- Example:

```python
cast(dst_half, src_float)
```

## 2. Vec Compare and Select

### `SelectModeType` and `SelectMode`

The vec `select(...)` stub infers one of two select modes internally.
Those mode objects are defined in `easyasc/utils/selectmode.py`.

In normal kernel code you do not pass `mode=` yourself.
The public `select(...)` API derives it from the runtime type of `src2` and records it on the emitted instruction.

### `SelectModeType`

- Purpose: represent one concrete vec select lowering mode.
- Stored field:
  - `name`
- Important behavior:
  - `str(mode)` returns names such as `TENSOR_TENSOR`
  - `repr(mode)` returns a debug-style form such as `SelectModeType('TENSOR_SCALAR')`
  - equality compares mode names

One implementation detail is worth knowing when debugging helper code:

- comparing a `SelectModeType` against an object of another type raises `TypeError`
- it does not silently return `False`

### `SelectMode`

`SelectMode` is the enum-like namespace that exports the two vec-side select forms:

- `SelectMode.TENSOR_TENSOR`
  - selected values come from two UB tensors, `src1` and `src2`
- `SelectMode.TENSOR_SCALAR`
  - the true branch comes from `src1`, while the false branch uses one scalar value broadcast across lanes

The current stub in `easyasc/stub_functions/vec/select.py` chooses the mode with a simple rule:

- if `src2` is a UB `Tensor`, mode is `SelectMode.TENSOR_TENSOR`
- otherwise `src2` must be a scalar-like value and mode is `SelectMode.TENSOR_SCALAR`

That means these two calls lower differently:

```python
select(dst, selmask, src1, src2_tensor)
select(dst, selmask, src1, 0.0)
```

Even when every other stride argument is the same, the emitted instruction carries a different `mode`, and the backend/simulator interprets `src2` accordingly.

### Why this type belongs on the A2 vec page

`SelectMode` is used by the A2 vec `select(...)` stub, not by the A5 micro `select(...)` instruction.
Keeping it here avoids mixing two unrelated APIs that merely share the word "select".

### `compare(dst, src1, src2, mode, repeat=None, ...)`

- Purpose: Compare two UB tensors and write the boolean result into a UB mask tensor.
- Parameters:
  - `dst`: destination UB `Tensor` holding the compare result
  - `src1`, `src2`: source UB tensors
  - `mode`: `CompareMode`
  - remaining parameters: repeat and stride metadata
- Restrictions:
  - exported by `a2`
  - `dst` must be UB `int8` or `uint8`
  - `src1` and `src2` must be UB tensors of matching dtype
  - supported source dtypes: `float`, `half`, `int16`, `int`
  - `compare()` currently ignores the current vec mask state
- Example:

```python
compare(mask_buf, xub, yub, CompareMode.GT)
```

### `compare_scalar(dst, src1, src2, mode, repeat=None, ...)`

- Purpose: Compare a UB tensor against a scalar and write the result into a UB mask tensor.
- Parameters:
  - `dst`: destination UB `Tensor` holding the compare result
  - `src1`: source UB tensor
  - `src2`: scalar `int`, `float`, or `Var`
  - `mode`: `CompareMode`
  - remaining parameters: repeat and stride metadata
- Restrictions:
  - exported by `a2`
  - `dst` must be UB `int8` or `uint8`
  - `src1` must be UB `float`, `half`, `int16`, or `int`
  - `compare_scalar()` currently ignores the current vec mask state
- Example:

```python
compare_scalar(mask_buf, xub, 0.0, CompareMode.GE)
```

### `set_cmpmask(src)`

- Purpose: Load compare-mask state from a UB tensor.
- Parameters:
  - `src`: source UB `Tensor`
- Restrictions:
  - exported by `a2`
  - `src` must be `Position.UB`
- Example:

```python
set_cmpmask(mask_buf)
```

### `select(dst, selmask, src1, src2, repeat=None, ...)`

- Purpose: Select between tensor/scalar inputs using a tensor or scalar selection mask.
- Parameters:
  - `dst`: destination UB `Tensor`
  - `selmask`: mask `Tensor` or scalar `Var`
  - `src1`: first source UB `Tensor`
  - `src2`: second source, either a UB tensor or a scalar
  - remaining parameters: repeat and stride metadata
- Restrictions:
  - exported by `a2`
  - `dst` and `src1` must be UB tensors
  - supported data dtypes: `float`, `half`, `int16`, `int`
  - tensor `selmask` must be `uint8`
  - scalar `selmask` must be one of the unsigned integer scalar dtypes supported by the runtime
  - `select()` currently ignores the current vec mask state; selection is controlled only by `selmask`
- Lowering modes:
  - if `src2` is a UB `Tensor`, the stub emits `mode=SelectMode.TENSOR_TENSOR`
  - if `src2` is a scalar `Var`, `int`, or `float`, the stub emits `mode=SelectMode.TENSOR_SCALAR`
- Example:

```python
select(dst, mask_var, src1, 0.0)
```

## 3. Vec Mask State

### `set_mask(mask_high, mask_low)`

- Purpose: Set the current vec mask registers.
- Parameters:
  - `mask_high`, `mask_low`: `int` or `Var`
- Restrictions:
  - exported by `a2`
  - if a `Var` is used, its dtype must be `uint64`
- Current simulator notes:
  - `mask_low` controls bits `0..63`
  - `mask_high` controls bits `64..127`
  - `mask[128:256]` is not modified by `set_mask()`
  - typical active prefixes are:
    - `float` / `int32`: `mask[0:64]`
    - `half` / `int16`: `mask[0:128]`
    - `int8` / `uint8`: `mask[0:256]`
  - the same mask prefix is reused for every repeat; it does not advance automatically per repeat
- Example:

```python
set_mask(0, 0xFFFFFFFFFFFFFFFF)
```

### `reset_mask()`

- Purpose: Reset the vec mask state to the default state.
- Parameters:
  - none
- Restrictions:
  - exported by `a2`
  - use after temporary partial-mask regions to avoid surprising later ops
- Current simulator note:
  - resets the full `mask[0:256]` back to all ones
- Example:

```python
reset_mask()
```

## 4. Gather and Scatter

### `gather(dst, src, offset, start_idx=0, repeat=None, dst_rep_stride=None)`

- Purpose: Gather elements from a UB source tensor using a UB offset tensor.
- Parameters:
  - `dst`: destination UB `Tensor`
  - `src`: source UB `Tensor`
  - `offset`: UB `Tensor` of byte offsets
  - `start_idx`: base byte offset
  - `repeat`: optional repeat count
  - `dst_rep_stride`: destination repeat stride
- Restrictions:
  - exported by `a2`
  - `offset` must be UB `uint32`
  - `dst.dtype` must equal `src.dtype`
  - offsets and `start_idx` are in bytes
  - `gather()` currently ignores the current vec mask state
- Example:

```python
gather(dst, src, offset)
```

### `scatter(dst, src, offset, repeat=None, src_rep_stride=None)`

- Purpose: Scatter elements from a UB source tensor into a UB destination tensor using offsets.
- Parameters:
  - `dst`: destination UB `Tensor`
  - `src`: source UB `Tensor`
  - `offset`: UB `Tensor` of byte offsets
  - `repeat`: optional repeat count
  - `src_rep_stride`: source repeat stride
- Restrictions:
  - exported by `a2`
  - `offset` must be UB `uint32`
  - `dst.dtype` must equal `src.dtype`
  - `scatter()` currently ignores the current vec mask state
- Example:

```python
scatter(dst, src, offset)
```
