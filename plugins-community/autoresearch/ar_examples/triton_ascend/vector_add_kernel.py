# Copyright 2026 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import importlib

import torch
import triton
import triton.language as tl

importlib.import_module("torch_npu")


@triton.jit
def vector_add_kernel(
    x_ptr, y_ptr, out_ptr, n_elements: tl.constexpr, block_size: tl.constexpr
):
    shape = (n_elements,)
    strides = (1,)
    offsets = (tl.program_id(0) * block_size,)
    block_shape = (block_size,)
    order = (0,)
    x_block = tl.make_block_ptr(x_ptr, shape, strides, offsets, block_shape, order)
    y_block = tl.make_block_ptr(y_ptr, shape, strides, offsets, block_shape, order)
    out_block = tl.make_block_ptr(out_ptr, shape, strides, offsets, block_shape, order)

    # Block bounds cover both complete tiles and a partially filled final tile.
    x = tl.load(x_block, boundary_check=(0,))
    y = tl.load(y_block, boundary_check=(0,))
    tl.store(out_block, x + y, boundary_check=(0,))


class ModelNew(torch.nn.Module):
    def forward(self, x, y):
        """Add matching contiguous tensors without modifying either input."""
        out = torch.empty_like(x)
        n_elements = out.numel()
        if n_elements == 0:
            return out

        block_size = min(1024, triton.next_power_of_2(n_elements))
        grid = (triton.cdiv(n_elements, block_size),)
        vector_add_kernel[grid](x, y, out, n_elements, block_size=block_size)
        return out
