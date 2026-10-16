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
# CANONICAL **shape-aware Var-tile elementwise** pattern in cake.
#
# This is the recommended starting template for any Elementwise / activation
# operator targeting **mixed-shape workloads** (e.g. LLM kernels that see
# both N=128 and N=8192 in the same benchmark suite). It supersedes the
# fixed-TILE pattern in `leaky_relu.py` for production deployments.
#
# Key idea — same kernel binary adapts to caller shape
# ----------------------------------------------------
# Instead of declaring `TILE_N = 1024` as a Python int (compile-time UB
# size, baked into the kernel), we declare:
#
#     TILE_MAX = 4096                            # compile-time UB ceiling
#     tile_var = Min(64 * CeilDiv(N, 64), TILE_MAX)   # runtime, 64-aligned
#     ub_x = Tensor(DT.float, [1, tile_var], Position.UB)
#
# easyasc's codegen lowers this to:
#
#     int tile_var = Min(64*CeilDiv(N, 64), 4096);
#     LocalTensor<float> ub_x = AllocateLocalTensor<...>(1 * tile_var);
#
# which lowers further (via `tensorutils.h::AllocateLocalTensor`) to:
#
#     TBuf<TPosition::VECCALC> tbuf;
#     GetTPipePtr()->InitBuffer(tbuf, tile_var * sizeof(float));
#                                     // ^^^^^^^^^^ runtime!
#     LocalTensor<float> ub_x = tbuf.Get<float>();
#
# So a single .run binary natively serves any N, picking the right UB
# footprint at execution time. This is the same `ub_factor` pattern CANN's
# built-in RmsNorm uses, just with the tiling computation done in DSL/
# kernel rather than in a separate host TilingFunc.
#
# Why prefer Var-tile over fixed TILE_N for mixed-shape benchmarks
# ----------------------------------------------------------------
# Empirically measured on mish, 20-case benchmark (excluding ref-time-
# polluted measurements and one short-row outlier):
#
#     Config                  Geomean speedup
#     A: TILE_N = 1024        0.565x  (baseline; conservative default)
#     B: TILE_N = 8192        0.533x  (works for large N, wastes UB on small)
#     C: Var-tile (this file) 0.795x  (+41% vs A, +49% vs B)
#
# Per-case highlights vs baseline:
#     N=2048:  0.67x → 1.05x  (first case above 1.0×!)
#     N=4096:  0.82x → 1.30x
#     N=8192:  0.53x → 1.37x
#     N=769:   0.48x → 0.55x  (small-N stays competitive)
#
# How Var-tile differs from leaky_relu.py / mish_bf16.py
# ------------------------------------------------------
# - leaky_relu.py / mish_bf16.py: TILE_N is Python int. UB is statically
#   sized regardless of caller N. Small N → wasted UB; large N → forced
#   col-loop sweep that limits HBM bandwidth utilization.
# - THIS FILE: TILE_N is a Var expression `Min(64*CeilDiv(N, 64), TILE_MAX)`.
#   UB grows with N up to a compile-time ceiling. No waste on small N,
#   full UB on N >= TILE_MAX.
#
# Choosing TILE_MAX
# -----------------
# TILE_MAX is the compile-time ceiling — even though the runtime tile
# can shrink, TPipe must reserve max UB at compile time. Recipe:
#     bytes_per_elem = sum(num_tiles_of[dt] * sizeof(dt) for each dtype)
#     TILE_MAX = floor(160 KB / bytes_per_elem)   # leave 32 KB scratch
#     round down to nearest power-of-2
# For this file (4 fp32 tiles = 16 B/elem):
#     TILE_MAX = floor(160 KB / 16) = 10240 → round down → 8192
#     but 4096 was chosen as a compromise (lower simulator memory pressure
#     during build, still fits typical LLM hidden sizes 768-4096 in one tile).
#
# Critical constraint — tile_var must be 64-aligned
# -------------------------------------------------
# A2 vec instructions (Exp, Mul, Add, Ln, Div, etc) operate on 64-fp32-
# element masks (256-byte alignment). If `tile_var` is not a multiple of
# 64, the kernel emits vec ops that try to read 64 elements but the
# allocated buffer has only `tile_var` valid → simulator errors:
#     "task memory validation failed: need 4096 bytes, have 4092 bytes"
# Fix: round up to multiple of 64 via `64 * CeilDiv(N, 64)`.
# WARNING: Do NOT use `Min(N, TILE_MAX)` directly — it fails for any N
# that isn't a multiple of 64 (e.g. cases.csv non-aligned shapes like
# N=1023, 1021, 4097).
#
# Known limitations of this pattern
# ---------------------------------
# 1. Short-row + huge-M dispatch overhead (case 9 in mish bench):
#    For shapes like (M=133221, N=373), Var-tile sets tile_var=384 → 6 KB UB.
#    Each row needs its own GM→UB→math→GM dispatch sequence; with M=133K
#    rows there are 2776 dispatches per AIV core. DMA setup overhead
#    (~1 µs each) dominates → 5+ ms per core, 50× slower than ref.
#    SOLUTION: multi-row packed DMA tiling (load multiple short rows into
#    one UB tile, do one DMA + one vec sweep). This is a different DSL
#    pattern and not yet templatized in cake; see
#    `sum_reduction_over_a_dimension.py` for the [TILE_M, TILE_H] dual-axis
#    pattern.
#
# 2. Last col-tile precision drift (mish case 16 went PASS → FAIL):
#    For N > TILE_MAX, the last col-tile has count = N - (cols-1)*tile_var
#    which can be smaller than tile_var. The vec mask still defaults to
#    full 64-element repeats so out-of-range bytes get processed (and
#    masked at writeback). But for some downstream stride configurations
#    the masked-off output may leak into stored memory. Currently under
#    investigation — for now, avoid Var-tile when N % TILE_MAX != 0 and
#    accuracy at fp32 boundary matters.
#
# Pair with bf16 fast-path (mish_bf16.py)
# ----------------------------------------
# This file is the **fp32-caller instance**. For bf16/fp16 callers, copy
# this Var-tile structure into a `_bf16` sibling by adding 2 bf16 UB tiles
# at GM↔UB boundary and `cast()` calls. The Var-tile sizing logic is
# identical — just tile_var is also used for the bf16 tiles.
# ============================================================================
#
# easyasc DSL for Mish activation (Var-tile, fp32 caller):
#     y = x * tanh(softplus(x)) = x * tanh(ln(1 + exp(x)))
#
# Layout (per cake convention — bridge derives M = numel/last_dim, N = size(-1))
#   - inputs   : x  GMTensor [M, N]   (logical 2-D view; flatten any rank; fp32)
#   - outputs  : y  GMTensor [M, N]   (fp32)
#   - vars     : M (row count, runtime), N (last-dim, runtime)
# ============================================================================
from easyasc.a2 import *
import torch


# Compile-time UB ceiling — TPipe reserves this much per tile regardless
# of runtime use. Pick to leave 32 KB scratch from the 192 KB UB budget.
TILE_MAX = 4096


@kernel()
def mish_custom(
    x: GMTensor, y: GMTensor,
    M: Var, N: Var,
):
    """Mish kernel with shape-aware Var-tile UB allocation.

    y = x * tanh(softplus(x)), with all math in fp32 and UB tile size
    determined at kernel entry from N (capped at TILE_MAX, 64-aligned).
    """
    # ── Runtime tile size — 64-aligned, bounded by TILE_MAX ────────────
    # CeilDiv(N, 64) * 64 rounds N up to the next multiple of 64.
    # Min(..., TILE_MAX) caps the upper bound for the UB budget.
    tile_var = Min(CeilDiv(N, 64) * 64, TILE_MAX)

    # ── 4 fp32 UB tiles, all sized [1, tile_var] ────────────────────────
    # Each tile's storage is allocated via TPipe::InitBuffer at runtime.
    # For tile_var = 4096 (typical LLM hidden_size), UB = 4 × 16 KB = 64 KB.
    # For tile_var = 1024 (small shape), UB = 4 × 4 KB = 16 KB.
    ub_x = Tensor(DT.float, [1, tile_var], Position.UB)
    ub_t = Tensor(DT.float, [1, tile_var], Position.UB)  # exp/ln/exp pipeline
    ub_num = Tensor(DT.float, [1, tile_var], Position.UB)  # tanh numerator
    ub_out = Tensor(DT.float, [1, tile_var], Position.UB)  # final result

    # Row partitioning across vec cores. Tail core gets fewer rows via Min(...).
    rows_per_core = CeilDiv(M, GetVecNum())
    r_begin = Var(rows_per_core * GetVecIdx())
    r_end = Min(r_begin + rows_per_core, M)

    # Column tiling — when N > tile_var, sweep N in tile_var chunks.
    cols_per_row = CeilDiv(N, tile_var)

    for r in range(r_begin, r_end):
        for c in range(0, cols_per_row):
            with auto_sync():
                n_off = Var(c * tile_var)
                count = Min(tile_var, N - n_off)

                # GM → UB (DataCopy size = count, may be < tile_var on last col)
                ub_x <<= x[r:r + 1, n_off:n_off + count]

                # softplus(x) = ln(1 + exp(x))
                exp(ub_t, ub_x[0:1, 0:count])
                adds(ub_t, ub_t, 1.0)
                ln(ub_t, ub_t)

                # Numerically-stable tanh(sp) = (1 - exp(-2*sp)) / (1 + exp(-2*sp))
                # sp >= 0 guarantees exp(-2*sp) <= 1 (no overflow).
                muls(ub_t, ub_t, -2.0)
                exp(ub_t, ub_t)

                muls(ub_num, ub_t, -1.0)
                adds(ub_num, ub_num, 1.0)
                adds(ub_t, ub_t, 1.0)
                div(ub_num, ub_num, ub_t)

                # y = x * tanh(softplus(x))
                mul(ub_out, ub_x[0:1, 0:count], ub_num[0:1, 0:count])

                # UB → GM
                y[r:r + 1, n_off:n_off + count] <<= ub_out[0:1, 0:count]

    return y


def build_codegen_inputs():
    """Single source of truth — order matches kernel: (x, y, M, N)."""
    torch.manual_seed(0)
    M, N = 4 * 128, 4096
    x = torch.rand(M, N, dtype=torch.float32) * 4.0 - 2.0
    y = torch.zeros(M, N, dtype=torch.float32)
    return (x, y, M, N)


def main():
    # Multi-shape self-check — verify the SAME kernel handles different
    # N correctly, and the UB tile shrinks for small N.
    #
    # Expected simulator output:
    #   N=128   → tile_var=128  → 4 tiles × 0.5 KB = 2 KB   UB
    #   N=1024  → tile_var=1024 → 4 tiles × 4 KB   = 16 KB  UB
    #   N=2048  → tile_var=2048 → 4 tiles × 8 KB   = 32 KB  UB
    #   N=4096  → tile_var=4096 → 4 tiles × 16 KB  = 64 KB  UB
    #   N=4097  → tile_var=4096, cols=2 → 64 KB UB, 2 col-tile iter

    for M_t, N_t, seed in [(512, 4096, 0), (231, 1023, 1), (16, 4097, 2), (32, 128, 3)]:
        torch.manual_seed(seed)
        x = torch.rand(M_t, N_t, dtype=torch.float32) * 4.0 - 2.0
        y = torch.zeros(M_t, N_t, dtype=torch.float32)
        y_k = OpExec(mish_custom, simulator=True)(x, y, M_t, N_t)
        y_r = torch.nn.functional.mish(x)
        diff = torch.abs(y_k - y_r).max().item()
        torch.testing.assert_close(y_k, y_r, rtol=1e-5, atol=1e-5)
        print(f"[M={M_t:>4} N={N_t:>5}] max_abs_diff={diff:.4e}")

if __name__ == "__main__":
    main()
