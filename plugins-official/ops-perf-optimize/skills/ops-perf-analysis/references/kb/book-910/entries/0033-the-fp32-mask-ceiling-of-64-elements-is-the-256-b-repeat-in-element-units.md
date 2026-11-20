```
ID:        0033-the-fp32-mask-ceiling-of-64-elements-is-the-256-b-repeat-in-element-units
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-arithmetic.md:402 — "| **FP32 mask 上限 64** | `Sub/Div` 的 `mask` 参数对 FP32 是 256 字节 ÷ 4 字节 = 64 元素 | 当 `alignedInnerDim > 64` 时分批处理 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `mask` above 64 is accepted for an FP32 `Sub` or `Div` and processes all requested elements on a named DAV_2201 board.
```

# 0033 · The FP32 mask ceiling of 64 elements IS the 256 B repeat, in element units

## 1 · Claim
Upstream asserts that the `mask` parameter of `Sub` and `Div` tops out at 64 elements for FP32, and
gives the derivation in the same sentence: 256 bytes ÷ 4 bytes. Upstream asserts the remedy is to
process in batches when the aligned inner dimension exceeds 64. Not established here.

## 2 · The wrong branch this removes
An agent sets `mask` from its row width because that is what the parameter looks like it means —
"how many elements to operate on". For an aligned inner dimension of 128 fp32 elements the value
is out of range, and the failure mode is the same silent-truncation family as 0031: the parameter
is narrow, the excess is lost, and the tail of every row is stale.

This entry is separate from 0032 despite sharing a number because the wrong branches differ. 0032's
branch is *tiling* — choosing a tile size that straddles the granularity and doubles the
instruction count. This one's is *parameter passing* — supplying a value the API cannot represent.
An agent can get the tiling right and still overflow the mask, and vice versa.

The dtype dependence is the specific hazard: 64 is correct for FP32 only. An agent that memorises
64 and applies it to FP16 halves its throughput; one that applies it to int8 loses three quarters.
The derivation upstream supplies — bytes ÷ sizeof — is what makes the number portable, and it is
the form to carry rather than the number.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-arithmetic.md:402`, verbatim:
```
| **FP32 mask 上限 64** | `Sub/Div` 的 `mask` 参数对 FP32 是 256 字节 ÷ 4 字节 = 64 元素 | 当 `alignedInnerDim > 64` 时分批处理 |
```
The 256 B in this derivation is the same quantity 0032 reaches from the eight-DataBlock repeat
(`ub_resident_design.md:58`, 8 × 32 B). Two documents in two skills arrive at 256 B by two routes.
They are the same repo and therefore one origin (STRATA S2) — this is a consistency check, not
corroboration, and the distinction matters: two documents can copy one error, and agreement between
them raises priority for verification without raising trust.

The batching pattern upstream ships, same file lines 260-263 and 271-273:
```cpp
for (uint32_t c = 0; c < repeatTimes; c++) {
    uint32_t curMask = (c == repeatTimes - 1) ? tailMask : MAX_MASK;
```
— note this couples the mask limit to the repeat limit of 0031: a loop that batches by mask also
counts repeats, and both counters have caps.

The general form of the rule this entry recommends carrying — derive the element count from a byte
width and `sizeof`, never from a memorised constant — is the same discipline upstream applies
elsewhere via runtime queries (0011). No source in scope states a `mask` ceiling for FP16, BF16 or
int8; those follow from the derivation and are extrapolation, marked as such in §7.

## 4 · Procedure
Proposed, runnable later; not run.

1. Header arm, read-only, no card: `grep -Rn "MAX_MASK\|mask" "$ASCEND_HOME_PATH"/*/include` for
   the `Sub`/`Div` overloads, recording the declared parameter type and any documented range, with
   the header path and toolkit version. A mask carried as a `uint64_t` bitmask behaves differently
   from one carried as a count, and the two readings are not distinguishable from upstream's prose.
2. Device arm, on a named die (occupancy before and after, no substitution): `Sub` over an FP32
   destination poisoned to 0xDEADBEEF, with `mask` set to 63, 64, 65 and 128, and a count of how
   many elements were actually written per call.
3. Repeat for FP16 with `mask` at 127, 128, 129, 256. The claim's derivation predicts the ceiling
   moves to 128; this arm is what tests the extrapolation rather than assuming it.

## 5 · Checker — acceptance declared before the run
Verdict variable `written(mask, dtype)`.
PASS for FP32 iff `written(64) == 64` and `written(65) != 65` — the ceiling identified by a step,
not by an error.
PASS for the derivation iff `written(128, fp16) == 128` and `written(129, fp16) != 129`.
A FP16 ceiling at 64 rather than 128 would mean the limit is an element count rather than a byte
width, overturning the derivation while leaving the FP32 number intact — reported as exactly that,
in two verdicts, rather than as a single pass or fail.
Positive fixture: `written(0)` must be 0 against the poisoned destination. A counter that reports
non-zero with an empty mask is not counting writes and invalidates every other cell.
Exit code is not the verdict; an over-range mask is not stated to fault.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no architecture stated by the source — routing rests on the
mechanism, and the 256 B it derives from has an A2/A3-scoped statement in 0032 but this sentence
does not. This entry establishes the ceiling for `Sub` and `Div` at FP32 only: those are the two
APIs and the one dtype upstream names. The FP16 (128), BF16 (128) and int8 (256) figures are
arithmetic from the derivation and are NOT established — §4 step 3 exists to test them. It does not
establish whether the mask is a count or a bitmask in the installed SDK, which §4 step 1 would
settle and which changes what "64" means.
