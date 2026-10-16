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
# matmul_bias_relu — easyasc A2 (ascend910b) fp16 cube matmul + FUSED AIV
# bias-add + ReLU epilogue.
#
# Origin : ported from CAKE2-easydsl-v2 dsl-baseline-generation-cv
#          references/output_example/matmul_bias_relu.py (tile.language CV DSL).
# Verify : simulator + real NPU (ASCEND_RT_VISIBLE_DEVICES=2, 910B2) — see
#          __main__; both PASS (see port report).
#
# Math (identical to source):
#     C = A[M,K] @ B[K,N]                      (fp32 cube accumulate)
#     D = fp16( relu( C + bias[N] ) )          (bias broadcast along M, fp16 I/O)
#
# Two-stage CV-fused pipeline (mirrors quant_matmul_dsl.py, fp16):
#   CUBE (AIC): matmul() accumulates A@B over K into a fp32 L0C tile, stores to
#               a per-core GM ping-pong workspace slot; CvMutex handoff.
#   VEC  (AIV): 2 AIV subcores split TILE_M rows. Each loads its fp32 matmul
#               band (ws), loads bias[n0:n0+TILE_N] once (cast fp16->fp32),
#               per-row adds the broadcast bias, applies relu (clamp min 0),
#               casts fp32->fp16, writes the valid cols.
#
# Tiling / capacity (a2 910B2, 24 cube cores):
#   TILE_M=128, TILE_N=128, TILE_K=128. DBuff L0C fp32 [128,128]*2=128KB (full
#   L0C). L1 a/b fp16 [128,128]=32KB (DBuff 64KB). Per-AIV UB: f32 band
#   [64,128]=32KB + f16 band [64,128]=16KB + bias rows [1,128] tiny << 192KB.
#   24-core flat-tile round-robin; tensorutils.h a2-compat patch via device_verify.
# ============================================================================
from easyasc.a2 import *
import torch

# ---- a2 24-core override (910B2/B3) — do NOT modify the shared easyasc lib ----
from easyasc import globvars as _gv
_gv.device_type = 'b2'
_gv.core_num = 24

TILE_M = 128
TILE_N = 128
TILE_K = 128
ROWS = TILE_M // 2          # rows per AIV subcore (64)

A2_CUBE_NUM = 24


@kernel()
def matmul_bias_relu_custom(
    A: GMTensor, B: GMTensor, bias: GMTensor, D: GMTensor,
    M: Var, N: Var, K: Var,
):
    ws = split_workspace(DT.float, [A2_CUBE_NUM, 2, TILE_M, TILE_N], name="ws")

    cv0 = CvMutex(0)
    cv1 = CvMutex(1)

    l1a = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1b = DBuff(DT.half, [TILE_K, TILE_N], Position.L1)   # stored [K,N], read .T
    l0c = DBuff(DT.float, [TILE_M, TILE_N], Position.L0C)

    f32_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)
    f16_ub = Tensor(DT.half, [ROWS, TILE_N], Position.UB)
    bias_h_ub = Tensor(DT.half, [1, TILE_N], Position.UB)
    bias_f_ub = Tensor(DT.float, [1, TILE_N], Position.UB)

    l1_cnt = Var(0)
    l0c_cnt = Var(0)

    tiles_m = CeilDiv(M, TILE_M)
    tiles_n = CeilDiv(N, TILE_N)
    total_tiles = Var(tiles_m * tiles_n)
    tiles_k = CeilDiv(K, TILE_K)

    core_step = Var(1, DT.int)
    core_step <<= GetCubeNum()

    sb = GetSubBlockIdx()
    row0 = Var(sb * ROWS)

    with auto_sync():
        for t in range(GetCubeIdx(), total_tiles, core_step):
            mt = Var(t // tiles_n)
            nt = Var(t % tiles_n)
            m0 = Var(mt * TILE_M)
            n0 = Var(nt * TILE_N)
            valid_m = Min(TILE_M, M - m0)
            valid_n = Min(TILE_N, N - n0)
            it = Var((t - GetCubeIdx()) // core_step)
            slot = Var(it % 2)

            # ----- CUBE: A@B over K into one fp32 L0C tile -----
            lc = l0c[l0c_cnt]
            for kt in range(0, tiles_k):
                k0 = Var(kt * TILE_K)
                valid_k = Min(TILE_K, K - k0)
                abuf = l1a[l1_cnt]
                bbuf = l1b[l1_cnt]
                with If(valid_m < TILE_M):
                    set_constant_to_l1(abuf, 0.0)
                with If(valid_k < TILE_K):
                    set_constant_to_l1(abuf, 0.0)
                    set_constant_to_l1(bbuf, 0.0)
                with If(valid_n < TILE_N):
                    set_constant_to_l1(bbuf, 0.0)
                abuf[0:valid_m, 0:valid_k] <<= A[m0:m0 + valid_m, k0:k0 + valid_k]
                bbuf[0:valid_k, 0:valid_n] <<= B[k0:k0 + valid_k, n0:n0 + valid_n]
                matmul(lc, abuf, bbuf.T, m=TILE_M, n=TILE_N, k=TILE_K,
                       is_init=(kt == 0))
                l1_cnt += 1

            with If(slot == 0):
                cv0.lock()
                ws[GetCubeIdx(), 0, 0:TILE_M, 0:TILE_N] <<= lc
                cv0.ready()
            with Else():
                cv1.lock()
                ws[GetCubeIdx(), 1, 0:TILE_M, 0:TILE_N] <<= lc
                cv1.ready()
            l0c_cnt += 1

            # ----- VEC bias-add + ReLU epilogue (2 AIV subcores split rows) -----
            vrows = Max(Min(ROWS, valid_m - row0), 0)
            bias_h_ub[0:1, 0:valid_n] <<= bias[n0:n0 + valid_n]
            cast(bias_f_ub[0:1, 0:TILE_N], bias_h_ub[0:1, 0:TILE_N])

            with If(slot == 0):
                cv0.wait()
                with If(vrows > 0):
                    f32_ub[0:vrows, 0:TILE_N] <<= ws[GetCubeIdx(), 0, row0:row0 + vrows, 0:TILE_N]
                    _bias_relu_band(f32_ub, f16_ub, bias_f_ub, vrows, D, m0 + row0, n0, valid_n)
                cv0.free()
            with Else():
                cv1.wait()
                with If(vrows > 0):
                    f32_ub[0:vrows, 0:TILE_N] <<= ws[GetCubeIdx(), 1, row0:row0 + vrows, 0:TILE_N]
                    _bias_relu_band(f32_ub, f16_ub, bias_f_ub, vrows, D, m0 + row0, n0, valid_n)
                cv1.free()

    return D


def _bias_relu_band(f32_ub, f16_ub, bias_f_ub, vrows, D, ym0, n0, valid_n):
    """D[band] = fp16( relu( matmul_band(fp32) + bias[N](fp32) ) ). Per-row
    broadcast bias-add (count=TILE_N each), a single relu over the whole band,
    then fp32->fp16 cast. A full [64,128] band = 128 repeats (<255)."""
    for r in range(0, vrows):
        add(f32_ub[r:r + 1, 0:TILE_N], f32_ub[r:r + 1, 0:TILE_N],
            bias_f_ub[0:1, 0:TILE_N], count=TILE_N)
    relu(f32_ub[0:vrows, 0:TILE_N], f32_ub[0:vrows, 0:TILE_N], count=vrows * TILE_N)
    cast(f16_ub[0:vrows, 0:TILE_N], f32_ub[0:vrows, 0:TILE_N])
    D[ym0:ym0 + vrows, n0:n0 + valid_n] <<= f16_ub[0:vrows, 0:valid_n]


# ─────────────────────────── Host helpers ───────────────────────────

def build_codegen_inputs():
    M, K, N = 512, 128, 256
    A = torch.zeros(M, K, dtype=torch.float16)
    B = torch.zeros(K, N, dtype=torch.float16)
    bias = torch.zeros(N, dtype=torch.float16)
    D = torch.zeros(M, N, dtype=torch.float16)
    return (A, B, bias, D, M, N, K)


def main():
    torch.manual_seed(0)

    cases = [
        (256, 128, 256),    # aligned
        (130, 96, 200),     # non-aligned M and N, K not 128-multiple
    ]

    all_ok = True
    for (M, K, N) in cases:
        A = torch.randn(M, K, dtype=torch.float16)
        B = torch.randn(K, N, dtype=torch.float16)
        bias = torch.randn(N, dtype=torch.float16)
        D = torch.zeros(M, N, dtype=torch.float16)

        out = OpExec(matmul_bias_relu_custom, simulator=True)(
            A, B, bias, D, M, N, K,
            shape_bindings={0: [0, 2], 1: [2, 1], 2: [1], 3: [0, 1]})

        ref = torch.relu(A.float() @ B.float() + bias.float()).to(torch.float16).float()
        max_abs = torch.abs(out.float() - ref).max().item()
        ok = torch.allclose(out.float(), ref, rtol=1e-3, atol=1e-3)
        all_ok = all_ok and ok
        print(f"sim  (M={M},K={K},N={N}): {'PASS' if ok else 'FAIL'} "
              f"max_abs_diff={max_abs:.3e}")

    print("SIM ALL PASS" if all_ok else "SIM SOME FAILED")

    # --- real-NPU verification (ASCEND_RT_VISIBLE_DEVICES=2, 910B2) ---
    import os
    if os.environ.get("RUN_DEVICE") == "1":
        M, K, N = 256, 128, 256
        A = torch.randn(M, K, dtype=torch.float16)
        B = torch.randn(K, N, dtype=torch.float16)
        bias = torch.randn(N, dtype=torch.float16)
        D = torch.zeros(M, N, dtype=torch.float16)
        from device_verify import device_run
        out = device_run(matmul_bias_relu_custom, (A, B, bias, D, M, N, K),
                         {0: [0, 2], 1: [2, 1], 2: [1], 3: [0, 1]}, "matmul_bias_relu_dev")
        ref = torch.relu(A.float() @ B.float() + bias.float()).to(torch.float16).float()
        max_abs = torch.abs(out.float() - ref).max().item()
        ok = torch.allclose(out.float(), ref, rtol=1e-3, atol=1e-3)
        print(f"DEVICE (M={M},K={K},N={N}): {'PASS' if ok else 'FAIL'} "
              f"max_abs_diff={max_abs:.3e}")
        assert ok, "device result mismatch"

if __name__ == "__main__":
    main()
