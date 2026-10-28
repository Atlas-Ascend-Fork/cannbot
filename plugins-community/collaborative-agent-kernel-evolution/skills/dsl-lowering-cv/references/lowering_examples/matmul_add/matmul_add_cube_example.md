### Example Input DSL (cube scope)
```python
for task_id in range(aicore_id, total_tasks, aicore_num):
    block_m = task_id // tile_count_n
    block_n = task_id % tile_count_n
    actual_m = tl.min(L1_M, M - block_m * L1_M)
    actual_n = tl.min(L1_N, N - block_n * L1_N)

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
    tileCountM = (M + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tileCountN = (N + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;
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
    LayoutB layoutB(K, N);
    LayoutC layoutC(M, N);
    constexpr uint32_t tileM = (uint32_t)L1Shape::M;
    constexpr uint32_t tileN = (uint32_t)L1Shape::N;

    for (uint32_t taskId = AscendC::GetBlockIdx(); taskId < totalTasks; taskId += AscendC::GetBlockNum()) {
      uint32_t blockM = taskId / tileCountN;
      uint32_t blockN = taskId % tileCountN;
      uint32_t offsetM = blockM * tileM;
      uint32_t offsetN = blockN * tileN;
      uint32_t actualM = ((M - offsetM) > tileM) ? tileM : (M - offsetM);
      uint32_t actualN = ((N - offsetN) > tileN) ? tileN : (N - offsetN);

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
  uint32_t M, N, K, tileCountM, tileCountN, totalTasks;
};
```

### Notes

- **Per-task scheduling**: Uses `taskId / tileCountN` and `taskId % tileCountN` to map 1D task index to 2D (blockM, blockN) tile coordinates. This is the standard pattern for per-task fused CV operators.
- **CrossCoreSetFlag per task**: Signal is inside the task loop, meaning each task independently signals completion to the corresponding Vector task.
- **Cube only receives inputs + workspace**: No residual tensor — residual is only needed by Vector.
