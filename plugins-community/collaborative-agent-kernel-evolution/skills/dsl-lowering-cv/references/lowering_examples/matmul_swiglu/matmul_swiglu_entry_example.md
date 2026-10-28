### Example Output (kernel entry)
```cpp
extern "C" __global__ __aicore__
void matmul_swiglu_custom(GM_ADDR a, GM_ADDR b, GM_ADDR d,
                          GM_ADDR workspace, GM_ADDR tiling)
{
  GET_TILING_DATA(t, tiling);
  if ASCEND_IS_AIC {
    KernelCube opCube;
    opCube.Init(a, b, workspace, t.M, t.N, t.K);
    opCube.Process();
  } else if ASCEND_IS_AIV {
    KernelVector opVector;
    opVector.Init(workspace, d, t.M, t.N, t.K);
    opVector.Process();
  }
}
```

### Notes

- **Parameter order**: inputs (a, b) → output (d) → workspace → tiling. No extra source tensors.
- **N in tiling**: tiling.N stores the half-width N. Both Cube and Vector compute `TWO_N = 2 * N` internally.
- **No BlockScheduler**: Per-task manual scheduling, same as matmul_gelu without scheduler.
