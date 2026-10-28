### Example Input DSL (vector scope — online softmax + output accumulation)
```python
# Per KV block, two Vector stages:
# Stage A (after BMM1): Online softmax on scores → prob
# Stage B (after BMM2): Accumulate O with rescaling

# Stage A:
with tl.scope('vector'):
    tl.cross_core_wait(score_ready_id)
    for r in range(curr_sub_m):
        # scale scores, compute row_max, update running_max
        # exp(score - running_max), row_sum, update running_sum
        # rescale previous O accumulator
        # cast prob fp32→fp16, store to workspace_prob
    tl.cross_core_set(prob_ready_id)

# Stage B:
with tl.scope('vector'):
    tl.cross_core_wait(out_ready_id)
    for r in range(curr_sub_m):
        # O_acc += O_partial (already rescaled in Stage A)
    tl.cross_core_set(update_done_id)

# After all KV blocks: final normalize O = O / running_sum
```

### Example Output (KernelVector — online softmax + accumulate)
```cpp
class KernelVector {
public:
  __aicore__ inline void Init(GM_ADDR q_unused, GM_ADDR o, GM_ADDR workspace,
                              uint32_t m, uint32_t n, uint32_t d, uint32_t bk, float scale)
  {
    this->m = m; this->n = n; this->d = d; this->bk = bk; this->scale = scale;
    kvBlocks = (n + bk - 1) / bk;
    tileCountM = (m + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;

    // Workspace partitioning (same as Cube)
    size_t wsScoreBytes = (size_t)m * (size_t)bk * sizeof(float);
    size_t wsProbBytes  = (size_t)m * (size_t)bk * sizeof(uint16_t);
    size_t wsOutBytes   = (size_t)m * (size_t)d  * sizeof(float);
    size_t wsMaxBytes   = (size_t)m * sizeof(float);

    __gm__ uint8_t* wsBase = (__gm__ uint8_t*)workspace;
    gmScore.SetGlobalBuffer((__gm__ ElementScore*)(wsBase));
    gmProb.SetGlobalBuffer((__gm__ ElementProb*)(wsBase + wsScoreBytes));
    gmOutPartial.SetGlobalBuffer((__gm__ ElementOut*)(wsBase + wsScoreBytes + wsProbBytes));
    gmMax.SetGlobalBuffer((__gm__ float*)(wsBase + wsScoreBytes + wsProbBytes + wsOutBytes));
    gmSum.SetGlobalBuffer((__gm__ float*)(wsBase + wsScoreBytes + wsProbBytes + wsOutBytes + wsMaxBytes));
    gmO.SetGlobalBuffer((__gm__ ElementOut*)o);

    aicoreIndex = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
    subcoreIndex = AscendC::GetSubBlockIdx();

    // UB buffers for row-by-row processing
    pipe.InitBuffer(inQueueScore, 1, bk * sizeof(float));
    pipe.InitBuffer(outQueueProb, 1, bk * sizeof(ElementProb));
    pipe.InitBuffer(inQueueOut, 1, d * sizeof(float));
    pipe.InitBuffer(inQueueAcc, 1, d * sizeof(float));
    pipe.InitBuffer(outQueueAcc, 1, d * sizeof(float));
    pipe.InitBuffer(tmpBufReduce, bk * sizeof(float));
    pipe.InitBuffer(tmpBufScalar, sizeof(float));
  }

  __aicore__ inline void Process()
  {
    constexpr uint32_t tileM = (uint32_t)L1Shape::M;

    for (uint32_t blockM = aicoreIndex; blockM < tileCountM; blockM += AscendC::GetBlockNum()) {
      uint32_t offsetM = blockM * tileM;
      uint32_t actualM = ((m - offsetM) > tileM) ? tileM : (m - offsetM);

      uint32_t subM = (actualM + AscendC::GetSubBlockNum() - 1) / AscendC::GetSubBlockNum();
      uint32_t subOffsetM = subcoreIndex * subM;
      uint32_t currSubM = (subOffsetM + subM <= actualM) ? subM : (actualM > subOffsetM ? actualM - subOffsetM : 0);
      uint32_t gmRowBase = offsetM + subOffsetM;

      for (uint32_t kvB = 0; kvB < kvBlocks; ++kvB) {
        uint32_t actualBk = ((n - kvB * bk) > bk) ? bk : (n - kvB * bk);

        // ====== Stage A: Online Softmax (Score → Prob) ======
        AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(SCORE_READY);

        if (currSubM > 0) {
          ProcessOnlineSoftmax(gmRowBase, currSubM, actualBk, kvB);
        }

        AscendC::CrossCoreSetFlag<0x2, PIPE_MTE3>(PROB_READY);

        // ====== Stage B: Output Accumulation ======
        AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(OUT_READY);

        if (currSubM > 0) {
          ProcessOutputAccum(gmRowBase, currSubM);
        }

        AscendC::CrossCoreSetFlag<0x2, PIPE_MTE3>(UPDATE_DONE);
      }

      // ====== Final normalize: O = O / running_sum ======
      if (currSubM > 0) {
        ProcessFinalNormalize(gmRowBase, currSubM);
      }
    }
  }

private:
  // ---- Stage A: Online Softmax ----
  __aicore__ inline void ProcessOnlineSoftmax(uint32_t gmRowBase, uint32_t numRows,
                                              uint32_t actualBk, uint32_t kvB)
  {
    LayoutScore layoutScore(m, bk);
    LayoutOut layoutO(m, d);

    for (uint32_t r = 0; r < numRows; ++r) {
      uint32_t rowId = gmRowBase + r;

      // Load score row
      AscendC::LocalTensor<float> ubScore = inQueueScore.AllocTensor<float>();
      AscendC::DataCopyPad(ubScore, gmScore[layoutScore.GetOffset(MatrixCoord{rowId, 0})],
                           AscendC::DataCopyExtParams(1, actualBk * sizeof(float), 0, 0, 0),
                           AscendC::DataCopyPadExtParams<float>(false, 0, 0, 0));
      inQueueScore.EnQue(ubScore);
      AscendC::LocalTensor<float> scoreRow = inQueueScore.DeQue<float>();

      AscendC::LocalTensor<float> ubReduce = tmpBufReduce.Get<float>();
      AscendC::LocalTensor<float> ubScalar = tmpBufScalar.Get<float>();

      // Scale: S *= scale
      AscendC::Muls(scoreRow, scoreRow, scale, actualBk);

      // Row max
      AscendC::ReduceMax(ubReduce, scoreRow, ubReduce, actualBk);
      float newMax = ubReduce.GetValue(0);

      // Load running max
      AscendC::DataCopyPad(ubScalar, gmMax[rowId],
                           AscendC::DataCopyExtParams(1, sizeof(float), 0, 0, 0),
                           AscendC::DataCopyPadExtParams<float>(false, 0, 0, 0));
      float oldMax = ubScalar.GetValue(0);
      float runningMax = (kvB == 0) ? newMax : (oldMax > newMax ? oldMax : newMax);

      // exp(score - running_max)
      AscendC::Adds(scoreRow, scoreRow, -runningMax, actualBk);
      AscendC::Exp(scoreRow, scoreRow, actualBk);

      // Row sum
      AscendC::ReduceSum(ubReduce, scoreRow, ubReduce, actualBk);
      float newSum = ubReduce.GetValue(0);

      // Update running statistics and rescale previous accumulator
      float runningSum;
      if (kvB > 0) {
        float rescale = expf(oldMax - runningMax);
        // Load old sum
        AscendC::DataCopyPad(ubScalar, gmSum[rowId],
                             AscendC::DataCopyExtParams(1, sizeof(float), 0, 0, 0),
                             AscendC::DataCopyPadExtParams<float>(false, 0, 0, 0));
        float oldSum = ubScalar.GetValue(0);
        runningSum = oldSum * rescale + newSum;

        // Rescale O accumulator: O[row] *= rescale
        AscendC::LocalTensor<float> ubAcc = inQueueAcc.AllocTensor<float>();
        AscendC::DataCopyPad(ubAcc, gmO[layoutO.GetOffset(MatrixCoord{rowId, 0})],
                             AscendC::DataCopyExtParams(1, d * sizeof(float), 0, 0, 0),
                             AscendC::DataCopyPadExtParams<float>(false, 0, 0, 0));
        inQueueAcc.EnQue(ubAcc);
        AscendC::LocalTensor<float> accRow = inQueueAcc.DeQue<float>();
        AscendC::Muls(accRow, accRow, rescale, d);
        AscendC::DataCopyPad(gmO[layoutO.GetOffset(MatrixCoord{rowId, 0})], accRow,
                             AscendC::DataCopyExtParams(1, d * sizeof(float), 0, 0, 0));
        inQueueAcc.FreeTensor(accRow);
      } else {
        runningSum = newSum;
      }

      // Store updated max and sum
      ubScalar.SetValue(0, runningMax);
      AscendC::DataCopyPad(gmMax[rowId], ubScalar,
                           AscendC::DataCopyExtParams(1, sizeof(float), 0, 0, 0));
      ubScalar.SetValue(0, runningSum);
      AscendC::DataCopyPad(gmSum[rowId], ubScalar,
                           AscendC::DataCopyExtParams(1, sizeof(float), 0, 0, 0));

      // Cast prob to fp16 → workspace_prob
      AscendC::LocalTensor<ElementProb> ubProb = outQueueProb.AllocTensor<ElementProb>();
      AscendC::Cast(ubProb, scoreRow, AscendC::RoundMode::CAST_NONE, actualBk);
      LayoutProb layoutProb(m, bk);
      AscendC::DataCopyPad(gmProb[layoutProb.GetOffset(MatrixCoord{rowId, 0})], ubProb,
                           AscendC::DataCopyExtParams(1, actualBk * sizeof(ElementProb), 0, 0, 0));
      outQueueProb.FreeTensor(ubProb);
      inQueueScore.FreeTensor(scoreRow);
    }
  }

  // ---- Stage B: Output Accumulation ----
  __aicore__ inline void ProcessOutputAccum(uint32_t gmRowBase, uint32_t numRows)
  {
    LayoutOut layoutOut(m, d);
    LayoutOut layoutO(m, d);

    for (uint32_t r = 0; r < numRows; ++r) {
      uint32_t rowId = gmRowBase + r;

      // Load O_partial from BMM2 workspace
      AscendC::LocalTensor<float> ubOutPart = inQueueOut.AllocTensor<float>();
      AscendC::DataCopyPad(ubOutPart, gmOutPartial[layoutOut.GetOffset(MatrixCoord{rowId, 0})],
                           AscendC::DataCopyExtParams(1, d * sizeof(float), 0, 0, 0),
                           AscendC::DataCopyPadExtParams<float>(false, 0, 0, 0));
      inQueueOut.EnQue(ubOutPart);

      // Load current O accumulator
      AscendC::LocalTensor<float> ubAcc = inQueueAcc.AllocTensor<float>();
      AscendC::DataCopyPad(ubAcc, gmO[layoutO.GetOffset(MatrixCoord{rowId, 0})],
                           AscendC::DataCopyExtParams(1, d * sizeof(float), 0, 0, 0),
                           AscendC::DataCopyPadExtParams<float>(false, 0, 0, 0));
      inQueueAcc.EnQue(ubAcc);

      AscendC::LocalTensor<float> outPart = inQueueOut.DeQue<float>();
      AscendC::LocalTensor<float> accRow = inQueueAcc.DeQue<float>();

      // O = O + O_partial (O was already rescaled in softmax stage)
      AscendC::Add(accRow, accRow, outPart, d);

      // Store back
      AscendC::DataCopyPad(gmO[layoutO.GetOffset(MatrixCoord{rowId, 0})], accRow,
                           AscendC::DataCopyExtParams(1, d * sizeof(float), 0, 0, 0));
      inQueueOut.FreeTensor(outPart);
      inQueueAcc.FreeTensor(accRow);
    }
  }

  // ---- Final Normalize: O = O / running_sum, cast to fp16 ----
  __aicore__ inline void ProcessFinalNormalize(uint32_t gmRowBase, uint32_t numRows)
  {
    LayoutOut layoutO(m, d);

    for (uint32_t r = 0; r < numRows; ++r) {
      uint32_t rowId = gmRowBase + r;

      // Load running sum
      AscendC::LocalTensor<float> ubScalar = tmpBufScalar.Get<float>();
      AscendC::DataCopyPad(ubScalar, gmSum[rowId],
                           AscendC::DataCopyExtParams(1, sizeof(float), 0, 0, 0),
                           AscendC::DataCopyPadExtParams<float>(false, 0, 0, 0));
      float invSum = 1.0f / ubScalar.GetValue(0);

      // Load O, divide by sum, cast, store
      AscendC::LocalTensor<float> ubAcc = inQueueAcc.AllocTensor<float>();
      AscendC::DataCopyPad(ubAcc, gmO[layoutO.GetOffset(MatrixCoord{rowId, 0})],
                           AscendC::DataCopyExtParams(1, d * sizeof(float), 0, 0, 0),
                           AscendC::DataCopyPadExtParams<float>(false, 0, 0, 0));
      inQueueAcc.EnQue(ubAcc);
      AscendC::LocalTensor<float> accRow = inQueueAcc.DeQue<float>();

      AscendC::Muls(accRow, accRow, invSum, d);

      // Cast fp32 → fp16 and store final output
      AscendC::LocalTensor<ElementProb> ubFinal = outQueueProb.AllocTensor<ElementProb>();
      AscendC::Cast(ubFinal, accRow, AscendC::RoundMode::CAST_NONE, d);
      AscendC::DataCopyPad(gmO[layoutO.GetOffset(MatrixCoord{rowId, 0})], ubFinal,
                           AscendC::DataCopyExtParams(1, d * sizeof(ElementProb), 0, 0, 0));
      outQueueProb.FreeTensor(ubFinal);
      inQueueAcc.FreeTensor(accRow);
    }
  }

private:
  AscendC::TPipe pipe;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueScore;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueProb;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueOut;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueAcc;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueAcc;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufReduce;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufScalar;

  AscendC::GlobalTensor<ElementScore> gmScore;
  AscendC::GlobalTensor<ElementProb> gmProb;
  AscendC::GlobalTensor<ElementOut> gmOutPartial;
  AscendC::GlobalTensor<float> gmMax;
  AscendC::GlobalTensor<float> gmSum;
  AscendC::GlobalTensor<ElementOut> gmO;

  uint32_t m, n, d, bk, kvBlocks, tileCountM;
  uint32_t aicoreIndex, subcoreIndex;
  float scale;

  using LayoutScore = layout::RowMajor;
  using LayoutProb = layout::RowMajor;
  using LayoutOut = layout::RowMajor;
};
```

### Key Patterns

1. **Online softmax (Welford-style)**: The core algorithm maintains `running_max` and `running_sum` across KV blocks. Each new block:
   - Computes local max, updates running max
   - Computes `exp(score - running_max)` for softmax numerator
   - Rescales previous O accumulator by `exp(old_max - new_max)` to maintain consistency
   - This is the same algorithm used in CANN `SoftmaxFlashV2`

2. **Vector→Cube signal uses PIPE_MTE3**: Both `PROB_READY` and `UPDATE_DONE` are signaled with `PIPE_MTE3` because Vector's last operation before signaling is a `DataCopyPad` write to GM (MTE3 pipe).

3. **Row-by-row processing**: Since online softmax requires per-row statistics (max, sum), all Vector processing is row-by-row using 1D `DataCopyPad`, not 2D tile copy helpers.

4. **UB buffer reuse across stages**: `inQueueAcc` is used in both softmax (rescale O) and output accumulation stages, but these execute sequentially within each KV block.

5. **Final normalize outside KV loop**: After all KV blocks complete, a final pass divides O by `running_sum` and casts to fp16. This is outside the sync loop — no cross-core events needed.

6. **UB budget**: All row-sized buffers (Bk or D elements):
   - inQueueScore: 256×4B = 1KB
   - outQueueProb: 256×2B = 0.5KB
   - inQueueOut: 128×4B = 0.5KB (D=128)
   - inQueueAcc: 128×4B = 0.5KB
   - tmpBufReduce: 256×4B = 1KB
   - tmpBufScalar: 4B
   - Total: ~3.5KB — extremely compact. Well within 176KB.

7. **Reference**: Maps to CANN `flash_attention_score_s1s2_bn2gs1.h`'s `ProcessVec1` (softmax) + `ProcessVec2` (accumulate) + `Bmm2ResultDiv` (final normalize).
