### Example Input DSL (vector scope)
```python
with tl.scope('vector'):
    num_sub = tl.get_num_sub_blocks()
    subcore_id = tl.get_sub_block_id()
    aicore_id = tl.program_id() // num_sub
    aicore_num = tl.num_programs() // num_sub
    compute_length = (L1_M // num_sub) * L1_N

    ub_c = tl.alloc_ub(compute_length, dtype=DTYPE_C)
    ub_compute = tl.alloc_ub(compute_length, dtype=DTYPE_C)
    ub_d = tl.alloc_ub(compute_length, dtype=DTYPE_D)

    for loop_idx in range(aicore_id, total_loops, aicore_num):
        tl.cross_core_wait(matmul_ready_id)
        ...
        with tl.copyin():
            tl.load_2d(workspace[gm_c_offset], src_layout, ub_c, ub_layout)
        with tl.compute():
            tl.vmul(ub_compute, ub_c, ub_c, count=compute_length)
            tl.vmul(ub_compute, ub_compute, ub_c, count=compute_length)
            tl.vaxpy(ub_compute, ub_c, alpha=TANH_APPROX_FACTOR, count=compute_length)
            tl.vmul_scalar(ub_compute, ub_compute, scalar_value=NEG_SQRT_EIGHT_OVER_PI, count=compute_length)
            tl.vexp(ub_compute, ub_compute, count=compute_length)
            tl.vadd_scalar(ub_compute, ub_compute, scalar_value=1.0, count=compute_length)
            tl.vdiv(ub_compute, ub_c, ub_compute, count=compute_length)
            tl.vcast(ub_d, ub_compute, count=compute_length)
        with tl.copyout():
            tl.store_2d(D[gm_d_offset], dst_layout, ub_d, ub_layout)
```

### Example Output (KernelVector)
```cpp
class KernelVector {
public:
  __aicore__ inline void Init(GM_ADDR workspace, GM_ADDR d, uint32_t M, uint32_t N, uint32_t K) {
    this->M = M; this->N = N;
    GemmCoord problemShape{M, N, K};
    blockScheduler = BlockScheduler(problemShape, MakeCoord(L1Shape::M, L1Shape::N));
    totalTiles = blockScheduler.GetCoreLoops();
    aicoreIndex = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
    subcoreIndex = AscendC::GetSubBlockIdx();

    gmC.SetGlobalBuffer((__gm__ ElementC *)workspace);
    gmD.SetGlobalBuffer((__gm__ ElementD *)d);

    constexpr uint32_t VEC_NUM = 2;
    computeLength = (L1Shape::M / VEC_NUM) * L1Shape::N;
    pipe.InitBuffer(inQueueC, 1, computeLength * sizeof(ElementC));
    pipe.InitBuffer(outQueueD, 1, computeLength * sizeof(ElementD));
    pipe.InitBuffer(tmpBuf, computeLength * sizeof(ElementC));
  }

  __aicore__ inline void Process() {
    for (uint32_t loopIdx = aicoreIndex; loopIdx < totalTiles; loopIdx += AscendC::GetBlockNum()) {
      GemmCoord blockCoord = blockScheduler.GetBlockCoord(loopIdx);
      GemmCoord actualBlockShape = blockScheduler.GetActualBlockShape(blockCoord);
      AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(matmulReady);

      uint32_t actual_m = actualBlockShape.m();
      uint32_t actual_n = actualBlockShape.n();
      uint32_t subM = (actual_m + AscendC::GetSubBlockNum() - 1) / AscendC::GetSubBlockNum();
      uint32_t subOffsetM = subcoreIndex * subM;
      currActualSubM = (subOffsetM + subM <= actual_m) ? subM : (actual_m > subOffsetM ? actual_m - subOffsetM : 0);
      currActualN = actual_n;

      if (currActualSubM > 0) {
        currGmRow = blockCoord.m() * L1Shape::M + subOffsetM;
        currGmCol = blockCoord.n() * L1Shape::N;
        CopyIn();
        Compute();
        CopyOut();
      }
    }
  }

private:
  __aicore__ inline void CopyIn() {
    AscendC::LocalTensor<ElementC> ubC = inQueueC.AllocTensor<ElementC>();
    auto actualSubblockShape = MakeCoord(currActualSubM, currActualN);
    auto ubTileStride = MakeCoord((int64_t)L1Shape::N, 1L);
    layout::RowMajor layoutComputeUb(actualSubblockShape, ubTileStride);
    LayoutC layoutC(M, N);
    copyGmToUbC(ubC, gmC[layoutC.GetOffset(MakeCoord(currGmRow, currGmCol))],
                layoutComputeUb, layoutC.GetTileLayout(actualSubblockShape));
    inQueueC.EnQue(ubC);
  }

  __aicore__ inline void Compute() {
    AscendC::LocalTensor<ElementC> ubC = inQueueC.DeQue<ElementC>();
    AscendC::LocalTensor<ElementD> ubD = outQueueD.AllocTensor<ElementD>();
    AscendC::LocalTensor<ElementC> ubCompute = tmpBuf.Get<ElementC>();

    // GELU: y = x / (1 + exp(NEG_COEFF * (x^3 + FACTOR * x)))
    constexpr float NEG_COEFF = -1.595769121f * 0.044715f;
    constexpr float FACTOR = 1.0f / 0.044715f;

    // ub_compute = x * x * x
    AscendC::Mul(ubCompute, ubC, ubC, computeLength);
    AscendC::Mul(ubCompute, ubCompute, ubC, computeLength);

    // ub_compute = x^3 + FACTOR * x  (vaxpy: dst += alpha * x)
    AscendC::Axpy(ubCompute, ubC, FACTOR, computeLength);

    // ub_compute = NEG_COEFF * ub_compute
    AscendC::Muls(ubCompute, ubCompute, NEG_COEFF, computeLength);

    // ub_compute = exp(ub_compute)
    AscendC::Exp(ubCompute, ubCompute, computeLength);

    // ub_compute = ub_compute + 1.0
    AscendC::Adds(ubCompute, ubCompute, 1.0f, computeLength);

    // ub_compute = x / ub_compute
    AscendC::Div(ubCompute, ubC, ubCompute, computeLength);

    // Cast fp32 -> fp16
    AscendC::Cast(ubD, ubCompute, AscendC::RoundMode::CAST_NONE, computeLength);

    outQueueD.EnQue(ubD);
    inQueueC.FreeTensor(ubC);
  }

  __aicore__ inline void CopyOut() {
    AscendC::LocalTensor<ElementD> ubD = outQueueD.DeQue<ElementD>();
    auto actualSubblockShape = MakeCoord(currActualSubM, currActualN);
    auto ubTileStride = MakeCoord((int64_t)L1Shape::N, 1L);
    layout::RowMajor layoutComputeUb(actualSubblockShape, ubTileStride);
    LayoutD layoutD(M, N);
    copyUbToGmD(gmD[layoutD.GetOffset(MakeCoord(currGmRow, currGmCol))], ubD,
                layoutD.GetTileLayout(actualSubblockShape), layoutComputeUb);
    outQueueD.FreeTensor(ubD);
  }

private:
  AscendC::TPipe pipe;
  AscendC::TQue<AscendC::TPosition::VECIN, 1>  inQueueC;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueD;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBuf;

  AscendC::GlobalTensor<ElementC> gmC;
  AscendC::GlobalTensor<ElementD> gmD;

  using CopyGmToUbC = Epilogue::Tile::CopyGm2Ub<ArchTag, CType>;
  using CopyUbToGmD = Epilogue::Tile::CopyUb2Gm<ArchTag, DType>;
  CopyGmToUbC copyGmToUbC;
  CopyUbToGmD copyUbToGmD;

  uint32_t M, N, totalTiles;
  uint32_t aicoreIndex, subcoreIndex, computeLength;
  uint32_t currGmRow, currGmCol, currActualSubM, currActualN;
  BlockScheduler blockScheduler;
};
```

### DSL → AscendC Mapping (Vector)

| DSL Construct | AscendC Equivalent |
|---|---|
| `tl.scope('vector')` | Code in `KernelVector` class |
| `tl.get_num_sub_blocks()` | `AscendC::GetSubBlockNum()` |
| `tl.get_sub_block_id()` | `AscendC::GetSubBlockIdx()` |
| `tl.cross_core_wait(event_id)` | `AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(event_id)` |
| `tl.alloc_ub(size, dtype=DTYPE_C)` for copyin | `pipe.InitBuffer(inQueueC, 1, size * sizeof(ElementC))` |
| `tl.alloc_ub(size, dtype=DTYPE_D)` for copyout | `pipe.InitBuffer(outQueueD, 1, size * sizeof(ElementD))` |
| `tl.alloc_ub(size, dtype=...)` for compute temp | `pipe.InitBuffer(tmpBuf, size * sizeof(...))` |
| `tl.load_2d(src, src_layout, dst_ub, ub_layout)` | `CopyGm2Ub(ubTensor, gmTensor[offset], ubLayout, gmLayout)` |
| `tl.store_2d(dst, dst_layout, src_ub, ub_layout)` | `CopyUb2Gm(gmTensor[offset], ubTensor, gmLayout, ubLayout)` |
| `tl.vmul(dst, a, b, count=N)` | `AscendC::Mul(dst, a, b, N)` |
| `tl.vexp(dst, src, count=N)` | `AscendC::Exp(dst, src, N)` |
| `tl.vadd_scalar(dst, src, scalar_value=v)` | `AscendC::Adds(dst, src, v, N)` |
| `tl.vmul_scalar(dst, src, scalar_value=v)` | `AscendC::Muls(dst, src, v, N)` |
| `tl.vdiv(dst, a, b, count=N)` | `AscendC::Div(dst, a, b, N)` |
| `tl.vcast(dst, src, count=N)` | `AscendC::Cast(dst, src, RoundMode::CAST_NONE, N)` |
| `tl.vaxpy(dst, x, alpha=a)` | `AscendC::Axpy(dst, x, a, N)` |

### Buffer Type Selection

| UB Buffer Purpose | Queue/Buffer Type | TPosition |
|---|---|---|
| Data loaded from GM (copyin) | `TQue` | `VECIN` |
| Data stored to GM (copyout) | `TQue` | `VECOUT` |
| Temporary compute workspace | `TBuf` | `VECCALC` |

### 2D Copy Helpers

For CV vector scope, use Catlass epilogue tile copy helpers:
```cpp
using CopyGmToUbC = Epilogue::Tile::CopyGm2Ub<ArchTag, CType>;
using CopyUbToGmD = Epilogue::Tile::CopyUb2Gm<ArchTag, DType>;
```

UB tile layout construction:
```cpp
auto actualSubblockShape = MakeCoord(currActualSubM, currActualN);
auto ubTileStride = MakeCoord((int64_t)L1Shape::N, 1L);
layout::RowMajor layoutComputeUb(actualSubblockShape, ubTileStride);
```
