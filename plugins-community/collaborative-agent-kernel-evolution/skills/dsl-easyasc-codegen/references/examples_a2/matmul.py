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


@kernel()
def qk_matmul_batched_kernel(
    q: GMTensor, k: GMTensor, qk: GMTensor,
    S1: Var, S2: Var, D: Var, BH: Var,
):
    l1q = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1k = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l0c = DBuff(DT.float, [TILE_M, TILE_N], Position.L0C)

    l1_cnt = Var(0)
    l0c_cnt = Var(0)

    tiles_m_per_batch = CeilDiv(S1, TILE_M)
    tiles_n = CeilDiv(S2, TILE_N)
    total_m_tiles = Var(BH * tiles_m_per_batch)

    m_tiles_per_core = CeilDiv(total_m_tiles, GetCubeNum())
    m_tile_begin = Var(m_tiles_per_core * GetCubeIdx())
    m_tile_end = Min(m_tile_begin + m_tiles_per_core, total_m_tiles)

    with auto_sync():
        for global_mt in range(m_tile_begin, m_tile_end):
            batch_idx = Var(global_mt // tiles_m_per_batch)
            local_mt = Var(global_mt % tiles_m_per_batch)
            q_row = Var(batch_idx * S1 + local_mt * TILE_M)
            k_row_base = Var(batch_idx * S2)

            for nt in range(0, tiles_n):
                n_offset = Var(nt * TILE_N)
                k_row = Var(k_row_base + n_offset)

                l1q[l1_cnt] <<= q[q_row:q_row + TILE_M, 0:D]
                l1k[l1_cnt] <<= k[k_row:k_row + TILE_N, 0:D]

                matmul(l0c[l0c_cnt], l1q[l1_cnt], l1k[l1_cnt], is_init=True)

                qk[q_row:q_row + TILE_M, n_offset:n_offset + TILE_N] <<= l0c[l0c_cnt]

                l1_cnt += 1
                l0c_cnt += 1

    return qk


def main():
    import torch

    torch.manual_seed(42)

    # --- small validation ---
    B, H, S1, S2, D = 1, 1, 256, 512, 128
    BH = B * H

    q = torch.randn(B, H, S1, D, dtype=torch.float16)
    k = torch.randn(B, H, S2, D, dtype=torch.float16)
    qk_ref = torch.einsum('bhsd,bhtd->bhst', q.float(), k.float())

    q_flat = q.reshape(BH * S1, D).contiguous()
    k_flat = k.reshape(BH * S2, D).contiguous()
    qk_flat = torch.zeros(BH * S1, S2, dtype=torch.float32)

    qk_out = OpExec(qk_matmul_batched_kernel, simulator=True)(
        q_flat, k_flat, qk_flat, S1, S2, D, BH)
    qk_out = qk_out.reshape(B, H, S1, S2)

    torch.testing.assert_close(qk_out, qk_ref, rtol=3e-3, atol=3e-3)
    print(f"small_test shape=({B},{H},{S1},{S2},{D}): "
          f"max_abs_diff={torch.abs(qk_out - qk_ref).max().item():.6e}")

    # --- multi-batch validation ---
    B, H, S1, S2, D = 1, 3, 256, 512, 128
    BH = B * H

    q = torch.randn(B, H, S1, D, dtype=torch.float16)
    k = torch.randn(B, H, S2, D, dtype=torch.float16)
    qk_ref = torch.einsum('bhsd,bhtd->bhst', q.float(), k.float())

    q_flat = q.reshape(BH * S1, D).contiguous()
    k_flat = k.reshape(BH * S2, D).contiguous()
    qk_flat = torch.zeros(BH * S1, S2, dtype=torch.float32)

    qk_out = OpExec(qk_matmul_batched_kernel, simulator=True)(
        q_flat, k_flat, qk_flat, S1, S2, D, BH)
    qk_out = qk_out.reshape(B, H, S1, S2)

    torch.testing.assert_close(qk_out, qk_ref, rtol=3e-3, atol=3e-3)
    print(f"batch_test shape=({B},{H},{S1},{S2},{D}): "
          f"max_abs_diff={torch.abs(qk_out - qk_ref).max().item():.6e}")

    # --- full-size validation (aligned with test_qkmatmul.py) ---
    B, H, S1, S2, D = 1, 3, 2048, 4096, 128
    BH = B * H

    q = torch.randn(B, H, S1, D, dtype=torch.float16)
    k = torch.randn(B, H, S2, D, dtype=torch.float16)
    qk_ref = torch.einsum('bhsd,bhtd->bhst', q.float(), k.float())

    q_flat = q.reshape(BH * S1, D).contiguous()
    k_flat = k.reshape(BH * S2, D).contiguous()
    qk_flat = torch.zeros(BH * S1, S2, dtype=torch.float32)

    qk_out = OpExec(qk_matmul_batched_kernel, simulator=True)(
        q_flat, k_flat, qk_flat, S1, S2, D, BH)
    qk_out = qk_out.reshape(B, H, S1, S2)

    torch.testing.assert_close(qk_out, qk_ref, rtol=3e-3, atol=3e-3)
    print(f"full_test shape=({B},{H},{S1},{S2},{D}): "
          f"max_abs_diff={torch.abs(qk_out - qk_ref).max().item():.6e}")

if __name__ == "__main__":
    main()
