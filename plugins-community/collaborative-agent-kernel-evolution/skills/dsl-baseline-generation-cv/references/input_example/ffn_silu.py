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

    def forward(self, X: torch.Tensor, W1: torch.Tensor, W2: torch.Tensor) -> torch.Tensor:
        hidden = F.silu(torch.matmul(X, W1))
        return torch.matmul(hidden, W2)


M = 1024
K = 1024
N1 = 2048
N2 = 1024


def get_inputs():
    X = torch.randn(M, K, dtype=torch.float16)
    W1 = torch.randn(K, N1, dtype=torch.float16)
    W2 = torch.randn(N1, N2, dtype=torch.float16)
    return [X, W1, W2]


def get_init_inputs():
    return []
