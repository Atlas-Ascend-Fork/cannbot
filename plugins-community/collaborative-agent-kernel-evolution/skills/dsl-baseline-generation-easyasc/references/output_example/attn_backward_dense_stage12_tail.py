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

from easyasc.a2 import *

TILE_M = 128
TILE_N = 128
TILE_K = 128
HALF_M = TILE_M // 2
HALF_N = TILE_N // 2
QUAT_M = HALF_M // 2
SUBS_M = 32
EPS = 1.0e-10


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


@kernel()
def attn_backward_dense_stage12_tail_kernel(
    q: GMTensor, k: GMTensor, grad: GMTensor, v: GMTensor, o: GMTensor, qkmax: GMTensor, qksum: GMTensor,
    p: GMTensor, dqk: GMTensor,
    S1: Var, S2: Var, D: Var, BH: Var, Q_ROWS: Var, KV_ROWS: Var, scale: Var,
):
    # Stage-1 + stage-2 fused dense backward slice on a2:
    # qk = q.float() @ k.float().t()
    # dp = grad.float() @ v.float().t()
    # p = exp(qk * scale - qkmax) / qksum
    # dqk = p * (dp - sum(o * grad)) * scale
    #
    # Important conventions captured in this version:
    # - stage-1 tail zero-fill happens on concrete L1 slots before partial GM -> L1 loads
    # - the a2 cube -> vec workspace bridge stays on stable full-tile shapes
    # - vec-side `valid_n` handling is done with masking and final GM boundaries
    # - the vec hot path uses QUAT_M-sized DBuff chunks to keep stable slot lineage
    #   without increasing the total UB footprint
    # - `bar_all()` is used around local zero-fill that must complete before later MTE2 loads
    qk_ws = split_workspace(DT.float, [GetCubeNum(), 2, TILE_M, TILE_N], name="qk_ws")
    dp_ws = split_workspace(DT.float, [GetCubeNum(), 2, TILE_M, TILE_N], name="dp_ws")

    l1q = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1g = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1k = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l1v = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
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
    pbuf = DBuff(DT.half, [QUAT_M, TILE_N], Position.UB)
    dqkbuf = DBuff(DT.half, [QUAT_M, TILE_N], Position.UB)

    qkdp_mutex = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)

    l1q_cnt = Var(0)
    l1g_cnt = Var(0)
    l1k_cnt = Var(0)
    l1v_cnt = Var(0)
    l0c_cnt = Var(0)
    ws_prod_cnt = Var(0)
    ws_cons_cnt = Var(0)
    vec_in_cnt = Var(0)
    vec_out_cnt = Var(0)

    cube_idx = GetCubeIdx()
    sb = GetSubBlockIdx()

    tiles_m = CeilDiv(S1, TILE_M)
    tiles_n = CeilDiv(S2, TILE_N)
    total_m = Var(BH * tiles_m)
    per_core = CeilDiv(total_m, GetCubeNum())
    mt_begin = Var(per_core * cube_idx)
    mt_end = Min(mt_begin + per_core, total_m)

    for gmt in range(mt_begin, mt_end):
        bh = Var(gmt // tiles_m)
        lmt = Var(gmt % tiles_m)
        row_in_bh = Var(lmt * TILE_M)
        q_row = Var(bh * S1 + row_in_bh)
        kv_base = Var(bh * S2)
        valid_m = Min(TILE_M, S1 - row_in_bh)

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

        for ni in range(0, tiles_n + 1):
            if ni < tiles_n:
                n_off = Var(ni * TILE_N)
                kv_row = Var(kv_base + n_off)
                valid_n = Min(TILE_N, S2 - n_off)
                kbuf = l1k[l1k_cnt]
                vbuf = l1v[l1v_cnt]
                prod_slot = var_mod(ws_prod_cnt, 2)

                with auto_sync():
                    if valid_n < TILE_N:
                        set_constant_to_l1(kbuf, 0.0)
                        set_constant_to_l1(vbuf, 0.0)

                    kbuf <<= k[kv_row:kv_row + valid_n, 0:D]
                    vbuf <<= v[kv_row:kv_row + valid_n, 0:D]

                    matmul(l0c[l0c_cnt], qbuf, kbuf, is_init=True)
                    qkdp_mutex.lock()
                    qk_ws[cube_idx, prod_slot, 0:TILE_M, 0:TILE_N] <<= l0c[l0c_cnt]
                    l0c_cnt += 1

                    matmul(l0c[l0c_cnt], gbuf, vbuf, is_init=True)
                    dp_ws[cube_idx, prod_slot, 0:TILE_M, 0:TILE_N] <<= l0c[l0c_cnt]
                    qkdp_mutex.ready()

                    l1k_cnt += 1
                    l1v_cnt += 1
                    l0c_cnt += 1
                    ws_prod_cnt += 1

            if ni > 0:
                prev_nt = Var(ni - 1)
                prev_n_off = Var(prev_nt * TILE_N)
                prev_valid_n = Min(TILE_N, S2 - prev_n_off)
                cons_slot = var_mod(ws_cons_cnt, 2)

                with auto_sync():
                    qkdp_mutex.wait()

                    if row_count > 0:
                        quat_tiles = CeilDiv(row_count, QUAT_M)
                        for qmt in range(0, quat_tiles):
                            quat_off = Var(qmt * QUAT_M)
                            chunk_rows = Min(QUAT_M, row_count - quat_off)

                            qk_tile = qkbuf[vec_in_cnt]
                            dp_tile = dpbuf[vec_in_cnt]
                            p_tile = pbuf[vec_out_cnt]
                            dqk_tile = dqkbuf[vec_out_cnt]

                            qk_tile[0:chunk_rows, 0:TILE_N] <<= qk_ws[
                                cube_idx, cons_slot, row_begin + quat_off:row_begin + quat_off + chunk_rows, 0:TILE_N
                            ]
                            dp_tile[0:chunk_rows, 0:TILE_N] <<= dp_ws[
                                cube_idx, cons_slot, row_begin + quat_off:row_begin + quat_off + chunk_rows, 0:TILE_N
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
                            if prev_valid_n < TILE_N:
                                apply_prob_tail_mask(qk_tile, prev_valid_n)
                            if chunk_rows < QUAT_M:
                                dup(qk_tile[chunk_rows:QUAT_M, 0:TILE_N], 0.0)

                            sub(dp_tile[:, 0:64], dp_tile[:, 0:64], odobrcb[quat_off:quat_off + QUAT_M, :])
                            sub(dp_tile[:, 64:128], dp_tile[:, 64:128], odobrcb[quat_off:quat_off + QUAT_M, :])
                            mul(dp_tile, qk_tile, dp_tile)
                            muls(dp_tile, dp_tile, scale)

                            cast(p_tile, qk_tile)
                            cast(dqk_tile, dp_tile)

                            p[
                                vec_row + quat_off:vec_row + quat_off + chunk_rows,
                                prev_n_off:prev_n_off + prev_valid_n,
                            ] <<= p_tile[
                                0:chunk_rows, 0:prev_valid_n
                            ]
                            dqk[
                                vec_row + quat_off:vec_row + quat_off + chunk_rows,
                                prev_n_off:prev_n_off + prev_valid_n,
                            ] <<= dqk_tile[0:chunk_rows, 0:prev_valid_n]

                            vec_in_cnt += 1
                            vec_out_cnt += 1

                    qkdp_mutex.free()
                    ws_cons_cnt += 1

        l1q_cnt += 1
        l1g_cnt += 1

    return p, dqk


def _qk_dp_ref(q, k, v, grad):
    q_f = q.float()
    k_f = k.float()
    v_f = v.float()
    grad_f = grad.float()
    qk = torch.einsum("bhsd,bhtd->bhst", q_f, k_f)
    dp = torch.einsum("bhsd,bhtd->bhst", grad_f, v_f)
    return {"qk": qk, "dp": dp}


def _prob_dqk_ref(qk, dp, o, grad, qkmax, qksum, d):
    o_f = o.float()
    grad_f = grad.float()
    scale = 1.0 / math.sqrt(d)

    score = qk * scale
    prob = torch.exp(score - qkmax.float().unsqueeze(-1)) / (qksum.float().unsqueeze(-1) + EPS)
    odo = torch.sum(o_f * grad_f, dim=-1)
    dqk = prob * (dp - odo.unsqueeze(-1)) * scale

    return {
        "prob": prob,
        "prob_half": prob.half(),
        "dqk": dqk,
        "dqk_half": dqk.half(),
    }


def _make_qk_stats(qk, d):
    score = qk * (1.0 / math.sqrt(d))
    qkmax = score.amax(dim=-1)
    exp_score = torch.exp(score - qkmax.unsqueeze(-1))
    qksum = exp_score.sum(dim=-1)
    return qkmax, qksum


def _run_case(B, H, SQ, SK, D):
    assert D == TILE_K

    torch.manual_seed(42)

    BH = B * H
    Q_ROWS = BH * SQ
    KV_ROWS = BH * SK

    q = torch.randn(B, H, SQ, D, dtype=torch.float16)
    k = torch.randn(B, H, SK, D, dtype=torch.float16)
    v = torch.randn(B, H, SK, D, dtype=torch.float16)
    o = torch.randn(B, H, SQ, D, dtype=torch.float16)
    grad = torch.randn(B, H, SQ, D, dtype=torch.float16)

    stage1 = _qk_dp_ref(q, k, v, grad)
    qk = stage1["qk"]
    dp = stage1["dp"]
    qkmax, qksum = _make_qk_stats(qk, D)
    ref = _prob_dqk_ref(qk, dp, o, grad, qkmax, qksum, D)

    q_flat = q.reshape(Q_ROWS, D).contiguous()
    k_flat = k.reshape(KV_ROWS, D).contiguous()
    v_flat = v.reshape(KV_ROWS, D).contiguous()
    o_flat = o.reshape(Q_ROWS, D).contiguous()
    grad_flat = grad.reshape(Q_ROWS, D).contiguous()
    qkmax_flat = qkmax.reshape(BH, SQ).contiguous()
    qksum_flat = qksum.reshape(BH, SQ).contiguous()
    p_flat = torch.zeros(Q_ROWS, SK, dtype=torch.float16)
    dqk_flat = torch.zeros(Q_ROWS, SK, dtype=torch.float16)
    shape_bindings = {
        0: [4, 2],
        1: [5, 2],
        2: [4, 2],
        3: [5, 2],
        4: [4, 2],
        5: [3, 0],
        6: [3, 0],
        7: [4, 1],
        8: [4, 1],
    }

    p_out, dqk_out = OpExec(attn_backward_dense_stage12_tail_kernel, simulator=True)(
        q_flat, k_flat, grad_flat, v_flat, o_flat, qkmax_flat, qksum_flat, p_flat, dqk_flat,
        SQ, SK, D, BH, Q_ROWS, KV_ROWS, 1.0 / math.sqrt(D),
        shape_bindings=shape_bindings,
    )
    p_out = p_out.reshape(B, H, SQ, SK)
    dqk_out = dqk_out.reshape(B, H, SQ, SK)

    p_ref = ref["prob_half"]
    dqk_ref = ref["dqk_half"]
    p_max_abs_diff = torch.abs(p_out.float() - p_ref.float()).max().item()
    dqk_max_abs_diff = torch.abs(dqk_out.float() - dqk_ref.float()).max().item()
    print(
        "shape=({}, {}, {}, {}, {}) p_max_abs_diff={:.6e} dqk_max_abs_diff={:.6e}".format(
            B, H, SQ, SK, D, p_max_abs_diff, dqk_max_abs_diff,
        )
    )
    torch.testing.assert_close(p_out.float(), p_ref.float(), rtol=2e-3, atol=2e-3)
    torch.testing.assert_close(dqk_out.float(), dqk_ref.float(), rtol=2e-3, atol=2e-3)


def main():
    _run_case(1, 1, 256, 256, 128)
    _run_case(1, 4, 1032, 2051, 128)

if __name__ == "__main__":
    main()
