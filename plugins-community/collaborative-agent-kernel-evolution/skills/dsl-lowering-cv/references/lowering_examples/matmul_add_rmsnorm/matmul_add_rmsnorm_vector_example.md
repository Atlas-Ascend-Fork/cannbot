### Example Input DSL (vector scope — two-pass row processing)
```python
with tl.scope('vector'):
    tl.cross_core_wait(matmul_done_id)
    # ... subcore partitioning ...

    for r in range(curr_m):
        row_id = row_start + r

        # Pass 1: Load matmul result + residual tile-by-tile, add, store X_add, accumulate sum_sq
        row_sum_sq = 0.0
        for block_n in range(tile_count_n):
            # load workspace[row_id, col_start:], residual[row_id, col_start:]
            # ub_add = mm + residual(fp32)
            # store X_add
            # sum_sq += ReduceSum(ub_add * ub_add)

        # Compute inv_rms
        inv_rms = (row_sum_sq / N + eps) ** (-0.5)

        # Pass 2: Load X_add + gamma tile-by-tile, normalize, store Y
        for block_n in range(tile_count_n):
            # load X_add[row_id, col_start:], gamma[col_start:]
            # y = x_add * inv_rms * gamma
            # store Y
```

### Example Output (KernelVector)
```cpp
class KernelVector {
public:
  __aicore__ inline void Init(GM_ADDR workspace, GM_ADDR residual, GM_ADDR gamma,
                              GM_ADDR y, GM_ADDR xadd, uint32_t m, uint32_t n,
                              uint32_t k, float eps)
  {
    this->m = m; this->n = n; this->k = k; this->eps = eps;
    tileCountM = (m + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tileCountN = (n + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;

    gmMM.SetGlobalBuffer((__gm__ ElementMM*)workspace);
    gmRes.SetGlobalBuffer((__gm__ ElementRes*)residual);
    gmGamma.SetGlobalBuffer((__gm__ ElementGamma*)gamma);
    gmY.SetGlobalBuffer((__gm__ ElementD*)y);
    gmXadd.SetGlobalBuffer((__gm__ ElementD*)xadd);

    aicoreIndex = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
    subcoreIndex = AscendC::GetSubBlockIdx();

    // All buffers are 1D row-sized (L1_N elements)
    pipe.InitBuffer(inQueueMM, 1, (uint32_t)L1Shape::N * sizeof(ElementMM));
    pipe.InitBuffer(inQueueRes, 1, (uint32_t)L1Shape::N * sizeof(ElementRes));
    pipe.InitBuffer(inQueueXadd, 1, (uint32_t)L1Shape::N * sizeof(ElementD));
    pipe.InitBuffer(inQueueGamma, 1, (uint32_t)L1Shape::N * sizeof(ElementGamma));
    pipe.InitBuffer(outQueueXadd, 1, (uint32_t)L1Shape::N * sizeof(ElementD));
    pipe.InitBuffer(outQueueY, 1, (uint32_t)L1Shape::N * sizeof(ElementD));
    pipe.InitBuffer(tmpBufFp32, (uint32_t)L1Shape::N * sizeof(float));
    pipe.InitBuffer(tmpBufSq, (uint32_t)L1Shape::N * sizeof(float));
  }

  __aicore__ inline void Process()
  {
    constexpr uint32_t tileM = (uint32_t)L1Shape::M;
    constexpr uint32_t tileN = (uint32_t)L1Shape::N;

    for (uint32_t blockM = aicoreIndex; blockM < tileCountM; blockM += AscendC::GetBlockNum()) {
      uint32_t offsetM = blockM * tileM;
      uint32_t actualM = ((m - offsetM) > tileM) ? tileM : (m - offsetM);

      uint32_t subM = (actualM + AscendC::GetSubBlockNum() - 1) / AscendC::GetSubBlockNum();
      uint32_t subOffsetM = subcoreIndex * subM;
      uint32_t currM = (subOffsetM + subM <= actualM) ? subM : (actualM > subOffsetM ? actualM - subOffsetM : 0);

      AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(MATMUL_DONE);

      if (currM > 0) {
        uint32_t rowStart = offsetM + subOffsetM;
        ProcessRows(rowStart, currM, tileN);
      }
    }
  }

private:
  __aicore__ inline void ProcessRows(uint32_t rowStart, uint32_t numRows, uint32_t tileN)
  {
    LayoutC layoutMM(m, n);
    LayoutD layoutRes(m, n);
    LayoutD layoutXadd(m, n);
    LayoutD layoutY(m, n);

    for (uint32_t r = 0; r < numRows; ++r) {
      uint32_t rowId = rowStart + r;

      // ========== Pass 1: Add residual + accumulate sum_sq ==========
      float rowSumSq = 0.0f;
      for (uint32_t bn = 0; bn < tileCountN; ++bn) {
        uint32_t colStart = bn * tileN;
        uint32_t currN = ((n - colStart) > tileN) ? tileN : (n - colStart);

        // CopyIn: matmul result + residual
        AscendC::LocalTensor<ElementMM> ubMM = inQueueMM.AllocTensor<ElementMM>();
        AscendC::DataCopyPad(ubMM, gmMM[layoutMM.GetOffset(MatrixCoord{rowId, colStart})],
                             AscendC::DataCopyExtParams(1, currN * sizeof(ElementMM), 0, 0, 0),
                             AscendC::DataCopyPadExtParams<ElementMM>(false, 0, 0, 0));
        inQueueMM.EnQue(ubMM);

        AscendC::LocalTensor<ElementRes> ubRes = inQueueRes.AllocTensor<ElementRes>();
        AscendC::DataCopyPad(ubRes, gmRes[layoutRes.GetOffset(MatrixCoord{rowId, colStart})],
                             AscendC::DataCopyExtParams(1, currN * sizeof(ElementRes), 0, 0, 0),
                             AscendC::DataCopyPadExtParams<ElementRes>(false, 0, 0, 0));
        inQueueRes.EnQue(ubRes);

        // Compute: add + accumulate
        AscendC::LocalTensor<ElementMM> mm = inQueueMM.DeQue<ElementMM>();
        AscendC::LocalTensor<ElementRes> res = inQueueRes.DeQue<ElementRes>();
        AscendC::LocalTensor<float> resFp32 = tmpBufFp32.Get<float>();
        AscendC::LocalTensor<float> sq = tmpBufSq.Get<float>();

        AscendC::Cast(resFp32, res, AscendC::RoundMode::CAST_NONE, currN);
        AscendC::Add(mm, mm, resFp32, currN);  // mm = matmul_result + residual (fp32)

        // Store X_add (cast to fp16)
        AscendC::LocalTensor<ElementD> ubXadd = outQueueXadd.AllocTensor<ElementD>();
        AscendC::Cast(ubXadd, mm, AscendC::RoundMode::CAST_NONE, currN);
        AscendC::DataCopyPad(gmXadd[layoutXadd.GetOffset(MatrixCoord{rowId, colStart})], ubXadd,
                             AscendC::DataCopyExtParams(1, currN * sizeof(ElementD), 0, 0, 0));
        outQueueXadd.FreeTensor(ubXadd);

        // Accumulate sum of squares
        AscendC::Mul(sq, mm, mm, currN);
        AscendC::ReduceSum(sq, sq, sq, currN);
        rowSumSq += sq.GetValue(0);

        inQueueMM.FreeTensor(mm);
        inQueueRes.FreeTensor(res);
      }

      // ========== Compute inv_rms ==========
      float rowMeanSq = rowSumSq / static_cast<float>(n);
      float invRms = 1.0f / sqrtf(rowMeanSq + eps);

      // ========== Pass 2: Normalize with gamma, store Y ==========
      for (uint32_t bn = 0; bn < tileCountN; ++bn) {
        uint32_t colStart = bn * tileN;
        uint32_t currN = ((n - colStart) > tileN) ? tileN : (n - colStart);

        // CopyIn: X_add + gamma
        AscendC::LocalTensor<ElementD> ubXaddIn = inQueueXadd.AllocTensor<ElementD>();
        AscendC::DataCopyPad(ubXaddIn, gmXadd[layoutXadd.GetOffset(MatrixCoord{rowId, colStart})],
                             AscendC::DataCopyExtParams(1, currN * sizeof(ElementD), 0, 0, 0),
                             AscendC::DataCopyPadExtParams<ElementD>(false, 0, 0, 0));
        inQueueXadd.EnQue(ubXaddIn);

        AscendC::LocalTensor<ElementGamma> ubGamma = inQueueGamma.AllocTensor<ElementGamma>();
        AscendC::DataCopyPad(ubGamma, gmGamma[colStart],
                             AscendC::DataCopyExtParams(1, currN * sizeof(ElementGamma), 0, 0, 0),
                             AscendC::DataCopyPadExtParams<ElementGamma>(false, 0, 0, 0));
        inQueueGamma.EnQue(ubGamma);

        // Compute: normalize + gamma
        AscendC::LocalTensor<ElementD> xaddDeq = inQueueXadd.DeQue<ElementD>();
        AscendC::LocalTensor<ElementGamma> gammaDeq = inQueueGamma.DeQue<ElementGamma>();
        AscendC::LocalTensor<float> xaddFp32 = tmpBufFp32.Get<float>();
        AscendC::LocalTensor<float> gammaFp32 = tmpBufSq.Get<float>();  // reuse sq buffer

        AscendC::Cast(xaddFp32, xaddDeq, AscendC::RoundMode::CAST_NONE, currN);
        AscendC::Muls(xaddFp32, xaddFp32, invRms, currN);
        AscendC::Cast(gammaFp32, gammaDeq, AscendC::RoundMode::CAST_NONE, currN);
        AscendC::Mul(xaddFp32, xaddFp32, gammaFp32, currN);

        // Store Y
        AscendC::LocalTensor<ElementD> ubY = outQueueY.AllocTensor<ElementD>();
        AscendC::Cast(ubY, xaddFp32, AscendC::RoundMode::CAST_NONE, currN);
        AscendC::DataCopyPad(gmY[layoutY.GetOffset(MatrixCoord{rowId, colStart})], ubY,
                             AscendC::DataCopyExtParams(1, currN * sizeof(ElementD), 0, 0, 0));
        outQueueY.FreeTensor(ubY);

        inQueueXadd.FreeTensor(xaddDeq);
        inQueueGamma.FreeTensor(gammaDeq);
      }
    }
  }

private:
  AscendC::TPipe pipe;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueMM;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueRes;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueXadd;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueGamma;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueXadd;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueY;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufFp32;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufSq;

  AscendC::GlobalTensor<ElementMM> gmMM;
  AscendC::GlobalTensor<ElementRes> gmRes;
  AscendC::GlobalTensor<ElementGamma> gmGamma;
  AscendC::GlobalTensor<ElementD> gmY;
  AscendC::GlobalTensor<ElementD> gmXadd;

  uint32_t m, n, k, tileCountM, tileCountN;
  uint32_t aicoreIndex, subcoreIndex;
  float eps;
};
```

### Key Patterns

1. **Two-pass row processing**: This is the defining pattern for matmul_add_rmsnorm:
   - **Pass 1**: For each row, iterate over all N-tiles to add residual, store X_add, and accumulate `sum_sq` (ReduceSum). This requires the complete row to compute the RmsNorm denominator.
   - **Pass 2**: Re-read X_add and gamma tile-by-tile, apply `x * inv_rms * gamma`, store Y.

2. **1D DataCopyPad (not 2D helpers)**: Since processing is row-by-row, use `DataCopyPad` with `DataCopyExtParams(1, len*sizeof(T), 0, 0, 0)`. This matches rms_matmul_scale's pattern.

3. **Dual output**: Both Y (normalized) and X_add (pre-norm residual add result) are written to GM. X_add is written in Pass 1, then re-read in Pass 2.

4. **Buffer reuse**: `tmpBufSq` (used for ReduceSum workspace in Pass 1) is reused as `gammaFp32` buffer in Pass 2 — stage-sequential reuse since the passes don't overlap.

5. **inv_rms computation**: `inv_rms = 1/sqrt(mean_sq + eps)` computed in scalar after Pass 1 completes for each row. Uses `sqrtf()` from `<cmath>`.

6. **UB budget**: All buffers are L1_N-sized (not full tile):
   - 6 queues × 256 × {2B or 4B} ≈ 6KB
   - 2 TBuf × 256 × 4B = 2KB
   - Total: ~8KB — very compact, well within 176KB.

7. **Reference**: This pattern matches the CANN `add_rms_norm_kernel.h` implementation which also uses a two-pass approach: first accumulate statistics, then normalize.
