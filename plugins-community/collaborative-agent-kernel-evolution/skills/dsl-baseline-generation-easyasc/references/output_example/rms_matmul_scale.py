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
# rms_matmul_scale — easyasc A2 (ascend910b) fused cube GEMM + AIV RMS-scale.
#
# 来源:  CAKE2-easydsl-v2/skills/dsl-baseline-generation-cv/references/
#        output_example/rms_matmul_scale.py  (CV DSL, tile.language)
# 语义:  x[M,K] fp16 (来自 [B,S,N,D] reshape, K=N*D), weight[K,O] fp16
#        inv_rms[M] = rsqrt(mean(x^2 over K) + eps)        # 对输入行归约
#        out[M,O]   = inv_rms[:,None] * (x @ weight)        # fp16
#        注意: RMS 在 matmul *之前* 对输入 x 的 K 维归约。
#
# 验证:  simulator ALL PASS + 910B2 real NPU (ASCEND_RT_VISIBLE_DEVICES=3),
#        rtol/atol 1e-3。门禁双过:
#          dev (256,256,256) aligned          PASS max_abs 1.95e-3
#          dev (200,320,192) M-tail+K/O-pad    PASS max_abs 1.95e-3
#        根因 (KB H27 NZ-fractal-stale, 落在 M 维): cube 把 x 载入 NZ 分形 L1
#        tile, matmul 读整块 TILE_M 行。M 尾块 (valid_m<TILE_M) 时 kernel 用
#        set_constant_to_l1 清零, 但真机只清逻辑视图 —— NZ 分形 padding 行
#        [valid_m:TILE_M] 保留 DBuff slot 上一 tile 的旧值, matmul 累加之。
#        sim 用稠密张量建模故清零生效 -> sim PASS / device FAIL。仅当 M 尾块
#        与奇数个 K-tile (>=3, 如 K=320->384) 同时出现 (复用的 DBuff slot 仍存
#        前一满 M tile 的行) 才暴露; (200,256,*) K=2 tile 时偶然不触发。
#        修复: host 把 M pad 到 TILE_M 倍数, valid_m==TILE_M 恒成立, partial-M
#        分支彻底消除; 全零 pad 行产出的垃圾输出行直接被 out[:M] 切掉。
#
# 排布 (两个结构上独立的 phase, 复用 sum_reduction(per-op auto_sync) + quant_matmul):
#   Phase1 (纯 VEC, 每 op-group 独立 with auto_sync(), 复用 add_rms_norm/
#           sum_reduction 已验证范式): 行块=64, 逐 K-tile(64 宽, cadd 一个 repeat
#           恰好一行) sum(x^2), rsqrt, brcb -> inv_gm[M,8] scratch (写回需 >=1 个
#           C0 block, 故用 8 宽广播)。把归约与 cube 流水彻底分离 —— 把归约塞进
#           cube 的 ws-pingpong + aggressive 区域会打乱 sync 顺序导致每行和错乱。
#   Phase2 (CUBE+VEC ws ping-pong, aggressive): 逐 O-tile matmul x@weight ->
#           fp32 L0C -> per-core ws slot; VEC 读回 fp32, 读 inv_gm, * inv_rms,
#           cast fp16, 写 out。
#   尾块: M 任意; K/O 由 host pad 到 TILE 倍数 (weight 转置 [O,K])。inv_rms 用
#         原始 K (host 传 Korig) 做除法; pad 的 K 列 x=0 不改 sum(x^2)。只写 valid_o。
# ============================================================================
from easyasc.a2 import *
import builtins
import torch

from easyasc import globvars as _gv
_gv.device_type = 'b2'
_gv.core_num = 24

TILE_M = 128
TILE_O = 128
TILE_K = 128
RED_M = 64           # row-tile for the pure-vec reduction (brcb needs 64)
RED_H = 64           # cadd group size (one repeat per row)
ROWS = TILE_M // 2   # AIV subcore rows in phase2
EPS = 1e-6

A2_CUBE_NUM = 24


@kernel()
def rms_matmul_scale_custom(
    x: GMTensor, weight: GMTensor, inv_gm: GMTensor, out: GMTensor,
    M: Var, K: Var, O: Var, Korig: Var,
):
    ws = split_workspace(DT.float, [A2_CUBE_NUM, 2, TILE_M, TILE_O], name="ws")

    # ---- Phase1 UB (pure vec reduction) ----
    xt = Tensor(DT.half, [RED_M, RED_H], Position.UB)
    xf = Tensor(DT.float, [RED_M, RED_H], Position.UB)
    sq = Tensor(DT.float, [RED_M, RED_H], Position.UB)
    chunk_s = Tensor(DT.float, [RED_M, 1], Position.UB)
    sum_s = Tensor(DT.float, [RED_M, 1], Position.UB)
    inv_s = Tensor(DT.float, [RED_M, 1], Position.UB)
    inv_brcb = Tensor(DT.float, [RED_M, 8], Position.UB)
    kf = Tensor(DT.float, [RED_M, 1], Position.UB)
    invk = Tensor(DT.float, [RED_M, 1], Position.UB)

    # 1/Korig at runtime. Device `rec` is a low-precision (~1e-3) Newton approx
    # (sim-exact only) — use true `div` (KB: device rec/rsqrt pitfall).
    one_t = Tensor(DT.float, [RED_M, 1], Position.UB)
    with auto_sync():
        dup(kf, Korig)
        dup(one_t, 1.0)
        div(invk, one_t, kf)

    n_row_tiles = CeilDiv(M, RED_M)
    tpc = CeilDiv(n_row_tiles, GetVecNum())
    tb = Var(tpc * GetVecIdx())
    te = Min(tb + tpc, n_row_tiles)
    n_k_tiles = CeilDiv(K, RED_H)

    for ti in range(tb, te):
        r0 = Var(ti * RED_M)
        vr = Min(RED_M, M - r0)
        with auto_sync():
            dup(sum_s, 0.0)
        for ki in range(0, n_k_tiles):
            k0 = Var(ki * RED_H)
            vk = Min(RED_H, K - k0)
            with auto_sync():
                xt <<= x[r0:r0 + vr, k0:k0 + vk]
                cast(xf, xt)
                mul(sq, xf, xf)
                cadd(chunk_s, sq)
                add(sum_s, sum_s, chunk_s)
        with auto_sync():
            mul(sum_s, sum_s, invk)        # mean = sum / Korig
            adds(sum_s, sum_s, EPS)
            # device rsqrt is a low-precision approx -> exact sqrt + div.
            sqrt(sum_s, sum_s)
            div(inv_s, one_t, sum_s)
            brcb(inv_brcb, inv_s, dst_blk_stride=1, dst_rep_stride=8)
            inv_gm[r0:r0 + vr, 0:8] <<= inv_brcb[0:vr, 0:8]

    # ---- Cross-phase barrier: every vec lane must finish writing inv_gm to GM
    #      (MTE3) before ANY phase2 vec lane reads inv_gm (MTE2). Phase1 row-tiles
    #      are sharded by GetVecIdx() across all cores, but phase2 reads inv_gm
    #      rows produced by a *different* vec lane — without a global vec barrier
    #      phase2 sees stale/zero inv_gm (row0 returned 0). allvec_* is a full
    #      barrier across all (core × VEC_COUNT) lanes, so it MUST be called
    #      unconditionally by every lane, outside the row loop and any If.
    allvec_ready(0, pipe=Pipe.MTE3)
    allvec_wait(0, pipe=Pipe.S)

    # ---- Phase2 UB (cube ws ping-pong + scale) ----
    l1a = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1b = DBuff(DT.half, [TILE_O, TILE_K], Position.L1)
    l0c = Tensor(DT.float, [TILE_M, TILE_O], Position.L0C)
    mm_ub = Tensor(DT.float, [ROWS, TILE_O], Position.UB)
    o_ub = Tensor(DT.half, [ROWS, TILE_O], Position.UB)
    ig_ub = Tensor(DT.float, [ROWS, 8], Position.UB)   # inv_rms broadcast tile

    cv0 = CvMutex(0)
    cv1 = CvMutex(1)
    l1_cnt = Var(0)

    tiles_m = CeilDiv(M, TILE_M)
    tiles_o = CeilDiv(O, TILE_O)
    tiles_k_mm = CeilDiv(K, TILE_K)
    core_step = Var(1)
    core_step <<= GetCubeNum()
    sb = GetSubBlockIdx()
    row0 = Var(sb * ROWS)

    with auto_sync("aggressive"):
        for mt in range(GetCubeIdx(), tiles_m, core_step):
            m0 = Var(mt * TILE_M)
            valid_m = Min(TILE_M, M - m0)
            vrows = Max(Min(ROWS, valid_m - row0), 0)
            gm_r0 = Var(m0 + row0)

            for ot in range(0, tiles_o):
                o0 = Var(ot * TILE_O)
                valid_o = Min(TILE_O, O - o0)
                slot = Var(ot % 2)

                with If(slot == 0):
                    cv0.lock()
                with Else():
                    cv1.lock()
                for kt in range(0, tiles_k_mm):
                    k0 = Var(kt * TILE_K)
                    valid_k = Min(TILE_K, K - k0)
                    abuf = l1a[l1_cnt]
                    bbuf = l1b[l1_cnt]
                    with If(valid_m < TILE_M):
                        set_constant_to_l1(abuf, 0.0)
                    with If(valid_k < TILE_K):
                        set_constant_to_l1(abuf, 0.0)
                        set_constant_to_l1(bbuf, 0.0)
                    with If(valid_o < TILE_O):
                        set_constant_to_l1(bbuf, 0.0)
                    abuf[0:valid_m, 0:valid_k] <<= x[m0:m0 + valid_m, k0:k0 + valid_k]
                    bbuf[0:valid_o, 0:valid_k] <<= weight[o0:o0 + valid_o, k0:k0 + valid_k]
                    matmul(l0c, abuf, bbuf, is_init=(kt == 0))
                    l1_cnt += 1
                with If(slot == 0):
                    ws[GetCubeIdx(), 0, 0:TILE_M, 0:TILE_O] <<= l0c
                    cv0.ready()
                with Else():
                    ws[GetCubeIdx(), 1, 0:TILE_M, 0:TILE_O] <<= l0c
                    cv1.ready()

                with If(slot == 0):
                    cv0.wait()
                    with If(vrows > 0):
                        mm_ub[0:vrows, 0:TILE_O] <<= ws[GetCubeIdx(), 0, row0:row0 + vrows, 0:TILE_O]
                        ig_ub[0:vrows, 0:8] <<= inv_gm[gm_r0:gm_r0 + vrows, 0:8]
                        _scale_rows(mm_ub, ig_ub)
                        cast(o_ub, mm_ub)
                        out[gm_r0:gm_r0 + vrows, o0:o0 + valid_o] <<= o_ub[0:vrows, 0:valid_o]
                    cv0.free()
                with Else():
                    cv1.wait()
                    with If(vrows > 0):
                        mm_ub[0:vrows, 0:TILE_O] <<= ws[GetCubeIdx(), 1, row0:row0 + vrows, 0:TILE_O]
                        ig_ub[0:vrows, 0:8] <<= inv_gm[gm_r0:gm_r0 + vrows, 0:8]
                        _scale_rows(mm_ub, ig_ub)
                        cast(o_ub, mm_ub)
                        out[gm_r0:gm_r0 + vrows, o0:o0 + valid_o] <<= o_ub[0:vrows, 0:valid_o]
                    cv1.free()

    return out


# Per-row scalar broadcast that is correct in THIS easyasc simulator+device.
# A plain `mul(wide[M, TILE_O], wide, narrow[M, 8])` is WRONG for TILE_O > 64:
# the default broadcast advances the narrow operand by ONE C0 datablock per
# vector repeat, but a 128-wide row spans TWO repeats, so row m reads narrow
# datablock 2m (row m got scaled by narrow row 2m). The robust idiom is to
# multiply in 64-column chunks (exactly ONE repeat per row) with the narrow
# operand pinned per row: src2_blk_stride=0 (all 8 cols read the same datablock
# element) and src2_rep_stride=1 (advance 1 datablock = 1 row per repeat).
# `narrow` must be a DENSE [M, 8] tile (e.g. loaded from a [M,8] GM buffer, or
# produced by brcb of a cadd-dense [M,1] source — NOT a GM-loaded [M,1], whose
# rows are 32B-padded and make brcb scatter every 8th row).
_SCALE_CHUNK = 64


def _scale_rows(wide, narrow):
    # IMPORTANT: unroll with Python's builtins.range so the column offsets are
    # compile-time int constants. Using easyasc's loop `range` here makes c0 a
    # symbolic Var, and a Var-offset column slice gets the wrong dst rep-stride
    # in the simulator (rows end up scaled by narrow[2m] / doubled).
    # Default stride inference over a dense [M,8] narrow tile is correct
    # (device-verified in matmul_add_rmsnorm). Forcing src2_blk_stride=0 made
    # EVERY row read row0's datablock on device (aligned-case error 7.27).
    mul(wide[0:ROWS, 0:64], wide[0:ROWS, 0:64], narrow)
    mul(wide[0:ROWS, 64:128], wide[0:ROWS, 64:128], narrow)


# ─────────────────────────── Host helpers ───────────────────────────
ALIGN_M = 128        # = TILE_M; pad M so valid_m == TILE_M always (see below)
ALIGN_K = 128
ALIGN_O = 128


def _ceil_mult(x, m):
    return ((x + m - 1) // m) * m


def pad_inputs(x2d, weight):
    M, K = x2d.shape
    K2, O = weight.shape
    Mp = _ceil_mult(M, ALIGN_M)
    Kp = _ceil_mult(K, ALIGN_K)
    Op = _ceil_mult(O, ALIGN_O)
    # Pad M to a TILE_M multiple (KB H27 / 2026-06-05 device pitfalls): the cube
    # path loads x into an NZ-fractal L1 tile and `matmul` reads the FULL TILE_M
    # rows. For an M-tail (valid_m < TILE_M) the kernel zeroes the tile with
    # `set_constant_to_l1`, but on device that only clears the *logical* view —
    # the NZ-fractal padding rows [valid_m:TILE_M] keep stale data from a prior
    # tile that the DBuff slot held, and `matmul` accumulates it. The simulator
    # models a dense tensor so the zero takes effect → sim PASS / device FAIL.
    # It surfaces only when an M-tail coincides with an ODD K-tile count (≥3,
    # e.g. K=320→384) so the reused DBuff slot still holds a previous full-M
    # tile's rows. Host-padding M to TILE_M removes the partial-M branch entirely
    # (valid_m == TILE_M always); the all-zero pad rows produce garbage output
    # rows that are simply sliced off (out[:M]).
    xp = torch.zeros(Mp, Kp, dtype=torch.float16)
    xp[:M, :K] = x2d
    wp = torch.zeros(Kp, Op, dtype=torch.float16)
    wp[:K, :O] = weight
    wt = wp.t().contiguous()                       # [Op, Kp]
    return xp, wt, Mp, Kp, Op, K


def build_codegen_inputs():
    M, K, O = 512, 256, 128
    x2d = torch.randn(M, K, dtype=torch.float16)
    weight = torch.randn(K, O, dtype=torch.float16)
    xp, wt, Mk, Kp, Op, Korig = pad_inputs(x2d, weight)
    inv_gm = torch.zeros(Mk, 8, dtype=torch.float32)
    out = torch.zeros(Mk, Op, dtype=torch.float16)
    return (xp, wt, inv_gm, out, Mk, Kp, Op, Korig)


def _run(simulator, M, K, O):
    x2d = torch.randn(M, K, dtype=torch.float16) * 0.1
    weight = torch.randn(K, O, dtype=torch.float16) * 0.1
    xp, wt, Mk, Kp, Op, Korig = pad_inputs(x2d, weight)
    inv_gm = torch.zeros(Mk, 8, dtype=torch.float32)
    outp = torch.zeros(Mk, Op, dtype=torch.float16)
    res = OpExec(rms_matmul_scale_custom, simulator=simulator)(
        xp, wt, inv_gm, outp, Mk, Kp, Op, Korig,
        shape_bindings={0: [0, 1], 1: [2, 1], 2: [0, None], 3: [0, 2]})
    out = res[:M, :O].float()
    inv_rms = torch.rsqrt(x2d.float().square().mean(-1, keepdim=True) + EPS)
    ref = (inv_rms * (x2d.float() @ weight.float())).float()
    ok = torch.allclose(out, ref, rtol=1e-3, atol=1e-3)
    md = torch.abs(out - ref).max().item()
    pad = "" if (K % ALIGN_K == 0 and O % ALIGN_O == 0) else f" (pad K {K}->{Kp}, O {O}->{Op})"
    print(f"{'sim' if simulator else 'dev'} (M={M},K={K},O={O}): "
          f"{'PASS' if ok else 'FAIL'}  max_abs_diff={md:.3e}{pad}")
    return ok


def main():
    import sys
    torch.manual_seed(0)
    sim = "--dev" not in sys.argv
    if not sim:
        import devrun  # noqa: F401
    shapes = [(256, 256, 256), (200, 320, 192)]   # one aligned, one non-128-aligned
    all_ok = True
    for (M, K, O) in shapes:
        all_ok = _run(sim, M, K, O) and all_ok
    print("ALL PASS" if all_ok else "SOME FAILED")

if __name__ == "__main__":
    main()
