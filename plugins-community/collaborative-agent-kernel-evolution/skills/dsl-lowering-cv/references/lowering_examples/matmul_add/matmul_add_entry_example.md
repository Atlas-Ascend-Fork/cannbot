### Example Output (kernel entry)
```cpp
extern "C" __global__ __aicore__
void matmul_add_custom(GM_ADDR a, GM_ADDR b, GM_ADDR residual, GM_ADDR d,
                       GM_ADDR workspace, GM_ADDR tiling)
{
  GET_TILING_DATA(t, tiling);
  if ASCEND_IS_AIC {
    KernelCube opCube;
    opCube.Init(a, b, workspace, t.M, t.N, t.K);
    opCube.Process();
  } else if ASCEND_IS_AIV {
    KernelVector opVector;
    opVector.Init(workspace, residual, d, t.M, t.N, t.K);
    opVector.Process();
  }
}
```

### Notes

- **Parameter order**: inputs (a, b, residual) → output (d) → workspace → tiling.
- **Cube receives**: input tensors (a, b) + workspace. No residual needed by Cube.
- **Vector receives**: workspace (matmul result) + residual (extra source) + output (d).
- **Per-task scheduling**: Both Cube and Vector use taskId-based loop internally.
