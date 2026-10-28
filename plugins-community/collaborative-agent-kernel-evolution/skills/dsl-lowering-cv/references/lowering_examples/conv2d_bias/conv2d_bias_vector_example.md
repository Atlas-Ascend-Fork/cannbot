### Conv2d Bias — Vector Pass

**Not applicable.** ConvBias is a Cube-only pattern. Bias is fused into the Cube pipeline via the BT buffer in BlockConv. Output goes directly to GM via Fixpipe.

### When Vector Scope IS Needed

If the operator requires post-conv activation beyond bias (e.g., Conv2d + Bias + ReLU), the pattern changes to Cube + Vector:

1. **Cube scope**: Use `BlockConv` but write to **workspace** (fp32) instead of output. Add `CrossCoreSetFlag` after conv.
2. **Vector scope**: `CrossCoreWaitFlag`, then load workspace tile, apply activation (e.g., `tl.vclamp_min` for ReLU), cast fp32→fp16, store to output.

This follows the same Cube→workspace→Vector pattern as `matmul_bias_relu`. The key difference is that the Cube pass uses `BlockConv` instead of `BlockMmad`.

For the activation-fused case, use `matmul_bias_relu_vector_example.md` as the Vector pass reference — the Vector logic is identical regardless of whether Cube did a matmul or a conv.
