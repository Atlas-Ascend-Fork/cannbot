### Example Input DSL (vector scope)
```python
with tl.scope('vector'):
    tl.cross_core_wait(matmul_ready_id)

    sub_m = tl.cdiv(actual_m, num_sub)
    sub_offset_m = subcore_id * sub_m
    curr_actual_sub_m = tl.min(sub_m, actual_m - sub_offset_m)
    if curr_actual_sub_m <= 0:
        continue

    curr_gm_row = (block_m * L1_M) + sub_offset_m
    curr_gm_col = (block_n * L1_N)
    ub_shape = tl.make_shape(curr_actual_sub_m, actual_n)
    ub_layout = tl.make_layout(ub_shape, tl.make_stride(L1_N, 1))

    gm_c_offset = layout_c.get_offset(coord=(curr_gm_row, curr_gm_col))
    gm_res_offset = layout_res.get_offset(coord=(curr_gm_row, curr_gm_col))
    gm_d_offset = layout_d.get_offset(coord=(curr_gm_row, curr_gm_col))

    with tl.copyin():
        tl.load_2d(workspace[gm_c_offset], ..., ub_c, ub_layout)
        tl.load_2d(residual[gm_res_offset], ..., ub_res, ub_layout)

    with tl.compute():
        tl.vcast(ub_res_fp32, ub_res, count=compute_length)
        tl.vadd(ub_c, ub_c, ub_res_fp32, count=compute_length)
        tl.vcast(ub_d, ub_c, count=compute_length)

    with tl.copyout():
        tl.store_2d(D[gm_d_offset], ..., ub_d, ub_layout)
```

### Example Output (KernelVector)
```cpp
class KernelVector {
public:
  __aicore__ inline void Init(GM_ADDR workspace, GM_ADDR residual, GM_ADDR d,
                              uint32_t M, uint32_t N, uint32_t K)
  {
    this->M = M; this->N = N;
    tileCountM = (M + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tileCountN = (N + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;
    totalTasks = tileCountM * tileCountN;

    aicoreIndex = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
    subcoreIndex = AscendC::GetSubBlockIdx();

    gmC.SetGlobalBuffer((__gm__ ElementC *)workspace);
    gmRes.SetGlobalBuffer((__gm__ ElementRes *)residual);
    gmD.SetGlobalBuffer((__gm__ ElementD *)d);

    constexpr uint32_t VEC_NUM = 2;
    computeLength = (L1Shape::M / VEC_NUM) * L1Shape::N;
    pipe.InitBuffer(inQueueC, 1, computeLength * sizeof(ElementC));
    pipe.InitBuffer(inQueueRes, 1, computeLength * sizeof(ElementRes));
    pipe.InitBuffer(outQueueD, 1, computeLength * sizeof(ElementD));
    pipe.InitBuffer(tmpBufResFp32, computeLength * sizeof(ElementC));
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
    AscendC::LocalTensor<ElementRes> ubRes = inQueueRes.AllocTensor<ElementRes>();

    auto actualSubShape = MakeCoord(currActualSubM, currActualN);
    auto ubTileStride = MakeCoord((int64_t)L1Shape::N, 1L);
    layout::RowMajor layoutUb(actualSubShape, ubTileStride);

    LayoutC layoutC(M, N);
    copyGmToUbC(ubC, gmC[layoutC.GetOffset(MakeCoord(currGmRow, currGmCol))],
                layoutUb, layoutC.GetTileLayout(actualSubShape));

    LayoutRes layoutRes(M, N);
    copyGmToUbRes(ubRes, gmRes[layoutRes.GetOffset(MakeCoord(currGmRow, currGmCol))],
                  layoutUb, layoutRes.GetTileLayout(actualSubShape));

    inQueueC.EnQue(ubC);
    inQueueRes.EnQue(ubRes);
  }

  __aicore__ inline void Compute()
  {
    AscendC::LocalTensor<ElementC> ubC = inQueueC.DeQue<ElementC>();
    AscendC::LocalTensor<ElementRes> ubRes = inQueueRes.DeQue<ElementRes>();
    AscendC::LocalTensor<ElementD> ubD = outQueueD.AllocTensor<ElementD>();
    AscendC::LocalTensor<ElementC> ubResFp32 = tmpBufResFp32.Get<ElementC>();

    // Cast residual fp16 → fp32
    AscendC::Cast(ubResFp32, ubRes, AscendC::RoundMode::CAST_NONE, computeLength);

    // matmul_result(fp32) + residual(fp32)
    AscendC::Add(ubC, ubC, ubResFp32, computeLength);

    // Cast fp32 → fp16 for output
    AscendC::Cast(ubD, ubC, AscendC::RoundMode::CAST_NONE, computeLength);

    outQueueD.EnQue(ubD);
    inQueueC.FreeTensor(ubC);
    inQueueRes.FreeTensor(ubRes);
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
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueRes;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueD;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufResFp32;

  AscendC::GlobalTensor<ElementC> gmC;
  AscendC::GlobalTensor<ElementRes> gmRes;
  AscendC::GlobalTensor<ElementD> gmD;

  using CopyGmToUbC = Epilogue::Tile::CopyGm2Ub<ArchTag, CType>;
  using CopyGmToUbRes = Epilogue::Tile::CopyGm2Ub<ArchTag, Gemm::GemmType<ElementRes, LayoutRes>>;
  using CopyUbToGmD = Epilogue::Tile::CopyUb2Gm<ArchTag, DType>;
  CopyGmToUbC copyGmToUbC;
  CopyGmToUbRes copyGmToUbRes;
  CopyUbToGmD copyUbToGmD;

  uint32_t M, N, tileCountM, tileCountN, totalTasks;
  uint32_t aicoreIndex, subcoreIndex, computeLength;
  uint32_t currGmRow, currGmCol, currActualSubM, currActualN;
};
```

### Key Patterns

1. **Dual CopyIn**: Both workspace (fp32 matmul result) and residual (fp16) are loaded via 2D copy helpers. Each has its own VECIN queue.
2. **Type promotion**: Residual is cast fp16→fp32 before addition to match matmul accumulation precision.
3. **Simple epilogue**: Cast+Add+Cast — the simplest OneSource epilogue pattern.
4. **UB budget**: 4 buffers × 64×256 = ~96KB well within 176KB limit.
   - inQueueC: 64×256×4B = 64KB (fp32)
   - inQueueRes: 64×256×2B = 32KB (fp16)
   - outQueueD: 64×256×2B = 32KB (fp16)
   - tmpBufResFp32: 64×256×4B = 64KB (fp32)
   - Total peak: 192KB — tight but within budget. If needed, reduce by using L1_M/4 subcore split.
