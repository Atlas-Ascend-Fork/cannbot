### Example Input DSL (cube scope)
```python
TWO_N = 2 * N
tile_count_m = tl.cdiv(M, L1_M)
tile_count_n = tl.cdiv(TWO_N, L1_N)
total_tasks = tile_count_m * tile_count_n

for task_id in range(aicore_id, total_tasks, aicore_num):
    block_m = task_id // tile_count_n
    block_n = task_id % tile_count_n
    actual_m = tl.min(L1_M, M - block_m * L1_M)
    actual_n = tl.min(L1_N, TWO_N - block_n * L1_N)

    with tl.scope('cube'):
        actual_block_shape = tl.make_shape(actual_m, actual_n, K)
        coord_a = (block_m * L1_M, 0)
        coord_b = (0, block_n * L1_N)
        coord_c = (block_m * L1_M, block_n * L1_N)

        with tl.compute():
            tl.dot(A[layout_a.get_offset(coord=coord_a)], layout_a,
                   B[layout_b.get_offset(coord=coord_b)], layout_b,
                   workspace[layout_c.get_offset(coord=coord_c)], layout_c,
                   actual_block_shape)

        tl.cross_core_set(matmul_ready_id)
```

### Example Output (KernelCube)
```cpp
class KernelCube {
public:
  __aicore__ inline void Init(GM_ADDR a, GM_ADDR b, GM_ADDR workspace,
                              uint32_t M, uint32_t N, uint32_t K)
  {
    this->M = M; this->N = N; this->K = K;
    this->TWO_N = 2 * N;
    tileCountM = (M + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tileCountN = (TWO_N + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;
    totalTasks = tileCountM * tileCountN;
    gmA.SetGlobalBuffer((__gm__ ElementA *)a);
    gmB.SetGlobalBuffer((__gm__ ElementB *)b);
    gmC.SetGlobalBuffer((__gm__ ElementC *)workspace);
  }

  __aicore__ inline void Process()
  {
    Arch::Resource<ArchTag> resource;
    BlockMmad blockMmad(resource);
    LayoutA layoutA(M, K);
    LayoutB layoutB(K, TWO_N);
    LayoutC layoutC(M, TWO_N);
    constexpr uint32_t tileM = (uint32_t)L1Shape::M;
    constexpr uint32_t tileN = (uint32_t)L1Shape::N;

    for (uint32_t taskId = AscendC::GetBlockIdx(); taskId < totalTasks; taskId += AscendC::GetBlockNum()) {
      uint32_t blockM = taskId / tileCountN;
      uint32_t blockN = taskId % tileCountN;
      uint32_t offsetM = blockM * tileM;
      uint32_t offsetN = blockN * tileN;
      uint32_t actualM = ((M - offsetM) > tileM) ? tileM : (M - offsetM);
      uint32_t actualN = ((TWO_N - offsetN) > tileN) ? tileN : (TWO_N - offsetN);

      GemmCoord actualShape{actualM, actualN, K};
      MatrixCoord coordA{offsetM, 0};
      MatrixCoord coordB{0, offsetN};
      MatrixCoord coordC{offsetM, offsetN};

      blockMmad(gmA[layoutA.GetOffset(coordA)], layoutA,
                gmB[layoutB.GetOffset(coordB)], layoutB,
                gmC[layoutC.GetOffset(coordC)], layoutC,
                actualShape);
      AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(matmulReady);
    }
  }

private:
  AscendC::GlobalTensor<ElementA> gmA;
  AscendC::GlobalTensor<ElementB> gmB;
  AscendC::GlobalTensor<ElementC> gmC;
  uint32_t M, N, K, TWO_N, tileCountM, tileCountN, totalTasks;
};
```

### Notes

- **TWO_N dimension**: The Cube operates on the full 2N width. Layout B is (K, 2N) and Layout C is (M, 2N).
- **Tile count on 2N**: `tileCountN = ceil(2N / L1_N)`, not `ceil(N / L1_N)`.
- **N stored for Vector**: The Init receives N (half-width), computes `TWO_N = 2 * N` internally.
