# CARD 001 · Small-channel transpose budgets `16*C + 32` bytes per element

- **Quote** (`ops/ascendc-perf-optimize/references/tiling/conversion/fallback/tiling-flow.md:28-40`):
  ```
  ubBudget = ubSize - reservedBytes
  perElemBytes = 16*C + 32
  tileNMax = min(
    AlignDown(ubBudget / perElemBytes, 32),   # UB约束
    255 * 16                                     # repeats约束
  )

  tileN = AlignUp(CeilDiv(N, coreNum), 32)     # 先按核数均分
  if tileN > tileNMax:
    minTiles = CeilDiv(N, tileNMax)
    alignedTiles = CeilDiv(minTiles, coreNum) * coreNum
    tileN = AlignUp(CeilDiv(N, alignedTiles), 32)
  ```
  and the scene gate at `:12-19` — `C ≤ 16 (small channel) → 进入本分支`, modelled as `[C, N] → [N, C]`.
- **Guessed book**: 950. No chip named in the file; the family's only architecture word is `dav-3510`
  as a GATHER precondition in `conversion/index.md:43`.
- **Guessed level**: L2 (memory hierarchy & residency) / L3 (data movement & layout).
- **Evidence class**: recipe-no-numbers. No measurement, no case, no board.
- **Why a card and not an entry**: the `16*C + 32` per-element cost is the one budget formula in the
  conversion family, but `reservedBytes` is undefined and `255 * 16` is a repeat-count limit whose
  `255` is the same unsourced `repeatTimes ≤ 255` this project must establish from scratch. Two
  unknowns in a four-line formula; 0163/0164/0165 carry the family's strategy layer, and this
  parameter layer needs the S1/S4 answers before an entry's §4 can be written against it.
- **OVERTURN sketch**: a small-channel transpose on a named 950 board where a tile at
  `ubBudget / (16*C + 32)` overflows UB, or where twice that runs correctly.
- **Cross-refs**: entries 0163, 0164, 0165; `harvest/standing/950-tiling.md` S1, S3, S4.
