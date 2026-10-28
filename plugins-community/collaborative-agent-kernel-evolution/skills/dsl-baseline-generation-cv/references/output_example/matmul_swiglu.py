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
def matmul_swiglu_kernel(A, B, D, workspace, M, N, K):
    # ----------------------------------------------------------------------
    # 1. Tiling & Layout Configuration
    # ----------------------------------------------------------------------
    # N is the HALF width (output width). The matmul produces (M, 2*N).
    TWO_N = 2 * N
    L1_M, L1_N = 128, 256
    DTYPE_C, DTYPE_D = tl.float32, tl.half

    # Global Layouts
    layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
    layout_b = tl.make_layout(tl.make_shape(K, TWO_N), tl.make_stride(TWO_N, 1))
    layout_c = tl.make_layout(tl.make_shape(M, TWO_N), tl.make_stride(TWO_N, 1))
    layout_d = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))

    # c = a@b          shape (M, 2*N)  fp32 in workspace
    # d = swiglu(c)    shape (M, N)    fp16 in D

    # ----------------------------------------------------------------------
    # Task tiling description
    # ----------------------------------------------------------------------
    # 1) Tile the matmul output (M, 2*N) along both axes:
    #       block_m in [0, tile_count_m), block_n in [0, tile_count_n)
    # 2) Each task handles an L1_M x L1_N tile of the full-width matmul output.
    # 3) Tasks are assigned round-robin to AICores:
    #       task_id = aicore_id + t * aicore_num
    #       block_m = task_id // tile_count_n, block_n = task_id % tile_count_n
    # 4) Each task: cube does matmul, vector does SwiGLU and writes half-width output.
    tile_count_m = tl.cdiv(M, L1_M)
    tile_count_n = tl.cdiv(TWO_N, L1_N)
    total_tasks = tile_count_m * tile_count_n

    matmul_ready_id = 0

    aicore_id = tl.program_id()
    aicore_num = tl.num_programs()
    num_sub = tl.get_num_sub_blocks()
    subcore_id = tl.get_sub_block_id()
    compute_length = (L1_M // num_sub) * L1_N

    # UB buffers
    # ub_c: full-width tile from workspace (fp32), holds both left and right halves
    # ub_compute: temp buffer for SiLU computation (fp32)
    # ub_d: half-width output tile (fp16)
    ub_c = tl.alloc_ub(compute_length, dtype=DTYPE_C)
    ub_compute = tl.alloc_ub(compute_length, dtype=DTYPE_C)
    ub_d = tl.alloc_ub(compute_length // 2, dtype=DTYPE_D)

    # ----------------------------------------------------------------------
    # 2. Per-task fused scheduling
    #    One outer loop drives cube and vector phases for one (block_m, block_n) tile.
    # ----------------------------------------------------------------------
    for task_id in range(aicore_id, total_tasks, aicore_num):
        block_m = task_id // tile_count_n
        block_n = task_id % tile_count_n
        actual_m = tl.min(L1_M, M - block_m * L1_M)
        actual_n = tl.min(L1_N, TWO_N - block_n * L1_N)

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

            # The tile covers actual_n columns of the 2*N-wide matmul output.
            # We need to figure out the left/right split within this tile.
            half_n = actual_n // 2

            # UB tile view: full-width tile loaded from workspace
            ub_shape = tl.make_shape(curr_actual_sub_m, actual_n)
            ub_layout = tl.make_layout(ub_shape, tl.make_stride(L1_N, 1))

            # Half-width layout for output
            ub_half_shape = tl.make_shape(curr_actual_sub_m, half_n)
            ub_half_layout = tl.make_layout(ub_half_shape, tl.make_stride(half_n, 1))

            gm_c_offset = layout_c.get_offset(coord=(curr_gm_row, curr_gm_col))

            # Output D offset: each tile spans half_n columns of the N-wide output.
            # The column in D is curr_gm_col // 2 (since the matmul is 2*N wide).
            gm_d_col = curr_gm_col // 2
            gm_d_offset = layout_d.get_offset(coord=(curr_gm_row, gm_d_col))

            sub_compute_length = curr_actual_sub_m * actual_n
            sub_half_length = curr_actual_sub_m * half_n

            # --- A. Copy-In (workspace -> ub_c) ---
            with tl.copyin():
                tl.load_2d(workspace[gm_c_offset], tl.make_layout(ub_shape, layout_c.stride()),
                           ub_c, ub_layout
                )

            # --- B. Compute SwiGLU: silu(left) * right ---
            # The full tile in ub_c has shape (curr_actual_sub_m, actual_n).
            # Left half: columns [0, half_n), Right half: columns [half_n, actual_n).
            # We use UB offset arithmetic to address the two halves in-place.
            with tl.compute():
                # Left half starts at offset 0 within each row, stride L1_N
                # Right half starts at offset half_n within each row, stride L1_N
                # For row-contiguous access we iterate per-row conceptually,
                # but the DSL operates on the flat UB region with stride tricks.

                # Step 1: ub_compute = exp(-left)
                #   Negate left half
                tl.vmul_scalar(ub_compute, ub_c, scalar_value=-1.0, count=sub_half_length,
                               src_stride=L1_N, dst_stride=half_n,
                               src_rep_stride=L1_N, dst_rep_stride=half_n,
                               repeat=curr_actual_sub_m, block_len=half_n)
                #   Exponentiate
                tl.vexp(ub_compute, ub_compute, count=sub_half_length)

                # Step 2: ub_compute = 1 + exp(-left)
                tl.vadd_scalar(ub_compute, ub_compute, scalar_value=1.0, count=sub_half_length)

                # Step 3: ub_compute = left / (1 + exp(-left))  =  silu(left)
                tl.vdiv(ub_compute, ub_c, ub_compute, count=sub_half_length,
                        src0_stride=L1_N, src1_stride=half_n, dst_stride=half_n,
                        src0_rep_stride=L1_N, src1_rep_stride=half_n, dst_rep_stride=half_n,
                        repeat=curr_actual_sub_m, block_len=half_n)

                # Step 4: ub_compute = silu(left) * right
                #   Right half is at ub_c[half_n] with stride L1_N per row
                tl.vmul(ub_compute, ub_compute, ub_c[half_n], count=sub_half_length,
                        src0_stride=half_n, src1_stride=L1_N, dst_stride=half_n,
                        src0_rep_stride=half_n, src1_rep_stride=L1_N, dst_rep_stride=half_n,
                        repeat=curr_actual_sub_m, block_len=half_n)

                # Step 5: Cast fp32 -> fp16
                tl.vcast(ub_d, ub_compute, count=sub_half_length)

            # --- C. Copy-Out (ub_d -> D) ---
            with tl.copyout():
                tl.store_2d(
                    D[gm_d_offset], tl.make_layout(ub_half_shape, layout_d.stride()),
                    ub_d, ub_half_layout
                )


# --- Host call ---
def host_main(A: torch.Tensor, B: torch.Tensor, D: torch.Tensor):
    M, K = A.shape
    K, TWO_N = B.shape
    N = TWO_N // 2

    workspace = torch.empty(M * TWO_N, dtype=torch.float32, device=A.device)
    core_num = tl.get_core_num()

    matmul_swiglu_kernel[core_num](
        A, B, D, workspace,
        M, N, K
    )
