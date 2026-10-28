### Example Input DSL (vector scope)
```python
with tl.scope('vector'):
    tl.cross_core_wait(matmul_ready_id)
    # ... subcore partitioning ...

    with tl.copyin():
        tl.load_2d(workspace[gm_c_offset], ..., ub_c, ub_layout)
        tl.load(bias[col_start:col_start + actual_n], ub_bias)

    with tl.compute():
        tl.vcast(ub_bias_fp32, ub_bias, count=actual_n)
        for row in range(curr_actual_sub_m):
            row_offset = row * L1_N
            tl.vadd(ub_c[row_offset:], ub_c[row_offset:], ub_bias_fp32, count=actual_n)
        tl.vclamp_min(ub_compute, ub_c, scalar_value=0.0, count=compute_length)
        tl.vcast(ub_d, ub_compute, count=compute_length)

    with tl.copyout():
        tl.store_2d(D[gm_d_offset], ..., ub_d, ub_layout)
```

### Example Output (KernelVector)
```cpp
class KernelVector {
public:
  __aicore__ inline void Init(GM_ADDR workspace, GM_ADDR bias, GM_ADDR d,
                              uint32_t M, uint32_t N, uint32_t K)
  {
    this->M = M; this->N = N;
    tileCountM = (M + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tileCountN = (N + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;
    totalTasks = tileCountM * tileCountN;

    aicoreIndex = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
    subcoreIndex = AscendC::GetSubBlockIdx();

    gmC.SetGlobalBuffer((__gm__ ElementC *)workspace);
    gmBias.SetGlobalBuffer((__gm__ ElementBias *)bias);
    gmD.SetGlobalBuffer((__gm__ ElementD *)d);

    constexpr uint32_t VEC_NUM = 2;
    computeLength = (L1Shape::M / VEC_NUM) * L1Shape::N;
    pipe.InitBuffer(inQueueC, 1, computeLength * sizeof(ElementC));
    pipe.InitBuffer(inQueueBias, 1, (uint32_t)L1Shape::N * sizeof(ElementBias));
    pipe.InitBuffer(outQueueD, 1, computeLength * sizeof(ElementD));
    pipe.InitBuffer(tmpBuf, computeLength * sizeof(ElementC));
    pipe.InitBuffer(tmpBufBiasFp32, (uint32_t)L1Shape::N * sizeof(ElementC));
  }

  __aicore__ inline void Process()
  {
    for (uint32_t taskId = aicoreIndex; taskId < totalTasks; taskId += AscendC::GetBlockNum()) {
      uint32_t blockM = taskId / tileCountN;
      uint32_t blockN = taskId % tileCountN;
      uint32_t offsetM = blockM * (uint32_t)L1Shape::M;
      uint32_t offsetN = blockN * (uint32_t)L1Shape::N;
      uint32_t actualM = ((M - offsetM) > (uint32_t)L1Shape::M) ? (uint32_t)L1Shape::M : (M - offsetM);
      uint32_t actualN = ((N - offsetN) > (uint32_t)L1Shape::N) ? (uint32_t)L1Shape::N : (N - offsetN);

      AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(matmulReady);

      uint32_t subM = (actualM + AscendC::GetSubBlockNum() - 1) / AscendC::GetSubBlockNum();
      uint32_t subOffsetM = subcoreIndex * subM;
      currActualSubM = (subOffsetM + subM <= actualM) ? subM : (actualM > subOffsetM ? actualM - subOffsetM : 0);
      currActualN = actualN;

      if (currActualSubM > 0) {
        currGmRow = offsetM + subOffsetM;
        currGmCol = offsetN;
        CopyIn();
        Compute();
        CopyOut();
      }
    }
  }

private:
  __aicore__ inline void CopyIn()
  {
    AscendC::LocalTensor<ElementC> ubC = inQueueC.AllocTensor<ElementC>();
    auto actualSubShape = MakeCoord(currActualSubM, currActualN);
    auto ubTileStride = MakeCoord((int64_t)L1Shape::N, 1L);
    layout::RowMajor layoutUb(actualSubShape, ubTileStride);
    LayoutC layoutC(M, N);
    copyGmToUbC(ubC, gmC[layoutC.GetOffset(MakeCoord(currGmRow, currGmCol))],
                layoutUb, layoutC.GetTileLayout(actualSubShape));
    inQueueC.EnQue(ubC);

    // Load bias vector (1D, per-tile column slice)
    AscendC::LocalTensor<ElementBias> ubBias = inQueueBias.AllocTensor<ElementBias>();
    AscendC::DataCopyPadExtParams<ElementBias> padParams(false, 0, 0, 0);
    AscendC::DataCopyPad(ubBias, gmBias[currGmCol],
                         AscendC::DataCopyExtParams(1, currActualN * sizeof(ElementBias), 0, 0, 0),
                         padParams);
    inQueueBias.EnQue(ubBias);
  }

  __aicore__ inline void Compute()
  {
    AscendC::LocalTensor<ElementC> ubC = inQueueC.DeQue<ElementC>();
    AscendC::LocalTensor<ElementBias> ubBias = inQueueBias.DeQue<ElementBias>();
    AscendC::LocalTensor<ElementD> ubD = outQueueD.AllocTensor<ElementD>();
    AscendC::LocalTensor<ElementC> ubCompute = tmpBuf.Get<ElementC>();
    AscendC::LocalTensor<ElementC> ubBiasFp32 = tmpBufBiasFp32.Get<ElementC>();

    // Cast bias fp16 → fp32
    AscendC::Cast(ubBiasFp32, ubBias, AscendC::RoundMode::CAST_NONE, currActualN);

    // Broadcast-add bias to each row: ubC[row, :] += bias[:]
    for (uint32_t row = 0; row < currActualSubM; ++row) {
      uint32_t rowOffset = row * (uint32_t)L1Shape::N;
      AscendC::Add(ubC[rowOffset], ubC[rowOffset], ubBiasFp32, currActualN);
    }

    // ReLU: clamp to min 0
    AscendC::Maxs(ubCompute, ubC, 0.0f, computeLength);

    // Cast fp32 → fp16
    AscendC::Cast(ubD, ubCompute, AscendC::RoundMode::CAST_NONE, computeLength);

    outQueueD.EnQue(ubD);
    inQueueC.FreeTensor(ubC);
    inQueueBias.FreeTensor(ubBias);
  }

  __aicore__ inline void CopyOut()
  {
    AscendC::LocalTensor<ElementD> ubD = outQueueD.DeQue<ElementD>();
    auto actualSubShape = MakeCoord(currActualSubM, currActualN);
    auto ubTileStride = MakeCoord((int64_t)L1Shape::N, 1L);
    layout::RowMajor layoutUb(actualSubShape, ubTileStride);
    LayoutD layoutD(M, N);
    copyUbToGmD(gmD[layoutD.GetOffset(MakeCoord(currGmRow, currGmCol))], ubD,
                layoutD.GetTileLayout(actualSubShape), layoutUb);
    outQueueD.FreeTensor(ubD);
  }

private:
  AscendC::TPipe pipe;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueC;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueBias;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueD;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBuf;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufBiasFp32;

  AscendC::GlobalTensor<ElementC> gmC;
  AscendC::GlobalTensor<ElementBias> gmBias;
  AscendC::GlobalTensor<ElementD> gmD;

  using CopyGmToUbC = Epilogue::Tile::CopyGm2Ub<ArchTag, CType>;
  using CopyUbToGmD = Epilogue::Tile::CopyUb2Gm<ArchTag, DType>;
  CopyGmToUbC copyGmToUbC;
  CopyUbToGmD copyUbToGmD;

  uint32_t M, N, tileCountM, tileCountN, totalTasks;
  uint32_t aicoreIndex, subcoreIndex, computeLength;
  uint32_t currGmRow, currGmCol, currActualSubM, currActualN;
};
```

### Key Patterns

1. **Bias broadcast-add**: bias is a 1D vector [N], loaded once per tile via 1D `DataCopyPad`. Cast to fp32, then broadcast-added to each row of the matmul result using a `for` loop over rows.
2. **ReLU via Maxs**: `AscendC::Maxs(dst, src, 0.0f, count)` implements element-wise max(x, 0) = ReLU. This is equivalent to `tl.vclamp_min(dst, src, scalar_value=0.0)`.
3. **Mixed copy methods**: Matmul result uses 2D `CopyGm2Ub` (tile layout); bias uses 1D `DataCopyPad` (contiguous vector).
4. **UB budget**:
   - inQueueC: 64×256×4B = 64KB (fp32 matmul result)
   - inQueueBias: 256×2B = 0.5KB (fp16 bias vector)
   - outQueueD: 64×256×2B = 32KB (fp16 output)
   - tmpBuf: 64×256×4B = 64KB (fp32 compute temp)
   - tmpBufBiasFp32: 256×4B = 1KB (fp32 bias)
   - Total: ~161.5KB within 176KB limit
