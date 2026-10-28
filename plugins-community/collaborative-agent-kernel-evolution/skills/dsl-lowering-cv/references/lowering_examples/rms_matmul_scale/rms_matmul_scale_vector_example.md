### Example Input DSL (vector scope)
```python
with tl.scope("vector"):
    num_sub = tl.get_num_sub_blocks()
    subcore_id = tl.get_sub_block_id()
    # compute inv_rms in parallel with cube
    # then tl.cross_core_wait(matmul_done_id)
    # finally scale and store
```

### Example Output (KernelVector, queues for IO + TBuf for temp)
```cpp
class KernelVector {
public:
  __aicore__ inline void Init(GM_ADDR x, GM_ADDR y, GM_ADDR workspace,
                              uint32_t m, uint32_t n, uint32_t k, float eps)
  {
    this->m = m; this->n = n; this->k = k; this->eps = eps;
    tile_count_m = (m + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tile_count_n = (n + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;

    // Workspace layout: [mm: M*N float][inv_rms: M float]
    __gm__ ElementMM* workspace_ptr = (__gm__ ElementMM*)workspace;
    gm_mm.SetGlobalBuffer(workspace_ptr);
    gm_inv.SetGlobalBuffer(workspace_ptr + (uint64_t)m * (uint64_t)n);
    gm_x.SetGlobalBuffer((__gm__ ElementA*)x);
    gm_y.SetGlobalBuffer((__gm__ ElementD*)y);

    aicore_index = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
    subcore_index = AscendC::GetSubBlockIdx();

    // Queues are for CopyIn/CopyOut; temporary compute workspace uses TBuf.
    pipe.InitBuffer(inQueueX, 1, REDUCE_TILE_K * sizeof(ElementA));
    pipe.InitBuffer(tmpBufXf32, REDUCE_TILE_K * sizeof(float));
    pipe.InitBuffer(inQueueInv, 1, sizeof(float));
    pipe.InitBuffer(outQueueInv, 1, sizeof(float));
    pipe.InitBuffer(inQueueMM, 1, (uint32_t)L1Shape::N * sizeof(ElementMM));
    pipe.InitBuffer(outQueueY, 1, (uint32_t)L1Shape::N * sizeof(ElementD));
  }

  __aicore__ inline void Process()
  {
    constexpr uint32_t tile_m = (uint32_t)L1Shape::M;
    constexpr uint32_t tile_n = (uint32_t)L1Shape::N;
    for (uint32_t block_m = aicore_index; block_m < tile_count_m; block_m += AscendC::GetBlockNum()) {
      uint32_t offset_m = block_m * tile_m;
      uint32_t actual_m = ((m - offset_m) > tile_m) ? tile_m : (m - offset_m);
      uint32_t sub_m = (actual_m + AscendC::GetSubBlockNum() - 1) / AscendC::GetSubBlockNum();
      uint32_t sub_offset_m = subcore_index * sub_m;
      uint32_t curr_m = (sub_offset_m + sub_m <= actual_m) ? sub_m : (actual_m > sub_offset_m ? actual_m - sub_offset_m : 0);

      if (curr_m > 0) {
        ComputeInvRms(offset_m + sub_offset_m, curr_m);
      }
      AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(MATMUL_READY);
      if (curr_m > 0) {
        ScaleRows(offset_m + sub_offset_m, curr_m, tile_n);
      }
    }
  }

private:
  // CopyIn uses VECIN queues; CopyOut uses VECOUT queues; temp buffers use VECCALC TBuf.
  __aicore__ inline void CopyInXTile(uint64_t gm_offset, uint32_t k_len) {
    AscendC::LocalTensor<ElementA> x_half = inQueueX.AllocTensor<ElementA>();
    AscendC::DataCopyPadExtParams<ElementA> padParams(false, 0, 0, 0);
    AscendC::DataCopyPad(x_half, gm_x[gm_offset],
                         AscendC::DataCopyExtParams(1, k_len * (uint32_t)sizeof(ElementA), 0, 0, 0),
                         padParams);
    inQueueX.EnQue(x_half);
  }

  __aicore__ inline float ComputeXTileSumSq(uint32_t k_len) {
    AscendC::LocalTensor<ElementA> x_half = inQueueX.DeQue<ElementA>();
    AscendC::LocalTensor<float> x_f32 = tmpBufXf32.Get<float>();
    AscendC::Cast(x_f32, x_half, AscendC::RoundMode::CAST_NONE, k_len);
    AscendC::Mul(x_f32, x_f32, x_f32, k_len);
    AscendC::ReduceSum(x_f32, x_f32, x_f32, k_len);
    inQueueX.FreeTensor(x_half);
    return x_f32.GetValue(0);
  }

  __aicore__ inline void ComputeInvRms(uint32_t row_start, uint32_t num_rows) {
    LayoutA layout_x(m, k);
    for (uint32_t r = 0; r < num_rows; ++r) {
      uint32_t row_id = row_start + r;
      float row_sum_sq = 0.0f;
      for (uint32_t k_base = 0; k_base < k; k_base += REDUCE_TILE_K) {
        uint32_t k_len = ((k - k_base) > REDUCE_TILE_K) ? REDUCE_TILE_K : (k - k_base);
        uint64_t gm_offset = (uint64_t)layout_x.GetOffset(MatrixCoord{row_id, k_base});
        CopyInXTile(gm_offset, k_len);
        row_sum_sq += ComputeXTileSumSq(k_len);
      }
      float row_mean = row_sum_sq / (float)k;
      float inv_rms = 1.0f / sqrtf(row_mean + eps);

      // Write inv_rms to workspace
      AscendC::LocalTensor<float> inv_local = outQueueInv.AllocTensor<float>();
      inv_local.SetValue(0, inv_rms);
      AscendC::DataCopyPad(gm_inv[row_id], inv_local,
                           AscendC::DataCopyExtParams(1, sizeof(float), 0, 0, 0));
      outQueueInv.FreeTensor(inv_local);
    }
  }

  __aicore__ inline void ScaleRows(uint32_t row_start, uint32_t num_rows, uint32_t tile_n) {
    LayoutC layout_mm(m, n);
    LayoutD layout_y(m, n);
    for (uint32_t r = 0; r < num_rows; ++r) {
      uint32_t row_id = row_start + r;
      // Read inv_rms scalar
      AscendC::LocalTensor<float> inv_local = inQueueInv.AllocTensor<float>();
      AscendC::DataCopyPad(inv_local, gm_inv[row_id],
                           AscendC::DataCopyExtParams(1, sizeof(float), 0, 0, 0),
                           AscendC::DataCopyPadExtParams<float>(false, 0, 0, 0));
      inQueueInv.EnQue(inv_local);
      AscendC::LocalTensor<float> inv_deq = inQueueInv.DeQue<float>();
      float inv_rms_val = inv_deq.GetValue(0);
      inQueueInv.FreeTensor(inv_deq);

      for (uint32_t bn = 0; bn < tile_count_n; ++bn) {
        uint32_t col_start = bn * tile_n;
        uint32_t curr_n = ((n - col_start) > tile_n) ? tile_n : (n - col_start);

        // CopyIn matmul tile
        AscendC::LocalTensor<ElementMM> mm_local = inQueueMM.AllocTensor<ElementMM>();
        uint64_t mm_offset = (uint64_t)layout_mm.GetOffset(MatrixCoord{row_id, col_start});
        AscendC::DataCopyPad(mm_local, gm_mm[mm_offset],
                             AscendC::DataCopyExtParams(1, curr_n * sizeof(ElementMM), 0, 0, 0),
                             AscendC::DataCopyPadExtParams<ElementMM>(false, 0, 0, 0));
        inQueueMM.EnQue(mm_local);

        // Compute: scale + cast
        AscendC::LocalTensor<ElementMM> mm_deq = inQueueMM.DeQue<ElementMM>();
        AscendC::LocalTensor<ElementD> y_local = outQueueY.AllocTensor<ElementD>();
        AscendC::Muls(mm_deq, mm_deq, inv_rms_val, curr_n);
        AscendC::Cast(y_local, mm_deq, AscendC::RoundMode::CAST_NONE, curr_n);
        outQueueY.EnQue(y_local);
        inQueueMM.FreeTensor(mm_deq);

        // CopyOut
        AscendC::LocalTensor<ElementD> y_out = outQueueY.DeQue<ElementD>();
        uint64_t y_offset = (uint64_t)layout_y.GetOffset(MatrixCoord{row_id, col_start});
        AscendC::DataCopyPad(gm_y[y_offset], y_out,
                             AscendC::DataCopyExtParams(1, curr_n * sizeof(ElementD), 0, 0, 0));
        outQueueY.FreeTensor(y_out);
      }
    }
  }

private:
  AscendC::TPipe pipe;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueX;
  AscendC::TBuf<AscendC::TPosition::VECCALC> tmpBufXf32;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueInv;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueInv;
  AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueMM;
  AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueY;
  AscendC::GlobalTensor<ElementA> gm_x;
  AscendC::GlobalTensor<ElementMM> gm_mm;
  AscendC::GlobalTensor<float> gm_inv;
  AscendC::GlobalTensor<ElementD> gm_y;
  uint32_t m, n, k, tile_count_m, tile_count_n, aicore_index, subcore_index;
  float eps;
};
```

### Key Patterns for Complex Vector Scope

1. **Multiple stages**: This example has two sequential stages — `ComputeInvRms` (before cross_core_wait) and `ScaleRows` (after). Structure the code to match DSL ordering.
2. **Workspace partitioning**: A single workspace GM_ADDR is split into regions. Compute offsets in `Init()`.
3. **1D DataCopyPad for non-2D data**: For vector-style row-by-row processing, use `DataCopyPad` with `DataCopyExtParams(1, len*sizeof(T), 0, 0, 0)` instead of 2D copy helpers.
4. **Scalar operations**: `GetValue(0)` and `SetValue(0, val)` for scalar read/write from/to local tensors.
5. **ReduceSum**: `AscendC::ReduceSum(dst, src, workspace, count)` — workspace can alias src.
