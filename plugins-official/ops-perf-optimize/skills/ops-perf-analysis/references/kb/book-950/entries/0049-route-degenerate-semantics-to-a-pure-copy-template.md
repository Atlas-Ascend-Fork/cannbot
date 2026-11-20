```
ID:        0049-route-degenerate-semantics-to-a-pure-copy-template
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-07-identity-pure-copy.md:14 — "通用数据变换的地址计算与临时 UB 主要服务于非平凡映射。identity 条件成立时，这些准备工作只增加 Scalar/VEC 指令和同步；单独的 pure-copy kernel 可以按输出元素的 grid-stride 分工直接复制"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-07-identity-pure-copy.md:34 — "若 copy 仍需 format/stride 变换，它不是 identity，必须使用保留正确 physical layout 的 copy 模板；不要把「shape 相同」误判为「地址映射相同」"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board where a degenerate case routed to a pure-copy
           template is not faster than the same case through the general transform — the metadata
           and index preparation would then cost nothing worth removing.
```

# 0049 · Route degenerate semantics to a pure-copy template

## 1 · Claim
Upstream asserts (card mem-07, evidence: three named arch35 commits, no numbers) that operators
with degenerate cases — a reshape that leaves the logical index unchanged, a split that is exactly
a contiguous block, parameters that reduce a rearrangement, interpolation or reduction to a copy —
should detect that condition in tiling and select a pure-copy template, skipping the stride,
magic-division, index-table and temporary-UB preparation that only serves non-trivial mappings; and
that a copy still requiring a format or stride change is not an identity. Not established here.

## 2 · The wrong branch this removes
The general path is correct for the degenerate case, so nothing fails — it merely spends Scalar and
VEC instructions plus synchronisation building machinery that maps each element to itself. An agent
profiling such a case sees scalar-heavy work with almost no arithmetic and, following the scalar
page, looks for redundant computation inside the kernel; the redundancy is the entire preparation
stage and it is removed by routing, not by editing.

The wrong branch inside the repair is the identity test. Equal element counts, or even equal
shapes, do not imply equal address mappings: the card's list is shape, axis, layout, stride, dtype,
offset and alias constraints, and a NZ-to-ND pair with identical logical shape is not an identity.
A too-loose test produces a fast path that copies bytes into the wrong places, which is a
correctness failure with no diagnostic.

## 3 · Ground / Source
`mem-07:6-10` diagnostic: the operator has degenerate semantics; the general path still builds
strides, magic divisors, index tables or temporary UB while the output maps one-to-one from the
input; and that condition is fully provable at tiling time from shape, axis, layout and attributes.

`mem-07:19-31` after-form: the tiling side computes
`isIdentity = SameLogicalIndexMapping(inputShape, outputShape, axes, layout)` and sets
`tilingKey = isIdentity ? TILING_KEY_PURE_COPY : TILING_KEY_GENERAL`; the kernel branches
`if constexpr (TILING_KEY == TILING_KEY_PURE_COPY)` into a grid-stride copy loop
(`for (uint64_t i = GlobalThreadOffset(); i < elemCount; i += GlobalThreadStride()) y[i] = x[i];`)
and otherwise into `BuildMetadataAndRunGeneralTransform()`.

Stop rules, `mem-07:42-45`: the decision must cover shape, axis, layout, stride, dtype, offset and
alias constraints — equal element counts are not sufficient; overlapping input and output need an
implementation with overlap semantics rather than an assumed-safe parallel copy; a general fallback
must remain, routed by a runtime predicate and never by CSV row number or a test-shape whitelist
(entry 0046); and the pure-copy path must still handle empty tensors, tails and multi-core shard
boundaries.

Evidence, `mem-07:38`: record `aiv_time` and instruction counts for identity and non-identity
groups separately, requiring the fast path to remove the general path's UB allocation, metadata
initialisation and index computation, with the non-identity path unaffected — no values given.
Commits at `:49`: SparseReshape identity reshape to a direct-copy VF kernel skipping stride and
magic-div preparation, SplitV pure-copy template, Concat pure-copy admission adjustment.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one reshape/split operator two ways from a common tree: (G) general transform for every
   case; (I) tiling-routed with a pure-copy template under the identity predicate. Record `md5sum`.
2. Case set: true identity reshape; split on a contiguous boundary; same logical shape with a
   format change (NZ against ND) — which must NOT be routed to pure copy; overlapping input and
   output; an empty tensor; and a case whose element count matches but whose axis order differs.
3. Capture `aiv_time`, scalar instruction count, peak UB; five repetitions, median and spread.
4. Compare outputs element-wise against a reference for every case.

## 5 · Checker — acceptance declared before the run
Verdict variables `path_taken(case)`, `gain(case)`, `correct(build, case)`. Acceptance:
`path_taken` matches the predicate's prediction on all six cases — in particular the format-change
and axis-order cases must take the general path; `gain > spread` on the identity cases; and
`correct` holds everywhere for build I, including the empty tensor and the overlap case.

Exit code is not the verdict. Element-wise comparison covers the whole output, since a wrongly
admitted identity typically produces a correctly sized output containing correctly typed garbage —
a shape or checksum comparison would pass it.

Red input: the same-shape-different-format case. It is the one the card names explicitly, and if
the predicate admits it the fast path will copy bytes into the wrong layout while the sizes agree.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured, by us or upstream. No board, operator or shape space. It does not establish how
`SameLogicalIndexMapping` should be computed, and alias analysis in particular may not be decidable
from tiling metadata alone. The grid-stride form in the card assumes a thread-indexed execution
model whose availability on this architecture is not established here. Nothing transfers to the
910 book.
