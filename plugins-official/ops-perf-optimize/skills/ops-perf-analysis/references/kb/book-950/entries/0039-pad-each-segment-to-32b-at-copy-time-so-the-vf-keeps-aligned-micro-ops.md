```
ID:        0039-pad-each-segment-to-32b-at-copy-time-so-the-vf-keeps-aligned-micro-ops
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-14-aligned-split-copy.md:14 — "RVEC load/store 对 32B 对齐地址走单拍对齐微指令，非对齐地址要拆成跨边界的多拍访问、更慢 … **搬运的对齐口径必须与 VF 里的段 offset 完全一致**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board where splitting the row copy so every VF segment
           starts 32B-aligned is not faster than one contiguous copy with a misaligned second
           segment — the misalignment penalty would then be smaller than the extra DataCopyPad
           and pad-UB cost at every shape, not merely at short segments.
```

# 0039 · Pad each segment to 32B at copy time so the VF keeps aligned micro-ops

## 1 · Claim
Upstream asserts (card vec-14, 性能数据 待实测) that RVEC load and store take a single-beat
aligned micro-instruction at 32-byte-aligned addresses and must split into multi-beat
boundary-crossing accesses otherwise; that when a VF loads a row in segments at different offsets
(front/back halves, even/odd, quarters), the copy stage should pad each segment start to a 32-byte
boundary and issue one `DataCopyPad` per segment, rather than saving a copy by moving the row
contiguously and letting the second segment land misaligned; and that the alignment used by the
copy must be exactly the alignment used by the VF's segment offsets and by the write-back stride.
Not established here.

## 2 · The wrong branch this removes
Copying the whole row in one `DataCopyPad` is obviously cheaper at the copy stage — one
descriptor, one issue, no padding waste — and it is what a memory-minded reviewer will prefer. The
cost lands somewhere else entirely: inside the VF, where every access to the second segment
degrades to a slower micro-instruction, once per beat, for the life of the kernel. An agent
optimising the copy stage and an agent optimising the compute stage will reach opposite
conclusions, and each will be right about its own lane.

The second failure this prevents is a correctness one, and it is the reason the card states the
alignment as a single shared quantity: `CeilAlign(segLen, 32/sizeof(T))` must appear in the
CopyIn `dstStride`, in the VF's `halfDAlign` offset, and in the CopyOut `srcStride`. Three places,
one value; if any drifts, the kernel reads the wrong data rather than running slowly.

## 3 · Ground / Source
`vec-14:6-10` diagnostic: the VF loads one row as segments at different offsets (RoPE half: `off`
and `halfOff`); `segLen*sizeof(T)` is not a multiple of 32 bytes, so a contiguous row copy puts the
second segment on a misaligned address; the trace shows non-aligned RVECLD/RVECST forms taking
extra beats, or the memory phase costing more than an aligned copy of the same length.

`vec-14:22-29` after-form:
> int64_t alignedHalf = Ops::Base::CeilAlign<int64_t>(segLen, BLOCK_TYPE_SIZE / sizeof(T)); // = VF 的 halfDAlign
> cp.srcStride = (D - segLen) * sizeof(T);                       // GM 侧跳过另一段（多行批量）
> cp.dstStride = alignedHalf * sizeof(T) / BLOCK_TYPE_SIZE;      // UB 段间对齐步进
> DataCopyPad(inUb,               gm[off],           cp, pad);   // 前半 -> UB 偏移 0
> DataCopyPad(inUb[alignedHalf],  gm[off + segLen],  cp, pad);   // 后半 -> 对齐偏移

Stop rules, `vec-14:36-41`: the three-place alignment identity quoted above; split only when the
segment length is genuinely unaligned, since an already-aligned segment is cheaper to move
contiguously; padding increases UB usage, so the tile budget must be computed on the aligned pitch
rather than the valid length; and when segments are very short and rows very many, the extra
`DataCopyPad` fixed cost may exceed the gain — settle it by measured `aiv_time`.

Source at `:45`: RoPE arch35 `CopyInHalfMode`/`CopyOutHalfMode`. The 32-byte figure here is one of
the several alignment constants this library refuses to globalise — see 0041.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one rotate-half VF two ways from a common tree: (C) one contiguous row copy, second
   segment misaligned; (A) two `DataCopyPad` calls with the second at `alignedHalf`. Record
   `md5sum` of both.
2. Sweep `segLen*sizeof(T)` over values that are and are not multiples of 32 bytes, and sweep row
   count over three values spanning 32×, so the "many short rows" stop rule is exercised.
3. Capture `aiv_time`, the memory-phase duration, and — from the instruction trace — the count of
   aligned versus unaligned RVECLD/RVECST forms; five repetitions, median and spread; record peak
   UB usage for both builds.
4. Compare outputs element-wise against a host reference for every shape, including the shapes
   where the alignment identity is deliberately broken in a third build (A') that uses a different
   constant in CopyOut than in the VF.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(segLen, rows)`, `unaligned_ops(build)`, `ub_peak(build)`, and
`correct(build, shape)`. Acceptance: `unaligned_ops(A) == 0`, `gain > spread` at unaligned segment
lengths with moderate row counts, `gain <= 0` at already-aligned segment lengths (the stop rule),
and `ub_peak(A) > ub_peak(C)` by the pad, which is the price being paid.

Exit code is not the verdict. Build A' must fail the element-wise comparison; the checker reports
which elements differ, since a stride mismatch produces a specific, recognisable displacement
rather than noise.

Red input: build A' as described, plus the already-aligned segment length. Both are cases where a
naive "did it get faster" checker would report success or say nothing; here they have declared,
opposite expected outcomes.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; 待实测 upstream. The 32-byte alignment figure is asserted for RVEC load/store on
this architecture and is not verified; per 0041 the alignment constant in this family is not a
single number, so even the figure's scope is unsettled. No board, shape, dtype or segmentation
pattern is established. It says nothing about GM-side alignment, about `DataCopyPad`'s own
constraints, or about whether the aligned micro-instruction advantage exists for stores as well as
loads — the card asserts both and measures neither.
