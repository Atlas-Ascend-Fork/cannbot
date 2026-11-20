```
ID:        0040-keep-the-main-copy-path-contiguous-and-aligned-and-isolate-the-tail
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-01-aligned-contiguous-copy.md:14 — "优化不是把任意 shape 强行补齐，而是将合法的对齐条件显式进入 tiling：主模板只处理连续对齐区间，尾块或非连续输入使用独立正确路径。这样快路径没有额外分支，慢路径也不会越界或误读"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board where routing aligned-contiguous cases to a
           dedicated template does not improve their `aiv_time` beyond spread against a single
           conservative template — the descriptor and padding overhead would then not be what the
           card says it is.
```

# 0040 · Keep the main copy path contiguous and aligned, and isolate the tail

## 1 · Claim
Upstream asserts (card mem-01, evidence: five named arch35 commits, no numbers) that contiguous
aligned reads and writes reduce transfer-descriptor, padding and tail-handling cost and keep UB/L1
and cache-line segmentation stable; and that the correct form of the optimisation is not to pad
arbitrary shapes into alignment but to admit the legal alignment condition into tiling, so the
main template handles only contiguous aligned ranges while tails and non-contiguous inputs take a
separate, independently correct path — leaving the fast path branch-free and the slow path safe.
Not established here: the card carries no measurement at all.

## 2 · The wrong branch this removes
One conservative copy template for every specification is the safe engineering choice, and it
makes every aligned case pay for the unaligned ones: stride handling, padding logic and a tail
test inside the main loop. The card's counter-position is a routing discipline — the predicate is
evaluated once, in tiling, and the kernel body is chosen by it.

The wrong branch on the other side is forcing alignment: padding an arbitrary shape to make it fit
the fast path, which adds invalid data movement and, worse, can produce a fast path whose write
range exceeds the valid elements. The card's stop rules put the padding value, the tail mask, the
write-back range and the access upper bound under independent verification in the slow path, and
forbid reusing the fast path's length.

## 3 · Ground / Source
`mem-01:6-10` diagnostic: the main path frequently uses `DataCopyPad`, unaligned copies or short
tail branches, and MTE efficiency is below that of contiguous bulk moves; the data is logically
contiguous but physical row stride, inner-axis length, L1 slice or format-conversion boundary does
not meet alignment; the operator covers aligned and unaligned specifications together, forcing all
of them onto a conservative template.

`mem-01:24-31` after-form: a `fastPath` predicate combining `IsContiguous(layout)`,
`IsAligned(innerBytes, alignBytes)` and `IsAligned(l1SliceBytes, alignBytes)`, selecting
`CopyAligned` or `CopyStridedOrTail`. `mem-01:33` insists the alignment condition be derived from
dtype and physical format — NZ/ND, scale, and different transpose directions do not have the same
contiguous inner axis — and that when only most tiles can be aligned, the main region and the tail
should be split at tiling time rather than tested every iteration.

Stop rules, `mem-01:41-44`: contiguity may not be judged from logical shape alone (format, real
pitch, offset, transpose and dtype width all enter); the slow path's padding value, tail mask,
write range and access bound are verified independently of the fast path; the alignment threshold
comes from the current API/hardware contract and — the sentence that becomes entry 0041 — 950
history shows 16B, 32B, 64B and 128B constraints, which must not be abstracted into one global
constant; and if alignment-driven splitting materially shrinks tiles or reduces parallelism, the
general path is kept and the routing decided by measurement.

Evidence, `mem-01:37`: the card names what to compare — MTE effective-byte rate, copy instruction
count and `aiv_time`, across contiguous main region, non-contiguous input, unaligned inner axis
and tail — but reports no values. Commits at `:48`: five arch35 changes across ops-nn and
ops-transformer (Conv2D C04 address alignment, BatchNorm aligned-UB template, MoE non-64B path,
PANZ scale 32B alignment, DropPad duplicate `AlignBytes` removal).

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one copy-dominated operator two ways from a common tree: (G) one general template with
   stride, padding and tail logic in the main loop; (R) tiling-routed, fast path for
   contiguous-aligned and a separate template otherwise. Record `md5sum` of both.
2. Build a specification set covering the four cases the card names: contiguous aligned;
   non-contiguous; unaligned inner axis; tail-dominated. Include at least one NZ-format case and
   one transposed case, since the card warns that contiguity differs by format.
3. Capture `aiv_time`, `aiv_mte2_ratio`, copy instruction count, and MTE effective-byte rate if the
   counter is available; five repetitions, median and spread.
4. Verify, per specification, which template executed — routing that silently falls back must not
   be averaged into the fast path's result.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(spec)`, `template_used(spec)`, and `correct(build, spec)` element-wise.
Acceptance: `gain > spread` on the contiguous-aligned specifications, `gain >= 0` (no regression)
on the others, and `template_used` matching the predicate's prediction for every specification.
Correctness must hold on the tail and non-contiguous specifications for build R, which is where an
over-eager fast path writes out of range.

Exit code is not the verdict. The element-wise comparison includes the elements *beyond* the valid
range, initialised to a sentinel, so an over-long aligned write is detected rather than ignored —
a comparison restricted to valid elements would pass exactly the bug the card's stop rule targets.

Red input: a specification whose inner axis is one element short of alignment, with the sentinel
region checked. Build R must either route it to the slow path or leave the sentinel untouched.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured, by us or upstream — the card is a recipe under a heading that promises data, and
supplies none. No board, shape, format or dtype is established. The alignment threshold is not a
single value and is not established here (0041). It does not establish the cost of the routing
predicate itself, nor the tiling-side cost of splitting the main region from the tail. The five
cited commits are external and were not read; they are provenance, not evidence.
