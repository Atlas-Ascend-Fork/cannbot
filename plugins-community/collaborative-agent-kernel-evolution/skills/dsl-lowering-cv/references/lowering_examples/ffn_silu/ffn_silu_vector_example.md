### Example Input DSL (vector scope — 2 stages with UB reuse)
```python
# Stage 2: Vector SiLU (workspace_mm1 → workspace_act)
with tl.scope('vector'):
    tl.cross_core_wait(mm1_done_id)
    # ... SiLU: x / (1 + exp(-x)), cast fp32 → fp16 ...
    tl.cross_core_set(act_done_id)

# Stage 4: Vector Cast (workspace_mm2 → Y)
with tl.scope('vector'):
    tl.cross_core_wait(mm2_done_id)
    # ... Cast fp32 → fp16 ...
```

### Example Output (KernelVector — multi-stage with UB reuse)
```cpp
class KernelVector {
public:
  __aicore__ inline void Init(GM_ADDR workspace, GM_ADDR y,
                              uint32_t m, uint32_t n1, uint32_t n2, uint32_t k)
  {
    this->m = m; this->n1 = n1; this->n2 = n2;
    tileCountM = (m + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tileCountN1 = (n1 + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;
    tileCountN2 = (n2 + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;

    // Workspace partitioning (same offsets as Cube)
    size_t wsMm1Bytes = (size_t)m * (size_t)n1 * sizeof(float);
    size_t wsActBytes = (size_t)m * (size_t)n1 * sizeof(uint16_t);

    gmMM1.SetGlobalBuffer((__gm__ ElementMM*)((__gm__ uint8_t*)workspace));
    gmAct.SetGlobalBuffer((__gm__ ElementAct*)((__gm__ uint8_t*)workspace + wsMm1Bytes));
    gmMM2.SetGlobalBuffer((__gm__ ElementMM*)((__gm__ uint8_t*)workspace + wsMm1Bytes + wsActBytes));
    gmY.SetGlobalBuffer((__gm__ ElementOut*)y);

    aicoreIndex = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
    subcoreIndex = AscendC::GetSubBlockIdx();

    // UB buffers — reused across Stage 2 and Stage 4 (stage-sequential)
    constexpr uint32_t VEC_NUM = 2;
    computeLength = (L1Shape::M / VEC_NUM) * L1Shape::N;
    pipe.InitBuffer(inQueue, 1, computeLength * sizeof(ElementMM));
    pipe.InitBuffer(outQueue, 1, computeLength * sizeof(ElementAct));
    pipe.InitBuffer(tmpBuf, computeLength * sizeof(ElementMM));
  }

  // Stage 2: SiLU activation (after MM1, before MM2)
  __aicore__ inline void ProcessActivation()
  {
    constexpr uint32_t tileM = (uint32_t)L1Shape::M;
    constexpr uint32_t tileN = (uint32_t)L1Shape::N;

    for (uint32_t blockM = aicoreIndex; blockM < tileCountM; blockM += AscendC::GetBlockNum()) {
      uint32_t offsetM = blockM * tileM;
      uint32_t actualM = ((m - offsetM) > tileM) ? tileM : (m - offsetM);

      AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(MM1_DONE);

      uint32_t subM = (actualM + AscendC::GetSubBlockNum() - 1) / AscendC::GetSubBlockNum();
      uint32_t subOffsetM = subcoreIndex * subM;
      uint32_t currSubM = (subOffsetM + subM <= actualM) ? subM : (actualM > subOffsetM ? actualM - subOffsetM : 0);

      if (currSubM > 0) {
        uint32_t gmRow = offsetM + subOffsetM;

        for (uint32_t blockN = 0; blockN < tileCountN1; ++blockN) {
          uint32_t colStart = blockN * tileN;
          uint32_t currN = ((n1 - colStart) > tileN) ? tileN : (n1 - colStart);

          // CopyIn from workspace_mm1
          auto subShape = MakeCoord(currSubM, currN);
          auto ubStride = MakeCoord((int64_t)L1Shape::N, 1L);
          layout::RowMajor layoutUb(subShape, ubStride);
          LayoutC layoutMM1(m, n1);

          AscendC::LocalTensor<ElementMM> ubIn = inQueue.AllocTensor<ElementMM>();
          copyGmToUb(ubIn, gmMM1[layoutMM1.GetOffset(MakeCoord(gmRow, colStart))],
                     layoutUb, layoutMM1.GetTileLayout(subShape));
          inQueue.EnQue(ubIn);

          // Compute SiLU: x / (1 + exp(-x))
          AscendC::LocalTensor<ElementMM> ubMM = inQueue.DeQue<ElementMM>();
          AscendC::LocalTensor<ElementAct> ubOut = outQueue.AllocTensor<ElementAct>();
          AscendC::LocalTensor<ElementMM> ubTmp = tmpBuf.Get<ElementMM>();

          uint32_t subLen = currSubM * currN;
          AscendC::Muls(ubTmp, ubMM, -1.0f, subLen);
          AscendC::Exp(ubTmp, ubTmp, subLen);
          AscendC::Adds(ubTmp, ubTmp, 1.0f, subLen);
          AscendC::Div(ubTmp, ubMM, ubTmp, subLen);
          AscendC::Cast(ubOut, ubTmp, AscendC::RoundMode::CAST_NONE, subLen);

          // CopyOut to workspace_act
          LayoutD layoutAct(m, n1);
          auto outShape = MakeCoord(currSubM, currN);
          auto outUbStride = MakeCoord((int64_t)L1Shape::N, 1L);
          layout::RowMajor layoutOutUb(outShape, outUbStride);

          outQueue.EnQue(ubOut);
          AscendC::LocalTensor<ElementAct> ubOutDeq = outQueue.DeQue<ElementAct>();
          copyUbToGm(gmAct[layoutAct.GetOffset(MakeCoord(gmRow, colStart))], ubOutDeq,
                     layoutAct.GetTileLayout(outShape), layoutOutUb);
          outQueue.FreeTensor(ubOutDeq);
          inQueue.FreeTensor(ubMM);
        }
      }
      // Signal Cube that activation is ready for this block_m
      AscendC::CrossCoreSetFlag<0x2, PIPE_MTE3>(ACT_DONE);
    }
  }

  // Stage 4: Output cast (after MM2)
  __aicore__ inline void ProcessOutputCast()
  {
    constexpr uint32_t tileM = (uint32_t)L1Shape::M;
    constexpr uint32_t tileN = (uint32_t)L1Shape::N;

    for (uint32_t blockM = aicoreIndex; blockM < tileCountM; blockM += AscendC::GetBlockNum()) {
      uint32_t offsetM = blockM * tileM;
      uint32_t actualM = ((m - offsetM) > tileM) ? tileM : (m - offsetM);

      AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(MM2_DONE);

      uint32_t subM = (actualM + AscendC::GetSubBlockNum() - 1) / AscendC::GetSubBlockNum();
      uint32_t subOffsetM = subcoreIndex * subM;
      uint32_t currSubM = (subOffsetM + subM <= actualM) ? subM : (actualM > subOffsetM ? actualM - subOffsetM : 0);

      if (currSubM > 0) {
        uint32_t gmRow = offsetM + subOffsetM;

        for (uint32_t blockN = 0; blockN < tileCountN2; ++blockN) {
          uint32_t colStart = blockN * tileN;
          uint32_t currN = ((n2 - colStart) > tileN) ? tileN : (n2 - colStart);

          // CopyIn from workspace_mm2 — reuse same inQueue/outQueue buffers
          auto subShape = MakeCoord(currSubM, currN);
          auto ubStride = MakeCoord((int64_t)L1Shape::N, 1L);
          layout::RowMajor layoutUb(subShape, ubStride);
          LayoutC layoutMM2(m, n2);

          AscendC::LocalTensor<ElementMM> ubIn = inQueue.AllocTensor<ElementMM>();
          copyGmToUb(ubIn, gmMM2[layoutMM2.GetOffset(MakeCoord(gmRow, colStart))],
                     layoutUb, layoutMM2.GetTileLayout(subShape));
          inQueue.EnQue(ubIn);

          // Compute: simple fp32 → fp16 cast
          AscendC::LocalTensor<ElementMM> ubMM = inQueue.DeQue<ElementMM>();
          AscendC::LocalTensor<ElementOut> ubOut = outQueue.AllocTensor<ElementOut>();
          uint32_t subLen = currSubM * currN;
          AscendC::Cast(ubOut, ubMM, AscendC::RoundMode::CAST_NONE, subLen);

          // CopyOut to Y
          LayoutD layoutY(m, n2);
          auto outShape = MakeCoord(currSubM, currN);
          auto outUbStride = MakeCoord((int64_t)L1Shape::N, 1L);
          layout::RowMajor layoutOutUb(outShape, outUbStride);

          outQueue.EnQue(ubOut);
          AscendC::LocalTensor<ElementOut> ubOutDeq = outQueue.DeQue<ElementOut>();
          copyUbToGm(gmY[layoutY.GetOffset(MakeCoord(gmRow, colStart))], ubOutDeq,
                     layoutY.GetTileLayout(outShape), layoutOutUb);
          outQueue.FreeTensor(ubOutDeq);
          inQueue.FreeTensor(ubMM);
        }
      }
    }
  }

private:
  AscendC::TPipe pipe;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueue;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueue;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBuf;

  AscendC::GlobalTensor<ElementMM> gmMM1;
  AscendC::GlobalTensor<ElementAct> gmAct;
  AscendC::GlobalTensor<ElementMM> gmMM2;
  AscendC::GlobalTensor<ElementOut> gmY;

  using CopyGmToUb = Epilogue::Tile::CopyGm2Ub<ArchTag, CType1>;
  using CopyUbToGm = Epilogue::Tile::CopyUb2Gm<ArchTag, Gemm::GemmType<ElementAct, LayoutD>>;
  CopyGmToUb copyGmToUb;
  CopyUbToGm copyUbToGm;

  uint32_t m, n1, n2, tileCountM, tileCountN1, tileCountN2;
  uint32_t aicoreIndex, subcoreIndex, computeLength;
};
```

### Key Patterns

1. **Stage-sequential UB reuse**: `inQueue`, `outQueue`, and `tmpBuf` are allocated once and reused across ProcessActivation (Stage 2) and ProcessOutputCast (Stage 4). This is safe because the stages execute sequentially — Stage 2 completes entirely before Stage 4 begins. Total UB: ~96KB (not duplicated).

2. **Vector→Cube signal uses PIPE_MTE3**: `CrossCoreSetFlag<0x2, PIPE_MTE3>(ACT_DONE)` — the Vector's last operation before signaling is a CopyOut (MTE3 pipe), so PIPE_MTE3 ensures the write is committed before Cube reads.

3. **SiLU computation**: Same 4-step formula as matmul_gelu's GELU but simpler:
   - `Muls(tmp, x, -1.0f)` → `Exp(tmp)` → `Adds(tmp, 1.0f)` → `Div(x, tmp)`

4. **Output cast is trivial**: Stage 4 just casts fp32→fp16. This is the simplest possible Vector stage.

5. **Per-block_m scheduling**: Both Vector stages use the same block_m loop as Cube, ensuring alignment of tile processing.

6. **Reference**: This pattern matches CANN `ffn.h` which implements the same MM1→Activation→MM2→Output pipeline with `ActiveType::SILU`.
