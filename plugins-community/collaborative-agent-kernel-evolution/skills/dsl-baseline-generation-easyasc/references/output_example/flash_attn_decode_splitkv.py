# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Flash-attention DECODE with SPLIT-KV / flash-decoding — A2 cube, TWO-kernel pipeline.

# Pairs with input_example/mha (cann-bench level4 MHA, decode — small-batch long-KV).

WHY (the lever flash_attn_decode.py documented but didn't pull):
  Plain BH-parallel decode (flash_attn_decode.py) gives each (b,n) head to ONE core that
  streams the whole KV cache serially. When BH = B*N >= #cores that saturates the chip.
  But when BH < #cores with a LONG KV (e.g. B=1, N=8, Skv=8192 -> BH=8 << 24 cores), most
  cores idle and the few busy ones serialise the long KV. SPLIT-KV (a.k.a. flash-decoding)
  fixes this: split the KV cache into `n_splits` chunks, give each (head, split) pair to a
  different core (BH*n_splits work-items), compute a PARTIAL softmax per chunk, then a
  second pass LSE-merges the partials. This is the defining IFA-decode optimisation.

  Cross-core merge cannot happen inside one kernel launch (a2 has no device-wide barrier;
  bar_all is intra-AICore only), so this is a TWO-KERNEL pipeline sharing a GM workspace:

    kernel 1 (PARTIAL):  work-item = (head hg, split si).  Online-softmax over THIS split's
        KV slice only; emit UN-normalised partial acc o_i [Sq,D], local max m_i [Sq], local
        denom l_i [Sq] to GM. (Same exp-safe [MH,64] machinery as flash_attn_decode.py,
        minus the final divide.)
    kernel 2 (COMBINE):  work-item = head hg.  Read all n_splits partials; gmax = max_i m_i;
        scale_i = exp(m_i - gmax); out = (Σ scale_i·o_i) / (Σ scale_i·l_i).  Pure vector.

  Correctness of masked/empty splits: an all-masked split has m_i = sentinel, so its
  scale_i = exp(sentinel - gmax) -> clamped exp underflows to ~0 — it contributes nothing
  to either sum, exactly as required (as long as >=1 split has a live key, true for these
  cann-bench shapes since S<=S_kv).

Inherits every a2 quirk + the exp/shape rules proven in flash_attn_decode.py (read its
header first): [MH,8] `exp` returns inf -> keep exp'd scalars [MH,64]; [1,MH] arithmetic is
unreliable -> [1,MH] only as transient cmax/cadd output; clamp exp args to EXP_FLOOR;
unroll D-chunks with Python-constant offsets (runtime-Var slice offset trips codegen).
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


# ============================================================================
# KERNEL 1 — PARTIAL: per (head, kv-split) un-normalised online-softmax partial.
# ============================================================================
@kernel()
def flash_attn_decode_partial_kernel(
    q: GMTensor,            # [B*N*Sq, D]
    k: GMTensor,            # [B*N*Skv, D]
    v: GMTensor,            # [B*N*Skv, D]
    mbias: GMTensor,        # [Sq, Skv]  additive causal bias (0 / NEG_LARGE)
    po: GMTensor,           # [B*N*nsplit*Sq, D]  fp32 un-normalised partial acc (rel. to local max)
    pm: GMTensor,           # [B*N*nsplit*Sq, 8]  local row max (col 0 used)
    pl: GMTensor,           # [B*N*nsplit*Sq, 8]  local row denom
    B: Var, N: Var, Sq: Var, Skv: Var, D: Var, scale: Var, nsplit: Var,
):
    qdt = q.dtype
    score_ws = split_workspace(DT.float, [GetCubeNum(), MH, TILE_N], name="score_ws")
    p_ws = split_workspace(qdt, [GetCubeNum(), MH, TILE_N], name="p_ws")
    pv_ws = split_workspace(DT.float, [GetCubeNum(), MH, DK_CAP], name="pv_ws")
    l1q = DBuff(qdt, [MH, DK_CAP], Position.L1)
    l1k = DBuff(qdt, [TILE_N, DK_CAP], Position.L1)
    l1p = DBuff(qdt, [MH, TILE_N], Position.L1)
    l1v = DBuff(qdt, [TILE_N, DK_CAP], Position.L1)
    l0c_qk = Tensor(DT.float, [MH, TILE_N], Position.L0C)
    l0c_pv = Tensor(DT.float, [MH, DK_CAP], Position.L0C)
    l1cnt = Var(0)
    qk_mutex = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)
    pv_mutex = CvMutex(2, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)
    p_mutex = VcMutex(1, src_end_pipe=Pipe.MTE3, dst_end_pipe=Pipe.FIX)

    scores = Tensor(DT.float, [MH, TILE_N], Position.UB)
    redm = Tensor(DT.float, [MH, HALF_N], Position.UB)
    mbias_t = Tensor(DT.float, [MH, TILE_N], Position.UB)
    p_ub = Tensor(qdt, [MH, TILE_N], Position.UB)
    pv_ub = Tensor(DT.float, [MH, DK_CAP], Position.UB)
    acc = Tensor(DT.float, [MH, DK_CAP], Position.UB)
    red_s = Tensor(DT.float, [1, MH], Position.UB)
    tmax8 = Tensor(DT.float, [MH, 8], Position.UB)
    tsum8 = Tensor(DT.float, [MH, 8], Position.UB)
    m_run = Tensor(DT.float, [MH, SCAL], Position.UB)
    m_new = Tensor(DT.float, [MH, SCAL], Position.UB)
    corr = Tensor(DT.float, [MH, SCAL], Position.UB)
    l_run = Tensor(DT.float, [MH, SCAL], Position.UB)
    m_out = Tensor(DT.float, [MH, 8], Position.UB)
    l_out = Tensor(DT.float, [MH, 8], Position.UB)

    split_len = CeilDiv(Skv, nsplit)            # KV positions per split
    total_wi = Var(B * N * nsplit)              # work-items = (head, split)
    wi_per_core = CeilDiv(total_wi, GetCubeNum())
    wi_begin = Var(wi_per_core * GetCubeIdx())
    wi_end = Min(wi_begin + wi_per_core, total_wi)
    c = GetCubeIdx()

    for wi in range(wi_begin, wi_end):
        hg = var_div(wi, nsplit)                # head index
        si = var_mod(wi, nsplit)                # split index
        qbase = Var(hg * Sq)
        kvbase = Var(hg * Skv)
        kv_lo = Var(si * split_len)             # this split's KV range [kv_lo, kv_hi)
        kv_hi = Min(kv_lo + split_len, Skv)
        valid_m = Sq

        dup(m_run, NEG_LARGE)
        dup(l_run, 0.0)
        dup(acc, 0.0)
        bar_all()

        n_loc = CeilDiv(kv_hi - kv_lo, TILE_N)   # KV tiles inside this split
        for kt in range(0, n_loc):
            off = Var(kv_lo + kt * TILE_N)       # GLOBAL kv offset
            tn = Min(TILE_N, kv_hi - off)

            dup(mbias_t, NEG_LARGE)
            bar_all()
            mbias_t[0:valid_m, 0:tn] <<= mbias[0:valid_m, off:off + tn]

            with auto_sync():
                set_constant_to_l1(l1q[0], 0.0)
                set_constant_to_l1(l1k[l1cnt], 0.0)
                l1q[0][0:valid_m, 0:D] <<= q[qbase:qbase + valid_m, 0:D]
                l1k[l1cnt][0:tn, 0:D] <<= k[kvbase + off:kvbase + off + tn, 0:D]
                matmul(l0c_qk, l1q[0], l1k[l1cnt], splitk=K_SPLIT, m=MH, n=TILE_N, k=D, is_init=True)
            bar_all()

            with auto_sync():
                qk_mutex.lock()
                score_ws[c, 0:MH, 0:TILE_N] <<= l0c_qk
                qk_mutex.ready()
                qk_mutex.wait()
                scores <<= score_ws[c, 0:MH, 0:TILE_N]
                muls(scores, scores, scale)
                add(scores, scores, mbias_t)
                vmax(redm[0:MH, 0:HALF_N], scores[0:MH, 0:HALF_N], scores[0:MH, HALF_N:TILE_N])
                cmax(red_s[0:1, 0:MH], redm[0:MH, 0:HALF_N])
                brcb(tmax8, red_s[0:1, 0:MH], repeat=MH // 8, dst_blk_stride=1, dst_rep_stride=8)
                vmax(m_new, m_run, tmax8)
                sub(corr, m_run, m_new)
                vmaxs(corr, corr, EXP_FLOOR)
                exp(corr, corr)
                vmax(m_run, m_run, tmax8)
                sub(scores[0:MH, 0:HALF_N], scores[0:MH, 0:HALF_N], m_new[0:MH, 0:HALF_N])
                sub(scores[0:MH, HALF_N:TILE_N], scores[0:MH, HALF_N:TILE_N], m_new[0:MH, 0:HALF_N])
                vmaxs(scores, scores, EXP_FLOOR)
                exp(scores, scores)
                add(redm[0:MH, 0:HALF_N], scores[0:MH, 0:HALF_N], scores[0:MH, HALF_N:TILE_N])
                cadd(red_s[0:1, 0:MH], redm[0:MH, 0:HALF_N], repeat=MH, dst_rep_stride=1)
                brcb(tsum8, red_s[0:1, 0:MH], repeat=MH // 8, dst_blk_stride=1, dst_rep_stride=8)
                mul(l_run, l_run, corr)
                add(l_run, l_run, tsum8)
                cast(p_ub, scores)
                qk_mutex.free()
                p_mutex.lock()
                p_ws[c, 0:MH, 0:TILE_N] <<= p_ub[0:MH, 0:TILE_N]
                p_mutex.ready()

            with auto_sync():
                set_constant_to_l1(l1v[l1cnt], 0.0)
                l1v[l1cnt][0:tn, 0:D] <<= v[kvbase + off:kvbase + off + tn, 0:D]
                p_mutex.wait()
                for pr in range(0, MH):
                    l1p[l1cnt][pr:pr + 1, 0:TILE_N] <<= p_ws[c, pr:pr + 1, 0:TILE_N]
                matmul(l0c_pv, l1p[l1cnt], l1v[l1cnt].T, splitn=N_SPLIT, m=MH, n=D, k=TILE_N, is_init=True)
                p_mutex.free()
                pv_mutex.lock()
                pv_ws[c, 0:MH, 0:D] <<= l0c_pv
                pv_mutex.ready()
                pv_mutex.wait()
                pv_ub[0:MH, 0:D] <<= pv_ws[c, 0:MH, 0:D]
                for od in DCHUNK_OFFS:
                    mul(acc[0:MH, od:od + HALF_N], acc[0:MH, od:od + HALF_N], corr[0:MH, 0:HALF_N])
                add(acc[0:MH, 0:D], acc[0:MH, 0:D], pv_ub[0:MH, 0:D])
                pv_mutex.free()
            l1cnt += 1

        # ---- emit UN-normalised partial: acc (fp32), local max (m_run), local denom (l_run) ----
        with auto_sync():
            adds(m_out, m_run[0:MH, 0:8], 0.0)     # copy first 8 cols (all replicated equal)
            adds(l_out, l_run[0:MH, 0:8], 0.0)
        bar_all()
        for hr in range(0, valid_m):
            prow = Var((hg * nsplit + si) * Sq + hr)
            po[prow:prow + 1, 0:D] <<= acc[hr:hr + 1, 0:D]    # fp32 partial acc
            pm[prow:prow + 1, 0:8] <<= m_out[hr:hr + 1, 0:8]
            pl[prow:prow + 1, 0:8] <<= l_out[hr:hr + 1, 0:8]
        bar_all()
    return po, pm, pl


# ============================================================================
# KERNEL 2 — COMBINE: LSE-merge the n_splits partials per head (pure vector).
# ============================================================================
@kernel()
def flash_attn_decode_combine_kernel(
    po: GMTensor,           # [B*N*nsplit*Sq, D]
    pm: GMTensor,           # [B*N*nsplit*Sq, 8]
    pl: GMTensor,           # [B*N*nsplit*Sq, 8]
    out: GMTensor,          # [B*N*Sq, D]  final normalised output
    B: Var, N: Var, Sq: Var, D: Var, nsplit: Var,
):
    odt = out.dtype
    # one (head) work-item handles its Sq rows; partials live in UB as [MH,*]
    o_i = Tensor(DT.float, [MH, DK_CAP], Position.UB)    # current split's partial acc
    m_i8 = Tensor(DT.float, [MH, 8], Position.UB)
    l_i8 = Tensor(DT.float, [MH, 8], Position.UB)
    gmax = Tensor(DT.float, [MH, SCAL], Position.UB)     # global max over splits
    scl = Tensor(DT.float, [MH, SCAL], Position.UB)      # exp(m_i - gmax)
    lprod = Tensor(DT.float, [MH, SCAL], Position.UB)    # scl * l_i, 64-wide
    acc = Tensor(DT.float, [MH, DK_CAP], Position.UB)
    lsum = Tensor(DT.float, [MH, SCAL], Position.UB)     # running denom, 64-wide (NOT [MH,8]:
    out_low = Tensor(odt, [MH, DK_CAP], Position.UB)     #   div with an [MH,8] divisor mis-broadcasts)

    total_heads = Var(B * N)
    heads_per_core = CeilDiv(total_heads, GetCubeNum())
    h_begin = Var(heads_per_core * GetVecIdx())
    h_end = Min(h_begin + heads_per_core, total_heads)
    valid_m = Sq

    for hg in range(h_begin, h_end):
        pbase = Var(hg * nsplit)        # first partial row-group for this head

        # ---- pass A: global max over splits (each split's load+vmax in its own auto_sync) ----
        dup(gmax, NEG_LARGE)
        bar_all()
        for si in range(0, nsplit):
            with auto_sync():
                prow = Var((pbase + si) * Sq)
                m_i8[0:valid_m, 0:8] <<= pm[prow:prow + valid_m, 0:8]
                vmax(gmax, gmax, m_i8)              # gmax loop-carried (same vec core, ordered)
        bar_all()

        # ---- pass B: rescale-accumulate ----
        dup(acc, 0.0)
        dup(lsum, 0.0)
        bar_all()
        for si in range(0, nsplit):
            with auto_sync():
                prow = Var((pbase + si) * Sq)
                o_i[0:valid_m, 0:D] <<= po[prow:prow + valid_m, 0:D]
                m_i8[0:valid_m, 0:8] <<= pm[prow:prow + valid_m, 0:8]
                l_i8[0:valid_m, 0:8] <<= pl[prow:prow + valid_m, 0:8]
                # scl = exp(m_i - gmax)  (WIDE [MH,64], exp-safe). Compute as -(gmax - m_i)
                # with the [MH,8] tensor as *src2* (only src2 block-broadcast is proven;
                # src1-broadcast is not), then negate.
                sub(scl, gmax, m_i8)               # gmax - m_i(8-bcast)  >= 0
                muls(scl, scl, -1.0)               # m_i - gmax  <= 0
                vmaxs(scl, scl, EXP_FLOOR)
                exp(scl, scl)
                # lsum += scl*l_i  (64-wide: l_i8[MH,8] block-broadcasts as the src2 of mul);
                # acc += scl*o_i    (scl[MH,64] scales each D chunk)
                mul(lprod, scl[0:MH, 0:SCAL], l_i8)            # scl * l_i -> [MH,64]
                add(lsum[0:MH, 0:SCAL], lsum[0:MH, 0:SCAL], lprod)
                for od in DCHUNK_OFFS:
                    mul(o_i[0:MH, od:od + HALF_N], o_i[0:MH, od:od + HALF_N], scl[0:MH, 0:HALF_N])
                add(acc[0:MH, 0:D], acc[0:MH, 0:D], o_i[0:MH, 0:D])
        bar_all()

        # ---- normalise: out = acc / lsum (lsum[MH,8] block-broadcast over D chunks) ----
        with auto_sync():
            for od in DCHUNK_OFFS:
                div(acc[0:MH, od:od + HALF_N], acc[0:MH, od:od + HALF_N], lsum[0:MH, 0:HALF_N])
            cast(out_low[0:MH, 0:D], acc[0:MH, 0:D])
        bar_all()
        for hr in range(0, valid_m):
            orow = Var(hg * Sq + hr)
            out[orow:orow + 1, 0:D] <<= out_low[hr:hr + 1, 0:D]
        bar_all()
    return out


# ---------------------------------------------------------------------------
# build_codegen_inputs() + simulator self-check (two-launch pipeline)
# ---------------------------------------------------------------------------
def _causal_mbias(Sq, Skv, is_causal):
    import torch
    mb = torch.zeros(Sq, Skv, dtype=torch.float32)
    if is_causal:
        i = torch.arange(Sq).unsqueeze(-1)
        j = torch.arange(Skv).unsqueeze(0)
        mb[(j > (i + (Skv - Sq)))] = NEG_LARGE
    return mb


def _make_case(Bv, Nv, Sqv, Skvv, Dv, nsplitv, scalev, is_causal=False, dtype=None, seed=0):
    import torch
    if dtype is None:
        dtype = torch.float16
    torch.manual_seed(seed)
    q = (torch.rand(Bv * Nv * Sqv, Dv) * 2 - 1).to(dtype)
    k = (torch.rand(Bv * Nv * Skvv, Dv) * 2 - 1).to(dtype)
    v = (torch.rand(Bv * Nv * Skvv, Dv) * 2 - 1).to(dtype)
    mbias = _causal_mbias(Sqv, Skvv, is_causal)
    return q, k, v, mbias, Bv, Nv, Sqv, Skvv, Dv, nsplitv, float(scalev), dtype


def build_codegen_inputs():
    # partial kernel's codegen inputs (combine is built separately by run_codegen on demand)
    import torch
    q, k, v, mbias, B, N, Sq, Skv, D, nsplit, scale, dt = _make_case(1, 3, 2, 384, 64, 2, 0.125, is_causal=True, seed=0)
    po = torch.zeros(B * N * nsplit * Sq, D, dtype=torch.float32)
    pm = torch.zeros(B * N * nsplit * Sq, 8, dtype=torch.float32)
    pl = torch.zeros(B * N * nsplit * Sq, 8, dtype=torch.float32)
    return q, k, v, mbias, po, pm, pl, B, N, Sq, Skv, D, scale, nsplit


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


def _run_case(name, case, rtol=2e-2, atol=2e-2):
    import torch
    from easyasc.simulator import SimulatorConfig
    q, k, v, mbias, B, N, Sq, Skv, D, nsplit, scale, dt = case
    po = torch.zeros(B * N * nsplit * Sq, D, dtype=torch.float32)
    pm = torch.zeros(B * N * nsplit * Sq, 8, dtype=torch.float32)
    pl = torch.zeros(B * N * nsplit * Sq, 8, dtype=torch.float32)
    out = torch.zeros(B * N * Sq, D, dtype=dt)
    cfg = SimulatorConfig(core_count=1, execution_timeout_s=1200.0)
    flash_attn_decode_partial_kernel._simulator_config = cfg
    flash_attn_decode_combine_kernel._simulator_config = cfg
    # kernel 1: partials
    po, pm, pl = OpExec(flash_attn_decode_partial_kernel, simulator=True)(
        q, k, v, mbias, po, pm, pl, B, N, Sq, Skv, D, scale, nsplit,
        shape_bindings={0: [None, 4], 1: [None, 4], 2: [None, 4], 3: [2, 3], 4: [None, 4]})
    # kernel 2: combine
    out = OpExec(flash_attn_decode_combine_kernel, simulator=True)(
        po, pm, pl, out, B, N, Sq, D, nsplit,
        shape_bindings={0: [None, 3], 3: [None, 3]})
    out_k = out.float().reshape(B, N, Sq, D)
    ref = _torch_ref(q, k, v, mbias, B, N, Sq, Skv, D, scale)
    mad = torch.abs(out_k - ref).max().item()
    print(f"{name}: B{B}N{N}Sq{Sq}Skv{Skv}D{D} nsplit={nsplit} max_abs_diff={mad:.6e}", flush=True)
    torch.testing.assert_close(out_k, ref, rtol=rtol, atol=atol)
    return mad


def main():
    import torch
    # small BH, long KV, split 4 ways (the case split-KV exists for): B=1,N=3 -> BH=3, n=4
    _run_case("decode_sq1_d128_split4", _make_case(1, 3, 1, 512, 128, 4, 0.0884, is_causal=False, seed=0))
    # uneven split (Skv=384, n=4 -> 96/split) + D=256
    _run_case("decode_sq1_d256_split4", _make_case(1, 3, 1, 384, 256, 4, 0.0625, is_causal=False, seed=1))
    # MTP Sq=2 causal, split 2
    _run_case("mtp_sq2_d128_split2_causal", _make_case(1, 3, 2, 512, 128, 2, 0.0884, is_causal=True, seed=2))
    # bf16
    _run_case("decode_sq1_d128_split4_bf16",
              _make_case(1, 3, 1, 512, 128, 4, 0.0884, is_causal=False, dtype=torch.bfloat16, seed=3),
              rtol=4e-2, atol=4e-2)
    print("ALL SIMULATOR CHECKS PASSED", flush=True)

if __name__ == "__main__":
    main()
