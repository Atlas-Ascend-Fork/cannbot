### Example Output (kernel entry)
```cpp
extern "C" __global__ __aicore__
void matmul_bias_relu_custom(GM_ADDR a, GM_ADDR b, GM_ADDR bias, GM_ADDR d,
                             GM_ADDR workspace, GM_ADDR tiling)
{
  GET_TILING_DATA(t, tiling);
  if ASCEND_IS_AIC {
    KernelCube opCube;
    opCube.Init(a, b, workspace, t.M, t.N, t.K);
    opCube.Process();
  } else if ASCEND_IS_AIV {
    KernelVector opVector;
    opVector.Init(workspace, bias, d, t.M, t.N, t.K);
    opVector.Process();
  }
}
```

### Notes

- **Parameter order**: inputs (a, b, bias) → output (d) → workspace → tiling.
- **bias as input**: bias is the third input tensor. Cube does not use it; Vector loads it for broadcast-add.
