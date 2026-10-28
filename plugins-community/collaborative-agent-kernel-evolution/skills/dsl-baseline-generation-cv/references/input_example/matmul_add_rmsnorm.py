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

    def forward(self, A: torch.Tensor, B: torch.Tensor, residual: torch.Tensor,
                gamma: torch.Tensor, eps: float = 1e-6) -> tuple:
        mm = torch.matmul(A, B)
        x_add = mm + residual
        # RmsNorm
        rms = torch.sqrt(torch.mean(x_add ** 2, dim=-1, keepdim=True) + eps)
        y = x_add / rms * gamma
        return y, x_add


M = 1024
K = 1024
N = 1024


def get_inputs():
    A = torch.randn(M, K, dtype=torch.float16)
    B = torch.randn(K, N, dtype=torch.float16)
    residual = torch.randn(M, N, dtype=torch.float16)
    gamma = torch.randn(N, dtype=torch.float16)
    return [A, B, residual, gamma]


def get_init_inputs():
    return []
