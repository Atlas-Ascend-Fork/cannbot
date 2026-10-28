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
        coord_d = (block_m * L1_M, block_n * L1_N)

        with tl.compute():
            tl.dot(A[layout_a.get_offset(coord=coord_a)], layout_a,
                   B[layout_b.get_offset(coord=coord_b)], layout_b,
                   D[layout_d.get_offset(coord=coord_d)], layout_d,
                   actual_block_shape)
```

### Example Output (KernelCube — Fixpipe)
```cpp
class KernelCube {
public:
  __aicore__ inline void Init(GM_ADDR a, GM_ADDR b, GM_ADDR d,
                              uint32_t M, uint32_t N, uint32_t K)
  {
    this->M = M; this->N = N; this->K = K;
    tileCountM = (M + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tileCountN = (N + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;
    totalTasks = tileCountM * tileCountN;
    gmA.SetGlobalBuffer((__gm__ ElementA *)a);
    gmB.SetGlobalBuffer((__gm__ ElementB *)b);
    gmD.SetGlobalBuffer((__gm__ ElementC *)d);  // Fixpipe: output is ElementC = half
  }

  __aicore__ inline void Process()
  {
    Arch::Resource<ArchTag> resource;
    BlockMmad blockMmad(resource);
    LayoutA layoutA(M, K);
    LayoutB layoutB(K, N);
    LayoutD layoutD(M, N);
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
      MatrixCoord coordD{offsetM, offsetN};

      // Fixpipe: BlockMmad writes directly to output tensor (gmD), no workspace
      blockMmad(gmA[layoutA.GetOffset(coordA)], layoutA,
                gmB[layoutB.GetOffset(coordB)], layoutB,
                gmD[layoutD.GetOffset(coordD)], layoutD,
                actualShape);
    }
  }

private:
  AscendC::GlobalTensor<ElementA> gmA;
  AscendC::GlobalTensor<ElementB> gmB;
  AscendC::GlobalTensor<ElementC> gmD;
  uint32_t M, N, K, tileCountM, tileCountN, totalTasks;
};
```

### Notes

- **Fixpipe: Cube writes directly to output**: No workspace, no cross-core sync, no Vector scope. `gmD` IS the final output tensor.
- **Identical to matmul Fixpipe**: The cube_pass for 1x1 conv is the same as any matmul with Fixpipe fp32→fp16 cast.
