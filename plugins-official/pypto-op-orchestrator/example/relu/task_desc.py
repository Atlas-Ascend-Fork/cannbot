#!/usr/bin/env python3
# coding: utf-8
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: CANN-2.0
"""ReLU 参考用例：PyTorch 参考实现 + 输入生成（两段式调用约定）。"""

import torch
import torch.nn as nn

FORMULA = "out[b, d] = max(x[b, d], 0)"
DYNAMIC_AXIS = ["B"]

A2_PERF_BASELINE = 2.85  # us (Ascend 910B3, torch_npu.profiler, warmup=3, runs=5)


class Model(nn.Module):
    """
    Simple model that performs a ReLU activation.
    """

    def __init__(self):
        super(Model, self).__init__()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Applies ReLU activation to the input tensor.

        Args:
            x (torch.Tensor): Input tensor of any shape.

        Returns:
            torch.Tensor: Output tensor with ReLU applied, same shape as input.
        """
        return torch.relu(x)


def get_inputs():
    batch_size = 16
    dim = 16384
    x = torch.randn(batch_size, dim)
    return [x]


def get_init_inputs():
    return []  # No special initialization inputs needed
