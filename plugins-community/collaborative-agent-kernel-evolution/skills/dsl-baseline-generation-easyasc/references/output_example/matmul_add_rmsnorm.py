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
# matmul_add_rmsnorm — easyasc A2 (ascend910b) fused cube GEMM + AIV
# residual-add + RMSNorm epilogue. TWO outputs (Y and X_add).
#
# 来源:  CAKE2-easydsl-v2/skills/dsl-baseline-generation-cv/references/
#        output_example/matmul_add_rmsnorm.py  (CV DSL, tile.language)
# 语义:  mm    = A @ B               A[M,K] fp16, B[K,N] fp16
#        x_add = mm + residual       residual[M,N] fp16  -> X_add[M,N] fp16
#        rms   = sqrt(mean(x_add^2, -1) + eps)
#        y     = x_add / rms * gamma  gamma[N] fp16       -> Y[M,N] fp16
#
# 验证:  simulator + 910B2 real NPU (ASCEND_RT_VISIBLE_DEVICES=3), rtol/atol 1e-3.
#
# 排布 (per-block_m, ws ping-pong 保 mm 的 fp32 精度, 复用 quant_matmul +
#       add_rms_norm 的 cadd+brcb 归约。RMS 对输出整行归约故按行块分核):
#   每核领一个 block_m, 两 AIV subcore 各处理行块一半行。
#   pass1: 逐 N-tile  CUBE matmul -> fp32 L0C -> per-core ws ping-pong slot
#          (CvMutex 交接保 fp32); VEC 读回 fp32 mm, +residual(fp16->fp32),
#          x_add 写 X_add(fp16), sum((x_add)^2) (cadd 前 128->64 合并)。
#   inv_rms = rsqrt(sum/N + eps), brcb 广播。
#   pass2: 逐 N-tile VEC 重读 X_add(fp16->fp32) * inv_rms * gamma -> Y(fp16)。
#   尾块: M 任意; K/N 由 host pad 到 TILE 倍数 (B 转置成 [N,K])。pad 列 mm=0,
#         x_add=0 -> sum_sq 不变 (gamma pad 0); 只写 valid_n。
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
ROWS = TILE_M // 2          # rows per AIV subcore (64) — matches brcb [64,1]->[64,8]
EPS = 1e-6

A2_CUBE_NUM = 24

# Max columns the per-row x_add UB cache can hold (= MAX_N_TILES * TILE_N).
# We CACHE x_add in UB across pass1->pass2 instead of round-tripping it through
# GM, because this easyasc build does NOT make a GM tensor written by `<<=`
# visible to a later `<<=` read within the same kernel for tile bands beyond the
# first (the nt>=1 columns read back stale garbage — verified with a minimal
# write-then-readback repro). A UB cache (fp16) is the only round-trip that
# stays coherent. N must be <= MAX_NCACHE; the host pads N to a TILE_N multiple.
MAX_NTILES = 2              # supports N up to MAX_NTILES*TILE_N = 256 (eval shapes)


@kernel()
def matmul_add_rmsnorm_custom(
    A: GMTensor, B: GMTensor, residual: GMTensor, gamma: GMTensor,
    Y: GMTensor, X_add: GMTensor,
    M: Var, K: Var, N: Var, N_orig: Var,
):
    # N is the PADDED column width (multiple of TILE_N) that drives the cube
    # N-tiling; N_orig is the TRUE hidden size. The RMS mean must divide by the
    # ORIGINAL N_orig, not the padded N — the padded columns of x_add are zero
    # (gamma/residual/mm all pad to 0) so they add nothing to the sum of squares,
    # but dividing by the padded N would shrink the mean and inflate inv_rms.
    # N_orig is an extra scalar arg (not referenced in shape_bindings).
    # SINGLE ws slot + single CvMutex, fully serialized per N-tile. A 2-slot
    # ping-pong (cv0/cv1 alternating on nt%2) silently drops a band: when the
    # vec lane reads slot0 while the cube is already filling slot1, one of the
    # two slots reads stale L0C (verified: cols of every other N-tile were
    # wrong). Serializing cube->ready->vec.wait->read->free per tile is correct.
    ws = split_workspace(DT.float, [A2_CUBE_NUM, 1, TILE_M, TILE_N], name="ws")

    cv0 = CvMutex(0)

    l1a = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1b = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l0c = Tensor(DT.float, [TILE_M, TILE_N], Position.L0C)

    h_ub = Tensor(DT.half, [ROWS, TILE_N], Position.UB)   # fp16 load staging
    gh_ub = Tensor(DT.half, [1, TILE_N], Position.UB)      # gamma fp16 staging
    res_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)   # fp32 mm from ws, then x_add
    xadd_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)
    sq_ub = Tensor(DT.float, [ROWS, TILE_N], Position.UB)
    g_ub = Tensor(DT.float, [1, TILE_N], Position.UB)
    o_ub = Tensor(DT.half, [ROWS, TILE_N], Position.UB)   # GM store staging
    # Per-row x_add cache (fp16) for the pass1->pass2 round-trip. easyasc Tensors
    # must be 2D, so we allocate ONE SEPARATE 2D [ROWS, TILE_N] tensor per N-tile
    # (MAX_NTILES of them) and address tile nt by Python-list index `xcache[nt]`.
    # Two cheaper-looking alternatives both silently corrupt bands beyond the
    # first in this easyasc build (each verified with a minimal repro):
    #   (a) a single wide [ROWS, MAX_NTILES*TILE_N] tensor sliced by a Var column
    #       offset [:, nt*TILE_N : nt*TILE_N+TILE_N] — the column slab has the
    #       wrong UB row-stride, so even tile0 fails to round-trip; and
    #   (b) a GM scratch written by `<<=` in pass1 and re-read by `<<=` in pass2
    #       within the same kernel — tile1+ read back stale data.
    # Separate per-tile UB tensors round-trip cleanly (repro: all tiles match).
    # This REQUIRES the N-tile loops to be COMPILE-TIME Python loops over
    # _pyrange(0, MAX_NTILES) (so `nt` is an int that can index the list), with a
    # runtime `with If(nt < tiles_n)` guard for the active tiles.
    xcache = [Tensor(DT.half, [ROWS, TILE_N], Position.UB) for _ in _pyrange(MAX_NTILES)]
    chunk_s = Tensor(DT.float, [ROWS, 1], Position.UB)
    sum_s = Tensor(DT.float, [ROWS, 1], Position.UB)
    inv_s = Tensor(DT.float, [ROWS, 1], Position.UB)
    inv_brcb = Tensor(DT.float, [ROWS, 8], Position.UB)
    n_t = Tensor(DT.float, [ROWS, 1], Position.UB)
    invn_t = Tensor(DT.float, [ROWS, 1], Position.UB)

    l1_cnt = Var(0)

    tiles_m = CeilDiv(M, TILE_M)
    tiles_n = CeilDiv(N, TILE_N)

    core_step = Var(1)
    core_step <<= GetCubeNum()

    sb = GetSubBlockIdx()
    row0 = Var(sb * ROWS)

    one_t = Tensor(DT.float, [ROWS, 1], Position.UB)
    with auto_sync():
        dup(n_t, N_orig)        # divide by the ORIGINAL hidden size, not padded N
        dup(one_t, 1.0)
        div(invn_t, one_t, n_t)   # device rec is low-precision -> exact div

    # ONE auto_sync region. Both passes live here and the pass1->pass2 x_add
    # round-trip is kept in the UB xcache (NOT GM): a GM tensor written by `<<=`
    # is not reliably visible to a later `<<=` read in the same kernel for
    # tile bands beyond the first, and a second auto_sync region with a
    # core-distributed loop corrupts the first region's later output bands.
    with auto_sync("aggressive"):
        for mt in range(GetCubeIdx(), tiles_m, core_step):
            m0 = Var(mt * TILE_M)
            valid_m = Min(TILE_M, M - m0)
            vrows = Max(Min(ROWS, valid_m - row0), 0)
            gm_r0 = Var(m0 + row0)

            # reset per-row running sum of squares for this block_m
            with If(vrows > 0):
                dup(sum_s, 0.0)

            # ---- pass1: per N-tile CUBE matmul -> ws, VEC +res -> X_add + xcache, accumulate ----
            # COMPILE-TIME loop over MAX_NTILES so `nt` is an int and indexes the
            # xcache list; `with If(nt < tiles_n)` runtime-guards the active tiles.
            for nt in _pyrange(0, MAX_NTILES):
                with If(nt < tiles_n):
                    n0 = Var(nt * TILE_N)
                    valid_n = Min(TILE_N, N - n0)

                    # CUBE matmul this N-tile into fp32 L0C, store to the single ws slot.
                    cv0.lock()
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
                        matmul(l0c, abuf, bbuf, is_init=(kt == 0))
                        l1_cnt += 1
                    ws[GetCubeIdx(), 0, 0:TILE_M, 0:TILE_N] <<= l0c
                    cv0.ready()

                    # VEC: read fp32 mm, + residual; write X_add(fp16) AND cache
                    # x_add (fp16) in the per-tile UB tensor for pass2; accumulate
                    # sum(x_add^2).
                    cv0.wait()
                    with If(vrows > 0):
                        res_ub[0:vrows, 0:TILE_N] <<= ws[GetCubeIdx(), 0, row0:row0 + vrows, 0:TILE_N]
                        h_ub[0:vrows, 0:TILE_N] <<= residual[gm_r0:gm_r0 + vrows, n0:n0 + valid_n]
                        cast(xadd_ub, h_ub)              # xadd_ub = residual(fp32)
                        add(xadd_ub, xadd_ub, res_ub)    # xadd_ub = mm + residual
                        cast(o_ub, xadd_ub)
                        X_add[gm_r0:gm_r0 + vrows, n0:n0 + valid_n] <<= o_ub[0:vrows, 0:valid_n]
                        xcache[nt][0:vrows, 0:TILE_N] <<= o_ub[0:vrows, 0:TILE_N]   # UB->UB, per-tile tensor
                        mul(sq_ub, xadd_ub, xadd_ub)
                        add(sq_ub[0:vrows, 0:64], sq_ub[0:vrows, 0:64], sq_ub[0:vrows, 64:128])
                        cadd(chunk_s, sq_ub[0:vrows, 0:64])
                        add(sum_s, sum_s, chunk_s)
                    cv0.free()

            # ---- inv_rms = rsqrt(sum/N + eps), then pass2 from the UB xcache ----
            with If(vrows > 0):
                mul(sum_s, sum_s, invn_t)
                adds(sum_s, sum_s, EPS)
                # device rsqrt is low-precision -> exact sqrt + div
                sqrt(sum_s, sum_s)
                div(inv_s, one_t, sum_s)
                brcb(inv_brcb, inv_s, dst_blk_stride=1, dst_rep_stride=8)

                # ---- pass2: y = x_add * inv_rms * gamma (x_add from UB cache) ----
                # COMPILE-TIME loop so `nt` indexes the xcache list; guarded by
                # `with If(nt < tiles_n)`.
                for nt in _pyrange(0, MAX_NTILES):
                    with If(nt < tiles_n):
                        n0 = Var(nt * TILE_N)
                        valid_n = Min(TILE_N, N - n0)
                        cast(xadd_ub, xcache[nt][0:vrows, 0:TILE_N])   # UB->UB, per-tile tensor
                        gh_ub[0:1, 0:TILE_N] <<= gamma[n0:n0 + valid_n]
                        cast(g_ub, gh_ub)
                        # per-COL gamma FIRST (count-mode, row by row — the quant_matmul
                        # idiom; a repeat-mode mul(wide[M,N], wide, gamma[1,N]) has no
                        # linear stride for "every row reads the same column block").
                        # Doing gamma before the repeat-mode _scale_rows keeps the
                        # final write to xadd_ub in repeat-mode: interleaving a
                        # count-mode write between a repeat-mode write and the cast
                        # mis-tracked the dependency and corrupted later rows.
                        for rr in _pyrange(0, ROWS):
                            mul(xadd_ub[rr:rr + 1, 0:TILE_N], xadd_ub[rr:rr + 1, 0:TILE_N],
                                g_ub[0:1, 0:TILE_N], count=TILE_N)
                        _scale_rows(xadd_ub, inv_brcb)   # per-ROW inv_rms broadcast (repeat-mode)
                        cast(o_ub, xadd_ub)
                        Y[gm_r0:gm_r0 + vrows, n0:n0 + valid_n] <<= o_ub[0:vrows, 0:valid_n]

    return Y, X_add


# Per-ROW scalar broadcast (the canonical add_rms_norm.py pattern). A 128-wide
# row spans 2 cadd repeats, so we multiply in 64-col chunks: each chunk is one
# repeat per row and `mul(wide[M,64], wide, narrow[M,8])` lets the wide operand's
# per-row repeat cadence drive iteration while narrow stays per row — DO NOT pass
# src2_blk_stride/src2_rep_stride; the default stride inference for a dense
# `[M,8]` narrow (brcb of a cadd/rsqrt-dense `[M,1]` source) is the correct
# broadcast (forcing src2_blk_stride=0/src2_rep_stride=1 made every row read
# narrow row 0's block — verified max_abs ~11).
#
# CRITICAL: the two 64-col chunk muls must be EXPLICITLY UNROLLED, not emitted
# from a `for c in range(2): mul(wide[:, c*64:c*64+64], ...)` loop. Even though
# `c*64` is a compile-time Python int, the loop form mis-tracked the second
# chunk's dst rep-stride and scaled rows 1..63 by the wrong inv_rms (verified:
# loop form max_abs 3.4, explicit form 4e-8). TILE_N=128 => exactly 2 chunks.
def _scale_rows(wide, narrow):
    mul(wide[0:ROWS, 0:64], wide[0:ROWS, 0:64], narrow)
    mul(wide[0:ROWS, 64:128], wide[0:ROWS, 64:128], narrow)


def _accum(mm_ub, h_ub, res_ub, xadd_ub, sq_ub, o_ub,
           chunk_s, sum_s, vrows, residual, X_add, gm_r0, n0, valid_n):
    """x_add = mm + residual; write X_add(fp16); accumulate sum((x_add)^2)."""
    h_ub[0:vrows, 0:TILE_N] <<= residual[gm_r0:gm_r0 + vrows, n0:n0 + valid_n]
    cast(res_ub, h_ub)
    add(xadd_ub, mm_ub, res_ub)
    cast(o_ub, xadd_ub)
    X_add[gm_r0:gm_r0 + vrows, n0:n0 + valid_n] <<= o_ub[0:vrows, 0:valid_n]
    mul(sq_ub, xadd_ub, xadd_ub)
    # cadd is a 64-lane group reduction; merge the two 64-col halves into the
    # first half of sq_ub in-place (no separate red_ub buffer), then reduce.
    add(sq_ub[0:vrows, 0:64], sq_ub[0:vrows, 0:64], sq_ub[0:vrows, 64:128])
    cadd(chunk_s, sq_ub[0:vrows, 0:64])
    add(sum_s, sum_s, chunk_s)


# ─────────────────────────── Host helpers ───────────────────────────
ALIGN_K = 128
ALIGN_N = 128


def _ceil_mult(x, m):
    return ((x + m - 1) // m) * m


def pad_inputs(A, B, residual, gamma):
    M, K = A.shape
    K2, N = B.shape
    Kp = _ceil_mult(K, ALIGN_K)
    Np = _ceil_mult(N, ALIGN_N)
    Ap = torch.zeros(M, Kp, dtype=torch.float16)
    Ap[:, :K] = A
    Bp = torch.zeros(Kp, Np, dtype=torch.float16)
    Bp[:K, :N] = B
    Bt = Bp.t().contiguous()                      # [Np, Kp]
    resp = torch.zeros(M, Np, dtype=torch.float16)
    resp[:, :N] = residual
    gp = torch.zeros(Np, dtype=torch.float16)
    gp[:N] = gamma
    return Ap, Bt, resp, gp, M, Kp, Np


def build_codegen_inputs():
    M, K, N = 512, 256, 128
    A = torch.randn(M, K, dtype=torch.float16)
    B = torch.randn(K, N, dtype=torch.float16)
    residual = torch.randn(M, N, dtype=torch.float16)
    gamma = torch.randn(N, dtype=torch.float16)
    Ap, Bt, resp, gp, Mk, Kp, Np = pad_inputs(A, B, residual, gamma)
    Y = torch.zeros(Mk, Np, dtype=torch.float16)
    Xa = torch.zeros(Mk, Np, dtype=torch.float16)
    return (Ap, Bt, resp, gp, Y, Xa, Mk, Kp, Np, N)   # last scalar = original N


def _run(simulator, M, K, N):
    # smaller magnitude so fp16 x_add (output) stays well within rtol on the norm
    A = torch.randn(M, K, dtype=torch.float16) * 0.1
    B = torch.randn(K, N, dtype=torch.float16) * 0.1
    residual = torch.randn(M, N, dtype=torch.float16)
    gamma = torch.randn(N, dtype=torch.float16)
    Ap, Bt, resp, gp, Mk, Kp, Np = pad_inputs(A, B, residual, gamma)
    Yp = torch.zeros(Mk, Np, dtype=torch.float16)
    Xap = torch.zeros(Mk, Np, dtype=torch.float16)
    res = OpExec(matmul_add_rmsnorm_custom, simulator=simulator)(
        Ap, Bt, resp, gp, Yp, Xap, Mk, Kp, Np, N,   # last scalar = original N (divisor)
        shape_bindings={0: [0, 1], 1: [2, 1], 2: [0, 2], 3: [2], 4: [0, 2], 5: [0, 2]})
    y_out_t, xa_out_t = res
    y_out = y_out_t[:M, :N].float()
    xa_out = xa_out_t[:M, :N].float()
    mm = A.float() @ B.float()
    x_add = mm + residual.float()
    rms = torch.sqrt((x_add ** 2).mean(-1, keepdim=True) + EPS)
    y_ref = x_add / rms * gamma.float()
    ok_y = torch.allclose(y_out, y_ref, rtol=1e-3, atol=1e-3)
    ok_x = torch.allclose(xa_out, x_add, rtol=1e-3, atol=1e-3)
    ok = ok_y and ok_x
    md_y = torch.abs(y_out - y_ref).max().item()
    md_x = torch.abs(xa_out - x_add).max().item()
    pad = "" if (K % ALIGN_K == 0 and N % ALIGN_N == 0) else f" (pad K {K}->{Kp}, N {N}->{Np})"
    print(f"{'sim' if simulator else 'dev'} (M={M},K={K},N={N}): "
          f"{'PASS' if ok else 'FAIL'}  max_abs_diff Y={md_y:.3e} Xadd={md_x:.3e}{pad}")
    return ok


def main():
    import sys
    torch.manual_seed(0)
    sim = "--dev" not in sys.argv
    if not sim:
        import devrun  # noqa: F401
    shapes = [(256, 256, 256), (200, 256, 192)]   # one aligned, one non-128-aligned N
    all_ok = True
    for (M, K, N) in shapes:
        all_ok = _run(sim, M, K, N) and all_ok
    print("ALL PASS" if all_ok else "SOME FAILED")

if __name__ == "__main__":
    main()
