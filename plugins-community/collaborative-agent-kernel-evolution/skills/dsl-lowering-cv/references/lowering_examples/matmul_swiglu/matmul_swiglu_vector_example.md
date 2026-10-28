### Example Input DSL (vector scope)
```python
with tl.scope('vector'):
    tl.cross_core_wait(matmul_ready_id)
    # ... subcore partitioning ...

    half_n = actual_n // 2
    sub_compute_length = curr_actual_sub_m * actual_n
    sub_half_length = curr_actual_sub_m * half_n

    with tl.copyin():
        tl.load_2d(workspace[gm_c_offset], ..., ub_c, ub_layout)

    with tl.compute():
        # SwiGLU: silu(left) * right
        # Left half: columns [0, half_n), Right half: columns [half_n, actual_n)
        # Using stride tricks for row-interleaved access

        # Step 1: ub_compute = -left (strided access)
        tl.vmul_scalar(ub_compute, ub_c, scalar_value=-1.0, ...)
        # Step 2: ub_compute = exp(-left)
        tl.vexp(ub_compute, ub_compute, count=sub_half_length)
        # Step 3: ub_compute = 1 + exp(-left)
        tl.vadd_scalar(ub_compute, ub_compute, scalar_value=1.0, count=sub_half_length)
        # Step 4: ub_compute = left / (1 + exp(-left)) = silu(left), strided div
        tl.vdiv(ub_compute, ub_c, ub_compute, ...)
        # Step 5: ub_compute = silu(left) * right, strided mul
        tl.vmul(ub_compute, ub_compute, ub_c[half_n], ...)
        # Step 6: Cast fp32 → fp16
        tl.vcast(ub_d, ub_compute, count=sub_half_length)

    with tl.copyout():
        tl.store_2d(D[gm_d_offset], ..., ub_d, ub_half_layout)
```

### Example Output (KernelVector)
```cpp
class KernelVector {
public:
  __aicore__ inline void Init(GM_ADDR workspace, GM_ADDR d,
                              uint32_t M, uint32_t N, uint32_t K)
  {
    this->M = M; this->N = N;
    this->TWO_N = 2 * N;
    tileCountM = (M + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tileCountN = (TWO_N + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;
    totalTasks = tileCountM * tileCountN;

    aicoreIndex = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
    subcoreIndex = AscendC::GetSubBlockIdx();

    gmC.SetGlobalBuffer((__gm__ ElementC *)workspace);
    gmD.SetGlobalBuffer((__gm__ ElementD *)d);

    constexpr uint32_t VEC_NUM = 2;
    computeLength = (L1Shape::M / VEC_NUM) * L1Shape::N;
    halfComputeLength = computeLength / 2;
    pipe.InitBuffer(inQueueC, 1, computeLength * sizeof(ElementC));
    pipe.InitBuffer(outQueueD, 1, halfComputeLength * sizeof(ElementD));
    pipe.InitBuffer(tmpBuf, computeLength * sizeof(ElementC));
  }

  __aicore__ inline void Process()
  {
    for (uint32_t taskId = aicoreIndex; taskId < totalTasks; taskId += AscendC::GetBlockNum()) {
      uint32_t blockM = taskId / tileCountN;
      uint32_t blockN = taskId % tileCountN;
      uint32_t offsetM = blockM * (uint32_t)L1Shape::M;
      uint32_t offsetN = blockN * (uint32_t)L1Shape::N;
      uint32_t actualM = ((M - offsetM) > (uint32_t)L1Shape::M) ? (uint32_t)L1Shape::M : (M - offsetM);
      uint32_t actualN = ((TWO_N - offsetN) > (uint32_t)L1Shape::N) ? (uint32_t)L1Shape::N : (TWO_N - offsetN);

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
    LayoutC layoutC(M, TWO_N);
    copyGmToUbC(ubC, gmC[layoutC.GetOffset(MakeCoord(currGmRow, currGmCol))],
                layoutUb, layoutC.GetTileLayout(actualSubShape));
    inQueueC.EnQue(ubC);
  }

  __aicore__ inline void Compute()
  {
    AscendC::LocalTensor<ElementC> ubC = inQueueC.DeQue<ElementC>();
    AscendC::LocalTensor<ElementD> ubD = outQueueD.AllocTensor<ElementD>();
    AscendC::LocalTensor<ElementC> ubCompute = tmpBuf.Get<ElementC>();

    uint32_t halfN = currActualN / 2;

    // SwiGLU: output = silu(left) * right
    // left = ubC[row * L1_N + 0..halfN-1], right = ubC[row * L1_N + halfN..actualN-1]
    // Process row by row to handle strided layout

    for (uint32_t row = 0; row < currActualSubM; ++row) {
      uint32_t srcRowOff = row * (uint32_t)L1Shape::N;  // source row offset in UB (stride = L1_N)
      uint32_t dstRowOff = row * halfN;                  // dest row offset (compact, stride = halfN)

      // Step 1: negate left half → ubCompute
      AscendC::Muls(ubCompute[dstRowOff], ubC[srcRowOff], -1.0f, halfN);

      // Step 2: exp(-left)
      AscendC::Exp(ubCompute[dstRowOff], ubCompute[dstRowOff], halfN);

      // Step 3: 1 + exp(-left)
      AscendC::Adds(ubCompute[dstRowOff], ubCompute[dstRowOff], 1.0f, halfN);

      // Step 4: silu(left) = left / (1 + exp(-left))
      AscendC::Div(ubCompute[dstRowOff], ubC[srcRowOff], ubCompute[dstRowOff], halfN);

      // Step 5: silu(left) * right
      AscendC::Mul(ubCompute[dstRowOff], ubCompute[dstRowOff], ubC[srcRowOff + halfN], halfN);
    }

    // Step 6: Cast fp32 → fp16
    uint32_t totalHalf = currActualSubM * halfN;
    AscendC::Cast(ubD, ubCompute, AscendC::RoundMode::CAST_NONE, totalHalf);

    outQueueD.EnQue(ubD);
    inQueueC.FreeTensor(ubC);
  }

  __aicore__ inline void CopyOut()
  {
    AscendC::LocalTensor<ElementD> ubD = outQueueD.DeQue<ElementD>();

    uint32_t halfN = currActualN / 2;
    // Output D column: each tile of the 2N-wide workspace maps to half-width output
    uint32_t gmDCol = currGmCol / 2;
    auto actualSubShape = MakeCoord(currActualSubM, halfN);
    auto ubTileStride = MakeCoord((int64_t)halfN, 1L);
    layout::RowMajor layoutUb(actualSubShape, ubTileStride);
    LayoutD layoutD(M, N);
    copyUbToGmD(gmD[layoutD.GetOffset(MakeCoord(currGmRow, gmDCol))], ubD,
                layoutD.GetTileLayout(actualSubShape), layoutUb);
    outQueueD.FreeTensor(ubD);
  }

private:
  AscendC::TPipe pipe;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueC;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueD;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBuf;

  AscendC::GlobalTensor<ElementC> gmC;
  AscendC::GlobalTensor<ElementD> gmD;

  using CopyGmToUbC = Epilogue::Tile::CopyGm2Ub<ArchTag, CType>;
  using CopyUbToGmD = Epilogue::Tile::CopyUb2Gm<ArchTag, DType>;
  CopyGmToUbC copyGmToUbC;
  CopyUbToGmD copyUbToGmD;

  uint32_t M, N, TWO_N, tileCountM, tileCountN, totalTasks;
  uint32_t aicoreIndex, subcoreIndex, computeLength, halfComputeLength;
  uint32_t currGmRow, currGmCol, currActualSubM, currActualN;
};
```

### Key Patterns

1. **Split-gate processing**: The full-width tile (actual_n columns of 2N) is loaded into UB. Left half is columns [0, halfN), right half is columns [halfN, actualN). Processing is done row-by-row because left/right halves are interleaved in UB (stride = L1_N).

2. **Row-by-row computation**: Unlike matmul_gelu where the entire tile can be processed as a flat vector, SwiGLU requires per-row processing because the left/right split is along the column dimension. Each row's left half is at offset `row * L1_N`, right half at `row * L1_N + halfN`.

3. **Compact output**: The compute result is stored compactly in ubCompute (stride = halfN), so the final Cast produces a contiguous half-width buffer. CopyOut uses a compact UB layout with stride halfN.

4. **Output column mapping**: `gmDCol = currGmCol / 2` maps the 2N-space column to N-space output column.

5. **SiLU formula**: `silu(x) = x / (1 + exp(-x))`, implemented as:
   - Negate → Exp → Adds(1.0) → Div(x, denom)
   - Same as CANN clipped_swiglu.hpp (without clipping bounds)

6. **UB budget**:
   - inQueueC: 64×256×4B = 64KB (fp32 full-width tile)
   - outQueueD: 64×128×2B = 16KB (fp16 half-width output)
   - tmpBuf: 64×256×4B = 64KB (fp32 compute workspace)
   - Total: ~144KB within 176KB limit
