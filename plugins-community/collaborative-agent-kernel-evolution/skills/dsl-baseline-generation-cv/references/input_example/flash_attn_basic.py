# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


class Model(nn.Module):
    def __init__(self):
        super(Model, self).__init__()

    def forward(self, Q: torch.Tensor, K: torch.Tensor, V: torch.Tensor) -> torch.Tensor:
        # Standard scaled dot-product attention
        # Q: (M, D), K: (N, D), V: (N, D), output: (M, D)
        scale = 1.0 / math.sqrt(Q.shape[-1])
        scores = torch.matmul(Q, K.transpose(-2, -1)) * scale  # (M, N)
        probs = F.softmax(scores, dim=-1)  # (M, N)
        return torch.matmul(probs, V)  # (M, D)


M = 1024
N = 1024
D = 128


def get_inputs():
    Q = torch.randn(M, D, dtype=torch.float16)
    K = torch.randn(N, D, dtype=torch.float16)
    V = torch.randn(N, D, dtype=torch.float16)
    return [Q, K, V]


def get_init_inputs():
    return []
