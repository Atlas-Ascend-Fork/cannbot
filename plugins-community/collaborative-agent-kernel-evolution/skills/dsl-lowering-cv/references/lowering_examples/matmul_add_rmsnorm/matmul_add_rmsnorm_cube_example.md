### Example Input DSL (cube scope)
```python
for block_m in range(aicore_id, tile_count_m, aicore_num):
    actual_m = tl.min(L1_M, M - block_m * L1_M)

    with tl.scope('cube'):
        for block_n in range(tile_count_n):
            actual_n = tl.min(L1_N, N - block_n * L1_N)
            actual_shape = tl.make_shape(actual_m, actual_n, K)

            coord_a = (block_m * L1_M, 0)
            coord_b = (0, block_n * L1_N)
            coord_c = (block_m * L1_M, block_n * L1_N)

            with tl.compute():
                tl.dot(A[...], layout_a, B[...], layout_b,
                       workspace[...], layout_c, actual_shape)

        tl.cross_core_set(matmul_done_id)
```

### Example Output (KernelCube)
```cpp
class KernelCube {
public:
  __aicore__ inline void Init(GM_ADDR a, GM_ADDR b, GM_ADDR workspace,
                              uint32_t m, uint32_t n, uint32_t k)
  {
    this->m = m; this->n = n; this->k = k;
    tileCountM = (m + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tileCountN = (n + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;
    gmA.SetGlobalBuffer((__gm__ ElementA*)a);
    gmB.SetGlobalBuffer((__gm__ ElementB*)b);
    gmMM.SetGlobalBuffer((__gm__ ElementMM*)workspace);
  }

  __aicore__ inline void Process()
  {
    Arch::Resource<ArchTag> resource;
    BlockMmad blockMmad(resource);
    LayoutA layoutA(m, k);
    LayoutB layoutB(k, n);
    LayoutC layoutMM(m, n);
    constexpr uint32_t tileM = (uint32_t)L1Shape::M;
    constexpr uint32_t tileN = (uint32_t)L1Shape::N;

    for (uint32_t blockM = AscendC::GetBlockIdx(); blockM < tileCountM; blockM += AscendC::GetBlockNum()) {
      uint32_t offsetM = blockM * tileM;
      uint32_t actualM = ((m - offsetM) > tileM) ? tileM : (m - offsetM);

      for (uint32_t blockN = 0; blockN < tileCountN; ++blockN) {
        uint32_t offsetN = blockN * tileN;
        uint32_t actualN = ((n - offsetN) > tileN) ? tileN : (n - offsetN);
        GemmCoord actualShape{actualM, actualN, k};

        MatrixCoord coordA{offsetM, 0};
        MatrixCoord coordB{0, offsetN};
        MatrixCoord coordMM{offsetM, offsetN};

        blockMmad(gmA[layoutA.GetOffset(coordA)], layoutA,
                  gmB[layoutB.GetOffset(coordB)], layoutB,
                  gmMM[layoutMM.GetOffset(coordMM)], layoutMM,
                  actualShape);
      }
      // Signal after ALL N tiles for this block_m are complete
      AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(MATMUL_DONE);
    }
  }

private:
  AscendC::GlobalTensor<ElementA> gmA;
  AscendC::GlobalTensor<ElementB> gmB;
  AscendC::GlobalTensor<ElementMM> gmMM;
  uint32_t m, n, k, tileCountM, tileCountN;
};
```

### Notes

- **Per-block_m scheduling**: Same as rms_matmul_scale. The outer loop is over block_m (strided by core count), inner loop over all block_n tiles. This is required because the Vector epilogue needs the entire row of matmul tiles to compute RmsNorm reduction.
- **CrossCoreSetFlag after inner loop**: Signal is placed after all N tiles in a block_m are computed, ensuring Vector has the complete row data for reduction.
