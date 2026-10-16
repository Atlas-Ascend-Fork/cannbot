# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Flash-attention DECODE / incremental (IFA-style) — A2 cube kernel.

# Pairs with input_example/mha (cann-bench level4 MHA, decode + MTP cases).

WHY A SEPARATE TEMPLATE FROM flash_attn_full.py (prefill):
  Prefill (flash_attn_full) tiles the LONG query length S1 into TILE_M=128 rows and
  parallelises over BH * ceil(S1/128) query tiles; QK/PV are square GEMMs.
  DECODE has S1 = Sq tiny (1 for autoregressive decode, 2 for MTP) against a LONG KV
  cache S2 = Skv. The whole M-tiling structure of prefill collapses:

    1. M = Sq (1 or 2) -> ONE tiny query tile, padded to MH=16. NO `tiles_m` loop.
       (Cube wants 16-alignment; an unaligned M=1/2 tile gives nan, so pad to MH and
        keep the valid rows in the lower QUARTER [0, MH/4) — see MSTEP note below.)
    2. Parallelism is over WORK-ITEMS = (b, n) heads only (each core owns a range of
       B*N heads and streams that head's full KV cache). For cann-bench MHA decode,
       BH = B*N is 32..4096, all >= the 24 cube cores, so plain BH-parallel saturates
       the cores. When BH < #cores with a long KV, use SPLIT-KV / flash-decoding instead:
       see the companion `flash_attn_decode_splitkv.py` (two-kernel pipeline — split Skv
       across cores into partials, then LSE-merge).
    3. QK/PV are GEMV-shaped (M=1..2). Memory-bound on the K/V cache load; the cube is
       under-utilised on M but is still the right datapath (matmul -> L0C) on a2.

WHAT IS REUSED FROM THE DEVICE-VERIFIED SparseFlashAttention cube kernel:
  Every a2 cube quirk is inherited (all sim-verified, several device-verified on 910B2):
  * a2 has NO l0c_to_ub and NO ub_to_l1: every L0C/UB<->L1 hop bounces through a GM
    split_workspace, owned across the cube/vector sub-cores by CvMutex (FIX->MTE2,
    L0C->GM->UB readback) and VcMutex (MTE3->FIX, UB->GM->L1 P publish). bar_all does
    NOT order FIX->MTE2 / MTE3->FIX, so the mutexes are mandatory.
  * Only the FIRST QUARTER of an MH-row matmul tile produces correct PV in this sim
    (rows >= MH/4 -> nan via the transposed V load). MH=16 so valid rows = [0,4);
    Sq <= 2 always fits. Step is implicit (single sub-block, valid_m = Sq).
  * Per-row softmax state collapse: a binary-tree of 2D adds/maxes can only go down to
    8-wide (32-byte vec-alignment floor — sub-8 slices like [4:8]/[1:2] are not aligned
    and raise "src must be 32-byte aligned"). The last 8->1 per-row reduction is a
    `cmax`/`cadd` that emits a [1,MH] row vector; we then `brcb` it back to [MH,8] to
    broadcast. PROBED at MH=16: all rows incl. the odd row 1 are correct to ~1e-8 (the
    [1,MH]-corrupts-odd-rows hazard in the SFA notes was an MH=32 phenomenon; MH=16 is
    clean), so the flash_attn_full [1,MH] running-stat idiom is safe here.

FULL ONLINE SOFTMAX + IN-KERNEL NORMALISE (this template does the real flash math, not
  the bounded-input shortcut):
  * Running per-row max `m`, sum `l` (both [1,MH]) and accumulator `acc` [MH,D] are
    carried across KV tiles. Each tile: m_new = max(m, rowmax(tile)); corr = exp(m-m_new);
    l = l*corr + rowsum(exp(s-m_new)); acc = acc*corr + P@V. This is numerically safe for
    ANY score range (the max-scoring key always contributes exp(0)=1, so l>=1 — no all-
    -masked-row 0/0 for the cann-bench shapes, where S<=S_kv guarantees >=1 live key).
  * Normalisation is done IN-KERNEL: `div(acc, l)` broadcast via brcb([MH,8],[1,MH]),
    exactly as flash_attn_full. (The SFA "rec/div corrupts rows -> divide in plugin"
    workaround was MH=32-specific; PROBED clean at MH=16, so this kernel returns the
    final normalised output directly — single output, no plugin post-divide.)
  * The corr-rescale of `acc` and the final `div` broadcast a [MH,8] block across D in
    fixed 64-wide chunks (a [MH,8] divisor block-broadcasts over 64 dst cols per op).

CAUSAL / MTP MASK (cases 16-18, Sq=2, is_causal):
  The kernel stays branch-free: it takes an ADDITIVE mask input `mbias` [Sq, Skv]
  (0 or -1e30), broadcast across all (b,n) work-items (causal mask is head-independent).
  The ModelNew plugin builds it from is_causal (right-bottom-aligned: position [i,j] is
  masked iff j > i + (Skv - Sq)). For Sq=1 decode (is_causal=False) mbias is all zeros.

DTYPE: one kernel serves fp16 AND bf16 — L1/P/out buffers are allocated with the input
  dtype `q.dtype` (matmul accepts both, accumulating fp32 in L0C); softmax math is fp32
  in UB. The only dtype-dependent line is the GM<->L1 buffer dtype and the final cast.

LAYOUT: kernel consumes BNSD-flattened GM (q [B*N*Sq, D], k/v [B*N*Skv, D]); the plugin
  permutes cann-bench's BSND <-> BNSD and writes the output permute back.

VERIFICATION: full online softmax + in-kernel normalise; single output (final attention
  result — no plugin post-divide). 5/5 sim self-checks AND 910B2 DEVICE-verified (codegen
  -> a2 kernel compile -> on-device aclnn run), device max_abs_diff matching sim to the
  digit (fp16 ~3e-5, bf16 ~2.2e-4); multi-core BH-split confirmed.

PERF (910B2, 100-launch avg, vs CANN FusedInferAttentionScore t_hw on the 9 cann-bench
  MHA decode/MTP cases): geomean ~4.4x slower than FIA (best 2.7x on the D256 cases,
  worst 6.7x on case-10 B1 where FIA is hyper-tuned for the tiny shape). Two safe device-
  measured wins are baked in vs the first cut (~15% faster): (1) whole-tile P GM->L1 load
  (1 DMA, not MH per-row — valid at MH=16); (2) QK matmul folded into the readback
  auto_sync (drops a per-tile bar_all; matmul->FIX-store is fenced within the block).
  MEASURED-NEGATIVE, deliberately NOT done: folding the PV block into the QK auto_sync +
  early V-load — it DEFEATS the cube/vector ping-pong the separate Cv/Vc-mutex blocks
  give, and was slower on device. Remaining ~4.4x gap is structural: (a) cube M is
  under-used (MH=16 tile, only Sq=1..2 valid query rows — inherent to MHA decode: each
  head has its own K/V so you cannot pack heads into M); (b) 3 mandatory GM bounces/tile
  (L0C<->GM<->UB x2 + UB->GM->L1; a2 has no L0C<->UB). Closing it further needs a
  flash_attn_full-style multi-stage software pipeline (overlap tile i+1 QK with tile i PV)
  — a large rewrite left as future work.
  Device-run recipe (OpExec JIT path): the codegen-emitted `tensorutils.h` carries
  a5-only fp8/PaddingMode identifiers that DON'T compile on CANN 8.5.0 a2, so the
  AICore .o silently fails to build (empty binary/, CPack "binary/config not found").
  Apply `output/sparse_flash_attention/patch_tensorutils.py` to the codegen template
  (or per-build copy) FIRST; then `OpExec(kernel, simulator=False)(... .npu() tensors)`
  builds + launches on device. Point both torch and the (hardcoded deviceId=0) test
  harness at an idle chip with `ASCEND_RT_VISIBLE_DEVICES=<phys>` + device 0.
"""
import os
import builtins

from easyasc.a2 import *

# ---- a2 24-core coverage (910B2/B3); default device_type='b3' caps block dim at 20. ----
from easyasc import globvars as _gv
_gv.device_type = 'b2'
_gv.core_num = 24

# Mask / running-max-init sentinel. NOT -1e30: this simulator's vec `exp` OVERFLOWS to
# +inf for an argument as extreme as -1e30 (the range-reduction blows up), and the
# online softmax evaluates exp(m_init - m_new) = exp(-SENTINEL) on the first KV tile —
# inf there gives acc*inf = nan. -3e4 is far below any real score (|q.k*scale| <= sqrt(D)
# <= 16), so it still fully suppresses masked slots (exp(-3e4 - max) underflows to 0),
# AND an all-masked *later* tile is safe (m_new = max(m_run, -3e4) = m_run -> corr =
# exp(0) = 1). (A genuinely all-masked *row* — none in these cann-bench shapes since
# S<=S_kv guarantees >=1 live key — would still need explicit 0-weight handling.)
NEG_LARGE = -3.0e4
TINY = 1.0e-30
# This simulator's vec `exp` OVERFLOWS to +inf for a large-negative argument (it does not
# saturate to 0). The online softmax feeds it big negatives: tile-0 corr = exp(m_init -
# m_new) and masked p = exp(score_masked - max) are both ~ -3e4. So CLAMP every exp arg to
# >= EXP_FLOOR before exp; exp(-80)=1.8e-35 ~ 0 (negligible, fp32-normal), and any arg
# above -80 is untouched, so there is no accuracy loss on real (un-masked) scores.
EXP_FLOOR = -80.0

# MH: padded query-token tile (M dim of the QK matmul). Multiple of 8 (brcb repeat=MH//8).
# Valid query rows must live in [0, MH/4) (the only quarter whose PV is correct in this
# sim); Sq in {1,2} for decode/MTP always fits.
MH = int(os.environ.get("FAD_MH", "16"))
MQUARTER = MH // 4
TILE_N = 128            # KV-cache tile (matmul N for QK, K for PV); L0 fractal width
HALF_N = TILE_N // 2
DK_CAP = int(os.environ.get("FAD_DK_CAP", "256"))   # max head dim D (cann-bench: 64/128/256)
K_SPLIT = 128
N_SPLIT = 128


# DK_CAP columns are normalised/rescaled in fixed 64-wide chunks. The chunk offsets are
# Python CONSTANTS (not a runtime `range` loop): a slice like `acc[dc*HALF_N:...]` with a
# runtime loop Var `dc` trips codegen (Var-arithmetic in a slice -> dc.value=0, so only
# chunk 0 is emitted and cols 64: stay unprocessed). `builtins.range` unrolls at trace
# time so every offset is a compile-time int. DK_CAP must be a multiple of HALF_N.
DCHUNK_OFFS = [i * HALF_N for i in builtins.range(DK_CAP // HALF_N)]


@kernel()
def flash_attn_decode_kernel(
    q: GMTensor,            # [B*N*Sq, D]    fp16/bf16  (BNSD-flattened)
    k: GMTensor,            # [B*N*Skv, D]   fp16/bf16
    v: GMTensor,            # [B*N*Skv, D]   fp16/bf16
    mbias: GMTensor,        # [Sq, Skv]      fp32  (0 / -1e30 causal bias, head-independent)
    out: GMTensor,          # [B*N*Sq, D]    fp16/bf16  (FINAL normalised attention output)
    B: Var, N: Var, Sq: Var, Skv: Var, D: Var, scale: Var,
):
    qdt = q.dtype   # one kernel for fp16 and bf16: L1/P/out follow the input dtype

    # ---- GM workspace bridges (a2 has no l0c_to_ub / ub_to_l1) ----
    score_ws = split_workspace(DT.float, [GetCubeNum(), MH, TILE_N], name="score_ws")
    p_ws = split_workspace(qdt, [GetCubeNum(), MH, TILE_N], name="p_ws")
    pv_ws = split_workspace(DT.float, [GetCubeNum(), MH, DK_CAP], name="pv_ws")

    # ---- L1 staging (cube operands; full D stages in L1 for D<=256, no Dk-tiling) ----
    l1q = DBuff(qdt, [MH, DK_CAP], Position.L1)
    l1k = DBuff(qdt, [TILE_N, DK_CAP], Position.L1)
    l1p = DBuff(qdt, [MH, TILE_N], Position.L1)
    l1v = DBuff(qdt, [TILE_N, DK_CAP], Position.L1)
    l0c_qk = Tensor(DT.float, [MH, TILE_N], Position.L0C)
    l0c_pv = Tensor(DT.float, [MH, DK_CAP], Position.L0C)
    l1cnt = Var(0)

    # ---- cross-side ownership (cube <-> vector) ----
    qk_mutex = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)
    pv_mutex = CvMutex(2, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.MTE2)
    p_mutex = VcMutex(1, src_end_pipe=Pipe.MTE3, dst_end_pipe=Pipe.FIX)

    # ---- softmax scratch (UB, fp32). CRITICAL shape rules (all PROBED on this sim):
    #   * `exp` on a NARROW [MH,8] (one 32-byte block) tensor returns +inf — BROKEN. exp
    #     on [MH,>=16] / [1,MH] is correct. So the running max/corr/denom that get exp'd or
    #     arithmetic'd are kept [MH,HALF_N] (64-wide, value replicated across all 64 cols).
    #   * [1,MH] row-vector ARITHMETIC (sub/vmax/mul) is also unreliable at MH=16. So [1,MH]
    #     is used ONLY as the transient cmax/cadd output; brcb -> [MH,8] -> block-broadcast
    #     into the [MH,HALF_N] running state via the next binary op.
    SCAL = HALF_N   # 64-wide replicated per-row scalars (exp-safe, arithmetic-safe)
    scores = Tensor(DT.float, [MH, TILE_N], Position.UB)
    redm = Tensor(DT.float, [MH, HALF_N], Position.UB)     # 128->64 reduction scratch
    mbias_t = Tensor(DT.float, [MH, TILE_N], Position.UB)  # per-ROW additive mask tile
    p_ub = Tensor(qdt, [MH, TILE_N], Position.UB)
    pv_ub = Tensor(DT.float, [MH, DK_CAP], Position.UB)
    acc = Tensor(DT.float, [MH, DK_CAP], Position.UB)      # running (rescaled) output
    red_s = Tensor(DT.float, [1, MH], Position.UB)         # transient cmax/cadd output
    tmax8 = Tensor(DT.float, [MH, 8], Position.UB)         # brcb output (block-broadcast src)
    tsum8 = Tensor(DT.float, [MH, 8], Position.UB)
    m_run = Tensor(DT.float, [MH, SCAL], Position.UB)      # running per-row max (replicated)
    m_new = Tensor(DT.float, [MH, SCAL], Position.UB)
    corr = Tensor(DT.float, [MH, SCAL], Position.UB)       # exp(m_old - m_new)
    l_run = Tensor(DT.float, [MH, SCAL], Position.UB)      # running denom (replicated)
    out_low = Tensor(qdt, [MH, DK_CAP], Position.UB)

    total_heads = Var(B * N)
    heads_per_core = CeilDiv(total_heads, GetCubeNum())
    h_begin = Var(heads_per_core * GetCubeIdx())
    h_end = Min(h_begin + heads_per_core, total_heads)

    n_ktiles = CeilDiv(Skv, TILE_N)
    c = GetCubeIdx()

    for hg in range(h_begin, h_end):
        qbase = Var(hg * Sq)        # this head's query rows  [qbase, qbase+Sq)
        kvbase = Var(hg * Skv)      # this head's KV rows
        valid_m = Sq                # <= MQUARTER, lower-quarter rows only

        dup(m_run, NEG_LARGE)       # running max starts at the sentinel
        dup(l_run, 0.0)
        dup(acc, 0.0)
        bar_all()

        for kt in range(0, n_ktiles):
            off = Var(kt * TILE_N)
            tn = Min(TILE_N, Skv - off)     # valid KV slots this tile (tail < TILE_N)

            # ---- additive causal/MTP bias for this KV tile; pad cols [tn:TILE_N] -> -inf so
            #      masked/padding slots get exp(...) = 0. The dup(vec)->load(MTE2) WAR on
            #      mbias_t needs this bar_all (autosync does not fence V->MTE2 WAW). (Folding
            #      the load into the QK auto_sync to drop this barrier was MEASURED net-negative
            #      across the high-BH cases and would assume Skv%TILE_N==0 — kept as is.) ----
            dup(mbias_t, NEG_LARGE)
            bar_all()
            mbias_t[0:valid_m, 0:tn] <<= mbias[0:valid_m, off:off + tn]

            # ============ QK^T matmul + readback + ONLINE softmax (one auto_sync) =========
            # Contiguous K tile load (dense flash, unlike SFA's per-row gather). Full D<=256
            # stages in L1 in one DMA; matmul splitk handles k>128 internally. matmul->L0C-store
            # ordering is handled inside the auto_sync (no bar_all between matmul and FIX store).
            with auto_sync():
                set_constant_to_l1(l1q[0], 0.0)
                set_constant_to_l1(l1k[l1cnt], 0.0)
                l1q[0][0:valid_m, 0:D] <<= q[qbase:qbase + valid_m, 0:D]
                l1k[l1cnt][0:tn, 0:D] <<= k[kvbase + off:kvbase + off + tn, 0:D]
                matmul(l0c_qk, l1q[0], l1k[l1cnt],
                       splitk=K_SPLIT, m=MH, n=TILE_N, k=D, is_init=True)
                qk_mutex.lock()
                score_ws[c, 0:MH, 0:TILE_N] <<= l0c_qk
                qk_mutex.ready()
                qk_mutex.wait()
                scores <<= score_ws[c, 0:MH, 0:TILE_N]

                muls(scores, scores, scale)
                add(scores, scores, mbias_t)        # per-row additive mask BEFORE the max

                # --- tile per-row max: 128->64 vmax, cmax 64->[1,MH] (sub-8 slices are not
                #     32B-aligned, so the last reduction must be cmax), then brcb to [MH,8] ---
                vmax(redm[0:MH, 0:HALF_N], scores[0:MH, 0:HALF_N], scores[0:MH, HALF_N:TILE_N])
                cmax(red_s[0:1, 0:MH], redm[0:MH, 0:HALF_N])
                brcb(tmax8, red_s[0:1, 0:MH], repeat=MH // 8, dst_blk_stride=1, dst_rep_stride=8)

                # --- online max update in [MH,SCAL] wide form (exp-safe). tmax8[MH,8]
                #     block-broadcasts into the 64-wide running state. ---
                vmax(m_new, m_run, tmax8)           # m_new = max(m_run, tile_max)  (8->64 bcast)
                sub(corr, m_run, m_new)             # m_old - m_new <= 0
                vmaxs(corr, corr, EXP_FLOOR)        # clamp (tile-0 init gives -3e4) so exp is safe
                exp(corr, corr)                     # WIDE [MH,64] exp -> correct (narrow [MH,8] -> inf)
                vmax(m_run, m_run, tmax8)           # m_run <- m_new

                # --- p = exp(scores - m_new); m_new is 64-wide so each score half subtracts
                #     element-wise (cols replicate the per-row max) ---
                sub(scores[0:MH, 0:HALF_N], scores[0:MH, 0:HALF_N], m_new[0:MH, 0:HALF_N])
                sub(scores[0:MH, HALF_N:TILE_N], scores[0:MH, HALF_N:TILE_N], m_new[0:MH, 0:HALF_N])
                vmaxs(scores, scores, EXP_FLOOR)    # clamp masked/far cols so exp is safe
                exp(scores, scores)

                # --- tile rowsum -> [1,MH] -> [MH,8]; online denom l = l*corr + tile_sum ---
                add(redm[0:MH, 0:HALF_N], scores[0:MH, 0:HALF_N], scores[0:MH, HALF_N:TILE_N])
                cadd(red_s[0:1, 0:MH], redm[0:MH, 0:HALF_N], repeat=MH, dst_rep_stride=1)
                brcb(tsum8, red_s[0:1, 0:MH], repeat=MH // 8, dst_blk_stride=1, dst_rep_stride=8)
                mul(l_run, l_run, corr)             # [MH,64] x [MH,64]
                add(l_run, l_run, tsum8)            # tile_sum8 block-broadcasts into l_run

                cast(p_ub, scores)                  # probs -> input dtype for PV matmul
                qk_mutex.free()
                p_mutex.lock()
                p_ws[c, 0:MH, 0:TILE_N] <<= p_ub[0:MH, 0:TILE_N]
                p_mutex.ready()

            # ============ P@V matmul + ONLINE rescale (separate auto_sync so the cube/vec
            # sub-cores pipeline via the Cv/Vc mutexes; merging into the QK block defeats the
            # ping-pong and is SLOWER on device — measured). =========
            with auto_sync():
                set_constant_to_l1(l1v[l1cnt], 0.0)
                l1v[l1cnt][0:tn, 0:D] <<= v[kvbase + off:kvbase + off + tn, 0:D]
                p_mutex.wait()
                # whole-tile GM->L1 nd2nz of P (1 DMA). The SFA per-row workaround was for
                # MH=32 where rows >=16 corrupt; at MH=16 the whole [MH,TILE_N] tile loads fine.
                l1p[l1cnt][0:MH, 0:TILE_N] <<= p_ws[c, 0:MH, 0:TILE_N]
                matmul(l0c_pv, l1p[l1cnt], l1v[l1cnt].T,
                       splitn=N_SPLIT, m=MH, n=D, k=TILE_N, is_init=True)
                p_mutex.free()

                pv_mutex.lock()
                pv_ws[c, 0:MH, 0:D] <<= l0c_pv
                pv_mutex.ready()
                pv_mutex.wait()
                pv_ub[0:MH, 0:D] <<= pv_ws[c, 0:MH, 0:D]

                # online output rescale: acc = acc*corr + P@V  (rescale by exp(m_old-m_new)
                # then add the new tile's PV). [D:DK_CAP] stays 0 (acc dup'd, corr keeps 0).
                for od in DCHUNK_OFFS:   # trace-time unroll (constant offsets)
                    mul(acc[0:MH, od:od + HALF_N], acc[0:MH, od:od + HALF_N], corr[0:MH, 0:HALF_N])
                add(acc[0:MH, 0:D], acc[0:MH, 0:D], pv_ub[0:MH, 0:D])
                pv_mutex.free()

            l1cnt += 1

        # ---- finalize: IN-KERNEL normalise out = acc / l_run (l_run is [MH,8] replicated,
        #      block-broadcast over each 64-col chunk), then write the final output ----
        with auto_sync():
            for od in DCHUNK_OFFS:   # trace-time unroll (constant offsets)
                div(acc[0:MH, od:od + HALF_N], acc[0:MH, od:od + HALF_N], l_run[0:MH, 0:HALF_N])
            cast(out_low[0:MH, 0:D], acc[0:MH, 0:D])
        bar_all()
        for hr in range(0, valid_m):
            orow = Var(qbase + hr)
            out[orow:orow + 1, 0:D] <<= out_low[hr:hr + 1, 0:D]   # final normalised output
        bar_all()

    return out


# ---------------------------------------------------------------------------
# build_codegen_inputs() + simulator self-check
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
    torch.manual_seed(seed)
    q = (torch.rand(Bv * Nv * Sqv, Dv) * 2 - 1).to(dtype)
    k = (torch.rand(Bv * Nv * Skvv, Dv) * 2 - 1).to(dtype)
    v = (torch.rand(Bv * Nv * Skvv, Dv) * 2 - 1).to(dtype)
    mbias = _causal_mbias(Sqv, Skvv, is_causal)
    out = torch.zeros(Bv * Nv * Sqv, Dv, dtype=dtype)
    return q, k, v, mbias, out, Bv, Nv, Sqv, Skvv, Dv, float(scalev)


def build_codegen_inputs():
    # ALL-DISTINCT scalar values so codegen's by-value dim inference is unambiguous.
    # Decode-ish GQA-free shape: B=1,N=3,Sq=2,Skv=128,D=64.
    return _make_case(1, 3, 2, 384, 64, 0.125, is_causal=True, seed=0)


def _torch_ref(q, k, v, mbias, B, N, Sq, Skv, D, scale):
    import torch
    py_range = builtins.range
    qf = q.float().reshape(B, N, Sq, D)
    kf = k.float().reshape(B, N, Skv, D)
    vf = v.float().reshape(B, N, Skv, D)
    mb = mbias.float()
    out = torch.zeros(B, N, Sq, D, dtype=torch.float32)
    for b in py_range(B):
        for n in py_range(N):
            sc = (qf[b, n] @ kf[b, n].transpose(-2, -1)) * scale + mb   # [Sq,Skv]
            sc = sc - sc.max(dim=-1, keepdim=True).values
            p = torch.exp(sc)
            out[b, n] = (p @ vf[b, n]) / (p.sum(dim=-1, keepdim=True) + TINY)
    return out


def _run_case(name, args, rtol=2e-2, atol=2e-2):
    import torch
    from easyasc.simulator import SimulatorConfig
    q, k, v, mbias, out, B, N, Sq, Skv, D, scale = args
    saved = getattr(flash_attn_decode_kernel, "_simulator_config", None)
    flash_attn_decode_kernel._simulator_config = SimulatorConfig(
        core_count=1, execution_timeout_s=1200.0,
    )
    try:
        res = OpExec(flash_attn_decode_kernel, simulator=True)(
            q, k, v, mbias, out, B, N, Sq, Skv, D, scale,
            shape_bindings={
                # scalar arg order: B=0,N=1,Sq=2,Skv=3,D=4,scale=5
                0: [None, 4],   # q     dim1 = D
                1: [None, 4],   # k     dim1 = D
                2: [None, 4],   # v     dim1 = D
                3: [2, 3],      # mbias dims = (Sq, Skv)
                4: [None, 4],   # out   dim1 = D
            },
        )
    finally:
        if saved is None:
            try:
                delattr(flash_attn_decode_kernel, "_simulator_config")
            except AttributeError:
                pass
        else:
            flash_attn_decode_kernel._simulator_config = saved
    out_k = res.float().reshape(B, N, Sq, D)   # kernel returns the final normalised output
    ref = _torch_ref(q, k, v, mbias, B, N, Sq, Skv, D, scale)
    mad = torch.abs(out_k - ref).max().item()
    print(f"{name}: shape(B={B},N={N},Sq={Sq},Skv={Skv},D={D}) max_abs_diff={mad:.6e}",
          flush=True)
    torch.testing.assert_close(out_k, ref, rtol=rtol, atol=atol)
    return mad


def main():
    import torch
    # decode Sq=1, D=128, multi-KV-tile, non-causal (cann-bench cases 10-14 shape family)
    _run_case("decode_sq1_d128", _make_case(2, 3, 1, 512, 128, 0.0884, is_causal=False, seed=0))
    # decode Sq=1, D=256 (cases 15 family) — exercises the D=256 path
    _run_case("decode_sq1_d256", _make_case(2, 3, 1, 384, 256, 0.0625, is_causal=False, seed=1))
    # MTP Sq=2, D=128, causal (cases 16-17 family) — exercises the additive causal mask
    _run_case("mtp_sq2_d128_causal", _make_case(2, 3, 2, 512, 128, 0.0884, is_causal=True, seed=2))
    # MTP Sq=2, D=256, causal (case 18 family)
    _run_case("mtp_sq2_d256_causal", _make_case(2, 3, 2, 384, 256, 0.0625, is_causal=True, seed=3))
    # bf16 instance (cases 12/17) — same kernel, dtype follows q.dtype
    _run_case("decode_sq1_d128_bf16",
              _make_case(2, 3, 1, 512, 128, 0.0884, is_causal=False, dtype=torch.bfloat16, seed=4),
              rtol=4e-2, atol=4e-2)
    print("ALL SIMULATOR CHECKS PASSED", flush=True)

if __name__ == "__main__":
    main()
