```
ID:        0026-datacopypad-rightpadding-is-a-uint8-and-stops-at-255-bytes
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:233 — "**DataCopyPad rightPadding 限制**：`rightPadding` 为 `uint8_t`，最大补零 255 字节。超过此限制需手动分块处理"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `DataCopyPad` with `rightPadding` set above 255 is accepted and pads correctly on a named DAV_2201 board — i.e. the field is wider than `uint8_t` in the installed SDK.
```

# 0026 · DataCopyPad's rightPadding is a uint8 and stops at 255 bytes

## 1 · Claim
Upstream asserts that `DataCopyPadExtParams::rightPadding` is a `uint8_t`, so at most 255 bytes of
padding can be requested, and that exceeding this requires manual blocking. Upstream separately
asserts that padded values participate in subsequent computation, so the padding value must be
chosen so as not to corrupt the result — zero is safe for `ReduceSum` but not necessarily for
`ReduceMax`. Not established here.

## 2 · The wrong branch this removes
An agent computes the padding it needs as `alignedSize - actualSize` and passes it through. For
most shapes the value is small and the cast is invisible. For a wide alignment target — 512 B for
bandwidth (0020), or a 256 B Compare requirement (0034) — the needed padding can exceed 255, and
the `uint8_t` truncates silently: a request for 300 bytes becomes 44. The transfer then succeeds,
pads the wrong amount, and the remaining 256 bytes hold whatever was in the destination.

The second half is a separate and more common error: padding with zeros and then reducing. Zero is
the identity for sum and the *minimum* for max — a `ReduceMax` over a zero-padded row of negative
values returns 0, which is not in the data. The failure is silent, plausible, and shape-dependent
(it only bites when the row needs padding at all).

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md`
§6 注意事项, line 233: "1. **DataCopyPad rightPadding 限制**：`rightPadding` 为 `uint8_t`，最大
补零 255 字节。超过此限制需手动分块处理。"

The struct, lines 67-74 of the same file:
```cpp
template <typename T>
struct DataCopyPadExtParams {
    bool isPad;            // 是否启用填充
    uint8_t leftPadding;   // 左侧填充字节数
    uint8_t rightPadding;  // 右侧填充字节数（最大 255）
    T paddingValue;        // 填充值
};
```
Note `leftPadding` is also `uint8_t` and is not mentioned in the 注意事项 — the same limit applies
and upstream does not say so. Recorded here; not a separate entry, since the wrong branch is
identical.

The value-safety half, line 235: "2. **补零数据的安全性**：补零后的数据参与后续计算，需确保补零
不影响算法正确性。例如 ReduceSum 场景补零安全（0 不影响求和），但 ReduceMax 可能受影响（0 可能
改变最大值）。" Restated as a checklist item at line 347: "- [ ] 补零数据不影响算法正确性
（ReduceMax 场景特别注意）".

Same repo, one origin, and note this is a **software type limit, not a hardware limit** — the same
distinction 0031 draws for `repeatTimes`. A `uint8_t` field caps the value regardless of what the
DMA engine could do, and nothing in the source says the engine is the binding constraint.

## 4 · Procedure
Proposed, runnable later; not run. The first half needs no card at all.

1. Header arm, read-only, permitted in the no-card phase — and the only arm that can establish the
   type: `grep -Rn "rightPadding" "$ASCEND_HOME_PATH"/*/include` (note `-R`, since these trees
   symlink). Record the declared type and the header path and the toolkit version. If it reads
   `uint8_t`, the claim is established at the level it is actually about, and no device is needed.
2. Behaviour arm, on a named die (occupancy before and after, no substitution): request
   `rightPadding` of 254, 255, 256 and 300 with a destination poisoned to 0xDEADBEEF, and count
   how many bytes were actually written past the data. The claim predicts 300 behaves as 44.
3. Value arm: a `ReduceMax` over a padded row of all-negative values, comparing against a host
   reference computed over the unpadded row. The claim predicts a mismatch.

## 5 · Checker — acceptance declared before the run
Three verdicts, kept apart because they are three claims.
`pad_type`: PASS iff the header declares `uint8_t`. Red input: `uint16_t` or wider.
`pad_written(request)`: PASS iff `pad_written(300) == 44` — the truncation, not merely a failure.
A request of 300 that errors out cleanly would OVERTURN the silent-truncation reading while
leaving the 255 cap intact, and must be recorded that way rather than as a pass.
`max_corrupted`: PASS iff the `ReduceMax` result differs from the host reference. This one is
expected to be *true* and confirms a hazard rather than a capability — a clean result here means
the framework masks padding from reductions, which would be better news and a correction to the
entry.
The positive fixture for arm 2: request `rightPadding = 0` with the poison intact and confirm the
counter reports 0 bytes written past the data. If it reports a non-zero count with no padding
requested, the counting method is wrong and arms at other values mean nothing.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no architecture stated by the source, and none is implied — a
struct field width is a software property that may differ between CANN releases while the hardware
does not change. No toolkit version is pinned, because upstream pins none; §4 step 1 exists to
supply one. This entry does not establish that 255 is a hardware limit. It does not establish
`leftPadding`'s behaviour, only that it shares the type. It does not establish which reduction
APIs are padding-safe beyond the two upstream names.
