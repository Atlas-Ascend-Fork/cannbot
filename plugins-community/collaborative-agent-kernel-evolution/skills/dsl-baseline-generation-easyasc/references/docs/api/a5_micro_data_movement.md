# A5 Micro Data Movement

This page documents the micro-side data movement helpers exported directly by `easyasc.a5`.

The descriptions below follow both the public stub APIs in `easyasc/stub_functions/micro/datamove.py`
and the current V2 simulator behavior in `easyasc/simulator_v2/ops/micro/runtime.py`.

All functions on this page:

- require an active `@vf` context
- operate on `Reg`, `MaskReg`, and UB `Tensor`
- treat UB tensors as flattened 1D views when they compute addresses

## 1. Register Geometry Used by These APIs

Many of the behaviors below depend on the micro register lane count and on the hardware `C0` block size.

- `lane_count = 256 / dtype_size_in_bytes`
- `c0 = 32 / dtype_size_in_bytes`

Common cases:

| dtype | element size | lane count | `C0` size |
| --- | --- | --- | --- |
| `int8` / `uint8` | 1 byte | 256 lanes | 32 lanes |
| `half` / `bfloat16` | 2 bytes | 128 lanes | 16 lanes |
| `float` / `int32` | 4 bytes | 64 lanes | 8 lanes |

This matters because:

- `ub_to_reg()` and `reg_to_ub()` interpret `blk_stride` in units of `C0` blocks
- these block-copy APIs expand masks to whole `C0` blocks
- `LoadDist.BRCB` repeats one scalar per `C0` block

## 2. Distribution Mode Objects

### `LoadDist`

- Purpose: Selects the behavior of `ub_to_reg_continuous()`.
- Parameter meaning:
  - `loaddist`: chooses how a flattened UB source stream is expanded or rearranged into one register.

Available values:

| API value | Simulator mode | Supported element sizes | Behavior |
| --- | --- | --- | --- |
| `LoadDist.DOWNSAMPLE` | `DIST_DS_B8`, `DIST_DS_B16` | 8-bit, 16-bit | Read every other source element. |
| `LoadDist.UPSAMPLE` | `DIST_US_B8`, `DIST_US_B16` | 8-bit, 16-bit | Repeat each source element twice. |
| `LoadDist.SINGLE_VALUE` | `DIST_BRC_B8`, `DIST_BRC_B16`, `DIST_BRC_B32` | 8-bit, 16-bit, 32-bit | Broadcast `src[0]` to every register lane. |
| `LoadDist.BRCB` | `DIST_E2B_B16`, `DIST_E2B_B32` | 16-bit, 32-bit | Broadcast one source element to one whole `C0` block. |
| `LoadDist.UNPACK` | `DIST_UNPACK_B8`, `DIST_UNPACK_B16`, `DIST_UNPACK_B32` | 8-bit, 16-bit, 32-bit | Write source values into even lanes, zero-fill odd lanes. |
| `LoadDist.UNPACK4` | `DIST_UNPACK4_B8` | 8-bit only | Write source values into lanes `0, 4, 8, ...`, zero-fill the rest. |

Behavior details:

- `DOWNSAMPLE`:
  - required source length: `lane_count * 2`
  - formula: `dst[i] = src[2 * i]`
- `UPSAMPLE`:
  - required source length: `lane_count / 2`
  - requires even `lane_count`
  - formula: `dst[2 * i] = src[i]`, `dst[2 * i + 1] = src[i]`
- `SINGLE_VALUE`:
  - required source length: `1`
  - formula: `dst[i] = src[0]`
- `BRCB`:
  - required source length: `lane_count / c0`
  - requires `lane_count % c0 == 0`
  - formula: for block `b`, `dst[b * c0 : (b + 1) * c0] = src[b]`
- `UNPACK`:
  - required source length: `lane_count / 2`
  - requires even `lane_count`
  - formula: `dst[2 * i] = src[i]`, `dst[2 * i + 1] = 0`
- `UNPACK4`:
  - required source length: `lane_count / 4`
  - requires `lane_count % 4 == 0`
  - formula: `dst[4 * i] = src[i]`, all other lanes are `0`

Simple examples:

```text
LoadDist.DOWNSAMPLE
src = [10, 11, 12, 13, 14, 15, 16, 17, ...]
dst = [10, 12, 14, 16, ...]
```

```text
LoadDist.UPSAMPLE
src = [5, 6, 7, 8]
dst = [5, 5, 6, 6, 7, 7, 8, 8]
```

```text
LoadDist.BRCB with half
lane_count = 128, c0 = 16
src = [1, 2, 3, 4, 5, 6, 7, 8]
dst[0:16]   = 1
dst[16:32]  = 2
dst[32:48]  = 3
...
dst[112:128] = 8
```

Example use:

```python
reg = Reg(DT.half)
src = Tensor(DT.half, [1, 8], Position.UB)
ub_to_reg_continuous(reg, src, LoadDist.BRCB)
```

### `LoadDistValue`

- Purpose: concrete value type behind the exported `LoadDist.*` members.
- Practical use:
  - you normally do not construct it directly
  - instead, pass predefined values such as `LoadDist.DOWNSAMPLE`, `LoadDist.BRCB`, `LoadDist.UNPACK`, or `LoadDist.SINGLE_VALUE`

Why it exists:

- the public API exposes readable names under the `LoadDist` namespace
- the underlying stub layer and simulator receive the concrete `LoadDistValue` carried by that name

Practical rule:

- use `LoadDist.*` in kernel code
- treat `LoadDistValue` as the implementation-level value type that shows up in low-level docs, type checks, and debug output

Example:

```python
mode = LoadDist.SINGLE_VALUE
ub_to_reg_continuous(dst_reg, src_ub, mode)
```

### `StoreDist`

- Purpose: Selects the behavior of `reg_to_ub_continuous()`.
- Parameter meaning:
  - `storedist`: chooses how register lanes are compacted or written into the flattened UB destination.

Available values:

| API value | Simulator mode | Supported element sizes | Behavior |
| --- | --- | --- | --- |
| `StoreDist.DOWNSAMPLE` | `DIST_PACK_B16`, `DIST_PACK_B32`, `DIST_PACK_B64` | 8-bit, 16-bit, 32-bit | Store every other source lane into a compact destination. |
| `StoreDist.PACK4` | `DIST_PACK4_B32` | 8-bit only | Store every fourth source lane into a compact destination. |
| `StoreDist.SINGLE_VALUE` | `DIST_FIRST_ELEMENT_B8`, `DIST_FIRST_ELEMENT_B16`, `DIST_FIRST_ELEMENT_B32` | 8-bit, 16-bit, 32-bit | Store only lane `0`. |
| `StoreDist.NORMAL` | `DIST_NORM_B8`, `DIST_NORM_B16`, `DIST_NORM_B32` | 8-bit, 16-bit, 32-bit | Store lanes `1:1`. |

Behavior details:

- `DOWNSAMPLE`:
  - destination length must be at least `lane_count / 2`
  - requires even `lane_count`
  - formula: `dst[i] = src[2 * i]`
- `PACK4`:
  - destination length must be at least `lane_count / 4`
  - requires `lane_count % 4 == 0`
  - formula: `dst[i] = src[4 * i]`
- `SINGLE_VALUE`:
  - destination length must be at least `1`
  - formula: `dst[0] = src[0]`
- `NORMAL`:
  - destination length must be at least `lane_count`
  - formula: `dst[i] = src[i]`

Mask behavior for continuous stores:

- `reg_to_ub_continuous()` resolves the source mask first.
- The mask is then expanded to whole `C0` blocks.
- The selected mode samples lanes from that expanded mask.
- Destination positions that are not selected keep their previous values.

Example:

```text
StoreDist.DOWNSAMPLE
src = [10, 11, 12, 13, 14, 15, 16, 17]
dst = [10, 12, 14, 16]
```

```text
StoreDist.PACK4
src = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
dst = [0, 4, 8]
```

Example use:

```python
reg = Reg(DT.int8)
dst = Tensor(DT.int8, [1, 64], Position.UB)
reg_to_ub_continuous(dst, reg, None, StoreDist.PACK4)
```

### `StoreDistValue`

- Purpose: concrete value type behind the exported `StoreDist.*` members.
- Practical use:
  - you normally do not construct it directly
  - instead, pass predefined values such as `StoreDist.NORMAL`, `StoreDist.DOWNSAMPLE`, `StoreDist.PACK4`, or `StoreDist.SINGLE_VALUE`

Why it exists:

- the public API uses readable mode names under `StoreDist`
- the underlying stub and simulator paths receive the corresponding `StoreDistValue`

Practical rule:

- use `StoreDist.*` in kernel code
- treat `StoreDistValue` as the implementation-level value type underneath those exported names

Example:

```python
mode = StoreDist.NORMAL
reg_to_ub_continuous(dst_ub, src_reg, None, mode)
```

## 3. Basic UB/Register Transfer

### `ub_to_reg(dst, src, blk_stride=1, mask=None)`

- Purpose: Load a UB tensor into one register.
- Parameters:
  - `dst`: destination `Reg`
  - `src`: source UB `Tensor`
  - `blk_stride`: distance between copied `C0` blocks in the flattened source
  - `mask`: optional `MaskReg`

How addressing works:

- When `blk_stride == 1` and the mask is full, the simulator uses a fast contiguous copy:
  - `dst[i] = src_flat[i]`
- Otherwise, addressing is computed in `C0`-sized blocks:
  - `src_index(i) = (i // c0) * (blk_stride * c0) + (i % c0)`

Interpretation of `blk_stride`:

- `blk_stride = 1`: copy adjacent `C0` blocks
- `blk_stride = 2`: copy one `C0` block, skip one `C0` block, copy the next
- `blk_stride = 3`: copy one `C0` block, skip two `C0` blocks, and so on

Mask behavior:

- For `ub_to_reg()`, the mask is expanded to full `C0` blocks.
- If any lane inside a `C0` block is enabled, the whole block is copied.
- Lanes not copied by the mask are zeroed in `dst`.

Example: `blk_stride` with `half`

```text
dtype = half
lane_count = 128
c0 = 16
blk_stride = 2

dst lanes   0..15  <- src lanes   0..15
dst lanes  16..31  <- src lanes  32..47
dst lanes  32..47  <- src lanes  64..79
dst lanes  48..63  <- src lanes  96..111
...
```

Equivalent formula:

```text
src_index(i) = (i // 16) * 32 + (i % 16)
```

Example: `MaskType.LOWEST1` with `half`

```text
lane_count = 128, c0 = 16
LOWEST1 initially enables only lane 0
after C0 expansion, lanes 0..15 become active

result:
dst[0:16]   = src[0:16]
dst[16:128] = 0
```

Example use:

```python
reg = Reg(DT.half)
src = Tensor(DT.half, [1, 256], Position.UB)
mask = MaskReg(DT.half, init_mode=MaskType.ALL)
ub_to_reg(reg, src, blk_stride=2, mask=mask)
```

Restrictions:

- `src.position` must be `Position.UB`
- `dst.dtype` must equal `src.dtype`
- `blk_stride` must be positive
- the flattened source view must be large enough for the highest computed address

### `reg_to_ub(dst, src, blk_stride=1, mask=None)`

- Purpose: Store one register into a UB tensor.
- Parameters:
  - `dst`: destination UB `Tensor`
  - `src`: source `Reg`
  - `blk_stride`: distance between written `C0` blocks in the flattened destination
  - `mask`: optional `MaskReg`

How addressing works:

- When `blk_stride == 1` and the mask is full, the simulator uses a fast contiguous store:
  - `dst_flat[i] = src[i]`
- Otherwise, addressing is computed with the same `C0` block rule as `ub_to_reg()`:
  - `dst_index(i) = (i // c0) * (blk_stride * c0) + (i % c0)`

Mask behavior:

- The mask is expanded to whole `C0` blocks.
- Only active lanes are written.
- Destination locations that are not written keep their previous values.

Example: `blk_stride` with `half`

```text
dtype = half
lane_count = 128
c0 = 16
blk_stride = 2

dst lanes   0..15   <- src lanes   0..15
dst lanes  32..47   <- src lanes  16..31
dst lanes  64..79   <- src lanes  32..47
dst lanes  96..111  <- src lanes  48..63
...
```

Equivalent formula:

```text
dst_index(i) = (i // 16) * 32 + (i % 16)
```

Example use:

```python
reg = Reg(DT.half)
dst = Tensor(DT.half, [1, 256], Position.UB)
reg_to_ub(dst, reg, blk_stride=2)
```

Restrictions:

- `dst.position` must be `Position.UB`
- `dst.dtype` must equal `src.dtype`
- `blk_stride` must be positive
- the flattened destination view must be large enough for the highest computed address

### `ub_to_reg_continuous(dst, src, loaddist)`

- Purpose: Load a flattened UB stream into a register using one of the predefined distribution patterns.
- Parameters:
  - `dst`: destination `Reg`
  - `src`: source UB `Tensor`
  - `loaddist`: a `LoadDist` value

Behavior summary:

- this API does not take a mask
- it always starts from `src_flat[0]`
- the selected `LoadDist` defines how many source elements are consumed and how they are mapped into the lanes of `dst`

Examples:

```python
ub_to_reg_continuous(reg, src, LoadDist.DOWNSAMPLE)
ub_to_reg_continuous(reg, src, LoadDist.UNPACK)
ub_to_reg_continuous(reg, src, LoadDist.BRCB)
```

Restrictions:

- `dst.dtype` must equal `src.dtype`
- the chosen mode must support the dtype width
- the flattened source must provide the number of elements required by the selected mode

### `reg_to_ub_continuous(dst, src, mask, storedist)`

- Purpose: Store a register into a flattened UB stream using one of the predefined compact-store patterns.
- Parameters:
  - `dst`: destination UB `Tensor`
  - `src`: source `Reg`
  - `mask`: optional `MaskReg`
  - `storedist`: a `StoreDist` value

Behavior summary:

- the selected `StoreDist` first defines which source lanes participate
- the source mask is applied to those participating lanes
- written destination positions are compacted starting from `dst_flat[0]`
- destination positions not selected by the mode/mask keep their existing values

Detailed example: `StoreDist.DOWNSAMPLE` with a partial mask

```text
src = [10, 11, 12, 13, 14, 15, 16, 17]
mode samples lanes [0, 2, 4, 6]

if the active sampled lanes are [0, 4, 6]
then dst receives:
dst[0] = 10
dst[1] = 14
dst[2] = 16

the next compact destination position is not written at all
```

Examples:

```python
reg_to_ub_continuous(dst, reg, None, StoreDist.NORMAL)
reg_to_ub_continuous(dst, reg, mask, StoreDist.DOWNSAMPLE)
```

Restrictions:

- `dst.dtype` must equal `src.dtype`
- the chosen mode must support the dtype width
- the flattened destination must be large enough for the highest compacted destination index

## 4. Convenience Transfer Wrappers

These wrappers only choose a `LoadDist` or `StoreDist` value for you.

| Wrapper | Equivalent call |
| --- | --- |
| `reg_to_ub_downsample(dst, src, mask)` | `reg_to_ub_continuous(dst, src, mask, StoreDist.DOWNSAMPLE)` |
| `reg_to_ub_pack4(dst, src, mask)` | `reg_to_ub_continuous(dst, src, mask, StoreDist.PACK4)` |
| `reg_to_ub_single(dst, src, mask)` | `reg_to_ub_continuous(dst, src, mask, StoreDist.SINGLE_VALUE)` |
| `ub_to_reg_single(dst, src)` | `ub_to_reg_continuous(dst, src, LoadDist.SINGLE_VALUE)` |
| `ub_to_reg_upsample(dst, src)` | `ub_to_reg_continuous(dst, src, LoadDist.UPSAMPLE)` |
| `ub_to_reg_downsample(dst, src)` | `ub_to_reg_continuous(dst, src, LoadDist.DOWNSAMPLE)` |
| `ub_to_reg_unpack(dst, src)` | `ub_to_reg_continuous(dst, src, LoadDist.UNPACK)` |
| `ub_to_reg_unpack4(dst, src)` | `ub_to_reg_continuous(dst, src, LoadDist.UNPACK4)` |
| `ub_to_reg_brcb(dst, src)` | `ub_to_reg_continuous(dst, src, LoadDist.BRCB)` |

Example:

```python
ub_to_reg_unpack(reg, src_ub)
reg_to_ub_single(dst_ub, reg)
```

## 5. Gather and Scatter

### `ub_to_reg_gather(dst, src, index, mask=None)`

- Purpose: Gather arbitrary UB elements into a register.
- Parameters:
  - `dst`: destination `Reg`
  - `src`: source UB `Tensor`
  - `index`: index `Reg`
  - `mask`: optional `MaskReg`

Addressing rule:

- The simulator flattens `src` first.
- For each active lane `i`, it reads:
  - `dst[i] = src_flat[index[i]]`

Mask behavior:

- The mask is lane-wise here. It is not expanded to `C0` blocks.
- Inactive lanes in `dst` are zero because the destination register is zero-initialized first.

Index behavior:

- `index` participates directly in address calculation.
- `index[i]` is already the final flattened element index.
- There is no extra multiply by element size, row width, or `C0`.

If `src` logically has shape `[rows, cols]`, then:

- flattened address `0 .. cols - 1` refers to row `0`
- flattened address `cols .. 2 * cols - 1` refers to row `1`
- in general: `flat_index = row * cols + col`

Example:

```text
src (flattened) = [100, 101, 102, 103, 104, 105]
index           = [4,   1,   1,   0]
mask            = VL3

dst[0] = src[4] = 104
dst[1] = src[1] = 101
dst[2] = src[1] = 101
dst[3] = 0      # masked off
```

Example use:

```python
data = Tensor(DT.half, [4, 64], Position.UB)
index = Reg(DT.uint16)
dst = Reg(DT.half)
mask = MaskReg(DT.half, init_mode=MaskType.ALL)
ub_to_reg_gather(dst, data, index, mask=mask)
```

Restrictions:

- `dst.dtype` must equal `src.dtype`
- `index` lane count must equal `dst` lane count
- the simulator requires `index` to be integer-typed
- the stub additionally enforces:
  - `uint16` index for 16-bit data
  - `uint32` index for 32-bit data
- every active index must be within the flattened source range

### `reg_to_ub_scatter(dst, src, index, mask=None)`

- Purpose: Scatter register lanes into arbitrary UB elements.
- Parameters:
  - `dst`: destination UB `Tensor`
  - `src`: source `Reg`
  - `index`: index `Reg`
  - `mask`: optional `MaskReg`

Addressing rule:

- The simulator flattens `dst` first.
- For each active lane `i`, it writes:
  - `dst_flat[index[i]] = src[i]`

Mask behavior:

- The mask is lane-wise here. It is not expanded to `C0` blocks.
- Inactive lanes do not write anything.
- Existing destination values remain unchanged at untouched positions.

Duplicate-index behavior:

- If multiple active lanes target the same destination index, writes occur in lane order.
- The last active lane wins.

Example:

```text
initial dst = [0, 0, 0, 0, 0]
src         = [10, 20, 30, 40]
index       = [3,  1,  3,  0]

lane 0 writes dst[3] = 10
lane 1 writes dst[1] = 20
lane 2 writes dst[3] = 30   # overwrites lane 0
lane 3 writes dst[0] = 40

final dst = [40, 20, 0, 30, 0]
```

Example use:

```python
dst = Tensor(DT.half, [4, 64], Position.UB)
src = Reg(DT.half)
index = Reg(DT.uint16)
reg_to_ub_scatter(dst, src, index)
```

Restrictions:

- `dst.dtype` must equal `src.dtype`
- `index` lane count must equal `src` lane count
- the simulator requires `index` to be integer-typed
- the stub additionally enforces:
  - `uint16` index for 16-bit data
  - `uint32` index for 32-bit data
- every active index must be within the flattened destination range

### `gather(dst, src, index)`

- Purpose: Gather from one register into another register.
- Parameters:
  - `dst`: destination `Reg`
  - `src`: source `Reg`
  - `index`: index `Reg`

Rule:

- For every lane `i`:
  - `dst[i] = src[index[i]]`

Important alias behavior:

- The simulator snapshots `src` before gathering.
- This means `gather(reg, reg, index)` behaves like a true gather from the original register, not an in-place progressive overwrite.

Example:

```text
src   = [10, 20, 30, 40]
index = [3, 2, 1, 0]
dst   = [40, 30, 20, 10]
```

Example with duplicate indices:

```text
src   = [10, 20, 30, 40]
index = [1, 1, 1, 1]
dst   = [20, 20, 20, 20]
```

Example use:

```python
dst = Reg(DT.half)
src = Reg(DT.half)
index = Reg(DT.uint16)
gather(dst, src, index)
```

Restrictions:

- `dst.dtype` must equal `src.dtype`
- `dst`, `src`, and `index` must all have the same lane count
- every index must be within the source register lane range

### `gather_mask(dst, src, mask=None)`

- Purpose: Compact masked source lanes to the front of the destination register.
- Parameters:
  - `dst`: destination `Reg`
  - `src`: source `Reg`
  - `mask`: optional `MaskReg`

Rule:

- Selected source lanes are copied in their original order.
- They are packed into `dst[0], dst[1], ...`.
- Remaining lanes in `dst` are zero-filled.

Example:

```text
src  = [10, 20, 30, 40, 50, 60]
mask = active at lanes [0, 2, 5]
dst  = [10, 30, 60, 0, 0, 0]
```

Important alias behavior:

- The simulator snapshots `src` before compaction.
- `gather_mask(src, src, mask)` therefore uses the original source contents.

Example use:

```python
dst = Reg(DT.half)
src = Reg(DT.half)
mask = MaskReg(DT.half, init_mode=MaskType.MULTI3)
gather_mask(dst, src, mask)
```

Restrictions:

- `dst.dtype` must equal `src.dtype`
- `dst` and `src` must have the same lane count

## 6. Interleave Helpers

### `interleave(dst0, dst1, src0, src1)`

- Purpose: Interleave two source registers into two destination registers.
- Parameters:
  - `dst0`, `dst1`: destination `Reg`
  - `src0`, `src1`: source `Reg`

Rule:

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

Alias behavior:

- The simulator snapshots both sources first.
- `interleave(reg0, reg1, reg0, reg1)` is therefore well-defined.

Example use:

```python
out0 = Reg(DT.half)
out1 = Reg(DT.half)
interleave(out0, out1, reg0, reg1)
```

Restrictions:

- all four registers must have the same dtype
- all four registers must have the same lane count
- the lane count must be even

### `deinterleave(dst0, dst1, src0, src1)`

- Purpose: Reverse the `interleave()` layout.
- Parameters:
  - `dst0`, `dst1`: destination `Reg`
  - `src0`, `src1`: source `Reg`

Rule:

- Let `half = lane_count / 2`.
- For `k in [0, half)`:
  - `dst0[k]        = src0[2 * k]`
  - `dst1[k]        = src0[2 * k + 1]`
  - `dst0[half + k] = src1[2 * k]`
  - `dst1[half + k] = src1[2 * k + 1]`

Example with 8 lanes:

```text
src0 = [a0, b0, a1, b1, a2, b2, a3, b3]
src1 = [a4, b4, a5, b5, a6, b6, a7, b7]

dst0 = [a0, a1, a2, a3, a4, a5, a6, a7]
dst1 = [b0, b1, b2, b3, b4, b5, b6, b7]
```

Round-trip property:

```text
deinterleave(*, *, *interleave(src0, src1)) == (src0, src1)
```

Alias behavior:

- Like `interleave()`, the simulator snapshots the sources first.

Example use:

```python
out0 = Reg(DT.half)
out1 = Reg(DT.half)
deinterleave(out0, out1, tmp0, tmp1)
```

Restrictions:

- all four registers must have the same dtype
- all four registers must have the same lane count
- the lane count must be even

## 7. Related Reading

Cast-related APIs are documented separately in [a5_micro_cast.md](a5_micro_cast.md).
