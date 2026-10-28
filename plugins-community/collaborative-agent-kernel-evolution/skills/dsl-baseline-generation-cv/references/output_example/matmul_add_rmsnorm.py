# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

import tile.language as tl
import torch


@ascend_kernel
def matmul_add_rmsnorm_kernel(A, B, residual, gamma, Y, X_add, workspace, M, N, K, norm_eps):
    # ----------------------------------------------------------------------
    # 1. Tiling & Layout Configuration
    # ----------------------------------------------------------------------
    L1_M, L1_N = 128, 256
    K_TILE = 1024
    DTYPE_C, DTYPE_D = tl.float32, tl.half

    layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
    layout_b = tl.make_layout(tl.make_shape(K, N), tl.make_stride(N, 1))
    layout_c = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
    layout_res = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
    layout_y = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
    layout_xadd = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))

    # c = a @ b
    # x_add = c + residual
    # y = rmsnorm(x_add) * gamma

    # ----------------------------------------------------------------------
    # 任务核间划分说明
    # ----------------------------------------------------------------------
    # 1) 将 M 轴按 L1_M 切成 tile_count_m 个 block_m 任务。
    # 2) 每个 block_m 内 Cube 负责所有 N 方向的 matmul。
    # 3) Vector 负责 residual add + RmsNorm，逐行处理（需要 reduction）。
    # 4) 输出两个 tensor：Y（归一化后）和 X_add（归一化前的 add 结果）。
    tile_count_m = tl.cdiv(M, L1_M)
    tile_count_n = tl.cdiv(N, L1_N)

    matmul_done_id = 0

    aicore_id = tl.program_id()
    aicore_num = tl.num_programs()

    # UB buffers for vector processing
    ub_mm_row = tl.alloc_ub(L1_N, dtype=DTYPE_C)
    ub_res_row = tl.alloc_ub(L1_N, dtype=DTYPE_D)
    ub_res_fp32 = tl.alloc_ub(L1_N, dtype=DTYPE_C)
    ub_add_row = tl.alloc_ub(L1_N, dtype=DTYPE_C)
    ub_gamma = tl.alloc_ub(L1_N, dtype=DTYPE_D)
    ub_gamma_fp32 = tl.alloc_ub(L1_N, dtype=DTYPE_C)
    ub_sq = tl.alloc_ub(L1_N, dtype=DTYPE_C)
    ub_reduce = tl.alloc_ub(L1_N, dtype=DTYPE_C)
    ub_y = tl.alloc_ub(L1_N, dtype=DTYPE_D)
    ub_xadd_out = tl.alloc_ub(L1_N, dtype=DTYPE_D)

    # ----------------------------------------------------------------------
    # 2. Per-block_m fused scheduling
    # ----------------------------------------------------------------------
    for block_m in range(aicore_id, tile_count_m, aicore_num):
        actual_m = tl.min(L1_M, M - block_m * L1_M)

        # --- Cube: matmul for all N tiles in this block_m ---
        with tl.scope('cube'):
            for block_n in range(tile_count_n):
                actual_n = tl.min(L1_N, N - block_n * L1_N)
                actual_shape = tl.make_shape(actual_m, actual_n, K)

                coord_a = (block_m * L1_M, 0)
                coord_b = (0, block_n * L1_N)
                coord_c = (block_m * L1_M, block_n * L1_N)

                with tl.compute():
                    tl.dot(
                        A[layout_a.get_offset(coord=coord_a)], layout_a,
                        B[layout_b.get_offset(coord=coord_b)], layout_b,
                        workspace[layout_c.get_offset(coord=coord_c)], layout_c,
                        actual_shape,
                    )

            tl.cross_core_set(matmul_done_id)

        # --- Vector: residual add + RmsNorm (per-row processing) ---
        with tl.scope('vector'):
            tl.cross_core_wait(matmul_done_id)

            num_sub = tl.get_num_sub_blocks()
            subcore_id = tl.get_sub_block_id()
            sub_m = tl.cdiv(actual_m, num_sub)
            sub_offset_m = subcore_id * sub_m
            curr_m = tl.min(sub_m, actual_m - sub_offset_m)

            if curr_m > 0:
                row_start = block_m * L1_M + sub_offset_m

                for r in range(curr_m):
                    row_id = row_start + r

                    # Step 1: Load matmul result row-by-row, add residual, compute sum_sq
                    row_sum_sq = 0.0

                    for block_n in range(tile_count_n):
                        col_start = block_n * L1_N
                        curr_n = tl.min(L1_N, N - col_start)

                        gm_mm_offset = layout_c.get_offset(coord=(row_id, col_start))
                        gm_res_offset = layout_res.get_offset(coord=(row_id, col_start))

                        with tl.copyin():
                            tl.load(workspace[gm_mm_offset + tl.arange(0, curr_n)], ub_mm_row)
                            tl.load(residual[gm_res_offset + tl.arange(0, curr_n)], ub_res_row)

                        with tl.compute():
                            # Cast residual to fp32 and add
                            tl.vcast(ub_res_fp32, ub_res_row, count=curr_n)
                            tl.vadd(ub_add_row, ub_mm_row, ub_res_fp32, count=curr_n)

                            # Store x_add (fp16) for output
                            tl.vcast(ub_xadd_out, ub_add_row, count=curr_n)

                            # Accumulate sum of squares for RmsNorm
                            tl.vmul(ub_sq, ub_add_row, ub_add_row, count=curr_n)
                            tl.reduce_sum(ub_reduce, ub_sq, ub_reduce)
                            row_sum_sq = row_sum_sq + tl.extract_scalar(ub_reduce, 0)

                        with tl.copyout():
                            gm_xadd_offset = layout_xadd.get_offset(coord=(row_id, col_start))
                            tl.store(X_add[gm_xadd_offset + tl.arange(0, curr_n)], ub_xadd_out)

                    # Step 2: Compute inv_rms for this row
                    row_mean_sq = row_sum_sq / float(N)
                    inv_rms = (row_mean_sq + norm_eps) ** (-0.5)

                    # Step 3: Normalize and apply gamma, store Y
                    for block_n in range(tile_count_n):
                        col_start = block_n * L1_N
                        curr_n = tl.min(L1_N, N - col_start)

                        gm_xadd_offset = layout_xadd.get_offset(coord=(row_id, col_start))
                        gm_y_offset = layout_y.get_offset(coord=(row_id, col_start))

                        with tl.copyin():
                            tl.load(X_add[gm_xadd_offset + tl.arange(0, curr_n)], ub_xadd_out)
                            tl.load(gamma[col_start + tl.arange(0, curr_n)], ub_gamma)

                        with tl.compute():
                            tl.vcast(ub_add_row, ub_xadd_out, count=curr_n)  # fp16→fp32
                            tl.vmul_scalar(ub_add_row, ub_add_row, scalar_value=inv_rms, count=curr_n)
                            tl.vcast(ub_gamma_fp32, ub_gamma, count=curr_n)
                            tl.vmul(ub_add_row, ub_add_row, ub_gamma_fp32, count=curr_n)
                            tl.vcast(ub_y, ub_add_row, count=curr_n)

                        with tl.copyout():
                            tl.store(Y[gm_y_offset + tl.arange(0, curr_n)], ub_y)


# --- Host 调用 ---
def host_main(A: torch.Tensor, B: torch.Tensor, residual: torch.Tensor,
              gamma: torch.Tensor, Y: torch.Tensor, X_add: torch.Tensor, norm_eps: float = 1e-6):
    M, K = A.shape
    K, N = B.shape

    workspace = torch.empty(M * N, dtype=torch.float32, device=A.device)
    core_num = tl.get_core_num()

    matmul_add_rmsnorm_kernel[core_num](
        A, B, residual, gamma, Y, X_add, workspace,
        M, N, K, norm_eps
    )
