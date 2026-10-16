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
# matmul_swiglu — easyasc A2 (ascend910b) fused cube GEMM + AIV SwiGLU epilogue.
#
# 来源:  CAKE2-easydsl-v2/skills/dsl-baseline-generation-cv/references/
#        output_example/matmul_swiglu.py  (CV DSL, tile.language)
# 语义:  mm = A @ B        A[M,K] fp16, B[K,2N] fp16  -> mm[M,2N]
#        left, right = mm[:, :N], mm[:, N:]
#        D = silu(left) * right    D[M,N] fp16,  silu(x)=x*sigmoid(x)=x/(1+exp(-x))
#
# 验证:  simulator + 910B2 real NPU (ASCEND_RT_VISIBLE_DEVICES=3), rtol/atol 1e-3.
#
# 排布 (cube+AIV 两段流水, 复用 quant_matmul_dsl.py 的 mmad + ws 结构):
#   每个输出 tile D[TILE_M, TILE_N] 对应 mm 的两个 N 分块: left=[n0,n0+TILE_N),
#   right=[N+n0, N+n0+TILE_N)。CUBE 对这两个分块各做一次 K 方向 matmul (B 列偏移
#   不同), 分别存到 per-core ws 的 slot0(left)/slot1(right)。AIV 两 subcore 各处理
#   tile 的一半行: 读回 left/right, silu(left)*right, cast fp16, 写 D。
#   尾块: M 任意; K/N 由 host pad 到 TILE 倍数 (B 转置成 [2N,K] staging)。
#         非对齐 N 尾块只写 valid_n 列。
# ============================================================================
from easyasc.a2 import *
import torch

from easyasc import globvars as _gv
_gv.device_type = 'b2'
_gv.core_num = 24

TILE_M = 128
TILE_N = 128
TILE_K = 128
ROWS = TILE_M // 2
HALF_ROWS = ROWS // 2

A2_CUBE_NUM = 24


@kernel()
def matmul_swiglu_custom(
    A: GMTensor, B: GMTensor, D: GMTensor,
    M: Var, K: Var, N: Var,
):
    # B is staged [2N, K] (host-transposed). TWON = 2*N.
    TWON = Var(2 * N)
    # ws: slot0 = left matmul tile, slot1 = right matmul tile.
    ws = split_workspace(DT.float, [A2_CUBE_NUM, 2, TILE_M, TILE_N], name="ws")

    cvL = CvMutex(0)
    cvR = CvMutex(1)

    l1a = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1b = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l0c = Tensor(DT.float, [TILE_M, TILE_N], Position.L0C)

    left_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)
    right_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)
    t_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)
    o_ub = Tensor(DT.half, [ROWS, TILE_N], Position.UB)

    l1_cnt = Var(0)

    tiles_m = CeilDiv(M, TILE_M)
    tiles_n = CeilDiv(N, TILE_N)
    total_tiles = Var(tiles_m * tiles_n)

    core_step = Var(1)
    core_step <<= GetCubeNum()

    sb = GetSubBlockIdx()
    row0 = Var(sb * ROWS)

    with auto_sync("aggressive"):
        for t in range(GetCubeIdx(), total_tiles, core_step):
            mt = Var(t // tiles_n)
            nt = Var(t % tiles_n)
            m0 = Var(mt * TILE_M)
            n0 = Var(nt * TILE_N)              # column in the N-wide output
            valid_m = Min(TILE_M, M - m0)
            valid_n = Min(TILE_N, N - n0)
            nL = Var(n0)                        # left  col in [0, N)  of mm
            nR = Var(N + n0)                    # right col in [N, 2N) of mm

            # ----- CUBE: matmul left tile -> ws slot0 -----
            tiles_k = CeilDiv(K, TILE_K)
            cvL.lock()
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
                bbuf[0:valid_n, 0:valid_k] <<= B[nL:nL + valid_n, k0:k0 + valid_k]
                matmul(l0c, abuf, bbuf, is_init=(kt == 0))
                l1_cnt += 1
            ws[GetCubeIdx(), 0, 0:TILE_M, 0:TILE_N] <<= l0c
            cvL.ready()

            # ----- CUBE: matmul right tile -> ws slot1 -----
            cvR.lock()
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
                bbuf[0:valid_n, 0:valid_k] <<= B[nR:nR + valid_n, k0:k0 + valid_k]
                matmul(l0c, abuf, bbuf, is_init=(kt == 0))
                l1_cnt += 1
            ws[GetCubeIdx(), 1, 0:TILE_M, 0:TILE_N] <<= l0c
            cvR.ready()

            # ----- VEC SwiGLU epilogue -----
            vrows = Max(Min(ROWS, valid_m - row0), 0)
            cvL.wait()
            cvR.wait()
            with If(vrows > 0):
                left_ub[0:vrows, 0:TILE_N] <<= ws[GetCubeIdx(), 0, row0:row0 + vrows, 0:TILE_N]
                right_ub[0:vrows, 0:TILE_N] <<= ws[GetCubeIdx(), 1, row0:row0 + vrows, 0:TILE_N]
                _swiglu_band(left_ub, right_ub, t_ub, o_ub, vrows, D, m0 + row0, n0, valid_n)
            cvL.free()
            cvR.free()

    return D


def _swiglu_band(left_ub, right_ub, t_ub, o_ub, vrows, D, ym0, n0, valid_n):
    """D = silu(left)*right on a [vrows, TILE_N] band. silu(x)=x/(1+exp(-x))."""
    h0 = Min(HALF_ROWS, vrows)
    h1 = Max(vrows - HALF_ROWS, 0)

    def _half(r0, rn):
        ls = left_ub[r0:r0 + rn, 0:TILE_N]
        rs = right_ub[r0:r0 + rn, 0:TILE_N]
        ts = t_ub[r0:r0 + rn, 0:TILE_N]
        os = o_ub[r0:r0 + rn, 0:TILE_N]
        # t = exp(-left); t = 1 + t; t = left / t = silu(left)
        muls(ts, ls, -1.0)
        exp(ts, ts)
        adds(ts, ts, 1.0)
        div(ts, ls, ts)
        # t = silu(left) * right
        mul(ts, ts, rs)
        cast(os, ts)

    _half(0, h0)
    with If(h1 > 0):
        _half(HALF_ROWS, h1)

    D[ym0:ym0 + vrows, n0:n0 + valid_n] <<= o_ub[0:vrows, 0:valid_n]


# ─────────────────────────── Host helpers ───────────────────────────
ALIGN_K = 128
ALIGN_N = 128


def _ceil_mult(x, m):
    return ((x + m - 1) // m) * m


def pad_inputs(A, B):
    """把输入补齐到 TILE 倍数并转置 B。

    A[M,K] fp16, B[K,2N] fp16. Pad K to TILE_K, N (=half of B width) to TILE_N.
    Transpose padded B to [2*Np, Kp] so each matmul reads l1b as [N-tile, K].
    """
    M, K = A.shape
    K2, TWON = B.shape
    assert K2 == K and TWON % 2 == 0
    N = TWON // 2
    Kp = _ceil_mult(K, ALIGN_K)
    Np = _ceil_mult(N, ALIGN_N)
    Ap = torch.zeros(M, Kp, dtype=torch.float16)
    Ap[:, :K] = A
    # Build padded [Kp, 2*Np]: left half cols [0,Np), right half cols [Np,2Np).
    Bp = torch.zeros(Kp, 2 * Np, dtype=torch.float16)
    Bp[:K, :N] = B[:, :N]       # left
    Bp[:K, Np:Np + N] = B[:, N:TWON]   # right
    Bt = Bp.t().contiguous()           # [2*Np, Kp]
    return Ap, Bt, M, Kp, Np


def build_codegen_inputs():
    M, K, N = 512, 256, 128            # B is [K, 2N]=[256,256]
    A = torch.randn(M, K, dtype=torch.float16)
    B = torch.randn(K, 2 * N, dtype=torch.float16)
    Ap, Bt, Mk, Kp, Np = pad_inputs(A, B)
    D = torch.zeros(Mk, Np, dtype=torch.float16)
    return (Ap, Bt, D, Mk, Kp, Np)


def _run(simulator, M, K, N):
    A = torch.randn(M, K, dtype=torch.float16)
    B = torch.randn(K, 2 * N, dtype=torch.float16)
    Ap, Bt, Mk, Kp, Np = pad_inputs(A, B)
    Dp = torch.zeros(Mk, Np, dtype=torch.float16)
    outp = OpExec(matmul_swiglu_custom, simulator=simulator)(
        Ap, Bt, Dp, Mk, Kp, Np,
        shape_bindings={0: [0, 1], 1: [None, 1], 2: [0, 2]})
    out = outp[:M, :N].float()
    mm = (A.float() @ B.float())
    left, right = mm[:, :N], mm[:, N:]
    ref = (torch.nn.functional.silu(left) * right).float()
    abs_diff = torch.abs(out - ref)
    max_abs = abs_diff.max().item()
    ok = torch.allclose(out, ref, rtol=1e-3, atol=1e-3)
    pad = "" if (K % ALIGN_K == 0 and N % ALIGN_N == 0) else f" (pad K {K}->{Kp}, N {N}->{Np})"
    print(f"{'sim' if simulator else 'dev'} (M={M},K={K},N={N}): "
          f"{'PASS' if ok else 'FAIL'}  max_abs_diff={max_abs:.3e}{pad}")
    return ok


def main():
    import sys
    torch.manual_seed(0)
    sim = "--dev" not in sys.argv
    if not sim:
        # device-only a2-compat tensorutils.h build hook (see matmul_gelu.py /
        # output/quant_matmul/patch_tensorutils.py). Optional.
        try:
            import devrun  # noqa: F401
        except ImportError:
            pass
    shapes = [(256, 256, 256), (200, 256, 100)]   # one aligned, one non-128-aligned N
    all_ok = True
    for (M, K, N) in shapes:
        all_ok = _run(sim, M, K, N) and all_ok
    print("ALL PASS" if all_ok else "SOME FAILED")

if __name__ == "__main__":
    main()
