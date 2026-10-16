# Membase → Regbase migration (a5 escape hatch when easyasc DSL is limited)

The easyasc a5 DSL exposes only part of the MicroAPI surface (see `dsl_coverage_and_gaps.md`).
When a kernel needs a primitive the DSL lacks, codegen falls back to **membase** AscendC
programming (whole-UB `LocalTensor` + the `AscendC::*` vec API) instead of a **regbase** `@vf`
(register-level `__VEC_SCOPE__` + `MicroAPI`/`AscendC::Reg::*`). Membase is correct but leaves the
register VF performance on the table.

This doc is the **escape-hatch workflow**: get a correct membase kernel first, then incrementally
lift its hot compute into regbase VF, re-verifying bit-exact at every step, and leave only the
genuinely non-convertible regions on the membase path.

Use alongside: `reg_vf_skeleton.md` (the VF target shape), `arch35_micro_reference.md` (exact
MicroAPI semantics), `dsl_coverage_and_gaps.md` (which gaps force membase), `micro_perf_rules.md`
(tune after the lift).

## Playbook (phased, bit-exact-gated)

A phased, **bit-exact-gated** workflow for taking a kernel that was generated as AscendC
*membase* (whole-UB `LocalTensor` vec API) and incrementally lifting its hot compute regions to
*regbase* (`__VEC_SCOPE__` + `RegTensor` + MicroAPI / `Reg::` ops). The membase version is the
**golden reference** for the entire migration; regbase is validated against it after every step.

> Namespace convention (from `arch35_micro_reference.md` §1): element-wise arithmetic, unary
> math, reductions, compare, and select are `AscendC::Reg::*` (`__simd_callee__` in
> `namespace AscendC::Reg`). Data movement, `Cast`, gather/scatter, mask creation, and
> `Histograms` are `AscendC::MicroAPI::*`. The two are not interchangeable — see `mapping_md`.

## Phase 0 — WHEN to trigger this workflow
1. Trigger only when the **easyasc a5 DSL cannot express the kernel** at the `@vf` micro level
   and codegen fell back to (or you hand-wrote) AscendC membase. Concretely:
   - A required primitive is a genuine `easyasc.a5` gap (`dsl_coverage_and_gaps.md` §2 / §1F):
     `Histograms`, unaligned load/store, `Squeeze` count-readback, fused ops, per-lane shift, etc.
   - Or `run_codegen` produced AscendC membase instead of a `@vf` reg kernel.
2. **Do NOT trigger** if the op is already covered by the DSL surface
   (`dsl_coverage_and_gaps.md` §1). Most reg/micro methodology IS exported (`ub_to_reg`,
   `cast`+`CastConfig`, `cadd`/`cgadd`, `gather_mask`, `mask_xor`, atomics, cube<->vec handshake).
   Re-author in the DSL instead of doing a manual membase->regbase lift.
3. The output of this workflow is a kernel that is **mostly regbase** with a documented residual
   of membase regions that have no MicroAPI counterpart.

## Phase 1 — Establish the membase golden baseline (the immovable reference)
1. Get the membase kernel compiling and **passing precision** with the AscendC `LocalTensor` vec
   API. This is the canonical skeleton:
   `TPipe::InitBuffer` for `TQue`/`TBuf` -> loop over tiles: `CopyIn` (GM->`LocalTensor` via
   `TQue::AllocTensor` + `DataCopy`/`DataCopyPad` + `EnQue`) -> `Compute` (`AscendC::Add/Mul/...`,
   `ReduceSum`, `Cast`, `Duplicate`, `PipeBarrier<PIPE_V>()`) -> `CopyOut` (`DeQue` +
   `DataCopy`/`DataCopyPad` -> GM + `FreeTensor`). Double-buffer with `BUFFER_NUM=2`.
2. Validate precision against the PyTorch reference (`numerical_precision.md` thresholds). Record
   the exact tolerance, dtype, and shapes used.
3. **Freeze this binary/output as the golden.** Every later regbase step must reproduce it
   **bit-exact** (not just within tolerance — bit-exact vs the membase output, so any drift is a
   real regression introduced by the lift, not accumulated fp noise).
4. Do not delete the membase compute. Keep each region behind a switch (e.g. a compile flag or a
   sibling function) so you can A/B the membase region vs its regbase replacement.

## Phase 2 — Identify the VF-convertible compute regions
1. Walk the membase `Compute()` body and bucket every op against `mapping_md`:
   - **Convertible**: has a 1:1 `Reg::*`/`MicroAPI::*` counterpart (Add/Sub/Mul/Div, Max/Min,
     And/Or/Xor, Exp/Ln/Sqrt/Abs/Relu, Cast, Duplicate, Compare/Select, ReduceSum/Max/Min,
     DataCopy load/store).
   - **Convertible-with-rewrite**: scalar ops `Adds`/`Muls`/`Maxs`/`Mins` — no direct reg scalar
     form; rewrite as `Reg::Duplicate` (broadcast scalar) + the vector op.
   - **Stays membase**: anything in `stays_membase_md` (no MicroAPI counterpart).
2. A region is a contiguous run of convertible ops that share the same residency and tail/mask
   handling — pick regions that start at a UB load and end at a UB store, so the lift is a clean
   `Load -> compute -> Store` island (see Phase 3 wrapping pattern).
3. Prefer regions on the hot path; small once-per-kernel ops are not worth the lift.
4. Confirm each candidate op's exact semantics/argument order in `arch35_micro_reference.md` §1
   before converting — name divergence is real (`vmax`->`Max`, `dup`->`Duplicate`).

## Phase 3 — Incrementally lift ONE region at a time (re-verify after EACH)
For each convertible region, in isolation:
1. **Signature**: introduce a `__VEC_SCOPE__`-wrapped helper (a `_vf` function) that takes
   `__ubuf__ T*` raw pointers for the region's inputs/outputs instead of `LocalTensor`/`TPipe`.
2. **Tensors**: replace the region's `LocalTensor<T>` with `MicroAPI::RegTensor<T>` declared
   **once at the top of the scope** (1-4 per type, e.g. `x_regs[4]`), never inside the loop
   (`reg_vf_skeleton.md` §1).
3. **Mask**: build one master mask via `MicroAPI::CreateMask<T>(MaskPattern::ALL())` or, for
   tail-correct loops, `MicroAPI::UpdateMask<T>(count)` each iteration. Pass it to every op in the
   region (`reg_vf_skeleton.md` §2). Mask dtype must match the RegTensor dtype.
4. **Load/store wrapping** (the core residency change): wrap the region as
   `MicroAPI::DataCopy`/`LoadAlign` (UB -> RegTensor) at the top, the `Reg::*`/`MicroAPI::*`
   compute in the middle, `MicroAPI::DataCopy`/`StoreAlign` (RegTensor -> UB) gated by the mask at
   the bottom. Residency is strictly `GM <-DataCopy-> UB <-LoadAlign/StoreAlign-> RegTensor`.
5. **Op rewrite**: translate each op per `mapping_md`. Drop the membase `count` arg (folds into the
   mask) and the shape/mask metadata; reductions become `Reg::Reduce<ReduceType::SUM/MAX/MIN>`;
   broadcast a reduced scalar back with `Reg::Duplicate`.
6. **Loop / pipeline**: collapse the membase `CeilDiv(tile,64)` inner tiling and
   `PipeBarrier<PIPE_V>()` into register-array indexing; remove SEvent/`EnQue`/`DeQue` pipeline
   events for the lifted region. Keep copy<->compute ordering correct (`reg_vf_skeleton.md` §4).
7. **Re-verify bit-exact** against the Phase-1 golden immediately, with only this one region
   converted. If it diverges, the bug is local to this region — debug before lifting the next.
   Common divergence causes: mask dtype/width mismatch, wrong `RoundMode`/`CastTrait` on `Cast`,
   missing `Duplicate(dst,0,ALL)` before a masked write or before a reduce, stale UB read (missing
   barrier between a copy and the consuming compute). See `arch35_micro_reference.md` §3 pitfalls.
8. Only after bit-exact passes, proceed to the next region. Never lift two regions in one step.

## Phase 4 — Leave genuinely non-convertible regions as membase (document why)
1. Regions whose ops appear in `stays_membase_md` stay on the AscendC `LocalTensor` path. The final
   kernel is a hybrid: regbase islands inside an otherwise membase shell (or vice versa), with UB
   as the handoff buffer between them.
2. At each membase<->regbase boundary, ensure the residency handoff is correct: a regbase island
   `StoreAlign`s to UB, then the membase side `DataCopy`s from that UB (and order the two with a
   barrier). Bit-exactness here is the cross-check that the handoff is right.
3. Document each retained membase region with: the blocking op, the matching `dsl_coverage_and_gaps.md`
   gap ID (e.g. P0 Histograms, P1 unaligned, P2 fused), and the emulation cost if it were forced
   into regbase. This keeps future migrators from re-attempting an impossible lift.
4. Final acceptance: whole-kernel output is bit-exact vs the Phase-1 membase golden, and the
   regbase coverage + residual-membase rationale are recorded.
---

## Membase (AscendC `LocalTensor`) -> Regbase (MicroAPI / `Reg::`) op mapping

Residency for every row: membase operands are `LocalTensor` in **UB**; regbase operands are
`RegTensor`/`MaskReg` in **registers**, inside a `__VEC_SCOPE__`. The membase `count` argument is
**always** replaced by a `MaskReg` (`CreateMask`/`UpdateMask`); shape/mask metadata is dropped.
No per-op load/store wrapping is needed for compute ops once operands are reg-resident — only the
region's edges do `LoadAlign`/`StoreAlign`. `<mode>` = `MaskMergeMode` (`ZEROING` default /
`MERGING`).

| Membase op | Regbase counterpart | What changes (residency / mask / load-store) |
|---|---|---|
| `AscendC::Add(dst,s0,s1,count)` | `AscendC::Reg::Add<T,mode>(dReg,s0Reg,s1Reg,mask)` | UB->reg; `count`->`mask`; no load/store wrap inside scope |
| `AscendC::Sub(dst,s0,s1,count)` | `AscendC::Reg::Sub<T,mode>(dReg,s0Reg,s1Reg,mask)` | UB->reg; `count`->`mask` |
| `AscendC::Mul(dst,s0,s1,count)` | `AscendC::Reg::Mul<T,mode>(dReg,s0Reg,s1Reg,mask)` | UB->reg; `count`->`mask` |
| `AscendC::Div(dst,s0,s1,count)` | `AscendC::Reg::Div<T,mode>(dReg,s0Reg,s1Reg,mask)` | UB->reg; `count`->`mask` |
| `AscendC::Max(dst,s0,s1,count)` | `AscendC::Reg::Max<T,mode>(dReg,s0Reg,s1Reg,mask)` | UB->reg; `count`->`mask` |
| `AscendC::Min(dst,s0,s1,count)` | `AscendC::Reg::Min<T,mode>(dReg,s0Reg,s1Reg,mask)` | UB->reg; `count`->`mask` |
| `AscendC::And(dst,s0,s1,count)` | `AscendC::Reg::And<T,mode>(dReg,s0Reg,s1Reg,mask)` | UB->reg; bitwise; `count`->`mask` |
| `AscendC::Or(dst,s0,s1,count)` | `AscendC::Reg::Or<T,mode>(dReg,s0Reg,s1Reg,mask)` | UB->reg; bitwise; `count`->`mask` |
| `AscendC::Xor(dst,s0,s1,count)` | `AscendC::Reg::Xor<T,mode>(dReg,s0Reg,s1Reg,mask)` | UB->reg; bitwise; `count`->`mask` |
| `AscendC::Exp(dst,src,count)` | `AscendC::Reg::Exp<T,mode>(dReg,sReg,mask)` | UB->reg; `count`->`mask` |
| `AscendC::Ln(dst,src,count)` | `AscendC::Reg::Ln<T,mode>(dReg,sReg,mask)` | UB->reg; `count`->`mask` (natural log only) |
| `AscendC::Sqrt(dst,src,count)` | `AscendC::Reg::Sqrt<T,mode>(dReg,sReg,mask)` | UB->reg; `count`->`mask` |
| `AscendC::Abs(dst,src,count)` | `AscendC::Reg::Abs<T,mode>(dReg,sReg,mask)` | UB->reg; `count`->`mask` |
| `AscendC::Relu(dst,src,count)` | `AscendC::Reg::Relu<T,mode>(dReg,sReg,mask)` | UB->reg; `count`->`mask` |
| `AscendC::Duplicate(dst,scalar,count)` | `AscendC::Reg::Duplicate<T[,mode]>(dReg,scalar[,mask])` | UB->reg; scalar broadcast; `count`->optional `mask` |
| `AscendC::Adds(dst,src,scalar,count)` | **no direct reg form** — `Reg::Duplicate(tmpReg,scalar)` + `Reg::Add(dReg,sReg,tmpReg,mask)` | scalar must be broadcast to a RegTensor first |
| `AscendC::Muls(dst,src,scalar,count)` | **no direct reg form** — `Reg::Duplicate` + `Reg::Mul` | broadcast scalar then vector mul |
| `AscendC::Maxs(dst,src,scalar,count)` | **no direct reg form** — `Reg::Duplicate` + `Reg::Max` | broadcast scalar then vector max |
| `AscendC::Mins(dst,src,scalar,count)` | **no direct reg form** — `Reg::Duplicate` + `Reg::Min` | broadcast scalar then vector min |
| `AscendC::Cast(dst,src,roundMode,count)` | `AscendC::MicroAPI::Cast<DstT,SrcT,CastTrait>(dReg,sReg,mask)` | UB->reg; `roundMode` moves into `CastTrait{RegLayout,SatMode,MaskMergeMode,RoundMode}`; narrowing needs `CAST_RINT`; mixed-precision needs UnPack(load)/Pack(store) sandwich |
| `AscendC::Compare(dst,s0,s1,count)` (bool out) | `AscendC::Reg::Compare<T,CMPMODE>(dMask,s0Reg,s1Reg,mask)` | bool `LocalTensor` out -> `MaskReg` out; `count`->`mask` |
| `AscendC::Compares(dst,src,scalar,count)` | `AscendC::Reg::Compares<T,CMPMODE>(dMask,sReg,scalar,mask)` (verify arg order; else `Duplicate`+`Compare`) | bool out -> `MaskReg`; scalar built-in; `count`->`mask` |
| `AscendC::Select(dst,selMask,s0,s1,count)` | `AscendC::Reg::Select<T>(dReg,s0Reg,s1Reg,mask)` | UB mask+operands -> `MaskReg`+RegTensor; `count`->`mask`; verify true/false arg order |
| `AscendC::ReduceSum(dst,src,workLocal,count)` | `AscendC::Reg::Reduce<ReduceType::SUM,T,mode>(dReg,sReg,mask)` | UB->reg; no `workLocal`; result in lane 0 — pre-`Duplicate(dst,0)` and ensure mask covers lane 0 |
| `AscendC::ReduceMax(dst,src,count)` | `AscendC::Reg::Reduce<ReduceType::MAX,T,mode>(dReg,sReg,mask)` | UB->reg; result lane 0; broadcast back with `Reg::Duplicate` |
| `AscendC::ReduceMin(dst,src,count)` | `AscendC::Reg::Reduce<ReduceType::MIN,T,mode>(dReg,sReg,mask)` | UB->reg; result lane 0 |
| `AscendC::DataCopy(dstLocal,srcGM,p)` / `DataCopyPad(...)` | `AscendC::MicroAPI::LoadAlign<T,LoadDist>(dReg,srcAddr)` (or `Load` for unaligned) inside `__VEC_SCOPE__` | residency split: GM->UB stays membase `DataCopy`; the new edge is UB->reg via `LoadAlign`; `LoadDist` (`DIST_NORM`/`DIST_DS_*`/unpack...) replaces block/stride params |
| `AscendC::DataCopy(dstGM,srcLocal,p)` | `AscendC::MicroAPI::StoreAlign<T,StoreDist>(dstAddr,sReg,mask)` inside `__VEC_SCOPE__` | reg->UB store gated by `MaskReg`; UB->GM stays membase `DataCopy`; `StoreDist` controls pack/interleave |
| `AscendC::PipeBarrier<PIPE_V>()` | removed inside the lifted region | reg ops are sequential; replace cross-pipe ordering with `LocalMemBar`/`bar_v` only at UB<->reg handoffs |
---

## Common before/after shapes (generalized)

These are the recurring membase→regbase transformation shapes. (Concrete before/after kernels live
in per-run workspaces, not in this skill — within an easyasc workspace the membase fallback is
typically `op_kernel/kernel_vec.h` using `LocalTensor` + `GM2UBPAD`/`UB2GMPAD`, and the regbase lift
is a sibling `op_kernel/<name>_vf.h` using `__VEC_SCOPE__` + `RegTensor`.)

1. **Fused norm + quant** (mixed precision, reduce, cast): per-row UB tiles → register arrays;
   `WholeReduceSum` → `Reg::Reduce<SUM>`; `CeilDiv` tile counts + `PipeBarrier<PIPE_V>` → raw register
   indexing; pipeline events removed. Cast keeps the UnPack(load)/Pack(store) sandwich.
2. **Iterative row/col normalization** (exp, reduce, broadcast-div): `BlockReduceMax/Sum` + mask +
   `CeilDiv` → `Reg::Reduce<MAX/SUM>`; broadcast the reduced scalar back with `Reg::Duplicate`;
   the whole block lives in a few `RegTensor` chunks instead of UB tiles.
3. **LUT / gather conversion + conditional select**: intermediate UB staging eliminated; the
   compute helper takes `__ubuf__ T*` raw pointers; table lookup becomes `MicroAPI::DataCopyGather`
   (byte-offset indices); the conditional path becomes `MicroAPI::Select` on a `MaskReg`.
4. **Histogram-style / all-register**: full residency move to registers, `MicroAPI` throughout —
   but this shape usually *cannot* be reached from the DSL (it needs `Histograms`/`DeInterleave`),
   so it is the canonical case that stays membase or requires hand-written AscendC (see below).

**Cast load/store-wrapping idiom** (the unit of a single lifted region), inside `__VEC_SCOPE__`:

```cpp
MicroAPI::RegTensor<SrcT> vIn;
MaskReg m = MicroAPI::UpdateMask<SrcT>(count);
MicroAPI::DataCopy<SrcT, LoadDist>(vIn, srcAddr);      // UB -> reg
MicroAPI::Cast<DstT, SrcT, CastTrait>(vOut, vIn, m);   // compute in reg
MicroAPI::DataCopy<DstT, StoreDist>(dstAddr, vOut, m); // reg -> UB (mask-gated)
```

One `MaskReg` from `UpdateMask` drives load, compute, and store of the region.

---

## What must stay membase (no MicroAPI counterpart)

These ops/regions have **no regbase counterpart** that preserves semantics, so the region that
uses them stays on the AscendC `LocalTensor` path. Each ties to a `dsl_coverage_and_gaps.md` gap;
keep the region membase and document the gap ID. (Distinct from the *convertible-with-rewrite*
scalar ops `Adds`/`Muls`/`Maxs`/`Mins`, which DO have a `Reg::Duplicate`+vector-op path — those
do not belong here.)

### Genuine gaps — keep membase
- **Histograms / bucketing** — `dsl_coverage_and_gaps.md` §2 **P0** (`arch35_micro_reference.md`
  §1D `Histograms`, §1F). No histogram primitive on the a5 surface; radix-sort digit counting and
  index-repetition statistics block here. (A hand-written regbase kernel *can* call
  `MicroAPI::Histograms` directly at the C++ MicroAPI level — that is exactly the instruction the
  DSL fails to expose, which is why such kernels fall back to membase / hand-written AscendC in the
  first place.)
- **Unaligned load/store family** — `dsl_coverage_and_gaps.md` §2 **P1** (`LoadUnAlign*`,
  `StoreUnAlign*`, `UnalignReg`). Membase relies on aligned load + host-side padding. Neighbor-window
  / compaction-with-misaligned-edges regions stay membase unless rewritten to aligned-load+sentinel.
- **Compact-with-count** — `dsl_coverage_and_gaps.md` §2 **P1** + `arch35_micro_reference.md` §1B
  (`Squeeze`/`gather_mask` has no surviving-count readback; `GetSpr`/`ClearSpr` not exposed). A
  variable-size filtered output whose length must be read back stays membase.
- **Fused ops** — `dsl_coverage_and_gaps.md` §2 **P2** + §1F: `MulAddDst` (`dst += s0*s1`),
  `MulsCast`, `AbsSub` (`|s0-s1|`), `ExpSub` (`exp(s0-s1)`), `Truncate`. Emulatable with the
  primitive pair (correct, more instructions) — only lift if hot; otherwise leave membase.
- **`Log`/`Log2`/`Log10` (non-natural log)** — only `Reg::Ln` (natural log) is reliable in the
  reg surface for the migration; arbitrary-base log unary regbase variants are not assumed present.
  Keep base-10/2 log regions membase unless verified against `arch35_micro_reference.md` §1D.
- **`Neg`, `Not` (bitwise)** — treat as not-available for the lift unless confirmed; the cited
  reg surface lists `Not`(unary)/`Neg` but findings flagged no safe regbase form — verify in
  `arch35_micro_reference.md` §1D before converting, else stay membase.
- **Per-lane `ShiftLeft`/`ShiftRight`** — `dsl_coverage_and_gaps.md` §1F: reg shift is scalar-amount
  only (`ShiftLefts`/`ShiftRights`). Per-lane (reg-amount) shifts stay membase.
- **Widening `Mull`, carry `AddC`/`SubC`, `Unsqueeze`, `MaskGenWithRegTensor`, `CreateAddrReg`** —
  `dsl_coverage_and_gaps.md` §1F: niche, no regbase path today.
- **Complex memory / structural ops** — `Gather`/`Scatter` with bounds logic, `Transpose`, and
  advanced ops (`Prelu` as a full op, `MulAddDst`/`AddRelu` fusions, `BilinearInterpolation`,
  `VPadding`): keep membase unless an exact MicroAPI counterpart is confirmed; structural ops have
  no compute-reg form.

### Boundary handling
At every membase<->regbase boundary the regbase island `StoreAlign`s to UB and the membase side
`DataCopy`s from that UB (order with a barrier). Bit-exactness vs the Phase-1 golden is the
cross-check that the residual-membase region and its handoff are correct.
---

*Mapping and shapes mined from production AscendC kernels and the authoritative MicroAPI headers;
the `AscendC::Reg::*` vs `AscendC::MicroAPI::*` split and op semantics are detailed in
`arch35_micro_reference.md` §1. Re-verify a primitive there before converting a region.*
