### Conv2d 1x1 — Vector Pass

**Not applicable.** This is a Fixpipe (Cube-only) pattern. Cube outputs fp16 directly to the output tensor via hardware Fixpipe. No Vector scope is needed.

If the operator requires post-conv activation (e.g., conv2d_1x1 + ReLU), switch to the standard Cube→workspace→Vector pattern and use matmul_bias_relu as the reference for the Vector pass.
