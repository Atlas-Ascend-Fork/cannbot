# A5 Micro Compare and Select

This page documents the `a5` micro compare/select helpers:

- `CompareMode`
- `CompareModeType`
- `compare`
- `select`

The descriptions below follow:

- the public stubs in `easyasc/stub_functions/micro/compare.py`
- the current V2 simulator behavior in `easyasc/simulator_v2/ops/micro/runtime.py`
- the helper mask behavior in `easyasc/stub_functions/micro/microutils.py`
- the current V2 micro tests under `testcases/simulator/micro/`

All functions on this page:

- require an active `@vf` context
- operate lane-wise on `Reg` and `MaskReg`
- use mask bits at micro lane granularity, not `C0`-expanded tensor masks

## 1. `CompareModeType` and `CompareMode`

`compare(...)` uses `CompareModeType` values to describe the predicate.

These types are defined in `easyasc/utils/comparemode.py`.

### `CompareModeType`

- Purpose: represent one concrete comparison predicate such as `LT` or `GE`.
- Stored field:
  - `name`
- Important behavior:
  - `str(mode)` returns names such as `LT` or `GE`
  - `repr(mode)` returns a debug-style form such as `CompareModeType('GE')`
  - equality compares mode names

One slightly unusual behavior in the current implementation:

- comparing a `CompareModeType` against an object of another type raises `TypeError`
- it does not silently return `False`

In practice this usually only matters in internal helper code or debugging code, not in normal kernel authoring.

### `CompareMode`

`CompareMode` is the enum-like namespace that exports the six supported predicates:

- `CompareMode.LT`
  - lane is active when `lhs < rhs`
- `CompareMode.LE`
  - lane is active when `lhs <= rhs`
- `CompareMode.GT`
  - lane is active when `lhs > rhs`
- `CompareMode.GE`
  - lane is active when `lhs >= rhs`
- `CompareMode.EQ`
  - lane is active when `lhs == rhs`
- `CompareMode.NE`
  - lane is active when `lhs != rhs`

These are singleton values, so normal user code should always pass:

```python
CompareMode.GT
```

rather than constructing `CompareModeType(...)` manually.

### Why this type lives best on this page

`CompareMode` only matters to the micro compare path documented here.
Moving it next to `compare(...)` keeps:

- the enum
- the compare API
- the simulator semantics

in one place.

## 2. Mental Model

At micro level:

- a `Reg` holds one vector of lanes
- a `MaskReg` holds one boolean bit per lane
- an execution mask decides which lanes are updated

There are two different roles for masks here:

- destination mask:
  - only for `compare`
  - receives boolean comparison results
- execution mask:
  - optional `mask=...` parameter
  - decides which lanes participate in the instruction

If `mask` is omitted, the stub calls `micro.get_mask(dtype)` through `ensure_mask(...)`.
In normal usage that means "use the current default execution mask for this dtype", which is typically the full active lane set unless earlier code changed it.

## 3. `compare(dst, src1, src2, mode, mask=None)`

- Purpose: compare one register against another register or a scalar and write the boolean result into a `MaskReg`.
- Parameters:
  - `dst`: destination `MaskReg`
  - `src1`: left-hand-side `Reg`
  - `src2`: right-hand-side `Reg`, `Var`, `int`, or `float`
  - `mode`: `CompareMode`
  - `mask`: optional execution `MaskReg`

### Supported comparison modes

- `CompareMode.LT`
- `CompareMode.LE`
- `CompareMode.GT`
- `CompareMode.GE`
- `CompareMode.EQ`
- `CompareMode.NE`

### Stub-level lowering

The stub emits one of two instruction forms:

- `micro_compare`
  - when `src2` is a `Reg`
- `micro_compares`
  - when `src2` is a scalar-like value

The scalar form does not materialize a temporary register in Python.
Instead, the scalar is formatted and the simulator later resolves it into a numeric value.

### Dtype restrictions

- `dst.dtype` must equal `src1.dtype`
- if `src2` is a `Reg`, then `src2.dtype` must also match
- if `src2` is scalar-like, it must stay in the same numeric family as `src1`
  - float-like `src1` (`DT.float` / `DT.half` / `DT.bfloat16`) requires a float-like scalar or `Var`
  - int-like `src1` requires an int-like scalar or `Var`
- `mode` must be a `CompareModeType`

This dtype rule is about lane count and register shape as much as element type:

- the simulator resolves lane views from dtype
- mismatched dtypes would imply incompatible lane shapes

### Simulator execution model

The simulator performs these steps:

1. resolve `dst` as a writable mask-lane vector
2. resolve `src1` as a register lane vector
3. resolve execution mask bits
4. compute `active = execution_mask`
5. if no lanes are active, return immediately
6. gather `lhs = src1[active]`
7. resolve `rhs`:
   - if `src2` is a `Reg`, gather `src2[active]`
   - otherwise resolve one scalar and broadcast it logically against `lhs`
8. compute comparison results for active lanes only
9. write those boolean results into `dst[active]`

Crucial consequence:

- masked-off lanes in `dst` are not touched
- they keep their previous values

That means `compare` is a masked update, not an unconditional overwrite.

### Exact lane rule

For each lane `i`:

```text
dst[i] = compare(src1[i], src2[i or scalar], mode)   if exec_mask[i] is active
dst[i] = old dst[i]                                  otherwise
```

### Scalar compare behavior

If `src2` is scalar-like:

- the simulator resolves it once
- then compares every active lane in `src1` against that scalar
- the stub rejects mixed float/int families before codegen

So:

```python
compare(mask_gt, reg, 2.0, CompareMode.GT)
```

means:

```text
mask_gt[i] = (reg[i] > 2.0)   on active lanes
```

### Register compare behavior

If `src2` is a `Reg`:

- both source registers are sliced by the same execution mask
- comparison is lane-wise only on active lanes

So:

```python
compare(mask_gt, r0, r1, CompareMode.GT, mask=gate)
```

means:

```text
mask_gt[i] = (r0[i] > r1[i])  if gate[i] is active
mask_gt[i] = old mask_gt[i]   otherwise
```

### Why masked-off lanes stay unchanged

The simulator writes only:

- `dst_view[active] = values`

It never clears or rebuilds the whole destination mask first.

That behavior is often useful when:

- one instruction updates only one chunk of a mask
- later instructions accumulate or refine mask state

But it also means you should explicitly initialize `dst` if you need deterministic values on masked-off lanes.

### Example: scalar threshold compare

```python
compare(mask_reg, r0, 0.0, CompareMode.GE)
```

Meaning:

- active lanes where `r0 >= 0` become `True`
- active lanes where `r0 < 0` become `False`
- masked-off lanes keep old `mask_reg`

### Example: partial masked compare

```python
compare(mask_reg, r0, r1, CompareMode.LT, mask=gate_mask)
```

Meaning:

- only lanes enabled by `gate_mask` are recomputed
- the rest of `mask_reg` stays unchanged

## 4. `select(dst, src1, src2, mask=None)`

- Purpose: choose lane values from `src1` or `src2` using a mask.
- Parameters:
  - `dst`: destination `Reg`
  - `src1`: source `Reg`
  - `src2`: source `Reg`
  - `mask`: optional `MaskReg`

### Dtype restrictions

- `dst.dtype`, `src1.dtype`, and `src2.dtype` must match

### Stub-level lowering

The stub emits:

- `Instruction("micro_select", dst=dst, src1=src1, src2=src2, mask=mask)`

If `mask` is omitted, it again falls back to `micro.get_mask(dtype)`.

### Simulator execution model

The simulator performs these steps:

1. resolve destination and both sources as lane vectors
2. resolve execution mask bits
3. snapshot both sources first:
   - `src1_snapshot = src1_view.clone()`
   - `src2_snapshot = src2_view.clone()`
4. copy the entire `src2_snapshot` into `dst`
5. overwrite active lanes of `dst` with values from `src1_snapshot`

So the effective rule is:

```text
dst[i] = src1[i]   if mask[i] is active
dst[i] = src2[i]   otherwise
```

### Why aliasing is safe here

Because the simulator snapshots both sources before writing:

- `dst is src1` still behaves like true select
- `dst is src2` still behaves like true select

Without the snapshots, aliasing would corrupt the not-yet-read source lanes.
The simulator explicitly avoids that problem.

### Full-lane overwrite semantics

Unlike `compare`, `select` always rebuilds the full destination:

- it first copies all lanes from `src2`
- then patches the active lanes from `src1`

So masked-off lanes do not keep the old destination value.
They always become the corresponding `src2` lane.

This is the most important semantic difference between:

- `compare`
- `select`

### Example

If:

```text
src1 = [10, 20, 30, 40]
src2 = [ 1,  2,  3,  4]
mask = [T, F, T, F]
```

then:

```text
dst = [10, 2, 30, 4]
```

### Example: branchless lane merge

```python
select(dst_reg, positive_path, negative_path, mask_reg)
```

Meaning:

- active mask lanes pick `positive_path`
- inactive mask lanes pick `negative_path`

This is the micro-level equivalent of a vectorized ternary operator.

## 5. Compare vs Select

Use `compare` when:

- you want to produce or update boolean lane state
- the destination is a `MaskReg`

Use `select` when:

- you already have a mask
- you want to merge two numeric register values into one `Reg`

Key semantic difference:

- `compare` updates only active destination lanes and leaves masked-off lanes unchanged
- `select` rebuilds the whole destination from `src2`, then overwrites active lanes from `src1`

## 6. Common Pitfalls

- Do not assume `compare(..., mask=...)` clears masked-off lanes. It does not.
- Do not assume `select(..., mask=...)` keeps old destination values on masked-off lanes. It does not; those lanes come from `src2`.
- Do not mix dtypes across `dst`, `src1`, and `src2`.
- Do not confuse the execution mask with the destination mask of `compare`. They are different roles.
