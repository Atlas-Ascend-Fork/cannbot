# Ascend Triton operator repair experience

Heuristic fixes for **Triton Ascend** kernels. These are **not guaranteed optimal**; match the compiler error or symptom, apply a **minimal** change, and re-run validation. Extend this list as new patterns appear.

---

## 1. Prefer `tl.math.*` over `libdevice.*` for elementwise math

The Ascend toolchain often routes “libdevice-style” math through symbols that are **unsupported or missing** compared to CUDA-oriented references. When the error names `libdevice.<name>`, try the **`tl.math`** equivalent first.

| Message / clue | Try |
|----------------|-----|
| `libdevice.tanh` (or similar) | `tl.math.tanh` |
| `libdevice.erf` (or similar) | `tl.math.erf` |
| Other `libdevice.<op>` | `tl.math.<op>` if it exists in your Triton version |

If `tl.math.erf` is still unavailable or lowering fails, a **small analytic approximation** (e.g. tanh-based) was used in one internal case—only when you can accept the numerical tradeoff and document it.

Keep semantics (dtype, masking) identical aside from the call target.

---

## 2. `allow_tf32` deprecated

Older flags such as **`allow_tf32`** may be rejected or deprecated on Ascend Triton.

- Prefer the documented replacement (e.g. **`input_precision='hf32'`** where the API supports it).
- Ensure operands that participate in that path use **float32** as expected by the compiler (cast or construct tensors/parameters in **fp32** so lowering matches intent).
- **TF32-style rounding is often meaningless on Ascend**: if the kernel mixes “TF32 dot” helpers with Ascend constraints, prefer a plain **fp32** dot path and remove TF32-only rounding that does not apply.

---

## 3. Infinity literals and `float32`

If lowering fails with **dtype / inference** issues around special values, ensure **infinity** is visible to the compiler as **float32** (e.g. scalars feeding `tl.full`, masks, or constants). Integer or ambiguous dtypes for `inf` can break inference.

---

## 4. UB overflow → reduce block size

Errors indicating **UB (unified buffer) overflow** or on-chip scratch exhaustion:

- **Reduce** `BLOCK_SIZE`, tile size, or other per-block parameters so each block uses less local/UB budget.
- Re-tune for performance only after correctness is stable.

Related log pattern: UB issues combined with **`hivm.hir.load` / `vcast` / `vsel`** in diagnostics—still try **smaller tiles** first before deeper IR work.

---

## 5. `TypeError: 0d block_type is forbidden` (Ascend)

The Ascend Triton compiler may reject certain **zero-dimensional `block_type`** forms.

**Symptom:** compile-time `TypeError` mentioning **`0d`** and **`block_type`**.

**Direction:**

- Avoid shapes that lower to a forbidden **scalar block** in that position. A pattern that has worked in practice is to materialize the value with an explicit dtype and a **defined** rank, for example:

  ```python
  sxn = tl.broadcast_to(tl.full((), sxn, tl.int64), ())
  ```

  Adapt the **variable name**, **dtype** (`tl.int64` vs `tl.float32`, etc.), and surrounding uses to your kernel. The intent is to replace a naïve 0-D form the compiler rejects with an explicit `tl.full` + `tl.broadcast_to` (or equivalent) so the block type is acceptable.

- This is **context-dependent**; if one reshape does not fix it, simplify how scalars enter loads/stores so they always pass through explicit `tl.full` / broadcasts with clear dtypes.

---

## 6. `while` loops vs bounded `for` + `range`

Many historical **general `while`** / IR **`scf.while`** failures are addressed by **CANN / bisheng upgrades**—prefer upgrading the stack before large kernel rewrites. If loop-related compiler crashes **persist**, try a bounded **`for k in range(...)`** with an explicit step; avoid **`tl.static_range`** that **fully unrolls** a huge trip count (IR blowup / compile timeout).

---

## 7. `tl.view` arguments (shape vs dtype)

**Symptom:** type/shape errors or bogus lowering when reshaping tensors in the kernel.

**Direction:** Confirm **`tl.view`** receives a **shape** (or correct tuple of extents), not a **dtype** where a shape was intended (internal case: `tl.view(a32, tl.int32)`-style mistakes). Match the Triton API for your version.

---

## 8. Chained boolean conditions

**Symptom:** odd failures on boolean-heavy expressions in `@triton.jit` code.

**Direction:** Split **compound boolean** conditions into intermediate masks or simpler tests so lowering is clearer for Ascend (internal case: “chained boolean” refactor in the kernel).

---

## 9. `tl.dot` and mixed dtypes

**Symptom:** compile or runtime issues when **`tl.dot`** mixes **fp16** and **fp32** operands in a path the stack handles poorly.

**Direction:** Align operands explicitly, e.g. **`.to(tl.float32)`** (or your target dtype) on both sides of **`tl.dot`** before the multiply-add, then cast back if needed.

---

## 10. `tl.trans` before `tl.dot` and AI Core alignment

**Symptom:** compile may succeed but execution hits **AI Core `ADDR_MISALIGN`** or similar when **`tl.trans`** participates in a **`tl.dot`** chain.

**Direction:** Change **load layout / pointer indexing** so the tile used in **`tl.dot`** already has the desired orientation—e.g. build **`[T, C]`** strides instead of **`[C, T]`** + **`tl.trans`**, and use **`tl.dot(x_tile, w_tile)`** without transposing one operand. Adjust **masks** to match the new row/column layout. Semantics should stay equivalent; this avoids some bad instruction sequences on NPU.

---

## 11. Numerical mismatch (1 ULP) between Triton and torch on Ascend

**Symptom:** differential test shows non-zero diffs, typically 1 ULP in fp32 scale or
±1 in int8 output, affecting a small percentage (<5%) of rows/elements. Reduction
ops (`tl.max`, `tl.sum`) are already confirmed bit-exact.

**Root cause on Ascend:** Triton keeps `x / CONST` as hardware **divide**
(`__hmf_div`), while torch CANN optimizes it to **multiply** by precomputed
reciprocal (`__hmf_mul`). Ascend's divider and multiplier have **different
rounding** → results differ by 1 ULP for 1-5% of values.

**How to confirm:**
1. Build a kernel with only the reduction (no division): compare `triton_max` vs `torch.abs().max()`. Should be bit-exact.
2. Build kernels for Triton DIV vs Triton MUL vs Torch DIV vs Torch MUL. If Triton MUL == Torch DIV == Torch MUL but Triton DIV differs, the diagnosis is confirmed.
3. Print hex of diff values — should be exactly 1 ULP.

**Fix:**

```python
# Before (differs from Torch):
scale = tl.maximum(row_max_abs / 127.0, 1e-10)

# After (matches Torch bit-exact):
INV_127: tl.constexpr = 1.0 / 127.0
scale = tl.maximum(row_max_abs * INV_127, 1e-10)
```

**Why:** Explicit `*(1.0/CONST)` uses Ascend's **multiplier** (same as Torch CANN),
producing bit-identical results. Also typically faster than division.

**Verify:** re-run differential test — should be 0 diffs.

---

## 12. Masked load still computes out-of-range offsets (MTE DDR out of range)

**Symptom:** runtime crash with `The DDR address of the MTE instruction is out
of range` even though the `tl.load`/`tl.store` carries a `mask`. Typical shapes:
an offset expression shifted by a constant (`(offs + half) * stride` or
`offs - half`), a `BLOCK` wider than the real extent, or scalar loads inside a
Python-style `for` loop.

**Direction:** the Ascend backend may evaluate the full address for masked-out
lanes, so a mask alone does not keep addresses in range. Make every offset
valid by construction:

- Split shifted/rotated access into separate loads over disjoint valid ranges,
  then recombine with `tl.where` on values.
- Keep `BLOCK` no larger than the real extent where possible, or ensure the
  backing allocation covers the padded width.
- Give every load/store a mask and never leave a scalar-loop load unmasked.

---

## 13. Negative static offsets rejected at compile time

**Symptom:** compile error `ConvertTritonIRToLinalgIR error: expected offsets
to be non-negative` when a load uses `offs - HALF_DIM`-style offsets.

**Direction:** all memory-access offsets must be non-negative.

- Preferred: shift the base pointer so offsets stay non-negative
  (`ptr_shifted = ptr - HALF_DIM; tl.load(ptr_shifted + offs, mask=mask)`).
- For dynamic offsets: `safe_offs = tl.maximum(offs - HALF_DIM, 0)` combined
  with a validity mask.
- Or split into segment loads over valid ranges (see entry 12).

---

## 14. int32/int64 mixing in pointer arithmetic

**Symptom:** MTE DDR out-of-range or `ACL stream synchronize failed` errors
that appear only for some shapes (for example when an index extent exceeds the
block width). Often caused by scalar kernel arguments (strides, indices)
inferred as int64 mixing with `tl.arange` int32 offsets.

**Direction:**

- Pass index/stride scalars from the host as int32 (`.to(torch.int32)` or
  `numpy.int32`) and keep in-kernel index arithmetic in a single width.
- Initialize index sentinels as plain Python `int` literals; avoid int64
  tensors as index inputs.
- Avoid `ptr.dtype.element_ty` on Ascend; pass the output dtype as a
  `tl.constexpr` parameter instead.

---

## 15. `tl.load` on an already-loaded tile / scalar extraction

**Symptom:** compile error `unsupported ptr type` when calling
`tl.load(tensor + idx)` where `tensor` is a loaded tile, or
`AttributeError: module 'triton.language' has no attribute 'get_element'`
when extracting scalars from a tile.

**Direction:** `tl.load`/`tl.store` accept pointers, not tiles.

- Reload the data from the base pointer with computed offsets instead of
  slicing an in-register tile.
- Prefer vector operations (`tl.sum`, `tl.where`, vector `tl.atomic_add`)
  over per-element extraction loops; per-version availability of scalar
  extraction helpers varies, so avoiding them is the portable choice.

---

## 16. UB overflow from concurrently live tiles (multi-buffered)

**Symptom:** `MLIRCompilationError: ub overflow, requires X bits while
1572864 bits available` when several tiles (multiple operands plus an
accumulator, or multi-buffered loop tiles) are live at once — distinct from a
single oversized block (entry 4).

**Direction:**

- Count every concurrently live tile (including compiler-inserted
  multi-buffering) against the unified-buffer capacity; the sum, not one tile,
  must fit.
- Shrink the block on the axis with the most live tiles, or split the
  reduction/feature axis into an inner loop so full-width intermediates are
  never materialized.
- Avoid storing large expression results into named temporaries; consume them
  in the expression directly.

---

## 17. `ValueError: Cannot make_shape_compatible` on 1D×2D broadcast

**Symptom:** compile error `Cannot make_shape_compatible: incompatible
dimensions` when multiplying a `[BLOCK_N]` vector by a `[BLOCK_N, D]` tile.

**Direction:** Triton broadcast rules align trailing dimensions; a bare 1D
tensor rarely aligns. Expand explicitly with `p[:, None]` (or `p[None, :]`)
before the operation. If `[:, None]` on a computed tensor is restricted in
your version, rebuild the index with `tl.arange` and expand that, or use
`tl.expand_dims`.

---

## 18. `unsupported AST node type: Break` (break/continue/return)

**Symptom:** compile failure naming `Break`, `Continue`, or an unsupported
`Return` inside `@triton.jit`.

**Direction:** early-exit control flow is not supported. Compute exact loop
bounds and grid extents up front, and neutralize tail lanes with masks
(`tl.where(mask, value, padding)`) instead of exiting early.

