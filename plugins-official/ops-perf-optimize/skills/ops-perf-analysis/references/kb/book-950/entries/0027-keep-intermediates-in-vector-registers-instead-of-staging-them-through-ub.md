```
ID:        0027-keep-intermediates-in-vector-registers-instead-of-staging-them-through-ub
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-05-eliminate-ub-staging.md:14 — "能在向量寄存器里直接接力的就不要落 UB 再读回。省掉中转 UB buffer、缩短 VF prologue、减一来一回的 load/store，并消除 `LocalMemBar` 的流水排空"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board where the register-resident form is not faster
           than the UB-staged form beyond run spread on a row-reduction operator — the staging
           round trip and its two barriers would then not be on the critical path.
```

# 0027 · Keep intermediates in vector registers instead of staging them through UB

## 1 · Claim
Upstream asserts (card vec-05, 性能数据 待实测) that values which can be relayed inside the
vector registers should not be written to UB and read back, and gives three forms of the repair:
(A) delete an fp32 pre-cast staging buffer and cast at the single point of use, dispatching by
C++ overload instead of an upper-layer `if constexpr`; (B) replace "reduce to lane 0 → store to a
UB slot → `LocalMemBar` → broadcast-load" with an in-register `Reduce` followed by `Duplicate`,
removing two pipeline drains and the scratch buffer; (C) replace UB→UB shuffling for offset or
interleave patterns with two offset loads into separate registers plus in-register
`DeInterleave`/`Interleave`/`Muls(-1)`. Not established here.

## 2 · The wrong branch this removes
UB staging is the natural way to write these kernels, because a UB tensor is addressable and a
register is not: the value is produced by one API and consumed by another, and a `LocalTensor` is
the type both accept. The costs are invisible at the source level — a scratch allocation that
shrinks the tile budget, a VF prologue that grows, a store and a broadcast-load per row, and two
`LocalMemBar` calls whose entire function is to drain the pipeline. On a row-reduction kernel
(softmax, RMSNorm) this happens once per row, so the drain frequency scales with the row count.
An agent looking at the profile sees a busy MTE3/MTE2 pair and treats it as a memory problem,
when the traffic is entirely internal to UB and can be deleted rather than optimised.

## 3 · Ground / Source
`vec-05:6-10` diagnostic: store→load round trips between MTE3 and MTE2 in two shapes —
pre-cast staging (cast to fp32 into a temporary UB, then load it back) and row-reduction scalar
broadcast staging (`Reduce` to lane 0 → write a UB slot → `LocalMemBar` → broadcast-read), which
the card calls the common IPC killer of softmax/norm/RMS.

Form B, `vec-05:25-35`, quoted because it is the compact statement of the whole card:
> // before：写 UB → LocalMemBar → broadcast-load（2 barrier + UB scratch）
> Reduce<ReduceType::MAX>(vRed, vMaxAcc, preg);
> DataCopy<float, StoreDist::DIST_FIRST_ELEMENT_B32>(scratch, vRed, preg);
> LocalMemBar<MemType::VEC_STORE, MemType::VEC_LOAD>();
> DataCopy<float, LoadDist::DIST_BRC_B32>(vMaxBrc, scratch);
>
> // after：寄存器内归约到 lane0，再 Duplicate 就地广播到全 lane
> Reduce<ReduceType::MAX>(vMaxBrc, vMaxAcc, preg);   // lane0 = 行 max
> Duplicate(vMaxBrc, vMaxBrc, preg);                 // 广播到全 lane，无 barrier/UB

Form C, `vec-05:41-59`, replaces a rotate-half implemented as two UB→UB `DataCopy` calls plus a
whole-block `Muls(sin, sin, -1.0, len)` pre-pass with two offset loads (`Load2`) and six register
operations; the interleaved variant uses `DeInterleave` / `Muls(-1)` / `Interleave` with nothing
landing in UB.

Stop rules, `vec-05:66-70`: a staging buffer reused elsewhere must not be deleted — check each
use; overload dispatch must cover every dtype combination actually built; after form B the
`Reduce` result is in lane 0 and must be `Duplicate`d before element-wise use; and if a UB round
trip is genuinely kept, the `LocalMemBar` between store and broadcast-load is mandatory — that
last is entry 0028, because its failure mode is not slowness. Cases at `:74`: qli-arch35 (form
A), hc-pre per-row softmax (form B), RoPE arch35 `HalfAlignVF`/`InterleaveModeVF` (form C).

Namespace caveat stated by the card itself at `:60` and `:70`: `DeInterleave`/`Interleave`/
`UpdateMask`/`RegTensor` are `AscendC::MicroAPI::` in the RoPE sources but some CANN builds expose
them as `AscendC::Reg::`, and in this repo's CANN (cann-9.0.0-beta.2) `LocalMemBar`/`MemType` are
in `AscendC::Reg`. A read-only grep of the installed cann-9.0.0-beta.2 headers is consistent with
the latter: `Reg::LocalMemBar<Reg::MemType::VEC_STORE, Reg::MemType::VEC_LOAD>()` appears in
`impl/adv_api/detail/math/fmod/fmod_c310_impl.h:207`. That corroborates the namespace, not the
performance claim.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one per-row softmax two ways from a common tree: (S) staged — reduce, store to scratch,
   `LocalMemBar`, broadcast-load; (Rg) register-resident — `Reduce` then `Duplicate`. Record
   `md5sum` for both and for rebuilds.
2. Sweep row count over four values spanning 32× at fixed row length; record peak UB usage per
   build, since the deleted scratch is part of the claimed benefit.
3. Capture `aiv_time`, `aiv_vec_ratio`, `aiv_mte2_ratio`, `aiv_mte3_ratio`; five repetitions,
   median and spread; count `LocalMemBar` occurrences in the disassembly of each build.
4. Repeat the whole comparison for form C on a rotate-half kernel, separately, so the two forms
   are never reported as one number.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(rows)`, `barriers(build)` from the disassembly, and `ub_peak(build)`.
Acceptance: `barriers(Rg) < barriers(S)`, `ub_peak(Rg) < ub_peak(S)`, and `gain` positive beyond
spread and increasing with row count. All three, because the card claims all three; a time gain
with an unchanged barrier count is unattributed.

Exit code is not the verdict — both builds run. Outputs are compared bit-exactly against a
reference over the full buffer; a register-resident reduction that is faster and wrong is a
failure, and the ordering of `Reduce` before `Duplicate` is exactly the kind of change that can
produce a lane-0-only result silently.

Red input: build S with the `LocalMemBar` deliberately removed (the 0028 case). Its output must
fail the bit-exact comparison. If it passes, the shape set does not exercise the hazard and no
conclusion about barriers is admissible from this run.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; 待实测 upstream. The three forms are different mechanisms with different risks
and this entry does not establish that a result for one transfers to another. No board, no shape,
no operator family. Register pressure is not addressed: keeping more values in registers is the
direct cause of the spill problem in 0036, and nothing here establishes where the trade turns.
The namespace observation is toolkit-specific and says nothing about another CANN version. Per
RULES.md Art. 1, nothing transfers to the 910 book.
