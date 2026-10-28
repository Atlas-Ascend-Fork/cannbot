### Example Input DSL (cube scope — 2 matmul stages)
```python
for block_m in range(aicore_id, tile_count_m, aicore_num):
    actual_m = tl.min(L1_M, M - block_m * L1_M)

    # Stage 1: Cube MM1 (X @ W1 → workspace_mm1)
    with tl.scope('cube'):
        for block_n in range(tile_count_n1):
            actual_n1 = tl.min(L1_N, N1 - block_n * L1_N)
            actual_shape = tl.make_shape(actual_m, actual_n1, K)
            with tl.compute():
                tl.dot(X[...], layout_x, W1[...], layout_w1,
                       workspace_mm1[...], layout_mm1, actual_shape)
        tl.cross_core_set(mm1_done_id)

    # ... Vector SiLU stage ...

    # Stage 3: Cube MM2 (workspace_act @ W2 → workspace_mm2)
    with tl.scope('cube'):
        tl.cross_core_wait(act_done_id)
        for block_n in range(tile_count_n2):
            actual_n2 = tl.min(L1_N, N2 - block_n * L1_N)
            actual_shape2 = tl.make_shape(actual_m, actual_n2, N1)
            with tl.compute():
                tl.dot(workspace_act[...], layout_act, W2[...], layout_w2,
                       workspace_mm2[...], layout_mm2, actual_shape2)
        tl.cross_core_set(mm2_done_id)
```

### Example Output (KernelCube — multi-method)
```cpp
class KernelCube {
public:
  __aicore__ inline void Init(GM_ADDR x, GM_ADDR w1, GM_ADDR w2, GM_ADDR workspace,
                              uint32_t m, uint32_t n1, uint32_t n2, uint32_t k)
  {
    this->m = m; this->n1 = n1; this->n2 = n2; this->k = k;
    tileCountM = (m + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;
    tileCountN1 = (n1 + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;
    tileCountN2 = (n2 + (uint32_t)L1Shape::N - 1) / (uint32_t)L1Shape::N;

    gmX.SetGlobalBuffer((__gm__ ElementInput*)x);
    gmW1.SetGlobalBuffer((__gm__ ElementWeight*)w1);
    gmW2.SetGlobalBuffer((__gm__ ElementWeight*)w2);

    // Workspace partitioning: [ws_mm1 | ws_act | ws_mm2]
    size_t wsMm1Bytes = (size_t)m * (size_t)n1 * sizeof(float);
    size_t wsActBytes = (size_t)m * (size_t)n1 * sizeof(uint16_t);

    gmMM1.SetGlobalBuffer((__gm__ ElementMM*)workspace);
    gmAct.SetGlobalBuffer((__gm__ ElementAct*)((__gm__ uint8_t*)workspace + wsMm1Bytes));
    gmMM2.SetGlobalBuffer((__gm__ ElementMM*)((__gm__ uint8_t*)workspace + wsMm1Bytes + wsActBytes));
  }

  __aicore__ inline void ProcessMM1()
  {
    Arch::Resource<ArchTag> resource1;
    BlockMmad1 blockMmad1(resource1);
    LayoutA layoutX(m, k);
    LayoutB layoutW1(k, n1);
    LayoutC layoutMM1(m, n1);
    constexpr uint32_t tileM = (uint32_t)L1Shape::M;
    constexpr uint32_t tileN = (uint32_t)L1Shape::N;

    for (uint32_t blockM = AscendC::GetBlockIdx(); blockM < tileCountM; blockM += AscendC::GetBlockNum()) {
      uint32_t offsetM = blockM * tileM;
      uint32_t actualM = ((m - offsetM) > tileM) ? tileM : (m - offsetM);

      for (uint32_t blockN = 0; blockN < tileCountN1; ++blockN) {
        uint32_t offsetN = blockN * tileN;
        uint32_t actualN = ((n1 - offsetN) > tileN) ? tileN : (n1 - offsetN);
        GemmCoord actualShape{actualM, actualN, k};

        blockMmad1(gmX[layoutX.GetOffset(MatrixCoord{offsetM, 0})], layoutX,
                   gmW1[layoutW1.GetOffset(MatrixCoord{0, offsetN})], layoutW1,
                   gmMM1[layoutMM1.GetOffset(MatrixCoord{offsetM, offsetN})], layoutMM1,
                   actualShape);
      }
      AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(MM1_DONE);
    }
  }

  __aicore__ inline void ProcessMM2()
  {
    Arch::Resource<ArchTag> resource2;
    BlockMmad2 blockMmad2(resource2);
    LayoutA layoutAct(m, n1);
    LayoutB layoutW2(n1, n2);
    LayoutC layoutMM2(m, n2);
    constexpr uint32_t tileM = (uint32_t)L1Shape::M;
    constexpr uint32_t tileN = (uint32_t)L1Shape::N;

    for (uint32_t blockM = AscendC::GetBlockIdx(); blockM < tileCountM; blockM += AscendC::GetBlockNum()) {
      uint32_t offsetM = blockM * tileM;
      uint32_t actualM = ((m - offsetM) > tileM) ? tileM : (m - offsetM);

      // Wait for Vector to complete SiLU activation for this block_m
      AscendC::CrossCoreWaitFlag<0x2, PIPE_MTE3>(ACT_DONE);

      for (uint32_t blockN = 0; blockN < tileCountN2; ++blockN) {
        uint32_t offsetN = blockN * tileN;
        uint32_t actualN = ((n2 - offsetN) > tileN) ? tileN : (n2 - offsetN);
        GemmCoord actualShape{actualM, actualN, n1};

        blockMmad2(gmAct[layoutAct.GetOffset(MatrixCoord{offsetM, 0})], layoutAct,
                   gmW2[layoutW2.GetOffset(MatrixCoord{0, offsetN})], layoutW2,
                   gmMM2[layoutMM2.GetOffset(MatrixCoord{offsetM, offsetN})], layoutMM2,
                   actualShape);
      }
      AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(MM2_DONE);
    }
  }

private:
  AscendC::GlobalTensor<ElementInput> gmX;
  AscendC::GlobalTensor<ElementWeight> gmW1;
  AscendC::GlobalTensor<ElementWeight> gmW2;
  AscendC::GlobalTensor<ElementMM> gmMM1;
  AscendC::GlobalTensor<ElementAct> gmAct;
  AscendC::GlobalTensor<ElementMM> gmMM2;
  uint32_t m, n1, n2, k, tileCountM, tileCountN1, tileCountN2;
};
```

### Key Patterns

1. **Multi-method Cube**: `ProcessMM1()` and `ProcessMM2()` are separate methods called sequentially from the entry function. Each creates its own `Resource` and `BlockMmad`.

2. **Workspace partitioning in Init**: The single workspace GM_ADDR is split into 3 segments using byte-level pointer arithmetic. Both Cube and Vector must use the same offset calculation.

3. **Bidirectional cross-core sync**:
   - MM1→Vector: `CrossCoreSetFlag<0x2, PIPE_FIX>(MM1_DONE)` (Cube signals Vector)
   - Vector→MM2: `CrossCoreWaitFlag<0x2, PIPE_MTE3>(ACT_DONE)` (Cube waits for Vector's MTE3 signal)
   - MM2→Vector: `CrossCoreSetFlag<0x2, PIPE_FIX>(MM2_DONE)` (Cube signals Vector again)

4. **MM2 K dimension = N1**: The second matmul uses the activation dimension N1 as its K dimension (workspace_act is M×N1, W2 is N1×N2).

5. **Same loop structure**: Both ProcessMM1 and ProcessMM2 use the same per-block_m scheduling with inner N-loop, just with different dimensions and BlockMmad instances.
