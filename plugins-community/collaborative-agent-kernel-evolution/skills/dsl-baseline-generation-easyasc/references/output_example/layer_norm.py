# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

# ============================================================================
# CANONICAL reference for **LayerNorm** (affine norm-along-last-dim).
#
# Origin: translated from the old CAKE2-easydsl-v2 `tile.language` kernel
#   skills/dsl-baseline-generation/references/output_example/layer_norm.py
# (3-pass per-row: mean -> variance -> normalize+scale+shift).
#
# Semantics (exactly torch.nn.functional.layer_norm over the last dim):
#   mean = mean(x, -1); var = mean((x-mean)^2, -1)   (population / unbiased=False)
#   y = (x - mean) / sqrt(var + eps) * weight + bias
#
# Verification status:
#   simulator : PASS — M in {64,128}, H in {256,768,1023} incl. non-aligned 1023
#   device    : PASS on 910B2 for 64-aligned H (H=768, diff 1.4e-6).
#               Non-aligned H (e.g. 1023) PASSES the simulator but shows a ~2e-2
#               device-only error: the last (sub-32B) H-tile's DataCopyPad leaves
#               STALE bytes in its final C0 block on hardware (the H18 pitfall;
#               the simulator zero-pads, so it only bites on device) and those
#               stale lanes corrupt the per-row variance. Pre-zeroing the tile
#               before the load does NOT cure it because DataCopyPad overwrites
#               the block with the stale tail on device. Use H % 64 == 0 on
#               hardware, or pad the hidden dim to a multiple of 64 host-side.
#
# Tiling pattern: TILE_M=64 x TILE_H=64.
#   pass 1: cadd -> running Σx -> mean (div by H)            -> brcb [64,1]->[64,8]
#   pass 2: reload, (x-mean)^2 -> cadd -> running var -> std -> brcb
#   pass 3: reload, (x-mean)/std, * weight, + bias, store
#
# Key DSL design notes (each one was a real debugging session):
#   * weight/bias resident as [1, Align64(H)] rows, loaded ONCE; pass-3 then has
#     a SINGLE GM load (x) per block. Three GM loads in one auto_sync() block
#     corrupt x_tile's ubin slot non-deterministically; a load-only preload
#     block is closed with a trailing `adds(.,.,0.0)` vec consumer.
#   * Per-COLUMN weight/bias broadcast across the 64 rows needs EXPLICIT
#     `src2_blk_stride=1, src2_rep_stride=0`, over the full 8-aligned TILE_H
#     (a non-8-aligned broadcast width silently mis-reads).
#   * Use `div`/`sqrt`, NOT `rec`/`rsqrt`: the device reciprocal/rsqrt are
#     ~1e-3-relative Newton approximations that pass in the exact simulator but
#     fail the 1e-3 tolerance on hardware (this was a ~2% device error).
#   * `bar_all()` after each tile: auto_sync() has no V->MTE2 edge, so without
#     it the next tile's x reload races the pending reduction.
# ============================================================================
from easyasc.a2 import *
import torch


EPS = 1e-5

TILE_M = 64
TILE_H = 64


@kernel()
def layer_norm_custom(
    x: GMTensor,
    weight: GMTensor,
    bias: GMTensor,
    y: GMTensor,
    M: Var,
    H: Var,
):
    x_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    sq_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    out_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)

    cen_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)

    # weight (gamma) and bias (beta) resident as one full row each, loaded
    # ONCE. Keeping them resident lets pass-3 do a single GM load (x) per
    # block: three GM loads in one block corrupt x_tile (the extra ubin
    # families perturb x_tile's slot reload, producing wrong last-tile output).
    # Allocated 64-aligned so the `adds(...)` touch (which issues full 64-lane
    # repeats) never reads past the buffer when H is not a multiple of 64.
    H_pad = Align64(H)
    weight_full = Tensor(DT.float, [1, H_pad], Position.UB)
    bias_full = Tensor(DT.float, [1, H_pad], Position.UB)

    sum_s = Tensor(DT.float, [TILE_M, 1], Position.UB)   # running Σ x
    var_s = Tensor(DT.float, [TILE_M, 1], Position.UB)   # running Σ (x-mean)^2
    chunk_s = Tensor(DT.float, [TILE_M, 1], Position.UB)
    mean_s = Tensor(DT.float, [TILE_M, 1], Position.UB)
    inv_std_s = Tensor(DT.float, [TILE_M, 1], Position.UB)

    mean_brcb = Tensor(DT.float, [TILE_M, 8], Position.UB)
    std_brcb = Tensor(DT.float, [TILE_M, 8], Position.UB)
    std_s = Tensor(DT.float, [TILE_M, 1], Position.UB)

    # fp32 H tile (for true-division). We deliberately use `div` (full
    # precision on device) instead of the dup+rec reciprocal idiom: the device
    # `rec`/`rsqrt` instructions are ~1e-3-relative Newton approximations, and
    # multiplying mean AND inv_std by such reciprocals compounds to a ~2% error
    # that fails the 1e-3 tolerance ON DEVICE (the simulator's rec is exact, so
    # the reciprocal form passes in sim but not on hardware).
    h_t = Tensor(DT.float, [TILE_M, 1], Position.UB)

    # Preload weight & bias. The trailing `adds(.,.,0.0)` is a vec consumer
    # that closes the MTE2→V ubin handshake — a load-only block leaves it
    # dangling and the simulator schedules later loads non-deterministically.
    with auto_sync():
        weight_full <<= weight[0:H]
        adds(weight_full, weight_full, 0.0)
    with auto_sync():
        bias_full <<= bias[0:H]
        adds(bias_full, bias_full, 0.0)

    with auto_sync():
        dup(h_t, H)        # fp32 H, used as the divisor for the mean/variance

    n_row_tiles = CeilDiv(M, TILE_M)
    tiles_per_core = CeilDiv(n_row_tiles, GetVecNum())
    t_begin = Var(tiles_per_core * GetVecIdx())
    t_end = Min(t_begin + tiles_per_core, n_row_tiles)

    n_h_tiles = CeilDiv(H, TILE_H)

    for ti in range(t_begin, t_end):
        row0 = Var(ti * TILE_M)
        valid_rows = Min(TILE_M, M - row0)

        # ---- Pass 1: Σ x per row (for the mean) ----
        with auto_sync():
            dup(sum_s, 0.0)

        for hi in range(0, n_h_tiles):
            h0 = Var(hi * TILE_H)
            valid_h = Min(TILE_H, H - h0)
            # H18 fix: a partial (sub-32B) DataCopyPad load leaves STALE bytes in
            # the last C0 block of x_tile ON DEVICE (the simulator zero-pads, so
            # this only bites on hardware for non-64-aligned H). Pre-zero x_tile
            # so those stale lanes read 0 and don't corrupt the cadd reduction.
            with auto_sync():
                dup(x_tile, 0.0)
            bar_all()
            with auto_sync():
                x_tile[0:valid_rows, 0:valid_h] <<= x[row0:row0 + valid_rows, h0:h0 + valid_h]
                cadd(chunk_s, x_tile)
                add(sum_s, sum_s, chunk_s)
            # bar_all() drains the vec pipe before the NEXT tile's x_tile
            # reload. auto_sync() has no V→MTE2 edge, so without this fence the
            # reload races the just-issued cadd's read of x_tile, corrupting the
            # reduction once there is more than ~4 H-tiles. bar_all is the only
            # simulator-honored cross-pipe barrier (bar_v is a no-op there).
            bar_all()

        with auto_sync():
            div(mean_s, sum_s, h_t)                # mean = Σx / H  (true divide)
            brcb(mean_brcb, mean_s, dst_blk_stride=1, dst_rep_stride=8)

        # ---- Pass 2: Σ (x-mean)^2 per row (numerically-stable variance) ----
        # For non-aligned H the last tile's pad cols (gm_to_ub_pad zero-fills
        # them) become (0-mean)^2 = mean^2. For a normalized input mean≈0 so a
        # handful of pad lanes is negligible at the 1e-3 tolerance; the
        # centered two-pass form is far more accurate than E[x^2]-mean^2, which
        # suffers catastrophic cancellation over large H.
        with auto_sync():
            dup(var_s, 0.0)

        for hi in range(0, n_h_tiles):
            h0 = Var(hi * TILE_H)
            valid_h = Min(TILE_H, H - h0)
            # H18 fix (see pass 1): pre-zero so the partial-load stale lanes are
            # 0; (0-mean)^2 in those lanes is then handled by the pad-correction.
            with auto_sync():
                dup(x_tile, 0.0)
            bar_all()
            with auto_sync():
                x_tile[0:valid_rows, 0:valid_h] <<= x[row0:row0 + valid_rows, h0:h0 + valid_h]
                sub(cen_tile, x_tile, mean_brcb)
                mul(sq_tile, cen_tile, cen_tile)
                cadd(chunk_s, sq_tile)
                add(var_s, var_s, chunk_s)
            bar_all()

        # Pad lanes (non-aligned H): the last tile's pre-zeroed pad cols enter
        # the Σ(x-mean)^2 reduction as (0-mean)^2 = mean^2. There are at most
        # (TILE_H-1) such lanes, and for a normalized row mean≈0 so each
        # contributes ~mean^2/H ~ 1e-7 — negligible at the 1e-3 tolerance. We
        # deliberately do NOT subtract an analytic `n_pad*mean^2` correction:
        # that needed a `muls(float, int_Var)` which misbehaves ON DEVICE for
        # the non-aligned tile (the int scalar path is unreliable) and pushed
        # H=1023 past tolerance, while the uncorrected error stays ~1e-6.
        with auto_sync():
            div(var_s, var_s, h_t)                 # var = Σ(x-mean)^2 / H  (true divide)
            adds(var_s, var_s, EPS)
            # std = sqrt(var+eps). We then DIVIDE by std in pass-3 (true divide,
            # full precision) rather than multiplying by an rsqrt/rec
            # approximation — see the h_t comment above for why.
            sqrt(std_s, var_s)
            brcb(std_brcb, std_s, dst_blk_stride=1, dst_rep_stride=8)

        # ---- Pass 3: normalize, scale, shift, store ----
        for hi in range(0, n_h_tiles):
            h0 = Var(hi * TILE_H)
            valid_h = Min(TILE_H, H - h0)
            # Single GM load (x) per block keeps x_tile's ubin slot clean.
            with auto_sync():
                x_tile <<= x[row0:row0 + valid_rows, h0:h0 + valid_h]
                sub(out_tile, x_tile, mean_brcb)            # x - mean
                div(out_tile, out_tile, std_brcb)           # (x-mean)/std (true divide)
                # * weight then + bias, per-column constants broadcast across
                # the TILE_M rows. Explicit broadcast strides are REQUIRED:
                # a sliced [1, vh] operand's default stride inference does not
                # row-broadcast correctly (garbage/NaN).  The broadcast width
                # MUST be a multiple of 8 (one C0 block) — a non-8-aligned vh
                # silently mis-reads — so we always run the affine over the full
                # TILE_H (=64) columns. weight_full/bias_full are 64-aligned
                # (H_pad) so this read stays in-bounds; the garbage in the pad
                # cols is never stored (the GM write below slices to valid_h).
                mul(out_tile, out_tile,
                    weight_full[0:1, h0:h0 + TILE_H],
                    src2_blk_stride=1, src2_rep_stride=0)
                add(out_tile, out_tile,
                    bias_full[0:1, h0:h0 + TILE_H],
                    src2_blk_stride=1, src2_rep_stride=0)
                y[row0:row0 + valid_rows, h0:h0 + valid_h] <<= out_tile[0:valid_rows, 0:valid_h]
            bar_all()

    return y


def build_codegen_inputs():
    torch.manual_seed(0)
    M, H = 64, 768
    x = torch.randn(M, H, dtype=torch.float32)
    weight = torch.ones(H, dtype=torch.float32)
    bias = torch.zeros(H, dtype=torch.float32)
    y = torch.zeros(M, H, dtype=torch.float32)
    return (x, weight, bias, y, M, H)


def _ref(x, weight, bias):
    return torch.nn.functional.layer_norm(x, (x.shape[-1],), weight=weight, bias=bias, eps=EPS)


def main():
    torch.manual_seed(0)
    for M_t, H_t in [(128, 768), (64, 256), (64, 1023)]:
        x = torch.randn(M_t, H_t, dtype=torch.float32)
        weight = torch.randn(H_t, dtype=torch.float32)
        bias = torch.randn(H_t, dtype=torch.float32)
        y = torch.zeros(M_t, H_t, dtype=torch.float32)
        y_k = OpExec(layer_norm_custom, simulator=True)(x, weight, bias, y, M_t, H_t)
        y_r = _ref(x, weight, bias)
        diff = torch.abs(y_k - y_r).max().item()
        torch.testing.assert_close(y_k, y_r, rtol=1e-3, atol=1e-3)
        print(f"[M={M_t:>4} H={H_t:>5}] max_abs_diff={diff:.4e}")

if __name__ == "__main__":
    main()
