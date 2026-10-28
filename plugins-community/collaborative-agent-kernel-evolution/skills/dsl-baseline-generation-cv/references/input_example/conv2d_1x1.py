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

    def forward(self, x: torch.Tensor, weight: torch.Tensor) -> torch.Tensor:
        return F.conv2d(x, weight, bias=None, stride=1, padding=0)


N = 2
CIN = 64
H = 16
W = 16
COUT = 128


def get_inputs():
    x = torch.randn(N, CIN, H, W, dtype=torch.float16)
    weight = torch.randn(COUT, CIN, 1, 1, dtype=torch.float16)
    return [x, weight]


def get_init_inputs():
    return []
