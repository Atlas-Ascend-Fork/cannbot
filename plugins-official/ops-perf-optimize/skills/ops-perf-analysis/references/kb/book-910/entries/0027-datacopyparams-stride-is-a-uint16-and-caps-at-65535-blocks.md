```
ID:        0027-datacopyparams-stride-is-a-uint16-and-caps-at-65535-blocks
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:239 — "**DataCopyParams stride 为 uint16_t**：最大 65535；超限需切换到 `DataCopyExtParams`"; ops/ascendc-performance-analysis/references/metrics_reference.md:418 — "| DataCopy GM→L1 | srcStride 不超过 65535 DataBlock | 超出时拆成多条指令 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `DataCopyParams` stride above 65535 is accepted and produces correct addressing on a named DAV_2201 board.
```

# 0027 · DataCopyParams stride is a uint16 and caps at 65535 blocks

## 1 · Claim
Upstream asserts that the stride fields of `DataCopyParams` are `uint16_t`, capping at 65535, and
that `DataCopyExtParams` is the wider-field alternative. Upstream asserts, in a separate document,
that the cap applies specifically to `srcStride` on the GM→L1 path and that the unit is DataBlocks
(32 B), not bytes — so the reachable span is 65535 × 32 B ≈ 2 MB. Not established here.

## 2 · The wrong branch this removes
An agent extracting a column, or a slice with a large row pitch, computes the stride from the
tensor's shape. For a tensor whose row pitch exceeds ~2 MB — which for fp16 means an inner
dimension above roughly one million elements, entirely ordinary in a large embedding or a long
sequence — the stride overflows the 16-bit field. The value wraps rather than faults, so the copy
reads from an address the agent never intended, inside the tensor, producing plausible wrong data
rather than a crash.

The unit is what makes this hard to see: the field counts 32 B blocks, so an agent that reasons in
bytes places the ceiling 32× lower than it is and dismisses the risk, or reasons in elements and
places it wrong by `sizeof(T)`. Two of the three plausible unit assumptions give the wrong answer.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md`
§6 注意事项 line 239: "4. **DataCopyParams stride 为 uint16_t**：最大 65535；超限需切换到
`DataCopyExtParams`。"

The unit and the path, `ops/ascendc-performance-analysis/references/metrics_reference.md:418`:
`| DataCopy GM→L1 | srcStride 不超过 65535 DataBlock | 超出时拆成多条指令 |` — "DataBlock", not
bytes. With the 32 B DataBlock of 0021/0022, that is 2 097 120 B of reachable stride. The
arithmetic is performed here and is not upstream's.

The wider struct upstream points to, from the same design document lines 58-65:
```cpp
struct DataCopyExtParams {
    uint16_t blockCount;   // 块数量
    uint32_t blockLen;     // 每块字节数
    uint32_t srcStride;    // 源地址块间步长（字节）
    uint32_t dstStride;    // 目的地址块间步长（字节）
    uint32_t reserved;     // 保留
};
```
— note that in the Ext form the strides are `uint32_t` **and the comment says the unit is bytes**,
while the narrow form's unit is DataBlocks. So switching to `DataCopyExtParams` to escape the cap
also changes the unit by 32×. An agent that swaps the struct and keeps the value has introduced a
32× addressing error, which is a worse failure than the one it was fixing. That interaction is not
stated anywhere upstream and is the most useful thing in this entry.

Note also `blockCount` remains `uint16_t` in the Ext form: the wider struct widens the strides and
the length, not the count.

Same repo throughout, so one origin; the two statements are from different skills but that does not
make them independent (STRATA S2).

## 4 · Procedure
Proposed, runnable later; not run.

1. Header arm, read-only, no card: `grep -Rn "struct DataCopyParams\|struct DataCopyExtParams" \
   "$ASCEND_HOME_PATH"/*/include` and record the declared field types and any unit comments, with
   the header path and toolkit version. This establishes the type claim and the unit claim at
   their own level of authority, which is the SDK, not this repo.
2. Device arm, on a named die (occupancy before and after, no substitution): a strided GM→UB copy
   with `srcStride` swept over 65534, 65535, 65536, 65540 DataBlocks against a GM tensor large
   enough to make all four legal addresses. Poison the destination first.
3. Compare every element against a host reference and, on mismatch, report which source offset the
   data actually came from — the wrap prediction is that stride 65536 reads as stride 0, and
   identifying the actual source is what distinguishes a wrap from any other corruption.
4. Unit arm: the same copy expressed once through `DataCopyParams` (blocks) and once through
   `DataCopyExtParams` (bytes) with values differing by exactly 32×, and confirm the two produce
   identical data. If they do not, the unit claim is wrong and is the finding.

## 5 · Checker — acceptance declared before the run
`stride_type`: PASS iff the header declares `uint16_t` in the narrow struct and `uint32_t` in the
Ext struct.
`wrap_offset`: PASS iff at stride 65536 the recovered source offset is 0 — the wrap, identified
positively, not merely "wrong data". A clean result at 65536 overturns the cap.
`unit_equiv`: PASS iff the block-unit and byte-unit expressions agree bitwise at 32×.
Arm 4 is this checker's positive fixture and must be run first: express the SAME copy with a
deliberate 32× error and confirm the comparison FINDS it. A comparison that passes on a
deliberately mis-scaled pair cannot certify the correctly-scaled one.
Exit code is not the verdict; a wrapped stride does not fault.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no architecture stated, and as with 0026 a struct field width
is a software property with no pinned toolkit version. This entry does not establish whether
`dstStride` shares the cap — one source names only `srcStride`, the other says "stride" generally.
It does not establish the behaviour on paths other than GM→L1 and GM→UB. The 2 MB reachable span
is arithmetic performed here from two upstream numbers, not an upstream claim. The 32× unit
mismatch between the two structs is read off their comments and would be established properly only
by §4 arm 4.
