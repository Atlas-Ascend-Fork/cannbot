### Key Differences from Standard MatMul Entry

- **7 GM_ADDR parameters**: a, b, scale, per_token_scale, y, workspace, tiling
- **KernelVector receives extra inputs**: scale and per_token_scale in addition to workspace and y
- **KernelCube writes to workspace**: Not to the output tensor y

### Example Output (kernel entry)
```cpp
extern "C" __global__ __aicore__
void quant_matmul_custom(GM_ADDR a, GM_ADDR b, GM_ADDR scale,
                         GM_ADDR per_token_scale, GM_ADDR y,
                         GM_ADDR workspace, GM_ADDR tiling) {
    GET_TILING_DATA(t, tiling);
    if ASCEND_IS_AIC {
        KernelCube opCube;
        opCube.Init(a, b, workspace, t.M, t.N, t.K);
        opCube.Process();
    } else if ASCEND_IS_AIV {
        KernelVector opVector;
        opVector.Init(workspace, scale, per_token_scale, y, t.M, t.N, t.K);
        opVector.Process();
    }
}
```

### Entry Pass Rules (Quant MatMul Specific)

1. **Parameter order**: inputs (a, b, scale, per_token_scale) → output (y) → workspace → tiling
2. **KernelCube.Init**: receives input tensors (a, b) + workspace + dimension scalars. Does NOT receive scale/per_token_scale (these are only used in dequant).
3. **KernelVector.Init**: receives workspace (int32 matmul result) + scale + per_token_scale + output y + dimension scalars. Does NOT receive a or b.
4. **Workspace flow**: Cube writes int32 matmul results → workspace → Vector reads and dequantizes to fp16 output.
5. **K passed to both**: Both Cube and Vector need K — Cube uses it for matmul, Vector uses it for scheduler initialization.
