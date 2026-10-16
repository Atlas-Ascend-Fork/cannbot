# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Flash-attention DECODE — SOFTWARE-PIPELINED perf variant of flash_attn_decode.py.

# Pairs with input_example/mha (cann-bench level4 MHA decode/MTP).

READ flash_attn_decode.py FIRST. This is the SAME kernel (BH-parallel, tiny-M online
softmax, in-kernel normalise, all the a2 exp/shape workarounds) but software-pipelined
like the upstream flash_attn_full.py: per (b,n) head it interleaves, in ONE loop
iteration `ni`,

    stage 1 (QK + softmax of KV-tile ni)   ||   stage 2 (P@V + rescale of KV-tile ni-1)

so the cube unit can run tile ni's QK matmul while the vector unit finishes tile ni-1's
softmax/rescale. The CvMutex/VcMutex hand-offs + double-buffered (slot = cnt%2) GM
workspaces / L1 / L0C are what let the two sub-cores overlap across iterations. This is
the canonical way to hide the per-tile GM-bounce + matmul latency that the simple
two-block-per-tile flash_attn_decode.py pays serially.

COST OF THE PIPELINE (why this is the *variant*, not the canonical example):
  * the QK of tile ni and the PV of tile ni-1 live in the SAME iteration but belong to
    DIFFERENT tiles — you must read it as a 2-tiles-in-flight pipeline;
  * everything stage1 writes that stage2 reads one iteration later is DOUBLE-BUFFERED:
    score_ws/p_ws/pv_ws have a 2-slot dim, l1k/l1p/l1v/l0c_qk/l0c_pv are 2-slot DBuffs,
    and the online-softmax correction `corr = exp(m_old - m_new)` is carried from stage1
    to stage2 in a 2-slot `corr_buf` (stage1 writes corr_buf[s1]; stage2, one iteration
    later, rescales acc by corr_buf[s2]);
  * prologue ni=0 runs stage1 only; epilogue ni=tiles_n runs stage2 only (drain).

ASSUMES Skv % TILE_N == 0 (no partial tail tile) — true for all cann-bench decode shapes
(Skv in {128,256,512,1024,2048,4096}); lets the per-tile mask load sit inside the stage-1
auto_sync with NO dup+bar_all prelude (a per-tile barrier would stall the pipeline). For a
tail, restore the `dup(mbias_t, NEG_LARGE); bar_all()` prelude from flash_attn_decode.py.

Correctness identical to flash_attn_decode.py (same online-softmax math; the pipeline only
reorders WHEN each tile's QK/PV runs). The corr-rescale of acc happens one iteration after
its max-update, but acc/l_run both end relative to the final running max, so out=acc/l_run
is unchanged. See flash_attn_decode.py header for the exp/[MH,8]/[1,MH]/DCHUNK rules.

PERF (910B2, 100-launch avg, us; vs the non-pipelined flash_attn_decode.py and FIA t_hw) —
the pipeline is SITUATIONAL, like split-KV: it wins where intra-head overlap matters and
loses where inter-head parallelism already hides latency:
    case10 B1  BH=32   16-tile : 117 -> 103  (WIN -12%, 6.7x->5.9x FIA)   <- low-BH/long-KV
    case15 B60 BH=960  D256     : 715 -> 686  (WIN  -4%)                   <- compute-heavier
    case11 B16 BH=512  8-tile   : 673 -> 725  (LOSE +8%)
    case13 B60 BH=1920 4-tile   : 1245-> 1346 (LOSE +8%)
So: DEFAULT to flash_attn_decode.py (simpler + faster on the high-BH majority); reach for
THIS pipelined variant only for the low-BH / long-KV / large-D regime (same niche as
flash_attn_decode_splitkv.py). All cases sim + 910B2-device verified correct.
"""
import os
import builtins

from easyasc.a2 import *

from easyasc import globvars as _gv
_gv.device_type = 'b2'
_gv.core_num = 24

NEG_LARGE = -3.0e4
TINY = 1.0e-30
EXP_FLOOR = -80.0
MH = int(os.environ.get("FAD_MH", "16"))
TILE_N = 128
HALF_N = TILE_N // 2
SCAL = HALF_N
DK_CAP = int(os.environ.get("FAD_DK_CAP", "256"))
K_SPLIT = 128
N_SPLIT = 128
DCHUNK_OFFS = [i * HALF_N for i in builtins.range(DK_CAP // HALF_N)]


@kernel()
def flash_attn_decode_pipelined_kernel(
    q: GMTensor,            # [B*N*Sq, D]    fp16/bf16  (BNSD-flattened)
    k: GMTensor,            # [B*N*Skv, D]
    v: GMTensor,            # [B*N*Skv, D]
    mbias: GMTensor,        # [Sq, Skv]      fp32 additive causal bias (0 / NEG_LARGE)
    out: GMTensor,          # [B*N*Sq, D]    fp16/bf16  final normalised output
    B: Var, N: Var, Sq: Var, Skv: Var, D: Var, scale: Var,
):
    qdt = q.dtype

    # ---- 2-slot GM bridges (slot = stageN_cnt % 2) ----
    score_ws = split_workspace(DT.float, [GetCubeNum(), 2, MH, TILE_N], name="score_ws")
    p_ws = split_workspace(qdt, [GetCubeNum(), 2, MH, TILE_N], name="p_ws")
    pv_ws = split_workspace(DT.float, [GetCubeNum(), 2, MH, DK_CAP], name="pv_ws")

    # ---- L1 / L0C, double-buffered where stage1 produces and stage2 consumes ----
    l1q = DBuff(qdt, [MH, DK_CAP], Position.L1)            # Q: loaded once per head, l1q[0]
    l1k = DBuff(qdt, [TILE_N, DK_CAP], Position.L1)        # K tile (stage1, slot s1)
    l1p = DBuff(qdt, [MH, TILE_N], Position.L1)            # P     (stage2, slot s2)
    l1v = DBuff(qdt, [TILE_N, DK_CAP], Position.L1)        # V tile (stage2, slot s2)
    l0c_qk = DBuff(DT.float, [MH, TILE_N], Position.L0C)   # stage1
    l0c_pv = DBuff(DT.float, [MH, DK_CAP], Position.L0C)   # stage2

    qk_mutex = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)
    pv_mutex = CvMutex(2, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)
    p_mutex = VcMutex(1, src_end_pipe=Pipe.MTE3, dst_end_pipe=Pipe.FIX)

    # ---- softmax scratch (see flash_attn_decode.py: exp'd scalars MUST be [MH,SCAL]) ----
    scores = Tensor(DT.float, [MH, TILE_N], Position.UB)
    redm = Tensor(DT.float, [MH, HALF_N], Position.UB)
    mbias_t = Tensor(DT.float, [MH, TILE_N], Position.UB)
    p_ub = Tensor(qdt, [MH, TILE_N], Position.UB)
    pv_ub = Tensor(DT.float, [MH, DK_CAP], Position.UB)
    acc = Tensor(DT.float, [MH, DK_CAP], Position.UB)      # running output (rescaled in stage2)
    m_run = Tensor(DT.float, [MH, SCAL], Position.UB)      # running max (updated in stage1)
    m_new = Tensor(DT.float, [MH, SCAL], Position.UB)
    l_run = Tensor(DT.float, [MH, SCAL], Position.UB)      # running denom (updated in stage1)
    red_s = Tensor(DT.float, [1, MH], Position.UB)
    tmax8 = Tensor(DT.float, [MH, 8], Position.UB)
    tsum8 = Tensor(DT.float, [MH, 8], Position.UB)
    corr_buf = DBuff(DT.float, [MH, SCAL], Position.UB)    # carries corr stage1->stage2 (2-slot)
    out_low = Tensor(qdt, [MH, DK_CAP], Position.UB)

    total_heads = Var(B * N)
    heads_per_core = CeilDiv(total_heads, GetCubeNum())
    h_begin = Var(heads_per_core * GetCubeIdx())
    h_end = Min(h_begin + heads_per_core, total_heads)
    tiles_n = CeilDiv(Skv, TILE_N)
    c = GetCubeIdx()

    stage1_cnt = Var(0)
    stage2_cnt = Var(0)

    for hg in range(h_begin, h_end):
        qbase = Var(hg * Sq)
        kvbase = Var(hg * Skv)
        valid_m = Sq

        # Q is fixed across KV tiles -> load once into l1q[0].
        dup(m_run, NEG_LARGE)
        dup(l_run, 0.0)
        dup(acc, 0.0)
        set_constant_to_l1(l1q[0], 0.0)
        l1q[0][0:valid_m, 0:D] <<= q[qbase:qbase + valid_m, 0:D]
        bar_all()

        for ni in range(0, tiles_n + 1):
            # ============ STAGE 1: QK^T(tile ni) + online softmax ============
            if ni < tiles_n:
                with auto_sync():
                    s1 = var_mod(stage1_cnt, 2)
                    off = Var(ni * TILE_N)
                    set_constant_to_l1(l1k[s1], 0.0)
                    l1k[s1][0:TILE_N, 0:D] <<= k[kvbase + off:kvbase + off + TILE_N, 0:D]
                    mbias_t[0:valid_m, 0:TILE_N] <<= mbias[0:valid_m, off:off + TILE_N]
                    matmul(l0c_qk[s1], l1q[0], l1k[s1],
                           splitk=K_SPLIT, m=MH, n=TILE_N, k=D, is_init=True)

                    qk_mutex.lock()
                    score_ws[c, s1, 0:MH, 0:TILE_N] <<= l0c_qk[s1]
                    qk_mutex.ready()
                    qk_mutex.wait()
                    scores <<= score_ws[c, s1, 0:MH, 0:TILE_N]

                    muls(scores, scores, scale)
                    add(scores, scores, mbias_t)
                    # tile max -> [MH,8]
                    vmax(redm[0:MH, 0:HALF_N], scores[0:MH, 0:HALF_N], scores[0:MH, HALF_N:TILE_N])
                    cmax(red_s[0:1, 0:MH], redm[0:MH, 0:HALF_N])
                    brcb(tmax8, red_s[0:1, 0:MH], repeat=MH // 8, dst_blk_stride=1, dst_rep_stride=8)
                    # corr = exp(m_old - m_new), stashed per-slot for stage2 (one iter later)
                    vmax(m_new, m_run, tmax8)
                    sub(corr_buf[s1], m_run, m_new)
                    vmaxs(corr_buf[s1], corr_buf[s1], EXP_FLOOR)
                    exp(corr_buf[s1], corr_buf[s1])
                    vmax(m_run, m_run, tmax8)                       # m_run <- m_new
                    # p = exp(scores - m_new)
                    sub(scores[0:MH, 0:HALF_N], scores[0:MH, 0:HALF_N], m_new[0:MH, 0:HALF_N])
                    sub(scores[0:MH, HALF_N:TILE_N], scores[0:MH, HALF_N:TILE_N], m_new[0:MH, 0:HALF_N])
                    vmaxs(scores, scores, EXP_FLOOR)
                    exp(scores, scores)
                    # online denom: l = l*corr + tile_sum
                    add(redm[0:MH, 0:HALF_N], scores[0:MH, 0:HALF_N], scores[0:MH, HALF_N:TILE_N])
                    cadd(red_s[0:1, 0:MH], redm[0:MH, 0:HALF_N], repeat=MH, dst_rep_stride=1)
                    brcb(tsum8, red_s[0:1, 0:MH], repeat=MH // 8, dst_blk_stride=1, dst_rep_stride=8)
                    mul(l_run, l_run, corr_buf[s1])
                    add(l_run, l_run, tsum8)

                    cast(p_ub, scores)
                    p_mutex.lock()
                    p_ws[c, s1, 0:MH, 0:TILE_N] <<= p_ub[0:MH, 0:TILE_N]
                    p_mutex.ready()
                    qk_mutex.free()
                    stage1_cnt += 1

            # ============ STAGE 2: P@V(tile ni-1) + online rescale of acc ============
            if ni > 0:
                with auto_sync():
                    s2 = var_mod(stage2_cnt, 2)
                    prev_off = Var((ni - 1) * TILE_N)
                    set_constant_to_l1(l1v[s2], 0.0)
                    l1v[s2][0:TILE_N, 0:D] <<= v[kvbase + prev_off:kvbase + prev_off + TILE_N, 0:D]
                    p_mutex.wait()
                    l1p[s2][0:MH, 0:TILE_N] <<= p_ws[c, s2, 0:MH, 0:TILE_N]
                    matmul(l0c_pv[s2], l1p[s2], l1v[s2].T,
                           splitn=N_SPLIT, m=MH, n=D, k=TILE_N, is_init=True)
                    p_mutex.free()

                    pv_mutex.lock()
                    pv_ws[c, s2, 0:MH, 0:D] <<= l0c_pv[s2]
                    pv_mutex.ready()
                    pv_mutex.wait()
                    pv_ub[0:MH, 0:D] <<= pv_ws[c, s2, 0:MH, 0:D]

                    # acc = acc * corr(tile ni-1) + PV   (corr stashed by stage1 last iter)
                    for od in DCHUNK_OFFS:
                        mul(acc[0:MH, od:od + HALF_N], acc[0:MH, od:od + HALF_N], corr_buf[s2][0:MH, 0:HALF_N])
                    add(acc[0:MH, 0:D], acc[0:MH, 0:D], pv_ub[0:MH, 0:D])
                    pv_mutex.free()
                    stage2_cnt += 1

        # ---- finalize: out = acc / l_run ----
        with auto_sync():
            for od in DCHUNK_OFFS:
                div(acc[0:MH, od:od + HALF_N], acc[0:MH, od:od + HALF_N], l_run[0:MH, 0:HALF_N])
            cast(out_low[0:MH, 0:D], acc[0:MH, 0:D])
        bar_all()
        for hr in range(0, valid_m):
            orow = Var(qbase + hr)
            out[orow:orow + 1, 0:D] <<= out_low[hr:hr + 1, 0:D]
        bar_all()

    return out


# ---------------------------------------------------------------------------
# build_codegen_inputs() + simulator self-check  (Skv % TILE_N == 0 required)
# ---------------------------------------------------------------------------
def _causal_mbias(Sq, Skv, is_causal):
    import torch
    mb = torch.zeros(Sq, Skv, dtype=torch.float32)
    if is_causal:
        i = torch.arange(Sq).unsqueeze(-1)
        j = torch.arange(Skv).unsqueeze(0)
        mb[(j > (i + (Skv - Sq)))] = NEG_LARGE
    return mb


def _make_case(Bv, Nv, Sqv, Skvv, Dv, scalev, is_causal=False, dtype=None, seed=0):
    import torch
    if dtype is None:
        dtype = torch.float16
    assert Skvv % TILE_N == 0, "pipelined variant assumes Skv % TILE_N == 0 (no tail)"
    torch.manual_seed(seed)
    q = (torch.rand(Bv * Nv * Sqv, Dv) * 2 - 1).to(dtype)
    k = (torch.rand(Bv * Nv * Skvv, Dv) * 2 - 1).to(dtype)
    v = (torch.rand(Bv * Nv * Skvv, Dv) * 2 - 1).to(dtype)
    mbias = _causal_mbias(Sqv, Skvv, is_causal)
    out = torch.zeros(Bv * Nv * Sqv, Dv, dtype=dtype)
    return q, k, v, mbias, out, Bv, Nv, Sqv, Skvv, Dv, float(scalev)


def build_codegen_inputs():
    return _make_case(1, 3, 2, 384, 64, 0.125, is_causal=True, seed=0)


def _torch_ref(q, k, v, mbias, B, N, Sq, Skv, D, scale):
    import builtins as _b
    import torch
    qf = q.float().reshape(B, N, Sq, D)
    kf = k.float().reshape(B, N, Skv, D)
    vf = v.float().reshape(B, N, Skv, D)
    mb = mbias.float()
    out = torch.zeros(B, N, Sq, D, dtype=torch.float32)
    for b in _b.range(B):
        for n in _b.range(N):
            sc = (qf[b, n] @ kf[b, n].transpose(-2, -1)) * scale + mb
            sc = sc - sc.max(dim=-1, keepdim=True).values
            p = torch.exp(sc)
            out[b, n] = (p @ vf[b, n]) / (p.sum(dim=-1, keepdim=True) + TINY)
    return out


def _run_case(name, args, rtol=2e-2, atol=2e-2):
    import torch
    from easyasc.simulator import SimulatorConfig
    q, k, v, mbias, out, B, N, Sq, Skv, D, scale = args
    flash_attn_decode_pipelined_kernel._simulator_config = SimulatorConfig(
        core_count=1, execution_timeout_s=1200.0)
    res = OpExec(flash_attn_decode_pipelined_kernel, simulator=True)(
        q, k, v, mbias, out, B, N, Sq, Skv, D, scale,
        shape_bindings={0: [None, 4], 1: [None, 4], 2: [None, 4], 3: [2, 3], 4: [None, 4]})
    out_k = res.float().reshape(B, N, Sq, D)
    ref = _torch_ref(q, k, v, mbias, B, N, Sq, Skv, D, scale)
    mad = torch.abs(out_k - ref).max().item()
    print(f"{name}: shape(B={B},N={N},Sq={Sq},Skv={Skv},D={D}) max_abs_diff={mad:.6e}", flush=True)
    torch.testing.assert_close(out_k, ref, rtol=rtol, atol=atol)
    return mad


def main():
    import torch
    _run_case("decode_sq1_d128", _make_case(2, 3, 1, 512, 128, 0.0884, is_causal=False, seed=0))
    _run_case("decode_sq1_d256", _make_case(2, 3, 1, 384, 256, 0.0625, is_causal=False, seed=1))
    _run_case("mtp_sq2_d128_causal", _make_case(2, 3, 2, 512, 128, 0.0884, is_causal=True, seed=2))
    _run_case("mtp_sq2_d256_causal", _make_case(2, 3, 2, 384, 256, 0.0625, is_causal=True, seed=3))
    _run_case("decode_sq1_d128_bf16",
              _make_case(2, 3, 1, 512, 128, 0.0884, is_causal=False, dtype=torch.bfloat16, seed=4),
              rtol=4e-2, atol=4e-2)
    print("ALL SIMULATOR CHECKS PASSED", flush=True)

if __name__ == "__main__":
    main()
