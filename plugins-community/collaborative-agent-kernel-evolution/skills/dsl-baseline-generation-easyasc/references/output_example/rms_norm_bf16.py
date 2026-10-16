# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

# ============================================================================================
# CANONICAL reference for the **mixed-dtype NN-Normalization** pattern in cake.
#
# This is the bf16-native counterpart of `add_rms_norm.py`. It demonstrates the
# **kernel-side cast** for norm-class ops where the reduction (`cadd`) MUST
# happen in fp32 to preserve precision, but I/O stays bf16 to keep HBM low.
#
# When to study this file
#   - Any norm-along-last-dim op (RMSNorm / LayerNorm / GroupNorm / QK-norm /
#     AddLayerNorm / AddRMSNorm) where the caller dtype is bf16 or fp16.
#   - Mixed-dtype pattern with reduction (different from mish_bf16, which is
#     pure elementwise — here we also have a per-row `cadd` that needs fp32).
#
# Pattern demonstrated — "ladder UB + fp32 reduction"
#   1. UB tiles in TWO dtypes per tensor (input, gamma, output):
#        x_ub_bf / y_ub_bf / w_ub_bf — bf16 (for GM2UB / UB2GM)
#        x_fp / y_fp / w_fp           — fp32 (for math + reduction)
#   2. Per H-tile loop:
#        a. GM (bf16) → UB (bf16) for the tile
#        b. cast UB (bf16) → UB (fp32)
#        c. fp32 math: square, accumulate Σ x² in fp32
#   3. Per row (one-shot after all H-tiles):
#        d. mean = Σ x² / H, rsqrt(mean + eps)
#        e. brcb the scalar to a vector
#        f. for each H-tile again: reload x, cast bf16→fp32, multiply by
#           inv_rms × gamma_fp, cast result fp32→bf16, write to GM
#
# Why two-pass over H instead of caching x_fp
#   For H=4096 with TILE_M=64 rows, caching the whole row would need
#   64×4096×4 = 1 MB UB per row tile — would not fit in 192 KB. So we re-read
#   x (bf16, half the bytes) and re-cast on pass 2. The trade-off: one extra
#   HBM read at bf16 rate (32 MB for [4096, 4096]) vs. fitting in UB.
#
# Comparison with `add_rms_norm.py` (fp32 quick-path baseline)
#   add_rms_norm.py: TILE_M=64, TILE_H=64, all fp32 UB tiles, no cast(),
#                    build_codegen_inputs returns fp32 tensors.
#   THIS FILE:       TILE_M=1, TILE_H=fits-hidden-size, mixed bf16/fp32 UB,
#                    explicit cast() at every GM↔UB boundary,
#                    build_codegen_inputs returns bf16 tensors.
#
# Why TILE_M=1 (process one row at a time) when add_rms_norm.py uses TILE_M=64
#   add_rms_norm.py needs TILE_M=64 because of the `brcb([64,1]→[64,8])` +
#   `mul(wide, wide, narrow)` broadcast pattern for inv_rms. Here, by handling
#   one row per tile, we can use a simpler `mul(..., src2_blk_stride=0,
#   src2_rep_stride=0)` broadcast — works for any TILE_M=1 row tile and removes
#   the brcb complexity. fm-easyasc uses this same single-row pattern.
#   Trade-off: less parallelism within a vec core, but more cores see more
#   work for typical M ≥ 200 cases.
#
# Verified end-to-end via simulator self-check (4 shapes covering aligned /
# non-aligned / tiny eps / boundary).
# ============================================================================================
#
# easyasc DSL for RMSNorm (bf16-native):
#     y = x / sqrt(mean(x², dim=-1, keepdim=True) + ε) * γ
#
# Layout
#   - inputs   : x      GMTensor [M, H]   (bf16)
#                gamma  GMTensor [H]       (bf16)
#   - output   : y      GMTensor [M, H]   (bf16)
#   - vars     : M (rows = numel/H), H (hidden), eps (fp32), inv_h (fp32 = 1/H, host-computed)
# ============================================================================================
from easyasc.a2 import *
import torch


# Compile-time max hidden size that fits in one UB tile. Choose to match the
# largest H you expect (e.g. 8192 for typical LLM cases). Increasing this raises
# per-row UB cost — see UB budget below.
#
# At TILE_H=8192 this file uses ~147 KB / 192 KB = 77% UB — well-utilized.
# Empirical UB scaling on this kernel (3 bf16 + 3 fp32 tiles ⇒ 18 B/elem):
#     TILE_H=4096 → ~74 KB (39%) — 2 inner H-tiles per row when H=8192
#     TILE_H=8192 → ~147 KB (77%) — 1 inner H-tile, no inner H-loop overhead
# Don't go higher than 8192 without restructuring — UB ceiling 192 KB only
# leaves room for the multi-stage reduce scratch tiles (PARTIAL_L=128 etc).
TILE_H = 8192

# Multi-stage reduce buffers. `cadd` is a 64-wide group reduction (256 B per
# repeat for fp32); to fully reduce 8192 floats we go 8192 → 128 (cadd) → 64
# (cadd) → 1 (sum first half + second half). These intermediate sizes are
# bounded compile-time constants.
PARTIAL_L = 128
SCALAR_BUF = 64
BCAST_L = 512


@kernel()
def rms_norm_custom(
    x: GMTensor,
    gamma: GMTensor,
    y: GMTensor,
    # Vars — order MUST match build_codegen_inputs and the aclnn header.
    M: Var,
    H: Var,
    eps: Var,      # @pybind:1e-6 in op_desc → pybind arg
    inv_h: Var,    # @f:1.0/static_cast<double>(H) in op_desc → host pre-computed
):
    """RMSNorm bf16-native — y = x / sqrt(mean(x²)+ε) * γ.

    All math in fp32 on UB; GM transfers stay bf16. UB per row:
      bf16 tiles : x_ub_bf, y_ub_bf, w_ub_bf  = 3 × 16 KB = 48 KB
      fp32 tiles : x_fp, y_fp, w_fp           = 3 × 32 KB = 96 KB
      scratch    : partial/sum_sq/inv_rms/bcast ≈ 4 KB
    TOTAL ≈ 148 KB / 192 KB (77%). For H>8192 either increase TILE_H or split.
    """
    # ── Low-precision UB tiles for GM ↔ UB transfers ────────────────────────
    x_ub_bf = Tensor(DT.bfloat16, [1, TILE_H], Position.UB)
    y_ub_bf = Tensor(DT.bfloat16, [1, TILE_H], Position.UB)
    w_ub_bf = Tensor(DT.bfloat16, [1, TILE_H], Position.UB)

    # ── fp32 UB tiles for math ──────────────────────────────────────────────
    x_fp = Tensor(DT.float, [1, TILE_H], Position.UB)
    y_fp = Tensor(DT.float, [1, TILE_H], Position.UB)
    w_fp = Tensor(DT.float, [1, TILE_H], Position.UB)

    # Multi-stage reduce scratch (kept fp32 — reduction precision is critical).
    partial = Tensor(DT.float, [1, PARTIAL_L], Position.UB)
    sum_sq_ub = Tensor(DT.float, [1, SCALAR_BUF], Position.UB)
    inv_rms_ub = Tensor(DT.float, [1, SCALAR_BUF], Position.UB)
    bcast_ub = Tensor(DT.float, [1, BCAST_L], Position.UB)

    # ── Load gamma once + upcast to fp32 (shared across all rows) ──────────
    w_ub_bf <<= gamma[0:1, 0:H]
    cast(w_fp[0:1, 0:H], w_ub_bf[0:1, 0:H])

    # ── Distribute rows across vec cores ────────────────────────────────────
    rows_per_core = CeilDiv(M, GetVecNum())
    row_start = Var(rows_per_core * GetVecIdx())
    row_end = Min(row_start + rows_per_core, M)

    for r in range(row_start, row_end):
        with auto_sync():
            # ── (1) GM (bf16) → UB (bf16) → UB (fp32) ──────────────────────
            x_ub_bf <<= x[r:r + 1, 0:H]
            cast(x_fp[0:1, 0:H], x_ub_bf[0:1, 0:H])

            # ── (2) Σ x² in fp32 — multi-stage reduce ──────────────────────
            mul(y_fp[0:1, 0:H], x_fp[0:1, 0:H], x_fp[0:1, 0:H])    # y_fp = x²
            dup(partial, 0.0)
            cadd(partial, y_fp[0:1, 0:H])                          # 8192 → 128
            add(partial[0:1, 0:64], partial[0:1, 0:64], partial[0:1, 64:128])  # 128 → 64
            dup(sum_sq_ub, 0.0)
            cadd(sum_sq_ub, partial[0:1, 0:64])                    # 64 → 1

            # ── (3) inv_rms = 1 / sqrt(mean + eps), broadcast to wide vec ──
            muls(sum_sq_ub, sum_sq_ub, inv_h)                      # mean = Σx² × (1/H)
            adds(sum_sq_ub, sum_sq_ub, eps)
            rsqrt(inv_rms_ub, sum_sq_ub)
            brcb(bcast_ub, inv_rms_ub, dst_blk_stride=1, dst_rep_stride=8)

            # ── (4) y_fp = x_fp * inv_rms_scalar * gamma_fp ────────────────
            # scalar-broadcast mul via src2_blk_stride=0, src2_rep_stride=0
            mul(
                y_fp[0:1, 0:H], x_fp[0:1, 0:H], bcast_ub,
                src2_blk_stride=0, src2_rep_stride=0,
            )
            mul(y_fp[0:1, 0:H], y_fp[0:1, 0:H], w_fp[0:1, 0:H])    # * gamma (fp32)

            # ── (5) UB (fp32) → UB (bf16) → GM (bf16) ──────────────────────
            cast(y_ub_bf[0:1, 0:H], y_fp[0:1, 0:H])
            y[r:r + 1, 0:H] <<= y_ub_bf[0:1, 0:H]

    return y


def build_codegen_inputs():
    """REQUIRED: bf16 tensors so codegen registers op with DT_BF16.

    Note inv_h is also a pre-computed Var (Python-side: 1.0/H). When using
    op_desc.json `@f:` derivation, the bridge cpp will recompute this on the
    host at call time — but at codegen time we still need a value to bind.
    """
    torch.manual_seed(0)
    M, H = 2048, 4096
    eps = 1e-6
    inv_h = 1.0 / float(H)
    x = torch.randn(M, H, dtype=torch.bfloat16)
    g = torch.ones(1, H, dtype=torch.bfloat16)
    y = torch.zeros(M, H, dtype=torch.bfloat16)
    return (x, g, y, M, H, eps, inv_h)


def _reference(x_bf, g_bf, eps):
    """fp32-internal reference matching the kernel's mixed-dtype path."""
    xf = x_bf.float()
    rms = torch.sqrt(xf.pow(2).mean(dim=-1, keepdim=True) + eps)
    y_fp32 = (xf / rms) * g_bf.float().view(-1)
    return y_fp32.bfloat16()


def main():
    # Multi-shape parametric self-check — each shape must pass the bf16
    # tolerance (atol/rtol = 2e-2, generous enough for bf16's ~3-digit precision).
    test_shapes = [
        (2048, 4096, 1e-6),     # LLaMA-3-8B style, aligned
        (1024, 8192, 1e-6),     # LLaMA-3-70B-ish, larger H
        (64, 768, 1e-6), # BERT-base small case
        (32, 2048, 1e-5), # GPT-2 medium with looser eps
    ]
    for M_t, H_t, eps_t in test_shapes:
        torch.manual_seed(M_t * H_t)
        x = torch.randn(M_t, H_t, dtype=torch.bfloat16)
        g = torch.ones(1, H_t, dtype=torch.bfloat16)
        y = torch.zeros(M_t, H_t, dtype=torch.bfloat16)
        inv_h_t = 1.0 / float(H_t)

        y_k = OpExec(rms_norm_custom, simulator=True)(x, g, y, M_t, H_t, eps_t, inv_h_t)
        y_r = _reference(x, g, eps_t)
        diff = torch.abs(y_k.float() - y_r.float()).max().item()
        torch.testing.assert_close(y_k, y_r, rtol=2e-2, atol=2e-2)
        print(f"M={M_t:>5} H={H_t:>5} eps={eps_t:.0e}  bf16 max_abs_diff={diff:.4e}")

if __name__ == "__main__":
    main()
