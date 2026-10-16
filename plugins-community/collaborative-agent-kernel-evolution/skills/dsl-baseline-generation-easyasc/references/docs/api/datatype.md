# Datatypes

This page documents the dtype objects used throughout `easyasc`.

Three names matter here:

- `DT`: the dtype namespace that kernel authors normally use
- `Datatype`: the underlying class behind `DT`
- `DataTypeValue`: the concrete dtype object stored on `Tensor`, `GMTensor`, `Reg`, `MaskReg`, and many helper APIs

In normal kernel code, you almost always write `DT.float`, `DT.half`, `DT.int`, and so on.

## 1. Overview

All user-facing dtype parameters ultimately expect a `DataTypeValue`.

Typical examples:

```python
ub = Tensor(DT.float, [M, N], Position.UB)
reg = Reg(DT.half)
count = Var(0, DT.int)
dst = reinterpret(src, DT.uint8)
```

Why this matters:

- tensor constructors validate `dtype` as `DataTypeValue`
- register constructors validate `dtype` as `DataTypeValue`
- scalar `Var` objects often infer or store `DT.int` / `DT.float`
- cast and reinterpret helpers use dtype objects, not strings

## 2. `DT`

### What it is

- `DT` is the public dtype namespace exported by `easyasc.a2` and `easyasc.a5`
- in the current implementation, `DT` is an alias of the `Datatype` class

So these refer to the same singleton dtype objects:

```python
from easyasc.a5 import DT
# internal equivalent:
# from easyasc.utils.datatype import Datatype

DT.float
DT.half
DT.int
```

### Why you should prefer `DT.*`

- it is the stable public authoring surface
- it keeps kernel code short and readable
- it gives you the predefined singleton dtype objects that the rest of the framework expects

Recommended style:

```python
ub = Tensor(DT.float, [128, 128], Position.UB)
idx = Reg(DT.uint16)
scale = Var(1.0, DT.float)
```

Avoid passing raw strings such as `"float"` or `"int8_t"` into APIs that expect a dtype object.

## 3. `Datatype`

### What it is

- `Datatype` is the underlying enum-like class defined in `easyasc/utils/datatype.py`
- each class attribute is one predefined `DataTypeValue` singleton

Available members:

| Public name | Backend spelling | `size` | `C0` |
| --- | --- | --- | --- |
| `DT.half` | `half` | `2` | `16` |
| `DT.float` | `float` | `4` | `8` |
| `DT.int` | `int` | `4` | `8` |
| `DT.int8` | `int8_t` | `1` | `32` |
| `DT.uint8` | `uint8_t` | `1` | `32` |
| `DT.int16` | `int16_t` | `2` | `16` |
| `DT.uint16` | `uint16_t` | `2` | `16` |
| `DT.e4m3` | `float8_e4m3_t` | `1` | `32` |
| `DT.e5m2` | `float8_e5m2_t` | `1` | `32` |
| `DT.bfloat16` | `bfloat16_t` | `2` | `16` |
| `DT.uint32` | `uint32_t` | `4` | `8` |
| `DT.uint64` | `uint64_t` | `8` | `4` |
| `DT.int64` | `int64_t` | `8` | `4` |
| `DT.hif8` | `hifloat8_t` | `1` | `32` |

### Common use of each family

- `DT.half`, `DT.float`, `DT.bfloat16`:
  - the most common tensor and register numeric dtypes
- `DT.int`:
  - integer scalar math
  - integer reinterpret targets for bitwise vec paths
- `DT.int8`, `DT.uint8`, `DT.int16`, `DT.uint16`:
  - compact storage, gather/scatter indices, and narrow micro data movement
- `DT.e4m3`, `DT.e5m2`, `DT.hif8`:
  - fp8-related paths
  - `DT.hif8` is also a special case in current micro cast default-config selection
- `DT.uint32`:
  - often used by counters such as the `cnt` argument in `update_mask`
- `DT.uint64`, `DT.int64`:
  - available, but less common in the current public examples

### Important singleton rule

Many internal paths compare dtypes by identity, not only by value.

Examples in the current codebase:

- `Var` arithmetic promotion checks `other.dtype is Datatype.float` and `other.dtype is Datatype.int`
- some vec bitwise lowering paths check `dst.dtype is Datatype.int`

That means this is the safe pattern:

```python
dtype = DT.float
```

and this is not recommended:

```python
dtype = DataTypeValue("float")
```

Even though `DataTypeValue("float") == DT.float` is true, it is not the same singleton object, so identity-based branches may not behave the same way.

Practical rule:

- always use predefined `DT.*` or `Datatype.*` members
- do not construct fresh `DataTypeValue(...)` objects in normal kernel authoring

## 4. `DataTypeValue`

### `DataTypeValue(name)`

- Purpose: represent one concrete dtype object
- Constructor parameter:
  - `name`: backend dtype spelling such as `"float"` or `"int8_t"`

You usually do not instantiate this class directly. The framework already provides the standard instances through `DT`.

### `__str__()` and `__repr__()`

- `str(dtype)` returns the backend spelling
- `repr(dtype)` returns `DataTypeValue('...')`

Examples:

```python
str(DT.float)    # "float"
str(DT.e5m2)     # "float8_e5m2_t"
repr(DT.uint16)  # "DataTypeValue('uint16_t')"
```

This is why generated code, error messages, and debug prints often show names such as `half`, `int8_t`, or `float8_e4m3_t`.

### Equality and hashing

- `DataTypeValue` is hashable
- equality compares dtype names
- comparing with a non-`DataTypeValue` raises `TypeError`

Examples:

```python
DT.float == DT.float
DT.int8 == DT.int8
```

But:

```python
DT.float == "float"   # raises TypeError
```

This is stricter than Python enums or strings. When checking a dtype, compare it to another dtype object, not to a string.

### `.size`

- Purpose: return the number of bytes per element
- Type: integer property

Examples:

```python
DT.half.size == 2
DT.float.size == 4
DT.e4m3.size == 1
DT.uint64.size == 8
```

Typical use:

- estimating tile byte size
- understanding width ratios in `reinterpret` or micro `cast`
- deriving how many elements fit in a fixed register or memory block

### `.C0`

- Purpose: return the framework's dtype-specific `C0` width
- Type: integer property

Examples:

```python
DT.half.C0 == 16
DT.float.C0 == 8
DT.int8.C0 == 32
DT.uint64.C0 == 4
```

`C0` is used throughout the framework when data movement or layout logic needs the hardware-native inner block width for that dtype.

Typical implications:

- `half` / `bfloat16` paths often reason in groups of `16`
- `float` / `int` / `uint32` paths often reason in groups of `8`
- 8-bit paths such as `int8`, `uint8`, `e4m3`, `e5m2`, and `hif8` often reason in groups of `32`

### Unsupported names

If you create a `DataTypeValue` with a name that the framework does not recognize, operations such as `.size` or `.C0` raise `ValueError`.

That is another reason to prefer predefined `DT.*` members instead of hand-built dtype objects.

## 5. Practical Examples

### Tensor, register, and scalar declarations

```python
ub = Tensor(DT.float, [M, N], Position.UB)
acc = Reg(DT.float)
idx = Reg(DT.uint16)
count = Var(0, DT.int)
```

### Reinterpret and cast reasoning

```python
src_i32 = reinterpret(src_f32, DT.int)
dst_h <<= src_f.astype(DT.half)
```

The first example changes how the same bytes are viewed. The second changes numeric dtype through micro cast logic.

### Size-aware mental math

```python
tile_bytes = DT.half.C0 * DT.half.size   # 16 * 2 = 32 bytes
```

This is the kind of quick calculation that shows up when reasoning about lane groups, block strides, and packing ratios.

## 6. Practical Guidance

- Use `DT.*` in normal kernel code.
- Treat `Datatype` as the underlying implementation namespace behind `DT`.
- Expect constructor and error messages to mention `DataTypeValue`.
- Use `.size` when you care about bytes.
- Use `.C0` when you care about dtype-native block width.
- Do not hand-construct `DataTypeValue(...)` unless you are extending framework internals and know every code path that must learn the new dtype.
