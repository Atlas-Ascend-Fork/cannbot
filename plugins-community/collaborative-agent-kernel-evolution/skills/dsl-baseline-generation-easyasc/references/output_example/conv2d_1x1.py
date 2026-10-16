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
# conv2d_1x1 — easyasc A2 (ascend910b) fp16 cube matmul.
#
# Origin : ported from CAKE2-easydsl-v2 dsl-baseline-generation-cv
#          references/output_example/conv2d_1x1.py (tile.language CV DSL).
# Verify : simulator + real NPU (ASCEND_RT_VISIBLE_DEVICES=2, 910B2), see
#          __main__ — both PASS, see header of installed copy / port report.
#
# Math (identical to source): a NHWC 1x1 convolution is exactly a matmul.
#     fmap [N,Cin,H,W] --(NHWC reshape)--> A [M=N*H*W, K=Cin]
#     weight [Cout,Cin,1,1] --(squeeze+T)--> B [K=Cin, N=Cout]
#     out  D [M, N=Cout]  =  A @ B          (fp16 in, fp16 out)
#
# Pipeline (mirrors qk_matmul_batched.py + grouped_matmul.py):
#   CUBE-only. Per output tile [TILE_M, TILE_N], accumulate over K with an
#   outer K-tile loop (is_init only on the first K-tile). The fp32 L0C is
#   written straight to the fp16 GM output via fixpipe (<<= casts f32->f16),
#   so no AIV epilogue is needed for the plain conv.
#
# NOTE on the kernel name: the function is `conv1x1_custom`, NOT
#   `conv2d_1x1_custom`. easyasc's codegen camel/snake round-trip drops the
#   `_` inside the numeric token `2d_1x1`: `conv2d_1x1_custom` -> camel
#   `Conv2d1x1Custom` -> the kernel-compile step looks for `conv2d1x1_custom.cpp`
#   while codegen WROTE `conv2d_1x1_custom.cpp`, so the device `binary` target
#   fails ("source file ... does not found"). `conv1x1_custom` round-trips
#   cleanly (`Conv1x1Custom` -> `conv1x1_custom`). The math/semantics are the
#   identical 1x1-conv-as-matmul; only the symbol name is digit-safe.
#
# Tiling / capacity (a2 910B2, 24 cube cores) — grouped_matmul-proven config:
#   TILE_M=128, TILE_N=128, TILE_K=128. DBuff L0C fp32 [128,128]*2 = 128KB
#   = the full L0C cap (the matmul shortcut's internal L0 ping-pong needs a
#   DBuff L0C; a single-buffer L0C deadlocks the FIX<->MTE1 event ring). L0A
#   fp16 [128,128]=32KB, L0B fp16 [128,128]=32KB (auto DBuff). L1 a/b tiles
#   fp16 [128,128]=32KB each (DBuff 64KB), << 512KB.
#   K is tiled by an outer K-loop (is_init only on the first K-tile).
#   24-core flat-tile round-robin (Var core_step alias, .value-safe).
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

# A2 cube core count hardcoded for the workspace first dim (GetCubeNum().value=0
# at codegen would size userWorkspaceSize to 0 -> 507015 device hang).
A2_CUBE_NUM = 24


@kernel()
def conv1x1_custom(
    A: GMTensor, B: GMTensor, D: GMTensor,
    M: Var, N: Var, K: Var,
):
    # split_workspace MUST exist so host tiling allocates a non-zero
    # userWorkspaceSize (else 507015 silent hang on device). Unused here.
    ws = split_workspace(DT.float, [A2_CUBE_NUM, 2, TILE_M, TILE_N], name="ws")

    l1a = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1b = DBuff(DT.half, [TILE_K, TILE_N], Position.L1)   # stored [K,N], read .T
    l0c = DBuff(DT.float, [TILE_M, TILE_N], Position.L0C)  # 128KB DBuff = full L0C

    l1_cnt = Var(0)
    l0c_cnt = Var(0)

    tiles_m = CeilDiv(M, TILE_M)
    tiles_n = CeilDiv(N, TILE_N)
    total_tiles = Var(tiles_m * tiles_n)
    tiles_k = CeilDiv(K, TILE_K)

    # core_step alias: range(start, stop, GetCubeNum()) trips codegen (.value=0).
    core_step = Var(1, DT.int)
    core_step <<= GetCubeNum()

    with auto_sync():
        for t in range(GetCubeIdx(), total_tiles, core_step):
            mt = Var(t // tiles_n)
            nt = Var(t % tiles_n)
            m0 = Var(mt * TILE_M)
            n0 = Var(nt * TILE_N)
            valid_m = Min(TILE_M, M - m0)
            valid_n = Min(TILE_N, N - n0)

            for kt in range(0, tiles_k):
                k0 = Var(kt * TILE_K)
                valid_k = Min(TILE_K, K - k0)

                abuf = l1a[l1_cnt]
                bbuf = l1b[l1_cnt]
                # zero-pad boundary tiles so padded rows/cols contribute 0.
                with If(valid_m < TILE_M):
                    set_constant_to_l1(abuf, 0.0)
                with If(valid_k < TILE_K):
                    set_constant_to_l1(abuf, 0.0)
                    set_constant_to_l1(bbuf, 0.0)
                with If(valid_n < TILE_N):
                    set_constant_to_l1(bbuf, 0.0)
                abuf[0:valid_m, 0:valid_k] <<= A[m0:m0 + valid_m, k0:k0 + valid_k]
                bbuf[0:valid_k, 0:valid_n] <<= B[k0:k0 + valid_k, n0:n0 + valid_n]

                # B stored [K,N] -> .T reads it as [N,K]; A@B**T**T == A@B.
                matmul(l0c[l0c_cnt], abuf, bbuf.T,
                       m=TILE_M, n=TILE_N, k=TILE_K,
                       is_init=(kt == 0))
                l1_cnt += 1

            # fp32 L0C -> fp16 GM (fixpipe cast), valid region only.
            D[m0:m0 + valid_m, n0:n0 + valid_n] <<= l0c[l0c_cnt][0:valid_m, 0:valid_n]
            l0c_cnt += 1

    return D


# ─────────────────────────── Host helpers ───────────────────────────

def conv2d_1x1_to_matmul(x, weight):
    """fmap [N,Cin,H,W] + weight [Cout,Cin,1,1] -> A [M,K], B [K,N], (N,Cout,H,W)."""
    Nb, Cin, H, W = x.shape
    Cout = weight.shape[0]
    A = x.permute(0, 2, 3, 1).reshape(Nb * H * W, Cin).contiguous()
    Bm = weight.squeeze(-1).squeeze(-1).t().contiguous()   # [Cin, Cout]
    return A, Bm, (Nb, Cout, H, W)


def build_codegen_inputs():
    # Distinct M, K, N for unambiguous shape binding.
    M, K, N = 512, 128, 256
    A = torch.zeros(M, K, dtype=torch.float16)
    B = torch.zeros(K, N, dtype=torch.float16)
    D = torch.zeros(M, N, dtype=torch.float16)
    return (A, B, D, M, N, K)


def main():
    torch.manual_seed(0)

    # (Nb, Cin, H, W, Cout) -> M=Nb*H*W, K=Cin, N=Cout.
    # second shape is non-aligned in M and N (M=2*7*9=126, N=200).
    cases = [
        (1, 128, 16, 16, 256),     # aligned: M=256, K=128, N=256
        (2, 96, 7, 9, 200),        # non-aligned: M=126, K=96, N=200
    ]

    all_ok = True
    for (Nb, Cin, H, W, Cout) in cases:
        x = torch.randn(Nb, Cin, H, W, dtype=torch.float16)
        weight = torch.randn(Cout, Cin, 1, 1, dtype=torch.float16)

        A, Bm, _ = conv2d_1x1_to_matmul(x, weight)
        M, K = A.shape
        N = Cout
        D = torch.zeros(M, N, dtype=torch.float16)

        out = OpExec(conv1x1_custom, simulator=True)(
            A, Bm, D, M, N, K,
            shape_bindings={0: [0, 2], 1: [2, 1], 2: [0, 1]})

        ref = (A.float() @ Bm.float()).to(torch.float16).float()
        out_f = out.float()
        max_abs = torch.abs(out_f - ref).max().item()
        ok = torch.allclose(out_f, ref, rtol=1e-3, atol=1e-3)
        all_ok = all_ok and ok
        print(f"sim  (M={M},K={K},N={N}): {'PASS' if ok else 'FAIL'} "
              f"max_abs_diff={max_abs:.3e}")

    print("SIM ALL PASS" if all_ok else "SIM SOME FAILED")

    # --- real-NPU verification (ASCEND_RT_VISIBLE_DEVICES=2, 910B2) ---
    # set RUN_DEVICE=1 to codegen+build+run on the NPU and assert vs torch.
    import os
    if os.environ.get("RUN_DEVICE") == "1":
        Nb, Cin, H, W, Cout = 1, 128, 16, 16, 256       # M=256,K=128,N=256
        x = torch.randn(Nb, Cin, H, W, dtype=torch.float16)
        weight = torch.randn(Cout, Cin, 1, 1, dtype=torch.float16)
        A, Bm, _ = conv2d_1x1_to_matmul(x, weight)
        M, K = A.shape
        N = Cout
        D = torch.zeros(M, N, dtype=torch.float16)
        from device_verify import device_run
        out = device_run(conv1x1_custom, (A, Bm, D, M, N, K),
                         {0: [0, 2], 1: [2, 1], 2: [0, 1]}, "conv2d_1x1_dev")
        ref = (A.float() @ Bm.float()).to(torch.float16).float()
        max_abs = torch.abs(out.float() - ref).max().item()
        ok = torch.allclose(out.float(), ref, rtol=1e-3, atol=1e-3)
        print(f"DEVICE (M={M},K={K},N={N}): {'PASS' if ok else 'FAIL'} "
              f"max_abs_diff={max_abs:.3e}")
        assert ok, "device result mismatch"

if __name__ == "__main__":
    main()
