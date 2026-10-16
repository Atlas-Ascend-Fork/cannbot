# Positions

This page documents the local-memory position objects used throughout `easyasc`.

Two names matter here:

- `Position`: the public namespace that kernel authors normally use
- `PositionType`: the concrete value object stored on `Tensor`, `DBuff`, and `TBuff`

In normal kernel code, you almost always write `Position.L1`, `Position.L0C`, or `Position.UB`.

## 1. Overview

`Position` describes where a local tensor or local buffer lives on chip.

Typical examples:

```python
l1 = Tensor(DT.half, [M, K], Position.L1)
l0c = DBuff(DT.float, [M, N], Position.L0C)
ub = TBuff(DT.float, [64, 64], Position.UB)
```

What uses `Position`:

- `Tensor(dtype, shape, position=...)`
- `DBuff(dtype, shape, position=...)`
- `TBuff(dtype, shape, position=...)`

What does not use `Position`:

- `GMTensor`

`GMTensor` represents global memory and therefore does not take a `PositionType`. If you are working with GM inputs or outputs, use `GMTensor`, not `Position.GM`.

## 2. `Position`

### What it is

- `Position` is the public enum-like namespace exported by `easyasc.a2` and `easyasc.a5`
- each member is a predefined `PositionType` singleton

Available members:

| Public name | Meaning | C++ mapping | Common role |
| --- | --- | --- | --- |
| `Position.L1` | on-chip L1 tensor storage | `TPosition::A1` | cube staging and transposed L1 views |
| `Position.L0A` | cube input buffer A | `TPosition::A2` | matmul left input staging |
| `Position.L0B` | cube input buffer B | `TPosition::B2` | matmul right input staging |
| `Position.L0C` | cube output / accumulation buffer | `TPosition::CO1` | matmul accumulator or cube result tiles |
| `Position.UB` | vec or micro unified buffer | `TPosition::VECCALC` | vec ops, micro ops, and vec-side staging |

### Why you should prefer `Position.*`

- it is the stable public authoring surface
- it gives you the singleton objects that the rest of the framework expects
- many internal checks compare positions by identity, not only by value

Examples from the current codebase:

- `Tensor.T` requires `self.position is Position.L1`
- `@vf` micro calls reject tensor inputs whose `position is not Position.UB`

That means this is the safe pattern:

```python
pos = Position.UB
```

and this is not recommended:

```python
pos = PositionType("UB")
```

Even though `PositionType("UB") == Position.UB` is true, it is not the same singleton object, so identity-based checks may not behave the same way.

## 3. `PositionType`

### `PositionType(name)`

- Purpose: represent one concrete local-memory position value
- Constructor parameter:
  - `name`: position name such as `"L1"` or `"UB"`

You usually do not instantiate this class directly. The framework already provides the standard instances through `Position`.

### `__str__()` and `__repr__()`

- `str(position)` returns the plain position name
- `repr(position)` returns `PositionType('...')`

Examples:

```python
str(Position.L0C)    # "L0C"
repr(Position.UB)    # "PositionType('UB')"
```

### Equality

- equality compares position names
- comparing with a non-`PositionType` raises `TypeError`

Example:

```python
Position.L1 == Position.L1
```

But:

```python
Position.L1 == "L1"   # raises TypeError
```

### `.cpp`

- Purpose: return the backend C++ `TPosition::*` spelling for this position
- Type: string property

Examples:

```python
Position.L1.cpp == "TPosition::A1"
Position.L0A.cpp == "TPosition::A2"
Position.L0B.cpp == "TPosition::B2"
Position.L0C.cpp == "TPosition::CO1"
Position.UB.cpp == "TPosition::VECCALC"
```

This property is what lowering and code generation eventually use when emitting buffer declarations and local tensor operations.

If you construct an unsupported `PositionType` manually, `.cpp` fails because there is no mapping entry for that name. That is another reason to prefer predefined `Position.*` members.

## 4. Practical Semantics of Each Position

### `Position.L1`

- local L1 staging space
- common source or destination for cube data movement
- the only local tensor position for which `Tensor.T` is valid in the current implementation

Example:

```python
l1x = Tensor(DT.half, [128, K], Position.L1)
l1x_t = l1x.T
```

### `Position.L0A` and `Position.L0B`

- cube input positions
- most often used as the two inputs to `mmad` or `matmul`-style cube flows
- usually reached from `L1` by cube-side movement

Example:

```python
l0a = Tensor(DT.half, [128, 128], Position.L0A)
l0b = Tensor(DT.half, [128, 128], Position.L0B)
```

### `Position.L0C`

- cube accumulation or result position
- usually stores float accumulators or cube outputs before writeback or vec-side postprocess

Example:

```python
l0c = DBuff(DT.float, [128, 128], Position.L0C)
```

### `Position.UB`

- vec-side and micro-side working space
- the most common local position for elementwise ops, gather/scatter, micro register load/store, and vec postprocessing
- `@vf` micro helpers currently require tensor inputs in `Position.UB`

Example:

```python
ub = Tensor(DT.float, [64, 64], Position.UB)
```

## 5. Where Position Matters in Practice

### Tensor and buffer constructors

`Tensor`, `DBuff`, and `TBuff` all validate that `position` is a `PositionType`.

Examples:

```python
tmp = Tensor(DT.float, [32, 32], Position.UB)
stage = DBuff(DT.half, [128, K], Position.L1)
pipe_buf = TBuff(DT.float, [64, 64], Position.UB)
```

### Position-sensitive API behavior

Some APIs care about the exact position, not just the shape or dtype.

Current examples in the implementation:

- `Tensor.T` only works on `Position.L1`
- many vec APIs expect source and destination tensors in `Position.UB`
- `@vf` micro modules only accept `Tensor` inputs in `Position.UB`
- cube staging flows typically move through `L1 -> L0A/L0B -> L0C`

### Parser and codegen meaning

The position also controls how local tensors are declared in generated C++.

For example:

```python
Position.L1.cpp   -> TPosition::A1
Position.L0C.cpp  -> TPosition::CO1
Position.UB.cpp   -> TPosition::VECCALC
```

That is why a wrong position is not just metadata noise. It changes which pipeline and which local-memory domain the tensor belongs to.

## 6. Practical Guidance

- Use predefined `Position.*` members in normal kernel code.
- Do not hand-construct `PositionType(...)` unless you are extending framework internals.
- Use `Position.UB` for vec and micro working tensors.
- Use `Position.L1` for cube staging tensors and transpose-enabled local views.
- Use `Position.L0A`, `Position.L0B`, and `Position.L0C` only when you are explicitly building cube pipelines.
- Use `GMTensor` for GM inputs and outputs; there is no `Position.GM` in the local-position namespace.
