```
ID:        0068-ub-side-stride-counts-32-byte-blocks-while-gm-side-stride-counts-bytes
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-buffer.md:293 — "**stride 计算**：UB 侧 stride 单位是 32 字节块，GM 侧是字节"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a strided copy on a named DAV_2201 board addresses correctly with both strides expressed in the same unit — i.e. the UB side accepts bytes.
```

# 0068 · UB-side stride counts 32-byte blocks while GM-side stride counts bytes

## 1 · Claim
Upstream asserts that in a strided copy the UB-side stride is expressed in units of 32-byte blocks
while the GM-side stride is expressed in bytes. Not established here.

## 2 · The wrong branch this removes
Two stride fields in one parameter struct, in different units, differing by 32×. An agent computes
both from the same tensor geometry — which is the only sensible way to compute them — and one of
the two is wrong by a factor of 32. Nothing rejects it: the transfer runs, addresses land inside the
allocation for small tensors, and the data is silently scrambled or drawn from the wrong rows.

Three things make this worse than an ordinary unit slip:
- **It is asymmetric by design**, so the usual defence (compute once, use twice) is exactly what
  fails. Correct code must convert deliberately in one direction and not the other.
- **The direction is not memorable.** "UB is blocks, GM is bytes" has no mnemonic behind it, and
  the reverse assumption is equally plausible — a developer who thinks "device-side is finer
  grained" gets it backwards.
- **It compounds 0027.** That entry records that escaping the narrow `DataCopyParams` (uint16
  strides in DataBlocks) to `DataCopyExtParams` (uint32 strides in **bytes**) changes the unit by
  32× on the *same side*. So there are now two independent 32× unit switches in the same API family
  — one between sides, one between struct variants — and an agent can hit either or both.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-buffer.md` §"批量搬运 + 逐行计算模式" 注意事项,
line 293, verbatim: "3. **stride 计算**：UB 侧 stride 单位是 32 字节块，GM 侧是字节".

The 32-byte block is the DataBlock of 0021 and 0022 (`ONE_BLK_SIZE = 32`), so the unit is the
architecture's fundamental movement granularity rather than an arbitrary choice — which makes the
rule learnable once stated, and is worth stating for that reason.

The related unit switch, from a different skill, same repo (one origin) —
`ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:58-65`
declares `DataCopyExtParams` with "`uint32_t srcStride;    // 源地址块间步长（**字节**）`", against
`ops/ascendc-performance-analysis/references/metrics_reference.md:418` for the narrow form —
"| DataCopy GM→L1 | srcStride 不超过 65535 **DataBlock** |". That pair is 0027's subject.

Neither statement is elaborated anywhere in scope: no source in scope gives a worked strided-copy
example with both strides computed from one shape, which is exactly the artefact that would make
the rule safe to apply. §4 builds one.

Same-repo throughout: one origin. An installed SDK header's parameter documentation would be an
independent origin and was not consulted.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Build one strided GM↔UB copy over a known pattern — a 2-D tensor whose every element encodes its
   own (row, col) — with the UB-side stride expressed in 32-byte blocks and the GM-side in bytes,
   per the claim.
3. Build the deliberately-wrong twin: both strides in bytes. Predicted to mis-address.
4. And the other wrong twin: both in blocks.
5. Poison the destination (0xDEADBEEF) before each launch, then verify every element and, on
   mismatch, decode which source element actually arrived. Reporting *where the data came from* —
   rather than only that it is wrong — is what distinguishes a 32× stride error from any other
   corruption and confirms the mechanism rather than the symptom.
6. Sweep dtypes fp32, fp16, int8, since the element-to-block ratio differs in each and a
   units-in-elements confusion would show a dtype dependence that a units-in-bytes one would not.

## 5 · Checker — acceptance declared before the run
Verdict: per arm, `bad_positions` and the decoded source-offset map.
PASS iff the claim's arm is bitwise correct AND both wrong twins mis-address, AND the decoded
offsets in the both-bytes twin are consistent with the UB side having been scaled by 32.
That last clause is the mechanistic check. A checker that only asked "is the claimed arm correct"
would pass on an implementation where strides are ignored entirely, and both wrong twins would also
pass — so the wrong twins are this procedure's planted positives and must FAIL for the run to mean
anything.
Red input: all three arms bitwise correct, which would mean the unit distinction has no effect here
and overturns the claim for this path.
Exit code is not the verdict; a mis-addressed copy does not fault.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no architecture stated by the source — routing rests on the
mechanism being 910-era SIMD DataCopy with no regbase/SIMT vocabulary. This entry does not
establish which API surface the rule applies to: `DataCopyParams`, `DataCopyExtParams` and the
`Nd2NzParams` family all carry stride fields and upstream's sentence names none of them. That gap
matters, because 0027 records that the Ext form's comment says bytes on the source side too. It
does not establish the unit for `dstStride` specifically, nor for L1-side strides. It does not cover
the `blockCount` field, whose own cap is 0069.
