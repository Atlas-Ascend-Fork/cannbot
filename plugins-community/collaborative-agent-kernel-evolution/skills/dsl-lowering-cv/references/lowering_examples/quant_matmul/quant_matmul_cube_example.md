### Key Differences from Standard fp16 MatMul

- **int8 GlobalTensors**: `GlobalTensor<int8_t>` for A and B
- **int32 workspace output**: `GlobalTensor<int32_t>` for C (workspace) — double-buffered, NOT full M×N
- **Per-stage cross-core flags**: `flagAicStore[WORKSPACE_STAGES]` and `flagAivCompute[WORKSPACE_STAGES]` arrays
- **Stage cycling**: `stageId = (stageId + 1) % WORKSPACE_STAGES` — Cube waits for AIV before reusing slot
- **Workspace offset**: `(stageId * coreNum + coreIdx) * L1_M` — each core has dedicated slots per stage
- **Cleanup loop**: Drains outstanding stages after main loop

### Example Input DSL (cube scope)
```python
with tl.scope('cube'):
    stage_id = 0
    stage_used = 0
    for loop_idx in range(tl.program_id(), total_loops, tl.num_programs()):
        # Wait for AIV to release this workspace slot (when pipeline full)
        if stage_used == WORKSPACE_STAGES:
            tl.cross_core_wait(flag_aiv_compute[stage_id])
        else:
            stage_used += 1

        block_coord = scheduler.get_block_coord(loop_idx)
        actual_block_shape = scheduler.get_actual_block_shape(block_coord)
        coord_a = (block_coord.m * L1_M, block_coord.k * L1_K)
        coord_b = (block_coord.k * L1_K, block_coord.n * L1_N)
        # Workspace offset: stage slot for this core
        coord_c = ((stage_id * core_num + core_id) * L1_M, 0)
        with tl.compute():
            tl.dot(A[layout_a.get_offset(coord=coord_a)], layout_a,
                   B[layout_b.get_offset(coord=coord_b)], layout_b,
                   workspace[layout_ws.get_offset(coord=coord_c)], layout_ws,
                   actual_block_shape)
        # Signal workspace slot ready for AIV
        tl.cross_core_set(flag_aic_store[stage_id])
        stage_id = (stage_id + 1) % WORKSPACE_STAGES
```

### Example Output (KernelCube)
```cpp
class KernelCube {
public:
    __aicore__ inline void Init(GM_ADDR a, GM_ADDR b, GM_ADDR workspace,
                                uint32_t M, uint32_t N, uint32_t K) {
        this->M = M;
        this->N = N;
        this->K = K;

        GemmCoord problemShape{M, N, K};
        blockScheduler = BlockScheduler(problemShape, MakeCoord(L1Shape::M, L1Shape::N));
        totalTiles = blockScheduler.GetCoreLoops();

        gmA.SetGlobalBuffer((__gm__ ElementA *)a);
        gmB.SetGlobalBuffer((__gm__ ElementB *)b);
        gmC.SetGlobalBuffer((__gm__ ElementC *)workspace);

        // Initialize per-stage flag IDs
        for (uint32_t s = 0; s < WORKSPACE_STAGES; ++s) {
            flagAicStore[s] = FLAG_AIC_STORE_BASE + s * 2;
            flagAivCompute[s] = FLAG_AIV_COMPUTE_BASE + s * 2;
        }
    }

    __aicore__ inline void Process() {
        Arch::Resource<ArchTag> resource;
        BlockMmad blockMmad(resource);

        LayoutA layoutA(M, K);
        LayoutB layoutB(K, N);

        uint32_t coreIdx = AscendC::GetBlockIdx();
        uint32_t coreNum = AscendC::GetBlockNum();

        // Workspace layout: L1_M * coreNum * WORKSPACE_STAGES rows x L1_N cols
        // Each core gets WORKSPACE_STAGES slots of L1_M x L1_N
        LayoutC layoutC(L1Shape::M * coreNum * WORKSPACE_STAGES, L1Shape::N);

        uint32_t stageId = 0;
        uint32_t stageUsed = 0;

        for (uint32_t loopIdx = coreIdx; loopIdx < totalTiles;
             loopIdx += coreNum) {
            GemmCoord blockCoord = blockScheduler.GetBlockCoord(loopIdx);
            GemmCoord actualBlockShape = blockScheduler.GetActualBlockShape(blockCoord);

            // Wait for AIV to release this workspace slot (only after pipeline full)
            if (stageUsed == WORKSPACE_STAGES) {
                AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(flagAivCompute[stageId]);
            } else {
                ++stageUsed;
            }

            // A/B offsets in full matrix
            MatrixCoord offsetA{(uint32_t)(blockCoord.m() * L1Shape::M),
                                (uint32_t)(blockCoord.k() * L1Shape::K)};
            MatrixCoord offsetB{(uint32_t)(blockCoord.k() * L1Shape::K),
                                (uint32_t)(blockCoord.n() * L1Shape::N)};

            // Workspace offset: stage slot for this core
            MatrixCoord offsetC{(stageId * coreNum + coreIdx) * L1Shape::M, 0};

            blockMmad(gmA[layoutA.GetOffset(offsetA)], layoutA,
                      gmB[layoutB.GetOffset(offsetB)], layoutB,
                      gmC[layoutC.GetOffset(offsetC)], layoutC,
                      actualBlockShape);

            // Signal workspace slot ready for AIV
            AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(flagAicStore[stageId]);

            stageId = (stageId + 1 < WORKSPACE_STAGES) ? (stageId + 1) : 0;
        }

        // Cleanup: wait for AIV to finish all outstanding stages
        while (stageUsed > 0) {
            uint32_t cleanupStage = (stageId >= stageUsed) ?
                (stageId - stageUsed) : (stageId + WORKSPACE_STAGES - stageUsed);
            AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(flagAivCompute[cleanupStage]);
            --stageUsed;
        }
        AscendC::PipeBarrier<PIPE_ALL>();
    }

private:
    AscendC::GlobalTensor<ElementA> gmA;
    AscendC::GlobalTensor<ElementB> gmB;
    AscendC::GlobalTensor<ElementC> gmC;
    uint32_t M = 0, N = 0, K = 0;
    uint32_t totalTiles = 0;
    BlockScheduler blockScheduler;
    uint32_t flagAicStore[WORKSPACE_STAGES];
    uint32_t flagAivCompute[WORKSPACE_STAGES];
};
```

### Workspace Double-Buffering Algorithm

The workspace is a shared buffer of size `L1_M * L1_N * coreNum * WORKSPACE_STAGES` (int32). Each core has `WORKSPACE_STAGES` (=2) dedicated slots:

```
Workspace Memory Layout:
  slot 0, core 0: [0 .. L1_M*L1_N)
  slot 0, core 1: [L1_M*L1_N .. 2*L1_M*L1_N)
  ...
  slot 0, core N-1: [(N-1)*L1_M*L1_N .. N*L1_M*L1_N)
  slot 1, core 0: [N*L1_M*L1_N .. (N+1)*L1_M*L1_N)
  ...
```

**Stage cycling protocol:**
1. Cube checks if the pipeline is full (`stageUsed == WORKSPACE_STAGES`). If so, waits for AIV's `flagAivCompute[stageId]`.
2. Cube writes matmul result to workspace slot `stageId` for this core.
3. Cube signals `flagAicStore[stageId]` — AIV can now read this slot.
4. `stageId` advances: `(stageId + 1) % WORKSPACE_STAGES`.
5. After the main loop, a cleanup loop waits for all outstanding AIV stages.

### Notes

- **LayoutB construction**: For RowMajor B=[K,N], the constructor takes `LayoutB(K, N)`. For ColumnMajor B=[N,K], also use `LayoutB(K, N)` — the logical matrix dimensions (rows=K, cols=N).
- **int32 workspace**: gmC is `GlobalTensor<int32_t>` pointing to workspace, not to the final output tensor. The KernelVector reads from this workspace for dequantization.
- **Layout objects before loop**: Layouts are constructed before the loop since they depend only on problem dimensions (M, N, K), not on per-tile coordinates.
- **`stageUsed` tracking**: Required so that the first `WORKSPACE_STAGES` iterations don't wait (no prior AIV work to wait for). Only after filling the pipeline does Cube need to wait before reusing slots.
- **Cleanup loop**: Essential to prevent Cube from completing before Vector finishes reading the last slots. Without cleanup, the entry function may exit while Vector is still reading workspace data.
