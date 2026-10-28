### Example Input DSL (kernel entry)
```python
rms_matmul_scale_kernel[core_num](x, weight, out, workspace_mm, workspace_inv, m, k, o, norm_eps)
```

### Example Output (kernel entry dispatch)
```cpp
extern "C" __global__ __aicore__
void rms_matmul_scale_custom(GM_ADDR x, GM_ADDR weight, GM_ADDR y, GM_ADDR workspace, GM_ADDR tiling)
{
  GET_TILING_DATA(t, tiling);
  if ASCEND_IS_AIC {
    KernelCube cube;
    cube.Init(x, weight, workspace, t.M, t.N, t.K);
    cube.Process();
  } else if ASCEND_IS_AIV {
    KernelVector vec;
    vec.Init(x, y, workspace, t.M, t.N, t.K, t.eps);
    vec.Process();
  }
}
```

### Notes

- **Workspace merging**: Even though DSL has `workspace_mm` and `workspace_inv` as separate tensors, the entry function receives a single `workspace` GM_ADDR. The vector kernel partitions it internally.
- **Parameter distribution**: Cube only needs input tensors + workspace. Vector needs input (for RMS), output, workspace, and attributes.
- **Attributes from tiling**: `norm_eps` is read from the tiling struct as `t.eps`.
