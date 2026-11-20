```
ID:        0021-fold-fp16-and-bf16-casts-into-the-load-and-store-instead-of-a-separate-pass
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-02-reduce-cast.md:34 — "fp32-in-register 的 VF 里，fp16/bf16 的升/降精度可与搬运融合：load 用 B16 UNPACK + Cast 一步升 fp32，store 用 Cast + B32 PACK 一步降回，无独立 Cast pass、无 fp32 中转 UB"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-02-reduce-cast.md:51 — "各 dtype 相对阈值 fp16 2⁻¹⁰ / bf16 2⁻⁷ / fp32 2⁻¹³"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build on a named 950 board in which the load/store-fused cast form shows no
           `aiv_time` reduction against a separate-Cast-pass form at equal precision — or one in
           which the fused form fails the stated relative-error thresholds, which would make it a
           precision change rather than a free win.
```

# 0021 · Fold fp16 and bf16 casts into the load and store instead of a separate pass

## 1 · Claim
Upstream asserts (card vec-02, 性能数据 待实测) three ways to reduce Cast cost: delete the
round trip entirely when the precision standard permits a single-precision chain; merge repeated
casts into one large-granularity conversion at the single point of use; and, in a RegBase VF
whose computation is fp32-in-register, fuse the up-cast into the load
(`DataCopy<..., LoadDist::DIST_UNPACK_B16>` then `Cast`) and the down-cast into the store
(`Cast` then `DataCopy<..., StoreDist::DIST_PACK_B32>`), so there is no separate Cast pass and no
fp32 staging buffer in UB, with the computation body shared across fp16/bf16/fp32 by
`if constexpr`. Upstream asserts the guard: Cast removal must pass the precision regression at
relative thresholds fp16 2⁻¹⁰, bf16 2⁻⁷, fp32 2⁻¹³. Not established here.

## 2 · The wrong branch this removes
An agent that sees a Cast-dense profile (0016) reaches for the obvious repair — drop to a single
precision throughout — and breaks accumulation-sensitive operators, because reductions and
softmax denominators need the wide intermediate. The card's ordering matters: after A (delete)
is admissible only under a precision standard; after B (merge) is the fallback for the
accumulation case; after C (fuse into the transfer) is the one that costs nothing numerically,
because the same conversions still happen — they simply stop occupying independent VECTOR
instructions and stop needing an fp32 buffer in UB. An agent that knows only A will either
break precision or, told that precision matters, conclude nothing can be done.

## 3 · Ground / Source
`vec-02:6-9` diagnostic: conversion instructions (`vcvt_f2f`/`vcvt_f2s`/`vcvt_s2f`) above 20% of
the VECTOR lane; a one-or-two-instruction computation wrapped in an in-and-out Cast pair, where
Cast can be 30–50% of total VEC time; high `aiv_vec_ratio` whose busy time comes from conversion
rather than useful arithmetic.

`vec-02:33-43`, after C, quoted with its code because the API spelling is the load-bearing part:

> - fp32-in-register 的 VF 里，fp16/bf16 的升/降精度可与搬运融合：load 用 B16 UNPACK + Cast
>   一步升 fp32，store 用 Cast + B32 PACK 一步降回，无独立 Cast pass、无 fp32 中转 UB。
> ```cpp
> DataCopy<bfloat16_t, MicroAPI::LoadDist::DIST_UNPACK_B16>(xBf16, inUb + off);
> Cast<float, bfloat16_t, castTraitB162B32>(vregIn, xBf16, preg);
> Cast<bfloat16_t, float, castTraitB322B16>(yBf16, vregOut, preg);
> DataCopy<bfloat16_t, MicroAPI::StoreDist::DIST_PACK_B32>(outUb + off, yBf16, preg);
> ```

Stop rules `vec-02:49-53`: confirm the precision standard before deleting a Cast (thresholds as
quoted); accumulation-type operators keep the fp32 intermediate and use after B; narrowing a cast
(int32→int16) requires the value range to be proven inside the target type. Source and case,
`vec-02:57`: RoPE arch35 `LoadTwoTensorForDtypeT`/`StoreOneTensorForDtypeT`.

An independent-origin observation about the API names, recorded in §3 and not lifted into §1: a
read-only grep of the installed CANN 9.0.0-beta.2 headers finds
`Reg::DataCopy<srcT, Reg::LoadDist::DIST_UNPACK_B16>` in
`arm64-linux/asc/impl/adv_api/detail/quantization/quant/ascend_quant_l300_impl.h:155`, i.e. the
load-distribution spelling the card uses exists in the vendor tree and is used there for the same
purpose. That corroborates the spelling; it corroborates nothing about the speed-up.

## 4 · Procedure
Later phase, needs a card; board token from the driver readout; device selection per 0010 with
occupancy recorded either side.
1. Build one bf16 elementwise operator three ways from a common tree: (P) separate Cast pass via
   an fp32 UB buffer; (M) merged single large-granularity Cast (after B); (C) cast fused into
   load and store (after C). Confirm builds are distinct and each is reproducible by `md5sum`.
2. Sweep the row length over four values spanning a factor of 16, including one shorter than a
   single VL so the VF start-up cost is visible.
3. Capture `aiv_time`, `aiv_vec_ratio`, and the VECTOR-lane conversion share (0016's grouping)
   for each build; five repetitions, median and spread; record peak UB usage per build.
4. Run the precision regression on all three, recording the maximum relative error per dtype
   against the stated thresholds, not merely pass/fail.

## 5 · Checker — acceptance declared before the run
Verdict variables: `gain_C = (aiv_time(P) − aiv_time(C))/aiv_time(P)`, `cast_share(C)`, and
`maxRelErr(C)` per dtype. Acceptance: `gain_C > spread`, `cast_share(C)` at least halved against
P, and `maxRelErr(C) <= 2^-7` for bf16 and `2^-10` for fp16. All three must hold; a time gain
with an unchanged conversion share means the gain came from something else and the attribution
fails even though the number is good.

Exit code is not the verdict; the precision harness exits 0 on a passing case and on a case it
skipped. The checker asserts the number of compared elements is the full output size, and reports
`regression_skipped` otherwise — a precision check that silently compares nothing is the blind
species this book names.

Red input: build P at the shortest row length, where the VF start-up cost may exceed the saved
conversions. If `gain_C` is negative there, that is the card's own stop rule (尾段单次 lane < 32
的短向量不值得改, vec-03:55) confirmed, and it is reported rather than excluded.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; the card's own evidence line is 待实测 and the 30–50% figure carries no case
identity. The precision thresholds are asserted, not verified, and this book has bound no
precision harness. Nothing here establishes that the fused form is available for every dtype
pair — only bf16/fp16 against fp32 are named — nor that `DIST_UNPACK_B16`/`DIST_PACK_B32` behave
identically across CANN versions. A5/arch3510 RegBase only, per the card library's own fence; no
board token is established, and nothing transfers to the 910 book.
