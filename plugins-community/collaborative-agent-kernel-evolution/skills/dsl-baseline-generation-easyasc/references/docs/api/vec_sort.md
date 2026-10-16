# A2 Vec Sort and Merge Helpers

This page documents the vector-side sorting helpers exported by `easyasc.a2`.

The descriptions below follow both the public stub APIs in `easyasc/stub_functions/vec/sort.py`
and the current V2 simulator behavior in `easyasc/simulator_v2/ops/vec/v.py`
plus the legacy-layout helper in `easyasc/simulator_v2/ops/vec/_legacy_vpipe.py`.

All functions on this page:

- run on the vec side
- require `UB` tensors
- currently support `float` data only
- are lowered to vec-side calls, not cube-side calls
- are executed by the simulator on flattened 1D pointer views

The last point matters: even if you write a 2D UB tensor in the DSL, the simulator treats the pointed region as a flat stream.

## 1. Shared Data Model

`sort32`, `mergesort4`, and `mergesort_2seq` all sort by values stored in even lanes and carry payload stored in odd lanes.

So an interleaved stream like:

```text
[value0, payload0, value1, payload1, value2, payload2, ...]
```

is interpreted as:

- even positions: sort keys
- odd positions: payload that must follow the corresponding key

The simulator always permutes payload with the same `argsort` index used for the values.

Important consequence:

- these helpers do not treat the whole tensor as ordinary scalar data
- they treat it as pairs of `(key, payload)` encoded inside one `float32` stream

For `sort32`, the payload comes from a separate `idx` tensor and is written into the odd lanes of `dst`.
For `mergesort4` and `mergesort_2seq`, the payload is already embedded in the odd lanes of the source stream.

## 2. `sort32(dst, src, idx, repeat=None)`

- Purpose: Sort each 32-element value block in descending order and interleave the sorted values with the reordered indices.

Parameter meaning:

- `dst`: destination UB `Tensor`
- `src`: source UB `Tensor` containing 32 values per repeat
- `idx`: source UB `Tensor` containing one index payload for each source value
- `repeat`: number of independent 32-element blocks

Input and output layout:

- each repeat reads:
  - `32` float values from `src`
  - `32` integer-like index values from `idx`
- each repeat writes:
  - `64` float elements to `dst`
- destination format per repeat is:

```text
[sorted_value0, sorted_index0_bits_as_float,
 sorted_value1, sorted_index1_bits_as_float,
 ...,
 sorted_value31, sorted_index31_bits_as_float]
```

What the simulator does for one repeat:

1. Read:
   - `src_block = src[rep * 32 : (rep + 1) * 32]`
   - `idx_block = idx[rep * 32 : (rep + 1) * 32]`
2. Sort values:
   - `arg = torch.argsort(src_block, descending=True)`
   - `src_sorted = src_block[arg]`
3. Reorder indices with the same permutation:
   - `idx_sorted = idx_block[arg]`
4. Reinterpret index bits as `float32`:
   - simulator first ensures an `int32`-compatible view
   - then writes `idx_sorted.view(torch.float32)` into the odd destination lanes
5. Interleave the result into `dst`.

That means `dst` is not "sorted values only". It is an interleaved `(value, index_bits)` stream.

Recovering the indices:

```python
sorted_values = dst[0::2]
sorted_index_bits = dst.view(torch.int32)[1::2]
```

If your runtime supports `torch.uint32`, you can reinterpret the same odd lanes as `uint32`.

Default inference:

- if `repeat` is omitted, the stub computes:
  - `repeat = (src.span[0] * src.span[1]) // 32`

Important caveat:

- that inference uses floor division
- if the logical source span is not an exact multiple of `32`, trailing elements are ignored by the inferred `repeat`
- the stub does not add a separate divisibility check

Example with one repeat:

```text
src = [5, 1, 7, 2, ...]
idx = [0, 1, 2, 3, ...]

after descending sort:
values -> [7, 5, 2, 1, ...]
index  -> [2, 0, 3, 1, ...]

dst = [7, bits(2), 5, bits(0), 2, bits(3), 1, bits(1), ...]
```

Tie behavior:

- the simulator delegates ordering to `torch.argsort(descending=True)`
- if two values are equal, tie order follows the current `torch.argsort` behavior
- the simulator does not add an extra stability rule on top of that

Restrictions and checks:

- `src`, `dst`, and `idx` must all be UB tensors
- `src.dtype` and `dst.dtype` must both be `float`
- `idx.dtype` must be `uint32` at the stub level
- the simulator accepts an `int32`-compatible tensor view for `idx`
- the simulator requires:
  - source size at least `repeat * 32`
  - index size at least `repeat * 32`
  - destination size at least `repeat * 64`

Minimal usage:

```python
sort32(sorted_pairs, values, indices)
```

## 3. `mergesort4(dst, src, length_per_seq, repeat)`

- Purpose: Merge four descending sequences of keys while carrying their odd-lane payload along with the same permutation.

Parameter meaning:

- `dst`: destination UB `Tensor`
- `src`: source UB `Tensor`
- `length_per_seq`: logical length of each of the four descending key sequences
- `repeat`: number of independent merge groups

Input layout per repeat:

- total elements per repeat:
  - `8 * length_per_seq`
- after deinterleaving:
  - `even_val` has length `4 * length_per_seq`
  - `odd_val` has length `4 * length_per_seq`
- the simulator interprets `even_val` as four contiguous descending splits:

```text
split 0 = even_val[0 : length_per_seq]
split 1 = even_val[length_per_seq : 2 * length_per_seq]
split 2 = even_val[2 * length_per_seq : 3 * length_per_seq]
split 3 = even_val[3 * length_per_seq : 4 * length_per_seq]
```

The odd lanes are just payload. They are not checked for ordering.

What the simulator does for one repeat:

1. Read one flat block of length `8 * length_per_seq`.
2. Deinterleave:
   - `even_val = block[0::2]`
   - `odd_val = block[1::2]`
3. Validate the precondition:
   - each of the four contiguous segments in `even_val` must already be in descending order
4. Compute:
   - `arg = torch.argsort(even_val, descending=True)`
5. Reorder both streams:
   - `even_new = even_val[arg]`
   - `odd_new = odd_val[arg]`
6. Reinterleave them into `dst`.

So the simulator behavior is:

- not a literal step-by-step tree merge
- but a checked "four descending runs" contract followed by a full descending reorder of the combined keys

Why the descending precondition matters:

- the simulator explicitly rejects any repeat whose four even-lane sub-sequences are not individually descending
- this mirrors the intended contract of a merge helper rather than a general-purpose arbitrary sort

Example with `length_per_seq = 2`:

```text
even_val before:
[90, 80, 75, 70, 60, 50, 40, 10]

interpreted as four descending runs:
[90, 80] | [75, 70] | [60, 50] | [40, 10]

odd_val before:
[a, b, c, d, e, f, g, h]

after argsort on even_val:
even_new = [90, 80, 75, 70, 60, 50, 40, 10]
odd_new  = [a, b, c, d, e, f, g, h]
```

If the runs overlap more interestingly:

```text
even_val before:
[90, 30, 80, 20, 70, 10, 60, 0]

runs:
[90, 30] | [80, 20] | [70, 10] | [60, 0]

after merge:
[90, 80, 70, 60, 30, 20, 10, 0]
```

and the odd payload is permuted in exactly the same way.

Tie behavior:

- tie ordering follows the current `torch.argsort(descending=True)` behavior
- no additional stability rule is layered on top by the simulator

Restrictions and checks:

- `src` and `dst` must be UB `float` tensors
- `length_per_seq` must be positive
- `repeat` must be non-negative
- the simulator requires:
  - source size at least `repeat * 8 * length_per_seq`
  - destination size at least `repeat * 8 * length_per_seq`
- for every repeat, all four even-lane runs must already be descending

Minimal usage:

```python
mergesort4(dst, src, 32, 1)
```

## 4. `mergesort_2seq(dst, src1, src2, size1, size2)`

- Purpose: Merge two descending interleaved `(key, payload)` streams into one descending interleaved result stream.

Parameter meaning:

- `dst`: destination UB `Tensor`
- `src1`: first source UB `Tensor`
- `src2`: second source UB `Tensor`
- `size1`: number of key/payload pairs consumed from `src1`
- `size2`: number of key/payload pairs consumed from `src2`

Input layout:

- `src1` contributes `2 * size1` float elements
- `src2` contributes `2 * size2` float elements
- after deinterleaving:
  - `even_1 = src1[0::2]`
  - `odd_1 = src1[1::2]`
  - `even_2 = src2[0::2]`
  - `odd_2 = src2[1::2]`

Precondition:

- `even_1` must already be descending
- `even_2` must already be descending

What the simulator does:

1. Read exactly `2 * size1` elements from `src1` and `2 * size2` elements from `src2`.
2. Deinterleave both streams into keys and payload.
3. Validate that `even_1` and `even_2` are both descending.
4. Concatenate:
   - `even_cat = [even_1, even_2]`
   - `odd_cat = [odd_1, odd_2]`
5. Compute one descending permutation:
   - `arg = torch.argsort(even_cat, descending=True)`
6. Reorder both concatenated streams with `arg`.
7. Interleave the merged result into `dst`.

As with `mergesort4`, the simulator models a merge contract by validating pre-sorted inputs first, then uses a whole-array descending reorder to build the final output.

Example:

```text
src1 pairs: [(100, a), (90, b), (70, c), (20, d)]
src2 pairs: [(95, e), (80, f), (10, g)]

merged keys:
[100, 95, 90, 80, 70, 20, 10]

merged payload:
[a, e, b, f, c, d, g]

dst stream:
[100, a, 95, e, 90, b, 80, f, 70, c, 20, d, 10, g]
```

Tie behavior:

- tie ordering follows the current `torch.argsort(descending=True)` behavior on the concatenated key stream
- the simulator does not guarantee a separate stable merge rule

Restrictions and checks:

- `dst`, `src1`, and `src2` must all be UB `float` tensors
- `size1` and `size2` must both be positive
- the simulator requires:
  - `src1` size at least `2 * size1`
  - `src2` size at least `2 * size2`
  - `dst` size at least `2 * (size1 + size2)`
- `even_1` and `even_2` must both already be descending

Minimal usage:

```python
mergesort_2seq(dst, left_pairs, right_pairs, size1, size2)
```
