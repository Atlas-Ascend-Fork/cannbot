# Numerical-precision methodology (a5 reg/micro kernels)

Generalized precision discipline for reduction / normalization / softmax / quantization
kernels. These are recurring practices in production arch35 norm/softmax/quant kernels; ignore
them and a kernel can pass a small smoke test yet fail evaluation precision on real shapes.

---

## 1. Accumulate in fp32, regardless of I/O dtype

Even when inputs/outputs are bf16 or fp16, do every **accumulation, mean, variance, and
normalization statistic in fp32**: cast to fp32 once on load, do all arithmetic in fp32, cast
back to the narrow dtype only at store. Long accumulation chains in bf16/fp16 lose bits fast.
> Study: `ops-nn-master/norm/rms_norm/op_kernel/arch35/rms_norm_regbase_common.h` → `ComputeFormer`;
> `ops-nn-master/norm/add_layer_norm/op_kernel/add_layer_norm_base.h` → `ReduceSumFP32`.

## 2. Subtract the max before `exp` (softmax stability)

For softmax/log-sum-exp, reduce-max across the reduction axis first, then compute `exp(x - max)`,
not `exp(x)`. The max is broadcast and reused in the denominator. Without it, `exp` overflows.
> Study: `ops-nn-master/activation/softmax_cross_entropy_with_logits/op_kernel/arch35/softmax_cross_entropy_with_logits_full_load.h` → `VfReduceMax`, `VfSubExp`.

## 3. Add epsilon before `sqrt` / reciprocal

Compute `rsqrt(var + eps)` / `1/sqrt(sum_sq/n + eps)` — add the epsilon **after accumulation,
before the sqrt/reciprocal** — to avoid divide-by-zero and denormal blow-up on tiny variance.
> Study: `ops-nn-master/norm/rms_norm/op_kernel/arch35/rms_norm_regbase_common.h` → `ComputeRstd`;
> `ops-nn-master/norm/rms_norm_quant/op_kernel/rms_norm_quant.h` → `FigureOutNorm`.

## 4. Clamp + saturate before a quantizing cast

When quantizing fp→int8, **clamp the value to `[qmin, qmax]` before the cast** (e.g. `vmaxs` to
qmin then `vmins` to qmax) and use a saturating cast config. Otherwise out-of-range values wrap
or produce NaN instead of saturating.
> Study: `ops-nn-master/norm/rms_norm_quant/op_kernel/rms_norm_quant.h` → `CastFromF16ToI8`,
> `ComputeFp16ToI8Quant`.

## 5. Store reduction statistics (mean / rstd) as fp32

Emit `mean` and `rstd` (and similar intermediate statistics) to GM as **fp32 even when the main
tensors are bf16/fp16** — the backward pass needs the precision. Reserve fp32 GM buffers for them
in the op contract.
> Study: `ops-nn-master/norm/add_layer_norm/op_kernel/add_layer_norm_kernel.h`;
> `ops-nn-master/norm/rms_norm/op_kernel/arch35/rms_norm_regbase.h`.

## 6. Pick the rounding mode by target dtype

Narrowing casts need a deliberate rounding mode: bf16 typically uses round-to-nearest-even
(`RoundMode.CAST_RINT`) to avoid bias; fp16 paths sometimes truncate (`CAST_NONE`). Set it in the
`CastConfig`, don't rely on a default.
> Study: `ops-nn-master/norm/rms_norm_quant/op_kernel/rms_norm_quant.h` → `CastFrom32To16`.

## 7. Multi-level (tree) reduction for large axes

For a reduction axis larger than one register span, reduce in stages: reduce a register-width
chunk to a partial, accumulate partials, then reduce the partials — instead of one long chain.
This both fits the hardware and reduces long-chain rounding error. Barrier between levels when
the partials live in UB.
> Study: `ops-nn-master/norm/rms_norm/op_kernel/arch35/rms_norm_regbase_common.h` → `ReduceSumImpl`,
> `ComputeMultiLevelReduce`.

## 8. Amortize the quant scale as a reciprocal

When dequantizing, compute `inv_scale = 1/scale` once in fp32 and multiply, rather than dividing
per element. One reciprocal beats N divides and is numerically consistent across the tile.
> Study: `ops-nn-master/norm/rms_norm_quant/op_kernel/rms_norm_quant.h` → `GetScaleAndOffset`.

---

## Honest scope note

Production arch35 code (as surveyed) uses the **two-pass** forms above — reduce-max then exp,
accumulate-then-normalize. **Online / single-pass algorithms** (online-softmax with running
max+rescale, Welford mean/variance, compensated/Kahan summation) were **not** observed in these
repos. Don't assume an online variant is available or expected; the two-pass discipline is the
documented norm. If a kernel genuinely needs online softmax (e.g. flash-attention-style), treat
it as new ground and validate carefully rather than copying a non-existent reference.
