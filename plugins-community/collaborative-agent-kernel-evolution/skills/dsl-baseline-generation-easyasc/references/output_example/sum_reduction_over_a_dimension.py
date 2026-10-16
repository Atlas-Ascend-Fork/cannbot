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
# CANONICAL reference for the **per-row reduce + broadcast back to row** pattern.
#
# This file replaces the older 1-D banner version. The previous file used
# `Tensor(DT.float, [N], Position.UB)` and assumed `cadd` was a whole-row
# reduction — both are wrong on current easyasc. This is the working 2-D
# rewrite with correct cadd group-reduction semantics + brcb broadcast.
#
# Why "reduce-then-broadcast" instead of writing a 1-column output `[M, 1]`?
#   The a2 `ub_to_gm_pad` instruction requires each GM row to be at least one
#   C0 block (32 bytes = 8 fp32 lanes) wide. Writing a `[M, 1]` output fails
#   with `MemoryError: task memory validation failed for ub_to_gm_pad src ...
#   need=2020 bytes, have=256 bytes` — the hardware DMA refuses single-column
#   writes. The standard fix is to broadcast the row scalar across the full
#   row width and write `[M, N]` back. Callers that want the actual `[M, 1]`
#   answer just slice `y[:, 0:1]` in Python.
#
# When to study this file
#   - Pure row-wise reduce: sum / max / min / mean over the last dim.
#     (max/min variants: swap `cadd` → `cmax`/`cmin`, drop the running add)
#   - L1-norm / L2-norm / row absmax: chain `abs`/`mul`/`sqrt` before the cadd.
#   - The "row-stat + apply-to-row" half of any LayerNorm / RMSNorm / Softmax —
#     this is the prefix; add_rms_norm.py is what comes next (rsqrt + scale).
#
# Patterns demonstrated
#   1. `cadd` group reduction (64 fp32 lanes per repeat → 1 scalar per row).
#      TILE_H=64 → one repeat per row covers the chunk exactly.
#   2. Cross-tile accumulation across H-tiles: `cadd → add(running, running, chunk)`.
#   3. brcb broadcast `[TILE_M, 1] → [TILE_M, 8]` for use as the narrow operand
#      in a wide×narrow mul (C0-block broadcast in the vec unit).
#   4. Tail handling on H: `valid_h` source slice, full TILE_H dst,
#      `gm_to_ub_pad` auto-zeros padding (correct for sum; for max/min you must
#      `dup` a sentinel into the tile first — see softmax.py).
#   5. Tail handling on M: `valid_rows = Min(TILE_M, M - row0)` at GM boundary.
#
# Verified end-to-end via simulator self-check.
# ============================================================================================
#
# easyasc DSL for sum reduction along the last dim, broadcast back across the row:
#     row_sum = sum(x[m, :])
#     y[m, n] = row_sum    for all n
#
# Equivalent to `x.sum(dim=-1, keepdim=True).expand_as(x)`.
# (If the caller wants `[M, 1]`, just slice `y[:, 0:1]` after this kernel.)
#
# Layout (per cake convention — bridge derives M = numel/last_dim, N = size(-1))
#   - inputs   : x  GMTensor [M, N]
#   - outputs  : y  GMTensor [M, N]   (broadcasted row sum)
#   - vars     : M (row count, runtime), N (last-dim, runtime)
# ============================================================================================
from easyasc.a2 import *
import torch


TILE_M = 64
TILE_H = 64


@kernel()
def sum_reduction_over_a_dimension_custom(
    x: GMTensor, y: GMTensor,
    M: Var, N: Var,
):
    """Row sum broadcast to row. y[m, n] = sum(x[m, :]) for all n."""
    # On-chip buffers.
    x_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    out_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    chunk_s = Tensor(DT.float, [TILE_M, 1], Position.UB)   # per-H-chunk sum per row
    sum_s = Tensor(DT.float, [TILE_M, 1], Position.UB)   # running sum per row
    sum_brcb = Tensor(DT.float, [TILE_M, 8], Position.UB)   # brcb broadcast buffer

    # Core partitioning: distribute M/TILE_M row-tiles across vec cores.
    n_row_tiles = CeilDiv(M, TILE_M)
    tiles_per_core = CeilDiv(n_row_tiles, GetVecNum())
    t_begin = Var(tiles_per_core * GetVecIdx())
    t_end = Min(t_begin + tiles_per_core, n_row_tiles)

    n_h_tiles = CeilDiv(N, TILE_H)   # Var arithmetic; not baked at codegen

    for ti in range(t_begin, t_end):
        row0 = Var(ti * TILE_M)
        valid_rows = Min(TILE_M, M - row0)

        # ---- Pass 1: per-row running sum across all H-tiles ----
        with auto_sync():
            dup(sum_s, 0.0)

        for hi in range(0, n_h_tiles):
            h0 = Var(hi * TILE_H)
            valid_h = Min(TILE_H, N - h0)
            with auto_sync():
                # gm_to_ub_pad auto-zeros cols valid_h..TILE_H — sum is unchanged
                # by adding zeros. (max/min would need an explicit dup sentinel.)
                x_tile <<= x[row0:row0 + valid_rows, h0:h0 + valid_h]
                cadd(chunk_s, x_tile)
                add(sum_s, sum_s, chunk_s)

        # brcb the row scalar to a [TILE_M, 8] narrow tile, used as the broadcast
        # source in the wide×narrow mul that materializes the output rows.
        with auto_sync():
            brcb(sum_brcb, sum_s, dst_blk_stride=1, dst_rep_stride=8)

        # ---- Pass 2: write the row-sum to every column of y ----
        # We use mul(out_tile, ones_like(x_tile), sum_brcb) — but constructing
        # ones_like is overkill; simpler: dup(out_tile, 1.0) then mul. Even
        # simpler: just brcb sum_s into a wide buffer directly by using brcb
        # with appropriate strides, then write that. We use the dup+mul form
        # because it's the same pattern sub-agents will need for scale-by-stat
        # ops (RMSNorm: dup → ub_x then mul out = ub_x * inv_rms_brcb).
        for hi in range(0, n_h_tiles):
            h0 = Var(hi * TILE_H)
            valid_h = Min(TILE_H, N - h0)
            with auto_sync():
                dup(out_tile, 1.0)
                mul(out_tile, out_tile, sum_brcb)   # wide × narrow broadcast
                y[row0:row0 + valid_rows, h0:h0 + valid_h] <<= out_tile[0:valid_rows, 0:valid_h]

    return y


def build_codegen_inputs():
    """Single source of truth — order matches kernel: (x, y, M, N)."""
    torch.manual_seed(0)
    M, N = 64 * 8, 4096
    x = torch.randn(M, N, dtype=torch.float32)
    y = torch.zeros(M, N, dtype=torch.float32)
    return (x, y, M, N)


def _ref(x):
    """Reference: x.sum(dim=-1, keepdim=True) broadcast over the row."""
    return x.sum(dim=-1, keepdim=True).expand_as(x).contiguous()


def main():
    # --- shape 1: aligned (M=512, N=4096) ---
    args = build_codegen_inputs()
    x = args[0]
    y_kernel = OpExec(sum_reduction_over_a_dimension_custom, simulator=True)(*args)
    y_ref = _ref(x)
    torch.testing.assert_close(y_kernel, y_ref, rtol=1e-4, atol=1e-3)
    print(f"[shape1 M={args[2]} N={args[3]}] max_abs_diff={torch.abs(y_kernel - y_ref).max().item():.6e}")

    # --- shape 2: different aligned shape (proves Var-parametric) ---
    torch.manual_seed(1)
    M2, N2 = 64, 256
    x2 = torch.randn(M2, N2, dtype=torch.float32)
    y2 = torch.zeros(M2, N2, dtype=torch.float32)
    y_kernel2 = OpExec(sum_reduction_over_a_dimension_custom, simulator=True)(x2, y2, M2, N2)
    y_ref2 = _ref(x2)
    torch.testing.assert_close(y_kernel2, y_ref2, rtol=1e-4, atol=1e-3)
    print(f"[shape2 M={M2} N={N2}] max_abs_diff={torch.abs(y_kernel2 - y_ref2).max().item():.6e}")

    # --- shape 3: H not divisible by TILE_H (exercises gm_to_ub_pad zero-pad) ---
    torch.manual_seed(2)
    M3, N3 = 64, 1023
    x3 = torch.randn(M3, N3, dtype=torch.float32)
    y3 = torch.zeros(M3, N3, dtype=torch.float32)
    y_kernel3 = OpExec(sum_reduction_over_a_dimension_custom, simulator=True)(x3, y3, M3, N3)
    y_ref3 = _ref(x3)
    torch.testing.assert_close(y_kernel3, y_ref3, rtol=1e-4, atol=1e-3)
    print(f"[shape3 M={M3} N={N3}] max_abs_diff={torch.abs(y_kernel3 - y_ref3).max().item():.6e}")

if __name__ == "__main__":
    main()
