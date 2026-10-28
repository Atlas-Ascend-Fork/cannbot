### Example Output (kernel entry — multi-stage dispatch)
```cpp
extern "C" __global__ __aicore__
void ffn_silu_custom(GM_ADDR x, GM_ADDR w1, GM_ADDR w2, GM_ADDR y,
                     GM_ADDR workspace, GM_ADDR tiling)
{
  GET_TILING_DATA(t, tiling);
  if ASCEND_IS_AIC {
    KernelCube opCube;
    opCube.Init(x, w1, w2, workspace, t.M, t.N1, t.N2, t.K);
    opCube.ProcessMM1();   // Stage 1: X @ W1 → ws_mm1
    opCube.ProcessMM2();   // Stage 3: ws_act @ W2 → ws_mm2 (waits for ACT_DONE internally)
  } else if ASCEND_IS_AIV {
    KernelVector opVector;
    opVector.Init(workspace, y, t.M, t.N1, t.N2, t.K);
    opVector.ProcessActivation();  // Stage 2: SiLU(ws_mm1) → ws_act (signals ACT_DONE)
    opVector.ProcessOutputCast();  // Stage 4: Cast(ws_mm2) → Y
  }
}
```

### Notes

- **Sequential stage calls**: Both AIC and AIV branches call two methods sequentially. The cross-core synchronization inside each method ensures correct ordering:
  - AIC: ProcessMM1 (signals MM1_DONE) → ProcessMM2 (waits ACT_DONE, signals MM2_DONE)
  - AIV: ProcessActivation (waits MM1_DONE, signals ACT_DONE) → ProcessOutputCast (waits MM2_DONE)
- **Timeline**:
  ```
  AIC: [===MM1===] signal(MM1_DONE) ----wait(ACT_DONE)---- [===MM2===] signal(MM2_DONE)
  AIV: ----wait(MM1_DONE)---- [===SiLU===] signal(ACT_DONE) ----wait(MM2_DONE)---- [===Cast===]
  ```
- **Parameter order**: inputs (x, w1, w2) → output (y) → workspace → tiling.
- **Single workspace**: All 3 segments (ws_mm1, ws_act, ws_mm2) are combined into one workspace GM_ADDR, partitioned in Init.
