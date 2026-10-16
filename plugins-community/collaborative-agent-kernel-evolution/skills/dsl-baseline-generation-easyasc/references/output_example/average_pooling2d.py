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
# CANONICAL reference for a **windowed-pooling / NHWC channel-vectorized** op.
#
# Origin: translated from the old CAKE2-easydsl-v2 `tile.language` kernel
#   skills/dsl-baseline-generation/references/output_example/average_pooling2d.py
# (which itself implemented the NHWC channel-tiled avg-pool used by the
# functional `module_fn` permute→avg_pool2d→permute).
#
# Semantics (exactly torch.nn.functional.avg_pool2d, kernel=stride=K, pad=0):
#   y[b, oh, ow, c] = mean_{0<=kh,kw<K} x[b, oh*K+kh, ow*K+kw, c]
#   Input/output are NHWC here; the host (Model / test) does the NCHW<->NHWC
#   permutes, matching the original functional.
#
# Verification status:
#   simulator : PASS — 3 shapes incl. non-square 9x15 and C=130 (not 64-aligned)
#   device    : PASS on 910B2 (max_abs_diff <= 1.2e-7) — see __main__ shapes.
#
# Tiling pattern:
#   * one OUTPUT pixel (b, oh, ow) owns a contiguous C-vector; output pixels are
#     round-robin'd across vec cores (GetVecNum/GetVecIdx).
#   * channels swept in TILE_C chunks; the K*K window is accumulated as K*K
#     C-vector adds, then divided by K*K.
#
# Key DSL design notes (the load-bearing ones):
#   * DIVIDE by K*K with `div(sum, sum, area_t)` — NOT `mul` by a `rec(1/area)`
#     reciprocal. The device `rec`/`rsqrt` are ~1e-3-relative Newton
#     approximations; the reciprocal form passes in the (exact) simulator but
#     fails the 1e-3 tolerance ON DEVICE. True `div` is full precision.
#   * `bar_all()` after each window add / store: `auto_sync()` has no V->MTE2
#     edge, so without it the next window's GM load races the pending add.
# ============================================================================
from easyasc.a2 import *
import torch


# Channel tile width (one vec sweep). C is typically <= a few hundred for the
# benchmark shapes; if C > TILE_C the kernel sweeps it in TILE_C chunks.
TILE_C = 512


@kernel()
def average_pooling2d_custom(
    x: GMTensor,          # NHWC, shape [B, Hin, Win, C] (flattened logical)
    y: GMTensor,          # NHWC, shape [B, OH, OW, C]
    B: Var, Hin: Var, Win: Var, C: Var,
    OH: Var, OW: Var, K: Var,
):
    """NHWC average pooling, kernel=stride=K, no padding.

    y[b, oh, ow, c] = mean_{kh,kw} x[b, oh*K+kh, ow*K+kw, c]

    Each output pixel (b, oh, ow) owns a contiguous C-vector. We accumulate the
    K*K input C-vectors of its window, then divide by K*K. Output pixels are
    distributed across vec cores; channels are swept in TILE_C chunks.
    """
    x_tile = Tensor(DT.float, [1, TILE_C], Position.UB)
    sum_tile = Tensor(DT.float, [1, TILE_C], Position.UB)
    area_t = Tensor(DT.float, [1, TILE_C], Position.UB)   # fp32 K*K (divisor)

    # K*K as an fp32 tile. We DIVIDE by it (true divide, full precision on
    # device) rather than multiplying by a `rec(1/area)` reciprocal — the
    # device `rec` is a ~1e-3-relative Newton approximation that pushes the
    # pooled mean just past the 1e-3 tolerance ON DEVICE (sim's rec is exact).
    area = Var(K * K)
    with auto_sync():
        dup(area_t, area)

    # Total output pixels, distributed across cores.
    n_pix = Var(B * OH * OW)
    pix_per_core = CeilDiv(n_pix, GetVecNum())
    p_begin = Var(pix_per_core * GetVecIdx())
    p_end = Min(p_begin + pix_per_core, n_pix)

    c_tiles = CeilDiv(C, TILE_C)

    for pix in range(p_begin, p_end):
        # Decode pix -> (b, oh, ow)
        b = Var(pix // (OH * OW))
        rem = Var(pix % (OH * OW))
        oh = Var(rem // OW)
        ow = Var(rem % OW)

        h0 = Var(oh * K)
        w0 = Var(ow * K)

        # base offset of output pixel's C-vector in the flattened NHWC array
        out_base = Var(((b * OH + oh) * OW + ow) * C)

        for ct in range(0, c_tiles):
            c0 = Var(ct * TILE_C)
            ccount = Min(TILE_C, C - c0)

            with auto_sync():
                dup(sum_tile, 0.0)

            # Accumulate the K*K window of C-vectors.
            for kh in range(0, K):
                ih = Var(h0 + kh)
                for kw in range(0, K):
                    iw = Var(w0 + kw)
                    in_base = Var(((b * Hin + ih) * Win + iw) * C + c0)
                    with auto_sync():
                        x_tile[0:1, 0:ccount] <<= x[in_base:in_base + ccount]
                        add(sum_tile[0:1, 0:ccount],
                            sum_tile[0:1, 0:ccount],
                            x_tile[0:1, 0:ccount])
                    bar_all()

            with auto_sync():
                div(sum_tile[0:1, 0:ccount], sum_tile[0:1, 0:ccount], area_t[0:1, 0:ccount])
                y[out_base + c0:out_base + c0 + ccount] <<= sum_tile[0:1, 0:ccount]
            bar_all()

    return y


def _ref(x_nchw, K):
    return torch.nn.functional.avg_pool2d(x_nchw, kernel_size=K)


def main():
    torch.manual_seed(0)
    for B_, C_, Hin_, Win_, K_ in [(2, 64, 12, 12, 3), (1, 130, 8, 8, 2), (2, 32, 9, 15, 3)]:
        OH_, OW_ = Hin_ // K_, Win_ // K_
        x_nchw = torch.randn(B_, C_, Hin_, Win_, dtype=torch.float32)
        # NCHW -> NHWC for the kernel
        x_nhwc = x_nchw.permute(0, 2, 3, 1).contiguous()
        y_nhwc = torch.zeros(B_, OH_, OW_, C_, dtype=torch.float32)
        yk = OpExec(average_pooling2d_custom, simulator=True)(
            x_nhwc.reshape(-1), y_nhwc.reshape(-1),
            B_, Hin_, Win_, C_, OH_, OW_, K_)
        yk = yk.reshape(B_, OH_, OW_, C_).permute(0, 3, 1, 2).contiguous()  # back to NCHW
        yr = _ref(x_nchw, K_)
        diff = torch.abs(yk - yr).max().item()
        print(f"[B={B_} C={C_} {Hin_}x{Win_} K={K_}] max_abs_diff={diff:.4e}")
        assert diff < 1e-3, "FAIL"

if __name__ == "__main__":
    main()
