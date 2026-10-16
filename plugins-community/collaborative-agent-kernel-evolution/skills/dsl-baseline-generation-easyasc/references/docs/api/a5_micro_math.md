# A5 Micro Math

This page documents the register-level math helpers exported directly by `easyasc.a5`.

The descriptions below follow:

- the public stubs under `easyasc/stub_functions/micro/`
- the current V2 simulator behavior in `easyasc/simulator_v2/ops/micro/runtime.py`
- the current micro tests under `testcases/simulator/micro/`

All functions on this page:

- require an active `@vf` context
- operate on `Reg` and `MaskReg`, not on UB `Tensor`
- work lane-wise unless a function is explicitly documented as a reduction
- for scalar-taking helpers, the stub does not perform implicit int-to-float conversion inside `@vf`

## 1. Register Generation and Duplication

### `arange(dst, start, increase=True)`

- Purpose: Fill every lane of a register with an arithmetic progression.
- Parameters:
  - `dst`: destination `Reg`
  - `start`: scalar start value
  - `increase`: whether the sequence increases or decreases

Behavior:

- This API writes all lanes of `dst`.
- If `increase=True`, the simulator computes:
  - `dst[i] = start + i`
- If `increase=False`, the simulator computes:
  - `dst[i] = start - i`
- Integer destination dtypes use integer arithmetic.
- Floating-point destination dtypes use floating-point arithmetic.

Supported destination dtypes in the public stub:

- `DT.int8`
- `DT.int16`
- `DT.int`
- `DT.half`
- `DT.float`

Notes:

- There is no mask argument.
- There is no `C0` grouping.
- The lane count still depends on dtype:
  - `half`: 128 lanes
  - `float`: 64 lanes
  - `int8`: 256 lanes

Examples:

```text
arange(dst_half, 0.0, increase=True)
dst = [0.0, 1.0, 2.0, 3.0, ...]
```

```text
arange(dst_int16, 5, increase=False)
dst = [5, 4, 3, 2, 1, 0, ...]
```

Example use:

```python
idx = Reg(DT.int16)
arange(idx, 0)
```

Restrictions:

- `dst` must be `Reg`
- `start` must be `Var`, `int`, or `float`
- float-like destinations require a float-like `start` / `Var`
- `increase` must be `bool`

### `dup(dst, src, mask=None)`

- Purpose: Broadcast one value into the active lanes of a register.
- Parameters:
  - `dst`: destination `Reg`
  - `src`: source `Reg`, `Var`, `int`, or `float`
  - `mask`: optional `MaskReg`

Behavior:

- If `src` is a scalar or `Var`, that scalar is written into every active lane of `dst`.
- If `src` is a `Reg`, the simulator reads only `src[0]` and broadcasts that single lane into every active lane of `dst`.
- The simulator zeroes `dst` first, then writes the broadcast value into active lanes only.
- Inactive lanes therefore become `0`.

Mask behavior:

- The mask is lane-wise.
- There is no `C0` expansion.
- Lanes not selected by the mask stay `0`.

Examples:

```text
dup(dst, 3.5, mask=VL4)
old dst = [10, 11, 12, 13, 14, 15]
new dst = [3.5, 3.5, 3.5, 3.5, 0, 0]
```

```text
src = [8, 9, 10, 11, ...]
dup(dst, src, mask=VL4)
result in active lanes = [8, 8, 8, 8]
```

Common pitfall:

- `dup(dst, src_reg)` is not a lane-wise copy.
- It broadcasts the first lane of `src_reg`.

Example use:

```python
dup(dst_reg, 1.0)
dup(dst_reg, src_reg, mask=mask)
```

Restrictions:

- `dst` must be `Reg`
- `src` must be `Reg`, `Var`, `int`, or `float`
- when `src` is a `Reg`, `src.dtype` must equal `dst.dtype`
- when `src` is scalar-like, float-like destinations require float-like scalars

## 2. Binary Register Ops

These functions share one simulator execution pattern:

- `vmax`
- `vmin`
- `add`
- `sub`
- `mul`
- `div`
- `vand`
- `vor`
- `vxor`
- `prelu`

Shared parameters:

- `dst`: destination `Reg`
- `src1`, `src2`: source `Reg`
- `mask`: optional `MaskReg`

Shared simulator rule:

- the simulator snapshots source registers first, so `dst` may alias `src1` and/or `src2`
- the simulator zeroes `dst` first
- active lanes are then written with the binary-op result
- inactive lanes therefore stay `0`

Equivalent masked form:

```text
dst[i] = op(src1[i], src2[i])   if mask[i] is active
dst[i] = 0                      otherwise
```

Shared restrictions:

- all three registers must have the same dtype
- the mask is lane-wise

### `vmax(dst, src1, src2, mask=None)`

- Purpose: Lane-wise maximum.
- Formula on active lanes:
  - `max(src1[i], src2[i])`
- Example:

```python
vmax(dst, r0, r1)
```

### `vmin(dst, src1, src2, mask=None)`

- Purpose: Lane-wise minimum.
- Formula on active lanes:
  - `min(src1[i], src2[i])`
- Example:

```python
vmin(dst, r0, r1)
```

### `add(dst, src1, src2, mask=None)`

- Purpose: Lane-wise add.
- Formula on active lanes:
  - `src1[i] + src2[i]`
- Example:

```python
add(dst, r0, r1)
```

### `sub(dst, src1, src2, mask=None)`

- Purpose: Lane-wise subtract.
- Formula on active lanes:
  - `src1[i] - src2[i]`
- Example:

```python
sub(dst, r0, r1)
```

### `mul(dst, src1, src2, mask=None)`

- Purpose: Lane-wise multiply.
- Formula on active lanes:
  - `src1[i] * src2[i]`
- Example:

```python
mul(dst, r0, r1)
```

### `div(dst, src1, src2, mask=None)`

- Purpose: Lane-wise divide.
- Formula on active lanes:
  - `src1[i] / src2[i]`
- Example:

```python
div(dst, r0, r1)
```

### `vand(dst, src1, src2, mask=None)`

- Purpose: Lane-wise bitwise and.
- Simulator behavior:
  - for integer-like lanes, applies bitwise `and`
  - for floating-point lanes, reinterprets the underlying bit pattern as an integer of the same width, applies bitwise `and`, then reinterprets back
- Example:

```python
vand(dst, r0, r1)
```

### `vor(dst, src1, src2, mask=None)`

- Purpose: Lane-wise bitwise or.
- Simulator behavior:
  - follows the same bit-pattern rule as `vand`
- Example:

```python
vor(dst, r0, r1)
```

### `vxor(dst, src1, src2, mask=None)`

- Purpose: Lane-wise bitwise xor.
- Simulator behavior:
  - follows the same bit-pattern rule as `vand`
- Example:

```python
vxor(dst, r0, r1)
```

### `prelu(dst, src1, src2, mask=None)`

- Purpose: Lane-wise parametric ReLU.
- Formula on active lanes:
  - `src1[i]` if `src1[i] > 0`
  - `src1[i] * src2[i]` otherwise
- Inactive lanes stay `0`.
- Example:

```python
prelu(dst, xreg, slope_reg)
```

## 3. Unary Register Ops

These functions share one simulator execution pattern:

- `exp`
- `abs`
- `relu`
- `sqrt`
- `ln`
- `log`
- `log2`
- `log10`
- `neg`
- `vnot`
- `vcopy`

Shared parameters:

- `dst`: destination `Reg`
- `src`: source `Reg`
- `mask`: optional `MaskReg`

Shared simulator rule:

- the simulator snapshots the source register first, so `dst` may alias `src`
- the simulator zeroes `dst` first
- active lanes are then written with the unary-op result
- inactive lanes therefore stay `0`

Equivalent masked form:

```text
dst[i] = op(src[i])   if mask[i] is active
dst[i] = 0            otherwise
```

Shared restrictions:

- `dst.dtype` must equal `src.dtype`
- the mask is lane-wise

Shared math note:

- For `exp`, `sqrt`, `ln`, `log`, `log2`, and `log10`, the simulator computes in `float32` unless the source is already `float32`/`float64`, then casts back to `dst.dtype`.

### `exp(dst, src, mask=None)`

- Purpose: Lane-wise exponential.
- Formula on active lanes:
  - `exp(src[i])`
- Example:

```python
exp(dst, src)
```

### `abs(dst, src, mask=None)`

- Purpose: Lane-wise absolute value.
- Formula on active lanes:
  - `abs(src[i])`
- Example:

```python
abs(dst, src)
```

### `relu(dst, src, mask=None)`

- Purpose: Lane-wise ReLU.
- Formula on active lanes:
  - `max(src[i], 0)`
- Example:

```python
relu(dst, src)
```

### `sqrt(dst, src, mask=None)`

- Purpose: Lane-wise square root.
- Formula on active lanes:
  - `sqrt(src[i])`
- Example:

```python
sqrt(dst, src)
```

### `ln(dst, src, mask=None)`

- Purpose: Lane-wise natural logarithm.
- Formula on active lanes:
  - `log(src[i])`
- Example:

```python
ln(dst, src)
```

### `log(dst, src, mask=None)`

- Purpose: Log helper exposed by the micro API.
- Current simulator behavior:
  - it is implemented the same way as `ln`
  - active lanes use natural logarithm, not base-10 logarithm
- Example:

```python
log(dst, src)
```

### `log2(dst, src, mask=None)`

- Purpose: Lane-wise base-2 logarithm.
- Formula on active lanes:
  - `log2(src[i])`
- Example:

```python
log2(dst, src)
```

### `log10(dst, src, mask=None)`

- Purpose: Lane-wise base-10 logarithm.
- Formula on active lanes:
  - `log10(src[i])`
- Example:

```python
log10(dst, src)
```

### `neg(dst, src, mask=None)`

- Purpose: Lane-wise negation.
- Formula on active lanes:
  - `-src[i]`
- Example:

```python
neg(dst, src)
```

### `vnot(dst, src, mask=None)`

- Purpose: Lane-wise bitwise not.
- Simulator behavior:
  - for `bool`, applies logical not
  - for other dtypes, reinterprets the bit pattern as an integer of the same width, applies bitwise not, then reinterprets back
- Example:

```python
vnot(dst, src)
```

### `vcopy(dst, src, mask=None)`

- Purpose: Register copy.
- Current simulator behavior:
  - active lanes copy `src`
  - inactive lanes stay `0`
  - with a full mask, the result is a full copy of `src`
- Example:

```python
vcopy(dst, src)
```

## 4. Unary-Scalar Register Ops

These functions all take:

- `dst`: destination `Reg`
- `src`: source `Reg`
- `value`: scalar value
- `mask`: optional `MaskReg`

The family splits into two execution styles.

### Family A: source-preserving masked unary-scalar ops

This family includes:

- `vmaxs`
- `vmins`
- `adds`
- `muls`
- `lrelu`
- `shiftls`
- `shiftrs`

Shared simulator rule:

- the simulator snapshots the source register first, so `dst` may alias `src`
- the simulator zeroes `dst` first
- active lanes are overwritten with the scalar-op result
- inactive lanes therefore stay `0`

Equivalent masked form:

```text
dst[i] = op(src[i], value)   if mask[i] is active
dst[i] = 0                   otherwise
```

### Family B: accumulating scalar op

This family only contains:

- `axpy`

Simulator rule:

- the simulator snapshots the old destination first, then zeroes `dst`
- active lanes compute:
  - `dst[i] = old_dst[i] + src[i] * value`
- inactive lanes stay `0`

This is different from every other unary-scalar helper on this page.

### `vmaxs(dst, src, value, mask=None)`

- Purpose: Lane-wise clamp to a lower bound.
- Formula on active lanes:
  - `max(src[i], value)`
- Example:

```python
vmaxs(dst, src, 0.0)
```

### `vmins(dst, src, value, mask=None)`

- Purpose: Lane-wise clamp to an upper bound.
- Formula on active lanes:
  - `min(src[i], value)`
- Example:

```python
vmins(dst, src, 1.0)
```

### `adds(dst, src, value, mask=None)`

- Purpose: Lane-wise scalar add.
- Formula on active lanes:
  - `src[i] + value`
- Example:

```python
adds(dst, src, 1.0)
```

### `muls(dst, src, value, mask=None)`

- Purpose: Lane-wise scalar multiply.
- Formula on active lanes:
  - `src[i] * value`
- Example:

```python
muls(dst, src, 2.0)
```

### `lrelu(dst, src, value, mask=None)`

- Purpose: Lane-wise leaky ReLU with scalar slope.
- Formula on active lanes:
  - `src[i]` if `src[i] > 0`
  - `src[i] * value` otherwise
- Example:

```python
lrelu(dst, src, 0.1)
```

### `shiftls(dst, src, value, mask=None)`

- Purpose: Lane-wise left shift.
- Simulator behavior:
  - reinterprets lanes through an integer view of the same width
  - shifts left by `value`
  - reinterprets back to the original dtype
  - if `value < 0`, the simulator reverses direction and performs a right shift instead
- Restrictions:
  - `value` must be `int` or `Var`
- Example:

```python
shiftls(dst, src, 1)
```

### `shiftrs(dst, src, value, mask=None)`

- Purpose: Lane-wise right shift.
- Simulator behavior:
  - follows the same bit-pattern rule as `shiftls`
  - if `value < 0`, the simulator reverses direction and performs a left shift instead
- Restrictions:
  - `value` must be `int` or `Var`
- Example:

```python
shiftrs(dst, src, 1)
```

### `axpy(dst, src, value, mask=None)`

- Purpose: Accumulate scaled `src` into `dst`.
- Formula on active lanes:
-  - `dst[i] = old_dst[i] + src[i] * value`
- Inactive lanes stay `0`.
- This is the only scalar op on this page that uses the existing destination contents as an input.
- Example:

```python
axpy(dst, src, 0.5)
```

## 5. Group-Style Micro Helpers

These helpers all snapshot the source register first and then zero the destination register before
writing their results. That gives them stable alias behavior such as:

```text
cadd(reg, reg, mask)
```

which still reduces the original register contents instead of the partially written destination.

The following functions share the same parameter shape:

- `cmax`
- `cgmax`
- `cmin`
- `cgmin`
- `cadd`
- `cgadd`
- `cpadd`

Shared parameters:

- `dst`: destination `Reg`
- `src`: source `Reg`
- `mask`: optional `MaskReg`

Shared restrictions:

- `dst.dtype` must equal `src.dtype`
- the mask is lane-wise

There are three distinct reduction families.

### Family A: `cadd`, `cmax`, `cmin`

- Reduce all active lanes of the register into one scalar result.
- The result is written to `dst[0]`.
- Every other lane in `dst` remains `0`.
- If no lane is active, the whole destination stays zero.

Formula:

```text
dst[0] = reduce(src[active_lanes])
dst[1:] = 0
```

Example:

```text
src  = [4, 1, 7, 2, 9, 3]
mask = active lanes [0, 2, 5]

cadd -> dst = [14, 0, 0, 0, 0, 0]
cmax -> dst = [7,  0, 0, 0, 0, 0]
cmin -> dst = [3,  0, 0, 0, 0, 0]
```

### Family B: `cgadd`, `cgmax`, `cgmin`

- Reduce independently inside 8 consecutive `C0` blocks.
- Let `c0 = 32 / dtype_size_in_bytes`.
- The current simulator expects:
  - `lane_count == 8 * c0`
- Block `b` covers:
  - `src[b * c0 : (b + 1) * c0]`
- The reduction result of block `b` is written to `dst[b]`.
- Lanes `dst[8:]` remain `0`.
- If one block has no active lanes, its output slot stays `0`.

Formula:

```text
for b in range(8):
    dst[b] = reduce(src[active lanes inside block b])
dst[8:] = 0
```

Example with `half`:

```text
dtype = half
c0 = 16

block 0 -> src lanes   0..15 -> dst[0]
block 1 -> src lanes  16..31 -> dst[1]
...
block 7 -> src lanes 112..127 -> dst[7]
```

### Family C: `cpadd`

- Performs pairwise add reduction.
- Adjacent source lanes are grouped as pairs:
  - pair `0`: lanes `(0, 1)`
  - pair `1`: lanes `(2, 3)`
  - pair `2`: lanes `(4, 5)`
  - and so on
- The current simulator requires an even lane count.
- For each pair, masked-off lanes contribute `0`.
- The pair result is written to the compacted front half of `dst`.
- The upper half of `dst` remains `0`.

Formula:

```text
dst[p] = masked(src[2 * p]) + masked(src[2 * p + 1])
dst[pair_count:] = 0
```

Example:

```text
src  = [10, 20, 30, 40, 50, 60]
mask = active lanes [0, 2, 5]

pair 0 -> 10 + 0  = 10
pair 1 -> 30 + 0  = 30
pair 2 -> 0  + 60 = 60

dst = [10, 30, 60, 0, 0, 0]
```

### `cmax(dst, src, mask=None)`

- Purpose: Whole-register max reduction.
- Result rule:
  - `dst[0] = max(active src lanes)`
  - `dst[1:] = 0`
- Example:

```python
cmax(dst, src)
```

### `cgmax(dst, src, mask=None)`

- Purpose: Per-`C0`-block max reduction.
- Result rule:
  - `dst[0:8]` hold per-block maxima
  - `dst[8:] = 0`
- Example:

```python
cgmax(dst, src)
```

### `cmin(dst, src, mask=None)`

- Purpose: Whole-register min reduction.
- Result rule:
  - `dst[0] = min(active src lanes)`
  - `dst[1:] = 0`
- Example:

```python
cmin(dst, src)
```

### `cgmin(dst, src, mask=None)`

- Purpose: Per-`C0`-block min reduction.
- Result rule:
  - `dst[0:8]` hold per-block minima
  - `dst[8:] = 0`
- Example:

```python
cgmin(dst, src)
```

### `cadd(dst, src, mask=None)`

- Purpose: Whole-register sum reduction.
- Result rule:
  - `dst[0] = sum(active src lanes)`
  - `dst[1:] = 0`
- Example:

```python
cadd(dst, src)
```

### `cgadd(dst, src, mask=None)`

- Purpose: Per-`C0`-block sum reduction.
- Result rule:
  - `dst[0:8]` hold per-block sums
  - `dst[8:] = 0`
- Example:

```python
cgadd(dst, src)
```

### `cpadd(dst, src, mask=None)`

- Purpose: Pairwise add reduction.
- Result rule:
  - `dst[p] = masked(src[2p]) + masked(src[2p+1])`
  - `dst[pair_count:] = 0`
- Notes:
  - this is not a whole-register sum
  - this is not a `C0`-block reduction
- Example:

```python
cpadd(dst, src)
```
