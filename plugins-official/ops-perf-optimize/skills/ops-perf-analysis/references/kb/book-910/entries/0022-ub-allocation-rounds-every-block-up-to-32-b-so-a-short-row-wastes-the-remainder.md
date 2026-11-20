```
ID:        0022-ub-allocation-rounds-every-block-up-to-32-b-so-a-short-row-wastes-the-remainder
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-datacopy.md:317 — "UB 分配以 **32 字节（dataBlock）** 为最小单位。非对齐 `blockLen` 场景，实际 UB 占用按 `ceil(blockLen * sizeof(T), 32)` 计算"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a UB budget on a named DAV_2201 board is shown to accommodate a multi-row `DataCopyPad` whose rows are short, at exactly `rows × blockLen × sizeof(T)` bytes with no rounding.
```

# 0022 · UB allocation rounds every block up to 32 B, so a short row wastes the remainder

## 1 · Claim
Upstream asserts that UB is allocated in units of 32 B (one dataBlock), and that for a non-aligned
`blockLen` the actual UB consumed is `ceil(blockLen * sizeof(T), 32)` per block, not the nominal
byte count. Upstream gives three worked cases: 8 fp32 elements occupy 32 B with no waste; 5 fp32
elements occupy 32 B and waste 12 B; 13 fp16 elements occupy 32 B and waste 6 B. Not established
here.

## 2 · The wrong branch this removes
An agent budgets UB as `rows × cols × sizeof(T)` — the arithmetic the data itself suggests — and
sizes its tile to fill the 192 KB (0003). With a short inner axis the real occupancy is higher,
sometimes far higher: at 5 fp32 elements per row the multiplier is 32/20 = 1.6×, so a budget that
fits on paper over-commits UB by 60 %. The failure is a launch-time allocation problem whose
message points at the buffer, not at the row width that caused it.

The inverse error is also live: an agent that discovers the rounding and pads its rows to 32 B in
*GM* has changed the data layout, and the padding then travels through every subsequent copy. The
rounding is a UB-occupancy property, not an instruction to reshape the source.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-datacopy.md:317` and the table at 325-329, verbatim:
"UB 分配以 **32 字节（dataBlock）** 为最小单位。非对齐 `blockLen` 场景，实际 UB 占用按
`ceil(blockLen * sizeof(T), 32)` 计算："
```
| 场景 | blockLen(元素) | dtype | 实际数据 | UB 占用 |
| 对齐 | 8 | fp32 | 32B | 32B（无浪费） |
| 非对齐 | 5 | fp32 | 20B | 32B（浪费 12B） |
| 非对齐 | 13 | fp16 | 26B | 32B（浪费 6B） |
```
Arithmetic checked here: 5 × 4 = 20 B → ceil to 32, waste 12 ✓; 13 × 2 = 26 B → ceil to 32, waste
6 ✓. Both rows are internally consistent.

The same 32 B block is the alignment requirement of 0021 and the bank row width of 0013 — three
different consequences of one granularity, which is why they are three entries rather than one
(different wrong branches, per this book's merge test).

The alignment helper upstream ships, same file line 226:
`uint32_t rLengthAlign = (rLength + 7) / 8 * 8;   // 对齐到 8 元素（FP32 下 32 字节）`.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Binary-search the ceiling rather than measuring a byte count, which is not directly observable:
   for a fixed row count `R` and dtype fp32, sweep `cols` over 5, 6, 7, 8 and for each find the
   largest `R` for which the kernel still launches. The claim predicts identical maximum `R` for
   cols 5, 6, 7 and 8 (all round to one 32 B block), and half that for cols 9..16 (two blocks).
3. Report the maximum `R` per `cols` and the host-side nominal byte figure alongside, so the ratio
   between nominal and effective is visible.
4. Confirm the launch failure is an allocation failure and not something else, by checking that
   `R_max + 1` fails and `R_max` succeeds repeatably across five attempts.

## 5 · Checker — acceptance declared before the run
Verdict variable `Rmax(cols)` for cols in 5..16.
PASS iff `Rmax(5) == Rmax(6) == Rmax(7) == Rmax(8)` and `Rmax(9) ≈ Rmax(8) / 2`.
The step structure is the claim; a smooth `Rmax` that scales as `1/cols` overturns it, and that is
the specific red input — it is what a no-rounding allocator would produce, and it is what an agent
budgeting nominally expects.
This checker is not reading only the lines it expects: it takes the whole `Rmax` curve over twelve
points rather than testing the single quoted case of 5 fp32 elements, so a rounding granularity
other than 32 B (say 64 B) would show as steps in the wrong places rather than as a pass.
Exit code is not the verdict — a launch failure is the *signal* here, so a non-zero exit is
expected on every probe above `Rmax`.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no architecture stated by the source. This entry does not
establish that the framework allocator, as opposed to the hardware, imposes the rounding — §4
cannot separate those. It does not establish the behaviour for `blockCount > 1` with a non-zero
`dstStride`, where the stride may absorb or add to the waste. It does not establish anything about
L1 or L0 allocation granularity. The three worked cases are fp32 and fp16 only; int8 and bf16 are
not covered by the source.
