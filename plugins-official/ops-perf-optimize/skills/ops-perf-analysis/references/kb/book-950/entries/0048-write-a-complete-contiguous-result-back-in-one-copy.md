```
ID:        0048-write-a-complete-contiguous-result-back-in-one-copy
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-06-direct-contiguous-output.md:14 — "对连续完整的结果，最佳搬出路径是一次或少量大块 copy。将连续性作为 tiling 路由条件，连续 case 直接从 UB 写最终 GM；非连续 case 保留 gather/scatter 模板。收益来自少掉的 copy 描述、索引访问、queue 操作与同步，而不是改变最终字节数"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-06-direct-contiguous-output.md:41 — "连续性需包含目的地址递增、元素无洞、无别名冲突和本轮结果完整四项，不能只检查逻辑 token 连续"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board where writing a complete contiguous result in one
           copy is not faster than segmented gather-out of the same bytes — the descriptor, index
           and synchronisation savings would then not exist at the sizes tested.
```

# 0048 · Write a complete contiguous result back in one copy

## 1 · Claim
Upstream asserts (card mem-06, evidence: three named arch35 commits, no numbers) that when a
result is already laid out contiguously in UB and this round's output is complete, it should be
written back in one — or a few — large copies rather than segment by segment; that contiguity
should be a tiling routing condition, with non-contiguous cases keeping the gather/scatter
template; and that the gain comes from fewer copy descriptors, index reads, queue operations and
synchronisations, not from moving fewer bytes. Not established here.

## 2 · The wrong branch this removes
An operator that supports gather-style outputs usually implements the general path first, and the
general path is correct for the contiguous case too. So contiguous outputs pay for index
computation and per-segment copies they do not need — and because the general path is correct, no
test reports anything. The card's move is again a routing one: decide contiguity in tiling, and
give the common case a body without the machinery.

The wrong branch inside the repair is the contiguity test. "The tokens are consecutive" is not the
same as "the destination addresses increase with no holes, no aliasing, and this round's result is
complete" — the card lists four conditions precisely because the first one alone is the tempting
approximation, and it admits cases where the fast path overwrites or omits.

## 3 · Ground / Source
`mem-06:6-10` diagnostic: results already contiguous in UB but still copied out per token, row,
expert or fragment; the gather/scatter branch covering contiguous outputs, so ordinary cases pay
for index arithmetic and repeated MTE issues; no further transformation of the intermediate output.

`mem-06:19-31` before/after: a per-part loop computing `OutputOffset(part)` becomes
`if (IsSingleContiguousRange(outputLayout, validElems)) { CopyOut(outGm[baseOffset], resultUb,
totalBytes); } else { GatherOrStridedCopyOut(); }`, with `:33` adding that a range exceeding the
current UB result may be split into a few contiguous chunks, but that data must not be rearranged
or duplicated merely to force a single copy.

Stop rules, `mem-06:41-44`: the four-part contiguity condition quoted in SOURCE; the write-back
length covers only valid elements, so tails, drop/pad and empty outputs must not write past the
end using an aligned length; a non-contiguous path already expressed efficiently by DMA strides
should not be replaced by a UB rearrangement plus a direct write; and outputs with cross-core
overlap or atomic accumulation semantics may not become plain writes.

Evidence, `mem-06:37`: compare MTE copy count, index/Scalar instruction count and `aiv_time` across
contiguous and non-contiguous groups, requiring the fast path to cover the complete result range
and cases with holes, repeated writes or interleaved layout to fall back — no values given.
Commits at `:48`: MoE Init Routing non-quantised contiguous write-out, MoE gather-copy redundancy
cleanup, Concat pure-copy admission adjustment (the last shared with mem-07).

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one operator two ways from a common tree: (S) segmented gather-out for every case; (C)
   tiling-routed, single-copy write-back when the four-part predicate holds. Record `md5sum`.
2. Case set: fully contiguous complete output; contiguous but incomplete (a tail missing);
   contiguous with a hole; overlapping destinations; and an atomic-accumulation output. The last
   three must route to the fallback.
3. Capture `aiv_time`, copy count, scalar instruction count; five repetitions, median and spread.
4. Compare outputs element-wise against a reference, with the memory beyond the valid range
   initialised to a sentinel.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(case)`, `copies(build, case)`, `path_taken(case)`, `sentinel_intact(case)`.
Acceptance: `path_taken` matches the predicate's prediction on all five cases; `copies(C)` is 1 on
the contiguous complete case; `gain > spread` there; and `sentinel_intact` is true everywhere —
that is the check that catches an aligned-length write-back running past the valid elements.

Exit code is not the verdict. The sentinel region is part of the comparison, so a fast path that is
faster because it writes more is caught rather than rewarded.

Red input: the contiguous-with-a-hole case. It must route to the fallback; if the predicate admits
it, the four-part condition has been implemented as the one-part approximation and the timing
results are void.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured, by us or upstream. No board, shape or operator family. It does not establish how
to evaluate `IsSingleContiguousRange` — the card states the four conditions and leaves the
implementation open, and aliasing in particular may not be decidable from tiling alone. It says
nothing about the size at which "one copy" should become "a few chunks", nor about output paths
that cross cores.
