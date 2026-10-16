# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
from easyasc.a2 import *

TILE_M = 128
TILE_N = 128
TILE_K = 128
HALF_M = TILE_M // 2
HALF_N = TILE_N // 2
NEG_LARGE = -1.0e30


@kernel()
def flash_attn_score_pv_kernel(
    q: GMTensor, k: GMTensor, v: GMTensor, pv: GMTensor,
    S1: Var, S2: Var, D: Var, BH: Var, scale: Var,
):
    score_ws = split_workspace(DT.float, [GetCubeNum(), 2, TILE_M, TILE_N], name="score_ws")
    p_ws = split_workspace(DT.half, [GetCubeNum(), 2, TILE_M, TILE_N], name="p_ws")

    l1q = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1k = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l1p = DBuff(DT.half, [TILE_M, TILE_N], Position.L1)
    l1v = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l0c = DBuff(DT.float, [TILE_M, TILE_N], Position.L0C)

    ub_score = Tensor(DT.float, [HALF_M, TILE_N], Position.UB)
    ub_tmp = Tensor(DT.float, [HALF_M, HALF_N], Position.UB)
    ub_max_s = Tensor(DT.float, [HALF_M, 1], Position.UB)
    ub_rmax_s = Tensor(DT.float, [HALF_M, 1], Position.UB)
    ub_max = Tensor(DT.float, [HALF_M, 8], Position.UB)
    ub_p = Tensor(DT.half, [HALF_M, TILE_N], Position.UB)

    qk_mutex = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)
    p_mutex = VcMutex(1, src_end_pipe=Pipe.MTE3, dst_end_pipe=Pipe.FIX)

    l1qk_cnt = Var(0)
    l1pv_cnt = Var(0)
    l0c_cnt = Var(0)
    stage1_cnt = Var(0)
    stage2_cnt = Var(0)

    cube_idx = GetCubeIdx()
    sb = GetSubBlockIdx()
    sb_row = Var(sb * HALF_M)

    tiles_m = CeilDiv(S1, TILE_M)
    tiles_n = CeilDiv(S2, TILE_N)
    total_m = Var(BH * tiles_m)
    per_core = CeilDiv(total_m, GetCubeNum())
    mt_begin = Var(per_core * cube_idx)
    mt_end = Min(mt_begin + per_core, total_m)

    for gmt in range(mt_begin, mt_end):
        bh = Var(gmt // tiles_m)
        lmt = Var(gmt % tiles_m)
        q_row = Var(bh * S1 + lmt * TILE_M)
        kv_base = Var(bh * S2)

        dup(ub_rmax_s, NEG_LARGE)

        for ni in range(0, tiles_n + 1):
            if ni < tiles_n:
                with auto_sync():
                    n_off = Var(ni * TILE_N)
                    k_row = Var(kv_base + n_off)
                    ws_slot = var_mod(stage1_cnt, 2)

                    l1q[l1qk_cnt] <<= q[q_row:q_row + TILE_M, 0:D]
                    l1k[l1qk_cnt] <<= k[k_row:k_row + TILE_N, 0:D]
                    matmul(l0c[l0c_cnt], l1q[l1qk_cnt], l1k[l1qk_cnt], is_init=True)

                    qk_mutex.lock()
                    score_ws[cube_idx, ws_slot, 0:TILE_M, 0:TILE_N] <<= l0c[l0c_cnt]
                    qk_mutex.ready()

                    qk_mutex.wait()
                    ub_score <<= score_ws[cube_idx, ws_slot, sb_row:sb_row + HALF_M, 0:TILE_N]

                    muls(ub_score, ub_score, scale)
                    vmax(ub_tmp, ub_score[0:HALF_M, 0:HALF_N], ub_score[0:HALF_M, HALF_N:TILE_N])
                    cmax(ub_max_s, ub_tmp)
                    vmax(ub_rmax_s, ub_rmax_s, ub_max_s)
                    brcb(ub_max, ub_rmax_s, dst_blk_stride=1, dst_rep_stride=8)

                    sub(ub_score[0:HALF_M, 0:HALF_N], ub_score[0:HALF_M, 0:HALF_N], ub_max)
                    sub(ub_score[0:HALF_M, HALF_N:TILE_N], ub_score[0:HALF_M, HALF_N:TILE_N], ub_max)

                    exp(ub_score, ub_score)
                    cast(ub_p, ub_score)

                    p_mutex.lock()
                    p_ws[cube_idx, ws_slot, sb_row:sb_row + HALF_M, 0:TILE_N] <<= ub_p
                    p_mutex.ready()
                    qk_mutex.free()

                    l1qk_cnt += 1
                    l0c_cnt += 1
                    stage1_cnt += 1

            if ni > 0:
                with auto_sync():
                    prev_nt = Var(ni - 1)
                    prev_n_off = Var(prev_nt * TILE_N)
                    p_slot = var_mod(stage2_cnt, 2)
                    v_row = Var(kv_base + prev_n_off)
                    out_row = Var((bh * tiles_n + prev_nt) * S1 + lmt * TILE_M)

                    p_mutex.wait()
                    l1p[l1pv_cnt] <<= p_ws[cube_idx, p_slot, 0:TILE_M, 0:TILE_N]
                    l1v[l1pv_cnt] <<= v[v_row:v_row + TILE_N, 0:D]
                    matmul(l0c[l0c_cnt], l1p[l1pv_cnt], l1v[l1pv_cnt].T, is_init=True)
                    pv[out_row:out_row + TILE_M, 0:D] <<= l0c[l0c_cnt]
                    p_mutex.free()

                    l1pv_cnt += 1
                    l0c_cnt += 1
                    stage2_cnt += 1

    return pv


def _ref_flash_attn_score_pv(q, k, v):
    import builtins
    import torch

    B, H, S1, D = q.shape
    S2 = k.shape[2]
    tiles_n = S2 // TILE_N
    scale = 1.0 / (D ** 0.5)

    q_f = q.float()
    k_f = k.float()
    v_f = v.float()

    m = torch.full((B, H, S1, 1), NEG_LARGE)
    pv = torch.zeros(B, H, tiles_n, S1, D, dtype=torch.float32)

    for j in builtins.range(0, S2, TILE_N):
        k_blk = k_f[:, :, j:j + TILE_N, :]
        s_j = torch.einsum("bhsd,bhtd->bhst", q_f, k_blk) * scale
        m_j = s_j.max(dim=-1, keepdim=True).values
        m = torch.maximum(m, m_j)

        p_j = torch.exp(s_j - m).half()
        v_blk = v_f[:, :, j:j + TILE_N, :]
        pv_j = torch.einsum("bhst,bhtd->bhsd", p_j.float(), v_blk)
        pv[:, :, j // TILE_N, :, :] = pv_j

    return pv


def main():
    import math
    import torch

    torch.manual_seed(42)

    def run_case(B, H, S1, S2, D):
        assert S1 % TILE_M == 0
        assert S2 % TILE_N == 0
        assert D == TILE_K

        BH = B * H
        tiles_n = S2 // TILE_N

        q = torch.randn(B, H, S1, D, dtype=torch.float16)
        k = torch.randn(B, H, S2, D, dtype=torch.float16)
        v = torch.randn(B, H, S2, D, dtype=torch.float16)
        pv_ref = _ref_flash_attn_score_pv(q, k, v)

        q_flat = q.reshape(BH * S1, D).contiguous()
        k_flat = k.reshape(BH * S2, D).contiguous()
        v_flat = v.reshape(BH * S2, D).contiguous()
        pv_flat = torch.zeros(BH * tiles_n * S1, D, dtype=torch.float32)

        pv_out = OpExec(flash_attn_score_pv_kernel, simulator=True)(
            q_flat, k_flat, v_flat, pv_flat, S1, S2, D, BH, 1.0 / math.sqrt(D))
        pv_out = pv_out.reshape(B, H, tiles_n, S1, D)

        torch.testing.assert_close(pv_out, pv_ref, rtol=2e-2, atol=2e-2)
        print(
            f"shape=({B},{H},{S1},{S2},{D}): "
            f"max_abs_diff={torch.abs(pv_out - pv_ref).max().item():.6e}"
        )

    run_case(1, 1, 256, 512, 128)
    run_case(1, 3, 256, 512, 128)
    run_case(1, 3, 2048, 4096, 128)

if __name__ == "__main__":
    main()
