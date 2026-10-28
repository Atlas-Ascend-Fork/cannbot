### Example Input DSL (cube scope — inner-loop over KV blocks)
```python
for block_m in range(aicore_id, tile_count_m, aicore_num):
    for kv_b in range(kv_blocks):
        # BMM1: Q @ K_b^T → workspace_score
        with tl.scope('cube'):
            if kv_b > 0:
                tl.cross_core_wait(update_done_id)
            tl.dot(Q[...], layout_q, K[coord_k...], layout_k,
                   workspace_score[...], layout_score, actual_shape_bmm1)
            tl.cross_core_set(score_ready_id)

        # ... Vector softmax ...

        # BMM2: P_b @ V_b → workspace_out
        with tl.scope('cube'):
            tl.cross_core_wait(prob_ready_id)
            tl.dot(workspace_prob[...], layout_prob, V[coord_v...], layout_v,
                   workspace_out[...], layout_out, actual_shape_bmm2)
            tl.cross_core_set(out_ready_id)

        # ... Vector accumulate ...
```

### Example Output (KernelCube — inner-loop pattern)
```cpp
class KernelCube {
public:
  __aicore__ inline void Init(GM_ADDR q, GM_ADDR k, GM_ADDR v, GM_ADDR workspace,
                              uint32_t m, uint32_t n, uint32_t d, uint32_t bk, float scale)
  {
    this->m = m; this->n = n; this->d = d; this->bk = bk;
    kvBlocks = (n + bk - 1) / bk;
    tileCountM = (m + (uint32_t)L1Shape::M - 1) / (uint32_t)L1Shape::M;

    gmQ.SetGlobalBuffer((__gm__ ElementQ*)q);
    gmK.SetGlobalBuffer((__gm__ ElementK*)k);
    gmV.SetGlobalBuffer((__gm__ ElementV*)v);

    // Workspace partitioning: [score | prob | out | max | sum]
    size_t wsScoreBytes = (size_t)m * (size_t)bk * sizeof(float);
    size_t wsProbBytes  = (size_t)m * (size_t)bk * sizeof(uint16_t);
    size_t wsOutBytes   = (size_t)m * (size_t)d  * sizeof(float);

    gmScore.SetGlobalBuffer((__gm__ ElementScore*)((__gm__ uint8_t*)workspace));
    gmProb.SetGlobalBuffer((__gm__ ElementProb*)((__gm__ uint8_t*)workspace + wsScoreBytes));
    gmOut.SetGlobalBuffer((__gm__ ElementOut*)((__gm__ uint8_t*)workspace + wsScoreBytes + wsProbBytes));
  }

  __aicore__ inline void Process()
  {
    Arch::Resource<ArchTag> resource;
    BlockMmad1 blockMmad1(resource);
    BlockMmad2 blockMmad2(resource);

    constexpr uint32_t tileM = (uint32_t)L1Shape::M;

    for (uint32_t blockM = AscendC::GetBlockIdx(); blockM < tileCountM; blockM += AscendC::GetBlockNum()) {
      uint32_t offsetM = blockM * tileM;
      uint32_t actualM = ((m - offsetM) > tileM) ? tileM : (m - offsetM);

      for (uint32_t kvB = 0; kvB < kvBlocks; ++kvB) {
        uint32_t kvStart = kvB * bk;
        uint32_t actualBk = ((n - kvStart) > bk) ? bk : (n - kvStart);

        // Wait for Vector to finish previous iteration's output accumulation
        if (kvB > 0) {
          AscendC::CrossCoreWaitFlag<0x2, PIPE_MTE3>(UPDATE_DONE);
        }

        // ---- BMM1: Q(M,D) @ K_b^T(D,Bk) → Score(M,Bk) ----
        {
          LayoutQ layoutQ(m, d);
          LayoutKT layoutKT(d, actualBk);         // ColumnMajor: logical (D, Bk)
          LayoutScore layoutScore(m, bk);

          GemmCoord shape1{actualM, actualBk, d};
          MatrixCoord coordQ{offsetM, 0};
          // K is row-major (N,D): K_b starts at row kvStart
          // For ColumnMajor B: offset = (0, kvStart) in logical (D, Bk) space
          // In physical storage (N,D), K_b[kvStart] is at row kvStart
          MatrixCoord coordKT{0, kvStart};
          MatrixCoord coordS{offsetM, 0};

          blockMmad1(gmQ[layoutQ.GetOffset(coordQ)], layoutQ,
                     gmK[kvStart * d], layoutKT,
                     gmScore[layoutScore.GetOffset(coordS)], layoutScore,
                     shape1);
        }
        AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(SCORE_READY);

        // Wait for Vector to finish softmax → prob ready
        AscendC::CrossCoreWaitFlag<0x2, PIPE_MTE3>(PROB_READY);

        // ---- BMM2: Prob(M,Bk) @ V_b(Bk,D) → OutPartial(M,D) ----
        {
          LayoutProb layoutProb(m, bk);
          LayoutV layoutV(n, d);                   // V is row-major (N, D)
          LayoutOut layoutOut(m, d);

          GemmCoord shape2{actualM, d, actualBk};
          MatrixCoord coordP{offsetM, 0};
          MatrixCoord coordV{kvStart, 0};
          MatrixCoord coordO{offsetM, 0};

          blockMmad2(gmProb[layoutProb.GetOffset(coordP)], layoutProb,
                     gmV[layoutV.GetOffset(coordV)], layoutV,
                     gmOut[layoutOut.GetOffset(coordO)], layoutOut,
                     shape2);
        }
        AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(OUT_READY);
      }
    }
  }

private:
  AscendC::GlobalTensor<ElementQ> gmQ;
  AscendC::GlobalTensor<ElementK> gmK;
  AscendC::GlobalTensor<ElementV> gmV;
  AscendC::GlobalTensor<ElementScore> gmScore;
  AscendC::GlobalTensor<ElementProb> gmProb;
  AscendC::GlobalTensor<ElementOut> gmOut;
  uint32_t m, n, d, bk, kvBlocks, tileCountM;
};
```

### Key Patterns

1. **Inner-loop over KV blocks**: This is **Option C** from the SKILL.md multi-Cube strategy — a single `Process()` with an inner `kvB` loop. Both BMM1 and BMM2 execute within the same loop body using the same `resource`.

2. **4-event bidirectional sync per iteration**:
   - Cube signals `SCORE_READY` (PIPE_FIX) → Vector does softmax → Vector signals `PROB_READY` (PIPE_MTE3)
   - Cube signals `OUT_READY` (PIPE_FIX) → Vector accumulates → Vector signals `UPDATE_DONE` (PIPE_MTE3)
   - Cube waits for `UPDATE_DONE` at the start of the **next** iteration (not current)

3. **K^T handling**: K is stored (N, D) row-major. For Q @ K^T, we use ColumnMajor layout for the B operand and offset directly to `gmK[kvStart * d]` for the KV block slice.

4. **Score/Prob workspace reused across iterations**: The same workspace_score and workspace_prob buffers are rewritten each KV block — they only need to hold one block at a time.

5. **Reference**: This maps to CANN `flash_attention_score_s1s2_bn2gs1.h`'s `IterateBmm1` + `IterateBmm2` pattern inside the S2 loop.
