# Cube Data Movement and Compute

This page documents the cube-side data-movement and compute helpers that remain in `easyasc.a2` and `easyasc.a5`.

Covered APIs:

- `gm_to_l1_nd2nz`
- `set_constant_to_l1`
- `l1_to_l0`
- `mmad`
- `l0c_to_gm_nz2nd`
- `l0c_to_l1`
- `l0c_to_ub`
- `DualMode` and `DualModeType`

## Hardware family note

Before reading any device-specific rule on this page, keep the family mapping straight:

- `device_type == "950"` -> C310
- `device_type.startswith("b")` -> C220
- in `easyasc/resources/tensorutils.h`, `__DAV_C310__` is the `950` path
- in `easyasc/resources/tensorutils.h`, `__DAV_C220_CUBE__` is the `b*` path

Several layout choices and lowering branches below depend on this mapping.

## 1. Layout Model: ND, NZ, ZN, and Alignment

Most cube helpers are easiest to understand if you separate two views of the same data:

- logical `ND` view:
  - ordinary 2D matrix semantics with shape `[M, N]`
- packed view:
  - the physical on-chip or pipeline-facing layout used by cube transfer/compute instructions

The simulator exposes the packed layout rules very clearly.

### L1 / L0A / L0B NZ-style packing

For `L1`, `L0A`, and the non-transposed `L0B` path, the simulator treats the packed storage as:

```text
[block_n, aligned_m, C0]
```

where:

- `block_n = ceil(N / C0)`
- `aligned_m = align16(M_stride)`
- `C0 = 32 / element_size_in_bytes`

Examples:

- `half` or `bfloat16`:
  - element size `2`
  - `C0 = 16`
- `float`:
  - element size `4`
  - `C0 = 8`
- `int8` / `uint8`:
  - element size `1`
  - `C0 = 32`

Logical indexing rule:

- logical `ND[row, col]`
- packed block index `block = col // C0`
- packed lane index `lane = col % C0`
- stored at `panel[block, row, lane]`

That is exactly what the simulator helpers `decode_nz_to_nd(...)` and `encode_nd_to_nz(...)` implement.

### L0C packing

`L0C` is different:

- its simulator layout uses a fixed `C0 = 16`
- this fixed `16` is independent of dtype

So `L0C` packed storage is conceptually:

```text
[block_n, align16(M_src), 16]
```

This is why `l0c_to_l1`, `l0c_to_gm_nz2nd`, and `l0c_to_ub` all decode source data with fixed `C0 = 16`.

### ZN path in `l1_to_l0`

The transpose path in `l1_to_l0` does not keep the same NZ layout.

The simulator writes a ZN-style layout whose shape depends on dtype:

- row block:
  - `32` for `int8`
  - `16` for other supported dtypes
- `N` is aligned to:
  - `32` for `int8`
  - otherwise to `C0`

This is how the transpose view for `L0A` / `L0B` is represented without materializing a normal 2D transpose in Python space.

### Why `align16(M)` appears everywhere

Most cube-side packed layouts align the `M` dimension to `16` rows in storage even when the logical copy height is smaller.

That means:

- logical tail rows remain valid
- extra physical rows are padding
- destination capacity checks usually use `align16(M_dst)` or `align16(M_src)`, not the raw logical `M`

### Tail columns

When `N` is not a multiple of `C0`:

- full blocks are copied normally
- the tail block copies only the first `tail = N % C0` lanes
- the remaining lanes in that last block are zero-padded in newly written packed buffers

The simulator explicitly zeroes destination buffers before many ND->NZ encodes for exactly this reason.

## 2. `gm_to_l1_nd2nz(dst, src, M=None, N=None, N_src=None, M_dst=None)`

- Purpose: copy a GM logical ND window into an `L1` tensor.
- Source:
  - logical ND
- Destination:
  - usually L1 NZ
  - on `b*` devices with `float` destination tensors, codegen lowers to an L1 ZZ helper instead
- Pipe:
  - `MTE2`
- Codegen lowering:
  - default: `GM2L1_ND2NZ(dst, src, M, N, N_src, M_dst);`
  - `b*` + `float`: `GM2L1_ND2ZZ(dst, src, M, N, N_src, M_dst);`

### Parameters

- `dst`:
  - destination `Tensor`
  - must be at `Position.L1`
- `src`:
  - source `GMTensor`
- `M`:
  - logical copied row count
- `N`:
  - logical copied column count
- `N_src`:
  - logical row stride of the GM source in elements
  - this is the width of the underlying source matrix, not necessarily the copied width
- `M_dst`:
  - logical destination row capacity before `align16`

### Automatic inference

If `M`, `N`, and `N_src` are all omitted, the stub infers them from the sliced `GMTensor` view:

- two sliced dimensions:
  - `M = src.span[first_sliced_dim]`
  - `N = src.span[second_sliced_dim]`
  - `N_src = src.shape[second_sliced_dim]`
- one sliced dimension:
  - treated as a single-row copy
  - `M = 1`
  - `N = src.span[sliced_dim]`
  - `N_src = src.shape[sliced_dim]`

If `M_dst` is omitted:

- `M_dst = dst.shape[0]`

### Simulator execution model

The simulator:

1. interprets `src` as a 1D pointer view into GM storage
2. interprets the logical source matrix as an ND window with row stride `N_src`
3. computes destination `C0` from destination dtype:
   - `C0 = 32 / dst.element_size()`
4. allocates/checks packed destination size using:
   - `block_count = ceil(N / C0)`
   - `aligned_M_dst = align16(M_dst)`
   - `needed = block_count * aligned_M_dst * C0`
5. zeroes the destination buffer
6. writes each full `C0` block and then the tail block if needed

### Practical meaning of ND -> NZ

Suppose:

- `dtype = half`, so `C0 = 16`
- `M = 3`
- `N = 20`
- `M_dst = 5`

Then:

- `aligned_M_dst = 16`
- `block_count = ceil(20 / 16) = 2`
- packed destination shape is conceptually `[2, 16, 16]`

Logical mapping:

- columns `0..15` go to block `0`
- columns `16..19` go to block `1`, lanes `0..3`
- block `1`, lanes `4..15` stay zero
- rows `3..15` in both blocks are padding

### Restrictions and errors

- `dst` must be `L1`
- `src` must be `GMTensor`
- `N <= N_src`
- `M <= M_dst`
- source and destination backing views must be large enough for the requested logical shape plus packing

### Example

```python
l1x <<= x[m0:m1, k0:k1]
```

With:

- `M = m1 - m0`
- `N = k1 - k0`
- `N_src = x.shape[last_sliced_dim]`
- `M_dst = l1x.shape[0]`

## 3. `set_constant_to_l1(tensor, val, n_blocks=None)`

- Purpose: fill an `L1` tensor with one scalar constant in its packed storage layout.
- Pipe:
  - `MTE2`
- Codegen lowering:
  - `InitConstValue(tensor, {1, n_blocks, 0, val});`

### Parameters

- `tensor`:
  - target `Tensor`
  - must be at `Position.L1`
- `val`:
  - scalar value
  - can be `Var`, `int`, or `float`
- `n_blocks`:
  - number of packed `C0` blocks to fill

### Dtype rules

The stub enforces that `val` matches `tensor.dtype` semantics:

- float-like tensor dtypes require float scalar input
- int-like tensor dtypes require int scalar input
- `Var` must carry a matching dtype

### Automatic inference

If `n_blocks` is omitted:

```text
n_blocks = tensor.shape[0] * tensor.shape[1] // tensor.dtype.C0
```

So the helper assumes the tensor shape already describes a packed-layout-compatible logical capacity.

### Simulator execution model

The simulator computes:

- `C0 = 32 / tensor.element_size()`
- `fill_elements = n_blocks * C0`

and fills the first `fill_elements` elements of the underlying linear L1 pointer view.

This is important:

- the operation is block-oriented
- it does not reason in logical `[M, N]` coordinates
- it simply fills the first packed region of the tensor storage

### Restrictions

- `tensor.offset` must be zero
- `n_blocks` must be non-negative
- destination view must be large enough for `n_blocks * C0` elements

### Example

```python
set_constant_to_l1(l1buf, 0.0)
```

Typical use:

- initialize an L1 staging buffer before partial overwrite
- create a padded packed tile with a known default value

## 4. `l1_to_l0(dst, src, m_dst=None, n_dst=None, m_src=None, n_src=None)`

- Purpose: move an `L1` tile into `L0A` or `L0B`.
- Source:
  - usually L1 NZ
  - on `b*` devices, `float` sources loaded through `GM2L1_ND2ZZ` are treated as L1 ZZ for lowering
- Destination:
  - L0 ZZ / NN / NZ / ZN depending on transpose path, destination, dtype, and device
- Pipe:
  - `MTE1`

### Codegen lowering

The exact emitted backend op depends on:

- destination position: `L0A` or `L0B`
- whether the source view has `.T`
- source dtype
- current device type

The parser chooses among backend ops such as:

- `L0NZ2ZZ`
- `L0NZ2NN`
- `L0NZ2NZ`
- `L0NZ2ZN`
- `L0ZZ2ZZ`
- `L0ZZ2NN`
- `L0ZZ2NZ`
- `L0ZZ2ZN`

On `b*` devices with `float` L1 sources, lowering uses the `L0ZZ2*` family; otherwise it keeps using the `L0NZ2*` family.

Current simulator note for the non-transposed path:

- on `b*`, `dst == L0A` is modeled as ZZ layout
- on `b*`, `dst == L0B` is modeled as NZ layout
- on `b*` with `float` L1 sources, the simulator decodes the source as ZZ before writing the destination layout

So the Python DSL surface is uniform, but the backend lowering is intentionally layout-specific.

### Parameters

- `dst`:
  - destination `Tensor`
  - must be `Position.L0A` or `Position.L0B`
- `src`:
  - source `Tensor`
  - must be `Position.L1`
- `m_dst`, `n_dst`:
  - logical destination tile shape
- `m_src`, `n_src`:
  - logical full source shape before slicing

### Automatic inference

If omitted:

- `m_dst = src.span[0]`
- `n_dst = src.span[1]`
- `m_src = src.shape[0]`
- `n_src = src.shape[1]`

The stub also forwards:

- `dst.is_transpose = src.is_transpose`

This is why `l0a <<= l1x.T` changes later lowering behavior without allocating a separate transposed buffer.

### Simulator execution model: non-transpose path

For the non-transposed path, the simulator:

1. interprets the source as NZ with:
   - `C0 = 32 / dst.element_size()`
   - source row stride `src_stride_m`
2. supports `l1_slice_offset=[row0, col0]` but only with slice step `1`
3. supports both:
   - aligned column starts such as `col0 = 16`
   - misaligned column starts such as `col0 = 5`
4. repacks the selected logical ND window back into destination NZ

Misaligned slicing matters because the simulator cannot just copy whole blocks when `src_col0 % C0 != 0`; it must gather lane by lane.

### Simulator execution model: transpose path

When `src.is_transpose` is true, the simulator:

1. decodes the requested L1 logical ND region
2. pads it into a ZN-compatible buffer
3. writes it with:
   - row block `32` for `int8`
   - row block `16` otherwise

This path exists because cube compute expects different packed orientations for different operands.

### Restrictions

- only `slice_step == 1` is supported in simulator
- source slice must remain inside `m_src` / `n_src`
- destination capacity is checked against packed NZ or ZN size, not only logical `m_dst * n_dst`

### Example

```python
l0a <<= l1a
l0b <<= l1b.T
```

Interpretation:

- first line keeps normal NZ-style orientation
- second line requests the transpose-oriented lowering path

## 5. `mmad(dst, src_a, src_b, M=None, N=None, K=None, is_init=True)`

- Purpose: perform cube matrix multiply-accumulate on already prepared `L0A` and `L0B` tiles.
- Pipe:
  - `M`
- Codegen lowering:
  - `MMAD(dst, src_a, src_b, M, K, N, is_init);`

### Parameters

- `dst`:
  - `Tensor` at `Position.L0C`
- `src_a`:
  - `Tensor` at `Position.L0A`
- `src_b`:
  - `Tensor` at `Position.L0B`
- `M`, `N`, `K`:
  - logical matmul dimensions
- `is_init`:
  - whether this op initializes the destination accumulation

### Automatic inference

If omitted:

- `M` comes from `src_a`
- `N` comes from `src_b`
- `K` comes from the inner dimension of `src_a`

The exact dimension used depends on whether `src_a` or `src_b` carries transpose metadata.

### Simulator execution model

The simulator:

1. decodes `src_a` NZ into logical shape `[M, K]`
2. decodes `src_b` NZ into logical shape `[N, K]`
3. computes:

```text
prod = a_nd @ b_nd^T
```

4. uses higher compute precision where appropriate:
   - `float16` / `bfloat16` accumulate in `float32`
   - small integer paths accumulate in `int32`
5. writes the result back into `L0C` NZ with fixed `C0 = 16`

### `is_init` behavior

- `is_init=True`:
  - current result overwrites the logical destination region
- `is_init=False`:
  - simulator first decodes the existing destination region
  - then adds the new product into it

So `is_init=False` is true accumulation, not just “do not zero beforehand”.

### L0C slice behavior

The simulator also supports logical destination slicing through stored `l0c_slice_offset` metadata:

- compute a submatrix
- write it into a window inside a larger `L0C` tile

But slice step must remain `1`.

### Restrictions

- `M`, `N`, `K` must be non-negative
- source/destination views must be large enough for the packed layouts
- only supported packed dtypes are accepted by the simulator

### Example

```python
mmad(l0c, l0a, l0b, M=M, N=N, K=K, is_init=True)
```

Typical accumulation loop:

```python
for k_tile in range(k_tiles):
    mmad(l0c, l0a, l0b, M=M, N=N, K=K_tile, is_init=(k_tile == 0))
```

## 6. `l0c_to_gm_nz2nd(dst, src, M=None, N=None, N_dst=None, M_src=None)`

- Purpose: write an `L0C` tile back to GM as logical ND.
- Source:
  - L0C NZ with fixed `C0 = 16`
- Destination:
  - GM ND
- Pipe:
  - `FIX`
- Codegen lowering:
  - `L0C2GM_NZ2ND(dst, src, M, N, N_dst, M_src);`

### Parameters

- `dst`:
  - destination `GMTensor`
- `src`:
  - source `Tensor` at `Position.L0C`
- `M`, `N`:
  - logical written size
- `N_dst`:
  - destination row stride in elements
- `M_src`:
  - logical source row capacity before `align16`

### Automatic inference

If `M`, `N`, and `N_dst` are all omitted, the stub infers them from the sliced GM destination view:

- two sliced dimensions:
  - `M = dst.span[first_sliced_dim]`
  - `N = dst.span[second_sliced_dim]`
  - `N_dst = dst.shape[second_sliced_dim]`
- one sliced dimension:
  - `M = 1`
  - `N = dst.span[sliced_dim]`
  - `N_dst = dst.shape[sliced_dim]`

If `M_src` is omitted:

- `M_src = src.shape[0]`

### Simulator execution model

The simulator:

1. decodes source `L0C` NZ with:
   - fixed `C0 = 16`
   - source stride `align16(M_src)`
2. obtains logical ND shape `[M, N]`
3. writes it into the GM pointer region using row stride `N_dst`

Unlike on-chip packed formats, GM is treated as ordinary ND with strided rows:

- row `r`
- begins at offset `r * N_dst`

### Atomic interaction

If an atomic context is active, the simulator does not overwrite directly.
Instead it combines the decoded logical ND region with the existing GM region using the active mode:

- `add`
- `max`
- `min`

### Restrictions

- `M <= M_src`
- `N <= N_dst`
- source must have enough packed `L0C` storage
- destination pointer region must have enough ND capacity

### Example

```python
z[m0:m1, n0:n1] <<= l0c
```

This typically infers:

- `M = m1 - m0`
- `N = n1 - n0`
- `N_dst = z.shape[last_sliced_dim]`

## 7. `l0c_to_l1(dst, src, M=None, N=None, M_dst=None, M_src=None, relu=False)`

- Purpose: move an `L0C` tile into `L1`.
- Source:
  - L0C NZ with fixed `C0 = 16`
- Destination:
  - L1 NZ with dtype-based `C0 = 32 / element_size`
- Pipe:
  - `FIX`
- Codegen lowering:
  - `L0C2L1(dst, src, M, N, M_dst, M_src, relu);`

### Parameters

- `dst`:
  - destination `Tensor` at `Position.L1`
- `src`:
  - source `Tensor` at `Position.L0C`
- `M`, `N`:
  - logical copied size
- `M_dst`:
  - logical destination row capacity before `align16`
- `M_src`:
  - logical source row capacity before `align16`
- `relu`:
  - whether to clamp negative values before writing

### Automatic inference

If omitted:

- `M = dst.span[0]`
- `N = dst.span[1]`
- `M_dst = dst.shape[0]`
- `M_src = src.shape[0]`

### Simulator execution model

The simulator:

1. decodes source `L0C` with:
   - fixed `C0 = 16`
   - source stride `align16(M_src)`
2. converts the decoded logical ND tensor to `dst.dtype`
3. optionally applies ReLU
4. encodes it into destination `L1` NZ using:
   - `C0_dst = 32 / dst.element_size()`
   - destination stride `align16(M_dst)`

This op is therefore a true repack:

- source packing rule and destination packing rule are different
- dtype may also change

### Why this is a useful example of “align by 16 or by C0”

In one op, both alignment families appear:

- source `L0C`:
  - fixed `C0 = 16`
- destination `L1`:
  - dtype-based `C0 = 32 / elem_size`
- both sides still align the row capacity with `align16(M_*)`

### Example

```python
l1mid <<= l0c
```

### Example with cast + ReLU

```python
l0c_to_l1(l1_out, l0c_acc, relu=True)
```

This decodes float accumulation data from `L0C`, clamps negative values, casts to `l1_out.dtype`, and then repacks into L1 NZ.

## 8. `DualModeType` and `DualMode`

`DualModeType` is the small value class used by `l0c_to_ub` to describe how one `L0C` result is routed toward vec-side consumers.

### `DualModeType`

- Fields:
  - `name`
  - `value`
- Behavior:
  - `str(mode)` returns names such as `SINGLE` or `SPLITM`
  - equality compares both name and numeric value

It is not usually constructed manually.

### `DualMode`

`DualMode` is the enum-like namespace that exports the three supported modes:

- `DualMode.SINGLE`
  - numeric value `0`
- `DualMode.SPLITM`
  - numeric value `1`
- `DualMode.SPLITN`
  - numeric value `2`

The stub also accepts raw integers `0`, `1`, and `2`, but the enum names are clearer and safer in user code.

### Meaning of each mode

`SINGLE`:

- no split
- one complete logical ND tile is sent to exactly one sub-block
- `sub_block_id` chooses lane `0` or `1`

`SPLITM`:

- split by rows
- the first half of rows goes to lane `0`
- the second half of rows goes to lane `1`
- requires even `M`

`SPLITN`:

- split by columns
- the left half of columns goes to lane `0`
- the right half of columns goes to lane `1`
- requires even `N`

### Why `DualMode` exists

`l0c_to_ub` is often the handoff point between cube output and vec processing.

The framework models two vec sub-block consumers, so a single `L0C` result may need to be:

- delivered whole to one lane
- split by rows across the two lanes
- split by columns across the two lanes

`DualMode` controls exactly that routing.

## 9. `l0c_to_ub(dst, src, M=None, N=None, N_dst=None, M_src=None, dual_mode=DualMode.SPLITM, sub_block_id=0, relu=False)`

- Purpose: move an `L0C` tile into `UB`, usually as a cube-to-vec handoff.
- Source:
  - L0C NZ with fixed `C0 = 16`
- Destination:
  - logical ND payload published into one or two vec lanes
- Pipe:
  - `FIX`
- Codegen lowering:
  - `L0C2UB_NZ2ND(dst, src, M, N, N_dst, M_src, dual_mode, sub_block_id, relu);`

### Parameters

- `dst`:
  - destination `Tensor` at `Position.UB`
- `src`:
  - source `Tensor` at `Position.L0C`
- `M`, `N`:
  - logical source tile size before splitting
- `N_dst`:
  - logical destination row stride
- `M_src`:
  - logical source row capacity before `align16`
- `dual_mode`:
  - `DualModeType` or raw integer `0/1/2`
- `sub_block_id`:
  - active lane id when using `SINGLE`
  - must be `0` or `1`
- `relu`:
  - optional clamp before publishing

### Automatic inference

If `M`, `N`, and `N_dst` are omitted, the stub infers them from `dst` and `dual_mode`:

- `SINGLE`:
  - `M = dst.span[0]`
  - `N = dst.span[1]`
- `SPLITM`:
  - `M = dst.span[0] * 2`
  - `N = dst.span[1]`
- `SPLITN`:
  - `M = dst.span[0]`
  - `N = dst.span[1] * 2`

In all three cases:

- `N_dst = dst.shape[1]`

If `M_src` is omitted:

- `M_src = src.shape[0]`

This is why a default `dst <<= src_l0c` route chooses `SPLITM`:

- one UB view describes one lane's half-tile
- the full source `M` is inferred as twice that lane-local height

### Simulator execution model

The simulator:

1. decodes source `L0C` NZ using fixed `C0 = 16`
2. converts it to `dst.dtype`
3. optionally applies ReLU
4. routes the logical ND result according to `dual_mode`
5. publishes flat ND payloads into the shared `L0CToUBState`

The publication is lane-aware and also slot-aware:

- destination tensor name identifies the logical handoff buffer family
- buffer slot index is preserved when the destination came from `DBuff` / `TBuff`

### Routing rules

`SINGLE`:

- publish the full `[M, N]` logical tile to lane `sub_block_id`
- the other lane receives nothing

`SPLITM`:

- requires even `M`
- lane `0` gets `logical[:M/2, :]`
- lane `1` gets `logical[M/2:, :]`

`SPLITN`:

- requires even `N`
- lane `0` gets `logical[:, :N/2]`
- lane `1` gets `logical[:, N/2:]`

### Destination capacity rules

Capacity is checked against the lane-local destination view, not the full source tile:

- `SINGLE`:
  - destination must hold `M * N`
- `SPLITM`:
  - destination must hold `(M/2) * N`
- `SPLITN`:
  - destination must hold `M * (N/2)`

This matches how vec lanes actually consume the published payload.

### Example: default split by rows

```python
ub_lane <<= l0c_tile
```

If `ub_lane.shape == [16, 16]`, the default inference becomes:

- `dual_mode = SPLITM`
- `M = 32`
- `N = 16`

So lane `0` and lane `1` each receive one `16 x 16` half-tile split along rows.

### Example: split by columns

```python
l0c_to_ub(ub_lane, l0c_tile, dual_mode=DualMode.SPLITN)
```

If `ub_lane.shape == [16, 16]`, the inferred full source tile is:

- `M = 16`
- `N = 32`

Lane routing:

- lane `0`: left `16` columns
- lane `1`: right `16` columns

### Example: publish to only one lane

```python
l0c_to_ub(ub_lane, l0c_tile, dual_mode=DualMode.SINGLE, sub_block_id=1)
```

Meaning:

- the full logical tile is published only to vec sub-block `1`
- sub-block `0` receives nothing for that publication

## 10. Choosing the Right Writeback Path

Use `l0c_to_gm_nz2nd` when:

- cube output is final or should live in GM
- the consumer expects ordinary ND layout

Use `l0c_to_l1` when:

- another cube stage still needs the data in packed on-chip form
- you want dtype conversion or ReLU before the next stage

Use `l0c_to_ub` when:

- vec code will consume the result next
- the result must be routed to one or both vec sub-blocks

## 11. Common Pitfalls

- Do not assume all packed layouts use the same `C0`. `L0C` uses fixed `16`, while `L1`/`L0A`/`L0B` use `32 / element_size`.
- Do not size buffers only from logical `M * N`. Capacity checks usually use packed size with `align16(M)` and block count `ceil(N / C0)`.
- Do not forget that `l1_to_l0` and `l0c_to_l1` are repacking operations, not plain memcpy.
- Do not use odd `M` with `DualMode.SPLITM` or odd `N` with `DualMode.SPLITN`.
- Do not assume `l0c_to_ub` writes one normal UB tensor directly in simulator. It publishes lane-local payloads through shared handoff state.
