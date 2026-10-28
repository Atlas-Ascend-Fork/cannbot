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
import torch_npu
import custom_ops_lib


def module_fn(x: torch.Tensor, weight: torch.Tensor, norm_eps: float = 1e-6) -> torch.Tensor:
    return custom_ops_lib.rms_matmul_scale_custom(x, weight, norm_eps)


class ModelNew(nn.Module):
    def __init__(self):
        super(ModelNew, self).__init__()

    def forward(self, x: torch.Tensor, weight: torch.Tensor, norm_eps: float = 1e-6, fn=module_fn) -> torch.Tensor:
        return fn(x, weight, norm_eps)
