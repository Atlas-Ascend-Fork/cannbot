```
ID:        0032-one-vector-repeat-covers-eight-32-b-datablocks-which-is-256-b
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:58 — "Vector 指令处理的数据被切分为固定大小的 **DataBlock**，每行长度为 32B。一个 Vector 指令在一个 Repeat 内最多处理 **8 个 DataBlock**（block0~block7）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a DAV_2201 board is shown to process more or fewer than eight 32 B DataBlocks per Vector repeat — e.g. a repeat covering 512 B, or a `blk_stride` sweep whose conflict period implies a different block count.
```

# 0032 · One Vector repeat covers eight 32 B DataBlocks — which is 256 B

## 1 · Claim
Upstream asserts that a Vector instruction splits its data into fixed-size DataBlocks of 32 B, and
that one instruction processes at most eight of them (block0 through block7) in one repeat. The
product, 256 B per repeat, is arithmetic performed in this entry and is not stated by that source.
Upstream separately asserts, in a different skill, that the `mask` parameter's FP32 ceiling of 64
elements is "256 字节 ÷ 4 字节" — the same 256 B, reached from the API side. Not established here.

## 2 · The wrong branch this removes
Without a repeat granularity an agent has no unit in which to reason about vector work. It sizes
tiles in elements, and the relationship between elements and instructions is opaque: 64 fp32
elements and 65 fp32 elements cost the same (one repeat versus two, the second almost empty), and
nothing in the source code shows the step. Tile sizes chosen for UB fit or for core balance land
arbitrarily against the 256 B boundary, and a tile of 65 elements per row does 2× the vector
instructions of a tile of 64 for 1.5 % more work.

The second wrong branch is unit confusion, and it is why this entry states the arithmetic
explicitly rather than assuming it. "8 DataBlocks", "256 bytes" and "64 elements" are the same
quantity in three units, and the three appear in three different documents. An agent that meets
the element form first will apply 64 to fp16 data, where the correct figure is 128.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md` §2.2.3, line 58,
verbatim in full: "Vector 指令处理的数据被切分为固定大小的 **DataBlock**，每行长度为 32B。一个
Vector 指令在一个 Repeat 内最多处理 **8 个 DataBlock**（block0~block7）。各 DataBlock 根据起始
地址映射到某个 bank，进而归属于某个 bank group。"

The document's architecture scope is set at its line 34: "下文以 NPU 架构版本 220x（Atlas A2/A3
系列）和 Atlas 350 为例说明" — so the eight-block statement sits in a passage explicitly covering
Atlas A2/A3, which is DAV_2201 per 0001. This is the strongest architecture attribution available
for this constant anywhere in scope.

The API-side form, `ops/ascendc-api-best-practices/references/api-arithmetic.md:402`:
"| **FP32 mask 上限 64** | `Sub/Div` 的 `mask` 参数对 FP32 是 256 字节 ÷ 4 字节 = 64 元素 |
当 `alignedInnerDim > 64` 时分批处理 |" — 256 B reached from the mask ceiling, independently of
the DataBlock count. Same repo, so one origin, but two different derivations of one number
agreeing is a consistency check worth recording. Carried separately by 0033, whose wrong branch is
the parameter cap rather than the granularity.

The worked consequence, same file lines 65-66, is 0015's bank arithmetic: eight blocks is exactly
why a `blk_stride` of 16 costs 8 cycles and one of 8 costs 4 — the cycle counts only work out with
eight blocks per repeat, so 0015's numbers are a consistency check on this one.

Arithmetic performed here and labelled as such: 8 × 32 B = 256 B; 256 B ÷ 4 B = 64 fp32 elements;
÷ 2 B = 128 fp16 elements; ÷ 1 B = 256 int8 elements. Only the first is corroborated by an
upstream sentence; the fp16 and int8 figures are extrapolations of the arithmetic and are NOT
upstream claims.

**This corrects a survey claim.** `harvest/surveys/DEEPDIVE_20260824_perf-optimize.md` §5.3 lists
"256 B repeat granularity" under "ESTABLISH FROM SCRATCH (no upstream authority)". Upstream
authority exists, in an A2/A3-scoped passage, and is quoted above.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Step-function sweep: one `Adds` over `N` fp32 elements, `N` swept over 56…80 in steps of 1,
   with the repeat count computed by the framework rather than by hand. Record `aiv_total_cycles`
   per `N`, five repeats each, first discarded.
3. The claim predicts a staircase with risers at `N = 65` and `N = 129`, not a straight line.
   Report the raw curve; fit the step positions rather than eyeballing them.
4. Repeat for fp16 with `N` swept over 120…144, where the claim's arithmetic predicts the riser at
   129. This second sweep is what tests the extrapolation in §3 rather than assuming it, and it is
   the more informative of the two.

## 5 · Checker — acceptance declared before the run
Verdict variable `riser_fp32`: the `N` at which `aiv_total_cycles` first exceeds its value at
`N = 64` by more than three times the repeat-to-repeat spread at `N = 64`.
PASS iff `riser_fp32 == 65`.
`riser_fp16`: PASS iff `== 129`. This one is the extrapolation's test; a riser at 65 for fp16 would
mean the granularity is 64 *elements* rather than 256 *bytes*, which is a different claim with the
same headline number and would send §1 back for correction.
Red input for both: a linear cycle count with no riser, which would mean the repeat granularity is
not observable this way and the run is INCONCLUSIVE rather than negative — distinguished by
checking that cycles at `N = 640` are roughly ten times those at `N = 64`, confirming the counter
tracks work at all. If that control fails, the sweep is VOID.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. The A2/A3 attribution is a scope line in a document's preamble,
not a measurement, and BOARD stays `family-claimed(unverified)` accordingly. This entry does not
establish the fp16 or int8 element counts — those are arithmetic in §3 and are what §4 step 4 would
test. It does not establish whether all Vector instructions share the eight-block repeat or whether
some (transcendentals, reductions) differ; upstream says "一个 Vector 指令" without qualification
and that is weaker than it sounds. It does not establish the cycle cost of a repeat. The
`mask`-parameter consequence is 0033's, not this entry's.
