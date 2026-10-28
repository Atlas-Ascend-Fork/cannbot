### Example Output (kernel entry — ConvBias / AIC-only)
```cpp
extern "C" __global__ __aicore__
void conv2d_bias_custom(GM_ADDR fmap, GM_ADDR filter, GM_ADDR bias, GM_ADDR output,
                         GM_ADDR workspace, GM_ADDR tiling)
{
  GET_TILING_DATA(t, tiling);
  // ConvBias: AIC-only dispatch
  if ASCEND_IS_AIC {
    KernelCube opCube;
    opCube.Init(fmap, filter, bias, output,
                t.batch, t.Cin, t.H, t.W, t.Cout,
                t.kH, t.kW, t.strideH, t.strideW, t.padH, t.padW,
                t.Ho, t.Wo, t.Cin1, t.Cout1);
    opCube.Process();
  }
}
```

### Notes

- **AIC-only**: ConvBias runs entirely on Cube cores. No `ASCEND_IS_AIV` branch.
- **Parameter order**: inputs (fmap, filter, bias) → output → workspace → tiling.
- **All conv params from tiling**: Batch, spatial dims, kernel size, stride, padding, and derived dims (Ho, Wo, Cin1, Cout1) are all passed via the tiling struct.
- **Input format requirement**: `fmap` must be in NC1HWC0 format, `filter` in FracZ format. Host is responsible for format conversion if inputs are in NCHW.

### Conv2d + Activation Variant

If Vector scope is needed (e.g., Conv2d + ReLU), change to:
```cpp
void conv2d_relu_custom(GM_ADDR fmap, GM_ADDR filter, GM_ADDR bias, GM_ADDR output,
                         GM_ADDR workspace, GM_ADDR tiling)
{
  GET_TILING_DATA(t, tiling);
  if ASCEND_IS_AIC {
    KernelCube opCube;
    opCube.Init(fmap, filter, workspace, ...);  // Write to workspace, not output
    opCube.Process();
  } else if ASCEND_IS_AIV {
    KernelVector opVector;
    opVector.Init(workspace, bias, output, ...);  // Read workspace, apply activation
    opVector.Process();
  }
}
```
