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
def matmul_gelu_kernel(A, B, D, workspace, M, N, K):
    # ----------------------------------------------------------------------
    # 1. Tiling & Layout Configuration
    # ----------------------------------------------------------------------
    L1_M, L1_N = 128, 256
    DTYPE_C, DTYPE_D = tl.float32, tl.half

    # Global Layouts
    layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
    layout_b = tl.make_layout(tl.make_shape(K, N), tl.make_stride(N, 1))
    layout_c = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))
    layout_d = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))

    # c = a@b
    # d = gelu(c)

    # ----------------------------------------------------------------------
    # 任务核间划分说明
    # ----------------------------------------------------------------------
    # 1) 将输出矩阵按 (M, N) 两个轴同时切分为 grid：
    #       block_m in [0, tile_count_m), block_n in [0, tile_count_n)
    # 2) 每个任务对应一个 L1_M * L1_N 的 tile（边界 tile 为实际尺寸）。
    # 3) 任务按一维 task_id 分配给 AICore：
    #       task_id = aicore_id + t * aicore_num
    #       block_m = task_id // tile_count_n, block_n = task_id % tile_count_n
    # 4) 每个任务内先 cube 做 matmul，再 vector 做 GELU。
    tile_count_m = tl.cdiv(M, L1_M)
    tile_count_n = tl.cdiv(N, L1_N)
    total_tasks = tile_count_m * tile_count_n

    matmul_ready_id = 0

    aicore_id = tl.program_id()
    aicore_num = tl.num_programs()
    num_sub = tl.get_num_sub_blocks()
    subcore_id = tl.get_sub_block_id()
    compute_length = (L1_M // num_sub) * L1_N

    ub_c = tl.alloc_ub(compute_length, dtype=DTYPE_C)
    ub_compute = tl.alloc_ub(compute_length, dtype=DTYPE_C)
    ub_d = tl.alloc_ub(compute_length, dtype=DTYPE_D)

    #   y = x / (1 + exp(NEG_SQRT_EIGHT_OVER_PI * (x^3 + TANH_APPROX_FACTOR * x)))
    NEG_SQRT_EIGHT_OVER_PI = -1.595769121 * 0.044715
    TANH_APPROX_FACTOR = 1.0 / 0.044715

    # ----------------------------------------------------------------------
    # 2. Per-task fused scheduling
    #    One outer loop drives cube and vector phases for one (block_m, block_n) tile.
    # ----------------------------------------------------------------------
    for task_id in range(aicore_id, total_tasks, aicore_num):
        block_m = task_id // tile_count_n
        block_n = task_id % tile_count_n
        actual_m = tl.min(L1_M, M - block_m * L1_M)
        actual_n = tl.min(L1_N, N - block_n * L1_N)

        with tl.scope('cube'):
            actual_block_shape = tl.make_shape(actual_m, actual_n, K)

            coord_a = (block_m * L1_M, 0)
            coord_b = (0, block_n * L1_N)
            coord_c = (block_m * L1_M, block_n * L1_N)

            with tl.compute():
                tl.dot(A[layout_a.get_offset(coord=coord_a)], layout_a,
                       B[layout_b.get_offset(coord=coord_b)], layout_b,
                       workspace[layout_c.get_offset(coord=coord_c)], layout_c,
                       actual_block_shape)

            tl.cross_core_set(matmul_ready_id)

        with tl.scope('vector'):
            tl.cross_core_wait(matmul_ready_id)

            sub_m = tl.cdiv(actual_m, num_sub)
            sub_offset_m = subcore_id * sub_m
            curr_actual_sub_m = tl.min(sub_m, actual_m - sub_offset_m)
            if curr_actual_sub_m <= 0:
                continue

            curr_gm_row = (block_m * L1_M) + sub_offset_m
            curr_gm_col = (block_n * L1_N)

            # UB tile view uses a fixed stride of L1_N in the M dimension (RowMajor tile).
            ub_shape = tl.make_shape(curr_actual_sub_m, actual_n)
            ub_layout = tl.make_layout(ub_shape, tl.make_stride(L1_N, 1))

            gm_c_offset = layout_c.get_offset(coord=(curr_gm_row, curr_gm_col))
            gm_d_offset = layout_d.get_offset(coord=(curr_gm_row, curr_gm_col))

            # --- A. Copy-In (workspace -> ub_c) ---
            with tl.copyin():
                tl.load_2d(workspace[gm_c_offset], tl.make_layout(ub_shape, layout_c.stride()),
                           ub_c, ub_layout
                )

            # --- B. Compute (ub_c -> ub_d via ub_compute) ---
            with tl.compute():
                # ub_compute = x^3
                tl.vmul(ub_compute, ub_c, ub_c, count=compute_length)
                tl.vmul(ub_compute, ub_compute, ub_c, count=compute_length)

                # ub_compute = x^3 + (TANH_APPROX_FACTOR * x)
                tl.vaxpy(ub_compute, ub_c, alpha=TANH_APPROX_FACTOR, count=compute_length)

                # ub_compute = NEG_SQRT_EIGHT_OVER_PI * ub_compute
                tl.vmul_scalar(ub_compute, ub_compute, scalar_value=NEG_SQRT_EIGHT_OVER_PI, count=compute_length)

                # ub_compute = exp(ub_compute); ub_compute = ub_compute + 1; ub_compute = x / ub_compute
                tl.vexp(ub_compute, ub_compute, count=compute_length)
                tl.vadd_scalar(ub_compute, ub_compute, scalar_value=1.0, count=compute_length)
                tl.vdiv(ub_compute, ub_c, ub_compute, count=compute_length)

                # Cast FP32 -> FP16 (output)
                tl.vcast(ub_d, ub_compute, count=compute_length)

            # --- C. Copy-Out (ub_d -> D) ---
            with tl.copyout():
                tl.store_2d(
                    D[gm_d_offset], tl.make_layout(ub_shape, layout_d.stride()),
                    ub_d, ub_layout
                )


# --- Host 调用 ---
def host_main(A: torch.Tensor, B: torch.Tensor, D: torch.Tensor):
    M, K = A.shape
    K, N = B.shape

    workspace = torch.empty(M * N, dtype=torch.float32, device=A.device)
    core_num = tl.get_core_num()

    matmul_gelu_kernel[core_num](
        A, B, D, workspace,
        M, N, K
    )
