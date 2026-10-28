### Example Output (kernel entry)
```cpp
extern "C" __global__ __aicore__
void matmul_gelu_custom(GM_ADDR a, GM_ADDR b, GM_ADDR d, GM_ADDR workspace, GM_ADDR tiling) {
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

### Entry Pass Rules

1. **Function signature**: Must match the operator's input/output tensors + workspace + tiling, all as `GM_ADDR`.
2. **Function name**: Must be the snake_case operator custom name (e.g., `matmul_gelu_custom`).
3. **GET_TILING_DATA**: Use `GET_TILING_DATA(t, tiling)` to load tiling parameters.
4. **AIC/AIV dispatch**: Use `ASCEND_IS_AIC` for cube core, `ASCEND_IS_AIV` for vector core.
5. **Parameter passing**:
   - KernelCube gets: input tensors + workspace + tiling scalars
   - KernelVector gets: workspace (intermediate) + output tensor + tiling scalars
   - Both classes receive the tiling parameters they need from the tiling struct `t`.
6. **Workspace is a single GM_ADDR**: Both cube and vector access the same workspace pointer. Vector may offset into it for different regions.
7. **Attributes**: If the operator has attributes (e.g., `eps`), they are in the tiling struct and passed to Init.

### Parameter Ordering Convention

The entry function parameters follow this order:
1. User input tensors (in order from project.json)
2. User output tensor(s)
3. `workspace` (GM_ADDR)
4. `tiling` (GM_ADDR) — always last
