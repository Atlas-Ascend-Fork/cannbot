#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------


"""Block-level schedule; buffer declarations are abbreviated by an opaque handle."""

from tilelang import language as T
from design.flash_attention_common import (
    FlashAttentionConfig as FlashAttentionConfig,
    FlashAttentionPlan,
)


@T.macro(hygienic=False)
def cube_begin_task(buffers, step):
    # 加载 Q，初始化 K 双槽信用并预取首个 K tile。
    pass


@T.macro(hygienic=False)
def vec_begin_task(buffers, step):
    # 初始化在线 softmax 和输出累加状态，保持 buffer 活性。
    pass


@T.macro(hygienic=False)
def cube_qk(buffers, step):
    # 预取下一个 K tile，计算 QK，写 S workspace 并发出 S_READY。
    pass


@T.macro(hygienic=False)
def vec_softmax(buffers, step):
    # 等待 S_READY，完成缩放、mask 和在线 softmax，写 P 并发出 P_READY。
    pass


@T.macro(hygienic=False)
def cube_pv(buffers, step):
    # 等待 P_READY，加载 P/V 并计算 PV，写 O workspace 并发出 O_READY。
    pass


@T.macro(hygienic=False)
def vec_merge_output(buffers, step):
    # 等待 O_READY，合并当前环槽的输出。
    pass


@T.macro(hygienic=False)
def cube_drain_step(buffers, step):
    # 配对回收本轮 QK/PV 的跨迭代同步标记。
    pass


@T.macro(hygienic=False)
def cube_finish_task(buffers, step):
    # 清空 K 双槽剩余信用，完成当前 task 的同步收尾。
    pass


@T.macro(hygienic=False)
def vec_store_output(buffers, step):
    # 归一化输出累加结果，转换 dtype 并写回有效行列。
    pass


@T.macro(hygienic=False)
def produce(buffers, t):
    with T.Scope("C"):
        cube_qk(buffers, t)
    with T.Scope("V"):
        vec_softmax(buffers, t)


@T.macro(hygienic=False)
def consume(buffers, t):
    with T.Scope("C"):
        cube_pv(buffers, t)
    with T.Scope("V"):
        vec_merge_output(buffers, t)


@T.macro(hygienic=False)
def pipeline(p, buffers):
    for t in T.serial(p.kv_loops + p.prelaunch):
        if t < p.kv_loops:
            produce(buffers, t)
        if t >= p.prelaunch:
            consume(buffers, t)
        with T.Scope("C"):
            cube_drain_step(buffers, t)


@T.macro(hygienic=False)
def run_task(p, buffers, task_idx):
    with T.Scope("C"):
        cube_begin_task(buffers, task_idx)
    with T.Scope("V"):
        vec_begin_task(buffers, task_idx)
    pipeline(p, buffers)
    with T.Scope("C"):
        cube_finish_task(buffers, task_idx)
    with T.Scope("V"):
        vec_store_output(buffers, task_idx)


@T.macro(hygienic=False)
def run_tasks(p, buffers, cid):
    for local_idx in T.serial(p.tasks_per_core):
        task_idx = cid * p.tasks_per_core + local_idx
        if task_idx < p.block_num:
            run_task(p, buffers, task_idx)


def flash_attention_fwd(cfg: FlashAttentionConfig):
    p = FlashAttentionPlan(cfg)

    @T.prim_func
    def main(
        q: T.Tensor(p.q_shape, p.config.dtype),
        k: T.Tensor(p.kv_shape, p.config.dtype),
        v: T.Tensor(p.kv_shape, p.config.dtype),
        output: T.Tensor(p.q_shape, p.config.dtype),
        buffers: T.handle,
    ):
        with T.Kernel(p.used_core_num, is_npu=True) as (cid, vid):
            run_tasks(p, buffers, cid)

    return main
