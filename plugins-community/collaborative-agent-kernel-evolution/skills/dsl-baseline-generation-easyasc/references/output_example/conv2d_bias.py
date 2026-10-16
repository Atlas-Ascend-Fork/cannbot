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
# conv2d_bias — easyasc A2 (ascend910b) fp16 cube matmul + FUSED AIV bias-add.
#
# Origin : ported from CAKE2-easydsl-v2 dsl-baseline-generation-cv
#          references/output_example/conv2d_bias.py (tile.language CV DSL).
# Verify : simulator + real NPU (ASCEND_RT_VISIBLE_DEVICES=2, 910B2) — see
#          __main__; both PASS (see port report).
#
# Math (identical to source, in the matmul-family framing the task specifies —
#   conv2d_bias = 1x1-conv-as-matmul + per-output-channel bias, post-added in
#   the AIV epilogue, exactly like matmul_bias_relu without the relu):
#     fmap [N,Cin,H,W] --(NHWC reshape)--> A [M=N*H*W, K=Cin]
#     weight [Cout,Cin,1,1] --(squeeze+T)--> B [K=Cin, N=Cout]
#     bias  [Cout]  (per-output-channel, broadcast over M)
#     out   D[M,N] = fp16( A@B + bias[N] )          (fp16 in, fp16 out)
#
# Two-stage CV-fused pipeline (mirrors quant_matmul_dsl.py, fp16 instead of i8):
#   CUBE (AIC): matmul() shortcut accumulates A@B over K into a fp32 L0C tile,
#               stores it to a per-core GM ping-pong workspace slot; the
#               CUBE->VEC handoff is a CvMutex (flag 0/1, ping-pong by per-core
#               iteration parity) so AIV drains one slot while cube fills the next.
#   VEC  (AIV): the 2 AIV subcores split the TILE_M rows (GetSubBlockIdx 0/1).
#               Each loads its fp32 row-band GM->UB, loads bias[n0:n0+TILE_N]
#               once (cast fp16->fp32), per-row adds bias, casts fp32->fp16, writes.
#
# Why an AIV bias epilogue (not the cube fixpipe BT bias): the a2 BT-bias path
#   has historically returned wrong values on device (grouped_matmul.py header),
#   so bias is added on the vector engine — matching the source DSL's vec post-add.
#
# Tiling / capacity (a2 910B2, 24 cube cores):
#   TILE_M=128, TILE_N=128, TILE_K=128. DBuff L0C fp32 [128,128]*2 = 128KB (full
#   L0C; single-buf L0C deadlocks the matmul-shortcut L0 ping-pong). L1 a/b
#   fp16 [128,128]=32KB (DBuff 64KB). Per-AIV UB: f32 band [64,128]=32KB +
#   f16 band [64,128]=16KB + bias rows [1,128] tiny << 192KB.
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
ROWS = TILE_M // 2          # rows handled by each of the 2 AIV subcores (64)

A2_CUBE_NUM = 24            # workspace first dim (GetCubeNum().value=0 -> 507015)


@kernel()
def conv2d_bias_custom(
    A: GMTensor, B: GMTensor, bias: GMTensor, D: GMTensor,
    M: Var, N: Var, K: Var,
):
    # Per-core GM workspace: 2 ping-pong slots of one fp32 [TILE_M, TILE_N] tile.
    ws = split_workspace(DT.float, [A2_CUBE_NUM, 2, TILE_M, TILE_N], name="ws")

    cv0 = CvMutex(0)
    cv1 = CvMutex(1)

    l1a = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1b = DBuff(DT.half, [TILE_K, TILE_N], Position.L1)   # stored [K,N], read .T
    l0c = DBuff(DT.float, [TILE_M, TILE_N], Position.L0C)

    # AIV UB: one fp32 band + one fp16 band (shared by both ping-pong slots,
    # drained sequentially) + the per-channel bias row (fp16 load + fp32 cast).
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

    sb = GetSubBlockIdx()                # 0 or 1: which AIV subcore
    row0 = Var(sb * ROWS)                # this subcore's row band within the tile

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

            # ----- CUBE store fp32 L0C -> per-core ws ping-pong slot -----
            with If(slot == 0):
                cv0.lock()
                ws[GetCubeIdx(), 0, 0:TILE_M, 0:TILE_N] <<= lc
                cv0.ready()
            with Else():
                cv1.lock()
                ws[GetCubeIdx(), 1, 0:TILE_M, 0:TILE_N] <<= lc
                cv1.ready()
            l0c_cnt += 1

            # ----- VEC bias-add epilogue (2 AIV subcores split rows) -----
            vrows = Max(Min(ROWS, valid_m - row0), 0)
            bias_h_ub[0:1, 0:valid_n] <<= bias[n0:n0 + valid_n]
            cast(bias_f_ub[0:1, 0:TILE_N], bias_h_ub[0:1, 0:TILE_N])

            with If(slot == 0):
                cv0.wait()
                with If(vrows > 0):
                    f32_ub[0:vrows, 0:TILE_N] <<= ws[GetCubeIdx(), 0, row0:row0 + vrows, 0:TILE_N]
                    _bias_band(f32_ub, f16_ub, bias_f_ub, vrows, D, m0 + row0, n0, valid_n)
                cv0.free()
            with Else():
                cv1.wait()
                with If(vrows > 0):
                    f32_ub[0:vrows, 0:TILE_N] <<= ws[GetCubeIdx(), 1, row0:row0 + vrows, 0:TILE_N]
                    _bias_band(f32_ub, f16_ub, bias_f_ub, vrows, D, m0 + row0, n0, valid_n)
                cv1.free()

    return D


def _bias_band(f32_ub, f16_ub, bias_f_ub, vrows, D, ym0, n0, valid_n):
    """Add per-channel bias to each row of a [vrows, TILE_N] fp32 band, cast to
    fp16, write the valid_n cols. bias_f_ub[0:1, :] broadcasts across rows; one
    add per row (count=TILE_N, ~2 repeats) stays far under the 255-repeat cap."""
    for r in range(0, vrows):
        add(f32_ub[r:r + 1, 0:TILE_N], f32_ub[r:r + 1, 0:TILE_N],
            bias_f_ub[0:1, 0:TILE_N], count=TILE_N)
    cast(f16_ub[0:vrows, 0:TILE_N], f32_ub[0:vrows, 0:TILE_N])
    D[ym0:ym0 + vrows, n0:n0 + valid_n] <<= f16_ub[0:vrows, 0:valid_n]


# ─────────────────────────── Host helpers ───────────────────────────

def conv2d_bias_to_matmul(x, weight, bias):
    """把 conv2d+bias 化为矩阵乘的输入。

    fmap [N,Cin,H,W] + weight [Cout,Cin,1,1] + bias [Cout] ->
    A [M,K], B [K,N], bias [N], (N,Cout,H,W).
    """
    Nb, Cin, H, W = x.shape
    Cout = weight.shape[0]
    A = x.permute(0, 2, 3, 1).reshape(Nb * H * W, Cin).contiguous()
    Bm = weight.squeeze(-1).squeeze(-1).t().contiguous()    # [Cin, Cout]
    return A, Bm, bias.contiguous(), (Nb, Cout, H, W)


def build_codegen_inputs():
    M, K, N = 512, 128, 256
    A = torch.zeros(M, K, dtype=torch.float16)
    B = torch.zeros(K, N, dtype=torch.float16)
    bias = torch.zeros(N, dtype=torch.float16)
    D = torch.zeros(M, N, dtype=torch.float16)
    return (A, B, bias, D, M, N, K)


def main():
    torch.manual_seed(0)

    # (Nb, Cin, H, W, Cout) -> M=Nb*H*W, K=Cin, N=Cout.
    cases = [
        (1, 128, 16, 16, 256),     # aligned: M=256, K=128, N=256
        (2, 96, 7, 9, 200),        # non-aligned: M=126, K=96, N=200
    ]

    all_ok = True
    for (Nb, Cin, H, W, Cout) in cases:
        x = torch.randn(Nb, Cin, H, W, dtype=torch.float16)
        weight = torch.randn(Cout, Cin, 1, 1, dtype=torch.float16)
        bias = torch.randn(Cout, dtype=torch.float16)

        A, Bm, bm, _ = conv2d_bias_to_matmul(x, weight, bias)
        M, K = A.shape
        N = Cout
        D = torch.zeros(M, N, dtype=torch.float16)

        out = OpExec(conv2d_bias_custom, simulator=True)(
            A, Bm, bm, D, M, N, K,
            shape_bindings={0: [0, 2], 1: [2, 1], 2: [1], 3: [0, 1]})

        ref = (A.float() @ Bm.float() + bias.float()).to(torch.float16).float()
        max_abs = torch.abs(out.float() - ref).max().item()
        ok = torch.allclose(out.float(), ref, rtol=1e-3, atol=1e-3)
        all_ok = all_ok and ok
        print(f"sim  (M={M},K={K},N={N}): {'PASS' if ok else 'FAIL'} "
              f"max_abs_diff={max_abs:.3e}")

    print("SIM ALL PASS" if all_ok else "SIM SOME FAILED")

    # --- real-NPU verification (ASCEND_RT_VISIBLE_DEVICES=2, 910B2) ---
    import os
    if os.environ.get("RUN_DEVICE") == "1":
        Nb, Cin, H, W, Cout = 1, 128, 16, 16, 256       # M=256,K=128,N=256
        x = torch.randn(Nb, Cin, H, W, dtype=torch.float16)
        weight = torch.randn(Cout, Cin, 1, 1, dtype=torch.float16)
        bias = torch.randn(Cout, dtype=torch.float16)
        A, Bm, bm, _ = conv2d_bias_to_matmul(x, weight, bias)
        M, K = A.shape
        N = Cout
        D = torch.zeros(M, N, dtype=torch.float16)
        from device_verify import device_run
        out = device_run(conv2d_bias_custom, (A, Bm, bm, D, M, N, K),
                         {0: [0, 2], 1: [2, 1], 2: [1], 3: [0, 1]}, "conv2d_bias_dev")
        ref = (A.float() @ Bm.float() + bias.float()).to(torch.float16).float()
        max_abs = torch.abs(out.float() - ref).max().item()
        ok = torch.allclose(out.float(), ref, rtol=1e-3, atol=1e-3)
        print(f"DEVICE (M={M},K={K},N={N}): {'PASS' if ok else 'FAIL'} "
              f"max_abs_diff={max_abs:.3e}")
        assert ok, "device result mismatch"

if __name__ == "__main__":
    main()
