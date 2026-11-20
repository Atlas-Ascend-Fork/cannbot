```
ID:        0021-datacopy-between-gm-and-ub-is-legal-only-when-the-transfer-is-strictly-32-b-aligned
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; several files in that repo state it, which is one origin
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/SKILL.md:71 — "| `DataCopy(GM↔UB)` | 仅当搬运数据**严格 32 字节对齐**时允许使用 | 非对齐场景必须使用 `DataCopyPad` |"; ops/ascendc-api-best-practices/references/api-datacopy.md:86 — "**DataCopy 要求 32 字节对齐**，非对齐会导致数据错误"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `DataCopy` of a deliberately non-32 B-aligned length between GM and UB is shown to produce correct data on a named DAV_2201 board across shapes and dtypes.
```

# 0021 · DataCopy between GM and UB is legal only when the transfer is strictly 32 B aligned

## 1 · Claim
Upstream asserts that `DataCopy` may be used between GM and UB only when the transferred data is
strictly 32-byte aligned, that non-aligned use causes wrong data rather than an error, and that
`DataCopyPad` is mandatory otherwise. Upstream asserts that 32 B is the DataBlock granularity,
spelled `ONE_BLK_SIZE = 32`. Not established here.

## 2 · The wrong branch this removes
`DataCopy` is the simpler call and the one every example uses. An agent whose shapes happen to be
aligned develops the habit, then meets a shape whose inner axis is not a multiple of 32 B — an
fp32 row of 5 elements, an fp16 row of 13 — and the call still compiles and still runs. Upstream's
word is 数据错误, wrong data, not a fault: nothing traps. The corruption is at the tail of each
row, so a spot check of the first elements passes and a mean-based tolerance check may pass too.
The agent's next debugging step is usually the compute kernel, not the copy.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/SKILL.md:71`, in the 强制规则 table:
```
| `DataCopy(GM↔UB)` | 仅当搬运数据**严格 32 字节对齐**时允许使用 | 非对齐场景必须使用 `DataCopyPad` |
```
`ops/ascendc-api-best-practices/references/api-datacopy.md` §"32 字节对齐要求", line 86:
"**DataCopy 要求 32 字节对齐**，非对齐会导致数据错误。" and the selection table at line 25:
"| **数据量严格 32 字节对齐** | `DataCopy` 或 `DataCopyPad` | 确定对齐时 DataCopy 可用，
DataCopyPad 更安全 |".

The granularity restated with its constant name,
`ops/ascendc-performance-analysis/references/metrics_reference.md:144`:
`| UB (Unified Buffer) | **32B** | ONE_BLK_SIZE = 32，DataBlock 对齐 |`, and line 405 of the same
file: `| UB 对齐 | 32B 对齐 | 使用非对齐搬运接口或冗余数据技巧 |`. The per-dtype element counts
are at `ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:88-92`:
FP32 8 elements, FP16/BF16 16, INT8 32 — all one 32 B block.

All of the above are the same repo and therefore one origin (RULES.md Art. 3, STRATA S2). A genuinely
independent origin would be the vendor's published AscendC API documentation or the installed
SDK's `DataCopy` header contract; neither was consulted.

**This corrects a survey claim.** `harvest/surveys/DEEPDIVE_20260824_perf-optimize.md` §5.3 lists
"32 B DataCopy block granularity" under "ESTABLISH FROM SCRATCH (no upstream authority, npu-arch
does not supply them)". The parenthetical is right — npu-arch supplies it nowhere — but the
headline is wrong: `ascendc-api-best-practices` supplies it directly and repeatedly. The
constant is therefore a harvested entry, not a standing question. See this book's final report for
the other items on that list that failed the same re-verification.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Two arms over the same shape family, one binary, alignment chosen by a runtime argument:
   - Arm A: element counts that are exact multiples of `32 / sizeof(T)`.
   - Arm B: element counts one element short of that, so the transfer is 4 B (fp32) or 2 B (fp16)
     short of a block.
3. Pre-fill the destination UB region and the GM destination with a recognisable poison pattern
   (0xDEADBEEF), so that "not written" is distinguishable from "written with zeros" — a zero-filled
   destination would make a partial copy look like a correct copy of sparse data.
4. Compare every element against a host-computed reference; report mismatch count and the
   positions. Sweep dtypes fp32, fp16, int8, since the block holds a different element count in
   each and the tail behaviour may differ.

## 5 · Checker — acceptance declared before the run
Verdict variable `mismatch_B`, the per-element mismatch count in arm B, with `mismatch_A` as the
control.
Gate first: `mismatch_A` must be 0. If the aligned arm is wrong, the harness is wrong and arm B
carries no information.
PASS (claim upheld) iff `mismatch_A == 0 && mismatch_B > 0` for at least one dtype.
The poison pattern is what lets this checker go red honestly: without it, an unwritten tail full of
zeros compared against a reference that also happens to be near zero would be scored as a match.
The specific input that makes it fail: if arm B is clean across all three dtypes, the claim is
overturned for those dtypes and the entry is narrowed in place — not quietly kept.
Exit code is not the verdict; a wrong-data outcome does not raise a fault, which is the whole
point of the claim.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; per-arch at best, and the sources carry no architecture at
all — the routing to this book rests on the mechanism being 910-era SIMD DataCopy with no
regbase/SIMT vocabulary, not on an arch marker. This entry does not establish what the wrong data
looks like, nor whether the corruption is at the head or the tail. It does not cover GM↔L1,
UB↔L1, or L0 paths, whose alignment rules are different (0028). It does not establish the
*address* alignment rule, which is a separate claim carried by 0023 and which upstream states with
a different scope.
