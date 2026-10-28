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
def conv2d_1x1_kernel(A, B, D, M, N, K):
    # ----------------------------------------------------------------------
    # 1. Tiling & Layout Configuration
    # ----------------------------------------------------------------------
    # 1x1 conv is equivalent to matmul:
    #   A = input reshaped to [N*H*W, Cin]  (M x K)
    #   B = weight reshaped to [Cin, Cout]  (K x N)
    #   D = output [N*H*W, Cout]            (M x N)
    L1_M, L1_N = 128, 256
    DTYPE_C = tl.half  # Fixpipe: Cube outputs fp16 directly, no Vector scope needed

    # Global Layouts (row-major 2D after reshape)
    layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
    layout_b = tl.make_layout(tl.make_shape(K, N), tl.make_stride(N, 1))
    layout_d = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))

    # ----------------------------------------------------------------------
    # 任务核间划分说明
    # ----------------------------------------------------------------------
    # 1) 将输出矩阵按 (M, N) 两个轴切分为 grid：
    #       block_m in [0, tile_count_m), block_n in [0, tile_count_n)
    # 2) 每个任务对应一个 L1_M * L1_N 的 tile。
    # 3) 任务按一维 task_id 分配给 AICore。
    # 4) Fixpipe 模式：Cube 直接输出 fp16，无 Vector scope。
    tile_count_m = tl.cdiv(M, L1_M)
    tile_count_n = tl.cdiv(N, L1_N)
    total_tasks = tile_count_m * tile_count_n

    aicore_id = tl.program_id()
    aicore_num = tl.num_programs()

    # ----------------------------------------------------------------------
    # 2. Per-task Fixpipe scheduling (Cube-only, no Vector)
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
            coord_d = (block_m * L1_M, block_n * L1_N)

            with tl.compute():
                tl.dot(A[layout_a.get_offset(coord=coord_a)], layout_a,
                       B[layout_b.get_offset(coord=coord_b)], layout_b,
                       D[layout_d.get_offset(coord=coord_d)], layout_d,
                       actual_block_shape)


# --- Host 调用 ---
def host_main(x: torch.Tensor, weight: torch.Tensor, D: torch.Tensor):
    N_batch, Cin, H, W = x.shape
    Cout = weight.shape[0]

    # 1x1 conv reshape: fmap [N,Cin,H,W] → A [N*H*W, Cin]
    M = N_batch * H * W
    K = Cin
    N_out = Cout
    A = x.permute(0, 2, 3, 1).reshape(M, K).contiguous()
    # weight [Cout, Cin, 1, 1] → B [Cin, Cout]
    B = weight.squeeze(-1).squeeze(-1).t().contiguous()

    core_num = tl.get_core_num()

    conv2d_1x1_kernel[core_num](
        A, B, D,
        M, N_out, K
    )
    # Output D is [M, Cout], reshape back to [N, Cout, H, W] by caller
