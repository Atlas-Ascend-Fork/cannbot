# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
from builtins import range as py_range
import math

import torch

from easyasc.a2 import *

TILE_M = 128
TILE_N = 128
TILE_K = 128
HALF_M = TILE_M // 2
HALF_N = TILE_N // 2
QUAT_M = HALF_M // 4
SUBS_M = 32
EPS = 1.0e-10
NEG_LARGE = -1.0e30


@func()
def build_suffix_invalid_mask(valid_cols: Var, out_mask: Var):
    signed_mask = Var(-1, DT.int64)
    two_i64 = Var(2, DT.int64)
    for _ in range(0, valid_cols):
        signed_mask <<= signed_mask * two_i64
    out_mask <<= signed_mask


@func()
def zero_half_suffix_invalid(buf: Tensor, valid_cols: Var):
    if valid_cols == 0:
        dup(buf, 0.0)
    elif valid_cols < HALF_N:
        suffix_mask = Var(0, DT.uint64)
        build_suffix_invalid_mask(valid_cols, suffix_mask)
        set_mask(0, suffix_mask)
        dup(buf, 0.0)
        reset_mask()


@func()
def apply_prob_tail_mask(prob_buf: Tensor, valid_n: Var):
    left_valid = Min(valid_n, HALF_N)
    right_valid = Max(valid_n - HALF_N, 0)
    zero_half_suffix_invalid(prob_buf[:, 0:HALF_N], left_valid)
    zero_half_suffix_invalid(prob_buf[:, HALF_N:TILE_N], right_valid)


@func()
def apply_prob_row_tail_mask(prob_buf: Tensor, valid_rows: Var):
    if valid_rows == 0:
        dup(prob_buf, 0.0)
    elif valid_rows < HALF_M:
        dup(prob_buf[valid_rows:HALF_M, 0:TILE_N], 0.0)


@func()
def init_tile_col_indices(col_idx: Tensor):
    packed_value = Var(0, DT.int64)
    packed_view = col_idx.reinterpret(DT.int64)
    for chunk in py_range(TILE_N // 2):
        base = chunk * 2
        packed_value <<= (
            base
            | ((base + 1) << 32)
        )
        packed_value >>= packed_view[0:1, chunk:chunk + 1]


@func()
def build_diagonal_tile_causal_mask(causal_mask: Tensor, col_idx: Tensor, row_begin: Var, valid_rows: Var):
    dup(causal_mask.reinterpret(DT.int), 0)
    for row in range(0, valid_rows):
        valid_cols = Var(row_begin + row + 1)
        if valid_cols > 0:
            compare_scalar(
                causal_mask[row:row + 1, 0:TILE_N // 8], col_idx, valid_cols, CompareMode.LT,
            )


@func()
def apply_diagonal_tile_causal_select(prob_buf: Tensor, causal_mask: Tensor, zero_buf: Tensor):
    select(prob_buf, causal_mask, prob_buf, zero_buf, SelectMode.TENSOR_SCALAR)


@kernel()
def attn_backward_dense_total_tail_causal_kernel(
    q: GMTensor, k: GMTensor, v: GMTensor, o: GMTensor, grad: GMTensor, qkmax: GMTensor, qksum: GMTensor,
    gq: GMTensor, gk: GMTensor, gv: GMTensor,
    S1: Var, S2: Var, D: Var, BH: Var, Q_ROWS: Var, KV_ROWS: Var, scale: Var,
):
    # Tail-safe causal dense attention backward on a2:
    # qk = q.float() @ k.float().t()
    # dp = grad.float() @ v.float().t()
    # p = causal_mask(exp(qk * scale - qkmax) / qksum)
    # dqk = p * (dp - sum(o.float() * grad.float(), dim=-1)) * scale
    # gv += p_half.float().transpose(-1, -2) @ grad.float()
    # gk += dqk_half.float().transpose(-1, -2) @ q.float()
    # gq += dqk_half.float() @ k.float()
    #
    # Important conventions captured in this version:
    # - full-future `N` tiles are skipped with `active_tiles_n`
    # - diagonal causal masking uses packed `uint8` masks plus one full-tile `select`
    # - full `128x128` diagonal tiles reuse a static packed mask built once per subblock
    # - tail `M` tiles rebuild the packed mask dynamically because `half_rows` shifts `row_begin`
    # - the stage-1 vec hot path uses QUAT_M-sized DBuff chunks so `qk/dp/p/dqk`
    #   keep stable slot lineage without introducing probability quantization
    # - stage-3 uses tile-level `atomic_add()` writeback, so outputs must be zero-initialized
    qk_ws = split_workspace(DT.float, [GetCubeNum(), 2, TILE_M, TILE_N], name="qk_ws")
    dp_ws = split_workspace(DT.float, [GetCubeNum(), 2, TILE_M, TILE_N], name="dp_ws")
    p_ws = split_workspace(DT.half, [GetCubeNum(), 2, TILE_M, TILE_N], name="p_ws")
    dqk_ws = split_workspace(DT.half, [GetCubeNum(), 2, TILE_M, TILE_N], name="dqk_ws")

    l1q = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1g = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1k = TBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l1v = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l1p = DBuff(DT.half, [TILE_M, TILE_N], Position.L1)
    l1dqk = DBuff(DT.half, [TILE_M, TILE_N], Position.L1)
    l0c = DBuff(DT.float, [TILE_M, TILE_N], Position.L0C)

    qkbuf = DBuff(DT.float, [QUAT_M, TILE_N], Position.UB)
    dpbuf = DBuff(DT.float, [QUAT_M, TILE_N], Position.UB)
    obuf = Tensor(DT.half, [HALF_M, TILE_K], Position.UB)
    gradbuf = Tensor(DT.half, [HALF_M, TILE_K], Position.UB)
    ofp32buf = Tensor(DT.float, [SUBS_M, TILE_K], Position.UB)
    gradfp32buf = Tensor(DT.float, [SUBS_M, TILE_K], Position.UB)
    qkmaxbuf = Tensor(DT.float, [1, HALF_M], Position.UB)
    qksumbuf = Tensor(DT.float, [1, HALF_M], Position.UB)
    qkmaxbrcb = Tensor(DT.float, [HALF_M, 8], Position.UB)
    qksumbrcb = Tensor(DT.float, [HALF_M, 8], Position.UB)
    odobuf = Tensor(DT.float, [1, SUBS_M], Position.UB)
    odobrcb = Tensor(DT.float, [HALF_M, 8], Position.UB)
    zero_buf = Tensor(DT.float, [1, HALF_N], Position.UB)
    ub_col_idx = Tensor(DT.int, [1, TILE_N], Position.UB)
    causal_mask_static = Tensor(DT.uint8, [HALF_M, TILE_N // 8], Position.UB)
    causal_mask_dynamic = Tensor(DT.uint8, [HALF_M, TILE_N // 8], Position.UB)
    pbuf = DBuff(DT.half, [QUAT_M, TILE_N], Position.UB)
    dqkbuf = DBuff(DT.half, [QUAT_M, TILE_N], Position.UB)

    qkdp_mutex = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)
    pdqk_mutex = VcMutex(1, src_end_pipe=Pipe.MTE3, dst_end_pipe=Pipe.FIX)

    l1q_cnt = Var(0)
    l1g_cnt = Var(0)
    l1k_cnt = Var(0)
    l1v_cnt = Var(0)
    l1p_cnt = Var(0)
    l1dqk_cnt = Var(0)
    l0c_cnt = Var(0)
    stage1_cnt = Var(0)
    stage2_cnt = Var(0)

    cube_idx = GetCubeIdx()
    sb = GetSubBlockIdx()

    tiles_m = CeilDiv(S1, TILE_M)
    tiles_n = CeilDiv(S2, TILE_N)
    total_m = Var(BH * tiles_m)
    per_core = CeilDiv(total_m, GetCubeNum())
    mt_begin = Var(per_core * cube_idx)
    mt_end = Min(mt_begin + per_core, total_m)

    with vec_scope():
        dup(zero_buf, 0.0)
        init_tile_col_indices(ub_col_idx)
        build_diagonal_tile_causal_mask(causal_mask_static, ub_col_idx, sb * HALF_M, HALF_M)

    for gmt in range(mt_begin, mt_end):
        bh = Var(gmt // tiles_m)
        lmt = Var(gmt % tiles_m)
        row_in_bh = Var(lmt * TILE_M)
        q_row = Var(bh * S1 + row_in_bh)
        kv_base = Var(bh * S2)
        valid_m = Min(TILE_M, S1 - row_in_bh)
        active_tiles_n = Min(tiles_n, CeilDiv(row_in_bh + valid_m, TILE_N))

        half_rows = CeilDiv(valid_m, 2)
        row_begin = Var(sb * half_rows)
        row_end = Min(row_begin + half_rows, valid_m)
        row_count = Var(row_end - row_begin)
        vec_row_in_bh = Var(row_in_bh + row_begin)
        vec_row = Var(q_row + row_begin)

        qbuf = l1q[l1q_cnt]
        gbuf = l1g[l1g_cnt]

        with auto_sync():
            if valid_m < TILE_M:
                set_constant_to_l1(qbuf, 0.0)
                set_constant_to_l1(gbuf, 0.0)

            qbuf <<= q[q_row:q_row + valid_m, 0:D]
            gbuf <<= grad[q_row:q_row + valid_m, 0:D]

            if row_count > 0:
                bar_all()
                if row_count < HALF_M:
                    dup(obuf, 0.0)
                    dup(gradbuf, 0.0)
                    dup(qkmaxbuf, 0.0)
                    dup(qksumbuf, 0.0)
                    bar_all()

                obuf[0:row_count, 0:D] <<= o[vec_row:vec_row + row_count, 0:D]
                gradbuf[0:row_count, 0:D] <<= grad[vec_row:vec_row + row_count, 0:D]
                qkmaxbuf[0:1, 0:row_count] <<= qkmax[bh:bh + 1, vec_row_in_bh:vec_row_in_bh + row_count]
                qksumbuf[0:1, 0:row_count] <<= qksum[bh:bh + 1, vec_row_in_bh:vec_row_in_bh + row_count]

                brcb(qkmaxbrcb, qkmaxbuf, repeat=HALF_M // 8, dst_blk_stride=1, dst_rep_stride=8)
                brcb(qksumbrcb, qksumbuf, repeat=HALF_M // 8, dst_blk_stride=1, dst_rep_stride=8)
                adds(qksumbrcb, qksumbrcb, EPS)

                for subs in range(0, HALF_M, SUBS_M):
                    cast(ofp32buf, obuf[subs:subs + SUBS_M, 0:D])
                    cast(gradfp32buf, gradbuf[subs:subs + SUBS_M, 0:D])

                    mul(ofp32buf[:, 0:64], ofp32buf[:, 0:64], gradfp32buf[:, 0:64])
                    mul(ofp32buf[:, 64:128], ofp32buf[:, 64:128], gradfp32buf[:, 64:128])
                    add(ofp32buf[:, 0:64], ofp32buf[:, 0:64], ofp32buf[:, 64:128])
                    cadd(odobuf, ofp32buf[:, 0:64])
                    brcb(
                        odobrcb[subs:subs + SUBS_M, :], odobuf,
                        repeat=SUBS_M // 8, dst_blk_stride=1, dst_rep_stride=8,
                    )

        for ni in range(0, active_tiles_n + 1):
            if ni < active_tiles_n:
                n_off = Var(ni * TILE_N)
                kv_row = Var(kv_base + n_off)
                valid_n = Min(TILE_N, S2 - n_off)
                kbuf = l1k[l1k_cnt]
                vbuf = l1v[l1v_cnt]
                stage1_slot = var_mod(stage1_cnt, 2)

                with auto_sync():
                    if valid_n < TILE_N:
                        set_constant_to_l1(kbuf, 0.0)
                        set_constant_to_l1(vbuf, 0.0)

                    kbuf <<= k[kv_row:kv_row + valid_n, 0:D]
                    vbuf <<= v[kv_row:kv_row + valid_n, 0:D]

                    matmul(l0c[l0c_cnt], qbuf, kbuf, is_init=True)
                    qkdp_mutex.lock()
                    qk_ws[cube_idx, stage1_slot, 0:TILE_M, 0:TILE_N] <<= l0c[l0c_cnt]
                    l0c_cnt += 1

                    matmul(l0c[l0c_cnt], gbuf, vbuf, is_init=True)
                    dp_ws[cube_idx, stage1_slot, 0:TILE_M, 0:TILE_N] <<= l0c[l0c_cnt]
                    qkdp_mutex.ready()

                    qkdp_mutex.wait()
                    pdqk_mutex.lock()
                    if row_count > 0:
                        quat_tiles = CeilDiv(row_count, QUAT_M)
                        vec_in_cnt = Var(0)
                        vec_out_cnt = Var(0)
                        for qmt in range(0, quat_tiles):
                            quat_off = Var(qmt * QUAT_M)
                            chunk_rows = Min(QUAT_M, row_count - quat_off)

                            qk_tile = qkbuf[vec_in_cnt]
                            dp_tile = dpbuf[vec_in_cnt]
                            p_tile = pbuf[vec_out_cnt]
                            dqk_tile = dqkbuf[vec_out_cnt]

                            qk_tile[0:chunk_rows, 0:TILE_N] <<= qk_ws[
                                cube_idx, stage1_slot, row_begin + quat_off:row_begin + quat_off + chunk_rows, 0:TILE_N
                            ]
                            dp_tile[0:chunk_rows, 0:TILE_N] <<= dp_ws[
                                cube_idx, stage1_slot, row_begin + quat_off:row_begin + quat_off + chunk_rows, 0:TILE_N
                            ]
                            if chunk_rows < QUAT_M:
                                dup(qk_tile[chunk_rows:QUAT_M, 0:TILE_N], 0.0)
                                dup(dp_tile[chunk_rows:QUAT_M, 0:TILE_N], 0.0)

                            muls(qk_tile, qk_tile, scale)
                            sub(qk_tile[:, 0:64], qk_tile[:, 0:64], qkmaxbrcb[quat_off:quat_off + QUAT_M, :])
                            sub(qk_tile[:, 64:128], qk_tile[:, 64:128], qkmaxbrcb[quat_off:quat_off + QUAT_M, :])
                            exp(qk_tile, qk_tile)
                            div(qk_tile[:, 0:64], qk_tile[:, 0:64], qksumbrcb[quat_off:quat_off + QUAT_M, :])
                            div(qk_tile[:, 64:128], qk_tile[:, 64:128], qksumbrcb[quat_off:quat_off + QUAT_M, :])
                            if valid_n < TILE_N:
                                apply_prob_tail_mask(qk_tile, valid_n)
                            if n_off == row_in_bh:
                                if valid_m == TILE_M:
                                    apply_diagonal_tile_causal_select(
                                        qk_tile,
                                        causal_mask_static[quat_off:quat_off + QUAT_M, 0:TILE_N // 8],
                                        zero_buf,
                                    )
                                else:
                                    build_diagonal_tile_causal_mask(
                                        causal_mask_dynamic, ub_col_idx, row_begin + quat_off, chunk_rows,
                                    )
                                    apply_diagonal_tile_causal_select(
                                        qk_tile, causal_mask_dynamic[0:QUAT_M, 0:TILE_N // 8], zero_buf,
                                    )
                            if chunk_rows < QUAT_M:
                                dup(qk_tile[chunk_rows:QUAT_M, 0:TILE_N], 0.0)

                            sub(dp_tile[:, 0:64], dp_tile[:, 0:64], odobrcb[quat_off:quat_off + QUAT_M, :])
                            sub(dp_tile[:, 64:128], dp_tile[:, 64:128], odobrcb[quat_off:quat_off + QUAT_M, :])
                            mul(dp_tile, qk_tile, dp_tile)
                            muls(dp_tile, dp_tile, scale)

                            cast(p_tile, qk_tile)
                            cast(dqk_tile, dp_tile)

                            p_ws[
                                cube_idx, stage1_slot, row_begin + quat_off:row_begin + quat_off + chunk_rows, 0:TILE_N
                            ] <<= p_tile[0:chunk_rows, 0:TILE_N]
                            dqk_ws[
                                cube_idx, stage1_slot, row_begin + quat_off:row_begin + quat_off + chunk_rows, 0:TILE_N
                            ] <<= dqk_tile[0:chunk_rows, 0:TILE_N]

                            vec_in_cnt += 1
                            vec_out_cnt += 1
                    pdqk_mutex.ready()
                    qkdp_mutex.free()

                    l1k_cnt += 1
                    l1v_cnt += 1
                    l0c_cnt += 1
                    stage1_cnt += 1

            if ni > 0:
                prev_nt = Var(ni - 1)
                prev_n_off = Var(prev_nt * TILE_N)
                prev_valid_n = Min(TILE_N, S2 - prev_n_off)
                prev_k_row = Var(kv_base + prev_n_off)
                stage2_slot = var_mod(stage2_cnt, 2)
                pslot = l1p[l1p_cnt]
                dqkslot = l1dqk[l1dqk_cnt]
                kgqbuf = l1k[stage2_cnt]

                with auto_sync():
                    pdqk_mutex.wait()

                    if valid_m < TILE_M:
                        set_constant_to_l1(pslot, 0.0)
                        set_constant_to_l1(dqkslot, 0.0)

                    pslot[0:valid_m, 0:TILE_N] <<= p_ws[cube_idx, stage2_slot, 0:valid_m, 0:TILE_N]
                    dqkslot[0:valid_m, 0:TILE_N] <<= dqk_ws[cube_idx, stage2_slot, 0:valid_m, 0:TILE_N]

                    matmul(l0c[l0c_cnt], pslot.T, gbuf.T, is_init=True)
                    with atomic_add():
                        gv[prev_k_row:prev_k_row + prev_valid_n, 0:D] <<= l0c[l0c_cnt][0:prev_valid_n, 0:D]
                    l0c_cnt += 1

                    matmul(l0c[l0c_cnt], dqkslot.T, qbuf.T, is_init=True)
                    with atomic_add():
                        gk[prev_k_row:prev_k_row + prev_valid_n, 0:D] <<= l0c[l0c_cnt][0:prev_valid_n, 0:D]
                    l0c_cnt += 1

                    matmul(l0c[l0c_cnt], dqkslot, kgqbuf.T, is_init=True)
                    with atomic_add():
                        gq[q_row:q_row + valid_m, 0:D] <<= l0c[l0c_cnt][0:valid_m, 0:D]
                    pdqk_mutex.free()

                    l1p_cnt += 1
                    l1dqk_cnt += 1
                    l0c_cnt += 1
                    stage2_cnt += 1

        l1q_cnt += 1
        l1g_cnt += 1

    return gq, gk, gv


def _causal_mask(S1: int, S2: int, device: torch.device) -> torch.Tensor:
    q_idx = torch.arange(S1, device=device).view(S1, 1)
    k_idx = torch.arange(S2, device=device).view(1, S2)
    return k_idx <= q_idx


def _dense_attn_backward_causal_ref(q, k, v, o, grad, qkmax, qksum):
    q_f = q.float()
    k_f = k.float()
    v_f = v.float()
    o_f = o.float()
    grad_f = grad.float()
    scale = 1.0 / math.sqrt(q.shape[-1])
    causal_mask = _causal_mask(q.shape[-2], k.shape[-2], q.device).view(1, 1, q.shape[-2], k.shape[-2])

    qk = torch.einsum("bhsd,bhtd->bhst", q_f, k_f)
    dp = torch.einsum("bhsd,bhtd->bhst", grad_f, v_f)
    prob = torch.exp(qk * scale - qkmax.float().unsqueeze(-1)) / (qksum.float().unsqueeze(-1) + EPS)
    prob = prob.masked_fill(~causal_mask, 0.0)
    odo = torch.sum(o_f * grad_f, dim=-1)
    dqk = prob * (dp - odo.unsqueeze(-1)) * scale

    prob_half = prob.half()
    dqk_half = dqk.half()
    gq = torch.einsum("bhst,bhtd->bhsd", dqk_half.float(), k_f)
    gk = torch.einsum("bhst,bhsd->bhtd", dqk_half.float(), q_f)
    gv = torch.einsum("bhst,bhsd->bhtd", prob_half.float(), grad_f)
    return {"gq": gq, "gk": gk, "gv": gv}


def _make_qk_stats_causal(q, k):
    score = torch.einsum("bhsd,bhtd->bhst", q.float(), k.float()) * (1.0 / math.sqrt(q.shape[-1]))
    causal_mask = _causal_mask(q.shape[-2], k.shape[-2], q.device).view(1, 1, q.shape[-2], k.shape[-2])
    score = score.masked_fill(~causal_mask, NEG_LARGE)
    qkmax = score.amax(dim=-1)
    qksum = torch.exp(score - qkmax.unsqueeze(-1)).sum(dim=-1)
    return qkmax, qksum


def _run_case(B, H, S1, S2, D):
    assert D == TILE_K

    torch.manual_seed(42)

    BH = B * H
    Q_ROWS = BH * S1
    KV_ROWS = BH * S2

    q = torch.randn(B, H, S1, D, dtype=torch.float16)
    k = torch.randn(B, H, S2, D, dtype=torch.float16)
    v = torch.randn(B, H, S2, D, dtype=torch.float16)
    o = torch.randn(B, H, S1, D, dtype=torch.float16)
    grad = torch.randn(B, H, S1, D, dtype=torch.float16)

    qkmax, qksum = _make_qk_stats_causal(q, k)
    ref = _dense_attn_backward_causal_ref(q, k, v, o, grad, qkmax, qksum)

    q_flat = q.reshape(Q_ROWS, D).contiguous()
    k_flat = k.reshape(KV_ROWS, D).contiguous()
    v_flat = v.reshape(KV_ROWS, D).contiguous()
    o_flat = o.reshape(Q_ROWS, D).contiguous()
    grad_flat = grad.reshape(Q_ROWS, D).contiguous()
    qkmax_flat = qkmax.reshape(BH, S1).contiguous()
    qksum_flat = qksum.reshape(BH, S1).contiguous()
    gq_flat = torch.zeros(Q_ROWS, D, dtype=torch.float32)
    gk_flat = torch.zeros(KV_ROWS, D, dtype=torch.float32)
    gv_flat = torch.zeros(KV_ROWS, D, dtype=torch.float32)

    shape_bindings = {
        0: [4, 2],
        1: [5, 2],
        2: [5, 2],
        3: [4, 2],
        4: [4, 2],
        5: [3, 0],
        6: [3, 0],
        7: [4, 2],
        8: [5, 2],
        9: [5, 2],
    }

    gq_out, gk_out, gv_out = OpExec(attn_backward_dense_total_tail_causal_kernel, simulator=True)(
        q_flat, k_flat, v_flat, o_flat, grad_flat, qkmax_flat, qksum_flat, gq_flat, gk_flat, gv_flat,
        S1, S2, D, BH, Q_ROWS, KV_ROWS, 1.0 / math.sqrt(D),
        shape_bindings=shape_bindings,
    )
    gq_out = gq_out.reshape(B, H, S1, D)
    gk_out = gk_out.reshape(B, H, S2, D)
    gv_out = gv_out.reshape(B, H, S2, D)

    gq_max_abs_diff = torch.abs(gq_out - ref["gq"]).max().item()
    gk_max_abs_diff = torch.abs(gk_out - ref["gk"]).max().item()
    gv_max_abs_diff = torch.abs(gv_out - ref["gv"]).max().item()
    print(
        "causal_shape=({}, {}, {}, {}, {}) gq_max_abs_diff={:.6e} gk_max_abs_diff={:.6e} gv_max_abs_diff={:.6e}".format(
            B, H, S1, S2, D, gq_max_abs_diff, gk_max_abs_diff, gv_max_abs_diff,
        )
    )
    torch.testing.assert_close(gq_out, ref["gq"], rtol=3e-3, atol=3e-3)
    torch.testing.assert_close(gk_out, ref["gk"], rtol=3e-3, atol=3e-3)
    torch.testing.assert_close(gv_out, ref["gv"], rtol=3e-3, atol=3e-3)


def main():
    _run_case(1, 1, 256, 256, 128)
    _run_case(1, 4, 1032, 2051, 128)

if __name__ == "__main__":
    main()
