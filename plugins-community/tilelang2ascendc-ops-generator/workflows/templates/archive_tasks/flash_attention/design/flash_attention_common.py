#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------


from dataclasses import dataclass

MAX_CORES = 20
MAX_DIM = 512


@dataclass(frozen=True)
class FlashAttentionConfig:
    batch: int
    heads: int
    q_seq_len: int
    kv_seq_len: int
    dim: int
    dtype: str = "float16"
    causal: bool = False


@dataclass(frozen=True)
class FlashAttentionPlan:
    config: FlashAttentionConfig

    def __post_init__(self):
        if self.config.dim > MAX_DIM:
            raise ValueError(f"head dim {self.config.dim} exceeds MAX_DIM={MAX_DIM}")
        if self.config.causal and self.config.q_seq_len > self.config.kv_seq_len:
            raise ValueError("causal requires q_seq_len <= kv_seq_len")

    @property
    def dim_align(self):
        c0 = 32 // (4 if self.config.dtype == "float32" else 2)
        aligned = ((self.config.dim + c0 - 1) // c0) * c0
        return ((self.config.dim + 127) // 128) * 128 if aligned > 128 else aligned

    @property
    def block_m(self):
        if self.config.dtype == "float32":
            return 64 if self.dim_align <= 128 else 32
        return 128 if self.dim_align <= 128 else 64

    @property
    def block_n(self):
        return 128

    @property
    def cube_k(self):
        return min(self.dim_align, 256)

    @property
    def prelaunch(self):
        return 2

    @property
    def ring_slots(self):
        return self.prelaunch + 1

    @property
    def q_blocks(self):
        return (self.config.q_seq_len + self.block_m - 1) // self.block_m

    @property
    def block_num(self):
        return self.q_blocks * self.config.heads * self.config.batch

    @property
    def used_core_num(self):
        return MAX_CORES

    @property
    def tasks_per_core(self):
        return (self.block_num + self.used_core_num - 1) // self.used_core_num

    @property
    def kv_loops(self):
        return (self.config.kv_seq_len + self.block_n - 1) // self.block_n

    @property
    def d_chunks(self):
        return (self.dim_align + 255) // 256

    @property
    def diff_s(self):
        return self.config.kv_seq_len - self.config.q_seq_len

    @property
    def tail_valid(self):
        return self.config.kv_seq_len % self.block_n

    @property
    def use_brcb(self):
        return self.dim_align <= 128

    @property
    def q_shape(self):
        c = self.config
        return [c.batch, c.heads, c.q_seq_len, c.dim]

    @property
    def kv_shape(self):
        c = self.config
        return [c.batch, c.heads, c.kv_seq_len, c.dim]

    @property
    def score_shape(self):
        return [self.block_num, self.ring_slots, self.block_m, self.block_n]

    @property
    def partial_shape(self):
        return [self.block_num, self.ring_slots, self.block_m, self.dim_align]


@dataclass(frozen=True)
class TaskIndex:
    task_idx: object
    bx: object
    by: object
    bz: object
