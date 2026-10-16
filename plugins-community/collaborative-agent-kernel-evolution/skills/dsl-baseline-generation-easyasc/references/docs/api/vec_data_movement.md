# A2 and Shared Vec Data Movement

This page documents the vector-side helpers that move data between `GM`, `UB`, and `L1`.

The descriptions below follow both the public stub APIs in `easyasc/stub_functions/vec/datamove.py`
and the current V2 simulator behavior in `easyasc/simulator_v2/ops/vec/mte2.py`,
`easyasc/simulator_v2/ops/vec/mte3.py`, and `easyasc/simulator_v2/ops/vec/v.py`
(including legacy-layout fallback through `easyasc/simulator_v2/ops/vec/_legacy_vpipe.py` where applicable).

Availability summary:

- exported by `easyasc.a2`: `gm_to_ub_pad`, `ub_to_gm_pad`, `ub_to_ub`
- exported by `easyasc.a5`: all functions on this page

Related page:

- [a2_vec_control.md](a2_vec_control.md) covers vec cast, compare/select, mask helpers, and gather/scatter helpers

## 1. Core Units and Addressing Rules

These APIs all end up operating on flattened pointer regions in the simulator.

- after slicing, the simulator expects a 1D pointer view for both source and destination
- all address formulas below are therefore written against a flattened array such as `src_flat` or `dst_flat`
- source and destination element sizes must match exactly

Two units show up repeatedly:

- `elem_size = dtype.size`
- `c0 = 32 / elem_size`

Common `c0` values:

| dtype | element size | `c0` |
| --- | --- | --- |
| `int8` / `uint8` | 1 byte | 32 |
| `half` / `bfloat16` | 2 bytes | 16 |
| `float` / `int32` | 4 bytes | 8 |

The important consequence is:

- `gm_to_ub_pad()` and `ub_to_gm_pad()` express the GM-side stride in elements, but the UB-side stride in extra 32-byte blocks after the aligned local burst footprint
- `ub_to_ub()` expresses both `burst_len` and both strides directly in 32-byte blocks
- `ub_to_l1_nd2nz()` and `ub_to_l1_nz()` use `c0` and `align16(m_dst)` to lay out NZ blocks in L1

## 2. `gm_to_ub_pad(dst, src, n_burst=None, burst_len_element=None, src_stride_element=None, dst_stride=None)`

- Purpose: Copy one or more GM bursts into UB and pad each UB burst up to a 32-byte boundary.

Parameter meaning:

- `dst`: destination UB `Tensor`
- `src`: source `GMTensor` or GM slice
- `n_burst`: number of bursts to copy
- `burst_len_element`: logical payload length of each burst, measured in elements
- `src_stride_element`: gap between consecutive GM bursts, measured in elements
- `dst_stride`: extra UB gap after each aligned local burst, measured in 32-byte blocks

What the simulator does:

1. Convert the logical sizes to bytes:
   - `burst_len_byte = burst_len_element * elem_size`
   - `src_stride_byte = src_stride_element * elem_size`
2. Align the local UB burst footprint:
   - `aligned_burst_len_byte = align32(burst_len_byte)`
3. Compute per-burst steps:
   - `src_step = burst_len_byte + src_stride_byte`
   - `dst_step = aligned_burst_len_byte + dst_stride * 32`
4. For each burst `b`:
   - copy `src_flat_bytes[b * src_step : b * src_step + burst_len_byte]`
   - into `dst_flat_bytes[b * dst_step : b * dst_step + burst_len_byte]`
5. If `aligned_burst_len_byte > burst_len_byte`, zero-fill the padded bytes in the destination burst.

That last rule is the main difference from a plain memcpy:

- GM contributes only the logical payload
- UB receives the payload plus zero padding up to the next 32-byte boundary

Concrete example with `half`:

```text
burst_len_element = 20
elem_size = 2
burst_len_byte = 40
aligned_burst_len_byte = 64

for each burst:
- copy 20 half elements from GM
- write them into the first 20 half slots in UB
- zero-fill the remaining 12 half slots in that 32-byte-aligned UB burst
```

Default inference:

- If the GM view has rank 1:
  - `n_burst = 1`
  - `burst_len_element = span[0]`
  - both GM-side and UB-side default strides are `0`
- If `src` is a 2D GM view with `span = [rows, cols]` and `shape = [full_rows, full_cols]`:
  - `n_burst = rows`
  - `burst_len_element = cols`
  - `src_stride_element = full_cols - cols`
- If `src` has rank greater than 2:
  - default inference only supports 1 or 2 sliced dimensions
  - if only one dimension is sliced:
    - slicing the last dimension becomes one burst
    - otherwise the burst length is the product of the contiguous suffix after that dimension
  - if two dimensions are sliced:
    - the inner sliced dimension must cover the contiguous suffix of the GM view
    - `n_burst` comes from the outer sliced span
    - `burst_len_element` becomes the product of the inner sliced span and the untouched trailing suffix
- `dst_stride` defaults to:
  - `(dst.shape[1] - burst_len_element) // dst.dtype.C0`

The default `dst_stride` is a floor division, not `CeilDiv`. That matches the simulator contract: the local burst already occupies `align32(burst_len_byte)` bytes, so `dst_stride` only expresses extra whole 32-byte blocks after that aligned footprint.

Example: rank-3 GM slice inference

```python
@kernel()
def copy(inp: GMTensor):
    dst = Tensor(DT.float, [2, 512], Position.UB)
    dst <<= inp[0, 6:8, :]
    return inp
```

This infers:

- `n_burst = 2`
- `burst_len_element = 512`
- `src_stride_element = 0`
- `dst_stride = 0`

Restrictions and checks:

- `dst.position` must be `Position.UB`
- `dst.dtype` must equal `src.dtype`
- all resolved transfer parameters must be non-negative
- the flattened GM source region must contain all requested bytes
- the flattened UB destination region must contain all aligned local bursts

When to use it:

- loading ND GM tiles into a padded UB tile
- loading widths that are not exact multiples of `c0`
- creating a UB tile that later participates in vec ops or `ub_to_gm_pad()`

Minimal usage:

```python
ub <<= x[m:m + rows, :]
```

## 3. `ub_to_gm_pad(dst, src, n_burst=None, burst_len_element=None, src_stride=None, dst_stride_element=None)`

- Purpose: Copy one or more UB bursts back to GM, dropping UB-side padding on the way out.

Parameter meaning:

- `dst`: destination `GMTensor` or GM slice
- `src`: source UB `Tensor`
- `n_burst`: number of bursts to store
- `burst_len_element`: logical payload length of each burst, measured in elements
- `src_stride`: extra UB gap after each aligned local burst, measured in 32-byte blocks
- `dst_stride_element`: gap between consecutive GM bursts, measured in elements

What the simulator does:

1. Convert the GM stride to bytes:
   - `burst_len_byte = burst_len_element * elem_size`
   - `dst_stride_byte = dst_stride_element * elem_size`
2. Reconstruct the UB burst footprint:
   - `aligned_burst_len_byte = align32(burst_len_byte)`
3. Compute per-burst steps:
   - `src_step = aligned_burst_len_byte + src_stride * 32`
   - `dst_step = burst_len_byte + dst_stride_byte`
4. For each burst `b`:
   - read only the first `burst_len_byte` bytes from the UB burst
   - write them into the GM burst

So `ub_to_gm_pad()` is the exact logical inverse of `gm_to_ub_pad()`:

- UB may have a padded local row
- only the logical payload is written back to GM
- the padded UB tail is ignored

Concrete example with `half`:

```text
burst_len_element = 20
elem_size = 2
burst_len_byte = 40
aligned_burst_len_byte = 64
src_stride = 0

for each burst:
- read the first 20 half elements from a 32-half UB row footprint
- ignore the remaining 12 padded half elements
- write only those 20 logical elements to GM
```

Default inference:

- If the GM view has rank 1:
  - `n_burst = 1`
  - `burst_len_element = span[0]`
  - both GM-side and UB-side default strides are `0`
- If `n_burst` is omitted, the stub infers all three GM-side parameters from `dst` exactly the same way that `gm_to_ub_pad()` infers them from its GM source.
- If you provide `n_burst` explicitly, the stub no longer infers `burst_len_element` or `dst_stride_element` for you.
- `src_stride` defaults to:
  - `(src.shape[1] - burst_len_element) // src.dtype.C0`

That means the common padded-UB pattern:

```python
out[0, 6:8, :20] <<= src_ub
```

typically uses:

- `burst_len_element = 20`
- `src_stride = (src_ub.shape[1] - 20) // c0`
- `dst_stride_element` inferred from the GM slice width

Atomic behavior:

- If global atomic mode is enabled, the simulator does not overwrite the GM payload directly.
- Instead, it applies an elementwise reduction between the current GM region and the UB payload.
- Supported modes are `add`, `max`, and `min`.
- If the mode is missing, the simulator defaults to `add`.
- The simulator widens the compute dtype before the reduction:
  - `half` / `bfloat16` -> `float32`
  - `int8` / `uint8` / `int16` -> `int32`
  - other dtypes stay in their original dtype

Atomic alignment restrictions:

- `burst_len_byte` must be aligned to `elem_size`
- `dst_stride_byte` must be aligned to `elem_size`
- `src_stride * 32` must be aligned to `elem_size`
- the resulting `src_step` and `dst_step` must also be aligned to `elem_size`

Restrictions and checks:

- `src.position` must be `Position.UB`
- `dst.dtype` must equal `src.dtype`
- all resolved transfer parameters must be non-negative
- the flattened UB source region must contain all aligned local bursts
- the flattened GM destination region must contain all logical bursts

Minimal usage:

```python
out[m:m + rows, :valid_n] <<= ub
```

## 4. `ub_to_l1_nd2nz(dst, src, m_dst=None, n_dst=None, m_src=None, n_src=None)`

- Purpose: Read a logical ND tile from UB and publish it into L1 in NZ layout.

Availability:

- exported only by `easyasc.a5`
- only valid when `device_type == "950"`

Parameter meaning:

- `dst`: destination `Tensor` in `Position.L1`
- `src`: source `Tensor` in `Position.UB`
- `m_dst`: logical destination height used to compute the NZ row stride
- `n_dst`: logical destination width capacity used for validation
- `m_src`: number of logical source rows to publish
- `n_src`: number of logical source columns to publish

The key layout constants are:

- `c0 = 32 / elem_size`
- `dst_stride_m = align16(m_dst)`
- `block_count = ceil(n_src / c0)`

The simulator treats:

- the source as a dense 2D ND tile of shape `[m_src, n_src]`
- the destination as an NZ panel of shape `[block_count, dst_stride_m, c0]`

Element mapping rule:

```text
block = col // c0
lane = col % c0

dst_panel[block, row, lane] = src_nd[row, col]
```

for every:

- `0 <= row < m_src`
- `0 <= col < n_src`

Important behavior details:

- `m_src` must not exceed `m_dst`
- `n_src` must not exceed `n_dst`
- `n_dst` is only a logical capacity check; the actual NZ block count still comes from `n_src`
- only the touched NZ positions are overwritten
- rows `m_src:dst_stride_m` in each block are left unchanged
- if the last block is partial, lanes `tail:c0` are left unchanged
- blocks beyond `ceil(n_src / c0)` are left unchanged

This is why tests fill `dst` with a sentinel value before the copy: the simulator preserves untouched parts of the L1 panel.

Default inference:

- `m_dst` defaults to `dst.shape[0]`
- `n_dst` defaults to `dst.span[1]`
- `m_src` defaults to `src.span[0]`
- `n_src` defaults to `src.span[1]`

The `m_dst` rule is easy to miss. If you write:

```python
dst = Tensor(DT.half, [32, 32], Position.L1)
src = Tensor(DT.half, [32, 32], Position.UB)
ub_to_l1_nd2nz(dst[4:20, 3:15], src[1:17, 2:14])
```

the stub infers:

- `m_dst = 32`, not `16`
- `n_dst = 12`
- `m_src = 16`
- `n_src = 12`

That matches the simulator layout rule: the L1 row stride is derived from the full destination allocation height, not from the sliced row count.

Concrete example with `half`:

```text
m_dst = 32
m_src = 16
n_src = 20
elem_size = 2
c0 = 16
dst_stride_m = 32
block_count = 2
```

Result:

- columns `0..15` go to `dst_panel[0, 0:16, 0:16]`
- columns `16..19` go to `dst_panel[1, 0:16, 0:4]`
- `dst_panel[:, 16:32, :]` keeps its previous value
- `dst_panel[1, :, 4:16]` keeps its previous value

Restrictions and checks:

- `dst.position` must be `Position.L1`
- `src.position` must be `Position.UB`
- `dst.dtype` must equal `src.dtype`
- `elem_size` must divide 32 exactly
- the flattened UB source region must contain `m_src * n_src` elements
- the flattened L1 destination region must contain `ceil(n_src / c0) * align16(m_dst) * c0` elements

Minimal usage:

```python
l1_tile <<= ub_tile
```

## 5. `ub_to_l1_nz(dst, src, m_dst=None, n_dst=None, m_src=None, n_src=None)`

- Purpose: Publish a UB tile that is already packed in compact NZ order into the padded NZ layout used by L1.

Availability:

- exported only by `easyasc.a5`
- only valid when `device_type == "950"`

Parameter meaning:

- the parameters have the same logical meaning as `ub_to_l1_nd2nz()`
- the difference is entirely in how the source UB region is interpreted

Source layout rule:

- `src` is not treated as ND
- it is treated as compact NZ blocks laid out back-to-back
- each block contributes exactly `m_src * c0` elements, even for the last partial-`N` block

Destination layout rule:

- `dst` still uses padded NZ layout with:
  - `c0 = 32 / elem_size`
  - `dst_stride_m = align16(m_dst)`
  - `block_count = ceil(n_src / c0)`

For block `b`, the simulator copies:

```text
src_begin = b * (m_src * c0)
dst_begin = b * (align16(m_dst) * c0)
copy_len  = m_src * c0
```

So the compact source packs blocks tightly, while the L1 destination inserts row padding between blocks.

Concrete example with `half`:

```text
m_dst = 32
m_src = 10
n_src = 20
elem_size = 2
c0 = 16
block_count = 2
```

Then:

- source block 0 occupies flat elements `[0 : 160)`
- source block 1 occupies flat elements `[160 : 320)`
- destination block 0 starts at flat element `0`
- destination block 1 starts at flat element `32 * 16 = 512`

This is why `src.nz()` is the natural producer for `ub_to_l1_nz()`: the source already contains padded `c0` lanes inside each block, but does not contain the larger `align16(m_dst)` row padding that L1 requires.

Important behavior details:

- `m_src <= m_dst` and `n_src <= n_dst` are still required
- `n_dst` is still only a logical capacity check; the actual block count still comes from `n_src`
- the last block still copies a full `m_src * c0` elements from the source
- tail lanes in that last source block must therefore already be padded in UB
- rows `m_src:align16(m_dst)` in each destination block are left unchanged
- blocks beyond `ceil(n_src / c0)` are left unchanged

Default inference:

- identical to `ub_to_l1_nd2nz()`
- `m_dst` still defaults to `dst.shape[0]`, not `dst.span[0]`

Restrictions and checks:

- `dst.position` must be `Position.L1`
- `src.position` must be `Position.UB`
- `dst.dtype` must equal `src.dtype`
- `elem_size` must divide 32 exactly
- for every block, the compact source region must contain `m_src * c0` elements
- for every block, the destination region must contain `align16(m_dst) * c0` elements

Minimal usage:

```python
l1_tile <<= ub_tile.nz()
```

## 6. `ub_to_ub(dst, src, n_burst=None, burst_len=None, src_stride=None, dst_stride=None)`

- Purpose: Copy UB data in 32-byte burst units, optionally skipping 32-byte gaps between bursts.

Parameter meaning:

- `dst`: destination UB `Tensor`
- `src`: source UB `Tensor`
- `n_burst`: number of bursts
- `burst_len`: payload length of each burst, measured in 32-byte blocks
- `src_stride`: gap between source bursts, measured in 32-byte blocks
- `dst_stride`: gap between destination bursts, measured in 32-byte blocks

What the simulator does:

- `burst_len_byte = burst_len * 32`
- `src_step = (burst_len + src_stride) * 32`
- `dst_step = (burst_len + dst_stride) * 32`

For each burst `b`:

```text
dst_flat_bytes[b * dst_step : b * dst_step + burst_len_byte] =
    src_flat_bytes[b * src_step : b * src_step + burst_len_byte]
```

Unlike `gm_to_ub_pad()` and `ub_to_gm_pad()`:

- there is no extra align-up step, because `burst_len` is already expressed in 32-byte units
- there is no zero-fill rule
- the copied footprint is always an exact multiple of 32 bytes

Default inference:

- `n_burst = dst.span[0]`
- `burst_len = CeilDiv(dst.span[1], dst.dtype.C0)`
- `dst_stride = CeilDiv(dst.shape[1] - dst.span[1], dst.dtype.C0)`
- `src_stride = CeilDiv(src.shape[1] - dst.span[1], src.dtype.C0)`

The `CeilDiv` part matters. If the logical width is not a multiple of `c0`, `ub_to_ub()` still copies the whole final 32-byte block.

Example with `float32`:

```text
c0 = 8
n_burst = 2
burst_len = 2
src_stride = 1
dst_stride = 0
```

Then:

- destination burst 0 receives `src[0:16]`
- destination burst 1 receives `src[24:40]`

That is exactly the behavior covered by the simulator test.

Typical use:

```python
tmp <<= src
```

or explicitly:

```python
ub_to_ub(tmp, src, n_burst=2, burst_len=2, src_stride=1, dst_stride=0)
```

Restrictions and checks:

- `dst.position` and `src.position` must both be `Position.UB`
- `dst.dtype` must equal `src.dtype`
- all resolved transfer parameters must be non-negative
- the flattened source region must contain every requested burst
- the flattened destination region must contain every requested burst
