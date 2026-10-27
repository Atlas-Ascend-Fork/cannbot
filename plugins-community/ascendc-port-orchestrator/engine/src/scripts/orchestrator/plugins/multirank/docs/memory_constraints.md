---
applies_to: soc=all; cann=all
reason: figures are SoC-scoped PER SECTION — each section names the architecture its numbers were verified on; append per-SoC columns/sections when witnessed, do not overwrite V220 numbers with unverified others.
verified_on: soc=V220 (A2/A3); cann=9.2.0-beta.1 official constraint/API pages
---

# Domain: Memory Access Constraints

> What the hardware REQUIRES of every access: alignment granularity, transfer
> granularity/spacing, and cross-observer consistency. Optimization (how to go
> fast) lives in `memory_access.md`; execution ordering (when operations retire)
> lives in `sync_fundamentals.md`. This page is the correctness floor.
>
> Current content covers V220 (A2/A3, NPU architecture 2201); each section
> states its SoC scope.
>
> Load when: choosing DataCopy counts/strides, writing scalar GM access
> (`SetValue`/`GetValue`), publishing cross-core/cross-rank aggregates, or
> debugging "only core0 correct" / garbage-read / silent-neighbor-overwrite
> symptoms.

## 1. Address alignment granularity (per storage unit)

Minimum access granularity / address alignment, V220 (arch 2201):

| Storage unit | Alignment |
|---|---|
| Unified Buffer (UB) | 32B |
| L1 Buffer | 32B |
| L0A Buffer / L0B Buffer | 512B |
| L0C Buffer | 64B |
| BiasTable Buffer | 64B |
| Fixpipe Buffer | 128B |
| DataCache line (scalar path) | 64B (8 × int64 / 16 × int32) |

Rules:

- Be alignment-aware on EVERY transfer. For UB non-aligned cases use the
  non-aligned copy interfaces (e.g. `DataCopyPad`), or the padding technique:
  copy in with redundant data, trim on the way out.
- The alignment is in BYTES, not elements: fp32 8 elements, fp16/bf16 16
  elements, int64 4 elements all equal 32B. Element-count reasoning alone is a
  recurring source of silent corruption.
- READS are constrained too: a V220 MTE2/DataCopy read below the 32B block
  boundary returns garbage without crashing. Pad the read count to the
  boundary, advance offsets by the TRUE count.

## 2. GM transfer granularity and spacing

V220 (arch 2201) figures; segment sizes may differ per SoC — restate per
section when another architecture is witnessed.

- Hardware splits transfers into 128B/256B/512B segments; a non-aligned
  request is rounded UP. The rounded-up tail silently lands on the next row of
  the same logical tensor when per-slot stride < aligned count — no crash, no
  error code, just a precision failure whose mismatch count factors exactly as
  batches × overshoot bytes. Fix class: pad the GM stride to the boundary and
  narrow back on the host side.
- Prefer GM addresses 512B-aligned, and tile the innermost axis of transfers
  to 128B/256B/512B.
- GM→L1 `DataCopy`: the gap between consecutive source blocks (tail of block N
  to head of block N+1) must not exceed 65535 DataBlocks (32B units); larger
  gaps must be split into multiple instructions.
- Bandwidth best practice: a single transfer of ≥16KB reaches the best
  achievable bandwidth; batch small transfers instead of tiling below this
  without a reason.
- Multi-core contention on one 512B window: MTE2/MTE3/Scalar address
  requests to GM are processed 512B-aligned — concurrent accesses from
  multiple cores that fall inside the SAME contiguous 512B window are
  serialized for coherence, even when the addresses all differ. Degradation
  grows with the number of cores hitting the window simultaneously (~10-20%
  queueing cost for a plain conflict; more as core count rises). Kernel
  inputs (including Workspace/Tiling) are guaranteed 512B-aligned, so the
  window test is a plain offset comparison.

  Two de-conflict methods:

  1. Stagger the access order — give each core a rotated iteration start:

  ```cpp
  int32_t idx = (i + AscendC::GetBlockIdx()) % tiling->loopOneCore;
  CopyIn(idx); Compute(); CopyOut(idx);
  ```

  2. Change the split so per-round blocks land on different rows/512B
     windows — e.g. column-split (per-core base `GetBlockIdx() * tileN`, all
     cores walking the same rows round by round) → row-split
     (`GetBlockIdx() * tileM * n`, per-core private rows):

  ```cpp
  xGm.SetGlobalBuffer(
      (__gm__ float*)x + AscendC::GetBlockIdx() * tiling->tileM * tiling->n);
  ```

  With the conflict removed, the first load brings the line into L2 and the
  remaining cores' accesses hit L2 instead — a net win over both serialized
  and scattered patterns.

## 3. Cross-observer consistency — the Scalar/DCache rule

Mechanism (V220 family; treat as the model for other SoCs until separately
witnessed):

- Every AIC/AIV core has its OWN private DataCache; Scalar reads/writes of GM
  go through it. `GetValue` fills the surrounding 64B line; `SetValue` modifies
  only the cached line and marks it dirty — GM is NOT updated at store time.
- The hardware does NOT keep DataCache and GM coherent across cores. The
  official constraint table says exactly this: the USER guarantees consistency
  (via `DataCacheCleanAndInvalid`) when scalar-written GM data is consumed by
  anyone else — including the writer core re-reading after an external (MTE)
  overwrite.
- In-pipe visibility is equally lazy: a scalar store travels the S-pipe and
  propagates toward GM gradually; `SyncAll` does NOT flush the S-pipe.

Decision rule: prefer the MTE engines end to end for anything
cross-core/cross-rank/cross-phase — stage the scalar in UB, publish with an
MTE3 `DataCopyPad`, consume via MTE2 / a dcache-bypass path. Treat direct
scalar GM operations as a hazard zone; `DataCacheCleanAndInvalid` is the
sanctioned exception, not the default. (SIMT-side visibility has its own
limitation: `asc_threadfence` provides ordering, not store-completion — do
not rely on it to make cross-iteration GM carries visible.)

## 4. `DataCacheCleanAndInvalid` — API reference and the multi-core overwrite trap

Header: `basic_api/kernel_operator_cache_intf.h`. Product support (per the
official API page): A2/A3 and Ascend 950PR/950DT supported; Atlas 推理系列
Vector Core NOT supported (AI Core supported, dcciDst-less prototype only);
older Atlas 训练系列 not supported.

API surface (template arity is arch-gated — the forms below are arch
2201/3002/2002, quote your own SDK header for other architectures):

```cpp
// arch 2201 / 3002 — three template parameters:
AscendC::DataCacheCleanAndInvalid<T, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                  AscendC::DcciDst::CACHELINE_OUT>(gmTensor);
// arch 2002 / 2201 also accept the two-parameter form (no DcciDst).
// Overloads exist for GlobalTensor<T> (GM) and LocalTensor<T> (UB).
```

Function split (official wording): **Clean** writes dirty lines back to GM
(avoid losing data); **Invalid** marks the addressed lines invalid so the next
access reloads from GM instead of serving stale cache.

Template parameters:

- `entireType`:
  - `SINGLE_CACHE_LINE` — refreshes only the line holding the passed address.
    **If the address is NOT 64B-aligned, one call only covers the part up to
    the 64B boundary — a second call on the remainder is needed to refresh the
    full line** (see the non-aligned example below).
  - `ENTIRE_DATA_CACHE` — the address is ignored; the whole per-core DCache is
    flushed. Large latency — avoid in performance-sensitive paths.
- `dcciDst` (enum, which storage coherence is guaranteed against):
  `CACHELINE_OUT` (DCache↔GM) ≡ `CACHELINE_ALL`; `CACHELINE_UB`
  (DCache↔UB, use the LocalTensor overload); `CACHELINE_ATOMIC` (coherence
  during atomics — Ascend 950PR/950DT only, NOT yet supported on A2/A3 per the
  official support table).

Canonical use cases: (a) reading GM that may have been modified by another
core — invalidate so the read hits GM; (b) Scalar-written GM that must be
published immediately — clean out. (Ascend 950PR/DT only: flush before
`SetCtrlSpr` changes the saturation mode of subsequent atomic data.)

Usage examples (distilled; base address 64B-aligned unless stated):

```cpp
// (1) writer side, 64B-aligned base — 8 x uint64_t fill exactly one line:
//     one call refreshes the whole line.
AscendC::GlobalTensor<uint64_t> global;
global.SetGlobalBuffer((__gm__ uint64_t*)mmAddr_ + AscendC::GetBlockIdx() * 1024);
for (int i = 0; i < 8; ++i) {
    global.SetValue(i, i);
}
AscendC::DataCacheCleanAndInvalid<uint64_t, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                  AscendC::DcciDst::CACHELINE_OUT>(global);

// (2) SAME line but base NOT 64B-aligned (e.g. mmAddr_ = 0x20): one call
//     refreshes only up to the 64B boundary — refresh the remainder with a
//     second call anchored inside the line:
//     ... first call as above ...
AscendC::DataCacheCleanAndInvalid<uint64_t, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                  AscendC::DcciDst::CACHELINE_OUT>(global[4]);

// (3) reader side — poll loop over externally-rewritten GM: invalidate
//     immediately BEFORE each read so the GetValue hits GM, not stale cache.
AscendC::DataCacheCleanAndInvalid<int32_t, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                  AscendC::DcciDst::CACHELINE_OUT>(flag[cntIdx]);
if (flag.GetValue(cntIdx) >= target) { break; }
```

```cpp
// (4) THE TRAP, do not write this: each core writes a DIFFERENT index, but
//     both indices live in the SAME 64B line — the later core's clean
//     rewrites the whole line from its copy and randomly erases the other
//     core's value. Multi-core writes to one shared line are only safe with
//     a single writer per line (see mitigations below).
AscendC::GlobalTensor<uint64_t> global;
global.SetGlobalBuffer((__gm__ uint64_t*)mmAddr_);   // one line, shared
global.SetValue(AscendC::GetBlockIdx(), AscendC::GetBlockIdx());
AscendC::DataCacheCleanAndInvalid<uint64_t, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                  AscendC::DcciDst::CACHELINE_OUT>(global);
```

Call-form witnesses: writer side — loop per line with a `Barrier()` between
the stores and the clean (catlass `matmul_client.h`); reader side — clean +
invalidate immediately BEFORE a `GetValue` poll of externally-rewritten GM
(live moe_fused_a8w8 GmmAicWalk/H4-flag polls).

**The multi-core overwrite trap** (example 4 above). The clean in DCCI writes
back the ENTIRE 64B line, not the bytes you stored. If two cores each
`SetValue` a different field that falls in the SAME line and then each issues
its own DCCI, the later clean rewrites the whole line from the second core's
copy — which still holds the STALE value of the first core's field — silently
erasing the first core's publish. The failure needs no race window: the mere
overlap of two writers' fields inside one line makes every-DCCI-correct code
lose data. This differs from general-purpose CPUs and is stated as a hard
limitation by the API's official documentation: multi-core writes to different
addresses within one cache line randomly overwrite each other.

Mitigations, in preference order:

1. Do not co-locate multi-writer fields: give each writer a line-exclusive
   slot — pad per-writer scalars so each writer's destination occupies its own
   64B line (the same isolation idea as padding per-core outputs past the 32B
   DataCopy block, lifted to the DCache-line granularity).
2. Single-writer publication: aggregate on one core (or via MTE/atomics) so
   at most one core ever dirties a given line.
3. sidestep entirely with the MTE path (§3) — no dirty lines, no clean to
   interleave.

Two adjacent footnotes:

- The bisheng compiler auto-appends a full-DCache flush at operator end in
  single-kernel compilation. In SuperKernel mode sub-kernels are plain
  functions — NO auto flush; insert DCCI yourself at sub-kernel boundaries
  where scalar GM state must survive.
- The SIMT surface of the same hardware is the builtin
  `__builtin_cce_dcci(nullptr, 1, 0)` — issue from thread 0 only, followed by
  `__syncthreads()`; pair with volatile GM pointers to keep the compiler from
  caching the loads.

## 5. Source/destination address overlap (API-generic constraint)

API-level rule (not SoC-specific as far as witnessed), for Tensor high-dim
slicing APIs where one tensor serves as both source and destination (address
overlap to save space):

- Within one iteration: src and dst must overlap 100% — partial overlap is
  unsupported.
- Across iterations: dst of iteration N must NOT overlap src of iteration N+1
  (the later read may already be overwritten).
- Exception — binocular APIs `Add/Sub/Mul/Max/Min/AddRelu/SubRelu` with dtypes
  half/int32_t/float DO allow dst(N) to overlap src1(N+1), provided
  `src1RepStride` or `dstRepStride` is 0.

## 6. Checklist

- [ ] Every DataCopy count/stride reasoned in BYTES against §1 (both directions: read and write)?
- [ ] Per-slot GM stride ≥ aligned write count (no silent neighbor overwrite)?
- [ ] Any multi-writer GM scalars co-located within one 64B line? → separate slots
- [ ] Cross-core/cross-rank scalar publication via MTE (not bare SetValue)?
- [ ] If DCCI is genuinely used: SINGLE_CACHE_LINE + single-writer-per-line verified?
- [ ] Reader polls of externally-rewritten GM invalidate before GetValue?
- [ ] GM→L1 block gaps ≤ 65535 DataBlocks?
