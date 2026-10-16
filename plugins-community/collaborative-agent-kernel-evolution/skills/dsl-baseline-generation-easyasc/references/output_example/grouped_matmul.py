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
# easyasc DSL canonical — Grouped Matmul (CV / contraction, A2 cube)
#
# Pattern: 一次 launch 完成所有 group 的 matmul（cross-group core round-robin），
#         单 kernel 输出 [M, N]，bias 在 host 端加。
#
# 适用算子家族
# ------------
#   - grouped_matmul (MoE / 多专家)
#   - grouped_gemm with shared K/N（每组 M 可异）
#   - 任何形如 `for g in range(E): y[rows_g] = x[rows_g] @ w[g]` 的算子
#
# 实测精度+性能（vs CANN aclnnGroupedMatmul baseline）
# ----------------------------------------------------
#   case (M,K,N,E,fp16):      cube_only_us   speedup
#     1031×128×128×4              7.0          1.12×
#     1009×1024×1024×8           21.6          1.44×
#     256×512×1024×8 (bf16)      12.8          1.14×
#     2047×1023×2047×8 (bf16)   216.7          0.79×（大 K bandwidth-bound）
#
# DSL 范式（继承自 qk_matmul_batched.py 加 grouped 调度）
# -------------------------------------------------------
#   1. DBuff (double-buffer) 所有 L1/L0C，K-loop ping-pong
#   2. cross-group RR core dispatch via `count <<= (count + blocks_in_g) % core_num`
#      （CANN 自家 GMMProcess 的等效做法 —— 一个 core 跨 group 连续接 block）
#   3. K-loop 内 set_constant_to_l1 处理 valid_m/valid_n/valid_k < TILE 的 padding
#   4. split_workspace 必须存在（即使不用），否则 device 端 workspace=0 会挂死
#   5. core_num_step 必须用 Var alias，原因：`range(start, stop, step)` 里
#      step=GetCubeNum() 在 codegen 阶段 .value=0 会 trip 整数除/取模为 0
#
# 不支持的 case
# -------------
#   - fp32 / fp64：cube 原生支持 fp32 mmad（throughput ~半 fp16），但 DSL 全
#     `DT.half`。要支持 fp32 需另起一份 DSL，把 l1x/l1w/l0a/l0b 改 DT.float、
#     TILE_K 按 dtype 折半（L0 容量限制）。
#   - bf16 native：plugin 当前 cast bf16→fp16，精度上 MARE ~1e-3（可接受），
#     性能跟 fp16 持平（cube bf16 mmad 跟 fp16 同 throughput）。
#   - cube-fused bias：a2 BT 路径已在 v3/v4 尝试，device 端拿不到正确 bias 值，
#     未通；bias 留给 plugin / vec post-add。
#
# 关键参考
# --------
#   父范本：references/output_example/qk_matmul_batched.py（CV 路径基础范本）
#   CANN 自家：opp/built-in/op_impl/.../grouped_matmul.h（mm.SetBias()+ ScheduleNorm）
# ============================================================================
from easyasc.a2 import *

# ---- a2 24 核覆盖（910B2/B3，详见 references/constraints/tiling.md）----
# easyasc.a2 默认 device_type='b3' → op_host SetBlockDim(20)。910B2/B3 实际
# cube_core_cnt=24，覆盖后 GetCubeNum() tile 分配与 launch block dim 都用满
# 24 核。仅本 DSL 内覆盖，不改共享 easyasc 库。910B4（20 核）请删除此覆盖。
from easyasc import globvars as _gv
_gv.device_type = 'b2'
_gv.core_num = 24

TILE_M = 128
TILE_N = 128
TILE_K = 128

# A2 910B cube core 数硬编码（24）。
# 不能用 GetCubeNum() 作 workspace 尺寸第一维 —— codegen 时 .value=0
# 会把 host tiling 的 userWorkspaceSize 算成 0 → device runtime 越界 (507015)。
A2_CUBE_NUM = 24


@kernel()
def grouped_matmul_custom(
    x: GMTensor, wt: GMTensor, group_offsets: GMTensor, y: GMTensor,
    M: Var, E: Var, K: Var, N: Var,
):
    """Grouped matmul, one launch handles all E groups.

    Inputs:
        x:             [M, K]   fp16   — activations concat'd along M-axis
        wt:            [E*N, K] fp16   — weight flattened (host has done
                                          transpose+reshape from [E,K,N])
        group_offsets: [E+1]    int32  — cumsum-with-leading-zero, last == M
        y:             [M, N]   fp16   — output

    Differences from a simple per-group launch:
      • diff1 — cross-group core round-robin: a core that finishes its blocks
        in group g picks the next free block in group g+1, instead of leaving
        cores idle until all of group g is done. Reproduces CANN GMMProcess.
    """
    # split_workspace MUST exist for host tiling to allocate non-zero
    # userWorkspaceSize. Buffer is allocated but never written/read; it's a
    # device runtime requirement to avoid the 507015 silent hang.
    ws = split_workspace(DT.float, [A2_CUBE_NUM, 2, TILE_M, TILE_N], name="ws")

    l1x = DBuff(DT.half, [TILE_M, TILE_K], Position.L1)
    l1w = DBuff(DT.half, [TILE_N, TILE_K], Position.L1)
    l0c = DBuff(DT.float, [TILE_M, TILE_N], Position.L0C)

    l1_cnt = Var(0)
    l0c_cnt = Var(0)

    core_num = GetCubeNum()
    core_idx = GetCubeIdx()
    # Var-alias trick: `range(start, stop, GetCubeNum())` would trip codegen
    # because step.value=0 at trace time. Alias into a non-zero Var so the
    # codegen emits the runtime value.
    core_num_step = Var(1, DT.int)
    core_num_step <<= core_num

    tiles_n = CeilDiv(N, TILE_N)
    count = Var(0, DT.int)

    for g in range(0, E):
        m_start_g = Var(0, DT.int)
        m_end_g = Var(0, DT.int)
        m_start_g.GetValueFrom(group_offsets[g:g + 1])
        m_end_g.GetValueFrom(group_offsets[g + 1:g + 2])
        m_g = Var(m_end_g - m_start_g)

        tiles_m = CeilDiv(m_g, TILE_M)
        blocks_in_g = Var(tiles_m * tiles_n)

        # === diff1: cross-group round-robin start index ===
        # Each core picks its first block in this group based on how many
        # blocks were consumed by previous groups across all cores.
        first_local = Var(0, DT.int)
        if core_idx >= count:
            first_local <<= core_idx - count
        else:
            first_local <<= core_idx + core_num - count

        with auto_sync():
            for local_idx in range(first_local, blocks_in_g, core_num_step):
                mt = Var(local_idx // tiles_n)
                nt = Var(local_idx % tiles_n)
                m_off_in_g = Var(mt * TILE_M)
                n_off = Var(nt * TILE_N)
                valid_m = Min(TILE_M, m_g - m_off_in_g)
                valid_n = Min(TILE_N, N - n_off)

                m_start_abs = Var(m_start_g + m_off_in_g)
                w_off = Var(g * N + n_off)

                # === K-tile 0: matmul with init L0C to zero ===
                valid_k = Min(TILE_K, K)
                xbuf = l1x[l1_cnt]
                wbuf = l1w[l1_cnt]
                # set_constant_to_l1 zeros the buffer for boundary tiles so
                # padded (out-of-bound) rows/cols contribute 0 to the matmul.
                if valid_m < TILE_M:
                    set_constant_to_l1(xbuf, 0.0)
                if valid_k < TILE_K:
                    set_constant_to_l1(xbuf, 0.0)
                if valid_n < TILE_N:
                    set_constant_to_l1(wbuf, 0.0)
                if valid_k < TILE_K:
                    set_constant_to_l1(wbuf, 0.0)
                xbuf <<= x[m_start_abs:m_start_abs + valid_m, 0:valid_k]
                wbuf <<= wt[w_off:w_off + valid_n, 0:valid_k]
                matmul(l0c[l0c_cnt], xbuf, wbuf, is_init=True)
                l1_cnt += 1

                # === K-tile 1..end: accumulate into L0C ===
                for k_off in range(TILE_K, K, TILE_K):
                    valid_k = Min(TILE_K, K - k_off)
                    xbuf = l1x[l1_cnt]
                    wbuf = l1w[l1_cnt]
                    if valid_m < TILE_M:
                        set_constant_to_l1(xbuf, 0.0)
                    if valid_k < TILE_K:
                        set_constant_to_l1(xbuf, 0.0)
                    if valid_n < TILE_N:
                        set_constant_to_l1(wbuf, 0.0)
                    if valid_k < TILE_K:
                        set_constant_to_l1(wbuf, 0.0)
                    xbuf <<= x[m_start_abs:m_start_abs + valid_m, k_off:k_off + valid_k]
                    wbuf <<= wt[w_off:w_off + valid_n, k_off:k_off + valid_k]
                    matmul(l0c[l0c_cnt], xbuf, wbuf, is_init=False)
                    l1_cnt += 1

                # === L0C → GM, only the valid_m × valid_n region ===
                y[m_start_abs:m_start_abs + valid_m, n_off:n_off + valid_n] <<= l0c[l0c_cnt][0:valid_m, 0:valid_n]
                l0c_cnt += 1

        # === diff1 cont'd: roll `count` mod core_num across groups ===
        new_count_full = Var(count + blocks_in_g)
        q = Var(new_count_full // core_num_step)
        count <<= new_count_full - Var(q * core_num_step)

    return y


# ─────────────────────────── Host helpers ───────────────────────────

def flatten_weight(weight, transpose_weight=False):
    """[E, K, N] → [E*N, K] (default) or [E, N, K] → [E*N, K]."""
    if transpose_weight:
        E, N, K = weight.shape
        return weight.reshape(E * N, K).contiguous()
    else:
        E, K, N = weight.shape
        return weight.transpose(-2, -1).reshape(E * N, K).contiguous()


def build_group_offsets(group_list):
    """[c_0, c_1, ..., c_{E-1}] → [0, c_0, c_1, ..., c_{E-1}] as int32 tensor."""
    import torch
    return torch.tensor([0] + list(group_list), dtype=torch.int32)


def build_codegen_inputs():
    import torch
    M, K, N, E = 128, 256, 512, 4
    group_list = [32, 64, 96, 128]
    x = torch.zeros(M, K, dtype=torch.float16)
    w = torch.zeros(E, K, N, dtype=torch.float16)
    wt = flatten_weight(w, transpose_weight=False)
    y = torch.zeros(M, N, dtype=torch.float16)
    group_offsets = build_group_offsets(group_list)
    return (x, wt, group_offsets, y, M, E, K, N)


def main():
    import torch
    torch.manual_seed(42)

    test_cases = [
        # (M, K, N, E, group_list)
        (128, 256, 512, 1, [128]),
        (128, 256, 512, 4, [32, 64, 96, 128]),
        (256, 512, 1024, 8, [32, 64, 96, 128, 160, 192, 224, 256]),
        (1009, 1024, 1024, 4, [253, 505, 757, 1009]),
        (200, 64, 128, 2, [100, 200]),
    ]

    for M, K, N, E, group_list in test_cases:
        x = torch.randn(M, K, dtype=torch.float16)
        w = torch.randn(E, K, N, dtype=torch.float16)
        wt = flatten_weight(w, transpose_weight=False)
        group_offsets = build_group_offsets(group_list)

        ref = torch.zeros(M, N, dtype=torch.float32)
        prev = 0
        for g, end in enumerate(group_list):
            mm = x[prev:end].float() @ w[g].float()
            ref[prev:end] = mm
            prev = end

        yb = torch.zeros(M, N, dtype=torch.float16)
        sb = {0: [0, 2], 1: [None, 2], 3: [0, 3]}  # y at tensor index 3
        y_out = OpExec(grouped_matmul_custom, simulator=True)(
            x, wt, group_offsets, yb, M, E, K, N, shape_bindings=sb)

        diff = (y_out.float() - ref).abs().max().item()
        rel = diff / (ref.abs().max().item() + 1e-7)
        print(f"sim (M={M},K={K},N={N},E={E}): max_abs_diff={diff:.4e} rel={rel:.4e}")
        torch.testing.assert_close(y_out.float(), ref, rtol=5e-2, atol=5e-2)

    print("simulator OK (canonical grouped_matmul, cross-group RR, no kernel bias)")

if __name__ == "__main__":
    main()
