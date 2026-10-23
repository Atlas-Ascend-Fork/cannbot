# Convert to Triton

Use a PyTorch-facing wrapper that launches a real Triton Ascend kernel. Keep
shape and allocation work in the wrapper and move arithmetic into `@triton.jit`.
Before writing the kernel, read the staged `triton-npu-op-coding-guide` skill
and follow the category card matching the operator.

```python
import torch
import torch.nn as nn
import triton
import triton.language as tl


@triton.jit
def add_kernel(x_ptr, y_ptr, out_ptr, n_elements, BLOCK_SIZE: tl.constexpr):
    offsets = tl.program_id(0) * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
    mask = offsets < n_elements
    tl.store(out_ptr + offsets, tl.load(x_ptr + offsets, mask=mask) + tl.load(y_ptr + offsets, mask=mask), mask=mask)


def add(x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    out = torch.empty_like(x)
    grid = lambda meta: ((out.numel() + meta["BLOCK_SIZE"] - 1) // meta["BLOCK_SIZE"],)
    add_kernel[grid](x, y, out, out.numel(), BLOCK_SIZE=128)
    return out


class Model(nn.Module):
    def forward(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        return add(x, y)


def get_init_inputs():
    return []


def get_inputs():
    return [torch.randn(2048, device="npu"), torch.randn(2048, device="npu")]
```

The public `Model` API and source-defined input-construction functions are
retained; only the computation moves into the Triton kernel. Validate with
`run-test-convert`.
