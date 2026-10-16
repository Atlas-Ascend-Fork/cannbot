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
EPS = 1.0e-10


@kernel()
def attn_backward_dense_stage1_tail_dbuf_kernel(
    q: GMTensor, k: GMTensor, grad: GMTensor, v: GMTensor, qk: GMTensor, dp: GMTensor,
    S1: Var, S2: Var, D: Var, BH: Var, Q_ROWS: Var, KV_ROWS: Var,
):
    # Stage-1 dense backward baseline with DBuff staging and tile tails:
    # qk = q.float() @ k.float().t()
    # dp = grad.float() @ v.float().t()
    #
    # Lessons captured in this version:
    # - keep DBuff / L0C tile shapes fixed and apply tails only at GM boundaries
    # - for tail tiles, zero the L1 slot before partial GM -> L1 load
    # - let matmul infer its packed layout on this path; explicit m/n/k changed NZ/ZZ behavior
    # - GM writeback can use <<= directly; no explicit M_src is needed here
    l1q = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1g = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1k = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l1v = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l0c = DBuff(DT.float, [TILE_M, TILE_N], Position.L0C)

    l1q_cnt = Var(0)
    l1g_cnt = Var(0)
    l1k_cnt = Var(0)
    l1v_cnt = Var(0)
    l0c_cnt = Var(0)

    tiles_m = CeilDiv(S1, TILE_M)
    tiles_n = CeilDiv(S2, TILE_N)
    total_m = Var(BH * tiles_m)
    per_core = CeilDiv(total_m, GetCubeNum())
    mt_begin = Var(per_core * GetCubeIdx())
    mt_end = Min(mt_begin + per_core, total_m)

    with auto_sync():
        for gmt in range(mt_begin, mt_end):
            bh = Var(gmt // tiles_m)
            lmt = Var(gmt % tiles_m)
            q_row = Var(bh * S1 + lmt * TILE_M)
            kv_base = Var(bh * S2)
            valid_m = Min(TILE_M, S1 - lmt * TILE_M)
            qbuf = l1q[l1q_cnt]
            gbuf = l1g[l1g_cnt]

            if valid_m < TILE_M:
                set_constant_to_l1(qbuf, 0.0)
                set_constant_to_l1(gbuf, 0.0)

            qbuf <<= q[q_row:q_row + valid_m, 0:D]
            gbuf <<= grad[q_row:q_row + valid_m, 0:D]

            for nt in range(0, tiles_n):
                n_off = Var(nt * TILE_N)
                kv_row = Var(kv_base + n_off)
                valid_n = Min(TILE_N, S2 - n_off)
                kbuf = l1k[l1k_cnt]
                vbuf = l1v[l1v_cnt]

                if valid_n < TILE_N:
                    set_constant_to_l1(kbuf, 0.0)
                    set_constant_to_l1(vbuf, 0.0)

                kbuf <<= k[kv_row:kv_row + valid_n, 0:D]
                vbuf <<= v[kv_row:kv_row + valid_n, 0:D]

                matmul(l0c[l0c_cnt], qbuf, kbuf, is_init=True)
                qk[q_row:q_row + valid_m, n_off:n_off + valid_n] <<= l0c[l0c_cnt]
                l0c_cnt += 1

                matmul(l0c[l0c_cnt], gbuf, vbuf, is_init=True)
                dp[q_row:q_row + valid_m, n_off:n_off + valid_n] <<= l0c[l0c_cnt]
                l0c_cnt += 1
                l1k_cnt += 1
                l1v_cnt += 1

            l1q_cnt += 1
            l1g_cnt += 1

    return qk, dp


def _qk_dp_ref(q, k, v, grad):
    q_f = q.float()
    k_f = k.float()
    v_f = v.float()
    grad_f = grad.float()
    qk = torch.einsum("bhsd,bhtd->bhst", q_f, k_f)
    dp = torch.einsum("bhsd,bhtd->bhst", grad_f, v_f)
    return {"qk": qk, "dp": dp}


def _dense_attn_backward_ref(q, k, v, o, grad, qkmax, qksum):
    stage1 = _qk_dp_ref(q, k, v, grad)
    qk = stage1["qk"]
    dp = stage1["dp"]
    q_f = q.float()
    k_f = k.float()
    o_f = o.float()
    grad_f = grad.float()
    scale = 1.0 / math.sqrt(q.shape[-1])

    score = qk * scale
    prob = torch.exp(score - qkmax.float().unsqueeze(-1)) / (qksum.float().unsqueeze(-1) + EPS)
    odo = torch.sum(o_f * grad_f, dim=-1)
    dqk = prob * (dp - odo.unsqueeze(-1)) * scale

    prob_half = prob.half()
    dqk_half = dqk.half()
    gq = torch.einsum("bhst,bhtd->bhsd", dqk_half.float(), k_f)
    gk = torch.einsum("bhst,bhsd->bhtd", dqk_half.float(), q_f)
    gv = torch.einsum("bhst,bhsd->bhtd", prob_half.float(), grad_f)

    return {"gq": gq, "gk": gk, "gv": gv}


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
    NQ = (SQ + TILE_M - 1) // TILE_M
    NK = (SK + TILE_N - 1) // TILE_N

    q = torch.randn(B, H, SQ, D, dtype=torch.float16)
    k = torch.randn(B, H, SK, D, dtype=torch.float16)
    v = torch.randn(B, H, SK, D, dtype=torch.float16)
    grad = torch.randn(B, H, SQ, D, dtype=torch.float16)
    o = torch.randn(B, H, SQ, D, dtype=torch.float16)

    ref = _qk_dp_ref(q, k, v, grad)
    qkmax, qksum = _make_qk_stats(ref["qk"], D)
    full_ref = _dense_attn_backward_ref(q, k, v, o, grad, qkmax, qksum)

    q_flat = q.reshape(Q_ROWS, D).contiguous()
    k_flat = k.reshape(KV_ROWS, D).contiguous()
    grad_flat = grad.reshape(Q_ROWS, D).contiguous()
    v_flat = v.reshape(KV_ROWS, D).contiguous()
    qk_flat = torch.zeros(Q_ROWS, SK, dtype=torch.float32)
    dp_flat = torch.zeros(Q_ROWS, SK, dtype=torch.float32)
    shape_bindings = {
        0: [4, 2],
        1: [5, 2],
        2: [4, 2],
        3: [5, 2],
        4: [4, 1],
        5: [4, 1],
    }

    qk_out, dp_out = OpExec(attn_backward_dense_stage1_tail_dbuf_kernel, simulator=True)(
        q_flat, k_flat, grad_flat, v_flat, qk_flat, dp_flat, SQ, SK, D, BH, Q_ROWS, KV_ROWS,
        shape_bindings=shape_bindings,
    )
    qk_out = qk_out.reshape(B, H, SQ, SK)
    dp_out = dp_out.reshape(B, H, SQ, SK)

    torch.testing.assert_close(qk_out, ref["qk"], rtol=3e-3, atol=3e-3)
    torch.testing.assert_close(dp_out, ref["dp"], rtol=3e-3, atol=3e-3)

    print(
        "shape=({}, {}, {}, {}, {}) NQ={} NK={} qk_max_abs_diff={:.6e} dp_max_abs_diff={:.6e}".format(
            B, H, SQ, SK, D, NQ, NK,
            torch.abs(qk_out - ref["qk"]).max().item(),
            torch.abs(dp_out - ref["dp"]).max().item(),
        )
    )
    print(
        "prepared_next_stage qkmax_shape={} qksum_shape={} gq_shape={}".format(
            tuple(qkmax.shape), tuple(qksum.shape), tuple(full_ref["gq"].shape),
        )
    )


def main():
    _run_case(1, 1, 256, 256, 128)
    _run_case(1, 4, 1032, 2051, 128)

if __name__ == "__main__":
    main()
