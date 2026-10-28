### Example Output (kernel entry — iterative KV block dispatch)
```cpp
extern "C" __global__ __aicore__
void flash_attn_basic_custom(GM_ADDR q, GM_ADDR k, GM_ADDR v, GM_ADDR o,
                             GM_ADDR workspace, GM_ADDR tiling)
{
  GET_TILING_DATA(t, tiling);
  if ASCEND_IS_AIC {
    KernelCube opCube;
    opCube.Init(q, k, v, workspace, t.M, t.N, t.D, t.Bk, t.scale);
    opCube.Process();
  } else if ASCEND_IS_AIV {
    KernelVector opVector;
    opVector.Init(q, o, workspace, t.M, t.N, t.D, t.Bk, t.scale);
    opVector.Process();
  }
}
```

### Notes

- **Parameter order**: inputs (q, k, v) → output (o) → workspace → tiling.
- **Single Process()**: Unlike FFN (separate ProcessMM1/ProcessMM2), Flash Attention uses a single `Process()` for both Cube and Vector. The iterative KV-block loop is **internal** to each class, with 4 cross-core events per iteration driving the pipeline.
- **Both classes share the same workspace**: Cube writes score/out; Vector reads score/out and writes prob/max/sum. The 5-segment workspace is partitioned identically in both Init methods.
- **Timeline per KV block**:
  ```
  AIC: [BMM1: Q@K^T] → signal(SCORE_READY) → wait(PROB_READY) → [BMM2: P@V] → signal(OUT_READY) → wait(UPDATE_DONE)
  AIV: wait(SCORE_READY) → [softmax] → signal(PROB_READY) → wait(OUT_READY) → [accum] → signal(UPDATE_DONE)
  ```
- **Attributes**: `scale` and `Bk` are passed through tiling struct.
