# A5 Micro Cast

This page documents the micro-side cast helpers exported by `easyasc.a5`.

The behavior described here is based on:

- the public authoring surface in `easyasc/stub_functions/micro/cast.py`
- the `Reg` convenience methods in `easyasc/utils/reg.py`
- the current V2 simulator implementation in `easyasc/simulator_v2/ops/micro/runtime.py`
- the current V2 micro tests under `testcases/simulator/micro/`

All cast APIs on this page:

- require an active `@vf` context
- operate on `Reg` and `MaskReg`
- use zeroing semantics for masked-off or unfilled destination lanes

## 1. Cast Building Blocks

### `RoundModeType`

- Purpose: represent one concrete micro cast rounding mode value.
- Typical use:
  - you normally do not construct it directly
  - instead, pass predefined values from `RoundMode.*`

The class is small, but it matters because `CastConfig` validates that `round_mode` is a `RoundModeType`.

Important behaviors:

- `str(mode)` returns the backend token name such as `CAST_RINT`
- `repr(mode)` returns `RoundModeType('...')`
- equality compares by mode name
- comparing against a non-`RoundModeType` raises `TypeError`

Examples:

```python
str(RoundMode.TO_EVEN)        # "CAST_RINT"
repr(RoundMode.FLOOR)         # "RoundModeType('CAST_FLOOR')"
RoundMode.CEIL == RoundMode.CEIL
```

Practical rule:

- use the predefined `RoundMode.*` members
- do not pass raw strings such as `"CAST_RINT"` into `CastConfig`

### `RoundMode`

- Purpose: enum-like namespace for the predefined micro cast rounding modes.
- Value type:
  - every member is a `RoundModeType`

Available members:

| Public name | Backend token | Intended meaning |
| --- | --- | --- |
| `RoundMode.NONE` | `CAST_NONE` | no explicit rounding policy |
| `RoundMode.TO_EVEN` | `CAST_RINT` | round to nearest, ties to even |
| `RoundMode.AWAY_FROM_ZERO` | `CAST_ROUND` | round away from zero |
| `RoundMode.FLOOR` | `CAST_FLOOR` | round toward negative infinity |
| `RoundMode.CEIL` | `CAST_CEIL` | round toward positive infinity |
| `RoundMode.TRUNC` | `CAST_TRUNC` | round toward zero by truncation |

What "intended meaning" means here:

- these are the semantic modes the backend C++ trait is told to use
- they matter most when the cast can discard precision or fractional information
- common examples are `float -> half`, `float -> int8`, `float -> e4m3`, and `float -> e5m2`

When round mode usually has little or no observable effect:

- same-width casts such as `half -> half`
- exact-value casts where the source value is already representable in the destination
- the current Python simulator, because it does not model each round mode separately

Current simulator behavior:

- the simulator preserves the selected `RoundMode` object in `CastConfig`
- the simulator does not currently branch on `TO_EVEN` vs `FLOOR` vs `TRUNC`, and so on
- numeric conversion currently relies mainly on `torch.Tensor.to(dtype)` plus the framework's saturation logic

Current codegen behavior:

- the selected mode is emitted into the generated trait as `RoundMode::{token}`
- for example, `RoundMode.TO_EVEN` becomes `RoundMode::CAST_RINT`

Example:

```python
cfg_floor = CastConfig(
    round_mode=RoundMode.FLOOR,
    reg_layout=RegLayout.ZERO,
    name="cfg_floor",
)
```

Another example:

```python
cfg_trunc = CastConfig(
    round_mode=RoundMode.TRUNC,
    reg_layout=RegLayout.ZERO,
    name="cfg_trunc",
)
```

### `CastConfig(round_mode=RoundMode.TO_EVEN, reg_layout=RegLayout.ZERO, saturate=False, name="")`

- Purpose: Stores the policy that a micro cast should use.
- Constructor parameters:
  - `round_mode`: the requested `RoundMode`
  - `reg_layout`: which logical slot to read from or write to when source and destination element widths differ
  - `saturate`: whether overflow handling should clamp instead of using the default dtype-conversion behavior
  - `name`: the symbolic name emitted into generated C++

What each parameter means:

- `round_mode`:
  - must be a `RoundModeType`
  - selects which `RoundMode.*` policy is attached to the generated cast trait
  - carried into code generation as part of the `MicroAPI::CastTrait`
  - current simulator note:
    - the simulator does not model each round mode separately
    - it currently relies on `torch.Tensor.to(dtype)` conversion behavior
- `reg_layout`:
  - only matters when `src.dtype.size != dst.dtype.size`
  - chooses which slot inside each cast ratio group is used
- `saturate`:
  - when `False`, simulator behavior follows `torch` dtype conversion
  - when `True`, the simulator clamps values before converting
- `name`:
  - must be non-empty by the time `cast()` emits the instruction
  - if you construct `CastConfig` inside an active micro, the object is registered into that micro and its name is prefixed automatically

Auto-registration behavior:

- When `CastConfig` is created inside an active `@vf`, it is appended to the micro module's `cast_cfg_list`.
- During code generation, that list becomes `MicroAPI::CastTrait` definitions in the generated C++.
- This is why config names need to be stable and unique.

Example:

```python
cfg_zero = CastConfig(
    round_mode=RoundMode.TO_EVEN,
    reg_layout=RegLayout.ZERO,
    saturate=False,
    name="cfg_zero",
)
```

Default-config behavior:

- `cast(..., config=None)` asks the current micro module for a default config.
- In the current implementation, most destinations use a default `RoundMode.TO_EVEN` config.
- `Datatype.hif8` is the current special case that defaults to `RoundMode.AWAY_FROM_ZERO`.

Why `Datatype.hif8` is mentioned here:

- the micro module maintains two cached default configs
- the general default is `RoundMode.TO_EVEN`
- the `hif8` default is a separate cached config created with `RoundMode.AWAY_FROM_ZERO`
- this affects what `cast(..., config=None)` means for those destinations

### `RegLayout`

- Purpose: Describes which slot inside a width-conversion group is active.
- Available values:
  - `RegLayout.ZERO`
  - `RegLayout.ONE`
  - `RegLayout.TWO`
  - `RegLayout.THREE`

Why `RegLayout` exists:

- Micro registers always have a fixed byte budget.
- When source and destination element sizes differ, one source lane does not map to exactly one destination lane.
- The cast therefore works with ratio-sized groups.
- `RegLayout` chooses which slot in each group is read or written.

Current legal slot rules:

| Cast ratio | Meaning | Legal layouts |
| --- | --- | --- |
| `1` | same-width cast | all layouts are currently accepted, but the layout is ignored |
| `2` | 16-bit <-> 32-bit or 8-bit <-> 16-bit | `ZERO`, `ONE` |
| `4` | 8-bit <-> 32-bit | `ZERO`, `ONE`, `TWO`, `THREE` |

If the layout slot is out of range for the active width ratio, the simulator raises an error.

Example:

```python
cfg_one = CastConfig(reg_layout=RegLayout.ONE, name="cfg_one")
```

## 2. Core API

### `cast(dst, src, config=None, mask=None)`

- Purpose: Cast one register into another register.
- Parameters:
  - `dst`: destination `Reg`
  - `src`: source `Reg`
  - `config`: optional `CastConfig`
  - `mask`: optional `MaskReg`

General behavior:

- `dst` is always zero-initialized first.
- The source register is snapshotted first, so aliasing like `cast(reg, reg, cfg, mask)` behaves predictably.
- The destination mask is resolved using `dst.dtype`.
- Masked-off lanes remain zero.

Current simulator-supported dtypes:

- `half`
- `float`
- `bfloat16`
- `int8`
- `uint8`
- `int32`
- `float8_e4m3_t`
- `float8_e5m2_t`

Current simulator caveats:

- `round_mode` is preserved in `CastConfig` and emitted to codegen, but it is not separately simulated yet.
- Unsupported dtype pairs can still be accepted by the stub layer and then fail in the simulator.

### 2.1 Same-Width Casts

This is the case where:

- `src.dtype.size == dst.dtype.size`

Addressing rule:

- for each active lane `i`:
  - `dst[i] = cast(src[i])`

Notes:

- `reg_layout` does not change the address mapping in this case
- all `RegLayout` values are currently accepted for same-width casts because no slot lookup is needed
- masked-off lanes stay zero

Example:

```text
src  = [a0, a1, a2, a3, a4, a5, ...]
mask = active at lanes [0..7]
dst  = [cast(a0), cast(a1), ..., cast(a7), 0, 0, ...]
```

This matches the simulator test where a same-width `half -> half` cast with `RegLayout.THREE`
still copies the active lanes 1:1 and zeroes the rest.

### 2.2 Narrow-to-Wide Casts

This is the case where:

- `src.dtype.size < dst.dtype.size`

Let:

- `ratio = dst.dtype.size / src.dtype.size`
- `slot = reg_layout`

Addressing rule:

- for each active destination lane `i`:
  - `src_index = i * ratio + slot`
  - `dst[i] = cast(src[src_index])`

Interpretation:

- every wide destination lane picks one element from a ratio-sized group in the source register
- `RegLayout.ZERO` picks the first element of each group
- `RegLayout.ONE` picks the second element, and so on

Example: `half -> float` (`ratio = 2`)

```text
src = [h0, h1, h2, h3, h4, h5, ...]

RegLayout.ZERO:
dst = [float(h0), float(h2), float(h4), ...]

RegLayout.ONE:
dst = [float(h1), float(h3), float(h5), ...]
```

Example: `int8 -> float` (`ratio = 4`)

```text
src group 0 = [b0, b1, b2, b3]
src group 1 = [b4, b5, b6, b7]

RegLayout.ZERO -> [float(b0), float(b4), ...]
RegLayout.ONE  -> [float(b1), float(b5), ...]
RegLayout.TWO  -> [float(b2), float(b6), ...]
RegLayout.THREE-> [float(b3), float(b7), ...]
```

### 2.3 Wide-to-Narrow Casts

This is the case where:

- `src.dtype.size > dst.dtype.size`

Let:

- `ratio = src.dtype.size / dst.dtype.size`
- `slot = reg_layout`

Addressing rule:

- the source lane index is `src_index = dst_index // ratio`
- only destination lanes whose `dst_index % ratio == slot` are written
- all other destination lanes stay zero

Interpretation:

- one wide source lane fans out over a ratio-sized destination group
- `RegLayout` selects which slot in that destination group receives the converted value

Example: `float -> half` (`ratio = 2`)

```text
src = [f0, f1, f2, f3, ...]

RegLayout.ZERO:
dst = [half(f0), 0, half(f1), 0, half(f2), 0, ...]

RegLayout.ONE:
dst = [0, half(f0), 0, half(f1), 0, half(f2), ...]
```

Example: `float -> int8` (`ratio = 4`)

```text
RegLayout.ZERO:
dst[0], dst[4], dst[8], ... = cast(src[0]), cast(src[1]), cast(src[2]), ...
all other lanes remain 0
```

This is exactly why a `float -> fp8` or `float -> int8` cast is commonly followed by `pack4()`:
the cast populates only one slot out of every 4 lanes, and `pack4()` compacts those lanes for UB storage.

### 2.4 Saturation Behavior

When `config.saturate == False`:

- the simulator uses `torch.Tensor.to(dst_dtype)` semantics
- overflow, NaN, and rounding therefore follow `torch`, not a custom hardware model

When `config.saturate == True`:

- for floating-point destinations:
  - finite values are clamped to the dtype's finite range
  - `inf`, `-inf`, and `nan` are left to the final float cast behavior
- for integer destinations:
  - finite values are clamped to the integer range
  - `+inf` becomes the integer max
  - `-inf` becomes the integer min
  - `nan` becomes `0`

Example: saturating `float -> int8`

```text
src = [-300.0, -129.0, -128.0, 127.0, 128.0, inf, -inf, nan]

after saturation:
[-128, -128, -128, 127, 127, 127, -128, 0]
```

### 2.5 Mask Behavior

For `cast()`:

- the mask is resolved on destination lanes
- there is no `C0` expansion
- unselected destination lanes remain zero

Example:

```text
mask = VL8
dst[0:8]   = converted values
dst[8:...] = 0
```

### 2.6 Direct Examples

Float to half, two layouts:

```python
src_reg = Reg(DT.float)
dst_zero = Reg(DT.half)
dst_one = Reg(DT.half)
mask = MaskReg(DT.half)

cfg_zero = CastConfig(reg_layout=RegLayout.ZERO, name="cfg_zero")
cfg_one = CastConfig(reg_layout=RegLayout.ONE, name="cfg_one")

cast(dst_zero, src_reg, cfg_zero, mask)
cast(dst_one, src_reg, cfg_one, mask)
```

Half to float:

```python
src_reg = Reg(DT.half)
dst_reg = Reg(DT.float)
cfg = CastConfig(reg_layout=RegLayout.ZERO, name="cfg_zero")
cast(dst_reg, src_reg, cfg)
```

Float to fp8 with packed UB writeback:

```python
src_reg = Reg(DT.float)
dst_fp8 = Reg(DT.e5m2)
cfg = CastConfig(reg_layout=RegLayout.ZERO, name="cfg_zero")

cast(dst_fp8, src_reg, cfg)
dst_ub <<= dst_fp8.pack4()
```

Restrictions:

- `dst` and `src` must both be `Reg`
- `config` must be a `CastConfig` after default resolution
- `mask` must be a `MaskReg`
- the chosen `RegLayout` must be valid for the width ratio
- the current simulator only supports the dtype set listed above

## 3. `Reg` Convenience Methods

### `Reg.cast(cfg=None)`

- Purpose: Build a cast `RegOP` using the same logical dtype as the source register.
- Common use:
  - apply a cast config explicitly while keeping the register dtype unchanged
  - build a cast node that will be emitted later by assignment

Important detail:

- `Reg.cast()` does not specify a new output dtype
- the resulting `RegOP` therefore keeps the source dtype
- if you want a concrete new dtype, prefer `Reg.astype(...)`

Example:

```python
src = Reg(DT.half)
dst = Reg(DT.half)
cfg = CastConfig(reg_layout=RegLayout.ZERO, name="cfg")
dst <<= src.cast(cfg)
```

### `Reg.astype(dtype, cfg=None)`

- Purpose: Build a cast `RegOP` with an explicit output dtype.
- Parameters:
  - `dtype`: target `DT.*` value
  - `cfg`: optional `CastConfig`

This is the most useful convenience form when writing micro code because it captures both:

- the target dtype
- the cast policy

Example:

```python
r_h = Reg(DT.half)
r_f = Reg(DT.float)
cfg = CastConfig(reg_layout=RegLayout.ZERO, name="cfg_zero")

r_f <<= r_h.astype(DT.float, cfg)
```

### `Reg.pack4()`

- Purpose: Build a `RegOP` that stores the register with `StoreDist.PACK4`.
- Why it appears in cast code:
  - after a wide-to-narrow cast with ratio `4`, only one lane out of every 4 contains a real value
  - `pack4()` compacts lanes `0, 4, 8, ...` into a contiguous UB output stream

Typical fp8 workflow:

1. cast `float -> e5m2` or `float -> e4m3` with `RegLayout.ZERO`
2. the cast writes converted values into register lanes `0, 4, 8, ...`
3. `pack4()` compacts those lanes when writing to UB

Example:

```python
src = Reg(DT.float)
dst = Reg(DT.e5m2)
cfg = CastConfig(reg_layout=RegLayout.ZERO, name="cfg_zero")

cast(dst, src, cfg)
packed_ub <<= dst.pack4()
```

For the exact `PACK4` store semantics, see [a5_micro_data_movement.md](a5_micro_data_movement.md).

## 4. Common Mental Model

When debugging a cast, use this checklist:

1. compare `src.dtype.size` and `dst.dtype.size`
2. compute the width ratio
3. check whether the chosen `RegLayout` is legal for that ratio
4. decide whether the cast is:
   - selecting one lane from each source group (`narrow -> wide`)
   - or filling one slot in each destination group (`wide -> narrow`)
5. remember that masked-off and unfilled destination lanes become zero
6. if overflow matters, check whether `saturate=True` is required
7. if simulator rounding matters, remember that current simulator behavior follows `torch`, not a dedicated round-mode implementation
