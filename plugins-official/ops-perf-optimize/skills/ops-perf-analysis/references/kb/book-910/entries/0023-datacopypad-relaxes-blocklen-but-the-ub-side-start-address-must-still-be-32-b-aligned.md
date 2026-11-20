```
ID:        0023-datacopypad-relaxes-blocklen-but-the-ub-side-start-address-must-still-be-32-b-aligned
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   verified — §4 run on 910B2 2026-08-25; the claim's conclusion (the UB-side start must be 32-B aligned)
           holds, its predicted mechanism does not: UB start offsets 4, 8 and 16 B ABORT the kernel (507035) rather
           than mis-placing rows, and at aligned starts `DataCopyPad` places every block at a 32-B-pitched UB slot
           regardless of a 4-B blockLen, so §5's predicted row pattern cannot occur (at offset 0 all rows but row 0
           mismatch a 4-B-pitch reference; the 32-B-pitch control has zero bad rows — the declared gate). Corrected
           in place; red input (no bad rows at any offset) NOT met. Previously harvested.
BOARD:     910B2 (measured 2026-08-25); other 910 parts unverified
SOURCE:    ops/ascendc-api-best-practices/references/api-datacopy.md:123 — "`DataCopyPad(GM, UB, ...)` 与 `DataCopyPad(UB, GM, ...)` 的 **UB 端起始地址必须 32 字节对齐**（blockLen 可以非 32B 对齐，但起始地址不能）"
INDEX:     means=`DataCopyPad` GM→UB, 64 blocks × 4 int8, UB destination poisoned 0x5A, UB start offset ∈ {0, 4, 8,
           16, 32, 64} B; per-row compare against a 4-B-pitch reference and against a 32-B-pitch reference
           conditions=CANN 9.1.0, 910B2 die 0, one AIV
           readouts: offsets 4 / 8 / 16 → 507035 (kernel aborted); offsets 0 / 32 / 64 → 63 of 64 rows mismatch the
           4-B-pitch reference (row 0 correct, bytes 01 02 03 04), 0 of 64 mismatch the 32-B-pitch reference
           time=2026-08-25
OVERTURN:  a `DataCopyPad` whose UB-side start address is deliberately offset by a non-multiple of 32 B is shown to produce correct data on a named DAV_2201 board.
```

# 0023 · DataCopyPad relaxes blockLen, but the UB-side start address must still be 32 B aligned

## 1 · Claim
Measured on 910B2: `DataCopyPad` GM→UB with a `blockLen` of 4 bytes runs only when the UB-side start
address is 32-B aligned — starts of 4, 8 and 16 bytes **abort the kernel with 507035**, starts of 0, 32 and
64 run — and at an aligned start it places **each block at its own 32-B-pitched UB slot**: 64 four-byte rows
occupy 64 × 32 B, the 28 bytes after each row keep their poison, and a program that expects the rows
packed at a 4-B pitch reads 63 of 64 rows wrong. Upstream's sentence — blockLen is relaxed, the UB start
is not — is therefore right, and stronger than it reads: the misaligned start is a fault, not a silent
mis-placement, and the "relaxed" blockLen still consumes a whole 32-B block per row in UB. Not
established: the UB→GM direction and dtypes wider than int8.

Inference, stated separately: the row pattern §5 predicted (rows at multiples of 8 clean, the rest not)
assumed rows packed at 4 B with the alignment re-established every 32 B; on this part the hardware never
packs them, so that pattern is unobservable — the entry's conclusion survives on a different mechanism.

## 2 · The wrong branch this removes
This is the trap that sits immediately behind 0021's fix. An agent hits the 32 B length constraint,
learns that `DataCopyPad` is the answer, switches to it, and reasonably concludes that alignment is
now handled — the API's whole purpose is unaligned data, and its name says pad. It then indexes
into a UB tensor row by row (`stridedBuf[row * cols]`) and every row whose byte offset is not a
multiple of 32 violates a constraint that the API it just adopted was supposed to have removed.

Two things make this worse than the plain length case. First, the failure is data-dependent on the
*row index*, so a test with a single row, or with a row count that happens to be a multiple of 8,
passes. Second, the constraint is on the address, which is computed by pointer arithmetic the agent
wrote rather than passed as a parameter, so it does not appear in any argument list an audit would
inspect.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-datacopy.md` §"UB 端起始地址 32B 对齐（易踩坑）",
line 123 verbatim: "`DataCopyPad(GM, UB, ...)` 与 `DataCopyPad(UB, GM, ...)` 的 **UB 端起始地址
必须 32 字节对齐**（blockLen 可以非 32B 对齐，但起始地址不能）。"

The concrete failing case, line 129: "// 例如 fp8 + cols=4 时每行 4 字节，只有 row ∈ {0, 8, 16,...}
满足 32B 对齐". Arithmetic checked here: 4 B per row × 8 rows = 32 B ✓, so every eighth row is
aligned and the other seven are not.

The fix upstream gives, lines 133-143: "修复方式：引入 strided staging buffer，把不规则行宽数据
重排到每行 32B 对齐的连续区" with
`DataCopyPad(gmOut[off], stridedBuf[row * 32], copyParams);  // src 每行 32B 对齐` — note the
staging buffer's row pitch is 32 B rather than the data's 4 B, so the fix costs 8× the UB for this
shape. That cost is part of the knowledge and is stated here rather than left for the agent to
discover.

Related and NOT the same claim: line 249 of
`ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md` —
"9. **列提取时 srcStride 和 blockLen 必须满足 32B 对齐**：每次提取一个子字段需多次搬运调用." That
is a constraint on `srcStride` and `blockLen` in the column-extraction case, which contradicts the
general "blockLen 可以非 32B 对齐" above unless the column case is special. Filed as
`harvest/contradictions-910.md` **C-910-006**: `DataCopyPad` is the API an agent adopts specifically
to escape `DataCopy`'s length constraint (0021), so whether that escape survives in the strided case
decides whether a whole class of column extractions is legal. §4 below tests the address constraint
only, so a run of it leaves the row open — §7 says so.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. One binary; the UB-side base offset is a runtime argument swept over 0, 4, 8, 16, 32 bytes with
   fp8 (or int8) data at 4 columns per row and 64 rows.
3. Poison the destination (0xDEADBEEF pattern) before each launch so an unwritten region is
   distinguishable from a zero-written one, and verify every element against a host reference.
4. Report mismatches per row index, not only in aggregate. The claim predicts a specific pattern —
   rows at multiples of 8 clean, others not — and an aggregate count would confirm "something is
   wrong" without confirming the mechanism.

**As run (2026-08-25, the 910 machine, die 0, job r5_910):** one binary; UB start offset a runtime argument
swept over 0, 4, 8, 16, 32, 64 B; int8 data, 64 rows × 4 columns, `DataCopyExtParams{64, 4, 0, 0}`; UB
poisoned 0x5A before the copy; the whole 8 KB UB region copied back to GM and every row compared against
(a) a 4-B-pitch reference (§5's "natural pitch") and (b) a 32-B-pitch reference (§5's staging-layout
control, `rightPadding` 28). Exit codes were recorded but the verdict is the per-row pattern as declared.
Deviation: offsets 4, 8, 16 produced no rows to compare — the launch synchronised with 507035; that
outcome is recorded as the finding it is, not as a missing point.

## 5 · Checker — acceptance declared before the run
Verdict variable `bad_rows(offset)`, the set of row indices with any mismatch.
Gate: at offset 0 with a 32 B row pitch (the staging-buffer layout), `bad_rows` must be empty. If
the aligned control fails, nothing else in the run means anything.
PASS iff at offset 0 with the natural 4 B pitch, `bad_rows` is exactly the complement of
{0, 8, 16, …} — the predicted pattern, not merely a non-empty set.
This distinction is the point. A checker that passed on "some rows wrong" would also pass if the
kernel were broken for an unrelated reason; requiring the predicted index pattern means the run
either confirms the stated mechanism or reports something the entry did not predict, and the
latter is recorded as a finding rather than rounded to a pass.
Red input: `bad_rows` empty at every offset, which overturns the claim.
Exit code is not the verdict.

## 6 · Evidence
RUN 2026-08-25, 910B2 die 0 (idle before and after).

| UB start offset | pitch expected by the reference | result |
|---|---|---|
| 0 | 4 B (packed) | 63 of 64 rows mismatch; row 0 = 01 02 03 04 correct |
| 4 | 4 B | **kernel aborted, sync = 507035** |
| 8 | 4 B | **kernel aborted, sync = 507035** |
| 16 | 4 B | **kernel aborted, sync = 507035** |
| 32 | 4 B | 63 of 64 rows mismatch; row 0 correct; byte before the start still poison (0x5A) |
| 64 | 4 B | 63 of 64 rows mismatch; row 0 correct |
| 0 | 32 B (one block per row) | **0 bad rows** — gate green |
| 32 | 32 B | **0 bad rows**; poison intact before the start |

Gate (aligned control, 32-B pitch): green. PASS pattern (rows ≠ multiples of 8 bad, at a 4-B pitch): NOT
observed — every row but the first is "bad" against a 4-B pitch because the rows sit 32 B apart; red input
(no bad rows at any offset): NOT met. Recorded as a finding: the claim's conclusion stands on a mechanism
(abort + 32-B block pitch) different from the one §5 predicted.

## 7 · Scope limits — what this entry does NOT establish
910B2 only; GM→UB only; int8 only; `blockLen` 4 B only (a 16-B or 24-B blockLen may behave differently at
the block boundary); offsets between 16 and 32 B and above 64 B not swept. Whether the 507035 at a
misaligned UB start is raised by the DataCopyPad instruction itself or by an address check in the runtime
is not established — the code is the generic vector-side abort. Nothing transfers to the 950 book (RULES.md
Art. 1).
