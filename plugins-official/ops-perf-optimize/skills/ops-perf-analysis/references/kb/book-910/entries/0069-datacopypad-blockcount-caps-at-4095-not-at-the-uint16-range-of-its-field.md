```
ID:        0069-datacopypad-blockcount-caps-at-4095-not-at-the-uint16-range-of-its-field
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   verified — §4 device arm run on 910B2 2026-08-25 via §5: `blocks_arrived(4095)` = 4095 and
           `blocks_arrived(4096)` = 0 → PASS for the cap; mechanism verdict = **WRAP** (12-bit): 4097 → 1, 5000 → 904,
           5900 → 1804, 8191 → 4095, 8192 → 0 — every arrival count equals blockCount mod 4096; red input
           (`blocks_arrived(8191)` = 8191) NOT met; positive fixture `blocks_arrived(0)` = 0 against the poisoned
           destination ✓. The header arm found no range check in the installed 9.1.0 headers (§6). Previously harvested.
BOARD:     910B2 (measured 2026-08-25); other 910 parts unverified
SOURCE:    ops/ascendc-api-best-practices/references/api-buffer.md:279 — "constexpr uint32_t MAX_BLOCK_COUNT = 4095;  // DataCopyPad blockCount 限制"; ibid:291 — "1. **tileRows 限制**：DataCopyPad 的 `blockCount` 最大 4095"
INDEX:     means=`DataCopyPad` GM→UB, blockLen 32 B, blockCount ∈ {0, 1, 100, 4094, 4095, 4096, 4097, 5000, 5900, 8191,
           8192}, UB destination poisoned 0x5A, block k carries payload 1 + k mod 251; arrivals counted per block
           conditions=CANN 9.1.0, 910B2 die 0, one AIV, direct launch
           readouts: arrived = 0, 1, 100, 4094, 4095, 0, 1, 904, 1804, 4095, 0 — i.e. blockCount mod 4096
           time=2026-08-25
OVERTURN:  a `DataCopyPad` with `blockCount` of 4096 or above transfers all requested blocks correctly on a named DAV_2201 board.
```

# 0069 · DataCopyPad's blockCount caps at 4095, not at the uint16 range of its field

## 1 · Claim
Measured on 910B2: `DataCopyPad`'s `blockCount` is honoured up to **4095** and **wraps modulo 4096** above it —
a request for 4096 blocks moves **none**, 4097 moves one, 5000 moves 904, 8191 moves 4095, 8192 moves none.
The struct field is `uint16_t`; the hardware field is 12 bits, and nothing in the toolkit's headers checks
the range (the header arm found no assert or clamp). So an over-range `blockCount` does not truncate to the
cap and does not fault: it silently delivers `blockCount mod 4096` blocks and leaves the rest of the
destination untouched — the most damaging of §5's three named mechanisms. Not established: whether the
same field width governs UB→GM (`DataCopyPad` out) or `DataCopy`'s `blockCount`; only GM→UB was run.

## 2 · The wrong branch this removes
An agent sizing a batched multi-row copy computes how many rows fit in UB (0003, 0022) and passes
that as `blockCount`. For a narrow row — a few hundred bytes — the row count that fits 192 KB is in
the thousands, and can exceed 4095 without any other constraint objecting. The parameter accepts it,
because the field is wide enough.

What makes this a trap rather than a documented cap: **the type does not warn.** 0026 and 0031
record the opposite pattern — a `uint8_t` field whose type IS the limit, so an over-range value
truncates visibly at 255. Here the field is `uint16_t` and the limit is 4095, so an agent that
audits parameter widths (a reasonable defence learned from 0026 and 0031) computes a ceiling of
65535 and concludes it is safe at 5000. The defence that works elsewhere fails here, and fails
quietly.

4095 is 2¹² − 1, which suggests a 12-bit hardware field behind a 16-bit software one. Upstream does
not say so and this entry does not claim it — but the arithmetic is worth recording because it
predicts the failure mode (wrap at 4096, not saturation), and §4 tests exactly that.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-buffer.md` §"Host 侧 Tiling 计算", lines 277-286,
verbatim:
```cpp
// A2/A3 UB = 192KB
constexpr uint64_t UB_SIZE = 192 * 1024;
constexpr uint32_t MAX_BLOCK_COUNT = 4095;  // DataCopyPad blockCount 限制
...
uint32_t tileRows = (UB_SIZE - overheadBytes) / bytesPerTileRow;
tileRows = std::max(1u, std::min(tileRows, MAX_BLOCK_COUNT));
```
and the 注意事项 restatement, line 291: "1. **tileRows 限制**：DataCopyPad 的 `blockCount` 最大
4095". Note the surrounding code is explicitly A2/A3-scoped by its own comment at line 277
("A2/A3 UB = 192KB"), which is the strongest architecture attribution available for this cap.

**The conflicting statement**, from a different skill in the same repo —
`ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:59-60`
declares the struct:
```cpp
struct DataCopyExtParams {
    uint16_t blockCount;   // 块数量
```
A `uint16_t` admits 65535. Neither document mentions the other, and neither says whether 4095 is a
hardware bound on `DataCopyPad` specifically or a property of the struct. Filed as
`harvest/contradictions-910.md` **C-910-012**.

Note the two are not strictly incompatible — a 16-bit field can carry a value the hardware clamps
at 4095 — but they give an agent two different ceilings, and the tiling clamp above is the only
place upstream acts on either. That the *acting* number is the smaller one is the practical answer;
that no document says why is the finding.

Related caps in this family, each with its own entry: `rightPadding` uint8 at 255 (0026),
`srcStride` uint16 at 65535 DataBlocks (0027). Three parameters, three different bounds, two of
which are their field widths and one of which is not.

## 4 · Procedure
Proposed, runnable later; not run.

1. Header arm, read-only, no card and the one that could settle it cheaply:
   `grep -Rn "blockCount" "$ASCEND_HOME_PATH"/*/include` for the declared type and any documented
   range or `static_assert`, with header path and toolkit version. An SDK header is an independent
   origin from this repo.
2. Device arm, on a named die (occupancy before and after, no substitution): `DataCopyPad` with
   `blockCount` swept over 4094, 4095, 4096, 4097, 8191, 8192 at a small `blockLen`, destination
   poisoned to 0xDEADBEEF.
3. Count how many blocks actually arrived, per value. The 12-bit-wrap hypothesis predicts 4096
   delivers 0 blocks; a clamp predicts it delivers 4095; a soft limit predicts it delivers 4096.
   These are three different outcomes and the procedure must distinguish them rather than reporting
   "wrong".
4. Report the arrival count, not a pass/fail, for every value in the sweep.

**As run (2026-08-25, the 910 machine, die 0, job r5_910):** step 1 as written on the installed 9.1.0 toolkit
(`blockCount` declared `uint16_t` in `kernel_struct_data_copy.h`; no `4095`, `0xFFF`, `MAX_BLOCK_COUNT` or
range assert anywhere under `asc/`). Step 2 with `blockLen` = 32 B (so that block k lands at UB offset 32k
and the arrival count is a byte scan), the destination poisoned to 0x5A5A, each source block filled with
1 + k mod 251 (blocks whose payload happens to equal the poison byte are counted separately as
"ambiguous" and never as arrivals); the sweep gained 100, 5000 and 5900 as extra interior points. A
blockLen = 16 B variant was also run and is NOT used for the verdict: `DataCopyPad` places each block at a
32-B-aligned UB slot regardless of blockLen (910:0023's finding), so a contiguous-16-B arrival scan
mis-counts by construction — recorded as an instrument note.

## 5 · Checker — acceptance declared before the run
Verdict variable `blocks_arrived(blockCount)`.
PASS for the cap iff `blocks_arrived(4095) == 4095` and `blocks_arrived(4096) != 4096`.
The mechanism is a **separate, three-way verdict** and is declared now: wrap (0 arrive), clamp
(4095 arrive), or something else. Which one holds decides whether an over-range request loses
everything or merely truncates, and those call for different defensive coding — a boolean checker
would report both as "the cap exists" and leave the more damaging case unnamed.
Red input for the whole entry: `blocks_arrived(8191) == 8191`, which overturns the cap and makes the
struct's uint16 range the operative bound — resolving C-910-012 the other way.
Positive fixture: `blocks_arrived(0)` must be 0 against the poisoned destination. A counter that
reports blocks arriving when none were requested is not counting arrivals.
Exit code is not the verdict; an over-range `blockCount` is not stated to fault.

## 6 · Evidence
RUN 2026-08-25, 910B2 die 0 (idle before and after), blockLen 32 B, UB destination poisoned:

| blockCount requested | blocks arrived | first missing block | reading |
|---|---|---|---|
| 0 | 0 | 0 | positive fixture: nothing arrives when nothing is asked |
| 1 | 1 | 1 | |
| 100 | 100 (99 + 1 poison-valued) | 100 | |
| 4094 | 4094 | 4094 | |
| 4095 | 4095 | 4095 | **cap honoured** |
| 4096 | **0** | 0 | **wrap** — 4096 mod 4096 |
| 4097 | 1 | 1 | wrap |
| 5000 | 904 | 904 | 5000 − 4096 |
| 5900 | 1804 | 1804 | 5900 − 4096 |
| 8191 | 4095 | 4095 | 8191 mod 4096 — red input NOT met |
| 8192 | 0 | 0 | wrap |

`blocks_arrived(blockCount)` = `blockCount mod 4096` at every point. Header arm: `blockCount` is
`uint16_t` in the `DataCopyExtParams` struct; no range check found in the installed headers. The
kernel never faulted (all launches sync = 0) — an over-range request is silent.

## 7 · Scope limits — what this entry does NOT establish
GM→UB `DataCopyPad` on 910B2 only; the UB→GM direction, `DataCopy` (non-pad), and the AIC side were not
swept. The wrap is inferred from arrival counts at eleven values (consistent with mod 4096 at all of them),
not from a hardware document. blockLen 32 B only for the verdict (see §4 as-run for the 16-B instrument
note). Whether a later CANN adds a host- or compile-time check is not known. Nothing transfers to the 950
book (RULES.md Art. 1).
