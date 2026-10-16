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
# CANONICAL fp32-instance of the **Elementwise / activation** pattern.
#
# This file is the FP32-CALLER instance of the cake canonical pattern:
#   "fp32 compute in UB, optional cast at GM↔UB boundary".
#
# For BF16/FP16 callers, see the sibling instance: `mish_bf16.py` (same
# pattern, same math, but with bf16/fp32 dual UB tiles + cast() at boundary).
#
# Why two files (not one unified template)
#   easyasc's `@kernel()` decorator does AST rewriting via
#   `easyasc/pythonic.py::_IfRewriter` — every Python `if`/`elif`/`else`
#   inside the kernel body is transformed into
#       with If(cond): ... with Elif(...): ... with Else(): ...
#   context managers. With-statements ALWAYS execute their Python body, so
#   `if dtype is DT.float: ub_lo = Tensor(...)` allocates the tile even when
#   the condition is False — both branches' bodies run; the `If`/`Else`
#   classes only control which branch's effects survive in the recorded IR.
#   Consequence: we CAN'T gate `Tensor(...)` allocation by caller dtype in a
#   single DSL file. The two per-dtype files coexist as instances of the same
#   pattern — code only differs in (a) which UB tiles are declared and (b)
#   whether cast() calls bracket the GM↔UB transfers.
#
# Universal cake dtype rule (applies to BOTH leaky_relu.py AND mish_bf16.py)
#   1. Vec computation is ALWAYS fp32 in UB. FP16/BF16 vec math has precision
#      footguns (esp. exp/ln/sum), so all math happens in fp32 UB tiles.
#      Matches the tiling-design rule for Elementwise:
#      "FP16 直接计算 → FP16 加减乘要先 Cast 到 FP32, 计算完再 Cast 回".
#   2. Caller dtype ONLY decides whether the kernel adds a cast step at the
#      GM↔UB boundary — nothing else about the DSL structure changes.
#   3. The cast happens INSIDE the kernel, NOT in the bridge cpp. Host-side
#      cast (the v2.1 auto fallback when DSL is fp32-only and op_desc is
#      bf16/fp16) wastes 3-5× HBM bandwidth.
#
# When to study this file (the fp32 instance)
#   - Building an elementwise activation whose ModelNew passes fp32 tensors.
#   - First-prototype phase: get correctness in fp32 first, then either keep
#     this version (if caller stays fp32) or copy to a `_bf16.py` sibling
#     and add cast() + dual UB tiles for bf16/fp16 deployment.
#
# Patterns demonstrated
#   1. 2-D UB allocation `[1, TILE_N]` (current easyasc rejects 1-D shapes).
#   2. Row-then-column tiling: outer `for r` partitioned across vec cores via
#      GetVecNum/GetVecIdx, inner `for c` column tiling.
#   3. Tail handling for `N % TILE_N != 0` via `count = Min(TILE_N, N - n_off)`.
#   4. `muls(dst, src, scalar_var)` — uses a runtime Var scalar so the bridge
#      can expose negative_slope/alpha/beta as a pybind arg.
#
# Verified end-to-end via simulator self-check (3 shapes including non-aligned).
# ============================================================================================
#
# easyasc DSL for LeakyReLU activation (fp32-instance):
#     y = max(x, 0) + min(x, 0) * negative_slope
#
# Equivalent to `torch.nn.functional.leaky_relu(x, negative_slope=...)`.
#
# Layout (per cake convention — bridge derives M = numel/last_dim, N = size(-1))
#   - inputs   : x  GMTensor [M, N]   (fp32; logical 2-D view, flatten any rank)
#   - outputs  : y  GMTensor [M, N]   (fp32)
#   - vars     : M (row count, runtime), N (last-dim, runtime),
#                negative_slope (float Var, runtime — passed by bridge or host)
# ============================================================================================
from easyasc.a2 import *
import torch


# Compile-time column tile size. Kept off the Var list so the bridge dim-alias
# mapping stays clean (only M / N / H / D / K are recognized dim aliases).
#
# ⚠ TILE_N = 1024 IS CONSERVATIVE — only 16 KB UB usage (8% of 192 KB budget).
# For real workloads, prefer a larger TILE_N. Empirically (mish_bf16 with
# identical 4-tile structure):
#     TILE_N=1024 → 20 KB (10%) — 8 col-tile-loop iters for N=8192
#     TILE_N=2048 → 40 KB (21%) — 4 iters
#     TILE_N=4096 → 80 KB (42%) — 2 iters
#     TILE_N=8192 → 160 KB (83%) — 1 iter, no col loop overhead
# Each doubling halves the inner col-loop count without changing precision.
# Rule of thumb: pick TILE_N = max(N) if your op_desc's largest N fits the
# UB tile-count × dtype-bytes budget; otherwise pick the largest power of 2
# such that (num_fp32_tiles × 4 + num_lo_tiles × 2) × TILE_N ≤ 160 KB.
# This file keeps TILE_N=1024 only because it's the smoke-test reference;
# for production, run `scripts/check_ub_usage.py` after self-check and bump
# TILE_N until UB usage ≥ 60%.
TILE_N = 1024


@kernel()
def leaky_relu_custom(
    x: GMTensor, y: GMTensor,
    M: Var, N: Var, negative_slope: Var,
):
    """LeakyReLU 内核：y = max(x, 0) + min(x, 0) * negative_slope。

    fp32 输入/输出，4 个 fp32 UB tile，无 cast。这是 elementwise 双分支
    activation 的 fp32 范本。要服务 bf16/fp16 caller，复制到 _bf16.py 并
    在 GM↔UB 边界加 cast()（见 mish_bf16.py 范本）。
    """
    # On-chip scratch — 2-D required by easyasc UB allocator.
    ub_x = Tensor(DT.float, [1, TILE_N], Position.UB)
    ub_pos = Tensor(DT.float, [1, TILE_N], Position.UB)
    ub_neg = Tensor(DT.float, [1, TILE_N], Position.UB)
    ub_out = Tensor(DT.float, [1, TILE_N], Position.UB)

    # Row partitioning across vec cores. Tail core gets fewer rows via Min(...).
    rows_per_core = CeilDiv(M, GetVecNum())
    r_begin = Var(rows_per_core * GetVecIdx())
    r_end = Min(r_begin + rows_per_core, M)

    # Column tiling — covers any N at runtime; tail tile via Min(...).
    cols_per_row = CeilDiv(N, TILE_N)

    for r in range(r_begin, r_end):
        for c in range(0, cols_per_row):
            with auto_sync():
                n_off = Var(c * TILE_N)
                count = Min(TILE_N, N - n_off)

                # GM → UB
                ub_x <<= x[r:r + 1, n_off:n_off + count]

                # Positive branch: pos = max(x, 0)
                ub_pos <<= maximum(ub_x[0:1, 0:count], 0.0)

                # Negative branch: neg = min(x, 0) * negative_slope
                ub_neg <<= minimum(ub_x[0:1, 0:count], 0.0)
                muls(ub_neg, ub_neg, negative_slope)  # Var scalar → broadcast over the row

                # Combine: out = pos + neg
                add(ub_out, ub_pos, ub_neg)

                # UB → GM
                y[r:r + 1, n_off:n_off + count] <<= ub_out[0:1, 0:count]

    return y


def build_codegen_inputs():
    """Single source of truth — order matches kernel: (x, y, M, N, negative_slope).

    Returns fp32 tensors → codegen registers DT_FLOAT → kernel binary natively
    serves fp32 callers (no cast layer in bridge). To serve bf16/fp16 callers,
    use the `mish_bf16.py` instance instead.
    """
    torch.manual_seed(0)
    M, N = 4 * 128, 4096
    x = torch.rand(M, N, dtype=torch.float32) * 4.0 - 2.0   # [-2, 2)，约半正半负
    y = torch.zeros(M, N, dtype=torch.float32)
    negative_slope = 0.01
    return (x, y, M, N, negative_slope)


def main():
    # --- shape 1: FFN-medium (M=512, N=4096) ---
    args = build_codegen_inputs()
    x = args[0]
    negative_slope = args[4]
    y_kernel = OpExec(leaky_relu_custom, simulator=True)(*args)
    y_ref = torch.nn.functional.leaky_relu(x, negative_slope=negative_slope)
    torch.testing.assert_close(y_kernel, y_ref, rtol=1e-6, atol=1e-6)
    print(f"[shape1 M={args[2]} N={args[3]}] max_abs_diff={torch.abs(y_kernel - y_ref).max().item():.6e}")

    # --- shape 2: different shape + different slope (proves Var-parametric) ---
    torch.manual_seed(1)
    M2, N2 = 64, 256
    x2 = torch.rand(M2, N2, dtype=torch.float32) * 10.0 - 5.0
    y2 = torch.zeros(M2, N2, dtype=torch.float32)
    slope2 = 0.2
    y_kernel2 = OpExec(leaky_relu_custom, simulator=True)(x2, y2, M2, N2, slope2)
    y_ref2 = torch.nn.functional.leaky_relu(x2, negative_slope=slope2)
    torch.testing.assert_close(y_kernel2, y_ref2, rtol=1e-6, atol=1e-6)
    print(f"[shape2 M={M2} N={N2} slope={slope2}] max_abs_diff={torch.abs(y_kernel2 - y_ref2).max().item():.6e}")

    # --- shape 3: non-aligned last-dim (exercises tail tile) ---
    torch.manual_seed(2)
    M3, N3 = 3 * 77, 1023
    x3 = torch.rand(M3, N3, dtype=torch.float32) * 4.0 - 2.0
    y3 = torch.zeros(M3, N3, dtype=torch.float32)
    slope3 = 0.05
    y_kernel3 = OpExec(leaky_relu_custom, simulator=True)(x3, y3, M3, N3, slope3)
    y_ref3 = torch.nn.functional.leaky_relu(x3, negative_slope=slope3)
    torch.testing.assert_close(y_kernel3, y_ref3, rtol=1e-6, atol=1e-6)
    print(f"[shape3 M={M3} N={N3} slope={slope3}] max_abs_diff={torch.abs(y_kernel3 - y_ref3).max().item():.6e}")

if __name__ == "__main__":
    main()
