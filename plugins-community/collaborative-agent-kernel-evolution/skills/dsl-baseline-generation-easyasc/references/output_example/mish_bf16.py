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
# CANONICAL reference for the **mixed-dtype elementwise activation** pattern in cake.
#
# This is the bf16 counterpart of `leaky_relu.py`. It demonstrates the
# **kernel-side cast** (fm-easyasc style) — the right way to serve bf16/fp16
# callers without the 3-5× HBM penalty of host-side cast.
#
# When to study this file
#   - Bandwidth-bound elementwise activations (mish/gelu/swish/sigmoid/...) where
#     the caller dtype is bf16 or fp16.
#   - Any op where DSL keeps fp32 for precision but inputs/outputs are bf16/fp16.
#
# Pattern demonstrated — "ladder UB" (per tile):
#   1. Allocate TWO sets of UB tiles per tensor:
#        - low-precision (bf16/fp16) for GM ↔ UB transfers
#        - fp32 for actual math
#   2. Per tile loop iteration:
#        a. GM (bf16) → UB (bf16)   via gm_to_ub_pad   [low-precision in]
#        b. UB (bf16) → UB (fp32)   via cast()         [upcast, UB-local, zero HBM]
#        c. fp32 math (exp/ln/...)
#        d. UB (fp32) → UB (bf16)   via cast()         [downcast]
#        e. UB (bf16) → GM (bf16)   via ub_to_gm_pad   [low-precision out]
#
# Why this beats host-side cast (the v2.1 default when DSL is fp32-only):
#   - Host cast: bf16 input is read at fp16-rate (32MB), expanded to fp32 (64MB write),
#     fed to kernel which reads/writes fp32 (128MB), then host casts output back
#     (64MB read + 32MB write).  TOTAL HBM = 320 MB for a 32 MB workload.
#   - Kernel-side cast: GM stays bf16 throughout (32MB read + 32MB write = 64MB).
#     The cast happens inside UB, which is on-chip — zero HBM cost.
#   - For bandwidth-bound ops, this is a 3-5× speedup with zero precision loss.
#
# Comparison with `leaky_relu.py` (the fp32 quick-path)
#   leaky_relu.py: Tensor(DT.float, [1, TILE_N]) × 4 tiles, no cast(), fp32 input.
#   THIS FILE:     Tensor(DT.bfloat16, [1, TILE_N]) × 2  +
#                  Tensor(DT.float,    [1, TILE_N]) × 4  +
#                  4 cast() calls per tile iteration.
#
# When to use the leaky_relu fp32 quick-path vs this bf16 mixed-dtype path
#   - fp32 quick-path: when caller dtype IS fp32, or when bandwidth doesn't matter
#     (e.g. tiny tensors < 1MB total). Simpler to write.
#   - bf16 mixed-dtype (THIS FILE): when caller dtype is bf16/fp16 AND the op is
#     bandwidth-bound (which most elementwise/norm ops are). Required for
#     production-quality bf16 LLM inference kernels.
#
# Verified end-to-end via simulator self-check (3 shapes including non-aligned bf16).
# ============================================================================================
#
# easyasc DSL for Mish activation (bf16-native):
#     y = x * tanh(softplus(x)) = x * tanh(ln(1 + exp(x)))
#
# Layout
#   - inputs   : x  GMTensor [M, N]   (bf16; dtype set by build_codegen_inputs)
#   - outputs  : y  GMTensor [M, N]   (bf16)
#   - vars     : M (rows), N (last-dim)
# ============================================================================================
from easyasc.a2 import *
import torch


# ⚠ TILE_N = 1024 is conservative — empirically (this file, N=8192):
#     TILE_N=1024 → 20 KB (10%)   TILE_N=2048 → 40 KB (21%)
#     TILE_N=4096 → 80 KB (42%)   TILE_N=8192 → 160 KB (83%)
# For production, bump TILE_N until UB Usage ≥ 60% (run check_ub_usage.py
# on simulator output to verify). UB budget formula:
#   (num_fp32_tiles × 4 + num_bf16_tiles × 2) × TILE_N ≤ 160 KB.
# Current allocation: 4 fp32 + 2 bf16 ⇒ 20 bytes/elem ⇒ max TILE_N ≈ 8192.
TILE_N = 1024  # compile-time col tile (conservative — see comment above)


@kernel()
def mish_custom(
    x: GMTensor, y: GMTensor,
    M: Var, N: Var,
):
    """Mish (bf16 in / bf16 out) — y = x * tanh(softplus(x)).

    All math happens in fp32 on UB; GM transfers stay bf16. Per-tile cost:
    2 cast() calls (in/out) + 9 fp32 math ops. UB usage: ~20 KB / 192 KB.
    """
    # Low-precision tiles for GM ↔ UB transfers (bf16, 2 bytes/elem).
    ub_x_bf = Tensor(DT.bfloat16, [1, TILE_N], Position.UB)   # 2 KB
    ub_y_bf = Tensor(DT.bfloat16, [1, TILE_N], Position.UB)   # 2 KB

    # fp32 tiles for actual computation (4 bytes/elem each).
    ub_x_fp = Tensor(DT.float, [1, TILE_N], Position.UB)   # 4 KB
    ub_t_fp = Tensor(DT.float, [1, TILE_N], Position.UB)   # 4 KB — exp/ln/exp pipeline
    ub_num_fp = Tensor(DT.float, [1, TILE_N], Position.UB)   # 4 KB — tanh numerator
    ub_out_fp = Tensor(DT.float, [1, TILE_N], Position.UB)   # 4 KB — y_fp before cast-down

    # Row partitioning across vec cores.
    rows_per_core = CeilDiv(M, GetVecNum())
    r_begin = Var(rows_per_core * GetVecIdx())
    r_end = Min(r_begin + rows_per_core, M)

    cols_per_row = CeilDiv(N, TILE_N)

    for r in range(r_begin, r_end):
        for c in range(0, cols_per_row):
            with auto_sync():
                n_off = Var(c * TILE_N)
                count = Min(TILE_N, N - n_off)

                # ── Stage 1: GM → UB (bf16) → UB (fp32) — low-precision in + upcast ──
                ub_x_bf <<= x[r:r + 1, n_off:n_off + count]
                cast(ub_x_fp[0:1, 0:count], ub_x_bf[0:1, 0:count])

                # ── Stage 2: fp32 math — numerically-stable tanh(softplus(x)) ──
                # softplus(x) = ln(1 + exp(x)),  always >= 0
                exp(ub_t_fp, ub_x_fp[0:1, 0:count])             # t = exp(x)
                adds(ub_t_fp, ub_t_fp, 1.0)                     # t = 1 + exp(x)
                ln(ub_t_fp, ub_t_fp)                            # t = softplus(x) = ln(1+exp(x))

                # tanh(s) for s>=0: stable form (1 - exp(-2s)) / (1 + exp(-2s))
                muls(ub_t_fp, ub_t_fp, -2.0)                    # t = -2*s         (<= 0)
                exp(ub_t_fp, ub_t_fp)                           # t = exp(-2*s) = e  (in (0, 1])

                muls(ub_num_fp, ub_t_fp, -1.0)                  # num = -e
                adds(ub_num_fp, ub_num_fp, 1.0)                 # num = 1 - e
                adds(ub_t_fp, ub_t_fp, 1.0)                     # t   = 1 + e
                div(ub_num_fp, ub_num_fp, ub_t_fp)              # num = tanh(softplus(x))

                # y = x * tanh(softplus(x))
                mul(ub_out_fp, ub_x_fp[0:1, 0:count], ub_num_fp[0:1, 0:count])

                # ── Stage 3: UB (fp32) → UB (bf16) → GM (bf16) — downcast + low-precision out ──
                cast(ub_y_bf[0:1, 0:count], ub_out_fp[0:1, 0:count])
                y[r:r + 1, n_off:n_off + count] <<= ub_y_bf[0:1, 0:count]

    return y


def build_codegen_inputs():
    """REQUIRED: builds bf16 tensors so codegen registers the op with DT_BF16.

    This is the key difference from the fp32 quick-path: tensors here are bf16,
    NOT fp32. The DSL kernel above declares both bf16 and fp32 UB tiles and
    casts between them — but the public-facing GMTensor dtype is whatever
    `build_codegen_inputs` passes in.
    """
    torch.manual_seed(0)
    M, N = 4 * 128, 4096
    x = (torch.rand(M, N, dtype=torch.float32) * 4.0 - 2.0).bfloat16()   # bf16, [-2, 2)
    y = torch.zeros(M, N, dtype=torch.bfloat16)
    return (x, y, M, N)


def main():
    # ---- shape 1: aligned (basic path) ----
    args = build_codegen_inputs()
    x = args[0]
    y_kernel = OpExec(mish_custom, simulator=True)(*args)
    y_ref = torch.nn.functional.mish(x.float()).bfloat16()
    diff = torch.abs(y_kernel.float() - y_ref.float()).max().item()
    # bf16 has ~3 decimal digits; mish range here is [-1, 1], so a few ULP
    # is acceptable. Threshold ~ 2^-6 ≈ 0.016 is generous.
    torch.testing.assert_close(y_kernel, y_ref, rtol=2e-2, atol=2e-2)
    print(f"[shape1 M={args[2]} N={args[3]}] bf16 max_abs_diff={diff:.6e}")

    # ---- shape 2: non-aligned tail ----
    torch.manual_seed(1)
    M2, N2 = 3 * 77, 1023
    x2 = (torch.rand(M2, N2, dtype=torch.float32) * 10.0 - 5.0).bfloat16()
    y2 = torch.zeros(M2, N2, dtype=torch.bfloat16)
    y_k2 = OpExec(mish_custom, simulator=True)(x2, y2, M2, N2)
    y_r2 = torch.nn.functional.mish(x2.float()).bfloat16()
    diff2 = torch.abs(y_k2.float() - y_r2.float()).max().item()
    torch.testing.assert_close(y_k2, y_r2, rtol=2e-2, atol=2e-2)
    print(f"[shape2 M={M2} N={N2}] bf16 max_abs_diff={diff2:.6e}")

    # ---- shape 3: multi col-tile per row + wider value range ----
    torch.manual_seed(2)
    M3, N3 = 16, 4097
    x3 = (torch.rand(M3, N3, dtype=torch.float32) * 20.0 - 10.0).bfloat16()
    y3 = torch.zeros(M3, N3, dtype=torch.bfloat16)
    y_k3 = OpExec(mish_custom, simulator=True)(x3, y3, M3, N3)
    y_r3 = torch.nn.functional.mish(x3.float()).bfloat16()
    diff3 = torch.abs(y_k3.float() - y_r3.float()).max().item()
    torch.testing.assert_close(y_k3, y_r3, rtol=2e-2, atol=2e-2)
    print(f"[shape3 M={M3} N={N3}] bf16 max_abs_diff={diff3:.6e}")

if __name__ == "__main__":
    main()
