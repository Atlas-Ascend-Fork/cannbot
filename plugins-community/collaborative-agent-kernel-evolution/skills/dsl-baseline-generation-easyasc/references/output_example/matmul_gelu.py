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
# matmul_gelu — easyasc A2 (ascend910b) fused cube GEMM + AIV GELU epilogue.
#
# 来源:  CAKE2-easydsl-v2/skills/dsl-baseline-generation-cv/references/
#        output_example/matmul_gelu.py  (CV DSL, tile.language)
# 语义:  d = gelu(A @ B)      A[M,K] fp16, B[K,N] fp16, D[M,N] fp16
#        GELU 用 tanh 近似 (与 CV 源同一公式):
#          g(x) = x * sigmoid(1.595769121 * (x + 0.044715 x^3))
#        源里写成 x / (1 + exp(NEG_SQRT_EIGHT_OVER_PI*(x^3 + TANH_FACTOR*x))),
#        其中 NEG_SQRT_EIGHT_OVER_PI = -1.595769121*0.044715,
#             TANH_FACTOR = 1/0.044715. 展开后 == 上式, 这里直接复用源公式。
#
# 验证:  simulator + 910B2 real NPU (ASCEND_RT_VISIBLE_DEVICES=3), rtol/atol 1e-3.
#
# 排布 (cube+AIV 两段流水, 复用 quant_matmul_dsl.py 的 mmad + ws ping-pong):
#   CUBE: 每个输出 tile [TILE_M,TILE_N], 在 K 方向 matmul 累加到 fp32 L0C,
#         再把 L0C 存到 per-core GM workspace ping-pong slot。
#   AIV : 两个 subcore 各处理 tile 的一半行, s32->跳过(这里是 fp32), 读回 ws,
#         做 GELU, cast fp16, 写 D。CvMutex(0/1) 做 cube->vec 交接。
#   尾块: M 任意; K/N 由 host pad 到 TILE_K/TILE_N 倍数 (B 转置成 [N,K] staging,
#         与 grouped_matmul.py 一致, 避免 partial-K NZ zero-pad device-stale 分支)。
#         非对齐 N 的尾块只写 valid_n 列。
# ============================================================================
from easyasc.a2 import *
import torch

from easyasc import globvars as _gv
_gv.device_type = 'b2'
_gv.core_num = 24

TILE_M = 128
TILE_N = 128
TILE_K = 128
ROWS = TILE_M // 2          # rows per AIV subcore (64)
HALF_ROWS = ROWS // 2       # 32, cast in two halves to keep <=128 repeats

A2_CUBE_NUM = 24

# GELU tanh-approx constants (identical to the CV source).
NEG_SQRT_EIGHT_OVER_PI = -1.595769121 * 0.044715
TANH_APPROX_FACTOR = 1.0 / 0.044715


@kernel()
def matmul_gelu_custom(
    A: GMTensor, B: GMTensor, D: GMTensor,
    M: Var, K: Var, N: Var,
):
    ws = split_workspace(DT.float, [A2_CUBE_NUM, 2, TILE_M, TILE_N], name="ws")

    cv0 = CvMutex(0)
    cv1 = CvMutex(1)

    l1a = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1b = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)   # B staged [N,K] (transposed by host)
    l0c = Tensor(DT.float, [TILE_M, TILE_N], Position.L0C)  # full L0C, single buffer

    # AIV UB buffers (fp32 compute, fp16 out).
    c_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)   # matmul result
    t_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)   # temp
    o_ub = Tensor(DT.half, [ROWS, TILE_N], Position.UB)   # fp16 out

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
            n0 = Var(nt * TILE_N)
            valid_m = Min(TILE_M, M - m0)
            valid_n = Min(TILE_N, N - n0)
            it = Var((t - GetCubeIdx()) // core_step)
            slot = Var(it % 2)

            # ----- CUBE: mmad over K into fp32 L0C -----
            tiles_k = CeilDiv(K, TILE_K)
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
                bbuf[0:valid_n, 0:valid_k] <<= B[n0:n0 + valid_n, k0:k0 + valid_k]
                # matmul(dst, l1a[M,K], l1b[N,K]) computes l1a @ l1b^T = A @ B.
                matmul(l0c, abuf, bbuf, is_init=(kt == 0))
                l1_cnt += 1

            # ----- CUBE store L0C -> ws ping-pong slot -----
            with If(slot == 0):
                cv0.lock()
                ws[GetCubeIdx(), 0, 0:TILE_M, 0:TILE_N] <<= l0c
                cv0.ready()
            with Else():
                cv1.lock()
                ws[GetCubeIdx(), 1, 0:TILE_M, 0:TILE_N] <<= l0c
                cv1.ready()

            # ----- VEC GELU epilogue -----
            vrows = Max(Min(ROWS, valid_m - row0), 0)
            with If(slot == 0):
                cv0.wait()
                with If(vrows > 0):
                    c_ub[0:vrows, 0:TILE_N] <<= ws[GetCubeIdx(), 0, row0:row0 + vrows, 0:TILE_N]
                    _gelu_band(c_ub, t_ub, o_ub, vrows, D, m0 + row0, n0, valid_n)
                cv0.free()
            with Else():
                cv1.wait()
                with If(vrows > 0):
                    c_ub[0:vrows, 0:TILE_N] <<= ws[GetCubeIdx(), 1, row0:row0 + vrows, 0:TILE_N]
                    _gelu_band(c_ub, t_ub, o_ub, vrows, D, m0 + row0, n0, valid_n)
                cv1.free()

    return D


def _gelu_band(c_ub, t_ub, o_ub, vrows, D, ym0, n0, valid_n):
    """GELU (tanh approx) on a [vrows, TILE_N] fp32 band, then cast->fp16, write.
       g = x / (1 + exp(NEG_SQRT_EIGHT_OVER_PI*(x^3 + TANH_FACTOR*x)))
       全 band 操作 (vrows<=64, TILE_N=256 -> <=256 reps), 但 mul/exp/div 等
       逐行 count=TILE_N 时只 4 reps; 这里用整 band op, vrows<=64 时
       vrows*256/64 = 256 reps > 255, 所以分两个 row-half 做。"""
    h0 = Min(HALF_ROWS, vrows)
    h1 = Max(vrows - HALF_ROWS, 0)

    def _half(r0, rn):
        cs = c_ub[r0:r0 + rn, 0:TILE_N]
        ts = t_ub[r0:r0 + rn, 0:TILE_N]
        os = o_ub[r0:r0 + rn, 0:TILE_N]
        # t = x^3
        mul(ts, cs, cs)
        mul(ts, ts, cs)
        # t = x^3 + TANH_FACTOR * x
        axpy(ts, cs, TANH_APPROX_FACTOR)
        # t = NEG_SQRT_EIGHT_OVER_PI * t
        muls(ts, ts, NEG_SQRT_EIGHT_OVER_PI)
        # t = exp(t); t = t + 1; t = x / t
        exp(ts, ts)
        adds(ts, ts, 1.0)
        div(ts, cs, ts)
        # cast fp32 -> fp16
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
    """A[M,K] fp16, B[K,N] fp16 -> pad K to TILE_K, N to TILE_N, transpose B to
    [N,K] (matmul reads l1b as [N,K] then computes A @ B^T = A@B). Returns
    (Ap, Bt, M, Kp, Np)."""
    M, K = A.shape
    K2, N = B.shape
    assert K2 == K
    Kp = _ceil_mult(K, ALIGN_K)
    Np = _ceil_mult(N, ALIGN_N)
    Ap = torch.zeros(M, Kp, dtype=torch.float16)
    Ap[:, :K] = A
    Bp = torch.zeros(Kp, Np, dtype=torch.float16)
    Bp[:K, :N] = B
    Bt = Bp.t().contiguous()        # [Np, Kp]
    return Ap, Bt, M, Kp, Np


def build_codegen_inputs():
    # Distinct M, K, N. K,N multiples of TILE so interior tiles are full.
    M, K, N = 512, 256, 256
    A = torch.randn(M, K, dtype=torch.float16)
    B = torch.randn(K, N, dtype=torch.float16)
    Ap, Bt, Mk, Kp, Np = pad_inputs(A, B)
    D = torch.zeros(Mk, Np, dtype=torch.float16)
    return (Ap, Bt, D, Mk, Kp, Np)


def _run(simulator, M, K, N):
    A = torch.randn(M, K, dtype=torch.float16)
    B = torch.randn(K, N, dtype=torch.float16)
    Ap, Bt, Mk, Kp, Np = pad_inputs(A, B)
    Dp = torch.zeros(Mk, Np, dtype=torch.float16)
    outp = OpExec(matmul_gelu_custom, simulator=simulator)(
        Ap, Bt, Dp, Mk, Kp, Np,
        shape_bindings={0: [0, 1], 1: [2, 1], 2: [0, 2]})
    out = outp[:M, :N].float()
    ref = torch.nn.functional.gelu(A.float() @ B.float()).float()
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
        # `--dev` runs OpExec(simulator=False) on a real 910B. The codegen-emitted
        # op_kernel/tensorutils.h still carries a5-only refs (PaddingMode /
        # QF322F32_PRE / fp8 / hif8) that don't compile on a2; a small build hook
        # (`devrun`) patches them under #ifdef __DAV_C310__ before b.sh — same
        # patch as output/quant_matmul/patch_tensorutils.py. Optional; device-only.
        try:
            import devrun  # noqa: F401
        except ImportError:
            pass
    shapes = [(256, 256, 256), (200, 320, 192)]   # one aligned, one non-64-aligned
    all_ok = True
    for (M, K, N) in shapes:
        all_ok = _run(sim, M, K, N) and all_ok
    print("ALL PASS" if all_ok else "SOME FAILED")

if __name__ == "__main__":
    main()
