### Key Differences from Standard GELU Vector Epilogue

- **2D tile-based processing**: Uses `CopyGm2Ub`/`CopyUb2Gm` for 2D tile transfers (not row-by-row `DataCopyPad`)
- **Tile broadcast operations**: `TileRowBroadcastMul`, `TileBrcbOneBlk`, `TileColBroadMul` for vectorized dequant
- **EPILOGUE_TILE_M sub-tiles**: Processes 32 rows at a time within each L1_M × L1_N tile
- **Batch scale loading**: Scale[N] loaded once per L1 tile, PerTokenScale[epRows] loaded per epilogue sub-tile
- **Per-stage workspace sync**: Matches KernelCube's double-buffered workspace protocol
- **Extra GM inputs**: Scale[N] (float, column-wise) and PerTokenScale[M] (float, row-wise)

### Example Input DSL (vector scope)
```python
with tl.scope('vector'):
    num_sub = tl.get_num_sub_blocks()
    subcore_id = tl.get_sub_block_id()
    aicore_id = tl.program_id() // num_sub
    aicore_num = tl.num_programs() // num_sub
    EPILOGUE_TILE_M = 32

    ub_c = tl.alloc_ub(EPILOGUE_TILE_M * L1_N, dtype=tl.int32)
    ub_float = tl.alloc_ub(EPILOGUE_TILE_M * L1_N, dtype=tl.float32)
    ub_d = tl.alloc_ub(EPILOGUE_TILE_M * L1_N, dtype=tl.half)
    ub_scale = tl.alloc_ub(L1_N, dtype=tl.float32)
    ub_pertoken = tl.alloc_ub(EPILOGUE_TILE_M, dtype=tl.float32)
    ub_pertoken_brcb = tl.alloc_ub(EPILOGUE_TILE_M * blk_size, dtype=tl.float32)

    stage_id = 0
    for loop_idx in range(aicore_id, total_loops, aicore_num):
        tl.cross_core_wait(flag_aic_store[stage_id])
        # ... subcore partition, boundary check ...
        # Pre-load Scale[col_start..+actual_n] once per L1 tile
        tl.load_1d(Scale[col_start], ub_scale, count=actual_n)

        for ep_start in range(0, curr_m, EPILOGUE_TILE_M):
            ep_rows = min(EPILOGUE_TILE_M, curr_m - ep_start)
            # Batch load PerTokenScale for this epilogue tile
            tl.load_1d(PerTokenScale[row_start + ep_start], ub_pertoken, count=ep_rows)
            # 2D tile load from workspace
            tl.load_2d(workspace[ws_offset], ws_layout, ub_c, ub_layout)
            # Dequant pipeline:
            tl.vcast(ub_float, ub_c)                    # int32 → float
            # tile_row_broadcast_mul(ub_float, ub_scale)  # × Scale[N] row broadcast
            # tile_brcb_one_blk(ub_pertoken_brcb, ub_pertoken)  # expand PerTokenScale
            # tile_col_broadcast_mul(ub_float, ub_pertoken_brcb)  # × PerTokenScale col broadcast
            tl.vcast(ub_d, ub_float)                    # float → fp16
            # 2D tile store to output
            tl.store_2d(Y[out_offset], out_layout, ub_d, ub_layout)

        tl.cross_core_set(flag_aiv_compute[stage_id])
        stage_id = (stage_id + 1) % WORKSPACE_STAGES
```

### Example Output (KernelVector)
```cpp
class KernelVector {
public:
    __aicore__ inline void Init(GM_ADDR workspace, GM_ADDR scale, GM_ADDR per_token_scale,
                                GM_ADDR y, uint32_t M, uint32_t N, uint32_t K) {
        this->M = M;
        this->N = N;

        GemmCoord problemShape{M, N, K};
        blockScheduler = BlockScheduler(problemShape, MakeCoord(L1Shape::M, L1Shape::N));
        totalTiles = blockScheduler.GetCoreLoops();

        aicoreIndex = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
        subcoreIndex = AscendC::GetSubBlockIdx();
        coreNum = AscendC::GetBlockNum();

        gmC.SetGlobalBuffer((__gm__ ElementC *)workspace);
        gmScale.SetGlobalBuffer((__gm__ float *)scale);
        gmPerToken.SetGlobalBuffer((__gm__ float *)per_token_scale);
        gmD.SetGlobalBuffer((__gm__ ElementD *)y);

        // Initialize per-stage flag IDs (same convention as KernelCube)
        for (uint32_t s = 0; s < WORKSPACE_STAGES; ++s) {
            flagAicStore[s] = FLAG_AIC_STORE_BASE + s * 2;
            flagAivCompute[s] = FLAG_AIV_COMPUTE_BASE + s * 2;
        }

        // Buffer sizes for tile-based processing
        constexpr uint32_t epTileN = L1Shape::N;
        constexpr uint32_t tileElements = EPILOGUE_TILE_M * epTileN;
        constexpr uint32_t eleNumPerBlk = BYTE_PER_BLK / sizeof(float);  // 8
        constexpr uint32_t brcbElements = EPILOGUE_TILE_M * eleNumPerBlk; // 32*8=256

        pipe.InitBuffer(inQueueC, 1, tileElements * sizeof(ElementC));
        pipe.InitBuffer(outQueueD, 1, tileElements * sizeof(ElementD));
        pipe.InitBuffer(tmpBufFloat, tileElements * sizeof(float));
        pipe.InitBuffer(inQueueScale, 1, epTileN * sizeof(float));
        pipe.InitBuffer(tmpBufScaleF32, epTileN * sizeof(float));
        pipe.InitBuffer(inQueuePerToken, 1, EPILOGUE_TILE_M * sizeof(float));
        pipe.InitBuffer(tmpBufPerToken, EPILOGUE_TILE_M * sizeof(float));
        pipe.InitBuffer(tmpBufPerTokenBrcb, brcbElements * sizeof(float));
    }

    __aicore__ inline void Process() {
        // Workspace layout: L1_M * coreNum * WORKSPACE_STAGES x L1_N
        LayoutC wsLayout(L1Shape::M * coreNum * WORKSPACE_STAGES, L1Shape::N);

        uint32_t stageId = 0;

        for (uint32_t loopIdx = aicoreIndex; loopIdx < totalTiles;
             loopIdx += coreNum) {
            GemmCoord blockCoord = blockScheduler.GetBlockCoord(loopIdx);
            GemmCoord actualBlockShape = blockScheduler.GetActualBlockShape(blockCoord);

            // Wait for AIC to finish storing to this workspace slot
            AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(flagAicStore[stageId]);

            uint32_t actualM = actualBlockShape.m();
            uint32_t actualN = actualBlockShape.n();

            // Subcore division along M
            uint32_t subM = (actualM + AscendC::GetSubBlockNum() - 1) / AscendC::GetSubBlockNum();
            uint32_t subOffsetM = subcoreIndex * subM;
            uint32_t currM = (subOffsetM + subM <= actualM) ? subM :
                             (actualM > subOffsetM ? actualM - subOffsetM : 0);

            if (currM > 0) {
                // Workspace row base for this stage+core
                uint32_t wsRowBase = (stageId * coreNum + aicoreIndex) * L1Shape::M + subOffsetM;
                // Output coordinates
                uint32_t outRowBase = blockCoord.m() * L1Shape::M + subOffsetM;
                uint32_t outColBase = blockCoord.n() * L1Shape::N;

                // Pre-load Scale[outColBase..+actualN] once per L1 tile
                LoadScale(outColBase, actualN);

                // Process in epilogue tiles of EPILOGUE_TILE_M rows
                for (uint32_t epStart = 0; epStart < currM; epStart += EPILOGUE_TILE_M) {
                    uint32_t epRows = (epStart + EPILOGUE_TILE_M <= currM) ?
                                      EPILOGUE_TILE_M : (currM - epStart);

                    // Batch load PerTokenScale for this epilogue tile
                    LoadPerTokenScale(outRowBase + epStart, epRows);

                    // 2D tile copy from workspace (workspace layout stride)
                    CopyInFromWorkspace(wsRowBase + epStart, epRows, actualN, wsLayout);

                    // Dequantize using tile broadcast ops
                    Compute(epRows, actualN);

                    // 2D tile copy to output (output layout stride)
                    CopyOutToOutput(outRowBase + epStart, outColBase, epRows, actualN);
                }
            }

            // Signal AIV done with this workspace slot
            AscendC::CrossCoreSetFlag<0x2, PIPE_MTE3>(flagAivCompute[stageId]);

            stageId = (stageId + 1 < WORKSPACE_STAGES) ? (stageId + 1) : 0;
        }
        AscendC::PipeBarrier<PIPE_ALL>();
    }

private:
    __aicore__ inline void LoadScale(uint32_t colStart, uint32_t count) {
        // Load Scale[colStart..colStart+count] from GM to UB
        AscendC::LocalTensor<float> scaleIn = inQueueScale.AllocTensor<float>();
        AscendC::DataCopyPadExtParams<float> padParams(false, 0, 0, 0);
        AscendC::DataCopyPad(scaleIn, gmScale[colStart],
                             AscendC::DataCopyExtParams(1, count * sizeof(float), 0, 0, 0),
                             padParams);
        inQueueScale.EnQue(scaleIn);

        AscendC::LocalTensor<float> scaleDeq = inQueueScale.DeQue<float>();
        AscendC::LocalTensor<float> scaleF32 = tmpBufScaleF32.Get<float>();
        AscendC::Adds(scaleF32, scaleDeq, 0.0f, count);  // copy to compute buffer
        inQueueScale.FreeTensor(scaleDeq);
    }

    __aicore__ inline void LoadPerTokenScale(uint32_t rowStart, uint32_t count) {
        // Batch load PerTokenScale[rowStart..rowStart+count] from GM to UB
        AscendC::LocalTensor<float> ptIn = inQueuePerToken.AllocTensor<float>();
        AscendC::DataCopyPadExtParams<float> padParams(false, 0, 0, 0);
        AscendC::DataCopyPad(ptIn, gmPerToken[rowStart],
                             AscendC::DataCopyExtParams(1, count * sizeof(float), 0, 0, 0),
                             padParams);
        inQueuePerToken.EnQue(ptIn);

        AscendC::LocalTensor<float> ptDeq = inQueuePerToken.DeQue<float>();
        AscendC::LocalTensor<float> ptBuf = tmpBufPerToken.Get<float>();
        AscendC::Adds(ptBuf, ptDeq, 0.0f, count);  // copy to compute buffer
        inQueuePerToken.FreeTensor(ptDeq);
    }

    __aicore__ inline void CopyInFromWorkspace(uint32_t wsRow, uint32_t rows, uint32_t cols,
                                                LayoutC const &wsLayout) {
        // 2D tile copy from workspace using CopyGm2Ub helper
        AscendC::LocalTensor<ElementC> ubC = inQueueC.AllocTensor<ElementC>();
        auto tileShape = MakeCoord(rows, cols);
        auto ubStride = MakeCoord((int64_t)L1Shape::N, 1L);
        layout::RowMajor ubLayout(tileShape, ubStride);
        copyGmToUbC(ubC, gmC[wsLayout.GetOffset(MakeCoord(wsRow, (uint32_t)0))],
                     ubLayout, wsLayout.GetTileLayout(tileShape));
        inQueueC.EnQue(ubC);
    }

    __aicore__ inline void Compute(uint32_t rows, uint32_t cols) {
        AscendC::LocalTensor<ElementC> ubC = inQueueC.DeQue<ElementC>();
        AscendC::LocalTensor<ElementD> ubD = outQueueD.AllocTensor<ElementD>();
        AscendC::LocalTensor<float> ubFloat = tmpBufFloat.Get<float>();
        AscendC::LocalTensor<float> scaleF32 = tmpBufScaleF32.Get<float>();
        AscendC::LocalTensor<float> ptRaw = tmpBufPerToken.Get<float>();
        AscendC::LocalTensor<float> ptBrcb = tmpBufPerTokenBrcb.Get<float>();

        // Step 1: int32 -> float
        AscendC::Cast(ubFloat, ubC, AscendC::RoundMode::CAST_NONE,
                       EpilogueTileShape::COUNT);

        // Step 2: multiply by Scale — row broadcast
        // Each row of ubFloat is multiplied element-wise by Scale[N] vector
        tileRowBroadMul(ubFloat, ubFloat, scaleF32);

        // Step 3: expand PerTokenScale from (M,1) to (M,blk) via Brcb hardware scatter
        tileBrcbOneBlk(ptBrcb, ptRaw);

        // Step 4: multiply by PerTokenScale — column broadcast
        // Each column of ubFloat is multiplied by the expanded PerTokenScale
        tileColBroadMul(ubFloat, ubFloat, ptBrcb);

        // Step 5: float -> fp16
        AscendC::Cast(ubD, ubFloat, AscendC::RoundMode::CAST_NONE,
                       EpilogueTileShape::COUNT);

        outQueueD.EnQue(ubD);
        inQueueC.FreeTensor(ubC);
    }

    __aicore__ inline void CopyOutToOutput(uint32_t outRow, uint32_t outCol,
                                            uint32_t rows, uint32_t cols) {
        // 2D tile copy to output using CopyUb2Gm helper
        AscendC::LocalTensor<ElementD> ubD = outQueueD.DeQue<ElementD>();
        auto tileShape = MakeCoord(rows, cols);
        auto ubStride = MakeCoord((int64_t)L1Shape::N, 1L);
        layout::RowMajor ubLayout(tileShape, ubStride);
        LayoutD layoutD(M, N);
        copyUbToGmD(gmD[layoutD.GetOffset(MakeCoord(outRow, outCol))], ubD,
                     layoutD.GetTileLayout(tileShape), ubLayout);
        outQueueD.FreeTensor(ubD);
    }

private:
    AscendC::TPipe pipe;
    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueC;
    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueD;
    AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufFloat;
    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueScale;
    AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufScaleF32;
    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueuePerToken;
    AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufPerToken;
    AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufPerTokenBrcb;

    AscendC::GlobalTensor<ElementC> gmC;
    AscendC::GlobalTensor<float> gmScale;
    AscendC::GlobalTensor<float> gmPerToken;
    AscendC::GlobalTensor<ElementD> gmD;

    // 2D copy helpers (tile-based, NOT row-by-row DataCopyPad)
    using CopyGmToUbC_t = Epilogue::Tile::CopyGm2Ub<ArchTag, CType>;
    using CopyUbToGmD_t = Epilogue::Tile::CopyUb2Gm<ArchTag, DType>;
    CopyGmToUbC_t copyGmToUbC;
    CopyUbToGmD_t copyUbToGmD;

    // Tile broadcast operations for vectorized dequant
    TileRowBroadMul tileRowBroadMul;
    TileBrcbOneBlk tileBrcbOneBlk;
    TileColBroadMul tileColBroadMul;

    uint32_t M = 0, N = 0;
    uint32_t totalTiles = 0;
    uint32_t aicoreIndex = 0, subcoreIndex = 0, coreNum = 0;
    BlockScheduler blockScheduler;
    uint32_t flagAicStore[WORKSPACE_STAGES];
    uint32_t flagAivCompute[WORKSPACE_STAGES];
};
```

### DSL → AscendC Mapping (Vector — Optimized Dequant Epilogue)

| DSL Construct | AscendC Equivalent |
|---|---|
| `tl.vcast(float, int32, count)` | `AscendC::Cast(ubFloat, ubC, CAST_NONE, EpilogueTileShape::COUNT)` |
| `tile_row_broadcast_mul(dst, scale)` | `tileRowBroadMul(ubFloat, ubFloat, scaleF32)` — `TileRowBroadcastMul` |
| `tl.load_1d(PerTokenScale[row], ub, count)` | `AscendC::DataCopyPad(ptIn, gmPerToken[row], ExtParams(...))` — batch load |
| `tile_brcb_one_blk(dst, src)` | `tileBrcbOneBlk(ptBrcb, ptRaw)` — `TileBroadcastOneBlk` Brcb scatter |
| `tile_col_broadcast_mul(dst, pertoken)` | `tileColBroadMul(ubFloat, ubFloat, ptBrcb)` — `TileOneBlkColumnBroadcastMul` |
| `tl.vcast(half, float, count)` | `AscendC::Cast(ubD, ubFloat, CAST_NONE, EpilogueTileShape::COUNT)` |
| `tl.load_2d(ws, ws_layout, ub, ub_layout)` | `copyGmToUbC(ubC, gmC[offset], ubLayout, wsLayout)` — `CopyGm2Ub` 2D tile |
| `tl.store_2d(Y, out_layout, ub, ub_layout)` | `copyUbToGmD(gmD[offset], ubD, outLayout, ubLayout)` — `CopyUb2Gm` 2D tile |
| `tl.cross_core_wait(flag_aic[s])` | `AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(flagAicStore[stageId])` |
| `tl.cross_core_set(flag_aiv[s])` | `AscendC::CrossCoreSetFlag<0x2, PIPE_MTE3>(flagAivCompute[stageId])` |

### Tile Broadcast Operations Reference

These operations replace the naive row-by-row `Mul()`/`Muls()`/`GetValue()` pattern with vectorized hardware primitives:

| Operation | What It Does | Replaces |
|---|---|---|
| `TileRowBroadcastMul` | Multiplies each row of (M,N) tile by Scale[N] vector | Per-row `Mul(ubFloat, ubFloat, scaleF32, N)` loop |
| `TileBroadcastOneBlk` | Expands (M,1) vector to (M, eleNumPerBlk) via Brcb scatter | Scalar `GetValue(rowId)` per row |
| `TileOneBlkColumnBroadcastMul` | Multiplies (M,N) tile by expanded (M,blk) column vector | Per-row `Muls(ubFloat, ubFloat, perTokenVal, N)` loop |

**Why this is faster:**
- **`GetValue()` → batch `DataCopyPad`**: Instead of 128 scalar GM reads per L1_M tile (one per row), loads all scale values in one DMA transfer per epilogue tile.
- **Per-row `Mul`/`Muls` → tile broadcast**: Instead of 128 separate vector operations per L1_M tile, performs 3 tile-wide operations per epilogue tile.
- **Row-by-row `DataCopyPad` → 2D `CopyGm2Ub`/`CopyUb2Gm`**: Instead of 128 individual 1D DMA calls per L1_M tile, performs one 2D DMA per epilogue tile.

### Key Differences from Row-by-Row Pattern

| Aspect | Row-by-Row (Old) | Tile-Based (Optimized) |
|---|---|---|
| Workspace read | `DataCopyPad` per row (128 calls/tile) | `CopyGm2Ub` per epilogue tile (4 calls/tile) |
| PerTokenScale | `GetValue(rowId)` scalar from GM (128 reads) | Batch `DataCopyPad` + `TileBrcbOneBlk` (4 loads) |
| Scale multiply | `Mul()` per row (128 ops) | `TileRowBroadcastMul` per epilogue tile (4 ops) |
| PerTokenScale multiply | `Muls()` per row (128 ops) | `TileBrcbOneBlk` + `TileColBroadMul` (8 ops) |
| Output write | `DataCopyPad` per row (128 calls) | `CopyUb2Gm` per epilogue tile (4 calls) |
| Cross-core sync | Single `matmulReady` event | Per-stage `flagAicStore[s]`/`flagAivCompute[s]` |

### Notes

- **EpilogueTileShape::COUNT**: Equals `EPILOGUE_TILE_M * L1Shape::N` (32 × 256 = 8192). Used as the element count for Cast operations that process the full sub-tile.
- **BYTE_PER_BLK**: AscendC constant (typically 32 bytes). `eleNumPerBlk = BYTE_PER_BLK / sizeof(float)` = 8 elements. The Brcb scatter expands each scalar to 8 copies.
- **`PIPE_MTE3` for AIV signal**: Vector uses `PIPE_MTE3` (not `PIPE_FIX`) for its CrossCoreSetFlag because the last operation before signaling is a copy-out (MTE3 pipe), not a fixpipe operation.
- **`PIPE_FIX` for AIC signal**: Cube uses `PIPE_FIX` because the last operation is blockMmad which uses the fix pipe.
- **Scale dtype is float**: Both Scale and PerTokenScale are `float` (not `half`). The reference kernel uses `GlobalTensor<float>` — no half→float cast needed for scale factors.
