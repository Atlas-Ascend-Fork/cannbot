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

import tile.language as tl
import torch


@ascend_kernel
def flash_attn_basic_kernel(Q, K, V, O, workspace_score, workspace_prob,
                             workspace_out, workspace_max, workspace_sum,
                             M, N, D, Bk, scale):
    # ----------------------------------------------------------------------
    # 1. Tiling & Layout Configuration
    # ----------------------------------------------------------------------
    # Flash Attention (basic, single-head, no causal mask):
    #   Per KV block b:
    #     [Cube]  S_b = Q @ K_b^T        (M, Bk) fp32
    #     [Vector] P_b = online_softmax(S_b, running_max, running_sum)  (M, Bk) fp16
    #     [Cube]  O_b = P_b @ V_b        (M, D) fp32
    #     [Vector] O += scale * O_b       (accumulate with rescaling)
    #   After all KV blocks:
    #     [Vector] O = O / running_sum    (final normalize)

    L1_M = 128
    DTYPE_SCORE = tl.float32
    DTYPE_PROB = tl.half
    DTYPE_OUT = tl.float32
    DTYPE_FINAL = tl.half

    layout_q = tl.make_layout(tl.make_shape(M, D), tl.make_stride(D, 1))
    layout_k = tl.make_layout(tl.make_shape(N, D), tl.make_stride(D, 1))  # K stored as (N, D)
    layout_v = tl.make_layout(tl.make_shape(N, D), tl.make_stride(D, 1))
    layout_score = tl.make_layout(tl.make_shape(M, Bk), tl.make_stride(Bk, 1))
    layout_prob = tl.make_layout(tl.make_shape(M, Bk), tl.make_stride(Bk, 1))
    layout_out = tl.make_layout(tl.make_shape(M, D), tl.make_stride(D, 1))
    layout_o = tl.make_layout(tl.make_shape(M, D), tl.make_stride(D, 1))

    # ----------------------------------------------------------------------
    # 数据依赖图（Data Dependency DAG）—— 每个 KV block 内
    # ----------------------------------------------------------------------
    # [Cube] Q(M,D) @ K_b(Bk,D)^T → ws_score(M,Bk) fp32
    #     ──sync(score_ready)──→
    # [Vector] online_softmax(ws_score, max, sum) → ws_prob(M,Bk) fp16
    #     ──sync(prob_ready)──→
    # [Cube] ws_prob(M,Bk) @ V_b(Bk,D) → ws_out(M,D) fp32
    #     ──sync(out_ready)──→
    # [Vector] O = O * rescale + ws_out, update max/sum
    #     ──sync(update_done)──→  [next KV block]
    #
    # 同步事件：4 per KV block iteration (score_ready, prob_ready, out_ready, update_done)
    # Workspace：ws_score(M×Bk×4), ws_prob(M×Bk×2), ws_out(M×D×4), max(M×4), sum(M×4)

    kv_blocks = tl.cdiv(N, Bk)

    score_ready_id = 0
    prob_ready_id = 1
    out_ready_id = 2
    update_done_id = 3

    aicore_id = tl.program_id()
    aicore_num = tl.num_programs()
    num_sub = tl.get_num_sub_blocks()
    subcore_id = tl.get_sub_block_id()

    # UB buffers for vector processing (reused across KV block iterations)
    # Peak UB: score_tile + prob_tile + reduce_temps ≈ 128KB (within 192KB)
    ub_score_row = tl.alloc_ub(Bk, dtype=DTYPE_SCORE)
    ub_prob_row = tl.alloc_ub(Bk, dtype=DTYPE_PROB)
    ub_reduce = tl.alloc_ub(Bk, dtype=DTYPE_SCORE)
    ub_out_row = tl.alloc_ub(D, dtype=DTYPE_OUT)
    ub_acc_row = tl.alloc_ub(D, dtype=DTYPE_OUT)
    ub_final = tl.alloc_ub(D, dtype=DTYPE_FINAL)
    ub_scalar = tl.alloc_ub(1, dtype=DTYPE_SCORE)

    # ----------------------------------------------------------------------
    # 2. Per-block_m scheduling (core-parallel over M dimension)
    # ----------------------------------------------------------------------
    tile_count_m = tl.cdiv(M, L1_M)

    for block_m in range(aicore_id, tile_count_m, aicore_num):
        actual_m = tl.min(L1_M, M - block_m * L1_M)
        row_start = block_m * L1_M

        # Initialize running max to -inf, running sum to 0
        sub_m = tl.cdiv(actual_m, num_sub)
        sub_offset_m = subcore_id * sub_m
        curr_sub_m = tl.min(sub_m, actual_m - sub_offset_m)

        # --- KV block iteration (core computation loop) ---
        for kv_b in range(kv_blocks):
            kv_start = kv_b * Bk
            actual_bk = tl.min(Bk, N - kv_start)

            # ============ Cube: Q @ K_b^T → workspace_score ============
            with tl.scope('cube'):
                if kv_b > 0:
                    tl.cross_core_wait(update_done_id)

                actual_shape_bmm1 = tl.make_shape(actual_m, actual_bk, D)

                coord_q = (row_start, 0)
                coord_k = (kv_start, 0)  # K is (N, D), we need K_b rows [kv_start:kv_start+Bk]
                coord_s = (row_start, 0)

                with tl.compute():
                    # Q(M,D) @ K_b^T(D,Bk) → S(M,Bk)
                    # Note: K is stored as (N,D), transpose gives (D,Bk)
                    tl.dot(
                        Q[layout_q.get_offset(coord=coord_q)], layout_q,
                        K[layout_k.get_offset(coord=coord_k)], layout_k,
                        workspace_score[layout_score.get_offset(coord=coord_s)], layout_score,
                        actual_shape_bmm1,
                    )

                tl.cross_core_set(score_ready_id)

            # ============ Vector: online softmax ============
            with tl.scope('vector'):
                tl.cross_core_wait(score_ready_id)

                if curr_sub_m > 0:
                    gm_row_base = row_start + sub_offset_m

                    for r in range(curr_sub_m):
                        row_id = gm_row_base + r
                        gm_score_offset = layout_score.get_offset(coord=(row_id, 0))

                        with tl.copyin():
                            tl.load(workspace_score[gm_score_offset + tl.arange(0, actual_bk)], ub_score_row)

                        with tl.compute():
                            # Scale: S = S * scale
                            tl.vmul_scalar(ub_score_row, ub_score_row, scalar_value=scale, count=actual_bk)

                            # Row max
                            tl.reduce_max(ub_reduce, ub_score_row, ub_reduce)
                            new_max = tl.extract_scalar(ub_reduce, 0)

                            # Load running max
                            with tl.copyin():
                                tl.load(workspace_max[row_id + tl.arange(0, 1)], ub_scalar)
                            old_max = tl.extract_scalar(ub_scalar, 0)

                            if kv_b == 0:
                                running_max = new_max
                            else:
                                running_max = max(old_max, new_max)

                            # exp(score - running_max)
                            tl.vadd_scalar(ub_score_row, ub_score_row, scalar_value=-running_max, count=actual_bk)
                            tl.vexp(ub_score_row, ub_score_row, count=actual_bk)

                            # Row sum of exp
                            tl.reduce_sum(ub_reduce, ub_score_row, ub_reduce)
                            new_sum = tl.extract_scalar(ub_reduce, 0)

                            # Rescale factor for previous accumulator
                            if kv_b > 0:
                                rescale = math.exp(old_max - running_max)
                                # Load running sum, rescale
                                with tl.copyin():
                                    tl.load(workspace_sum[row_id + tl.arange(0, 1)], ub_scalar)
                                old_sum = tl.extract_scalar(ub_scalar, 0)
                                running_sum = old_sum * rescale + new_sum

                                # Rescale output accumulator: O[row] *= rescale
                                with tl.copyin():
                                    tl.load(O[layout_o.get_offset(coord=(row_id, 0)) + tl.arange(0, D)], ub_acc_row)
                                tl.vmul_scalar(ub_acc_row, ub_acc_row, scalar_value=rescale, count=D)
                                with tl.copyout():
                                    tl.store(O[layout_o.get_offset(coord=(row_id, 0)) + tl.arange(0, D)], ub_acc_row)
                            else:
                                running_sum = new_sum

                            # Store updated max and sum
                            tl.set_scalar(ub_scalar, 0, running_max)
                            with tl.copyout():
                                tl.store(workspace_max[row_id + tl.arange(0, 1)], ub_scalar)
                            tl.set_scalar(ub_scalar, 0, running_sum)
                            with tl.copyout():
                                tl.store(workspace_sum[row_id + tl.arange(0, 1)], ub_scalar)

                            # Cast prob to fp16 for next matmul
                            tl.vcast(ub_prob_row, ub_score_row, count=actual_bk)

                        gm_prob_offset = layout_prob.get_offset(coord=(row_id, 0))
                        with tl.copyout():
                            tl.store(workspace_prob[gm_prob_offset + tl.arange(0, actual_bk)], ub_prob_row)

                tl.cross_core_set(prob_ready_id)

            # ============ Cube: P_b @ V_b → workspace_out ============
            with tl.scope('cube'):
                tl.cross_core_wait(prob_ready_id)

                actual_shape_bmm2 = tl.make_shape(actual_m, D, actual_bk)

                coord_p = (row_start, 0)
                coord_v = (kv_start, 0)
                coord_o = (row_start, 0)

                with tl.compute():
                    # P(M,Bk) @ V_b(Bk,D) → O_partial(M,D)
                    tl.dot(
                        workspace_prob[layout_prob.get_offset(coord=coord_p)], layout_prob,
                        V[layout_v.get_offset(coord=coord_v)], layout_v,
                        workspace_out[layout_out.get_offset(coord=coord_o)], layout_out,
                        actual_shape_bmm2,
                    )

                tl.cross_core_set(out_ready_id)

            # ============ Vector: O += O_partial ============
            with tl.scope('vector'):
                tl.cross_core_wait(out_ready_id)

                if curr_sub_m > 0:
                    for r in range(curr_sub_m):
                        row_id = gm_row_base + r
                        gm_out_offset = layout_out.get_offset(coord=(row_id, 0))
                        gm_o_offset = layout_o.get_offset(coord=(row_id, 0))

                        with tl.copyin():
                            tl.load(workspace_out[gm_out_offset + tl.arange(0, D)], ub_out_row)
                            tl.load(O[gm_o_offset + tl.arange(0, D)], ub_acc_row)

                        with tl.compute():
                            # O = O + O_partial  (O was already rescaled in softmax stage)
                            tl.vadd(ub_acc_row, ub_acc_row, ub_out_row, count=D)

                        with tl.copyout():
                            tl.store(O[gm_o_offset + tl.arange(0, D)], ub_acc_row)

                tl.cross_core_set(update_done_id)

        # --- After all KV blocks: final normalize O = O / running_sum ---
        with tl.scope('vector'):
            if curr_sub_m > 0:
                for r in range(curr_sub_m):
                    row_id = (row_start + sub_offset_m) + r
                    gm_o_offset = layout_o.get_offset(coord=(row_id, 0))

                    with tl.copyin():
                        tl.load(workspace_sum[row_id + tl.arange(0, 1)], ub_scalar)
                        tl.load(O[gm_o_offset + tl.arange(0, D)], ub_acc_row)

                    with tl.compute():
                        inv_sum = 1.0 / tl.extract_scalar(ub_scalar, 0)
                        tl.vmul_scalar(ub_acc_row, ub_acc_row, scalar_value=inv_sum, count=D)
                        tl.vcast(ub_final, ub_acc_row, count=D)

                    with tl.copyout():
                        tl.store(O[gm_o_offset + tl.arange(0, D)], ub_final)


# --- Host 调用 ---
def host_main(Q: torch.Tensor, K: torch.Tensor, V: torch.Tensor, O: torch.Tensor):
    M, D = Q.shape
    N, D = K.shape
    Bk = 256  # KV block size

    scale = 1.0 / math.sqrt(D)

    # Workspace segments:
    # ws_score:  M × Bk × sizeof(fp32) — attention score buffer
    # ws_prob:   M × Bk × sizeof(fp16) — probability buffer
    # ws_out:    M × D  × sizeof(fp32) — partial output buffer
    # ws_max:    M × sizeof(fp32)       — running max per row
    # ws_sum:    M × sizeof(fp32)       — running sum per row
    workspace_score = torch.empty(M * Bk, dtype=torch.float32, device=Q.device)
    workspace_prob = torch.empty(M * Bk, dtype=torch.float16, device=Q.device)
    workspace_out = torch.empty(M * D, dtype=torch.float32, device=Q.device)
    workspace_max = torch.full((M,), float('-inf'), dtype=torch.float32, device=Q.device)
    workspace_sum = torch.zeros(M, dtype=torch.float32, device=Q.device)

    # Initialize O to zero for accumulation
    O.zero_()

    core_num = tl.get_core_num()

    flash_attn_basic_kernel[core_num](
        Q, K, V, O,
        workspace_score, workspace_prob, workspace_out, workspace_max, workspace_sum,
        M, N, D, Bk, scale
    )
