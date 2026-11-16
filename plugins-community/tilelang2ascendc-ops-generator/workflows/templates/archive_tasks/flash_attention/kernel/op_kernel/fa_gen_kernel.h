/*
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 * ----------------------------------------------------------------------------------------------------------
 */

// ----------------------------------------------------------------------------------------------------------
// FlashAttention forward - generalized standalone AscendC kernel (MHA, kv_heads == heads).
//
// Origin: tilelang 手写同步设计 design/tile_level/flash_attention.py 的编译产物，
// generalized：dim 运行期 + block_m 按 dim_align 分档 + d_chunks K 累加
// + causal 右下对齐 + 全显式旗语（AUTO_SYNC 关闭）。同步结构（flag 编号 / 顺序）
// 与生成码逐字节一致，禁止改动。
// ----------------------------------------------------------------------------------------------------------
#ifndef FA_GEN_KERNEL_H
#define FA_GEN_KERNEL_H

#include "kernel_common.h"
#include "flash_attention_cube.h"
#include "flash_attention_vec.h"

namespace fa_gen {

struct FaGenStorage {
    AscendC::TBuf<AscendC::TPosition::A1> ascend_l1;
    AscendC::TBuf<AscendC::TPosition::A2> ascend_l0a;
    AscendC::TBuf<AscendC::TPosition::B2> ascend_l0b;
    AscendC::TBuf<AscendC::TPosition::CO1> ascend_l0c;
    AscendC::TBuf<AscendC::TPosition::VECCALC> ascend_ub;
};

struct FaGenUbLayout {
    uint32_t acc_o;
    uint32_t sumexp;
    uint32_t m_i;
    uint32_t alpha_ring;
    uint32_t acc_s_ub;
    uint32_t mask_col;
    uint32_t col_idx;
    uint32_t bound_vec;
    uint32_t tmp;
    uint32_t m_i_2d;
    uint32_t brcb_elems;
    uint32_t brcb;
    uint32_t sumexp_i_ring;
    uint32_t acc_s_half;
    uint32_t acc_o_ub;
    uint32_t base_total;
    uint32_t causal_cmp;
    bool bound_alias;
    uint32_t bound_2d;
    uint32_t after_bound;
    uint32_t acc_o_half;
    uint32_t total;
};

struct FaGenTask {
    int64_t bx;
    int64_t by;
    int64_t bz;
    int64_t q_base;
    int64_t kv_base;
    int64_t ws_s_base;
    int64_t ws_p_base;
    int64_t ws_o_base;
    int64_t q_tail_m;
};

template <typename T>
CATLASS_DEVICE void FaGenInitShape(FaGenContext<T>& ctx, GM_ADDR tiling_handle)
{
    auto tiling_gm = reinterpret_cast<__gm__ FlashAttentionGenTiling*>(tiling_handle);
    ctx.batch = tiling_gm->batch;
    ctx.heads = tiling_gm->heads;
    ctx.q_seq_len = tiling_gm->q_seq_len;
    ctx.kv_seq_len = tiling_gm->kv_seq_len;
    ctx.dim = tiling_gm->dim;
    ctx.sm_scale = tiling_gm->sm_scale;
    ctx.causal = tiling_gm->causal;

    constexpr uint32_t C0 = 32 / sizeof(T); // 16: fp16/bf16, 8: fp32
    ctx.dim_align = (ctx.dim + C0 - 1) / C0 * C0;
    // dim_align > 128 时按 128 整 chunk 取齐
    if (ctx.dim_align > 128) {
        ctx.dim_align = (ctx.dim + 127) / 128 * 128;
    }
    // block_m 按 dim_align 分档（fp32 减半 + dim>128 也 64）
    if constexpr (sizeof(T) == 4) {
        ctx.block_m = (ctx.dim_align <= 128) ? 64 : 32;
    } else if (ctx.dim_align <= 128) {
        ctx.block_m = 128;
    } else {
        ctx.block_m = 64;
    }
    ctx.half_m = ctx.block_m / 2;
    ctx.cube_k = ctx.dim_align < 256 ? ctx.dim_align : 256;
    ctx.d_chunks = (ctx.dim_align + 255) / 256;
    ctx.diff_s = ctx.kv_seq_len - ctx.q_seq_len;
    ctx.q_blocks = (ctx.q_seq_len + ctx.block_m - 1) / ctx.block_m;
    ctx.block_num = ctx.q_blocks * ctx.heads * ctx.batch;
    ctx.tasks_per_core = (ctx.block_num + MAX_CORES - 1) / MAX_CORES;
    ctx.kv_loops = (ctx.kv_seq_len + BLOCK_N - 1) / BLOCK_N;
    ctx.kv_tail = ctx.kv_seq_len % BLOCK_N;

    // workspace 步长（元素，per-task）
    ctx.ws_s_task = RING * ctx.block_m * BLOCK_N;       // fp32
    ctx.ws_p_task = RING * ctx.block_m * BLOCK_N;       // T
    ctx.ws_o_task = RING * ctx.block_m * ctx.dim_align; // fp32
}

template <typename T>
CATLASS_DEVICE void FaGenBindGm(FaGenContext<T>& ctx, GM_ADDR q_handle, GM_ADDR k_handle, GM_ADDR v_handle,
                                GM_ADDR output_handle, GM_ADDR workspace_s_handle, GM_ADDR workspace_p_handle,
                                GM_ADDR workspace_o_handle)
{
    ctx.q.SetGlobalBuffer((__gm__ T*)q_handle);
    ctx.k.SetGlobalBuffer((__gm__ T*)k_handle);
    ctx.v.SetGlobalBuffer((__gm__ T*)v_handle);
    ctx.output.SetGlobalBuffer((__gm__ T*)output_handle);
    ctx.workspace_s.SetGlobalBuffer((__gm__ float*)workspace_s_handle);
    ctx.workspace_p.SetGlobalBuffer((__gm__ T*)workspace_p_handle);
    ctx.workspace_o.SetGlobalBuffer((__gm__ float*)workspace_o_handle);
}

template <typename T>
CATLASS_DEVICE void FaGenAllocateCube(FaGenContext<T>& ctx, AscendC::TPipe& pipe, FaGenStorage& storage)
{
    const uint32_t q_sz = ctx.block_m * ctx.dim_align * sizeof(T);
    const uint32_t k_sz = BLOCK_N * ctx.dim_align * sizeof(T);
    const uint32_t p_sz = ctx.block_m * BLOCK_N * sizeof(T);
    pipe.InitBuffer(storage.ascend_l1, q_sz + 2 * k_sz + p_sz + k_sz); // k_l1 双槽
    pipe.InitBuffer(storage.ascend_l0a, 65536);
    pipe.InitBuffer(storage.ascend_l0b, 65536);
    pipe.InitBuffer(storage.ascend_l0c, 131072);
}

template <typename T>
CATLASS_DEVICE FaGenUbLayout FaGenMakeUbLayout(const FaGenContext<T>& ctx)
{
    FaGenUbLayout u;
    u.acc_o = 0;
    u.sumexp = u.acc_o + ctx.half_m * ctx.dim_align * 4;
    u.m_i = u.sumexp + ctx.half_m * 4;
    u.alpha_ring = u.m_i + ctx.half_m * 4;
    u.acc_s_ub = u.alpha_ring + RING * ctx.half_m * 4;
    u.mask_col = u.acc_s_ub + ctx.half_m * BLOCK_N * 4;
    u.col_idx = u.mask_col + BLOCK_N * 4;
    u.bound_vec = u.col_idx + BLOCK_N * 4;
    u.tmp = u.bound_vec + ctx.half_m * 4;
    u.m_i_2d = u.tmp + ctx.half_m * 256;
    u.brcb_elems = (ctx.dim_align <= 128) ? ctx.half_m * 8 : 8;
    u.brcb = u.m_i_2d + ctx.half_m * BLOCK_N * 4;
    u.sumexp_i_ring = u.brcb + u.brcb_elems * 4;
    u.acc_s_half = u.sumexp_i_ring + RING * ctx.half_m * 4;
    u.acc_o_ub = u.acc_s_half + ctx.half_m * BLOCK_N * sizeof(T);
    u.base_total = u.acc_o_ub + ctx.half_m * ctx.dim_align * 4;
    u.causal_cmp = u.acc_s_half;
    u.bound_alias = (ctx.dim_align >= 128);
    u.bound_2d = u.bound_alias ? u.acc_o_ub : u.base_total;
    u.after_bound = u.bound_alias ? u.base_total : u.base_total + ctx.half_m * BLOCK_N * 4;
    u.acc_o_half = u.acc_o_ub;
    u.total = u.after_bound;
    return u;
}

template <typename T>
CATLASS_DEVICE void FaGenBindCube(FaGenContext<T>& ctx, FaGenStorage& storage)
{
    const uint32_t q_sz = ctx.block_m * ctx.dim_align * sizeof(T);
    const uint32_t k_sz = BLOCK_N * ctx.dim_align * sizeof(T);
    const uint32_t p_sz = ctx.block_m * BLOCK_N * sizeof(T);
    ctx.q_l1 = storage.ascend_l1.GetWithOffset<T>(ctx.block_m * ctx.dim_align, 0);
    ctx.k_l1 = storage.ascend_l1.GetWithOffset<T>(BLOCK_N * ctx.dim_align, q_sz);
    ctx.k_l1b = storage.ascend_l1.GetWithOffset<T>(BLOCK_N * ctx.dim_align, q_sz + k_sz);
    ctx.acc_s_l1 = storage.ascend_l1.GetWithOffset<T>(ctx.block_m * BLOCK_N, q_sz + 2 * k_sz);
    ctx.v_l1 = storage.ascend_l1.GetWithOffset<T>(BLOCK_N * ctx.dim_align, q_sz + 2 * k_sz + p_sz);

    // L0A/L0B 别名复用：fp32 tile 占满 64KB，QK(lhs/rhs) 与 PV(p/v) 时分复用
    // 同一 buffer；fp16/bf16 分开两半。分档后偏移由"放得下则分开、放不下则别名"决定。
    const uint32_t lhs_sz = ctx.block_m * ctx.cube_k * sizeof(T);
    const uint32_t rhs_sz = ctx.cube_k * BLOCK_N * sizeof(T);
    const uint32_t p_l0_off = (lhs_sz + p_sz <= 65536) ? lhs_sz : 0;
    const uint32_t v_l0_off = (2 * rhs_sz <= 65536) ? rhs_sz : 0;
    ctx.lhs_l0 = storage.ascend_l0a.GetWithOffset<T>(ctx.block_m * ctx.cube_k, 0);
    ctx.p_l0 = storage.ascend_l0a.GetWithOffset<T>(ctx.block_m * BLOCK_N, p_l0_off);
    ctx.rhs_l0 = storage.ascend_l0b.GetWithOffset<T>(ctx.cube_k * BLOCK_N, 0);
    ctx.v_l0 = storage.ascend_l0b.GetWithOffset<T>(BLOCK_N * ctx.cube_k, v_l0_off);
    ctx.acc_s_l0c = storage.ascend_l0c.GetWithOffset<float>(ctx.block_m * BLOCK_N, 0);
    ctx.acc_o_l0c = storage.ascend_l0c.GetWithOffset<float>(ctx.block_m * ctx.cube_k, ctx.block_m * BLOCK_N * 4);
}

template <typename T>
CATLASS_DEVICE void FaGenBindVector(FaGenContext<T>& ctx, FaGenStorage& storage, const FaGenUbLayout& u)
{
    ctx.acc_o = storage.ascend_ub.GetWithOffset<float>(ctx.half_m * ctx.dim_align, u.acc_o);
    ctx.sumexp = storage.ascend_ub.GetWithOffset<float>(ctx.half_m, u.sumexp);
    ctx.m_i = storage.ascend_ub.GetWithOffset<float>(ctx.half_m, u.m_i);
    ctx.alpha_ring = storage.ascend_ub.GetWithOffset<float>(RING * ctx.half_m, u.alpha_ring);
    ctx.acc_s_ub = storage.ascend_ub.GetWithOffset<float>(ctx.half_m * BLOCK_N, u.acc_s_ub);
    ctx.mask_col = storage.ascend_ub.GetWithOffset<float>(BLOCK_N, u.mask_col);
    ctx.col_idx = storage.ascend_ub.GetWithOffset<float>(BLOCK_N, u.col_idx);
    ctx.bound_vec = storage.ascend_ub.GetWithOffset<float>(ctx.half_m, u.bound_vec);
    ctx.tmp_ub = storage.ascend_ub.GetWithOffset<uint8_t>(ctx.half_m * 256, u.tmp);
    ctx.m_i_2d = storage.ascend_ub.GetWithOffset<float>(ctx.half_m * BLOCK_N, u.m_i_2d);
    ctx.brcb_tmp = storage.ascend_ub.GetWithOffset<float>(u.brcb_elems, u.brcb);
    ctx.sumexp_i_ring = storage.ascend_ub.GetWithOffset<float>(RING * ctx.half_m, u.sumexp_i_ring);
    ctx.acc_s_half = storage.ascend_ub.GetWithOffset<T>(ctx.half_m * BLOCK_N, u.acc_s_half);
    ctx.acc_o_ub = storage.ascend_ub.GetWithOffset<float>(ctx.half_m * ctx.dim_align, u.acc_o_ub);
    ctx.acc_o_half = storage.ascend_ub.GetWithOffset<T>(ctx.half_m * ctx.dim_align, u.acc_o_half);
    ctx.causal_cmp = storage.ascend_ub.GetWithOffset<uint8_t>(ctx.half_m * BLOCK_N, u.causal_cmp);
    ctx.bound_2d = storage.ascend_ub.GetWithOffset<float>(ctx.half_m * BLOCK_N, u.bound_2d);
}

template <typename T>
CATLASS_DEVICE FaGenTask FaGenMakeTask(const FaGenContext<T>& ctx, int64_t task_idx)
{
    FaGenTask task;
    task.bx = task_idx % ctx.q_blocks;
    task.by = (task_idx / ctx.q_blocks) % ctx.heads;
    task.bz = task_idx / ctx.q_blocks / ctx.heads;
    task.q_base = ((task.bz * ctx.heads + task.by) * ctx.q_seq_len + task.bx * ctx.block_m) * ctx.dim;
    task.kv_base = (task.bz * ctx.heads + task.by) * ctx.kv_seq_len * ctx.dim;
    task.ws_s_base = task_idx * ctx.ws_s_task;
    task.ws_p_base = task_idx * ctx.ws_p_task;
    task.ws_o_base = task_idx * ctx.ws_o_task;
    task.q_tail_m = min64(ctx.block_m, ctx.q_seq_len - task.bx * ctx.block_m);
    return task;
}

template <typename T>
CATLASS_DEVICE void FaGenBeginTask(FaGenContext<T>& ctx, const FaGenTask& task)
{
    if ASCEND_IS_AIC {
        FaGenC0LoadQ(ctx, task.q_base, task.q_tail_m);
        // preload：K 槽信用预置 + 预加载 K(0) 到槽 0
        AscendC::SetFlag<AscendC::HardEvent::MTE1_MTE2>(0); // K 槽 0 空闲
        AscendC::SetFlag<AscendC::HardEvent::MTE1_MTE2>(1); // K 槽 1 空闲
        AscendC::WaitFlag<AscendC::HardEvent::MTE1_MTE2>(0);
        fa_dyn::copy_gm_to_l1_dyn<T>(ctx.k_l1[0], ctx.k[task.kv_base], BLOCK_N, ctx.dim_align, ctx.dim,
                                     min64(BLOCK_N, ctx.kv_seq_len), ctx.dim, true);
        AscendC::SetFlag<AscendC::HardEvent::MTE2_MTE1>(0); // K 槽 0 就绪
    }
    if ASCEND_IS_AIV {
        FaGenV0Init(ctx);
    }
}

template <typename T>
CATLASS_DEVICE void FaGenProduce(FaGenContext<T>& ctx, const FaGenTask& task, int64_t t, int64_t vid)
{
    if (t < ctx.kv_loops) {
        const int64_t slot = t % RING;
        if ASCEND_IS_AIC {
            FaGenC1(ctx, task.kv_base, task.ws_s_base, slot, t);
        }
        if ASCEND_IS_AIV {
            FaGenV1(ctx, task.ws_s_base, task.ws_p_base, slot, t, vid, task.bx);
        }
    }
}

template <typename T>
CATLASS_DEVICE void FaGenConsume(FaGenContext<T>& ctx, const FaGenTask& task, int64_t t, int64_t vid)
{
    if (PRELAUNCH <= t) {
        const int64_t tc = t - PRELAUNCH;
        const int64_t slot_c = tc % RING;
        if ASCEND_IS_AIC {
            FaGenC2(ctx, task.kv_base, task.ws_p_base, task.ws_o_base, slot_c, tc);
        }
        if ASCEND_IS_AIV {
            FaGenV2(ctx, task.ws_o_base, slot_c, tc, vid);
        }
    }
}

template <typename T>
CATLASS_DEVICE void FaGenDrain(FaGenContext<T>& ctx, int64_t t)
{
    // ring 尾定向 drain（替代哨兵 PIPE_ALL）
    if ASCEND_IS_AIC {
        if (t < ctx.kv_loops) {
            AscendC::WaitFlag<AscendC::HardEvent::M_MTE1>(3);
            AscendC::WaitFlag<AscendC::HardEvent::FIX_M>(3);
        }
        if (PRELAUNCH <= t) {
            const int64_t now_k = t - PRELAUNCH;
            if (now_k < ctx.kv_loops) {
                AscendC::WaitFlag<AscendC::HardEvent::M_MTE1>(5);
                AscendC::WaitFlag<AscendC::HardEvent::FIX_M>(4);
                AscendC::WaitFlag<AscendC::HardEvent::MTE1_MTE2>(4);
            }
        }
    }
}

template <typename T>
CATLASS_DEVICE void FaGenEndTask(FaGenContext<T>& ctx, const FaGenTask& task, int64_t vid)
{
    // task 尾 drain：K 槽 0/1 空闲信用清零（每槽残留 1 个 set）
    if ASCEND_IS_AIC {
        AscendC::WaitFlag<AscendC::HardEvent::MTE1_MTE2>(0);
        AscendC::WaitFlag<AscendC::HardEvent::MTE1_MTE2>(1);
    }
    if ASCEND_IS_AIV {
        FaGenEpilogue(ctx, task.bx, vid, task.q_base);
    }
}

template <typename T>
CATLASS_DEVICE void FaGenRunTask(FaGenContext<T>& ctx, int64_t task_idx, int64_t vid)
{
    const FaGenTask task = FaGenMakeTask(ctx, task_idx);
    FaGenBeginTask(ctx, task);
    for (int64_t t = 0; t < ctx.kv_loops + PRELAUNCH; ++t) {
        FaGenProduce(ctx, task, t, vid);
        FaGenConsume(ctx, task, t, vid);
        FaGenDrain(ctx, t);
    }
    FaGenEndTask(ctx, task, vid);
}

template <typename T>
CATLASS_DEVICE void FaGenRunTasks(FaGenContext<T>& ctx, int64_t cid, int64_t vid)
{
    for (int64_t local_idx = 0; local_idx < ctx.tasks_per_core; ++local_idx) {
        AscendC::PipeBarrier<PIPE_ALL>();
        const int64_t task_idx = cid * ctx.tasks_per_core + local_idx;
        if (task_idx < ctx.block_num) {
            FaGenRunTask(ctx, task_idx, vid);
        }
        AscendC::PipeBarrier<PIPE_ALL>();
    }
}

} // namespace fa_gen

template <typename T>
CATLASS_DEVICE void fa_fwd_run(GM_ADDR q_handle, GM_ADDR k_handle, GM_ADDR v_handle, GM_ADDR output_handle,
                               GM_ADDR workspace_s_handle, GM_ADDR workspace_p_handle, GM_ADDR workspace_o_handle,
                               GM_ADDR tiling_handle)
{
    using namespace fa_gen;
    FaGenContext<T> ctx;
    FaGenInitShape(ctx, tiling_handle);
    AscendC::TPipe pipe;
    FaGenStorage storage;
    FaGenBindGm(ctx, q_handle, k_handle, v_handle, output_handle, workspace_s_handle, workspace_p_handle,
                workspace_o_handle);
    FaGenAllocateCube(ctx, pipe, storage);
    const FaGenUbLayout u = FaGenMakeUbLayout(ctx);
    pipe.InitBuffer(storage.ascend_ub, u.total);
    pipe.Destroy();
    auto cid = AscendC::GetBlockIdx();
    if ASCEND_IS_AIV {
        cid = cid / 2;
    }
    auto vid = AscendC::GetSubBlockIdx();
    FaGenBindCube(ctx, storage);
    FaGenBindVector(ctx, storage, u);
    FaGenRunTasks(ctx, cid, vid);
}

#endif // FA_GEN_KERNEL_H
