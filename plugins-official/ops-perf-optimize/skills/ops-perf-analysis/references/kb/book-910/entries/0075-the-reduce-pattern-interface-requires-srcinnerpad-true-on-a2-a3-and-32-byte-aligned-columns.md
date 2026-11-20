```
ID:        0075-the-reduce-pattern-interface-requires-srcinnerpad-true-on-a2-a3-and-32-byte-aligned-columns
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-reduce-pattern.md:58 — "| `srcInnerPad` | bool | A2/A3 芯片只支持 `true` |"; ibid:57 — "| `srcShape` | uint32_t[] | `{rows, alignedCols}`，**alignedCols 必须 32 字节对齐** |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a Reduce Pattern call with `srcInnerPad = false` produces correct results on a named DAV_2201 board, or a non-32-byte-aligned `alignedCols` does.
```

# 0075 · The Reduce Pattern interface requires srcInnerPad = true on A2/A3 and 32-byte-aligned columns

## 1 · Claim
Upstream asserts that the Pattern-based reduction interface (`ReduceMax` / `ReduceSum` with
`Pattern::Reduce::AR` or `::RA`) takes a `srcInnerPad` flag which **on A2/A3 chips supports only
`true`**, and that the `srcShape` argument's `alignedCols` must be 32-byte aligned. Upstream asserts
the element type is `half` or `float`. Upstream asserts that the overload which omits an explicit
`sharedTmpBuffer` still requires temporary space to be reserved via `InitBuffer`, or UB overflows at
runtime, and that the required size comes from `GetReduceMaxMaxMinTmpSize`. Not established here.

## 2 · The wrong branch this removes
Three branches, and the third is the one that bites hardest.

**`srcInnerPad`.** A boolean parameter with two legal values in the signature and one legal value on
this family. An agent reasoning about whether its inner dimension is padded — the natural reading of
the name — will set it to `false` for unpadded data and, per upstream, be outside what A2/A3
supports. The parameter looks like a description of the data and is in fact a platform constraint.

**`alignedCols`.** The argument's own name says aligned, and 32 B is the familiar granularity
(0021), so this is the mildest of the three. It is stated because the shape array is built from
tensor dimensions and the alignment must be applied deliberately: `{rows, cols}` is the obvious
literal and is wrong whenever `cols × sizeof(T)` is not a multiple of 32.

**The temporary buffer.** The overload without `sharedTmpBuffer` reads as "the framework handles
it". Upstream states plainly that it does not: space must still be reserved through `InitBuffer`,
and omitting it overflows UB **at runtime**. So the convenient-looking overload is the dangerous
one, and the failure is a memory overrun rather than an error return. Upstream recommends the
explicit form for exactly this reason and rates it ⭐⭐⭐⭐⭐ against ⭐⭐⭐.

The size to reserve is not derivable by hand — upstream supplies `GetReduceMaxMaxMinTmpSize`
returning a max and a min. That is a query-don't-hardcode instance (0011) in a place where an agent
would otherwise guess.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-reduce-pattern.md` §参数说明, lines 49-58, the two
constrained rows verbatim:
```
| `srcShape` | uint32_t[] | `{rows, alignedCols}`，**alignedCols 必须 32 字节对齐** |
| `srcInnerPad` | bool | A2/A3 芯片只支持 `true` |
```
with `| T | half/float | 数据类型 |` at line 51 — consistent with 0045's A2 finding that `ReduceSum`
accepts only half and float, from a different skill in the same repo.

The pattern semantics, lines 42-43: "`Pattern::Reduce::AR` | 沿最后一维（列方向） | (R, C) | (R,) |
每行归约为1个值" and "`Pattern::Reduce::RA` | 沿第一维（行方向） | (R, C) | (C,) | 每列归约为1个值".

The temporary-space warning, line 34: "> **⚠️ 形式2 必须预留临时空间**，否则运行时 UB 越界。" —
restated at line 64 ("**两种形式都需要预留临时空间**") and line 128 ("⚠️ **必须在 InitBuffer 预留**").
Three statements of one point in one short file, which is upstream signalling that this is the
common failure.

The sizing query, lines 76-80:
```cpp
uint32_t maxSize, minSize;
AscendC::GetReduceMaxMaxMinTmpSize(srcShape, sizeof(T), isReuse, maxSize, minSize);
pipe->InitBuffer(tmpBuf, maxSize);
```
with the reference `asc-devkit/docs/api/GetReduceMaxMaxMinTmpSize.md` (line 83) — a pointer outside
this repo, not followed here.

The 32-byte alignment restated in the worked example, line 96: "uint32_t srcShape[] = {rows,
alignedCols};  // alignedCols 必须 32 字节对齐".

Same repo, one origin. Note the A2/A3 scoping is on `srcInnerPad` only; the alignment and the
temporary-space rules carry no architecture.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. `srcInnerPad` arm: identical `ReduceMax<float, AR>` calls at `true` and at `false`, same shape,
   same buffers, md5-confirmed to differ only in that argument. Verify both against a host reference
   element-wise. Record whether `false` fails to compile, returns wrong values, or works.
3. Alignment arm: `alignedCols` swept over a 32 B multiple and the two values either side of it, at
   fp32 and fp16 (different element counts per 32 B), destination poisoned; report mismatch
   positions, since a tail-only corruption and a whole-result corruption are different findings.
4. Temporary-space arm: the no-`sharedTmpBuffer` overload with `InitBuffer` reserving (a)
   `maxSize`, (b) `minSize`, (c) nothing. Predicted: (c) overruns UB. Place a poisoned guard region
   immediately after the buffer and check it after each call — an overrun that happens to land in
   unused UB would otherwise look clean.
5. Report `maxSize` and `minSize` from `GetReduceMaxMaxMinTmpSize` for a range of shapes, so the
   sizing function's behaviour is recorded rather than assumed.

## 5 · Checker — acceptance declared before the run
`innerpad_false_ok`: the claim is upheld iff `false` fails to compile OR produces mismatches. A
clean `false` overturns the A2/A3 restriction for this call.
`align_bad_positions(cols)`: PASS iff empty at 32 B multiples and non-empty otherwise.
`guard_dirty(reservation)`: PASS for the temporary-space claim iff dirty with no reservation and
clean with `maxSize`. The `minSize` case is reported separately with no declared expectation — it is
upstream's own "节省内存" option and whether it is actually sufficient is not stated.
The guard region is what lets arm 4 go red honestly: without it, an overrun into unallocated-but-
present UB produces correct output and the check would report success. That is the blind species
this book tracks, and the guard is the fixture against it.
Exit code is not the verdict; a UB overrun is not stated to fault.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. "A2/A3" is two product lines, not a board, and the
architecture scoping attaches to `srcInnerPad` alone — the alignment and temporary-space rules carry
none. This entry does not establish what `srcInnerPad` *does* when true, only that it must be; the
name suggests inner-dimension padding and upstream does not define it. It does not establish whether
the restriction covers `ReduceSum` as well as `ReduceMax` — the parameter table is shared but the
worked examples differ. It does not establish the relationship between `maxSize` and `minSize`, nor
when the smaller is safe. `GetReduceMaxMaxMinTmpSize`'s own documentation lives outside this repo
and was not read.
