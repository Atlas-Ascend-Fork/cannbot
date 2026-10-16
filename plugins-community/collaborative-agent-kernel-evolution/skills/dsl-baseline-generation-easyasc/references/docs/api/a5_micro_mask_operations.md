# A5 Micro Mask Operations

This page documents the `a5` micro mask helpers other than compare/select.

Covered APIs:

- `mask_not`
- `mask_and`
- `mask_or`
- `mask_xor`
- `mask_mov`
- `mask_sel`
- `mask_interleave`
- `mask_deinterleave`
- `mask_pack`
- `mask_unpack`
- `move_mask_spr`
- `update_mask`

The descriptions below follow:

- the public stubs in `easyasc/stub_functions/micro/mask.py`
- the current V2 simulator behavior in `easyasc/simulator_v2/ops/micro/runtime.py`
- the current V2 micro tests under `testcases/simulator/micro/`

All functions on this page:

- require an active `@vf` context
- operate on `MaskReg`
- use lane-wise boolean masks

## 1. Unary and Binary Mask Ops

These helpers operate on boolean lane masks stored in `MaskReg`.

Important distinction:

- `mask_not`, `mask_and`, `mask_or`, `mask_xor`, and `mask_mov` only update active execution-mask lanes
- masked-off lanes keep the previous contents of `dst`
- `mask_sel` behaves differently and is documented separately below

### `mask_not(dst, src, mask=None)`

- Purpose: invert one mask register into another.
- Parameters:
  - `dst`: destination `MaskReg`
  - `src`: source `MaskReg`
  - `mask`: optional execution mask

Behavior:

```text
dst[i] = not src[i]   if exec_mask[i] is active
dst[i] = old dst[i]   otherwise
```

Example:

```python
mask_not(dst_mask, src_mask)
```

### `mask_and(dst, src1, src2, mask=None)`

- Purpose: logical and of two mask registers.
- Parameters:
  - `dst`: destination `MaskReg`
  - `src1`, `src2`: source `MaskReg`
  - `mask`: optional execution mask

Behavior:

```text
dst[i] = src1[i] and src2[i]   if exec_mask[i] is active
dst[i] = old dst[i]            otherwise
```

Example:

```python
mask_and(dst_mask, m0, m1)
```

### `mask_or(dst, src1, src2, mask=None)`

- Purpose: logical or of two mask registers.
- Behavior on active lanes:
  - `src1[i] or src2[i]`
- Masked-off lanes keep the old destination value.
- Example:

```python
mask_or(dst_mask, m0, m1)
```

### `mask_xor(dst, src1, src2, mask=None)`

- Purpose: logical xor of two mask registers.
- Behavior on active lanes:
  - `src1[i] xor src2[i]`
- Masked-off lanes keep the old destination value.
- Example:

```python
mask_xor(dst_mask, m0, m1)
```

### `mask_mov(dst, src, mask=None)`

- Purpose: copy one mask register into another under an execution mask.
- Behavior:

```text
dst[i] = src[i]       if exec_mask[i] is active
dst[i] = old dst[i]   otherwise
```

- Example:

```python
mask_mov(dst_mask, src_mask)
```

### `mask_sel(dst, src1, src2, mask=None)`

- Purpose: select between two mask registers.
- Parameters:
  - `dst`: destination `MaskReg`
  - `src1`, `src2`: source `MaskReg`
  - `mask`: optional execution mask

Behavior:

- The simulator first copies `src2` into `dst`.
- It then overwrites active execution-mask lanes with `src1`.

Equivalent rule:

```text
dst[i] = src1[i]   if exec_mask[i] is active
dst[i] = src2[i]   otherwise
```

Important alias note:

- Unlike register `select()`, current `mask_sel()` does not snapshot the sources first.
- Avoid aliasing `dst` with `src1` or `src2` if you need strict select semantics.

Example:

```python
mask_sel(dst_mask, left_mask, right_mask, ctrl_mask)
```

Shared restrictions for all ops in this section:

- all participating mask registers must have the same dtype

## 2. Multi-Register Mask Routing

### `mask_interleave(dst0, dst1, src0, src1)`

- Purpose: interleave two source mask registers into two destination mask registers.
- Parameters:
  - `dst0`, `dst1`: destination `MaskReg`
  - `src0`, `src1`: source `MaskReg`

Behavior:

- The simulator snapshots both sources first.
- Let `half = lane_count / 2`.
- For `k in [0, half)`:
  - `dst0[2 * k]     = src0[k]`
  - `dst0[2 * k + 1] = src1[k]`
  - `dst1[2 * k]     = src0[half + k]`
  - `dst1[2 * k + 1] = src1[half + k]`

Example with 8 lanes:

```text
src0 = [a0, a1, a2, a3, a4, a5, a6, a7]
src1 = [b0, b1, b2, b3, b4, b5, b6, b7]

dst0 = [a0, b0, a1, b1, a2, b2, a3, b3]
dst1 = [a4, b4, a5, b5, a6, b6, a7, b7]
```

Restrictions:

- all four masks must have the same dtype
- the lane count must be even

### `mask_deinterleave(dst0, dst1, src0, src1)`

- Purpose: reverse the `mask_interleave()` layout.
- Parameters:
  - `dst0`, `dst1`: destination `MaskReg`
  - `src0`, `src1`: source `MaskReg`

Behavior:

- The simulator snapshots both sources first.
- Let `half = lane_count / 2`.
- For `k in [0, half)`:
  - `dst0[k]        = src0[2 * k]`
  - `dst1[k]        = src0[2 * k + 1]`
  - `dst0[half + k] = src1[2 * k]`
  - `dst1[half + k] = src1[2 * k + 1]`

Example:

```python
mask_deinterleave(out0, out1, in0, in1)
```

Restrictions:

- all four masks must have the same dtype
- the lane count must be even

## 3. Pack, Unpack, and Control

### `mask_pack(dst, src, low_part=True)`

- Purpose: pack the even lanes of a source mask into either the low half or high half of the destination mask.
- Parameters:
  - `dst`: destination `MaskReg`
  - `src`: source `MaskReg`
  - `low_part`: choose low half when `True`, high half when `False`

Behavior:

- The simulator snapshots `src` first.
- Let `half = lane_count / 2`.
- It extracts `src[0], src[2], src[4], ...`.
- If `low_part=True`, those values are written to `dst[0:half]`.
- If `low_part=False`, those values are written to `dst[half:lane_count]`.
- All other destination lanes become `False`.

Example with 8 lanes:

```text
src = [a0, a1, a2, a3, a4, a5, a6, a7]

mask_pack(..., low_part=True)  -> [a0, a2, a4, a6, 0,  0,  0,  0]
mask_pack(..., low_part=False) -> [0,  0,  0,  0,  a0, a2, a4, a6]
```

Restrictions:

- `dst.dtype` must equal `src.dtype`
- the lane count must be even

### `mask_unpack(dst, src, low_part=True)`

- Purpose: expand a packed mask back into the even lanes of the destination.
- Parameters:
  - `dst`: destination `MaskReg`
  - `src`: source `MaskReg`
  - `low_part`: read the low packed half when `True`, the high packed half when `False`

Behavior:

- Let `half = lane_count / 2`.
- If `low_part=True`, the simulator reads `src[0:half]`.
- If `low_part=False`, it reads `src[half:lane_count]`.
- Those values are written to `dst[0], dst[2], dst[4], ...`.
- All odd destination lanes become `False`.

Example with 8 lanes:

```text
src = [p0, p1, p2, p3, q0, q1, q2, q3]

mask_unpack(..., low_part=True)  -> [p0, 0, p1, 0, p2, 0, p3, 0]
mask_unpack(..., low_part=False) -> [q0, 0, q1, 0, q2, 0, q3, 0]
```

Restrictions:

- `dst.dtype` must equal `src.dtype`
- the lane count must be even

### `move_mask_spr(dst)`

- Purpose: move mask state from the SPR path into a mask register.
- Parameters:
  - `dst`: destination `MaskReg`

Current simulator status:

- `move_mask_spr()` is not implemented in the simulator.
- The simulator raises `NotImplementedError`.

Example:

```python
move_mask_spr(mask_reg)
```

### `update_mask(dst, cnt)`

- Purpose: build a prefix mask from a scalar lane count and update that counter for the next chunk.
- Parameters:
  - `dst`: destination `MaskReg`
  - `cnt`: `Var` with dtype `DT.uint32`

Behavior:

- Let `lane_count` be the number of lanes of `dst.dtype`.
- The simulator computes:
  - `active_count = clamp(cnt, 0, lane_count)`
- It then writes:
  - `dst[0:active_count] = True`
  - `dst[active_count:] = False`
- After that, it updates `cnt` in-place:
  - `cnt = max(cnt - lane_count, 0)`

This makes repeated calls consume a long logical count one register-width chunk at a time.

Example with `half`:

```text
lane_count = 128
initial cnt = 300

call 1:
  dst = first 128 lanes active
  cnt becomes 172

call 2:
  dst = first 128 lanes active
  cnt becomes 44

call 3:
  dst = first 44 lanes active
  cnt becomes 0
```

Example use:

```python
update_mask(mask_reg, lane_count_var)
```

Restrictions:

- `dst` must be `MaskReg`
- `cnt` must be a `Var`
- `cnt.dtype` must be `DT.uint32`
