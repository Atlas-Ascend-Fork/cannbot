#!/usr/bin/env python3
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


# 每组参数依次描述批次、头数、Q/KV 序列长度、头维度和数据类型。
CASE_SPECS = (
    (1, 32, 256, 256, 128, "float16"),
    (1, 16, 512, 512, 64, "float16"),
    (1, 16, 512, 512, 64, "float32"),
    (1, 32, 512, 512, 128, "float16"),
    (1, 12, 1024, 1024, 64, "float16"),
    (2, 16, 1024, 1024, 128, "float16"),
    (1, 24, 1024, 1024, 80, "float16"),
    (1, 71, 1024, 1024, 64, "float16"),
    (1, 16, 2048, 2048, 128, "bfloat16"),
    (2, 16, 1024, 1024, 128, "float32"),
    (3, 10, 1208, 1208, 64, "float32"),
    (1, 16, 2048, 2048, 192, "bfloat16"),
    (1, 32, 2048, 2048, 64, "float16"),
    (3, 10, 1536, 1536, 64, "float32"),
    (1, 32, 2048, 2048, 128, "bfloat16"),
    (3, 10, 1432, 1432, 64, "float32"),
    (1, 16, 2048, 2048, 256, "float16"),
    (4, 16, 1536, 1536, 128, "bfloat16"),
    (1, 32, 2048, 2048, 96, "bfloat16"),
    (1, 32, 2048, 2048, 80, "float16"),
    (2, 8, 2048, 2048, 128, "float32"),
    (1, 48, 2048, 2048, 64, "float16"),
    (2, 16, 1536, 1536, 128, "float32"),
    (6, 8, 2048, 2048, 128, "float16"),
    (1, 16, 3584, 3584, 128, "float16"),
    (1, 16, 2560, 2560, 128, "float32"),
    (32, 8, 1024, 1024, 64, "bfloat16"),
    (1, 64, 2048, 2048, 64, "float16"),
    (8, 32, 1024, 1024, 128, "bfloat16"),
    (16, 16, 1024, 1024, 128, "bfloat16"),
    (2, 32, 2048, 2048, 128, "float16"),
    (1, 16, 4096, 4096, 128, "float16"),
    (1, 16, 4096, 4096, 128, "bfloat16"),
    (32, 32, 512, 512, 128, "float16"),
    (1, 32, 3072, 3072, 128, "bfloat16"),
    (1, 24, 4096, 4096, 128, "bfloat16"),
    (1, 16, 4096, 4096, 128, "float32"),
    (1, 32, 4096, 4096, 128, "bfloat16"),
    (1, 32, 4096, 4096, 128, "float16"),
    (1, 32, 4096, 4096, 96, "bfloat16"),
    (1, 40, 4096, 4096, 128, "bfloat16"),
    (1, 56, 4096, 4096, 128, "bfloat16"),
    (2, 32, 4096, 4096, 128, "float16"),
    (1, 16, 8192, 8192, 128, "float16"),
    (1, 24, 8192, 8192, 128, "bfloat16"),
    (1, 28, 8192, 8192, 128, "bfloat16"),
    (1, 8, 16384, 16384, 64, "float16"),
    (1, 32, 8192, 8192, 128, "bfloat16"),
    (1, 32, 8192, 8192, 128, "float16"),
    (1, 64, 8192, 8192, 128, "bfloat16"),
)


class Model(nn.Module):
    def __init__(self) -> None:
        super().__init__()

    def forward(
        self, q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, is_causal: bool = False
    ):
        acc = torch.einsum("bhsd,bhkd->bhsk", q, k) * (1.0 / q.shape[-1]) ** 0.5
        if is_causal:
            # 右下对齐 causal（GQA golden 同语义）：行 i 可见列 j <= i + diff
            s_q, s_kv = q.shape[2], k.shape[2]
            diff = s_kv - s_q
            i = torch.arange(s_q, device=acc.device).view(s_q, 1)
            j = torch.arange(s_kv, device=acc.device).view(1, s_kv)
            acc = acc.masked_fill(j > (i + diff), float("-inf"))
        acc = acc.softmax(dim=-1)
        o = torch.einsum("bhsk,bhkd->bhsd", acc, v)
        return o


def _case_inputs(spec):
    batch, heads, q_len, kv_len, dim, dtype_name = spec
    dtype = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }[dtype_name]
    q = torch.rand(batch, heads, q_len, dim, dtype=dtype)
    k = torch.rand(batch, heads, kv_len, dim, dtype=dtype)
    v = torch.rand(batch, heads, kv_len, dim, dtype=dtype)
    return [q, k, v]


def get_input_groups():
    return [_case_inputs(spec) for spec in CASE_SPECS]


def get_init_inputs():
    return []
