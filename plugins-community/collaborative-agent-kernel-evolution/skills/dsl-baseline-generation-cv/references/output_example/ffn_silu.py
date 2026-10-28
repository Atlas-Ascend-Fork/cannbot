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
def ffn_silu_kernel(X, W1, W2, Y, workspace_mm1, workspace_act, workspace_mm2, M, N1, N2, K):
    # ----------------------------------------------------------------------
    # 1. Tiling & Layout Configuration
    # ----------------------------------------------------------------------
    # FFN: X @ W1 → SiLU → @ W2 → Y
    # Stage 1 (Cube):   MM1: X(M,K) @ W1(K,N1) → workspace_mm1(M,N1) fp32
    # Stage 2 (Vector):  SiLU(workspace_mm1) → workspace_act(M,N1) fp16
    # Stage 3 (Cube):   MM2: workspace_act(M,N1) @ W2(N1,N2) → workspace_mm2(M,N2) fp32
    # Stage 4 (Vector):  Cast(workspace_mm2) → Y(M,N2) fp16

    L1_M, L1_N = 128, 256
    DTYPE_MM = tl.float32
    DTYPE_ACT = tl.half
    DTYPE_OUT = tl.half

    layout_x = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
    layout_w1 = tl.make_layout(tl.make_shape(K, N1), tl.make_stride(N1, 1))
    layout_mm1 = tl.make_layout(tl.make_shape(M, N1), tl.make_stride(N1, 1))
    layout_act = tl.make_layout(tl.make_shape(M, N1), tl.make_stride(N1, 1))
    layout_w2 = tl.make_layout(tl.make_shape(N1, N2), tl.make_stride(N2, 1))
    layout_mm2 = tl.make_layout(tl.make_shape(M, N2), tl.make_stride(N2, 1))
    layout_y = tl.make_layout(tl.make_shape(M, N2), tl.make_stride(N2, 1))

    # ----------------------------------------------------------------------
    # 数据依赖图（Data Dependency DAG）
    # ----------------------------------------------------------------------
    # [Cube] MM1(X, W1) → ws_mm1 ──sync(mm1_done)──→ [Vector] SiLU(ws_mm1) → ws_act
    #                                                    ──sync(act_done)──→
    # [Cube] MM2(ws_act, W2) → ws_mm2 ──sync(mm2_done)──→ [Vector] Cast(ws_mm2) → Y
    #
    # 同步事件：3 个 cross-core events
    # Workspace：3 段（ws_mm1: M×N1×4, ws_act: M×N1×2, ws_mm2: M×N2×4）
    # UB 复用：Stage 2 和 Stage 4 的 UB 可顺序复用（阶段间不重叠）

    tile_count_m = tl.cdiv(M, L1_M)
    tile_count_n1 = tl.cdiv(N1, L1_N)
    tile_count_n2 = tl.cdiv(N2, L1_N)

    mm1_done_id = 0
    act_done_id = 1
    mm2_done_id = 2

    aicore_id = tl.program_id()
    aicore_num = tl.num_programs()
    num_sub = tl.get_num_sub_blocks()
    subcore_id = tl.get_sub_block_id()

    # UB buffers (reused across stages, peak ~64KB per stage within 192KB)
    compute_length = (L1_M // num_sub) * L1_N
    ub_in = tl.alloc_ub(compute_length, dtype=DTYPE_MM)
    ub_compute = tl.alloc_ub(compute_length, dtype=DTYPE_MM)
    ub_out = tl.alloc_ub(compute_length, dtype=DTYPE_ACT)

    # ----------------------------------------------------------------------
    # 2. Per-block_m fused 4-stage scheduling
    # ----------------------------------------------------------------------
    for block_m in range(aicore_id, tile_count_m, aicore_num):
        actual_m = tl.min(L1_M, M - block_m * L1_M)

        # ============ Stage 1: Cube MM1 (X @ W1 → workspace_mm1) ============
        with tl.scope('cube'):
            for block_n in range(tile_count_n1):
                actual_n1 = tl.min(L1_N, N1 - block_n * L1_N)
                actual_shape = tl.make_shape(actual_m, actual_n1, K)

                coord_x = (block_m * L1_M, 0)
                coord_w1 = (0, block_n * L1_N)
                coord_mm1 = (block_m * L1_M, block_n * L1_N)

                with tl.compute():
                    tl.dot(
                        X[layout_x.get_offset(coord=coord_x)], layout_x,
                        W1[layout_w1.get_offset(coord=coord_w1)], layout_w1,
                        workspace_mm1[layout_mm1.get_offset(coord=coord_mm1)], layout_mm1,
                        actual_shape,
                    )

            tl.cross_core_set(mm1_done_id)

        # ============ Stage 2: Vector SiLU (workspace_mm1 → workspace_act) ============
        with tl.scope('vector'):
            tl.cross_core_wait(mm1_done_id)

            sub_m = tl.cdiv(actual_m, num_sub)
            sub_offset_m = subcore_id * sub_m
            curr_sub_m = tl.min(sub_m, actual_m - sub_offset_m)

            if curr_sub_m > 0:
                curr_gm_row = (block_m * L1_M) + sub_offset_m

                for block_n in range(tile_count_n1):
                    col_start = block_n * L1_N
                    curr_n1 = tl.min(L1_N, N1 - col_start)

                    ub_shape = tl.make_shape(curr_sub_m, curr_n1)
                    ub_layout = tl.make_layout(ub_shape, tl.make_stride(L1_N, 1))

                    gm_mm1_offset = layout_mm1.get_offset(coord=(curr_gm_row, col_start))
                    gm_act_offset = layout_act.get_offset(coord=(curr_gm_row, col_start))

                    with tl.copyin():
                        tl.load_2d(workspace_mm1[gm_mm1_offset],
                                   tl.make_layout(ub_shape, layout_mm1.stride()),
                                   ub_in, ub_layout)

                    with tl.compute():
                        sub_length = curr_sub_m * curr_n1
                        # SiLU(x) = x / (1 + exp(-x))
                        tl.vmul_scalar(ub_compute, ub_in, scalar_value=-1.0, count=sub_length)
                        tl.vexp(ub_compute, ub_compute, count=sub_length)
                        tl.vadd_scalar(ub_compute, ub_compute, scalar_value=1.0, count=sub_length)
                        tl.vdiv(ub_compute, ub_in, ub_compute, count=sub_length)
                        # Cast fp32 → fp16
                        tl.vcast(ub_out, ub_compute, count=sub_length)

                    with tl.copyout():
                        tl.store_2d(workspace_act[gm_act_offset],
                                    tl.make_layout(ub_shape, layout_act.stride()),
                                    ub_out, ub_layout)

            tl.cross_core_set(act_done_id)

        # ============ Stage 3: Cube MM2 (workspace_act @ W2 → workspace_mm2) ============
        with tl.scope('cube'):
            tl.cross_core_wait(act_done_id)

            for block_n in range(tile_count_n2):
                actual_n2 = tl.min(L1_N, N2 - block_n * L1_N)
                actual_shape2 = tl.make_shape(actual_m, actual_n2, N1)

                coord_act = (block_m * L1_M, 0)
                coord_w2 = (0, block_n * L1_N)
                coord_mm2 = (block_m * L1_M, block_n * L1_N)

                with tl.compute():
                    tl.dot(
                        workspace_act[layout_act.get_offset(coord=coord_act)], layout_act,
                        W2[layout_w2.get_offset(coord=coord_w2)], layout_w2,
                        workspace_mm2[layout_mm2.get_offset(coord=coord_mm2)], layout_mm2,
                        actual_shape2,
                    )

            tl.cross_core_set(mm2_done_id)

        # ============ Stage 4: Vector Cast (workspace_mm2 → Y) ============
        with tl.scope('vector'):
            tl.cross_core_wait(mm2_done_id)

            # Reuse UB buffers from Stage 2 (stage-sequential reuse)
            if curr_sub_m > 0:
                for block_n in range(tile_count_n2):
                    col_start = block_n * L1_N
                    curr_n2 = tl.min(L1_N, N2 - col_start)

                    ub_shape2 = tl.make_shape(curr_sub_m, curr_n2)
                    ub_layout2 = tl.make_layout(ub_shape2, tl.make_stride(L1_N, 1))

                    gm_mm2_offset = layout_mm2.get_offset(coord=(curr_gm_row, col_start))
                    gm_y_offset = layout_y.get_offset(coord=(curr_gm_row, col_start))

                    with tl.copyin():
                        tl.load_2d(workspace_mm2[gm_mm2_offset],
                                   tl.make_layout(ub_shape2, layout_mm2.stride()),
                                   ub_in, ub_layout2)

                    with tl.compute():
                        sub_length2 = curr_sub_m * curr_n2
                        tl.vcast(ub_out, ub_in, count=sub_length2)

                    with tl.copyout():
                        tl.store_2d(Y[gm_y_offset],
                                    tl.make_layout(ub_shape2, layout_y.stride()),
                                    ub_out, ub_layout2)


# --- Host 调用 ---
def host_main(X: torch.Tensor, W1: torch.Tensor, W2: torch.Tensor, Y: torch.Tensor):
    M, K = X.shape
    K, N1 = W1.shape
    N1, N2 = W2.shape

    # 3 workspace segments:
    # ws_mm1:  M × N1 × sizeof(fp32) — matmul1 output accumulator
    # ws_act:  M × N1 × sizeof(fp16) — activation output (Cube input for MM2)
    # ws_mm2:  M × N2 × sizeof(fp32) — matmul2 output accumulator
    workspace_mm1 = torch.empty(M * N1, dtype=torch.float32, device=X.device)
    workspace_act = torch.empty(M * N1, dtype=torch.float16, device=X.device)
    workspace_mm2 = torch.empty(M * N2, dtype=torch.float32, device=X.device)
    core_num = tl.get_core_num()

    ffn_silu_kernel[core_num](
        X, W1, W2, Y,
        workspace_mm1, workspace_act, workspace_mm2,
        M, N1, N2, K
    )
