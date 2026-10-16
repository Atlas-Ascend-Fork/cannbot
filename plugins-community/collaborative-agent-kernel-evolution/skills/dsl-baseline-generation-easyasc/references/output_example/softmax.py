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
# CANONICAL reference for the **3-pass tiled softmax** pattern.
#
# This file replaces the older 1-D version. The previous file used 1-D Tensor
# allocations + assumed single-tile fit + used a `[1]` UB output for cmax/cadd
# (rejected by the current easyasc UB allocator and group-reduction semantics).
# This is the working 2-D 3-pass tiled rewrite.
#
# Scope (intentional)
#   - Supports any M (rows partitioned across vec cores; tail row-tile via valid_rows).
#   - Supports H that is a multiple of TILE_H=64.
#   - Non-aligned H is OUT OF SCOPE for this baseline — see "Tail handling note".
#
# When to study this file
#   - Numerically-stable softmax over the last dim, single op.
#     Fused variants live in `flash_attn_score.py` / `flash_attn_full.py`.
#   - Any "row max / row sum / per-row normalize" pipeline:
#       softmax / log-softmax / row-wise normalize-to-unit / temperature-scaled
#       softmax / online softmax tail-correction.
#
# Patterns demonstrated (canonical 3-pass tiled softmax)
#   pass 1: row max — `cmax(chunk_max, x_tile)` → `vmax(running_max, ...)`
#   pass 2: row sum of `exp(x - max)` — `cadd(chunk_sum, ...)` → `add(running, ...)`
#   pass 3: write `exp(x - max) / sum` — re-load x, sub max (broadcasted), exp,
#           multiply by `1/sum` (broadcasted)
#
# Key idioms (each maps onto `references/constraints/`)
#   1. `cmax` / `cadd` are **group reductions** (per-repeat group of 64 fp32 lanes).
#      The simulator's legacy_vpipe walks one repeat per row when src.shape = [M, 64]
#      and dst_rep_stride=1 — exactly what we set up. TILE_H must be 64 (one repeat
#      per row covers one chunk).
#   2. `brcb([M, 1] → [M, 8])` for scalar→row broadcast (max, then inv_sum).
#      The narrow [M, 8] operand triggers C0-block broadcast against the wide [M, 64].
#   3. `rec` reciprocal once per row → `mul` by broadcast in pass 3 (no scalar div).
#
# Tail handling note (H not divisible by TILE_H)
#   The canonical fix is a sentinel: `dup(x_tile, NEG_LARGE)` BEFORE the GM load
#   so cols valid_h..TILE_H look like -inf to cmax. The simulator's `<<=` with an
#   LHS slice (e.g. `x_tile[0:valid_rows, 0:valid_h] <<= x[...]`) is not fully
#   wired up to preserve the dup'd sentinel in the unused cols — `gm_to_ub_pad`
#   currently overwrites the entire dst row including padding cols.
#   Until that's fixed, write your H-tail-handling softmax variant by:
#     (a) restricting H to multiples of TILE_H, OR
#     (b) padding the input on host before the kernel call (pad-with -inf), OR
#     (c) using the fused softmax-in-attn pattern from `flash_attn_score.py`,
#         which already handles tail via masking.
#
# Verified end-to-end via simulator self-check (3 shapes, all H multiples of 64).
# ============================================================================================
#
# easyasc DSL for softmax along the last dim:
#     m = max(x, dim=-1, keepdim=True)
#     e = exp(x - m)
#     s = sum(e, dim=-1, keepdim=True)
#     y = e / s
#
# Equivalent to `torch.softmax(x, dim=-1)`.
#
# Layout (bridge derives M = numel/last_dim, N = size(-1))
#   - inputs   : x  GMTensor [M, N]
#   - outputs  : y  GMTensor [M, N]
#   - vars     : M (row count, runtime), N (last-dim, runtime; must be multiple of 64)
# ============================================================================================
from easyasc.a2 import *
import torch


TILE_M = 64
TILE_H = 64

# Sentinel for max-init. Hardware-friendly large-negative finite value
# (NOT float("-inf") — easier on the simulator and downstream casts).
NEG_LARGE = -1.0e30


@kernel()
def softmax_custom(
    x: GMTensor, y: GMTensor,
    M: Var, N: Var,
):
    """Numerically-stable softmax along last dim, 3-pass tiled.

    Three passes are needed because each row's max / sum span N which may not
    fit in UB. Pass 1 finds the row max, pass 2 finds sum(exp(x - max)), pass 3
    writes exp(x - max) / sum.
    """
    # Row-tile slabs ([64, 64] each = 16 KB).
    x_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    e_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    out_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)

    # Per-row scalar state.
    max_s = Tensor(DT.float, [TILE_M, 1], Position.UB)
    chunk_max_s = Tensor(DT.float, [TILE_M, 1], Position.UB)
    sum_s = Tensor(DT.float, [TILE_M, 1], Position.UB)
    chunk_sum_s = Tensor(DT.float, [TILE_M, 1], Position.UB)
    inv_sum_s = Tensor(DT.float, [TILE_M, 1], Position.UB)

    # Broadcast buffers — [TILE_M, 8] is the a2 narrow operand width.
    max_brcb = Tensor(DT.float, [TILE_M, 8], Position.UB)
    inv_sum_brcb = Tensor(DT.float, [TILE_M, 8], Position.UB)

    # Core partitioning.
    n_row_tiles = CeilDiv(M, TILE_M)
    tiles_per_core = CeilDiv(n_row_tiles, GetVecNum())
    t_begin = Var(tiles_per_core * GetVecIdx())
    t_end = Min(t_begin + tiles_per_core, n_row_tiles)

    n_h_tiles = CeilDiv(N, TILE_H)

    for ti in range(t_begin, t_end):
        row0 = Var(ti * TILE_M)
        valid_rows = Min(TILE_M, M - row0)

        # =========== Pass 1: row max ===========
        with auto_sync():
            dup(max_s, NEG_LARGE)

        for hi in range(0, n_h_tiles):
            h0 = Var(hi * TILE_H)
            with auto_sync():
                # H is a multiple of TILE_H (scope restriction), so full TILE_H load.
                x_tile <<= x[row0:row0 + valid_rows, h0:h0 + TILE_H]
                cmax(chunk_max_s, x_tile)
                vmax(max_s, max_s, chunk_max_s)

        # Broadcast row max to [TILE_M, 8] for use in pass 2 / 3 subs.
        with auto_sync():
            brcb(max_brcb, max_s, dst_blk_stride=1, dst_rep_stride=8)
            dup(sum_s, 0.0)

        # =========== Pass 2: row sum of exp(x - max) ===========
        for hi in range(0, n_h_tiles):
            h0 = Var(hi * TILE_H)
            with auto_sync():
                x_tile <<= x[row0:row0 + valid_rows, h0:h0 + TILE_H]
                sub(e_tile, x_tile, max_brcb)      # wide × narrow broadcast
                exp(e_tile, e_tile)
                cadd(chunk_sum_s, e_tile)
                add(sum_s, sum_s, chunk_sum_s)

        # 1/sum, broadcast.
        with auto_sync():
            rec(inv_sum_s, sum_s)
            brcb(inv_sum_brcb, inv_sum_s, dst_blk_stride=1, dst_rep_stride=8)

        # =========== Pass 3: write exp(x - max) * (1/sum) ===========
        for hi in range(0, n_h_tiles):
            h0 = Var(hi * TILE_H)
            with auto_sync():
                x_tile <<= x[row0:row0 + valid_rows, h0:h0 + TILE_H]
                sub(e_tile, x_tile, max_brcb)
                exp(e_tile, e_tile)
                mul(out_tile, e_tile, inv_sum_brcb)
                y[row0:row0 + valid_rows, h0:h0 + TILE_H] <<= out_tile[0:valid_rows, 0:TILE_H]

    return y


def build_codegen_inputs():
    """Single source of truth — order matches kernel: (x, y, M, N)."""
    torch.manual_seed(0)
    M, N = 64 * 4, 4096
    x = torch.randn(M, N, dtype=torch.float32)
    y = torch.zeros(M, N, dtype=torch.float32)
    return (x, y, M, N)


def main():
    # --- shape 1: aligned (M=256, N=4096) ---
    args = build_codegen_inputs()
    x = args[0]
    y_kernel = OpExec(softmax_custom, simulator=True)(*args)
    y_ref = torch.softmax(x, dim=-1)
    torch.testing.assert_close(y_kernel, y_ref, rtol=1e-4, atol=1e-5)
    print(f"[shape1 M={args[2]} N={args[3]}] max_abs_diff={torch.abs(y_kernel - y_ref).max().item():.6e}")

    # --- shape 2: smaller aligned shape ---
    torch.manual_seed(1)
    M2, N2 = 128, 64
    x2 = torch.randn(M2, N2, dtype=torch.float32)
    y2 = torch.zeros(M2, N2, dtype=torch.float32)
    y_kernel2 = OpExec(softmax_custom, simulator=True)(x2, y2, M2, N2)
    y_ref2 = torch.softmax(x2, dim=-1)
    torch.testing.assert_close(y_kernel2, y_ref2, rtol=1e-4, atol=1e-5)
    print(f"[shape2 M={M2} N={N2}] max_abs_diff={torch.abs(y_kernel2 - y_ref2).max().item():.6e}")

    # --- shape 3: very wide H (proves N is not baked) ---
    torch.manual_seed(2)
    M3, N3 = 64, 8192
    x3 = torch.randn(M3, N3, dtype=torch.float32)
    y3 = torch.zeros(M3, N3, dtype=torch.float32)
    y_kernel3 = OpExec(softmax_custom, simulator=True)(x3, y3, M3, N3)
    y_ref3 = torch.softmax(x3, dim=-1)
    torch.testing.assert_close(y_kernel3, y_ref3, rtol=1e-4, atol=1e-5)
    print(f"[shape3 M={M3} N={N3}] max_abs_diff={torch.abs(y_kernel3 - y_ref3).max().item():.6e}")

if __name__ == "__main__":
    main()
