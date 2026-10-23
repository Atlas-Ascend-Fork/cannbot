# Category index — routing into the category cards

[fundamentals.md](categories/fundamentals.md) is always read first; its rules
apply to every kernel and category cards do not repeat them. Then route to one
primary category card below — at most one secondary card when the operator
genuinely spans two categories (composition precedence: fundamentals always
apply; the primary card owns category structure; a secondary card contributes
only its scope and pitfalls).

## By operator category

| Card | Read when the operator… |
|---|---|
| [elementwise.md](categories/elementwise.md) | maps each output element from the input element(s) at the same position — arithmetic, activations, math functions, casts, and their backward variants |
| [reduction.md](categories/reduction.md) | merges many elements into fewer along an axis — `dim=` reductions, argmax/argmin, prefix scans (`cumsum`), histogram-style table reductions, split-axis merges |
| [softmax-norm.md](categories/softmax-norm.md) | computes per-row or per-group statistics and then applies them — softmax family, LayerNorm/RMSNorm/GroupNorm, fused norm variants, and their backward |
| [matmul.md](categories/matmul.md) | is a GEMM contraction or a matmul with a fused epilogue — projections, batched/grouped (MoE) GEMMs, transposed-weight linear layers |
| [attention.md](categories/attention.md) | is the fused `softmax(Q·Kᵀ/√d)·V` chain — MHA/SDPA/flash forwards, GQA/MQA, causal/window/softcap masking, prefill/decode variants |
| [sort-select.md](categories/sort-select.md) | reorders or selects by comparison — sort/argsort/topk, selection-with-suppression loops (NMS-style), score-then-select composites |
| [indexing.md](categories/indexing.md) | moves data by an index tensor — gather/index_select/embedding lookups, scatter/index_put writes, embedding backward, token permute, MoE dispatch |
| [interpolate-pad.md](categories/interpolate-pad.md) | changes the shape by resampling, padding, or repetition — interpolate/upsample in every mode, pad in every mode, repeat/repeat_interleave |
| [layout-transform.md](categories/layout-transform.md) | only reorders data without changing values or shape — permute/transpose variants, copy-forcing reshapes, paged/block-table scatter-copies |
| [convolution.md](categories/convolution.md) | is a convolution — standard 1D/2D/3D (grouped), depthwise, transposed, 1×1, and causal depthwise conv1d (SSM-style) |

## By requested PyTorch API

Route the API the source module calls; when an API is not listed, match by
category semantics above.

| PyTorch API | Card |
|---|---|
| `add`, `mul`, `sub`, `div`, `pow`, `neg`, `abs`, `exp`, `log`, `sqrt`, `rsqrt`, `sin`, `cos`, `clamp`, `torch.where` (pointwise) | [elementwise.md](categories/elementwise.md) |
| `relu`, `sigmoid`, `tanh`, `gelu`, `silu`, SwiGLU/GEGLU gated variants, dtype casts | [elementwise.md](categories/elementwise.md) |
| `sum`, `mean`, `prod`, `max`, `min`, `argmax`, `argmin`, `logsumexp`, `var`, `std`, `count_nonzero` | [reduction.md](categories/reduction.md) |
| `cumsum`, `histogram`, `bincount` | [reduction.md](categories/reduction.md) |
| `softmax`, `log_softmax`, `cross_entropy` | [softmax-norm.md](categories/softmax-norm.md) |
| `layer_norm`, `rms_norm` (RMSNorm), `group_norm`, fused norm variants | [softmax-norm.md](categories/softmax-norm.md) |
| `matmul`, `mm`, `bmm`, `addmm`, `einsum`, `nn.Linear` / `F.linear`, grouped/MoE GEMMs | [matmul.md](categories/matmul.md) |
| `scaled_dot_product_attention`, `flash_attn*`, `torch_npu.npu_fusion_attention*`, multi-head/GQA attention modules, RoPE/rotary embeddings | [attention.md](categories/attention.md) |
| `sort`, `argsort`, `topk`, `mssd`/NMS-style ops, `torch_npu.npu_sort_v2` | [sort-select.md](categories/sort-select.md) |
| `index_select`, `gather`, `take`, `Tensor[index]`, `index_put_`, `scatter`, `scatter_add` | [indexing.md](categories/indexing.md) |
| `nn.Embedding` / `embedding`, `embedding_dense_backward`, token permute/unpermute, MoE dispatch (grouped gather/scatter) | [indexing.md](categories/indexing.md) |
| `interpolate` / `upsample` (nearest, bilinear, bicubic, area; `align_corners`), `F.interpolate` | [interpolate-pad.md](categories/interpolate-pad.md) |
| `pad` (constant, reflect, replicate, circular), `F.pad` | [interpolate-pad.md](categories/interpolate-pad.md) |
| `repeat`, `repeat_interleave`, `tile` | [interpolate-pad.md](categories/interpolate-pad.md) |
| `permute`, `transpose` / `.t()`, `.contiguous()`-forcing reshapes, paged KV-cache writes via block tables | [layout-transform.md](categories/layout-transform.md) |
| `conv1d`, `conv2d`, `conv3d` (incl. grouped and depthwise), `conv_transpose1d/2d/3d`, causal conv1d (SSM/Mamba) | [convolution.md](categories/convolution.md) |
