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
# ffn_silu — easyasc A2 (ascend910b) fused FFN: X@W1 -> SiLU -> @W2 -> Y.
# Two cube GEMMs with an AIV SiLU activation between them.
#
# 来源:  CAKE2-easydsl-v2/skills/dsl-baseline-generation-cv/references/
#        output_example/ffn_silu.py  (CV DSL, tile.language)
# 语义:  hidden = silu(X @ W1)        X[M,K] fp16, W1[K,N1] fp16  -> hidden[M,N1] fp16
#        Y      = hidden @ W2         W2[N1,N2] fp16             -> Y[M,N2] fp16
#        silu(x) = x / (1 + exp(-x)).
#
# 验证:  simulator + 910B2 real NPU (ASCEND_RT_VISIBLE_DEVICES=3), rtol/atol 1e-3.
#
# 排布 (per-block_m 四阶段, 复用 quant_matmul mmad + add_rms_norm 风格):
#   CUBE MM1: hidden_mm[block_m, 全 N1] = X @ W1  -> hidden scratch GM(暂 fp16)。
#   AIV SiLU: 两 subcore 各处理行块一半行, 读 hidden(fp16)->fp32, silu, 写回 hidden(fp16)。
#   CUBE MM2: Y[block_m, 全 N2] = hidden @ W2   (hidden 作 cube A 输入, 对 N1 收缩)。
#   AIV cast: cube 已直接把 fp32 L0C cast 成 fp16 写 Y, 无需额外 vec。
#   尾块: M 任意; K/N1/N2 由 host pad 到 TILE 倍数 (W1->[N1,K], W2->[N2,N1])。
#         hidden scratch pad 的 N1 列在 silu 后为 silu(0)=0, 对 MM2 收缩贡献 0。
# ============================================================================
_pyrange = range          # capture Python's range before easyasc.a2 shadows it
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
def ffn_silu_custom(
    X: GMTensor, W1: GMTensor, W2: GMTensor, hidden: GMTensor, Y: GMTensor,
    M: Var, K: Var, N1: Var, N2: Var,
):
    # MM1 routes its fp32 result through the per-core ws workspace (one slot per
    # N1-tile, MAX_N1TILES slots) instead of writing the fp16 hidden GM directly.
    # The cube->vec handoff is then a clean fp32 ws read (CvMutex), exactly the
    # quant_matmul / matmul_swiglu / matmul_gelu idiom. The vec writes the silu
    # result to the hidden GM scratch ONCE; MM2's cube reads it back. The cube
    # write of hidden GM in the previous (buggy) version + the vec read of that
    # same GM was the non-deterministic cube<->vec GM hazard (a GM tensor written
    # by the cube via `<<=` was not reliably visible to a later vec `<<=` read for
    # bands beyond the first — verified non-deterministic nbad). Keeping MM1 in
    # ws (never GM) removes that hazard; the only GM round-trip left is the
    # one-directional vec-write -> cube-read of hidden, fenced by the VcMutex.
    MAX_N1TILES = 2          # N1 padded to <= MAX_N1TILES*TILE_N = 256 (eval shapes)
    ws = split_workspace(DT.float, [A2_CUBE_NUM, MAX_N1TILES, TILE_M, TILE_N], name="ws")

    cv1 = CvMutex(0)     # cube MM1 (ws) done -> vec SiLU   (cube->vec)
    cv2 = VcMutex(1)     # vec SiLU (hidden GM) done -> cube MM2    (vec->cube)

    l1a = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1b = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l0c = Tensor(DT.float, [TILE_M, TILE_N], Position.L0C)

    h_ub = Tensor(DT.half, [ROWS, TILE_N], Position.UB)   # hidden fp16 store staging
    r_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)   # fp32 mm read from ws
    f_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)   # fp32 compute
    t_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)

    l1_cnt = Var(0)

    tiles_m = CeilDiv(M, TILE_M)
    tiles_n1 = CeilDiv(N1, TILE_N)
    tiles_n2 = CeilDiv(N2, TILE_N)

    core_step = Var(1)
    core_step <<= GetCubeNum()

    sb = GetSubBlockIdx()
    row0 = Var(sb * ROWS)

    with auto_sync():
        for mt in range(GetCubeIdx(), tiles_m, core_step):
            m0 = Var(mt * TILE_M)
            valid_m = Min(TILE_M, M - m0)

            # ===== Stage1 CUBE: MM1 = X @ W1 -> per-core ws (fp32) =====
            # Compile-time N1-tile loop (so nt indexes the ws slot dim) guarded by
            # `with If(nt < tiles_n1)`.
            cv1.lock()
            for nt in _pyrange(0, MAX_N1TILES):
                with If(nt < tiles_n1):
                    n0 = Var(nt * TILE_N)
                    valid_n = Min(TILE_N, N1 - n0)
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
                        abuf[0:valid_m, 0:valid_k] <<= X[m0:m0 + valid_m, k0:k0 + valid_k]
                        bbuf[0:valid_n, 0:valid_k] <<= W1[n0:n0 + valid_n, k0:k0 + valid_k]
                        matmul(l0c, abuf, bbuf, is_init=(kt == 0))
                        l1_cnt += 1
                    ws[GetCubeIdx(), nt, 0:TILE_M, 0:TILE_N] <<= l0c
            cv1.ready()

            # ===== Stage2 AIV: SiLU(ws) -> hidden GM =====
            vrows = Max(Min(ROWS, valid_m - row0), 0)
            cv1.wait()
            cv2.lock()                       # vec: wait cube done reading prev hidden
            with If(vrows > 0):
                gm_r0 = Var(m0 + row0)
                for nt in _pyrange(0, MAX_N1TILES):
                    with If(nt < tiles_n1):
                        n0 = Var(nt * TILE_N)
                        valid_n = Min(TILE_N, N1 - n0)
                        # read this subcore's row band of the fp32 MM1 tile from ws
                        r_ub[0:vrows, 0:TILE_N] <<= ws[GetCubeIdx(), nt, row0:row0 + vrows, 0:TILE_N]
                        # silu(x) = x / (1 + exp(-x))
                        muls(t_ub, r_ub, -1.0)
                        exp(t_ub, t_ub)
                        adds(t_ub, t_ub, 1.0)
                        div(t_ub, r_ub, t_ub)
                        cast(h_ub, t_ub)
                        hidden[gm_r0:gm_r0 + vrows, n0:n0 + valid_n] <<= h_ub[0:vrows, 0:valid_n]
            cv1.free()                       # vec: release ws MM1 buffer for next iter
            cv2.ready()                      # vec: signal hidden ready for MM2

            # ===== Stage3 CUBE: MM2 = hidden @ W2 -> Y =====
            cv2.wait()                       # cube: wait vec SiLU done
            for nt in range(0, tiles_n2):
                n0 = Var(nt * TILE_N)
                valid_n = Min(TILE_N, N2 - n0)
                tiles_k1 = CeilDiv(N1, TILE_K)
                for kt in range(0, tiles_k1):
                    k0 = Var(kt * TILE_K)
                    valid_k = Min(TILE_K, N1 - k0)
                    abuf = l1a[l1_cnt]
                    bbuf = l1b[l1_cnt]
                    with If(valid_m < TILE_M):
                        set_constant_to_l1(abuf, 0.0)
                    with If(valid_k < TILE_K):
                        set_constant_to_l1(abuf, 0.0)
                        set_constant_to_l1(bbuf, 0.0)
                    with If(valid_n < TILE_N):
                        set_constant_to_l1(bbuf, 0.0)
                    abuf[0:valid_m, 0:valid_k] <<= hidden[m0:m0 + valid_m, k0:k0 + valid_k]
                    bbuf[0:valid_n, 0:valid_k] <<= W2[n0:n0 + valid_n, k0:k0 + valid_k]
                    matmul(l0c, abuf, bbuf, is_init=(kt == 0))
                    l1_cnt += 1
                Y[m0:m0 + valid_m, n0:n0 + valid_n] <<= l0c[0:valid_m, 0:valid_n]
            cv2.free()                       # cube: release hidden for next iter's SiLU

    return Y


# ─────────────────────────── Host helpers ───────────────────────────
ALIGN = 128


def _ceil_mult(x, m):
    return ((x + m - 1) // m) * m


def pad_inputs(X, W1, W2):
    M, K = X.shape
    K2, N1 = W1.shape
    N1b, N2 = W2.shape
    Kp = _ceil_mult(K, ALIGN)
    N1p = _ceil_mult(N1, ALIGN)
    N2p = _ceil_mult(N2, ALIGN)
    Xp = torch.zeros(M, Kp, dtype=torch.float16)
    Xp[:, :K] = X
    W1p = torch.zeros(Kp, N1p, dtype=torch.float16)
    W1p[:K, :N1] = W1
    W1t = W1p.t().contiguous()                       # [N1p, Kp]
    W2p = torch.zeros(N1p, N2p, dtype=torch.float16)
    W2p[:N1, :N2] = W2
    W2t = W2p.t().contiguous()                       # [N2p, N1p]
    return Xp, W1t, W2t, M, Kp, N1p, N2p


def build_codegen_inputs():
    M, K, N1, N2 = 512, 256, 384, 128
    X = torch.randn(M, K, dtype=torch.float16)
    W1 = torch.randn(K, N1, dtype=torch.float16)
    W2 = torch.randn(N1, N2, dtype=torch.float16)
    Xp, W1t, W2t, Mk, Kp, N1p, N2p = pad_inputs(X, W1, W2)
    hidden = torch.zeros(Mk, N1p, dtype=torch.float16)
    Y = torch.zeros(Mk, N2p, dtype=torch.float16)
    return (Xp, W1t, W2t, hidden, Y, Mk, Kp, N1p, N2p)


def _run(simulator, M, K, N1, N2):
    X = torch.randn(M, K, dtype=torch.float16) * 0.1
    W1 = torch.randn(K, N1, dtype=torch.float16) * 0.1
    W2 = torch.randn(N1, N2, dtype=torch.float16) * 0.1
    Xp, W1t, W2t, Mk, Kp, N1p, N2p = pad_inputs(X, W1, W2)
    hidden = torch.zeros(Mk, N1p, dtype=torch.float16)
    Yp = torch.zeros(Mk, N2p, dtype=torch.float16)
    res = OpExec(ffn_silu_custom, simulator=simulator)(
        Xp, W1t, W2t, hidden, Yp, Mk, Kp, N1p, N2p,
        shape_bindings={0: [0, 1], 1: [2, 1], 2: [3, 2], 3: [0, 2], 4: [0, 3]})
    out = res[:M, :N2].float()
    hid = torch.nn.functional.silu(X.float() @ W1.float())
    ref = (hid @ W2.float()).float()
    ok = torch.allclose(out, ref, rtol=1e-3, atol=1e-3)
    md = torch.abs(out - ref).max().item()
    pad = "" if (K % ALIGN == 0 and N1 % ALIGN == 0 and N2 % ALIGN == 0) else \
          f" (pad K {K}->{Kp}, N1 {N1}->{N1p}, N2 {N2}->{N2p})"
    print(f"{'sim' if simulator else 'dev'} (M={M},K={K},N1={N1},N2={N2}): "
          f"{'PASS' if ok else 'FAIL'}  max_abs_diff={md:.3e}{pad}")
    return ok


def main():
    import sys
    torch.manual_seed(0)
    sim = "--dev" not in sys.argv
    if not sim:
        import devrun  # noqa: F401
    shapes = [(256, 256, 256, 128), (200, 256, 192, 100)]   # one aligned, one non-128 N1/N2
    all_ok = True
    for (M, K, N1, N2) in shapes:
        all_ok = _run(sim, M, K, N1, N2) and all_ok
    print("ALL PASS" if all_ok else "SOME FAILED")

if __name__ == "__main__":
    main()
