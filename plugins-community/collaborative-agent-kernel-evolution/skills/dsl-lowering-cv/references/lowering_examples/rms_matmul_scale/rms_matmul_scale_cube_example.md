### Example Input DSL (cube scope)
```python
with tl.scope("cube"):
    for block_m in range(aicore_id, tile_count_m, aicore_num):
        actual_m = tl.min(L1_M, M - block_m * L1_M)
        for block_n in range(tile_count_n):
            actual_n = tl.min(L1_N, O - block_n * L1_N)
            actual_shape = tl.make_shape(actual_m, actual_n, K)
            coord_x = (block_m * L1_M, 0)
            coord_w = (0, block_n * L1_N)
            coord_mm = (block_m * L1_M, block_n * L1_N)
            with tl.compute():
                tl.dot(x[...], layout_x, weight[...], layout_w,
                       workspace_mm[...], layout_mm, actual_shape)
        tl.cross_core_set(matmul_done_id)
```

### Example Output (KernelCube)
```cpp
class KernelCube {
public:
  __aicore__ inline void Init(GM_ADDR x, GM_ADDR weight, GM_ADDR workspace, uint32_t m, uint32_t n, uint32_t k)
  {
    this->m = m; this->n = n; this->k = k;
    tile_count_m = (m + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tile_count_n = (n + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;
    gm_x.SetGlobalBuffer((__gm__ ElementA*)x);
    gm_w.SetGlobalBuffer((__gm__ ElementB*)weight);
    gm_mm.SetGlobalBuffer((__gm__ ElementMM*)workspace);
  }

  __aicore__ inline void Process()
  {
    Arch::Resource<ArchTag> resource;
    BlockMmad blockMmad(resource);
    LayoutA layout_x(m, k);
    LayoutB layout_w(k, n);
    LayoutC layout_mm(m, n);
    constexpr uint32_t tile_m = (uint32_t)L1Shape::M;
    constexpr uint32_t tile_n = (uint32_t)L1Shape::N;

    for (uint32_t block_m = AscendC::GetBlockIdx(); block_m < tile_count_m; block_m += AscendC::GetBlockNum()) {
      uint32_t offset_m = block_m * tile_m;
      uint32_t actual_m = ((m - offset_m) > tile_m) ? tile_m : (m - offset_m);
      for (uint32_t block_n = 0; block_n < tile_count_n; ++block_n) {
        uint32_t offset_n = block_n * tile_n;
        uint32_t actual_n = ((n - offset_n) > tile_n) ? tile_n : (n - offset_n);
        GemmCoord actual_shape{actual_m, actual_n, k};

        MatrixCoord coord_x{offset_m, 0};
        MatrixCoord coord_w{0, offset_n};
        MatrixCoord coord_mm{offset_m, offset_n};
        blockMmad(gm_x[layout_x.GetOffset(coord_x)], layout_x,
                  gm_w[layout_w.GetOffset(coord_w)], layout_w,
                  gm_mm[layout_mm.GetOffset(coord_mm)], layout_mm,
                  actual_shape);
      }
      // Signal once per block_m (per-row tile), matching DSL placement of cross_core_set.
      AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(MATMUL_READY);
    }
  }
private:
  AscendC::GlobalTensor<ElementA> gm_x;
  AscendC::GlobalTensor<ElementB> gm_w;
  AscendC::GlobalTensor<ElementMM> gm_mm;
  uint32_t m, n, k, tile_count_m, tile_count_n;
};
```

### Notes

- **Manual scheduling (no BlockScheduler)**: When DSL uses manual `for block_m in range(aicore_id, tile_count_m, aicore_num)`, translate directly to `for (uint32_t block_m = AscendC::GetBlockIdx(); block_m < tile_count_m; block_m += AscendC::GetBlockNum())`.
- **Inner loop over N**: The `block_n` loop is inside the outer `block_m` loop, matching DSL structure.
- **cross_core_set placement**: Signal is placed after the inner `block_n` loop completes, matching DSL's `tl.cross_core_set(matmul_done_id)` position (once per block_m).
- **Layout construction**: `LayoutA layout_x(m, k)` constructs a row-major layout with dimensions m×k.
