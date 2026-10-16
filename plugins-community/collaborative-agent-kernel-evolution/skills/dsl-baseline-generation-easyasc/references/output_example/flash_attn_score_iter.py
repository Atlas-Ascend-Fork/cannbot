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
def flash_attn_score_iter_kernel(
    q: GMTensor, k: GMTensor, p: GMTensor,
    S1: Var, S2: Var, D: Var, BH: Var, scale: Var,
):
    ws = split_workspace(DT.float, [GetCubeNum(), 2, TILE_M, TILE_N], name="ws")

    # Cube buffers
    l1q = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1k = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l0c = DBuff(DT.float, [TILE_M, TILE_N], Position.L0C)

    # Vec buffers (per sub-block, each has independent 192KB UB)
    ub_data = Tensor(DT.float, [HALF_M, TILE_N], Position.UB)
    ub_tmp = Tensor(DT.float, [HALF_M, HALF_N], Position.UB)
    ub_max_s = Tensor(DT.float, [HALF_M, 1], Position.UB)
    ub_rmax_s = Tensor(DT.float, [HALF_M, 1], Position.UB)
    ub_max = Tensor(DT.float, [HALF_M, 8], Position.UB)
    ub_out = Tensor(DT.half, [HALF_M, TILE_N], Position.UB)

    cvmutex = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)

    l1_cnt = Var(0)
    l0c_cnt = Var(0)
    ws_cnt = Var(0)

    cube_idx = GetCubeIdx()
    sb = GetSubBlockIdx()
    sb_row = Var(sb * HALF_M)

    tiles_m = CeilDiv(S1, TILE_M)
    tiles_n = CeilDiv(S2, TILE_N)
    total_m = Var(BH * tiles_m)
    per_core = CeilDiv(total_m, GetCubeNum())
    mt_begin = Var(per_core * cube_idx)
    mt_end = Min(mt_begin + per_core, total_m)

    with auto_sync():
        for gmt in range(mt_begin, mt_end):
            batch = Var(gmt // tiles_m)
            lmt = Var(gmt % tiles_m)
            q_row = Var(batch * S1 + lmt * TILE_M)
            k_base = Var(batch * S2)

            dup(ub_rmax_s, NEG_LARGE)

            for nt in range(0, tiles_n):
                n_off = Var(nt * TILE_N)
                k_row = Var(k_base + n_off)
                ws_slot = var_mod(ws_cnt, 2)

                # Cube: Q @ K^T
                l1q[l1_cnt] <<= q[q_row:q_row + TILE_M, 0:D]
                l1k[l1_cnt] <<= k[k_row:k_row + TILE_N, 0:D]
                matmul(l0c[l0c_cnt], l1q[l1_cnt], l1k[l1_cnt], is_init=True)

                cvmutex.lock()
                ws[cube_idx, ws_slot, 0:TILE_M, 0:TILE_N] <<= l0c[l0c_cnt]
                cvmutex.ready()

                # Vec: postprocess on this sub-block's HALF_M rows
                cvmutex.wait()
                ub_data <<= ws[cube_idx, ws_slot, sb_row:sb_row + HALF_M, 0:TILE_N]

                muls(ub_data, ub_data, scale)

                # Per-tile row max
                vmax(ub_tmp, ub_data[0:HALF_M, 0:HALF_N], ub_data[0:HALF_M, HALF_N:TILE_N])
                cmax(ub_max_s, ub_tmp)

                # Update running max in scalar format, then broadcast
                vmax(ub_rmax_s, ub_rmax_s, ub_max_s)
                brcb(ub_max, ub_rmax_s, dst_blk_stride=1, dst_rep_stride=8)

                # Subtract running max (sliced so repeat aligns with narrow max buf)
                sub(ub_data[0:HALF_M, 0:HALF_N], ub_data[0:HALF_M, 0:HALF_N], ub_max)
                sub(ub_data[0:HALF_M, HALF_N:TILE_N], ub_data[0:HALF_M, HALF_N:TILE_N], ub_max)

                exp(ub_data, ub_data)
                cast(ub_out, ub_data)

                out_row = Var(q_row + sb_row)
                p[out_row:out_row + HALF_M, n_off:n_off + TILE_N] <<= ub_out
                cvmutex.free()

                l1_cnt += 1
                l0c_cnt += 1
                ws_cnt += 1

    return p


def _ref_flash_attn_score_iter(q, k):
    import builtins
    import torch
    B, H, S1, D = q.shape
    S2 = k.shape[2]
    scale = 1.0 / (D ** 0.5)
    q_f, k_f = q.float(), k.float()
    m = torch.full((B, H, S1, 1), NEG_LARGE)
    p = torch.zeros(B, H, S1, S2)
    for j in builtins.range(0, S2, TILE_N):
        k_blk = k_f[:, :, j:j + TILE_N, :]
        s = torch.einsum('bhsd,bhtd->bhst', q_f, k_blk) * scale
        m_j = s.max(dim=-1, keepdim=True).values
        m = torch.maximum(m, m_j)
        p[:, :, :, j:j + TILE_N] = torch.exp(s - m)
    return p.half()


def main():
    import torch
    import math

    torch.manual_seed(42)

    # --- small validation ---
    B, H, S1, S2, D = 1, 1, 256, 512, 128
    BH = B * H
    q = torch.randn(B, H, S1, D, dtype=torch.float16)
    k = torch.randn(B, H, S2, D, dtype=torch.float16)
    p_ref = _ref_flash_attn_score_iter(q, k)

    q_flat = q.reshape(BH * S1, D).contiguous()
    k_flat = k.reshape(BH * S2, D).contiguous()
    p_flat = torch.zeros(BH * S1, S2, dtype=torch.float16)

    p_out = OpExec(flash_attn_score_iter_kernel, simulator=True)(
        q_flat, k_flat, p_flat, S1, S2, D, BH, 1.0 / math.sqrt(D))
    p_out = p_out.reshape(B, H, S1, S2)

    torch.testing.assert_close(p_out, p_ref, rtol=1e-2, atol=1e-2)
    print(f"small_test ({B},{H},{S1},{S2},{D}): "
          f"max_diff={torch.abs(p_out.float() - p_ref.float()).max().item():.6e}")

    # --- multi-batch validation ---
    B, H, S1, S2, D = 1, 3, 256, 512, 128
    BH = B * H
    q = torch.randn(B, H, S1, D, dtype=torch.float16)
    k = torch.randn(B, H, S2, D, dtype=torch.float16)
    p_ref = _ref_flash_attn_score_iter(q, k)

    q_flat = q.reshape(BH * S1, D).contiguous()
    k_flat = k.reshape(BH * S2, D).contiguous()
    p_flat = torch.zeros(BH * S1, S2, dtype=torch.float16)

    p_out = OpExec(flash_attn_score_iter_kernel, simulator=True)(
        q_flat, k_flat, p_flat, S1, S2, D, BH, 1.0 / math.sqrt(D))
    p_out = p_out.reshape(B, H, S1, S2)

    torch.testing.assert_close(p_out, p_ref, rtol=1e-2, atol=1e-2)
    print(f"batch_test ({B},{H},{S1},{S2},{D}): "
          f"max_diff={torch.abs(p_out.float() - p_ref.float()).max().item():.6e}")

    # --- full-size validation ---
    B, H, S1, S2, D = 1, 3, 2048, 4096, 128
    BH = B * H
    q = torch.randn(B, H, S1, D, dtype=torch.float16)
    k = torch.randn(B, H, S2, D, dtype=torch.float16)
    p_ref = _ref_flash_attn_score_iter(q, k)

    q_flat = q.reshape(BH * S1, D).contiguous()
    k_flat = k.reshape(BH * S2, D).contiguous()
    p_flat = torch.zeros(BH * S1, S2, dtype=torch.float16)

    p_out = OpExec(flash_attn_score_iter_kernel, simulator=True)(
        q_flat, k_flat, p_flat, S1, S2, D, BH, 1.0 / math.sqrt(D))
    p_out = p_out.reshape(B, H, S1, S2)

    torch.testing.assert_close(p_out, p_ref, rtol=1e-2, atol=1e-2)
    print(f"full_test ({B},{H},{S1},{S2},{D}): "
          f"max_diff={torch.abs(p_out.float() - p_ref.float()).max().item():.6e}")

if __name__ == "__main__":
    main()
