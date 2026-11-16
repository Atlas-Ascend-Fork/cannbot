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

import tilelang
from tilelang import language as T
from tilelang.intrinsics import make_zn_layout
from tvm.tir import BufferRegion
from tvm.ir import Range
from tvm.script.ir_builder import IRBuilder

from design.flash_attention_common import (
    MAX_DIM as MAX_DIM,
    FlashAttentionConfig as FlashAttentionConfig,
    FlashAttentionPlan,
    TaskIndex,
)

pass_configs = {
    tilelang.PassConfigKey.TL_ASCEND_MEMORY_PLANNING: True,
    tilelang.PassConfigKey.TL_ASCEND_AUTO_SYNC: False,
}
SIG_S_READY = 0
SIG_P_READY = 1
SIG_O_READY = 2


@dataclass(frozen=True)
class GlobalBuffers:
    q: object
    k: object
    v: object
    output: object
    workspace_s: object
    workspace_p: object
    workspace_o: object
    sm_scale: object


@dataclass(frozen=True)
class CubeBuffers:
    q_l1: object
    k_l1: object
    v_l1: object
    acc_s_l1: object
    lhs_l0: object
    rhs_l0: object
    p_l0: object
    v_l0: object
    acc_s_l0c: object
    acc_o_l0c: object


@dataclass(frozen=True)
class VectorBuffers:
    acc_o: object
    acc_o_ub: object
    acc_o_half: object
    sumexp: object
    m_i: object
    alpha_ring: object
    sumexp_i_ring: object
    acc_s_ub: object
    acc_s_half: object
    m_i_2d: object
    brcb_tmp: object
    mask_col: object
    col_idx: object
    bound_vec: object
    bound_2d: object
    causal_cmp: object


@dataclass(frozen=True)
class LocalBuffers:
    c: object
    v: object


def _alloc(allocator, name, shape, dtype="float"):
    return IRBuilder.name(name, allocator(shape, dtype))


def _allocate_cube(p):
    q_l1 = _alloc(T.alloc_L1, "q_l1", [p.block_m, p.dim_align], p.config.dtype)
    k_l1 = _alloc(T.alloc_L1, "k_l1", [2, p.block_n, p.dim_align], p.config.dtype)
    v_l1 = _alloc(T.alloc_L1, "v_l1", [p.block_n, p.dim_align], p.config.dtype)
    acc_s_l1 = _alloc(T.alloc_L1, "acc_s_l1", [p.block_m, p.block_n], p.config.dtype)
    T.annotate_layout(
        {
            q_l1: make_zn_layout(q_l1),
            k_l1: make_zn_layout(k_l1),
            v_l1: make_zn_layout(v_l1),
            acc_s_l1: make_zn_layout(acc_s_l1),
        }
    )
    lhs_l0 = _alloc(T.alloc_L0A, "lhs_l0", [p.block_m, p.cube_k], p.config.dtype)
    rhs_l0 = _alloc(T.alloc_L0B, "rhs_l0", [p.cube_k, p.block_n], p.config.dtype)
    p_l0 = _alloc(T.alloc_L0A, "p_l0", [p.block_m, p.block_n], p.config.dtype)
    v_l0 = _alloc(T.alloc_L0B, "v_l0", [p.block_n, p.cube_k], p.config.dtype)
    acc_s_l0c = _alloc(T.alloc_L0C, "acc_s_l0c", [p.block_m, p.block_n])
    acc_o_l0c = _alloc(T.alloc_L0C, "acc_o_l0c", [p.block_m, p.cube_k])
    return CubeBuffers(
        q_l1, k_l1, v_l1, acc_s_l1, lhs_l0, rhs_l0, p_l0, v_l0, acc_s_l0c, acc_o_l0c
    )


def _allocate_vector(p):
    acc_o = _alloc(T.alloc_ub, "acc_o", [p.block_m // 2, p.dim_align])
    acc_o_ub = _alloc(T.alloc_ub, "acc_o_ub", [p.block_m // 2, p.dim_align])
    acc_o_half = _alloc(
        T.alloc_ub, "acc_o_half", [p.block_m // 2, p.dim_align], p.config.dtype
    )
    sumexp = _alloc(T.alloc_ub, "sumexp", [p.block_m // 2, 1])
    m_i = _alloc(T.alloc_ub, "m_i", [p.block_m // 2, 1])
    alpha_ring = _alloc(T.alloc_ub, "alpha_ring", [p.ring_slots, p.block_m // 2, 1])
    sumexp_i_ring = _alloc(
        T.alloc_ub, "sumexp_i_ring", [p.ring_slots, p.block_m // 2, 1]
    )
    acc_s_ub = _alloc(T.alloc_ub, "acc_s_ub", [p.block_m // 2, p.block_n])
    acc_s_half = _alloc(
        T.alloc_ub, "acc_s_half", [p.block_m // 2, p.block_n], p.config.dtype
    )
    m_i_2d = _alloc(T.alloc_ub, "m_i_2d", [p.block_m // 2, p.block_n])
    brcb_tmp = _alloc(T.alloc_ub, "brcb_tmp", [p.block_m // 2 * 8 if p.use_brcb else 8])
    mask_col = _alloc(T.alloc_ub, "mask_col", [p.block_n])
    col_idx = _alloc(T.alloc_ub, "col_idx", [p.block_n])
    bound_vec = _alloc(T.alloc_ub, "bound_vec", [p.block_m // 2])
    bound_2d = _alloc(T.alloc_ub, "bound_2d", [p.block_m // 2, p.block_n])
    causal_cmp = _alloc(T.alloc_ub, "causal_cmp", [p.block_m // 2, p.block_n], "uint8")
    return VectorBuffers(
        acc_o,
        acc_o_ub,
        acc_o_half,
        sumexp,
        m_i,
        alpha_ring,
        sumexp_i_ring,
        acc_s_ub,
        acc_s_half,
        m_i_2d,
        brcb_tmp,
        mask_col,
        col_idx,
        bound_vec,
        bound_2d,
        causal_cmp,
    )


@T.macro(hygienic=False)
def cube_begin_task(p, b, gm, task):
    slice_lower_0 = task.bx * p.block_m
    slice_upper_1 = (task.bx + 1) * p.block_m
    slice_upper_2 = p.config.dim
    T.copy(
        gm.q[task.bz, task.by, slice_lower_0:slice_upper_1, 0:slice_upper_2], b.c.q_l1
    )
    T.set_flag("mte1", "mte2", 0)
    T.set_flag("mte1", "mte2", 1)
    T.wait_flag("mte1", "mte2", 0)
    slice_upper_0 = p.block_n
    slice_upper_1 = p.config.dim
    T.copy(gm.k[task.bz, task.by, 0:slice_upper_0, 0:slice_upper_1], b.c.k_l1[0, :, :])
    T.set_flag("mte2", "mte1", 0)


@T.macro(hygienic=False)
def vec_begin_task(b):
    T.tile.fill(b.v.acc_o[0, :], 0.0)
    T.tile.fill(b.v.sumexp[0, :], 0.0)
    T.tile.fill(b.v.m_i, -(2**30))


@T.macro(hygienic=False)
def cube_qk(p, b, gm, task, t, slot_prod):
    if t + 1 < p.kv_loops:
        T.wait_flag("mte1", "mte2", (t + 1) % 2)
        slice_lower_0 = (t + 1) * p.block_n
        slice_upper_1 = (t + 2) * p.block_n
        slice_upper_2 = p.config.dim
        T.copy(
            gm.k[task.bz, task.by, slice_lower_0:slice_upper_1, 0:slice_upper_2],
            b.c.k_l1[(t + 1) % 2, :, :],
        )
        T.set_flag("mte2", "mte1", (t + 1) % 2)
    T.wait_flag("mte2", "mte1", t % 2)
    for cc in T.serial(p.d_chunks):
        T.set_flag("m", "mte1", 1)
        T.wait_flag("m", "mte1", 1)
        T.copy(b.c.q_l1[0, cc * p.cube_k], b.c.lhs_l0)
        T.copy(b.c.k_l1[t % 2, 0, cc * p.cube_k], b.c.rhs_l0, transpose=True)
        T.set_flag("mte1", "m", 0)
        T.wait_flag("mte1", "m", 0)
        T.set_flag("fix", "m", 1)
        T.wait_flag("fix", "m", 1)
        T.mma(b.c.lhs_l0, b.c.rhs_l0, b.c.acc_s_l0c, init=cc == 0)
    T.set_flag("m", "fix", 0)
    T.wait_flag("m", "fix", 0)
    T.copy(b.c.acc_s_l0c, gm.workspace_s[task.task_idx, slot_prod, :, :])
    T.set_flag("mte1", "mte2", t % 2)
    T.set_flag("m", "mte1", 3)
    T.set_flag("fix", "m", 3)
    T.set_cross_flag("FIX", SIG_S_READY)


@T.macro(hygienic=False)
def vec_apply_mask(p, b, task, vid, t):
    h_start = vid * (p.block_m // 2)
    if p.tail_valid != 0:
        if t == p.kv_loops - 1:
            T.tile.fill(b.v.mask_col, T.float32(-(2**30)))
            T.tile.fill(
                BufferRegion(b.v.mask_col, [Range(0, p.tail_valid)]), T.float32(0.0)
            )
            for h_i in range(p.block_m // 2):
                T.tile.add(b.v.acc_s_ub[h_i, :], b.v.acc_s_ub[h_i, :], b.v.mask_col)
    if p.config.causal:
        if (t + 1) * p.block_n - 1 > task.bx * p.block_m + p.diff_s:
            T.tile.createvecindex(b.v.col_idx, T.cast(t * p.block_n, "float32"))
            T.tile.createvecindex(
                b.v.bound_vec,
                T.cast(task.bx * p.block_m + h_start + p.diff_s, "float32"),
            )
            T.tile.broadcast(b.v.m_i_2d, b.v.col_idx, axis=0)
            T.tile.broadcast(b.v.bound_2d, b.v.bound_vec, axis=1)
            T.tile.compare(b.v.causal_cmp, b.v.m_i_2d, b.v.bound_2d, "LE")
            T.tile.select(
                b.v.acc_s_ub,
                b.v.causal_cmp,
                b.v.acc_s_ub,
                T.float32(-(2**30)),
                "VSEL_TENSOR_SCALAR_MODE",
            )


@T.macro(hygienic=False)
def vec_softmax(p, b, gm, task, vid, t, slot_prod):
    T.wait_cross_flag(SIG_S_READY)
    h_start = vid * (p.block_m // 2)
    T.set_flag("v", "mte2", 1)
    T.wait_flag("v", "mte2", 1)
    T.copy(b.v.m_i, b.v.alpha_ring[slot_prod, :, :])
    slice_upper_0 = h_start + p.block_m // 2
    T.copy(
        gm.workspace_s[task.task_idx, slot_prod, h_start:slice_upper_0, :], b.v.acc_s_ub
    )
    T.set_flag("mte2", "v", 0)
    T.wait_flag("mte2", "v", 0)
    T.tile.mul(b.v.acc_s_ub, b.v.acc_s_ub, gm.sm_scale)
    vec_apply_mask(p, b, task, vid, t)
    T.reduce_max(b.v.acc_s_ub, b.v.m_i, dim=-1)
    T.tile.max(b.v.m_i, b.v.m_i, b.v.alpha_ring[slot_prod, :, :])
    T.tile.sub(
        b.v.alpha_ring[slot_prod, :, :], b.v.alpha_ring[slot_prod, :, :], b.v.m_i
    )
    T.tile.exp(b.v.alpha_ring[slot_prod, :, :], b.v.alpha_ring[slot_prod, :, :])
    if p.use_brcb:
        T.tile.row_expand_sub_experiment(
            BufferRegion(b.v.acc_s_ub, [Range(0, p.block_m // 2), Range(0, 64)]),
            BufferRegion(b.v.acc_s_ub, [Range(0, p.block_m // 2), Range(0, 64)]),
            b.v.m_i,
            b.v.brcb_tmp,
        )
        T.tile.row_expand_sub_experiment(
            BufferRegion(b.v.acc_s_ub, [Range(0, p.block_m // 2), Range(64, 128)]),
            BufferRegion(b.v.acc_s_ub, [Range(0, p.block_m // 2), Range(64, 128)]),
            b.v.m_i,
            b.v.brcb_tmp,
        )
    else:
        T.tile.broadcast(b.v.m_i_2d, b.v.m_i)
        T.tile.sub(b.v.acc_s_ub, b.v.acc_s_ub, b.v.m_i_2d)
    T.tile.exp(b.v.acc_s_ub, b.v.acc_s_ub)
    T.reduce_sum(b.v.acc_s_ub, b.v.sumexp_i_ring[slot_prod, :, :], dim=-1)
    T.set_flag("mte3", "v", 1)
    T.wait_flag("mte3", "v", 1)
    T.copy(b.v.acc_s_ub, b.v.acc_s_half)
    T.set_flag("v", "mte3", 0)
    T.wait_flag("v", "mte3", 0)
    slice_upper_0 = h_start + p.block_m // 2
    T.copy(
        b.v.acc_s_half,
        gm.workspace_p[task.task_idx, slot_prod, h_start:slice_upper_0, :],
    )
    T.set_cross_flag("MTE3", SIG_P_READY)


@T.macro(hygienic=False)
def cube_pv(p, b, gm, task, now_k, slot_cons):
    T.wait_cross_flag(SIG_P_READY)
    T.set_flag("mte1", "mte2", 3)
    T.wait_flag("mte1", "mte2", 3)
    T.copy(gm.workspace_p[task.task_idx, slot_cons, :, :], b.c.acc_s_l1)
    slice_lower_0 = now_k * p.block_n
    slice_upper_1 = (now_k + 1) * p.block_n
    slice_upper_2 = p.config.dim
    T.copy(
        gm.v[task.bz, task.by, slice_lower_0:slice_upper_1, 0:slice_upper_2], b.c.v_l1
    )
    T.set_flag("mte2", "mte1", 2)
    T.wait_flag("mte2", "mte1", 2)
    T.set_flag("m", "mte1", 1)
    T.wait_flag("m", "mte1", 1)
    T.copy(b.c.acc_s_l1, b.c.p_l0)
    for cc in T.serial(p.d_chunks):
        T.set_flag("m", "mte1", 1)
        T.wait_flag("m", "mte1", 1)
        T.copy(b.c.v_l1[0, cc * p.cube_k], b.c.v_l0)
        T.set_flag("mte1", "m", 0)
        T.wait_flag("mte1", "m", 0)
        T.set_flag("fix", "m", 1)
        T.wait_flag("fix", "m", 1)
        T.mma(b.c.p_l0, b.c.v_l0, b.c.acc_o_l0c, init=True)
        T.set_flag("m", "fix", 0)
        T.wait_flag("m", "fix", 0)
        slice_lower_0 = cc * p.cube_k
        slice_upper_1 = (cc + 1) * p.cube_k
        T.copy(
            b.c.acc_o_l0c,
            gm.workspace_o[task.task_idx, slot_cons, :, slice_lower_0:slice_upper_1],
        )
    T.set_flag("m", "mte1", 5)
    T.set_flag("fix", "m", 4)
    T.set_flag("mte1", "mte2", 4)
    T.set_cross_flag("FIX", SIG_O_READY)


@T.macro(hygienic=False)
def vec_merge_output(p, b, gm, task, vid, now_k, slot_cons):
    T.wait_cross_flag(SIG_O_READY)
    h_start = vid * (p.block_m // 2)
    T.set_flag("v", "mte2", 1)
    T.wait_flag("v", "mte2", 1)
    slice_upper_0 = h_start + p.block_m // 2
    T.copy(
        gm.workspace_o[task.task_idx, slot_cons, h_start:slice_upper_0, :], b.v.acc_o_ub
    )
    T.set_flag("mte2", "v", 0)
    T.wait_flag("mte2", "v", 0)
    if now_k == 0:
        T.copy(b.v.acc_o_ub, b.v.acc_o)
        T.copy(b.v.sumexp_i_ring[slot_cons, :, :], b.v.sumexp)
    elif p.dim_align == 128:
        T.tile.broadcast(b.v.m_i_2d, b.v.alpha_ring[slot_cons, :, :])
        T.tile.mul(b.v.acc_o, b.v.acc_o, b.v.m_i_2d)
        T.tile.add(b.v.acc_o, b.v.acc_o, b.v.acc_o_ub)
        T.tile.mul(b.v.sumexp, b.v.sumexp, b.v.alpha_ring[slot_cons, :, :])
        T.tile.add(b.v.sumexp, b.v.sumexp, b.v.sumexp_i_ring[slot_cons, :, :])
    else:
        for h_i in range(p.block_m // 2):
            T.tile.mul(
                b.v.acc_o[h_i, :], b.v.acc_o[h_i, :], b.v.alpha_ring[slot_cons, h_i, 0]
            )
        T.tile.add(b.v.acc_o, b.v.acc_o, b.v.acc_o_ub)
        T.tile.mul(b.v.sumexp, b.v.sumexp, b.v.alpha_ring[slot_cons, :, :])
        T.tile.add(b.v.sumexp, b.v.sumexp, b.v.sumexp_i_ring[slot_cons, :, :])


@T.macro(hygienic=False)
def cube_drain_step(p, t):
    if t < p.kv_loops:
        T.wait_flag("m", "mte1", 3)
        T.wait_flag("fix", "m", 3)
    if p.prelaunch <= t:
        now_k = t - p.prelaunch
        if now_k < p.kv_loops:
            T.wait_flag("m", "mte1", 5)
            T.wait_flag("fix", "m", 4)
            T.wait_flag("mte1", "mte2", 4)


@T.macro(hygienic=False)
def cube_finish_task():
    T.wait_flag("mte1", "mte2", 0)
    T.wait_flag("mte1", "mte2", 1)


@T.macro(hygienic=False)
def vec_store_output(p, b, gm, task, vid):
    for h_i in range(p.block_m // 2):
        T.tile.div(b.v.acc_o[h_i, :], b.v.acc_o[h_i, :], b.v.sumexp[h_i, 0])
    T.copy(b.v.acc_o, b.v.acc_o_half)
    T.set_flag("v", "mte3", 0)
    T.wait_flag("v", "mte3", 0)
    row_start = task.bx * p.block_m + vid * (p.block_m // 2)
    slice_upper_0 = p.config.dim
    slice_upper_1 = row_start + p.block_m // 2
    slice_upper_2 = p.config.dim
    T.copy(
        b.v.acc_o_half[:, 0:slice_upper_0],
        gm.output[task.bz, task.by, row_start:slice_upper_1, 0:slice_upper_2],
    )


@T.macro(hygienic=False)
def produce(p, b, gm, task, vid, t):
    slot_prod = t % p.ring_slots
    with T.Scope("C"):
        cube_qk(p, b, gm, task, t, slot_prod)
    with T.Scope("V"):
        vec_softmax(p, b, gm, task, vid, t, slot_prod)


@T.macro(hygienic=False)
def consume(p, b, gm, task, vid, t):
    now_k = t - p.prelaunch
    slot_cons = now_k % p.ring_slots
    with T.Scope("C"):
        cube_pv(p, b, gm, task, now_k, slot_cons)
    with T.Scope("V"):
        vec_merge_output(p, b, gm, task, vid, now_k, slot_cons)


@T.macro(hygienic=False)
def pipeline(p, b, gm, task, vid):
    for t in T.serial(p.kv_loops + p.prelaunch):
        if t < p.kv_loops:
            produce(p, b, gm, task, vid, t)
        if t >= p.prelaunch:
            consume(p, b, gm, task, vid, t)
        with T.Scope("C"):
            cube_drain_step(p, t)


@T.macro(hygienic=False)
def run_task(p, b, gm, task, vid):
    with T.Scope("C"):
        cube_begin_task(p, b, gm, task)
    with T.Scope("V"):
        vec_begin_task(b)
    pipeline(p, b, gm, task, vid)
    with T.Scope("C"):
        cube_finish_task()
    with T.Scope("V"):
        vec_store_output(p, b, gm, task, vid)


@T.macro(hygienic=False)
def run_tasks(p, b, gm, cid, vid):
    for local_idx in T.serial(p.tasks_per_core):
        task_idx = cid * p.tasks_per_core + local_idx
        if task_idx < p.block_num:
            run_task(
                p,
                b,
                gm,
                TaskIndex(
                    task_idx,
                    task_idx % p.q_blocks,
                    task_idx // p.q_blocks % p.config.heads,
                    task_idx // p.q_blocks // p.config.heads % p.config.batch,
                ),
                vid,
            )


@tilelang.jit(
    out_idx=[3], workspace_idx=[4, 5, 6], pass_configs=pass_configs, target="ascendc"
)
def flash_attention_fwd(cfg: FlashAttentionConfig):
    p = FlashAttentionPlan(cfg)

    @T.prim_func
    def main(
        q: T.Tensor(p.q_shape, p.config.dtype),
        k: T.Tensor(p.kv_shape, p.config.dtype),
        v: T.Tensor(p.kv_shape, p.config.dtype),
        output: T.Tensor(p.q_shape, p.config.dtype),
        workspace_s: T.Tensor(p.score_shape, "float"),
        workspace_p: T.Tensor(p.score_shape, p.config.dtype),
        workspace_o: T.Tensor(p.partial_shape, "float"),
        sm_scale: T.float32,
    ):
        with T.Kernel(p.used_core_num, is_npu=True) as (cid, vid):
            run_tasks(
                p,
                LocalBuffers(_allocate_cube(p), _allocate_vector(p)),
                GlobalBuffers(
                    q, k, v, output, workspace_s, workspace_p, workspace_o, sm_scale
                ),
                cid,
                vid,
            )

    return main
