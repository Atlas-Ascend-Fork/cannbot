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

"""Device-side memory operations shared by the named profiling kernels."""

import triton
import triton.language as tl


@triton.jit
def write_strided_blocks(
    dst_ptr,
    src_ptr,
    n_elements,
    block_size: tl.constexpr,
    core_num: tl.constexpr,
    copy: tl.constexpr,
):
    """Copy or zero each block once, without launching a separate kernel."""
    pid = tl.program_id(0)
    num_blocks = tl.cdiv(n_elements, block_size)
    for block_idx in range(pid, num_blocks, core_num):
        block_start = block_idx * block_size
        offsets = block_start + tl.arange(0, block_size)
        mask = offsets < n_elements
        if copy:
            data = tl.load(src_ptr + offsets, mask=mask)
        else:
            data = tl.zeros([block_size], dtype=tl.int32)
        tl.store(dst_ptr + offsets, data, mask=mask)
