### Example Output (kernel entry)
```cpp
extern "C" __global__ __aicore__
void matmul_add_rmsnorm_custom(GM_ADDR a, GM_ADDR b, GM_ADDR residual, GM_ADDR gamma,
                               GM_ADDR y, GM_ADDR xadd,
                               GM_ADDR workspace, GM_ADDR tiling)
{
  GET_TILING_DATA(t, tiling);
  if ASCEND_IS_AIC {
    KernelCube opCube;
    opCube.Init(a, b, workspace, t.M, t.N, t.K);
    opCube.Process();
  } else if ASCEND_IS_AIV {
    KernelVector opVector;
    opVector.Init(workspace, residual, gamma, y, xadd, t.M, t.N, t.K, t.eps);
    opVector.Process();
  }
}
```

### Notes

- **Parameter order**: inputs (a, b, residual, gamma) → outputs (y, xadd) → workspace → tiling.
- **Dual outputs**: Both `y` (normalized output) and `xadd` (residual-added intermediate) are output GM_ADDRs.
- **Vector receives all extra tensors**: residual, gamma, both outputs, workspace, dimensions, and eps attribute.
- **Cube only needs**: inputs (a, b) and workspace for matmul accumulation.
