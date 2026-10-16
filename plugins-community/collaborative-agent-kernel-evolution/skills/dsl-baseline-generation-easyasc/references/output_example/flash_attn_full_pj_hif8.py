# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
import builtins
import math
import os
import sys
from typing import Tuple

import torch

from easyasc.a2 import *

sys.path.insert(0, os.path.dirname(__file__))
from to_hif8_torch import to_hif8_torch

P_HIF8_SCALE = 128.0
HIF8_MIN_CLAMP = 2.0 ** -22
EXP_MASK = 0x7F800000
EXPABS_BIAS = -0x00800000
EXPABS_LE15 = 32768.0
EXPABS_LE7 = 128.0
EXPABS_LE3 = 8.0

TILE_M = 128
TILE_N = 128
TILE_K = 128
HALF_M = TILE_M // 2
HALF_N = TILE_N // 2
NEG_LARGE = -1.0e30


@func()
def quantize_p_chunk_nonneg_scaled(
    p_chunk: Tensor,
    exp_chunk: Tensor,
    meta_chunk: Tensor,
    factor_chunk: Tensor,
    flag_chunk: Tensor,
    one_chunk: Tensor,
    expmask_u32: Tensor,
):
    meta_chunk <<= p_chunk

    x_u16 = meta_chunk.reinterpret(DT.uint16)
    exp_u16 = exp_chunk.reinterpret(DT.uint16)
    expmask_u16 = expmask_u32.reinterpret(DT.uint16)
    vand(exp_u16, x_u16, expmask_u16)

    expabs_u16 = meta_chunk.reinterpret(DT.uint16)
    vnot(expabs_u16, exp_u16)
    vand(expabs_u16, expabs_u16, expmask_u16)
    expabs_i32 = meta_chunk.reinterpret(DT.int)
    adds(expabs_i32, expabs_i32, EXPABS_BIAS)
    vmax(meta_chunk, meta_chunk, exp_chunk)

    vmaxs(exp_chunk, exp_chunk, HIF8_MIN_CLAMP)

    dup(factor_chunk, 0.5)
    compare_scalar(flag_chunk, meta_chunk, EXPABS_LE15, CompareMode.LE)
    select(factor_chunk, flag_chunk, factor_chunk, one_chunk, SelectMode.TENSOR_SCALAR)
    mul(exp_chunk, exp_chunk, factor_chunk)

    dup(factor_chunk, 0.5)
    compare_scalar(flag_chunk, meta_chunk, EXPABS_LE7, CompareMode.LE)
    select(factor_chunk, flag_chunk, factor_chunk, one_chunk, SelectMode.TENSOR_SCALAR)
    mul(exp_chunk, exp_chunk, factor_chunk)

    dup(factor_chunk, 0.5)
    compare_scalar(flag_chunk, meta_chunk, EXPABS_LE3, CompareMode.LE)
    select(factor_chunk, flag_chunk, factor_chunk, one_chunk, SelectMode.TENSOR_SCALAR)
    mul(exp_chunk, exp_chunk, factor_chunk)

    div(p_chunk, p_chunk, exp_chunk)
    adds(p_chunk, p_chunk, 0.5)
    roundint = meta_chunk.reinterpret(DT.int)
    cast(roundint, p_chunk, round_mode=RoundMode.TRUNC)
    cast(p_chunk, roundint)
    mul(p_chunk, p_chunk, exp_chunk)
    muls(p_chunk, p_chunk, 1.0 / P_HIF8_SCALE)


@func()
def build_suffix_invalid_mask(valid_cols: Var, out_mask: Var):
    signed_mask = Var(-1, DT.int64)
    two_i64 = Var(2, DT.int64)
    for _ in range(0, valid_cols):
        signed_mask <<= signed_mask * two_i64
    out_mask <<= signed_mask


@func()
def mask_score_half_suffix_invalid(score_half: Tensor, valid_cols: Var):
    if valid_cols == 0:
        dup(score_half, NEG_LARGE)
    elif valid_cols < HALF_N:
        suffix_mask = Var(0, DT.uint64)
        build_suffix_invalid_mask(valid_cols, suffix_mask)
        set_mask(0, suffix_mask)
        dup(score_half, NEG_LARGE)
        reset_mask()


@func()
def apply_score_tail_mask(ub_score: Tensor, valid_n: Var):
    left_valid = Min(valid_n, HALF_N)
    right_valid = Max(valid_n - HALF_N, 0)
    mask_score_half_suffix_invalid(ub_score[0:HALF_M, 0:HALF_N], left_valid)
    mask_score_half_suffix_invalid(ub_score[0:HALF_M, HALF_N:TILE_N], right_valid)


@func()
def apply_score_row_tail_mask_after_shift(ub_score: Tensor, valid_rows: Var):
    if valid_rows == 0:
        dup(ub_score, NEG_LARGE)
    elif valid_rows < HALF_M:
        dup(ub_score[valid_rows:HALF_M, 0:TILE_N], NEG_LARGE)


@kernel()
def flash_attn_full_pj_hif8_kernel(
    q: GMTensor, k: GMTensor, v: GMTensor, out: GMTensor, rowmax: GMTensor, rowsum: GMTensor,
    S1: Var, S2: Var, D: Var, BH: Var, scale: Var,
):
    score_ws = split_workspace(DT.float, [GetCubeNum(), 2, TILE_M, TILE_N], name="score_ws")
    p_ws = split_workspace(DT.half, [GetCubeNum(), 2, TILE_M, TILE_N], name="p_ws")
    pv_ws = split_workspace(DT.float, [GetCubeNum(), 2, TILE_M, TILE_K], name="pv_ws")

    l1q = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1k = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l1p = DBuff(DT.half, [TILE_M, TILE_N], Position.L1)
    l1v = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l0c = DBuff(DT.float, [TILE_M, TILE_N], Position.L0C)

    ub_score = Tensor(DT.float, [HALF_M, TILE_N], Position.UB)
    ub_chunk = Tensor(DT.float, [HALF_M, HALF_N], Position.UB)
    ub_pv = Tensor(DT.float, [HALF_M, TILE_K], Position.UB)
    ub_tmp = Tensor(DT.float, [HALF_M, HALF_N], Position.UB)
    ub_meta = Tensor(DT.float, [HALF_M, HALF_N], Position.UB)
    ub_factor = Tensor(DT.float, [HALF_M, HALF_N], Position.UB)
    ub_one = Tensor(DT.float, [1, HALF_N], Position.UB)
    ub_max_s = Tensor(DT.float, [HALF_M, 1], Position.UB)
    ub_rmax_s = Tensor(DT.float, [HALF_M, 1], Position.UB)
    ub_sum_s = Tensor(DT.float, [HALF_M, 1], Position.UB)
    ub_rsum_s = Tensor(DT.float, [HALF_M, 1], Position.UB)
    ub_zero_s = Tensor(DT.float, [HALF_M, 1], Position.UB)
    ub_max = Tensor(DT.float, [HALF_M, 8], Position.UB)
    ub_rowsum = Tensor(DT.float, [HALF_M, 8], Position.UB)
    ub_p = Tensor(DT.half, [HALF_M, TILE_N], Position.UB)
    ub_flag = Tensor(DT.uint8, [HALF_M, HALF_N], Position.UB)
    ub_expdiff = Tensor(DT.float, [HALF_M, 8], Position.UB)
    accum_ub = Tensor(DT.float, [HALF_M, TILE_K], Position.UB)
    expdiff_buf = DBuff(DT.float, [HALF_M, 1], Position.UB)
    accum_store_ready = SEvent(Pipe.V, Pipe.MTE3, name="accum_store_ready")
    accum_store_valid = SEvent(Pipe.MTE3, Pipe.V, preset=True, name="accum_store_valid")

    qk_mutex = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)
    p_mutex = VcMutex(1, src_end_pipe=Pipe.MTE3, dst_end_pipe=Pipe.FIX)
    pv_mutex = CvMutex(2, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)

    l1qk_cnt = Var(0)
    l1pv_cnt = Var(0)
    l0c_cnt = Var(0)
    stage1_cnt = Var(0)
    stage2_cnt = Var(0)

    cube_idx = GetCubeIdx()
    sb = GetSubBlockIdx()
    sb_row = Var(sb * HALF_M)
    expmask_u32 = ub_p.reinterpret(DT.uint32)

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
        valid_m = Min(TILE_M, S1 - lmt * TILE_M)
        local_valid_m = Min(HALF_M, Max(valid_m - sb_row, 0))

        dup(ub_rmax_s, NEG_LARGE)
        dup(ub_rsum_s, 0.0)
        dup(ub_zero_s, 0.0)
        dup(ub_one, 1.0)
        accum_store_valid.wait()
        dup(accum_ub, 0.0)

        for ni in range(0, tiles_n + 1):
            if ni < tiles_n:
                with auto_sync():
                    n_off = Var(ni * TILE_N)
                    kv_row = Var(kv_base + n_off)
                    valid_n = Min(TILE_N, S2 - n_off)
                    stage1_slot = var_mod(stage1_cnt, 2)

                    l1q[l1qk_cnt] <<= q[q_row:q_row + valid_m, 0:D]
                    l1k[l1qk_cnt] <<= k[kv_row:kv_row + valid_n, 0:D]
                    matmul(l0c[l0c_cnt], l1q[l1qk_cnt], l1k[l1qk_cnt], is_init=True)

                    qk_mutex.lock()
                    score_ws[cube_idx, stage1_slot, 0:TILE_M, 0:TILE_N] <<= l0c[l0c_cnt]
                    qk_mutex.ready()

                    qk_mutex.wait()
                    ub_score <<= score_ws[cube_idx, stage1_slot, sb_row:sb_row + HALF_M, 0:TILE_N]

                    muls(ub_score, ub_score, scale)
                    if valid_n < TILE_N:
                        apply_score_tail_mask(ub_score, valid_n)
                    vmax(ub_tmp, ub_score[0:HALF_M, 0:HALF_N], ub_score[0:HALF_M, HALF_N:TILE_N])
                    cmax(ub_max_s, ub_tmp)

                    add(expdiff_buf[stage1_slot], ub_rmax_s, ub_zero_s)
                    vmax(ub_rmax_s, ub_rmax_s, ub_max_s)
                    sub(expdiff_buf[stage1_slot], expdiff_buf[stage1_slot], ub_rmax_s)
                    exp(expdiff_buf[stage1_slot], expdiff_buf[stage1_slot])

                    brcb(ub_max, ub_rmax_s, dst_blk_stride=1, dst_rep_stride=8)
                    sub(ub_score[0:HALF_M, 0:HALF_N], ub_score[0:HALF_M, 0:HALF_N], ub_max)
                    sub(ub_score[0:HALF_M, HALF_N:TILE_N], ub_score[0:HALF_M, HALF_N:TILE_N], ub_max)
                    if local_valid_m < HALF_M:
                        apply_score_row_tail_mask_after_shift(ub_score, local_valid_m)

                    exp(ub_score, ub_score)
                    add(ub_tmp, ub_score[0:HALF_M, 0:HALF_N], ub_score[0:HALF_M, HALF_N:TILE_N])
                    cadd(ub_sum_s, ub_tmp)
                    mul(ub_rsum_s, ub_rsum_s, expdiff_buf[stage1_slot])
                    add(ub_rsum_s, ub_rsum_s, ub_sum_s)

                    muls(ub_score, ub_score, P_HIF8_SCALE)
                    dup(expmask_u32, EXP_MASK)
                    ub_chunk <<= ub_score[0:HALF_M, 0:HALF_N]
                    quantize_p_chunk_nonneg_scaled(
                        ub_chunk, ub_tmp, ub_meta, ub_factor, ub_flag, ub_one, expmask_u32,
                    )
                    ub_score[0:HALF_M, 0:HALF_N] <<= ub_chunk
                    ub_chunk <<= ub_score[0:HALF_M, HALF_N:TILE_N]
                    quantize_p_chunk_nonneg_scaled(
                        ub_chunk, ub_tmp, ub_meta, ub_factor, ub_flag, ub_one, expmask_u32,
                    )
                    ub_score[0:HALF_M, HALF_N:TILE_N] <<= ub_chunk
                    cast(ub_p, ub_score)

                    p_mutex.lock()
                    p_ws[cube_idx, stage1_slot, sb_row:sb_row + HALF_M, 0:TILE_N] <<= ub_p
                    p_mutex.ready()
                    qk_mutex.free()

                    l1qk_cnt += 1
                    l0c_cnt += 1
                    stage1_cnt += 1

            if ni > 0:
                with auto_sync():
                    prev_nt = Var(ni - 1)
                    prev_n_off = Var(prev_nt * TILE_N)
                    prev_valid_n = Min(TILE_N, S2 - prev_n_off)
                    stage2_slot = var_mod(stage2_cnt, 2)
                    v_row = Var(kv_base + prev_n_off)

                    p_mutex.wait()
                    l1p[l1pv_cnt] <<= p_ws[cube_idx, stage2_slot, 0:TILE_M, 0:TILE_N]
                    l1v[l1pv_cnt] <<= v[v_row:v_row + prev_valid_n, 0:D]
                    matmul(l0c[l0c_cnt], l1p[l1pv_cnt], l1v[l1pv_cnt].T, is_init=True)
                    p_mutex.free()

                    pv_mutex.lock()
                    pv_ws[cube_idx, stage2_slot, 0:TILE_M, 0:D] <<= l0c[l0c_cnt]
                    pv_mutex.ready()

                    pv_mutex.wait()
                    ub_pv <<= pv_ws[cube_idx, stage2_slot, sb_row:sb_row + HALF_M, 0:D]

                    brcb(ub_expdiff, expdiff_buf[stage2_slot], dst_blk_stride=1, dst_rep_stride=8)
                    mul(accum_ub[0:HALF_M, 0:HALF_N], accum_ub[0:HALF_M, 0:HALF_N], ub_expdiff)
                    mul(accum_ub[0:HALF_M, HALF_N:TILE_K], accum_ub[0:HALF_M, HALF_N:TILE_K], ub_expdiff)
                    add(accum_ub, accum_ub, ub_pv)
                    pv_mutex.free()

                    l1pv_cnt += 1
                    l0c_cnt += 1
                    stage2_cnt += 1

        brcb(ub_rowsum, ub_rsum_s, dst_blk_stride=1, dst_rep_stride=8)
        div(accum_ub[0:HALF_M, 0:HALF_N], accum_ub[0:HALF_M, 0:HALF_N], ub_rowsum)
        div(accum_ub[0:HALF_M, HALF_N:TILE_K], accum_ub[0:HALF_M, HALF_N:TILE_K], ub_rowsum)

        if local_valid_m > 0:
            out_row = Var(q_row + sb_row)
            accum_store_ready.set()
            accum_store_ready.wait()
            out[out_row:out_row + local_valid_m, 0:D] <<= accum_ub[0:local_valid_m, 0:D]
            rowmax[out_row:out_row + local_valid_m] <<= ub_rmax_s[0:local_valid_m, 0:1]
            rowsum[out_row:out_row + local_valid_m] <<= ub_rsum_s[0:local_valid_m, 0:1]
        accum_store_valid.set()

    return out, rowmax, rowsum


def _ref_flash_attn_full_pj_hif8(
    q: torch.Tensor, k: torch.Tensor, v: torch.Tensor,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    B, H, S1, D = q.shape
    S2 = k.shape[2]
    scale = 1.0 / math.sqrt(D)

    q_f = q.float()
    k_f = k.float()
    v_f = v.float()

    row_max = torch.zeros(B, H, S1, 1, dtype=torch.float32, device=q.device)
    row_sum = torch.zeros(B, H, S1, 1, dtype=torch.float32, device=q.device)
    out = torch.zeros(B, H, S1, D, dtype=torch.float32, device=q.device)

    for j in builtins.range(0, S2, TILE_N):
        k_blk = k_f[:, :, j:j + TILE_N, :]
        score_j = torch.einsum("bhsd,bhtd->bhst", q_f, k_blk) * scale
        max_j = score_j.max(dim=-1, keepdim=True).values

        if j == 0:
            row_max = max_j
            expdiff = torch.ones_like(row_max)
        else:
            curr_max = torch.maximum(row_max, max_j)
            expdiff = torch.exp(row_max - curr_max)
            row_max = curr_max

        p_j = torch.exp(score_j - row_max)
        sum_j = p_j.sum(dim=-1, keepdim=True)
        p_j = to_hif8_torch(p_j * P_HIF8_SCALE) / P_HIF8_SCALE

        if j == 0:
            row_sum = sum_j
        else:
            row_sum = row_sum * expdiff + sum_j

        v_blk = v_f[:, :, j:j + TILE_N, :]
        pv_j = torch.einsum("bhst,bhtd->bhsd", p_j, v_blk)
        if j == 0:
            out = pv_j
        else:
            out = out * expdiff + pv_j

    return out / row_sum, row_max, row_sum


def _standard_flash_attn_ref(q: torch.Tensor, k: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    score = torch.einsum("bhsd,bhtd->bhst", q.float(), k.float()) * (1.0 / math.sqrt(q.shape[-1]))
    prob = torch.softmax(score, dim=-1)
    return torch.einsum("bhst,bhtd->bhsd", prob, v.float())


def main():
    torch.manual_seed(42)

    def run_case(B: int, H: int, S1: int, S2: int, D: int) -> None:
        assert D == TILE_K

        BH = B * H
        q = torch.randn(B, H, S1, D, dtype=torch.float16)
        k = torch.randn(B, H, S2, D, dtype=torch.float16)
        v = torch.randn(B, H, S2, D, dtype=torch.float16)
        out_ref, rowmax_ref, rowsum_ref = _ref_flash_attn_full_pj_hif8(q, k, v)
        softmax_ref = _standard_flash_attn_ref(q, k, v)

        q_flat = q.reshape(BH * S1, D).contiguous()
        k_flat = k.reshape(BH * S2, D).contiguous()
        v_flat = v.reshape(BH * S2, D).contiguous()
        out_flat = torch.zeros(BH * S1, D, dtype=torch.float32)
        rowmax_flat = torch.zeros(BH * S1, dtype=torch.float32)
        rowsum_flat = torch.zeros(BH * S1, dtype=torch.float32)

        out_kernel, rowmax_kernel, rowsum_kernel = OpExec(
            flash_attn_full_pj_hif8_kernel,
            simulator=True,
            out_dir="./tmp/flash_attn_full_pj_hif8",
        )(q_flat, k_flat, v_flat, out_flat, rowmax_flat, rowsum_flat, S1, S2, D, BH, 1.0 / math.sqrt(D))
        out_kernel = out_kernel.reshape(B, H, S1, D)
        rowmax_kernel = rowmax_kernel.reshape(B, H, S1)
        rowsum_kernel = rowsum_kernel.reshape(B, H, S1)

        tolerances = [(2e-2, 2e-2), (3e-2, 3e-2)]
        used_rtol, used_atol = tolerances[-1]
        for rtol, atol in tolerances:
            try:
                torch.testing.assert_close(out_kernel, out_ref, rtol=rtol, atol=atol)
                used_rtol, used_atol = rtol, atol
                break
            except AssertionError:
                used_rtol, used_atol = tolerances[-1]

        torch.testing.assert_close(out_kernel, out_ref, rtol=used_rtol, atol=used_atol)
        torch.testing.assert_close(rowmax_kernel, rowmax_ref.squeeze(-1), rtol=1e-5, atol=1e-5)
        torch.testing.assert_close(rowsum_kernel, rowsum_ref.squeeze(-1), rtol=1e-5, atol=1e-5)
        print(
            f"shape=({B},{H},{S1},{S2},{D}): "
            f"tol=({used_rtol:.0e},{used_atol:.0e}) "
            f"kernel_max_abs_diff={torch.abs(out_kernel - out_ref).max().item():.6e} "
            f"rowmax_max_abs_diff={torch.abs(rowmax_kernel - rowmax_ref.squeeze(-1)).max().item():.6e} "
            f"rowsum_max_abs_diff={torch.abs(rowsum_kernel - rowsum_ref.squeeze(-1)).max().item():.6e} "
            f"inline_vs_softmax_max_abs_diff={torch.abs(out_ref - softmax_ref).max().item():.6e}",
            flush=True,
        )

    for shape in (
        (1, 1, 256, 384, 128),
        (1, 1, 256, 266, 128),
        (1, 1, 256, 321, 128),
        (1, 1, 256, 352, 128),
        (1, 1, 256, 383, 128),
        (1, 1, 1024, 2175, 128),
        (1, 1, 129, 256, 128),
        (1, 1, 191, 256, 128),
        (1, 1, 192, 256, 128),
        (1, 1, 193, 256, 128),
        (1, 1, 255, 256, 128),
        (1, 1, 257, 256, 128),
        (1, 3, 193, 256, 128),
        (1, 1, 1025, 2175, 128),
    ):
        run_case(*shape)

if __name__ == "__main__":
    main()
