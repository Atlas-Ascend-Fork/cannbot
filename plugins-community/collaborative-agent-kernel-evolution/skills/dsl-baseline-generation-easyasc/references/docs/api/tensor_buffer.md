# Tensor and Buffer Types

This page documents the main tensor-like objects used by kernel authors to describe on-chip storage, GM views, and slot-based buffering.

These classes are closely related:

- `Tensor`: 2D on-chip tensor or tensor view
- `GMTensor`: GM tensor or GM tensor view
- `DBuff`: double-buffer family that yields `Tensor` slot views
- `TBuff`: triple-buffer family that yields `Tensor` slot views

The implementation lives in `easyasc/utils/Tensor.py`, so several behaviors that look like "syntax sugar" in user code are actually driven by Python operator overloads in these classes.

## 1. `Tensor`

### `Tensor(dtype, shape, position=Position.L1, name="")`

- Purpose: represent a 2D local tensor in `L1`, `L0A`, `L0B`, `L0C`, or `UB`.
- Constructor parameters:
  - `dtype`: `DataTypeValue`
  - `shape`: 2D shape, each dimension must be `int` or `Var`
  - `position`: local memory position
  - `name`: optional explicit tensor name
- Runtime behavior:
  - shape rank must be exactly `2`
  - if `name=""`, the runtime creates a temporary name such as `_tmp_tensor_*`
  - constructor emits `create_tensor` into the active kernel or active micro module
- Important stored metadata:
  - `shape`: declared logical shape
  - `offset`: current per-dimension view offset
  - `span`: current visible view size
  - `step`: current per-dimension step, currently always `1`
  - `source_buf` / `source_index`: filled when this tensor is a `DBuff` or `TBuff` slot view
  - `is_transpose`: marks an L1 transpose view
  - `_is_nz`: marks a UB tensor view as already NZ-packed
  - `vec_copy_mode`: marks special UB<->Reg load/store layouts such as `single()` or `unpack()`

Example:

```python
ub = Tensor(DT.float, [M, N], Position.UB)
l1 = Tensor(DT.half, [128, K], Position.L1)
```

### `set_shape(shape)`

- Purpose: update the logical shape and current span of an existing tensor object.
- Parameters:
  - `shape`: 2D list/tuple
- Restrictions:
  - rank must still be exactly `2`
- Behavior:
  - updates both `shape` and `span`
  - does not emit a new instruction by itself
- Typical use:
  - internal shape adjustment before `l1_to_l0`
  - advanced helper code, not a common first-line user API

### `.T`

- Purpose: create an L1 transpose view without allocating a new tensor.
- Restrictions:
  - only valid when `position is Position.L1`
- Behavior:
  - returns a shallow view copy
  - sets `is_transpose=True`
  - does not emit `create_tensor`
  - actual transpose interpretation is consumed later by `l1_to_l0`, `mmad`, parser lowering, and simulator execution

Example:

```python
l0a <<= l1x.T
```

### `.nz()`

- Purpose: mark a UB tensor view as already packed in NZ layout.
- Behavior:
  - returns a shallow view copy
  - sets `_is_nz=True`
  - used by `Tensor.__ilshift__` when copying `UB -> L1`
- Effect:
  - `l1 <<= ub.nz()` routes to `ub_to_l1_nz`
  - `l1 <<= ub` routes to `ub_to_l1_nd2nz`

Example:

```python
l1 <<= ub_packed.nz()
```

### `reinterpret(target_dtype, name="")`

- Purpose: create a dtype-reinterpreted tensor view over the same storage.
- Parameters:
  - `target_dtype`: destination `DataTypeValue`
  - `name`: optional view name
- Restrictions:
  - source must be a `Tensor`
  - `L0C` tensors are not supported
- Behavior:
  - preserves storage/view metadata such as `offset`, `source_buf`, and transpose state
  - rescales the second dimension of both `shape` and `span` according to `target_dtype.C0 / src.dtype.C0`
  - emits a `reinterpret` instruction in kernel context
- Practical meaning:
  - reinterpretation is a layout-level view change, not a numeric cast
  - use it when the underlying packed storage should be read with another element type
- Relation to the top-level helper:
  - `tensor.reinterpret(...)` is a thin convenience wrapper around `reinterpret(tensor, ...)`
  - both forms emit the same `reinterpret` instruction and create the same kind of view

Example:

```python
ub_u8 = ub_fp16.reinterpret(DT.uint8)
```

### `dst <<= other`

`Tensor.__ilshift__` is one of the main dispatch points in the DSL. The actual instruction chosen depends on the destination tensor position and the runtime type of `other`.

#### `Tensor <<= VecOP`

- Purpose: materialize a vec expression into a UB destination.
- Restrictions:
  - destination must be `Position.UB`
- Behavior:
  - calls `VecOP.emit(dst)`

Example:

```python
dst <<= src.abs() + 1.0
```

#### `Tensor <<= GMTensor`

- Purpose: load GM data into local storage.
- Supported routes:
  - `UB <<= GMTensor` -> `gm_to_ub_pad`
  - `L1 <<= GMTensor` -> `gm_to_l1_nd2nz`
- Restrictions:
  - destination must be `UB` or `L1`

Example:

```python
ub <<= x_gm[mb:mb + 128, kb:kb + 128]
l1 <<= x_gm[mb:mb + 128, kb:kb + 128]
```

#### `Tensor <<= Tensor`

- Purpose: move data between local memory domains.
- Supported routes:
  - `UB <<= UB` -> `ub_to_ub`
  - `L1 <<= UB` -> `ub_to_l1_nd2nz`
  - `L1 <<= UB.nz()` -> `ub_to_l1_nz`
  - `L1 <<= L0C` -> `l0c_to_l1`
  - `UB <<= L0C` -> `l0c_to_ub`
  - `L0A/L0B <<= L1` -> `l1_to_l0`
- Additional behavior for `L0A/L0B <<= L1`:
  - destination shape is updated to the source view span
  - if the destination tensor itself came from a same-dtype buffer family, the parent buffer shape is updated too
  - transpose state is forwarded through `l1_to_l0`
- Restrictions:
  - any unsupported position pair raises an error

Example:

```python
l0a <<= l1a
ub_out <<= l0c
l1_mid <<= ub_mid.nz()
```

#### `Tensor <<= Reg`

- Purpose: store a micro register into UB.
- Scope:
  - primarily an A5 micro-side convenience route
- Behavior:
  - if `dst.dtype == src.dtype`, emits plain `reg_to_ub`
  - if dtypes differ, runtime allocates a temporary register, casts into the destination dtype, then chooses:
    - `reg_to_ub_pack4` for `4-byte -> 1-byte`
    - `reg_to_ub_downsample` for `4-byte -> 2-byte` or `2-byte -> 1-byte`
    - plain `reg_to_ub` otherwise
- Restrictions:
  - casted register stores must happen inside an active `@vf` context

Example:

```python
ub_dst <<= reg_f32.astype(DT.half)
```

#### `Tensor <<= RegList`

- Purpose: store a row-style register list into UB.
- Behavior:
  - writes each register into a contiguous block-sized slice of the destination tensor
  - block size is `256 // dtype.size`

Example:

```python
ub_rows <<= reg_rows
```

#### `Tensor <<= RegOP`

- Purpose: materialize a register-expression or explicit reg-to-UB data movement into UB.
- Behavior:
  - direct reg-to-UB style ops such as `reg_to_ub_scatter` emit directly
  - other reg expressions are evaluated into a temporary register and then stored with `reg_to_ub`

### Copy-mode view helpers

These methods do not move data by themselves. They return a shallow tensor view with `vec_copy_mode` set. That mode is later consumed by `Reg <<= tensor_view` or related micro-store logic.

#### `downsample()`

- Marks the tensor view for narrow-lane load semantics.
- Common effect:
  - `reg <<= ub.downsample()` routes to `ub_to_reg_downsample`

#### `upsample()`

- Marks the tensor view for widened-lane load semantics.
- Common effect:
  - `reg <<= ub.upsample()` routes to `ub_to_reg_upsample`

#### `unpack()`

- Marks the tensor view for 2-way unpacked load semantics.
- Common effect:
  - `reg <<= ub.unpack()` routes to `ub_to_reg_unpack`

#### `unpack4()`

- Marks the tensor view for 4-way unpacked load semantics.
- Common effect:
  - `reg <<= ub.unpack4()` routes to `ub_to_reg_unpack4`

#### `brcb()`

- Marks the tensor view for BRCB-style scalar broadcast load semantics.
- Common effect:
  - `reg <<= ub.brcb()` routes to `ub_to_reg_brcb`

#### `single()`

- Marks the tensor view for scalar extraction semantics.
- Common effect:
  - `reg <<= ub[0:1, col:col + 1].single()` routes to `ub_to_reg_single`

Example:

```python
scalar_reg <<= y_ub[row:row + 1, 0:1].single()
```

### Vec-expression builders

`Tensor` also acts as the entry point for A2 vec expressions.

- Arithmetic operators:
  - `a + b`, `a - b`, `a * b`, `a / b`
- Scalar forms:
  - `a + 1.0`, `a * alpha`
- Unary helpers:
  - `.exp()`, `.ln()`, `.abs()`, `.rec()`, `.sqrt()`, `.rsqrt()`, `.relu()`, `.vnot()`
- Group reducers:
  - `.cmax()`, `.cgmax()`, `.cmin()`, `.cgmin()`, `.cadd()`, `.cgadd()`, `.cpadd()`
- Other helpers:
  - `.cast()`
  - `.maximum(other)`
  - `.minimum(other)`
  - bitwise-style `.__and__(other)` / `.__or__(other)`

Restrictions:

- these builders are only valid on `UB` tensors
- they return `VecOP` objects; they do not execute until assigned or passed to a vec API

For the detailed numeric behavior of those vec ops, see [a2_vec_math.md](a2_vec_math.md).

### `tensor[index]`

- Purpose: create a tensor view with updated `offset` and `span`.
- Supported indices:
  - tuple of per-dimension slices for normal 2D slicing
  - single `int` or `Var` as a special shorthand for "shift the last dimension base offset"
- Restrictions:
  - rank must still match the tensor rank
  - slice `step` must be `None` or `1`
- Behavior:
  - returns a new tensor view
  - preserves `source_buf`, `source_index`, transpose state, and NZ flag
  - emits `slice_tensor` in kernel context or `micro_slice_tensor` in micro context

Important special case:

- `tensor[k]` does not reduce rank
- instead, it keeps the same 2D shape and shifts only the last-dimension base offset by `k`

That special form is what makes patterns such as row-block writes work:

```python
dst[block * i] <<= regs[i]
```

Example with ordinary slicing:

```python
tile = ub[row0:row1, col0:col1]
```

## 2. Tensor Storage Helpers

These helpers also manipulate tensor-backed storage, but they are exposed as top-level functions because they either allocate GM workspace or affect the kernel's local allocation state.

### `reinterpret(src, target_dtype, name="")`

- Purpose: build a new `Tensor` view over the same underlying storage, but reinterpret each element with another dtype.
- Parameters:
  - `src`: source `Tensor`
  - `target_dtype`: destination `DataTypeValue`
  - `name`: optional view name
- Restrictions:
  - `src` must be a `Tensor`
  - `target_dtype` must be a `DataTypeValue`
  - `src.position` cannot be `Position.L0C`
  - the reinterpret path assumes a 2D tensor view
- What it changes:
  - the returned tensor keeps the same physical storage, `offset`, `step`, `source_buf`, `source_index`, transpose flag, and NZ flag
  - only the logical dtype and the second dimension of `shape` / `span` are rescaled
- Width-rescale rule:
  - the code uses the dtype packing factor `C0`
  - `dst_cols = src_cols * src.dtype.C0 / target_dtype.C0`
  - the same formula is applied to `span[1]`
  - for symbolic `Var` dimensions, the DSL emits `var_mul` / `var_div` style expressions instead of collapsing to a Python integer
- Why the second dimension changes:
  - local tensors are treated as 2D views whose inner dimension carries packed-lane width
  - reinterpret keeps the total byte span constant, so a wider element type means fewer logical columns and a narrower element type means more logical columns
- Simulator validation:
  - simulator execution recomputes the expected destination span from source bytes
  - if the rescaled view would not preserve byte size exactly, execution fails instead of silently truncating
  - the simulator also checks that the source view is contiguous enough for reinterpret and that user-supplied `dst_shape` metadata matches the expected rescale result
- Codegen lowering:
  - parser lowering maps this to `src.ReinterpretCast<dst_dtype>()`
  - no data movement happens here; later loads/stores read the same bytes through a different element type
- Difference from `cast`:
  - `reinterpret` changes only the view
  - `cast` creates numerically converted values
- Typical use cases:
  - inspect a packed buffer with a narrower scalar type
  - hand the same UB/L1 allocation to another instruction family that expects a different dtype view
  - preserve slot-buffer metadata while changing how later instructions interpret the bytes

Example: `half -> uint8`

```python
ub_fp16 = Tensor(DT.half, [4, 16], Position.UB)
ub_u8 = reinterpret(ub_fp16, DT.uint8, name="ub_u8")
```

Resulting logical view:

- source `C0 = 16`, destination `C0 = 32`
- destination columns become `16 * 16 / 32 = 8`
- `ub_u8` sees the same storage as shape `[4, 8]`

Example: buffer slot metadata is preserved

```python
ub_ring = DBuff(DT.half, [4, 16], Position.UB)
slot = ub_ring[stage]
slot_u8 = slot.reinterpret(DT.uint8)
```

Practical effect:

- `slot_u8.source_buf is ub_ring`
- `slot_u8.source_index is stage`
- autosync and simulator bookkeeping still know which logical slot the view came from

### `split_workspace(dtype, shape, name="")`

- Purpose: carve out one named GM workspace slice from the kernel-owned workspace region and expose it as a `GMTensor`.
- Parameters:
  - `dtype`: workspace element dtype
  - `shape`: workspace tensor shape
  - `name`: optional explicit workspace tensor name
- Restrictions:
  - intended for kernel context
  - `dtype` must be a `DataTypeValue`
  - each `shape` element must be an `int` or `Var`
- High-level model:
  - the kernel has one incoming workspace base pointer
  - each `split_workspace(...)` call consumes a contiguous segment from that base pointer
  - the returned `GMTensor` is just a typed view into that segment
- DSL bookkeeping behavior:
  - the helper computes `numel` as the product of all shape dimensions
  - in kernel context it appends the declared `shape` to `active_kernel.workspace_shapes`
  - it emits a `split_workspace` instruction carrying `dtype`, `numel`, and the chosen tensor name
- Codegen lowering:
  - lowering advances the workspace pointer with `shiftAddr<dtype>(workspace, numel, offset)`
  - then it binds a `GlobalTensor<dtype>` view to the shifted address
  - in other words, the generated code performs pointer slicing, not a GM allocation syscall
- Simulator behavior:
  - simulator allocates or reuses a backing tensor per workspace name
  - if the same workspace name is seen again, dtype, shape, and `numel` must match exactly
  - simulator accepts general workspace shapes and validates the full shape product against `numel`
- When to use it:
  - intermediate GM staging across cube/vec phases
  - scratch output that is too large for on-chip storage
  - kernels that need persistent temporary GM regions in addition to their explicit inputs and outputs
- When not to use it:
  - ordinary inputs/outputs already present in the kernel signature
  - temporary on-chip storage, which should use `Tensor`, `DBuff`, or `TBuff` instead

Example:

```python
workspace_tile = split_workspace(DT.float, [M, N], name="workspace_tile")
workspace_tile <<= ub_partial
```

Conceptual effect:

- if this is the first workspace split in the kernel, `workspace_tile` points at the base workspace address
- the next `split_workspace(...)` call starts immediately after `M * N` float elements

Example: two independent named workspaces

```python
tmp_a = split_workspace(DT.float, [M, N], name="tmp_a")
tmp_b = split_workspace(DT.float, [M, N], name="tmp_b")
```

Practical effect:

- `tmp_a` and `tmp_b` refer to different GM regions
- simulator tracking keeps their payloads separate because the names differ

### `reset_cache()`

- Purpose: reset the kernel's local allocation/cache state before later local tensors are created or reused.
- Parameters:
  - none
- Restrictions:
  - meaningful only in kernel context
- What "cache" means here:
  - this helper does not flush GM or clear tensor payloads
  - it resets the DSL/runtime state that tracks local memory allocation offsets and cached local slice contexts
- DSL behavior:
  - in kernel context it emits a `reset_cache` instruction
- Codegen lowering:
  - parser lowering emits `pipe_ptr->Reset();` and then `OccupyMMTE1Events();`
  - when kernel headers are written, only the auto-inserted prologue pair is preserved but rewritten as `// pipe_ptr->Reset();` and `// OccupyMMTE1Events();`
  - user-authored `reset_cache()` calls still lower to the raw helper calls inside the generated body
  - this makes later local allocations start from a fresh pipeline-managed state
- Simulator behavior:
  - simulator resets its per-position allocation offsets back to zero
  - cached local slice-context records are cleared
  - existing Python tensor objects still exist, but subsequent allocations behave as if local memory placement is starting over
- Why this exists:
  - some kernels want to phase local allocations, finish one stage, then restart placement for a later stage instead of monotonically growing local offsets forever
  - it is especially relevant for long kernels that reuse the same on-chip footprint across disjoint stages
- What it does not do:
  - it does not rewrite GM tensors
  - it does not numerically zero UB/L1/L0 contents in the simulator
  - it does not replace explicit synchronization; it only resets allocation/cache bookkeeping

Example:

```python
stage0_ub = Tensor(DT.float, [64, 64], Position.UB)
# ... stage 0 work ...
reset_cache()
stage1_ub = Tensor(DT.float, [64, 64], Position.UB)
```

Practical meaning:

- after `reset_cache()`, the second `Tensor(...)` can reuse the same local allocation region that stage 0 consumed
- without it, later allocations would continue from the previous running offset

## 3. `GMTensor`

### `GMTensor(dtype, shape, name="")`

- Purpose: represent a GM tensor in a kernel signature, return value, or workspace split.
- Constructor parameters:
  - `dtype`: `DataTypeValue`
  - `shape`: shape made of `int` or `Var`
  - `name`: optional tensor name
- Runtime behavior:
  - unlike `Tensor`, the shape is not restricted to rank `2`
  - constructor emits `create_gm_tensor` in kernel context
- Important stored metadata:
  - `offset`, `span`, `step`: current GM view metadata
  - `slice_mask`: marks which dimensions were created from `slice` syntax
  - `_mutex`: optional bound `CvMutex` or `VcMutex`
  - `data`: simulator/runtime payload attached by `OpExec`

Example:

```python
@kernel()
def my_kernel(x: GMTensor, y: GMTensor, z: GMTensor, M: Var, N: Var, K: Var):
    return z
```

### `bind_cv_mutex(...)`

- Purpose: attach a cube-producer / vec-consumer mutex to this GM tensor.
- Parameters:
  - `flag_id`, `depth`, `src_start_pipe`, `dst_start_pipe`, `src_end_pipe`, `dst_end_pipe`
- Behavior:
  - constructs a `CvMutex`
  - stores it into `self._mutex`
  - returns the mutex object
- Typical use:
  - tie a logical GM output or handoff object to explicit cross-side ownership calls
- Further reading:
  - see [synchronize.md](synchronize.md) for the full `CvMutex` token model and examples

### `bind_vc_mutex(...)`

- Purpose: attach a vec-producer / cube-consumer mutex to this GM tensor.
- Parameters:
  - same conceptual meaning as `bind_cv_mutex`
- Behavior:
  - constructs a `VcMutex`
  - stores it into `self._mutex`
  - returns the mutex object
- Further reading:
  - see [synchronize.md](synchronize.md) for the full `VcMutex` token model and examples

### `lock()`, `ready()`, `wait()`, `free()`

- Purpose: forward synchronization calls to the bound mutex.
- Restrictions:
  - a mutex must already be bound
- Behavior:
  - `lock()`: producer waits for a reusable slot
  - `ready()`: producer publishes a filled slot
  - `wait()`: consumer waits for the producer
  - `free()`: consumer returns the slot

Example:

```python
z.bind_cv_mutex(0)
z.lock()
z.ready()
z.wait()
z.free()
```

### `dst_gm <<= src_tensor`

- Purpose: write a local tensor back to GM.
- Supported routes:
  - `GMTensor <<= UB Tensor` -> `ub_to_gm_pad`
  - `GMTensor <<= L0C Tensor` -> `l0c_to_gm_nz2nd`
- Restrictions:
  - source must be `UB` or `L0C`

Example:

```python
z <<= ub_out
z <<= l0c_out
```

### `gmtensor[index]`

- Purpose: create an N-D GM view.
- Supported per-dimension indices:
  - `int`
  - `Var`
  - `slice`
- Restrictions:
  - index rank must match GM tensor rank
  - at most two dimensions may use `slice`
  - slice `step` must be `None` or `1`
- Behavior:
  - returns a new `GMTensor` view
  - `int` / `Var` dimensions become span-`1` dimensions
  - sliced dimensions are marked in `slice_mask`
  - bound mutex and simulator data payload are preserved on the view
  - emits `slice_gm_tensor`

This is what lets rank-3 or rank-4 GM tensors be lowered into the 2D transfer helpers that default-infer contiguous slices.

Example:

```python
tile = x[b, h, m0:m1, k0:k1]
```

### `gmtensor[index] = value`

- Purpose: slice-assignment convenience for GM destinations.
- Supported values:
  - `Tensor` at `L0C`
  - `GMTensor`
- Behavior:
  - `dst_slice = gm[...]`
  - `dst_slice = l0c_tensor` emits `l0c_to_gm_nz2nd`
  - assignment from another `GMTensor` is accepted as a no-op placeholder for Python syntax compatibility

Example:

```python
z[m0:m1, n0:n1] = l0c_tile
```

## 4. `DBuff`

### `DBuff(dtype, shape, position=Position.L1, name="")`

- Purpose: represent a logical double-buffer family.
- Constructor parameters:
  - same style as `Tensor`
- Restrictions:
  - shape rank must be exactly `2`
  - buffer creation is kernel-side, not micro-side
- Behavior:
  - constructor emits `create_dbuf`
  - the family owns two logical slots

Example:

```python
l1x = DBuff(DT.half, [128, K], Position.L1)
```

### `dbuf[index]`

- Purpose: get a slot view as a normal `Tensor`.
- Parameters:
  - `index`: `int` or `Var`
- Behavior:
  - returns a `Tensor` view with:
    - `source_buf = dbuf`
    - `source_index = index`
  - emits `get_buf`
  - the returned tensor can then be sliced, assigned, loaded, or consumed exactly like any other `Tensor`

Why this metadata matters:

- autosync groups use `source_buf` and `source_index`
- simulator slot-aware paths can recover logical slot identity from the returned view

Example:

```python
l1x[cnt] <<= x[m0:m1, k0:k1]
```

### `dbuf[index] = value`

- Purpose: Python augmented-assignment compatibility hook.
- Parameters:
  - `index`: `int` or `Var`
  - `value`: must be a `Tensor`
- Important behavior:
  - this method only validates types
  - the real instruction emission already happened in the `Tensor` view returned by `dbuf[index]`

This detail matters for understanding why the following works:

```python
dbuf[cnt] <<= src
```

Python evaluates that as:

1. `slot = dbuf.__getitem__(cnt)`
2. `slot.__ilshift__(src)`
3. `dbuf.__setitem__(cnt, slot)`

So the meaningful DSL action happens in step 2.

### Slot identity

- `DBuff` represents a two-slot family
- when simulator code needs a concrete slot number, it resolves the runtime index modulo `2`
- the unmodded index token is still preserved at the DSL level for sync-key grouping

## 5. `TBuff`

### `TBuff(dtype, shape, position=Position.L1, name="")`

- Purpose: represent a logical triple-buffer family.
- Constructor parameters:
  - same style as `Tensor`
- Restrictions:
  - shape rank must be exactly `2`
  - buffer creation is kernel-side, not micro-side
- Behavior:
  - constructor emits `create_tbuf`
  - the family owns three logical slots

Example:

```python
ub_stage = TBuff(DT.float, [64, 64], Position.UB)
```

### `tbuff[index]`

- Purpose: get a slot view as a normal `Tensor`.
- Parameters:
  - `index`: `int` or `Var`
- Behavior:
  - same view mechanics as `DBuff.__getitem__`
  - returned tensor remembers `source_buf = tbuff` and `source_index = index`
  - emits `get_buf`

Example:

```python
tmp = ub_stage[stage]
```

### `tbuff[index] = value`

- Purpose: Python augmented-assignment compatibility hook.
- Parameters:
  - `index`: `int` or `Var`
  - `value`: must be a `Tensor`
- Behavior:
  - same as `DBuff.__setitem__`: validation only, no new instruction emission

### Slot identity

- `TBuff` represents a three-slot family
- when simulator code needs a concrete slot number, it resolves the runtime index modulo `3`
- the original index token is still kept for DSL-level sync grouping

## 6. Practical Usage Notes

- Use `Tensor` for concrete on-chip storage and local views.
- Use `GMTensor` for kernel inputs, outputs, and workspace views that live in GM.
- Use `DBuff` when a producer/consumer pair alternates between two slots.
- Use `TBuff` when the schedule needs a three-slot rotation instead of a two-slot one.
- Prefer `buf[idx] <<= ...` over manually creating per-slot tensors; the buffer-family metadata is important for autosync grouping and simulator bookkeeping.
- Remember that `Tensor` and `GMTensor` slicing mostly preserves rank by storing `offset` and `span`, rather than by creating a physically smaller standalone object.
