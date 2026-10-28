### Example Input DSL (cube scope)
```python
with tl.scope('cube'):
    for loop_idx in range(tl.program_id(), total_loops, tl.num_programs()):
        block_coord = scheduler.get_block_coord(loop_idx)
        block_m, block_n, block_k = block_coord
        actual_block_shape = scheduler.get_actual_block_shape(block_coord)
        coord_a = (block_m * L1_M, block_k * L1_K)
        coord_b = (block_k * L1_K, block_n * L1_N)
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
  __aicore__ inline void Init(GM_ADDR a, GM_ADDR b, GM_ADDR workspace, uint32_t M, uint32_t N, uint32_t K) {
    this->M = M; this->N = N; this->K = K;
    GemmCoord problemShape{M, N, K};
    blockScheduler = BlockScheduler(problemShape, MakeCoord(L1Shape::M, L1Shape::N));
    totalTiles = blockScheduler.GetCoreLoops();
    gmA.SetGlobalBuffer((__gm__ ElementA *)a);
    gmB.SetGlobalBuffer((__gm__ ElementB *)b);
    gmC.SetGlobalBuffer((__gm__ ElementC *)workspace);
  }

  __aicore__ inline void Process() {
    Arch::Resource<ArchTag> resource;
    BlockMmad blockMmad(resource);
    for (uint32_t loopIdx = AscendC::GetBlockIdx(); loopIdx < totalTiles; loopIdx += AscendC::GetBlockNum()) {
      GemmCoord blockCoord = blockScheduler.GetBlockCoord(loopIdx);
      GemmCoord actualBlockShape = blockScheduler.GetActualBlockShape(blockCoord);
      MatrixCoord offsetA{(uint32_t)(blockCoord.m() * L1Shape::M), (uint32_t)(blockCoord.k() * L1Shape::K)};
      MatrixCoord offsetB{(uint32_t)(blockCoord.k() * L1Shape::K), (uint32_t)(blockCoord.n() * L1Shape::N)};
      MatrixCoord offsetC{(uint32_t)(blockCoord.m() * L1Shape::M), (uint32_t)(blockCoord.n() * L1Shape::N)};
      LayoutA layoutA(M, K);
      LayoutB layoutB(K, N);
      LayoutC layoutC(M, N);
      blockMmad(gmA[layoutA.GetOffset(offsetA)], layoutA,
                gmB[layoutB.GetOffset(offsetB)], layoutB,
                gmC[layoutC.GetOffset(offsetC)], layoutC,
                actualBlockShape);
      AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(matmulReady);
    }
  }
private:
  AscendC::GlobalTensor<ElementA> gmA;
  AscendC::GlobalTensor<ElementB> gmB;
  AscendC::GlobalTensor<ElementC> gmC;
  uint32_t M, N, K, totalTiles;
  BlockScheduler blockScheduler;
};
```

### DSL → AscendC Mapping (Cube)

| DSL Construct | AscendC Equivalent |
|---|---|
| `tl.scope('cube')` | Code in `KernelCube` class |
| `tl.program_id()` | `AscendC::GetBlockIdx()` |
| `tl.num_programs()` | `AscendC::GetBlockNum()` |
| `scheduler.get_block_coord(idx)` | `blockScheduler.GetBlockCoord(idx)` |
| `scheduler.get_actual_block_shape(coord)` | `blockScheduler.GetActualBlockShape(coord)` |
| `layout.get_offset(coord=(...))` | `layout.GetOffset(MatrixCoord{...})` |
| `tl.dot(A, layoutA, B, layoutB, C, layoutC, shape)` | `blockMmad(gmA[...], layoutA, gmB[...], layoutB, gmC[...], layoutC, shape)` |
| `tl.cross_core_set(event_id)` | `AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(event_id)` |

### Key Implementation Notes

1. **BlockScheduler** is instantiated with `(problemShape, MakeCoord(L1Shape::M, L1Shape::N))` when DSL uses a scheduler.
2. **For manual scheduling** (no DSL scheduler), compute `tile_count_m/n` manually and loop with stride pattern.
3. **Layout construction**: `LayoutA layoutA(M, K)` for RowMajor means stride = (K, 1).
4. **Resource**: `Arch::Resource<ArchTag> resource` must be created before `BlockMmad`.
5. **cross_core_set placement**: Must match DSL placement (inside or outside inner loop).
