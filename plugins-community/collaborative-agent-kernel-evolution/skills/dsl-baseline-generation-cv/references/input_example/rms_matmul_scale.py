# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

import torch
import torch.nn as nn
import torch.nn.functional as F


class Model(nn.Module):
    def __init__(self):
        super(Model, self).__init__()

    def forward(self, x: torch.Tensor, weight: torch.Tensor, norm_eps: float = 1e-6) -> torch.Tensor:
        B, S, N, D = x.shape
        x_rs = x.reshape(B, S, N * D)
        inv_rms = torch.rsqrt(x_rs.square().mean(-1, keepdim=True) + norm_eps)
        return inv_rms * torch.matmul(x_rs, weight)

BATCH, SEQ, NUM_HEADS, HEAD_DIM = 16, 256, 4, 512
TOTAL = 2 * NUM_HEADS + NUM_HEADS * NUM_HEADS


def get_inputs():
    x = torch.rand(BATCH, SEQ, NUM_HEADS, HEAD_DIM).half()
    weight = torch.rand(NUM_HEADS * HEAD_DIM, TOTAL).half()
    return [x, weight]


def get_init_inputs():
    return []  # No special initialization inputs needed
