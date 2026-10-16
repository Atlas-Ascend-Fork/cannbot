# Register and Mask Types

This page documents the A5 micro-side register objects:

- `Reg`
- `RegList`
- `MaskReg`
- `MaskType`
- `MaskTypeValue`

These types are defined mainly in `easyasc/utils/reg.py` and `easyasc/utils/mask.py`. They are A5 micro authoring objects and are most useful inside `@vf` code.

Important distinction:

- many `Reg` / `RegList` / `MaskReg` methods return `RegOP` builders
- some methods emit instructions immediately
- some operators look like normal Python arithmetic, but actually build micro IR

For the detailed numeric behavior of the underlying micro ops, see:

- [a5_micro_math.md](a5_micro_math.md)
- [a5_micro_data_movement.md](a5_micro_data_movement.md)
- [a5_micro_cast.md](a5_micro_cast.md)
- [a5_micro_compare_select.md](a5_micro_compare_select.md)
- [a5_micro_mask_operations.md](a5_micro_mask_operations.md)

## 1. `Reg`

### `Reg(dtype, name="")`

- Purpose: represent one A5 micro register.
- Constructor parameters:
  - `dtype`: register dtype
  - `name`: optional explicit register name
- Restrictions:
  - `dtype` must be `DataTypeValue`
  - if `name=""`, an active `@vf` context is required so the runtime can auto-generate `_reg_*`
- Behavior:
  - stores `dtype` and `name`
  - emits `create_reg` when created inside an active micro module

Example:

```python
r0 = Reg(DT.float)
r1 = Reg(DT.float)
```

### `__repr__()` and `__str__()`

- `repr(reg)` shows both name and dtype.
- `str(reg)` returns just the register name.
- Practical use:
  - mostly for debug output and generated-expression readability

### Arithmetic operators

These operators do not execute immediately. They return `RegOP` builders.

#### `a + b`

- If `b` is `Reg`, returns `RegOP("add", a, b)`.
- If `b` is `int`, `float`, or `Var`, returns `RegOP("adds", a, b)`.
- If `b` is another `RegOP`, it is first materialized to a temporary register.

#### `a - b`

- `Reg - Reg` -> `RegOP("sub", a, b)`
- `Reg - scalar` -> `RegOP("adds", a, -scalar)`
- `scalar - Reg` is only supported when the scalar side is already a `Reg` or `RegOP`

#### `a * b`

- `Reg * Reg` -> `RegOP("mul", a, b)`
- `Reg * scalar` -> `RegOP("muls", a, scalar)`

#### `a / b`

- `Reg / Reg` -> `RegOP("div", a, b)`
- `Reg / scalar` -> `RegOP("muls", a, 1 / scalar)`
- this means scalar division is expressed as multiply-by-reciprocal at the builder level

### Comparison operators

These also return `RegOP`, not Python `bool`.

- `a >= b` -> `RegOP("compare", a, b, CompareMode.GE)`
- `a > b` -> `CompareMode.GT`
- `a <= b` -> `CompareMode.LE`
- `a < b` -> `CompareMode.LT`
- `a == b` -> `CompareMode.EQ`
- `a != b` -> `CompareMode.NE`

Practical meaning:

- comparison results must be assigned into a `MaskReg`
- for example: `mask <<= (r0 > r1)`

### `reg <<= other`

`Reg.__ilshift__` is the main imperative assignment path.

#### `Reg <<= RegOP`

- Purpose: execute a register-expression into this register.
- Behavior:
  - releases temporary inputs first
  - emits the underlying op into `self`

Example:

```python
r2 <<= r0 + r1
```

#### `Reg <<= Tensor`

- Purpose: load UB data into a register.
- Restrictions:
  - intended for micro-side UB loads
- Behavior:
  - checks `other.vec_copy_mode`
  - same-dtype routes:
    - default -> `ub_to_reg`
    - `brcb()` -> `ub_to_reg_brcb`
    - `upsample()` -> `ub_to_reg_upsample`
    - `unpack()` -> `ub_to_reg_unpack`
    - `unpack4()` -> `ub_to_reg_unpack4`
    - `downsample()` -> `ub_to_reg_downsample`
    - `single()` -> `ub_to_reg_single`
  - cross-dtype routes:
    - runtime allocates a temporary register in the tensor dtype
    - loads into that temporary using the appropriate data-movement path
    - emits `cast(self, tmp_reg)`
    - releases the temporary
- Important restriction:
  - mixed dtype tensor-to-reg assignment requires active micro context

Example:

```python
r0 <<= ub
scalar_reg <<= ub[0:1, col:col + 1].single()
```

#### `Reg <<= Reg`

- Purpose: copy one register into another.
- Behavior:
  - emits `vcopy(self, other)`

#### `Reg <<= scalar_or_var`

- Purpose: broadcast a scalar into the destination register.
- Accepted sources:
  - `int`
  - `float`
  - `Var`
- Behavior:
  - emits `dup(self, value)`

Example:

```python
r0 <<= 0.0
r1 <<= count_var
```

### Cast helpers

#### `cast(cfg=None)`

- Purpose: create a cast builder using the register's current dtype as source and leaving destination dtype to the eventual assignment target.
- Returns:
  - `RegOP("cast", self, cfg)`
- If `cfg is None`, a default `CastConfig()` is created.

#### `astype(dtype, cfg=None)`

- Purpose: create a cast builder with explicit destination dtype.
- Returns:
  - `RegOP("cast", self, cfg, dtype)`

Practical difference:

- `.cast()` is usually used when the destination register is already known
- `.astype(dtype)` is more explicit when the cast target dtype is part of the expression

For detailed lane-layout and saturation semantics, see [a5_micro_cast.md](a5_micro_cast.md).

### Unary math builders

These return `RegOP` builders:

- `exp()`
- `abs()`
- `sqrt()`
- `relu()`
- `ln()`
- `log()`
- `log2()`
- `log10()`
- `neg()`
- `vnot()`
- `vcopy()`

Example:

```python
r1 <<= r0.abs()
r2 <<= r0.log()
```

### Unary-scalar builders

These return `RegOP` builders:

- `shiftls(value)`
- `shiftrs(value)`
- `axpy(value)`
- `lrelu(value)`
- `vmins(value)`
- `vmaxs(value)`

Restrictions:

- `shiftls` / `shiftrs` conceptually expect integer block/shift counts
- the others accept `int`, `float`, or `Var`

### Binary register builders

These return `RegOP` builders:

- `vand(other)`
- `vor(other)`
- `vxor(other)`
- `prelu(other)`
- `vmax(other)`
- `vmin(other)`

### Reduction / group builders

These return `RegOP` builders whose result is another `Reg`:

- `cadd()`
- `cmax()`
- `cmin()`
- `cgadd()`
- `cgmax()`
- `cgmin()`
- `cpadd()`

For the exact lane-reduction semantics, see [a5_micro_math.md](a5_micro_math.md).

### Duplication and sequence helpers

#### `dup()`

- Returns:
  - `RegOP("dup", self)`
- Practical meaning:
  - this is the builder form that broadcasts `self[0]` when materialized into another register

Example:

```python
r1 <<= r0.dup()
```

#### `fill(value)`

- Purpose: immediate scalar fill into this register.
- Behavior:
  - directly emits `dup(self, value)`
- Difference from `dup()`:
  - `fill()` is imperative and mutates `self`
  - `dup()` is expression-building and uses an existing register as source

Example:

```python
r0.fill(0.0)
```

#### `arange(start, increase=True)`

- Purpose: fill the register with an arithmetic lane sequence.
- Parameters:
  - `start`: `int`, `float`, or `Var`
  - `increase`: whether the sequence increases or decreases by one lane step
- Behavior:
  - emits `arange(self, start, increase=...)` immediately
- This is an imperative method, not a builder.

Example:

```python
idx.arange(0)
```

### UB-store convenience builders

These methods return `RegOP` objects that are intended to be consumed by `Tensor <<= ...`:

- `downsample()` -> `RegOP("reg_to_ub_downsample", self)`
- `pack4()` -> `RegOP("reg_to_ub_pack4", self)`
- `single_value()` -> `RegOP("reg_to_ub_single", self)`

Typical use:

```python
ub <<= reg.pack4()
```

### Gather helpers

These methods are imperative. They emit into `self` directly and return `None`.

#### `ub_gather(src, index, mask=None)`

- Purpose: gather from a UB tensor using per-lane indices.
- Behavior:
  - calls `ub_to_reg_gather(self, src, index, mask=mask)`

#### `gather(src, index)`

- Purpose: gather from another register using per-lane indices.
- Behavior:
  - calls `gather(self, src, index)`

#### `gather_mask(src, mask=None)`

- Purpose: compress or gather active lanes from a source register under a mask.
- Behavior:
  - calls `gather_mask(self, src, mask=mask)`

The exact data-selection rules for these gather helpers are documented in [a5_micro_data_movement.md](a5_micro_data_movement.md).

## 2. `RegList`

### `RegList(dtype, length, name="")`

- Purpose: represent a fixed-length logical list of micro registers.
- Constructor parameters:
  - `dtype`: register dtype
  - `length`: number of logical elements
  - `name`: optional base name
- Restrictions:
  - `length` must be a positive `int`
  - if `name=""`, active micro context is required so the runtime can auto-generate `_reglist_*`
- Behavior:
  - emits `create_reglist` in active micro context

Example:

```python
rows = RegList(DT.float, 2)
```

### `__repr__()` and `__str__()`

- `repr(reglist)` shows base name, dtype, and logical length.
- `str(reglist)` returns only the base name.

### `reglist[i]`

- Restrictions:
  - index must be `int`
- Behavior:
  - returns a proxy `Reg`
  - proxy name is formatted as `"{reglist.name}[{i}]"`
  - no container lookup or storage object is created
- Important consequence:
  - `RegList` behaves more like a naming convention over several registers than a Python list storing child objects

Example:

```python
r0 = rows[0]
```

### `reglist[i] = value`

- Purpose: satisfy Python augmented-assignment protocol.
- Behavior:
  - intentionally does nothing
- Why:
  - `reglist[i] <<= ...` already emitted the meaningful instruction on the proxy register
  - Python still calls `__setitem__` after augmented assignment, so this hook must exist

### `reglist <<= tensor`

- Purpose: load a whole row-style register list from UB.
- Restrictions:
  - source must be `Tensor`
- Behavior:
  - block size is `256 // dtype.size`
  - for each logical register `i`, the runtime loads from `tensor[block * i]`
  - each element load is delegated to the proxy register assignment path

Example:

```python
rows <<= ub
```

### `reglist <<= regop`

- Purpose: execute an elementwise or reduction-style builder into the whole register list.
- Supported `RegOP` families:
  - binary: `add`, `sub`, `mul`, `div`, `vmax`, `vmin`, `vand`, `vor`, `vxor`, `prelu`
  - unary: `exp`, `abs`, `sqrt`, `relu`, `ln`, `log`, `log2`, `log10`, `neg`, `vnot`, `vcopy`
  - unary-scalar: `shiftls`, `shiftrs`, `axpy`, `lrelu`, `vmaxs`, `vmins`, `adds`, `muls`
- Behavior:
  - if the source inside the `RegOP` is another `RegList`, lengths must match
  - masks attached to the source `RegOP` are copied onto each per-element op
  - elementwise execution is expanded into proxy-register assignments one element at a time
- Unsupported ops:
  - any `RegOP` outside the supported families raises

### Binary expression builders

These return `RegOP` builders:

- `__add__(other)`
- `__sub__(other)`
- `__mul__(other)`
- `__truediv__(other)`
- `vmax(other)`
- `vmin(other)`
- `vand(other)`
- `vor(other)`
- `vxor(other)`
- `prelu(other)`

Supported `other` forms when materialized into a destination `RegList`:

- another `RegList` of the same length
- a single `Reg`
- a scalar for the basic arithmetic ops only

### Unary expression builders

These return `RegOP` builders:

- `exp()`
- `abs()`
- `sqrt()`
- `relu()`
- `ln()`
- `log()`
- `log2()`
- `log10()`
- `neg()`
- `vnot()`
- `vcopy()`
- `shiftls(value)`
- `shiftrs(value)`
- `axpy(value)`
- `lrelu(value)`
- `vmaxs(value)`
- `vmins(value)`

### Reduction builders

These return `RegOP` objects that reduce a whole `RegList` to a single `Reg`:

- `cmax()`
- `cmin()`
- `cadd()`

When such a `RegOP` is materialized into a `Reg`, current runtime behavior is:

- combine elements pairwise across the list
- then apply the final single-register group reduction

### `fill(value)`

- Purpose: fill every logical register element with the same scalar.
- Behavior:
  - loops over all indices
  - emits `self[i] <<= value` for each proxy register
- This is imperative, not a builder.

Example:

```python
rows.fill(0.0)
```

## 3. `MaskReg`

### `MaskReg(dtype, init_mode=None, name="")`

- Purpose: represent a micro mask register.
- Constructor parameters:
  - `dtype`: data dtype whose lane geometry this mask follows
  - `init_mode`: optional `MaskTypeValue`
  - `name`: optional explicit mask-register name
- Default behavior:
  - if `init_mode is None`, it becomes `MaskType.ALL`
- Restrictions:
  - `dtype` must be `DataTypeValue`
  - `init_mode` must be `MaskTypeValue`
  - if `name=""`, active micro context is required for auto-generated `_maskreg_*`
- Behavior:
  - emits `create_maskreg` in active micro context

Example:

```python
mask = MaskReg(DT.half)
mask_none = MaskReg(DT.half, init_mode=MaskType.NONE)
```

### `__repr__()` and `__str__()`

- `repr(mask)` shows name, dtype, and initial mask mode.
- `str(mask)` returns just the mask-register name.

### `mask * regop`

- Purpose: attach a mask to a `RegOP`.
- Restrictions:
  - right-hand side must be `RegOP`
- Behavior:
  - calls `regop.setmask(mask)`
  - returns the same `RegOP`
- Practical meaning:
  - this is a convenient syntax for masked expression building

Example:

```python
r2 <<= mask * (r0 + r1)
```

### `mask <<= other`

`MaskReg.__ilshift__` supports two source categories.

#### `mask <<= Var`

- Purpose: update the mask bits from a counter-like scalar.
- Restrictions:
  - source must be `Var`
- Behavior:
  - emits `update_mask(mask, cnt)`

#### `mask <<= RegOP`

- Purpose: execute a mask-producing `RegOP` into this mask register.
- Behavior:
  - releases temporary inputs
  - emits the underlying op into `self`

Example:

```python
mask <<= (r0 > r1)
mask <<= ~other_mask
```

### Bitwise mask builders

These return `RegOP` builders:

- `~mask` -> `mask_not`
- `mask0 & mask1` -> `mask_and`
- `mask0 | mask1` -> `mask_or`
- `mask0 ^ mask1` -> `mask_xor`

### `mov(src)`

- Purpose: build a mask copy op.
- Returns:
  - `RegOP("mask_mov", src)`

### `sel(src1, src2)`

- Purpose: build a mask-to-mask select op.
- Returns:
  - `RegOP("mask_sel", src1, src2)`
- Meaning:
  - chooses between two mask registers under the execution mask attached to the `RegOP`

### `pack(low_part=True)`

- Purpose: build a mask pack op.
- Returns:
  - `RegOP("mask_pack", self, low_part)`

### `unpack(low_part=True)`

- Purpose: build a mask unpack op.
- Returns:
  - `RegOP("mask_unpack", self, low_part)`

### `move_to_spr()`

- Purpose: build a move-to-mask-SPR op.
- Returns:
  - `RegOP("move_mask_spr")`
- Note:
  - this is the builder form
  - many kernels use the direct helper `move_mask_spr(mask)` instead

### `update(cnt)`

- Purpose: update the current mask from a counter `Var`.
- Behavior:
  - emits `update_mask(self, cnt)` directly
- This is imperative, unlike `pack()` / `unpack()`.

### `select(src1, src2)`

- Purpose: build a masked data-register select using this mask register.
- Parameters:
  - `src1`, `src2`: `Reg`
- Behavior:
  - creates `RegOP("select", src1, src2)`
  - attaches `self` as the execution mask
  - returns the resulting `RegOP`
- Important distinction:
  - `sel()` is mask-to-mask selection
  - `select()` is data-register selection under this mask

Example:

```python
r_out <<= mask.select(r_true, r_false)
```

## 4. `MaskTypeValue`

### `MaskTypeValue(name)`

- Purpose: represent one concrete predefined mask mode.
- Typical usage:
  - you usually do not construct it directly
  - instead, use values from the `MaskType` namespace

### `__repr__()` and `__str__()`

- `repr(value)` returns `MaskTypeValue('...')`
- `str(value)` returns the raw mode name such as `ALL`, `VL8`, or `M3`

### Equality

- comparing the same object returns `True`
- comparing two `MaskTypeValue` objects compares their `.name`
- comparing with any non-`MaskTypeValue` object raises `TypeError`

Practical meaning:

- `MaskTypeValue` behaves more like a strict enum token than a plain string

## 5. `MaskType`

`MaskType` is the enum-like namespace that exposes reusable `MaskTypeValue` presets.

These presets control the initial lane bits of a new `MaskReg`. Current simulator behavior is:

- `MaskType.ALL`
  - all lanes active
- `MaskType.NONE`
  - no lanes active
- `MaskType.LOWEST1`
  - lowest 1 lane active
- `MaskType.LOWEST2`
  - lowest 2 lanes active
- `MaskType.LOWEST3`
  - lowest 3 lanes active
- `MaskType.LOWEST4`
  - lowest 4 lanes active
- `MaskType.LOWEST8`
  - lowest 8 lanes active
- `MaskType.LOWEST16`
  - lowest 16 lanes active
- `MaskType.LOWEST32`
  - lowest 32 lanes active
- `MaskType.LOWEST128`
  - lowest 128 lanes active, clamped by the lane count of the dtype
- `MaskType.LOWHALF`
  - lowest half of lanes active
- `MaskType.LOWQUAT`
  - lowest quarter of lanes active
- `MaskType.MULTI3`
  - every third lane active: `0, 3, 6, ...`
- `MaskType.MULTI4`
  - every fourth lane active: `0, 4, 8, ...`

Example:

```python
mask = MaskReg(DT.half, init_mode=MaskType.LOWEST8)
```

## 6. Practical Usage Notes

- Use `Reg` when you need one vector-width micro register.
- Use `RegList` when your algorithm is naturally row-block based and expands cleanly into several equal-width registers.
- Use `MaskReg` both as a stored boolean-lane state object and as an execution mask attached to `RegOP`.
- Prefer the builder forms when composing expressions:
  - `r2 <<= r0.abs()`
  - `r2 <<= mask * (r0 + r1)`
- Prefer the imperative forms when you are explicitly loading, storing, or mutating state:
  - `r0 <<= ub`
  - `rows.fill(0.0)`
  - `mask.update(cnt)`
- Remember that `RegList[i]` is a proxy register view, not a Python container element with separate storage.
