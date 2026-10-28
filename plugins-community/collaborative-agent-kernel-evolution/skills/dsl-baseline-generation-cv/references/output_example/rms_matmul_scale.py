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
def rms_matmul_scale_kernel(x, weight, out, workspace_mm, workspace_inv, M, K, O, norm_eps):
    # ----------------------------------------------------------------------
    # 1. Tiling & Layout Configuration
    # ----------------------------------------------------------------------
    L1_M, L1_N = 128, 256
    K_TILE = 1024  # K轴在vector侧的UB分块大小
    DTYPE_X = tl.half
    DTYPE_MM = tl.float32
    DTYPE_OUT = tl.half

    layout_x = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
    layout_w = tl.make_layout(tl.make_shape(K, O), tl.make_stride(O, 1))
    layout_mm = tl.make_layout(tl.make_shape(M, O), tl.make_stride(O, 1))
    layout_out = tl.make_layout(tl.make_shape(M, O), tl.make_stride(O, 1))

    # ----------------------------------------------------------------------
    # 任务核间划分说明
    # ----------------------------------------------------------------------
    # 1) 将 M 轴（即 B*S）按 L1_M 切成 tile_count_m 个 block_m 任务。
    # 2) 每个 AICore 以步长方式领取 block_m: block_m = aicore_id + t * aicore_num。
    # 3) 每个 block_m 内：
    #    - Cube 负责该行块所有 N 方向分块的 matmul，写入 workspace_mm。
    #    - 两个 Vector subcore 负责该行块的 inv_rms，写入 workspace_inv。
    #    - matmul 与 inv_rms 完成后，Vector 执行逐元素乘法并写回 out。
    tile_count_m = tl.cdiv(M, L1_M)
    tile_count_n = tl.cdiv(O, L1_N)

    matmul_done_id = 0

    aicore_id = tl.program_id()
    aicore_num = tl.num_programs()

    # ----------------------------------------------------------------------
    # 2. Per-block_m fused scheduling
    #    One outer loop drives cube and vector tasks for the same block_m.
    # ----------------------------------------------------------------------
    for block_m in range(aicore_id, tile_count_m, aicore_num):
        actual_m = tl.min(L1_M, M - block_m * L1_M)

        with tl.scope("cube"):
            for block_n in range(tile_count_n):
                actual_n = tl.min(L1_N, O - block_n * L1_N)
                actual_shape = tl.make_shape(actual_m, actual_n, K)

                coord_x = (block_m * L1_M, 0)
                coord_w = (0, block_n * L1_N)
                coord_mm = (block_m * L1_M, block_n * L1_N)

                with tl.compute():
                    tl.dot(
                        x[layout_x.get_offset(coord=coord_x)],
                        layout_x,
                        weight[layout_w.get_offset(coord=coord_w)],
                        layout_w,
                        workspace_mm[layout_mm.get_offset(coord=coord_mm)],
                        layout_mm,
                        actual_shape,
                    )

            tl.cross_core_set(matmul_done_id)

        with tl.scope("vector"):
            num_sub = tl.get_num_sub_blocks()  # expected 2
            subcore_id = tl.get_sub_block_id()

            x_ub = tl.alloc_ub(K_TILE, dtype=DTYPE_X)
            x_fp32_ub = tl.alloc_ub(K_TILE, dtype=DTYPE_MM)
            sq_ub = tl.alloc_ub(K_TILE, dtype=DTYPE_MM)
            reduce_ub = tl.alloc_ub(K_TILE, dtype=DTYPE_MM)
            mm_ub = tl.alloc_ub(L1_N, dtype=DTYPE_MM)
            out_ub = tl.alloc_ub(L1_N, dtype=DTYPE_OUT)
            scalar_ub = tl.alloc_ub(1, dtype=DTYPE_MM)

            sub_m = tl.cdiv(actual_m, num_sub)
            sub_offset_m = subcore_id * sub_m
            curr_m = tl.min(sub_m, actual_m - sub_offset_m)

            if curr_m > 0:
                row_start = block_m * L1_M + sub_offset_m

                # A) inv_rms for this subcore's rows (parallel with cube matmul)
                for r in range(curr_m):
                    row_id = row_start + r
                    row_sum_sq = 0.0

                    for k_base in range(0, K, K_TILE):
                        k_len = tl.min(K_TILE, K - k_base)
                        gm_x_offset = layout_x.get_offset(coord=(row_id, k_base))

                        with tl.copyin():
                            tl.load(x[gm_x_offset + tl.arange(0, k_len)], x_ub)

                        with tl.compute():
                            tl.vcast(x_fp32_ub, x_ub, count=k_len)
                            tl.vmul(sq_ub, x_fp32_ub, x_fp32_ub, count=k_len)
                            tl.reduce_sum(reduce_ub, sq_ub, reduce_ub)
                            row_sum_sq = row_sum_sq + tl.extract_scalar(reduce_ub, 0)

                    row_mean = row_sum_sq / float(K)
                    row_inv_rms = (row_mean + norm_eps) ** (-0.5)

                    with tl.copyout():
                        tl.set_scalar(scalar_ub, 0, row_inv_rms)
                        tl.store(workspace_inv + tl.arange(row_id, row_id + 1), scalar_ub)

            # B) wait for cube matmul of this block_m to complete
            tl.cross_core_wait(matmul_done_id)

            # C) scale: out[row, :] = inv_rms[row] * matmul[row, :]
            if curr_m > 0:
                for r in range(curr_m):
                    row_id = row_start + r

                    with tl.copyin():
                        tl.load(workspace_inv + tl.arange(row_id, row_id + 1), scalar_ub)
                    inv_rms_row = tl.extract_scalar(scalar_ub, 0)

                    for block_n in range(tile_count_n):
                        col_start = block_n * L1_N
                        curr_n = tl.min(L1_N, O - col_start)

                        gm_mm_offset = layout_mm.get_offset(coord=(row_id, col_start))
                        gm_out_offset = layout_out.get_offset(coord=(row_id, col_start))

                        with tl.copyin():
                            tl.load(workspace_mm[gm_mm_offset + tl.arange(0, curr_n)], mm_ub)

                        with tl.compute():
                            tl.vmul_scalar(mm_ub, mm_ub, scalar_value=inv_rms_row, count=curr_n)
                            tl.vcast(out_ub, mm_ub, count=curr_n)

                        with tl.copyout():
                            tl.store(out[gm_out_offset + tl.arange(0, curr_n)], out_ub)


def host_main(x: torch.Tensor, weight: torch.Tensor, out: torch.Tensor, norm_eps: float = 1e-6):
    # x: [B, S, N, D] (contiguous in D), viewed as [M, K] where M=B*S, K=N*D
    # weight: [K, O]
    b, s, n, d = x.shape
    m = b * s
    k = n * d
    o = weight.shape[1]

    workspace_mm = torch.empty(m * o, dtype=torch.float32, device=x.device)
    workspace_inv = torch.empty(m, dtype=torch.float32, device=x.device)
    core_num = tl.get_core_num()

    rms_matmul_scale_kernel[core_num](
        x,
        weight,
        out,
        workspace_mm,
        workspace_inv,
        m,
        k,
        o,
        norm_eps,
    )
