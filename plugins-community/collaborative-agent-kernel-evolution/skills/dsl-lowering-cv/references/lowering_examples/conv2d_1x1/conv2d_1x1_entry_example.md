### Example Output (kernel entry — Fixpipe / AIC-only)
```cpp
extern "C" __global__ __aicore__
void conv2d_1x1_custom(GM_ADDR a, GM_ADDR b, GM_ADDR d,
                        GM_ADDR workspace, GM_ADDR tiling)
{
  GET_TILING_DATA(t, tiling);
  // Fixpipe: AIC-only dispatch, no AIV branch
  if ASCEND_IS_AIC {
    KernelCube opCube;
    opCube.Init(a, b, d, t.M, t.N, t.K);
    opCube.Process();
  }
}
```

### Notes

- **AIC-only**: No `ASCEND_IS_AIV` branch. Fixpipe pattern runs entirely on Cube cores.
- **Parameters**: `a` = reshaped input [M,K], `b` = reshaped weight [K,N], `d` = output [M,N].
- **Host is responsible for reshape**: The 4D→2D reshape (NCHW → [N*H*W, Cin]) happens on host before kernel launch. The kernel sees only 2D tensors.
