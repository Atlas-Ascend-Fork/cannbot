# axis-gather Example (np.take / tf.gather / ONNX Gather Semantics)

⚠️ **This implements axis-based gather where indices is 1-D**

For PyTorch's `torch.gather` (index.shape == output.shape), see `../torch_gather_20_20/`.

## Semantics

Gathers slices along a specified axis using a 1-D index tensor:

```python
# NumPy
output = np.take(input, indices, axis=1)

# TensorFlow
output = tf.gather(input, indices, axis=1)

# ONNX
output = Gather(input, indices, axis=1)

# PyTorch equivalent
output = torch.index_select(input, dim=1, index=indices)
```

**Shape relationship**:
```
input.shape  = [d0, d1, d2, ..., dn]
indices.shape = [k]                      # 1-D
output.shape = [d0, k, d2, ..., dn]      # axis=1 replaced by k
```

## Addressing Pattern

The kernel decomposes the flat output index into outer/gathered/inner components:

```cpp
// Decompose flat index
uint32_t inner = idx % innerSize;           // elements after axis
uint32_t j = (idx / innerSize) % indexSize; // position in indices
uint32_t outer = idx / (innerSize * indexSize);  // elements before axis

// Read the gather index (one per slab, shared across inner dimension)
int64_t indexValue = indices[j];

// Compute source offset
uint64_t srcOffset = outer * (axisSize * innerSize)
                   + indexValue * innerSize
                   + inner;

output[idx] = input[srcOffset];
```

**Key insight**: `indices[j]` is read once per slab and shared across all `inner` positions. This is what distinguishes axis-gather from torch.gather.

## Files in This Example

- `gather.asc` — Standalone SIMT kernel (Model B, VF-based)
- `gather_custom_tiling.h` — Tiling data structure with `GET_TILING_DATA` fallback

## Verification

Compile-verified on CANN 9.1.0-beta.3 / Ascend950PR (`dav-3510`), 2026-08-05:

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
A="$ASCEND_HOME_PATH/$(uname -m)-linux"

bisheng --asc-aicore-lang --npu-arch=dav-3510 --cce-aicore-only \
  -std=c++17 -O2 -D__NPU_TILING__ \
  -I"$A/include" -I"$A/asc/include" -I"$A/asc/impl" -I. \
  -c gather.asc -o gather.o

nm -C gather.o | grep -c 'simt_gather_axis'   # expect 8
```

Drop `--cce-aicore-only` and this still exits 0 — but produces a 35 KB host-only
object with **zero** VF instantiations. Always check the symbol count.

Exit 0, 14368 B object, 8 `simt_gather_axis` VF instantiations
(`{float, half, bfloat16_t, int32_t}` × `{int32_t, int64_t}` index types).

### On-device numerical verification

Run on **Ascend950PR_9599** (1 device, `acl.get_soc_name()`; `npu-smi` is absent in
this environment), 2026-08-05. Shape `x[3,20,7]`, `indices[20]`, axis=1 →
`y[3,20,7]` = 420 elements per path, output buffer poisoned with `0xFF` before
launch so an unwritten element cannot read as a pass.

The index vector deliberately mixes forward, reversed, duplicate (`5,5`), negative
(`-1` → wraps to 19), and two out-of-bounds entries (`20` and `-21`) to exercise the
wrap-then-guard order and the OOB→0 path.

| dtypeCode | index int32 | index int64 |
|---|---|---|
| 0 float32  | 0 mismatches | 0 mismatches |
| 1 float16  | 0 mismatches | 0 mismatches |
| 2 bfloat16 | 0 mismatches | 0 mismatches |
| 3 int32    | 0 mismatches | 0 mismatches |

All 8 dispatch paths pass against a CPU golden — 3360 elements total, 0 mismatches.
Tolerance: exact for float32/int32, 1e-2 for float16, 1e-1 for bfloat16.

Harness notes for anyone reproducing this: launch is `gather_custom<<<blocks, 0,
stream>>>(...)` (3-arg, Model B — `dim3(threadsPerBlock)` comes from the tiling via
`asc_vf_call`, *not* from the launch). Host-side `(GM_ADDR)` casts emit 5
`'cce_global' attribute ignored` warnings — expected, not a defect. Host
`bfloat16_t` is a bisheng builtin proxy with a deleted copy-assign and no float
conversion, so it cannot go in a `std::vector`; stage bf16 as raw `uint16_t` and
convert by hand.

## Tiling Data Fields

> **Field order is load-bearing.** Tiling arrives via `reinterpret_cast` on a raw
> struct, so a host built from a different field order than the kernel silently swaps
> values — valid addresses, wrong data, no compile error. `gather_custom_tiling.h` in
> this directory is the single source of truth; the listing below is a copy of it and
> must stay byte-identical in order and names.

```cpp
struct GatherCustomTilingData {
    uint32_t totalElements;    // numel(y) == outerSize * indexLen * innerSize
    uint32_t threadsPerBlock;  // threads per block (256) — arg to dim3() in asc_vf_call
    uint32_t dtypeCode;        // 0=float32, 1=float16, 2=bfloat16, 3=int32
    uint32_t indexDtypeCode;   // 0=int32, 1=int64
    uint32_t outerSize;        // prod(x.shape[:axis])
    uint32_t axisSize;         // x.shape[axis]  (bound for the OOB index guard)
    uint32_t innerSize;        // prod(x.shape[axis+1:])
    uint32_t indexLen;         // numel(indices) — the gathered extent of the output
};
```

The host computes these from input shapes and the axis attribute.

## When to Use This Pattern

Use axis-gather when:
- Selecting rows/columns/slices from a table
- Embedding lookup (vocabulary → dense vectors)
- Reordering along a single dimension
- Your framework uses `np.take`, `tf.gather`, or ONNX `Gather`

Use `torch.gather` (see `../torch_gather_20_20/`) when:
- Each output element needs a different index
- Index tensor has the same shape as output
- Implementing sparse attention or dynamic routing

## Common Mistake

Copying `torch_gather_20_20` for an axis-gather operator produces **silently wrong results**. The memory accesses are valid but gather from incorrect locations. Always verify the semantic variant first.
