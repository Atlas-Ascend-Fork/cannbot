# dsl-baseline-generation-cv 参考示例

本目录收录 Cube+Vector（CV）融合算子的 AscendDSL baseline 样例，供本 skill 由
functional PyTorch 生成含 `tl.scope('cube')` / `tl.scope('vector')` 结构的 DSL 时对照。

目录构成：

- `ascend_dsl_cv.py` — CV DSL 知识库（常量 `ASCEND_DSL_CV_KNOWLEDGE`），按章节组织
  多 scope 布局、workspace 分段、跨核事件、激活与 RoPE 等实现模式
- `input_example/<op>.py` — 输入侧：算子的 functional PyTorch 实现
- `output_example/<op>.py` — 输出侧：对应的 CV DSL baseline

已收录算子：`matmul_add`、`matmul_gelu`、`matmul_swiglu`、`matmul_bias_relu`、
`matmul_add_rmsnorm`、`rms_matmul_scale`、`ffn_silu`、`conv2d_1x1`、`conv2d_bias`、
`flash_attn_basic`。
